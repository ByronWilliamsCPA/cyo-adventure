"""Unit tests for the authoring-plan service (validation, warnings, job creation)."""

from __future__ import annotations

import random
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api.schemas import AuthoringPlanRequest
from cyo_adventure.core.exceptions import StateTransitionError, ValidationError
from cyo_adventure.db.models import Concept, GenerationJob, StoryRequest
from cyo_adventure.diversity.query import DifferentiationLevel, SimilarityContext
from cyo_adventure.events import Actor
from cyo_adventure.generation.skeleton_match import select_skeleton_for_cell
from cyo_adventure.story_requests.authoring_plan import (
    build_authoring_plan,
    eligibility_warnings,
)

# In-cell candidate lists (sorted, as candidates_for_cell returns them) for the
# two cells these tests exercise. Each cell now holds three production
# skeletons, and the pick within a cell is a weighted-random draw over an
# unseedable SystemRandom, so tests assert membership in the cell rather than a
# single fixed slug.
_CELL_8_11_SHORT_PROSE = [
    "the-cave-of-echoes",
    "the-locked-carousel",
    "the-robot-fair-sabotage",
]
_CELL_13_16_MEDIUM_PROSE = [
    "the-conservatory-wars",
    "the-signal-in-the-static",
    "the-undertow-season",
]


class _FakeResult:
    """A no-op result for the recent-usage query; every test starts with no history."""

    def all(self) -> list[tuple[str | None]]:
        return []


class _FakeSession:
    """Minimal async session double for build_authoring_plan.

    build_authoring_plan now makes up to two scalar() calls in sequence: the
    idempotency lookup first, then (for mechanism='automated_provider') the
    allowlist check inside is_enabled_allowlist_pair. This fake dispatches by
    call order rather than inspecting the statement, mirroring the file's
    existing "ignore the statement" style. ``execute`` backs the recency
    query inside recent_skeleton_usage (WS-C PR2); every unit test starts
    with no history.
    """

    def __init__(
        self, *, existing_job: GenerationJob | None = None, allowlisted: bool = True
    ) -> None:
        self._existing_job = existing_job
        self._allowlisted = allowlisted
        self._scalar_calls = 0
        self.added: list[object] = []

    async def scalar(self, statement: object) -> object:
        """Return the existing-job seed first, then the allowlist stub."""
        _ = statement
        self._scalar_calls += 1
        if self._scalar_calls == 1:
            return self._existing_job
        return object() if self._allowlisted else None

    async def execute(self, statement: object) -> _FakeResult:
        """Return an empty recency result; every unit test starts with no history."""
        _ = statement
        return _FakeResult()

    def add(self, obj: object) -> None:
        """Record an added ORM instance."""
        self.added.append(obj)

    async def flush(self) -> None:
        """Assign a UUID to any tracked object still missing an id."""
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()  # pyright: ignore[reportAttributeAccessIssue]


def _concept(band: str = "8-11") -> Concept:
    return Concept(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        brief={"age_band": band, "premise": "a fox finds a lantern"},
    )


def _request() -> StoryRequest:
    return StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a fox",
        status="approved",
    )


def _admin_actor() -> Actor:
    """Build the admin Actor that assigns the authoring plan in these tests."""
    return Actor(actor_id=uuid.uuid4(), actor_role="admin")


@pytest.mark.asyncio
async def test_fresh_generation_automated_provider_creates_queued_job() -> None:
    """The unchanged path: a queued job, no skeleton, no warnings."""
    session = _FakeSession()
    concept = _concept()
    result = await build_authoring_plan(
        session,
        _request(),
        concept,
        AuthoringPlanRequest(
            method="fresh_generation",
            mechanism="automated_provider",
            prep_model="openrouter/some-model",
            provider="anthropic",
            model="claude-sonnet-4-6",
        ),
        actor=_admin_actor(),
    )
    assert result.job.status == "queued"
    assert result.job.concept_id == concept.id
    assert result.skeleton_slug is None
    assert result.warnings == []
    # Pin the metadata SHAPE: a fresh_generation automated_provider job carries
    # ONLY provider/model (no skeleton_slug), which is exactly what keeps the
    # worker routing it to generate_story rather than skeleton fill.
    assert result.job.authoring_metadata == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    }


