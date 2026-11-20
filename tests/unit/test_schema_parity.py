"""Unit tests for cyo_adventure.core.schema_parity (no database).

The comparator is exercised against a small hand-built ``MetaData`` so each
direction (behind, ahead, warnings) is pinned in isolation; the integration
suite (tests/integration/test_schema_parity_check.py) runs it against the real
ORM and the real migration chain.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
)

from cyo_adventure.core.schema_parity import (
    LiveCatalog,
    LiveColumn,
    SchemaComparison,
    SchemaParityMonitor,
    build_live_catalog,
    compare_schema,
    normalize_pg_type,
)

pytestmark = pytest.mark.unit


def _metadata() -> MetaData:
    md = MetaData()
    Table(
        "family",
        md,
        Column("id", Integer, primary_key=True),
        Column("name", String(120), nullable=False),
        Column("note", Text, nullable=True),
    )
    Table(
        "story",
        md,
        Column("id", Integer, primary_key=True),
        Column("score", Float, nullable=True),
        Column("cost", Numeric(12, 6), nullable=True),
        Column("published", Boolean, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    Table("elsewhere", md, Column("id", Integer, primary_key=True), schema="audit")
    return md


def _live_in_parity() -> LiveCatalog:
    return build_live_catalog(
        [
            ("family", "id", False, "integer"),
            ("family", "name", False, "character varying(120)"),
            ("family", "note", True, "text"),
            ("story", "id", False, "integer"),
            ("story", "score", True, "double precision"),
            ("story", "cost", True, "numeric(12,6)"),
            ("story", "published", False, "boolean"),
            ("story", "created_at", False, "timestamp with time zone"),
        ]
    )


class TestNormalizePgType:
    @pytest.mark.parametrize(
        ("orm", "pg"),
        [
            ("VARCHAR(64)", "character varying(64)"),
            ("VARCHAR", "character varying"),
            ("NUMERIC(12, 6)", "numeric(12,6)"),
            ("FLOAT", "double precision"),
            ("TIMESTAMP WITH TIME ZONE", "timestamp with time zone"),
            ("TIMESTAMP", "timestamp without time zone"),
            ("CHAR(2)", "character(2)"),
            ("UUID", "uuid"),
            ("JSONB", "jsonb"),
        ],
    )
    def test_compiled_and_catalog_spellings_meet(self, orm: str, pg: str) -> None:
        assert normalize_pg_type(orm) == normalize_pg_type(pg)

    def test_different_lengths_stay_different(self) -> None:
        assert normalize_pg_type("VARCHAR(10)") != normalize_pg_type(
            "character varying(20)"
        )


class TestCompareSchema:
    def test_identical_schema_is_in_parity(self) -> None:
        result = compare_schema(_metadata(), _live_in_parity())
        assert result == SchemaComparison(orm_tables=2, orm_columns=8)
        assert not result.behind
        assert not result.ahead

    def test_table_in_another_schema_is_not_compared(self) -> None:
        result = compare_schema(_metadata(), _live_in_parity())
        assert "elsewhere" not in result.missing_tables

    def test_missing_column_is_behind(self) -> None:
        live = _live_in_parity()
        del live["story"]["published"]
        result = compare_schema(_metadata(), live)
        assert result.behind
        assert result.missing_columns == (("story", "published"),)
        assert result.missing_tables == ()

    def test_missing_table_counts_every_column(self) -> None:
        live = _live_in_parity()
        del live["family"]
        result = compare_schema(_metadata(), live)
        assert result.behind
        assert result.missing_tables == ("family",)
        assert result.missing_column_count == 3

    def test_extra_column_and_table_are_ahead_not_behind(self) -> None:
        live = _live_in_parity()
        live["family"]["future"] = LiveColumn(is_nullable=True, data_type="text")
        live["brand_new"] = {"id": LiveColumn(is_nullable=False, data_type="integer")}
        result = compare_schema(_metadata(), live)
        assert not result.behind
        assert result.ahead
        assert result.extra_columns == (("family", "future"),)
        assert result.extra_tables == ("brand_new",)

    def test_tooling_table_is_not_reported_as_ahead(self) -> None:
        live = _live_in_parity()
        live["schema_migrations"] = {
            "version": LiveColumn(is_nullable=False, data_type="text")
        }
        assert not compare_schema(_metadata(), live).ahead

    def test_nullability_and_type_differences_warn_without_changing_verdict(
        self,
    ) -> None:
        live = _live_in_parity()
        live["family"]["note"] = LiveColumn(is_nullable=False, data_type="text")
        live["family"]["name"] = LiveColumn(
            is_nullable=False, data_type="character varying(64)"
        )
        result = compare_schema(_metadata(), live)
        assert not result.behind
        assert not result.ahead
        assert [
            (m.column, m.expected, m.actual) for m in result.nullability_mismatches
        ] == [("note", "NULL", "NOT NULL")]
        assert [(m.column, m.expected, m.actual) for m in result.type_mismatches] == [
            ("name", "character varying(120)", "character varying(64)")
        ]


def _comparison(*, behind: bool) -> SchemaComparison:
    if behind:
        return SchemaComparison(
            orm_tables=1, orm_columns=1, missing_columns=(("t", "c"),)
        )
    return SchemaComparison(orm_tables=1, orm_columns=1)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TestSchemaParityMonitor:
    def test_result_is_cached_within_ttl(self) -> None:
        calls = 0

        async def measure() -> SchemaComparison:
            nonlocal calls
            calls += 1
            return _comparison(behind=False)

        clock = _Clock()
        monitor = SchemaParityMonitor(measure=measure, ttl_seconds=300, clock=clock)

        async def run() -> list[bool]:
            fresh: list[bool] = []
            for _ in range(3):
                _, was_fresh = await monitor.current()
                fresh.append(was_fresh)
                clock.now += 10
            return fresh

        assert asyncio.run(run()) == [True, False, False]
        assert calls == 1

    def test_measurement_repeats_after_ttl(self) -> None:
        outcomes = iter([True, False])

        async def measure() -> SchemaComparison:
            return _comparison(behind=next(outcomes))

        clock = _Clock()
        monitor = SchemaParityMonitor(measure=measure, ttl_seconds=300, clock=clock)

        async def run() -> tuple[str, str]:
            first, _ = await monitor.current()
            clock.now += 301
            second, _ = await monitor.current()
            return first.state, second.state

        assert asyncio.run(run()) == ("behind", "ok")

    def test_failure_is_unknown_with_class_name_only_and_retries_sooner(
        self,
    ) -> None:
        calls = 0

        async def measure() -> SchemaComparison:
            nonlocal calls
            calls += 1
            msg = "connect to postgresql://u:hunter2@db.internal failed"
            raise ConnectionError(msg)

        clock = _Clock()
        monitor = SchemaParityMonitor(
            measure=measure, ttl_seconds=300, retry_seconds=60, clock=clock
        )

        async def run() -> None:
            result, _ = await monitor.current()
            assert result.state == "unknown"
            assert result.error_type == "ConnectionError"
            assert result.comparison is None
            assert "hunter2" not in repr(result)
            clock.now += 61
            _ = await monitor.current()

        asyncio.run(run())
        assert calls == 2

    def test_concurrent_callers_share_one_measurement(self) -> None:
        calls = 0

        async def measure() -> SchemaComparison:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return _comparison(behind=True)

        monitor = SchemaParityMonitor(measure=measure)

        async def run() -> list[str]:
            results = await asyncio.gather(*(monitor.current() for _ in range(5)))
            return [r.state for r, _ in results]

        assert asyncio.run(run()) == ["behind"] * 5
        assert calls == 1

    def test_survives_a_new_event_loop(self) -> None:
        async def measure() -> SchemaComparison:
            await asyncio.sleep(0)
            return _comparison(behind=False)

        clock = _Clock()
        monitor = SchemaParityMonitor(measure=measure, ttl_seconds=1, clock=clock)

        async def contended() -> None:
            _ = await asyncio.gather(monitor.current(), monitor.current())

        asyncio.run(contended())
        clock.now += 5
        # A second loop must get a fresh lock, not one bound to the first.
        asyncio.run(contended())
        cached = monitor.cached
        assert cached is not None
        assert cached.state == "ok"
