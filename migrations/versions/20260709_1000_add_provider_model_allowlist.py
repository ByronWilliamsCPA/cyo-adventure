"""add provider_model_allowlist and its audit table, seeded (WS-C PR1)

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-09 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# #ASSUME: data-integrity: this seed list is hand-synced with
# cyo_adventure.generation.allowlist.DEFAULT_ALLOWLIST. Migrations are frozen
# and must not import live app constants (same rule as
# 20260707_1700_add_moderation_setting.py's admin_noise_floor seed), so the
# two lists are kept in lockstep by hand.
# #VERIFY: tests/integration/test_provider_model_allowlist_migration.py
# asserts the row count equals 5 and spot-checks two representative
# (provider, model_id) pairs are present and enabled after upgrade.
_SEED_ROWS = (
    ("anthropic", "claude-sonnet-4-6", "Claude Sonnet 4.6 (direct)"),
    ("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5 (direct)"),
    ("openrouter", "anthropic/claude-haiku-4.5", "OpenRouter primary (Haiku 4.5)"),
    ("openrouter", "anthropic/claude-sonnet-4.6", "OpenRouter fallback (Sonnet 4.6)"),
    ("ollama", "qwen2.5:14b", "Ollama local default"),
)


def upgrade() -> None:
    """Create the allowlist table and its append-only audit table, then seed."""
    op.create_table(
        "provider_model_allowlist",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('anthropic', 'openrouter', 'modal', 'ollama')",
            name="ck_provider_model_allowlist_provider",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "model_id", name="uq_provider_model_allowlist_provider_model"
        ),
    )
    op.create_table(
        "provider_model_allowlist_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("old_enabled", sa.Boolean(), nullable=True),
        sa.Column("new_enabled", sa.Boolean(), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "changed_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="ck_provider_model_allowlist_audit_action",
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # #ASSUME: external-resources: gen_random_uuid() is a PostgreSQL 13+
    # built-in (moved out of the pgcrypto extension into core in PG13); the
    # testcontainers image (postgres:16-alpine) and Supabase's managed
    # Postgres both satisfy this, so no CREATE EXTENSION is needed.
    # #VERIFY: test_seed_rows_present_after_upgrade below runs this migration
    # against postgres:16-alpine.
    for provider, model_id, display_name in _SEED_ROWS:
        op.execute(
            sa.text(
                "INSERT INTO provider_model_allowlist "
                "(id, provider, model_id, enabled, display_name, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :provider, :model_id, true, "
                ":display_name, now(), now())"
            ).bindparams(provider=provider, model_id=model_id, display_name=display_name)
        )


def downgrade() -> None:
    """Drop both new tables (seed rows go with the table)."""
    op.drop_table("provider_model_allowlist_audit")
    op.drop_table("provider_model_allowlist")
