"""add storybook_version skeleton_slug column

Revision ID: 228c68e8f1e7
Revises: b4c5d6e7f8a9
Create Date: 2026-07-09 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "228c68e8f1e7"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable storybook_version.skeleton_slug column (WS-C PR2).

    Nullable, no backfill: fresh_generation and imported-book versions never
    had a skeleton, and every pre-PR2 skeleton_fill row predates this
    provenance column, so both simply have no recorded slug, which degrades
    to "unknown" for display rather than an error (mirrors the provider
    column's own null semantics, migration 20260706_1500).
    """
    op.add_column(
        "storybook_version",
        sa.Column("skeleton_slug", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    """Drop storybook_version.skeleton_slug."""
    op.drop_column("storybook_version", "skeleton_slug")
