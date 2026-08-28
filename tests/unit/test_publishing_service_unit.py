"""Docker-independent unit tests for cyo_adventure.publishing.service.

These tests call the service functions directly with a mocked AsyncSession,
constructing ORM objects without a DB. They cover every function and both
legal and illegal state-transition paths.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.api.deps import Principal
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
    StateTransitionError,
)
from cyo_adventure.db.models import Storybook, StorybookVersion, StoryRequest
from cyo_adventure.events import Actor
from cyo_adventure.moderation.pipeline import _stamp_mock_reviewer
from cyo_adventure.moderation.report import (
    Finding,
    ModerationReport,
    Source,
    Verdict,
)
from cyo_adventure.publishing import service
from tests.conftest import make_clean_moderation_report

pytestmark = pytest.mark.asyncio


def _principal(role: str) -> Principal:
    """Build a minimal Principal with the given role."""
    return Principal(
        subject=f"{role}-x",
        user_id=uuid.uuid4(),
        role=role,
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _story(status: str, *, current: int | None = None) -> Storybook:
    """Construct a Storybook ORM instance without a session."""
    return Storybook(
        id="s1",
        family_id=uuid.uuid4(),
        status=status,
        current_published_version=current,
    )


@pytest.mark.unit
async def test_submit_draft_moves_to_in_review() -> None:
    """submit() on a draft story transitions status to in_review and flushes."""
    story = _story("draft")
    session = AsyncMock(spec=AsyncSession)

    await service.submit(session, story, actor=Actor.system())

    assert story.status == "in_review"
    # One flush, not two: record_event flushes, and that single flush carries
    # the status transition with it. Atomicity comes from the caller's
    # transaction (events spec D1), not from flushing twice inside it, so a
    # second await here would be a wasted round trip rather than a guarantee.
    assert session.flush.await_count == 1


@pytest.mark.unit
async def test_submit_needs_revision_moves_to_in_review() -> None:
    """submit() on a needs_revision story transitions to in_review and flushes."""
    story = _story("needs_revision")
    session = AsyncMock(spec=AsyncSession)

    await service.submit(session, story, actor=Actor.system())

    assert story.status == "in_review"
    # One flush, not two: record_event flushes, and that single flush carries
    # the status transition with it. Atomicity comes from the caller's
    # transaction (events spec D1), not from flushing twice inside it, so a
    # second await here would be a wasted round trip rather than a guarantee.
    assert session.flush.await_count == 1


@pytest.mark.unit
async def test_submit_illegal_status_raises() -> None:
    """submit() on an already-published story raises StateTransitionError; no flush."""
    story = _story("published")
    session = AsyncMock(spec=AsyncSession)
    actor = Actor.system()

    with pytest.raises(StateTransitionError):
        await service.submit(session, story, actor=actor)

    session.flush.assert_not_awaited()


@pytest.mark.unit
async def test_submit_without_moderation_report_raises() -> None:
    """submit() on a draft whose latest version was never screened is blocked (#57).

    Mirrors the moderation-report gate approve() already enforces: without
    this check, the admin submit endpoint (api/approval.py::submit_storybook)
    could move a draft straight to in_review without moderation ever running.
    """
    story = _story("draft")
    version_row = StorybookVersion(storybook_id="s1", version=1, blob={})
    session = AsyncMock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=1)
    session.get = AsyncMock(return_value=version_row)
    actor = Actor.system()

    with pytest.raises(BusinessLogicError):
        await service.submit(session, story, actor=actor)

    assert story.status == "draft"
    session.flush.assert_not_awaited()


@pytest.mark.unit
async def test_submit_with_moderation_report_succeeds() -> None:
    """submit() on a draft whose latest version has a moderation_report succeeds."""
    story = _story("draft")
    version_row = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob={},
        moderation_report=make_clean_moderation_report(),
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=1)
    session.get = AsyncMock(return_value=version_row)

    await service.submit(session, story, actor=Actor.system())

    assert story.status == "in_review"
    # One flush, not two: record_event flushes, and that single flush carries
    # the status transition with it. Atomicity comes from the caller's
    # transaction (events spec D1), not from flushing twice inside it, so a
    # second await here would be a wasted round trip rather than a guarantee.
    assert session.flush.await_count == 1


@pytest.mark.unit
async def test_approve_publishes_and_stamps() -> None:
    """approve() transitions to published, stamps approved_by and published_at."""
    story = _story("in_review")
    version_row = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob={},
        moderation_report=make_clean_moderation_report(),
    )
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=version_row)
    # W0.4: no GenerationJob is modeled for this storybook/version, so
    # _stamp_resulting_storybook_id's concept_id lookup must no-op cleanly;
    # a bare AsyncMock(spec=AsyncSession) makes session.execute(...) itself
    # return an AsyncMock whose scalar_one_or_none() is a coroutine, not a
    # value, so it must be given a real (sync) Result double here.
    session.execute = AsyncMock(return_value=_scalar_result(None))
    principal = _principal("admin")

    result = await service.approve(session, principal, story, 1)

    assert result is version_row
    assert story.status == "published"
    assert story.current_published_version == 1
    assert version_row.approved_by == principal.user_id
    assert version_row.published_at is not None
    assert isinstance(version_row.published_at, datetime)
    session.flush.assert_awaited_once()


@pytest.mark.unit
async def test_approve_without_moderation_report_raises() -> None:
    """approve() on a never-screened version raises BusinessLogicError.

    Closes C3-SAFETY Finding 2: the admin submit endpoint can still move a
    draft to in_review without moderation ever running (Finding 1 closed the
    import path's own unmoderated route). This guard is the structural choke
    point that makes "no unmoderated path reaches published" hold regardless
    of how the story got here.
    """
    story = _story("in_review")
    version_row = StorybookVersion(storybook_id="s1", version=1, blob={})
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=version_row)

    principal = _principal("admin")
    with pytest.raises(BusinessLogicError):
        await service.approve(session, principal, story, 1)

    assert story.status == "in_review"
    session.flush.assert_not_awaited()


@pytest.mark.unit
async def test_approve_rejects_a_non_admin_principal() -> None:
    """approve() itself refuses a non-admin principal, before any DB access.

    Defense-in-depth regression: approve() now has two privileged callers
    (api/approval.py::approve_storybook and
    publishing/catalog_publish.py::promote_catalog_story), both of which
    already gate on is_admin before reaching here. This asserts the
    service-level re-check rejects a non-admin principal directly, so the
    invariant holds even if a caller's own gate is ever skipped or buggy.
    """
    story = _story("in_review")
    session = AsyncMock(spec=AsyncSession)

    principal = _principal("guardian")
    with pytest.raises(AuthorizationError, match="admin role required"):
        await service.approve(session, principal, story, 1)

    assert story.status == "in_review"
    session.get.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.unit
async def test_approve_rejects_mqa_fixture_outside_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """approve() refuses an mqa_-prefixed storybook when not in staging.

    Defense in depth for the staging Moderation QA corpus
    (moderation-review-redesign-2026-07-28.md section 5, point 3): the seed
    script's own environment guard already keeps these fixtures out of any
    non-staging database, but this is the independent second layer at the
    sole publish path, in case an admin somehow acquires an mqa_-prefixed
    row outside staging (a misclick, a copied id, a future automation).
    """
    monkeypatch.setattr(service, "settings", SimpleNamespace(environment="production"))
    story = _story("in_review")
    story.id = "mqa_block_selfharm_reference"
    session = AsyncMock(spec=AsyncSession)
    principal = _principal("admin")

    with pytest.raises(BusinessLogicError, match="mqa_block_selfharm_reference"):
        await service.approve(session, principal, story, 1)

    assert story.status == "in_review"
    session.get.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.unit
async def test_approve_allows_mqa_fixture_in_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """approve() does not block an mqa_-prefixed storybook while in staging.

    The QA corpus must actually be approvable in staging for a human to
    exercise the review surface end to end; this pins that the mqa_ guard is
    scoped to non-staging environments only, not a blanket ban on the prefix.
    """
    monkeypatch.setattr(service, "settings", SimpleNamespace(environment="staging"))
    story = _story("in_review")
    story.id = "mqa_clean_meadow_market"
    version_row = StorybookVersion(
        storybook_id="mqa_clean_meadow_market",
        version=1,
        blob={},
        moderation_report=make_clean_moderation_report(),
    )
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=version_row)
    # W0.4: see the matching comment on test_approve_publishes_and_stamps.
    session.execute = AsyncMock(return_value=_scalar_result(None))
    principal = _principal("admin")

    result = await service.approve(session, principal, story, 1)

    assert result is version_row
    assert story.status == "published"


@pytest.mark.unit
async def test_approve_missing_version_raises() -> None:
    """approve() raises ResourceNotFoundError when the version row is absent."""
    story = _story("in_review")
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=None)

    principal = _principal("admin")
    with pytest.raises(ResourceNotFoundError):
        await service.approve(session, principal, story, 1)


@pytest.mark.unit
async def test_approve_illegal_status_raises() -> None:
    """approve() on a draft raises StateTransitionError before the version lookup."""
    story = _story("draft")
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock()

    principal = _principal("admin")
    with pytest.raises(StateTransitionError):
        await service.approve(session, principal, story, 1)

    session.get.assert_not_awaited()


@pytest.mark.unit
async def test_send_back_moves_to_needs_revision() -> None:
    """send_back() transitions in_review to needs_revision and flushes."""
    story = _story("in_review")
    session = AsyncMock(spec=AsyncSession)

    await service.send_back(
        session, _principal("admin"), story, "too scary", reason_code="safety_concern"
    )

    assert story.status == "needs_revision"
    session.flush.assert_awaited_once()


@pytest.mark.unit
async def test_send_back_illegal_status_raises() -> None:
    """send_back() on a draft raises StateTransitionError; no flush."""
    story = _story("draft")
    session = AsyncMock(spec=AsyncSession)

    principal = _principal("admin")
    with pytest.raises(StateTransitionError):
        await service.send_back(
            session, principal, story, "reason", reason_code="other"
        )

    session.flush.assert_not_awaited()


@pytest.mark.unit
async def test_archive_moves_to_archived() -> None:
    """archive() transitions published to archived and flushes."""
    story = _story("published", current=1)
    session = AsyncMock(spec=AsyncSession)

    await service.archive(session, _principal("admin"), story)

    assert story.status == "archived"
    session.flush.assert_awaited_once()


@pytest.mark.unit
async def test_archive_illegal_status_raises() -> None:
    """archive() on a draft raises StateTransitionError; no flush."""
    story = _story("draft")
    session = AsyncMock(spec=AsyncSession)

    principal = _principal("admin")
    with pytest.raises(StateTransitionError):
        await service.archive(session, principal, story)

    session.flush.assert_not_awaited()


@pytest.mark.unit
async def test_approve_stamps_utc_published_at() -> None:
    """approve() stamps published_at with a timezone-aware UTC datetime."""
    story = _story("in_review")
    version_row = StorybookVersion(
        storybook_id="s1",
        version=2,
        blob={},
        moderation_report=make_clean_moderation_report(),
    )
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=version_row)
    # W0.4: see the matching comment on test_approve_publishes_and_stamps.
    session.execute = AsyncMock(return_value=_scalar_result(None))
    before = datetime.now(UTC)

    await service.approve(session, _principal("admin"), story, 2)

    after = datetime.now(UTC)
    assert version_row.published_at is not None
    assert version_row.published_at.tzinfo is not None
    assert before <= version_row.published_at <= after


def _scalar_result(value: object) -> MagicMock:
    """Build a fake ``Result`` whose ``scalar_one_or_none()`` returns ``value``.

    Mirrors this module's other hand-rolled session-mocking helpers: no real
    SQLAlchemy Result is constructed, only the one method
    ``_stamp_resulting_storybook_id`` calls on it.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.unit
async def test_approve_stamps_resulting_storybook_id() -> None:
    """approve() links the originating request's resulting_storybook_id (W0.4).

    session.execute is called twice by approve(), both from
    _stamp_resulting_storybook_id: the concept_id SELECT, then the request row
    SELECT; side_effect supplies each in that order. There is no third call:
    the report-nulling UPDATE that used to run first was removed by ADR-007's
    2026-08-11 amendment (see tests/unit/test_report_retention.py).
    """
    story = _story("in_review")
    version_row = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob={},
        moderation_report=make_clean_moderation_report(),
    )
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=version_row)
    concept_id = uuid.uuid4()
    request_row = StoryRequest(
        family_id=uuid.uuid4(),
        request_text="a dragon who loves pancakes",
        age_band="5-8",
        concept_id=concept_id,
    )
    session.execute = AsyncMock(
        side_effect=[
            _scalar_result(concept_id),
            _scalar_result(request_row),
        ]
    )

    await service.approve(session, _principal("admin"), story, 1)

    assert request_row.resulting_storybook_id == "s1"


