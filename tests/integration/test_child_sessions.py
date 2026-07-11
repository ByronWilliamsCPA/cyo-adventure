"""Integration tests for the child-session mint endpoint (G1 / P6-04).

Exercises minting authorization (guardian own-family, admin, cross-family,
child, unauthenticated, missing child account), the end-to-end round-trip
(a minted token authenticates as a CHILD principal scoped to one profile),
and the P6-09 negative cases (a child token is rejected on a guardian
endpoint and on another profile's library).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import ChildProfile
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.security]


# ---------------------------------------------------------------------------
# mint authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardian_mints_own_family_profile_returns_201(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian mints a session for a profile in its own family."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["profile_id"] == str(seed.child_profile_id)
    assert body["token"]
    assert body["expires_at"]


@pytest.mark.asyncio
async def test_admin_mints_any_profile_returns_201(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin is global and may mint for any profile."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_guardian_cannot_mint_other_family_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian naming another family's profile is rejected with 403."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.other_child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_child_cannot_mint(client: AsyncClient, seed: Seed) -> None:
    """A child dev-stub token cannot mint a session (403 at the role gate)."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_unauthenticated_mint_returns_401(
    client: AsyncClient, seed: Seed
) -> None:
    """Minting without a bearer token is rejected with 401."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
    )
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_mint_requires_child_account(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A profile with no child User cannot start a session (404)."""
    async with sessions() as session:
        bare = ChildProfile(
            family_id=seed.family_id, display_name="No Account", age_band="10-13"
        )
        session.add(bare)
        await session.commit()
        bare_id = bare.id

    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(bare_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_mint_rejects_malformed_profile_id(
    client: AsyncClient, seed: Seed
) -> None:
    """A non-UUID profile id is rejected with 422 before any lookup."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": "not-a-uuid"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_mint_forbids_unknown_body_field(client: AsyncClient, seed: Seed) -> None:
    """An unexpected body field is rejected (extra='forbid')."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id), "role": "admin"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# end-to-end round-trip
# ---------------------------------------------------------------------------


async def _mint_child_token(client: AsyncClient, seed: Seed) -> str:
    """Mint a child token for the seeded profile and return the raw JWT."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["token"]
    assert isinstance(token, str)
    return token


@pytest.mark.asyncio
async def test_minted_token_authenticates_as_scoped_child(
    client: AsyncClient, seed: Seed
) -> None:
    """A minted token yields a CHILD principal scoped to exactly one profile."""
    token = await _mint_child_token(client, seed)
    resp = await client.get("/api/v1/me", headers=auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "child"
    assert body["profile_ids"] == [str(seed.child_profile_id)]
    assert body["family_id"] == str(seed.family_id)


@pytest.mark.asyncio
async def test_minted_token_reads_own_library(client: AsyncClient, seed: Seed) -> None:
    """A child token may list its own profile's library."""
    token = await _mint_child_token(client, seed)
    resp = await client.get(
        "/api/v1/library",
        params={"profile_id": str(seed.child_profile_id)},
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# P6-09 negative cases: a child token on out-of-scope surfaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_child_token_rejected_on_guardian_endpoint(
    client: AsyncClient, seed: Seed
) -> None:
    """A minted child token cannot reach a guardian-only endpoint (403)."""
    token = await _mint_child_token(client, seed)
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "New Kid", "age_band": "10-13"},
        headers=auth(token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_child_token_rejected_on_other_profile_library(
    client: AsyncClient, seed: Seed
) -> None:
    """A child token scoped to profile A cannot read profile B's library."""
    token = await _mint_child_token(client, seed)
    resp = await client.get(
        "/api/v1/library",
        params={"profile_id": str(seed.other_child_profile_id)},
        headers=auth(token),
    )
    assert resp.status_code in (403, 404), resp.text
    assert not (200 <= resp.status_code < 300)
