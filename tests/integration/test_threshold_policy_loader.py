"""Loader test: DB rows become a ThresholdPolicy; empty table means defaults."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from cyo_adventure.db.models import ModerationThreshold
from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.thresholds import (
    DEFAULT_THRESHOLD,
    Threshold,
    load_threshold_policy,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_empty_table_yields_default_only_policy(engine: AsyncEngine) -> None:
    """No rows: every lookup resolves to the code default."""
    async with AsyncSession(engine) as session:
        policy = await load_threshold_policy(session)
    assert policy.resolve("3-5", "toxicity") == DEFAULT_THRESHOLD


async def test_rows_load_into_policy(engine: AsyncEngine) -> None:
    """A stored override row resolves for its exact (band, category) key."""
    async with AsyncSession(engine) as session:
        session.add(
            ModerationThreshold(
                age_band="3-5",
                category="violence",
                min_verdict="advisory",
                min_score=0.3,
            )
        )
        await session.commit()
    async with AsyncSession(engine) as session:
        policy = await load_threshold_policy(session)
    assert policy.resolve("3-5", "violence") == Threshold(
        min_verdict=Verdict.ADVISORY, min_score=0.3
    )
    assert policy.resolve("5-8", "violence") == DEFAULT_THRESHOLD
