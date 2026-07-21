#!/usr/bin/env python3
"""WS-8 scheduled cadence runner: the periodic S1-S6 flywheel cycle (D8, OQ-2).

The v2 cadence of design section 8.1: a scheduled (weekly) run that executes the
flywheel stages S1-S6 behind the six design-8.2 hard bounds and ALWAYS ends at a
draft PR. A human merges; nothing here merges, approves, enables auto-merge, or
pushes to ``main`` (the D4 automation boundary is inherited wholesale). It wires
the delivered pieces:

    S1  read CELL_SATURATED events + trigger thresholds  (flywheel_scan reuse)
      -> cap gate (flywheel.cadence.select_growable_cells, the single 8.2 point)
      -> S2-S5 per growable cell (flywheel_candidates.run_cell_candidates)
      -> S6 prepare a DRAFT promotion PR             (prepare_promotion_pr reuse)

**Every triggered-but-capped cell is reported explicitly** ("cell X saturated but
capped: <bound>"), so demand pressure is deferred, never silently dropped (design
8.2 safety property).

**Injected state, no hidden I/O in tests.** Open-PR state and merge history come
from INJECTED providers so a test supplies canned state and no real GitHub or
database call happens. On a real run whose open-PR feed cannot be confirmed, the
runner degrades conservatively: it does NOT open a PR when it cannot confirm
capacity, and reports why (a capped cell is never grown on an unknown state).

Cadence: run weekly. Environment-dependent because S1 needs read access to the
pipeline-events database; a typical invocation is an operator cron or a scheduled
CI workflow on the default weekly slot, e.g.::

    # crontab: Mondays 09:00 UTC, dry-run report only (no side effect)
    0 9 * * 1  cd /srv/cyo-adventure && uv run python scripts/flywheel_cycle.py

    # a real run that prepares draft PRs (never merges):
    uv run python scripts/flywheel_cycle.py --run --create-prs

Exit codes:
    0 - the cycle plan was produced (dry run) or executed (``--run``).
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess  # nosec B404 -- read-only `gh pr list` only, list-form argv; audited below
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

# Make the repository root importable so the sibling scripts resolve when this
# file is run directly (its own directory, not the repo root, is on sys.path).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.flywheel.cadence import (  # noqa: E402
    CappedCell,
    reading_cell,
    select_growable_cells,
)
from cyo_adventure.flywheel.strategy import Catalog, Cell, load_catalog  # noqa: E402
from cyo_adventure.flywheel.trigger import (  # noqa: E402
    DEFAULT_MIN_CATALOG_EVENTS,
    DEFAULT_MIN_DISTINCT_REQUESTS,
    RawSaturationEvent,
    SaturationReading,
    saturated_cells,
    saturation_readings,
)
from scripts import flywheel_candidates as fc  # noqa: E402
from scripts import flywheel_report as fr  # noqa: E402
from scripts import prepare_promotion_pr as ppr  # noqa: E402
from scripts.flywheel_scan import fetch_saturation_events  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    # S1: fetch raw CELL_SATURATED events over a window (default: DB-backed).
    EventSource = Callable[[int], list[RawSaturationEvent]]
    # The gate's injected open-PR state and merge history providers.
    OpenPrProvider = Callable[[Catalog], "OpenPrFeed"]
    MergeHistoryProvider = Callable[[Catalog, str], "MergeHistory"]
    # S2-S5: grow one cell, returning its bundle directory (or None if none survived).
    CellRunner = Callable[[SaturationReading], Path | None]
    # S6: prepare a draft PR from a bundle directory, returning an exit code.
    PrPreparer = Callable[[Path], int]

_DEFAULT_WINDOW_DAYS = 30
_DEFAULT_OUT_DIR = Path("out") / "mutations"


@dataclass(frozen=True, slots=True)
class OpenPrFeed:
    """The open-``skeleton-promotion``-PR state the cap gate needs (injected).

    Attributes:
        cells: The cells that already have an open promotion PR (per-cell cap).
        global_count: The total number of open promotion PRs (global cap).
        confirmed: Whether this state could be confirmed. When False, the runner
            degrades conservatively and opens no PR (it cannot confirm capacity).
    """

    cells: frozenset[Cell]
    global_count: int
    confirmed: bool


@dataclass(frozen=True, slots=True)
class MergeHistory:
    """The promotion-merge history the cap gate needs (injected).

    Attributes:
        last_merge_by_cell: The most recent promotion-merge date per cell
            (cool-down bound).
        month_merge_count: The count of promotion merges already in the run's
            month (monthly-budget bound).
    """

    last_merge_by_cell: dict[Cell, date]
    month_merge_count: int


# --------------------------------------------------------------------------- #
# Default providers (real environment; every one is overridden in tests).
# --------------------------------------------------------------------------- #


def _db_event_source(window_days: int) -> list[RawSaturationEvent]:
    """Fetch CELL_SATURATED events via the read-only DB read (flywheel_scan reuse)."""
    return asyncio.run(fetch_saturation_events(window_days))


def _gh_open_pr_feed(catalog: Catalog) -> OpenPrFeed:
    """Read open ``skeleton-promotion`` PRs via ``gh``; degrade conservatively.

    Counts open promotion PRs (global cap) and maps each PR's
    ``flywheel/promote-<mutant_slug>`` head branch back to its parent's cell (the
    per-cell cap). ANY failure (``gh`` absent, non-zero, unparseable) returns an
    UNCONFIRMED feed so the runner opens nothing rather than guessing capacity.

    Args:
        catalog: The catalog scan (maps a parent slug to its cell).

    Returns:
        OpenPrFeed: The confirmed open-PR state, or an unconfirmed empty feed.
    """
    # #ASSUME: external-resources: `gh` is on PATH and authenticated. list-form
    # argv, no shell, read-only subcommand. A failure is NOT fatal: it yields an
    # unconfirmed feed and the runner defers every cell (fail-closed on capacity).
    # #VERIFY: tests inject canned feeds; this real path only runs in a real env.
    try:
        result = subprocess.run(  # nosec B603 B607
            [
                "gh",
                "pr",
                "list",
                "--label",
                ppr.PROMOTION_LABEL,
                "--state",
                "open",
                "--json",
                "headRefName",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        rows = cast("object", json.loads(result.stdout))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return OpenPrFeed(cells=frozenset(), global_count=0, confirmed=False)
    if not isinstance(rows, list):
        return OpenPrFeed(cells=frozenset(), global_count=0, confirmed=False)
    branches = [
        head
        for row in cast("list[object]", rows)
        if isinstance(row, dict)
        and isinstance(head := cast("dict[str, object]", row).get("headRefName"), str)
    ]
    cells: set[Cell] = set()
    for branch in branches:
        cell = _branch_cell(branch, catalog)
        if cell is not None:
            cells.add(cell)
    return OpenPrFeed(
        cells=frozenset(cells), global_count=len(branches), confirmed=True
    )


def _branch_cell(branch: str, catalog: Catalog) -> Cell | None:
    """Map a ``flywheel/promote-<parent>-fw-<sig>`` branch to its parent's cell."""
    prefix = "flywheel/promote-"
    if not branch.startswith(prefix):
        return None
    mutant_slug = branch[len(prefix) :]
    parent_slug = mutant_slug.rsplit("-fw-", 1)[0]
    entry = catalog.by_slug(parent_slug)
    if entry is None or entry.metadata.length is None:
        return None
    return Cell(
        band=entry.metadata.age_band.value,
        length=entry.metadata.length.value,
        style=entry.metadata.narrative_style.value,
    )


