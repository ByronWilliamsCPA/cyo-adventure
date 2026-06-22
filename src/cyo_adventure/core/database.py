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


# #CRITICAL: external resources: the async engine is built at import time from
# settings.database_url, but no connection opens until first session use, so an
# unreachable database surfaces as an opaque error on the first request rather
# than at startup. pool_pre_ping recycles stale connections, not an absent host.
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
