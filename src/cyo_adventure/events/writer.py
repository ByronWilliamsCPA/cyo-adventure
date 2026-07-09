"""Append a PipelineEvent row from the transaction performing a transition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import PipelineEvent
from cyo_adventure.events.models import Actor, EventType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Per-event-type payload key allowlist. Keys not listed are rejected before write.
# This is the enforcement mechanism for the PII-free payload contract (spec D3):
# ids, enum values, scores, counts, controlled-vocab reasons only; never free text.
_PAYLOAD_ALLOWLIST: dict[EventType, frozenset[str]] = {
    EventType.REQUEST_CREATED: frozenset({"initiator_role"}),
    EventType.REQUEST_APPROVED: frozenset(
        {"series_created", "anchor_resolved", "series_id"}
    ),
    EventType.REQUEST_DECLINED: frozenset(),
    EventType.PLAN_ASSIGNED: frozenset({"job_status", "plan_kind"}),
    EventType.GENERATION_STARTED: frozenset(),
    EventType.GENERATION_FINISHED: frozenset(
        {"outcome", "provider", "model", "prompt_version"}
    ),
    EventType.MODERATION_COMPLETED: frozenset(
        {"overall_verdict", "repaired", "counts"}
    ),
    EventType.REPAIR_APPLIED: frozenset({"stage"}),
    EventType.SENT_BACK: frozenset(),
    EventType.RELEASED: frozenset(),
    EventType.THRESHOLD_CHANGED: frozenset(
        {"age_band", "category", "action", "min_verdict", "min_score"}
    ),
    EventType.NOISE_FLOOR_CHANGED: frozenset({"value"}),
    EventType.BOOK_ASSIGNED: frozenset({"child_profile_id"}),
    EventType.RATED: frozenset({"value", "is_update"}),
}


def _validate_payload(event_type: EventType, payload: dict[str, object]) -> None:
    allowed = _PAYLOAD_ALLOWLIST[event_type]
    extra = set(payload) - allowed
    if extra:
        msg = f"payload for {event_type} has disallowed keys: {sorted(extra)}"
        raise ValidationError(msg, field="payload", value=sorted(extra))


async def record_event(
    session: AsyncSession,
    actor: Actor,
    *,
    entity_type: str,
    entity_id: str,
    event_type: EventType,
    from_state: str | None = None,
    to_state: str | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    """Add one append-only PipelineEvent to the caller's session and flush.

    The row inherits the caller's transaction: it commits with the transition and
    rolls back with it (spec decision D1). Never opens or commits its own transaction.

    # #CRITICAL: data-integrity: an event with an out-of-contract payload would leak
    #   PII into a durable append-only log (spec D3).
    # #VERIFY: _validate_payload rejects any key outside the per-event allowlist;
    #   tested in tests/unit/test_pipeline_event_writer.py.
    # #CRITICAL: external-resources: this writes to Postgres inside the caller's unit
    #   of work; a failure here must roll the transition back, not be swallowed.
    # #VERIFY: no try/except; the exception propagates to the unit-of-work.
    """
    data = payload or {}
    _validate_payload(event_type, data)
    session.add(
        PipelineEvent(
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=str(event_type),
            from_state=from_state,
            to_state=to_state,
            payload=data,
        )
    )
    await session.flush()
