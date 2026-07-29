"""Reading-state and completion endpoints.

Reading-state saves use revision-based optimistic concurrency: a PUT carries the
``state_revision`` it started from and the server applies and increments only on a
match, otherwise returning 409 with the current row (multi-device reconciliation,
tech-spec "Multi-device sync rules"). Saves are pinned to the story version they
began on, and an ``event_id`` makes offline-queue replays idempotent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import select

from cyo_adventure.api.deps import (
    Context,
    authorize_family,
    authorize_profile,
)
from cyo_adventure.api.schemas import (
    CompletionBody,
    CompletionListView,
    CompletionView,
    ConflictView,
    ReadingStateBody,
    ReadingStateView,
    SeriesNextBook,
    SeriesNextView,
    error_responses,
)
from cyo_adventure.api.sentinel_log import strip_and_log
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import (
    Completion,
    ReadingState,
    Series,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from cyo_adventure.player.replay import validate_reading_state
from cyo_adventure.publishing.state_machine import Visibility
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

_logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1", tags=["reading"], responses=error_responses(401, 403, 404)
)

_PUBLISHED = "published"


def _parse_uuid(raw: str, field: str) -> uuid.UUID:
    """Parse a UUID path/body value, mapping failure to a 422 error."""
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        msg = f"{field} must be a UUID"
        raise ValidationError(msg, field=field, value=raw) from exc


def _view(row: ReadingState) -> ReadingStateView:
    """Build the response view from a reading-state row."""
    return ReadingStateView(
        child_profile_id=str(row.child_profile_id),
        storybook_id=row.storybook_id,
        version=row.version,
        current_node=row.current_node,
        var_state=dict(row.var_state),
        path=list(row.path),
        visit_set=list(row.visit_set),
        save_slots=dict(row.save_slots),
        state_revision=row.state_revision,
        updated_by_device_id=row.updated_by_device_id,
        last_synced_at=row.last_synced_at,
    )


def _conflict(row: ReadingState, detail: str) -> JSONResponse:
    """Build a 409 conflict response carrying the current row."""
    body = ConflictView(detail=detail, current_row=_view(row))
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


async def _load_readable_storybook(
    ctx: Context, storybook_id: str, profile_id: uuid.UUID
) -> Storybook:
    """Load a storybook and assert the given profile may read it.

    Three-way access branch (WS-E Task 13 follow-up, same E5 amendment ruling
    as the library/ratings paths): an own-family book is always readable; a
    cross-family family-visibility book is always 403; a cross-family catalog
    book is readable only when it is assigned to ``profile_id``.

    Args:
        ctx: The request context (principal + session).
        storybook_id: The story id from the path or body.
        profile_id: The already-authorized child profile whose progress or
            completion is being read or written.

    Returns:
        Storybook: A story the profile may read.

    Raises:
        ResourceNotFoundError: If the story does not exist (404).
        AuthorizationError: If the story is a cross-family family-visibility
            book, or a cross-family catalog book not assigned to the profile
            (403).
    """
    # #CRITICAL: security: every reading-state/completion path gates here
    # before touching the row: own-family books pass; a cross-family
    # visibility='family' book is 403 (authorization-matrix.md, unchanged); a
    # cross-family visibility='catalog' book requires a StorybookAssignment
    # row for this profile, so a valid token for family A still cannot reach
    # family B's private stories or unassigned catalog stories.
    # #VERIFY: own-family -> pass; cross-family family-visibility -> 403;
    # catalog+assigned -> pass; catalog+unassigned -> 403 (drive-by progress
    # writes are blocked like drive-by ratings in ratings.py).
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if book.family_id != ctx.principal.family_id:
        if book.visibility != Visibility.CATALOG.value:
            authorize_family(ctx.principal, book.family_id)
        else:
            assigned = await ctx.session.scalar(
                select(StorybookAssignment.storybook_id).where(
                    StorybookAssignment.storybook_id == book.id,
                    StorybookAssignment.child_profile_id == profile_id,
                )
            )
            if assigned is None:
                msg = "storybook is not accessible to this profile"
                raise AuthorizationError(msg, resource=book.id)
    return book


async def _require_assignment(
    ctx: Context, storybook_id: str, profile_id: uuid.UUID
) -> None:
    """Require a StorybookAssignment row for this profile and story.

    M1: this is a SEPARATE, always-required predicate from
    ``_load_readable_storybook``'s family/visibility gate above. Before this
    fix, an own-family book always passed that gate with no assignment check
    at all, so a child could read/write reading-state and completions for any
    published, approved story in their own family, whether or not a guardian
    had ever actually assigned it to them; the cross-family catalog arm was
    already assignment-gated. Deliberately NOT called from ``get_series_next``
    (out of M1's named scope): that route only leaks the next book's
    metadata, never its content, and its own read gate on the CURRENT book
    already runs through this same function via the other two routes.

    Args:
        ctx: The request context (principal + session).
        storybook_id: The story id.
        profile_id: The already-authorized child profile.

    Raises:
        ResourceNotFoundError: If no assignment row exists for this
            (profile, story) pair (404, matching the existence-hiding
            convention library.py/assignments.py already use for unassigned
            content).
    """
    assigned = await ctx.session.scalar(
        select(StorybookAssignment.storybook_id).where(
            StorybookAssignment.storybook_id == storybook_id,
            StorybookAssignment.child_profile_id == profile_id,
        )
    )
    if assigned is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)


def _require_current_published_approved(
    book: Storybook, version_row: StorybookVersion, version: int
) -> None:
    """Reject a non-current, non-published, or unapproved version.

    M1: mirrors ``library.py::get_storybook_version``'s non-admin gate. Called
    only where a NEW pin to ``version`` is being established (a first
    reading-state save, or a completion, both cite ``version`` verbatim from
    the request body); an update to an ALREADY-pinned row is deliberately
    exempt (see the ``require_current`` docstring on
    ``_validate_against_pinned_version``) so continued reading on a
    since-superseded version keeps working.

    Args:
        book: The storybook row (status + current_published_version).
        version_row: The version row being validated.
        version: The version number being validated.

    Raises:
        ResourceNotFoundError: If the book is not published, this is not its
            current published version, or the version lacks ``approved_by``
            (404, existence hidden).
    """
    if (
        book.status != _PUBLISHED
        or book.current_published_version != version
        or version_row.approved_by is None
    ):
        msg = f"version {version} of storybook '{book.id}' not found"
        raise ResourceNotFoundError(msg)


async def _validate_against_pinned_version(
    ctx: Context,
    body: ReadingStateBody,
    book: Storybook,
    *,
    require_current: bool,
) -> None:
    """Load the pinned story version and validate the save against it.

    Args:
        ctx: The request context (principal + session).
        body: The save payload (carries the version being pinned/validated).
        book: The storybook row (its ``id`` is the story id), for the
            current/published/approved check.
        require_current: When ``True`` (a first, create-path save), also
            require the version be the book's CURRENT published, approved
            version (M1). ``False`` for an update to an already-established
            row: the saved state may legitimately be pinned to an older
            version than the currently published one (a since-superseded
            republish), so re-checking current/published/approved on every
            update would break that supported scenario.

    Raises:
        ResourceNotFoundError: If ``body.version`` has no persisted version
            row, or (when ``require_current`` and the caller is non-admin)
            the version is not the book's current published, approved one.
        ValidationError: If the structural floor or full replay rejects the state.
    """
    # #CRITICAL: data integrity: run the structural floor (always) plus full
    # engine replay (when choice_path is present) before any write so a forged
    # current_node/var_state/path cannot be persisted (Finding 2). Called only
    # at the two sites that actually write (create, and a version-matched
    # update), so a stale-session version mismatch can 409 before this runs.
    # #ASSUME: security: choice_path is optional this slice; absent it, only the
    # structural floor runs (tracked as C5 in
    # docs/planning/r1-deferred-debt-register.md).
    # #CRITICAL: security: save_slots is passed too, closing the one field this
    # gate used to omit. It was client-writable and persisted straight onto the
    # row below with no content check at all, which defeated the anti-forgery
    # intent stated immediately above. validate_reading_state now refuses any
    # non-empty slot map (B1).
    # #VERIFY: tests/unit/test_replay.py::test_non_empty_save_slots_rejected.
    # #VERIFY: player/replay.py validate_reading_state; missing version -> 404.
    version_row = await ctx.session.get(StorybookVersion, (book.id, body.version))
    if version_row is None:
        msg = f"version {body.version} of '{book.id}' not found"
        raise ResourceNotFoundError(msg)
    if require_current and not ctx.principal.is_admin:
        _require_current_published_approved(book, version_row, body.version)
    validate_reading_state(
        version_row.blob,
        current_node=body.current_node,
        var_state=body.var_state,
        path=body.path,
        visit_set=body.visit_set,
        choice_path=body.choice_path,
        save_slots=body.save_slots,
    )


@router.get("/reading-state/{profile_id}/{storybook_id}")
async def get_reading_state(
    profile_id: str,
    storybook_id: str,
    ctx: Context,
) -> ReadingStateView:
    """Return a child's reading state for a story.

    Args:
        profile_id: The child profile.
        storybook_id: The story.
        ctx: The request context (principal and session).

    Returns:
        ReadingStateView: The stored reading state.

    Raises:
        ResourceNotFoundError: If the story or reading state does not exist.
    """
    # #CRITICAL: security: profile access is authorized before any row read so a
    # child cannot read another profile's state (IDOR); the path profile is
    # authoritative (the body carries no profile_id).
    # #VERIFY: authorize_profile raises AuthorizationError -> 403; covered by
    # tests/integration/test_authorization.py.
    # #CRITICAL: security: M1 (security-hardening-plan-2026-07.md): an own-family
    # book previously passed _load_readable_storybook with no assignment check
    # at all, so a child could read reading-state for any published story in
    # their own family, assigned or not. Admins are exempt (they manage every
    # family's assignments; mirrors library.py::get_storybook_version).
    # #VERIFY: tests/integration/test_reading_state.py::
    # test_get_reading_state_unassigned_story_404.
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    await _load_readable_storybook(ctx, storybook_id, parsed)
    if not ctx.principal.is_admin:
        await _require_assignment(ctx, storybook_id, parsed)
    row = await ctx.session.get(ReadingState, (parsed, storybook_id))
    if row is None:
        msg = f"no reading state for profile '{profile_id}' on '{storybook_id}'"
        raise ResourceNotFoundError(msg)
    return _view(row)


@router.get("/series-next/{profile_id}/{storybook_id}")
async def get_series_next(
    profile_id: str,
    storybook_id: str,
    ctx: Context,
) -> SeriesNextView:
    """Resolve the next book in this storybook's series for a profile.

    Expected absences (not a series book, no next book yet, next book
    unpublished, next book not readable by this profile) answer 200 with
    ``next: null``; errors are reserved for the CURRENT book being unknown
    or unreadable, matching the other kid-scoped reading routes (WS-G spec
    section 4).

    Args:
        profile_id: The child profile asking to continue.
        storybook_id: The series book the profile just finished.
        ctx: The request context.

    Returns:
        SeriesNextView: The next book's id, published version, title,
            declared entry node, and state-carry flag, or ``next: null``.

    Raises:
        ResourceNotFoundError: If the current storybook does not exist.
        AuthorizationError: If the profile is not the principal's, or the
            CURRENT book is not readable by it.
    """
    # #CRITICAL: security: profile authorization and the current book's read
    # gate run before any series resolution so this route cannot be used to
    # probe another family's series structure.
    # #VERIFY: test_series_next_other_familys_profile_forbidden (the
    # authorize_profile gate) and
    # test_series_next_current_book_not_readable_forbidden (the current
    # book's read gate raising AuthorizationError -> 403).
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    book = await _load_readable_storybook(ctx, storybook_id, parsed)
    if book.series_id is None or book.book_index is None:
        return SeriesNextView(next=None)
    sibling = await ctx.session.scalar(
        select(Storybook).where(
            Storybook.series_id == book.series_id,
            Storybook.book_index == book.book_index + 1,
        )
    )
    published_version = sibling.current_published_version if sibling else None
    if sibling is None or sibling.status != "published" or published_version is None:
        return SeriesNextView(next=None)
    # #ASSUME: security: the next book must pass the SAME read gate as any
    # direct open; reusing _load_readable_storybook keeps this route from
    # becoming a second, divergent access path. Expected absence maps a
    # sibling 403/404 to next=null, which also avoids an existence oracle
    # (unreadable and nonexistent answer identically).
    # #VERIFY: test_series_next_unassigned_catalog_sibling_is_null vs
    # test_series_next_assigned_catalog_sibling_returned.
    try:
        await _load_readable_storybook(ctx, sibling.id, parsed)
    except (AuthorizationError, ResourceNotFoundError):
        return SeriesNextView(next=None)
    version_row = await ctx.session.get(
        StorybookVersion, (sibling.id, published_version)
    )
    if version_row is None:
        return SeriesNextView(next=None)
    series_row = await ctx.session.get(Series, book.series_id)
    blob = version_row.blob
    # #CRITICAL: security: this is a kid-facing series-continuation feed, so
    # a raw personalization sentinel (e.g. {~HERO:Explorer~}) must never
    # reach a non-opted-in reader (ADR-023 P3); see
    # tests/unit/test_title_strip_registry.py for the authoritative
    # strip-or-raw enumeration across every title-bearing response surface.
    # #VERIFY: test_reading_api_unit.py::TestGetSeriesNext::
    # test_next_book_title_strips_sentinels.
    title = blob.get("title")
    # #EDGE: data integrity: a pre-WS-G sibling blob carries no embedded
    # series block; the declared entry node is then unknown and the client
    # falls back to the document's start_node (identical in v1 by G2).
    # #VERIFY: test_series_next_legacy_sibling_has_null_entry_node.
    entry: str | None = None
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        series_block = metadata.get("series")
        if isinstance(series_block, dict):
            raw_entry = series_block.get("series_entry_node")
            if isinstance(raw_entry, str):
                entry = raw_entry
    stripped_title = (
        strip_and_log(
            title,
            at="series_next.title",
            storybook_id=sibling.id,
            version=published_version,
        )
        if isinstance(title, str)
        else ""
    )
    return SeriesNextView(
        next=SeriesNextBook(
            storybook_id=sibling.id,
            version=published_version,
            title=stripped_title,
            series_entry_node=entry,
            carries_state=series_row.carries_state if series_row else False,
        )
    )


@router.put(
    "/reading-state/{profile_id}/{storybook_id}",
    response_model=ReadingStateView,
    responses={
        409: {
            "model": ConflictView,
            "description": (
                "Revision or version conflict; the body carries the current row "
                "for client-side reconciliation."
            ),
        }
    },
)
async def put_reading_state(
    profile_id: str,
    storybook_id: str,
    body: ReadingStateBody,
    ctx: Context,
) -> ReadingStateView | JSONResponse:
    """Save reading progress with revision-based optimistic concurrency.

    Args:
        profile_id: The child profile (authoritative; body has no profile_id).
        storybook_id: The story.
        body: The save payload.
        ctx: The request context.

    Returns:
        ReadingStateView | JSONResponse: The saved row on success, or a 409
            conflict body carrying the current row on a revision/version clash.

    Raises:
        ResourceNotFoundError: If the story, or the version body.version cites,
            does not exist.
        ValidationError: If a first (create) save does not start at revision 0,
            or the submitted state fails the structural floor or full replay.
    """
    # #CRITICAL: security: profile access is authorized before any row read or
    # write so a child cannot write another profile's state (IDOR).
    # #VERIFY: authorize_profile raises AuthorizationError -> 403.
    # #CRITICAL: security: M1 (security-hardening-plan-2026-07.md): an
    # own-family book previously passed _load_readable_storybook with no
    # assignment check, so a child could write reading-state for any
    # published story in their own family, assigned or not. Admins are
    # exempt (mirrors library.py::get_storybook_version).
    # #VERIFY: tests/integration/test_reading_state.py::
    # test_put_reading_state_unassigned_story_404.
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    book = await _load_readable_storybook(ctx, storybook_id, parsed)
    if not ctx.principal.is_admin:
        await _require_assignment(ctx, storybook_id, parsed)
    # #CRITICAL: concurrency: lock the row for the read-modify-write so two
    # concurrent saves for the same profile/story serialize instead of racing the
    # revision check (optimistic concurrency, tech-spec multi-device sync rules).
    # #VERIFY: SELECT ... FOR UPDATE on Postgres; a concurrent first-write race
    # still relies on the primary key (single reader per profile in Phase 1).
    row = await ctx.session.scalar(
        select(ReadingState)
        .where(
            ReadingState.child_profile_id == parsed,
            ReadingState.storybook_id == storybook_id,
        )
        .with_for_update()
    )
    if row is None:
        # M1: the create path establishes a NEW pin; require the current,
        # published, approved version so a first save cannot pin to a
        # superseded or never-approved version (require_current=True).
        await _validate_against_pinned_version(ctx, body, book, require_current=True)
        return _create_reading_state(ctx, parsed, storybook_id, body)
    # Idempotent replay: the same event was already applied; return current row.
    if body.event_id is not None and row.last_event_id == body.event_id:
        return _view(row)
    # A stale-session version mismatch is a concurrency conflict, not a lookup
    # failure: it must 409 even when body.version has no persisted version row
    # (the client is out of date, not malformed), so this check runs before
    # version validation below.
    if body.version != row.version:
        return _conflict(row, "reading_state version mismatch")
    if body.state_revision != row.state_revision:
        return _conflict(row, "reading_state revision mismatch")
    # M1: an update to an ALREADY-established row may legitimately continue
    # against an older, since-superseded version the row is pinned to,
    # so this path does not re-require the current/published/approved
    # version (require_current=False); only structural/replay validation
    # runs.
    await _validate_against_pinned_version(ctx, body, book, require_current=False)
    _apply_body(row, body)
    return _view(row)


def _create_reading_state(
    ctx: Context, profile_id: uuid.UUID, storybook_id: str, body: ReadingStateBody
) -> ReadingStateView:
    """Create the first reading-state row for a profile/story pair.

    Raises:
        ValidationError: If the first save does not start at ``state_revision`` 0;
            the server owns the counter, so a client may not seed an arbitrary
            starting revision.
    """
    # #ASSUME: data integrity: the first save for a profile/story pair must start
    # at revision 0 so the server, not the client, owns the revision counter.
    # #VERIFY: reject a nonzero starting revision before inserting the row.
    if body.state_revision != 0:
        msg = "first reading-state save must start at state_revision 0"
        raise ValidationError(msg, field="state_revision", value=body.state_revision)
    row = ReadingState(
        child_profile_id=profile_id,
        storybook_id=storybook_id,
        version=body.version,
        current_node=body.current_node,
    )
    _apply_body(row, body)
    ctx.session.add(row)
    return _view(row)


def _apply_body(row: ReadingState, body: ReadingStateBody) -> None:
    """Apply a save body to a row and bump the server revision."""
    row.version = body.version
    row.current_node = body.current_node
    row.var_state = dict(body.var_state)
    row.path = list(body.path)
    row.visit_set = list(body.visit_set)
    row.save_slots = dict(body.save_slots)
    row.state_revision = body.state_revision + 1
    row.last_event_id = body.event_id
    row.updated_by_device_id = body.device_id
    row.last_synced_at = datetime.now(UTC)


def _version_ending_ids(blob: Mapping[str, object]) -> set[str]:
    """Return the set of ending ids declared in a stored Storybook blob."""
    nodes = blob.get("nodes")
    if not isinstance(nodes, list):
        return set()
    found: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or node.get("is_ending") is not True:
            continue
        ending = node.get("ending")
        if isinstance(ending, dict) and isinstance(ending.get("id"), str):
            found.add(ending["id"])
    return found


@router.post("/completions")
async def record_completion(body: CompletionBody, ctx: Context) -> CompletionView:
    """Record that a child reached an ending of a story version.

    Args:
        body: The completion request.
        ctx: The request context.

    Returns:
        CompletionView: The recorded (or pre-existing) completion.

    Raises:
        ResourceNotFoundError: If the story or version does not exist.
        ValidationError: If the ending id is not part of the cited version.
    """
    # #CRITICAL: security: profile access and story readability (own-family,
    # or catalog-and-assigned; see _load_readable_storybook) are authorized
    # before the completion is recorded so a child cannot write completions
    # for another profile or an inaccessible book (IDOR).
    # #VERIFY: authorize_profile/_load_readable_storybook raise -> 403;
    # ending_id is validated against the cited version's blob (data integrity).
    # #CRITICAL: security: M1 (security-hardening-plan-2026-07.md): an
    # own-family book previously passed _load_readable_storybook with no
    # assignment check, so a child could record completions for any
    # published, approved story in their own family, assigned or not.
    # Unlike the reading-state routes, every completion is a fresh pin (no
    # update path), so the current/published/approved check runs
    # unconditionally here rather than behind a require_current flag.
    # Admins are exempt (mirrors library.py::get_storybook_version).
    # #VERIFY: tests/integration/test_reading_state.py::
    # test_record_completion_unassigned_story_404 and
    # test_record_completion_non_current_version_rejected.
    parsed = _parse_uuid(body.profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    book = await _load_readable_storybook(ctx, body.storybook_id, parsed)
    if not ctx.principal.is_admin:
        await _require_assignment(ctx, body.storybook_id, parsed)
    version_row = await ctx.session.get(
        StorybookVersion, (body.storybook_id, body.version)
    )
    if version_row is None:
        msg = f"version {body.version} of '{body.storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if not ctx.principal.is_admin:
        _require_current_published_approved(book, version_row, body.version)
    if body.ending_id not in _version_ending_ids(version_row.blob):
        msg = "ending_id does not belong to the cited version"
        raise ValidationError(msg, field="ending_id", value=body.ending_id)
    key = (parsed, body.storybook_id, body.version, body.ending_id)
    existing = await ctx.session.get(Completion, key)
    if existing is not None:
        row = existing
    else:
        row = _new_completion(ctx, parsed, body)
        # Flush so the DB server_default populates found_at, then read it back so
        # the response timestamp matches the persisted value rather than the app
        # clock at request time.
        await ctx.session.flush()
        await ctx.session.refresh(row, ["found_at"])
    return _completion_view(row)


def _new_completion(
    ctx: Context, profile_id: uuid.UUID, body: CompletionBody
) -> Completion:
    """Insert a new completion row."""
    row = Completion(
        child_profile_id=profile_id,
        storybook_id=body.storybook_id,
        version=body.version,
        ending_id=body.ending_id,
    )
    ctx.session.add(row)
    return row


def _completion_view(row: Completion) -> CompletionView:
    """Build the response view from a Completion row."""
    return CompletionView(
        child_profile_id=str(row.child_profile_id),
        storybook_id=row.storybook_id,
        version=row.version,
        ending_id=row.ending_id,
        found_at=row.found_at,
    )


@router.get("/completions/{profile_id}")
async def list_completions(profile_id: str, ctx: Context) -> CompletionListView:
    """List every ending a child profile has completed.

    Phase 3d (COPPA 312.6(a) access / GDPR Article 15): ``completion`` was
    the one child-linked table with no read path at all before this endpoint;
    a guardian requesting an access/export report for their child had no way
    to retrieve it.

    Args:
        profile_id: The child profile whose completions are requested.
        ctx: The request context (principal + session).

    Returns:
        CompletionListView: The profile's completions.

    Raises:
        ValidationError: If profile_id is not a UUID.
        AuthorizationError: If the profile is not the caller's.
    """
    # #CRITICAL: security: a caller may only read completions for a profile it
    # owns, mirroring ratings.py::list_ratings.
    # #VERIFY: authorize_profile raises AuthorizationError -> 403.
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    # Stable order: most-recently-found first, storybook_id/ending_id as
    # tie-breakers so the response is deterministic across calls (mirrors
    # list_ratings's ordering rationale).
    rows = await ctx.session.scalars(
        select(Completion)
        .where(Completion.child_profile_id == parsed)
        .order_by(
            Completion.found_at.desc(),
            Completion.storybook_id.asc(),
            Completion.ending_id.asc(),
        )
    )
    return CompletionListView(completions=[_completion_view(row) for row in rows.all()])
