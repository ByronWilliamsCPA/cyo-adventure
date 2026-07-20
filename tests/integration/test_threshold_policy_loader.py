"""Loader test: DB rows become a ThresholdPolicy; empty table means defaults."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from cyo_adventure.db.models import (
    Family,
    ModerationThreshold,
    ModerationThresholdAudit,
    User,
)
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


async def test_bad_min_verdict_insert_rejected_by_check(engine: AsyncEngine) -> None:
    """ck_moderation_threshold_min_verdict rejects an out-of-enum value."""
    async with AsyncSession(engine) as session:
        session.add(
            ModerationThreshold(
                age_band="3-5",
                category="violence",
                min_verdict="bogus",
                min_score=None,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_out_of_range_min_score_rejected_by_check(engine: AsyncEngine) -> None:
    """ck_moderation_threshold_min_score rejects a score outside [0.0, 1.0]."""
    async with AsyncSession(engine) as session:
        session.add(
            ModerationThreshold(
                age_band="3-5",
                category="violence",
                min_verdict="advisory",
                min_score=1.5,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_unknown_age_band_insert_rejected_by_check(engine: AsyncEngine) -> None:
    """ck_moderation_threshold_age_band rejects a band outside the AgeBand enum."""
    async with AsyncSession(engine) as session:
        session.add(
            ModerationThreshold(
                age_band="2-4",
                category="violence",
                min_verdict="advisory",
                min_score=None,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_duplicate_band_category_rejected_by_unique_constraint(
    engine: AsyncEngine,
) -> None:
    """uq_moderation_threshold_band_category rejects a repeated (band, category)."""
    async with AsyncSession(engine) as session:
        session.add(
            ModerationThreshold(
                age_band="3-5", category="violence", min_verdict="advisory"
            )
        )
        await session.commit()
    async with AsyncSession(engine) as session:
        session.add(
            ModerationThreshold(age_band="3-5", category="violence", min_verdict="flag")
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_audit_action_check_rejects_unknown_action(engine: AsyncEngine) -> None:
    """ck_moderation_threshold_audit_action rejects an action outside upsert/delete."""
    async with AsyncSession(engine) as session:
        fam = Family(name="AuditActionCheckFamily")
        session.add(fam)
        await session.flush()
        admin = User(
            family_id=fam.id,
            role="admin",
            authn_subject="audit-check-admin",
            is_admin=True,
        )
        session.add(admin)
        await session.flush()
        session.add(
            ModerationThresholdAudit(
                age_band="3-5",
                category="violence",
                action="edited",
                changed_by=admin.id,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_malformed_min_verdict_row_is_skipped_with_warning(
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    """A row that bypasses the CHECK (constraint dropped, e.g. pre-constraint
    backfill) is skipped by the loader, logged, and falls back to the default.
    """
    # #EDGE: data-integrity: `engine` shares one schema for every test in this
    # xdist worker (tests/integration/conftest.py TRUNCATEs data between tests
    # but does not rebuild DDL), so a dropped constraint here would otherwise
    # leak into later tests, e.g. test_bad_min_verdict_insert_rejected_by_check.
    # #VERIFY: restore the constraint in `finally`, matching the CHECK clause
    # in db/models.py::ModerationThreshold / supabase/migrations/20260710000000_baseline.sql.
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE moderation_threshold "
                "DROP CONSTRAINT ck_moderation_threshold_min_verdict"
            )
        )
    try:
        async with AsyncSession(engine) as session:
            session.add(
                ModerationThreshold(
                    age_band="3-5",
                    category="violence",
                    min_verdict="bogus",
                    min_score=None,
                )
            )
            await session.commit()
        with caplog.at_level("WARNING"):
            async with AsyncSession(engine) as session:
                policy = await load_threshold_policy(session)
        assert policy.resolve("3-5", "violence") == DEFAULT_THRESHOLD
        assert "moderation_threshold_row_malformed" in caplog.text
        assert "violence" in caplog.text
    finally:
        # The malformed row itself would violate the CHECK being restored, so
        # it must be cleared first (the row's own id is irrelevant; delete by
        # the malformed value to avoid depending on prior statements above).
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM moderation_threshold WHERE min_verdict = 'bogus'")
            )
            await conn.execute(
                text(
                    "ALTER TABLE moderation_threshold "
                    "ADD CONSTRAINT ck_moderation_threshold_min_verdict "
                    "CHECK (min_verdict IN "
                    "('advisory', 'flag', 'block'))"
                )
            )
