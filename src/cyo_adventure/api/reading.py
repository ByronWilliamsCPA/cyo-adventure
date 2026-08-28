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
from sqlalchemy import func, select

from cyo_adventure.api.deps import (
    Context,
    Role,
    authorize_family,
    authorize_profile,
)
from cyo_adventure.api.schemas import (
    CompletionBody,
    CompletionListView,
    CompletionRecordedView,
    CompletionView,
    ConflictView,
    ReadingStateBody,
    ReadingStateResultView,
    ReadingStateView,
    SeriesNextBook,
    SeriesNextView,
    error_responses,
)
from cyo_adventure.api.sentinel_log import strip_and_log
from cyo_adventure.characters.progression import record_progression
from cyo_adventure.characters.seeding import character_seed
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import (
    Character,
    CharacterAttribute,
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
from cyo_adventure.validator.series import SATISFYING_ENDING_KINDS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.storybook.evaluator import VarState

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


async def _view(session: AsyncSession, row: ReadingState) -> ReadingStateView:
    """Build the response view from a reading-state row.

    ``character_name`` is looked up live rather than stored, because
    Character rows are never deleted on retirement (only marked
    ``is_active=False``); a live lookup by the row's persisted
    ``character_id`` therefore still resolves a retired character's name
    correctly, which is the right answer to "whose adventure is this".
    """
    # #ASSUME: external resources: this helper reaches the database now, so it
    # needs a live session and every call site must await it. The name is read
    # live rather than snapshotted because Character rows are only marked
    # is_active=False on retirement, never deleted, so the lookup still
    # resolves for a read whose bound character has since been retired.
    # #VERIFY: tests/integration/test_reading_character_binding.py::
    # test_starting_a_read_binds_the_active_character_and_seeds_its_state
    # asserts the active character's name comes back, and
    # test_a_read_in_progress_keeps_its_recorded_seed asserts the same name
    # still resolves after that character is retired mid-book.
    character_name: str | None = None
    if row.character_id is not None:
        character_name = await session.scalar(
            select(Character.name).where(Character.id == row.character_id)
        )
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
        character_id=str(row.character_id) if row.character_id is not None else None,
        character_name=character_name,
        seed_var_state=dict(row.seed_var_state)
        if row.seed_var_state is not None
        else None,
    )


async def _conflict(
    session: AsyncSession, row: ReadingState, detail: str
) -> JSONResponse:
    """Build a 409 conflict response carrying the current row."""
    body = ConflictView(detail=detail, current_row=await _view(session, row))
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


async def _attributes_of(
    session: AsyncSession, character_id: uuid.UUID
) -> dict[str, int]:
    """Return the stored attribute rows for one character as a flat dict.

    Mirrors ``characters.py::_attributes_of`` exactly, duplicated rather than
    imported: that name is module-private (leading underscore) and this
    package's convention is a small explained duplicate over widening
    another module's public surface for one call site (see
    ``personalization.py::_is_active`` mirroring
    ``family_connections.py::_is_active``).

    Args:
        session: The request session.
        character_id: The character whose attributes are read.

    Returns:
        dict[str, int]: Attribute name to value; empty if none are stored.
    """
    # #ASSUME: data integrity: the seed is exactly the attribute rows persisted
    # for this character, with no defaulting or synthesis here. A character
    # with no stored rows therefore carries an empty seed, which
    # StoryEngine.start_continuation treats as "no carry" and falls back to the
    # story's declared initials rather than zeroing anything.
    # #VERIFY: tests/integration/test_reading_character_binding.py::
    # test_starting_a_read_binds_the_active_character_and_seeds_its_state
    # asserts the persisted seed equals the exact attribute rows written for
    # the bound character.
    rows = await session.scalars(
        select(CharacterAttribute).where(
            CharacterAttribute.character_id == character_id
        )
    )
    return {row.name: row.value_int for row in rows.all()}


