"""Unit tests for the child story-request feature (model, brief, screening)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.api.schemas import (
    InterpretedElementView,
    RequestInterpretationView,
)
from cyo_adventure.api.story_requests import _to_view
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    Family,
    GenerationJob,
    Series,
    StoryRequest,
)
from cyo_adventure.generation.concept import AnchorContext, ConceptBrief
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.moderation.thresholds import ThresholdPolicy
from cyo_adventure.story_requests import service
from cyo_adventure.story_requests.brief import brief_from_request
from cyo_adventure.story_requests.interpretation import build_general_interpretation
from cyo_adventure.story_requests.screening import screen_request_text
from cyo_adventure.story_requests.service import ApprovalConfirmation
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle


@dataclass(frozen=True, slots=True)
class _FakeFlag:
    """Minimal screening-flag stand-in (only ``.category`` is read)."""

    category: str


@dataclass(frozen=True, slots=True)
class _FakeScreening:
    """Minimal ScreeningResult stand-in for build_general_interpretation.

    Only ``.blocked`` and ``.flags`` are read by the general layer (the flags
    sequence is empty here, so no advisory elements are produced).
    """

    blocked: bool
    flags: tuple[_FakeFlag, ...] = ()


def test_story_request_defaults_to_pending() -> None:
    """A newly constructed StoryRequest has status 'pending'."""
    req = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        age_band="8-11",
    )
    assert req.status == "pending"
    assert req.moderation_flags is None
    assert req.reviewed_by is None
    assert req.concept_id is None


def _profile(age_band: str = "8-11", cap: float = 99.0) -> ChildProfile:
    return ChildProfile(
        family_id=uuid.uuid4(),
        display_name="Emma",
        age_band=age_band,
        reading_level_cap=cap,
    )


def test_brief_from_request_uses_band_budget_and_generic_protagonist() -> None:
    """The brief inherits band node/ending budgets and a generic protagonist."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        age_band="8-11",
        length="short",
    )
    brief = brief_from_request(request, _profile("8-11"))
    assert isinstance(brief, ConceptBrief)
    assert brief.premise == "a story about a brave fox"
    assert brief.age_band == AgeBand.BAND_8_11
    assert brief.length == Length.SHORT
    assert brief.narrative_style == NarrativeStyle.PROSE
    assert brief.target_node_count == 15  # band_profile 8-11 min_nodes
    assert brief.ending_count == 3  # band_profile 8-11 min_endings
    assert brief.protagonist.name == "Explorer"  # never a real child name
    assert brief.tier == 1


def test_brief_from_request_band_comes_from_request_not_profile() -> None:
    """The flip: a request band different from the profile band wins."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a mystery",
        status="pending",
        age_band="10-13",
    )
    brief = brief_from_request(request, _profile("8-11"))
    assert brief.age_band == AgeBand.BAND_10_13


def test_brief_from_request_without_profile_uses_band_reading_target() -> None:
    """A profile-less request (PR 2 flows) gets the band FK target."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        request_text="a space story",
        status="pending",
        age_band="8-11",
    )
    brief = brief_from_request(request, None)
    assert brief.reading_level_target == pytest.approx(4.0)  # _BAND_FK_TARGET[8-11]


def test_brief_from_request_uses_reading_cap_when_below_sentinel() -> None:
    """A concrete reading_level_cap (below 99) becomes the FK target."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a gentle tale",
        status="pending",
        age_band="5-8",
    )
    brief = brief_from_request(request, _profile("5-8", cap=2.5))
    assert brief.reading_level_target == pytest.approx(2.5)


def test_brief_from_request_null_length_stays_null() -> None:
    """A request with no stored length yields a brief with length=None.

    ConceptBrief.length is genuinely optional (no repo-wide default), unlike
    narrative_style, which falls back to prose; this isolates that distinction.
    """
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        age_band="8-11",
    )
    brief = brief_from_request(request, _profile("8-11"))
    assert brief.length is None


def test_brief_from_request_narrative_style_comes_from_request() -> None:
    """A non-default narrative_style on the request flows into the brief.

    Proves the value comes from the request itself, not the NarrativeStyle.PROSE
    fallback that applies only when the request's narrative_style is unset.
    """
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a choose-your-path mystery",
        status="pending",
        age_band="13-16",
        narrative_style="gamebook",
    )
    brief = brief_from_request(request, _profile("13-16"))
    assert brief.narrative_style is NarrativeStyle.GAMEBOOK


def test_brief_from_request_surfaces_anchor_context() -> None:
    """Passing an anchor_context surfaces it unchanged on the brief."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a sequel about the same brave fox",
        status="pending",
        age_band="8-11",
    )
    ctx = AnchorContext(title="The Fox and the Map", character_names=["Robin"])
    brief = brief_from_request(request, _profile("8-11"), anchor_context=ctx)
    assert brief.anchor_context is ctx


