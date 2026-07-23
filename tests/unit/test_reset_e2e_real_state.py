"""Unit tests for the ``scripts.reset_e2e_real_state`` safety guard.

Only ``_require_local_database`` is exercised here: it is the pure,
side-effect-free tripwire that stands between the module's destructive
``TRUNCATE``/``UPDATE``/``DELETE`` statements and a shared or production
database. The statement-level behaviour (what each DELETE cascades to) is
covered by the real-backend e2e harness against a live disposable Postgres, not
by these unit tests, because it depends on the actual schema and CASCADE rules.

These back the ``#VERIFY`` markers on ``_require_local_database`` in
``scripts/reset_e2e_real_state.py``.
"""

from __future__ import annotations

import pytest

import scripts.reset_e2e_real_state as reset
from cyo_adventure.core.exceptions import ConfigurationError

_LOCAL_DSN = "postgresql+asyncpg://cyo:cyo@localhost:5442/cyo_adventure"


def _set_settings(
    monkeypatch: pytest.MonkeyPatch, *, environment: str, dsn: str
) -> None:
    """Point the module-level settings singleton at a test environment/DSN."""
    monkeypatch.setattr(reset.settings, "environment", environment)
    monkeypatch.setattr(reset.settings, "database_url", dsn)


def test_require_local_database_accepts_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local environment with a localhost DSN passes the guard silently."""
    _set_settings(monkeypatch, environment="local", dsn=_LOCAL_DSN)
    reset._require_local_database()  # must not raise


def test_require_local_database_refuses_non_local_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-local environment is rejected even with a localhost DSN."""
    _set_settings(monkeypatch, environment="production", dsn=_LOCAL_DSN)
    with pytest.raises(ConfigurationError, match="not 'local'"):
        reset._require_local_database()


def test_require_local_database_refuses_hosted_supabase_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hosted Supabase DSN is rejected by the explicit denylist tripwire."""
    dsn = "postgresql+asyncpg://u:p@db.cvrnaydpzijtszfbsraq.supabase.co:5432/postgres"
    _set_settings(monkeypatch, environment="local", dsn=dsn)
    with pytest.raises(ConfigurationError, match="Supabase"):
        reset._require_local_database()


def test_require_local_database_refuses_hosted_supabase_pooler_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pooler host shape (``*.pooler.supabase.com``) is rejected too."""
    dsn = "postgresql+asyncpg://u:p@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    _set_settings(monkeypatch, environment="local", dsn=dsn)
    with pytest.raises(ConfigurationError, match="Supabase"):
        reset._require_local_database()


def test_require_local_database_refuses_non_local_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-local, non-Supabase host still fails the localhost allowlist."""
    dsn = "postgresql+asyncpg://u:p@db.internal.example:5432/postgres"
    _set_settings(monkeypatch, environment="local", dsn=dsn)
    with pytest.raises(ConfigurationError, match="is not local"):
        reset._require_local_database()