def _git_merge_history(catalog: Catalog, as_of_month: str) -> MergeHistory:
    """Derive promotion-merge history from ``skeletons/**`` git log (D7 reuse).

    Reuses D7's read-only ``git log`` lineage-addition reader: a merged flywheel
    tree adds a ``*.lineage.json`` sidecar, so a tree addition whose slug is in
    the lineage-slug set is a flywheel merge. Merge dates are month-granular here
    (the D7 reader keys on ``YYYY-MM``); a deployment needing day-precise
    cool-downs injects a finer provider. Month granularity is conservative for
    the cool-down (a mid-month merge reads as the 1st, which is at worst slightly
    older, never falsely fresh).

    Args:
        catalog: The (post-merge) catalog scan; a merged tree's slug resolves to
            its cell here.
        as_of_month: The run's ``YYYY-MM`` month, for the monthly-budget count.

    Returns:
        MergeHistory: The per-cell last-merge dates and the month's merge count.
    """
    runner = fr.default_git_runner(_REPO_ROOT)
    additions, lineage_slugs = fr.added_skeleton_history(runner)
    last_merge_by_cell: dict[Cell, date] = {}
    month_merge_count = 0
    for addition in additions:  # git log order: newest first
        if addition.slug not in lineage_slugs:
            continue
        if addition.month == as_of_month:
            month_merge_count += 1
        entry = catalog.by_slug(addition.slug)
        if entry is None or entry.metadata.length is None:
            continue
        cell = Cell(
            band=entry.metadata.age_band.value,
            length=entry.metadata.length.value,
            style=entry.metadata.narrative_style.value,
        )
        # Newest-first: keep the first (most recent) merge date seen per cell.
        if cell not in last_merge_by_cell:
            last_merge_by_cell[cell] = date.fromisoformat(f"{addition.month}-01")
    return MergeHistory(
        last_merge_by_cell=last_merge_by_cell, month_merge_count=month_merge_count
    )


