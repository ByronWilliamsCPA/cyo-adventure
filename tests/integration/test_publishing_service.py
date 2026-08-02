"""Integration tests for the publishing service (real async Postgres session)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, select

from cyo_adventure.core.exceptions import BusinessLogicError, StateTransitionError
from cyo_adventure.db.models import (
    Concept,
    Family,
    GenerationJob,
    Storybook,
    StorybookVersion,
    StoryRequest,
    User,
)
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


async def test_approve_stamps_resulting_storybook_id(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """approve() links the originating story_request to the published book (W0.4).

    Full request -> concept -> job -> storybook chain, matching how
    generation/worker.py and story_requests/service.py actually build it:
    a StoryRequest with concept_id set, a GenerationJob carrying the same
    concept_id plus the (storybook_id, version) the worker persisted.
    """
    async with sessions() as session:
        book, guardian_id = await _make_story(
            session,
            status="in_review",
            moderation_report=make_clean_moderation_report(),
        )
        concept = Concept(family_id=book.family_id, brief={"topic": "dragons"})
        session.add(concept)
        await session.flush()
        request = StoryRequest(
            family_id=book.family_id,
            request_text="a dragon who loves pancakes",
            age_band="5-8",
            concept_id=concept.id,
        )
        session.add(request)
        session.add(
            GenerationJob(
                concept_id=concept.id,
                storybook_id=book.id,
                version=1,
                status="passed",
            )
        )
        await session.flush()

        principal = _principal(guardian_id, book.family_id)
        await approval_service.approve(session, principal, book, 1)

        assert request.resulting_storybook_id == book.id


async def test_approve_without_generation_job_leaves_resulting_storybook_id_none(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """approve() no-ops the stamp when no GenerationJob matches the book.

    A catalog-imported or hand-crafted storybook has no originating
    GenerationJob row, so there is no concept_id (and therefore no request)
    to resolve; publishing must still succeed.
    """
    async with sessions() as session:
        book, guardian_id = await _make_story(
            session,
            status="in_review",
            moderation_report=make_clean_moderation_report(),
        )
        principal = _principal(guardian_id, book.family_id)
        version_row = await approval_service.approve(session, principal, book, 1)
        assert book.status == "published"
        assert version_row.approved_by == guardian_id


async def test_story_request_survives_storybook_deletion_with_link_nulled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Deleting a storybook SET NULLs resulting_storybook_id, not the request row.

    W0.4's FK mirrors every other nullable, non-owning reference on
    story_request (profile_id, reviewed_by, concept_id, anchor_storybook_id):
    the request is family-owned content that must survive its linked
    storybook vanishing by any means, including a raw delete. No live
    application code path deletes a Storybook row today (see the migration's
    own header comment), so this exercises the schema-level guarantee
    directly rather than through an admin endpoint.
    """
    async with sessions() as session:
        book, guardian_id = await _make_story(
            session,
            status="in_review",
            moderation_report=make_clean_moderation_report(),
        )
        concept = Concept(family_id=book.family_id, brief={"topic": "dragons"})
        session.add(concept)
        await session.flush()
        request = StoryRequest(
            family_id=book.family_id,
            request_text="a dragon who loves pancakes",
            age_band="5-8",
            concept_id=concept.id,
        )
        session.add(request)
        session.add(
            GenerationJob(
                concept_id=concept.id,
                storybook_id=book.id,
                version=1,
                status="passed",
            )
        )
        await session.flush()
        principal = _principal(guardian_id, book.family_id)
        await approval_service.approve(session, principal, book, 1)
        assert request.resulting_storybook_id == book.id
        request_id = request.id
        await session.commit()

    async with sessions() as session:
        # StorybookVersion CASCADEs from Storybook (ondelete="CASCADE"); the
        # version row must go first so the FK from storybook_version does not
        # block the storybook delete under a database that enforces the
        # constraint eagerly within the same statement ordering.
        await session.execute(
            delete(StorybookVersion).where(StorybookVersion.storybook_id == book.id)
        )
        await session.execute(delete(Storybook).where(Storybook.id == book.id))
        await session.commit()

    async with sessions() as session:
        survivor = await session.scalar(
            select(StoryRequest).where(StoryRequest.id == request_id)
        )
        assert survivor is not None
        assert survivor.resulting_storybook_id is None


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
    """Build an admin approver Principal for service tests.

    Every approval-service operation exercised here (approve, send_back,
    archive) is admin-only in production: api/approval.py routes each handler
    through ``_load_admin_story``, which enforces ``principal.is_admin``, and
    ``approve()`` now re-checks the same invariant at the service boundary.
    The principal therefore carries the admin capability (a valid dual-role
    ``role=guardian, is_admin=True`` adult).
    """
    from cyo_adventure.api.deps import Principal

    return Principal(
        subject="g",
        user_id=user_id,
        role="guardian",
        family_id=family_id,
        profile_ids=frozenset(),
        is_admin=True,
    )