async def _resolve_active_character(
    session: AsyncSession, profile_id: uuid.UUID
) -> Character | None:
    """Return the profile's active character row, or ``None`` if it has none.

    The one query this whole feature rests on: it takes ``profile_id`` from
    the caller, never from a request body, so its result cannot be steered
    by anything the client sent.
    """
    # #CRITICAL: security: profile_id is the AUTHENTICATED profile taken from
    # the route path, never a request-body field. If a client could steer this
    # query it could bind another profile's character, and because the seed
    # becomes the replay baseline, seeding would become an arbitrary-variable-
    # write primitive that replay validation would then bless. The marker lives
    # here, on the resolver, and not only at the call site, so an edit that
    # widens this signature to accept a caller-supplied id sees it.
    # #VERIFY: tests/integration/test_reading_character_binding.py::
    # test_a_client_supplied_character_id_is_rejected
    #
    # #CRITICAL: data integrity: scalar() with no LIMIT and no ORDER BY is
    # safe ONLY because db/models.py declares the partial unique index
    # uq_character_one_active on child_profile_id WHERE is_active, so at most
    # one row can ever match. The safety lives in the schema, not in this
    # query: relax that index and this call site silently picks an arbitrary
    # character, with nothing raising anywhere.
    # #VERIFY: tests/unit/test_character_models.py::
    # test_only_one_character_per_profile_may_be_active proves the declared
    # index is unique and partial; tests/integration/test_schema_parity.py::
    # test_migrated_character_one_active_index_is_partial proves the migrated
    # database carries it as a partial index too.
    return await session.scalar(
        select(Character).where(
            Character.child_profile_id == profile_id,
            Character.is_active.is_(True),
        )
    )


async def _bind_active_character(
    session: AsyncSession, profile_id: uuid.UUID
) -> tuple[uuid.UUID | None, VarState | None]:
    """Resolve the profile's active character and seed a read start from it.

    Returns:
        tuple[uuid.UUID | None, VarState | None]: The character's id and its
            seed. The seed half is ``None`` whenever there is nothing to
            carry, both when the profile has no active character and in the
            (API-unreachable) case of an active character with no stored
            attribute rows; an unseeded read is the normal case, not an error.
    """
    # #ASSUME: data integrity: a profile with no active character seeds
    # nothing and both halves of the return are None together. An unseeded
    # read is the normal case, not an error, so this must never raise and must
    # never substitute a synthesized default seed for the missing character.
    # #VERIFY: tests/integration/test_reading_character_binding.py::
    # test_starting_a_read_with_no_active_character_is_unseeded asserts both
    # the response fields and the persisted columns are NULL.
    character = await _resolve_active_character(session, profile_id)
    if character is None:
        return None, None
    attributes = await _attributes_of(session, character.id)
    # `or None` collapses the empty seed to NULL rather than persisting `{}`.
    # A character with zero attribute rows is unreachable through the API
    # (create always writes the four canonical rows via initial_attributes),
    # and downstream behaviour is identical either way because `if carried:`
    # is falsy for both, but `{}` would be a third persisted shape that the
    # "both halves are None together" contract above does not describe, and it
    # would surface as `seed_var_state: {}` on the wire instead of `null`.
    return character.id, (character_seed(attributes) or None)


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


