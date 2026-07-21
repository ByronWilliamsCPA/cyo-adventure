"""Unit tests for the WS-8 flywheel cadence gate (design section 8.2, D8).

The gate :func:`cyo_adventure.flywheel.cadence.select_growable_cells` is the
SINGLE enforcement point for the four cell-facing hard bounds. These tests pin
each bound on hand-built state (the gate is pure: no I/O, no wall-clock), assert
the headline flood property (a flood of saturation events yields at most the
capped PR count), and assert that every capped cell is reported with its specific
bound, never silently dropped.
"""

from __future__ import annotations

from datetime import date, timedelta

from cyo_adventure.flywheel.cadence import (
    CAP_BOUNDS,
    CAP_COOLDOWN,
    CAP_MONTHLY_BUDGET,
    CAP_OPEN_PR_GLOBAL,
    CAP_OPEN_PR_PER_CELL,
    CappedCell,
    reading_cell,
    select_growable_cells,
)
from cyo_adventure.flywheel.strategy import (
    COOLDOWN_DAYS,
    MONTHLY_MERGE_BUDGET,
    OPEN_PR_GLOBAL,
    Cell,
)
from cyo_adventure.flywheel.trigger import SaturationReading

_AS_OF = date(2026, 7, 21)
_NO_MERGES: dict[Cell, date] = {}


def _reading(
    length: str, *, band: str = "8-11", style: str = "prose"
) -> SaturationReading:
    """Build a triggered reading for a distinct cell (length keeps cells distinct)."""
    return SaturationReading(
        band=band,
        length=length,
        style=style,
        catalog_events=5,
        leaf_events=1,
        distinct_requests=3,
        window_days=30,
    )


def _flood(n: int) -> list[SaturationReading]:
    """Build ``n`` triggered readings, each in a distinct cell."""
    return [_reading(f"len{i}") for i in range(n)]


# --- headline flood property ---------------------------------------------------


def test_flood_with_fresh_state_grows_at_most_the_capacity() -> None:
    """A flood of distinct saturated cells yields at most the capped PR count."""
    triggered = _flood(10)
    growable, capped = select_growable_cells(
        triggered,
        open_pr_cells=frozenset(),
        open_pr_global_count=0,
        last_merge_by_cell=_NO_MERGES,
        month_merge_count=0,
        as_of_date=_AS_OF,
    )
    # Capacity is min(OPEN_PR_GLOBAL, MONTHLY_MERGE_BUDGET) with fresh state.
    capacity = min(OPEN_PR_GLOBAL, MONTHLY_MERGE_BUDGET)
    assert len(growable) == capacity
    assert len(capped) == 10 - capacity
    # The overflow is capped by the global open-PR bound (the binding constraint).
    assert all(c.bound == CAP_OPEN_PR_GLOBAL for c in capped)


def test_flood_at_global_cap_grows_nothing_and_reports_all_capped() -> None:
    """With the global open-PR cap already reached, zero cells grow (all capped)."""
    triggered = _flood(8)
    growable, capped = select_growable_cells(
        triggered,
        open_pr_cells=frozenset(),
        open_pr_global_count=OPEN_PR_GLOBAL,
        last_merge_by_cell=_NO_MERGES,
        month_merge_count=0,
        as_of_date=_AS_OF,
    )
    assert growable == []
    assert len(capped) == 8
    assert all(c.bound == CAP_OPEN_PR_GLOBAL for c in capped)


# --- per-cell open PR ----------------------------------------------------------


def test_flood_into_one_cell_with_open_pr_caps_that_cell_per_cell() -> None:
    """A cell that already has an open promotion PR is capped per-cell."""
    busy = _reading("busy")
    fresh = _reading("fresh")
    growable, capped = select_growable_cells(
        [busy, fresh],
        open_pr_cells=frozenset({reading_cell(busy)}),
        open_pr_global_count=1,
        last_merge_by_cell=_NO_MERGES,
        month_merge_count=0,
        as_of_date=_AS_OF,
    )
    assert [reading_cell(r) for r in growable] == [reading_cell(fresh)]
    assert len(capped) == 1
    assert capped[0].cell == reading_cell(busy)
    assert capped[0].bound == CAP_OPEN_PR_PER_CELL


# --- cool-down -----------------------------------------------------------------


