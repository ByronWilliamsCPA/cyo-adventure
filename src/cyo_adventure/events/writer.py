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
        # ADR-015 G3: "auto_approved" is the pre-authorization audit marker
        # (True when this approval came from a guardian's standing envelope,
        # not a fresh explicit click); a bool, not free text, so it fits the
        # PII-free payload contract unchanged.
        {"series_created", "anchor_resolved", "series_id", "auto_approved"}
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
    # Gate entry carries no payload by design: the from_state already
    # distinguishes a first submit (draft) from a resubmission after a
    # send-back (needs_revision), and the actor_role distinguishes the
    # pipeline from a person. Nothing further is needed to measure
    # approval duration, and anything a reviewer typed would be free text.
    EventType.SUBMITTED: frozenset(),
    # Review-scorecard calibration (2026-08): the closed-vocabulary reason
    # code a reviewer selects alongside their free-text reason
    # (publishing/reason_codes.py::SendBackReasonCodeLiteral, validated by
    # that module's validate_reason_code before it reaches this payload).
    # An enum value, never free
    # text, so it fits the PII-free payload contract (D3) unchanged; the
    # free-text reason itself stays log-only, never persisted here.
    EventType.SENT_BACK: frozenset({"reason_code"}),
    # ADR-005 amendment (2026-08-25, gate D2): an admin may approve over a
    # block or high-severity finding with a recorded justification. The
    # justification itself is free text an admin typed, which the PII-free
    # payload contract (D3, see _MAX_PAYLOAD_STR_LEN below) forbids; it is
    # logged, not persisted, mirroring SENT_BACK's own free-text reason
    # staying log-only above. Only the structured counts of what was
    # overridden are audited here, present solely on the override path
    # (publishing/service.py::approve); a normal approval's payload keeps its
    # pre-existing shape.
    EventType.RELEASED: frozenset(
        {"visibility", "overridden_block_count", "overridden_high_count"}
    ),
    # A5 incident/pull-everywhere path: no payload needed, the
    # storybook entity_id is the only durable reference this transition
    # requires. SENT_BACK above used to be the comparison here and no longer
    # is: it now carries a reason_code.
    EventType.STORYBOOK_ARCHIVED: frozenset(),
    # `RS-C1`: the recall reason, from publishing/reason_codes.py's closed
    # recall vocabulary. Same shape and same D3 argument as SENT_BACK above.
    EventType.STORYBOOK_RECALLED: frozenset({"reason_code"}),
    EventType.THRESHOLD_CHANGED: frozenset(
        {"age_band", "category", "action", "min_verdict", "min_score"}
    ),
    EventType.NOISE_FLOOR_CHANGED: frozenset({"value"}),
    EventType.BOOK_ASSIGNED: frozenset({"child_profile_id"}),
    # G8 per-child unassign: mirrors BOOK_ASSIGNED. The revoked child's profile
    # id is an id, not free text, so it fits the PII-free payload contract (D3).
    EventType.BOOK_UNASSIGNED: frozenset({"child_profile_id"}),
    EventType.RATED: frozenset({"value", "is_update"}),
    # K15: a structured, no-free-text child signal (ADR-016). Only the closed
    # vocabulary reason and the storybook id are ever recorded here; the flag
    # itself carries no free text and neither does this event.
    EventType.KID_FLAGGED: frozenset({"reason", "storybook_id"}),
    EventType.FLAG_RESOLVED: frozenset({"resolution"}),
    # WS-J admin user management. Deliberately excludes email/display_name/
    # family name: those are contact/identity data, not the control-plane
    # facts (action, role, status) this log needs to stay PII-free (D3).
    EventType.USER_MANAGED: frozenset({"action", "role", "status"}),
    EventType.FAMILY_MANAGED: frozenset({"action", "status"}),
    # ADR-016 (register G17): "role" ("viewer"/"sharer") and "active" (both
    # sides now consented) are consent markers, not free text, added for the
    # new consent/revoke actions; "created"/"removed" (admin CRUD) never set
    # them. ADR-023 P4 adds "tombstoned_disclosure_consents", a COUNT of the
    # ring-2 consents the "removed" action revoked as a side effect: a bare
    # integer, so it names how much evidence changed state without naming
    # whose (no profile id, no slot value).
    EventType.FAMILY_CONNECTION_CHANGED: frozenset(
        {
            "action",
            "connected_family_id",
            "role",
            "active",
            "tombstoned_disclosure_consents",
        }
    ),
    # G6: the node id only, never the edited prose (spec D3); see
    # api/node_edit.py::edit_node.
    EventType.NODE_EDITED: frozenset({"node_id"}),
    # WS-8 catalog flywheel: the full cell coordinate plus the escalation
    # level. The producer (the CELL_SATURATED emitter) writes closed-vocabulary
    # enum values (AgeBand/Length/NarrativeStyle/DifferentiationLevel); the
    # writer's own guarantee is the key allowlist plus the payload-type/length
    # bound below (not enum-membership validation), which is enough that no theme
    # text, family, or child identifier can ride this payload. The flywheel
    # trigger's distinct-request denominator is the row's entity_id anchor, not
    # payload content (design section 4.1).
    EventType.CELL_SATURATED: frozenset({"age_band", "length", "style", "level"}),
    # Phase 8a: the family_id filter (None when the admin listed across
    # every family) and the row count returned; no profile-level detail, so
    # the log itself never becomes a second copy of the child data it is
    # auditing access to.
    EventType.PROFILE_VIEWED: frozenset({"family_id", "count"}),
    # ADR-023 P3/P4: the closed-vocabulary slot_type, which ring (1 or 2) it
    # was scoped to, and the action taken. Deliberately excludes any actual
    # personalization value (a child's name, a pet's name, a pronoun set):
    # this event audits that a slot was toggled, never what it now holds.
    EventType.PERSONALIZATION_TOGGLED: frozenset({"slot_type", "ring", "action"}),
    # ADR-023 P4: the connected family's id and a count of slot types
    # shared. Never the slot values or any child-identifying detail: the
    # count is enough to audit the grant without becoming a second copy of
    # what was shared.
    EventType.RING2_CONSENT_GRANTED: frozenset(
        {"connected_family_id", "slot_type_count"}
    ),
    # ADR-023 P4: the ring-2 consent counterpart to RING2_CONSENT_GRANTED;
    # only the connected family's id, since a revoke has no slot-count of
    # its own to audit.
    EventType.RING2_CONSENT_REVOKED: frozenset({"connected_family_id"}),
    # Moderation review redesign: the fresh report's overall gating verdict,
    # a PII-free per-verdict count mapping (mirrors MODERATION_COMPLETED's
    # own "counts" key), the prior stored report's reviewer_independent
    # marker (whether the version being re-moderated was previously
    # mock-moderated), and a bare boolean for whether the repair pass rewrote
    # the book's text, never finding messages or story prose. "repaired" is a
    # bool by construction, so it cannot carry prose even by accident, and it
    # is the one thing in this payload that says the stored text CHANGED,
    # which an audit reader otherwise could not tell from a verdict alone.
    # "coverage_complete" is a bare bool too, and it is what separates a verdict
    # that judged the prose from one that fails closed because nobody did. An
    # audit reader cannot recover that from "overall_verdict": "block" alone,
    # and the two states call for opposite remedies.
    EventType.STORYBOOK_REMODERATED: frozenset(
        {
            "overall_verdict",
            "counts",
            "prior_reviewer_independent",
            "repaired",
            "coverage_complete",
        }
    ),
    # S9 digest job: a bare count of pending info-severity notifications this
    # family had waiting; never which notifications, never any child- or
    # story-identifying detail (D3).
    EventType.NOTIFICATION_DIGEST_READY: frozenset({"digest_count"}),
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
