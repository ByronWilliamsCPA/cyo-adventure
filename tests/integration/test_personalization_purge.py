"""ADR-028: purging a profile's personalization must also purge character_name.

character_name (Task 3 of the persistent-characters plan) is the only
PERSONALIZATION_FIELDS member whose value lives outside
child_profile_personalization: it is synthesized at resolve time from the
profile's active Character row. A purge path that only ever deleted rows
from child_profile_personalization would report the slot purged while the
child's chosen character name stayed in the database, in the `character`
table, forever. This module tests the database half of that claim:
`purge_profile_personalization` (wired into `DELETE /profiles/{id}`, per
`api/profiles.py::delete_profile`) actually deletes from `character`, and the
`ck_cpp_value_cardinality` CHECK refuses a character_name row that carries a
value. The pure half, that the `PURGE_TARGETS` map names `character` as
character_name's purge target, needs no database and lives in
`tests/unit/test_personalization_purge_targets.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.api import profiles as profiles_module
from cyo_adventure.api.personalization import purge_profile_personalization
from cyo_adventure.db.models import Character, ChildProfile, ChildProfilePersonalization
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    import uuid

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_purging_character_name_clears_the_character_row(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """purge_profile_personalization deletes the profile's active Character row.

    The seed fixture already gives `seed.child_profile_id` an active
    character (`seed.character_id`, ADR-028's authz-matrix fixture). Calling
    the purge function directly, without deleting the profile itself, is
    the most targeted proof that the function's own DELETE statement is what
    removes the row, not the profile-row cascade this same function also
    happens to duplicate (see `api/profiles.py::delete_profile`'s docstring).
    """
    async with sessions() as s:
        character = await s.get(Character, seed.character_id)
        assert character is not None
        assert character.child_profile_id == seed.child_profile_id

    async with sessions() as s:
        await purge_profile_personalization(s, seed.child_profile_id)
        await s.commit()

    async with sessions() as s:
        remaining = await s.scalar(
            select(Character).where(Character.child_profile_id == seed.child_profile_id)
        )
        assert remaining is None
        # The profile row itself is untouched: this function purges values,
        # not the profile.
        assert (await s.get(ChildProfile, seed.child_profile_id)) is not None


async def test_purging_clears_personalization_rows_alongside_the_character(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The same call also clears ordinary child_profile_personalization rows.

    Guards against a fix that solved the character_name gap by adding a
    second, separate delete call somewhere else and leaving this function's
    original personalization-row purge behind unexercised by any test.
    """
    async with sessions() as s:
        s.add(
            ChildProfilePersonalization(
                child_profile_id=seed.child_profile_id,
                slot_type="pet_name",
                value_text="Whiskers",
                ring1_enabled=True,
            )
        )
        await s.commit()

    async with sessions() as s:
        await purge_profile_personalization(s, seed.child_profile_id)
        await s.commit()

    async with sessions() as s:
        remaining = await s.scalar(
            select(ChildProfilePersonalization).where(
                ChildProfilePersonalization.child_profile_id == seed.child_profile_id
            )
        )
        assert remaining is None


async def test_delete_profile_route_calls_the_purge_and_leaves_no_character_rows(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: DELETE /profiles/{id} calls the purge and leaves zero rows.

    The zero-rows assertion alone does not prove the route calls anything:
    `character.child_profile_id` carries an ON DELETE CASCADE FK, so deleting
    the profile empties the table whether or not
    `purge_profile_personalization` was ever invoked. Removing the call from
    `delete_profile` would leave a rows-only test green while the explicit
    purge, which is the ADR-028 requirement and the thing that also runs on
    purge-without-delete paths, had silently disappeared.

    So this spies on the call itself and delegates to the real function, then
    still asserts the observable end state.
    """
    calls: list[uuid.UUID] = []
    real = profiles_module.purge_profile_personalization

    async def _spy(session: AsyncSession, profile_id: uuid.UUID) -> None:
        calls.append(profile_id)
        await real(session, profile_id)

    monkeypatch.setattr(profiles_module, "purge_profile_personalization", _spy)

    resp = await client.delete(
        f"/api/v1/profiles/{seed.child_profile_id}",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 204, resp.text
    assert calls == [seed.child_profile_id], (
        "DELETE /profiles/{id} must call purge_profile_personalization for the "
        "profile being deleted; the ON DELETE CASCADE FK is not a substitute"
    )

    async with sessions() as s:
        remaining = await s.scalar(
            select(Character).where(Character.child_profile_id == seed.child_profile_id)
        )
        assert remaining is None


async def test_character_name_row_carrying_a_value_is_rejected_by_the_database(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """`ck_cpp_value_cardinality` refuses a character_name row with a value.

    #CRITICAL: data integrity: character_name's value is synthesized at
    resolve time from the profile's active character, so its consent row must
    carry the toggles and nothing else. The Pydantic body validator rejects
    this shape at the edge and `_shape_violations` rejects it in the pure
    validator, but neither covers a writer that bypasses the API: a
    migration, a script, or a future route. The renamed, slot-scoped CHECK is
    the last line, and until this test existed nothing exercised its
    character_name branch against real Postgres.
    """
    for column, value in (
        ("value_text", "Zephyr"),
        ("value_enum", "Zephyr"),
    ):
        async with sessions() as s:
            s.add(
                ChildProfilePersonalization(
                    child_profile_id=seed.child_profile_id,
                    slot_type="character_name",
                    ring1_enabled=True,
                    **{column: value},
                )
            )
            with pytest.raises(IntegrityError, match="ck_cpp_value_cardinality"):
                await s.flush()


async def test_ordinary_slot_row_value_cardinality_is_still_enforced(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The CHECK's ELSE branch still demands exactly one value for the rest.

    The constraint became a slot-scoped CASE when character_name was added.
    Carving out one slot is exactly the edit that can accidentally relax the
    rule for the other eleven, and a test that only exercises the new branch
    would not notice.
    """
    async with sessions() as s:
        s.add(
            ChildProfilePersonalization(
                child_profile_id=seed.child_profile_id,
                slot_type="pet_name",
                value_text="Whiskers",
                value_enum="dog",
                ring1_enabled=True,
            )
        )
        with pytest.raises(IntegrityError, match="ck_cpp_value_cardinality"):
            await s.flush()

    async with sessions() as s:
        s.add(
            ChildProfilePersonalization(
                child_profile_id=seed.child_profile_id,
                slot_type="pet_name",
                ring1_enabled=True,
            )
        )
        with pytest.raises(IntegrityError, match="ck_cpp_value_cardinality"):
            await s.flush()
