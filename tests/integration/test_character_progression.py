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

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import (
    Character,
    CharacterAttribute,
    CharacterBookCompletion,
    ReadingState,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from cyo_adventure.storybook.character_vocabulary import ARCHETYPE_VARIABLE_NAME
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
    archetype: int | None = None,
) -> None:
    """Insert character_attribute rows directly.

    Mirrors tests/integration/test_reading_character_binding.py::
    _seed_attributes exactly: attributes are server-derived and no character
    route accepts them in a request body, so a test that needs a non-zero
    (or non-default) attribute must write the rows itself.

    ``archetype`` defaults to None (no row written) because the integration
    ``seed`` fixture inserts its Character straight through the ORM, never
    through ``api/characters.py::create_character``, so no ``initial_attributes``
    run and the character genuinely has no archetype row. Only the archetype
    exclusion test needs one.
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
        if archetype is not None:
            session.add(
                CharacterAttribute(
                    character_id=character_id,
                    name=ARCHETYPE_VARIABLE_NAME,
                    value_int=archetype,
                )
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


_THREE_ENDINGS = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "02_tier1_three_endings.json"
)
# The lantern story the `seed` fixture publishes declares no ending harsher
# than `discovery`, so the "death or setback grants nothing" half of the spec
# needs a second book. This one is an EXISTING fixture, not authored for this
# test: `e_fire_escape` is kind `setback`.
_SETBACK_ENDING = "e_fire_escape"


async def _publish_second_book(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> tuple[str, int]:
    """Publish and assign the three-endings fixture to the seeded profile.

    Mirrors the `seed` fixture's own publish block (Storybook +
    StorybookVersion + StorybookAssignment), which is what
    `record_completion`'s readable/assigned/current-published-approved gate
    requires.

    Returns:
        tuple[str, int]: The second book's (storybook_id, version).
    """
    blob = json.loads(_THREE_ENDINGS.read_text(encoding="utf-8"))
    story_id = str(blob["id"])
    version = int(blob["version"])
    async with sessions() as session:
        session.add(
            Storybook(
                id=story_id,
                family_id=seed.family_id,
                current_published_version=version,
                status="published",
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=version,
                blob=blob,
                approved_by=seed.admin_user_id,
                published_at=datetime.now(UTC),
            )
        )
        session.add(
            StorybookAssignment(
                child_profile_id=seed.child_profile_id, storybook_id=story_id
            )
        )
        await session.commit()
    return story_id, version


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_satisfying_ending_raises_a_stat_and_counts_the_book(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A satisfying ending raises the exit-state stat and increments books_completed.

    wits and nerve are seeded at 1, not 0, deliberately: they are absent from
    the exit var_state, and at 0 the assertion below could not tell "left
    alone" apart from "zeroed by the writeback".
    """
    await _seed_attributes(sessions, seed.character_id, might=0, wits=1, nerve=1)
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
    assert values["wits"] == 1
    assert values["nerve"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_an_unsatisfying_ending_writes_nothing(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A non-satisfying ending records the completion but grows nothing.

    Covers both ends of the non-satisfying range the spec names ("nothing is
    granted on death or setback"), not just the mildest one: `xe_term` in the
    lantern book is `discovery` (neutral), and `e_fire_escape` in the
    three-endings book is `setback`. Only `discovery` is reachable in the
    story the `seed` fixture publishes, so the second half publishes an
    existing second fixture rather than reading the harsher case as covered
    by the neutral one.
    """
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

    setback_book, setback_version = await _publish_second_book(sessions, seed)
    async with sessions() as session:
        session.add(
            ReadingState(
                child_profile_id=seed.child_profile_id,
                storybook_id=setback_book,
                version=setback_version,
                current_node="n_fire",
                var_state={"might": 2},
                path=["n_fire"],
                visit_set=["n_fire"],
                save_slots={},
                state_revision=0,
                character_id=seed.character_id,
                seed_var_state=None,
            )
        )
        await session.commit()

    setback = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": setback_book,
            "version": setback_version,
            "ending_id": _SETBACK_ENDING,
        },
        headers=auth(seed.child_token),
    )
    assert setback.status_code == 200, setback.text

    books_completed, values = await _character_progress(sessions, seed.character_id)
    assert books_completed == 0
    assert values["might"] == 0


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
    """A mis-declared book cannot leave a 0..2 stat holding 99.

    What this isolates is the outcome, not the line that produced it: the
    stat lands at the canonical maximum and the request still succeeds. It
    cannot attribute that to ``LEAST``. Under a GREATEST-only implementation
    it fails for a different reason, the database CHECK
    ``ck_character_attribute_value_range`` rejects 99 and the POST 500s, so
    the CHECK is defense in depth behind the clamp rather than a second
    thing this test distinguishes.
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_archetype_is_never_raised_by_a_completion(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """archetype is identity, not progression, so the writeback must skip it.

    This is the only test that pins ``progression.py``'s explicit
    ``_PROGRESSION_VARIABLES`` filter. It needs BOTH halves to discriminate:
    an ``archetype`` row must exist for the character (the ``seed`` fixture
    inserts its Character through the ORM, so no ``initial_attributes`` ever
    ran and no such row exists by default), AND the exit var_state must carry
    ``archetype`` at a value above the seeded one. Without both, deleting the
    filter changes nothing, because the UPDATE would simply match zero rows.
    """
    await _seed_attributes(
        sessions, seed.character_id, might=0, wits=0, nerve=0, archetype=2
    )
    await _seed_reading_state(
        sessions,
        seed,
        var_state={"might": 1, ARCHETYPE_VARIABLE_NAME: 5},
        character_id=seed.character_id,
    )

    resp = await client.post(
        "/api/v1/completions",
        json=_completion_body(seed, _SATISFYING_ENDING),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text

    async with sessions() as session:
        archetype = await session.get(
            CharacterAttribute, (seed.character_id, ARCHETYPE_VARIABLE_NAME)
        )
        assert archetype is not None
        assert archetype.value_int == 2

    # The writeback did run; archetype was skipped, not the whole loop.
    _, values = await _character_progress(sessions, seed.character_id)
    assert values["might"] == 1
