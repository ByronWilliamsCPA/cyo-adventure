"""Persistent character CRUD (ADR-028): create, rename, activate, retire.

A character carries progression across books within one profile: a chosen
archetype and three stats (might/wits/nerve), stored as ``character_attribute``
rows and surfaced here as a flat ``attributes`` dict (see
``characters/seeding.py``). At most one character per profile may be active
(the ``uq_character_one_active`` partial unique index); creating a second
character, or explicitly activating a retired one, retires whichever
character was active before, in the same transaction as the activation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.api.deps import (
    Context,
    Principal,
    authorize_profile,
    parse_uuid,
)
from cyo_adventure.api.schemas import (
    CharacterCreateBody,
    CharacterListView,
    CharacterUpdateBody,
    CharacterView,
    error_responses,
)
from cyo_adventure.characters.seeding import initial_attributes
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
)
from cyo_adventure.db.models import Character, CharacterAttribute, ChildProfile

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/v1", tags=["characters"], responses=error_responses(401, 403)
)


def _require_guardian(principal: Principal) -> None:
    """Reject principals that may not permanently delete a character.

    Args:
        principal: The authenticated caller.

    Raises:
        AuthorizationError: If the caller does not hold the guardian role.
    """
    # #CRITICAL: security: only a guardian may permanently erase a character
    # (irreversible progression loss); a child may create, rename, and switch
    # between characters, but never delete one outright.
    # #VERIFY: tests/integration/test_characters_api.py::
    # test_kid_cannot_delete_character, ::test_guardian_can_delete_character.
    if not principal.is_guardian:
        msg = "guardian role required"
        raise AuthorizationError(msg)


async def _attributes_of(
    session: AsyncSession, character_id: uuid.UUID
) -> dict[str, int]:
    """Return the stored attribute rows for one character as a flat dict.

    Args:
        session: The request session.
        character_id: The character whose attributes are read.

    Returns:
        dict[str, int]: Attribute name to value; empty if none are stored.
    """
    rows = await session.scalars(
        select(CharacterAttribute).where(
            CharacterAttribute.character_id == character_id
        )
    )
    return {row.name: row.value_int for row in rows.all()}


def _view(row: Character, attributes: dict[str, int]) -> CharacterView:
    """Build the response view from a Character row and its attribute dict.

    Args:
        row: The ORM row.
        attributes: The character's stored attributes (name to value).

    Returns:
        CharacterView: The wire-safe view.
    """
    return CharacterView(
        id=str(row.id),
        profile_id=str(row.child_profile_id),
        name=row.name,
        archetype=row.archetype,
        look=row.look,
        is_active=row.is_active,
        books_completed=row.books_completed,
        attributes=attributes,
        created_at=row.created_at,
        retired_at=row.retired_at,
    )


async def _load_character(session: AsyncSession, character_id: uuid.UUID) -> Character:
    """Load a Character row by id or raise 404.

    Args:
        session: The request session.
        character_id: The character to load.

    Returns:
        Character: The loaded row.

    Raises:
        ResourceNotFoundError: If no character with this id exists.
    """
    row = await session.get(Character, character_id)
    if row is None:
        msg = f"character '{character_id}' not found"
        raise ResourceNotFoundError(msg)
    return row


async def _retire_active_character(
    session: AsyncSession,
    profile_id: uuid.UUID,
    *,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """Retire the profile's currently active character, if any.

    Args:
        session: The request session (unit-of-work; not committed here).
        profile_id: The profile whose active character is retired.
        exclude_id: A character id to skip (the one being activated), so
            re-activating the already-active character is a no-op rather than
            retiring and re-activating itself.
    """
    # #CRITICAL: concurrency: this read-then-update is always followed, in the
    # SAME request, by the caller inserting or activating the replacement --
    # both statements share the request's session and its single commit (see
    # api/deps.py::get_db_session). The partial unique index
    # uq_character_one_active is checked per-statement, so the retiring
    # UPDATE below must be flushed before the replacement is marked active, or
    # Postgres rejects the activation and leaves the profile with a retired
    # incumbent and no active character: a worse state than the one it
    # started in. That ordering says nothing about real concurrent requests:
    # two overlapping activate-or-create calls for the same profile can both
    # run this SELECT and both see zero active incumbents (each transaction's
    # write is invisible to the other until commit), so both proceed to mark
    # their own row active. Postgres then serializes the second flush behind
    # the first's uncommitted uq_character_one_active entry and rejects it
    # with an IntegrityError once the first commits; the caller (below in
    # this module) catches that and raises StateTransitionError, an HTTP 409,
    # rather than letting it surface as an unhandled 500.
    # #VERIFY: tests/integration/test_characters_api.py::
    # test_creating_a_second_character_retires_the_incumbent_atomically,
    # ::test_activating_a_replacement_retires_the_incumbent_atomically,
    # ::test_concurrent_activations_collide_into_a_409_not_a_500.
    stmt = select(Character).where(
        Character.child_profile_id == profile_id, Character.is_active.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(Character.id != exclude_id)
    incumbent = await session.scalar(stmt)
    if incumbent is not None:
        incumbent.is_active = False
        incumbent.retired_at = datetime.now(UTC)
        await session.flush()


@router.get("/characters")
async def list_characters(profile_id: str, ctx: Context) -> CharacterListView:
    """List one profile's characters, active first.

    Args:
        profile_id: The child profile whose characters are requested (query).
        ctx: The request context (principal + unit-of-work session).

    Returns:
        CharacterListView: The profile's characters, active before retired,
        then most-recently-created first within each group.

    Raises:
        ValidationError: If profile_id is not a UUID.
        AuthorizationError: If the profile is not the caller's.
    """
    # #CRITICAL: security: a caller may only list characters for a profile it
    # owns (guardian: own family; child: own profile).
    # #VERIFY: authorize_profile raises AuthorizationError -> 403.
    parsed = parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    rows = await ctx.session.scalars(
        select(Character)
        .where(Character.child_profile_id == parsed)
        .order_by(Character.is_active.desc(), Character.created_at.desc())
    )
    characters = rows.all()
    views = [
        _view(row, await _attributes_of(ctx.session, row.id)) for row in characters
    ]
    return CharacterListView(characters=views)


@router.post("/characters", status_code=201, responses=error_responses(404, 409))
async def create_character(body: CharacterCreateBody, ctx: Context) -> CharacterView:
    """Create a character for a child profile, activating it.

    Creating a new character while one is already active retires the
    incumbent in the same transaction: a profile has at most one active
    character at any time.

    Args:
        body: The new character's fields.
        ctx: The request context (principal + unit-of-work session).

    Returns:
        CharacterView: The stored, active character with zeroed stats.

    Raises:
        ValidationError: If profile_id is not a UUID.
        AuthorizationError: If the profile is not the caller's.
        ResourceNotFoundError: If the profile row does not exist.
        StateTransitionError: If a concurrent request already activated a
            character for this profile between the retire check above and
            this insert's flush (HTTP 409).
    """
    # #CRITICAL: security: a caller may only create a character for a profile
    # it owns; family_id is never taken from the request (see below).
    # #VERIFY: tests/integration/test_characters_api.py::
    # test_kid_cannot_create_character_for_sibling_profile,
    # ::test_guardian_cannot_create_character_for_another_familys_profile.
    profile_id = parse_uuid(body.profile_id, "profile_id")
    authorize_profile(ctx.principal, profile_id)
    profile = await ctx.session.get(ChildProfile, profile_id)
    if profile is None:
        msg = f"profile '{body.profile_id}' not found"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: concurrency: see _retire_active_character's docstring; the
    # retire and this insert share the same session/transaction.
    await _retire_active_character(ctx.session, profile_id)
    # #ASSUME: data integrity: family_id is sourced from the loaded
    # ChildProfile row, never from the request body -- CharacterCreateBody has
    # no family_id field at all, so extra=forbid also rejects a client attempt
    # to supply one. A client-supplied family_id would defeat the Tier 1 RLS
    # policy that keys on this column.
    # #VERIFY: the composite FK (fk_character_profile_family) would reject a
    # mismatched pair at the database layer even if this were ever bypassed.
    row = Character(
        child_profile_id=profile_id,
        family_id=profile.family_id,
        name=body.name,
        archetype=body.archetype,
        look=body.look,
    )
    ctx.session.add(row)
    try:
        await ctx.session.flush()
    except IntegrityError as exc:
        msg = f"profile '{profile_id}' already has an active character"
        raise StateTransitionError(msg) from exc
    await ctx.session.refresh(row, ["created_at"])
    attributes = initial_attributes(body.archetype)
    ctx.session.add_all(
        [
            CharacterAttribute(character_id=row.id, name=name, value_int=value)
            for name, value in attributes.items()
        ]
    )
    await ctx.session.flush()
    return _view(row, attributes)


@router.patch("/characters/{character_id}", responses=error_responses(404))
async def update_character(
    character_id: str, body: CharacterUpdateBody, ctx: Context
) -> CharacterView:
    """Rename or re-choose a character's archetype/look.

    Args:
        character_id: The character to update.
        body: The fields to change; omitted fields are untouched. Attributes
            and books_completed are absent from the body by design (see
            ``CharacterUpdateBody``'s docstring) and cannot be set here.
        ctx: The request context (principal + unit-of-work session).

    Returns:
        CharacterView: The updated character.

    Raises:
        ValidationError: If character_id is not a UUID.
        ResourceNotFoundError: If no character with this id exists.
        AuthorizationError: If the character's profile is not the caller's.
    """
    parsed = parse_uuid(character_id, "character_id")
    row = await _load_character(ctx.session, parsed)
    # #CRITICAL: security: load-then-authorize: the character's OWN profile,
    # never a client-supplied one, is what gates this write.
    # #VERIFY: tests/integration/test_authz_matrix.py's ROUTE_TABLE entry for
    # ("PATCH", "/api/v1/characters/{character_id}"), which is now a member of
    # both _CROSS_FAMILY_ROUTE_KEYS (test_cross_family_guardian_is_rejected,
    # ::test_cross_family_guardian_from_stranger_family_is_rejected) and
    # _CROSS_FAMILY_CHILD_ROUTE_KEYS (test_cross_family_child_from_stranger_family_is_rejected,
    # ::test_family_a_child_cannot_reach_stranger_family_profile).
    authorize_profile(ctx.principal, row.child_profile_id)
    if body.name is not None:
        row.name = body.name
    if body.archetype is not None:
        row.archetype = body.archetype
    if body.look is not None:
        row.look = body.look
    await ctx.session.flush()
    attributes = await _attributes_of(ctx.session, row.id)
    return _view(row, attributes)


@router.post("/characters/{character_id}/activate", responses=error_responses(404, 409))
async def activate_character(character_id: str, ctx: Context) -> CharacterView:
    """Make a retired character active again, retiring whichever is active now.

    Args:
        character_id: The character to activate.
        ctx: The request context (principal + unit-of-work session).

    Returns:
        CharacterView: The now-active character.

    Raises:
        ValidationError: If character_id is not a UUID.
        ResourceNotFoundError: If no character with this id exists.
        AuthorizationError: If the character's profile is not the caller's.
        StateTransitionError: If a concurrent request already activated a
            different character for this profile between the retire check
            below and this activation's flush (HTTP 409).
    """
    parsed = parse_uuid(character_id, "character_id")
    row = await _load_character(ctx.session, parsed)
    authorize_profile(ctx.principal, row.child_profile_id)
    # #CRITICAL: concurrency: retiring the incumbent and activating the
    # replacement must be one transaction. The partial unique index
    # uq_character_one_active makes a two-statement version fail loudly
    # rather than corrupt, but it fails on the ACTIVATE, leaving the child
    # with a retired incumbent and no active character: a worse state than
    # the one they started in. Both statements share this request's
    # session, which commits once. Two genuinely CONCURRENT activate requests
    # for different characters on the same profile are a distinct risk this
    # single-transaction ordering does not cover: each request's own
    # _retire_active_character can run before the other's activation commits,
    # so both see no incumbent and both proceed. Postgres then serializes the
    # second flush behind the first's uncommitted uq_character_one_active
    # entry and rejects it with an IntegrityError once the first commits,
    # which is caught below and re-raised as StateTransitionError (HTTP 409)
    # rather than surfacing as an unhandled 500.
    # #VERIFY: tests/integration/test_characters_api.py::
    # test_activating_a_replacement_retires_the_incumbent_atomically,
    # ::test_concurrent_activations_collide_into_a_409_not_a_500.
    # #ASSUME: data integrity: profile_id is captured now, before the flush
    # that can fail, rather than read off `row` inside the except block
    # below. A failed flush's rollback restores the pre-flush snapshot and
    # expires row's attributes, so `row.child_profile_id` after that point is
    # a lazy-load against a session already left DEACTIVE by the failure;
    # that load raises PendingRollbackError, pre-empting the
    # StateTransitionError this handler means to raise before it is even
    # constructed.
    # #VERIFY: test_concurrent_activations_collide_into_a_409_not_a_500 pins
    # this: it failed with PendingRollbackError, not StateTransitionError,
    # until this local variable was introduced.
    profile_id = row.child_profile_id
    await _retire_active_character(ctx.session, profile_id, exclude_id=row.id)
    row.is_active = True
    row.retired_at = None
    try:
        await ctx.session.flush()
    except IntegrityError as exc:
        msg = f"profile '{profile_id}' already has an active character"
        raise StateTransitionError(msg) from exc
    attributes = await _attributes_of(ctx.session, row.id)
    return _view(row, attributes)


@router.post("/characters/{character_id}/retire", responses=error_responses(404))
async def retire_character(character_id: str, ctx: Context) -> CharacterView:
    """Retire a character, leaving the profile with no active character.

    Idempotent: retiring an already-retired character is a no-op rather than
    overwriting its existing ``retired_at``.

    Args:
        character_id: The character to retire.
        ctx: The request context (principal + unit-of-work session).

    Returns:
        CharacterView: The character, now inactive.

    Raises:
        ValidationError: If character_id is not a UUID.
        ResourceNotFoundError: If no character with this id exists.
        AuthorizationError: If the character's profile is not the caller's.
    """
    parsed = parse_uuid(character_id, "character_id")
    row = await _load_character(ctx.session, parsed)
    authorize_profile(ctx.principal, row.child_profile_id)
    # #ASSUME: data integrity: retiring the only active character leaves the
    # profile with zero active characters; this is legal, not an error, and no
    # replacement is chosen automatically.
    # #VERIFY: tests/integration/test_characters_api.py::
    # test_retiring_the_only_active_character_leaves_none_active.
    if row.is_active:
        row.is_active = False
        row.retired_at = datetime.now(UTC)
        await ctx.session.flush()
    attributes = await _attributes_of(ctx.session, row.id)
    return _view(row, attributes)


@router.delete(
    "/characters/{character_id}", status_code=204, responses=error_responses(404)
)
async def delete_character(character_id: str, ctx: Context) -> None:
    """Permanently erase a character and its progression.

    Args:
        character_id: The character to delete.
        ctx: The request context (principal + unit-of-work session).

    Raises:
        AuthorizationError: If the caller is not a guardian, or the
            character's profile is not the caller's.
        ResourceNotFoundError: If no character with this id exists.
    """
    _require_guardian(ctx.principal)
    parsed = parse_uuid(character_id, "character_id")
    row = await _load_character(ctx.session, parsed)
    authorize_profile(ctx.principal, row.child_profile_id)
    await ctx.session.delete(row)
    await ctx.session.flush()
