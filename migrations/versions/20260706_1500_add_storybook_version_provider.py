"""add storybook_version provider column

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-06 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable storybook_version.provider column (F18/#63).

    Nullable, no backfill: existing rows predate provenance tracking and
    simply have no recorded provider, which degrades to "unknown" for
    display rather than an error.
    """
    op.add_column(
        "storybook_version",
        sa.Column("provider", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    """Drop storybook_version.provider."""
    op.drop_column("storybook_version", "provider")
