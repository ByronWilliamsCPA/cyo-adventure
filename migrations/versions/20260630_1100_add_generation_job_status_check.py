"""add generation_job status check constraint

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-30 11:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "ck_generation_job_status",
        "generation_job",
        "status IN ('queued', 'running', 'passed', 'needs_review', 'failed')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_generation_job_status", "generation_job", type_="check")
