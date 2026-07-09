"""Pipeline event log (WS-D): append-only capture of lifecycle transitions."""

from __future__ import annotations

from cyo_adventure.events.models import SYSTEM_ACTOR_ROLE, Actor, EventType
from cyo_adventure.events.writer import record_event

__all__ = ["SYSTEM_ACTOR_ROLE", "Actor", "EventType", "record_event"]
