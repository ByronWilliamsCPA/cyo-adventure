"""Behavioral tests for the security_event append-only trigger (OPS-005).

Mirrors test_pipeline_event_append_only.py's approach and rationale exactly:
the trigger (``trg_security_event_append_only`` calling
``security_event_append_only()``) exists only in the Supabase SQL migration
(``supabase/migrations/20260804070000_add_security_event_table.sql``), not in
ORM metadata, so the ``create_all``-built schemas used by the rest of the
integration suite do not carry it. These tests build a database from the real
migration chain and assert the trigger's runtime behavior directly.
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
# test's or pipeline_event's own append-only test's databases on the shared
# server.
_DB_NAME = "security_event_append_only_mig"

# #CRITICAL: data-integrity: the append-only guarantee for the security event
# log lives entirely in a database trigger defined only in the SQL
# migrations; nothing in the application layer or the ORM metadata enforces
# it, so a dropped or broken trigger would let UPDATE/DELETE mutate the audit
# log while every create_all-based test still passes green.
# #VERIFY: the tests below run against a database built from the real
# migration chain and fail loudly if INSERT stops working or if
# UPDATE/DELETE stop being rejected with the trigger's "append-only" error.


@pytest_asyncio.fixture
async def event_conn(pg_url: str) -> AsyncIterator[asyncpg.Connection]:
    """Yield an asyncpg connection to a database built from the migrations.

    Mirrors test_pipeline_event_append_only.py::event_conn exactly: create a
    database on the shared session-scoped testcontainers server, create the
    ``postgres`` role the baseline dump's ``OWNER TO`` statements require,
    then apply every ``supabase/migrations/*.sql`` file in lexicographic
    order over the asyncpg simple-query protocol so multi-statement files
    run as one batch.

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


async def _insert_event(conn: asyncpg.Connection) -> uuid.UUID:
    """Insert one minimal security_event row and return its id.

    Args:
        conn: Open asyncpg connection to the migrated database.

    Returns:
        The UUID primary key of the inserted row.
    """
    event_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO security_event "
        "(id, event_type, reason, client_ip) "
        "VALUES ($1, 'security_auth_failed', 'unknown subject', '203.0.113.5')",
        event_id,
    )
    return event_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_insert_is_allowed(event_conn: asyncpg.Connection) -> None:
    """An INSERT into security_event succeeds and the row is readable back.

    Args:
        event_conn: Connection to a database built from the migration chain.
    """
    event_id = await _insert_event(event_conn)
    stored_type = await event_conn.fetchval(
        "SELECT event_type FROM security_event WHERE id = $1", event_id
    )
    assert stored_type == "security_auth_failed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_is_rejected(event_conn: asyncpg.Connection) -> None:
    """An UPDATE on security_event is rejected by the append-only trigger.

    Args:
        event_conn: Connection to a database built from the migration chain.
    """
    event_id = await _insert_event(event_conn)
    with pytest.raises(asyncpg.PostgresError, match="append-only"):
        await event_conn.execute(
            "UPDATE security_event SET reason = 'x' WHERE id = $1", event_id
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_is_rejected(event_conn: asyncpg.Connection) -> None:
    """A DELETE on security_event is rejected by the append-only trigger.

    Args:
        event_conn: Connection to a database built from the migration chain.
    """
    event_id = await _insert_event(event_conn)
    with pytest.raises(asyncpg.PostgresError, match="append-only"):
        await event_conn.execute("DELETE FROM security_event WHERE id = $1", event_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_truncate_bypasses_the_trigger(event_conn: asyncpg.Connection) -> None:
    """TRUNCATE succeeds: the row-level trigger does not fire for it.

    # #EDGE: data-integrity: the trigger is BEFORE DELETE OR UPDATE FOR EACH
    # ROW; TRUNCATE is a statement-level operation, so Postgres never fires
    # row triggers for it and the append-only guard is intentionally
    # bypassable by TRUNCATE (which test/reset tooling relies on), exactly
    # like pipeline_event's identical trigger.
    # #VERIFY: this test asserts the bypass explicitly; if the trigger were
    # ever extended with BEFORE TRUNCATE (closing the bypass), this test
    # fails and forces the reset tooling to be revisited in the same change.

    Args:
        event_conn: Connection to a database built from the migration chain.
    """
    await _insert_event(event_conn)
    await event_conn.execute("TRUNCATE security_event")
    remaining = await event_conn.fetchval("SELECT count(*) FROM security_event")
    assert remaining == 0
