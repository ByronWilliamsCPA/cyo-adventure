"""The no-unapproved-publish invariant across both library read paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Storybook, StorybookVersion

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _add_unapproved_published_story(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> str:
    """Insert a status='published' story in Family A whose version is unapproved."""
    async with sessions() as session:
        story_id = "unapproved-but-published"
        session.add(
            Storybook(
                id=story_id,
                family_id=seed.family_id,
                current_published_version=1,
                status="published",
            )
        )
        session.add(
            StorybookVersion(storybook_id=story_id, version=1, blob={"id": story_id})
        )
        await session.commit()
        return story_id


async def test_unapproved_story_not_in_library(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A published-status but unapproved story is excluded from the list."""
    bad_id = await _add_unapproved_published_story(sessions, seed)
    resp = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    listed = {item["id"] for item in resp.json()["stories"]}
    assert seed.storybook_id in listed  # the approved seed story shows
    assert bad_id not in listed  # the unapproved one does not
