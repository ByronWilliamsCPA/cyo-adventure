"""Integration tests for the guardian storage/download view (G15 remainder).

Real Postgres, real HTTP client (mirrors test_device_grants.py's convention
for this sibling feature): proves the report/remove/list endpoints end to
end, including cross-family scoping and the title/profile-name projection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import DeviceDownload
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_report_creates_a_row(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    resp = await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 204, resp.text

    async with sessions() as s:
        row = await s.scalar(
            select(DeviceDownload).where(
                DeviceDownload.device_id == "device-1",
                DeviceDownload.child_profile_id == seed.child_profile_id,
                DeviceDownload.storybook_id == seed.storybook_id,
            )
        )
        assert row is not None
        assert row.family_id == seed.family_id


async def test_repeat_report_advances_last_confirmed_at_without_duplicating(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    body = {
        "device_id": "device-1",
        "profile_id": str(seed.child_profile_id),
        "storybook_id": seed.storybook_id,
    }
    first = await client.put(
        "/api/v1/device-downloads", json=body, headers=auth(seed.guardian_token)
    )
    assert first.status_code == 204, first.text
    second = await client.put(
        "/api/v1/device-downloads", json=body, headers=auth(seed.guardian_token)
    )
    assert second.status_code == 204, second.text

    async with sessions() as s:
        rows = (
            await s.scalars(
                select(DeviceDownload).where(
                    DeviceDownload.device_id == "device-1",
                    DeviceDownload.child_profile_id == seed.child_profile_id,
                    DeviceDownload.storybook_id == seed.storybook_id,
                )
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].updated_at >= rows[0].created_at


async def test_report_wrong_profile_is_403(client: AsyncClient, seed: Seed) -> None:
    resp = await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.other_child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


async def test_report_nonexistent_profile_is_403_via_ownership_check(
    client: AsyncClient, seed: Seed
) -> None:
    """A fabricated profile id is never in any real principal's accessible set.

    ``authorize_profile`` runs before the ``ChildProfile`` existence check
    (mirrors ``flags.py::create_flag``'s identical ordering), so a
    nonexistent id 403s rather than 404s: a guardian's/child's accessible
    profile set is always derived from real rows, so a made-up id can never
    be "theirs" in the first place. The 404 branch exists for a genuine race
    (the profile is deleted between token mint and this request) that a
    fabricated id cannot exercise at the HTTP level.
    """
    resp = await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": "00000000-0000-4000-8000-000000000000",
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.dual_token),
    )
    assert resp.status_code == 403, resp.text


async def test_remove_deletes_the_row(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )

    resp = await client.request(
        "DELETE",
        "/api/v1/device-downloads",
        params={"device_id": "device-1", "storybook_id": seed.storybook_id},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 204, resp.text

    async with sessions() as s:
        row = await s.scalar(
            select(DeviceDownload).where(
                DeviceDownload.device_id == "device-1",
                DeviceDownload.storybook_id == seed.storybook_id,
            )
        )
        assert row is None


async def test_remove_never_touches_another_familys_row(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "shared-device-id",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )

    # Family B removes the same device_id/storybook_id pair; family A's own
    # row (different family_id, enforced by the WHERE clause, not by the
    # device_id happening to differ) must survive.
    await client.request(
        "DELETE",
        "/api/v1/device-downloads",
        params={"device_id": "shared-device-id", "storybook_id": seed.storybook_id},
        headers=auth(seed.other_child_token),
    )

    async with sessions() as s:
        row = await s.scalar(
            select(DeviceDownload).where(
                DeviceDownload.device_id == "shared-device-id",
                DeviceDownload.child_profile_id == seed.child_profile_id,
                DeviceDownload.storybook_id == seed.storybook_id,
            )
        )
        assert row is not None


async def test_list_returns_profile_name_and_book_title(
    client: AsyncClient, seed: Seed
) -> None:
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )

    resp = await client.get(
        "/api/v1/device-downloads", headers=auth(seed.guardian_token)
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["device_id"] == "device-1"
    assert item["profile_id"] == str(seed.child_profile_id)
    assert item["storybook_id"] == seed.storybook_id
    assert item["profile_name"]
    assert item["downloaded_at"] is not None
    assert item["last_confirmed_at"] is not None


async def test_list_never_leaks_another_familys_rows(
    client: AsyncClient, seed: Seed
) -> None:
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-b",
            "profile_id": str(seed.other_child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.other_child_token),
    )

    resp = await client.get(
        "/api/v1/device-downloads", headers=auth(seed.guardian_token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_list_rejects_child_principal(client: AsyncClient, seed: Seed) -> None:
    resp = await client.get("/api/v1/device-downloads", headers=auth(seed.child_token))
    assert resp.status_code == 403, resp.text


async def test_list_allows_admin(client: AsyncClient, seed: Seed) -> None:
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )
    resp = await client.get("/api/v1/device-downloads", headers=auth(seed.admin_token))
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
