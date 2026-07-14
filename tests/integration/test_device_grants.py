"""Integration tests for the device-grant management endpoints (ADR-014 phase 1).

Exercises minting authorization (guardian own-family, admin any-family,
guardian cross-family rejection, admin-omitted-family rejection, child and
device rejection, unauthenticated), the family-scoped list/revoke surface,
and the end-to-end round-trip (a minted grant authenticates as a DEVICE
principal). Mirrors ``test_child_sessions.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import DeviceGrant
from tests.integration.conftest import Seed, Stranger, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.security]


# ---------------------------------------------------------------------------
# mint authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardian_mints_own_family_returns_201(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian mints a device grant for its own family (family_id omitted)."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["family_id"] == str(seed.family_id)
    assert body["authorized_by"]
    assert body["token"]
    assert body["expires_at"]
    assert body["id"]


@pytest.mark.asyncio
async def test_guardian_may_name_own_family_explicitly(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian naming its own family_id explicitly is accepted."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={"family_id": str(seed.family_id), "label": "Kitchen tablet"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_admin_mints_own_family_returns_201(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin naming its own family works (admins have a family_id too)."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={"family_id": str(seed.family_id)},
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_admin_mints_other_family_returns_201(
    client: AsyncClient, seed: Seed, stranger: Stranger
) -> None:
    """An admin is global and may mint a device grant for another family."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={"family_id": str(stranger.family_id)},
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["family_id"] == str(stranger.family_id)


@pytest.mark.asyncio
async def test_admin_omitting_family_id_is_422(client: AsyncClient, seed: Seed) -> None:
    """An admin-only caller must supply family_id (no default to fall back to)."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={},
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_guardian_cannot_mint_other_family(
    client: AsyncClient, seed: Seed, stranger: Stranger
) -> None:
    """A guardian naming another family's id is rejected with 403."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={"family_id": str(stranger.family_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_child_cannot_mint_device_grant(client: AsyncClient, seed: Seed) -> None:
    """A child dev-stub token cannot mint a device grant (403 at the role gate)."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_unauthenticated_mint_returns_401(client: AsyncClient) -> None:
    """Minting without a bearer token is rejected with 401."""
    resp = await client.post("/api/v1/device-grants", json={})
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_mint_rejects_malformed_family_id(
    client: AsyncClient, seed: Seed
) -> None:
    """A non-UUID family_id is rejected with 422 before any lookup."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={"family_id": "not-a-uuid"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_mint_forbids_unknown_body_field(client: AsyncClient, seed: Seed) -> None:
    """An unexpected body field is rejected (extra='forbid')."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={"role": "admin"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_mint_persists_matching_jti(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The persisted row's id matches the response id, and exactly one row exists."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    grant_id = resp.json()["id"]

    async with sessions() as session:
        rows = (await session.scalars(select(DeviceGrant))).all()
    assert len(rows) == 1
    assert str(rows[0].id) == grant_id
    assert rows[0].revoked_at is None


# ---------------------------------------------------------------------------
# list / revoke
# ---------------------------------------------------------------------------


async def _mint_grant(
    client: AsyncClient, token: str, *, label: str | None = None
) -> str:
    """Mint a device grant and return its id."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={} if label is None else {"label": label},
        headers=auth(token),
    )
    assert resp.status_code == 201, resp.text
    grant_id = resp.json()["id"]
    assert isinstance(grant_id, str)
    return grant_id