@pytest.mark.asyncio
async def test_skeleton_fill_skill_parks_job_with_metadata() -> None:
    """The new path: an awaiting_manual_fill job carrying skeleton + theme_brief."""
    session = _FakeSession()
    concept = _concept("8-11")
    result = await build_authoring_plan(
        session,
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
        actor=_admin_actor(),
    )
    assert result.job.status == "awaiting_manual_fill"
    assert result.skeleton_slug in _CELL_8_11_SHORT_PROSE
    assert result.job.authoring_metadata == {
        "skeleton_slug": result.skeleton_slug,
        "skeleton_band": "8-11",
        "theme_brief": concept.brief,
        "review_stage1_model": None,
        "review_stage2_model": None,
    }


def test_fresh_generation_with_skill_mechanism_is_rejected() -> None:
    """mechanism='skill' only makes sense with method='skeleton_fill'.

    The illegal pairing is now unrepresentable: the schema-level
    model_validator rejects it at construction (a pydantic ValidationError ->
    FastAPI 422), so it never reaches build_authoring_plan.
    """
    with pytest.raises(PydanticValidationError):
        AuthoringPlanRequest(
            method="fresh_generation", mechanism="skill", prep_model="sonnet"
        )


@pytest.mark.asyncio
async def test_skeleton_fill_automated_provider_creates_queued_job_with_metadata() -> (
    None
):
    """Plan 2: automated skeleton-fill prep is now supported and queued."""
    session = _FakeSession()
    concept = _concept("8-11")
    plan = AuthoringPlanRequest(
        method="skeleton_fill",
        mechanism="automated_provider",
        prep_model="openrouter/some-model",
        provider="anthropic",
        model="claude-sonnet-4-6",
    )
    result = await build_authoring_plan(
        session, _request(), concept, plan, actor=_admin_actor()
    )
    assert result.job.status == "queued"
    assert result.skeleton_slug in _CELL_8_11_SHORT_PROSE
    assert result.job.authoring_metadata == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "skeleton_slug": result.skeleton_slug,
        "skeleton_band": "8-11",
        "theme_brief": concept.brief,
        "review_stage1_model": None,
        "review_stage2_model": None,
    }


@pytest.mark.asyncio
async def test_unrecognized_skill_model_is_rejected() -> None:
    """prep_model must be a real Claude Code session model for mechanism='skill'."""
    session = _FakeSession()
    with pytest.raises(ValidationError):
        await build_authoring_plan(
            session,
            _request(),
            _concept(),
            AuthoringPlanRequest(
                method="skeleton_fill", mechanism="skill", prep_model="gpt-4o"
            ),
            actor=_admin_actor(),
        )


@pytest.mark.asyncio
async def test_existing_job_for_concept_is_conflict() -> None:
    """A second authoring-plan call for the same concept is a 409, not a duplicate job."""
    concept = _concept()
    existing = GenerationJob(id=uuid.uuid4(), concept_id=concept.id, status="queued")
    session = _FakeSession(existing_job=existing)
    with pytest.raises(StateTransitionError):
        await build_authoring_plan(
            session,
            _request(),
            concept,
            AuthoringPlanRequest(
                method="fresh_generation",
                mechanism="automated_provider",
                prep_model="openrouter/some-model",
                provider="anthropic",
                model="claude-sonnet-4-6",
            ),
            actor=_admin_actor(),
        )


@pytest.mark.asyncio
async def test_no_matching_skeleton_for_band_is_rejected() -> None:
    """A band with no skeleton directory at all yields a 422, not a crash."""
    session = _FakeSession()
    with pytest.raises(ValidationError):
        await build_authoring_plan(
            session,
            _request(),
            _concept("99-100"),
            AuthoringPlanRequest(
                method="skeleton_fill", mechanism="skill", prep_model="sonnet"
            ),
            actor=_admin_actor(),
        )


def test_eligibility_warnings_flags_haiku_on_hard_band() -> None:
    """haiku + a 10-13/13-16/16+ band skeleton_fill gets a non-blocking warning."""
    warnings = eligibility_warnings("skeleton_fill", "skill", "13-16", "haiku")
    assert len(warnings) == 1
    assert "haiku" in warnings[0]


