"""add storybook_assignment table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the table, then backfill to preserve current visibility."""
    op.create_table(
        "storybook_assignment",
        sa.Column("child_profile_id", sa.Uuid(), nullable=False),
        sa.Column("storybook_id", sa.String(length=120), nullable=False),
        sa.Column("assigned_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["child_profile_id"], ["child_profile.id"]),
        sa.ForeignKeyConstraint(["storybook_id"], ["storybook.id"]),
        sa.ForeignKeyConstraint(["assigned_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("child_profile_id", "storybook_id"),
    )
    op.create_index(
        "ix_storybook_assignment_storybook_id",
        "storybook_assignment",
        ["storybook_id"],
    )
    # Backfill: preserve exactly today's visibility (every child in a family sees
    # every published story in that family). assigned_by NULL marks the system
    # backfill. Books published AFTER this migration require an explicit assign.
    # #CRITICAL: data integrity: this INSERT ... SELECT is the sole guarantee that
    # no currently-visible story disappears on deploy; the family-scoped JOIN plus
    # the published filter must exactly reproduce prior visibility, never widening
    # it across families nor narrowing it below the pre-assignment gate.
    # #VERIFY: test_assignment_backfill_data_integrity asserts exact-set equality
    # across two families (no cross-family pair, no draft row).
    op.execute(
        sa.text(
            "INSERT INTO storybook_assignment "
            "(child_profile_id, storybook_id, assigned_by, created_at) "
            "SELECT cp.id, sb.id, NULL, now() "
            "FROM storybook sb "
            "JOIN child_profile cp ON cp.family_id = sb.family_id "
            "WHERE sb.status = 'published'"
        )
    )


def downgrade() -> None:
    """Drop the assignment table (Postgres drops its dependent index with it)."""
    op.drop_table("storybook_assignment")
