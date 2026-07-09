"""Add append-only pipeline_event table (WS-D).

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-08 18:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

_APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION pipeline_event_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'pipeline_event is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

_APPEND_ONLY_TRIGGER = """
CREATE TRIGGER trg_pipeline_event_append_only
BEFORE UPDATE OR DELETE ON pipeline_event
FOR EACH ROW EXECUTE FUNCTION pipeline_event_append_only();
"""


def upgrade() -> None:
    """Create pipeline_event, its indexes, and the append-only trigger."""
    op.create_table(
        "pipeline_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("actor_role", sa.String(length=16), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        # Closed-vocabulary CHECKs (literal lists, self-contained per migration
        # convention). These must match the PipelineEvent model's constraints
        # (ck_pipeline_event_* added in Task 2's fix). If the EventType enum or
        # the entity/role vocab changes, both this migration's successor and the
        # model change together.
        sa.CheckConstraint(
            "event_type IN ('request_created', 'request_approved', "
            "'request_declined', 'plan_assigned', 'generation_started', "
            "'generation_finished', 'moderation_completed', 'repair_applied', "
            "'sent_back', 'released', 'threshold_changed', 'noise_floor_changed', "
            "'book_assigned', 'rated')",
            name="ck_pipeline_event_event_type",
        ),
        sa.CheckConstraint(
            "actor_role IN ('system', 'guardian', 'child', 'admin')",
            name="ck_pipeline_event_actor_role",
        ),
        sa.CheckConstraint(
            "entity_type IN ('story_request', 'generation_job', 'storybook', "
            "'storybook_version', 'series', 'storybook_assignment', 'rating', "
            "'moderation_threshold', 'moderation_setting')",
            name="ck_pipeline_event_entity_type",
        ),
    )
    op.create_index(
        "ix_pipeline_event_entity", "pipeline_event", ["entity_type", "entity_id"]
    )
    op.create_index("ix_pipeline_event_event_type", "pipeline_event", ["event_type"])
    op.create_index("ix_pipeline_event_occurred_at", "pipeline_event", ["occurred_at"])
    op.execute(_APPEND_ONLY_FN)
    op.execute(_APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    """Drop the trigger, function, indexes, and table."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_pipeline_event_append_only ON pipeline_event"
    )
    op.execute("DROP FUNCTION IF EXISTS pipeline_event_append_only()")
    op.drop_index("ix_pipeline_event_occurred_at", table_name="pipeline_event")
    op.drop_index("ix_pipeline_event_event_type", table_name="pipeline_event")
    op.drop_index("ix_pipeline_event_entity", table_name="pipeline_event")
    op.drop_table("pipeline_event")
