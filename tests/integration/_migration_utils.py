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
import secrets
from pathlib import Path

import asyncpg
from sqlalchemy import make_url, text
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


async def migrate_and_connect_as(
    pg_url: str, db_name: str, role: str
) -> tuple[str, str]:
    """Build a migrated sibling database and promote a NOLOGIN role to LOGIN.

    Applies the full migration chain (so the ADR-021 service roles and the
    ADR-022 Tier 1 policies both exist), then flips ``role`` -- created NOLOGIN
    by ``20260720170100_create_service_roles.sql`` -- to LOGIN with a fresh
    random password so a caller can authenticate as it and be subject to its
    RLS policies. The role is neither the table owner nor BYPASSRLS, which is
    exactly why connecting as it makes policies observable (the owner-connected
    default fixtures never see a policy filter a row).

    Args:
        pg_url: Admin ``postgresql+asyncpg://`` URL for the testcontainers
            server (the session-scoped ``pg_url`` fixture).
        db_name: Fresh database name; must match ``_SAFE_IDENTIFIER_RE``.
        role: The migrated-schema role to promote. Interpolated into
            ``ALTER ROLE`` DDL (role identifiers cannot be bound), so it is
            validated against the same safe-identifier pattern as ``db_name``.

    Returns:
        tuple[str, str]: ``(admin_url, role_url)`` -- the RLS-bypassing owner
        DSN for the new database (seed baseline rows through it) and a DSN
        authenticated as ``role`` (run RLS-subject assertions through it).

    Raises:
        ValueError: If ``role`` is not a safe Postgres identifier.
    """
    if not _SAFE_IDENTIFIER_RE.match(role):
        msg = f"role {role!r} is not a safe Postgres identifier"
        raise ValueError(msg)

    admin_url = await create_migrated_database(pg_url, db_name)
    # secrets.token_urlsafe emits the URL-safe base64 alphabet only (no
    # quotes), so it is safe to interpolate into the string-literal password
    # position, which ALTER ROLE does not accept as a bind parameter. A fresh
    # value per call means a stale connection can never reuse a prior password.
    password = secrets.token_urlsafe(16)
    admin = create_async_engine(
        admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin.connect() as conn:
            await conn.execute(
                text(f"ALTER ROLE \"{role}\" LOGIN PASSWORD '{password}'")
            )
    finally:
        await admin.dispose()

    # render_as_string(hide_password=False): str(URL) masks the password as
    # "***", which would then be sent verbatim and fail auth.
    role_url = (
        make_url(admin_url)
        .set(username=role, password=password)
        .render_as_string(hide_password=False)
    )
    return admin_url, role_url
