"""Docker-independent unit tests for cyo_adventure.publishing.service.

These tests call the service functions directly with a mocked AsyncSession,
constructing ORM objects without a DB. They cover every function and both
legal and illegal state-transition paths.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.core.exceptions import (
    BusinessLogicError,
    ResourceNotFoundError,
    StateTransitionError,
)
from cyo_adventure.db.models import Storybook, StorybookVersion
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
    session = AsyncMock()

    await service.submit(session, story)

    assert story.status == "in_review"
    session.flush.assert_awaited_once()


@pytest.mark.unit
async def test_submit_needs_revision_moves_to_in_review() -> None:
    """submit() on a needs_revision story transitions to in_review and flushes."""
    story = _story("needs_revision")
    session = AsyncMock()

    await service.submit(session, story)

    assert story.status == "in_review"
    session.flush.assert_awaited_once()


@pytest.mark.unit
async def test_submit_illegal_status_raises() -> None:
    """submit() on an already-published story raises StateTransitionError; no flush."""
    story = _story("published")
    session = AsyncMock()

    with pytest.raises(StateTransitionError):
        await service.submit(session, story)

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
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=1)
    session.get = AsyncMock(return_value=version_row)

    with pytest.raises(BusinessLogicError):
        await service.submit(session, story)

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
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=1)
    session.get = AsyncMock(return_value=version_row)

    await service.submit(session, story)

    assert story.status == "in_review"
    session.flush.assert_awaited_once()


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
    session = AsyncMock()
    session.get = AsyncMock(return_value=version_row)
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
    session = AsyncMock()
    session.get = AsyncMock(return_value=version_row)

    with pytest.raises(BusinessLogicError):
        await service.approve(session, _principal("admin"), story, 1)

    assert story.status == "in_review"
    session.flush.assert_not_awaited()


@pytest.mark.unit
async def test_approve_missing_version_raises() -> None:
    """approve() raises ResourceNotFoundError when the version row is absent."""
    story = _story("in_review")
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    with pytest.raises(ResourceNotFoundError):
        await service.approve(session, _principal("admin"), story, 1)


@pytest.mark.unit
async def test_approve_illegal_status_raises() -> None:
    """approve() on a draft raises StateTransitionError before the version lookup."""
    story = _story("draft")
    session = AsyncMock()
    session.get = AsyncMock()

    with pytest.raises(StateTransitionError):
        await service.approve(session, _principal("admin"), story, 1)

    session.get.assert_not_awaited()


@pytest.mark.unit
async def test_send_back_moves_to_needs_revision() -> None:
    """send_back() transitions in_review to needs_revision and flushes."""
    story = _story("in_review")
    session = AsyncMock()

    await service.send_back(session, _principal("admin"), story, "too scary")

    assert story.status == "needs_revision"
    session.flush.assert_awaited_once()


@pytest.mark.unit
async def test_send_back_illegal_status_raises() -> None:
    """send_back() on a draft raises StateTransitionError; no flush."""
    story = _story("draft")
    session = AsyncMock()

    with pytest.raises(StateTransitionError):
        await service.send_back(session, _principal("admin"), story, "reason")

    session.flush.assert_not_awaited()


@pytest.mark.unit
async def test_archive_moves_to_archived() -> None:
    """archive() transitions published to archived and flushes."""
    story = _story("published", current=1)
    session = AsyncMock()

    await service.archive(session, _principal("admin"), story)

    assert story.status == "archived"
    session.flush.assert_awaited_once()


@pytest.mark.unit
async def test_archive_illegal_status_raises() -> None:
    """archive() on a draft raises StateTransitionError; no flush."""
    story = _story("draft")
    session = AsyncMock()

    with pytest.raises(StateTransitionError):
        await service.archive(session, _principal("admin"), story)

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
    session = AsyncMock()
    session.get = AsyncMock(return_value=version_row)
    before = datetime.now(UTC)

    await service.approve(session, _principal("admin"), story, 2)

    after = datetime.now(UTC)
    assert version_row.published_at is not None
    assert version_row.published_at.tzinfo is not None
    assert before <= version_row.published_at <= after


@pytest.mark.unit
async def test_auto_reject_moves_draft_to_needs_revision() -> None:
    """auto_reject() transitions draft to needs_revision and flushes."""
    session = AsyncMock()
    story = _story("draft")

    await service.auto_reject(session, story)

    assert story.status == "needs_revision"
    session.flush.assert_awaited_once()


@pytest.mark.unit
async def test_auto_reject_illegal_state_raises_and_does_not_flush() -> None:
    """auto_reject() on published raises StateTransitionError; no flush."""
    session = AsyncMock()
    story = _story("published")

    with pytest.raises(StateTransitionError):
        await service.auto_reject(session, story)

    session.flush.assert_not_awaited()
