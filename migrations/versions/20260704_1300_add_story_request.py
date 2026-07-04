"""add story_request table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-04 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the story_request table, its indexes, and its status CHECK."""
    op.create_table(
        "story_request",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("request_text", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "moderation_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concept_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["family_id"], ["family.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["child_profile.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["user.id"]),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'declined', 'blocked')",
            name="ck_story_request_status",
        ),
    )
    op.create_index(
        "ix_story_request_family_status",
        "story_request",
        ["family_id", "status"],
    )
    op.create_index(
        "ix_story_request_profile_status",
        "story_request",
        ["profile_id", "status"],
    )
    op.create_index("ix_story_request_status", "story_request", ["status"])


def downgrade() -> None:
    """Drop the story_request table (Postgres drops its indexes with it)."""
    op.drop_table("story_request")