@pytest.mark.unit
async def test_approve_resulting_storybook_id_noop_without_generation_job() -> None:
    """approve() leaves resulting_storybook_id untouched with no matching job.

    A catalog-imported or hand-crafted storybook with no GenerationJob row
    (storybook_id, version) has nothing to resolve a concept_id from; this is
    the same silent no-op contract as
    generation/worker.py::_stamp_request_interpretation.
    """
    story = _story("in_review")
    version_row = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob={},
        moderation_report=make_clean_moderation_report(),
    )
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=version_row)
    session.execute = AsyncMock(
        side_effect=[
            _scalar_result(None),  # no GenerationJob matches
        ]
    )

    result = await service.approve(session, _principal("admin"), story, 1)

    assert result is version_row
    assert story.status == "published"
    # Exactly one execute() call, the concept lookup; the request lookup is
    # never reached with no concept_id, and approve() issues no UPDATE of its
    # own (ADR-007's 2026-08-11 amendment removed the report-nulling one).
    assert session.execute.await_count == 1


@pytest.mark.unit
async def test_approve_resulting_storybook_id_noop_without_request_row() -> None:
    """approve() leaves resulting_storybook_id untouched with no request row.

    A guardian-authored or catalog concept has no originating StoryRequest;
    this is a silent no-op, matching
    generation/worker.py::_stamp_request_interpretation's own contract.
    """
    story = _story("in_review")
    version_row = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob={},
        moderation_report=make_clean_moderation_report(),
    )
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=version_row)
    session.execute = AsyncMock(
        side_effect=[
            _scalar_result(uuid.uuid4()),
            _scalar_result(None),  # no StoryRequest matches the concept_id
        ]
    )

    result = await service.approve(session, _principal("admin"), story, 1)

    assert result is version_row
    assert story.status == "published"


