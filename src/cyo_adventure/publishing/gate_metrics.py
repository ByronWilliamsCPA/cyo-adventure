"""Human-gate duration and send-back metrics (R-11).

The approval gate is the least instrumented stage in the pipeline. Generation
and moderation both stamp their own timings, but the question "how long does a
person take, and how often do they send a story back" had no answer: the log
recorded how a review round ENDED (``released``/``sent_back``) and never when
one BEGAN. ``EventType.SUBMITTED`` (added 2026-08-23) closes that, and this
module is its read side.

Pure computation lives in module-level functions so it unit tests without a
database; ``load_gate_events`` is the only DB read. This module never writes,
mirroring ``moderation/insights.py``.

Two pairing rules carry the whole measurement's credibility:

- An **open** round (entered, not yet decided) has no duration and no outcome.
  Substituting "now" for its decision time would bias the average downward by
  exactly the reviews that are running long.
- A decision with **no preceding entry** is dropped. Every ``released`` and
  ``sent_back`` row written before the ``submitted`` migration is such a row;
  pairing one with a later entry invents a negative duration, and pairing it
  with an earlier one invents a duration spanning the migration.

Same-transaction transitions (a measurement limit, not a bug):
``pipeline_event.occurred_at`` defaults to Postgres ``now()``, which is
TRANSACTION start time, not statement time. Two gate transitions committed in
one transaction therefore carry an IDENTICAL timestamp, and their order is
unrecoverable: the primary key is a random UUID, so there is no monotonic
tiebreaker to fall back on. Production never hits this (each transition is its
own HTTP request, hence its own transaction), and the recorded duration is
measured to the deciding transaction's start, which skews sub-second. A test or
script that drives several transitions through one session must commit between
them or its rounds will not pair.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from cyo_adventure.db.models import PipelineEvent
from cyo_adventure.events import EventType

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

# The three gate events, all keyed on entity_type "storybook" with the
# storybook id as entity_id (publishing/service.py::submit, ::approve,
# ::send_back), so pairing needs no cross-entity join.
_ENTITY_TYPE = "storybook"


class GateOutcome(StrEnum):
    """How a review round ended."""

    RELEASED = "released"
    SENT_BACK = "sent_back"


_TERMINAL: dict[str, GateOutcome] = {
    EventType.RELEASED.value: GateOutcome.RELEASED,
    EventType.SENT_BACK.value: GateOutcome.SENT_BACK,
}


@dataclass(frozen=True)
class GateRound:
    """One pass of one storybook through the human gate.

    Attributes:
        storybook_id: The story under review.
        round_index: 1-based position in this story's sequence of rounds.
        entered_at: When the story entered the queue (the ``submitted`` event).
        decided_at: When a person decided, or ``None`` while still in review.
        outcome: The decision, or ``None`` while still in review.
    """

    storybook_id: str
    round_index: int
    entered_at: datetime
    decided_at: datetime | None
    outcome: GateOutcome | None

    @property
    def duration_seconds(self) -> float | None:
        """Return wall-clock seconds spent at the gate, or ``None`` if open.

        Returns:
            Seconds between entry and decision; ``None`` for an open round.
        """
        if self.decided_at is None:
            return None
        return (self.decided_at - self.entered_at).total_seconds()


@dataclass(frozen=True)
class GateSummary:
    """Aggregate gate behaviour across a set of rounds.

    Attributes:
        total_rounds: Every round, open or decided.
        decided_rounds: Rounds a person actually closed.
        open_rounds: Rounds still sitting in the queue.
        send_back_rate: Send-backs over DECIDED rounds, or ``None`` if none
            are decided. Never 0.0 for "no data": a rate of zero is a claim
            about reviewer behaviour, absence of data is not.
        median_duration_seconds: Median over decided rounds, or ``None``.
        released_storybooks: Stories that reached ``released`` at least once.
        mean_rounds_to_release: Mean rounds a released story needed, counting
            the releasing round. ``None`` when nothing has been released.
    """

    total_rounds: int
    decided_rounds: int
    open_rounds: int
    send_back_rate: float | None
    median_duration_seconds: float | None
    released_storybooks: int
    mean_rounds_to_release: float | None


def build_rounds(
    events: Iterable[tuple[str, str, datetime]],
) -> list[GateRound]:
    """Pair gate events into review rounds, per storybook.

    Args:
        events: ``(storybook_id, event_type, occurred_at)`` tuples in any
            order. Event types outside the three gate events are ignored.

    Returns:
        Rounds sorted by storybook id then round index.
    """
    # Sorting by timestamp is what makes pairing meaningful; the loader's row
    # order is not guaranteed, and callers may hand us a merged sequence.
    # #EDGE: data-integrity: two gate events sharing an occurred_at sort in
    # input order, which is arbitrary for DB-loaded rows. Ties are real, not
    # theoretical: occurred_at defaults to Postgres now() (transaction start),
    # so every event committed in one transaction shares a timestamp. Such a
    # pair is genuinely unorderable, the primary key being a random UUID rather
    # than a sequence, so this sort does not try to resolve it; the rounds
    # simply fail to pair and surface as open. Production is unaffected: one
    # transition per request means one transition per transaction.
    # #VERIFY: tests/integration/test_publishing_gate_metrics.py commits
    # between transitions for exactly this reason and pairs both rounds; the
    # same test written as a single transaction produced two open rounds.
    ordered = sorted(events, key=lambda event: event[2])

    rounds: list[GateRound] = []
    open_round: dict[str, tuple[int, datetime]] = {}
    next_index: dict[str, int] = {}

    for storybook_id, event_type, occurred_at in ordered:
        if event_type == EventType.SUBMITTED.value:
            # #EDGE: data-integrity: a second submit while a round is already
            # open should be impossible (state_machine.py refuses in_review ->
            # in_review). If one appears, both rounds are kept, so the anomaly
            # surfaces as an inflated open_rounds rather than being swallowed.
            # #VERIFY: no test asserts this shape because no code path can
            # produce it; the branch exists so a future one is visible.
            index = next_index.get(storybook_id, 1)
            next_index[storybook_id] = index + 1
            _close(rounds, storybook_id, open_round.pop(storybook_id, None))
            open_round[storybook_id] = (index, occurred_at)
            continue

        outcome = _TERMINAL.get(event_type)
        if outcome is None:
            continue
        entry = open_round.pop(storybook_id, None)
        if entry is None:
            # A decision with no entry: a pre-migration row. Dropped rather
            # than paired, see this module's docstring.
            continue
        index, entered_at = entry
        rounds.append(
            GateRound(
                storybook_id=storybook_id,
                round_index=index,
                entered_at=entered_at,
                decided_at=occurred_at,
                outcome=outcome,
            )
        )

    for storybook_id, entry in open_round.items():
        _close(rounds, storybook_id, entry)

    return sorted(rounds, key=lambda r: (r.storybook_id, r.round_index))


def _close(
    rounds: list[GateRound],
    storybook_id: str,
    entry: tuple[int, datetime] | None,
) -> None:
    """Append an undecided round for an entry that never got a decision.

    Args:
        rounds: Accumulator to append to.
        storybook_id: The story the round belongs to.
        entry: ``(round_index, entered_at)``, or ``None`` for no open round.
    """
    if entry is None:
        return
    index, entered_at = entry
    rounds.append(
        GateRound(
            storybook_id=storybook_id,
            round_index=index,
            entered_at=entered_at,
            decided_at=None,
            outcome=None,
        )
    )


def summarize_rounds(rounds: Sequence[GateRound]) -> GateSummary:
    """Aggregate rounds into the R-11 headline figures.

    Args:
        rounds: Rounds from :func:`build_rounds`.

    Returns:
        The summary. Every ratio is ``None`` rather than 0.0 when its
        denominator is empty.
    """
    decided = [r for r in rounds if r.outcome is not None]
    durations = [r.duration_seconds for r in decided if r.duration_seconds is not None]
    sent_back = sum(1 for r in decided if r.outcome is GateOutcome.SENT_BACK)

    release_round: dict[str, int] = {}
    for round_ in decided:
        if round_.outcome is GateOutcome.RELEASED:
            existing = release_round.get(round_.storybook_id)
            if existing is None or round_.round_index < existing:
                release_round[round_.storybook_id] = round_.round_index

    return GateSummary(
        total_rounds=len(rounds),
        decided_rounds=len(decided),
        open_rounds=len(rounds) - len(decided),
        send_back_rate=(sent_back / len(decided)) if decided else None,
        median_duration_seconds=statistics.median(durations) if durations else None,
        released_storybooks=len(release_round),
        mean_rounds_to_release=(
            statistics.fmean(release_round.values()) if release_round else None
        ),
    )


async def load_gate_events(session: AsyncSession) -> list[tuple[str, str, datetime]]:
    """Read every gate event from the append-only log.

    Args:
        session: The request-scoped async session.

    Returns:
        ``(storybook_id, event_type, occurred_at)`` tuples, unordered.
    """
    # #ASSUME: external-resources: a whole-corpus read, mirroring
    # insights.py::load_version_records' no-window stance at v1 volumes.
    # Three event types over one entity type is a narrow slice of the log;
    # revisit with an occurred_at window if pipeline_event grows past a few
    # hundred thousand rows.
    # #VERIFY: tests/integration/test_publishing_gate_metrics.py exercises the
    # loader against a real session.
    rows = (
        await session.execute(
            select(
                PipelineEvent.entity_id,
                PipelineEvent.event_type,
                PipelineEvent.occurred_at,
            ).where(
                PipelineEvent.entity_type == _ENTITY_TYPE,
                PipelineEvent.event_type.in_(
                    [
                        EventType.SUBMITTED.value,
                        EventType.RELEASED.value,
                        EventType.SENT_BACK.value,
                    ]
                ),
            )
        )
    ).all()
    # cast rather than re-tupling element by element: SQLAlchemy types a Row's
    # members as Any, so unpacking them buys no safety and only adds noise.
    return [cast("tuple[str, str, datetime]", tuple(row)) for row in rows]
