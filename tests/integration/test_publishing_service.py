"""Integration tests for the publishing service (real async Postgres session)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.exceptions import BusinessLogicError, StateTransitionError
from cyo_adventure.db.models import Family, Storybook, StorybookVersion, User
from cyo_adventure.publishing import service as approval_service
from tests.conftest import make_clean_moderation_report

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _make_story(
    session: AsyncSession,
    *,
    status: str,
    moderation_report: dict[str, object] | None = None,
) -> tuple[Storybook, uuid.UUID]:
    """Seed one family, one guardian, and a single-version story in ``status``.

    Returns the storybook row and the guardian's user id.
    """
    fam = Family(name="Fam")
    session.add(fam)
    await session.flush()
    guardian = User(family_id=fam.id, role="guardian", authn_subject="g")
    session.add(guardian)
    await session.flush()
    book = Storybook(
        id="story-1", family_id=fam.id, status=status, current_published_version=None
    )
    session.add(book)
    await session.flush()
    session.add(
        StorybookVersion(
            storybook_id="story-1",
            version=1,
            blob={"id": "story-1"},
            moderation_report=moderation_report,
        )
    )
    await session.flush()
    return book, guardian.id


async def test_approve_stamps_provenance_and_publishes(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """approve() sets published + current_published_version + approved_by + published_at."""
    async with sessions() as session:
        book, guardian_id = await _make_story(
            session,
            status="in_review",
            moderation_report=make_clean_moderation_report(),
        )
        principal = _principal(guardian_id, book.family_id)
        version_row = await approval_service.approve(session, principal, book, 1)
        assert book.status == "published"
        assert book.current_published_version == 1
        assert version_row.approved_by == guardian_id
        assert version_row.published_at is not None


async def test_approve_from_draft_raises(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """approve() on a draft is an illegal transition (must go through in_review)."""
    async with sessions() as session:
        book, guardian_id = await _make_story(session, status="draft")
        principal = _principal(guardian_id, book.family_id)
        with pytest.raises(StateTransitionError):
            await approval_service.approve(session, principal, book, 1)
        assert book.status == "draft"


async def test_approve_without_moderation_raises(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """approve() on an in_review story with no moderation_report is blocked.

    Closes C3-SAFETY Findings 1-2 (adversarial-safety-evaluation.md): a story
    that reached in_review by any route other than the moderated generation
    worker (the import path, or a direct admin submit) must not be
    approvable/publishable until it has been screened.
    """
    async with sessions() as session:
        book, guardian_id = await _make_story(session, status="in_review")
        principal = _principal(guardian_id, book.family_id)
        with pytest.raises(BusinessLogicError):
            await approval_service.approve(session, principal, book, 1)
        assert book.status == "in_review"


async def test_submit_then_send_back(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """submit() draft->in_review, send_back() in_review->needs_revision."""
    async with sessions() as session:
        book, guardian_id = await _make_story(
            session,
            status="draft",
            moderation_report=make_clean_moderation_report(),
        )
        principal = _principal(guardian_id, book.family_id)
        await approval_service.submit(session, book)
        assert book.status == "in_review"
        await approval_service.send_back(session, principal, book, "too scary")
        assert book.status == "needs_revision"


async def test_submit_without_moderation_raises(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """submit() on a draft with no moderation_report is blocked (closes #57).

    Mirrors test_approve_without_moderation_raises: a story that reached
    draft by any route other than the moderated generation worker must not
    be movable to in_review until it has been screened.
    """
    async with sessions() as session:
        book, _guardian_id = await _make_story(session, status="draft")
        with pytest.raises(BusinessLogicError):
            await approval_service.submit(session, book)
        assert book.status == "draft"


async def test_archive_published(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """archive() published->archived."""
    async with sessions() as session:
        book, guardian_id = await _make_story(session, status="published")
        principal = _principal(guardian_id, book.family_id)
        await approval_service.archive(session, principal, book)
        assert book.status == "archived"


def _principal(user_id: uuid.UUID, family_id: uuid.UUID) -> object:
    """Build a guardian Principal for service tests."""
    from cyo_adventure.api.deps import Principal

    return Principal(
        subject="g",
        user_id=user_id,
        role="guardian",
        family_id=family_id,
        profile_ids=frozenset(),
    )
