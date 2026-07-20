"""Shared helper for applying the full supabase/migrations chain to a fresh database.

Extracted from ``test_schema_parity.py`` (ADR-021) so both the schema-parity
check and the RLS service-role regression test (``test_rls_service_roles.py``)
build their migrated database identically: any future migration-application
quirk (multi-statement files, the testcontainers ``postgres`` role
prerequisite) is fixed once, here, instead of drifting between two
hand-duplicated copies.
"""

from __future__ import annotations

import re
from pathlib import Path

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

MIGRATIONS = sorted(
    (Path(__file__).resolve().parents[2] / "supabase" / "migrations").glob("*.sql")
)

# A conservative Postgres identifier pattern (letters, digits, underscore,
# must not start with a digit). Every caller in this repo passes a fixed
# literal (e.g. "parity_mig", "rls_service_roles"), never external input, but
# db_name is interpolated directly into DDL (CREATE/DROP DATABASE cannot be
# parameterized via asyncpg/SQLAlchemy bind params), so this is a defense
# against a future caller accidentally passing something unsafe, not a live
# threat today.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


async def create_migrated_database(pg_url: str, db_name: str) -> str:
    """Create a fresh sibling database and apply every supabase/migrations/*.sql file.

    Mirrors a real Supabase Postgres cluster's migration application: files
    run in lexicographic timestamp order via asyncpg's simple-query protocol
    (which executes a multi-statement file as a single batch, unlike
    SQLAlchemy's ``text()`` execution path).

    Args:
        pg_url: A SQLAlchemy ``postgresql+asyncpg://`` URL pointing at the
            testcontainers Postgres server's admin/default database; the new
            database is created as a sibling on the same server.
        db_name: The name of the fresh database to create. Must match
            ``_SAFE_IDENTIFIER_RE``; this is interpolated into
            ``CREATE``/``DROP DATABASE`` DDL, which cannot be parameterized.

    Returns:
        str: A SQLAlchemy ``postgresql+asyncpg://`` URL for the newly created
        and migrated database (same server, same credentials, new database
        name).

    Raises:
        ValueError: If db_name does not match the safe-identifier pattern.
    """
    if not _SAFE_IDENTIFIER_RE.match(db_name):
        msg = f"db_name {db_name!r} is not a safe Postgres identifier"
        raise ValueError(msg)

    admin = create_async_engine(
        pg_url, poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        # #ASSUME: external-resources: the baseline migration is a pg_dump
        # from a live Supabase project, where every table/function is owned
        # by the built-in "postgres" role; that role always exists in a real
        # Supabase Postgres instance. The testcontainers image used here sets
        # POSTGRES_USER=test, so its cluster superuser is "test" rather than
        # "postgres" and the dump's "ALTER ... OWNER TO postgres" statements
        # would fail with "role postgres does not exist". Creating the role
        # here mirrors the target environment's prerequisite rather than
        # editing the baseline SQL.
        # #EDGE: concurrency: roles are cluster-global, so a check-then-create
        # from Python would race if two sessions on the same server ran it
        # concurrently. The DO block below is a single server-side statement
        # that swallows exactly duplicate_object, so a concurrent creator
        # cannot make it fail, and any OTHER error (permissions, syntax)
        # still propagates.
        # #VERIFY: test_schema_parity.py and test_rls_service_roles.py both
        # apply the full baseline dump through this path; a role-creation
        # regression fails either test loudly at CREATE ROLE, not silently.
        await conn.execute(
            text(
                "DO $$ BEGIN "
                'CREATE ROLE "postgres"; '
                "EXCEPTION WHEN duplicate_object THEN NULL; "
                "END $$"
            )
        )
    await admin.dispose()

    base = pg_url.replace("postgresql+asyncpg://", "postgresql://")
    root = base.rsplit("/", 1)[0]
    raw = await asyncpg.connect(f"{root}/{db_name}")
    try:
        for path in MIGRATIONS:
            await raw.execute(path.read_text())
    finally:
        await raw.close()

    return pg_url.rsplit("/", 1)[0] + f"/{db_name}"
