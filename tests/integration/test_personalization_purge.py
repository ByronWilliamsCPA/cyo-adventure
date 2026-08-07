"""ADR-028: purging a profile's personalization must also purge character_name.

character_name (Task 3 of the persistent-characters plan) is the only
PERSONALIZATION_FIELDS member whose value lives outside
child_profile_personalization: it is synthesized at resolve time from the
profile's active Character row. A purge path that only ever deleted rows
from child_profile_personalization would report the slot purged while the
child's chosen character name stayed in the database, in the `character`
table, forever. This module tests both halves of that claim: the explicit
`PURGE_TARGETS` map names `character` as character_name's purge target, and
`purge_profile_personalization` (wired into `DELETE /profiles/{id}`, per
`api/profiles.py::delete_profile`) actually deletes from it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.api.personalization import (
    PURGE_TARGETS,
    purge_profile_personalization,
)
from cyo_adventure.db.models import Character, ChildProfile, ChildProfilePersonalization
from cyo_adventure.storybook.theme_contract import PERSONALIZATION_FIELDS
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_purge_targets_is_exhaustive_over_personalization_fields() -> None:
    """PURGE_TARGETS names every PERSONALIZATION_FIELDS member, and nothing else.

    Both directions matter. A field missing from PURGE_TARGETS is a slot the
    purge path has no story for at all; a stray extra key is a purge target
    for a slot type that no longer exists, which is exactly the kind of
    drift AL-068/UW-C20 found in the neighboring CLOSED_VOCABULARIES map (see
    tests/unit/test_personalization_vocab_drift.py). Asserting set equality
    covers both without hardcoding either list a second time here.
    """
    assert set(PURGE_TARGETS) == set(PERSONALIZATION_FIELDS), (
        "PURGE_TARGETS and PERSONALIZATION_FIELDS have drifted apart; a slot "
        "type must appear in both or neither, or the next slot added to "
        "PERSONALIZATION_FIELDS silently has no decided purge target"
    )


async def test_purge_targets_names_character_for_character_name_only() -> None:
    """character_name is the one PURGE_TARGETS entry naming `character`.

    Every other entry names `personalization_row`: pinning that split
    directly (rather than only via the exhaustiveness test above) makes a
    future edit that widened `character`'s purge target to a second slot,
    or narrowed character_name's away from it, fail here with a message
    naming the exact slot, instead of only failing the vaguer set-equality
    assertion.
    """
    character_targets = {
        slot_type
        for slot_type, target in PURGE_TARGETS.items()
        if target == "character"
    }
    assert character_targets == {"character_name"}


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


async def test_delete_profile_route_leaves_zero_character_rows(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """End to end: DELETE /profiles/{id} leaves zero character rows behind.

    `test_purging_character_name_clears_the_character_row` above proves the
    purge function's own DELETE statement works in isolation; this proves
    the route actually calls it (or, redundantly and just as correctly,
    that the ON DELETE CASCADE FK does the same job), matching the exact
    wording of the purge-path requirement: purging a profile's
    personalization leaves zero `character` rows for that profile.
    """
    resp = await client.delete(
        f"/api/v1/profiles/{seed.child_profile_id}",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 204, resp.text

    async with sessions() as s:
        remaining = await s.scalar(
            select(Character).where(Character.child_profile_id == seed.child_profile_id)
        )
        assert remaining is None
