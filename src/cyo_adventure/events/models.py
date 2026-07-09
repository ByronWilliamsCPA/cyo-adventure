"""Value types for the pipeline event log (WS-D capture layer)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid


class _PrincipalLike(Protocol):
    """Structural type for the caller Actor.from_principal reads from.

    Mirrors the two attributes ``api.deps.Principal`` exposes (``user_id``,
    ``role``) without importing that module: this module sits low in the
    dependency graph and importing ``api.deps`` here would pull in far more
    than these two fields need (and risks a cycle back through this
    package). A Protocol gives BasedPyright the exact attribute types it
    needs to resolve ``principal.user_id``/``principal.role`` without a
    ``# type: ignore``, while any duck-typed caller (real ``Principal`` or a
    test double) still satisfies it structurally.
    """

    # Read-only properties, not plain attributes: Protocol data members are
    # checked invariantly (the exact declared type, not a subtype), which
    # would reject api.deps.Principal's ``role: Role`` (Role is a StrEnum
    # subtype of str, not str itself). A read-only property is checked
    # covariantly, so any object whose role is assignable TO str (Role
    # included) still satisfies this Protocol.
    @property
    def user_id(self) -> uuid.UUID: ...

    @property
    def role(self) -> str: ...


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
    def from_principal(cls, principal: _PrincipalLike) -> Actor:
        """Build an Actor from an api.deps.Principal (duck-typed to avoid an import cycle).

        # #ASSUME: data-integrity: principal exposes user_id (uuid) and role (StrEnum)
        # #VERIFY: covered by the per-transition integration tests that pass a real Principal
        """
        return cls(
            actor_id=principal.user_id,
            actor_role=str(principal.role),
        )

    @classmethod
    def system(cls) -> Actor:
        """The actor for worker/moderation transitions with no request principal."""
        return cls(actor_id=None, actor_role=SYSTEM_ACTOR_ROLE)
