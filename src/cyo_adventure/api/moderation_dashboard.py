"""Admin read-only moderation insight dashboard (WS-F).

Aggregates persisted moderation reports and the pipeline event log into
override evidence and threshold suggestions. Read-only: the only write in
the WS-F flow is the reused, audited threshold upsert in
``api/moderation_thresholds.py`` (decision F3).
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import (
    CategoryInsightView,
    MinVerdict,
    ModerationDashboardView,
    SuggestionListView,
    ThresholdChangeView,
    ThresholdSuggestionView,
)
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import PipelineEvent
from cyo_adventure.events import EventType
from cyo_adventure.moderation.insights import (
    SUGGESTION_MIN_DECIDED,
    SUGGESTION_MIN_OVERRIDE_RATE,
    aggregate_insights,
    load_version_records,
    suggest_thresholds,
)
from cyo_adventure.moderation.thresholds import load_threshold_policy

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


@router.get("/admin/moderation/suggestions")
async def moderation_suggestions(ctx: Context) -> SuggestionListView:
    """Computed threshold proposals awaiting admin ratification.

    Never applied automatically (umbrella decision 3); the apply control on
    the dashboard calls the existing audited threshold upsert (F3), and a
    raised threshold retires its own suggestion (F2).
    """
    _require_admin(ctx)
    records = await load_version_records(ctx.session)
    insights = aggregate_insights(records)
    policy = await load_threshold_policy(ctx.session)
    suggestions = suggest_thresholds(insights, policy)
    return SuggestionListView(
        min_decided_versions=SUGGESTION_MIN_DECIDED,
        min_override_rate=SUGGESTION_MIN_OVERRIDE_RATE,
        suggestions=[
            ThresholdSuggestionView(
                age_band=suggestion.age_band,
                category=suggestion.category,
                current_min_verdict=cast("MinVerdict", suggestion.current_min_verdict),
                current_min_score=suggestion.current_min_score,
                suggested_min_verdict=cast(
                    "MinVerdict", suggestion.suggested_min_verdict
                ),
                override_rate=suggestion.override_rate,
                decided_versions=suggestion.decided_versions,
                released_versions=suggestion.released_versions,
            )
            for suggestion in suggestions
        ],
    )
