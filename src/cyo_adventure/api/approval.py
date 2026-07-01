"""Admin-only storybook approval endpoints.

The publish state machine's HTTP surface: submit a draft for review, approve
(and publish) an in-review story, send one back for revision, or archive a
published one. Approval is a backend safety process owned by a global admin, so
every handler requires the admin role (403 otherwise) and authority is
cross-family (authorize_family is intentionally NOT called). Each handler loads
the story (404) and calls the publishing service (409 on an illegal transition).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import func, select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.review_surface import build_review_surface
from cyo_adventure.api.schemas import (
    ApprovedView,
    ArchivedView,
    ReviewSurfaceView,
    SendBackRequest,
    SentBackView,
    SubmittedView,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
)
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.publishing import service as approval_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["approval"])


async def _load_admin_story(ctx: Context, storybook_id: str) -> Storybook:
    """Load a storybook for an admin action, enforcing the admin role first.

    Args:
        ctx: The request context (principal + session).
        storybook_id: The story id from the path.

    Returns:
        Storybook: The storybook (any family; admin is global).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ResourceNotFoundError: If the story does not exist (404).
    """
    # #CRITICAL: security: admin-only GLOBAL operation. The role is checked
    # BEFORE the load so a non-admin never learns whether a story exists, and
    # authorize_family is intentionally NOT called because admin authority is
    # cross-family (the backend safety-review operator).
    # #VERIFY: non-admin -> 403; admin + unknown id -> 404.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    return book


@router.post("/storybooks/{storybook_id}/submit")
async def submit_storybook(storybook_id: str, ctx: Context) -> SubmittedView:
    """Submit a draft or needs-revision story for review (admin only)."""
    book = await _load_admin_story(ctx, storybook_id)
    await approval_service.submit(ctx.session, book)
    return SubmittedView(
        id=book.id,
        status=book.status,
        current_published_version=book.current_published_version,
    )


@router.post("/storybooks/{storybook_id}/approve")
async def approve_storybook(storybook_id: str, ctx: Context) -> ApprovedView:
    """Approve and publish the latest version of an in-review story (admin only)."""
    book = await _load_admin_story(ctx, storybook_id)
    version = await _latest_version(ctx.session, storybook_id)
    version_row = await approval_service.approve(
        ctx.session, ctx.principal, book, version
    )
    # #CRITICAL: security: a successful approve is the SOLE published path and the
    # service stamps approved_by + published_at in the same operation, so both are
    # non-None here; ApprovedView's required fields encode that invariant in the
    # wire contract (the response layer cannot emit published-without-approver).
    # #VERIFY: approval_service.approve sets both before flush; None would be a bug.
    if version_row.approved_by is None or version_row.published_at is None:
        msg = "approved version is missing its approval stamp"
        raise BusinessLogicError(msg, rule="publish_without_approver")
    return ApprovedView(
        id=book.id,
        status=book.status,
        current_published_version=version,
        approved_by=str(version_row.approved_by),
        published_at=version_row.published_at,
    )


@router.post("/storybooks/{storybook_id}/send-back")
async def send_back_storybook(
    storybook_id: str, body: SendBackRequest, ctx: Context
) -> SentBackView:
    """Send an in-review story back for revision with a reason (admin only)."""
    book = await _load_admin_story(ctx, storybook_id)
    await approval_service.send_back(ctx.session, ctx.principal, book, body.reason)
    return SentBackView(id=book.id, status=book.status, reason=body.reason)


@router.post("/storybooks/{storybook_id}/archive")
async def archive_storybook(storybook_id: str, ctx: Context) -> ArchivedView:
    """Archive a published story, removing it from the library (admin only)."""
    book = await _load_admin_story(ctx, storybook_id)
    await approval_service.archive(ctx.session, ctx.principal, book)
    return ArchivedView(id=book.id, status=book.status)


async def _latest_version(session: AsyncSession, storybook_id: str) -> int:
    """Return the highest version number for a storybook.

    Args:
        session: The request session.
        storybook_id: The story id.

    Returns:
        int: The latest version number.

    Raises:
        ResourceNotFoundError: If the story has no versions.
    """
    # #ASSUME: data integrity: slice 1 stories are single-version, so "approve
    # the storybook" means approve its latest (only) version.
    # #VERIFY: a story with no versions cannot be approved (404).
    latest = await session.scalar(
        select(func.max(StorybookVersion.version)).where(
            StorybookVersion.storybook_id == storybook_id
        )
    )
    if latest is None:
        msg = f"storybook '{storybook_id}' has no versions"
        raise ResourceNotFoundError(msg)
    return latest


@router.get("/storybooks/{storybook_id}/review")
async def get_review_surface(
    storybook_id: str,
    ctx: Context,
    version: int | None = None,
) -> ReviewSurfaceView:
    """Return the guardian review surface for a story version (admin only).

    Args:
        storybook_id: The story to review.
        ctx: The request context (principal and session).
        version: The version to review; defaults to the latest.

    Returns:
        ReviewSurfaceView: Blob plus moderation summary, flagged passages, and
            story-level findings.

    Raises:
        AuthorizationError: If the principal is not an admin/guardian for the family.
        ResourceNotFoundError: If the story or the requested version does not exist.
    """
    # #CRITICAL: security: this reads unpublished, possibly-flagged content, so it
    # must be admin-only and family-scoped; _load_admin_story enforces both before
    # any row is read (a child token must never reach the review surface).
    # #VERIFY: _load_admin_story raises AuthorizationError -> 403 for non-admins.
    book = await _load_admin_story(ctx, storybook_id)
    resolved = (
        version
        if version is not None
        else await _latest_version(ctx.session, storybook_id)
    )
    version_row = await ctx.session.get(StorybookVersion, (storybook_id, resolved))
    if version_row is None:
        msg = f"version {resolved} of storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    return build_review_surface(
        status=book.status,
        storybook_id=storybook_id,
        version=resolved,
        blob=version_row.blob,
        moderation_report=version_row.moderation_report,
    )
