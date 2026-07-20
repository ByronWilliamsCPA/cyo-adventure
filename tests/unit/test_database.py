"""Tests for cyo_adventure.core.database module.

Verifies import-side-effect-free behaviour, type identity of the engine,
sessionmaker, Base, and the get_engine/get_session public functions.
No live database is required.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType


class TestBase:
    """Tests for the ORM declarative Base class."""

    @pytest.mark.unit
    def test_base_is_declarative_base_subclass(self) -> None:
        """Verify Base is a DeclarativeBase subclass."""
        from sqlalchemy.orm import DeclarativeBase

        from cyo_adventure.core.database import Base

        assert issubclass(Base, DeclarativeBase)

    @pytest.mark.unit
    def test_base_has_metadata(self) -> None:
        """Verify Base exposes a metadata object for schema management."""
        from sqlalchemy import MetaData

        from cyo_adventure.core.database import Base

        assert isinstance(Base.metadata, MetaData)


class TestGetEngine:
    """Tests for the get_engine() public function."""

    @pytest.mark.unit
    def test_get_engine_returns_async_engine(self) -> None:
        """Verify get_engine returns an AsyncEngine instance."""
        from sqlalchemy.ext.asyncio import AsyncEngine

        from cyo_adventure.core.database import get_engine

        engine = get_engine()

        assert isinstance(engine, AsyncEngine)

    @pytest.mark.unit
    def test_get_engine_returns_singleton(self) -> None:
        """Verify get_engine returns the same object on repeated calls."""
        from cyo_adventure.core.database import get_engine

        first = get_engine()
        second = get_engine()

        assert first is second

    @pytest.mark.unit
    def test_engine_has_pool_pre_ping_enabled(self) -> None:
        """Verify the engine is configured with pool_pre_ping for stale-connection recycling."""
        from cyo_adventure.core.database import get_engine

        engine = get_engine()

        # pool_pre_ping is exposed via the sync engine
        assert engine.sync_engine.pool._pre_ping is True  # type: ignore[attr-defined]


class TestGetSession:
    """Tests for the get_session() public function."""

    @pytest.mark.unit
    def test_get_session_returns_async_session(self) -> None:
        """Verify get_session returns an AsyncSession instance."""
        from sqlalchemy.ext.asyncio import AsyncSession

        from cyo_adventure.core.database import get_session

        session = get_session()

        assert isinstance(session, AsyncSession)

    @pytest.mark.unit
    def test_get_session_returns_new_session_each_call(self) -> None:
        """Verify each call to get_session produces a distinct session object."""
        from cyo_adventure.core.database import get_session

        session_a = get_session()
        session_b = get_session()

        assert session_a is not session_b

    @pytest.mark.unit
    def test_get_session_session_is_not_committed_at_creation(self) -> None:
        """Verify session is not in the committed state immediately after creation."""
        from cyo_adventure.core.database import get_session

        session = get_session()

        # A fresh session should not show as active/committed; is_active is True
        # (session object exists) but no transaction has been committed.
        assert session.is_active


class TestGetWorkerEngine:
    """Tests for the get_worker_engine() public function (ADR-021)."""

    @pytest.mark.unit
    def test_get_worker_engine_returns_async_engine(self) -> None:
        """Verify get_worker_engine returns an AsyncEngine instance."""
        from sqlalchemy.ext.asyncio import AsyncEngine

        from cyo_adventure.core.database import get_worker_engine

        engine = get_worker_engine()

        assert isinstance(engine, AsyncEngine)

    @pytest.mark.unit
    def test_get_worker_engine_returns_singleton(self) -> None:
        """Verify get_worker_engine returns the same object on repeated calls."""
        from cyo_adventure.core.database import get_worker_engine

        first = get_worker_engine()
        second = get_worker_engine()

        assert first is second

    @pytest.mark.unit
    def test_worker_engine_is_a_distinct_object_from_the_api_engine(self) -> None:
        """The worker engine must be its own connection pool, never the API engine's.

        Even pre-cutover, when worker_database_url_effective falls back to the
        same DSN as database_url, the two engines must remain separate pool
        objects; sharing the pool object would defeat the point of a distinct
        worker engine once a cutover DOES set a different DSN.
        """
        from cyo_adventure.core.database import get_engine, get_worker_engine

        assert get_worker_engine() is not get_engine()


class TestGetWorkerSession:
    """Tests for the get_worker_session() public function (ADR-021)."""

    @pytest.mark.unit
    def test_get_worker_session_returns_async_session(self) -> None:
        """Verify get_worker_session returns an AsyncSession instance."""
        from sqlalchemy.ext.asyncio import AsyncSession

        from cyo_adventure.core.database import get_worker_session

        session = get_worker_session()

        assert isinstance(session, AsyncSession)

    @pytest.mark.unit
    def test_get_worker_session_returns_new_session_each_call(self) -> None:
        """Verify each call to get_worker_session produces a distinct session object."""
        from cyo_adventure.core.database import get_worker_session

        session_a = get_worker_session()
        session_b = get_worker_session()

        assert session_a is not session_b

    @pytest.mark.unit
    def test_get_worker_session_is_bound_to_the_worker_engine(self) -> None:
        """A worker session's bind must be the worker engine, not the API engine."""
        from cyo_adventure.core.database import get_worker_engine, get_worker_session

        session = get_worker_session()

        assert session.bind is get_worker_engine()


