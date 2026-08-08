"""Unit tests for the character-cap/active-conflict integrity discriminator.

Covers ``db.integrity.is_character_one_active_conflict`` (the pure predicate,
mirroring ``tests/unit/test_child_sessions_provision.py`` for
``is_authn_subject_conflict``) and, since a predicate can be correct in
isolation while a call site still ignores it, the handler-level wiring in
``api/characters.py::create_character`` and ``::activate_character``: only
the ``uq_character_one_active`` race becomes a 409 ``StateTransitionError``;
every other constraint violation (``ck_character_archetype``,
``ck_character_not_active_and_retired``, an FK violation, ...) must
propagate as the real ``IntegrityError`` instead of being relabeled.
Docker-independent: the session is an ``AsyncMock``, never a real database.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.api import characters as characters_module
from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.schemas import CharacterCreateBody
from cyo_adventure.core.exceptions import StateTransitionError
from cyo_adventure.db.integrity import is_character_one_active_conflict
from cyo_adventure.db.models import Character, ChildProfile

pytestmark = [pytest.mark.unit]


class _FakeOrigError(Exception):
    """Stand-in for a DBAPI error with driver-reported diagnostic fields.

    Mirrors ``tests/unit/test_child_sessions_provision.py::_FakeOrigError``:
    asyncpg exposes ``sqlstate`` and ``constraint_name``; psycopg exposes
    ``pgcode``. Each attribute is optional so a test can model a driver that
    surfaces none of them and force the message-text fallback.
    """

    def __init__(
        self,
        message: str,
        *,
        sqlstate: str | None = None,
        pgcode: str | None = None,
        constraint_name: str | None = None,
    ) -> None:
        super().__init__(message)
        if sqlstate is not None:
            self.sqlstate = sqlstate
        if pgcode is not None:
            self.pgcode = pgcode
        if constraint_name is not None:
            self.constraint_name = constraint_name


def _integrity_error(orig: _FakeOrigError) -> IntegrityError:
    return IntegrityError("INSERT INTO ...", None, orig)


def _principal(profile_id: uuid.UUID, *, role: str = "guardian") -> Principal:
    """Return a minimal Principal authorized for exactly one profile."""
    return Principal(
        subject=f"{role}-x",
        user_id=uuid4(),
        role=role,
        family_id=uuid4(),
        profile_ids=frozenset({profile_id}),
    )


# ---------------------------------------------------------------------------
# is_character_one_active_conflict: the pure predicate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unique_violation_on_one_active_index_is_conflict() -> None:
    """23505 on uq_character_one_active is the benign activation race."""
    orig = _FakeOrigError(
        'duplicate key value violates unique constraint "uq_character_one_active"',
        sqlstate="23505",
        constraint_name="uq_character_one_active",
    )
    assert is_character_one_active_conflict(_integrity_error(orig)) is True


@pytest.mark.unit
def test_archetype_check_violation_is_not_conflict() -> None:
    """A CHECK violation on archetype is a real defect, not the active race."""
    orig = _FakeOrigError(
        'new row for relation "character" violates check constraint '
        '"ck_character_archetype"',
        sqlstate="23514",
        constraint_name="ck_character_archetype",
    )
    assert is_character_one_active_conflict(_integrity_error(orig)) is False


@pytest.mark.unit
def test_not_active_and_retired_check_violation_is_not_conflict() -> None:
    """The is_active/retired_at consistency CHECK is a real defect too."""
    orig = _FakeOrigError(
        'new row for relation "character" violates check constraint '
        '"ck_character_not_active_and_retired"',
        sqlstate="23514",
        constraint_name="ck_character_not_active_and_retired",
    )
    assert is_character_one_active_conflict(_integrity_error(orig)) is False


@pytest.mark.unit
def test_profile_family_fk_violation_is_not_conflict() -> None:
    """The composite FK violation must propagate, not be swallowed as a 409."""
    orig = _FakeOrigError(
        "insert or update on table character violates foreign key "
        "constraint; see fk_character_profile_family",
        sqlstate="23503",
        constraint_name="fk_character_profile_family",
    )
    assert is_character_one_active_conflict(_integrity_error(orig)) is False


@pytest.mark.unit
def test_message_text_fallback_when_constraint_name_absent() -> None:
    """When the driver omits the constraint, fall back to the message text."""
    orig = _FakeOrigError(
        'duplicate key value violates unique constraint "uq_character_one_active"',
        sqlstate="23505",
    )
    assert is_character_one_active_conflict(_integrity_error(orig)) is True


# ---------------------------------------------------------------------------
# create_character: the handler-level flush guard
# ---------------------------------------------------------------------------


def _create_session(*, flush_error: IntegrityError, profile: ChildProfile) -> AsyncMock:
    """Build a mocked AsyncSession that fails create_character's insert flush.

    ``session.scalar`` is called twice before the flush: once by
    ``_reject_when_at_character_cap`` (the count query, answered 0, well
    under the cap) and once by ``_retire_active_character`` (the active-
    incumbent query, answered None, so no retire-then-insert path runs).
    Neither call's SQL is inspected; the side_effect list relies on call
    order, which ``create_character`` fixes.
    """
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=profile)
    session.scalar = AsyncMock(side_effect=[0, None])
    session.flush = AsyncMock(side_effect=flush_error)
    return session


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_character_translates_only_the_one_active_race() -> None:
    """A uq_character_one_active flush failure becomes a 409 StateTransitionError."""
    profile_id = uuid4()
    profile = ChildProfile(id=profile_id, family_id=uuid4(), age_band="8-11")
    orig = _FakeOrigError(
        'duplicate key value violates unique constraint "uq_character_one_active"',
        sqlstate="23505",
        constraint_name="uq_character_one_active",
    )
    session = _create_session(flush_error=_integrity_error(orig), profile=profile)
    ctx = RequestContext(principal=_principal(profile_id), session=session)
    body = CharacterCreateBody(
        profile_id=str(profile_id), name="Ember", archetype="scout", look="avatar_02"
    )

    with pytest.raises(StateTransitionError, match="already has an active character"):
        await characters_module.create_character(body, ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_character_propagates_other_integrity_errors() -> None:
    """A CHECK/FK flush failure propagates as IntegrityError, not a 409.

    Reverting the ``is_character_one_active_conflict`` guard in
    ``create_character`` back to a bare ``except IntegrityError: raise
    StateTransitionError(...)`` makes this fail: every constraint violation
    would relabel as "already has an active character", including this one,
    which has nothing to do with activation.
    """
    profile_id = uuid4()
    profile = ChildProfile(id=profile_id, family_id=uuid4(), age_band="8-11")
    orig = _FakeOrigError(
        'new row for relation "character" violates check constraint '
        '"ck_character_archetype"',
        sqlstate="23514",
        constraint_name="ck_character_archetype",
    )
    flush_error = _integrity_error(orig)
    session = _create_session(flush_error=flush_error, profile=profile)
    ctx = RequestContext(principal=_principal(profile_id), session=session)
    body = CharacterCreateBody(
        profile_id=str(profile_id), name="Ember", archetype="scout", look="avatar_02"
    )

    with pytest.raises(IntegrityError) as excinfo:
        await characters_module.create_character(body, ctx)
    assert excinfo.value is flush_error
    assert not isinstance(excinfo.value, StateTransitionError)


# ---------------------------------------------------------------------------
# activate_character: the handler-level flush guard
# ---------------------------------------------------------------------------


def _retired_character(profile_id: uuid.UUID) -> Character:
    """Build an unpersisted, retired Character ORM row for activate_character."""
    return Character(
        id=uuid4(),
        child_profile_id=profile_id,
        family_id=uuid4(),
        name="Ember",
        archetype="scout",
        look="avatar_02",
        is_active=False,
    )


def _activate_session(*, flush_error: IntegrityError, row: Character) -> AsyncMock:
    """Build a mocked AsyncSession that fails activate_character's flush.

    ``session.get`` answers ``_load_character``'s lookup; ``session.scalar``
    answers ``_retire_active_character``'s incumbent query with None (no
    other active character to retire first).
    """
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=row)
    session.scalar = AsyncMock(return_value=None)
    session.flush = AsyncMock(side_effect=flush_error)
    return session


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activate_character_translates_only_the_one_active_race() -> None:
    """A uq_character_one_active flush failure becomes a 409 StateTransitionError."""
    profile_id = uuid4()
    row = _retired_character(profile_id)
    orig = _FakeOrigError(
        'duplicate key value violates unique constraint "uq_character_one_active"',
        sqlstate="23505",
        constraint_name="uq_character_one_active",
    )
    session = _activate_session(flush_error=_integrity_error(orig), row=row)
    ctx = RequestContext(principal=_principal(profile_id), session=session)

    with pytest.raises(StateTransitionError, match="already has an active character"):
        await characters_module.activate_character(str(row.id), ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activate_character_propagates_other_integrity_errors() -> None:
    """A CHECK-constraint flush failure propagates as IntegrityError, not a 409.

    Reverting the guard in ``activate_character`` to a bare
    ``except IntegrityError: raise StateTransitionError(...)`` makes this
    fail: the not-active-and-retired CHECK violation would also be relabeled
    "already has an active character".
    """
    profile_id = uuid4()
    row = _retired_character(profile_id)
    orig = _FakeOrigError(
        'new row for relation "character" violates check constraint '
        '"ck_character_not_active_and_retired"',
        sqlstate="23514",
        constraint_name="ck_character_not_active_and_retired",
    )
    flush_error = _integrity_error(orig)
    session = _activate_session(flush_error=flush_error, row=row)
    ctx = RequestContext(principal=_principal(profile_id), session=session)

    with pytest.raises(IntegrityError) as excinfo:
        await characters_module.activate_character(str(row.id), ctx)
    assert excinfo.value is flush_error
    assert not isinstance(excinfo.value, StateTransitionError)
