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

from cyo_adventure.core.config import settings


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


def _unique_prepared_statement_name() -> str:
    """Return a process-unique name for an asyncpg prepared statement.

    Passed as the asyncpg dialect's ``prepared_statement_name_func`` so that no
    two prepared statements share a name. Under a transaction-mode pooler this
    prevents a name created on one pooled backend from colliding when that
    backend is later handed to a different client session.
    """
    return f"__cyo_asyncpg_{uuid.uuid4().hex}__"


def _build_connect_args(*, disable_prepared_cache: bool) -> dict[str, object]:
    """Build asyncpg connect args for the configured database URL.

    Args:
        disable_prepared_cache: When True, disable the asyncpg dialect's
            prepared-statement cache and force a unique name per prepared
            statement. Set this for a transaction-mode pooler (Supabase
            Supavisor on :6543, PgBouncer transaction mode).

    Returns:
        An empty mapping for a direct PostgreSQL connection, or the
        cache-disabling connect args for a transaction-mode pooler.
    """
    # #CRITICAL: external resources: a transaction pooler multiplexes one
    # backend across client sessions, so a cached or fixed-name server-side
    # prepared statement collides across sessions and 500s the request.
    # prepared_statement_cache_size=0 stops the dialect reusing them, and the
    # unique name func stops asyncpg's per-execution names colliding.
    # #VERIFY: tests/unit/test_database.py exercises both branches.
    if not disable_prepared_cache:
        return {}
    return {
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": _unique_prepared_statement_name,
    }


# #CRITICAL: external resources: the async engine is built at import time from
# settings.database_url, but no connection opens until first session use, so an
# unreachable database surfaces as an opaque error on the first request rather
# than at startup. pool_pre_ping recycles stale connections, not an absent host.
# pool_pre_ping is safe under a transaction pooler as of SQLAlchemy 2.0.21 (the
# ping now runs inside a transaction rather than in AUTOCOMMIT).
# #VERIFY: gate traffic on api/health.check_database (readiness probe) so an
# unreachable database fails the readiness check instead of live requests.
# #CRITICAL: concurrency: no pool_size / max_overflow / pool_timeout is set, so
# SQLAlchemy defaults apply (pool_size=5, max_overflow=10). Under higher
# concurrency, sessions block waiting on the pool and requests stall.
# #VERIFY: set pool_size and max_overflow explicitly from settings once the
# expected concurrent-session ceiling is known.
_engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args=_build_connect_args(
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