def test_brief_from_request_anchor_context_defaults_to_none() -> None:
    """Without an anchor_context argument, the brief's field stays None."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        age_band="8-11",
    )
    brief = brief_from_request(request, _profile("8-11"))
    assert brief.anchor_context is None


def test_brief_from_request_banned_themes_become_content_nogo() -> None:
    """G2: a profile's banned_themes flow into the brief's content_nogo verbatim."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        age_band="8-11",
    )
    profile = _profile("8-11")
    profile.banned_themes = ["spiders", "magic"]
    brief = brief_from_request(request, profile)
    assert brief.content_nogo == ["spiders", "magic"]


def test_brief_from_request_content_flag_cap_stricter_than_band_is_carried() -> None:
    """G2: a cap stricter than the 8-11 band's ceiling (violence=mild) is kept as-is."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        age_band="8-11",
    )
    profile = _profile("8-11")
    profile.allowed_content_flags = {"violence": "none"}
    brief = brief_from_request(request, profile)
    assert brief.special_constraints == ["Keep violence at or below 'none'."]


def test_brief_from_request_content_flag_cap_looser_than_band_is_clamped() -> None:
    """G2: a guardian cannot loosen a cap past the band ceiling (PL-16 still applies).

    band 8-11's scariness ceiling is 'moderate'; requesting 'intense' clamps
    down to the ceiling rather than passing 'intense' to the generator.
    """
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        age_band="8-11",
    )
    profile = _profile("8-11")
    profile.allowed_content_flags = {"scariness": "intense"}
    brief = brief_from_request(request, profile)
    assert brief.special_constraints == ["Keep scariness at or below 'moderate'."]


def test_brief_from_request_profile_with_no_g2_controls_is_unaffected() -> None:
    """G2: a profile with no banned themes or flag caps set yields empty lists."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        age_band="8-11",
    )
    brief = brief_from_request(request, _profile("8-11"))
    assert brief.content_nogo == []
    assert brief.special_constraints == []


def test_brief_from_request_without_profile_has_no_content_controls() -> None:
    """G2: a profile-less request has no per-child controls to apply."""
    request = StoryRequest(
        family_id=uuid.uuid4(),
        request_text="a space story",
        status="pending",
        age_band="8-11",
    )
    brief = brief_from_request(request, None)
    assert brief.content_nogo == []
    assert brief.special_constraints == []


@pytest.mark.asyncio
async def test_screen_blocks_on_pii_match() -> None:
    """A request naming a real child is blocked before any classifier call."""
    result = await screen_request_text(
        "a story about Emma and a dragon",
        child_names=frozenset({"Emma"}),
        openai_key=None,
        perspective_key=None,
    )
    assert result.blocked is True
    assert any(f.category == "personal_information" for f in result.flags)


@pytest.mark.asyncio
async def test_screen_clean_when_no_keys_and_no_pii() -> None:
    """With no PII and no classifier keys, the request is not blocked."""
    result = await screen_request_text(
        "a story about a brave fox",
        child_names=frozenset({"Emma"}),
        openai_key=None,
        perspective_key=None,
    )
    assert result.blocked is False
    assert result.flags == []


@pytest.mark.asyncio
async def test_screen_blocks_on_bright_line_classifier(monkeypatch) -> None:
    """A bright-line BLOCK finding from the classifier blocks the request."""

    async def _fake_run_classifiers(**_kwargs: object) -> list[Finding]:
        return [
            Finding(
                stage=0,
                source=Source.OPENAI,
                category="sexual/minors",
                node_id="request",
                verdict=Verdict.BLOCK,
                score=0.99,
                message="OpenAI bright-line category 'sexual/minors' flagged",
            )
        ]

    monkeypatch.setattr(
        "cyo_adventure.story_requests.screening.run_classifiers",
        _fake_run_classifiers,
    )
    result = await screen_request_text(
        "some idea",
        child_names=frozenset(),
        openai_key="k",
        perspective_key=None,
    )
    assert result.blocked is True
    # Redacted: no score/source leak into the flag payload.
    flag = next(f for f in result.flags if f.verdict is Verdict.BLOCK)
    assert flag.category == "sexual/minors"
    assert "flagged" in flag.message


