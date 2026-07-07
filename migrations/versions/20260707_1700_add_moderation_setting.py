"""add moderation_setting table with seeded admin noise floor (WS-A addendum)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-07 17:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create moderation_setting and seed the admin_noise_floor default."""
    op.create_table(
        "moderation_setting",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "value >= 0 AND value <= 1",
            name="ck_moderation_setting_value",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("key"),
    )
    # #ASSUME: data-integrity: the admin noise floor must exist from the first
    # request after this migration runs, since load_admin_noise_floor() only
    # falls back to the code default when the row is entirely absent (e.g. in
    # unit-test schemas built from metadata with no migration run at all). A
    # parameterized literal INSERT (not bulk_insert, which would bind
    # `now()` as a literal timestamp rather than a server-evaluated one) seeds
    # the row atomically with table creation.
    # #VERIFY: tests/integration/test_moderation_setting_migration.py asserts
    # the seeded row is present with value 0.05 immediately after upgrade.
    # Migrations are frozen and must not import live app constants, so this
    # literal is hand-maintained; it must match
    # cyo_adventure.moderation.thresholds.ADMIN_NOISE_FLOOR_KEY.
    op.execute(
        sa.text(
            "INSERT INTO moderation_setting (key, value, updated_at, updated_by) "
            "VALUES (:key, :value, now(), NULL)"
        ).bindparams(key="admin_noise_floor", value=0.05)
    )


def downgrade() -> None:
    """Drop the moderation_setting table."""
    op.drop_table("moderation_setting")