def _acts_as_admin(ctx: Context, book: Storybook) -> bool:
    """Return whether the caller carries ADMIN authority over this book.

    # #CRITICAL: security: the M1/H1 gates below must NOT key on the raw
    # ``is_admin`` capability flag. ``_profile_ids_for`` in deps.py returns an
    # empty profile set for anyone whose base role is not GUARDIAN, so an
    # admin-ONLY adult already 403s at ``authorize_profile`` upstream and never
    # reaches these gates; an ``is_admin`` test therefore fires for exactly one
    # population, the dual-role adult (role=GUARDIAN + is_admin=True), whose
    # profile set is their own whole family. That is precisely the population
    # the gates protect, so an ``is_admin`` exemption would silently disable
    # them for a dual-role parent's own children. ``acting_role`` collapses
    # to ADMIN only for a CROSS-family target, so a dual-role adult is fully
    # gated on their own family and unrestricted on another family's content
    # (the cross-family review authority the exemption actually exists for).
    # On these reading routes the ADMIN branch is in fact unreachable today,
    # because every one of them is entered through ``authorize_profile`` on a
    # path ``profile_id``, which already confines the caller to profiles in
    # their OWN family; it is kept as a deliberate mirror of the same gate in
    # library.py::get_storybook_version, where cross-family draft review IS
    # reachable, so the two cannot drift apart. Failing closed here is the
    # safe direction of that redundancy.
    # #VERIFY: tests/integration/test_reading_state.py::
    # test_dual_role_adult_is_gated_on_own_family.

    Args:
        ctx: The request context (principal + session).
        book: The storybook whose family is the authorization target.

    Returns:
        bool: ``True`` only when the principal acts on this book in the ADMIN
            capacity (a cross-family action by an admin-capable adult).
    """
    return ctx.principal.acting_role(book.family_id) == Role.ADMIN


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
    seed_var_state: VarState | None,
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
        seed_var_state: The server-held seed the persisted row began from, or
            ``None`` for an unseeded read (see ``put_reading_state`` for how
            each call site sources this).

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
    if require_current and not _acts_as_admin(ctx, book):
        _require_current_published_approved(book, version_row, body.version)
    validate_reading_state(
        version_row.blob,
        current_node=body.current_node,
        var_state=body.var_state,
        path=body.path,
        visit_set=body.visit_set,
        choice_path=body.choice_path,
        save_slots=body.save_slots,
        seed_var_state=seed_var_state,
    )