def test_eligibility_warnings_silent_for_stronger_model() -> None:
    """The same band with opus produces no warning."""
    assert eligibility_warnings("skeleton_fill", "skill", "13-16", "opus") == []


def test_eligibility_warnings_silent_for_easy_band() -> None:
    """haiku on an easy band (8-11) produces no warning."""
    assert eligibility_warnings("skeleton_fill", "skill", "8-11", "haiku") == []


def test_automated_provider_requires_both_provider_and_model() -> None:
    """provider and model are both required at the schema boundary when
    mechanism='automated_provider'."""
    with pytest.raises(PydanticValidationError):
        AuthoringPlanRequest(
            method="fresh_generation",
            mechanism="automated_provider",
            prep_model="openrouter/some-model",
            provider="anthropic",
            # model omitted
        )


def test_provider_model_rejected_when_mechanism_not_automated_provider() -> None:
    """provider/model set on a mechanism='skill' request is rejected, not
    silently dropped: the inverse of the required-together rule so no invalid
    combination is representable at the boundary."""
    with pytest.raises(PydanticValidationError):
        AuthoringPlanRequest(
            method="skeleton_fill",
            mechanism="skill",
            prep_model="sonnet",
            provider="anthropic",
            model="claude-sonnet-4-6",
        )


@pytest.mark.asyncio
async def test_unallowlisted_provider_model_is_rejected() -> None:
    """A provider/model pair that is not an enabled allowlist row is a 422."""
    session = _FakeSession(allowlisted=False)
    with pytest.raises(ValidationError):
        await build_authoring_plan(
            session,
            _request(),
            _concept(),
            AuthoringPlanRequest(
                method="fresh_generation",
                mechanism="automated_provider",
                prep_model="openrouter/some-model",
                provider="anthropic",
                model="not-a-real-model",
            ),
            actor=_admin_actor(),
        )


@pytest.mark.asyncio
async def test_skeleton_fill_populates_alternatives() -> None:
    """The result carries every in-cell candidate, not just the pick."""
    session = _FakeSession()
    concept = _concept("8-11")
    result = await build_authoring_plan(
        session,
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
        actor=_admin_actor(),
    )
    # 8-11/short/prose now has three production skeletons; the result carries
    # the full sorted cell and the pick is one of them.
    assert result.skeleton_alternatives == _CELL_8_11_SHORT_PROSE
    assert result.skeleton_slug in _CELL_8_11_SHORT_PROSE


@pytest.mark.asyncio
async def test_fresh_generation_has_no_alternatives() -> None:
    session = _FakeSession()
    result = await build_authoring_plan(
        session,
        _request(),
        _concept(),
        AuthoringPlanRequest(
            method="fresh_generation",
            mechanism="automated_provider",
            prep_model="openrouter/some-model",
            provider="anthropic",
            model="claude-sonnet-4-6",
        ),
        actor=_admin_actor(),
    )
    assert result.skeleton_alternatives == []


@pytest.mark.asyncio
async def test_skeleton_fill_honors_unconstrained_override() -> None:
    """An out-of-cell override is accepted with a warning, never blocked."""
    session = _FakeSession()
    concept = _concept("8-11")
    plan = AuthoringPlanRequest(
        method="skeleton_fill",
        mechanism="skill",
        prep_model="sonnet",
        skeleton_slug="the-sunspire-ascent",  # a real 13-16/medium/gamebook skeleton
    )
    result = await build_authoring_plan(
        session, _request(), concept, plan, actor=_admin_actor()
    )
    assert result.skeleton_slug == "the-sunspire-ascent"
    assert any("outside the request's cell" in w for w in result.warnings)
    # C1: the override's REAL band (13-16), not the request's band (8-11), is
    # persisted, so the fill paths later look for skeletons/13-16/... .
    assert result.job.authoring_metadata is not None
    assert result.job.authoring_metadata["skeleton_band"] == "13-16"


