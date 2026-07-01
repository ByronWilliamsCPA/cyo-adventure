"""add storybook status and user role check constraints

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        'ck_storybook_status',
        'storybook',
        "status IN ('draft', 'in_review', 'needs_revision', "
        "'published', 'archived')",
    )
    op.create_check_constraint(
        'ck_user_role',
        'user',
        "role IN ('guardian', 'child', 'admin')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_user_role', 'user', type_='check')
    op.drop_constraint('ck_storybook_status', 'storybook', type_='check')
