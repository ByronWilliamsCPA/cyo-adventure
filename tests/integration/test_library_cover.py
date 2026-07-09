"""list_library surfaces cover_image_url as LibraryItem.cover_url."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import StorybookVersion
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_cover_url_present_when_set(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A stored cover_image_url surfaces as LibraryItem.cover_url."""
    cover_url = "https://p.supabase.co/storage/v1/object/public/covers/x.webp?v=1"
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        row.cover_image_url = cover_url
        row.cover_status = "ready"
        await s.commit()

    resp = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    story = next(
        item for item in resp.json()["stories"] if item["id"] == seed.storybook_id
    )
    assert story["cover_url"] == cover_url


async def test_cover_url_null_by_default(
    client: AsyncClient,
    seed: Seed,
) -> None:
    """A story with no cover generated yet shows a null cover_url."""
    resp = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    story = next(
        item for item in resp.json()["stories"] if item["id"] == seed.storybook_id
    )
    assert story["cover_url"] is None