@pytest.mark.asyncio
async def test_skeleton_fill_weighted_pick_persists_request_band() -> None:
    """The non-override (weighted) path stores the request's own band."""
    session = _FakeSession()
    concept = _concept("8-11")
    result = await build_authoring_plan(
        session,
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
        actor=_admin_actor(),
    )
    assert result.job.authoring_metadata is not None
    assert result.job.authoring_metadata["skeleton_band"] == "8-11"


@pytest.mark.asyncio
async def test_skeleton_fill_override_unknown_slug_is_rejected() -> None:
    session = _FakeSession()
    with pytest.raises(ValidationError):
        await build_authoring_plan(
            session,
            _request(),
            _concept("8-11"),
            AuthoringPlanRequest(
                method="skeleton_fill",
                mechanism="skill",
                prep_model="sonnet",
                skeleton_slug="does-not-exist-anywhere",
            ),
            actor=_admin_actor(),
        )


@pytest.mark.asyncio
async def test_skeleton_fill_null_length_falls_back_to_short() -> None:
    """concept.brief with no "length" key at all still forms a cell (decision 3)."""
    session = _FakeSession()
    concept = Concept(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        brief={"age_band": "8-11", "premise": "a fox finds a lantern"},
    )
    result = await build_authoring_plan(
        session,
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
        actor=_admin_actor(),
    )
    assert result.skeleton_slug in _CELL_8_11_SHORT_PROSE


@pytest.mark.asyncio
async def test_skeleton_fill_teen_band_null_length_falls_back_to_medium() -> None:
    """M1: a teen-band request with no length matches a real medium skeleton.

    13-16 has no "short" production skeleton, so the pre-fix default ("short")
    hits the empty-cell 422 for every null-length teen request; "medium" does
    not, and picks a real skeleton for the cell.
    """
    session = _FakeSession()
    concept = Concept(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        brief={"age_band": "13-16", "premise": "a teen finds a signal"},
    )
    result = await build_authoring_plan(
        session,
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
        actor=_admin_actor(),
    )
    # 13-16/medium/prose now has three production skeletons; the pick is one.
    assert result.skeleton_slug in _CELL_13_16_MEDIUM_PROSE


@pytest.mark.asyncio
async def test_skeleton_fill_empty_cell_override_succeeds() -> None:
    """B1 headline: a valid admin override for a request whose OWN cell is empty
    must NOT hit the empty-cell 422 (decision C-6, unconstrained override).

    The request's cell ("99-100" has no skeleton directory at all) is empty, so
    the auto-pick path would 422; but a valid override slug names a real
    skeleton in another band and is accepted. The same empty cell WITHOUT an
    override still 422s.
    """
    concept = _concept("99-100")
    result = await build_authoring_plan(
        _FakeSession(),
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill",
            mechanism="skill",
            prep_model="sonnet",
            skeleton_slug="the-cave-of-echoes",  # a real 8-11 skeleton
        ),
        actor=_admin_actor(),
    )
    assert result.skeleton_slug == "the-cave-of-echoes"
    assert result.job.authoring_metadata is not None
    # The override's REAL band (8-11) is persisted, not the request's empty cell.
    assert result.job.authoring_metadata["skeleton_band"] == "8-11"
    # The in-cell candidate list stays empty: the override is out-of-cell.
    assert result.skeleton_alternatives == []
    assert any("outside the request's cell" in w for w in result.warnings)

    # Same empty cell, NO override -> the empty-cell 422 still fires.
    with pytest.raises(ValidationError):
        await build_authoring_plan(
            _FakeSession(),
            _request(),
            _concept("99-100"),
            AuthoringPlanRequest(
                method="skeleton_fill", mechanism="skill", prep_model="sonnet"
            ),
            actor=_admin_actor(),
        )


@pytest.mark.asyncio
async def test_skeleton_fill_defaulted_length_appends_warning() -> None:
    """F6: coercing an absent request length to a default surfaces a
    non-blocking warning (warn, never block)."""
    concept = Concept(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        brief={"age_band": "13-16", "premise": "a teen finds a signal"},
    )
    result = await build_authoring_plan(
        _FakeSession(),
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
        actor=_admin_actor(),
    )
    assert any("defaulted to 'medium'" in w for w in result.warnings)
    assert result.skeleton_slug in _CELL_13_16_MEDIUM_PROSE