@pytest.mark.asyncio
async def test_screen_fails_open_on_classifier_network_error(
    monkeypatch,
) -> None:
    """When a classifier network call fails, the request proceeds (fail-open).

    The guardian remains the human gate; this test proves that network failures
    in classifier APIs do not hard-block story requests. The failure is now
    surfaced as a non-gating ``classifier_degraded`` advisory rather than being
    silently dropped, so the request stays unblocked while the degradation is
    visible.
    """

    class _FakeRequest:
        """Minimal request object for ConnectError."""

    async def _fake_post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError(
            "Network unreachable",
            request=_FakeRequest(),  # type: ignore[arg-type]
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    result = await screen_request_text(
        "some idea",
        child_names=frozenset(),
        openai_key="k",
        perspective_key=None,
    )
    assert result.blocked is False
    # Fail-open: not blocked, but the outage is now visible as a non-gating
    # degraded advisory rather than silently swallowed.
    assert [f.category for f in result.flags] == ["classifier_degraded"]


def test_ensure_pending_rejects_non_pending() -> None:
    """The pending guard raises a 409-mapped error for a decided request."""
    req = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="x",
        status="approved",
        age_band="8-11",
    )
    with pytest.raises(StateTransitionError):
        service.ensure_pending(req)


class _FakeScalars:
    """Stand-in for the iterable returned by ``session.scalars``."""

    def __init__(self, values: list[str]) -> None:
        self._values = values

    def all(self) -> list[str]:
        """Return the seeded scalar values."""
        return self._values


_UNSET = object()


class _FakeSession:
    """Minimal async session double for ``service.approve_story_request``.

    Mirrors the ``_FakeSession`` pattern in test_generation_api_unit.py so this
    module's service-level tests stay DB-free (no testcontainers). ``flush``
    assigns a UUID to any added object still missing one, mimicking the ORM's
    Python-side ``default=uuid.uuid4`` column default that a real flush applies.

    ADR-015: ``approve_story_request`` now calls ``enforce_family_quota``
    unconditionally (before the profile lookup this double originally existed
    for), which issues its own ``session.get(Family, ...)`` and
    ``session.scalar(<count query>)``. ``family_result`` defaults to a fresh,
    unconfigured ``Family`` (quota falls back to
    ``settings.default_monthly_story_quota``) and ``approved_count`` defaults
    to 0, so every pre-existing call site that does not care about budget
    behavior keeps passing the quota check unchanged; a budget-focused test
    overrides one or both to exercise the gate itself.
    """

    def __init__(
        self,
        *,
        get_result: object | None = None,
        child_names: list[str] | None = None,
        family_result: object | None = _UNSET,
        approved_count: int = 0,
    ) -> None:
        self._get_result = get_result
        self._child_names = child_names or []
        self._family_result = (
            Family(name="Fake Family") if family_result is _UNSET else family_result
        )
        self._approved_count = approved_count
        self.added: list[object] = []
        self.get_calls: list[tuple[type[object], object]] = []

    async def get(self, model: type[object], key: object) -> object | None:
        """Record the call and return the seeded row for ``model`` (or None)."""
        self.get_calls.append((model, key))
        if model is Family:
            return self._family_result
        return self._get_result

    async def scalars(self, statement: object) -> _FakeScalars:
        """Return the seeded family child display names."""
        _ = statement
        return _FakeScalars(self._child_names)

    async def scalar(self, statement: object) -> int:
        """Return the seeded monthly-approved-count (ADR-015 budget queries)."""
        _ = statement
        return self._approved_count

    def add(self, obj: object) -> None:
        """Record an added ORM instance."""
        self.added.append(obj)

    async def flush(self) -> None:
        """Assign a UUID to any tracked object still missing an id."""
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()  # pyright: ignore[reportAttributeAccessIssue]


def _guardian(family_id: uuid.UUID) -> Principal:
    """Build a guardian Principal for the given family."""
    return Principal(
        subject="guardian-sub",
        user_id=uuid.uuid4(),
        role="guardian",  # pyright: ignore[reportArgumentType]
        family_id=family_id,
        profile_ids=frozenset(),
    )


def _admin(family_id: uuid.UUID) -> Principal:
    """Build an admin Principal "belonging to" the given family.

    An admin base-role Principal's ``acting_role`` always resolves to
    ``Role.ADMIN`` regardless of the target family it acts on (see
    ``Principal.acting_role``'s docstring), so ``family_id`` here is only the
    principal's own nominal family, not a constraint on which family it may
    act against.
    """
    return Principal(
        subject="admin-sub",
        user_id=uuid.uuid4(),
        role="admin",  # pyright: ignore[reportArgumentType]
        family_id=family_id,
        profile_ids=frozenset(),
    )


