"""Guardian notification feed (S9 delivery infrastructure, G10 first slice).

This package never writes anything: it is a read-only projection over the
append-only ``pipeline_event`` log (``db/models.py::PipelineEvent``,
``events/writer.py``). There is no notification table, no push channel, and
no server-side unread state for this first slice; a caller tracks the newest
``occurred_at`` it has already shown and passes it back as ``since`` on the
next poll (``api/notifications.py``).

Module layout:

* ``models``: DB-free value types (``EntityContext``, ``RawNotification``,
  ``NotificationItem``).
* ``registry``: pure, DB-free composition of a ``PipelineEvent`` row plus its
  resolved ``EntityContext`` into a guardian-facing ``RawNotification``. The
  single ``EventType -> composer`` registry dict here is the extension point
  for a new guardian-relevant event type.
* ``service``: the DB-touching half. Resolves each candidate event's owning
  entity (and thereby its family) and enforces family scoping before any
  composer runs.
"""

from __future__ import annotations

from cyo_adventure.notifications.models import (
    EntityContext,
    NotificationItem,
    RawNotification,
    Severity,
)
from cyo_adventure.notifications.service import list_guardian_notifications

__all__ = [
    "EntityContext",
    "NotificationItem",
    "RawNotification",
    "Severity",
    "list_guardian_notifications",
]
