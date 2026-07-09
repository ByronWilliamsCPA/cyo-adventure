"""Add series table and soft-continuation columns (WS-B PR 3).

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-08 16:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create series, then link story_request and storybook to it."""
    op.create_table(
        "series",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "family_id", sa.Uuid(), sa.ForeignKey("family.id"), nullable=False
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("age_band", sa.String(length=16), nullable=False),
        sa.Column("carries_state", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "age_band IN ('3-5', '5-8', '8-11', '10-13', '13-16', '16+')",
            name="ck_series_age_band",
        ),
    )
    op.create_index("ix_series_family_id", "series", ["family_id"])

    op.add_column("story_request", sa.Column("series_id", sa.Uuid(), nullable=True))
    op.add_column(
        "story_request",
        sa.Column("anchor_storybook_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "story_request",
        sa.Column("proposed_series_title", sa.String(length=120), nullable=True),
    )
    op.create_foreign_key(
        "fk_story_request_series_id_series",
        "story_request",
        "series",
        ["series_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_story_request_anchor_storybook_id_storybook",
        "story_request",
        "storybook",
        ["anchor_storybook_id"],
        ["id"],
    )
    # A request proposes a NEW series title or continues an existing series via
    # an anchor, never both. Name reflects the two columns constrained.
    op.create_check_constraint(
        "ck_story_request_title_anchor_mutex",
        "story_request",
        "NOT (proposed_series_title IS NOT NULL AND anchor_storybook_id IS NOT NULL)",
    )
    # An anchored (continuation) request must carry its series id; series_link
    # relies on it to assign book_index. Every anchored-insert path already sets
    # series_id from resolve_anchor; this blocks a drifted row.
    op.create_check_constraint(
        "ck_story_request_anchor_requires_series",
        "story_request",
        "anchor_storybook_id IS NULL OR series_id IS NOT NULL",
    )

    op.add_column("storybook", sa.Column("series_id", sa.Uuid(), nullable=True))
    op.add_column("storybook", sa.Column("book_index", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_storybook_series_id_series", "storybook", "series", ["series_id"], ["id"]
    )
    # #CRITICAL: concurrency: two continuations of the same series racing on book_index
    # #VERIFY: unique constraint plus one retry on conflict; concurrency test in PR 3
    op.create_unique_constraint(
        "uq_storybook_series_book_index", "storybook", ["series_id", "book_index"]
    )
    op.create_check_constraint(
        "ck_storybook_book_index", "storybook", "book_index IS NULL OR book_index >= 1"
    )
    op.create_check_constraint(
        "ck_storybook_series_index_pairing",
        "storybook",
        "(series_id IS NULL) = (book_index IS NULL)",
    )


def downgrade() -> None:
    """Drop the soft-continuation columns and the series table."""
    op.drop_constraint(
        "ck_storybook_series_index_pairing", "storybook", type_="check"
    )
    op.drop_constraint("ck_storybook_book_index", "storybook", type_="check")
    op.drop_constraint(
        "uq_storybook_series_book_index", "storybook", type_="unique"
    )
    op.drop_constraint("fk_storybook_series_id_series", "storybook", type_="foreignkey")
    op.drop_column("storybook", "book_index")
    op.drop_column("storybook", "series_id")
    op.drop_constraint(
        "ck_story_request_anchor_requires_series", "story_request", type_="check"
    )
    op.drop_constraint(
        "ck_story_request_title_anchor_mutex", "story_request", type_="check"
    )
    op.drop_constraint(
        "fk_story_request_anchor_storybook_id_storybook",
        "story_request",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_story_request_series_id_series", "story_request", type_="foreignkey"
    )
    op.drop_column("story_request", "proposed_series_title")
    op.drop_column("story_request", "anchor_storybook_id")
    op.drop_column("story_request", "series_id")
    op.drop_index("ix_series_family_id", table_name="series")
    op.drop_table("series")
