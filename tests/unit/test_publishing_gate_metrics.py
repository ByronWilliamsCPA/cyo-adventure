"""Human-gate duration and send-back metrics (R-11).

The gate is the least measured stage in the pipeline: generation and
moderation both emit timings, but "how long did a person take, and how often
did they send it back" was never derivable. These tests pin the pairing rules
that turn the append-only ``pipeline_event`` log into review rounds, and in
particular the two ways a naive pairing would produce a confident wrong
number: an undecided round read as an instant decision, and a decision event
that predates the ``submitted`` event's existence pairing with an unrelated
later entry.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cyo_adventure.events import EventType
from cyo_adventure.publishing.gate_metrics import (
    GateOutcome,
    build_rounds,
    summarize_rounds,
)

_T0 = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def _ev(
    event_type: EventType, minutes: int, story: str = "s1"
) -> tuple[str, str, datetime]:
    """Build one (storybook_id, event_type value, occurred_at) log tuple."""
    return (story, event_type.value, _T0 + timedelta(minutes=minutes))


@pytest.mark.unit
def test_a_submit_then_release_is_one_decided_round() -> None:
    """The simplest shape: one entry, one decision, one measured duration."""
    rounds = build_rounds([_ev(EventType.SUBMITTED, 0), _ev(EventType.RELEASED, 30)])

    assert len(rounds) == 1
    assert rounds[0].storybook_id == "s1"
    assert rounds[0].round_index == 1
    assert rounds[0].outcome is GateOutcome.RELEASED
    assert rounds[0].duration_seconds == 30 * 60


@pytest.mark.unit
def test_a_send_back_and_resubmit_are_two_rounds() -> None:
    """Rounds are paired by ORDER, not by outcome kind.

    A send-back ends round 1; the resubmission opens round 2. Without the
    ``submitted`` event round 2 would have no entry timestamp at all, which is
    the gap this whole measurement exists to close.
    """
    rounds = build_rounds(
        [
            _ev(EventType.SUBMITTED, 0),
            _ev(EventType.SENT_BACK, 10),
            _ev(EventType.SUBMITTED, 100),
            _ev(EventType.RELEASED, 115),
        ]
    )

    assert [r.round_index for r in rounds] == [1, 2]
    assert [r.outcome for r in rounds] == [GateOutcome.SENT_BACK, GateOutcome.RELEASED]
    assert [r.duration_seconds for r in rounds] == [10 * 60, 15 * 60]


@pytest.mark.unit
def test_an_undecided_round_carries_no_duration() -> None:
    """A story still sitting in the queue is open, not instantly approved.

    Defaulting an open round's decision time to "now" or to its entry time
    would silently pull the average down by exactly the reviews that are
    running long, which is the opposite of what the measurement is for.
    """
    rounds = build_rounds([_ev(EventType.SUBMITTED, 0)])

    assert len(rounds) == 1
    assert rounds[0].outcome is None
    assert rounds[0].duration_seconds is None


@pytest.mark.unit
def test_a_decision_before_any_submit_is_dropped() -> None:
    """A pre-migration decision must never pair with a later entry.

    ``submitted`` was added in 20260823120000; every ``released`` and
    ``sent_back`` row written before it has no entry event. Pairing such a row
    with the next ``submitted`` to arrive would invent a NEGATIVE duration, and
    pairing it with the previous one would invent a duration spanning the
    migration. Dropping it is the only honest option, and it is why
    ``summarize_rounds`` reports a decided count rather than assuming every
    decision in the log is measurable.
    """
    rounds = build_rounds(
        [
            _ev(EventType.RELEASED, 0),
            _ev(EventType.SUBMITTED, 100),
            _ev(EventType.RELEASED, 130),
        ]
    )

    assert len(rounds) == 1
    assert rounds[0].duration_seconds == 30 * 60


@pytest.mark.unit
def test_rounds_are_kept_separate_per_storybook() -> None:
    """Interleaved stories never pair across each other."""
    rounds = build_rounds(
        [
            _ev(EventType.SUBMITTED, 0, story="s1"),
            _ev(EventType.SUBMITTED, 5, story="s2"),
            _ev(EventType.RELEASED, 20, story="s2"),
            _ev(EventType.SENT_BACK, 40, story="s1"),
        ]
    )

    by_story = {r.storybook_id: r for r in rounds}
    assert by_story["s1"].outcome is GateOutcome.SENT_BACK
    assert by_story["s1"].duration_seconds == 40 * 60
    assert by_story["s2"].outcome is GateOutcome.RELEASED
    assert by_story["s2"].duration_seconds == 15 * 60


@pytest.mark.unit
def test_unordered_input_is_sorted_before_pairing() -> None:
    """The loader's row order is not guaranteed, so pairing sorts first."""
    ordered = build_rounds([_ev(EventType.SUBMITTED, 0), _ev(EventType.RELEASED, 30)])
    shuffled = build_rounds([_ev(EventType.RELEASED, 30), _ev(EventType.SUBMITTED, 0)])

    assert shuffled == ordered


@pytest.mark.unit
def test_summary_reports_send_back_rate_over_decided_rounds_only() -> None:
    """Open rounds are counted but excluded from the rate's denominator.

    An open round has no outcome, so including it would make the send-back
    rate drift downward purely because reviews are in flight.
    """
    rounds = build_rounds(
        [
            _ev(EventType.SUBMITTED, 0, story="s1"),
            _ev(EventType.SENT_BACK, 10, story="s1"),
            _ev(EventType.SUBMITTED, 0, story="s2"),
            _ev(EventType.RELEASED, 20, story="s2"),
            _ev(EventType.SUBMITTED, 0, story="s3"),
        ]
    )

    summary = summarize_rounds(rounds)

    assert summary.total_rounds == 3
    assert summary.decided_rounds == 2
    assert summary.open_rounds == 1
    assert summary.send_back_rate == 0.5
    assert summary.median_duration_seconds == 900.0


@pytest.mark.unit
def test_summary_of_no_decided_rounds_reports_none_not_zero() -> None:
    """No data is not a rate of zero.

    A 0.0 send-back rate reads as "reviewers never send anything back", which
    is a claim; ``None`` reads as "not measurable yet", which is the truth.
    """
    summary = summarize_rounds(build_rounds([_ev(EventType.SUBMITTED, 0)]))

    assert summary.decided_rounds == 0
    assert summary.send_back_rate is None
    assert summary.median_duration_seconds is None


@pytest.mark.unit
def test_rounds_to_release_counts_only_stories_that_reached_release() -> None:
    """Mean rounds-to-release ignores stories still in the loop.

    A story sent back twice and still unresolved would otherwise cap the
    metric at its current round count and understate the true cost.
    """
    rounds = build_rounds(
        [
            _ev(EventType.SUBMITTED, 0, story="done"),
            _ev(EventType.SENT_BACK, 10, story="done"),
            _ev(EventType.SUBMITTED, 20, story="done"),
            _ev(EventType.RELEASED, 30, story="done"),
            _ev(EventType.SUBMITTED, 0, story="stuck"),
            _ev(EventType.SENT_BACK, 10, story="stuck"),
        ]
    )

    summary = summarize_rounds(rounds)

    assert summary.released_storybooks == 1
    assert summary.mean_rounds_to_release == 2.0
