#!/usr/bin/env python3
"""Report whether a live database matches this checkout's migrations and ORM.

Read-only. Answers the question register row ``UW-C363`` says nothing
answered: is this database behind the code that is about to run on it (or
already running on it)?

Two independent halves, reported separately:

1. **Migration history.** Files in ``supabase/migrations/`` versus the
   versions the Supabase CLI recorded in
   ``supabase_migrations.schema_migrations``. Lists migrations in the repo but
   not applied (pending) and versions applied but unknown to this checkout.
2. **ORM schema.** Every table and column in ``Base.metadata`` versus the live
   catalog (``pg_catalog``, so the answer does not depend on the connecting
   role's grants). Lists what the ORM maps that the database lacks, and what
   the database has that the ORM does not map. Nullability and type
   differences are listed as warnings that never change the verdict.

Verdicts and exit codes::

    IN PARITY          0
    DATABASE AHEAD     0   old app on a newer schema; usually tolerable
                           (exit 4 instead with --fail-on-ahead)
    DATABASE BEHIND    1   the app would fail; apply migrations first
    INCOMPLETE         3   migration history unreadable; schema half reported
    (error)            2   no URL, cannot connect, or the query failed

Run it from a checkout of the ref you are deploying (or have deployed): the
comparison is against THIS checkout's migrations and models.

Usage::

    export SCHEMA_PARITY_DATABASE_URL='postgresql://...'   # never on argv
    uv run python scripts/check_schema_parity.py
    uv run python scripts/check_schema_parity.py --json

#CRITICAL: security: the database URL is read from an environment variable
only (never a CLI argument, which would land in shell history and ``ps``), and
is never printed, logged, or echoed in an error. Connection errors report the
exception class name only, because a driver message can carry host or user
detail. Output is names of tables, columns, and migrations, never a data row,
so a report is safe to paste into an issue.
#VERIFY: tests/unit/test_check_schema_parity_script.py asserts the URL and
its password never appear in output on success or on a connection failure.

#CRITICAL: security: every statement runs inside a READ ONLY transaction with
a statement timeout, and only reads ``pg_catalog`` and
``supabase_migrations.schema_migrations``. A role with no write privilege at
all is sufficient (see docs/operations/runbook.md section 2.5).
#VERIFY: tests/integration/test_schema_parity_check.py runs this against a
real migrated Postgres.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from unittest import mock

import asyncpg

from cyo_adventure.core.schema_parity import (
    CATALOG_QUERY_SQL,
    SchemaComparison,
    build_live_catalog,
    compare_schema,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy import MetaData

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
DEFAULT_URL_ENV = "SCHEMA_PARITY_DATABASE_URL"

EXIT_OK = 0
EXIT_BEHIND = 1
EXIT_ERROR = 2
EXIT_INCOMPLETE = 3
EXIT_AHEAD = 4

VERDICT_PARITY = "IN PARITY"
VERDICT_BEHIND = "DATABASE BEHIND"
VERDICT_AHEAD = "DATABASE AHEAD"
VERDICT_INCOMPLETE = "INCOMPLETE"

# The Supabase CLI keys schema_migrations on the leading digits of the
# filename (``<version>_<name>.sql``) and skips files that do not match.
_MIGRATION_FILE_RE = re.compile(r"^(?P<version>\d+)_(?P<name>.+)\.sql$")

# #ASSUME: external resources: the Supabase CLI records each applied migration
# as a row in supabase_migrations.schema_migrations keyed by a text `version`
# column holding the filename's digit prefix (ADR-012; the CLI's own DDL).
# Only `version` is read, because later CLI releases added optional columns
# (name, statements, created_by) that an older history table lacks.
# #VERIFY: .github/workflows/supabase-ci.yml runs this script against a stack
# the real CLI built and migrated, and fails unless the verdict is IN PARITY.
_HISTORY_TABLE = "supabase_migrations.schema_migrations"
_HISTORY_EXISTS_SQL = "SELECT to_regclass('supabase_migrations.schema_migrations')"
_HISTORY_SQL = "SELECT version::text FROM supabase_migrations.schema_migrations"

_STATEMENT_TIMEOUT_SQL = "SET LOCAL statement_timeout = '30s'"
_CONNECT_TIMEOUT_SECONDS = 15

CatalogRow = tuple[str, str, bool, str]


class _Connection(Protocol):
    """The slice of ``asyncpg.Connection`` this script uses (asyncpg ships no stubs)."""

    async def execute(self, query: str) -> str: ...

    async def fetch(self, query: str) -> list[Sequence[object]]: ...

    async def fetchval(self, query: str) -> object: ...

    def transaction(
        self, *, readonly: bool = False
    ) -> AbstractAsyncContextManager[object]: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class RepoMigration:
    """A migration file in the checkout.

    Attributes:
        version: The digit prefix the CLI records.
        filename: The file's basename without ``.sql``.
    """

    version: str
    filename: str


@dataclass
class HistoryHalf:
    """The migration-history comparison.

    Attributes:
        available: Whether the history table could be read.
        unavailable_reason: Why not, when ``available`` is False: a fixed
            description or an exception class name, never a driver message.
        repo_count: Migrations in the checkout.
        applied_count: Versions recorded as applied.
        repo_head: Newest repo version.
        applied_head: Newest applied version.
        pending: Repo migrations not applied, oldest first.
        pending_before_head: The part of ``pending`` that sorts before the
            applied head; ``supabase db push`` without ``--include-all``
            skips these, so they stay pending after a "successful" push.
        unknown_applied: Applied versions with no file in this checkout.
    """

    available: bool
    unavailable_reason: str | None = None
    repo_count: int = 0
    applied_count: int = 0
    repo_head: str | None = None
    applied_head: str | None = None
    pending: list[RepoMigration] = field(default_factory=list[RepoMigration])
    pending_before_head: list[RepoMigration] = field(
        default_factory=list[RepoMigration]
    )
    unknown_applied: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class DatabaseRead:
    """Everything read from the database in one read-only transaction.

    Attributes:
        catalog_rows: ``CATALOG_QUERY_SQL`` rows.
        applied: Applied migration versions, or None when not read.
        history_reason: Why the history could not be read, if it could not.
    """

    catalog_rows: list[CatalogRow]
    applied: list[str] | None
    history_reason: str | None


def load_repo_migrations(directory: Path) -> list[RepoMigration]:
    """List the checkout's migrations in the order the CLI applies them.

    Args:
        directory: The ``supabase/migrations`` directory.

    Returns:
        list[RepoMigration]: Matching files, sorted by version.
    """
    found: list[RepoMigration] = []
    for path in directory.glob("*.sql"):
        match = _MIGRATION_FILE_RE.match(path.name)
        if match:
            found.append(RepoMigration(match["version"], path.stem))
    return sorted(found, key=lambda m: m.version)


def compare_history(
    repo: Sequence[RepoMigration], applied: Sequence[str]
) -> HistoryHalf:
    """Compare repo migrations with applied versions.

    Args:
        repo: The checkout's migrations, sorted by version.
        applied: Versions read from the history table.

    Returns:
        HistoryHalf: Pending and unknown sets.
    """
    applied_set = set(applied)
    repo_versions = {m.version for m in repo}
    applied_head = max(applied_set) if applied_set else None
    pending = [m for m in repo if m.version not in applied_set]
    before = [
        m for m in pending if applied_head is not None and m.version < applied_head
    ]
    return HistoryHalf(
        available=True,
        repo_count=len(repo),
        applied_count=len(applied_set),
        repo_head=repo[-1].version if repo else None,
        applied_head=applied_head,
        pending=pending,
        pending_before_head=before,
        unknown_applied=sorted(applied_set - repo_versions),
    )


def load_metadata() -> MetaData:
    """Import the ORM models with an empty environment and return the metadata.

    Importing ``cyo_adventure.db.models`` imports ``core.config``, which builds
    ``Settings()`` from the environment at import time. The operator's shell
    may hold a partial deployment config that refuses to validate, and none of
    it is relevant to reading ``Base.metadata``, so the import runs against
    the safe local defaults instead.

    Returns:
        MetaData: The application's metadata, with every model registered.
    """
    with mock.patch.dict(os.environ, {}, clear=True):
        # Deferred on purpose: see the docstring for why this import must not
        # run against the caller's environment.
        import cyo_adventure.db.models  # noqa: F401, PLC0415  # pyright: ignore[reportUnusedImport]
        from cyo_adventure.core.database import Base  # noqa: PLC0415

    return Base.metadata


def asyncpg_dsn(url: str) -> str:
    """Accept a SQLAlchemy-style URL as well as a plain libpq one.

    Args:
        url: ``postgresql://``, ``postgres://``, or ``postgresql+asyncpg://``.

    Returns:
        str: A DSN asyncpg accepts.
    """
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    return f"{scheme.split('+', 1)[0]}://{rest}"


async def read_database(dsn: str, *, read_history: bool) -> DatabaseRead:
    """Run the catalog (and optionally history) queries read-only.

    Args:
        dsn: Connection string; never echoed.
        read_history: Whether to read the migration-history table.

    Returns:
        DatabaseRead: The rows read.
    """
    # statement_cache_size=0: a Supavisor transaction-mode pooler (port 6543)
    # rejects asyncpg's named prepared statements; harmless when direct.
    conn = cast(
        "_Connection",
        await asyncpg.connect(  # pyright: ignore[reportUnknownMemberType]
            dsn, timeout=_CONNECT_TIMEOUT_SECONDS, statement_cache_size=0
        ),
    )
    try:
        async with conn.transaction(readonly=True):
            _ = await conn.execute(_STATEMENT_TIMEOUT_SQL)
            rows: list[CatalogRow] = [
                (str(r[0]), str(r[1]), bool(r[2]), str(r[3]))
                for r in await conn.fetch(CATALOG_QUERY_SQL)
            ]
            if not read_history:
                return DatabaseRead(rows, None, None)
            if await conn.fetchval(_HISTORY_EXISTS_SQL) is None:
                return DatabaseRead(rows, None, f"{_HISTORY_TABLE} does not exist")
            try:
                async with conn.transaction():  # a savepoint
                    versions = [str(r[0]) for r in await conn.fetch(_HISTORY_SQL)]
            except asyncpg.PostgresError as exc:
                return DatabaseRead(
                    rows,
                    None,
                    f"could not read {_HISTORY_TABLE} ({type(exc).__name__})",
                )
            return DatabaseRead(rows, versions, None)
    finally:
        await conn.close()


def decide(
    comparison: SchemaComparison,
    history: HistoryHalf | None,
    *,
    fail_on_ahead: bool,
) -> tuple[str, int]:
    """Combine both halves into one verdict and exit code.

    BEHIND takes precedence: a database that is both behind and ahead (a
    diverged history) still fails the app, and the report lists both sides.

    Args:
        comparison: The ORM-schema half.
        history: The migration-history half, or None when skipped.
        fail_on_ahead: Exit non-zero on AHEAD too.

    Returns:
        tuple[str, int]: Verdict label and exit code.
    """
    pending = history is not None and history.available and bool(history.pending)
    if comparison.behind or pending:
        return VERDICT_BEHIND, EXIT_BEHIND
    if history is not None and not history.available:
        return VERDICT_INCOMPLETE, EXIT_INCOMPLETE
    unknown = history is not None and bool(history.unknown_applied)
    if comparison.ahead or unknown:
        return VERDICT_AHEAD, EXIT_AHEAD if fail_on_ahead else EXIT_OK
    return VERDICT_PARITY, EXIT_OK


VERDICT_NOTES = {
    VERDICT_PARITY: "the database matches this checkout's migrations and ORM",
    VERDICT_BEHIND: (
        "the app would fail: apply pending migrations "
        "(docs/operations/runbook.md section 2.5) before deploying this image"
    ),
    VERDICT_AHEAD: (
        "an older app on a newer schema; usually tolerable, but deploy the "
        "matching image"
    ),
    VERDICT_INCOMPLETE: (
        "the migration history could not be read; only the ORM-schema half "
        "was checked (pass --schema-only to accept that)"
    ),
}


def _dotted(pairs: Sequence[tuple[str, str]]) -> list[str]:
    return [f"{t}.{c}" for t, c in pairs]


def build_json(
    verdict: str,
    code: int,
    comparison: SchemaComparison,
    history: HistoryHalf | None,
) -> dict[str, object]:
    """Build the ``--json`` document.

    Args:
        verdict: Verdict label.
        code: Exit code.
        comparison: The ORM-schema half.
        history: The migration-history half, or None when skipped.

    Returns:
        dict[str, object]: A JSON-serializable report (names only, no data).
    """
    migrations: dict[str, object]
    if history is None:
        migrations = {"checked": False}
    elif not history.available:
        migrations = {
            "checked": True,
            "available": False,
            "reason": history.unavailable_reason,
        }
    else:
        migrations = {
            "checked": True,
            "available": True,
            "repo_count": history.repo_count,
            "applied_count": history.applied_count,
            "repo_head": history.repo_head,
            "applied_head": history.applied_head,
            "pending": [m.filename for m in history.pending],
            "pending_before_applied_head": [
                m.filename for m in history.pending_before_head
            ],
            "unknown_applied": history.unknown_applied,
        }
    return {
        "verdict": verdict,
        "exit_code": code,
        "migrations": migrations,
        "schema": {
            "orm_tables": comparison.orm_tables,
            "orm_columns": comparison.orm_columns,
            "missing_tables": list(comparison.missing_tables),
            "missing_columns": _dotted(comparison.missing_columns),
            "extra_tables": list(comparison.extra_tables),
            "extra_columns": _dotted(comparison.extra_columns),
            "warnings": {
                kind: [
                    {
                        "column": f"{m.table}.{m.column}",
                        "orm": m.expected,
                        "database": m.actual,
                    }
                    for m in mismatches
                ]
                for kind, mismatches in (
                    ("nullability", comparison.nullability_mismatches),
                    ("type", comparison.type_mismatches),
                )
            },
        },
    }


def _section(lines: list[str], title: str, items: Sequence[str]) -> None:
    lines.append(f"{title}: {len(items)}")
    lines.extend(f"    {item}" for item in items)


def render_text(
    verdict: str, comparison: SchemaComparison, history: HistoryHalf | None
) -> str:
    """Render the report as paste-safe text.

    Args:
        verdict: Verdict label.
        comparison: The ORM-schema half.
        history: The migration-history half, or None when skipped.

    Returns:
        str: Human-readable report (names only, no data, no connection detail).
    """
    lines = [f"VERDICT: {verdict} ({VERDICT_NOTES[verdict]})", "", "Migration history"]
    if history is None:
        lines.append("  not checked (--schema-only)")
    elif not history.available:
        lines.append(f"  UNAVAILABLE: {history.unavailable_reason}")
    else:
        lines.append(
            f"  repo: {history.repo_count} (head {history.repo_head}); "
            f"applied: {history.applied_count} (head {history.applied_head})"
        )
        _section(
            lines,
            "  pending (in repo, not applied)",
            [m.filename for m in history.pending],
        )
        if history.pending_before_head:
            _section(
                lines,
                "  of which sort BEFORE the applied head "
                "(db push without --include-all skips these)",
                [m.filename for m in history.pending_before_head],
            )
        _section(
            lines, "  applied but unknown to this checkout", history.unknown_applied
        )
    counts = f"{comparison.orm_tables} tables, {comparison.orm_columns} columns"
    lines += ["", f"ORM schema ({counts})"]
    _section(lines, "  missing tables (app would fail)", comparison.missing_tables)
    _section(
        lines,
        "  missing columns (app would fail)",
        _dotted(comparison.missing_columns),
    )
    _section(lines, "  extra tables (ahead, tolerable)", comparison.extra_tables)
    _section(
        lines,
        "  extra columns (ahead, tolerable)",
        _dotted(comparison.extra_columns),
    )
    lines += ["", "Warnings (do not change the verdict)"]
    for kind, mismatches in (
        ("nullability", comparison.nullability_mismatches),
        ("type", comparison.type_mismatches),
    ):
        _section(
            lines,
            f"  {kind} differences",
            [
                f"{m.table}.{m.column}: orm {m.expected}, database {m.actual}"
                for m in mismatches
            ],
        )
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only check that a live database matches this checkout's "
            "supabase/migrations and ORM models."
        )
    )
    _ = parser.add_argument(
        "--url-env",
        default=DEFAULT_URL_ENV,
        help=(
            "Name of the environment variable holding the database URL "
            f"(default {DEFAULT_URL_ENV}). The URL itself is never accepted "
            "on the command line."
        ),
    )
    _ = parser.add_argument("--json", action="store_true", help="Emit JSON.")
    _ = parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=DEFAULT_MIGRATIONS_DIR,
        help="Override supabase/migrations (for tests).",
    )
    _ = parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Skip the migration-history half (for a role that cannot read it).",
    )
    _ = parser.add_argument(
        "--fail-on-ahead",
        action="store_true",
        help=f"Exit {EXIT_AHEAD} instead of 0 when the database is ahead.",
    )
    return parser.parse_args(argv)


def _error(message: str, *, as_json: bool) -> int:
    if as_json:
        print(
            json.dumps({"verdict": "ERROR", "exit_code": EXIT_ERROR, "error": message})
        )
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    return EXIT_ERROR


def main(argv: Sequence[str] | None = None) -> int:
    """Run the check.

    Args:
        argv: Arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        int: The exit code (see the module docstring).
    """
    args = _parse_args(argv)
    url_env = cast("str", args.url_env)
    as_json = cast("bool", args.json)
    schema_only = cast("bool", args.schema_only)
    migrations_dir = cast("Path", args.migrations_dir)
    fail_on_ahead = cast("bool", args.fail_on_ahead)

    url = os.environ.get(url_env, "").strip()
    if not url:
        return _error(
            f"environment variable {url_env} is not set; export the database "
            "URL there (it is never accepted as an argument)",
            as_json=as_json,
        )
    repo = [] if schema_only else load_repo_migrations(migrations_dir)
    if not schema_only and not repo:
        return _error(f"no migrations found under {migrations_dir}", as_json=as_json)
    metadata = load_metadata()
    try:
        read = asyncio.run(
            read_database(asyncpg_dsn(url), read_history=not schema_only)
        )
    except (
        OSError,
        TimeoutError,
        ValueError,
        asyncpg.PostgresError,
        asyncpg.InterfaceError,
    ) as exc:
        # Class name only: asyncpg and OS messages can name the host and user.
        return _error(
            f"could not query the database ({type(exc).__name__})", as_json=as_json
        )
    comparison = compare_schema(metadata, build_live_catalog(read.catalog_rows))
    history: HistoryHalf | None
    if schema_only:
        history = None
    elif read.applied is None:
        history = HistoryHalf(available=False, unavailable_reason=read.history_reason)
    else:
        history = compare_history(repo, read.applied)
    verdict, code = decide(comparison, history, fail_on_ahead=fail_on_ahead)
    if as_json:
        print(json.dumps(build_json(verdict, code, comparison, history), indent=2))
    else:
        print(render_text(verdict, comparison, history))
    return code


if __name__ == "__main__":
    sys.exit(main())
