"""The schema-drift detectors against a real migrated Postgres (UW-C363).

Exercises ``scripts/check_schema_parity.py`` end to end and the runtime
readiness measurement (``api/health.py::_measure_schema_parity``) on databases
built from the real ``supabase/migrations`` chain, for each verdict:

- parity: the full chain, with every version recorded as applied;
- behind: the chain minus its newest migration (the shape production was found
  in on 2026-08-24, and very likely again after 20260908000000);
- ahead: the full chain plus a column and a history row this checkout does not
  know (a newer schema under an older image).

``test_schema_parity.py`` is the CI guard that the migrations and the ORM
agree; this file proves the detectors that compare a LIVE database to both.
The history table is created here with the Supabase CLI's DDL, since the
testcontainers database is migrated by applying the SQL directly rather than
through the CLI; ``supabase-ci.yml`` runs the script against a CLI-built stack.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration._migration_utils import MIGRATIONS, create_migrated_database

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.core.schema_parity import SchemaComparison

_SPEC = importlib.util.spec_from_file_location(
    "check_schema_parity",
    Path(__file__).resolve().parents[2] / "scripts" / "check_schema_parity.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
parity_script = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = parity_script
_SPEC.loader.exec_module(parity_script)

pytestmark = pytest.mark.integration

_URL_ENV = "SCHEMA_PARITY_DATABASE_URL"
_NEWEST = MIGRATIONS[-1]


def _version(path: Path) -> str:
    return path.name.split("_", 1)[0]


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _build(
    pg_url: str,
    db_name: str,
    migrations: Sequence[Path],
    recorded: Sequence[str],
    extra_sql: str = "",
) -> str:
    url = await create_migrated_database(pg_url, db_name, migrations)
    conn = await asyncpg.connect(_plain(url))
    try:
        # The CLI's own bookkeeping DDL (version is the primary key; name and
        # statements arrived in later CLI releases and are unused here).
        await conn.execute(
            "CREATE SCHEMA IF NOT EXISTS supabase_migrations;"
            "CREATE TABLE IF NOT EXISTS supabase_migrations.schema_migrations "
            "(version text PRIMARY KEY, statements text[], name text);"
        )
        await conn.executemany(
            "INSERT INTO supabase_migrations.schema_migrations (version) VALUES ($1)",
            [(v,) for v in recorded],
        )
        if extra_sql:
            await conn.execute(extra_sql)
    finally:
        await conn.close()
    return url


def _run_script(
    url: str, capsys: pytest.CaptureFixture[str], *args: str
) -> tuple[int, str]:
    with patch.dict("os.environ", {_URL_ENV: url}):
        code = parity_script.main(list(args))
    return code, capsys.readouterr().out


async def _measure_runtime(url: str) -> SchemaComparison:
    from cyo_adventure.api import health

    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def session() -> AsyncGenerator[AsyncSession]:
        async with factory() as s:
            yield s

    try:
        with patch("cyo_adventure.core.database.get_session", side_effect=session):
            return await health._measure_schema_parity()
    finally:
        await engine.dispose()


def test_full_chain_is_in_parity_with_no_warnings(
    pg_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    url = asyncio.run(
        _build(pg_url, "sp_parity", MIGRATIONS, [_version(p) for p in MIGRATIONS])
    )

    code, out = _run_script(url, capsys, "--json")
    report = json.loads(out)

    assert code == 0
    assert report["verdict"] == "IN PARITY"
    assert report["migrations"]["pending"] == []
    assert report["migrations"]["unknown_applied"] == []
    assert report["schema"]["missing_columns"] == []
    assert report["schema"]["extra_columns"] == []
    # The noise guard: a database built by the real chain must produce zero
    # nullability or type warnings, or the warnings would train people to
    # ignore the report.
    assert report["schema"]["warnings"] == {"nullability": [], "type": []}
    assert report["schema"]["orm_columns"] > 300

    runtime = asyncio.run(_measure_runtime(url))
    assert not runtime.behind
    assert not runtime.ahead


def test_missing_newest_migration_is_behind(
    pg_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    applied = MIGRATIONS[:-1]
    url = asyncio.run(
        _build(pg_url, "sp_behind", applied, [_version(p) for p in applied])
    )

    code, out = _run_script(url, capsys)

    assert code == 1
    assert out.startswith("VERDICT: DATABASE BEHIND")
    assert _NEWEST.stem in out
    # The newest migration adds the cover-review columns the ORM maps; their
    # absence is what 500s the storybook-version pages.
    assert "storybook_version.cover_review_verdict" in out
    assert "postgresql://" not in out

    runtime = asyncio.run(_measure_runtime(url))
    assert runtime.behind
    assert ("storybook_version", "cover_review_verdict") in runtime.missing_columns


def test_recorded_but_schema_present_pending_migration_is_still_behind(
    pg_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """History alone flags a pending migration even when every column exists.

    A seed or constraint migration adds no column, so the ORM half cannot see
    it; the history half must.
    """
    recorded = [_version(p) for p in MIGRATIONS[:-1]]
    url = asyncio.run(_build(pg_url, "sp_history_behind", MIGRATIONS, recorded))

    code, out = _run_script(url, capsys, "--json")
    report = json.loads(out)

    assert code == 1
    assert report["migrations"]["pending"] == [_NEWEST.stem]
    assert report["schema"]["missing_columns"] == []


def test_unknown_column_and_history_row_is_ahead(
    pg_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    recorded = [_version(p) for p in MIGRATIONS] + ["29991231000000"]
    url = asyncio.run(
        _build(
            pg_url,
            "sp_ahead",
            MIGRATIONS,
            recorded,
            extra_sql='ALTER TABLE "family" ADD COLUMN future_col text;',
        )
    )

    code, out = _run_script(url, capsys, "--json")
    report = json.loads(out)
    assert code == 0
    assert report["verdict"] == "DATABASE AHEAD"
    assert report["migrations"]["unknown_applied"] == ["29991231000000"]
    assert report["schema"]["extra_columns"] == ["family.future_col"]

    strict_code, _ = _run_script(url, capsys, "--fail-on-ahead")
    assert strict_code == 4

    runtime = asyncio.run(_measure_runtime(url))
    assert not runtime.behind
    assert runtime.ahead


def test_missing_history_table_is_incomplete_not_parity(
    pg_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    url = asyncio.run(create_migrated_database(pg_url, "sp_no_history"))

    code, out = _run_script(url, capsys)
    assert code == 3
    assert out.startswith("VERDICT: INCOMPLETE")

    schema_only_code, schema_only_out = _run_script(url, capsys, "--schema-only")
    assert schema_only_code == 0
    assert schema_only_out.startswith("VERDICT: IN PARITY")
