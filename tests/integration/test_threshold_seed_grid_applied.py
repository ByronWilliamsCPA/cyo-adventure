"""`RS-B2`: the seed grid, verified against a freshly MIGRATED database.

The plan's verification instruction for this task is explicit about why this
file exists rather than an assertion against a developer's existing database:

    #CRITICAL: data integrity: a conditional migration guard exits 0 having
    done nothing when its subject is ABSENT, not only when already applied, and
    editing an applied migration is inert because Supabase tracks by version.
    #VERIFY: assert post-seed row count against the expected (band, category)
    product in a test that runs against a freshly migrated schema, not against
    a developer's existing database.

The integration suite's own schema is built from ORM metadata
(``Base.metadata.create_all``), which runs no migration and therefore seeds
nothing, so a test against the ordinary ``sessions`` fixture would find zero
rows and prove nothing about the seed either way. Every test here applies the
whole ``supabase/migrations/*.sql`` chain to a brand-new database first.

The unit companion (tests/unit/test_threshold_seed_grid.py) checks that the SQL
SAYS the right thing; this module checks that Postgres DOES it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.thresholds import (
    GRADED_SCORE_CATEGORIES,
    Threshold,
    ThresholdPolicy,
    admin_noise_floor_for,
)
from cyo_adventure.storybook.models import AgeBand
from tests.integration._migration_utils import (
    MIGRATIONS,
    create_migrated_database,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_EXPECTED_ROWS = len(AgeBand) * len(GRADED_SCORE_CATEGORIES)


async def _seeded_rows(
    pg_url: str, db_name: str
) -> list[tuple[str, str, str, float | None]]:
    """Apply every migration to a fresh database and read the seeded grid back.

    Deliberately NOT the shared ``sessions``/``engine`` fixtures: those build
    the schema from ``Base.metadata.create_all`` and apply no migration at all,
    so the seeded grid this module is about would simply be absent and every
    assertion below would pass or fail for the wrong reason. A rolled-back
    transaction over a pre-existing database has the same problem from the
    other side; it cannot distinguish "the migration seeded this" from "a
    developer's database already held it". Same reason, same helper, as
    ``test_schema_parity.py`` and the RLS enforcement suites; see the
    ADR-021/ADR-022 harness note at the foot of ``tests/integration/conftest.py``.
    """
    mig_url = await create_migrated_database(pg_url, db_name)
    engine = create_async_engine(mig_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT age_band, category, min_verdict, min_score "
                    "FROM public.moderation_threshold "
                    "ORDER BY age_band, category"
                )
            )
            return [(str(r[0]), str(r[1]), str(r[2]), r[3]) for r in result.fetchall()]
    finally:
        await engine.dispose()


async def test_the_migrated_grid_holds_exactly_the_expected_pairs(
    pg_url: str,
) -> None:
    """36 rows, one per (band, graded category), no more and no fewer.

    Row COUNT alone would pass on 36 wrong pairs, so the pair SET is asserted
    and the count is asserted as its consequence. This is the assertion the
    plan asked for.

    Args:
        pg_url: Public alias for the session-scoped testcontainers Postgres URL
            fixture (see ``tests/integration/conftest.py``).
    """
    rows = await _seeded_rows(pg_url, "threshold_seed_grid")
    assert len(rows) == _EXPECTED_ROWS
    assert {(band, category) for band, category, _, _ in rows} == {
        (band.value, category)
        for band in AgeBand
        for category in GRADED_SCORE_CATEGORIES
    }


async def test_every_migrated_row_is_behaviour_preserving(pg_url: str) -> None:
    """No seeded row may change what either lane surfaces.

    Asserted through the live resolver rather than by reading the columns,
    because "min_score IS NULL" only matters insofar as
    ``admin_noise_floor_for`` treats it as "use the flat floor". Each seeded
    row is rebuilt into a real ThresholdPolicy and compared against an EMPTY
    policy on the same input: equality is the behaviour-preservation claim, and
    it fails the moment a row ships a concrete cutoff.

    Args:
        pg_url: Public alias for the session-scoped testcontainers Postgres URL
            fixture.
    """
    rows = await _seeded_rows(pg_url, "threshold_seed_preserving")
    assert rows, "no seeded rows to check"
    empty = ThresholdPolicy(rows={})
    flat = 0.05
    for band, category, min_verdict, min_score in rows:
        assert min_verdict == "flag", f"{band}/{category} shipped a non-default verdict"
        assert min_score is None, f"{band}/{category} shipped a concrete cutoff"
        seeded = ThresholdPolicy(
            rows={
                (band, category): Threshold(
                    min_verdict=Verdict(min_verdict), min_score=min_score
                )
            }
        )
        assert admin_noise_floor_for(
            category, age_band=band, policy=seeded, flat_floor=flat
        ) == admin_noise_floor_for(
            category, age_band=band, policy=empty, flat_floor=flat
        )
        # And the guardian lane, which gates on the verdict, is unchanged too.
        assert seeded.resolve(band, category) == empty.resolve(band, category)


async def test_reapplying_the_seed_does_not_duplicate_or_revert(
    pg_url: str,
) -> None:
    """The seed is idempotent AND non-destructive.

    Two properties in one test because they share a setup and are only
    meaningful together: running the INSERT a second time must add no row (the
    unique constraint plus ON CONFLICT), and must not overwrite a cutoff an
    operator has since set (DO NOTHING rather than DO UPDATE). A staging
    restore replays the whole chain against a database that already holds
    operator edits, so the second property is the one that protects real
    decisions.

    Args:
        pg_url: Public alias for the session-scoped testcontainers Postgres URL
            fixture.
    """
    seed = next(
        path
        for path in MIGRATIONS
        if path.name == "20260831120000_seed_moderation_threshold_grid.sql"
    )
    # A standalone engine again, for the reason given on ``_seeded_rows``, plus
    # one specific to this test: replaying the seed has to COMMIT so the second
    # application sees the first one's rows and the operator's edit. Inside the
    # shared session fixture's rolled-back transaction there is no second
    # application to observe, so the idempotency claim would be untestable.
    mig_url = await create_migrated_database(pg_url, "threshold_seed_replay")
    engine = create_async_engine(mig_url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            # An operator tunes one cell after the first application.
            await conn.execute(
                text(
                    "UPDATE public.moderation_threshold SET min_score = 0.42 "
                    "WHERE age_band = '13-16' AND category = 'violence'"
                )
            )
        async with engine.begin() as conn:
            await conn.exec_driver_sql(seed.read_text(encoding="utf-8"))
        async with engine.connect() as conn:
            total = (
                await conn.execute(
                    text("SELECT count(*) FROM public.moderation_threshold")
                )
            ).scalar_one()
            tuned = (
                await conn.execute(
                    text(
                        "SELECT min_score FROM public.moderation_threshold "
                        "WHERE age_band = '13-16' AND category = 'violence'"
                    )
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    assert total == _EXPECTED_ROWS, "the replay duplicated rows"
    assert tuned == pytest.approx(0.42), "the replay reverted an operator's cutoff"
