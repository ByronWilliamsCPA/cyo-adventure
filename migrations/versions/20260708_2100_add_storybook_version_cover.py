"""Add storybook_version cover columns (book-cover feature, Task 2).

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-08 21:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None

_COVER_STATUS_VALUES = "'none', 'generating', 'ready', 'failed'"


def upgrade() -> None:
    """Add cover_image_url (nullable) and cover_status (backfilled) columns.

    cover_status uses a server_default so existing rows backfill to "none"
    without a separate data migration; cover_image_url stays nullable since
    no cover has been generated for pre-existing rows.
    """
    op.add_column(
        "storybook_version",
        sa.Column("cover_image_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "storybook_version",
        sa.Column(
            "cover_status",
            sa.String(length=20),
            nullable=False,
            server_default="none",
        ),
    )
    op.create_check_constraint(
        "ck_storybook_version_cover_status",
        "storybook_version",
        f"cover_status IN ({_COVER_STATUS_VALUES})",
    )


def downgrade() -> None:
    """Drop the cover columns and their check constraint."""
    op.drop_constraint(
        "ck_storybook_version_cover_status",
        "storybook_version",
        type_="check",
    )
    op.drop_column("storybook_version", "cover_status")
    op.drop_column("storybook_version", "cover_image_url")
