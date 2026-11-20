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

import asyncio

import pytest

import cyo_adventure.db.models  # noqa: F401  # populate Base.metadata
import scripts.reset_e2e_real_state as reset
from cyo_adventure.core.database import Base
from cyo_adventure.core.exceptions import BusinessLogicError, ConfigurationError

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


# --- --stamp-fixture-moderation (build_fixture_moderation_report) -----------

_GENERATED_ID = "s_3f2a1c9e-1b2c-4d5e-8f90-a1b2c3d4e5f6"


def _mock_stamped_report() -> dict[str, object]:
    """A stored mock-reviewer report, shaped like ``_stamp_mock_reviewer`` output."""
    return {
        "findings": [
            {
                "stage": 0,
                "source": "pipeline",
                "category": "pipeline",
                "verdict": "advisory",
                "message": "moderated with the mock reviewer; no real safety review ran",
                "structural": True,
                "concern": "mock_reviewer_active",
            }
        ],
        "reviewer": {
            "provider": "mock",
            "model": None,
            "endpoint": [],
            "temperature": None,
            "batch_size": 8,
        },
        "aggregate": {"nodes_reviewed": 9, "pass_counts": {"llm_safety": 9}},
        "summary": {
            "count": 1,
            "hard_block": False,
            "soft_flag": False,
            "coverage_complete": True,
            "repaired": False,
            "reviewer_independent": False,
        },
    }


def test_the_mock_stamped_input_is_refused_by_the_approval_gate() -> None:
    """Precondition: the input shape really is what approve() refuses today."""
    assert reset.moderation_report_unusable(_mock_stamped_report()) is True


def test_fixture_report_passes_the_approval_predicates() -> None:
    """The stamped replacement clears both gates approve() asks first."""
    report = reset.build_fixture_moderation_report(
        _GENERATED_ID, _mock_stamped_report()
    )
    assert reset.moderation_report_unusable(report) is False
    assert reset.moderation_coverage_incomplete(report) is False
    assert report["findings"] == []
    reviewer = report["reviewer"]
    assert isinstance(reviewer, dict)
    # The row names its own origin, never a real reviewer.
    assert reviewer["provider"] == "e2e-fixture"
    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["nodes_reviewed"] == 9


@pytest.mark.parametrize(
    "storybook_id",
    ["s_bridge_builder", "s_tide_pools", "sk_some_skeleton", "s_not-a-uuid"],
)
def test_fixture_report_refuses_a_non_generated_story_id(storybook_id: str) -> None:
    """Seeded and imported slugs can never be stamped approvable."""
    with pytest.raises(BusinessLogicError, match="not a worker-generated"):
        reset.build_fixture_moderation_report(storybook_id, _mock_stamped_report())


def test_fixture_report_refuses_a_report_without_the_mock_stamp() -> None:
    """A report that may be a genuine judgment is never overwritten."""
    genuine = _mock_stamped_report()
    genuine["findings"] = []
    summary = genuine["summary"]
    assert isinstance(summary, dict)
    summary["reviewer_independent"] = True
    with pytest.raises(BusinessLogicError, match="mock-reviewer stamp"):
        reset.build_fixture_moderation_report(_GENERATED_ID, genuine)


def test_fixture_report_refuses_independence_false_without_the_stamp_finding() -> None:
    """Both mock marks are required, not just reviewer_independent=False."""
    partial = _mock_stamped_report()
    partial["findings"] = []
    with pytest.raises(BusinessLogicError, match="mock-reviewer stamp"):
        reset.build_fixture_moderation_report(_GENERATED_ID, partial)


@pytest.mark.parametrize("stored", [None, "not a dict", {"findings": "x"}])
def test_fixture_report_refuses_a_malformed_stored_report(stored: object) -> None:
    """A missing or corrupt report is not evidence of a mock run."""
    with pytest.raises(BusinessLogicError, match="mock-reviewer stamp"):
        reset.build_fixture_moderation_report(_GENERATED_ID, stored)


def test_stamp_guard_refuses_non_local_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stamp mode shares the reset's local-database guard."""
    _set_settings(monkeypatch, environment="production", dsn=_LOCAL_DSN)
    with pytest.raises(ConfigurationError, match="stamp an e2e-real fixture"):
        asyncio.run(reset.stamp_fixture_moderation(_GENERATED_ID))
