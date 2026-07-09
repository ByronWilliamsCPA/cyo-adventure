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
    """The ``enabled`` column declares a client-side default of True.

    SQLAlchemy applies ``mapped_column(default=...)`` at flush/INSERT time,
    not at Python construction, so this asserts the declared default via
    column metadata rather than reading the attribute off a freshly
    constructed (unflushed) instance.
    """
    assert ProviderModelAllowlist.__table__.c.enabled.default.arg is True


def test_audit_row_requires_changed_by_at_construction_time_type() -> None:
    """changed_by is typed non-optional; the class does not declare a Python default."""
    # The real guarantee is the DB NOT NULL FK exercised by the migration
    # round-trip test in Task 3; this test only pins that the ORM column
    # itself carries no silently-nullable Python default that would mask a
    # missing changed_by until the DB constraint fires.
    assert ProviderModelAllowlistAudit.__table__.c.changed_by.nullable is False
    audit = ProviderModelAllowlistAudit(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        action="create",
        old_enabled=None,
        new_enabled=True,
        changed_by=__import__("uuid").uuid4(),
    )
    assert audit.action == "create"