@router.get("/reading-state/{profile_id}/{storybook_id}")
async def get_reading_state(
    profile_id: str,
    storybook_id: str,
    ctx: Context,
) -> ReadingStateResultView:
    """Return a child's reading state for a story, or an explicit absence.

    A profile with no saved progress for the story is a normal condition,
    not an error: this answers 200 with ``state: null``, matching the
    convention ``get_series_next`` documents below for the other
    kid-scoped reading routes. Errors are reserved for the story or the
    profile's access to it being invalid.

    Args:
        profile_id: The child profile.
        storybook_id: The story.
        ctx: The request context (principal and session).

    Returns:
        ReadingStateResultView: The stored reading state, or ``state: null``
            if the profile has not started this book.

    Raises:
        ResourceNotFoundError: If the story does not exist, or the profile
            has no assignment for a cross-family catalog story (see
            ``_require_assignment``).
        AuthorizationError: If the story is a cross-family family-visibility
            book not readable by this profile.
    """
    # #CRITICAL: security: profile access is authorized before any row read so a
    # child cannot read another profile's state (IDOR); the path profile is
    # authoritative (the body carries no profile_id).
    # #VERIFY: authorize_profile raises AuthorizationError -> 403; covered by
    # tests/integration/test_authorization.py.
    # #CRITICAL: security: M1 (security-hardening-plan-2026-07.md): an own-family
    # book previously passed _load_readable_storybook with no assignment check
    # at all, so a child could read reading-state for any published story in
    # their own family, assigned or not. Only a CROSS-family admin action is
    # exempt (see _acts_as_admin); an admin-capable adult reading their own
    # family's content is held to the same gate as any other guardian.
    # #VERIFY: tests/integration/test_reading_state.py::
    # test_get_reading_state_unassigned_own_family_story_404.
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    book = await _load_readable_storybook(ctx, storybook_id, parsed)
    if not _acts_as_admin(ctx, book):
        await _require_assignment(ctx, storybook_id, parsed)
    row = await ctx.session.get(ReadingState, (parsed, storybook_id))
    if row is None:
        return ReadingStateResultView(state=None)
    return ReadingStateResultView(state=await _view(ctx.session, row))


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
    # published story in their own family, assigned or not. Only a
    # CROSS-family admin action is exempt (see _acts_as_admin).
    # #VERIFY: tests/integration/test_reading_state.py::
    # test_put_reading_state_unassigned_own_family_story_404.
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    book = await _load_readable_storybook(ctx, storybook_id, parsed)
    if not _acts_as_admin(ctx, book):
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
        #
        # #CRITICAL: security: the bound character is resolved from the
        # AUTHENTICATED profile, never from the request. A client-supplied
        # character_id would let one profile seed a read with another's
        # numbers, and because the seed becomes the replay baseline, it would
        # promote seeding into an arbitrary-variable-write primitive that
        # replay validation would then bless.
        # #VERIFY: tests/integration/test_reading_character_binding.py::
        # test_a_client_supplied_character_id_is_rejected
        #
        # #CRITICAL: data integrity: the seed is snapshotted into
        # reading_state.seed_var_state at read start and never recomputed.
        # Recomputing on save would let a mid-book retirement or a writeback
        # from another book rewrite the baseline this read is validated
        # against, invalidating a save the child legitimately holds.
        # #VERIFY: same module, test_a_read_in_progress_keeps_its_recorded_seed
        #
        # #EDGE: data integrity: a first save that omits choice_path is checked
        # only against the structural floor, so it can persist a var_state the
        # bound seed could never have produced. Nothing here can tell the
        # difference: the divergence is detectable only with a replay proof,
        # which is exactly what choice_path supplies. Every later save that
        # DOES carry a choice_path replays from the stored seed, disagrees, and
        # 422s, so the read wedges permanently. Accepted deliberately rather
        # than fixed server-side: today's client
        # (frontend/src/offline/sync.ts::toPutPayload) sends no choice_path at
        # all, so an equality check here would 422 legitimate saves the moment
        # a story mutates a seeded variable.
        #
        # STATUS (Task 9 landed): the client-side remedy this marker asked for
        # is now in place for an ONLINE fresh read. CharacterView.seed_var_state
        # exposes the server-computed seed before any row exists, and
        # frontend/src/reader/ReaderPage.tsx opens a fresh read from it via
        # startContinuation() instead of the story's declared initials. Two
        # narrow residuals keep this marker open rather than closing it:
        #   1. A fresh read that cannot reach the network, OR IS SERVED A
        #      CACHED characters response (the frontend service worker's
        #      catch-all /v1/* rule is NetworkFirst with a 5s timeout over a
        #      7-day cache: vite.config.ts; a body cached before this deploy
        #      has no seed_var_state at all), still opens from declared
        #      initials, and its queued first save can persist a var_state
        #      the bound seed could not have produced.
        #   2. The active character can change between the client's seed fetch
        #      and this create path's own _bind_active_character call (a
        #      guardian or a second tab switching characters in that window),
        #      so the two can disagree even online. The row then carries the
        #      NEW character's seed over a var_state actually produced from
        #      the OLD character's seed; nothing 422s at save time (residual 1
        #      applies here too: no choice_path to replay against), but on the
        #      read's next resume `canGoBack` fails closed against that
        #      mismatched seed, so Go back silently disappears for the rest of
        #      that read, and RESTART reopens from the new character's
        #      numbers. Not a wedge and not a defect Task 9 introduced, but
        #      worse than "latent" undersells it.
        # Both are latent, not live, for exactly the reason above: the client
        # sends no choice_path. Anything that starts sending one must close
        # them first (cache the active character's seed alongside the offline
        # story blob, and echo the seed the client actually started from so
        # this path can reject a mismatch rather than record a different one).
        # #VERIFY: nothing proves the wedge today, and nothing can while the
        # client omits choice_path; do not read a green suite as evidence the
        # condition is closed. The nearest real evidence is the complementary
        # case, tests/integration/test_reading_character_binding.py::
        # test_a_first_save_carrying_a_choice_path_replays_from_the_bound_seed,
        # which proves the seed IS enforced on this create path whenever a
        # choice_path is present. The client half is pinned by
        # tests/integration/test_reading_character_binding.py::
        # test_character_view_seed_matches_the_seed_a_read_start_would_bind
        # (one mapping, both sides) and frontend/src/reader/ReaderPage.test.tsx
        # "seeds a fresh read from the profile's active character".
        character_id, seed_var_state = await _bind_active_character(ctx.session, parsed)
        await _validate_against_pinned_version(
            ctx, body, book, require_current=True, seed_var_state=seed_var_state
        )
        return await _create_reading_state(
            ctx,
            parsed,
            storybook_id,
            body,
            character_id=character_id,
            seed_var_state=seed_var_state,
        )
    # Idempotent replay: the same event was already applied; return current row.
    if body.event_id is not None and row.last_event_id == body.event_id:
        return await _view(ctx.session, row)
    # A stale-session version mismatch is a concurrency conflict, not a lookup
    # failure: it must 409 even when body.version has no persisted version row
    # (the client is out of date, not malformed), so this check runs before
    # version validation below.
    if body.version != row.version:
        return await _conflict(ctx.session, row, "reading_state version mismatch")
    if body.state_revision != row.state_revision:
        return await _conflict(ctx.session, row, "reading_state revision mismatch")
    # M1: an update to an ALREADY-established row may legitimately continue
    # against an older, since-superseded version the row is pinned to,
    # so this path does not re-require the current/published/approved
    # version (require_current=False); only structural/replay validation
    # runs.
    # #CRITICAL: data integrity: row is already loaded above (the FOR UPDATE
    # select), so pass its persisted seed_var_state rather than None: a
    # character-seeded read must replay from the seed the server recorded on
    # creation, not from declared initials (see replay.py::_check_replay).
    # #VERIFY: tests/unit/test_reading_api_unit.py::
    # TestPutReadingState::test_update_path_forwards_the_row_seed_not_none
    # proves this call site forwards row.seed_var_state specifically (an
    # asymmetric body that is accepted under None but rejected under the
    # row's seed); tests/unit/test_replay.py::
    # test_replay_of_a_seeded_read_starts_from_the_seed and
    # test_replay_rejects_a_state_claiming_a_seed_it_was_not_given cover the
    # underlying seeded-replay behaviour this call site threads through.
    #
    # #CRITICAL: data integrity: this branch must FORWARD the stored
    # reading_state.seed_var_state column and must never re-derive the seed
    # from the profile's currently-active character. Recomputing is the
    # natural-looking implementation and it rewrites history mid-book: a
    # retirement, or a writeback from another book, would move the baseline a
    # read in progress is validated against and reject a save the child
    # legitimately holds. The create branch above cannot express this rule,
    # since there is nothing yet to recompute from; this is the branch where
    # "never recomputed" is a live constraint.
    # #VERIFY: tests/integration/test_reading_character_binding.py::
    # test_a_read_in_progress_keeps_its_recorded_seed retires the bound
    # character mid-book and then saves from the original seed, expecting 200,
    # which a recomputing implementation would 422; tests/unit/
    # test_reading_api_unit.py::TestPutReadingState::
    # test_update_path_forwards_the_row_seed_not_none pins the forwarding of
    # row.seed_var_state specifically.
    await _validate_against_pinned_version(
        ctx, body, book, require_current=False, seed_var_state=row.seed_var_state
    )
    _apply_body(row, body)
    return await _view(ctx.session, row)


