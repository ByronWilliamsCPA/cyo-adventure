"""Admin read-only moderation insight dashboard (WS-F).

Aggregates persisted moderation reports and the pipeline event log into
override evidence and threshold suggestions. Read-only: the only write in
the WS-F flow is the reused, audited threshold upsert in
``api/moderation_thresholds.py`` (decision F3).
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import (
    CategoryInsightView,
    ModerationDashboardView,
    ThresholdChangeView,
)
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import PipelineEvent
from cyo_adventure.events import EventType
from cyo_adventure.moderation.insights import aggregate_insights, load_version_records

router = APIRouter(prefix="/api/v1", tags=["moderation-dashboard"])

_RECENT_CHANGES_LIMIT = 20


def _require_admin(ctx: Context) -> None:
    """Reject non-admin principals before any read."""
    # #CRITICAL: security: these aggregates describe the moderation posture
    # across every family and drive threshold changes; admin-only (F5).
    # #VERIFY: tests/integration/test_moderation_dashboard_api.py::
    # TestDashboardEndpoint::test_guardian_gets_403
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


@router.get("/admin/moderation/dashboard")
async def moderation_dashboard(ctx: Context) -> ModerationDashboardView:
    """Aggregated override evidence plus recent threshold changes."""
    _require_admin(ctx)
    # #ASSUME: external-resources: a whole-corpus read per request is
    # deliberate at v1 volumes, mirroring load_version_records' own no-cache
    # stance; revisit with an occurred_at window if either grows large.
    # #VERIFY: tests/integration/test_moderation_dashboard_api.py::
    # TestDashboardEndpoint.
    records = await load_version_records(ctx.session)
    insights = aggregate_insights(records)
    recent = (
        await ctx.session.scalars(
            select(PipelineEvent)
            .where(
                PipelineEvent.event_type.in_(
                    [
                        EventType.THRESHOLD_CHANGED.value,
                        EventType.NOISE_FLOOR_CHANGED.value,
                    ]
                )
            )
            .order_by(PipelineEvent.occurred_at.desc())
            .limit(_RECENT_CHANGES_LIMIT)
        )
    ).all()
    return ModerationDashboardView(
        insights=[
            CategoryInsightView(
                age_band=insight.age_band,
                category=insight.category,
                advisory_findings=insight.advisory_findings,
                flag_findings=insight.flag_findings,
                decided_versions=insight.decided_versions,
                released_versions=insight.released_versions,
                override_rate=insight.override_rate,
                last_seen=insight.last_seen,
            )
            for insight in insights
        ],
        recent_changes=[
            ThresholdChangeView(
                occurred_at=event.occurred_at,
                event_type=event.event_type,
                entity_id=event.entity_id,
                payload=event.payload,
            )
            for event in recent
        ],
    )
