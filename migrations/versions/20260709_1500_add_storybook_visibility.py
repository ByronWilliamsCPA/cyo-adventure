"""Add storybook.visibility for the guardian catalog (WS-E, decision E1).

Revision ID: 9c4e7d2a5b18
Revises: 228c68e8f1e7
Create Date: 2026-07-09 15:00:00
"""

from __future__ import annotations

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c4e7d2a5b18"
down_revision: Union[str, Sequence[str], None] = "228c68e8f1e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the visibility column; existing rows backfill to 'family'."""
    op.add_column(
        "storybook",
        sa.Column(
            "visibility",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'family'"),
        ),
    )
    op.create_check_constraint(
        "ck_storybook_visibility",
        "storybook",
        "visibility IN ('family', 'catalog')",
    )


def downgrade() -> None:
    """Drop the visibility constraint and column."""
    op.drop_constraint("ck_storybook_visibility", "storybook", type_="check")
    op.drop_column("storybook", "visibility")
