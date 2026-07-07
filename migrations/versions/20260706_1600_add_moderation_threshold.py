"""add moderation_threshold and moderation_threshold_audit tables (WS-A)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-06 16:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the threshold override table and its append-only audit table."""
    op.create_table(
        "moderation_threshold",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("age_band", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("min_verdict", sa.String(length=16), nullable=False),
        sa.Column("min_score", sa.Float(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "min_verdict IN ('advisory', 'flag', 'block')",
            name="ck_moderation_threshold_min_verdict",
        ),
        sa.CheckConstraint(
            "min_score IS NULL OR (min_score >= 0.0 AND min_score <= 1.0)",
            name="ck_moderation_threshold_min_score",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "age_band", "category", name="uq_moderation_threshold_band_category"
        ),
    )
    op.create_table(
        "moderation_threshold_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("age_band", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("old_min_verdict", sa.String(length=16), nullable=True),
        sa.Column("new_min_verdict", sa.String(length=16), nullable=True),
        sa.Column("old_min_score", sa.Float(), nullable=True),
        sa.Column("new_min_score", sa.Float(), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "changed_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop both WS-A threshold tables."""
    op.drop_table("moderation_threshold_audit")
    op.drop_table("moderation_threshold")