def _make_cell_runner(out_root: Path) -> CellRunner:
    """Return the default S2-S5 runner: grow a cell via flywheel_candidates."""

    def _run(reading: SaturationReading) -> Path | None:
        result = fc.run_cell_candidates(
            reading_cell(reading), out_root=out_root, ledger_root=_REPO_ROOT
        )
        return result.bundle_dir

    return _run


def _make_pr_preparer(*, skeletons_root: Path, create: bool) -> PrPreparer:
    """Return the default S6 preparer: prepare a DRAFT PR via prepare_promotion_pr.

    Delegates to the D4 script, which NEVER merges/approves/auto-merges and ends
    at a draft PR. Without ``create`` it is a dry run (prints the ``gh pr create
    --draft`` command); with ``create`` it stages a worktree and opens the draft
    PR (still never merging).
    """

    def _prepare(bundle_dir: Path) -> int:
        argv = [str(bundle_dir), "--skeletons-root", str(skeletons_root)]
        if create:
            argv.append("--create")
        return ppr.main(argv)

    return _prepare


# --------------------------------------------------------------------------- #
# Reporting.
# --------------------------------------------------------------------------- #


def _fmt_cell(cell: Cell) -> str:
    """Return a stable ``band=.. length=.. style=..`` cell label."""
    return f"band={cell.band} length={cell.length} style={cell.style}"


def _fmt_reading(reading: SaturationReading) -> str:
    """Return a stable cell label plus the deferred demand counters."""
    return (
        f"{_fmt_cell(reading_cell(reading))} "
        f"(catalog={reading.catalog_events} distinct_requests={reading.distinct_requests})"
    )


def _render_plan(
    *,
    triggered: Sequence[SaturationReading],
    growable: Sequence[SaturationReading],
    capped: Sequence[CappedCell],
    as_of: date,
    window_days: int,
    dry_run: bool,
) -> list[str]:
    """Render the cycle plan (which cells grow, which are capped and why)."""
    mode = "DRY RUN (no side effect)" if dry_run else "RUN"
    lines = [
        "CYO Adventure scheduled flywheel cycle (S1-S6)",
        f"mode: {mode} | as-of: {as_of.isoformat()} | window: {window_days} days",
        (
            f"triggered cells: {len(triggered)} | growable: {len(growable)} | "
            f"capped: {len(capped)}"
        ),
        "",
        f"Growable cells ({len(growable)}):",
    ]
    verb = "would prepare" if dry_run else "preparing"
    lines.extend(
        f"  {_fmt_reading(r)} -> {verb} a DRAFT promotion PR" for r in growable
    )
    if not growable:
        lines.append("  (none)")
    lines.extend(["", f"Capped cells, deferred not dropped ({len(capped)}):"])
    lines.extend(
        f"  {_fmt_reading(c.reading)} saturated but capped: {c.bound}" for c in capped
    )
    if not capped:
        lines.append("  (none)")
    return lines


