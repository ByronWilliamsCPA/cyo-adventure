"""Integration tests for server-derived character binding (ADR-028, Task 6).

The binding rule, verbatim from the spec: the server resolves the character
with ``SELECT id FROM character WHERE child_profile_id = <authenticated
profile> AND is_active``. The client never supplies it. These tests exercise
that rule end to end: binding happens once, at read start, and the recorded
seed is never recomputed on a later save.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    CharacterAttribute,
    ChildProfile,
    ReadingState,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
    User,
)
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_SEEDED_STORY_ID = "s_char_seed_binding_test"
_SEEDED_STORY_VERSION = 1


def _meta() -> dict[str, object]:
    """Minimal valid metadata block for a synthetic test story."""
    return {
        "age_band": "10-13",
        "reading_level": {"scheme": "flesch_kincaid", "target": 4.0, "tolerance": 1.0},
        "tier": 2,
        "themes": [],
        "estimated_minutes": 5,
        "ending_count": 1,
        "topology": "branch_and_bottleneck",
        "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
    }


def _seeded_story_blob() -> dict[str, object]:
    """A two-node story declaring `might` int 0..2, initial 0, one choice.

    Mirrors tests/unit/test_replay.py::_seeded_story_blob exactly: `might`
    is a real character-attribute name (see db/models.py
    _CHARACTER_ATTRIBUTE_NAMES), so a character seeded with a `might` value
    actually moves this story's replayed var_state, unlike the shared
    `seed`'s lantern fixture (which declares no character-attribute-named
    variable at all).
    """
    return {
        "schema_version": "2.0",
        "id": _SEEDED_STORY_ID,
        "version": _SEEDED_STORY_VERSION,
        "title": "Seed Binding Test",
        "metadata": _meta(),
        "variables": [
            {"name": "might", "type": "int", "initial": 0, "min": 0, "max": 2}
        ],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": "Start here.",
                "on_enter": [],
                "choices": [
                    {
                        "id": "c_press_on",
                        "label": "Press on",
                        "target": "n_end",
                        "effects": [],
                    }
                ],
            },
            {
                "id": "n_end",
                "body": "Done.",
                "is_ending": True,
                "ending": {
                    "id": "e_end",
                    "valence": "positive",
                    "kind": "success",
                    "title": "End",
                },
                "choices": [],
            },
        ],
    }


async def _seed_attributes(
    sessions: async_sessionmaker[AsyncSession],
    character_id: uuid.UUID,
    *,
    might: int,
    wits: int,
    nerve: int,
) -> None:
    """Insert character_attribute rows directly (no PATCH route sets them).

    Attributes are server-derived and no character route accepts them in a
    request body (schemas.py::CharacterUpdateBody's docstring), so a test
    that needs a non-zero attribute must write the rows itself.
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


async def _seed_binding_story(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Insert the `might`-declaring story, published and assigned to seed's child."""
    async with sessions() as session:
        session.add(
            Storybook(
                id=_SEEDED_STORY_ID,
                family_id=seed.family_id,
                current_published_version=_SEEDED_STORY_VERSION,
                status="published",
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=_SEEDED_STORY_ID,
                version=_SEEDED_STORY_VERSION,
                blob=_seeded_story_blob(),
                approved_by=seed.admin_user_id,
                published_at=datetime.now(UTC),
            )
        )
        session.add(
            StorybookAssignment(
                child_profile_id=seed.child_profile_id,
                storybook_id=_SEEDED_STORY_ID,
            )
        )
        await session.commit()


async def _new_child_without_character(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> tuple[str, uuid.UUID]:
    """Create a sibling profile with no character at all, assigned seed's book.

    Distinct from ``seed.child_profile_id`` (which owns an always-active
    fixture character): case 2 needs a profile that genuinely has none, so
    the binding query returns no row rather than an inactive one.
    """
    token = f"child-no-character-{uuid.uuid4()}"
    async with sessions() as session:
        profile = ChildProfile(
            family_id=seed.family_id,
            display_name="Reader Without A Character",
            age_band="10-13",
        )
        session.add(profile)
        await session.flush()
        profile_id = profile.id
        session.add(
            User(
                family_id=seed.family_id,
                role="child",
                authn_subject=token,
                child_profile_id=profile_id,
            )
        )
        session.add(
            StorybookAssignment(
                child_profile_id=profile_id,
                storybook_id=seed.storybook_id,
            )
        )
        await session.commit()
    return token, profile_id


def _save_body(
    version: int, *, node: str, revision: int, **extra: object
) -> dict[str, object]:
    """Build a reading-state PUT body against the shared lantern story."""
    return {
        "version": version,
        "current_node": node,
        "var_state": {"has_lantern": True},
        "path": ["n_entrance", node],
        "visit_set": ["n_entrance", node],
        "save_slots": {},
        "state_revision": revision,
        **extra,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_starting_a_read_binds_the_active_character_and_seeds_its_state(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Case 1: a first save for a profile with an active character persists
    that character's id and the seed derived from its attributes.
    """
    await _seed_attributes(sessions, seed.character_id, might=2, wits=1, nerve=0)

    resp = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}",
        json=_save_body(seed.version, node="n_entrance", revision=0),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["character_id"] == str(seed.character_id)
    assert body["character_name"] == "Route Matrix Rowan"
    assert body["seed_var_state"] == {"might": 2, "wits": 1, "nerve": 0}

    async with sessions() as session:
        row = await session.get(
            ReadingState, (seed.child_profile_id, seed.storybook_id)
        )
        assert row is not None
        assert row.character_id == seed.character_id
        assert row.seed_var_state == {"might": 2, "wits": 1, "nerve": 0}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_starting_a_read_with_no_active_character_is_unseeded(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Case 2: a profile with no active character persists NULL for both.

    An unseeded read is the normal case, not an error.
    """
    token, profile_id = await _new_child_without_character(sessions, seed)

    resp = await client.put(
        f"/api/v1/reading-state/{profile_id}/{seed.storybook_id}",
        json=_save_body(seed.version, node="n_entrance", revision=0),
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["character_id"] is None
    assert body["character_name"] is None
    assert body["seed_var_state"] is None

    async with sessions() as session:
        row = await session.get(ReadingState, (profile_id, seed.storybook_id))
        assert row is not None
        assert row.character_id is None
        assert row.seed_var_state is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_client_supplied_character_id_is_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """Case 3 (security-relevant): a PUT body carrying character_id is a 422.

    ReadingStateBody is extra="forbid"; if a client could name the
    character, it could name another profile's, and because the seed
    becomes the replay baseline, seeding would become an arbitrary-
    variable-write primitive that replay validation would then bless.
    """
    resp = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}",
        json=_save_body(
            seed.version,
            node="n_entrance",
            revision=0,
            character_id=str(seed.character_id),
        ),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_saving_a_state_reached_from_the_seed_validates(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Case 4a: a state reached by replaying from the recorded seed saves."""
    await _seed_binding_story(sessions, seed)
    await _seed_attributes(sessions, seed.character_id, might=2, wits=0, nerve=0)

    start = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{_SEEDED_STORY_ID}",
        json={
            "version": _SEEDED_STORY_VERSION,
            "current_node": "n_start",
            "var_state": {"might": 2},
            "path": ["n_start"],
            "visit_set": ["n_start"],
            "save_slots": {},
            "state_revision": 0,
        },
        headers=auth(seed.child_token),
    )
    assert start.status_code == 200, start.text
    assert start.json()["seed_var_state"] == {"might": 2, "wits": 0, "nerve": 0}

    resp = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{_SEEDED_STORY_ID}",
        json={
            "version": _SEEDED_STORY_VERSION,
            "current_node": "n_end",
            "var_state": {"might": 2},
            "path": ["n_start", "n_end"],
            "visit_set": ["n_start", "n_end"],
            "save_slots": {},
            "state_revision": 1,
            "choice_path": ["c_press_on"],
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_saving_a_state_only_reachable_from_a_different_seed_is_rejected(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Case 4b: a state only reachable from a different seed is rejected.

    The recorded seed is might=2; a save claiming the declared-initial
    (unseeded) value of might=0 was never reachable from this read and must
    fail replay, not be accepted as if it started fresh.
    """
    await _seed_binding_story(sessions, seed)
    await _seed_attributes(sessions, seed.character_id, might=2, wits=0, nerve=0)

    start = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{_SEEDED_STORY_ID}",
        json={
            "version": _SEEDED_STORY_VERSION,
            "current_node": "n_start",
            "var_state": {"might": 2},
            "path": ["n_start"],
            "visit_set": ["n_start"],
            "save_slots": {},
            "state_revision": 0,
        },
        headers=auth(seed.child_token),
    )
    assert start.status_code == 200, start.text

    resp = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{_SEEDED_STORY_ID}",
        json={
            "version": _SEEDED_STORY_VERSION,
            "current_node": "n_end",
            "var_state": {"might": 0},
            "path": ["n_start", "n_end"],
            "visit_set": ["n_start", "n_end"],
            "save_slots": {},
            "state_revision": 1,
            "choice_path": ["c_press_on"],
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_read_in_progress_keeps_its_recorded_seed(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Case 5: retiring the character mid-book does not move the baseline.

    "Recompute the seed on every save" is the natural implementation and it
    silently rewrites history mid-book: a retirement would move the
    baseline a read in progress is validated against, and reject a save the
    child legitimately holds. This test would FAIL if the save path
    recomputed the seed from the (now inactive) character's current
    attributes instead of reading the stored snapshot: after retirement the
    active-character query returns no row, so a recomputing implementation
    would replay from an unseeded (might=0) baseline and reject the
    might=2 state below as tampered.
    """
    await _seed_binding_story(sessions, seed)
    await _seed_attributes(sessions, seed.character_id, might=2, wits=0, nerve=0)

    start = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{_SEEDED_STORY_ID}",
        json={
            "version": _SEEDED_STORY_VERSION,
            "current_node": "n_start",
            "var_state": {"might": 2},
            "path": ["n_start"],
            "visit_set": ["n_start"],
            "save_slots": {},
            "state_revision": 0,
        },
        headers=auth(seed.child_token),
    )
    assert start.status_code == 200, start.text

    retire = await client.post(
        f"/api/v1/characters/{seed.character_id}/retire",
        headers=auth(seed.child_token),
    )
    assert retire.status_code == 200, retire.text
    assert retire.json()["is_active"] is False

    resp = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{_SEEDED_STORY_ID}",
        json={
            "version": _SEEDED_STORY_VERSION,
            "current_node": "n_end",
            "var_state": {"might": 2},
            "path": ["n_start", "n_end"],
            "visit_set": ["n_start", "n_end"],
            "save_slots": {},
            "state_revision": 1,
            "choice_path": ["c_press_on"],
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["character_id"] == str(seed.character_id)
    assert body["seed_var_state"] == {"might": 2, "wits": 0, "nerve": 0}
