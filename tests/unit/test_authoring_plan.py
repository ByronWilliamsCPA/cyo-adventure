"""Unit tests for the authoring-plan service (validation, warnings, job creation)."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api.schemas import AuthoringPlanRequest
from cyo_adventure.core.exceptions import StateTransitionError, ValidationError
from cyo_adventure.db.models import Concept, GenerationJob, StoryRequest
from cyo_adventure.events import Actor
from cyo_adventure.story_requests.authoring_plan import (
    build_authoring_plan,
    eligibility_warnings,
)

pytestmark = pytest.mark.asyncio


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
    assert result.skeleton_slug == "the-cave-of-echoes"
    assert result.job.authoring_metadata == {
        "skeleton_slug": "the-cave-of-echoes",
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
    assert result.skeleton_slug == "the-cave-of-echoes"
    assert result.job.authoring_metadata == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "skeleton_slug": "the-cave-of-echoes",
        "skeleton_band": "8-11",
        "theme_brief": concept.brief,
        "review_stage1_model": None,
        "review_stage2_model": None,
    }


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
    # 8-11/short/prose has exactly one production skeleton on disk today.
    assert result.skeleton_alternatives == ["the-cave-of-echoes"]
    assert result.skeleton_slug == "the-cave-of-echoes"


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
    assert result.skeleton_slug == "the-cave-of-echoes"


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
    # 13-16/medium/prose has exactly one production skeleton on disk today.
    assert result.skeleton_slug == "the-signal-in-the-static"