@pytest.mark.unit
async def test_auto_reject_moves_draft_to_needs_revision() -> None:
    """auto_reject() transitions draft to needs_revision and flushes."""
    session = AsyncMock(spec=AsyncSession)
    story = _story("draft")

    await service.auto_reject(session, story)

    assert story.status == "needs_revision"
    session.flush.assert_awaited_once()


@pytest.mark.unit
async def test_auto_reject_illegal_state_raises_and_does_not_flush() -> None:
    """auto_reject() on published raises StateTransitionError; no flush."""
    session = AsyncMock(spec=AsyncSession)
    story = _story("published")

    with pytest.raises(StateTransitionError):
        await service.auto_reject(session, story)

    session.flush.assert_not_awaited()


def _mock_stamped_moderation_report() -> dict[str, object]:
    """A report the mock reviewer produced, in its real persisted shape.

    Built through the real ``_stamp_mock_reviewer`` and the real ``to_dict``
    rather than hand-written, so a change to either half of the stamp reaches
    this test instead of drifting away from it. The ADVISORY finding is the
    control: it is a genuine, non-artifact judgment, so the refusal below
    cannot be attributed to "the report had nothing in it".

    Returns:
        The persisted report body for a mock-moderated version.
    """
    report = ModerationReport()
    report.add(
        Finding(
            stage=0,
            source=Source.PIPELINE,
            category="prose_craft_sameness",
            verdict=Verdict.ADVISORY,
            message="self-repetition: 3 nodes repeat another node's body",
            node_id=None,
        )
    )
    _stamp_mock_reviewer(report)
    return report.to_dict()