@pytest.mark.asyncio
async def test_skeleton_fill_specified_length_no_default_warning() -> None:
    """F6 inverse: an explicit request length adds no defaulted-length warning."""
    concept = Concept(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        brief={
            "age_band": "8-11",
            "length": "short",
            "premise": "a fox finds a lantern",
        },
    )
    result = await build_authoring_plan(
        _FakeSession(),
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
        actor=_admin_actor(),
    )
    assert not any("defaulted to" in w for w in result.warnings)
    assert result.skeleton_slug in _CELL_8_11_SHORT_PROSE


def _sim_ctx(
    *,
    similar_count_per_slug: dict[str, int],
    recommendation: DifferentiationLevel,
) -> SimilarityContext:
    """Build a SimilarityContext for mocking `similarity_context` (WS-4).

    Only `similar_count_per_slug` and `recommendation` matter to
    build_authoring_plan's auto-pick path; the other fields are filled with
    innocuous defaults since nothing under test reads them.
    """
    return SimilarityContext(
        neighbors=(),
        cell_theme_saturation=0.0,
        used_slugs=frozenset(),
        similar_count_per_slug=similar_count_per_slug,
        recommendation=recommendation,
    )


def _short_prose_8_11_concept() -> Concept:
    """A concept with an explicit length, so no defaulted-length warning
    pollutes the WS-4 warnings assertions below."""
    return Concept(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        brief={
            "age_band": "8-11",
            "length": "short",
            "premise": "a fox finds a lantern",
        },
    )


@pytest.mark.asyncio
async def test_skeleton_fill_auto_pick_passes_similar_usage_to_selection() -> None:
    """WS-4: the auto-pick path threads similarity_context's per-slug similar
    counts into select_skeleton_for_cell, de-weighting a saturated slug -- the
    same seed with and without similar_usage picks differently."""
    saturated_slug = _CELL_8_11_SHORT_PROSE[0]
    similar_counts = {saturated_slug: 5}
    ctx = _sim_ctx(
        similar_count_per_slug=similar_counts,
        recommendation=DifferentiationLevel.TREE,
    )
    session = _FakeSession()
    concept = _short_prose_8_11_concept()
    with (
        patch(
            "cyo_adventure.story_requests.authoring_plan.similarity_context",
            new=AsyncMock(return_value=ctx),
        ),
        patch(
            "cyo_adventure.story_requests.authoring_plan.random.SystemRandom",
            new=lambda: random.Random(42),
        ),
    ):
        result = await build_authoring_plan(
            session,
            _request(),
            concept,
            AuthoringPlanRequest(
                method="skeleton_fill", mechanism="skill", prep_model="sonnet"
            ),
            actor=_admin_actor(),
        )
    expected = select_skeleton_for_cell(
        _CELL_8_11_SHORT_PROSE,
        {},
        random.Random(42),
        similar_usage=similar_counts,
    )
    assert result.skeleton_slug == expected.slug
    # The blended weighting must pick differently from the legacy (no
    # similar_usage) pick under the identical seed, proving the counts were
    # actually threaded through rather than ignored: uniform weights consume
    # the RNG's draw differently than [0.0625, 1, 1].
    legacy = select_skeleton_for_cell(_CELL_8_11_SHORT_PROSE, {}, random.Random(42))
    assert legacy.slug != result.skeleton_slug


@pytest.mark.asyncio
async def test_skeleton_fill_auto_pick_tree_adds_no_warning() -> None:
    """DifferentiationLevel.TREE (plenty of untouched trees) adds no warning."""
    ctx = _sim_ctx(
        similar_count_per_slug=dict.fromkeys(_CELL_8_11_SHORT_PROSE, 0),
        recommendation=DifferentiationLevel.TREE,
    )
    session = _FakeSession()
    concept = _short_prose_8_11_concept()
    with patch(
        "cyo_adventure.story_requests.authoring_plan.similarity_context",
        new=AsyncMock(return_value=ctx),
    ):
        result = await build_authoring_plan(
            session,
            _request(),
            concept,
            AuthoringPlanRequest(
                method="skeleton_fill", mechanism="skill", prep_model="sonnet"
            ),
            actor=_admin_actor(),
        )
    assert result.warnings == []


