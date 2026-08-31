"""Storybook approval endpoints, mostly admin-only.

The publish state machine's HTTP surface: submit a draft for review, approve
(and publish) an in-review story, send one back for revision, or archive a
published one. Approval is a backend safety process owned by a global admin, so
every mutating handler requires the admin role (403 otherwise) and authority is
cross-family (authorize_family is intentionally NOT called); each such handler
loads the story via ``_load_admin_story`` (404) and calls the publishing service
(409 on an illegal transition).

The one exception is the read-only ``get_review_surface`` (GET .../review),
which also admits a guardian scoped to their own family via
``_load_review_target``: register G6's "edit half" gives a guardian read
access to the same content ``node_edit.py`` already lets them write. Guardian
veto/reject of a story remains out of scope and undecided (ADR-005); every
state-transition handler in this module stays admin-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NamedTuple, TypeAlias, cast

from fastapi import APIRouter
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import and_, case, func, or_, select, tuple_

from cyo_adventure.api.deps import Context, authorize_family
from cyo_adventure.api.review_surface import (
    build_moderation_decision_detail,
    build_review_queue_item,
    build_review_surface,
)
from cyo_adventure.api.schemas import (
    ApproveBody,
    ApprovedView,
    ArchivedView,
    OutstandingCoverDetail,
    OutstandingDecisionItem,
    OutstandingDecisionsView,
    OutstandingModerationDetail,
    RecalledView,
    RecallRequest,
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
from cyo_adventure.events import Actor
from cyo_adventure.moderation.thresholds import (
    load_admin_noise_floor,
    load_threshold_policy,
)
from cyo_adventure.publishing import service as approval_service
from cyo_adventure.publishing.state_machine import (
    LEGAL_TRANSITIONS,
    Action,
    Status,
    Visibility,
)
from cyo_adventure.storybook.models import ContentFlags
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/v1", tags=["approval"], responses=error_responses(401, 403)
)

_logger = get_logger(__name__)

_IN_REVIEW = "in_review"
_PUBLISHED = "published"
_ADMIN_ROLE_REQUIRED = "admin role required"

# The one cover_status that represents an unmade human decision. The other four
# ("none", "generating", "ready", "failed") are all states in which nobody is
# waiting on an admin: covers/service.py::generate_cover parks a finished cover
# here and only covers/service.py::approve_cover moves it to "ready".
_COVER_PENDING_REVIEW = "pending_review"

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
        msg = _ADMIN_ROLE_REQUIRED
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
    # #CRITICAL: security: same own-family-aware persona stamping as the
    # send-back and release endpoints. An owner resubmitting their own
    # family's story is audited as guardian even though the route is
    # admin-gated; only a cross-family resubmit is stamped admin.
    # #VERIFY: test_dual_role_same_family_submit_stamps_guardian and
    # test_dual_role_foreign_family_submit_stamps_admin in
    # tests/integration/test_pipeline_event_instrumentation.py. Both name the
    # submit path specifically: the file's other submit tests seed an admin
    # whose base role is already admin, so acting_role's two branches return
    # the same string for them and an inverted family comparison would still
    # satisfy their assertions.
    await approval_service.submit(
        ctx.session,
        book,
        actor=Actor.from_principal(
            ctx.principal,
            acting_role=ctx.principal.acting_role(book.family_id).value,
        ),
    )
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
        ctx.session,
        ctx.principal,
        book,
        version,
        visibility=visibility,
        override_reason=body.override_reason if body else None,
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
    # #CRITICAL: security: authorization for this transition is _load_admin_story
    # and nothing in this function body; it raises before the service call for a
    # non-admin or a foreign-family story. Do not reorder the send_back call
    # above it.
    # #VERIFY: tests/integration/test_approval_api.py::test_child_cannot_send_back
    # asserts 403 for a non-admin token on this exact route. There is no
    # cross-family send-back test yet; _load_admin_story is shared with the
    # approve path, which does have one.
    # #ASSUME: data integrity: reason_code is validated twice, and deliberately.
    # SendBackRequest types it as SendBackReasonCodeLiteral so pydantic rejects an
    # unknown code at this boundary with a 422, which is why the declared
    # responses list only 404 and 409; publishing/service.py::send_back validates
    # it again because the API boundary is not its only caller (a script or worker
    # reaching the service directly would otherwise write an out-of-vocabulary
    # label onto an append-only pipeline_event that has no deletion path).
    # #VERIFY: tests/unit/test_send_back_reason_codes.py::
    # test_validate_reason_code_rejects_unknown_code covers the domain half.
    book = await _load_admin_story(ctx, storybook_id)
    await approval_service.send_back(
        ctx.session, ctx.principal, book, body.reason, reason_code=body.reason_code
    )
    return SentBackView(
        id=book.id,
        status=cast("Literal['needs_revision']", book.status),
        reason=body.reason,
        reason_code=body.reason_code,
    )


@router.post("/storybooks/{storybook_id}/archive", responses=error_responses(404, 409))
async def archive_storybook(storybook_id: str, ctx: Context) -> ArchivedView:
    """Archive a published story, removing it from the library (admin only)."""
    book = await _load_admin_story(ctx, storybook_id)
    await approval_service.archive(ctx.session, ctx.principal, book)
    return ArchivedView(id=book.id, status=cast("Literal['archived']", book.status))


@router.post("/storybooks/{storybook_id}/recall", responses=error_responses(404, 409))
async def recall_storybook(
    storybook_id: str, body: RecallRequest, ctx: Context
) -> RecalledView:
    """Recall a published story back to the review queue (admin only).

    The recoverable alternative to ``archive``, added for `RS-C1`. Use it when a
    published book needs another look, typically because the moderation
    thresholds moved after it was approved, so its stored verdict was reached
    under rules that no longer apply.

    Three consequences a caller should know, stated here rather than left to be
    discovered:

    - A ``catalog``-visibility book recalls from **every** family at once, not
      just its owning one, because catalog visibility is ANDed with
      ``status == "published"`` on every read path.
    - Assignment rows **survive**, which is what makes this recoverable:
      re-approving puts the book back on exactly the shelves it left. Nothing
      needs to be reassigned.
    - An offline copy already downloaded to a device is **not** reached. It is
      evicted only by that device's next successful ``/v1/library`` fetch
      (``frontend/src/offline/revocation.ts``); there is no push channel. This
      is pre-existing and shared with ``archive``, so recall does not introduce
      it, but it means neither action is an incident-response tool.
    """
    # #CRITICAL: security: authorization is _load_admin_story and nothing in
    # this body, same as send_back/archive above; it raises before the service
    # call for a non-admin or a foreign-family story. Do not reorder.
    # #VERIFY: tests/integration/test_recall_api.py::
    # test_a_guardian_cannot_recall_a_published_book asserts 403 on this route.
    book = await _load_admin_story(ctx, storybook_id)
    await approval_service.recall(
        ctx.session, ctx.principal, book, reason_code=body.reason_code
    )
    return RecalledView(
        id=book.id,
        status=cast("Literal['in_review']", book.status),
        current_published_version=book.current_published_version,
        reason_code=body.reason_code,
    )


async def _load_review_target(ctx: Context, storybook_id: str) -> Storybook:
    """Load a storybook for the review surface, enforcing role + ownership.

    Read-only counterpart of ``_load_admin_story``, scoped to the GET review
    surface only. Admin keeps global (cross-family) access; a guardian may
    read their own family's story so they can reach the node-edit endpoint's
    existing guardian-or-admin authorization (``node_edit.py::
    _load_edit_target``) with content to edit. This does NOT extend to
    submit/approve/send_back/archive, which stay admin-only via
    ``_load_admin_story``: those are the publish/veto decision, a separate,
    open ADR-005 product question this helper does not touch.

    Args:
        ctx: The request context (principal + session).
        storybook_id: The story id from the path.

    Returns:
        Storybook: The storybook (any family for admin; the caller's own
            family for a guardian).

    Raises:
        AuthorizationError: If the caller is neither admin nor guardian
            (-> 403), or a guardian's family does not own the story (-> 403).
        ResourceNotFoundError: If the story does not exist (-> 404).
    """
    # #CRITICAL: security: role gate before any row is read, mirroring
    # node_edit.py::_load_edit_target exactly. Admin is the global safety
    # operator; guardian is scoped to their own family below via
    # authorize_family. Neither a child nor a device token may read the
    # review surface (it can carry unpublished, possibly-flagged content).
    # #VERIFY: tests/unit/test_approval_unit.py::test_review_surface_blocks_child,
    # ::test_review_surface_blocks_device.
    if not (ctx.principal.is_admin or ctx.principal.is_guardian):
        msg = "admin or guardian role required"
        raise AuthorizationError(msg, required_permission="admin_or_guardian")
    # #ASSUME: concurrency: this is a read-only GET, unlike _load_admin_story
    # and node_edit.py's _load_edit_target which both lock the row because
    # they precede a write. No FOR UPDATE lock here: a concurrent
    # approve/edit racing this read can only produce a stale-but-consistent
    # snapshot, never a lost update, since this handler writes nothing back.
    # #VERIFY: tests/unit/test_approval_unit.py asserts no with_for_update()
    # clause on the statement this helper issues.
    stmt = select(Storybook).where(Storybook.id == storybook_id)
    book = (await ctx.session.execute(stmt)).scalar_one_or_none()
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if not ctx.principal.is_admin:
        # #CRITICAL: security: a guardian may read only their own family's
        # review surface; admin authority is global and skips this check
        # (mirrors node_edit.py::_load_edit_target's identical stance).
        # #VERIFY: tests/integration/test_authz_matrix.py cross-family
        # guardian case; tests/unit/test_approval_unit.py::
        # test_review_surface_guardian_other_family_rejected.
        authorize_family(ctx.principal, book.family_id)
    return book


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
    """Return the review surface for a story version.

    Admin (any family), or guardian for their own family's story.

    Args:
        storybook_id: The story to review.
        ctx: The request context (principal and session).
        version: The version to review; defaults to the latest.

    Returns:
        ReviewSurfaceView: Blob plus moderation summary, flagged passages,
            story-level findings, the ranked/structural/low-advisory merged-
            finding buckets, and the story's validator (RL-13/PL-19) findings.

    Raises:
        AuthorizationError: If the caller is neither admin nor guardian
            (403), or a guardian requests another family's story (403).
        ValidationError: If a supplied version is not a positive integer, or the
            stored moderation report is corrupt at rest.
        ResourceNotFoundError: If the story or the requested version does not exist.
    """
    # #CRITICAL: security: this reads unpublished, possibly-flagged content, so
    # access is admin (global) or guardian scoped to their own family;
    # _load_review_target enforces both the role gate and the family-ownership
    # check before any row is read (a child or device token must never reach
    # the review surface). This is the "edit half" of register G6: it gives a
    # guardian read access to the content node_edit.py already lets them
    # write. It does NOT extend to submit/approve/send_back/archive, which
    # remain admin-only via _load_admin_story -- guardian veto/reject is a
    # separate, open ADR-005 product-scope question, not decided here.
    # #VERIFY: _load_review_target raises AuthorizationError -> 403 for
    # non-admin/non-guardian callers and for a guardian outside the story's
    # family.
    book = await _load_review_target(ctx, storybook_id)
    # #ASSUME: data integrity: version is a client-supplied query parameter with
    # no schema-level lower bound; reject a non-positive value before it reaches
    # the composite-key lookup below rather than let it silently 404.
    # #VERIFY: tests/unit/test_approval_unit.py::
    # test_review_surface_rejects_non_positive_version.
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
    # blocks are never hidden). A guardian caller gets admin_noise_floor=None
    # (build_review_surface's un-denoised default), matching node_edit.py's
    # existing `floor = ... if ctx.principal.is_admin else None` conditional,
    # so a guardian sees every finding at native score, not the admin-tuned
    # noise floor meant for a reviewer triaging the whole cross-family queue.
    # #VERIFY: tests/integration/test_review_surface_noise_floor.py (admin
    # path unchanged); tests/unit/test_approval_unit.py::
    # test_review_surface_guardian_gets_no_noise_floor.
    floor = (
        await load_admin_noise_floor(ctx.session) if ctx.principal.is_admin else None
    )
    # #ASSUME: security: `RS-B3` resolves the admin floor per (age_band,
    # category), so the band rides along with the floor. The policy read is
    # skipped entirely when floor is None (the guardian path), because a None
    # flat floor short-circuits admin_noise_floor_for before the policy is
    # consulted: loading it there would be a query whose result cannot matter.
    # #VERIFY: tests/unit/test_admin_noise_floor.py::
    # test_flat_floor_none_wins_over_a_band_row.
    policy = await load_threshold_policy(ctx.session) if floor is not None else None
    return build_review_surface(
        status=book.status,
        storybook_id=storybook_id,
        version=resolved,
        blob=version_row.blob,
        moderation_report=version_row.moderation_report,
        admin_noise_floor=floor,
        validation_report=version_row.validation_report,
        age_band=_summary_age_band(version_row.blob) or "",
        policy=policy,
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
        msg = _ADMIN_ROLE_REQUIRED
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
    # `RS-B3`: loaded once for the whole listing for the same reason the floor
    # is, and passed per row alongside that row's band so a queue badge and the
    # detail view it links to resolve the same floor.
    policy = await load_threshold_policy(ctx.session)
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
                    age_band=_summary_age_band(row.blob) or "",
                    policy=policy,
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


def _is_recallable(status: str) -> bool:
    """Report whether a RECALL is legal from ``status`` right now.

    Derived from the publish state machine's transition table rather than
    compared against the ``"published"`` literal, so this surface and the
    ``POST .../recall`` handler can never disagree about which rows are
    actionable: widening RECALL's legal sources in LEGAL_TRANSITIONS widens this
    flag in the same commit, and narrowing it stops offering the control.

    Args:
        status: The storybook's persisted lifecycle status.

    Returns:
        bool: True when ``(status, RECALL)`` is a legal transition.
    """
    # #ASSUME: data integrity: ``status`` came from a column carrying
    # ck_storybook_status, so Status(status) succeeds for every row written by
    # this application. A value outside the enum means the CHECK was dropped or
    # bypassed; report "not recallable" and log rather than 500 the whole
    # listing, matching the per-row isolation the rest of this surface uses.
    # #VERIFY: tests/unit/test_outstanding_decisions.py::
    # test_recallable_is_derived_from_the_transition_table.
    try:
        current = Status(status)
    except ValueError:
        _logger.warning("outstanding_decision_unknown_status", status=status)
        return False
    return (current, Action.RECALL) in LEGAL_TRANSITIONS


# The bulk query's column shape, in select() order. Kept separate from
# _OutstandingRow below because a SQLAlchemy Row is NOT the named object it is
# projected into: a Row's attributes are the COLUMN names, so
# ``row.storybook_id`` raises AttributeError on a query that selected
# ``Storybook.id``, and a JSONB extraction arrives as ``anon_1``. Positional
# construction is therefore the only honest bridge.
_CandidateRow: TypeAlias = tuple[
    str,
    str,
    "uuid.UUID",
    int | None,
    int,
    str | None,
    str | None,
    "dict[str, object] | None",
    str,
    "datetime",
]


class _OutstandingRow(NamedTuple):
    """One candidate (storybook, version) pair for the outstanding-decisions list.

    Names the ten columns the bulk query selects so the loop below reads by
    field rather than by tuple position, which is what keeps a column reorder
    from silently swapping ``status`` and ``title``. ``NamedTuple`` matches the
    idiom review_surface.py already uses for its own row shapes.

    Constructed positionally from a ``_CandidateRow``, so the field ORDER here
    must match the select() column order exactly; the field names are this
    module's own and are unrelated to the query's column labels.
    """

    storybook_id: str
    status: str
    family_id: uuid.UUID
    current_published_version: int | None
    version: int
    title: str | None
    age_band: str | None
    moderation_report: dict[str, object] | None
    cover_status: str
    version_created_at: datetime


def _build_decision_item(
    row: _OutstandingRow,
    *,
    kind: Literal["moderation", "cover"],
    moderation: OutstandingModerationDetail | None = None,
    cover: OutstandingCoverDetail | None = None,
) -> OutstandingDecisionItem:
    """Project one row into a decision item of the given kind.

    A book can hold a moderation decision and a cover decision at once, and the
    two rows share every identifying field. Building both through one function
    is what guarantees they agree: a moderation row and a cover row for the same
    book cannot end up naming different versions or different recallability.

    Args:
        row: The bulk query row for this (storybook, version) pair.
        kind: Which decision this row represents.
        moderation: The moderation detail, for ``kind="moderation"``.
        cover: The cover detail, for ``kind="cover"``.

    Returns:
        OutstandingDecisionItem: The projected row.
    """
    return OutstandingDecisionItem(
        kind=kind,
        storybook_id=row.storybook_id,
        # #EDGE: data integrity: a blob with no string title falls back to the
        # id rather than an empty string, matching _summary_title, so an admin
        # always has something clickable to identify the book by.
        title=row.title or row.storybook_id,
        status=row.status,
        version=row.version,
        family_id=str(row.family_id),
        age_band=row.age_band,
        version_created_at=row.version_created_at,
        recallable=_is_recallable(row.status),
        moderation=moderation,
        cover=cover,
    )


def _decision_rank(item: OutstandingDecisionItem) -> tuple[int, float]:
    """Order outstanding decisions by how much a child is exposed meanwhile.

    Not by recency: this list exists because these decisions were already
    missed, so "newest first" would bury exactly the rows that have been
    invisible longest. The four ranks, worst first:

    0. A block on a book children can read right now.
    1. Any other moderation decision on a published book (a flag, or a report
       too damaged to draw a verdict from, which is not a clean bill of health).
    2. A cover awaiting review on the version a child reads, so the book is on
       the shelf with no art.
    3. A cover awaiting review on a version no child reaches.

    Args:
        item: One built decision row.

    Returns:
        tuple[int, float]: (rank, epoch seconds) with unknown timestamps sorted
            last within their rank rather than treated as brand new.
    """
    if item.moderation is not None:
        rank = 0 if item.moderation.block_findings else 1
    else:
        rank = 2 if item.cover is not None and item.cover.child_facing else 3
    stamp = (
        item.version_created_at.timestamp()
        if item.version_created_at is not None
        else float("inf")
    )
    return (rank, stamp)


@router.get("/admin/outstanding-decisions")
async def get_outstanding_decisions(ctx: Context) -> OutstandingDecisionsView:
    """Return every admin decision the review queue does not list (admin only).

    The review queue lists ``in_review`` stories only, which is correct for its
    own job and is why two whole classes of decision have no surface at all: a
    moderation verdict that turned into a block on an ALREADY-PUBLISHED book
    (what `RS-C1`'s recall exists to act on, and what a threshold change
    produces in bulk), and a cover parked at ``pending_review`` on a book of any
    status. Both are decisions nobody is being shown, which under ADR-005 makes
    them safety defects rather than missing convenience.

    Args:
        ctx: The request context (principal and session).

    Returns:
        OutstandingDecisionsView: One row per outstanding decision, worst first
            (see ``_decision_rank``). A book holding both kinds yields two rows,
            because each resolves through a different action on a different page.

    Raises:
        AuthorizationError: If the caller is not an admin (-> 403).
    """
    # #CRITICAL: security: admin-only GLOBAL surface, gated before any row is
    # read so a non-admin never learns which books carry an unresolved verdict.
    # authorize_family is intentionally NOT called: this is the cross-family
    # safety operator's view, exactly as get_review_queue is.
    # #VERIFY: tests/unit/test_outstanding_decisions.py::
    # test_outstanding_decisions_blocks_non_admin (no DB round trip).
    if not ctx.principal.is_admin:
        msg = _ADMIN_ROLE_REQUIRED
        raise AuthorizationError(msg, required_permission="admin")
    latest_version = (
        select(func.max(StorybookVersion.version))
        .where(StorybookVersion.storybook_id == Storybook.id)
        .correlate(Storybook)
        .scalar_subquery()
    )
    # #CRITICAL: data integrity: for a PUBLISHED book the decision is about the
    # version a child actually reads, which api/library.py resolves as
    # current_published_version, NOT the latest row: a newer draft version can
    # sit above it, and a verdict read off that version would describe content
    # no child can reach. For every other status the latest version is the
    # subject. A bare coalesce(current_published_version, latest) would be
    # WRONG rather than merely imprecise: `RS-C1`'s recall deliberately leaves
    # current_published_version set on a book it moves to in_review, so a
    # coalesce would keep reading the now-unpublished version forever.
    # #VERIFY: tests/integration/test_outstanding_decisions_api.py::
    # test_a_recalled_book_reports_its_latest_version_not_the_published_one.
    decision_version = case(
        (
            and_(
                Storybook.status == _PUBLISHED,
                Storybook.current_published_version.is_not(None),
            ),
            Storybook.current_published_version,
        ),
        else_=latest_version,
    )
    # #ASSUME: external resources: this surface must never load a content blob.
    # A blob averages megabytes and there is one per candidate row, while every
    # number here is derived from moderation_report; selecting specific columns
    # (Core Rows, not ORM objects, so no deferred-attribute reload can happen
    # later) keeps the whole listing to one round trip plus the two config
    # loads. Title and age band are pulled out of the blob IN POSTGRES for the
    # same reason.
    # #VERIFY: tests/unit/test_outstanding_decisions.py::
    # test_outstanding_decisions_is_bulk_not_n_plus_one.
    candidates = cast(
        "list[_CandidateRow]",
        (
            await ctx.session.execute(
                select(
                    Storybook.id,
                    Storybook.status,
                    Storybook.family_id,
                    Storybook.current_published_version,
                    StorybookVersion.version,
                    StorybookVersion.blob["title"].as_string(),
                    StorybookVersion.blob["metadata"]["age_band"].as_string(),
                    StorybookVersion.moderation_report,
                    StorybookVersion.cover_status,
                    StorybookVersion.created_at,
                )
                .join(
                    StorybookVersion,
                    and_(
                        StorybookVersion.storybook_id == Storybook.id,
                        StorybookVersion.version == decision_version,
                    ),
                )
                .where(
                    or_(
                        Storybook.status == _PUBLISHED,
                        StorybookVersion.cover_status == _COVER_PENDING_REVIEW,
                    )
                )
            )
        ).all(),
    )
    if not candidates:
        return OutstandingDecisionsView(items=[])
    # Loaded once for the whole listing, never per row, and for the same reason
    # get_review_queue loads them: a count shown here must equal the count the
    # detail view this row links to computes from the same floor and policy.
    floor = await load_admin_noise_floor(ctx.session)
    policy = await load_threshold_policy(ctx.session)
    items: list[OutstandingDecisionItem] = []
    for candidate in candidates:
        row = _OutstandingRow(*candidate)
        try:
            # Only a published book can carry an outstanding MODERATION
            # decision. A draft or in_review book's verdict already has a home
            # (the review queue), and an archived or needs_revision book reaches
            # no child, so re-surfacing its verdict would only add noise to the
            # one list that must stay short enough to be read.
            moderation = (
                build_moderation_decision_detail(
                    storybook_id=row.storybook_id,
                    status=row.status,
                    version=row.version,
                    moderation_report=row.moderation_report,
                    admin_noise_floor=floor,
                    age_band=row.age_band or "",
                    policy=policy,
                )
                if row.status == _PUBLISHED
                else None
            )
            if moderation is not None:
                items.append(
                    _build_decision_item(row, kind="moderation", moderation=moderation)
                )
            # A pending cover, by contrast, is outstanding at ANY status: the
            # decision is unmade regardless of where the book sits, and
            # ``child_facing`` is what separates the urgent case (a published
            # book on the shelf with no art) from the merely unfinished one.
            if row.cover_status == _COVER_PENDING_REVIEW:
                items.append(
                    _build_decision_item(
                        row,
                        kind="cover",
                        cover=OutstandingCoverDetail(
                            cover_status=row.cover_status,
                            child_facing=(
                                row.status == _PUBLISHED
                                and row.version == row.current_published_version
                            ),
                        ),
                    )
                )
        except ValidationError as exc:
            # #EDGE: data integrity: one book's moderation_report is corrupt at
            # rest. Isolate that book (logged with its id) rather than failing
            # the listing: this surface is the only place the OTHER books'
            # unresolved decisions appear, so one bad row must not hide them.
            # Mirrors get_review_queue's review_queue_item_corrupt handling.
            # #VERIFY: tests/integration/test_outstanding_decisions_api.py::
            # test_a_corrupt_report_isolates_only_its_own_book.
            _logger.warning(
                "outstanding_decision_item_corrupt",
                storybook_id=row.storybook_id,
                version=row.version,
                error=str(exc),
            )
            continue
    items.sort(key=_decision_rank)
    return OutstandingDecisionsView(items=items)


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


async def _load_latest_versions(
    session: AsyncSession, ids: list[str]
) -> dict[str, int]:
    """Return the latest version number per storybook id (one bulk query).

    Args:
        session: The active database session.
        ids: The storybook ids to resolve.

    Returns:
        dict[str, int]: storybook id -> its highest ``StorybookVersion.version``.
            A storybook with no version row yet is simply absent from the dict.
    """
    latest_rows = cast(
        "list[tuple[str, int]]",
        (
            await session.execute(
                select(
                    StorybookVersion.storybook_id,
                    func.max(StorybookVersion.version),
                )
                .where(StorybookVersion.storybook_id.in_(ids))
                .group_by(StorybookVersion.storybook_id)
            )
        ).all(),
    )
    return dict(latest_rows)


async def _load_version_rows_by_key(
    session: AsyncSession, keys: list[tuple[str, int]]
) -> dict[tuple[str, int], StorybookVersion]:
    """Bulk-load the ``(storybook_id, version)`` rows named by ``keys``.

    Args:
        session: The active database session.
        keys: The ``(storybook_id, version)`` pairs to load.

    Returns:
        dict[tuple[str, int], StorybookVersion]: Row keyed by its own
            ``(storybook_id, version)``.
    """
    version_rows = (
        await session.scalars(
            select(StorybookVersion).where(
                tuple_(StorybookVersion.storybook_id, StorybookVersion.version).in_(
                    keys
                )
            )
        )
    ).all()
    return {(row.storybook_id, row.version): row for row in version_rows}


def _versionless_summaries(books: Sequence[Storybook]) -> list[StorybookSummary]:
    """Build best-effort summaries for storybooks with no version row yet.

    Args:
        books: Storybooks none of which has a ``StorybookVersion`` row (draft
            not yet generated).

    Returns:
        list[StorybookSummary]: One summary per book, title falls back to the
            id, newest ``created_at`` first.
    """
    return sorted(
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


def _build_summary(
    book: Storybook,
    latest: dict[str, int],
    by_key: dict[tuple[str, int], StorybookVersion],
) -> StorybookSummary:
    """Build one storybook's summary, resolving its latest version's blob.

    Args:
        book: The storybook row.
        latest: storybook id -> latest version number (see
            ``_load_latest_versions``).
        by_key: ``(storybook_id, version)`` -> that version row (see
            ``_load_version_rows_by_key``).

    Returns:
        StorybookSummary: The library-listing summary for this storybook.
    """
    version = latest.get(book.id)
    row = by_key.get((book.id, version)) if version is not None else None
    blob = row.blob if row is not None else None
    return StorybookSummary(
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
        msg = _ADMIN_ROLE_REQUIRED
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
    latest = await _load_latest_versions(ctx.session, ids)
    keys = list(latest.items())
    if not keys:
        # Every story lacks a version row (draft not yet generated); still list
        # them with a best-effort title so the operator can see them.
        return StorybookLibraryView(items=_versionless_summaries(books))

    by_key = await _load_version_rows_by_key(ctx.session, keys)
    items = [_build_summary(book, latest, by_key) for book in books]
    # Newest activity first: sort by the latest version's creation time, falling
    # back to the storybook's own created_at for versionless drafts.
    items.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
    return StorybookLibraryView(items=items)
