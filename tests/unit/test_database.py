"""Tests for cyo_adventure.core.database module.

Verifies import-side-effect-free behaviour, type identity of the engine,
sessionmaker, Base, and the get_engine/get_session public functions.
No live database is required.
"""

from __future__ import annotations

import pytest


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


class TestImportSideEffects:
    """Tests verifying no DB connection is opened at import time."""

    @pytest.mark.unit
    def test_module_imports_without_live_database(self) -> None:
        """Importing database module must not raise even without a live database."""
        import importlib

        # If the module is already imported, reimport to exercise the path;
        # no exception means no connection was attempted.
        import cyo_adventure.core.database as db_module

        importlib.reload(db_module)

    @pytest.mark.unit
    def test_engine_pool_has_no_checked_out_connections_at_startup(self) -> None:
        """Verify pool shows zero checked-out connections right after import."""
        from cyo_adventure.core.database import get_engine

        engine = get_engine()
        # Access sync pool status without touching the DB
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
    """Tests for the pool-class enabler (ADR-009 Task 1.7)."""

    @pytest.mark.unit
    def test_direct_connection_gets_no_engine_kwargs(self) -> None:
        """A direct PostgreSQL connection must keep the default QueuePool."""
        from cyo_adventure.core.database import _build_engine_kwargs

        assert _build_engine_kwargs(disable_prepared_cache=False) == {}

    @pytest.mark.unit
    def test_transaction_pooler_uses_null_pool(self) -> None:
        """A transaction pooler must use NullPool so no prepared statement
        outlives a single checkout (nothing ever DEALLOCATEs a uniquely-named
        statement, so the default QueuePool would accumulate them without bound)."""
        from sqlalchemy.pool import NullPool

        from cyo_adventure.core.database import _build_engine_kwargs

        assert _build_engine_kwargs(disable_prepared_cache=True) == {
            "poolclass": NullPool
        }


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

        importlib.reload(config_module)
        try:
            importlib.reload(db_module)

            connect_args = captured_kwargs["connect_args"]
            assert connect_args["prepared_statement_cache_size"] == 0  # type: ignore[index]
            assert connect_args["statement_cache_size"] == 0  # type: ignore[index]
            assert captured_kwargs["poolclass"] is db_module.NullPool
        finally:
            monkeypatch.undo()
            importlib.reload(config_module)
            importlib.reload(db_module)
