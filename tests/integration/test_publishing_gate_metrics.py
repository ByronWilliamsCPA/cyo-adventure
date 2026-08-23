"""End-to-end check that gate metrics read what the gate actually writes (R-11).

``tests/unit/test_publishing_gate_metrics.py`` pins the pairing rules against
hand-built tuples. That leaves one thing a unit test cannot prove: whether
``load_gate_events``'s ``entity_type``/``event_type`` filter matches the
strings ``publishing/service.py`` really emits. A typo in either would return
an empty list and every metric would read as "no data" rather than failing, so
this drives a real story through a real send-back-and-resubmit cycle and
asserts the round structure comes back out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Family, Storybook, StorybookVersion, User
from cyo_adventure.events import Actor
from cyo_adventure.publishing import service as approval_service
from cyo_adventure.publishing.gate_metrics import (
    GateOutcome,
    build_rounds,
    load_gate_events,
    summarize_rounds,
)
from cyo_adventure.publishing.state_machine import Visibility
from tests.conftest import make_clean_moderation_report

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed(session: AsyncSession, story_id: str) -> tuple[Storybook, uuid.UUID]:
    """Seed a family, a dual-role reviewer, and a screened draft story."""
    fam = Family(name="Gate Metrics Family")
    session.add(fam)
    await session.flush()
    reviewer = User(
        family_id=fam.id, role="guardian", authn_subject=f"g-{story_id}", is_admin=True
    )
    session.add(reviewer)
    await session.flush()
    book = Storybook(id=story_id, family_id=fam.id, status="draft")
    session.add(book)
    await session.flush()
    session.add(
        StorybookVersion(
            storybook_id=story_id,
            version=1,
            blob={"id": story_id},
            moderation_report=make_clean_moderation_report(),
        )
    )
    await session.flush()
    return book, reviewer.id


async def _reload(session: AsyncSession, story_id: str) -> Storybook:
    """Re-fetch a story into a fresh session between transitions."""
    book = await session.get(Storybook, story_id)
    assert book is not None
    return book


def _principal(user_id: uuid.UUID, family_id: uuid.UUID) -> object:
    """Build the dual-role reviewer principal the service functions expect."""
    from cyo_adventure.api.deps import Principal

    return Principal(
        subject="g",
        user_id=user_id,
        role="guardian",
        family_id=family_id,
        profile_ids=frozenset(),
        is_admin=True,
    )


async def test_a_full_send_back_and_resubmit_cycle_reads_back_as_two_rounds(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Two real rounds through the gate come back as two paired rounds.

    The story is submitted, sent back, resubmitted and released, which is the
    shape the whole measurement exists for: round 2 has no start timestamp
    anywhere else in the system, because a resubmission re-runs no moderation.
    """
    story_id = "gate-metrics-1"
    # One transaction per transition, mirroring production, where each is its
    # own HTTP request. This is load-bearing, not cosmetic: pipeline_event's
    # occurred_at defaults to Postgres now(), which is TRANSACTION start time,
    # so four transitions committed together would share one timestamp and be
    # unorderable. See gate_metrics.py's "Same-transaction transitions" note.
    async with sessions() as session:
        book, reviewer_id = await _seed(session, story_id)
        reviewer, family = reviewer_id, book.family_id
        await approval_service.submit(session, book, actor=Actor.system())
        await session.commit()

    async with sessions() as session:
        book = await _reload(session, story_id)
        await approval_service.send_back(
            session,
            _principal(reviewer, family),
            book,
            "too scary",
            reason_code="safety_concern",
        )
        await session.commit()

    async with sessions() as session:
        book = await _reload(session, story_id)
        await approval_service.submit(
            session, book, actor=Actor(actor_id=reviewer, actor_role="guardian")
        )
        await session.commit()

    async with sessions() as session:
        book = await _reload(session, story_id)
        await approval_service.approve(
            session, _principal(reviewer, family), book, 1, visibility=Visibility.FAMILY
        )
        await session.commit()

    async with sessions() as session:
        rounds = build_rounds(await load_gate_events(session))

    mine = [r for r in rounds if r.storybook_id == story_id]
    assert [r.round_index for r in mine] == [1, 2]
    assert [r.outcome for r in mine] == [GateOutcome.SENT_BACK, GateOutcome.RELEASED]
    # Real clock, so only the sign and the ordering are assertable here; the
    # exact arithmetic is pinned in the unit tests.
    for round_ in mine:
        assert round_.duration_seconds is not None
        assert round_.duration_seconds >= 0

    summary = summarize_rounds(mine)
    assert summary.decided_rounds == 2
    assert summary.send_back_rate == 0.5
    assert summary.released_storybooks == 1
    assert summary.mean_rounds_to_release == 2.0


async def test_a_story_still_in_review_reads_back_as_an_open_round(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A submitted-but-undecided story is open, with no duration."""
    story_id = "gate-metrics-2"
    async with sessions() as session:
        book, _reviewer_id = await _seed(session, story_id)
        await approval_service.submit(session, book, actor=Actor.system())
        await session.commit()

    async with sessions() as session:
        rounds = build_rounds(await load_gate_events(session))

    mine = [r for r in rounds if r.storybook_id == story_id]
    assert len(mine) == 1
    assert mine[0].outcome is None
    assert mine[0].duration_seconds is None
    assert summarize_rounds(mine).send_back_rate is None
