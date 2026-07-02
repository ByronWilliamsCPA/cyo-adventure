"""Integration tests for the profiles API (C4a-2).

List scoping follows the authorization matrix: a guardian sees every profile
in their own family, a child sees only their own, and nobody sees another
family's rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_requires_authentication(client: AsyncClient) -> None:
    """GET /profiles without a bearer is a 401."""
    resp = await client.get("/api/v1/profiles")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_lists_own_family_profiles(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian sees all of their family's profiles and nothing else."""
    resp = await client.get("/api/v1/profiles", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    profiles = resp.json()["profiles"]
    assert [p["display_name"] for p in profiles] == ["Reader A"]
    row = profiles[0]
    assert row["id"] == str(seed.child_profile_id)
    assert row["age_band"] == "10-13"
    assert row["reading_level_cap"] == 99.0
    assert row["avatar"] is None
    assert row["tts_enabled"] is False
    assert "created_at" in row


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_lists_only_own_profile(client: AsyncClient, seed: Seed) -> None:
    """A child token resolves to exactly its own profile."""
    resp = await client.get("/api/v1/profiles", headers=auth(seed.child_token))
    assert resp.status_code == 200, resp.text
    profiles = resp.json()["profiles"]
    assert [p["id"] for p in profiles] == [str(seed.child_profile_id)]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_profileless_child_gets_empty_list(
    client: AsyncClient, seed: Seed
) -> None:
    """A child with no assigned profile gets an empty list, not an error."""
    del seed  # fixture seeds the child-noprofile user
    resp = await client.get("/api/v1/profiles", headers=auth("child-noprofile"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["profiles"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_creates_profile(client: AsyncClient, seed: Seed) -> None:
    """A guardian creates a profile; it is echoed back and then listed."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "  Nova  ", "age_band": "5-8", "avatar": "fox"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["display_name"] == "Nova"  # whitespace stripped
    assert body["age_band"] == "5-8"
    assert body["reading_level_cap"] == 99.0
    assert body["avatar"] == "fox"
    assert body["tts_enabled"] is False

    listed = await client.get("/api/v1/profiles", headers=auth(seed.guardian_token))
    names = [p["display_name"] for p in listed.json()["profiles"]]
    assert names == ["Reader A", "Nova"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_cannot_create_profile(client: AsyncClient, seed: Seed) -> None:
    """A child token is rejected with 403 before any write."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8"},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_unknown_age_band(client: AsyncClient, seed: Seed) -> None:
    """An age band outside the six-band vocabulary is a 422."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "4-6"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_unknown_fields(client: AsyncClient, seed: Seed) -> None:
    """extra=forbid rejects unmodeled body fields."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8", "family_id": "x"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_updates_caps_and_clears_avatar(
    client: AsyncClient, seed: Seed
) -> None:
    """PATCH updates provided fields; explicit null clears the avatar."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8", "avatar": "fox"},
        headers=guardian,
    )
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}",
        json={"reading_level_cap": 4.5, "age_band": "8-11", "avatar": None},
        headers=guardian,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reading_level_cap"] == 4.5
    assert body["age_band"] == "8-11"
    assert body["avatar"] is None
    assert body["display_name"] == "Nova"  # untouched field survives


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_omitting_avatar_keeps_it(client: AsyncClient, seed: Seed) -> None:
    """A PATCH that omits avatar leaves the stored avatar unchanged."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8", "avatar": "owl"},
        headers=guardian,
    )
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}", json={"tts_enabled": True}, headers=guardian
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["avatar"] == "owl"
    assert resp.json()["tts_enabled"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_cannot_update_other_familys_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """Cross-family PATCH is a 403 (authorize_profile), leaking nothing."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.other_child_profile_id}",
        json={"reading_level_cap": 1.0},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_cannot_update_profile(client: AsyncClient, seed: Seed) -> None:
    """A child may not change their own caps."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"reading_level_cap": 99.0},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_rejects_malformed_uuid(client: AsyncClient, seed: Seed) -> None:
    """A non-UUID path id is a 422 from _parse_uuid."""
    resp = await client.patch(
        "/api/v1/profiles/not-a-uuid",
        json={"tts_enabled": True},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_ignores_explicit_null_on_non_avatar_fields(
    client: AsyncClient, seed: Seed
) -> None:
    """Explicit null on a non-avatar field is silently ignored (is not None gate)."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8"},
        headers=guardian,
    )
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}",
        json={"age_band": None},
        headers=guardian,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["age_band"] == "5-8"  # unchanged, null was ignored


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_rejects_unknown_fields(client: AsyncClient, seed: Seed) -> None:
    """extra=forbid rejects unmodeled body fields on PATCH too."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"family_id": "x"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422