@pytest.mark.asyncio
async def test_approve_stamps_and_builds_brief_from_stored_text() -> None:
    """Approval stamps status/reviewer/timestamp/concept_id, and the concept's
    brief premise is the request's own stored text, not any other source.
    Approval no longer creates a GenerationJob (see
    story_requests/authoring_plan.py for that step)."""
    family_id = uuid.uuid4()
    profile = _profile("8-11")
    profile.id = uuid.uuid4()
    principal = _guardian(family_id)
    stored_text = "a story about a lighthouse keeper and a curious seal"
    request = StoryRequest(
        family_id=family_id,
        profile_id=profile.id,
        request_text=stored_text,
        status="pending",
        age_band="8-11",
    )
    session = _FakeSession(get_result=profile, child_names=[])

    concept_id = await service.approve_story_request(
        session,
        principal,
        request,
        confirmation=ApprovalConfirmation(
            age_band=AgeBand.BAND_8_11,
            length=Length.MEDIUM,
            narrative_style=NarrativeStyle.PROSE,
        ),
    )

    assert request.status == "approved"
    assert request.age_band == "8-11"
    assert request.length == "medium"
    assert request.narrative_style == "prose"
    assert request.reviewed_by == principal.user_id
    assert request.reviewed_at is not None
    assert request.concept_id is not None
    assert concept_id == str(request.concept_id)

    concept = next(o for o in session.added if isinstance(o, Concept))
    assert concept.brief["premise"] == stored_text
    assert not any(isinstance(o, GenerationJob) for o in session.added)


@pytest.mark.asyncio
async def test_approve_story_request_pii_backstop_trips() -> None:
    """A request that names a real family child trips the belt-and-suspenders
    PII backstop at approval time, even though submission-time screening
    should already have blocked it (defense against a screening defect)."""
    family_id = uuid.uuid4()
    profile = _profile("8-11")
    profile.id = uuid.uuid4()
    principal = _guardian(family_id)
    request = StoryRequest(
        family_id=family_id,
        profile_id=profile.id,
        request_text="a story about Amelia and a dragon",
        status="pending",
        age_band="8-11",
    )
    session = _FakeSession(get_result=profile, child_names=["Amelia"])
    confirmation = ApprovalConfirmation(
        age_band=AgeBand.BAND_8_11,
        length=Length.MEDIUM,
        narrative_style=NarrativeStyle.PROSE,
    )

    with pytest.raises(ValidationError):
        await service.approve_story_request(
            session,
            principal,
            request,
            confirmation=confirmation,
        )


@pytest.mark.asyncio
async def test_approve_story_request_missing_profile_is_not_found() -> None:
    """Approving a request whose profile no longer exists raises 404."""
    family_id = uuid.uuid4()
    principal = _guardian(family_id)
    request = StoryRequest(
        family_id=family_id,
        profile_id=uuid.uuid4(),
        request_text="a fox",
        status="pending",
        age_band="8-11",
    )
    session = _FakeSession(get_result=None, child_names=[])
    confirmation = ApprovalConfirmation(
        age_band=AgeBand.BAND_8_11,
        length=Length.MEDIUM,
        narrative_style=NarrativeStyle.PROSE,
    )

    with pytest.raises(ResourceNotFoundError):
        await service.approve_story_request(
            session,
            principal,
            request,
            confirmation=confirmation,
        )


@pytest.mark.asyncio
async def test_approve_story_request_without_profile_skips_profile_lookup() -> None:
    """A profile-less request (guardian/admin initiated) approves cleanly.

    ``request.profile_id`` is None, so the ChildProfile-existence branch must
    never call ``session.get(ChildProfile, ...)``; only the family-quota
    lookup (``session.get(Family, ...)``, ADR-015) and the family-scoped
    child-names query run.
    """
    family_id = uuid.uuid4()
    principal = _guardian(family_id)
    request = StoryRequest(
        family_id=family_id,
        request_text="a space story",
        status="pending",
        age_band="8-11",
    )
    session = _FakeSession(get_result=None, child_names=[])

    concept_id = await service.approve_story_request(
        session,
        principal,
        request,
        confirmation=ApprovalConfirmation(
            age_band=AgeBand.BAND_8_11,
            length=Length.MEDIUM,
            narrative_style=NarrativeStyle.PROSE,
        ),
    )

    assert request.status == "approved"
    assert request.age_band == "8-11"
    assert request.length == "medium"
    assert request.narrative_style == "prose"
    assert concept_id == str(request.concept_id)
    assert session.get_calls == [(Family, family_id)]