class TestImportSideEffects:
    """Tests verifying no DB connection is opened at import time."""

    @pytest.mark.unit
    def test_module_imports_without_live_database(self) -> None:
        """Reimporting database module builds an engine without opening a connection."""
        import importlib

        # If the module is already imported, reimport to exercise the path;
        # a populated, idle pool (no checked-out connections) confirms the
        # engine was constructed lazily rather than by attempting a connect.
        import cyo_adventure.core.database as db_module

        reloaded = importlib.reload(db_module)

        assert reloaded.get_engine() is not None
        assert reloaded.get_engine().sync_engine.pool.checkedout() == 0  # type: ignore[attr-defined]

    @pytest.mark.unit
    def test_engine_pool_has_no_checked_out_connections_at_startup(self) -> None:
        """Verify pool shows zero checked-out connections right after import."""
        from cyo_adventure.core.database import get_engine

        engine = get_engine()
        # Access sync pool status without touching the DB
        pool = engine.sync_engine.pool
        assert pool.checkedout() == 0  # type: ignore[attr-defined]

    @pytest.mark.unit
    def test_worker_engine_pool_has_no_checked_out_connections_at_startup(
        self,
    ) -> None:
        """The worker engine (ADR-021) is equally side-effect-free at import."""
        from cyo_adventure.core.database import get_worker_engine

        engine = get_worker_engine()
        pool = engine.sync_engine.pool
        assert pool.checkedout() == 0  # type: ignore[attr-defined]


class TestConnectArgs:
    """Tests for transaction-pooler connect args (ADR-009 Task 1.7)."""

    @pytest.mark.unit
    def test_direct_connection_gets_no_connect_args(self) -> None:
        """A direct PostgreSQL connection must not disable prepared statements."""
        from cyo_adventure.core.database import _build_connect_args

        assert _build_connect_args(disable_prepared_cache=False) == {}

    @pytest.mark.unit
    def test_transaction_pooler_disables_both_prepared_statement_caches(self) -> None:
        """A transaction pooler must disable BOTH asyncpg's own cache and the
        SQLAlchemy dialect's cache, and use a name func.

        asyncpg's native statement_cache_size and SQLAlchemy's
        prepared_statement_cache_size are two independent caches; disabling
        only one still reproduces the collision this setting exists to
        prevent, just less often (confirmed against the installed dialect
        source: only prepared_statement_cache_size/prepared_statement_name_func
        are popped before the remaining kwargs reach asyncpg.connect(), so
        statement_cache_size passes through as asyncpg's own native arg).
        """
        from cyo_adventure.core.database import _build_connect_args

        args = _build_connect_args(disable_prepared_cache=True)

        assert args == {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": args["prepared_statement_name_func"],
        }
        assert callable(args["prepared_statement_name_func"])

    @pytest.mark.unit
    def test_prepared_statement_names_are_unique(self) -> None:
        """A large sample of generated prepared-statement names must all be distinct
        and match the expected shape (prefix, 32 hex chars, suffix)."""
        import re

        from cyo_adventure.core.database import _unique_prepared_statement_name

        names = {_unique_prepared_statement_name() for _ in range(1000)}

        assert len(names) == 1000
        assert all(
            re.fullmatch(r"__cyo_asyncpg_[0-9a-f]{32}__", name) for name in names
        )

    @pytest.mark.unit
    def test_name_func_in_connect_args_produces_valid_names(self) -> None:
        """The wired name func must be the module's unique-name generator."""
        from cyo_adventure.core.database import (
            _build_connect_args,
            _unique_prepared_statement_name,
        )

        args = _build_connect_args(disable_prepared_cache=True)

        assert args["prepared_statement_name_func"] is _unique_prepared_statement_name