@pytest.mark.asyncio
async def test_list_returns_only_own_family_active_grants(
    client: AsyncClient, seed: Seed, stranger: Stranger
) -> None:
    """The list is scoped to the caller's own family and excludes revoked rows."""
    own_id = await _mint_grant(client, seed.guardian_token, label="Own device")
    await _mint_grant(client, stranger.guardian_token, label="Stranger device")

    resp = await client.get("/api/v1/device-grants", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert [item["id"] for item in items] == [own_id]
    assert items[0]["label"] == "Own device"
    assert items[0]["revoked_at"] is None


@pytest.mark.asyncio
async def test_list_excludes_revoked_grant(client: AsyncClient, seed: Seed) -> None:
    """A revoked grant no longer appears in the list."""
    grant_id = await _mint_grant(client, seed.guardian_token)

    revoke_resp = await client.delete(
        f"/api/v1/device-grants/{grant_id}", headers=auth(seed.guardian_token)
    )
    assert revoke_resp.status_code == 204, revoke_resp.text

    list_resp = await client.get(
        "/api/v1/device-grants", headers=auth(seed.guardian_token)
    )
    assert list_resp.status_code == 200, list_resp.text
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_revoke_persists_revoked_at(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Revoking sets revoked_at rather than deleting the row."""
    grant_id = await _mint_grant(client, seed.guardian_token)

    resp = await client.delete(
        f"/api/v1/device-grants/{grant_id}", headers=auth(seed.guardian_token)
    )
    assert resp.status_code == 204, resp.text

    async with sessions() as session:
        rows = (await session.scalars(select(DeviceGrant))).all()
    assert len(rows) == 1
    assert rows[0].revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_other_family_grant_is_404(
    client: AsyncClient, seed: Seed, stranger: Stranger
) -> None:
    """A guardian may not revoke another family's grant; the id is a 404, not 403."""
    stranger_grant_id = await _mint_grant(client, stranger.guardian_token)

    resp = await client.delete(
        f"/api/v1/device-grants/{stranger_grant_id}", headers=auth(seed.guardian_token)
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_revoke_unknown_id_is_404(client: AsyncClient, seed: Seed) -> None:
    """Revoking a nonexistent id is 404."""
    resp = await client.delete(
        "/api/v1/device-grants/00000000-0000-0000-0000-000000000000",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_child_cannot_list_or_revoke(client: AsyncClient, seed: Seed) -> None:
    """A child dev-stub token is rejected on both list and revoke (403)."""
    list_resp = await client.get(
        "/api/v1/device-grants", headers=auth(seed.child_token)
    )
    assert list_resp.status_code == 403, list_resp.text

    revoke_resp = await client.delete(
        "/api/v1/device-grants/00000000-0000-0000-0000-000000000000",
        headers=auth(seed.child_token),
    )
    assert revoke_resp.status_code == 403, revoke_resp.text


# ---------------------------------------------------------------------------
# end-to-end round-trip + negative cases for the minted device token itself
# ---------------------------------------------------------------------------


async def _mint_device_token(client: AsyncClient, seed: Seed) -> str:
    """Mint a device grant and return the raw JWT (not just its id)."""
    resp = await client.post(
        "/api/v1/device-grants",
        json={},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["token"]
    assert isinstance(token, str)
    return token


@pytest.mark.asyncio
async def test_minted_device_token_authenticates_as_device_principal(
    client: AsyncClient, seed: Seed
) -> None:
    """A minted device token yields a DEVICE principal scoped to no profiles."""
    token = await _mint_device_token(client, seed)
    resp = await client.get("/api/v1/me", headers=auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "device"
    assert body["is_admin"] is False
    assert body["profile_ids"] == []
    assert body["family_id"] == str(seed.family_id)


@pytest.mark.asyncio
async def test_device_token_cannot_mint_another_device_grant(
    client: AsyncClient, seed: Seed
) -> None:
    """A device principal cannot mint a device grant for itself or anyone else."""
    token = await _mint_device_token(client, seed)
    resp = await client.post("/api/v1/device-grants", json={}, headers=auth(token))
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_device_token_cannot_reach_guardian_endpoint(
    client: AsyncClient, seed: Seed
) -> None:
    """A minted device token cannot reach an ordinary guardian-only endpoint."""
    token = await _mint_device_token(client, seed)
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "New Kid", "age_band": "10-13"},
        headers=auth(token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_device_token_cannot_onboard(client: AsyncClient, seed: Seed) -> None:
    """A device grant token cannot provision a guardian Family+User."""
    token = await _mint_device_token(client, seed)
    resp = await client.post("/api/v1/onboarding", json={}, headers=auth(token))
    assert resp.status_code == 403, resp.text
