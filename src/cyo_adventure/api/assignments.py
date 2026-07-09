"""Assignment endpoints: a guardian grants a published story to child profiles.

Assigning is the read-gate for a story: a child's library listing and direct
version fetch both filter on ``storybook_assignment``, so a child sees only
stories explicitly assigned to their profile. This router is guardian-only; a
child token is rejected. It is add-only and idempotent (re-assigning an already
assigned profile is a no-op). There is no unassign endpoint: removing access has
reading-state and offline-cache implications deferred past the first release.

Error ordering follows the repo convention in ``ratings.py`` and
``library.py`` (``get_storybook_version``): an unknown storybook id is 404,
while an EXISTING storybook owned by another family is 403 via
``authorize_family``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import and_, select

from cyo_adventure.api.deps import (
    Context,
    authorize_family,
    authorize_profile,
    parse_uuid,
)
from cyo_adventure.api.review_surface import build_content_summary
from cyo_adventure.api.schemas import (
    AssignmentCreateBody,
    AssignmentListView,
    ContentSummaryView,
    GuardianBookItem,
    GuardianBooksView,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import Storybook, StorybookAssignment, StorybookVersion
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.moderation.thresholds import ThresholdPolicy, load_threshold_policy
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

router = APIRouter(prefix="/api/v1", tags=["assignments"])

_PUBLISHED = "published"
_logger = get_logger(__name__)


def _assignment_list(
    storybook_id: str, profile_ids: Iterable[object]
) -> AssignmentListView:
    """Build the response view with sorted, stringified profile ids."""
    return AssignmentListView(
        storybook_id=storybook_id,
        profile_ids=sorted(str(pid) for pid in profile_ids),
    )


async def _require_guardian_family_book(ctx: Context, storybook_id: str) -> Storybook:
    """Return the storybook after guardian-only and same-family checks.

    Args:
        ctx: The request context (principal + session).
        storybook_id: The story id from the path.

    Returns:
        Storybook: The story owned by the guardian's family.

    Raises:
        AuthorizationError: If the caller is not a guardian, or the story
            belongs to another family (403).
        ResourceNotFoundError: If the story does not exist (404).
    """
    # #CRITICAL: security: guardian-only; a child token cannot read or widen
    # assignments, and an admin (a cross-family safety reviewer, not a family
    # assigner) is rejected here too. Error ordering matches ratings.py and
    # library.py (get_storybook_version): 404-if-missing precedes
    # authorize_family, so an unknown id is 404 and a cross-family book is 403.
    # #VERIFY: is_guardian gate -> 403; None -> 404; authorize_family -> 403.
    if not ctx.principal.is_guardian:
        msg = "only a guardian may manage assignments"
        raise AuthorizationError(msg)
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(ctx.principal, book.family_id)
    return book


async def _authorize_content_summary(
    ctx: Context, storybook_id: str
) -> tuple[StorybookVersion, int]:
    """Return the current published version for a guardian/admin content summary.

    Args:
        ctx: The request context (principal + session).
        storybook_id: The story id from the path.

    Returns:
        tuple[StorybookVersion, int]: The current published version row and its
            version number.

    Raises:
        AuthorizationError: If the caller is a child, or a guardian from another
            family (403).
        ResourceNotFoundError: If the story does not exist, is not published,
            its current published version row is missing, or that row lacks
            approved_by (defense-in-depth; the sole publish path is expected
            to stamp it) (404).
    """
    # #CRITICAL: security: guardian-or-admin only; a child token can never read a
    # content summary. A guardian is family-scoped (cross-family -> 403); an admin
    # is global and skips the family check (mirrors library.py's is_admin bypass).
    # Missing OR unpublished -> 404 (not 403) so an unpublished story's existence
    # is not revealed, matching get_storybook_version's information-hiding rule.
    # #VERIFY: child -> 403; cross-family guardian -> 403; missing/unpublished -> 404.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = "only a guardian or admin may read a content summary"
        raise AuthorizationError(msg)
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None or book.status != _PUBLISHED:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if not ctx.principal.is_admin:
        authorize_family(ctx.principal, book.family_id)
    version = book.current_published_version
    if version is None:
        msg = f"storybook '{storybook_id}' has no published version"
        raise ResourceNotFoundError(msg)
    version_row = await ctx.session.get(StorybookVersion, (storybook_id, version))
    if version_row is None:
        msg = f"storybook '{storybook_id}' has no published version"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: security: status == "published" is expected to imply
    # approved_by is set (the sole publish path in publishing/service.py stamps
    # both atomically). This gate is defense-in-depth per review: a future
    # publish path that fails to stamp approved_by must not expose an
    # unapproved version's moderation summary. Mirrors get_storybook_version's
    # approved_by check in library.py.
    # #VERIFY: published status + approved_by is None -> 404.
    if version_row.approved_by is None:
        msg = f"storybook '{storybook_id}' has no published version"
        raise ResourceNotFoundError(msg)
    return version_row, version


@router.get("/storybooks/{storybook_id}/content-summary")
async def get_content_summary(storybook_id: str, ctx: Context) -> ContentSummaryView:
    """Return the redacted content review summary for a published story.

    Guardians see this in the assign flow so they know what a book was flagged
    for before granting it to a child. It carries the gating summary, the total
    flagged count, and story-level findings only; per-node flagged passages are
    withheld (the admin review surface owns those).

    Args:
        storybook_id: The published story to summarize.
        ctx: The request context (principal + session).

    Returns:
        ContentSummaryView: The redacted guardian content summary.

    Raises:
        AuthorizationError: Child caller or cross-family guardian (403).
        ResourceNotFoundError: Unknown or unpublished story, or a missing
            published version row (404).
        ValidationError: If the stored moderation report is corrupt at rest.
    """
    version_row, version = await _authorize_content_summary(ctx, storybook_id)
    policy = await load_threshold_policy(ctx.session)
    return build_content_summary(
        storybook_id=storybook_id,
        version=version,
        blob=version_row.blob,
        moderation_report=version_row.moderation_report,
        age_band=_book_age_band(version_row.blob),
        policy=policy,
    )


@router.post("/storybooks/{storybook_id}/assignments")
async def assign_storybook(
    storybook_id: str, body: AssignmentCreateBody, ctx: Context
) -> AssignmentListView:
    """Assign a published story to one or more of the guardian's child profiles.

    Args:
        storybook_id: The story to assign.
        body: The requested profile ids.
        ctx: The request context (principal + unit-of-work session).

    Returns:
        AssignmentListView: The full current set of assigned profile ids.

    Raises:
        AuthorizationError: Non-guardian caller, a cross-family storybook, or a
            profile outside the family.
        ResourceNotFoundError: Unknown storybook id.
        BusinessLogicError: The story is not published.
        ValidationError: A profile id is not a UUID.
    """
    # #CRITICAL: security: validate role/family/profile scope BEFORE any write so
    # a guardian cannot assign a non-published story or a foreign profile.
    # #VERIFY: order is guardian(403) -> missing book(404) -> cross-family(403)
    # -> non-published(400) -> foreign profile(403).
    book = await _require_guardian_family_book(ctx, storybook_id)
    if book.status != _PUBLISHED:
        msg = "only a published story can be assigned"
        raise BusinessLogicError(msg)
    profile_ids = [parse_uuid(pid, "profile_ids") for pid in body.profile_ids]
    for pid in profile_ids:
        authorize_profile(ctx.principal, pid)
    # #EDGE: concurrency: two guardians assigning the same (profile, story) can
    # both read no existing row and both INSERT, raising a PK violation at flush
    # (a 500). Vanishingly rare for a family's assign UI; accepted rather than
    # locking. #VERIFY: switch to INSERT ... ON CONFLICT DO NOTHING if it recurs.
    existing = set(
        await ctx.session.scalars(
            select(StorybookAssignment.child_profile_id).where(
                StorybookAssignment.storybook_id == storybook_id
            )
        )
    )
    # Guarding each insert on ``existing`` (updated in-loop) makes the write
    # idempotent AND dedupes duplicate ids within one request: the second
    # occurrence of a repeated id finds it already present and is skipped.
    for pid in profile_ids:
        if pid not in existing:
            ctx.session.add(
                StorybookAssignment(
                    child_profile_id=pid,
                    storybook_id=storybook_id,
                    assigned_by=ctx.principal.user_id,
                )
            )
            # #ASSUME: data-integrity: emit book_assigned once per NEWLY-created
            # assignment row only; the idempotent skip branch above (pid already
            # in existing) must never re-emit for an already-assigned profile.
            # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
            # test_assign_writes_book_assigned_event_per_new_assignment.
            await record_event(
                ctx.session,
                Actor.from_principal(ctx.principal),
                entity_type="storybook_assignment",
                entity_id=f"{pid}:{storybook_id}",
                event_type=EventType.BOOK_ASSIGNED,
                payload={"child_profile_id": str(pid)},
            )
            existing.add(pid)
    await ctx.session.flush()
    return _assignment_list(storybook_id, existing)


@router.get("/storybooks/{storybook_id}/assignments")
async def list_assignments(storybook_id: str, ctx: Context) -> AssignmentListView:
    """List the child profiles a story is currently assigned to.

    Args:
        storybook_id: The story whose assignments are requested.
        ctx: The request context (principal + session).

    Returns:
        AssignmentListView: The current assigned profile ids.

    Raises:
        AuthorizationError: Non-guardian caller or cross-family storybook.
        ResourceNotFoundError: Unknown storybook id.
    """
    # #CRITICAL: security: same guardian-only/same-family gate as the POST path.
    # #VERIFY: _require_guardian_family_book raises 403 (role or cross-family)
    # or 404 (missing) before any read.
    await _require_guardian_family_book(ctx, storybook_id)
    rows = await ctx.session.scalars(
        select(StorybookAssignment.child_profile_id).where(
            StorybookAssignment.storybook_id == storybook_id
        )
    )
    return _assignment_list(storybook_id, rows)


def _book_age_band(blob: dict[str, object]) -> str:
    """Return the story's age band from blob metadata, or empty string.

    Args:
        blob: The stored Storybook content blob.

    Returns:
        str: ``metadata.age_band`` when present and a string, else ``""``.
    """
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        age_band = metadata.get("age_band")
        if isinstance(age_band, str):
            return age_band
    return ""


def _guardian_book_item(
    book: Storybook,
    version_row: StorybookVersion,
    assigned_profile_ids: list[str],
    *,
    policy: ThresholdPolicy,
) -> GuardianBookItem:
    """Project one published version into a guardian browse row.

    Reuses ``build_content_summary`` for the redacted content badge (the
    screened flag and total flagged count) so the browse surface never
    re-derives moderation gating. A ``moderation_report`` that is corrupt at rest
    degrades this one row's badge rather than failing the whole listing.

    Args:
        book: The published storybook row.
        version_row: Its current published version (blob + moderation report).
        assigned_profile_ids: The child profiles this book is assigned to.
        policy: The resolved threshold policy shared across the whole listing.

    Returns:
        GuardianBookItem: The browse row with title, content badge, and the
            sorted assignment set.
    """
    # #EDGE: data integrity: build_content_summary raises ValidationError on a
    # moderation_report that no longer conforms at rest (e.g. an unrecognized
    # verdict). One corrupt row must not 500 the whole browse list, so isolate
    # it: log the bad row and degrade its badge to screened=False, flagged_count=0.
    # A corrupt report is an unscreened badge, not a clean one; we cannot vouch
    # for flags we cannot read, so failing open to "Clean" would be a falsely
    # reassuring safety signal. Mirrors get_review_queue's per-row isolation.
    # #VERIFY: tests/integration/test_guardian_books_api.py::
    # test_corrupt_report_row_degrades_not_500.
    version = version_row.version
    try:
        summary = build_content_summary(
            storybook_id=book.id,
            version=version,
            blob=version_row.blob,
            moderation_report=version_row.moderation_report,
            age_band=_book_age_band(version_row.blob),
            policy=policy,
        )
        screened = summary.screened
        flagged_count = summary.flagged_count
    except ValidationError:
        _logger.warning(
            "guardian_book_content_summary_corrupt",
            storybook_id=book.id,
            version=version,
        )
        screened = False
        flagged_count = 0
    title = version_row.blob.get("title")
    return GuardianBookItem(
        storybook_id=book.id,
        title=title if isinstance(title, str) and title else book.id,
        version=version,
        age_band=_book_age_band(version_row.blob),
        screened=screened,
        flagged_count=flagged_count,
        assigned_profile_ids=sorted(assigned_profile_ids),
    )


@router.get("/guardian/books")
async def list_guardian_books(ctx: Context) -> GuardianBooksView:
    """List the family's published books with content tags and assignments.

    A guardian browses every published, approved book in their OWN family (not
    just their own request history), each carrying a redacted content badge
    (screened flag + flagged count) and the set of child profiles it is
    currently assigned to, so they can decide what to grant. Books are ordered
    newest-first by creation time (ties broken by id) so the list has a stable,
    guardian-friendly order across requests.

    Args:
        ctx: The request context (principal + session).

    Returns:
        GuardianBooksView: The family's published books, each with a content
            badge and its current assignment set.

    Raises:
        AuthorizationError: If the caller is not a guardian; a child cannot
            enumerate the family's books and an admin has no assign authority on
            this family surface (403).
    """
    # #CRITICAL: security: guardian-only browse-to-assign surface. A child token
    # cannot enumerate the family's books, and an admin (the cross-family safety
    # reviewer, not a family assigner) is rejected too, matching
    # assign_storybook's guardian-only authority. There is no cross-family id in
    # the path, so 404-over-403 information-hiding does not apply; family
    # isolation is enforced by the WHERE family_id clause below.
    # #VERIFY: child -> 403; admin -> 403; a guardian sees only own-family rows
    # (tests/integration/test_guardian_books_api.py).
    if not ctx.principal.is_guardian:
        msg = "only a guardian may browse the family library"
        raise AuthorizationError(msg)
    # #CRITICAL: security: match library.py's visibility gate exactly: same
    # family, status published, a current published version, and approved_by IS
    # NOT NULL. An unapproved or unpublished version must never surface here.
    # #VERIFY: the join pins version == current_published_version and the WHERE
    # requires approved_by IS NOT NULL (test_unapproved_published_book_is_excluded,
    # test_unpublished_book_is_excluded).
    # #ASSUME: external-resources: load every published version's blob and report
    # in ONE join query and all assignments in ONE IN query, so the listing stays
    # two queries total regardless of how large the family library grows.
    # #VERIFY: no per-row DB round-trip; the content badge is a pure projection.
    rows = (
        await ctx.session.execute(
            select(Storybook, StorybookVersion)
            .join(
                StorybookVersion,
                and_(
                    StorybookVersion.storybook_id == Storybook.id,
                    StorybookVersion.version == Storybook.current_published_version,
                ),
            )
            .where(
                Storybook.family_id == ctx.principal.family_id,
                Storybook.status == _PUBLISHED,
                Storybook.current_published_version.is_not(None),
                StorybookVersion.approved_by.is_not(None),
            )
            .order_by(Storybook.created_at.desc(), Storybook.id)
        )
    ).all()
    if not rows:
        return GuardianBooksView(books=[])
    book_ids = [book.id for book, _ in rows]
    assign_rows = await ctx.session.scalars(
        select(StorybookAssignment).where(
            StorybookAssignment.storybook_id.in_(book_ids)
        )
    )
    assigned: dict[str, list[str]] = {}
    for assignment in assign_rows:
        assigned.setdefault(assignment.storybook_id, []).append(
            str(assignment.child_profile_id)
        )
    # #ASSUME: external-resources: one threshold-policy load for the whole
    # listing, not per-row, so the per-row query count stays fixed regardless
    # of library size (mirrors the two-query assumption above).
    # #VERIFY: no per-row policy load; tests/integration/test_guardian_books_api.py.
    policy = await load_threshold_policy(ctx.session)
    books = [
        _guardian_book_item(book, version_row, assigned.get(book.id, []), policy=policy)
        for book, version_row in rows
    ]
    return GuardianBooksView(books=books)
