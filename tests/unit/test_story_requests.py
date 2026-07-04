"""Unit tests for the child story-request feature (model, brief, screening)."""

from __future__ import annotations

import uuid

import httpx
import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.core.exceptions import (
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import ChildProfile, Concept, GenerationJob, StoryRequest
from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.story_requests import service
from cyo_adventure.story_requests.brief import brief_from_request
from cyo_adventure.story_requests.screening import screen_request_text
from cyo_adventure.storybook.models import AgeBand


def test_story_request_defaults_to_pending() -> None:
    """A newly constructed StoryRequest has status 'pending'."""
    req = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a story about a brave fox",
        status="pending",
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
    brief = brief_from_request("a story about a brave fox", _profile("8-11"))
    assert isinstance(brief, ConceptBrief)
    assert brief.premise == "a story about a brave fox"
    assert brief.age_band == AgeBand.BAND_8_11
    assert brief.target_node_count == 15  # band_profile 8-11 min_nodes
    assert brief.ending_count == 3  # band_profile 8-11 min_endings
    assert brief.protagonist.name == "Explorer"  # never a real child name
    assert brief.tier == 1


def test_brief_from_request_uses_reading_cap_when_below_sentinel() -> None:
    """A concrete reading_level_cap (below 99) becomes the FK target."""
    brief = brief_from_request("a gentle tale", _profile("5-8", cap=2.5))
    assert brief.reading_level_target == 2.5


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
    in classifier APIs do not hard-block story requests. The fail-open behavior
    is a property of run_classifiers' internal per-call except (httpx.HTTPError,
    ValueError) contract.
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
    assert result.flags == []


def test_ensure_pending_rejects_non_pending() -> None:
    """The pending guard raises a 409-mapped error for a decided request."""
    req = StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="x",
        status="approved",
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

    async def get(self, model: type[object], key: object) -> object | None:
        """Return the seeded profile row (or None), ignoring the key."""
        _ = (model, key)
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
    brief premise is the request's own stored text, not any other source."""
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
    )
    session = _FakeSession(get_result=profile, child_names=[])

    concept_id, job_id = await service.approve_story_request(
        session, principal, request
    )

    assert request.status == "approved"
    assert request.reviewed_by == principal.user_id
    assert request.reviewed_at is not None
    assert request.concept_id is not None
    assert concept_id == str(request.concept_id)

    concept = next(o for o in session.added if isinstance(o, Concept))
    assert concept.brief["premise"] == stored_text
    job = next(o for o in session.added if isinstance(o, GenerationJob))
    assert job.concept_id == concept.id
    assert job_id == str(job.id)


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
    )
    session = _FakeSession(get_result=profile, child_names=["Amelia"])

    with pytest.raises(ValidationError):
        await service.approve_story_request(session, principal, request)


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
    )
    session = _FakeSession(get_result=None, child_names=[])

    with pytest.raises(ResourceNotFoundError):
        await service.approve_story_request(session, principal, request)
