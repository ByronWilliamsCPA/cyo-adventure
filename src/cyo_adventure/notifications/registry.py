"""Kind registry: pure, DB-free composition of pipeline_event rows (G10).

Each composer takes the raw ``PipelineEvent`` row and the ``EntityContext``
already resolved for it (``notifications/service.py``) and returns a
``RawNotification``, or ``None`` to drop the event (a guardian-irrelevant
instance of an otherwise-relevant event type, e.g. a guardian-initiated
``request_created``). Composers never touch the database and never re-check
family ownership -- every fact they need is either on the event row itself
(``payload``, ``from_state``/``to_state``) or pre-resolved and already
family-scoped by the caller, so this module is unit-testable with plain
constructed fixtures (no session, no ASGI).

Extending the registry: add one ``EventType -> composer`` entry to
``_COMPOSERS``. ``EventType.KID_FLAGGED`` (a sibling workstream landing
concurrently) is looked up via ``getattr`` so this module never hard-fails if
that enum member does not exist yet in
``cyo_adventure.events.models.EventType``; once it lands, the composer below
activates with no further change here. Its ``EntityContext`` is resolved by
whichever resolver in ``notifications/service.py`` matches the entity_type
the sibling actually writes the event against (see that module's docstring).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from cyo_adventure.events.models import EventType
from cyo_adventure.notifications.models import EntityContext, RawNotification

if TYPE_CHECKING:
    from cyo_adventure.db.models import PipelineEvent

Composer = Callable[["PipelineEvent", EntityContext], "RawNotification | None"]

_BLOCKED_STATE = "blocked"
_CHILD_INITIATOR = "child"
_FAILED_OUTCOME = "failed"
# GenerationJob outcomes that count as "finished, now awaiting human review":
# passed and needs_review both reach the moderation/approval gate; failed is
# handled separately (an alert, not an info notice); awaiting_manual_fill and
# any future status are deliberately NOT notified here (no guardian action is
# possible on them yet in this slice).
_REVIEWABLE_OUTCOMES = frozenset({"passed", "needs_review"})


def _child_label(ctx: EntityContext) -> str:
    """Return a display label for the child a notification concerns."""
    return ctx.profile_name or "Your child"


def _story_label(ctx: EntityContext) -> str:
    """Return a display label for the story a notification concerns."""
    return ctx.storybook_title or "A story"


def _compose_request_created(
    event: PipelineEvent, ctx: EntityContext
) -> RawNotification | None:
    """Map REQUEST_CREATED: a child-initiated pending request awaits consent.

    A guardian- or admin-initiated request needs no consent notice (the
    submitter already knows they made it); a screening-blocked request is
    surfaced as an alert regardless of who initiated it, since the guardian
    has no other visibility into it (the raw request text is never stored on
    a blocked row or in this event's PII-free payload, by the D3 contract in
    events/writer.py::_PAYLOAD_ALLOWLIST).

    #ASSUME: data-integrity: ``event.payload["initiator_role"]`` is one of
    "child", "guardian", "admin" (story_request.initiator_role's own closed
    vocabulary, mirrored into the event by api/story_requests.py and
    story_requests/service.py); any other value is treated the same as a
    non-child initiator (no consent notice), which is the safe default.
    #VERIFY: tests/unit/test_notifications_registry.py::
    TestComposeRequestCreated covers child/guardian/blocked.
    """
    payload = event.payload or {}
    if event.to_state == _BLOCKED_STATE:
        return RawNotification(
            kind="request_blocked",
            title=f"{_child_label(ctx)}'s story idea was blocked",
            body="Safety screening blocked this idea before it reached you.",
            severity="alert",
        )
    if payload.get("initiator_role") != _CHILD_INITIATOR:
        return None
    return RawNotification(
        kind="awaiting_consent",
        title=f"{_child_label(ctx)}'s story request is waiting for you",
        body="Review the idea and approve or decline it to keep it moving.",
        severity="info",
    )


def _compose_request_approved(
    _event: PipelineEvent, ctx: EntityContext
) -> RawNotification | None:
    """Map REQUEST_APPROVED: informational, the request is now generating."""
    return RawNotification(
        kind="request_approved",
        title=f"{_child_label(ctx)}'s story request was approved",
        body="It has moved into story generation.",
        severity="info",
    )


def _compose_request_declined(
    _event: PipelineEvent, ctx: EntityContext
) -> RawNotification | None:
    """Map REQUEST_DECLINED: informational, the request will not proceed."""
    return RawNotification(
        kind="request_declined",
        title=f"{_child_label(ctx)}'s story request was declined",
        body="It will not be generated.",
        severity="info",
    )


def _compose_generation_finished(
    event: PipelineEvent, ctx: EntityContext
) -> RawNotification | None:
    """Map GENERATION_FINISHED: alert on failure, info once it reaches review."""
    payload = event.payload or {}
    outcome = payload.get("outcome")
    if outcome == _FAILED_OUTCOME:
        return RawNotification(
            kind="generation_failed",
            title=f"{_story_label(ctx)} could not be generated",
            body="Something went wrong while writing this story.",
            severity="alert",
        )
    if outcome in _REVIEWABLE_OUTCOMES:
        return RawNotification(
            kind="generation_finished",
            title=f"{_story_label(ctx)} finished generating",
            body="It is now awaiting review before it can be published.",
            severity="info",
        )
    return None


def _compose_released(
    _event: PipelineEvent, ctx: EntityContext
) -> RawNotification | None:
    """Map RELEASED: a story was published to the family library."""
    return RawNotification(
        kind="story_ready",
        title=f"{_story_label(ctx)} is ready on the shelf",
        body="It has been approved and published to your family library.",
        severity="info",
    )


def _compose_book_assigned(
    _event: PipelineEvent, ctx: EntityContext
) -> RawNotification | None:
    """Map BOOK_ASSIGNED: a story was assigned to a specific child's shelf."""
    return RawNotification(
        kind="story_ready",
        title=f"{_story_label(ctx)} is ready on {_child_label(ctx)}'s shelf",
        body="It has been assigned and is ready to read.",
        severity="info",
    )


