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

from cyo_adventure.api.deps import Context, authorize_family, authorize_profile
from cyo_adventure.api.schemas import (
    CompletionBody,
    CompletionView,
    ConflictView,
    ReadingStateBody,
    ReadingStateView,
)
from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import (
    Completion,
    ReadingState,
    Storybook,
    StorybookVersion,
)

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


async def _load_owned_storybook(ctx: Context, storybook_id: str) -> Storybook:
    """Load a storybook and assert the principal's family owns it."""
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(ctx.principal, book.family_id)
    return book


@router.get(
    "/reading-state/{profile_id}/{storybook_id}", response_model=ReadingStateView
)
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
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    await _load_owned_storybook(ctx, storybook_id)
    row = await ctx.session.get(ReadingState, (parsed, storybook_id))
    if row is None:
        msg = f"no reading state for profile '{profile_id}' on '{storybook_id}'"
        raise ResourceNotFoundError(msg)
    return _view(row)


@router.put("/reading-state/{profile_id}/{storybook_id}", response_model=None)
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
    """
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    await _load_owned_storybook(ctx, storybook_id)
    row = await ctx.session.get(ReadingState, (parsed, storybook_id))
    if row is None:
        return _create_reading_state(ctx, parsed, storybook_id, body)
    # Idempotent replay: the same event was already applied; return current row.
    if body.event_id is not None and row.last_event_id == body.event_id:
        return _view(row)
    if body.version != row.version:
        return _conflict(row, "reading_state version mismatch")
    if body.state_revision != row.state_revision:
        return _conflict(row, "reading_state revision mismatch")
    _apply_body(row, body)
    return _view(row)


def _create_reading_state(
    ctx: Context, profile_id: uuid.UUID, storybook_id: str, body: ReadingStateBody
) -> ReadingStateView:
    """Create the first reading-state row for a profile/story pair."""
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


@router.post("/completions", response_model=CompletionView)
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
    parsed = _parse_uuid(body.profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    await _load_owned_storybook(ctx, body.storybook_id)
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
    row = existing or _new_completion(ctx, parsed, body)
    return CompletionView(
        child_profile_id=str(row.child_profile_id),
        storybook_id=row.storybook_id,
        version=row.version,
        ending_id=row.ending_id,
        found_at=row.found_at if existing else datetime.now(UTC),
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
