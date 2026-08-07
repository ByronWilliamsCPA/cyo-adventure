"""Integration tests for the character CRUD endpoints (ADR-028).

Attributes and books_completed are absent from every request model by
design (server-derived; extra=forbid). A run through this module without
Docker reachable is skipped, not passed, per the `_pg_url` fixture's own
CI-loud-failure guarantee.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.api import characters as characters_module
from cyo_adventure.api.deps import Principal, RequestContext, Role
from cyo_adventure.core.exceptions import StateTransitionError
from cyo_adventure.db.models import Character, ChildProfile
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    import uuid

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _create_body(profile_id: str, *, name: str = "Ember") -> dict[str, str]:
    """Build a minimal, valid character-creation request body."""
    return {
        "profile_id": profile_id,
        "name": name,
        "archetype": "scout",
        "look": "avatar_02",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_creates_character_for_own_family_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian creates a character for a profile in their family: 201."""
    resp = await client.post(
        "/api/v1/characters",
        json=_create_body(str(seed.child_profile_id)),
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["books_completed"] == 0
    assert body["attributes"]["might"] == 0
    assert body["attributes"]["wits"] == 0
    assert body["attributes"]["nerve"] == 0
    assert body["is_active"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kid_creates_character_for_own_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """A kid principal creates a character for their own profile: 201."""
    resp = await client.post(
        "/api/v1/characters",
        json=_create_body(str(seed.child_profile_id)),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kid_cannot_create_character_for_sibling_profile(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A kid principal creating for a genuine sibling profile: 403.

    Builds a second child profile inside family A, the caller's own family:
    a real sibling. This is a test-local row, not part of the shared
    ``seed`` fixture, because ``seed`` is reused across the whole
    integration suite and other tests (e.g. test_profiles.py,
    test_families_api.py) hardcode family A's profile count and roster; a
    sibling baked into the shared seed silently breaks those unrelated
    assertions. This is distinct from the cross-family case covered by
    ``test_guardian_cannot_create_character_for_another_familys_profile``
    and the authz matrix's cross-family sweeps, which use
    ``other_child_profile_id`` (family B).
    """
    async with sessions() as setup_session:
        sibling = ChildProfile(
            family_id=seed.family_id,
            display_name="Reader A's Sibling",
            age_band="10-13",
        )
        setup_session.add(sibling)
        await setup_session.flush()
        sibling_id: uuid.UUID = sibling.id
        await setup_session.commit()

    resp = await client.post(
        "/api/v1/characters",
        json=_create_body(str(sibling_id)),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_cannot_create_character_for_another_familys_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian creating for another family's profile: 403."""
    resp = await client.post(
        "/api/v1/characters",
        json=_create_body(str(seed.other_child_profile_id)),
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_with_books_completed_is_rejected_not_silently_dropped(
    client: AsyncClient, seed: Seed
) -> None:
    """PATCH with books_completed set: 422, never a silent drop.

    books_completed is server-derived and absent from CharacterUpdateBody;
    extra=forbid turns the attempt into a 422 rather than accepting the
    request and ignoring the field.
    """
    resp = await client.patch(
        f"/api/v1/characters/{seed.character_id}",
        json={"books_completed": 5},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_with_attributes_is_rejected_not_silently_dropped(
    client: AsyncClient, seed: Seed
) -> None:
    """PATCH with an attributes dict set: 422, for the same reason.

    Attributes are earned through gameplay/progression writeback, never
    written directly by a guardian or kid through this endpoint.
    """
    resp = await client.patch(
        f"/api/v1/characters/{seed.character_id}",
        json={"attributes": {"might": 2}},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_creating_a_second_character_retires_the_incumbent_atomically(
    client: AsyncClient, seed: Seed
) -> None:
    """Creating a second character while one is active retires the first.

    Both facts -- the new character active, the old one retired with a
    retired_at -- must hold in the same response cycle: the retire and the
    create/activate share one transaction (see api/characters.py's
    _retire_active_character docstring).
    """
    second = await client.post(
        "/api/v1/characters",
        json=_create_body(str(seed.child_profile_id), name="Second Character"),
        headers=auth(seed.guardian_token),
    )
    assert second.status_code == 201, second.text
    second_body = second.json()
    assert second_body["is_active"] is True

    listing = await client.get(
        "/api/v1/characters",
        params={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    assert listing.status_code == 200, listing.text
    characters = listing.json()["characters"]
    incumbent = next(c for c in characters if c["id"] == str(seed.character_id))
    newcomer = next(c for c in characters if c["id"] == second_body["id"])
    assert incumbent["is_active"] is False
    assert incumbent["retired_at"] is not None
    assert newcomer["is_active"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_activating_a_replacement_retires_the_incumbent_atomically(
    client: AsyncClient, seed: Seed
) -> None:
    """POST .../activate on a retired character retires whichever is active.

    Mirrors the create-time atomic retire, but through the explicit
    activate endpoint.
    """
    second = await client.post(
        "/api/v1/characters",
        json=_create_body(str(seed.child_profile_id), name="Second Character"),
        headers=auth(seed.guardian_token),
    )
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]

    # seed.character_id was retired by the create above; re-activate it.
    reactivate = await client.post(
        f"/api/v1/characters/{seed.character_id}/activate",
        headers=auth(seed.guardian_token),
    )
    assert reactivate.status_code == 200, reactivate.text
    assert reactivate.json()["is_active"] is True

    listing = await client.get(
        "/api/v1/characters",
        params={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    characters = listing.json()["characters"]
    original = next(c for c in characters if c["id"] == str(seed.character_id))
    other = next(c for c in characters if c["id"] == second_id)
    assert original["is_active"] is True
    assert other["is_active"] is False
    assert other["retired_at"] is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kid_cannot_delete_character(client: AsyncClient, seed: Seed) -> None:
    """A kid attempting DELETE: 403."""
    resp = await client.delete(
        f"/api/v1/characters/{seed.character_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_can_delete_character(client: AsyncClient, seed: Seed) -> None:
    """A guardian deleting a character in their family: 204."""
    resp = await client.delete(
        f"/api/v1/characters/{seed.character_id}",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 204, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_family_guardian_cannot_delete_character(
    client: AsyncClient, seed: Seed
) -> None:
    """A family-B guardian deleting family A's character: 403/404, never 204.

    DELETE is role-gated to GUARDIAN only, so it is absent from
    ``_CROSS_FAMILY_ROUTE_KEYS`` in ``test_authz_matrix.py``: that sweep
    resolves DELETE's ``RouteSpec`` via ``_random_uuid_path``, which would
    404 unconditionally regardless of the ownership check, proving nothing
    about IDOR safety. This test exercises the real character id
    (``seed.character_id``) against a real, disallowed guardian
    (``seed.other_guardian_token``) instead, so a 403/404 here can only come
    from the endpoint's own ownership check.
    """
    resp = await client.delete(
        f"/api/v1/characters/{seed.character_id}",
        headers=auth(seed.other_guardian_token),
    )
    assert resp.status_code in (403, 404), resp.text
    assert not (200 <= resp.status_code < 300), resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retiring_the_only_active_character_leaves_none_active(
    client: AsyncClient, seed: Seed
) -> None:
    """Retiring the only active character leaves zero active, no error."""
    resp = await client.post(
        f"/api/v1/characters/{seed.character_id}/retire",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    listing = await client.get(
        "/api/v1/characters",
        params={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    assert listing.status_code == 200, listing.text
    characters = listing.json()["characters"]
    assert all(not c["is_active"] for c in characters)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_activations_collide_into_a_409_not_a_500(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Two genuinely concurrent activations for one profile: 409, never a 500.

    Bypasses HTTP to control transaction overlap directly (the codebase's
    only prior "race" test, test_provider_allowlist_api.py::
    test_add_duplicate_pair_is_409, is actually two sequential requests, and
    sequential activate calls here never collide: each correctly
    retire-then-activates). Two independent sessions each activate a
    different character on seed.child_profile_id, sequenced so both retire
    checks run before either commits: both see zero active incumbents (each
    transaction's write is invisible to the other under READ COMMITTED)
    and both proceed to mark their own row active. Postgres then serializes
    the second flush behind the first's uncommitted uq_character_one_active
    entry and rejects it with an IntegrityError once the first commits; the
    handler (api/characters.py::activate_character) must catch that and
    raise StateTransitionError, never let it surface as an unhandled 500.
    """
    async with sessions() as setup_session:
        # Both characters are constructed already retired: is_active
        # defaults to True on the Character model, and seed.character_id is
        # already active, so a "second" row built with the default would
        # collide with it immediately at this setup flush, before either
        # concurrent activation below ever runs.
        second = Character(
            child_profile_id=seed.child_profile_id,
            family_id=seed.family_id,
            name="Second Character",
            archetype="scout",
            look="avatar_02",
            is_active=False,
            retired_at=datetime.now(UTC),
        )
        setup_session.add(second)
        first_row = await setup_session.get(Character, seed.character_id)
        assert first_row is not None
        # Retire the incumbent too: the profile starts with zero active
        # characters, so both concurrent activations below see "no
        # incumbent" and race to become the sole active one.
        first_row.is_active = False
        first_row.retired_at = datetime.now(UTC)
        await setup_session.flush()
        second_id: uuid.UUID = second.id
        await setup_session.commit()

    principal = Principal(
        subject="guardian-a-concurrency-test",
        user_id=seed.admin_user_id,
        role=Role.GUARDIAN,
        family_id=seed.family_id,
        profile_ids=frozenset({seed.child_profile_id}),
    )

    session_a = sessions()
    session_b = sessions()
    try:
        ctx_a = RequestContext(principal=principal, session=session_a)
        ctx_b = RequestContext(principal=principal, session=session_b)

        a_flushed = asyncio.Event()
        release_a = asyncio.Event()

        async def _activate_a() -> object:
            view = await characters_module.activate_character(
                str(seed.character_id), ctx_a
            )
            a_flushed.set()
            await release_a.wait()
            await session_a.commit()
            return view

        async def _activate_b() -> object:
            await a_flushed.wait()
            return await characters_module.activate_character(str(second_id), ctx_b)

        async def _release_after_delay() -> None:
            # #CRITICAL: timing: session_b's flush blocks at the real
            # Postgres level (MVCC waiting on session_a's uncommitted unique
            # index entry), not on a Python-level lock, so this sleep only
            # needs to outlast the time for session_b to reach that wait; the
            # collision itself is serialized by Postgres, not by this delay.
            # #VERIFY: a flaky failure here (session_b returning 200 instead
            # of raising) would mean 0.2s was too short on a slow CI runner;
            # widen the sleep rather than removing the synchronization.
            await asyncio.sleep(0.2)
            release_a.set()

        results = await asyncio.gather(
            _activate_a(),
            _activate_b(),
            _release_after_delay(),
            return_exceptions=True,
        )
    finally:
        await session_a.close()
        await session_b.close()

    a_result, b_result, _release_result = results
    assert not isinstance(a_result, BaseException), a_result
    assert isinstance(b_result, StateTransitionError), (
        "expected the losing concurrent activation to raise "
        f"StateTransitionError, got {b_result!r}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_character_rejects_a_sentinel_shaped_name(
    client: AsyncClient, seed: Seed
) -> None:
    """A sentinel-shaped character name is refused at set time: 422.

    A character's name resolves into the `character_name` personalization
    slot, and the resolved payload ships it to the reader beside
    `sentinel_pattern` for substitution into story prose. A name carrying the
    sentinel's own braces is a template-forgery vector, so it must never
    reach the database, let alone a rendered story.
    """
    resp = await client.post(
        "/api/v1/characters",
        json=_create_body(str(seed.child_profile_id), name="{~HERO:friend~}"),
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_character_rejects_a_control_character_in_the_name(
    client: AsyncClient, seed: Seed
) -> None:
    """A name carrying a control character is refused at set time: 422."""
    resp = await client.post(
        "/api/v1/characters",
        json=_create_body(str(seed.child_profile_id), name="Ro\x07sa"),
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_character_rejects_a_band_denylisted_name(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A name matching the profile's band-mandatory denylist: 422.

    The denylist floor is band-scoped, so this needs a profile in a band that
    actually mandates the `weapon` bundle. The shared ``seed`` profiles are
    all 10-13, where it is not mandatory, so this builds a test-local 5-8
    profile in family A rather than changing the shared seed (other modules
    hardcode family A's profile roster).
    """
    async with sessions() as setup_session:
        young = ChildProfile(
            family_id=seed.family_id,
            display_name="Reader A's Younger Sibling",
            age_band="5-8",
        )
        setup_session.add(young)
        await setup_session.flush()
        young_id: uuid.UUID = young.id
        await setup_session.commit()

    resp = await client.post(
        "/api/v1/characters",
        json=_create_body(str(young_id), name="Captain Sword"),
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rename_character_rejects_a_sentinel_shaped_name(
    client: AsyncClient, seed: Seed
) -> None:
    """The rename path is gated too, not only creation: 422.

    A gate on POST alone would be bypassed by creating a clean character and
    then renaming it, which is the same free-text channel one request later.
    """
    resp = await client.patch(
        f"/api/v1/characters/{seed.character_id}",
        json={"name": "{~HERO:friend~}"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text
