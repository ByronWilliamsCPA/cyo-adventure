"""Value types for the pipeline event log (WS-D capture layer)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from cyo_adventure.core.exceptions import ValidationError

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
    # A5 incident/pull-everywhere path: an admin archives a published story
    # (publishing/service.py::archive, the sole published->archived hop per
    # state_machine.py), removing it from every child's shelf. Drives the G10
    # guardian-notification composer (notifications/registry.py) and, on the
    # client side, the next reconcileOfflineCache() call that evicts the book
    # from any device that already downloaded it
    # (frontend/src/offline/revocation.ts).
    STORYBOOK_ARCHIVED = "storybook_archived"
    THRESHOLD_CHANGED = "threshold_changed"
    NOISE_FLOOR_CHANGED = "noise_floor_changed"
    BOOK_ASSIGNED = "book_assigned"
    # G8 per-child kill switch: a guardian revokes one child's access to a book
    # (api/assignments.py::unassign_storybook). Emitted once per assignment row
    # actually removed; a no-op unassign (already unassigned) writes nothing.
    BOOK_UNASSIGNED = "book_unassigned"
    RATED = "rated"
    KID_FLAGGED = "kid_flagged"
    FLAG_RESOLVED = "flag_resolved"
    # WS-J admin user management: each covers several mutations via a
    # payload "action" field (mirrors THRESHOLD_CHANGED covering both upsert
    # and delete), rather than one event type per CRUD verb per entity.
    USER_MANAGED = "user_managed"
    FAMILY_MANAGED = "family_managed"
    FAMILY_CONNECTION_CHANGED = "family_connection_changed"
    # G6: a prose-only passage edit (node body and/or choice label text) that
    # forced a re-run of the deterministic gate and the node's moderation
    # findings. The payload carries only the node id (never the edited prose)
    # per spec D3; see api/node_edit.py.
    NODE_EDITED = "node_edited"
    # Phase 8a (GDPR Article 30 accountability): the only READ this
    # taxonomy audits, deliberately. Every other member above logs a
    # mutation; this one logs an admin's cross-family read of child-linked
    # data (api/admin_profiles.py::list_admin_profiles), since that read
    # crosses a tenant boundary no other GET in this API does (every other
    # admin GET is either same-family or non-child data). One event per
    # call, not one per row returned; see events/writer.py's payload
    # allowlist for this type.
    PROFILE_VIEWED = "profile_viewed"
    # WS-8 catalog flywheel (docs/planning/ws8-catalog-flywheel-design.md section
    # 4.1): a request-time cell-saturation signal, persisted so the flywheel's
    # trigger can compute per-cell demand without ever recording theme text. The
    # payload carries ONLY closed-vocabulary enum values (age band, length,
    # style, differentiation level); see events/writer.py's allowlist.
    CELL_SATURATED = "cell_saturated"
    # ADR-023 P3/P4 (story personalization): a guardian flips one
    # personalization slot on or off, or edits its value, for a child profile
    # (emitted by api/personalization.py::put_personalization). The type was
    # added ahead of its writer, so an earlier revision of this comment said
    # "not yet wired"; the writer landed in the same change that introduced
    # the endpoint. The payload carries only the closed-vocabulary slot_type, the
    # ring (1 or 2) it was scoped to, and the action taken; never the actual
    # value (a child's name, a pet's name, etc.), per spec D3. See
    # events/writer.py's allowlist for this type.
    PERSONALIZATION_TOGGLED = "personalization_toggled"
    # ADR-023 P4: a guardian in a connected family grants ring-2 sharing
    # (the narrower "shared with connected families" slot subset) for a
    # child profile to a specific connected family. The payload carries the
    # connected family's id and a count of slot types shared, never the
    # slot values themselves or any child-identifying detail.
    RING2_CONSENT_GRANTED = "ring2_consent_granted"
    # ADR-023 P4: the ring-2 consent counterpart to RING2_CONSENT_GRANTED; a
    # guardian revokes previously granted ring-2 sharing with one connected
    # family. The payload carries only the connected family's id.
    RING2_CONSENT_REVOKED = "ring2_consent_revoked"


SYSTEM_ACTOR_ROLE = "system"

# The acting-role stamp for admin-gated transitions. Passed to
# Actor.from_principal by call sites whose authorization gate is the admin
# capability, so a dual-role adult (guardian base role + is_admin) is audited
# in the capacity that authorized the action.
ADMIN_ACTOR_ROLE = "admin"


@dataclass(frozen=True)
class Actor:
    """Who caused a transition. System transitions carry no user id."""

    actor_id: uuid.UUID | None
    actor_role: str

    def __post_init__(self) -> None:
        """Enforce spec D2: system actors carry no user id; user actors always do.

        # #CRITICAL: data-integrity: a mismatched actor_id/actor_role pair would
        # write a contradictory row into the append-only audit log. This makes the
        # illegal pairing unconstructible in the type layer; the DB CHECK
        # ``ck_pipeline_event_system_actor_null`` is the backstop for non-ORM writers.
        # #VERIFY: raises ValidationError on any mismatch; covered by
        # tests/unit/test_pipeline_event_writer.py.
        """
        is_system = self.actor_role == SYSTEM_ACTOR_ROLE
        if is_system != (self.actor_id is None):
            msg = (
                "system actor requires actor_id=None; "
                "user actor requires a non-null actor_id"
            )
            raise ValidationError(msg, field="actor_id", value=self.actor_id)

    @classmethod
    def from_principal(
        cls, principal: _PrincipalLike, *, acting_role: str | None = None
    ) -> Actor:
        """Build an Actor from an api.deps.Principal (duck-typed to avoid an import cycle).

        ``acting_role`` overrides the principal's base role for the stamp:
        admin-gated call sites pass ``"admin"`` so a dual-role adult
        (guardian base role + admin capability) is audited in the capacity
        that authorized the action, not the persona they logged in with.

        # #ASSUME: data-integrity: principal exposes user_id (uuid) and role (StrEnum)
        # #VERIFY: covered by the per-transition integration tests that pass a real Principal
        """
        return cls(
            actor_id=principal.user_id,
            actor_role=acting_role if acting_role is not None else str(principal.role),
        )

    @classmethod
    def system(cls) -> Actor:
        """The actor for worker/moderation transitions with no request principal."""
        return cls(actor_id=None, actor_role=SYSTEM_ACTOR_ROLE)
