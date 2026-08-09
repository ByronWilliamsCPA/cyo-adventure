"""Unit tests for the ``scripts.reset_e2e_real_state`` safety guard.

``_require_local_database`` is the pure, side-effect-free tripwire that
stands between the module's destructive ``TRUNCATE``/``UPDATE``/``DELETE``
statements and a shared or production database. The statement-level
behaviour (what each DELETE cascades to) is covered by the real-backend e2e
harness against a live disposable Postgres, not by these unit tests, because
it depends on the actual schema and CASCADE rules.

These back the ``#VERIFY`` markers on ``_require_local_database`` in
``scripts/reset_e2e_real_state.py``.

``test_truncated_tables_cover_every_dependent_foreign_key`` is different: it
is a schema-derived invariant check, not a guard-behaviour test. It replaces
a prose ``#ASSUME`` comment that once claimed "nothing declares a foreign key
onto reading_state", a claim that PR #649 (``character_book_completion``)
falsified silently: the comment was never re-checked by anything, and the
``#VERIFY`` test it cited did not exist (grandfathered in
``rad-citation-baseline.toml``). This test walks live SQLAlchemy metadata
instead of trusting a comment, so the next foreign key added onto any table
``scripts/reset_e2e_real_state.py`` truncates fails this unit test instead of
only the real-backend Playwright job.
"""

from __future__ import annotations

import pytest

import cyo_adventure.db.models  # noqa: F401  # populate Base.metadata
import scripts.reset_e2e_real_state as reset
from cyo_adventure.core.database import Base
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


def test_truncated_tables_cover_every_dependent_foreign_key() -> None:
    """Every table with an FK onto a truncated table must itself be truncated.

    Postgres refuses ``TRUNCATE`` of a table referenced by a foreign key from
    a table not named in the same statement (``FeatureNotSupportedError``),
    and ``ondelete="CASCADE"`` does not rescue a ``TRUNCATE`` the way it
    rescues a ``DELETE``. This derives the answer from live SQLAlchemy
    metadata rather than trusting ``_TRUNCATED_TABLES`` to have been kept in
    sync by hand, so a future foreign key onto ``reading_state`` (or onto any
    other table in that set) fails here instead of only in the real-backend
    Playwright job.
    """
    truncated = set(reset._TRUNCATED_TABLES)
    uncovered_referencing_tables: set[str] = set()
    for table in Base.metadata.sorted_tables:
        for fk_constraint in table.foreign_key_constraints:
            referred_table_name = fk_constraint.referred_table.name
            if referred_table_name in truncated and table.name not in truncated:
                uncovered_referencing_tables.add(table.name)

    assert not uncovered_referencing_tables, (
        "these tables declare a foreign key onto a table in "
        "_TRUNCATED_TABLES but are not themselves in _TRUNCATED_TABLES, so "
        "the TRUNCATE statement in reset_e2e_real_state() will raise "
        f"FeatureNotSupportedError: {sorted(uncovered_referencing_tables)}"
    )
