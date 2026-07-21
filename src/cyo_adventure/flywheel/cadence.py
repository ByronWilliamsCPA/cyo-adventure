"""WS-8 catalog-flywheel cadence gate: the single cap-enforcement point (8.2).

The scheduled cadence runner (D8, ``scripts/flywheel_cycle.py``) turns a set of
triggered cells (from D1's :func:`~cyo_adventure.flywheel.trigger.saturated_cells`)
into the cells it may actually grow this cycle. Every one of the design-8.2 hard
bounds is enforced HERE, in one pure function, so the safety property is
structural: a triggered cell that a bound blocks is returned as a
:class:`CappedCell` carrying the SPECIFIC bound that blocked it, never silently
dropped. Demand is only ever deferred, never lost.

The four cell-facing bounds this gate enforces (the trigger threshold is applied
upstream by D1; ``MAX_ATTEMPTS_PER_CELL`` is applied per cell inside the strategy):

- **open PRs per cell** (:data:`~cyo_adventure.flywheel.strategy.OPEN_PR_PER_CELL`):
  a cell that already has an open ``skeleton-promotion`` PR waits;
- **open PRs global** (:data:`~cyo_adventure.flywheel.strategy.OPEN_PR_GLOBAL`):
  the cycle admits cells only up to the remaining global open-PR capacity;
- **per-cell cool-down** (:data:`~cyo_adventure.flywheel.strategy.COOLDOWN_DAYS`):
  a cell merged within the cool-down window waits;
- **monthly promotion budget**
  (:data:`~cyo_adventure.flywheel.strategy.MONTHLY_MERGE_BUDGET`): the cycle
  admits cells only up to the month's remaining budget.

**The function is pure and deterministic.** It performs no I/O and reads no
wall-clock: the run date, the open-PR state, the merge history, and the month's
merge count are all INJECTED, so a test drives every bound from hand-built state
and the same inputs always yield the same plan (design principle 7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.flywheel.strategy import (
    COOLDOWN_DAYS,
    MONTHLY_MERGE_BUDGET,
    OPEN_PR_GLOBAL,
    Cell,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import date

    from cyo_adventure.flywheel.trigger import SaturationReading

# The bound identifiers a capped cell reports. Closed set, one per design-8.2
# cell-facing bound; the runner renders these verbatim ("cell X saturated but
# capped: <bound>").
CAP_OPEN_PR_PER_CELL = "open-pr-per-cell"
CAP_OPEN_PR_GLOBAL = "open-pr-global"
CAP_COOLDOWN = "cool-down"
CAP_MONTHLY_BUDGET = "monthly-budget"

# Every bound this gate can record, for the report/test completeness check.
CAP_BOUNDS: frozenset[str] = frozenset(
    {CAP_OPEN_PR_PER_CELL, CAP_OPEN_PR_GLOBAL, CAP_COOLDOWN, CAP_MONTHLY_BUDGET}
)


@dataclass(frozen=True, slots=True)
class CappedCell:
    """A triggered cell a bound blocked this cycle (deferred, not dropped).

    Attributes:
        reading: The triggered saturation reading (its counters are preserved so
            the report shows the demand pressure that was deferred).
        cell: The ``(band, length, style)`` coordinate the reading maps to.
        bound: The SPECIFIC bound that blocked the cell (one of :data:`CAP_BOUNDS`):
            the FIRST bound that applied in the gate's precedence order.
    """

    reading: SaturationReading
    cell: Cell
    bound: str


def reading_cell(reading: SaturationReading) -> Cell:
    """Return the ``(band, length, style)`` cell coordinate of a reading.

    Args:
        reading: A per-cell saturation reading.

    Returns:
        Cell: The reading's cell coordinate (enum values only).
    """
    return Cell(band=reading.band, length=reading.length, style=reading.style)


def select_growable_cells(  # noqa: PLR0913 -- one cohesive 8.2 cap-gate signature
    triggered_cells: Sequence[SaturationReading],
    *,
    open_pr_cells: frozenset[Cell],
    open_pr_global_count: int,
    last_merge_by_cell: Mapping[Cell, date],
    month_merge_count: int,
    as_of_date: date,
) -> tuple[list[SaturationReading], list[CappedCell]]:
    """Apply the four design-8.2 cell-facing bounds; partition triggered cells.

    This is the flywheel's single cap-enforcement point (design 8.2 safety
    property). It is pure: no I/O, no wall-clock. Every triggered cell ends up in
    exactly one of the two returned lists, so a capped cell is always reported
    with its bound, never silently dropped.

    Precedence per cell (the FIRST applying bound is the one recorded):

    1. **per-cell open PR** (:data:`CAP_OPEN_PR_PER_CELL`): the cell is in
       ``open_pr_cells``;
    2. **cool-down** (:data:`CAP_COOLDOWN`): the cell was merged fewer than
       :data:`~cyo_adventure.flywheel.strategy.COOLDOWN_DAYS` days before
       ``as_of_date``;
    3. **global open-PR capacity** (:data:`CAP_OPEN_PR_GLOBAL`): the remaining
       :data:`~cyo_adventure.flywheel.strategy.OPEN_PR_GLOBAL` capacity, net of
       ``open_pr_global_count`` and the cells already admitted this cycle, is
       exhausted;
    4. **monthly budget** (:data:`CAP_MONTHLY_BUDGET`): the remaining
       :data:`~cyo_adventure.flywheel.strategy.MONTHLY_MERGE_BUDGET`, net of
       ``month_merge_count`` and the cells already admitted this cycle, is
       exhausted.

    The two capacity bounds are decremented as cells are admitted, so the number
    of growable cells is bounded by
    ``min(remaining_global, remaining_monthly)``: a flood of saturation events
    can yield at most the capped number of new PRs, in cell order.

    Args:
        triggered_cells: The over-threshold readings from D1 (in a stable order).
        open_pr_cells: The cells with an open ``skeleton-promotion`` PR.
        open_pr_global_count: The current global count of open promotion PRs.
        last_merge_by_cell: The most recent merge date per cell (absent = never
            merged).
        month_merge_count: The count of promotion merges already in the current
            month.
        as_of_date: The run date the cool-down is measured against (injected;
            never the wall clock).

    Returns:
        tuple[list[SaturationReading], list[CappedCell]]: ``(growable, capped)``,
            partitioning ``triggered_cells``; the union is complete and disjoint.
    """
    remaining_global = max(0, OPEN_PR_GLOBAL - open_pr_global_count)
    remaining_monthly = max(0, MONTHLY_MERGE_BUDGET - month_merge_count)

    growable: list[SaturationReading] = []
    capped: list[CappedCell] = []
    for reading in triggered_cells:
        cell = reading_cell(reading)
        bound = _blocking_bound(
            cell,
            open_pr_cells=open_pr_cells,
            last_merge_by_cell=last_merge_by_cell,
            as_of_date=as_of_date,
            remaining_global=remaining_global,
            remaining_monthly=remaining_monthly,
        )
        if bound is not None:
            capped.append(CappedCell(reading=reading, cell=cell, bound=bound))
            continue
        growable.append(reading)
        remaining_global -= 1
        remaining_monthly -= 1
    return growable, capped


def _blocking_bound(  # noqa: PLR0913 -- the four 8.2 bounds plus running budgets
    cell: Cell,
    *,
    open_pr_cells: frozenset[Cell],
    last_merge_by_cell: Mapping[Cell, date],
    as_of_date: date,
    remaining_global: int,
    remaining_monthly: int,
) -> str | None:
    """Return the first design-8.2 bound blocking ``cell``, or None if growable.

    Applies the four cell-facing bounds in the fixed precedence order documented
    on :func:`select_growable_cells`; the remaining-capacity values are the
    caller's running budgets (already net of cells admitted earlier this cycle).

    Args:
        cell: The cell coordinate under test.
        open_pr_cells: The cells with an open promotion PR.
        last_merge_by_cell: The most recent merge date per cell.
        as_of_date: The run date the cool-down is measured against.
        remaining_global: The global open-PR capacity left this cycle.
        remaining_monthly: The monthly merge budget left this cycle.

    Returns:
        str | None: The blocking bound id, or None when the cell may grow.
    """
    if cell in open_pr_cells:
        return CAP_OPEN_PR_PER_CELL
    merged_on = last_merge_by_cell.get(cell)
    if merged_on is not None and (as_of_date - merged_on).days < COOLDOWN_DAYS:
        return CAP_COOLDOWN
    if remaining_global <= 0:
        return CAP_OPEN_PR_GLOBAL
    if remaining_monthly <= 0:
        return CAP_MONTHLY_BUDGET
    return None
