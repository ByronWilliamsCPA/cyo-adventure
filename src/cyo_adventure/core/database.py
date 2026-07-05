"""Async SQLAlchemy engine and session management for CYO Adventure.

Provides the generic database plumbing shared by all ORM models:
- A declarative ``Base`` that adventure/book models inherit from.
- A lazily-connecting async engine built from ``settings.database_url``.
- A ``get_session`` async context manager that yields a scoped session.

The engine is created at import time but does not open a connection until a
session is first used, so importing this module is side-effect free for tests
and tooling.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from cyo_adventure.core.config import settings


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


def _unique_prepared_statement_name() -> str:
    """Return a name unique for all practical purposes, for an asyncpg prepared statement.

    Passed as the asyncpg dialect's ``prepared_statement_name_func`` so that no
    two prepared statements share a name. A UUID4 is unique across processes,
    hosts, and restarts (not merely within the current process), which is what
    lets this prevent a name created on one pooled backend from colliding when
    that backend is later handed to a different client session, possibly in a
    different worker process entirely.
    """
    return f"__cyo_asyncpg_{uuid.uuid4().hex}__"


def _build_connect_args(*, disable_prepared_cache: bool) -> dict[str, object]:
    """Build asyncpg connect args for the configured database URL.

    Args:
        disable_prepared_cache: When True, disable both of asyncpg's
            prepared-statement caches and force a unique name per prepared
            statement. Set this for a transaction-mode pooler (Supabase
            Supavisor on :6543, PgBouncer transaction mode).

    Returns:
        dict[str, object]: An empty mapping for a direct PostgreSQL
        connection, or the cache-disabling connect args for a
        transaction-mode pooler.
    """
    # #CRITICAL: concurrency: a transaction pooler multiplexes one backend
    # across client sessions, so a cached or fixed-name server-side prepared
    # statement collides across sessions and 500s the request. Two distinct
    # caches must both be disabled, not one: statement_cache_size is asyncpg's
    # own native cache (passed straight through to asyncpg.connect()), while
    # prepared_statement_cache_size is a separate cache the SQLAlchemy asyncpg
    # dialect layers on top (see AsyncAdapt_asyncpg_connection._prepare in
    # sqlalchemy/dialects/postgresql/asyncpg.py). Disabling only one leaves the
    # other still reusing/evicting statements, reproducing the same collision
    # this setting exists to prevent, just less often.
    # #VERIFY: tests/unit/test_database.py exercises both branches.
    if not disable_prepared_cache:
        return {}
    return {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": _unique_prepared_statement_name,
    }


def _build_engine_kwargs(*, disable_prepared_cache: bool) -> dict[str, object]:
    """Build extra create_async_engine kwargs for the configured database URL.

    Args:
        disable_prepared_cache: When True, use NullPool so no asyncpg
            connection (and therefore no server-side prepared statement) is
            reused across logical checkouts.

    Returns:
        dict[str, object]: An empty mapping for a direct PostgreSQL
        connection (the default QueuePool applies), or
        ``{"poolclass": NullPool}`` for a transaction-mode pooler.
    """
    # #CRITICAL: concurrency: _build_connect_args gives every prepared
    # statement a unique name, so none is ever reused or evicted by either
    # cache. Under the default QueuePool the same asyncpg connection is
    # reused across many logical checkouts for the life of the process, so
    # those uniquely-named statements accumulate server-side memory without
    # bound for as long as that connection lives; nothing ever DEALLOCATEs
    # them. NullPool opens a fresh connection per checkout and closes it on
    # return, so no prepared statement outlives a single checkout.
    # #VERIFY: tests/unit/test_database.py exercises both branches.
    if not disable_prepared_cache:
        return {}
    return {"poolclass": NullPool}


# #CRITICAL: external resources: the async engine is built at import time from
# settings.database_url, but no connection opens until first session use, so an
# unreachable database surfaces as an opaque error on the first request rather
# than at startup. pool_pre_ping recycles stale connections, not an absent host.
# pool_pre_ping is safe under a transaction pooler as of SQLAlchemy 2.0.21 (the
# ping now runs inside a transaction rather than in AUTOCOMMIT).
# #VERIFY: gate traffic on api/health.check_database (readiness probe) so an
# unreachable database fails the readiness check instead of live requests.
# #CRITICAL: concurrency: for a direct connection (database_disable_prepared_cache
# False), no pool_size / max_overflow / pool_timeout is set, so SQLAlchemy
# defaults apply (pool_size=5, max_overflow=10). Under higher concurrency,
# sessions block waiting on the pool and requests stall. This does not apply
# when the pooler branch is active: NullPool opens a fresh connection per
# checkout and has no pool_size/max_overflow of its own.
# #VERIFY: set pool_size and max_overflow explicitly from settings once the
# expected concurrent-session ceiling is known for a direct connection.
_engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args=_build_connect_args(
        disable_prepared_cache=settings.database_disable_prepared_cache
    ),
    **_build_engine_kwargs(
        disable_prepared_cache=settings.database_disable_prepared_cache
    ),
)
_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine,
    expire_on_commit=False,
)


def get_engine() -> AsyncEngine:
    """Return the shared async engine (useful for migrations and health checks)."""
    return _engine


def get_session() -> AsyncSession:
    """Return a new async session for use as an async context manager."""
    return _session_factory()
