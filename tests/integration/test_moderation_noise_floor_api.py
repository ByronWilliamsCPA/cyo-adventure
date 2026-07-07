"""Admin GET/PUT for the global moderation noise floor (WS-A addendum Task A3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.db.models import ModerationSetting
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_URL = "/api/v1/admin/moderation/noise-floor"


async def test_guardian_gets_403_on_get(client: AsyncClient, seed: Seed) -> None:
    """A non-admin caller is rejected before any read."""
    res = await client.get(_URL, headers=auth(seed.guardian_token))
    assert res.status_code == 403


async def test_guardian_gets_403_on_put_with_no_state_change(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """A non-admin caller is rejected before any write; no row is created."""
    res = await client.put(_URL, json={"value": 0.2}, headers=auth(seed.guardian_token))
    assert res.status_code == 403
    async with AsyncSession(engine) as session:
        rows = (await session.scalars(select(ModerationSetting))).all()
    assert rows == []


async def test_get_with_no_row_returns_default(client: AsyncClient, seed: Seed) -> None:
    """GET with no persisted row falls back to the 0.05 code default."""
    res = await client.get(_URL, headers=auth(seed.admin_token))
    assert res.status_code == 200
    assert res.json() == {"value": 0.05}


async def test_put_then_get_roundtrips(client: AsyncClient, seed: Seed) -> None:
    """A successful PUT persists the value; a subsequent GET returns it."""
    res = await client.put(_URL, json={"value": 0.2}, headers=auth(seed.admin_token))
    assert res.status_code == 200
    assert res.json() == {"value": 0.2}
    res = await client.get(_URL, headers=auth(seed.admin_token))
    assert res.status_code == 200
    assert res.json() == {"value": 0.2}


async def test_put_over_max_rejected(client: AsyncClient, seed: Seed) -> None:
    """A value above 1.0 is a 422, not a silently-clamped write."""
    res = await client.put(_URL, json={"value": 1.5}, headers=auth(seed.admin_token))
    assert res.status_code == 422


async def test_put_below_min_rejected(client: AsyncClient, seed: Seed) -> None:
    """A negative value is a 422, not a silently-clamped write."""
    res = await client.put(_URL, json={"value": -0.1}, headers=auth(seed.admin_token))
    assert res.status_code == 422


async def test_put_records_updated_by(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """A successful PUT stamps updated_by with the admin's user id."""
    res = await client.put(_URL, json={"value": 0.3}, headers=auth(seed.admin_token))
    assert res.status_code == 200
    async with AsyncSession(engine) as session:
        row = await session.get(ModerationSetting, "admin_noise_floor")
    assert row is not None
    assert row.updated_by is not None