async def _create_reading_state(
    ctx: Context,
    profile_id: uuid.UUID,
    storybook_id: str,
    body: ReadingStateBody,
    *,
    character_id: uuid.UUID | None,
    seed_var_state: VarState | None,
) -> ReadingStateView:
    """Create the first reading-state row for a profile/story pair.

    Args:
        ctx: The request context (principal + session).
        profile_id: The child profile starting the read.
        storybook_id: The story being started.
        body: The save payload.
        character_id: The bound active character's id, or ``None`` if the
            profile has none (resolved server-side; see
            ``_bind_active_character``).
        seed_var_state: The seed derived from that character's attributes,
            or ``None`` for an unseeded read.

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
        character_id=character_id,
        seed_var_state=seed_var_state,
    )
    _apply_body(row, body)
    ctx.session.add(row)
    # Ordering dependency: _view() queries when a character is bound, which
    # autoflushes this pending INSERT, so the row must already be fully
    # populated by _apply_body and added before the view runs.
    return await _view(ctx.session, row)


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


def _ending_kind(blob: Mapping[str, object], ending_id: str) -> str | None:
    """Return the declared ``kind`` of one ending in a stored Storybook blob.

    Args:
        blob: The pinned version's stored Storybook content blob.
        ending_id: The ending to look up.

    Returns:
        str | None: The ending's ``kind`` string (e.g. ``"success"``), or
        ``None`` if the ending id is not declared or the blob is malformed.
    """
    nodes = blob.get("nodes")
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if not isinstance(node, dict) or node.get("is_ending") is not True:
            continue
        ending = node.get("ending")
        if isinstance(ending, dict) and ending.get("id") == ending_id:
            kind = ending.get("kind")
            return kind if isinstance(kind, str) else None
    return None


def _ending_is_satisfying(blob: Mapping[str, object], ending_id: str) -> bool:
    """Whether ``ending_id`` is a satisfying ending, per CH-4's own definition.

    # #CRITICAL: security: ``kind`` is read from ``blob``, the SERVER's pinned
    # version content (``version_row.blob``, already loaded by
    # ``record_completion`` to validate the ending id), never from the
    # completion request body. ``CompletionBody`` has no kind/valence/
    # "satisfying" field for a client to assert in the first place, so a
    # child cannot claim a win for a book they did not finish: doing so would
    # turn character progression into a self-service API, farming stats
    # across the whole library without ever reaching a real satisfying
    # ending.
    # #VERIFY: tests/unit/test_reading_api_unit.py::
    # TestCompletionBodyContract::
    # test_a_completion_body_carrying_an_extra_field_is_rejected pins the
    # "no such field for a client to assert" half (extra="forbid"), and
    # tests/integration/test_character_progression.py::
    # test_a_satisfying_ending_raises_a_stat_and_counts_the_book and
    # test_an_unsatisfying_ending_writes_nothing pin that the server blob's
    # kind is what actually decides.

    Args:
        blob: The pinned version's stored Storybook content blob.
        ending_id: The ending reached, already validated to belong to this
            version by the caller.

    Returns:
        bool: True when the ending's declared kind is one of
        ``SATISFYING_ENDING_KINDS`` (SR-9's own definition, reused here
        rather than duplicated; see ``validator/series.py``).
    """
    kind = _ending_kind(blob, ending_id)
    return kind is not None and kind in SATISFYING_ENDING_KINDS


def _completion_ending_count(
    blob: Mapping[str, object], storybook_id: str, version: int
) -> int:
    """Return the version's declared ending count from blob metadata, or 0.

    Mirrors ``reading_history.py::_ending_count``: duplicated rather than
    imported so this module has no cross-router dependency, per this
    package's small-helper-duplication convention.

    # #ASSUME: data integrity: ``metadata.ending_count`` is enforced to equal
    # the story's real ending count at validation time (validator/layer1.py
    # L1-7), so a published version's value is trustworthy. A missing or
    # malformed field degrades to 0 (never raises) so a malformed blob cannot
    # 500 the completion POST a child is mid-celebration on.
    # #VERIFY: a malformed value is logged, not silently swallowed.

    Args:
        blob: The pinned version's stored Storybook content blob.
        storybook_id: The story id, for the warning log.
        version: The version number, for the warning log.

    Returns:
        int: The declared ending count, or 0 if absent/malformed.
    """
    metadata = blob.get("metadata")
    if not isinstance(metadata, dict):
        return 0
    count = metadata.get("ending_count")
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    if count is not None:
        _logger.warning(
            "completion_malformed_ending_count",
            storybook_id=storybook_id,
            version=version,
        )
    return 0


async def _distinct_endings_found(
    ctx: Context, profile_id: uuid.UUID, storybook_id: str, version: int
) -> int:
    """Count a profile's distinct completed endings for one book version.

    # #CRITICAL: concurrency: read-after-write within the same request's own
    # (not-yet-committed) transaction. ``record_completion`` flushes a new
    # row before this query runs, so the just-recorded ending is always
    # counted even though the transaction has not committed. A second,
    # concurrent completion from another device is invisible here until that
    # OTHER request commits; that request in turn counts its own flushed row.
    # Neither request can under-report the ending it itself just recorded.
    # #VERIFY: tests/integration/test_reading_state.py::
    # test_completion_response_reports_is_new_and_counts and
    # test_completion_repeat_reports_is_new_false.

    Args:
        ctx: The request context (session).
        profile_id: The child profile.
        storybook_id: The storybook id.
        version: The version number.

    Returns:
        int: The number of distinct ending ids this profile has completed
        for this (storybook, version).
    """
    count = await ctx.session.scalar(
        select(func.count(func.distinct(Completion.ending_id))).where(
            Completion.child_profile_id == profile_id,
            Completion.storybook_id == storybook_id,
            Completion.version == version,
        )
    )
    return count or 0


@router.post("/completions")
async def record_completion(
    body: CompletionBody, ctx: Context
) -> CompletionRecordedView:
    """Record that a child reached an ending of a story version.

    Args:
        body: The completion request.
        ctx: The request context.

    Returns:
        CompletionRecordedView: The recorded (or pre-existing) completion,
        plus ``is_new`` (whether this call inserted the row rather than
        hitting an existing one), ``found`` (this profile's distinct-ending
        count for the book/version after this call), and ``total`` (the
        version's declared ending count). See design review 2026-08-01
        section 3.4 / kid-appeal-implementation-plan.md W0.3.

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
    # Only a CROSS-family admin action is exempt (see _acts_as_admin).
    # #VERIFY: tests/integration/test_reading_state.py::
    # test_record_completion_unassigned_own_family_story_404 and
    # test_record_completion_rejects_non_current_version_404.
    parsed = _parse_uuid(body.profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    book = await _load_readable_storybook(ctx, body.storybook_id, parsed)
    acts_as_admin = _acts_as_admin(ctx, book)
    if not acts_as_admin:
        await _require_assignment(ctx, body.storybook_id, parsed)
    version_row = await ctx.session.get(
        StorybookVersion, (body.storybook_id, body.version)
    )
    if version_row is None:
        msg = f"version {body.version} of '{body.storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if not acts_as_admin:
        _require_current_published_approved(book, version_row, body.version)
    if body.ending_id not in _version_ending_ids(version_row.blob):
        msg = "ending_id does not belong to the cited version"
        raise ValidationError(msg, field="ending_id", value=body.ending_id)
    key = (parsed, body.storybook_id, body.version, body.ending_id)
    existing = await ctx.session.get(Completion, key)
    # #ASSUME: data integrity: `existing is None` is the only signal of
    # "this call inserted the row" (the PK-get above is the sole dedupe path,
    # no separate "was it created" flag exists on Completion itself).
    # #VERIFY: test_completion_repeat_reports_is_new_false posts the same
    # (profile, storybook, version, ending) twice and asserts is_new flips.
    is_new = existing is None
    if existing is not None:
        row = existing
    else:
        row = _new_completion(ctx, parsed, body)
        # Flush so the DB server_default populates found_at, then read it back so
        # the response timestamp matches the persisted value rather than the app
        # clock at request time. This flush is also what makes the
        # just-inserted row visible to _distinct_endings_found's query below,
        # which runs on the same (uncommitted) transaction.
        await ctx.session.flush()
        await ctx.session.refresh(row, ["found_at"])
    # Attempted on EVERY call, not gated on `is_new`: the offline queue can
    # replay this exact completion after a crash between the Completion
    # insert above and this writeback, and `record_progression` is its own
    # idempotent unit (see its module docstring), so re-attempting it here is
    # always safe and is what makes a partial-crash recovery possible at all.
    reading_state_row = await ctx.session.get(ReadingState, (parsed, body.storybook_id))
    if (
        reading_state_row is not None
        and reading_state_row.character_id is not None
        and _ending_is_satisfying(version_row.blob, body.ending_id)
    ):
        # #EDGE: data integrity: exit_var_state below is
        # reading_state_row.var_state, which is only as trustworthy as replay
        # validation, and replay only runs when a save carries a
        # choice_path; today's frontend (frontend/src/offline/sync.ts::
        # toPutPayload) sends none, so a client can already persist a
        # var_state no legitimate play could reach (see the #CRITICAL marker
        # above _create_reading_state's choice_path handling). This
        # writeback turns that pre-existing per-read weakness into a
        # durable, cross-book one instead of adding a new hole: the raise in
        # record_progression is monotone and capped at
        # CANONICAL_CHARACTER_VARIABLES[name].max, so the worst case is a
        # child maxing their own character's stats, never a value beyond the
        # vocabulary ceiling and never another profile's character.
        # #VERIFY: no test in this suite proves this boundary; closing it is
        # a hard prerequisite tracked as UW-C72 in unscheduled-work-register.md
        # (the player deriving its starting var_state from seed_var_state, per
        # the choice_path note above), not attempted here.
        await record_progression(
            ctx.session,
            reading_state=reading_state_row,
            character_id=reading_state_row.character_id,
            ending_id=body.ending_id,
            exit_var_state=reading_state_row.var_state,
        )
    found = await _distinct_endings_found(ctx, parsed, body.storybook_id, body.version)
    total = _completion_ending_count(version_row.blob, body.storybook_id, body.version)
    return _completion_recorded_view(row, is_new=is_new, found=found, total=total)


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
    """Build the plain response view (used by ``list_completions``) from a row."""
    return CompletionView(
        child_profile_id=str(row.child_profile_id),
        storybook_id=row.storybook_id,
        version=row.version,
        ending_id=row.ending_id,
        found_at=row.found_at,
    )


def _completion_recorded_view(
    row: Completion, *, is_new: bool, found: int, total: int
) -> CompletionRecordedView:
    """Build the ``POST /completions`` response: the row plus the celebration signal.

    Args:
        row: The (new-or-existing) Completion row.
        is_new: Whether this call's insert created the row (False on a
            repeat completion of an already-found ending).
        found: The profile's distinct-ending count for this book/version,
            counted fresh after this call.
        total: The book version's declared ending count.

    Returns:
        CompletionRecordedView: The assembled response.
    """
    # #EDGE: data integrity: CompletionRecordedView now REJECTS an incoherent
    # tally (found > total, or a new find with a zero count), which is the
    # right contract for a consumer but the wrong failure mode here: the row
    # is already committed by the time this view is built, so letting response
    # validation raise would hand a child an error screen for an ending the
    # server did in fact record. The only way found can exceed total is a
    # pinned version whose metadata.ending_count understates its real endings
    # (validator L1-7 makes that unreachable for anything published through
    # the gate; a hand-edited or restored row is not). Widen total to the
    # count actually observed and log, so the ending screen reads "3 of 3"
    # rather than "3 of 2" and the bad version is findable.
    # #VERIFY: tests/unit/test_reading_api_unit.py::
    # TestCompletionRecordedViewBoundary::
    # test_recorded_view_widens_an_understated_ending_total.
    if found > total:
        _logger.warning(
            "completion_ending_total_understated",
            storybook_id=row.storybook_id,
            version=row.version,
            declared_total=total,
            distinct_found=found,
        )
        total = found
    return CompletionRecordedView(
        child_profile_id=str(row.child_profile_id),
        storybook_id=row.storybook_id,
        version=row.version,
        ending_id=row.ending_id,
        found_at=row.found_at,
        is_new=is_new,
        found=found,
        total=total,
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
