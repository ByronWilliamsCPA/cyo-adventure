"""Value types for the pipeline event log (WS-D capture layer)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid


class EventType(StrEnum):
    """Every enumerated story-lifecycle transition (spec section 'Event taxonomy')."""

    REQUEST_CREATED = "request_created"
    REQUEST_APPROVED = "request_approved"
    REQUEST_DECLINED = "request_declined"
    PLAN_ASSIGNED = "plan_assigned"
    GENERATION_STARTED = "generation_started"
    GENERATION_FINISHED = "generation_finished"
    MODERATION_COMPLETED = "moderation_completed"
    REPAIR_APPLIED = "repair_applied"
    SENT_BACK = "sent_back"
    RELEASED = "released"
    THRESHOLD_CHANGED = "threshold_changed"
    NOISE_FLOOR_CHANGED = "noise_floor_changed"
    BOOK_ASSIGNED = "book_assigned"
    RATED = "rated"


SYSTEM_ACTOR_ROLE = "system"


@dataclass(frozen=True)
class Actor:
    """Who caused a transition. System transitions carry no user id."""

    actor_id: uuid.UUID | None
    actor_role: str

    @classmethod
    def from_principal(cls, principal: object) -> Actor:
        """Build an Actor from an api.deps.Principal (duck-typed to avoid an import cycle).

        # #ASSUME: data-integrity: principal exposes user_id (uuid) and role (StrEnum)
        # #VERIFY: covered by the per-transition integration tests that pass a real Principal
        """
        return cls(
            actor_id=principal.user_id,  # type: ignore[attr-defined]
            actor_role=str(principal.role),  # type: ignore[attr-defined]
        )

    @classmethod
    def system(cls) -> Actor:
        """The actor for worker/moderation transitions with no request principal."""
        return cls(actor_id=None, actor_role=SYSTEM_ACTOR_ROLE)