def _render_unconfirmed(triggered: Sequence[SaturationReading]) -> list[str]:
    """Render the conservative-degrade report when open-PR state is unconfirmed."""
    lines = [
        "CYO Adventure scheduled flywheel cycle (S1-S6)",
        (
            "open-PR state could NOT be confirmed (no GitHub feed available); "
            "capacity is unknown, so NO PR is opened this cycle (conservative "
            "degrade, design 8.1 safety posture)."
        ),
        "",
        (
            f"Triggered cells deferred pending a confirmed open-PR feed "
            f"({len(triggered)}):"
        ),
    ]
    lines.extend(
        f"  {_fmt_reading(r)} deferred: open-PR state unconfirmed" for r in triggered
    )
    if not triggered:
        lines.append("  (none)")
    return lines


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #


def run_cycle(
    *,
    window_days: int,
    min_catalog_events: int,
    min_distinct_requests: int,
    as_of: date,
    dry_run: bool,
    event_source: EventSource,
    open_pr_provider: OpenPrProvider,
    merge_history_provider: MergeHistoryProvider,
    cell_runner: CellRunner,
    pr_preparer: PrPreparer,
) -> list[str]:
    """Execute one flywheel cycle end to end and return the report lines.

    Pure over its injected seams (no direct I/O beyond what the providers do), so
    a test drives the whole S1-S6 plan from canned state. The cap gate
    (:func:`~cyo_adventure.flywheel.cadence.select_growable_cells`) is the single
    enforcement point; this function only orchestrates and reports.

    Args:
        window_days: The S1 saturation window.
        min_catalog_events: The trigger's catalog-event threshold.
        min_distinct_requests: The trigger's distinct-request threshold.
        as_of: The run date (drives cool-down and the monthly-budget month).
        dry_run: When True, only the plan is produced (no bundle, no PR).
        event_source: The S1 event read.
        open_pr_provider: The open-PR state provider (the gate's per-cell/global
            caps).
        merge_history_provider: The merge-history provider (cool-down / budget).
        cell_runner: The S2-S5 per-cell grower (returns a bundle dir or None).
        pr_preparer: The S6 draft-PR preparer.

    Returns:
        list[str]: The report lines (the caller joins and prints them).
    """
    events = event_source(window_days)
    readings = saturation_readings(events, window_days=window_days)
    triggered = saturated_cells(
        readings,
        min_catalog_events=min_catalog_events,
        min_distinct_requests=min_distinct_requests,
    )

    catalog = load_catalog(_REPO_ROOT)
    feed = open_pr_provider(catalog)
    if not feed.confirmed:
        # Conservative degrade: cannot confirm capacity, so open nothing.
        return _render_unconfirmed(triggered)

    history = merge_history_provider(catalog, as_of.strftime("%Y-%m"))
    growable, capped = select_growable_cells(
        triggered,
        open_pr_cells=feed.cells,
        open_pr_global_count=feed.global_count,
        last_merge_by_cell=history.last_merge_by_cell,
        month_merge_count=history.month_merge_count,
        as_of_date=as_of,
    )

    lines = _render_plan(
        triggered=triggered,
        growable=growable,
        capped=capped,
        as_of=as_of,
        window_days=window_days,
        dry_run=dry_run,
    )
    if dry_run:
        return lines

    lines.extend(["", "Execution (S2-S6):"])
    for reading in growable:
        label = _fmt_cell(reading_cell(reading))
        bundle_dir = cell_runner(reading)
        if bundle_dir is None:
            lines.append(f"  {label}: no candidate survived; no PR prepared")
            continue
        code = pr_preparer(bundle_dir)
        status = "draft PR prepared" if code == 0 else f"PR prep refused (exit {code})"
        lines.append(f"  {label}: bundled {bundle_dir} -> {status}")
    return lines