@pytest.mark.asyncio
async def test_create_series_derives_carries_state_episodic() -> None:
    """A '5-8' (episodic) band series does not carry state (ADR-011)."""
    family_id = uuid.uuid4()
    principal = _guardian(family_id)
    session = _FakeSession()

    series = await service.create_series(
        session, principal, title="Fox Tales", family_id=family_id, age_band="5-8"
    )

    assert isinstance(series, Series)
    assert series.title == "Fox Tales"
    assert series.age_band == "5-8"
    assert series.carries_state is False
    assert series.family_id == family_id
    assert series.created_by == principal.user_id
    assert series in session.added


@pytest.mark.asyncio
async def test_create_series_derives_carries_state_state_carrying() -> None:
    """A '13-16' (older) band series carries state (ADR-011)."""
    family_id = uuid.uuid4()
    principal = _guardian(family_id)
    session = _FakeSession()

    series = await service.create_series(
        session, principal, title="Fox Tales", family_id=family_id, age_band="13-16"
    )

    assert series.carries_state is True


@pytest.mark.asyncio
async def test_approve_with_series_title_creates_series_and_sets_request() -> None:
    """Approving a non-anchored pending request with ``series_title`` ratifies
    a new Series row, links it onto the request, and still returns a concept
    id (the series ratification does not short-circuit the normal approval
    tail)."""
    family_id = uuid.uuid4()
    principal = _guardian(family_id)
    request = StoryRequest(
        family_id=family_id,
        request_text="a story about a clever fox",
        status="pending",
        age_band="8-11",
    )
    session = _FakeSession(get_result=None, child_names=[])

    concept_id = await service.approve_story_request(
        session,
        principal,
        request,
        confirmation=ApprovalConfirmation(
            age_band=AgeBand.BAND_8_11,
            length=Length.MEDIUM,
            narrative_style=NarrativeStyle.PROSE,
        ),
        series_title="Fox Tales",
    )

    series = next(o for o in session.added if isinstance(o, Series))
    assert series.title == "Fox Tales"
    assert series.age_band == "8-11"
    assert request.series_id == series.id
    assert concept_id == str(request.concept_id)


@pytest.mark.asyncio
async def test_approve_without_series_title_creates_no_series() -> None:
    """Approving with ``series_title=None`` (the default) never adds a Series
    row and leaves the request standalone."""
    family_id = uuid.uuid4()
    principal = _guardian(family_id)
    request = StoryRequest(
        family_id=family_id,
        request_text="a standalone tale",
        status="pending",
        age_band="8-11",
    )
    session = _FakeSession(get_result=None, child_names=[])

    await service.approve_story_request(
        session,
        principal,
        request,
        confirmation=ApprovalConfirmation(
            age_band=AgeBand.BAND_8_11,
            length=Length.MEDIUM,
            narrative_style=NarrativeStyle.PROSE,
        ),
    )

    assert not any(isinstance(o, Series) for o in session.added)
    assert request.series_id is None


@pytest.mark.asyncio
async def test_approve_anchored_request_with_series_title_raises() -> None:
    """An anchored (continuation) request cannot also ratify a new series;
    the guard fires before any anchor lookup, so a fake session with no
    Storybook/Series support still exercises the real code path."""
    family_id = uuid.uuid4()
    principal = _guardian(family_id)
    request = StoryRequest(
        family_id=family_id,
        request_text="book two of the fox saga",
        status="pending",
        age_band="8-11",
        anchor_storybook_id="s_anchor123",
    )
    session = _FakeSession(get_result=None, child_names=[])
    confirmation = ApprovalConfirmation(
        age_band=AgeBand.BAND_8_11,
        length=Length.MEDIUM,
        narrative_style=NarrativeStyle.PROSE,
    )

    with pytest.raises(ValidationError):
        await service.approve_story_request(
            session,
            principal,
            request,
            confirmation=confirmation,
            series_title="A New Series",
        )


