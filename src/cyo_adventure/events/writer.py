"""Append a PipelineEvent row from the transaction performing a transition."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

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
    EventType.RELEASED: frozenset({"visibility"}),
    EventType.THRESHOLD_CHANGED: frozenset(
        {"age_band", "category", "action", "min_verdict", "min_score"}
    ),
    EventType.NOISE_FLOOR_CHANGED: frozenset({"value"}),
    EventType.BOOK_ASSIGNED: frozenset({"child_profile_id"}),
    EventType.RATED: frozenset({"value", "is_update"}),
    # K15: a structured, no-free-text child signal (ADR-016). Only the closed
    # vocabulary reason and the storybook id are ever recorded here; the flag
    # itself carries no free text and neither does this event.
    EventType.KID_FLAGGED: frozenset({"reason", "storybook_id"}),
    EventType.FLAG_RESOLVED: frozenset({"resolution"}),
}


# Longest legitimate payload string value is a provider/model identifier or a
# str(uuid) (36 chars); a controlled-vocabulary value never approaches this.
# The bound turns a free-text value (story prose, a child name mistakenly
# routed under an allowlisted key) into a hard rejection.
_MAX_PAYLOAD_STR_LEN = 200


def _validate_payload_value(event_type: EventType, key: str, value: object) -> None:
    """Reject payload values that are not PII-safe scalars, counts, or ids.

    Key-level allowlisting (below) guarantees only expected keys are present;
    this guards the VALUES under those keys so the PII-free contract (spec D3)
    does not rest on caller discipline alone. Permitted: None, bool, int,
    float, a bounded str, or a dict of str->int (moderation verdict counts).
    """
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if len(value) > _MAX_PAYLOAD_STR_LEN:
            msg = (
                f"payload value for {event_type}.{key} exceeds "
                f"{_MAX_PAYLOAD_STR_LEN} chars; free text is not permitted (D3)"
            )
            raise ValidationError(msg, field=key, value=len(value))
        return
    if isinstance(value, dict):
        pairs = cast("dict[object, object]", value)
        if all(isinstance(k, str) and isinstance(v, int) for k, v in pairs.items()):
            return
    msg = f"payload value for {event_type}.{key} is not a PII-safe scalar or count (D3)"
    raise ValidationError(msg, field=key, value=type(value).__name__)


def _validate_payload(event_type: EventType, payload: dict[str, object]) -> None:
    allowed = _PAYLOAD_ALLOWLIST[event_type]
    extra = set(payload) - allowed
    if extra:
        msg = f"payload for {event_type} has disallowed keys: {sorted(extra)}"
        raise ValidationError(msg, field="payload", value=sorted(extra))
    for key, value in payload.items():
        _validate_payload_value(event_type, key, value)


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
