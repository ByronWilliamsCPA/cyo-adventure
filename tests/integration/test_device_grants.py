"""Integration tests for the device-grant management endpoints (ADR-014 phase 1).

Exercises minting authorization (guardian own-family, admin any-family,
guardian cross-family rejection, admin-omitted-family rejection, child and
device rejection, unauthenticated), the family-scoped list/revoke surface,
and the end-to-end round-trip (a minted grant authenticates as a DEVICE
principal). Mirrors ``test_child_sessions.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.core.device_grant import mint_device_grant_token
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
    # expires_at is stamped at mint from the token TTL, in the future (#252).
    assert rows[0].expires_at is not None
    assert rows[0].expires_at > datetime.now(UTC)


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
    # The list returns only active grants, so a revocation timestamp would
    # always be null; the field is deliberately dropped from the wire contract
    # (its mere presence in the list means the grant is active).
    assert "revoked_at" not in items[0]


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
async def test_list_excludes_expired_unrevoked_grant(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """An unrevoked-but-expired grant is a ghost and must not appear (#252).

    The grant's JWT no longer verifies (so it can mint nothing online), yet its
    revoked_at is NULL; only the persisted expires_at lets the list exclude it,
    keeping "present in the list" == "actually usable".
    """
    grant_id = await _mint_grant(client, seed.guardian_token)

    # Force the grant past its expiry without revoking it.
    async with sessions() as session:
        grant = await session.get(DeviceGrant, uuid.UUID(grant_id))
        assert grant is not None
        assert grant.expires_at is not None  # stamped at mint
        grant.expires_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()

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
async def test_double_revoke_preserves_first_revoked_at(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A second DELETE is an idempotent no-op that keeps the first revoked_at.

    The row exists to be a stable revocation record; a double-submitted DELETE
    must not silently push revoked_at forward and lose when the grant was
    actually revoked (issue #253).
    """
    grant_id = await _mint_grant(client, seed.guardian_token)

    first = await client.delete(
        f"/api/v1/device-grants/{grant_id}", headers=auth(seed.guardian_token)
    )
    assert first.status_code == 204, first.text
    async with sessions() as session:
        first_revoked_at = (await session.scalars(select(DeviceGrant))).one().revoked_at
    assert first_revoked_at is not None

    second = await client.delete(
        f"/api/v1/device-grants/{grant_id}", headers=auth(seed.guardian_token)
    )
    assert second.status_code == 204, second.text
    async with sessions() as session:
        second_revoked_at = (
            (await session.scalars(select(DeviceGrant))).one().revoked_at
        )
    assert second_revoked_at == first_revoked_at


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


# ---------------------------------------------------------------------------
# revocation enforcement (deps.py::_device_principal online check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoked_device_token_is_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """A cryptographically valid token is refused once its grant is revoked.

    The token itself never changes and stays perfectly signed; revocation is a
    server-side, online-only decision (``deps.py::_device_principal`` looks the
    jti up and rejects a non-null ``revoked_at``). This is the whole point of a
    revocable device grant: a self-contained token cannot know it was revoked.
    """
    token = await _mint_device_token(client, seed)
    grant_id = await _grant_id_for_token(client, seed)

    # Before revocation the token authenticates as a device principal.
    ok = await client.get("/api/v1/me", headers=auth(token))
    assert ok.status_code == 200, ok.text

    revoke = await client.delete(
        f"/api/v1/device-grants/{grant_id}", headers=auth(seed.guardian_token)
    )
    assert revoke.status_code == 204, revoke.text

    # The identical token is now refused: the online revocation check fires
    # before any principal is built.
    denied = await client.get("/api/v1/me", headers=auth(token))
    assert denied.status_code == 401, denied.text


@pytest.mark.asyncio
async def test_device_token_with_unknown_jti_is_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """A validly-signed token whose jti has no grant row is refused.

    Forging a signature is not required to probe this path: a token signed with
    the real secret but carrying a jti that was never persisted (e.g. a grant
    row hard-deleted out from under a still-live token) must not authenticate.
    ``_device_principal`` treats "no row" and "revoked row" identically, with
    the same 401 message, so neither is a jti-existence oracle.
    """
    token, _expires_at = mint_device_grant_token(
        family_id=seed.family_id,
        authorized_by=seed.admin_user_id,
        jti=uuid.uuid4(),
    )
    resp = await client.get("/api/v1/me", headers=auth(token))
    assert resp.status_code == 401, resp.text


async def _grant_id_for_token(client: AsyncClient, seed: Seed) -> str:
    """Return the id of the caller's single active grant (for revoke-by-id)."""
    resp = await client.get("/api/v1/device-grants", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1, items
    grant_id = items[0]["id"]
    assert isinstance(grant_id, str)
    return grant_id
