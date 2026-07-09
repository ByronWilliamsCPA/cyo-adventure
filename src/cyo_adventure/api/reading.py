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

from cyo_adventure.api.deps import Context, authorize_family, authorize_profile
from cyo_adventure.api.schemas import (
    CompletionBody,
    CompletionView,
    ConflictView,
    ReadingStateBody,
    ReadingStateView,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import (
    Completion,
    ReadingState,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from cyo_adventure.player.replay import validate_reading_state
from cyo_adventure.publishing.state_machine import Visibility

if TYPE_CHECKING:
    from collections.abc import Mapping

router = APIRouter(prefix="/api/v1", tags=["reading"])


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


async def _validate_against_pinned_version(
    ctx: Context, storybook_id: str, body: ReadingStateBody
) -> None:
    """Load the pinned story version and validate the save against it.

    Raises:
        ResourceNotFoundError: If ``body.version`` has no persisted version row.
        ValidationError: If the structural floor or full replay rejects the state.
    """
    # #CRITICAL: data integrity: run the structural floor (always) plus full
    # engine replay (when choice_path is present) before any write so a forged
    # current_node/var_state/path cannot be persisted (Finding 2). Called only
    # at the two sites that actually write (create, and a version-matched
    # update), so a stale-session version mismatch can 409 before this runs.
    # #ASSUME: security: choice_path is optional this slice; absent it, only the
    # structural floor runs (completion-plan.md tracks making it required).
    # #VERIFY: player/replay.py validate_reading_state; missing version -> 404.
    version_row = await ctx.session.get(StorybookVersion, (storybook_id, body.version))
    if version_row is None:
        msg = f"version {body.version} of '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    validate_reading_state(
        version_row.blob,
        current_node=body.current_node,
        var_state=body.var_state,
        path=body.path,
        visit_set=body.visit_set,
        choice_path=body.choice_path,
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
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    await _load_readable_storybook(ctx, storybook_id, parsed)
    row = await ctx.session.get(ReadingState, (parsed, storybook_id))
    if row is None:
        msg = f"no reading state for profile '{profile_id}' on '{storybook_id}'"
        raise ResourceNotFoundError(msg)
    return _view(row)


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
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    await _load_readable_storybook(ctx, storybook_id, parsed)
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
        await _validate_against_pinned_version(ctx, storybook_id, body)
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
    await _validate_against_pinned_version(ctx, storybook_id, body)
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
    parsed = _parse_uuid(body.profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    await _load_readable_storybook(ctx, body.storybook_id, parsed)
    version_row = await ctx.session.get(
        StorybookVersion, (body.storybook_id, body.version)
    )
    if version_row is None:
        msg = f"version {body.version} of '{body.storybook_id}' not found"
        raise ResourceNotFoundError(msg)
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
    return CompletionView(
        child_profile_id=str(row.child_profile_id),
        storybook_id=row.storybook_id,
        version=row.version,
        ending_id=row.ending_id,
        found_at=row.found_at,
    )


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
