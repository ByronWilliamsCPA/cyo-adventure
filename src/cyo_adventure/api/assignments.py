"""Assignment endpoints: a guardian grants a published story to child profiles.

Assigning is the read-gate for a story: a child's library listing and direct
version fetch both filter on ``storybook_assignment``, so a child sees only
stories explicitly assigned to their profile. This router is guardian-only; a
child token is rejected. Assigning is add-only and idempotent (re-assigning an
already assigned profile is a no-op). Unassigning (the G8 per-child kill switch,
``DELETE .../assignments/{profile_id}``) is likewise idempotent and revokes
access ONLY: it removes the assignment row and leaves the child's reading state,
completion, and rating untouched, so re-assigning later resumes the child's
progress. The offline copy is evicted at the next sync by the client's
``reconcileOfflineCache``; destroying child data is a separate, explicit privacy
flow, never a side effect of revoking a shelf grant.

Error ordering follows the repo convention in ``ratings.py`` and
``library.py`` (``get_storybook_version``): an unknown storybook id is 404,
while an EXISTING storybook that is neither own-family nor catalog-visibility
is 403 (WS-E's visibility gate, ``_require_guardian_visible_book``). A
catalog-visibility book owned by another family IS assignable; the returned
assignment set is always scoped to the caller's own family regardless of the
book's visibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from fastapi import APIRouter
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import Select, and_, or_, select

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
    error_responses,
)
from cyo_adventure.api.sentinel_log import strip_and_log
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import (
    ChildProfile,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.moderation.thresholds import ThresholdPolicy, load_threshold_policy
from cyo_adventure.publishing.state_machine import Visibility
from cyo_adventure.storybook.models import ContentFlags, parse_age_band_rank
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable

router = APIRouter(
    prefix="/api/v1", tags=["assignments"], responses=error_responses(401, 403)
)

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


def _family_assignment_ids_stmt(
    storybook_id: str, family_id: uuid.UUID
) -> Select[tuple[uuid.UUID]]:
    """Select the book's assigned profile ids belonging to one family.

    #CRITICAL: security: every assignment set returned to a guardian must be
    scoped to their own family; a catalog book's global set would leak other
    families' child profile UUIDs (WS-E plan deviation 2).
    #VERIFY: test_catalog_assignment_listing_is_family_scoped.
    """
    return (
        select(StorybookAssignment.child_profile_id)
        .join(
            ChildProfile,
            StorybookAssignment.child_profile_id == ChildProfile.id,
        )
        .where(
            StorybookAssignment.storybook_id == storybook_id,
            ChildProfile.family_id == family_id,
        )
    )


async def _require_guardian_visible_book(ctx: Context, storybook_id: str) -> Storybook:
    """Return the storybook after guardian-only and visibility checks.

    Args:
        ctx: The request context (principal + session).
        storybook_id: The story id from the path.

    Returns:
        Storybook: A story that is either owned by the guardian's family or
            shared to the catalog.

    Raises:
        AuthorizationError: If the caller is not a guardian, or the story is
            neither own-family nor catalog (403).
        ResourceNotFoundError: If the story does not exist (404).
    """
    # #CRITICAL: security: E5's server-side visibility gate; the UI badge is a
    # convenience, never the gate. Guard order is unchanged from the pre-WS-E
    # helper: guardian-only (403) -> missing (404) -> visibility (403). A
    # cross-family book is assignable ONLY when visibility='catalog'; the
    # child read gate (StorybookAssignment in library.py) is untouched.
    # #VERIFY: test_guardian_assigns_other_family_catalog_book (allow) and
    # test_guardian_cannot_assign_other_family_private_book (deny).
    if not ctx.principal.is_guardian:
        msg = "only a guardian may manage assignments"
        raise AuthorizationError(msg)
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if (
        book.family_id != ctx.principal.family_id
        and book.visibility != Visibility.CATALOG.value
    ):
        msg = "storybook is not visible to this family"
        raise AuthorizationError(msg, resource=storybook_id)
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
        AuthorizationError: If the caller is a child, or a guardian from
            another family reading a non-catalog (family-visibility) book
            (403).
        ResourceNotFoundError: If the story does not exist, is not published,
            its current published version row is missing, or that row lacks
            approved_by (defense-in-depth; the sole publish path is expected
            to stamp it) (404).
    """
    # #CRITICAL: security: a guardian may read a cross-family summary ONLY for a
    # catalog-shared book (WS-E E3: the assign dialog needs the badge detail for
    # anything assignable); a family-visibility book keeps the family gate. An
    # admin remains global. #VERIFY: catalog summary 200 / private cross-family 403.
    # A child token can never read a content summary. Missing OR unpublished ->
    # 404 (not 403) so an unpublished story's existence is not revealed, matching
    # get_storybook_version's information-hiding rule.
    # #VERIFY: child -> 403; cross-family guardian on a family-visibility book ->
    # 403 (catalog -> 200, per the #VERIFY above); missing/unpublished -> 404.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = "only a guardian or admin may read a content summary"
        raise AuthorizationError(msg)
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None or book.status != _PUBLISHED:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if not ctx.principal.is_admin and book.visibility != Visibility.CATALOG.value:
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