@pytest.mark.unit
async def test_approve_refuses_a_mock_stamped_report_even_with_an_override() -> None:
    """A mock-moderated story is unapprovable, and no reason text rescues it.

    Since the gap-G1 stamp became unconditional, every story moderated with
    the mock reviewer carries ``reviewer_independent = False``, which
    ``moderation_report_unusable`` treats as decisive on its own. That check
    sits ABOVE the ``severe_finding_counts`` gate in ``approve``, and
    ``override_reason`` gates only the lower one, so an admin has no path
    through: the answer is to re-moderate with a real reviewer, not to
    justify the approval.

    Passing an override here is the whole point of the test. Omitting it
    would leave the refusal ambiguous between "unusable report" and "no
    reason supplied", which is the reading that would let a future change
    quietly wire an override into this gate with the test still green.
    """
    story = _story("in_review")
    version_row = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob={},
        moderation_report=_mock_stamped_moderation_report(),
    )
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=version_row)
    # Built outside the raises block: S5778 allows exactly one call in the
    # body, so a second one here would make the assertion ambiguous about
    # which call raised.
    principal = _principal("admin")

    with pytest.raises(BusinessLogicError) as excinfo:
        await service.approve(
            session,
            principal,
            story,
            1,
            override_reason="reviewed the whole book by hand",
        )

    # The rule name, not the message text: the message is prose that may be
    # reworded, while the rule is the machine-readable identity of the gate
    # that fired. Asserting it is what distinguishes this refusal from the
    # never-screened and illegal-transition ones above it.
    assert excinfo.value.details["rule"] == "approve_with_unusable_moderation"
    assert story.status == "in_review"
    session.flush.assert_not_awaited()
