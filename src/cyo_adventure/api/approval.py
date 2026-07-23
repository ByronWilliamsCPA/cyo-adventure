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
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select, tuple_

from cyo_adventure.api.deps import Context
from cyo_adventure.api.review_surface import (
    build_review_queue_item,
    build_review_surface,
)
from cyo_adventure.api.schemas import (
    ApproveBody,
    ApprovedView,
    ArchivedView,
    ReviewQueueItem,
    ReviewQueueView,
    ReviewSurfaceView,
    SendBackRequest,
    SentBackView,
    StorybookLibraryView,
    StorybookSummary,
    SubmittedView,
    error_responses,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.moderation.thresholds import load_admin_noise_floor
from cyo_adventure.publishing import service as approval_service
from cyo_adventure.publishing.state_machine import Visibility
from cyo_adventure.storybook.models import ContentFlags
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/v1", tags=["approval"], responses=error_responses(401, 403)
)

_logger = get_logger(__name__)

_IN_REVIEW = "in_review"

# The five storybook lifecycle statuses (mirrors db/models._STORYBOOK_STATUS_VALUES).
# Used to validate the master-library status filter (P19).
_STORYBOOK_STATUSES = frozenset(
    {"draft", "in_review", "needs_revision", "published", "archived"}
)

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
    # #CRITICAL: concurrency: every admin transition (submit/approve/send_back/
    # archive) loads its storybook through this one helper, so locking here
    # closes all four at once. Without the lock, two admins approving the same
    # in-review story concurrently both read status="in_review" before either
    # commits, both pass publishing/service.py's in-memory status re-check, and
    # the last writer silently overwrites approved_by (audit Finding 3, #129).
    # With the lock, the second admin's transaction blocks here until the first
    # commits, then reloads status="published" and 409s instead of overwriting.
    # #VERIFY: SELECT ... FOR UPDATE on Postgres;
    # tests/unit/test_approval_unit.py::test_load_admin_story_locks_row_for_update
    # asserts the lock clause is present; a true two-session concurrent test is
    # deferred (accepted debt, see the #129 issue thread).
    stmt = select(Storybook).where(Storybook.id == storybook_id).with_for_update()
    book = (await ctx.session.execute(stmt)).scalar_one_or_none()
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    return book


@router.post("/storybooks/{storybook_id}/submit", responses=error_responses(404, 409))
async def submit_storybook(storybook_id: str, ctx: Context) -> SubmittedView:
    """Submit a draft or needs-revision story for review (admin only)."""
    book = await _load_admin_story(ctx, storybook_id)
    await approval_service.submit(ctx.session, book)
    return SubmittedView(
        id=book.id,
        status=cast("Literal['in_review']", book.status),
        current_published_version=book.current_published_version,
    )


@router.post(
    "/storybooks/{storybook_id}/approve", responses=error_responses(400, 404, 409)
)
async def approve_storybook(
    storybook_id: str, ctx: Context, body: ApproveBody | None = None
) -> ApprovedView:
    """Approve and publish the latest version of an in-review story (admin only)."""
    book = await _load_admin_story(ctx, storybook_id)
    version = await _latest_version(ctx.session, storybook_id)
    # #ASSUME: data integrity: a missing body means visibility=family (the
    # pre-WS-E contract); ApproveBody's Literal rejects unmodeled values at 422.
    # #VERIFY: test_approve_rejects_unknown_visibility.
    visibility = Visibility(body.visibility) if body is not None else Visibility.FAMILY
    version_row = await approval_service.approve(
        ctx.session, ctx.principal, book, version, visibility=visibility
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
        visibility=cast("Literal['family', 'catalog']", book.visibility),
    )


@router.post(
    "/storybooks/{storybook_id}/send-back", responses=error_responses(404, 409)
)
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


@router.post("/storybooks/{storybook_id}/archive", responses=error_responses(404, 409))
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


