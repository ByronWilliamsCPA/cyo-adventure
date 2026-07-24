"""ADR-022 spike: prove ``set_config(..., is_local => true)`` does not bleed.

This is the "one thing to prove first" from the ADR-022 (tiered RLS scoping)
debate verdict. Tier 1 RLS policies read the caller's family from a
transaction-scoped session variable:

    current_setting('app.family_id', true)

which the request path must set once per transaction via
``SELECT set_config('app.family_id', <family_uuid>, true)``. The security of
the whole scheme rests on one property: when a pooled backend connection is
handed from one request to the next, the ``app.family_id`` set by the first
request MUST NOT still be readable by the second. If it bled, request B could
inherit request A's family scope and read another family's children's data,
the exact cross-tenant leak RLS exists to prevent.

Why this test builds its own engine instead of reusing the ``engine`` fixture:
the shared ``engine`` fixture (see ``conftest.py``) uses ``NullPool``, which
opens a fresh backend per checkout and closes it on return. A fresh backend
trivially cannot carry stale session state, so testing bleed against NullPool
would prove nothing about production. Production's API engine (the Supabase
session-mode pooler on ``:5432``) uses a real ``QueuePool`` that REUSES
backends across requests, so this spike forces ``pool_size=1`` /
``max_overflow=0`` to pin one shared backend and drive the exact reuse path
production hits. ``pg_backend_pid()`` is asserted equal across the two logical
requests so a passing test cannot be explained away by the pool having quietly
handed out a second connection.

Two independent Postgres mechanisms make the property hold, and this spike
exercises both so a regression in either is caught:

1. ``is_local => true`` scopes the setting to the current transaction; the
   value reverts the instant that transaction ends (COMMIT or ROLLBACK).
2. SQLAlchemy's pool ``reset_on_return`` default issues a ROLLBACK when a
   connection is returned to the pool, which independently ends any lingering
   transaction and reverts local settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = pytest.mark.asyncio

_FAMILY_A = "11111111-1111-1111-1111-111111111111"
_GUC = "app.family_id"


@pytest_asyncio.fixture
async def single_conn_sessions(
    pg_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Yield a session factory pinned to exactly one reused backend connection.

    ``pool_size=1`` with ``max_overflow=0`` means every checkout that does not
    overlap another must reuse the one backend, which is what lets the bleed
    assertions below be meaningful (see the module docstring). ``pool_pre_ping``
    mirrors the production engine (``core/database.py::_create_engine``) so the
    checkout-time ``SELECT 1`` ping is part of the path under test.

    # #CRITICAL: concurrency: pool_size=1/max_overflow=0 means two OVERLAPPING
    # checkouts would deadlock (the second waits forever for a connection that
    # never frees). Every test here must fully close session A before opening
    # session B; do not hold two sessions from this factory open at once.
    # #VERIFY: each test uses ``async with`` blocks that close sequentially.
    """
    eng: AsyncEngine = create_async_engine(
        pg_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )
    try:
        yield async_sessionmaker(eng, expire_on_commit=False)
    finally:
        await eng.dispose()


async def _backend_pid(session: AsyncSession) -> int:
    """Return the Postgres backend PID serving this session's connection."""
    pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
    assert isinstance(pid, int)
    return pid


async def _read_family_setting(session: AsyncSession) -> str | None:
    """Read ``app.family_id`` with the missing-ok flag (fail-closed semantics).

    ``current_setting(name, true)`` returns NULL rather than raising when the
    setting was never assigned, which is exactly the fail-closed behavior a
    Tier 1 policy relies on: an unset context yields NULL, and
    ``family_id = NULL`` is never true, so the policy matches zero rows.
    """
    return (
        await session.execute(text("SELECT current_setting(:guc, true)"), {"guc": _GUC})
    ).scalar_one()


async def test_set_config_visible_within_its_own_transaction(
    single_conn_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Sanity check: a local setting IS readable inside the transaction that set it.

    Establishes the positive baseline the bleed tests contrast against: the
    mechanism does work as intended for the request that owns the transaction.
    """
    async with single_conn_sessions() as session:
        await session.execute(
            text("SELECT set_config(:guc, :val, true)"),
            {"guc": _GUC, "val": _FAMILY_A},
        )
        assert await _read_family_setting(session) == _FAMILY_A


async def test_local_setting_does_not_bleed_across_commit_on_reused_backend(
    single_conn_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Committing request A must not leave A's family scope readable by request B.

    Models two sequential requests sharing one pooled backend: request A sets
    its family scope and commits (the normal success path); request B then
    checks out the SAME backend and must see no ``app.family_id`` at all.
    """
    async with single_conn_sessions() as session_a:
        pid_a = await _backend_pid(session_a)
        await session_a.execute(
            text("SELECT set_config(:guc, :val, true)"),
            {"guc": _GUC, "val": _FAMILY_A},
        )
        assert await _read_family_setting(session_a) == _FAMILY_A
        await session_a.commit()
    # session_a's connection is now back in the one-slot pool.

    async with single_conn_sessions() as session_b:
        pid_b = await _backend_pid(session_b)
        # If the backends differ the pool handed out a second connection and
        # the no-bleed assertion below would be vacuous; pin reuse so the test
        # actually exercises the shared-backend path production runs.
        assert pid_b == pid_a, "expected the pooled backend to be reused"
        leaked = await _read_family_setting(session_b)
        assert leaked != _FAMILY_A, f"family scope bled across requests: {leaked!r}"
        assert not leaked, f"expected an unset (fail-closed) scope, got {leaked!r}"


async def test_local_setting_does_not_bleed_across_rollback_on_reused_backend(
    single_conn_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A rolled-back request A must likewise leak nothing to request B.

    The rollback path matters independently: a request that errors mid-flight
    rolls back rather than commits, and an ``is_local`` setting must revert on
    ROLLBACK exactly as it does on COMMIT. This guards the error path that a
    commit-only test would miss.
    """
    async with single_conn_sessions() as session_a:
        pid_a = await _backend_pid(session_a)
        await session_a.execute(
            text("SELECT set_config(:guc, :val, true)"),
            {"guc": _GUC, "val": _FAMILY_A},
        )
        assert await _read_family_setting(session_a) == _FAMILY_A
        await session_a.rollback()

    async with single_conn_sessions() as session_b:
        pid_b = await _backend_pid(session_b)
        assert pid_b == pid_a, "expected the pooled backend to be reused"
        leaked = await _read_family_setting(session_b)
        assert leaked != _FAMILY_A, f"family scope bled across requests: {leaked!r}"
        assert not leaked, f"expected an unset (fail-closed) scope, got {leaked!r}"


async def test_unset_family_context_reads_as_falsy_fail_closed(
    single_conn_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A backend that never set ``app.family_id`` reads it as NULL, not a value.

    This is the property a Tier 1 policy leans on for its default-deny posture:
    with no context set, ``current_setting('app.family_id', true)`` is NULL, so
    ``family_id::text = NULL`` is never true and the policy exposes zero rows.
    A caller who forgets to set the context therefore sees nothing rather than
    everything.
    """
    async with single_conn_sessions() as session:
        assert not await _read_family_setting(session)