@pytest.mark.asyncio
async def test_skeleton_fill_auto_pick_leaf_saturation_warns_and_logs() -> None:
    """DifferentiationLevel.LEAF (cell exhausted for this theme) appends the
    leaf-differentiation warning and emits the saturation log line."""
    ctx = _sim_ctx(
        similar_count_per_slug=dict.fromkeys(_CELL_8_11_SHORT_PROSE, 1),
        recommendation=DifferentiationLevel.LEAF,
    )
    session = _FakeSession()
    concept = _short_prose_8_11_concept()
    logged: list[tuple[str, dict[str, object]]] = []

    class _CapturingLogger:
        def info(self, event: str, **kwargs: object) -> None:
            logged.append((event, kwargs))

    with (
        patch(
            "cyo_adventure.story_requests.authoring_plan.similarity_context",
            new=AsyncMock(return_value=ctx),
        ),
        patch(
            "cyo_adventure.story_requests.authoring_plan.logger", new=_CapturingLogger()
        ),
    ):
        result = await build_authoring_plan(
            session,
            _request(),
            concept,
            AuthoringPlanRequest(
                method="skeleton_fill", mechanism="skill", prep_model="sonnet"
            ),
            actor=_admin_actor(),
        )
    assert any(
        "already been used for a similar-theme story" in w for w in result.warnings
    )
    assert any("relying on leaf-level differentiation" in w for w in result.warnings)
    assert len(logged) == 1
    event, kwargs = logged[0]
    assert event == "selection.cell_theme_saturated"
    assert kwargs["band"] == "8-11"
    assert kwargs["level"] == "leaf"


@pytest.mark.asyncio
async def test_skeleton_fill_auto_pick_catalog_saturation_warns_and_logs() -> None:
    """DifferentiationLevel.CATALOG (multiple similar-theme uses per skeleton)
    appends the catalog-growth warning and emits the saturation log line."""
    ctx = _sim_ctx(
        similar_count_per_slug=dict.fromkeys(_CELL_8_11_SHORT_PROSE, 2),
        recommendation=DifferentiationLevel.CATALOG,
    )
    session = _FakeSession()
    concept = _short_prose_8_11_concept()
    logged: list[tuple[str, dict[str, object]]] = []

    class _CapturingLogger:
        def info(self, event: str, **kwargs: object) -> None:
            logged.append((event, kwargs))

    with (
        patch(
            "cyo_adventure.story_requests.authoring_plan.similarity_context",
            new=AsyncMock(return_value=ctx),
        ),
        patch(
            "cyo_adventure.story_requests.authoring_plan.logger", new=_CapturingLogger()
        ),
    ):
        result = await build_authoring_plan(
            session,
            _request(),
            concept,
            AuthoringPlanRequest(
                method="skeleton_fill", mechanism="skill", prep_model="sonnet"
            ),
            actor=_admin_actor(),
        )
    assert any("saturated for this theme" in w for w in result.warnings)
    assert any(
        "consider authoring a new skeleton for the cell" in w for w in result.warnings
    )
    assert len(logged) == 1
    event, kwargs = logged[0]
    assert event == "selection.cell_theme_saturated"
    assert kwargs["level"] == "catalog"


@pytest.mark.asyncio
async def test_skeleton_fill_auto_pick_family_id_none_is_unchanged() -> None:
    """WS-4 backward compat: family_id=None (admin/catalog request) short-
    circuits similarity_context's history load to empty, so every similar
    count is zero and no saturation warning appears -- identical to the
    pre-WS-4 behavior. Uses the real similarity_context (not mocked)."""
    session = _FakeSession()
    concept = _short_prose_8_11_concept()
    request = StoryRequest(
        family_id=None,
        profile_id=uuid.uuid4(),
        request_text="a fox",
        status="approved",
    )
    result = await build_authoring_plan(
        session,
        request,
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
        actor=_admin_actor(),
    )
    assert result.skeleton_slug in _CELL_8_11_SHORT_PROSE
    assert result.warnings == []
