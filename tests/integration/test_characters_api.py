"""Integration tests for the character CRUD endpoints (ADR-028).

Attributes and books_completed are absent from every request model by
design (server-derived; extra=forbid). A run through this module without
Docker reachable is skipped, not passed, per the `_pg_url` fixture's own
CI-loud-failure guarantee.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient


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
    client: AsyncClient, seed: Seed
) -> None:
    """A kid principal creating for a profile that is not their own: 403."""
    resp = await client.post(
        "/api/v1/characters",
        # child_token's own profile is child_profile_id; other_child_profile_id
        # belongs to family B, a sibling from this caller's point of view.
        json=_create_body(str(seed.other_child_profile_id)),
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
