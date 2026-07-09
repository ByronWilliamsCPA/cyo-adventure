"""Shared assertions for pipeline_event instrumentation tests.

Underscore-prefixed module name so pytest does not collect it as a test module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa

from cyo_adventure.db.models import PipelineEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def fetch_events(
    sessions: async_sessionmaker[AsyncSession], event_type: str
) -> list[PipelineEvent]:
    """Return all pipeline_event rows of a given event_type, oldest first."""
    async with sessions() as session:
        rows = await session.execute(
            sa.select(PipelineEvent)
            .where(PipelineEvent.event_type == event_type)
            .order_by(PipelineEvent.occurred_at)
        )
        return list(rows.scalars())


async def assert_single_event(
    sessions: async_sessionmaker[AsyncSession],
    *,
    event_type: str,
    entity_type: str,
    to_state: str | None = None,
    actor_role: str | None = None,
    actor_is_system: bool | None = None,
) -> PipelineEvent:
    """Assert exactly one event of event_type exists and matches the given fields."""
    events = await fetch_events(sessions, event_type)
    assert len(events) == 1, f"expected 1 {event_type}, found {len(events)}"
    event = events[0]
    assert event.entity_type == entity_type
    if to_state is not None:
        assert event.to_state == to_state
    if actor_role is not None:
        assert event.actor_role == actor_role
    if actor_is_system is not None:
        assert (event.actor_id is None) == actor_is_system
    return event
