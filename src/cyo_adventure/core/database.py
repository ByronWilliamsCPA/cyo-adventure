"""Async SQLAlchemy engine and session management for CYO Adventure.

Provides the generic database plumbing shared by all ORM models:
- A declarative ``Base`` that adventure/book models inherit from.
- A lazily-connecting async engine built from ``settings.database_url``
  (the API engine) and a second one built from
  ``settings.worker_database_url_effective`` (the worker engine, ADR-021).
- ``get_session`` / ``get_worker_session`` async context managers that each
  yield a scoped session bound to their respective engine.

Both engines are built through the same ``_create_engine`` constructor so
they cannot drift in connect-args, pool, or prepared-statement-cache wiring.
When ``worker_database_url`` is unset (the default, pre-cutover state), the
worker engine's DSN falls back to ``database_url`` and the two engines are
functionally identical, just separate connection pools; nothing about
runtime connection identity changes until a per-environment ADR-021 cutover
sets a distinct worker DSN.

FastAPI request handlers must use ``get_session`` (the API engine); RQ worker
processes (``generation/worker_main.py``, ``covers/worker.py``) must use
``get_worker_session`` (the worker engine).

Both engines are created at import time but do not open a connection until a
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


def _build_engine_kwargs(
    *, disable_prepared_cache: bool, pool_size: int, max_overflow: int
) -> dict[str, object]:
    """Build extra create_async_engine kwargs for the configured database URL.

    Args:
        disable_prepared_cache: When True, use NullPool so no asyncpg
            connection (and therefore no server-side prepared statement) is
            reused across logical checkouts.
        pool_size: The QueuePool base size to apply on the direct-connection
            branch only (ADR-021). Never reaches the pooler branch: NullPool
            has no ``pool_size``/``max_overflow`` parameters of its own, and
            passing them raises ``TypeError`` at engine construction, so this
            function must never merge them into the NullPool kwargs.
        max_overflow: The QueuePool overflow ceiling, direct-connection
            branch only. Same NullPool-incompatibility note as ``pool_size``.

    Returns:
        dict[str, object]: ``{"pool_size": pool_size, "max_overflow":
        max_overflow}`` for a direct PostgreSQL connection, or
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
        return {"pool_size": pool_size, "max_overflow": max_overflow}
    return {"poolclass": NullPool}


def _create_engine(url: str) -> AsyncEngine:
    """Build one async engine from a database DSN, shared by the API and worker engines.

    Both ``_engine`` (API) and ``_worker_engine`` (RQ workers, ADR-021) are
    constructed through this single function so their connect-args, pool
    class, and prepared-statement-cache wiring can never drift apart: a
    hand-duplicated second ``create_async_engine`` call would risk one engine
    silently missing a setting the other has (e.g. a future connect_args
    tweak applied to only one call site).

    Args:
        url: The database DSN to build the engine from (``database_url`` for
            the API engine, ``worker_database_url_effective`` for the
            worker engine).

    Returns:
        AsyncEngine: A lazily-connecting engine; no connection opens until
        first use (see the import-side-effect-free #CRITICAL note below).
    """
    # #CRITICAL: external resources: the async engine is built at import time
    # from a settings-derived URL, but no connection opens until first session
    # use, so an unreachable database surfaces as an opaque error on the first
    # request rather than at startup. pool_pre_ping recycles stale
    # connections, not an absent host. pool_pre_ping is safe under a
    # transaction pooler as of SQLAlchemy 2.0.21 (the ping now runs inside a
    # transaction rather than in AUTOCOMMIT).
    # #VERIFY: gate traffic on api/health.check_database (readiness probe) so
    # an unreachable database fails the readiness check instead of live
    # requests.
    return create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args=_build_connect_args(
            disable_prepared_cache=settings.database_disable_prepared_cache
        ),
        **_build_engine_kwargs(
            disable_prepared_cache=settings.database_disable_prepared_cache,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        ),
    )


# #CRITICAL: concurrency: for a direct connection (database_disable_prepared_cache
# False), pool_size/max_overflow are threaded from settings.database_pool_size /
# settings.database_max_overflow (ADR-021; defaults 5/10 match SQLAlchemy's
# prior implicit QueuePool defaults, so an environment that never sets these
# keeps its current pool ceiling). This does not apply when the pooler branch
# is active: NullPool opens a fresh connection per checkout and has no
# pool_size/max_overflow of its own; _build_engine_kwargs never passes them on
# that branch (doing so would raise TypeError at engine construction).
# #VERIFY: tests/unit/test_database.py::TestEngineKwargs pins both the
# direct-branch wiring and the pooler-branch TypeError-avoidance guard.
_engine: AsyncEngine = _create_engine(settings.database_url)
_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine,
    expire_on_commit=False,
)

# Worker-process engine (ADR-021). Built from worker_database_url_effective,
# which falls back to database_url when worker_database_url is unset, so
# pre-cutover this is a distinct connection pool with identical connection
# identity to _engine, not a behavior change. Post-cutover (a separate,
# manual, per-environment step; see docs/operations/runbook.md), this pool
# connects as the least-privilege cyo_worker role instead of the shared
# credential _engine uses.
_worker_engine: AsyncEngine = _create_engine(settings.worker_database_url_effective)
_worker_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _worker_engine,
    expire_on_commit=False,
)


def get_engine() -> AsyncEngine:
    """Return the shared API async engine (useful for migrations and health checks)."""
    return _engine


def get_session() -> AsyncSession:
    """Return a new async session bound to the API engine, for FastAPI request paths."""
    return _session_factory()


def get_worker_engine() -> AsyncEngine:
    """Return the shared worker async engine (ADR-021; RQ worker processes only)."""
    return _worker_engine


def get_worker_session() -> AsyncSession:
    """Return a new async session bound to the worker engine.

    Use this (never ``get_session``) from RQ worker processes
    (``generation/worker.py``, ``generation/worker_main.py``,
    ``covers/worker.py``) so a post-cutover ``WORKER_DATABASE_URL`` (ADR-021)
    actually takes effect for background jobs.
    """
    return _worker_session_factory()
