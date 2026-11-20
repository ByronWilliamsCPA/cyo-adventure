"""Compare the ORM's expected schema against a live database catalog.

The application and its database schema deploy separately: the app image is
pulled onto the host by hand, while migrations are applied by dispatching
``supabase-production.yml``. Nothing tied the two together, and on 2026-08-24
production was found 18 migrations behind ``main`` and returning 500 on every
authenticated adult request while ``/health/ready`` stayed green (register row
``UW-C363``, lessons ``AL-605`` and ``AL-606``). SQLAlchemy validates no mapping
at import or at startup, so a mapped column missing from the live table is not
an error until the first query that selects it.

This module is the single comparator behind both drift signals:

- ``scripts/check_schema_parity.py`` (an operator CLI, which adds the
  migration-history half on top of this), and
- ``api/health.py::check_schema_parity`` (the runtime readiness check), via
  :class:`SchemaParityMonitor`.

What "expected" means: the app's expectation is ``Base.metadata`` itself, the
same table and column objects every ORM query is compiled from. That is the one
source that cannot drift from the code, because it IS the code. A list of
migration versions baked into the image at build time was rejected as the
runtime source: it describes what the repo intended, not what the queries
select, and a seed-only or constraint-only migration would make it report drift
the app cannot feel. The migration list still matters to an operator, which is
why the CLI reports it separately.

Direction matters and is asymmetric on purpose. A table or column the ORM maps
that the database lacks is BEHIND: the first query touching it fails. A table
or column the database has that the ORM does not map is AHEAD: an old image on
a new schema, which reads fine because SQL never selects what it was not asked
for. Only BEHIND is a failure.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeAlias

from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable

    from sqlalchemy import MetaData

__all__ = [
    "CATALOG_QUERY_SQL",
    "ColumnMismatch",
    "LiveCatalog",
    "LiveColumn",
    "SchemaComparison",
    "SchemaParityMonitor",
    "SchemaParityResult",
    "build_live_catalog",
    "compare_schema",
    "expected_catalog",
    "normalize_pg_type",
]

# Every column of every relation in ``public``, read from pg_catalog rather
# than information_schema.
#
# #CRITICAL: security: information_schema.columns lists only columns the
# CURRENT role holds some privilege on. ADR-021 splits the API and worker onto
# separate least-privilege roles, so a table only the worker is granted would
# read as "missing" through information_schema and raise a false BEHIND on the
# API process. pg_attribute is catalog metadata visible to every role, so the
# comparison answers "does the column exist", not "may this role read it".
# #VERIFY: tests/integration/test_schema_parity_check.py builds the catalog
# from a fully migrated database and asserts zero missing columns; the query
# selects names and type text only, never a data row.
#
# relkind: r=table, p=partitioned table, v=view, m=materialized view,
# f=foreign table. A view the ORM maps is as real to a SELECT as a table.
CATALOG_QUERY_SQL = """
SELECT c.relname AS table_name,
       a.attname AS column_name,
       NOT a.attnotnull AS is_nullable,
       format_type(a.atttypid, a.atttypmod) AS data_type
FROM pg_catalog.pg_attribute AS a
JOIN pg_catalog.pg_class AS c ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND a.attnum > 0
  AND NOT a.attisdropped
