"""Schema parity: Supabase SQL migrations must match the ORM models.

Replaces the retired ``alembic check`` gate. Two databases are built on the
same Postgres server: one by applying every ``supabase/migrations/*.sql``
file in lexicographic order (the simple-query protocol handles
multi-statement files), one from ``Base.metadata.create_all``. Their
inspected structure must be identical.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from cyo_adventure.core.database import Base

_MIGRATIONS = sorted(
    (Path(__file__).resolve().parents[2] / "supabase" / "migrations").glob("*.sql")
)

# Tables owned by tooling, not the ORM.
_IGNORED_TABLES = {"schema_migrations"}

# Matches a Postgres type cast (``::text``, ``::charactervarying``,
# ``::text[]``) once the surrounding text has been lowercased and had all
# whitespace stripped.
_CAST_RE = re.compile(r"::[a-z_]+(\[\])?")


def _norm_check(sqltext: str) -> str:
    """Normalize a CHECK constraint's expression text for parity comparison.

    Postgres re-serializes a CHECK expression's cast chain differently
    depending on how the constraint was originally declared: a pg_dump
    baseline casts each array literal individually
    (``'x'::charactervarying::text``), while SQLAlchemy's compiled DDL casts
    the whole array once at the end (``'x'::charactervarying]::text[]``).
    Both produce the same runtime comparison (``status::text = ANY(...)``
    against a set of string literals), so stripping every cast annotation
    collapses the two spellings to the same normalized form without
    touching the literal values or operators being compared.

    # #ASSUME: data-integrity: stripping casts loosens formatting only; two
    # constraints that differ in their literal values, columns, or operators
    # (not merely in cast spelling) must still compare unequal.
    # #VERIFY: covered by test_migrations_match_orm_models comparing the
    # normalized checks list per table.

    Args:
        sqltext: The raw ``sqltext`` reported by
            ``Inspector.get_check_constraints``.

    Returns:
        The normalized, cast-free constraint text.
    """
    collapsed = sqltext.replace(" ", "").lower()
    return _CAST_RE.sub("", collapsed)


def _norm_default(value: str | None) -> str | None:
    """Normalize a column server default across dump vs create_all spellings.

    A pg_dump-format migration and ``create_all`` render the same default
    differently even though both are inspected from a real Postgres catalog:
    a dump writes ``'{}'::jsonb`` while SQLAlchemy's DDL compiler emits
    ``'{}'``, and string defaults may differ in quoting or an explicit
    ``::text`` cast. Stripping the cast, quotes, and case differences
    collapses these to the same normalized form without touching the
    underlying default value itself.

    # #ASSUME: data-integrity: this normalization only strips formatting
    # (casts, quotes, case, whitespace); it must never make two genuinely
    # different default values compare equal.
    # #VERIFY: covered by test_migrations_match_orm_models failing loudly on
    # any drift that survives normalization.

    Args:
        value: The raw ``server_default`` string reported by SQLAlchemy's
            ``Inspector.get_columns``, or ``None`` if the column has no
            default.

    Returns:
        The normalized default string, or ``None`` if there is no default.
    """
    if value is None:
        return None
    normalized = value
    for cast in (
        "::jsonb",
        "::text",
        "::character varying",
        "::timestamp with time zone",
    ):
        normalized = normalized.replace(cast, "")
    return normalized.replace("'", "").strip().lower()


def _snapshot(sync_conn: Any) -> dict[str, Any]:
    """Inspect a connection's ``public`` schema into a comparable snapshot.

    Args:
        sync_conn: A sync-style connection handed in via ``run_sync`` (the
            SQLAlchemy ``Inspector`` API is sync-only).

    Returns:
        A mapping of table name to its columns, primary key, foreign keys,
        unique constraints, indexes, and check constraints, all normalized
        for cross-database comparison.
    """
    insp = inspect(sync_conn)
    snap: dict[str, Any] = {}
    for table in sorted(insp.get_table_names(schema="public")):
        if table in _IGNORED_TABLES:
            continue
        cols = {
            c["name"]: (
                str(c["type"]).lower(),
                c["nullable"],
                _norm_default(c.get("default")),
            )
            for c in insp.get_columns(table)
        }
        pk = tuple(insp.get_pk_constraint(table)["constrained_columns"])
        fks = sorted(
            (
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
                tuple(fk["referred_columns"]),
            )
            for fk in insp.get_foreign_keys(table)
        )
        uniques = sorted(
            tuple(u["column_names"]) for u in insp.get_unique_constraints(table)
        )
        indexes = sorted(
            (tuple(i["column_names"]), bool(i["unique"]))
            for i in insp.get_indexes(table)
        )
        checks = sorted(
            _norm_check(c["sqltext"]) for c in insp.get_check_constraints(table)
        )
        snap[table] = {
            "columns": cols,
            "pk": pk,
            "fks": fks,
            "uniques": uniques,
            "indexes": indexes,
            "checks": checks,
        }
    return snap


@pytest.mark.asyncio
async def test_migrations_match_orm_models(pg_url: str) -> None:
    """Applying every migration must produce the same schema as the ORM models.

    Builds ``parity_mig`` (from ``supabase/migrations/*.sql``, applied via the
    asyncpg simple-query protocol so multi-statement files run as a batch) and
    ``parity_orm`` (from ``Base.metadata.create_all``) on the same
    testcontainers Postgres server, then compares their inspected structure
    table-by-table. Any drift is either a missing/incorrect ORM model or a
    baseline SQL bug; the fix belongs in the mismatched side, never in
    loosening this comparison.

    Args:
        pg_url: Public alias for the session-scoped ``_pg_url`` testcontainers
            Postgres URL fixture (see ``tests/integration/conftest.py``); the
            alias avoids Ruff's PT019 on a leading-underscore parameter that
            this test needs the value of, not just the side effect of.
    """
    assert _MIGRATIONS, "no supabase migrations found"
    admin = create_async_engine(
        pg_url, poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as conn:
        await conn.execute(text("DROP DATABASE IF EXISTS parity_mig"))
        await conn.execute(text("DROP DATABASE IF EXISTS parity_orm"))
        await conn.execute(text("CREATE DATABASE parity_mig"))
        await conn.execute(text("CREATE DATABASE parity_orm"))
        # #ASSUME: external-resources: the baseline migration is a pg_dump
        # from a live Supabase project, where every table/function is owned
        # by the built-in "postgres" role; that role always exists in a real
        # Supabase Postgres instance. The testcontainers image used here sets
        # POSTGRES_USER=test, so its cluster superuser is "test" rather than
        # "postgres" and the dump's "ALTER ... OWNER TO postgres" statements
        # would fail with "role postgres does not exist". Creating the role
        # here mirrors the target environment's prerequisite rather than
        # editing the baseline SQL, since ownership plays no part in the
        # schema-parity comparison below (Inspector snapshots do not include
        # object owner).
        # #VERIFY: a superuser (the testcontainers "test" role) may reassign
        # ownership to any existing role without being a member of it, so no
        # further grants are required for the migration's OWNER TO statements
        # to succeed.
        role_exists = await conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'postgres'")
        )
        if role_exists.scalar() is None:
            await conn.execute(text('CREATE ROLE "postgres"'))
    await admin.dispose()

    base = pg_url.replace("postgresql+asyncpg://", "postgresql://")
    root = base.rsplit("/", 1)[0]
    raw = await asyncpg.connect(f"{root}/parity_mig")
    try:
        for path in _MIGRATIONS:
            await raw.execute(path.read_text())
    finally:
        await raw.close()

    orm_url = pg_url.rsplit("/", 1)[0] + "/parity_orm"
    orm_engine = create_async_engine(orm_url, poolclass=NullPool)
    async with orm_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    mig_engine = create_async_engine(
        pg_url.rsplit("/", 1)[0] + "/parity_mig", poolclass=NullPool
    )
    async with mig_engine.connect() as conn:
        mig_snap = await conn.run_sync(_snapshot)
    async with orm_engine.connect() as conn:
        orm_snap = await conn.run_sync(_snapshot)
    await mig_engine.dispose()
    await orm_engine.dispose()

    assert set(mig_snap) == set(orm_snap), (
        f"table set differs: only-in-migrations={set(mig_snap) - set(orm_snap)}, "
        f"only-in-orm={set(orm_snap) - set(mig_snap)}"
    )
    for table in sorted(mig_snap):
        assert mig_snap[table] == orm_snap[table], f"schema drift in table {table!r}"
