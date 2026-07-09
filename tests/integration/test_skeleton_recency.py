"""Integration tests for recent_skeleton_usage (WS-C PR2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Family, Storybook, StorybookVersion
from cyo_adventure.generation.skeleton_match import recent_skeleton_usage

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


async def _seed_version(
    session: AsyncSession,
    family_id: uuid.UUID,
    *,
    storybook_id: str,
    skeleton_slug: str | None,
) -> None:
    session.add(Storybook(id=storybook_id, family_id=family_id, status="draft"))
    await session.flush()
    session.add(
        StorybookVersion(
            storybook_id=storybook_id,
            version=1,
            blob={"id": storybook_id, "title": "T", "nodes": []},
            skeleton_slug=skeleton_slug,
        )
    )
    await session.flush()


async def test_recent_skeleton_usage_counts_within_family(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        family = Family(name="Recency Fam")
        session.add(family)
        await session.flush()
        await _seed_version(
            session, family.id, storybook_id="s_r1", skeleton_slug="the-cave-of-echoes"
        )
        await _seed_version(
            session, family.id, storybook_id="s_r2", skeleton_slug="the-cave-of-echoes"
        )
        await _seed_version(
            session,
            family.id,
            storybook_id="s_r3",
            skeleton_slug="the-sky-ship-stowaway",
        )
        await _seed_version(session, family.id, storybook_id="s_r4", skeleton_slug=None)
        await session.commit()

        usage = await recent_skeleton_usage(session, family.id)
        assert usage == {"the-cave-of-echoes": 2, "the-sky-ship-stowaway": 1}


async def test_recent_skeleton_usage_returns_empty_for_none_family_id(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        assert await recent_skeleton_usage(session, None) == {}


async def test_recent_skeleton_usage_returns_empty_for_family_with_no_history(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        family = Family(name="Empty Fam")
        session.add(family)
        await session.flush()
        await session.commit()

        assert await recent_skeleton_usage(session, family.id) == {}


async def test_recent_skeleton_usage_ignores_other_families(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        family_a = Family(name="Fam A")
        family_b = Family(name="Fam B")
        session.add_all([family_a, family_b])
        await session.flush()
        await _seed_version(
            session,
            family_a.id,
            storybook_id="s_a1",
            skeleton_slug="the-cave-of-echoes",
        )
        await _seed_version(
            session,
            family_b.id,
            storybook_id="s_b1",
            skeleton_slug="the-sky-ship-stowaway",
        )
        await session.commit()

        usage = await recent_skeleton_usage(session, family_a.id)
        assert usage == {"the-cave-of-echoes": 1}
