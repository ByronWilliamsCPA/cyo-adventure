"""Loader test: DB row becomes the admin noise floor; empty table means default.

Mirrors tests/integration/test_threshold_policy_loader.py: the ``engine``
fixture (tests/integration/conftest.py) builds the schema from ORM metadata
with no seed row, which is exactly the path load_admin_noise_floor() must
default on (the real seed row only exists after the migration runs).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from cyo_adventure.db.models import ModerationSetting
from cyo_adventure.moderation.thresholds import (
    ADMIN_NOISE_FLOOR_DEFAULT,
    load_admin_noise_floor,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_default_when_no_row(engine: AsyncEngine) -> None:
    """No moderation_setting row: the code default is returned."""
    async with AsyncSession(engine) as session:
        value = await load_admin_noise_floor(session)
    assert value == ADMIN_NOISE_FLOOR_DEFAULT


async def test_explicit_value_when_row_exists(engine: AsyncEngine) -> None:
    """A stored row overrides the code default."""
    async with AsyncSession(engine) as session:
        session.add(ModerationSetting(key="admin_noise_floor", value=0.2))
        await session.commit()
    async with AsyncSession(engine) as session:
        value = await load_admin_noise_floor(session)
    assert value == 0.2