class TestEngineKwargs:
    """Tests for the pool-class enabler (ADR-009 Task 1.7) and pool sizing (ADR-021)."""

    @pytest.mark.unit
    def test_direct_connection_gets_pool_size_and_max_overflow(self) -> None:
        """A direct PostgreSQL connection must thread pool_size/max_overflow (ADR-021)."""
        from cyo_adventure.core.database import _build_engine_kwargs

        assert _build_engine_kwargs(
            disable_prepared_cache=False, pool_size=7, max_overflow=13
        ) == {"pool_size": 7, "max_overflow": 13}

    @pytest.mark.unit
    def test_transaction_pooler_uses_null_pool(self) -> None:
        """A transaction pooler must use NullPool so no prepared statement
        outlives a single checkout (nothing ever DEALLOCATEs a uniquely-named
        statement, so the default QueuePool would accumulate them without bound)."""
        from sqlalchemy.pool import NullPool

        from cyo_adventure.core.database import _build_engine_kwargs

        assert _build_engine_kwargs(
            disable_prepared_cache=True, pool_size=7, max_overflow=13
        ) == {"poolclass": NullPool}

    @pytest.mark.unit
    def test_transaction_pooler_never_receives_pool_size_kwargs(self) -> None:
        """Regression guard (ADR-021): pool_size/max_overflow must never reach
        the NullPool branch, since NullPool has no such parameters and passing
        them raises TypeError at engine construction. This is deliberately the
        loud failure mode this test pins, not a value assertion."""
        from cyo_adventure.core.database import _build_engine_kwargs

        kwargs = _build_engine_kwargs(
            disable_prepared_cache=True, pool_size=7, max_overflow=13
        )

        assert "pool_size" not in kwargs
        assert "max_overflow" not in kwargs


@contextlib.contextmanager
def _swapped_settings_and_reloaded_db_module(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[ModuleType, ModuleType]]:
    """Swap the config.settings singleton in place, reload database, then restore.

    Encapsulates the in-place settings-singleton-swap pattern documented on
    ``test_disable_prepared_cache_env_var_flows_into_create_async_engine``
    below: env vars must be set via ``monkeypatch`` BEFORE entering this
    context manager, and ``config_module.Settings()`` picks them up when a
    fresh instance is built here.

    #CRITICAL: data-integrity: do NOT use importlib.reload(config_module)
    instead of this swap. Reloading config rebinds
    cyo_adventure.core.config.settings to a brand-new object, orphaning
    every module that did `from ...config import settings` at its own
    import time (api.deps, core.device_grant, core.child_session all bind
    the singleton by value); those keep the OLD instance while a later
    fixture monkeypatches the NEW one, producing an order-dependent flake
    in unrelated suites. Swapping the module attribute in place (config's
    module body is just `settings = Settings()`) and restoring the EXACT
    original object in the finally block preserves the instance identity
    every importer holds.
    #VERIFY: any new test built on this helper should still pass when run
    immediately before an integration device/child token test, in any order.

    Args:
        monkeypatch: The active pytest monkeypatch fixture; its ``undo()``
            is called here so env vars set before entering are also cleared
            on exit, alongside the settings/module restoration.

    Yields:
        tuple[ModuleType, ModuleType]: ``(config_module, db_module)`` after
        the swap and reload, for the caller to inspect.
    """
    import importlib

    import cyo_adventure.core.config as config_module
    import cyo_adventure.core.database as db_module

    original_settings = config_module.settings
    config_module.settings = config_module.Settings()
    try:
        importlib.reload(db_module)
        yield config_module, db_module
    finally:
        monkeypatch.undo()
        config_module.settings = original_settings
        importlib.reload(db_module)


