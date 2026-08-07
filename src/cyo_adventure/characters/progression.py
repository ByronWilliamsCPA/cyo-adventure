"""Progression writeback: raise a persistent character's stats (ADR-028 decision 6).

Spec section 7.3, three requirements: a character grows only from a satisfying
ending; growth is monotone and capped at the vocabulary ceiling (a book cannot
lower a stat the child earned elsewhere, and cannot push it past the canonical
max); and the writeback is idempotent under offline-queue replay, by
constraint rather than by an application-side check (a read-then-write
"have we done this?" is racy under concurrent sync from two devices).

Both statements below are computed IN the database, not read-modify-written in
Python, for exactly that reason.

``character_book_completion``'s primary key is three columns: the reading
state's ``(child_profile_id, storybook_id)`` plus ``character_id``.
``ending_id`` is stored but is NOT part of the key. Two consequences follow,
both deliberate (see db/models.py::CharacterBookCompletion):

- A given character can be credited for a given storybook exactly once,
  forever, including across a re-read of the same book and across a later
  version of that same book. There is no "completed it again" or "completed
  the new version" bonus.
- Because ``ending_id`` sits outside the key, recording a second completion at
  a *different* ending for the same (profile, storybook, character) is a
  no-op, the same as replaying the identical ending: ``ON CONFLICT DO
  NOTHING`` cannot distinguish the two, and nothing here tries to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from cyo_adventure.storybook.character_vocabulary import (
    ARCHETYPE_VARIABLE_NAME,
    CANONICAL_CHARACTER_VARIABLES,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.db.models import ReadingState
    from cyo_adventure.storybook.evaluator import VarState

_INSERT_COMPLETION = text(
    """
    INSERT INTO character_book_completion (
        reading_state_child_profile_id,
        reading_state_storybook_id,
        character_id,
        ending_id
    )
    VALUES (:profile_id, :storybook_id, :character_id, :ending_id)
    ON CONFLICT DO NOTHING
    RETURNING character_id
    """
)

_RAISE_ATTRIBUTE = text(
    """
    UPDATE character_attribute
    SET value_int = LEAST(:canonical_max, GREATEST(value_int, :exit_value))
    WHERE character_id = :character_id AND name = :name
    """
)

# books_completed is incremented in-database for the same reason as the
# attribute raise below: an application-side `character.books_completed += 1`
# reads the current value in Python and writes an absolute new value back,
# which loses an update when two different books finish for the same
# character in overlapping transactions (each reads the same pre-increment
# value and both write the same post-increment value). Computing the
# increment in the UPDATE statement itself makes it commute with a concurrent
# increment the same way LEAST/GREATEST does for the attribute.
_INCREMENT_BOOKS_COMPLETED = text(
    """
    UPDATE character
    SET books_completed = books_completed + 1
    WHERE id = :character_id
    """
)

# archetype is identity, not progression: it is the character's chosen role
# (Scout, Guardian, ...), set once at creation/build and never raised by a
# book finishing well. Filtering it out explicitly here means a future book
# that happens to both declare `accepts_character` stats AND export an
# `archetype` variable in its exit var_state still cannot touch it, rather
# than relying on the accident that no such book exists today.
_PROGRESSION_VARIABLES = {
    name: variable
    for name, variable in CANONICAL_CHARACTER_VARIABLES.items()
    if name != ARCHETYPE_VARIABLE_NAME
}


async def record_progression(
    session: AsyncSession,
    *,
    reading_state: ReadingState,
    character_id: uuid.UUID,
    ending_id: str,
    exit_var_state: VarState,
) -> None:
    """Grow a character from a satisfying completion, idempotently.

    The caller (``api/reading.py::record_completion``) is responsible for
    calling this only when the ending reached is satisfying; this function
    performs no ending-kind check of its own; it only turns "a satisfying
    completion happened" into a books_completed increment and a monotone,
    capped attribute raise, exactly once per (reading_state, character) pair
    no matter how many times it is called for the same pair.

    Args:
        session: The request's database session. The caller commits; this
            function only adds statements to the current transaction.
        reading_state: The reading-state row the completion belongs to. Only
            its ``child_profile_id`` and ``storybook_id`` are read, to build
            the ``character_book_completion`` key.
        character_id: The character to credit and grow.
        ending_id: The ending reached, stored on the completion row but not
            part of its primary key (see module docstring).
        exit_var_state: The reading state's persisted ``var_state`` at
            completion time; the source of the values a stat may be raised
            to. Never the request body: see the ``#CRITICAL`` marker at this
            function's call site in ``api/reading.py``.
    """
    # #CRITICAL: concurrency: the attribute update is computed IN the
    # statement, not read-modify-written in Python. Two devices syncing
    # the same completion concurrently would both read the old value and
    # both write the same new one, losing one book's progress; LEAST and
    # GREATEST make the update commutative and idempotent.
    # #VERIFY: tests/integration/test_character_progression.py::
    # test_a_lower_exit_value_does_not_reduce_a_stat and
    # test_a_stat_cannot_exceed_the_canonical_maximum
    result = await session.execute(
        _INSERT_COMPLETION,
        {
            "profile_id": reading_state.child_profile_id,
            "storybook_id": reading_state.storybook_id,
            "character_id": character_id,
            "ending_id": ending_id,
        },
    )
    # #ASSUME: data integrity: an empty RETURNING result is the ONLY signal
    # that this (reading_state, character) pair was already credited; there
    # is no separate "was it created" flag. This is what makes the increment
    # below conditional on the INSERT having affected a row rather than
    # running unconditionally on every call, which would let idempotency of
    # the completion row coexist with a books_completed counter that climbed
    # on every replay.
    # #VERIFY: tests/integration/test_character_progression.py::
    # test_a_replayed_completion_does_not_increment_twice and
    # test_books_completed_increments_only_when_a_row_was_inserted.
    if result.first() is None:
        return

    await session.execute(_INCREMENT_BOOKS_COMPLETED, {"character_id": character_id})

    for name, canonical in _PROGRESSION_VARIABLES.items():
        if name not in exit_var_state:
            continue
        exit_value = exit_var_state[name]
        # #EDGE: data integrity: a non-int exit value (VarValue is
        # bool | int | str; every canonical variable is declared INT, so a
        # well-formed story never produces one) is skipped rather than sent
        # to a statement whose parameter is typed as an integer, since bool
        # is a subclass of int and would otherwise silently pass as 0 or 1.
        # #VERIFY: no test in this suite feeds a str or bool exit value for a
        # canonical name; every fixture here declares might/wits/nerve as int.
        if not isinstance(exit_value, int) or isinstance(exit_value, bool):
            continue
        await session.execute(
            _RAISE_ATTRIBUTE,
            {
                "character_id": character_id,
                "name": name,
                "exit_value": exit_value,
                "canonical_max": canonical.max,
            },
        )
