#!/usr/bin/env python3
"""Read-only WS-8 catalog-flywheel metrics report (design section 9, D7).

Assembles the six section-9 tables plus the section-6.5 catalog-hygiene table
into one markdown document, from four already-committed or scratch sources and
NOTHING that mutates state:

1. Net new trees per month (headline) - from ``*.lineage.json`` additions in
   ``skeletons/**`` git history plus the catalog scan; hand-authored additions
   (a tree ``.json`` with no accompanying ``*.lineage.json``) are counted
   SEPARATELY so the flywheel's own contribution is honest (design 9).
2. Distinct trees per cell (trend) - per cell, the skeleton count and the
   in-cell pairwise ``structural_distance`` min/median, the same numbers the
   floor calibrator computes.
3. Effective catalog size - :func:`~cyo_adventure.diversity.aggregate.
   effective_catalog_size` over the catalog (usage-weighted served-window ECS
   needs the reading-events DB and is noted as such).
4. Promotion funnel - per-outcome counts from the ledger
   (``out/mutations/_ledger/attempts.jsonl``); PR opened/merged/closed come
   from git/GitHub and are noted as not derivable here.
5. Re-guidance cost - the derivable parts from the ledger; the rest (items per
   bundled candidate, human edit rate) needs merged promotion bundles/PRs and
   is noted.
6. Demand response - CATALOG-event rate before vs after a merge, DB-OPTIONAL;
   empty with a note when no reading-events DB is supplied.
7. Catalog hygiene (6.5) - the standing in-cell minimum pairwise
   ``structural_distance`` over the WHOLE catalog, surfacing any near-duplicate
   pair so erosion is visible every cycle.

    uv run python scripts/flywheel_report.py --as-of 2026-07-21

**CRITICAL: this script is READ-ONLY.** It reads git history (``git log``
only), the catalog files, and the ledger, and writes exactly ONE file: the
markdown report under ``docs/planning/flywheel-reports/`` (or ``--out``). It
never mutates state, never runs a writing git command, never opens a PR, and
never gates CI. Every table degrades gracefully: an empty table (no merged
promotions yet, an empty ledger, no events) is a valid, honest result printed
with an explanatory note, never an error.

Determinism: the report carries NO wall-clock. The as-of label is an injected
argument and the git history, ledger, and catalog are the only inputs, so the
same inputs render byte-identical markdown across runs (the D7 determinism
test).

Exit codes:
    0 - report written (whether or not any table has rows).
    2 - argparse usage error.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess  # nosec B404 -- read-only `git log` only, list-form argv; audited below
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from cyo_adventure.diversity.aggregate import effective_catalog_size
from cyo_adventure.diversity.structure import structural_distance
from cyo_adventure.flywheel.ledger import (
    OUTCOME_DISCARDED,
    OUTCOME_HELD,
    OUTCOME_PROMOTABLE,
    OUTCOME_SHELVED,
    AttemptRecord,
    ledger_path,
    load_records,
)
from cyo_adventure.flywheel.strategy import (
    Catalog,
    CatalogEntry,
    cell_of_entry,
    load_catalog,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    # A git runner takes the argv AFTER ``git`` and returns stdout. Injectable so
    # tests drive the report from a fixture history with no real repository.
    GitRunner = Callable[[Sequence[str]], str]

# The repository root, resolved from this file so the report behaves identically
# regardless of the invoking cwd (mirrors the strategy/floors convention).
_REPO_ROOT = Path(__file__).resolve().parents[1]

# The committed report home (design OQ-8: trend tables are longitudinal and
# belong in versioned history).
_REPORT_DIR = _REPO_ROOT / "docs" / "planning" / "flywheel-reports"

# The one read-only git subcommand this report ever runs. The default runner
# refuses anything else, so the read-only property is enforced, not merely
# documented (the D7 read-only-pin test asserts this).
_ALLOWED_GIT_SUBCOMMANDS: frozenset[str] = frozenset({"log"})

# A per-commit marker prefix for the ``git log`` format. U+001F (unit
# separator) never appears in a path, so a marked line is unambiguously a commit
# header and every other non-blank line is an added file path.
_COMMIT_MARKER = "\x1f"

# The lineage / contract sidecar suffixes (mirrors generation.skeleton
# SIDECAR_SUFFIXES by value; a report holds no cross-module private import).
_LINEAGE_SUFFIX = ".lineage.json"
_CONTRACT_SUFFIX = ".contract.json"


def default_git_runner(repo_root: Path) -> GitRunner:
    """Return a read-only ``git`` runner bound to ``repo_root``.

    The returned callable runs ``git -C <repo_root> <argv...>`` with list-form
    argv and no shell, and REFUSES any subcommand outside
    :data:`_ALLOWED_GIT_SUBCOMMANDS` (only ``log``), so the report structurally
    cannot invoke a mutating git command.

    Args:
        repo_root: The repository whose history is read.

    Returns:
        GitRunner: The bound, read-only runner.
    """

    def _run(argv: Sequence[str]) -> str:
        # #CRITICAL: security: the report is read-only. Refusing any subcommand
        # but `log` makes that enforceable here, at the one process boundary; a
        # mutating git command (commit/add/push) can never be issued.
        # #VERIFY: the D7 read-only test asserts a non-`log` subcommand raises and
        # that the source runs no writing git command.
        if not argv or argv[0] not in _ALLOWED_GIT_SUBCOMMANDS:
            subcommand = argv[0] if argv else "(none)"
            msg = f"refusing non-read-only git subcommand {subcommand!r}"
            raise ValueError(msg)
        # #ASSUME: external-resources: git is on PATH and the cwd is a work tree.
        # list-form argv, no shell; a git failure surfaces as a non-zero exit that
        # the caller sees as empty output, degrading the table to "no history".
        result = subprocess.run(  # nosec B603 B607
            ["git", "-C", str(repo_root), *argv],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout

    return _run


# --- Table 1: net new trees per month -----------------------------------------


class TreeAddition:
    """One added ``skeletons/**`` tree file from git history.

    Attributes:
        slug: The tree's slug (filename stem).
        month: The ``YYYY-MM`` the tree file was added.
    """

    __slots__ = ("month", "slug")

    def __init__(self, slug: str, month: str) -> None:
        self.slug = slug
        self.month = month


def _log_added_skeleton_files(git_runner: GitRunner) -> str:
    """Return the ``git log`` add-history of ``skeletons/`` files.

    Args:
        git_runner: The injected read-only git runner.

    Returns:
        str: The raw ``git log`` output (commit markers + added file paths).
    """
    return git_runner(
        [
            "log",
            "--diff-filter=A",
            "--name-only",
            "--date=short",
            f"--format={_COMMIT_MARKER}%ad",
            "--",
            "skeletons",
        ]
    )


def parse_tree_additions(log_output: str) -> tuple[list[TreeAddition], set[str]]:
    """Parse ``git log`` output into tree additions and the lineage-slug set.

    A ``*.lineage.json`` addition marks its tree as flywheel-derived; a
    ``*.contract.json`` addition is ignored (a parameterization PR adds a
    contract but NO new tree, so it is correctly not a net-new tree, D6 note); a
    plain ``<slug>.json`` addition is a tree whose origin is decided by whether
    its slug is in the lineage-slug set.

    Args:
        log_output: The raw ``_log_added_skeleton_files`` output.

    Returns:
        tuple[list[TreeAddition], set[str]]: The tree additions in log order, and
            the set of slugs that ever had a lineage sidecar added.
    """
    additions: list[TreeAddition] = []
    lineage_slugs: set[str] = set()
    month = ""
    for raw_line in log_output.splitlines():
        if raw_line.startswith(_COMMIT_MARKER):
            date = raw_line[len(_COMMIT_MARKER) :].strip()
            month = date[:7]
            continue
        path = raw_line.strip()
        if not path or month == "":
            continue
        name = Path(path).name
        if name.endswith(_LINEAGE_SUFFIX):
            lineage_slugs.add(name[: -len(_LINEAGE_SUFFIX)])
        elif name.endswith(_CONTRACT_SUFFIX):
            continue
        elif name.endswith(".json"):
            additions.append(TreeAddition(slug=name[: -len(".json")], month=month))
    return additions, lineage_slugs


def added_skeleton_history(
    git_runner: GitRunner,
) -> tuple[list[TreeAddition], set[str]]:
    """Return the parsed ``skeletons/**`` add-history and the lineage-slug set.

    The public reuse seam for the D8 scheduled cadence runner
    (``scripts/flywheel_cycle.py``), which derives its merge history from the same
    read-only ``git log`` lineage-addition reader this report uses. It composes
    the two existing steps (:func:`_log_added_skeleton_files` then
    :func:`parse_tree_additions`) so a caller reuses D7's git-log reader without
    touching this module's private helpers.

    Args:
        git_runner: The injected read-only git runner.

    Returns:
        tuple[list[TreeAddition], set[str]]: The tree additions in git-log order
            (newest first) and the set of slugs that ever gained a lineage sidecar.
    """
    return parse_tree_additions(_log_added_skeleton_files(git_runner))


def _render_net_new_table(
    additions: Sequence[TreeAddition], lineage_slugs: set[str]
) -> list[str]:
    """Render the net-new-trees-per-month table (design 9 headline)."""
    flywheel_by_month: dict[str, int] = {}
    hand_by_month: dict[str, int] = {}
    for addition in additions:
        bucket = flywheel_by_month if addition.slug in lineage_slugs else hand_by_month
        bucket[addition.month] = bucket.get(addition.month, 0) + 1

    lines = [
        "## 1. Net new trees per month (headline)",
        "",
        (
            "Flywheel-derived trees carry a `*.lineage.json` sidecar; "
            "hand-authored trees do not. The two are counted separately so the "
            "flywheel's own contribution is honest (design section 9)."
        ),
        "",
    ]
    months = sorted(set(flywheel_by_month) | set(hand_by_month))
    if not months:
        lines.append(
            "_No `skeletons/**` tree additions in git history yet "
            "(a fresh system before the first promotion). Empty is honest._"
        )
        lines.append("")
        return lines
    lines.extend(
        [
            "| Month | Flywheel (lineage) | Hand-authored | Total |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    total_flywheel = 0
    total_hand = 0
    for month in months:
        flywheel = flywheel_by_month.get(month, 0)
        hand = hand_by_month.get(month, 0)
        total_flywheel += flywheel
        total_hand += hand
        lines.append(f"| {month} | {flywheel} | {hand} | {flywheel + hand} |")
    lines.append(
        f"| **Total** | **{total_flywheel}** | **{total_hand}** | "
        f"**{total_flywheel + total_hand}** |"
    )
    lines.append("")
    return lines


# --- Catalog cell grouping (tables 2 and 7) -----------------------------------


def _cell_key(entry: CatalogEntry) -> tuple[str, str, str] | None:
    """Return an entry's exact ``(band, length, style)`` cell, or None.

    Mirrors the floor calibrator's ``_cell_of`` so tables 2 and 7 report the same
    numbers the calibrator computes: a tree missing any of the three coordinates
    (a length-less tree) forms no cell and is excluded from the pairwise
    distance sample, exactly as the calibrator drops it.

    Args:
        entry: The catalog entry.

    Returns:
        tuple[str, str, str] | None: The cell tuple, or None when incomplete.
    """
    cell = cell_of_entry(entry)
    if cell is None:
        return None
    return (cell.band, cell.length, cell.style)


def _cells_by_key(catalog: Catalog) -> dict[tuple[str, str, str], list[CatalogEntry]]:
    """Group the production-eligible catalog entries by exact cell (calibrator rule)."""
    by_cell: dict[tuple[str, str, str], list[CatalogEntry]] = {}
    for entry in catalog.entries:
        if not entry.metadata.production_eligible:
            continue
        cell = _cell_key(entry)
        if cell is None:
            continue
        by_cell.setdefault(cell, []).append(entry)
    return by_cell


def _pairwise_by_cell(
    by_cell: dict[tuple[str, str, str], list[CatalogEntry]],
) -> dict[tuple[str, str, str], list[tuple[float, str, str]]]:
    """Compute every in-cell pairwise ``structural_distance`` once, keyed by cell.

    ``structural_distance`` is the expensive call (graph-edit distance over the
    full document); both the distinct-trees table (min/median) and the hygiene
    table (nearest pair) derive from these same pairs, so they are computed once
    here and shared rather than recomputed per table.
    """
    return {
        cell: [
            (
                structural_distance(entries[i].document, entries[j].document),
                entries[i].slug,
                entries[j].slug,
            )
            for i in range(len(entries))
            for j in range(i + 1, len(entries))
        ]
        for cell, entries in by_cell.items()
    }


def _fmt_cell(cell: tuple[str, str, str]) -> str:
    """Return a stable ``band=.. length=.. style=..`` cell label."""
    return f"band={cell[0]} length={cell[1]} style={cell[2]}"


def _render_distinct_trees_table(
    by_cell: dict[tuple[str, str, str], list[CatalogEntry]],
    pairwise: dict[tuple[str, str, str], list[tuple[float, str, str]]],
) -> list[str]:
    """Render the distinct-trees-per-cell table (design 9 trend, table 2)."""
    lines = [
        "## 2. Distinct trees per cell (trend)",
        "",
        (
            "Per cell: the production-eligible tree count and the in-cell pairwise "
            "`structural_distance` distribution (min/median), the same numbers the "
            "floor calibrator computes. A rising count with a collapsing minimum "
            "distance is the flywheel gaming its own metric (CR-5), so both are "
            "shown together."
        ),
        "",
    ]
    if not by_cell:
        lines.append(
            "_No production-eligible cells with complete coordinates in the "
            "catalog. Empty is honest._"
        )
        lines.append("")
        return lines
    lines.extend(
        [
            "| Cell | Trees | Min distance | Median distance |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for cell in sorted(by_cell):
        entries = by_cell[cell]
        distances = [distance for distance, _, _ in pairwise[cell]]
        if distances:
            min_str = f"{min(distances):.6f}"
            median_str = f"{statistics.median(distances):.6f}"
        else:
            min_str = "n/a"
            median_str = "n/a"
        lines.append(
            f"| {_fmt_cell(cell)} | {len(entries)} | {min_str} | {median_str} |"
        )
    lines.append("")
    return lines


def _render_effective_catalog_size(catalog: Catalog) -> list[str]:
    """Render the effective-catalog-size line (design 9, table 3)."""
    production = [
        entry for entry in catalog.entries if entry.metadata.production_eligible
    ]
    ecs = effective_catalog_size(production, key=lambda entry: entry.slug)
    return [
        "## 3. Effective catalog size",
        "",
        (
            "`effective_catalog_size` (exponentiated Shannon entropy) over the "
            "production catalog, one instance per tree keyed by slug. A "
            "usage-weighted served-window ECS needs the reading-events database "
            "and is not computed by this read-only file report."
        ),
        "",
        f"- Production trees: {len(production)}",
        f"- Catalog effective size (uniform, one per tree): {ecs:.6f}",
        "",
    ]


# --- Table 4: promotion funnel -------------------------------------------------


def _latest_outcome_per_sig(records: Sequence[AttemptRecord]) -> dict[str, str]:
    """Return the latest outcome per signature (last-write-wins, ledger order)."""
    latest: dict[str, str] = {}
    for record in records:
        latest[record.attempt_sig] = record.outcome
    return latest


def _discards_by_stage(records: Sequence[AttemptRecord]) -> dict[str, int]:
    """Return the count of discarded attempts grouped by failing acceptance stage."""
    by_stage: dict[str, int] = {}
    for record in records:
        if record.outcome != OUTCOME_DISCARDED:
            continue
        stage = record.failing_stage or "(unspecified)"
        by_stage[stage] = by_stage.get(stage, 0) + 1
    return by_stage


def _render_funnel_table(records: Sequence[AttemptRecord]) -> list[str]:
    """Render the promotion-funnel table from the ledger (design 9, table 4)."""
    lines = [
        "## 4. Promotion funnel",
        "",
        (
            "Per-outcome attempt counts from the ledger "
            "(`out/mutations/_ledger/attempts.jsonl`), latest outcome per attempt "
            "signature. PR opened / merged / closed-without-merge come from "
            "git/GitHub and are NOT derivable from the ledger; they are omitted "
            "here rather than guessed."
        ),
        "",
    ]
    if not records:
        lines.append(
            "_The ledger is empty or absent (a fresh system before the first "
            "flywheel cycle, or a fresh checkout that lost the gitignored scratch "
            "file). Empty is honest._"
        )
        lines.append("")
        return lines
    latest = _latest_outcome_per_sig(records)
    counts = {
        OUTCOME_PROMOTABLE: 0,
        OUTCOME_HELD: 0,
        OUTCOME_SHELVED: 0,
        OUTCOME_DISCARDED: 0,
    }
    for outcome in latest.values():
        if outcome in counts:
            counts[outcome] += 1
    lines.extend(
        [
            "| Stage | Count |",
            "| --- | ---: |",
            f"| Distinct attempts | {len(latest)} |",
            f"| Promotable | {counts[OUTCOME_PROMOTABLE]} |",
            f"| Held (unresolved re-guidance) | {counts[OUTCOME_HELD]} |",
            f"| Shelved (survivor, not selected) | {counts[OUTCOME_SHELVED]} |",
            f"| Discarded | {counts[OUTCOME_DISCARDED]} |",
        ]
    )
    discards = _discards_by_stage(records)
    lines.extend(
        f"| Discarded at stage `{stage}` | {discards[stage]} |"
        for stage in sorted(discards)
    )
    lines.append("")
    return lines


def _render_reguide_cost_table(records: Sequence[AttemptRecord]) -> list[str]:
    """Render the re-guidance-cost table (design 9, table 5)."""
    latest = _latest_outcome_per_sig(records)
    held = sum(1 for outcome in latest.values() if outcome == OUTCOME_HELD)
    promotable = sum(1 for outcome in latest.values() if outcome == OUTCOME_PROMOTABLE)
    return [
        "## 5. Re-guidance cost",
        "",
        (
            "Items per bundled candidate, the agent-draft floor-pass rate, and the "
            "human edit rate at review require merged promotion bundles and PR "
            "diffs, which are absent before the first promotion; those parts are "
            "noted, not fabricated. The ledger-derivable proxy is the held (needing "
            "re-guidance) vs promotable split."
        ),
        "",
        f"- Held candidates (needing re-guidance): {held}",
        f"- Promotable candidates: {promotable}",
        (
            "- Items per bundled candidate / floor-pass rate / human edit rate: "
            "not derivable (no merged promotion bundles or PRs yet)."
        ),
        "",
    ]


def _render_demand_response_table(*, demand_available: bool) -> list[str]:
    """Render the demand-response table (design 9, table 6, DB-OPTIONAL)."""
    lines = [
        "## 6. Demand response",
        "",
        (
            "Per triggered cell, the CATALOG-event rate before vs after a merge, "
            "from `CELL_SATURATED` events. This is DB-optional: it needs the "
            "pipeline-events database (read-only, mirroring `flywheel_scan.py`)."
        ),
        "",
    ]
    if not demand_available:
        lines.append(
            "_No pipeline-events database supplied to this run, so the "
            "demand-response table is empty. Empty is honest; run the DB-backed "
            "scan for this table._"
        )
        lines.append("")
        return lines
    lines.append(
        "_A pipeline-events source was supplied but no triggered cell has a "
        "pre/post-merge window yet (no merges to bracket). Empty is honest._"
    )
    lines.append("")
    return lines


def _render_hygiene_table(
    pairwise: dict[tuple[str, str, str], list[tuple[float, str, str]]],
) -> list[str]:
    """Render the catalog-hygiene table (design 6.5, table 7)."""
    lines = [
        "## 7. Catalog hygiene (in-cell minimum pairwise distance)",
        "",
        (
            "The standing minimum pairwise `structural_distance` within each cell "
            "over the WHOLE catalog (design 6.5). Any near-duplicate pair (the "
            "known clamp lesson is a ~0.0009 hand-authored pair) is surfaced every "
            "cycle so erosion is visible; automation reports, the owner decides. No "
            "automated deletion, ever."
        ),
        "",
    ]
    rows: list[tuple[float, tuple[str, str, str], str, str]] = []
    for cell, pairs in pairwise.items():
        if not pairs:
            continue
        distance, slug_a, slug_b = min(
            pairs, key=lambda pair: (pair[0], pair[1], pair[2])
        )
        rows.append((distance, cell, slug_a, slug_b))
    if not rows:
        lines.append(
            "_No cell has two or more trees, so no in-cell pair exists yet. Empty "
            "is honest._"
        )
        lines.append("")
        return lines
    lines.extend(
        [
            "| Cell | Min pair distance | Nearest pair |",
            "| --- | ---: | --- |",
        ]
    )
    for distance, cell, slug_a, slug_b in sorted(
        rows, key=lambda row: (row[0], row[1])
    ):
        lines.append(f"| {_fmt_cell(cell)} | {distance:.6f} | {slug_a} + {slug_b} |")
    global_min = min(rows, key=lambda row: (row[0], row[1]))
    lines.append("")
    lines.append(
        f"**Catalog-wide nearest in-cell pair:** {global_min[2]} + {global_min[3]} "
        f"at distance {global_min[0]:.6f} ({_fmt_cell(global_min[1])})."
    )
    lines.append("")
    return lines


def build_report(
    *,
    as_of_label: str,
    git_runner: GitRunner,
    records: Sequence[AttemptRecord],
    catalog: Catalog,
    demand_available: bool = False,
) -> str:
    """Assemble the full flywheel markdown report from injected inputs (design 9).

    Pure over its arguments: no wall-clock, no I/O of its own beyond what the
    injected ``git_runner`` reads, so the same inputs render byte-identical
    markdown (the D7 determinism property). The ``as_of_label`` is the only date
    in the document and it is caller-supplied, never derived from the clock.

    Args:
        as_of_label: The report's as-of label (an injected date/label string).
        git_runner: The read-only git runner (for the net-new-trees history).
        records: The parsed ledger records (may be empty).
        catalog: The scanned catalog (may be empty).
        demand_available: Whether a pipeline-events source was supplied for the
            demand-response table (defaults to False -> that table is empty).

    Returns:
        str: The full markdown report, ending in a newline.
    """
    additions, lineage_slugs = parse_tree_additions(
        _log_added_skeleton_files(git_runner)
    )
    by_cell = _cells_by_key(catalog)
    pairwise = _pairwise_by_cell(by_cell)
    lines = [
        "# CYO Adventure catalog-flywheel report",
        "",
        f"As of: {as_of_label}",
        "",
        (
            "Read-only trend report (WS-8 design section 9). Every table is "
            'trend-only and NEVER gates CI (the WS-0 "never" list applies). An '
            "empty table is a valid, honest result on a fresh system, not an error."
        ),
        "",
    ]
    lines.extend(_render_net_new_table(additions, lineage_slugs))
    lines.extend(_render_distinct_trees_table(by_cell, pairwise))
    lines.extend(_render_effective_catalog_size(catalog))
    lines.extend(_render_funnel_table(records))
    lines.extend(_render_reguide_cost_table(records))
    lines.extend(_render_demand_response_table(demand_available=demand_available))
    lines.extend(_render_hygiene_table(pairwise))
    return "\n".join(lines).rstrip("\n") + "\n"


def _default_out_path(as_of_label: str) -> Path:
    """Return the default report path for an as-of label under the report home."""
    safe_label = "".join(
        ch if ch.isalnum() or ch in "-_" else "-" for ch in as_of_label
    )
    return _REPORT_DIR / f"flywheel-report-{safe_label}.md"


def _build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--as-of",
        required=True,
        help=(
            "The report's as-of label (e.g. 2026-07-21). Determinism relies on "
            "this being supplied, not derived from the wall clock."
        ),
    )
    _ = parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Output markdown path. Defaults to "
            "docs/planning/flywheel-reports/flywheel-report-<label>.md."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Assemble the flywheel report and write it to disk.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        int: ``0`` on a written report, ``2`` on an argparse usage error.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    as_of_label = str(args.as_of)
    out_arg = args.out
    # ASSUME: security: --out is canonicalized with .resolve() (CWE-23
    # hardening, Snyk python/PT), but deliberately NOT contained to a fixed
    # base (the generation/import_cli.py::_load_blob idiom):
    # tests/unit/test_flywheel_report.py::test_main_writes_only_the_out_file
    # exercises --out against a pytest tmp_path fixture well outside the
    # repo tree with no chdir, proving arbitrary-location paths are
    # legitimate, exercised behavior that containment would reject. No
    # privilege boundary is crossed either way: the operator (or scheduled
    # job) invoking this dev-only reporter already has full filesystem
    # access, per the path-traversal verification report
    # (scratchpad/pt-verification-report.md).
    # VERIFY: any future change adding a fixed base must re-run
    # test_flywheel_report.py first; a rejection there means real behavior
    # broke.
    out_path = (
        Path(out_arg).resolve()
        if isinstance(out_arg, Path)
        else _default_out_path(as_of_label)
    )

    records = load_records(ledger_path(_REPO_ROOT))
    catalog = load_catalog(_REPO_ROOT)
    report = build_report(
        as_of_label=as_of_label,
        git_runner=default_git_runner(_REPO_ROOT),
        records=records,
        catalog=catalog,
    )

    # The ONLY write this read-only report performs: its own output file.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _ = out_path.write_text(report, encoding="utf-8")
    sys.stdout.write(f"{out_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
