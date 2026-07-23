"""StorybookVersion cover columns and CHECK constraint."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from cyo_adventure.db.models import StorybookVersion

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tests.integration.conftest import Seed

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_cover_status_defaults_to_none(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        row = await session.get(
            StorybookVersion,
            (seed.storybook_id, seed.version),
        )
        assert row is not None
        assert row.cover_status == "none"
        assert row.cover_image_url is None


@pytest.mark.asyncio
async def test_cover_status_rejects_unknown_value(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        statement = text(
            "UPDATE storybook_version SET cover_status = 'bogus' "
            "WHERE storybook_id = :sid AND version = :v"
        )
        params = {"sid": seed.storybook_id, "v": seed.version}
        with pytest.raises(IntegrityError):
            await session.execute(statement, params)
