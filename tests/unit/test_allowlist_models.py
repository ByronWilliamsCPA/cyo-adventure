"""Unit tests for the ProviderModelAllowlist ORM shape (no DB required)."""

from __future__ import annotations

import uuid

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


def test_audit_row_changed_by_column_is_non_nullable() -> None:
    """changed_by has no silently-nullable Python default, and a row constructed
    with it holds its fields.

    The real NOT NULL FK guarantee is exercised by the migration round-trip test
    in Task 3; this test only pins that the ORM column itself carries no
    Python-side default that would mask a missing changed_by until the DB
    constraint fires, and that a fully-specified row constructs cleanly.
    """
    assert ProviderModelAllowlistAudit.__table__.c.changed_by.nullable is False
    audit = ProviderModelAllowlistAudit(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        action="create",
        old_enabled=None,
        new_enabled=True,
        changed_by=uuid.uuid4(),
    )
    assert audit.action == "create"
