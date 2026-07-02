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
