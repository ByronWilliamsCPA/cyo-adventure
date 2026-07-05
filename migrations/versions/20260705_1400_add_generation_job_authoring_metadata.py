"""add generation_job authoring_metadata column and awaiting_manual_fill status

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-05 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add authoring_metadata; widen the status CHECK for awaiting_manual_fill."""
    op.add_column(
        "generation_job",
        sa.Column(
            "authoring_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.drop_constraint("ck_generation_job_status", "generation_job", type_="check")
    op.create_check_constraint(
        "ck_generation_job_status",
        "generation_job",
        "status IN ('queued', 'running', 'passed', 'needs_review', 'failed', "
        "'awaiting_manual_fill')",
    )


def downgrade() -> None:
    """Drop authoring_metadata; restore the original status CHECK."""
    op.drop_constraint("ck_generation_job_status", "generation_job", type_="check")
    op.create_check_constraint(
        "ck_generation_job_status",
        "generation_job",
        "status IN ('queued', 'running', 'passed', 'needs_review', 'failed')",
    )
    op.drop_column("generation_job", "authoring_metadata")
