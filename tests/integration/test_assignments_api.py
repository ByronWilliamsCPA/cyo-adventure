"""Integration tests for storybook assignment: ORM, API, and read-gate invariants."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    Storybook,
    StorybookAssignment,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_storybook_assignment_roundtrip(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """An assignment row inserts and reads back with its composite key."""
    async with sessions() as session:
        fam = Family(name="Fam")
        session.add(fam)
        await session.flush()
        profile = ChildProfile(family_id=fam.id, display_name="Kid", age_band="8-11")
        session.add(profile)
        book = Storybook(id="s-assign-1", family_id=fam.id, status="published")
        session.add(book)
        await session.flush()
        session.add(
            StorybookAssignment(child_profile_id=profile.id, storybook_id="s-assign-1")
        )
        await session.commit()
        profile_id = profile.id

    async with sessions() as session:
        row = await session.get(StorybookAssignment, (profile_id, "s-assign-1"))
        assert row is not None
        assert row.assigned_by is None