class TestEngineWiring:
    """End-to-end tests that Settings actually flows into create_async_engine.

    TestConnectArgs/TestEngineKwargs above test the pure helper functions in
    isolation with literal booleans; these tests close the gap of verifying
    the real env-var -> Settings -> create_async_engine wiring, so a typo in
    the env var name or field wiring cannot pass silently.
    """

    @pytest.mark.unit
    def test_disable_prepared_cache_env_var_flows_into_create_async_engine(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Setting the real env var must reach create_async_engine's actual
        connect_args and poolclass kwargs, not just the helper functions."""
        import importlib

        import sqlalchemy.ext.asyncio as sa_asyncio

        monkeypatch.setenv("CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE", "true")

        captured_kwargs: dict[str, object] = {}
        real_create_async_engine = sa_asyncio.create_async_engine

        def fake_create_async_engine(*args: object, **kwargs: object):
            captured_kwargs.update(kwargs)
            return real_create_async_engine(*args, **kwargs)

        monkeypatch.setattr(sa_asyncio, "create_async_engine", fake_create_async_engine)

        import cyo_adventure.core.config as config_module
        import cyo_adventure.core.database as db_module

        # #CRITICAL: data-integrity: do NOT reload config_module to pick up the
        # env var. importlib.reload rebinds cyo_adventure.core.config.settings to
        # a brand-new object, orphaning every module that did
        # `from ...config import settings` at its own import time (api.deps,
        # core.device_grant, core.child_session all bind the singleton by value).
        # Those keep the OLD instance while the integration conftest's autouse
        # secret fixtures monkeypatch the NEW one, so a later device/child-session
        # token op reads a secret-less settings and 400s. Under pytest-randomly's
        # shuffled order that surfaces as an order-dependent flake in unrelated
        # suites. Swap the singleton in place (config's module body is just
        # `settings = Settings()`, so this reads the env identically) and restore
        # the EXACT original object in finally, preserving the instance identity
        # every importer holds.
        # #VERIFY: run this test immediately before an integration device/child
        # token test (any order) and both pass; see the deterministic repro in
        # the fix for this flake.
        original_settings = config_module.settings
        config_module.settings = config_module.Settings()
        try:
            importlib.reload(db_module)

            connect_args = captured_kwargs["connect_args"]
            assert connect_args["prepared_statement_cache_size"] == 0  # type: ignore[index]
            assert connect_args["statement_cache_size"] == 0  # type: ignore[index]
            assert captured_kwargs["poolclass"] is db_module.NullPool
            # ADR-021 regression guard: pool_size/max_overflow must never
            # reach create_async_engine alongside poolclass=NullPool, since
            # NullPool has no such parameters (TypeError at construction).
            assert "pool_size" not in captured_kwargs
            assert "max_overflow" not in captured_kwargs
        finally:
            monkeypatch.undo()
            config_module.settings = original_settings
            importlib.reload(db_module)

    @pytest.mark.unit
    def test_pool_size_and_max_overflow_env_vars_flow_into_create_async_engine(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ADR-021 pool-bound env vars reach create_async_engine's real kwargs."""
        import sqlalchemy.ext.asyncio as sa_asyncio

        monkeypatch.setenv("CYO_ADVENTURE_DATABASE_POOL_SIZE", "17")
        monkeypatch.setenv("CYO_ADVENTURE_DATABASE_MAX_OVERFLOW", "23")

        captured_kwargs: dict[str, object] = {}
        real_create_async_engine = sa_asyncio.create_async_engine

        def fake_create_async_engine(*args: object, **kwargs: object):
            captured_kwargs.update(kwargs)
            return real_create_async_engine(*args, **kwargs)

        monkeypatch.setattr(sa_asyncio, "create_async_engine", fake_create_async_engine)

        with _swapped_settings_and_reloaded_db_module(monkeypatch):
            assert captured_kwargs["pool_size"] == 17
            assert captured_kwargs["max_overflow"] == 23

    @pytest.mark.unit
    def test_worker_url_env_var_routes_only_the_worker_engine(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A distinct CYO_ADVENTURE_WORKER_DATABASE_URL builds a worker engine
        pointed at that DSN while the API engine keeps database_url (ADR-021).
        """
        worker_url = (
            "postgresql+asyncpg://cyo_worker:testpass@worker.example.com/cyo_adventure"
        )
        monkeypatch.setenv("CYO_ADVENTURE_WORKER_DATABASE_URL", worker_url)
        monkeypatch.setenv("CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE", "false")

        with _swapped_settings_and_reloaded_db_module(monkeypatch) as (_, db_module):
            worker_engine_url = db_module.get_worker_engine().url
            assert worker_engine_url.render_as_string(hide_password=False) == worker_url
            assert worker_engine_url.host == "worker.example.com"
            assert db_module.get_engine().url.host != "worker.example.com"

    @pytest.mark.unit
    def test_unset_worker_url_gives_worker_engine_the_same_dsn_as_api_engine(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pre-cutover (worker_database_url unset), both engines' DSNs match,
        confirming the fallback is a real no-op on connection identity."""
        monkeypatch.delenv("CYO_ADVENTURE_WORKER_DATABASE_URL", raising=False)
        monkeypatch.delenv("WORKER_DATABASE_URL", raising=False)

        with _swapped_settings_and_reloaded_db_module(monkeypatch) as (_, db_module):
            assert str(db_module.get_worker_engine().url) == str(
                db_module.get_engine().url
            )
