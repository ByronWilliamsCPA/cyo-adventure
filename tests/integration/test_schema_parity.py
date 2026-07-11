"""Schema parity: Supabase SQL migrations must match the ORM models.

Replaces the retired schema-migration-tool check gate. Two databases are built on the
same Postgres server: one by applying every ``supabase/migrations/*.sql``
file in lexicographic order (the simple-query protocol handles
multi-statement files), one from ``Base.metadata.create_all``. Their
inspected structure must be identical.

Known blind spots (currently vacuous, revisit if the schema grows them):
FK ON DELETE/ON UPDATE actions, index access methods, native enum types,
sequences, and triggers/functions (the ``pipeline_event`` append-only
trigger is covered behaviorally in ``test_pipeline_event_append_only.py``).
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

# Imported for its side effect of registering every ORM table on
# Base.metadata, so this module's create_all does not silently depend on
# conftest.py happening to import the models first. (Without it the failure
# would still be loud, an empty ORM table set, but explicit is better.)
import cyo_adventure.db.models  # noqa: F401
from cyo_adventure.core.database import Base

_MIGRATIONS = sorted(
    (Path(__file__).resolve().parents[2] / "supabase" / "migrations").glob("*.sql")
)

# Tables owned by tooling, not the ORM.
_IGNORED_TABLES = {"schema_migrations"}

# Matches ONLY the SQLAlchemy-side rendering of a string-enum membership
# array: every element is a quoted literal cast to exactly
# ``::character varying``, and the whole ARRAY carries a single trailing
# ``::text[]`` cast, e.g.
# ``ARRAY['draft'::character varying, 'published'::character varying]::text[]``.
# An element cast to any OTHER type, an array cast to anything but
# ``text[]``, or a non-literal element does not match, so such expressions
# are compared verbatim and any type-level difference stays visible.
_ORM_ENUM_ARRAY_RE = re.compile(
    r"ARRAY\["
    r"(?P<elems>'(?:[^']|'')*'::character varying"
    r"(?:, '(?:[^']|'')*'::character varying)*)"
    r"\]::text\[\]"
)

# Within a matched element list: the ``::character varying`` cast that ends
# one element, i.e. one followed by the ``, '`` separator of the next quoted
# literal or by the end of the list.
# #EDGE: data-integrity: the lookahead (?=, '|$) assumes enum literals never
# contain the byte sequence ::character varying, '; spurious mismatch if violated.
# #VERIFY: violation produces a loud parity mismatch in
# test_migrations_match_orm_models, never a silent pass.
_ELEM_CAST_RE = re.compile(r"::character varying(?=, '|$)")


def _norm_check(sqltext: str) -> str:
    """Canonicalize one known cast-placement spelling in a CHECK expression.

    Postgres stores a parsed expression tree per CHECK constraint, and both
    parity databases are read back through the same ``pg_get_constraintdef``
    deparser, so constraint text compares byte-for-byte between the two
    catalogs with a single exception: the string-enum membership pattern
    ``col::text = ANY (ARRAY[...])``. The pg_dump baseline declares the cast
    at the array level (``(ARRAY[...])::text[]``), which the parser pushes
    down into each element (deparsed as ``'x'::character varying::text``,
    no array-level cast), while SQLAlchemy's compiled ``IN`` produces
    elements without the push-down (``'x'::character varying``) plus an
    array-level ``::text[]``. The two trees are semantically identical:
    every varchar literal cast to text, elementwise versus arraywise.

    This function rewrites exactly that one SQLAlchemy-side spelling into
    the pushed-down form: for an ``ARRAY[...]::text[]`` whose every element
    is a quoted literal cast to ``::character varying``, it appends
    ``::text`` to each element and drops the array-level ``::text[]``.
    Nothing else is touched: no case folding, no quote or whitespace
    stripping, and no cast removal, so constraints that differ in literal
    values (including their case), column names, operators, or cast types
    still compare unequal verbatim.

    # #ASSUME: data-integrity: the rewrite fires only on the exact spelling
    # matched by _ORM_ENUM_ARRAY_RE and is meaning-preserving there
    # (casting each varchar element to text equals casting the varchar[]
    # array to text[]); expressions with any other cast type or shape pass
    # through unmodified and must match byte-for-byte on their own.
    # #VERIFY: _ORM_ENUM_ARRAY_RE requires the literal token
    # "::character varying" on every element and "::text[]" on the array,
    # so a differing cast type on either side leaves that side unrewritten
    # and the comparison fails loudly; literal values are carried into the
    # output verbatim (no lowercasing, no quote stripping) by construction
    # of _ELEM_CAST_RE, which only inserts "::text" after an element's
    # closing cast.

    Args:
        sqltext: The raw ``sqltext`` reported by
            ``Inspector.get_check_constraints``.

    Returns:
        The constraint text with only the enum-array cast spelling
        canonicalized; all other text is preserved byte-for-byte.
    """

    def _push_down(match: re.Match[str]) -> str:
        elems = _ELEM_CAST_RE.sub("::character varying::text", match.group("elems"))
        return f"ARRAY[{elems}]"

    return _ORM_ENUM_ARRAY_RE.sub(_push_down, sqltext)


def _snapshot(sync_conn: Any) -> dict[str, Any]:
    """Inspect a connection's ``public`` schema into a comparable snapshot.

    Args:
        sync_conn: A sync-style connection handed in via ``run_sync`` (the
            SQLAlchemy ``Inspector`` API is sync-only).

    Returns:
        A mapping of table name to its columns, primary key, foreign keys,
        unique constraints, indexes, and check constraints. Server defaults
        are compared verbatim (both catalogs deparse a stored default
        expression through the same ``pg_get_expr``, so identical defaults
        render identically and no normalization is applied); check
        constraints get only the single cast-spelling canonicalization
        documented on ``_norm_check``.
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
                c.get("default"),
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
        # editing the baseline SQL; ownership plays no part in the
        # schema-parity comparison below (Inspector snapshots do not include
        # object owner).
        # #EDGE: concurrency: roles are cluster-global, so a check-then-create
        # from Python would race if two sessions on the same server ran it
        # concurrently (pytest-xdist workers each start their own
        # session-scoped container today, but that is a fixture detail this
        # statement should not depend on). The DO block below is a single
        # server-side statement that swallows exactly duplicate_object, so a
        # concurrent creator cannot make it fail, and any OTHER error
        # (permissions, syntax) still propagates.
        # #VERIFY: a superuser (the testcontainers "test" role) may reassign
        # ownership to any existing role without being a member of it, so no
        # further grants are required for the migration's OWNER TO statements
        # to succeed; verified by this test applying the full baseline dump.
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
