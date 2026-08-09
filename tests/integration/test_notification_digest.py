"""Integration tests for the S9 server-scheduled notification digest job.

Real Postgres, real cross-family data (mirrors test_deletion_drill.py's
convention): proves the digest job counts a real family's pending
info-severity notifications, writes exactly one summary event, and does not
re-count or re-fire once its own cursor has moved past what it already
reported.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import PipelineEvent
from cyo_adventure.events.models import Actor, EventType
from cyo_adventure.events.writer import record_event
from cyo_adventure.notifications.digest import run_notification_digest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tests.integration.conftest import Seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


async def _digest_events(
    sessions: async_sessionmaker[AsyncSession], family_id: object
) -> list[PipelineEvent]:
    async with sessions() as s:
        rows = await s.scalars(
            select(PipelineEvent).where(
                PipelineEvent.entity_type == "family",
                PipelineEvent.entity_id == str(family_id),
                PipelineEvent.event_type == EventType.NOTIFICATION_DIGEST_READY,
            )
        )
        return list(rows.all())


async def test_family_with_a_pending_release_gets_one_digest_event(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A published-story RELEASED event (info-severity) yields one digest."""
    async with sessions() as s:
        await record_event(
            s,
            Actor.system(),
            entity_type="storybook",
            entity_id=seed.storybook_id,
            event_type=EventType.RELEASED,
            payload={"visibility": "family"},
        )
        await s.commit()

    async with sessions() as s:
        written = await run_notification_digest(s, now=_NOW)
        await s.commit()
    assert written >= 1

    events = await _digest_events(sessions, seed.family_id)
    assert len(events) == 1
    assert events[0].payload == {"digest_count": 1}


async def test_second_run_does_not_re_digest_the_same_window(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """Running the job again with no new events writes no second digest.

    The family's own cursor (its prior digest event's timestamp) advances
    past the RELEASED event, so a re-run has nothing new to report.
    """
    async with sessions() as s:
        await record_event(
            s,
            Actor.system(),
            entity_type="storybook",
            entity_id=seed.storybook_id,
            event_type=EventType.RELEASED,
            payload={"visibility": "family"},
        )
        await s.commit()

    async with sessions() as s:
        await run_notification_digest(s, now=_NOW)
        await s.commit()
    async with sessions() as s:
        await run_notification_digest(s, now=_NOW + timedelta(minutes=5))
        await s.commit()

    events = await _digest_events(sessions, seed.family_id)
    assert len(events) == 1


async def test_a_family_with_nothing_pending_gets_no_digest_event(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """No qualifying event at all means no digest event is written."""
    async with sessions() as s:
        written = await run_notification_digest(s, now=_NOW)
        await s.commit()
    assert written == 0

    events = await _digest_events(sessions, seed.family_id)
    assert events == []


async def test_a_later_release_after_the_first_digest_is_counted_fresh(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A second RELEASED event after the first digest's cursor gets its own digest."""
    async with sessions() as s:
        await record_event(
            s,
            Actor.system(),
            entity_type="storybook",
            entity_id=seed.storybook_id,
            event_type=EventType.RELEASED,
            payload={"visibility": "family"},
        )
        await s.commit()
    async with sessions() as s:
        await run_notification_digest(s, now=_NOW)
        await s.commit()

    async with sessions() as s:
        await record_event(
            s,
            Actor.system(),
            entity_type="storybook",
            entity_id=seed.storybook_id,
            event_type=EventType.RELEASED,
            payload={"visibility": "family"},
        )
        await s.commit()
    async with sessions() as s:
        await run_notification_digest(s, now=_NOW + timedelta(hours=1))
        await s.commit()

    events = await _digest_events(sessions, seed.family_id)
    assert len(events) == 2
    assert all(e.payload == {"digest_count": 1} for e in events)
