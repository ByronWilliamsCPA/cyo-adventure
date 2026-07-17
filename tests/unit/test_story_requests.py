"""Unit tests for the child story-request feature (model, brief, screening)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.api.story_requests import _to_view
from cyo_adventure.core.exceptions import (
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    GenerationJob,
    Series,
    StoryRequest,
)
from cyo_adventure.generation.concept import AnchorContext, ConceptBrief
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.moderation.thresholds import ThresholdPolicy
from cyo_adventure.story_requests import service
from cyo_adventure.story_requests.brief import brief_from_request
from cyo_adventure.story_requests.screening import screen_request_text
from cyo_adventure.story_requests.service import ApprovalConfirmation
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle


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


class _FakeSession:
    """Minimal async session double for ``service.approve_story_request``.

    Mirrors the ``_FakeSession`` pattern in test_generation_api_unit.py so this
    module's service-level tests stay DB-free (no testcontainers). ``flush``
    assigns a UUID to any added object still missing one, mimicking the ORM's
    Python-side ``default=uuid.uuid4`` column default that a real flush applies.
    """

    def __init__(
        self, *, get_result: object | None = None, child_names: list[str] | None = None
    ) -> None:
        self._get_result = get_result
        self._child_names = child_names or []
        self.added: list[object] = []
        self.get_calls: list[tuple[type[object], object]] = []

    async def get(self, model: type[object], key: object) -> object | None:
        """Record the call and return the seeded profile row (or None)."""
        self.get_calls.append((model, key))
        return self._get_result

    async def scalars(self, statement: object) -> _FakeScalars:
        """Return the seeded family child display names."""
        _ = statement
        return _FakeScalars(self._child_names)

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

    with pytest.raises(ValidationError):
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

    with pytest.raises(ResourceNotFoundError):
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


@pytest.mark.asyncio
async def test_approve_story_request_without_profile_skips_profile_lookup() -> None:
    """A profile-less request (guardian/admin initiated) approves cleanly.

    ``request.profile_id`` is None, so the profile-existence branch must never
    call ``session.get``; only the family-scoped child-names query runs.
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
    assert session.get_calls == []


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

    with pytest.raises(ValidationError):
        await service.approve_story_request(
            session,
            principal,
            request,
            confirmation=ApprovalConfirmation(
                age_band=AgeBand.BAND_8_11,
                length=Length.MEDIUM,
                narrative_style=NarrativeStyle.PROSE,
            ),
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