@router.get(
    "/storybooks/{storybook_id}/content-summary", responses=error_responses(404)
)
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
        AuthorizationError: Child caller, or a guardian from another family
            reading a non-catalog (family-visibility) book (403).
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


@router.post(
    "/storybooks/{storybook_id}/assignments", responses=error_responses(400, 404)
)
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
        AuthorizationError: Non-guardian caller, a storybook that is neither
            own-family nor catalog, or a profile outside the family.
        ResourceNotFoundError: Unknown storybook id.
        BusinessLogicError: The story is not published.
        ValidationError: A profile id is not a UUID.
    """
    # #CRITICAL: security: validate role/family/profile scope BEFORE any write so
    # a guardian cannot assign a non-published story or a foreign profile.
    # #VERIFY: order is guardian(403) -> missing book(404) -> not-visible(403)
    # -> non-published(400) -> foreign profile(403).
    book = await _require_guardian_visible_book(ctx, storybook_id)
    if book.status != _PUBLISHED:
        msg = "only a published story can be assigned"
        raise BusinessLogicError(msg)
    profile_ids = [parse_uuid(pid, "profile_ids") for pid in body.profile_ids]
    for pid in profile_ids:
        authorize_profile(ctx.principal, pid)
    # #CRITICAL: security: H1 - a story's age band is a content-suitability
    # ceiling, not a preference; a book banded above a target profile's band
    # must never become assignable (e.g. a 13-16 book onto an 8-11 profile).
    # This is the PRIMARY gate; library.py's read paths carry the same check
    # as defense in depth in case an assignment row is ever created another
    # way. Lenient (fail open) on missing/unparseable data on EITHER side:
    # a legacy blob with no metadata.age_band, or a profile whose stored
    # age_band string is not a recognized AgeBand, has no ceiling to compare
    # against, and this is not the layer that should invent one.
    # #VERIFY: tests/integration/test_assignments_api.py::
    # test_assign_storybook_rejects_band_above_profile_band (allow
    # equal/lower band, reject a book banded above the profile).
    book_rank = await _book_age_band_rank(ctx, book)
    if book_rank is not None:
        profiles_by_id = {
            p.id: p
            for p in await ctx.session.scalars(
                select(ChildProfile).where(ChildProfile.id.in_(profile_ids))
            )
        }
        for pid in profile_ids:
            profile = profiles_by_id.get(pid)
            if profile is None:
                continue
            profile_rank = parse_age_band_rank(profile.age_band)
            if profile_rank is not None and book_rank > profile_rank:
                msg = "storybook's age band exceeds the target profile's age band"
                raise BusinessLogicError(msg)
    # #EDGE: concurrency: two guardians assigning the same (profile, story) can
    # both read no existing row and both INSERT, raising a PK violation at flush
    # (a 500). Vanishingly rare for a family's assign UI; accepted rather than
    # locking. #VERIFY: switch to INSERT ... ON CONFLICT DO NOTHING if it recurs.
    existing = set(
        await ctx.session.scalars(
            _family_assignment_ids_stmt(storybook_id, ctx.principal.family_id)
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


@router.get("/storybooks/{storybook_id}/assignments", responses=error_responses(404))
async def list_assignments(storybook_id: str, ctx: Context) -> AssignmentListView:
    """List the child profiles a story is currently assigned to.

    Args:
        storybook_id: The story whose assignments are requested.
        ctx: The request context (principal + session).

    Returns:
        AssignmentListView: The current assigned profile ids.

    Raises:
        AuthorizationError: Non-guardian caller, or a storybook that is
            neither own-family nor catalog.
        ResourceNotFoundError: Unknown storybook id.
    """
    # #CRITICAL: security: same guardian-only/visibility gate as the POST path.
    # #VERIFY: _require_guardian_visible_book raises 403 (role or visibility)
    # or 404 (missing) before any read.
    await _require_guardian_visible_book(ctx, storybook_id)
    rows = await ctx.session.scalars(
        _family_assignment_ids_stmt(storybook_id, ctx.principal.family_id)
    )
    return _assignment_list(storybook_id, rows)


@router.delete(
    "/storybooks/{storybook_id}/assignments/{profile_id}",
    responses=error_responses(404),
)
async def unassign_storybook(
    storybook_id: str, profile_id: str, ctx: Context
) -> AssignmentListView:
    """Revoke a single child's access to a story (G8 per-child kill switch).

    Removing the assignment row is the whole operation: the child's library
    listing and direct version fetch both gate on ``storybook_assignment``
    (api/library.py), so deleting the row hides the book at the next sync and
    the offline cache evicts it via ``reconcileOfflineCache``. Reading state,
    completion, and rating rows are deliberately PRESERVED (invisible behind the
    read gate) so re-assigning resumes the child's progress. Unlike the assign
    path there is no published-status gate, so a guardian can still pull an
    already-archived book off a child's shelf. The response is the book's full
    remaining assignment set, matching the POST path.

    Args:
        storybook_id: The story to revoke.
        profile_id: The child profile to revoke it from.
        ctx: The request context (principal + unit-of-work session).

    Returns:
        AssignmentListView: The book's remaining assigned profile ids for the
            caller's family.

    Raises:
        AuthorizationError: Non-guardian caller, a storybook that is neither
            own-family nor catalog, or a profile outside the family.
        ResourceNotFoundError: Unknown storybook id.
        ValidationError: The profile id is not a UUID.
    """
    # #CRITICAL: security: guardian-only + own-family/visibility + own-profile
    # gate BEFORE any delete so a guardian cannot revoke access on a foreign
    # child or a book outside the family/catalog boundary. Same guard order as
    # the POST path minus the published-status check (an archived book must
    # still be unassignable).
    # #VERIFY: guardian(403) -> missing book(404) -> not-visible(403) -> foreign
    # profile(403); tests/integration/test_assignments_api.py::
    # test_child_cannot_unassign_403 and the cross-family/foreign-profile arms.
    await _require_guardian_visible_book(ctx, storybook_id)
    pid = parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, pid)
    existing = await ctx.session.get(StorybookAssignment, (pid, storybook_id))
    if existing is not None:
        await ctx.session.delete(existing)
        # #ASSUME: data-integrity: emit book_unassigned once per row ACTUALLY
        # removed; an idempotent no-op delete (already unassigned) must never
        # write a spurious revocation event. Mirrors assign_storybook's
        # emit-once-per-newly-created-row discipline.
        # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
        # test_unassign_writes_book_unassigned_event (second no-op emits none).
        await record_event(
            ctx.session,
            Actor.from_principal(ctx.principal),
            entity_type="storybook_assignment",
            entity_id=f"{pid}:{storybook_id}",
            event_type=EventType.BOOK_UNASSIGNED,
            payload={"child_profile_id": str(pid)},
        )
    await ctx.session.flush()
    rows = await ctx.session.scalars(
        _family_assignment_ids_stmt(storybook_id, ctx.principal.family_id)
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


async def _book_age_band_rank(ctx: Context, book: Storybook) -> int | None:
    """Return the current published version's age-band rank, or None.

    Args:
        ctx: The request context (principal + session).
        book: The storybook whose current published version supplies the band.

    Returns:
        int | None: The band's rank (for ``<=`` comparisons against a target
            profile's band), or ``None`` when the book has no current
            published version row, or its blob carries no parseable
            ``metadata.age_band``.
    """
    if book.current_published_version is None:
        return None
    version_row = await ctx.session.get(
        StorybookVersion, (book.id, book.current_published_version)
    )
    if version_row is None:
        return None
    return parse_age_band_rank(_book_age_band(version_row.blob))


def _book_themes(blob: dict[str, object]) -> list[str]:
    """Return the story's themes from the blob metadata, or [] if absent.

    Args:
        blob: The stored Storybook content blob.

    Returns:
        list[str]: ``metadata.themes``, filtered to string entries, or ``[]``
            when the metadata or field is absent.
    """
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        themes = metadata.get("themes")
        if isinstance(themes, list):
            return [theme for theme in themes if isinstance(theme, str)]
    return []


def _book_content_flags(blob: dict[str, object]) -> ContentFlags | None:
    """Return the story's content-sensitivity flags, or None if absent/invalid.

    Args:
        blob: The stored Storybook content blob.

    Returns:
        ContentFlags | None: The parsed ``metadata.content_flags``, or
            ``None`` when absent or invalid.
    """
    # #ASSUME: data integrity: a blob written by an older schema version may
    # carry a ``content_flags`` shape ``ContentFlags`` no longer accepts;
    # degrade to ``None`` (omit the badge) rather than fail the whole browse
    # listing for a detail-only field.
    # #VERIFY: tests/unit/test_assignments_api_unit.py::TestBookDetailHelpers.
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        flags = metadata.get("content_flags")
        if isinstance(flags, dict):
            try:
                return ContentFlags.model_validate(flags)
            except PydanticValidationError:
                return None
    return None


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
        GuardianBookItem: The browse row with title (personalization
            sentinels stripped to their generic word, ADR-023 P3), content
            badge, and the sorted assignment set.
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
    # #CRITICAL: security: this is the guardian browse-and-assign list, not
    # an admin/review surface, so a raw personalization sentinel (e.g.
    # {~HERO:Explorer~}) must never reach it (ADR-023 P3); see
    # tests/unit/test_title_strip_registry.py for the authoritative
    # strip-or-raw enumeration across every title-bearing response surface.
    # Themes are stripped for the same reason: metadata.themes reaches this
    # same guardian model two lines below the title.
    # #VERIFY: test_assignments_api_unit.py::TestGuardianBookItem::
    # test_title_strips_sentinels.
    title = version_row.blob.get("title")
    return GuardianBookItem(
        storybook_id=book.id,
        title=(
            strip_and_log(
                title,
                at="guardian_book.title",
                storybook_id=book.id,
                version=version,
            )
            if isinstance(title, str) and title
            else book.id
        ),
        version=version,
        age_band=_book_age_band(version_row.blob),
        visibility=cast("Literal['family', 'catalog']", book.visibility),
        screened=screened,
        flagged_count=flagged_count,
        assigned_profile_ids=sorted(assigned_profile_ids),
        themes=[
            strip_and_log(
                theme,
                at="guardian_book.themes",
                storybook_id=book.id,
                version=version,
            )
            for theme in _book_themes(version_row.blob)
        ],
        content_flags=_book_content_flags(version_row.blob),
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
    # #CRITICAL: security: match library.py's visibility gate, widened for
    # catalog books (WS-E decision E3): same family OR globally-browsable
    # catalog, status published, a current published version, and approved_by
    # IS NOT NULL. Family isolation for `family`-visibility books is the
    # `or_` clause's first arm; `catalog` books are globally browsable BY
    # DESIGN, so the second arm intentionally has no family_id filter. An
    # unapproved or unpublished version must never surface here regardless of
    # visibility.
    # #VERIFY: the join pins version == current_published_version and the WHERE
    # requires approved_by IS NOT NULL (test_unapproved_published_book_is_excluded,
    # test_unpublished_book_is_excluded); a catalog book from another family is
    # listed (test_catalog_book_from_other_family_is_listed_with_badge) while a
    # family-visibility book from another family stays hidden
    # (test_other_family_private_book_stays_hidden).
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
                or_(
                    Storybook.family_id == ctx.principal.family_id,
                    Storybook.visibility == Visibility.CATALOG.value,
                ),
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
    # #CRITICAL: security: scope the assignment projection to the CALLER's
    # family. A catalog book may be assigned by many families; projecting the
    # global set would leak other families' child profile UUIDs (WS-E plan
    # deviation 2). #VERIFY: test_catalog_book_assignment_set_is_family_scoped.
    assign_rows = await ctx.session.execute(
        select(
            StorybookAssignment.storybook_id,
            StorybookAssignment.child_profile_id,
        )
        .join(
            ChildProfile,
            StorybookAssignment.child_profile_id == ChildProfile.id,
        )
        .where(
            StorybookAssignment.storybook_id.in_(book_ids),
            ChildProfile.family_id == ctx.principal.family_id,
        )
    )
    assigned: dict[str, list[str]] = {}
    for assignment_storybook_id, child_profile_id in assign_rows:
        assigned.setdefault(assignment_storybook_id, []).append(str(child_profile_id))
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