def test_to_view_skips_malformed_verdict() -> None:
    """An out-of-enum stored verdict is skipped, not raised, so the view survives.

    moderation_flags is unconstrained JSONB, so a legacy or manually-edited row
    can hold a verdict string outside the Verdict enum. _to_view must drop that
    single flag rather than let Verdict(verdict) raise and 500 the whole list.

    The second flag uses "flag" (not "advisory"): the default threshold policy
    hides advisory-level findings (WS-A), so a verdict that must survive both
    the malformed-verdict skip AND the threshold filter is used here to isolate
    the malformed-verdict behavior under test.
    """
    request = StoryRequest(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        initiator_role="child",
        age_band="10-13",
        narrative_style="prose",
        moderation_flags={
            "blocked": False,
            "flags": [
                {
                    "category": "toxicity",
                    "verdict": "not-a-real-verdict",
                    "message": "x",
                },
                {
                    "category": "toxicity",
                    "verdict": "flag",
                    "message": "borderline",
                },
            ],
        },
        created_at=datetime(2026, 7, 4, tzinfo=UTC),
    )

    # surface_all=False exercises the filtered guardian view: the malformed
    # verdict is skipped AND the threshold filter applies.
    view = _to_view(request, policy=ThresholdPolicy(rows={}), surface_all=False)

    assert len(view.moderation_flags) == 1
    assert view.moderation_flags[0].verdict is Verdict.FLAG
    assert view.moderation_flags[0].message == "borderline"


def test_to_view_skips_non_dict_flag_entry() -> None:
    """A raw non-dict entry in the flags list is skipped, not raised.

    moderation_flags is unconstrained JSONB; a legacy row or manual edit
    could store a bare string or number in the flags array instead of an
    object. _parse_flag's isinstance(item, dict) guard drops it silently.
    """
    request = StoryRequest(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        initiator_role="child",
        age_band="10-13",
        narrative_style="prose",
        moderation_flags={
            "blocked": False,
            "flags": [
                "not-a-flag-object",
                {
                    "category": "toxicity",
                    "verdict": "flag",
                    "message": "borderline",
                },
            ],
        },
        created_at=datetime(2026, 7, 4, tzinfo=UTC),
    )

    view = _to_view(request, policy=ThresholdPolicy(rows={}), surface_all=False)

    assert len(view.moderation_flags) == 1
    assert view.moderation_flags[0].message == "borderline"


def test_to_view_skips_flag_entry_missing_required_string_fields() -> None:
    """A dict flag entry with a non-string field (e.g. a numeric verdict) is
    skipped rather than raising, since _parse_flag requires verdict, category,
    and message to all be strings before it even attempts Verdict(verdict)."""
    request = StoryRequest(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        initiator_role="child",
        age_band="10-13",
        narrative_style="prose",
        moderation_flags={
            "blocked": False,
            "flags": [
                {
                    "category": "toxicity",
                    "verdict": 42,
                    "message": "malformed verdict type",
                },
                {
                    "category": "toxicity",
                    "verdict": "flag",
                    "message": "borderline",
                },
            ],
        },
        created_at=datetime(2026, 7, 4, tzinfo=UTC),
    )

    view = _to_view(request, policy=ThresholdPolicy(rows={}), surface_all=False)

    assert len(view.moderation_flags) == 1
    assert view.moderation_flags[0].message == "borderline"


# ---------------------------------------------------------------------------
# WS-7 D8: the K19 interpretation projection on the story-request view.
# ---------------------------------------------------------------------------


