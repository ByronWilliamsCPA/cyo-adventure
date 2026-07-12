"""Integration tests for GET /api/v1/me."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_guardian_identity(client: AsyncClient, seed: Seed) -> None:
    """A guardian's /me reflects its role and its family's profile ids."""
    resp = await client.get("/api/v1/me", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject"] == seed.guardian_token
    assert body["role"] == "guardian"
    assert body["is_admin"] is False
    assert body["family_id"] == str(seed.family_id)
    assert str(seed.child_profile_id) in body["profile_ids"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_child_identity_scoped_to_own_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """A child's /me lists only its own assigned profile, not its sibling's."""
    resp = await client.get("/api/v1/me", headers=auth(seed.child_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "child"
    assert body["profile_ids"] == [str(seed.child_profile_id)]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_admin_identity(client: AsyncClient, seed: Seed) -> None:
    """An admin-only adult's /me reflects the admin base role and capability."""
    resp = await client.get("/api/v1/me", headers=auth(seed.admin_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "admin"
    assert body["is_admin"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_dual_role_identity(client: AsyncClient, seed: Seed) -> None:
    """A dual-role adult's /me carries the guardian persona AND the capability.

    The frontend picks the guardian shell from ``role`` and shows the admin
    console entry from ``is_admin``; both must be present on one identity.
    """
    resp = await client.get("/api/v1/me", headers=auth(seed.dual_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "guardian"
    assert body["is_admin"] is True
    assert body["family_id"] == str(seed.family_id)
    assert str(seed.child_profile_id) in body["profile_ids"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_requires_authentication(client: AsyncClient) -> None:
    """No bearer token yields 401, not a 500 or an anonymous identity."""
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
