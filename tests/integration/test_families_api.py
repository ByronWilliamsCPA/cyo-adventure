"""Integration tests for admin family create/rename/deactivate (WS-J).

Exercises the new ``POST``/``PATCH`` routes on ``/api/v1/admin/families``:
the 403 gate, create, rename, member counts, and the deactivation cascade
(and its deliberate non-reactivation asymmetry).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.db.models import Family, User

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_FAMILIES = "/api/v1/admin/families"


async def _independent_admin_token(
    sessions: async_sessionmaker[AsyncSession],
) -> str:
    """Seed an active admin in a brand-new family, unrelated to ``seed``.

    Several tests below deactivate the ``seed`` family, which (by the
    documented cascade) also deactivates ``seed.admin_token``/``dual_token``
    since both belong to that same family. A second admin call (e.g. the
    reactivate step) needs a caller whose OWN account survives the first
    call's cascade.
    """
    async with sessions() as session:
        family = Family(name="Independent Admin Family")
        session.add(family)
        await session.flush()
        admin = User(
            family_id=family.id,
            role="admin",
            is_admin=True,
            authn_subject="independent-admin",
        )
        session.add(admin)
        await session.commit()
    return "independent-admin"


async def test_guardian_gets_403_on_create_and_update(
    client: AsyncClient, seed: Seed
) -> None:
    """A non-admin guardian is refused create/update (403)."""
    create_resp = await client.post(
        _FAMILIES, headers=auth(seed.guardian_token), json={"name": "Nope"}
    )
    assert create_resp.status_code == 403

    update_resp = await client.patch(
        f"{_FAMILIES}/{seed.family_id}",
        headers=auth(seed.guardian_token),
        json={"name": "Nope"},
    )
    assert update_resp.status_code == 403


async def test_create_family_has_zero_members(client: AsyncClient, seed: Seed) -> None:
    """A freshly created family reports zero guardians/admins and zero kids."""
    _ = seed
    resp = await client.post(
        _FAMILIES, headers=auth(seed.admin_token), json={"name": "Brand New Family"}
    )
    assert resp.status_code == 201, resp.text
    body = cast("dict[str, object]", resp.json())
    assert body["name"] == "Brand New Family"
    assert body["status"] == "active"
    assert body["guardian_count"] == 0
    assert body["kid_count"] == 0


async def test_list_reports_seed_family_member_counts(
    client: AsyncClient, seed: Seed
) -> None:
    """The seed family's counts reflect its 3 adults and 1 kid profile."""
    resp = await client.get(_FAMILIES, headers=auth(seed.admin_token))
    assert resp.status_code == 200
    row = next(r for r in resp.json()["families"] if r["id"] == str(seed.family_id))
    # Seed family A: admin-a, guardian-a, dual-a (3 guardian/admin rows) + 1 kid.
    assert row["guardian_count"] == 3
    assert row["kid_count"] == 1


async def test_rename_family(client: AsyncClient, seed: Seed) -> None:
    """PATCH with only ``name`` renames without touching status."""
    resp = await client.patch(
        f"{_FAMILIES}/{seed.family_id}",
        headers=auth(seed.admin_token),
        json={"name": "Renamed Family"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed Family"
    assert body["status"] == "active"


async def test_deactivate_family_cascades_to_members_and_blocks_login(
    client: AsyncClient, seed: Seed
) -> None:
    """Deactivating a family deactivates its members and blocks their login."""
    resp = await client.patch(
        f"{_FAMILIES}/{seed.family_id}",
        headers=auth(seed.admin_token),
        json={"status": "deactivated"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deactivated"

    me_resp = await client.get("/api/v1/me", headers=auth(seed.guardian_token))
    assert me_resp.status_code == 401


async def test_reactivate_family_does_not_reactivate_members(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """Reactivating a family alone does not restore its members' access."""
    # Deactivating cascades to seed.admin_token itself (a member of
    # seed.family_id), so the reactivate call below uses an admin from an
    # unrelated family instead of seed.admin_token.
    outside_admin = await _independent_admin_token(sessions)
    await client.patch(
        f"{_FAMILIES}/{seed.family_id}",
        headers=auth(seed.admin_token),
        json={"status": "deactivated"},
    )
    reactivate = await client.patch(
        f"{_FAMILIES}/{seed.family_id}",
        headers=auth(outside_admin),
        json={"status": "active"},
    )
    assert reactivate.status_code == 200
    assert reactivate.json()["status"] == "active"

    # The family itself is active again, but its guardian was individually
    # deactivated by the cascade and stays that way (deliberate asymmetry).
    me_resp = await client.get("/api/v1/me", headers=auth(seed.guardian_token))
    assert me_resp.status_code == 401


async def test_unknown_family_id_is_404(client: AsyncClient, seed: Seed) -> None:
    """PATCH on a nonexistent family id 404s."""
    resp = await client.patch(
        f"{_FAMILIES}/00000000-0000-0000-0000-000000000000",
        headers=auth(seed.admin_token),
        json={"name": "Ghost"},
    )
    assert resp.status_code == 404