# Human-readable clauses for each closed-vocabulary KidFlag.reason value
# (db/models.py::_KID_FLAG_REASON_VALUES). A reason outside this map (a
# future addition to that vocabulary this registry has not been updated for
# yet) falls back to the generic clause below rather than raising.
_KID_FLAG_REASON_CLAUSES = {
    "scared_me": "said this story scared them",
    "confusing": "found this story confusing",
    "did_not_like": "didn't like this story",
}


def _compose_kid_flagged(
    event: PipelineEvent, ctx: EntityContext
) -> RawNotification | None:
    """Map KID_FLAGGED (tolerant, see module docstring): content was flagged.

    The event payload carries only the closed-vocabulary ``reason`` and
    ``storybook_id`` (events/writer.py's KID_FLAGGED payload allowlist; no
    child-authored free text ever reaches this event, per ADR-016).

    #CRITICAL: security: this composer only ever runs on an event whose
    EntityContext has already been resolved to the caller's own family by
    notifications/service.py (any event that does not resolve there, or
    resolves to a different family, is dropped before compose() is called);
    it never independently widens what a guardian can see.
    #VERIFY: tests/unit/test_notifications_registry.py::
    TestComposeKidFlagged exercises this composer directly (by calling it,
    not by round-tripping through the registry dict) so the mapping stayed
    pinned even before the sibling event type landed.
    """
    payload = event.payload or {}
    reason = payload.get("reason")
    clause = _KID_FLAG_REASON_CLAUSES.get(
        reason if isinstance(reason, str) else "", "flagged this story"
    )
    return RawNotification(
        kind="kid_flagged",
        title=f"{_child_label(ctx)} flagged a story",
        body=f"{_child_label(ctx)} {clause} in {_story_label(ctx)}; it needs your review.",
        severity="alert",
    )


_COMPOSERS: dict[EventType, Composer] = {
    EventType.REQUEST_CREATED: _compose_request_created,
    EventType.REQUEST_APPROVED: _compose_request_approved,
    EventType.REQUEST_DECLINED: _compose_request_declined,
    EventType.GENERATION_FINISHED: _compose_generation_finished,
    EventType.RELEASED: _compose_released,
    EventType.BOOK_ASSIGNED: _compose_book_assigned,
}

# #ASSUME: data-integrity: a sibling workstream is adding EventType.KID_FLAGGED
# concurrently with this slice. getattr with a None default means an absent
# member is simply never registered here (no AttributeError at import time,
# no crash for any caller of this module); once the sibling's change lands,
# the next import of this module picks the member up with no code change.
# #VERIFY: tests/unit/test_notifications_registry.py::
# test_registry_import_never_fails_when_kid_flagged_is_absent and
# test_kid_flagged_registers_automatically_once_the_enum_member_exists.
_KID_FLAGGED = getattr(EventType, "KID_FLAGGED", None)
if _KID_FLAGGED is not None:
    _COMPOSERS[_KID_FLAGGED] = _compose_kid_flagged


def relevant_event_type_values() -> list[str]:
    """Return the wire-format values of every EventType this registry maps.

    Used by ``service.py`` to build the ``pipeline_event.event_type IN (...)``
    candidate filter without duplicating the registry's key set.

    Returns:
        list[str]: The ``.value`` of each registered ``EventType``.
    """
    return [event_type.value for event_type in _COMPOSERS]


def compose(event: PipelineEvent, ctx: EntityContext) -> RawNotification | None:
    """Return the composed notification for one event, or None to drop it.

    Args:
        event: The pipeline_event row. A row whose ``event_type`` is not
            registered returns None here rather than raising, even though
            ``service.py``'s candidate query already restricts itself to
            ``relevant_event_type_values()``; a defensive caller should not
            have to know that invariant holds.
        ctx: The resolved, already family-scoped entity context.

    Returns:
        RawNotification | None: The composed item, or None if this event's
        type is unmapped or its composer decided it is not guardian-relevant.
    """
    try:
        kind = EventType(event.event_type)
    except ValueError:
        return None
    composer = _COMPOSERS.get(kind)
    if composer is None:
        return None
    return composer(event, ctx)
