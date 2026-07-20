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


def test_audit_row_changed_by_is_nullable_with_set_null_ondelete() -> None:
    """changed_by is nullable with ON DELETE SET NULL, not NOT NULL (Phase 3a).

    Every real write path (the admin API) always stamps a real admin here;
    this column is nullable specifically so a guardian/admin's Article 17
    self-deletion is never blocked by an FK violation on audit rows from
    before their account was erased. See the column's #CRITICAL comment in
    db/models.py and tests/integration/test_deletion_drill.py for the erasure
    path this enables.
    """
    column = ProviderModelAllowlistAudit.__table__.c.changed_by
    assert column.nullable is True
    fk = next(iter(column.foreign_keys))
    assert fk.ondelete == "SET NULL"
    audit = ProviderModelAllowlistAudit(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        action="create",
        old_enabled=None,
        new_enabled=True,
        changed_by=uuid.uuid4(),
    )
    assert audit.action == "create"