def test_to_view_projects_general_layer_interpretation() -> None:
    """A pending row's stored general-layer interpretation is projected verbatim.

    _to_view validates the stored JSONB into a RequestInterpretationView: a
    straight projection with the same layer, version, summaries, and one
    InterpretedElementView per stored element (here the single band-promise
    element, disposition BUILT_IN / STORY_FIT with element=None).
    """
    interpretation = build_general_interpretation(
        screening=_FakeScreening(blocked=False),
        band=AgeBand.BAND_10_13,
        banned_themes=(),
        premise="a story about a brave fox",
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    request = StoryRequest(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        initiator_role="child",
        age_band="10-13",
        narrative_style="prose",
        moderation_flags={"blocked": False, "flags": []},
        interpretation=interpretation.model_dump(mode="json"),
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    view = _to_view(request, policy=ThresholdPolicy(rows={}), surface_all=False)

    assert isinstance(view.interpretation, RequestInterpretationView)
    assert view.interpretation.layer == "general"
    assert view.interpretation.interpretation_version == 1
    assert view.interpretation.kid_summary
    assert view.interpretation.guardian_summary
    assert len(view.interpretation.elements) == 1
    element = view.interpretation.elements[0]
    assert isinstance(element, InterpretedElementView)
    assert element.disposition == "built_in"
    assert element.reason == "story_fit"
    assert element.element is None
    assert element.kid_text
    assert element.guardian_text


def test_to_view_null_interpretation_projects_none() -> None:
    """A pre-WS-7 row (null interpretation column) projects to None, not a raise."""
    request = StoryRequest(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
        initiator_role="child",
        age_band="10-13",
        narrative_style="prose",
        moderation_flags={"blocked": False, "flags": []},
        interpretation=None,
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    view = _to_view(request, policy=ThresholdPolicy(rows={}), surface_all=False)

    assert view.interpretation is None


def test_to_view_blocked_row_carries_generic_interpretation_and_no_text() -> None:
    """A blocked row surfaces request_text=None AND the generic interpretation.

    CR-1: the stored blocked-row interpretation is the generic
    CANNOT_CARRY/SAFETY_POLICY object with NO premise-derived content (every
    element carries element=None), so it is safe to expose alongside the
    redacted request_text. This asserts both the redaction and that the raw
    premise never round-trips into the projected interpretation.
    """
    premise = "topsecretpremisephrase"
    interpretation = build_general_interpretation(
        screening=_FakeScreening(blocked=True),
        band=AgeBand.BAND_10_13,
        banned_themes=(),
        premise=premise,
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    request = StoryRequest(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text=premise,
        status="blocked",
        initiator_role="child",
        age_band="10-13",
        narrative_style="prose",
        moderation_flags={"blocked": True, "flags": []},
        interpretation=interpretation.model_dump(mode="json"),
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    view = _to_view(request, policy=ThresholdPolicy(rows={}), surface_all=False)

    # Blocked-row redaction (existing rule) still holds.
    assert view.request_text is None
    # ... AND the generic interpretation is carried alongside it (CR-1).
    assert isinstance(view.interpretation, RequestInterpretationView)
    assert view.interpretation.elements
    assert all(e.element is None for e in view.interpretation.elements)
    assert view.interpretation.elements[0].disposition == "cannot_carry"
    assert view.interpretation.elements[0].reason == "safety_policy"
    # CR-1: no premise-derived content round-trips into the interpretation.
    assert premise not in view.interpretation.model_dump_json()


# ---------------------------------------------------------------------------
# ADR-015 budget-consent delta: G7 guardian cost gate, G3 pre-authorization.
#
# Only the gate logic itself (resolve_family_quota, _bypasses_family_quota,
# enforce_family_quota's block/pass/admin-bypass outcomes, and
# can_auto_approve's fast no-DB-touch short-circuits) is unit-testable
# against the hand-rolled _FakeSession, which cannot distinguish a
# family-scoped count from a profile-scoped count (both route through the
# same seeded `approved_count`). Scenarios that need two distinguishable
# counts (envelope-vs-quota, the month boundary, the HTTP-level auto-approve
# and budget-endpoint flows) live in
# tests/integration/test_story_requests_budget.py against a real database.
# ---------------------------------------------------------------------------


class TestResolveFamilyQuota:
    """resolve_family_quota: override vs platform-default fallback."""

    def test_none_falls_back_to_platform_default(self) -> None:
        family = Family(name="Fam")
        assert family.monthly_story_quota is None
        assert (
            service.resolve_family_quota(family) == settings.default_monthly_story_quota
        )

    def test_explicit_override_wins(self) -> None:
        family = Family(name="Fam", monthly_story_quota=42)
        assert service.resolve_family_quota(family) == 42

    def test_explicit_zero_is_not_treated_as_unset(self) -> None:
        """0 is a valid (very strict) quota, not the sentinel for "use the
        default"; only None means unset."""
        family = Family(name="Fam", monthly_story_quota=0)
        assert service.resolve_family_quota(family) == 0


class TestBypassesFamilyQuota:
    """_bypasses_family_quota: mirrors Principal.acting_role's admin cases."""

    def test_guardian_never_bypasses_own_family(self) -> None:
        family_id = uuid.uuid4()
        assert service._bypasses_family_quota(_guardian(family_id), family_id) is False

    def test_admin_always_bypasses(self) -> None:
        """A pure admin-role Principal bypasses regardless of family match
        (ADR-015: "admin caller" bypasses, not only a cross-family admin)."""
        family_id = uuid.uuid4()
        assert service._bypasses_family_quota(_admin(family_id), family_id) is True
        assert service._bypasses_family_quota(_admin(family_id), uuid.uuid4()) is True

    def test_dual_role_guardian_admin_bypasses_only_cross_family(self) -> None:
        own_family = uuid.uuid4()
        other_family = uuid.uuid4()
        dual = Principal(
            subject="dual",
            user_id=uuid.uuid4(),
            role="guardian",  # pyright: ignore[reportArgumentType]
            family_id=own_family,
            profile_ids=frozenset(),
            is_admin=True,
        )
        assert service._bypasses_family_quota(dual, own_family) is False
        assert service._bypasses_family_quota(dual, other_family) is True


@pytest.mark.asyncio
class TestEnforceFamilyQuota:
    """enforce_family_quota: the guardian-cost-gate enforcement point."""

    async def test_blocks_when_spend_meets_quota(self) -> None:
        family_id = uuid.uuid4()
        family = Family(id=family_id, name="Fam", monthly_story_quota=2)
        session = _FakeSession(family_result=family, approved_count=2)
        guardian = _guardian(family_id)
        with pytest.raises(StateTransitionError, match="monthly story budget reached"):
            await service.enforce_family_quota(session, guardian, family_id)

    async def test_passes_when_under_quota(self) -> None:
        family_id = uuid.uuid4()
        family = Family(id=family_id, name="Fam", monthly_story_quota=2)
        session = _FakeSession(family_result=family, approved_count=1)
        await service.enforce_family_quota(session, _guardian(family_id), family_id)

    async def test_admin_bypasses_even_when_over_quota(self) -> None:
        family_id = uuid.uuid4()
        family = Family(id=family_id, name="Fam", monthly_story_quota=0)
        session = _FakeSession(family_result=family, approved_count=99)
        # Must not raise, and must never even look up the family row (the
        # bypass check runs first).
        await service.enforce_family_quota(session, _admin(family_id), family_id)
        assert session.get_calls == []

    async def test_missing_family_is_not_found(self) -> None:
        family_id = uuid.uuid4()
        session = _FakeSession(family_result=None)
        guardian = _guardian(family_id)
        with pytest.raises(ResourceNotFoundError):
            await service.enforce_family_quota(session, guardian, family_id)


@pytest.mark.asyncio
class TestApproveStoryRequestQuotaGate:
    """approve_story_request's own call to enforce_family_quota."""

    async def test_over_quota_blocks_before_any_concept_is_added(self) -> None:
        family_id = uuid.uuid4()
        family = Family(id=family_id, name="Fam", monthly_story_quota=0)
        principal = _guardian(family_id)
        request = StoryRequest(
            family_id=family_id,
            request_text="a fox",
            status="pending",
            age_band="8-11",
        )
        session = _FakeSession(
            get_result=None, child_names=[], family_result=family, approved_count=1
        )
        confirmation = ApprovalConfirmation(
            age_band=AgeBand.BAND_8_11,
            length=Length.MEDIUM,
            narrative_style=NarrativeStyle.PROSE,
        )

        with pytest.raises(StateTransitionError, match="monthly story budget reached"):
            await service.approve_story_request(
                session,
                principal,
                request,
                confirmation=confirmation,
            )

        assert request.status == "pending"
        assert request.concept_id is None
        assert not any(isinstance(o, Concept) for o in session.added)

    async def test_admin_approval_bypasses_even_at_zero_quota(self) -> None:
        family_id = uuid.uuid4()
        family = Family(id=family_id, name="Fam", monthly_story_quota=0)
        principal = _admin(family_id)
        request = StoryRequest(
            family_id=family_id,
            request_text="a platform-funded story",
            status="pending",
            age_band="8-11",
        )
        session = _FakeSession(
            get_result=None, child_names=[], family_result=family, approved_count=99
        )

        concept_id = await service.approve_story_request(
            session,
            principal,
            request,
            confirmation=ApprovalConfirmation(
                age_band=AgeBand.BAND_8_11,
                length=Length.MEDIUM,
                narrative_style=NarrativeStyle.PROSE,
            ),
        )
        assert concept_id == str(request.concept_id)
        assert request.status == "approved"
        assert request.approved_at is not None


@pytest.mark.asyncio
class TestCanAutoApprove:
    """can_auto_approve's fast, no-DB-touch short-circuits (G3)."""

    async def test_false_when_auto_approve_disabled(self) -> None:
        profile = ChildProfile(
            family_id=uuid.uuid4(),
            display_name="Kid",
            age_band="8-11",
            request_auto_approve=False,
            monthly_request_envelope=5,
        )
        family = Family(name="Fam")
        # A bare object() proves the short-circuit never touches the
        # session: any await on it would raise AttributeError.
        session = object()
        assert (
            await service.can_auto_approve(session, profile, family)  # type: ignore[arg-type]
            is False
        )

    async def test_false_when_envelope_unset(self) -> None:
        profile = ChildProfile(
            family_id=uuid.uuid4(),
            display_name="Kid",
            age_band="8-11",
            request_auto_approve=True,
            monthly_request_envelope=None,
        )
        family = Family(name="Fam")
        session = object()
        assert (
            await service.can_auto_approve(session, profile, family)  # type: ignore[arg-type]
            is False
        )
