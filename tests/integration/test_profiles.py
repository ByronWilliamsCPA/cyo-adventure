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