def test_recent_merge_caps_cell_by_cooldown_older_merge_is_growable() -> None:
    """A cell merged within the cool-down is capped; one past it may grow."""
    recent = _reading("recent")
    old = _reading("old")
    last_merge = {
        reading_cell(recent): _AS_OF - timedelta(days=10),
        reading_cell(old): _AS_OF - timedelta(days=COOLDOWN_DAYS + 10),
    }
    growable, capped = select_growable_cells(
        [recent, old],
        open_pr_cells=frozenset(),
        open_pr_global_count=0,
        last_merge_by_cell=last_merge,
        month_merge_count=0,
        as_of_date=_AS_OF,
    )
    assert [reading_cell(r) for r in growable] == [reading_cell(old)]
    assert len(capped) == 1
    assert capped[0].cell == reading_cell(recent)
    assert capped[0].bound == CAP_COOLDOWN


def test_merge_exactly_at_cooldown_boundary_is_growable() -> None:
    """A merge exactly COOLDOWN_DAYS ago is out of the window (growable)."""
    reading = _reading("edge")
    last_merge = {reading_cell(reading): _AS_OF - timedelta(days=COOLDOWN_DAYS)}
    growable, capped = select_growable_cells(
        [reading],
        open_pr_cells=frozenset(),
        open_pr_global_count=0,
        last_merge_by_cell=last_merge,
        month_merge_count=0,
        as_of_date=_AS_OF,
    )
    assert len(growable) == 1
    assert capped == []


# --- monthly budget ------------------------------------------------------------


def test_monthly_budget_exhausted_caps_every_cell() -> None:
    """With the month's merge budget spent, every triggered cell is capped."""
    triggered = _flood(5)
    growable, capped = select_growable_cells(
        triggered,
        open_pr_cells=frozenset(),
        open_pr_global_count=0,
        last_merge_by_cell=_NO_MERGES,
        month_merge_count=MONTHLY_MERGE_BUDGET,
        as_of_date=_AS_OF,
    )
    assert growable == []
    assert len(capped) == 5
    assert all(c.bound == CAP_MONTHLY_BUDGET for c in capped)


# --- completeness, precedence, determinism ------------------------------------


def test_every_triggered_cell_is_reported_once_and_never_dropped() -> None:
    """The union of growable and capped is exactly the triggered set (disjoint)."""
    triggered = _flood(7)
    growable, capped = select_growable_cells(
        triggered,
        open_pr_cells=frozenset(),
        open_pr_global_count=1,
        last_merge_by_cell=_NO_MERGES,
        month_merge_count=1,
        as_of_date=_AS_OF,
    )
    accounted = {reading_cell(r) for r in growable} | {c.cell for c in capped}
    assert accounted == {reading_cell(r) for r in triggered}
    assert len(growable) + len(capped) == len(triggered)
    # Every capped cell carries a known, specific bound.
    assert all(c.bound in CAP_BOUNDS for c in capped)


def test_per_cell_open_pr_takes_precedence_over_cooldown() -> None:
    """A cell both open-PR'd and in cool-down records the FIRST bound (per-cell)."""
    reading = _reading("both")
    growable, capped = select_growable_cells(
        [reading],
        open_pr_cells=frozenset({reading_cell(reading)}),
        open_pr_global_count=1,
        last_merge_by_cell={reading_cell(reading): _AS_OF - timedelta(days=1)},
        month_merge_count=0,
        as_of_date=_AS_OF,
    )
    assert growable == []
    assert capped[0].bound == CAP_OPEN_PR_PER_CELL


def test_gate_is_deterministic_for_the_same_inputs() -> None:
    """The same as-of date and state yield the same partition (pure function)."""
    triggered = _flood(6)

    def _call() -> tuple[list[SaturationReading], list[CappedCell]]:
        return select_growable_cells(
            triggered,
            open_pr_cells=frozenset(),
            open_pr_global_count=1,
            last_merge_by_cell=_NO_MERGES,
            month_merge_count=0,
            as_of_date=_AS_OF,
        )

    first_growable, first_capped = _call()
    second_growable, second_capped = _call()
    assert [reading_cell(r) for r in first_growable] == [
        reading_cell(r) for r in second_growable
    ]
    assert [(c.cell, c.bound) for c in first_capped] == [
        (c.cell, c.bound) for c in second_capped
    ]
