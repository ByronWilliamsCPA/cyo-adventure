"""Behavioral tests for the ck_user_child_not_admin and ck_user_admin_role_flag
CHECK constraints.

The dual admin/guardian roles design (see
docs/planning/admin-guardian-dual-roles-plan.md) relies on two ORM-level
CheckConstraints (``db/models.py::User.__table_args__``) to keep ``role`` and
``is_admin`` mutually consistent: ``ck_user_child_not_admin`` keeps the admin
capability off child rows, and ``ck_user_admin_role_flag`` requires that an
admin-role row always carries the capability. Both are backed by an identical
CHECK added at rest by
``supabase/migrations/20260712000000_user_is_admin.sql``. The ORM copies are
exercised implicitly by every unit test that builds a schema via
``create_all``, but that never proves the real migration's CHECK expressions
are spelled correctly or actually reject a bad row in Postgres. These tests
build a database from the real migration chain and assert the constraints'
runtime behavior directly, mirroring the pattern in
``test_pipeline_event_append_only.py``.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_MIGRATIONS = sorted(
    (Path(__file__).resolve().parents[2] / "supabase" / "migrations").glob("*.sql")
)

# Dedicated database name so this module never collides with the parity
# test's or the append-only test's databases on the shared server.
_DB_NAME = "user_admin_constraint_mig"

# #CRITICAL: security: the at-rest backstop keeping the admin capability off
# child rows lives in a CHECK constraint defined only in the SQL migrations;
# nothing in the application layer stops a raw SQL write path (or an ORM
# session that bypasses the API boundary) from persisting
# (role='child', is_admin=true), which would then grant a child principal
# the global review/approval capability at the auth boundary (api/deps.py).
# #VERIFY: ck_user_child_not_admin rejects (role='child', is_admin=true) at
# rest; the tests below run against a database built from the real
# migration chain and fail loudly if the constraint is ever dropped, renamed,
# or narrowed.


@pytest_asyncio.fixture
async def user_conn(pg_url: str) -> AsyncIterator[asyncpg.Connection]:
    """Yield an asyncpg connection to a database built from the migrations.

    Mirrors the apply pattern in ``test_schema_parity.py`` and
    ``test_pipeline_event_append_only.py``: create a database on the shared
    session-scoped testcontainers server, create the ``postgres`` role that
    the baseline dump's ``OWNER TO`` statements require, then apply every
    ``supabase/migrations/*.sql`` file in lexicographic order over the
    asyncpg simple-query protocol so multi-statement files run as one batch.

    Args:
        pg_url: Public alias for the session-scoped ``_pg_url``
            testcontainers Postgres URL fixture
            (``tests/integration/conftest.py``).

    Yields:
        An open asyncpg connection to the freshly migrated database.
    """
    assert _MIGRATIONS, "no supabase migrations found"
    admin = create_async_engine(
        pg_url, poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {_DB_NAME}"))
        await conn.execute(text(f"CREATE DATABASE {_DB_NAME}"))
        await conn.execute(
            text(
                "DO $$ BEGIN "
                'CREATE ROLE "postgres"; '
                "EXCEPTION WHEN duplicate_object THEN NULL; "
                "END $$"
            )
        )
    await admin.dispose()

    dsn = (
        pg_url.replace("postgresql+asyncpg://", "postgresql://").rsplit("/", 1)[0]
        + f"/{_DB_NAME}"
    )
    raw = await asyncpg.connect(dsn)
    try:
        for path in _MIGRATIONS:
            await raw.execute(path.read_text())
        # The baseline dump clears search_path for the session
        # (set_config('search_path', '', false)), so restore it before
        # handing the connection to the tests, which use unqualified names.
        await raw.execute("SET search_path = public")
        yield raw
    finally:
        await raw.close()


async def _insert_family(conn: asyncpg.Connection) -> uuid.UUID:
    """Insert one minimal family row and return its id.

    Args:
        conn: Open asyncpg connection to the migrated database.

    Returns:
        The UUID primary key of the inserted row.
    """
    family_id = uuid.uuid4()
    await conn.execute(
        'INSERT INTO "family" (id, name) VALUES ($1, $2)',
        family_id,
        "Constraint Test Family",
    )
    return family_id


async def _insert_user(
    conn: asyncpg.Connection,
    family_id: uuid.UUID,
    *,
    role: str,
    is_admin: bool,
    authn_subject: str,
) -> uuid.UUID:
    """Insert one "user" row with the given role/is_admin and return its id.

    Args:
        conn: Open asyncpg connection to the migrated database.
        family_id: The owning family's id.
        role: The base persona ('guardian', 'child', or 'admin').
        is_admin: The admin capability flag to persist.
        authn_subject: A unique authn subject for the row.

    Returns:
        The UUID primary key of the inserted row.
    """
    user_id = uuid.uuid4()
    await conn.execute(
        'INSERT INTO "user" (id, family_id, role, is_admin, authn_subject) '
        "VALUES ($1, $2, $3, $4, $5)",
        user_id,
        family_id,
        role,
        is_admin,
        authn_subject,
    )
    return user_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_with_admin_capability_insert_is_rejected(
    user_conn: asyncpg.Connection,
) -> None:
    """An INSERT of (role='child', is_admin=true) is rejected at rest.

    Args:
        user_conn: Connection to a database built from the migration chain.
    """
    family_id = await _insert_family(user_conn)
    with pytest.raises(asyncpg.CheckViolationError):
        await _insert_user(
            user_conn,
            family_id,
            role="child",
            is_admin=True,
            authn_subject="child-admin-insert",
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_with_admin_capability_update_is_rejected(
    user_conn: asyncpg.Connection,
) -> None:
    """An UPDATE that flips an existing child row to is_admin=true is rejected.

    Args:
        user_conn: Connection to a database built from the migration chain.
    """
    family_id = await _insert_family(user_conn)
    user_id = await _insert_user(
        user_conn,
        family_id,
        role="child",
        is_admin=False,
        authn_subject="child-admin-update",
    )
    with pytest.raises(asyncpg.CheckViolationError):
        await user_conn.execute(
            'UPDATE "user" SET is_admin = true WHERE id = $1', user_id
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_with_admin_capability_insert_is_allowed(
    user_conn: asyncpg.Connection,
) -> None:
    """A dual-role (role='guardian', is_admin=true) row is a normal insert.

    Positive control: the constraint targets only the child role, so it must
    not reject the dual-role shape the admin-guardian design depends on.

    Args:
        user_conn: Connection to a database built from the migration chain.
    """
    family_id = await _insert_family(user_conn)
    user_id = await _insert_user(
        user_conn,
        family_id,
        role="guardian",
        is_admin=True,
        authn_subject="dual-role-insert",
    )
    stored_is_admin = await user_conn.fetchval(
        'SELECT is_admin FROM "user" WHERE id = $1', user_id
    )
    assert stored_is_admin is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_role_without_capability_insert_is_rejected(
    user_conn: asyncpg.Connection,
) -> None:
    """An INSERT of (role='admin', is_admin=false) is rejected at rest.

    Args:
        user_conn: Connection to a database built from the migration chain.
    """
    family_id = await _insert_family(user_conn)
    with pytest.raises(asyncpg.CheckViolationError):
        await _insert_user(
            user_conn,
            family_id,
            role="admin",
            is_admin=False,
            authn_subject="admin-no-capability-insert",
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_role_with_capability_insert_is_allowed(
    user_conn: asyncpg.Connection,
) -> None:
    """An INSERT of (role='admin', is_admin=true) is a normal insert.

    Positive control: the constraint targets only the admin-without-capability
    shape, so it must not reject the consistent admin-role row the
    admin-guardian design depends on.

    Args:
        user_conn: Connection to a database built from the migration chain.
    """
    family_id = await _insert_family(user_conn)
    user_id = await _insert_user(
        user_conn,
        family_id,
        role="admin",
        is_admin=True,
        authn_subject="admin-with-capability-insert",
    )
    stored_is_admin = await user_conn.fetchval(
        'SELECT is_admin FROM "user" WHERE id = $1', user_id
    )
    assert stored_is_admin is True
