"""Value types for the guardian notification projection (S9 delivery layer, G10).

Every type here is a plain, DB-free dataclass. None of them touch a session or
an ORM row's live state; ``notifications/service.py`` builds them from data it
has already read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

# 'alert' is reserved for safety-relevant kinds (a blocked or flagged story,
# a failed generation the guardian must act on); everything else is 'info'.
Severity = Literal["alert", "info"]


@dataclass(frozen=True, slots=True)
class EntityContext:
    """Family-scoped facts about the entity a ``pipeline_event`` row names.

    Resolved once per ``(entity_type, entity_id)`` pair by an entity resolver
    in ``notifications/service.py`` before any kind composer in
    ``notifications/registry.py`` runs. ``family_id`` is the only field every
    composer can rely on being present; it is also the sole security-relevant
    field, since ``service.py`` compares it against the caller's
    ``Principal.family_id`` before a composer ever sees the event (a
    composer never re-checks it and must not be trusted to).

    Attributes:
        family_id: The family that owns the underlying entity. Never
            optional: an entity resolver that cannot determine this must
            omit the entity from its result map entirely rather than guess.
        storybook_id: The story the entity concerns, or None.
        storybook_title: The story's current published title, or None if
            unpublished, malformed, or not applicable to this entity type.
        profile_id: The child profile the entity concerns, or None.
        profile_name: The child's display name, or None.
        request_id: The story_request id, or None.
    """

    family_id: uuid.UUID
    storybook_id: str | None = None
    storybook_title: str | None = None
    profile_id: uuid.UUID | None = None
    profile_name: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class RawNotification:
    """A composed notification, before the event's id/timestamp are attached."""

    kind: str
    title: str
    body: str
    severity: Severity


@dataclass(frozen=True, slots=True)
class NotificationItem:
    """One wire-ready notification: a composed row plus its event identity."""

    id: str
    occurred_at: datetime
    kind: str
    severity: Severity
    title: str
    body: str
    storybook_id: str | None
    request_id: str | None
    profile_id: str | None