"""

# Tables in ``public`` that tooling owns and the ORM never maps. Listed so they
# are not reported as AHEAD noise; nothing here can affect a BEHIND verdict.
_TOOLING_TABLES = frozenset({"schema_migrations"})

_VARCHAR_RE = re.compile(r"^varchar(\(\d+\))?$")
_CHAR_RE = re.compile(r"^char(\(\d+\))?$")

# Spellings where SQLAlchemy's compiled DDL type and Postgres's format_type()
# name the same storage type differently. Measured against the full migration
# chain on 2026-11-20: these, plus the varchar/char/numeric rules in
# normalize_pg_type, are the only differences across all 307 mapped columns.
_TYPE_ALIASES = {
    "float": "double precision",
    "double": "double precision",
    "real": "real",
    "timestamp": "timestamp without time zone",
    "time": "time without time zone",
    "bool": "boolean",
    "int": "integer",
    "int4": "integer",
    "int8": "bigint",
    "int2": "smallint",
}


def normalize_pg_type(spelling: str) -> str:
    """Canonicalize a Postgres type name so two spellings of one type compare equal.

    Args:
        spelling: A type as SQLAlchemy compiles it (``VARCHAR(64)``,
            ``NUMERIC(12, 6)``) or as ``format_type`` renders it
            (``character varying(64)``, ``numeric(12,6)``).

    Returns:
        str: A lower-case canonical spelling.
    """
    s = " ".join(spelling.strip().lower().split())
    s = s.replace(", ", ",")
    if _VARCHAR_RE.match(s):
        s = "character varying" + s[len("varchar") :]
    elif _CHAR_RE.match(s):
        s = "character" + s[len("char") :]
    return _TYPE_ALIASES.get(s, s)


@dataclass(frozen=True)
class LiveColumn:
    """One column as the live catalog describes it.

    Attributes:
        is_nullable: Whether the column accepts NULL.
        data_type: ``format_type`` rendering of the column type.
    """

    is_nullable: bool
    data_type: str


# table name -> column name -> column description
LiveCatalog: TypeAlias = dict[str, dict[str, LiveColumn]]


@dataclass(frozen=True)
class _ExpectedColumn:
    nullable: bool
    data_type: str


def build_live_catalog(rows: Iterable[tuple[str, str, bool, str]]) -> LiveCatalog:
    """Fold ``CATALOG_QUERY_SQL`` result rows into a nested lookup.

    Args:
        rows: ``(table_name, column_name, is_nullable, data_type)`` tuples.

    Returns:
        LiveCatalog: table name to column name to :class:`LiveColumn`.
    """
    catalog: LiveCatalog = {}
    for table_name, column_name, is_nullable, data_type in rows:
        catalog.setdefault(table_name, {})[column_name] = LiveColumn(
            is_nullable=bool(is_nullable), data_type=str(data_type)
        )
    return catalog


def expected_catalog(metadata: MetaData) -> dict[str, dict[str, _ExpectedColumn]]:
    """Derive the schema the ORM will query from ``Base.metadata``.

    Only tables in the default (``public``) schema are considered; a table
    declared with another schema is outside what ``CATALOG_QUERY_SQL`` reads.

    Args:
        metadata: The application's ``Base.metadata``.

    Returns:
        dict: table name to column name to its expected nullability and
        canonical type.
    """
    dialect = postgresql.dialect()
    expected: dict[str, dict[str, _ExpectedColumn]] = {}
    for table in metadata.sorted_tables:
        if table.schema not in (None, "public"):
            continue
        columns: dict[str, _ExpectedColumn] = {}
        for column in table.columns:
            columns[column.name] = _ExpectedColumn(
                nullable=bool(column.nullable),
                data_type=normalize_pg_type(column.type.compile(dialect=dialect)),
            )
        expected[table.name] = columns
    return expected


@dataclass(frozen=True)
class ColumnMismatch:
    """A column present on both sides whose definition differs.

    Attributes:
        table: Table name.
        column: Column name.
        expected: The ORM's value (nullability as ``"NULL"``/``"NOT NULL"``,
            or a canonical type).
        actual: The live database's value, same encoding.
    """

    table: str
    column: str
    expected: str
    actual: str


@dataclass(frozen=True)
class SchemaComparison:
    """The result of comparing ``Base.metadata`` to a live catalog.

    ``missing_*`` is BEHIND (the app will fail). ``extra_*`` is AHEAD (an older
    app on a newer schema; tolerable). Nullability and type mismatches are
    reported as warnings and never change the verdict: a live database built by
    the same migration chain that ``tests/integration/test_schema_parity.py``
    proves equal to the ORM has none, so a mismatch here means a pending
    migration that the migration-history half of the CLI names directly.

    Attributes:
        orm_tables: Number of ORM tables compared.
        orm_columns: Number of ORM columns compared.
        missing_tables: ORM tables absent from the database.
        missing_columns: ``(table, column)`` pairs absent from an existing table.
        extra_tables: Database tables the ORM does not map.
        extra_columns: ``(table, column)`` pairs the ORM does not map, on tables
            it does map.
        nullability_mismatches: Columns whose NULL-ability differs.
        type_mismatches: Columns whose canonical type differs.
    """

    orm_tables: int
    orm_columns: int
    missing_tables: tuple[str, ...] = ()
    missing_columns: tuple[tuple[str, str], ...] = ()
    extra_tables: tuple[str, ...] = ()
    extra_columns: tuple[tuple[str, str], ...] = ()
    nullability_mismatches: tuple[ColumnMismatch, ...] = ()
    type_mismatches: tuple[ColumnMismatch, ...] = ()

    @property
    def behind(self) -> bool:
        """Whether the database lacks something the ORM maps."""
        return bool(self.missing_tables or self.missing_columns)

    @property
    def ahead(self) -> bool:
        """Whether the database has tables or columns the ORM does not map."""
        return bool(self.extra_tables or self.extra_columns)

    @property
    def missing_column_count(self) -> int:
        """Columns unavailable to the app, counting every column of a missing table."""
        return len(self.missing_columns)


def _nullability(nullable: bool) -> str:
    return "NULL" if nullable else "NOT NULL"


def compare_schema(metadata: MetaData, live: LiveCatalog) -> SchemaComparison:
    """Compare the ORM's tables and columns to a live catalog.

    Args:
        metadata: The application's ``Base.metadata``.
        live: The catalog built from ``CATALOG_QUERY_SQL``.

    Returns:
        SchemaComparison: Every difference, each list sorted for stable output.
    """
    expected = expected_catalog(metadata)
    missing_tables: list[str] = []
    missing_columns: list[tuple[str, str]] = []
    extra_columns: list[tuple[str, str]] = []
    nullability: list[ColumnMismatch] = []
    types: list[ColumnMismatch] = []

    for table, columns in expected.items():
        live_columns = live.get(table)
        if live_columns is None:
            missing_tables.append(table)
            missing_columns.extend((table, name) for name in columns)
            continue
        for name, want in columns.items():
            have = live_columns.get(name)
            if have is None:
                missing_columns.append((table, name))
                continue
            if have.is_nullable != want.nullable:
                nullability.append(
                    ColumnMismatch(
                        table,
                        name,
                        _nullability(want.nullable),
                        _nullability(have.is_nullable),
                    )
                )
            have_type = normalize_pg_type(have.data_type)
            if have_type != want.data_type:
                types.append(ColumnMismatch(table, name, want.data_type, have_type))
        extra_columns.extend(
            (table, name) for name in live_columns if name not in columns
        )

    extra_tables = [t for t in live if t not in expected and t not in _TOOLING_TABLES]

    return SchemaComparison(
        orm_tables=len(expected),
        orm_columns=sum(len(c) for c in expected.values()),
        missing_tables=tuple(sorted(missing_tables)),
        missing_columns=tuple(sorted(missing_columns)),
        extra_tables=tuple(sorted(extra_tables)),
        extra_columns=tuple(sorted(extra_columns)),
        nullability_mismatches=tuple(
            sorted(nullability, key=lambda m: (m.table, m.column))
        ),
        type_mismatches=tuple(sorted(types, key=lambda m: (m.table, m.column))),
    )


# ---------------------------------------------------------------------------
# Runtime monitor
# ---------------------------------------------------------------------------

ParityState: TypeAlias = Literal["ok", "behind", "unknown"]


@dataclass(frozen=True)
class SchemaParityResult:
    """One runtime measurement, cached by :class:`SchemaParityMonitor`.

    Attributes:
        state: ``"ok"`` (in parity or ahead), ``"behind"`` (the ORM maps
            something the database lacks), or ``"unknown"`` (the catalog query
            failed, so nothing was measured).
        measured_at: ``time.monotonic()`` when the measurement finished.
        comparison: The full comparison, absent when ``state == "unknown"``.
        error_type: Exception class name when the measurement failed. Never
            the message: a driver error can carry host or DSN detail.
    """

    state: ParityState
    measured_at: float
    comparison: SchemaComparison | None = None
    error_type: str | None = None


@dataclass
class SchemaParityMonitor:
    """Compute schema parity rarely, off the request path, and cache the answer.

    One catalog query (a few hundred rows of names, no data) per ``ttl_seconds``
    at most, regardless of how often readiness is polled. Concurrent callers
    that find the cache stale share one in-flight measurement through the lock
    rather than each issuing the query.

    #ASSUME: timing: a five-minute TTL is the trade between "the signal clears
    soon after the owner applies migrations" and "the probe adds no load". An
    unknown result retries after ``retry_seconds`` instead, because a transient
    connection blip should not suppress the signal for a full TTL.
    #VERIFY: tests/unit/test_schema_parity.py::TestSchemaParityMonitor pins the
    cache hit, the TTL expiry, the shorter unknown retry, and single-flight
    behaviour under concurrent callers.

    Attributes:
        measure: Coroutine returning a fresh :class:`SchemaComparison`. Raising
            is allowed and yields ``state="unknown"``.
        ttl_seconds: How long an ``ok`` or ``behind`` result stays fresh.
        retry_seconds: How long an ``unknown`` result stays fresh.
        clock: Monotonic clock, injectable for tests.
    """

    measure: Callable[[], Awaitable[SchemaComparison]]
    ttl_seconds: float = 300.0
    retry_seconds: float = 60.0
    clock: Callable[[], float] = time.monotonic
    _cached: SchemaParityResult | None = field(default=None, init=False)
    _lock: asyncio.Lock | None = field(default=None, init=False)
    _lock_loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)

    @property
    def cached(self) -> SchemaParityResult | None:
        """The last measurement, fresh or not, without triggering a new one."""
        return self._cached

    def _loop_lock(self) -> asyncio.Lock:
        """Return a lock bound to the running event loop.

        #EDGE: concurrency: an ``asyncio.Lock`` binds to the first loop that
        waits on it. The monitor is module-level and outlives any one loop
        (each test client, or a uvicorn reload, runs its own), so a lock is
        created per loop rather than once at import.
        #VERIFY: TestSchemaParityMonitor::test_survives_a_new_event_loop.

        Returns:
            asyncio.Lock: The lock for the current loop.
        """
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    def _fresh(self, result: SchemaParityResult) -> bool:
        window = self.retry_seconds if result.state == "unknown" else self.ttl_seconds
        return self.clock() - result.measured_at < window

    async def current(self) -> tuple[SchemaParityResult, bool]:
        """Return a fresh-enough result, measuring only when the cache is stale.

        Returns:
            tuple[SchemaParityResult, bool]: The result, and whether this call
            performed a new measurement (callers log only on a new one, so a
            readiness poll every few seconds does not repeat the same line).
        """
        cached = self._cached
        if cached is not None and self._fresh(cached):
            return cached, False
        async with self._loop_lock():
            # #EDGE: concurrency: re-check under the lock; a caller that queued
            # behind an in-flight measurement must reuse it, not repeat it.
            # #VERIFY: TestSchemaParityMonitor::test_concurrent_callers_share_one_measurement.
            cached = self._cached
            if cached is not None and self._fresh(cached):
                return cached, False
            result = await self._measure_once()
            self._cached = result
            return result, True

    async def _measure_once(self) -> SchemaParityResult:
        try:
            comparison = await self.measure()
        except Exception as exc:  # noqa: BLE001 -- a diagnostic must never raise into readiness
            return SchemaParityResult(
                state="unknown",
                measured_at=self.clock(),
                error_type=type(exc).__name__,
            )
        state: ParityState = "behind" if comparison.behind else "ok"
        return SchemaParityResult(
            state=state, measured_at=self.clock(), comparison=comparison
        )
