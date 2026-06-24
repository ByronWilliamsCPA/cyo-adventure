"""add rating table

Revision ID: a1b2c3d4e5f6
Revises: 78336bfff81e
Create Date: 2026-06-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '78336bfff81e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('rating',
    sa.Column('child_profile_id', sa.Uuid(), nullable=False),
    sa.Column('storybook_id', sa.String(length=120), nullable=False),
    sa.Column('value', sa.Integer(), nullable=False),
    sa.Column('rated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('value BETWEEN 1 AND 5', name='ck_rating_value_range'),
    sa.ForeignKeyConstraint(['child_profile_id'], ['child_profile.id'], ),
    sa.ForeignKeyConstraint(['storybook_id'], ['storybook.id'], ),
    sa.PrimaryKeyConstraint('child_profile_id', 'storybook_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('rating')
