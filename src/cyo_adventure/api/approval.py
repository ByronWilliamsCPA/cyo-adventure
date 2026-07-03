"""Admin-only storybook approval endpoints.

The publish state machine's HTTP surface: submit a draft for review, approve
(and publish) an in-review story, send one back for revision, or archive a
published one. Approval is a backend safety process owned by a global admin, so
every handler requires the admin role (403 otherwise) and authority is
cross-family (authorize_family is intentionally NOT called). Each handler loads
the story (404) and calls the publishing service (409 on an illegal transition).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from fastapi import APIRouter
from sqlalchemy import func, select, tuple_

from cyo_adventure.api.deps import Context
from cyo_adventure.api.review_surface import (
    build_review_queue_item,
    build_review_surface,
)
from cyo_adventure.api.schemas import (
    ApprovedView,
    ArchivedView,
    ReviewQueueView,
    ReviewSurfaceView,
    SendBackRequest,
    SentBackView,
    SubmittedView,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.publishing import service as approval_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["approval"])

_IN_REVIEW = "in_review"

# #ASSUME: data integrity: each `cast("Literal[...]", book.status)` call below
# assumes approval_service's corresponding call (submit/approve/send_back/archive)
# leaves book.status at exactly the one literal named, per
# publishing/state_machine.py's LEGAL_TRANSITIONS. The cast itself performs no
# runtime check; Pydantic revalidates the claim when the response model is
# constructed, so a service/state-machine bug surfaces as a loud error there
# instead of a silently-wrong status.
# #VERIFY: publishing/state_machine.py's LEGAL_TRANSITIONS still maps SUBMIT,
# APPROVE, SEND_BACK, and ARCHIVE to exactly in_review, published,
# needs_revision, and archived respectively (tests/unit/test_state_machine.py).


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
        status=cast("Literal['in_review']", book.status),
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
        status=cast("Literal['published']", book.status),
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
    return SentBackView(
        id=book.id,
        status=cast("Literal['needs_revision']", book.status),
        reason=body.reason,
    )


@router.post("/storybooks/{storybook_id}/archive")
async def archive_storybook(storybook_id: str, ctx: Context) -> ArchivedView:
    """Archive a published story, removing it from the library (admin only)."""
    book = await _load_admin_story(ctx, storybook_id)
    await approval_service.archive(ctx.session, ctx.principal, book)
    return ArchivedView(id=book.id, status=cast("Literal['archived']", book.status))


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
        AuthorizationError: If the caller is not an admin (403).
        ValidationError: If a supplied version is not a positive integer, or the
            stored moderation report is corrupt at rest.
        ResourceNotFoundError: If the story or the requested version does not exist.
    """
    # #CRITICAL: security: this reads unpublished, possibly-flagged content, so it
    # must be admin-only; _load_admin_story enforces the admin role (global,
    # cross-family authority, same as every other handler in this module) before
    # any row is read (a child token must never reach the review surface).
    # #VERIFY: _load_admin_story raises AuthorizationError -> 403 for non-admins.
    book = await _load_admin_story(ctx, storybook_id)
    # #ASSUME: data integrity: version is a client-supplied query parameter with
    # no schema-level lower bound; reject a non-positive value before it reaches
    # the composite-key lookup below rather than let it silently 404.
    # #VERIFY: tests/unit/test_approval_unit.py::test_review_surface_rejects_non_positive_version.
    if version is not None and version <= 0:
        msg = "version must be a positive integer"
        raise ValidationError(msg, field="version", value=version)
    resolved = (
        version
        if version is not None
        else await _latest_version(ctx.session, storybook_id)
    )
    # #ASSUME: external resources: this composite-key lookup is a second async
    # DB round trip after _load_admin_story's; both must complete within the
    # request's session/transaction scope (api/deps.py::Context).
    # #VERIFY: ctx.session is request-scoped and closed by the deps context manager.
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


@router.get("/review-queue")
async def get_review_queue(ctx: Context) -> ReviewQueueView:
    """Return every storybook awaiting an admin publish decision (admin only).

    Args:
        ctx: The request context (principal and session).

    Returns:
        ReviewQueueView: One item per ``in_review`` storybook, across all
            families, carrying the screened flag and flagged count so the
            console can bucket Flagged versus Ready to review.

    Raises:
        AuthorizationError: If the caller is not an admin (-> 403).
    """
    # #CRITICAL: security: admin-only GLOBAL queue. The role is checked before
    # any row is read (a non-admin never learns which stories are in review),
    # and authorize_family is intentionally NOT called: the safety operator
    # screens cross-family, mirroring get_review_surface / _load_admin_story.
    # #VERIFY: tests/unit/test_approval_unit.py::test_review_queue_blocks_non_admin
    # (no DB round trip) and tests/integration/test_approval_api.py cross-family case.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")
    books = (
        await ctx.session.scalars(
            select(Storybook).where(Storybook.status == _IN_REVIEW)
        )
    ).all()
    if not books:
        return ReviewQueueView(items=[])
    # #ASSUME: external resources: resolve the latest version per story and load
    # those version rows in two bulk queries (grouped max, then a composite
    # (storybook_id, version) IN filter), never one round trip per story.
    # #VERIFY: tests/unit/test_approval_unit.py::test_review_queue_is_bulk_not_n_plus_one
    # asserts exactly two scalars() and one execute() for two stories.
    ids = [book.id for book in books]
    # #ASSUME: data integrity: the grouped-max query returns untyped SQL Row
    # objects; cast the result to its known (storybook_id, max_version) shape at
    # this boundary so the queue's version lookups are concretely typed, not Any.
    # This mirrors the module's existing cast() use at typing boundaries.
    # #VERIFY: each group has at least one version row, so max_version is never
    # None; a story with no versions never appears here and is dropped below.
    latest_rows = cast(
        "list[tuple[str, int]]",
        (
            await ctx.session.execute(
                select(
                    StorybookVersion.storybook_id,
                    func.max(StorybookVersion.version),
                )
                .where(StorybookVersion.storybook_id.in_(ids))
                .group_by(StorybookVersion.storybook_id)
            )
        ).all(),
    )
    latest: dict[str, int] = dict(latest_rows)
    keys = list(latest.items())
    version_rows = (
        await ctx.session.scalars(
            select(StorybookVersion).where(
                tuple_(StorybookVersion.storybook_id, StorybookVersion.version).in_(
                    keys
                )
            )
        )
    ).all()
    by_key = {(row.storybook_id, row.version): row for row in version_rows}
    items = [
        build_review_queue_item(
            storybook_id=book.id,
            status=book.status,
            version=latest[book.id],
            blob=by_key[(book.id, latest[book.id])].blob,
            moderation_report=by_key[(book.id, latest[book.id])].moderation_report,
        )
        for book in books
        if book.id in latest and (book.id, latest[book.id]) in by_key
    ]
    return ReviewQueueView(items=items)
