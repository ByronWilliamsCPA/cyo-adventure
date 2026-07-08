"""add story_request lifecycle fields (WS-B PR 1)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-08 09:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add lifecycle columns, backfill band from the profile, then constrain."""
    op.add_column(
        "story_request",
        sa.Column(
            "initiator_role",
            sa.String(length=16),
            server_default=sa.text("'child'"),
            nullable=False,
        ),
    )
    op.add_column(
        "story_request", sa.Column("age_band", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "story_request", sa.Column("length", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "story_request",
        sa.Column(
            "narrative_style",
            sa.String(length=16),
            server_default=sa.text("'prose'"),
            nullable=False,
        ),
    )
    # #CRITICAL: data integrity: every historical row must get a band before the
    # NOT NULL tightening; the moderation flag context reads it after the flip.
    # #VERIFY: test_backfill_band_from_profile_and_role_default.
    op.execute(
        "UPDATE story_request SET age_band = child_profile.age_band "
        "FROM child_profile WHERE story_request.profile_id = child_profile.id"
    )
    op.alter_column("story_request", "age_band", nullable=False)
    op.alter_column("story_request", "profile_id", nullable=True)
    op.create_check_constraint(
        "ck_story_request_initiator_role",
        "story_request",
        "initiator_role IN ('child', 'guardian', 'admin')",
    )
    op.create_check_constraint(
        "ck_story_request_age_band",
        "story_request",
        "age_band IN ('3-5', '5-8', '8-11', '10-13', '13-16', '16+')",
    )
    op.create_check_constraint(
        "ck_story_request_length",
        "story_request",
        "length IS NULL OR length IN ('short', 'medium', 'long')",
    )
    op.create_check_constraint(
        "ck_story_request_narrative_style",
        "story_request",
        "narrative_style IN ('prose', 'gamebook')",
    )
    op.create_check_constraint(
        "ck_story_request_style_band",
        "story_request",
        "narrative_style = 'prose' OR age_band IN ('13-16', '16+')",
    )


def downgrade() -> None:
    """Drop the WS-B lifecycle columns and restore profile_id NOT NULL."""
    op.drop_constraint("ck_story_request_style_band", "story_request", type_="check")
    op.drop_constraint(
        "ck_story_request_narrative_style", "story_request", type_="check"
    )
    op.drop_constraint("ck_story_request_length", "story_request", type_="check")
    op.drop_constraint("ck_story_request_age_band", "story_request", type_="check")
    op.drop_constraint(
        "ck_story_request_initiator_role", "story_request", type_="check"
    )
    op.alter_column("story_request", "profile_id", nullable=False)
    op.drop_column("story_request", "narrative_style")
    op.drop_column("story_request", "length")
    op.drop_column("story_request", "age_band")
    op.drop_column("story_request", "initiator_role")
