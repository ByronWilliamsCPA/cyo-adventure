"""Integration tests for progression writeback (ADR-028, Task 7).

Spec section 7.3: a completed book raises a persistent character's stats
only when the ending reached is satisfying, the raise is monotone and capped
at the canonical maximum, and the whole writeback is idempotent by
constraint (the ``character_book_completion`` primary key), not by an
application-side check.

The shared lantern fixture (``tests/fixtures/storybook/valid/03_tier2_lantern.json``,
loaded by the ``seed`` fixture) already declares four endings of mixed kind:
``e_treasure_found`` and ``xe_d0`` are ``success`` (satisfying), ``e_safe_exit``
is ``completion`` (also satisfying), and ``xe_term`` is ``discovery``
(neutral, NOT satisfying). These tests reuse that story rather than
authoring a new one, and write the ``reading_state`` row directly (bypassing
a real PUT save and its replay validation) so each test controls the exit
``var_state`` precisely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import (
    Character,
    CharacterAttribute,
    CharacterBookCompletion,
    ReadingState,
)
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    import uuid

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_SATISFYING_ENDING = "e_treasure_found"
_SATISFYING_ENDING_2 = "xe_d0"
_UNSATISFYING_ENDING = "xe_term"


async def _seed_attributes(
    sessions: async_sessionmaker[AsyncSession],
    character_id: uuid.UUID,
    *,
    might: int,
    wits: int,
    nerve: int,
) -> None:
    """Insert character_attribute rows directly.

    Mirrors tests/integration/test_reading_character_binding.py::
    _seed_attributes exactly: attributes are server-derived and no character
    route accepts them in a request body, so a test that needs a non-zero
    (or non-default) attribute must write the rows itself.
    """
    async with sessions() as session:
        session.add_all(
            [
                CharacterAttribute(
                    character_id=character_id, name="might", value_int=might
                ),
                CharacterAttribute(
                    character_id=character_id, name="wits", value_int=wits
                ),
                CharacterAttribute(
                    character_id=character_id, name="nerve", value_int=nerve
                ),
            ]
        )
        await session.commit()


async def _seed_reading_state(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    *,
    var_state: dict[str, object],
    character_id: uuid.UUID | None,
) -> None:
    """Insert a reading_state row directly, bypassing a real PUT save.

    The completions endpoint reads var_state (for progression) and
    character_id off the persisted row, never off the completion request
    body (CompletionBody carries neither field at all). Writing the row
    directly gives each test exact control over the exit values a stat may
    be raised to, without needing a structurally reachable play-through to
    satisfy PUT's replay validation.
    """
    async with sessions() as session:
        session.add(
            ReadingState(
                child_profile_id=seed.child_profile_id,
                storybook_id=seed.storybook_id,
                version=seed.version,
                current_node="n_treasure",
                var_state=dict(var_state),
                path=["n_treasure"],
                visit_set=["n_treasure"],
                save_slots={},
                state_revision=0,
                character_id=character_id,
                seed_var_state=None,
            )
        )
        await session.commit()


async def _character_progress(
    sessions: async_sessionmaker[AsyncSession], character_id: uuid.UUID
) -> tuple[int, dict[str, int | None]]:
    """Return (books_completed, {name: value_int or None}) for the three stats."""
    async with sessions() as session:
        character = await session.get(Character, character_id)
        assert character is not None
        values: dict[str, int | None] = {}
        for name in ("might", "wits", "nerve"):
            attribute = await session.get(CharacterAttribute, (character_id, name))
            values[name] = attribute.value_int if attribute is not None else None
        return character.books_completed, values


async def _completion_rows(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> list[CharacterBookCompletion]:
    """Return the character_book_completion rows for the seeded profile/book."""
    async with sessions() as session:
        result = await session.execute(
            select(CharacterBookCompletion).where(
                CharacterBookCompletion.reading_state_child_profile_id
                == seed.child_profile_id,
                CharacterBookCompletion.reading_state_storybook_id == seed.storybook_id,
            )
        )
        return list(result.scalars().all())


def _completion_body(seed: Seed, ending_id: str) -> dict[str, object]:
    return {
        "profile_id": str(seed.child_profile_id),
        "storybook_id": seed.storybook_id,
        "version": seed.version,
        "ending_id": ending_id,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_satisfying_ending_raises_a_stat_and_counts_the_book(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A satisfying ending raises the exit-state stat and increments books_completed."""
    await _seed_attributes(sessions, seed.character_id, might=0, wits=0, nerve=0)
    await _seed_reading_state(
        sessions, seed, var_state={"might": 1}, character_id=seed.character_id
    )

    resp = await client.post(
        "/api/v1/completions",
        json=_completion_body(seed, _SATISFYING_ENDING),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text

    books_completed, values = await _character_progress(sessions, seed.character_id)
    assert books_completed == 1
    assert values["might"] == 1
    # Stats absent from the exit var_state are untouched, not zeroed.
    assert values["wits"] == 0
    assert values["nerve"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_an_unsatisfying_ending_writes_nothing(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A non-satisfying ending (discovery) records the completion but grows nothing."""
    await _seed_attributes(sessions, seed.character_id, might=0, wits=0, nerve=0)
    await _seed_reading_state(
        sessions, seed, var_state={"might": 2}, character_id=seed.character_id
    )

    resp = await client.post(
        "/api/v1/completions",
        json=_completion_body(seed, _UNSATISFYING_ENDING),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text

    books_completed, values = await _character_progress(sessions, seed.character_id)
    assert books_completed == 0
    assert values["might"] == 0
    rows = await _completion_rows(sessions, seed)
    assert rows == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_replayed_completion_does_not_increment_twice(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The offline queue replays; the PK is what makes the second a no-op.

    Assert on books_completed after TWO calls, not on the second call's
    return value: a handler that returns early on its own bookkeeping would
    pass a return-value assertion while still double-incrementing under two
    concurrent workers.
    """
    await _seed_attributes(sessions, seed.character_id, might=0, wits=0, nerve=0)
    await _seed_reading_state(
        sessions, seed, var_state={"might": 2}, character_id=seed.character_id
    )
    body = _completion_body(seed, _SATISFYING_ENDING)

    first = await client.post(
        "/api/v1/completions", json=body, headers=auth(seed.child_token)
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        "/api/v1/completions", json=body, headers=auth(seed.child_token)
    )
    assert second.status_code == 200, second.text

    books_completed, values = await _character_progress(sessions, seed.character_id)
    assert books_completed == 1
    assert values["might"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_lower_exit_value_does_not_reduce_a_stat(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Monotone: a book the child coasted through cannot cost them might."""
    await _seed_attributes(sessions, seed.character_id, might=2, wits=0, nerve=0)
    await _seed_reading_state(
        sessions, seed, var_state={"might": 0}, character_id=seed.character_id
    )

    resp = await client.post(
        "/api/v1/completions",
        json=_completion_body(seed, _SATISFYING_ENDING),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text

    _, values = await _character_progress(sessions, seed.character_id)
    assert values["might"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_stat_cannot_exceed_the_canonical_maximum(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """LEAST(:canonical_max, ...) in-statement: a mis-declared book cannot
    write 5 (or 99) into a 0..2 vocabulary.
    """
    await _seed_attributes(sessions, seed.character_id, might=0, wits=0, nerve=0)
    await _seed_reading_state(
        sessions, seed, var_state={"might": 99}, character_id=seed.character_id
    )

    resp = await client.post(
        "/api/v1/completions",
        json=_completion_body(seed, _SATISFYING_ENDING),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text

    _, values = await _character_progress(sessions, seed.character_id)
    assert values["might"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_books_completed_increments_only_when_a_row_was_inserted(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The increment is conditional on the INSERT affecting a row.

    If it were unconditional, idempotency of the completion row (its
    primary key has no ``ending_id`` column, see db/models.py::
    CharacterBookCompletion) would coexist with a counter that climbed on
    every completion, including a SECOND, DIFFERENT ending for a book
    already credited. This test completes two distinct satisfying endings
    of the same book for the same character and asserts the counter still
    reads 1, not 2.
    """
    await _seed_attributes(sessions, seed.character_id, might=0, wits=0, nerve=0)
    await _seed_reading_state(
        sessions, seed, var_state={"might": 1}, character_id=seed.character_id
    )

    first = await client.post(
        "/api/v1/completions",
        json=_completion_body(seed, _SATISFYING_ENDING),
        headers=auth(seed.child_token),
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        "/api/v1/completions",
        json=_completion_body(seed, _SATISFYING_ENDING_2),
        headers=auth(seed.child_token),
    )
    assert second.status_code == 200, second.text

    books_completed, _ = await _character_progress(sessions, seed.character_id)
    assert books_completed == 1
    rows = await _completion_rows(sessions, seed)
    assert len(rows) == 1
    assert rows[0].ending_id == _SATISFYING_ENDING