def _build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--window-days",
        type=int,
        default=_DEFAULT_WINDOW_DAYS,
        help=f"S1 saturation window in days (default: {_DEFAULT_WINDOW_DAYS}).",
    )
    _ = parser.add_argument(
        "--min-catalog-events",
        type=int,
        default=DEFAULT_MIN_CATALOG_EVENTS,
        help=f"Trigger catalog-event threshold (default: {DEFAULT_MIN_CATALOG_EVENTS}).",
    )
    _ = parser.add_argument(
        "--min-distinct-requests",
        type=int,
        default=DEFAULT_MIN_DISTINCT_REQUESTS,
        help=(
            "Trigger distinct-request threshold "
            f"(default: {DEFAULT_MIN_DISTINCT_REQUESTS})."
        ),
    )
    _ = parser.add_argument(
        "--as-of",
        default=None,
        help="Run date YYYY-MM-DD for cool-down/budget (default: today, UTC).",
    )
    _ = parser.add_argument(
        "--out-dir",
        default=str(_DEFAULT_OUT_DIR),
        help=f"Bundle output root under out/ (default: {_DEFAULT_OUT_DIR}).",
    )
    _ = parser.add_argument(
        "--skeletons-root",
        default=str(_REPO_ROOT / "skeletons"),
        help="Live catalog root for verify_bundle at S6 (default: ./skeletons).",
    )
    _ = parser.add_argument(
        "--run",
        action="store_true",
        help="Execute S2-S6 (bundle + prepare draft PRs). Default is a dry-run plan.",
    )
    _ = parser.add_argument(
        "--create-prs",
        action="store_true",
        help="With --run, actually open the draft PRs (never merges). Else dry-run PRs.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    event_source: EventSource | None = None,
    open_pr_provider: OpenPrProvider | None = None,
    merge_history_provider: MergeHistoryProvider | None = None,
    cell_runner: CellRunner | None = None,
    pr_preparer: PrPreparer | None = None,
) -> int:
    """Run one scheduled flywheel cycle (dry-run plan by default).

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).
        event_source: Optional S1 event read override (default: DB-backed).
        open_pr_provider: Optional open-PR state override (default: ``gh``-backed,
            degrading conservatively).
        merge_history_provider: Optional merge-history override (default: git-log).
        cell_runner: Optional S2-S5 override (default: flywheel_candidates).
        pr_preparer: Optional S6 override (default: prepare_promotion_pr, draft).

    Returns:
        int: ``0`` on a produced/executed cycle, ``2`` on an argparse usage error.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    as_of_arg = cast("str | None", args.as_of)
    as_of = (
        date.fromisoformat(as_of_arg)
        if as_of_arg is not None
        else datetime.now(UTC).date()
    )
    out_root = Path(cast("str", args.out_dir)).resolve()
    skeletons_root = Path(cast("str", args.skeletons_root)).resolve()
    dry_run = not cast("bool", args.run)

    lines = run_cycle(
        window_days=int(cast("int", args.window_days)),
        min_catalog_events=int(cast("int", args.min_catalog_events)),
        min_distinct_requests=int(cast("int", args.min_distinct_requests)),
        as_of=as_of,
        dry_run=dry_run,
        event_source=event_source if event_source is not None else _db_event_source,
        open_pr_provider=(
            open_pr_provider if open_pr_provider is not None else _gh_open_pr_feed
        ),
        merge_history_provider=(
            merge_history_provider
            if merge_history_provider is not None
            else _git_merge_history
        ),
        cell_runner=(
            cell_runner if cell_runner is not None else _make_cell_runner(out_root)
        ),
        pr_preparer=(
            pr_preparer
            if pr_preparer is not None
            else _make_pr_preparer(
                skeletons_root=skeletons_root, create=cast("bool", args.create_prs)
            )
        ),
    )
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
