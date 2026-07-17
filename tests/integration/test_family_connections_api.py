"""Integration tests for directional family-connection admin CRUD (WS-J).

Exercises ``/api/v1/admin/family-connections``: the 403 gate, the create/
list/delete round trip, the one-way (non-symmetric) contract, self-connection
rejection, and the duplicate-pair conflict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CONNECTIONS = "/api/v1/admin/family-connections"


async def _other_family_id(client: AsyncClient, seed: Seed) -> str:
    resp = await client.post(
        "/api/v1/admin/families",
        headers=auth(seed.admin_token),
        json={"name": "Connection Target"},
    )
    assert resp.status_code == 201
    return cast("str", resp.json()["id"])


async def test_guardian_gets_403(client: AsyncClient, seed: Seed) -> None:
    """A non-admin guardian is refused list/create (403)."""
    list_resp = await client.get(_CONNECTIONS, headers=auth(seed.guardian_token))
    assert list_resp.status_code == 403

    create_resp = await client.post(
        _CONNECTIONS,
        headers=auth(seed.guardian_token),
        json={
            "family_id": str(seed.family_id),
            "connected_family_id": str(seed.family_id),
        },
    )
    assert create_resp.status_code == 403


async def test_create_list_delete_roundtrip(client: AsyncClient, seed: Seed) -> None:
    """A created connection appears in the list and can be deleted."""
    target = await _other_family_id(client, seed)

    create = await client.post(
        _CONNECTIONS,
        headers=auth(seed.admin_token),
        json={"family_id": str(seed.family_id), "connected_family_id": target},
    )
    assert create.status_code == 201, create.text
    connection_id = create.json()["id"]

    listing = await client.get(_CONNECTIONS, headers=auth(seed.admin_token))
    assert listing.status_code == 200
    ids = [row["id"] for row in listing.json()["connections"]]
    assert connection_id in ids

    delete_resp = await client.delete(
        f"{_CONNECTIONS}/{connection_id}", headers=auth(seed.admin_token)
    )
    assert delete_resp.status_code == 204

    listing_after = await client.get(_CONNECTIONS, headers=auth(seed.admin_token))
    ids_after = [row["id"] for row in listing_after.json()["connections"]]
    assert connection_id not in ids_after


async def test_directional_not_symmetric(client: AsyncClient, seed: Seed) -> None:
    """family_id -> connected_family_id does not imply the reverse row."""
    target = await _other_family_id(client, seed)

    resp = await client.post(
        _CONNECTIONS,
        headers=auth(seed.admin_token),
        json={"family_id": str(seed.family_id), "connected_family_id": target},
    )
    assert resp.status_code == 201

    # The reverse direction is a DIFFERENT, still-unwritten pair.
    reverse = await client.post(
        _CONNECTIONS,
        headers=auth(seed.admin_token),
        json={"family_id": target, "connected_family_id": str(seed.family_id)},
    )
    assert reverse.status_code == 201

    listing = await client.get(_CONNECTIONS, headers=auth(seed.admin_token))
    pairs = {
        (row["family_id"], row["connected_family_id"])
        for row in listing.json()["connections"]
    }
    assert (str(seed.family_id), target) in pairs
    assert (target, str(seed.family_id)) in pairs


async def test_self_connection_rejected(client: AsyncClient, seed: Seed) -> None:
    """A family cannot connect to itself (422)."""
    resp = await client.post(
        _CONNECTIONS,
        headers=auth(seed.admin_token),
        json={
            "family_id": str(seed.family_id),
            "connected_family_id": str(seed.family_id),
        },
    )
    assert resp.status_code == 422


async def test_duplicate_connection_conflicts(client: AsyncClient, seed: Seed) -> None:
    """Creating the same directional pair twice is rejected (409)."""
    target = await _other_family_id(client, seed)
    body = {"family_id": str(seed.family_id), "connected_family_id": target}

    first = await client.post(_CONNECTIONS, headers=auth(seed.admin_token), json=body)
    assert first.status_code == 201

    second = await client.post(_CONNECTIONS, headers=auth(seed.admin_token), json=body)
    assert second.status_code == 409


async def test_unknown_family_is_404(client: AsyncClient, seed: Seed) -> None:
    """A well-formed but nonexistent family id 404s rather than FK-erroring."""
    resp = await client.post(
        _CONNECTIONS,
        headers=auth(seed.admin_token),
        json={
            "family_id": str(seed.family_id),
            "connected_family_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert resp.status_code == 404