@router.get("/storybooks/{storybook_id}/review", responses=error_responses(404))
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
    # #ASSUME: security: floor denoises the ADMIN review view only; admin_surfaces
    # guarantees FLAG/BLOCK/unscored findings always surface (bright-line 0.0
    # blocks are never hidden). The floor reaches build_review_surface from two
    # admin call sites (this detail view and get_review_queue below); guardian
    # reuse paths keep passing None.
    # #VERIFY: tests/integration/test_review_surface_noise_floor.py.
    floor = await load_admin_noise_floor(ctx.session)
    return build_review_surface(
        status=book.status,
        storybook_id=storybook_id,
        version=resolved,
        blob=version_row.blob,
        moderation_report=version_row.moderation_report,
        admin_noise_floor=floor,
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
    # #EDGE: data integrity: keys is empty only when every in_review story lacks
    # a version row (a corrupt-at-rest anomaly). Short-circuit before issuing a
    # degenerate empty composite-IN query, and log it so the anomaly is visible.
    # #VERIFY: tests/integration/test_approval_api.py seeds an in_review story
    # with no version row.
    if not keys:
        _logger.warning("review_queue_all_stories_unversioned", story_count=len(books))
        return ReviewQueueView(items=[])
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
    # #ASSUME: security: the queue is admin-only (gated above), so the admin
    # noise floor applies here exactly as on the detail view: a noise-only
    # story must not land in the console's Flagged bucket while its detail
    # view (floored) shows nothing. Loaded once for the whole listing, never
    # per row.
    # #VERIFY: tests/integration/test_review_surface_noise_floor.py queue case;
    # admin_surfaces guarantees FLAG/BLOCK/unscored findings always surface.
    floor = await load_admin_noise_floor(ctx.session)
    items: list[ReviewQueueItem] = []
    for book in books:
        version = latest.get(book.id)
        # #EDGE: data integrity: an in_review story with no resolvable latest
        # version is an anomaly; log it (with its id) rather than dropping it
        # silently, since this queue is the operator's only surface for it.
        if version is None:
            _logger.warning(
                "review_queue_storybook_missing_version", storybook_id=book.id
            )
            continue
        row = by_key.get((book.id, version))
        if row is None:
            _logger.warning(
                "review_queue_storybook_missing_version",
                storybook_id=book.id,
                version=version,
            )
            continue
        try:
            items.append(
                build_review_queue_item(
                    storybook_id=book.id,
                    status=book.status,
                    version=version,
                    blob=row.blob,
                    moderation_report=row.moderation_report,
                    admin_noise_floor=floor,
                    created_at=row.created_at,
                )
            )
        except ValidationError as exc:
            # #EDGE: data integrity: one story's moderation_report is corrupt at
            # rest. Isolate the bad row (logged with its id) instead of failing
            # the whole queue with a 422: the queue is the safety operator's only
            # surface, so one corrupt row must not deny review of every other
            # pending story. Mirrors library.py's per-row degrade-with-warning.
            # #VERIFY: tests/integration/test_approval_api.py corrupt-report case.
            _logger.warning(
                "review_queue_item_corrupt",
                storybook_id=book.id,
                version=version,
                error=str(exc),
            )
            continue
    return ReviewQueueView(items=items)


def _summary_title(blob: object, storybook_id: str) -> str:
    """Return the story title from the blob, or the id as a fallback."""
    if isinstance(blob, dict):
        title = blob.get("title")
        if isinstance(title, str) and title:
            return title
    return storybook_id


def _summary_age_band(blob: object) -> str | None:
    """Return the target age band from the blob metadata, or None if absent."""
    if isinstance(blob, dict):
        metadata = blob.get("metadata")
        if isinstance(metadata, dict):
            band = metadata.get("age_band")
            if isinstance(band, str) and band:
                return band
    return None


def _summary_themes(blob: object) -> list[str]:
    """Return the story's themes from the blob metadata, or [] if absent.

    Args:
        blob: The stored Storybook content blob (``StorybookVersion.blob``),
            typed ``object`` because a story with no version row yet has none.

    Returns:
        list[str]: ``metadata.themes``, filtered to string entries, or ``[]``
            when the blob, metadata, or field is absent.
    """
    if isinstance(blob, dict):
        metadata = blob.get("metadata")
        if isinstance(metadata, dict):
            themes = metadata.get("themes")
            if isinstance(themes, list):
                return [theme for theme in themes if isinstance(theme, str)]
    return []


def _summary_content_flags(blob: object) -> ContentFlags | None:
    """Return the story's content-sensitivity flags, or None if absent/invalid.

    Args:
        blob: The stored Storybook content blob (``StorybookVersion.blob``),
            typed ``object`` because a story with no version row yet has none.

    Returns:
        ContentFlags | None: The parsed ``metadata.content_flags``, or
            ``None`` when absent or invalid.
    """
    # #ASSUME: data integrity: a blob written by an older schema version may
    # carry a ``content_flags`` shape ``ContentFlags`` no longer accepts;
    # degrade to ``None`` (omit the badge) rather than fail the whole library
    # listing for a detail-only field.
    # #VERIFY: tests/unit/test_approval_unit.py.
    if isinstance(blob, dict):
        metadata = blob.get("metadata")
        if isinstance(metadata, dict):
            flags = metadata.get("content_flags")
            if isinstance(flags, dict):
                try:
                    return ContentFlags.model_validate(flags)
                except PydanticValidationError:
                    return None
    return None


@router.get("/admin/storybooks")
async def list_admin_storybooks(
    ctx: Context, status: str | None = None
) -> StorybookLibraryView:
    """Return every storybook for the admin master library (admin only, P19).

    Unlike the review queue (in_review only), this lists stories in ANY
    lifecycle status so an admin can browse and re-open a published, archived,
    needs_revision, or draft story via the existing review detail view. Newest
    activity (latest version's creation time) first.

    Args:
        ctx: The request context (principal and session).
        status: Optional lifecycle-status filter (e.g. ``"published"``); when
            omitted, every status is returned.

    Returns:
        StorybookLibraryView: One summary per storybook, newest activity first.

    Raises:
        AuthorizationError: If the caller is not an admin (-> 403).
        ValidationError: If ``status`` is not a recognized lifecycle status.
    """
    # #CRITICAL: security: admin-only GLOBAL library, mirroring get_review_queue.
    # The role is checked before any row is read, and authorize_family is NOT
    # called: the safety operator browses cross-family.
    # #VERIFY: tests/unit/test_approval_unit.py::test_admin_storybooks_blocks_non_admin.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")

    # #EDGE: data-integrity: reject an unknown status filter loudly rather than
    # silently returning everything (which would mislead the operator).
    # #VERIFY: test_admin_storybooks_rejects_unknown_status.
    if status is not None and status not in _STORYBOOK_STATUSES:
        msg = f"unknown storybook status '{status}'"
        raise ValidationError(msg, field="status", value=status)

    stmt = select(Storybook)
    if status is not None:
        stmt = stmt.where(Storybook.status == status)
    books = (await ctx.session.scalars(stmt)).all()
    if not books:
        return StorybookLibraryView(items=[])

    # #ASSUME: external-resources: resolve the latest version per story and load
    # those version rows in two bulk queries, never one round trip per story
    # (same pattern as get_review_queue).
    # #VERIFY: test_admin_storybooks_is_bulk_not_n_plus_one.
    ids = [book.id for book in books]
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
    if not keys:
        # Every story lacks a version row (draft not yet generated); still list
        # them with a best-effort title so the operator can see them.
        return StorybookLibraryView(
            items=sorted(
                (
                    StorybookSummary(
                        storybook_id=book.id,
                        title=book.id,
                        status=book.status,
                        version=0,
                        family_id=str(book.family_id),
                        current_published_version=book.current_published_version,
                        created_at=book.created_at,
                    )
                    for book in books
                ),
                key=lambda item: item.created_at,
                reverse=True,
            )
        )
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

    items: list[StorybookSummary] = []
    for book in books:
        version = latest.get(book.id)
        row = by_key.get((book.id, version)) if version is not None else None
        blob = row.blob if row is not None else None
        items.append(
            StorybookSummary(
                storybook_id=book.id,
                title=_summary_title(blob, book.id),
                status=book.status,
                version=version if version is not None else 0,
                age_band=_summary_age_band(blob),
                family_id=str(book.family_id),
                current_published_version=book.current_published_version,
                created_at=book.created_at,
                updated_at=row.created_at if row is not None else None,
                themes=_summary_themes(blob),
                content_flags=_summary_content_flags(blob),
            )
        )
    # Newest activity first: sort by the latest version's creation time, falling
    # back to the storybook's own created_at for versionless drafts.
    items.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
    return StorybookLibraryView(items=items)
