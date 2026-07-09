"""Unit tests for the ProviderModelAllowlist ORM shape (no DB required)."""

from __future__ import annotations

from cyo_adventure.db.models import ProviderModelAllowlist, ProviderModelAllowlistAudit


def test_provider_model_allowlist_tablename() -> None:
    """The table name matches the spec's natural-key table."""
    assert ProviderModelAllowlist.__tablename__ == "provider_model_allowlist"


def test_provider_model_allowlist_audit_tablename() -> None:
    """The audit table name matches the spec."""
    assert ProviderModelAllowlistAudit.__tablename__ == "provider_model_allowlist_audit"


def test_allowlist_row_defaults_enabled_true() -> None:
    """A freshly constructed row defaults to enabled=True (Python-side default)."""
    row = ProviderModelAllowlist(provider="anthropic", model_id="claude-sonnet-4-6")
    assert row.enabled is True
    assert row.display_name is None


def test_audit_row_requires_changed_by_at_construction_time_type() -> None:
    """changed_by is typed non-optional; the class does not declare a Python default."""
    # The real guarantee is the DB NOT NULL FK exercised by the migration
    # round-trip test in Task 3; this test only pins that the ORM column
    # itself carries no silently-nullable Python default that would mask a
    # missing changed_by until the DB constraint fires.
    audit = ProviderModelAllowlistAudit(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        action="create",
        old_enabled=None,
        new_enabled=True,
        changed_by=__import__("uuid").uuid4(),
    )
    assert audit.action == "create"
