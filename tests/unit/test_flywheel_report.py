"""Unit tests for the WS-8 flywheel metrics report (design section 9, D7).

The report is READ-ONLY: it reads git history (an injected runner here), the
ledger, and the catalog, and renders one markdown document. These tests pin its
determinism, the lineage-vs-hand-authored attribution split, graceful empty
degradation, and the read-only property.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.flywheel.ledger import (
    OUTCOME_DISCARDED,
    OUTCOME_HELD,
    OUTCOME_PROMOTABLE,
    OUTCOME_SHELVED,
    ledger_path,
    load_records,
)
from cyo_adventure.flywheel.strategy import Catalog, load_catalog

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.flywheel.ledger import AttemptRecord

# Import the report script by path (scripts/ is not an importable package).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "flywheel_report.py"
_SPEC = importlib.util.spec_from_file_location("flywheel_report", _SCRIPT_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
flywheel_report = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(flywheel_report)

_MARKER = "\x1f"


def _fixture_git_log() -> str:
    """Return a canned ``git log`` add-history: one flywheel tree, one hand-authored.

    ``fw-alpha`` lands with a ``*.lineage.json`` sidecar in 2026-07 (flywheel);
    ``hand-tree`` lands with no sidecar in 2026-06 (hand-authored); a
    ``*.contract.json`` addition is present and must be ignored (D6 note).
    """
    return (
        f"{_MARKER}2026-07-10\n"
        "skeletons/3-5/fw-alpha.json\n"
        "skeletons/3-5/fw-alpha.lineage.json\n"
        "skeletons/3-5/fw-alpha.contract.json\n"
        "\n"
        f"{_MARKER}2026-06-05\n"
        "skeletons/3-5/hand-tree.json\n"
    )


def _empty_git_log(_argv: Sequence[str]) -> str:
    """A git runner with no history (fresh system)."""
    return ""


def _canned_git_runner(output: str) -> object:
    """Return a git runner ignoring its argv and returning ``output``."""

    def _run(_argv: Sequence[str]) -> str:
        return output

    return _run


def _fixture_catalog(tmp_path: Path) -> Catalog:
    """Return a two-tree fixture catalog in one cell (copies of a real skeleton).

    Two copies of a real 3-5 skeleton share a cell, so tables 2 and 7 have an
    in-cell pair (min distance 0.0 for identical structure), exercising the
    non-empty catalog paths without depending on the live catalog's contents.
    """
    source = _REPO_ROOT / "skeletons" / "3-5" / "the-sleepy-little-star.json"
    document = source.read_text(encoding="utf-8")
    band_dir = tmp_path / "skeletons" / "3-5"
    band_dir.mkdir(parents=True)
    for slug in ("rep-alpha", "rep-beta"):
        _ = (band_dir / f"{slug}.json").write_text(document, encoding="utf-8")
    return load_catalog(tmp_path)


def _fixture_records(tmp_path: Path) -> list[AttemptRecord]:
    """Write a fixture ledger JSONL and return its parsed records."""
    path = ledger_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cell = {"band": "3-5", "length": "short", "style": "prose"}
    rows = [
        {
            "attempt_sig": "sig-promotable",
            "parent_slug": "p",
            "parent_sha256": "h",
            "cell": cell,
            "chain": [],
            "outcome": OUTCOME_PROMOTABLE,
            "failing_stage": None,
            "discard_reason": "",
            "distances": {"parent_distance": 0.3, "min_in_cell_distance": 0.4},
            "timestamp": "2026-07-20T00:00:00+00:00",
        },
        {
            "attempt_sig": "sig-held",
            "parent_slug": "p",
            "parent_sha256": "h",
            "cell": cell,
            "chain": [],
            "outcome": OUTCOME_HELD,
            "failing_stage": None,
            "discard_reason": "",
            "distances": {},
            "timestamp": "2026-07-20T00:00:01+00:00",
        },
        {
            "attempt_sig": "sig-shelved",
            "parent_slug": "p",
            "parent_sha256": "h",
            "cell": cell,
            "chain": [],
            "outcome": OUTCOME_SHELVED,
            "failing_stage": None,
            "discard_reason": "",
            "distances": {},
            "timestamp": "2026-07-20T00:00:02+00:00",
        },
        {
            "attempt_sig": "sig-discarded",
            "parent_slug": "p",
            "parent_sha256": "h",
            "cell": cell,
            "chain": [],
            "outcome": OUTCOME_DISCARDED,
            "failing_stage": "stage-2-cell-assertion",
            "discard_reason": "cell mismatch",
            "distances": {},
            "timestamp": "2026-07-20T00:00:03+00:00",
        },
    ]
    _ = path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return load_records(path)


# --- Determinism (D7 test) ----------------------------------------------------


def test_report_is_byte_identical_across_two_runs(tmp_path: Path) -> None:
    """The same fixture git/ledger/catalog renders byte-identical markdown twice."""
    catalog = _fixture_catalog(tmp_path)
    records = _fixture_records(tmp_path)
    git_runner = _canned_git_runner(_fixture_git_log())
    first = flywheel_report.build_report(
        as_of_label="2026-07-21",
        git_runner=git_runner,
        records=records,
        catalog=catalog,
    )
    second = flywheel_report.build_report(
        as_of_label="2026-07-21",
        git_runner=git_runner,
        records=records,
        catalog=catalog,
    )
    assert first == second
    assert first.endswith("\n")
    assert first.startswith("# CYO Adventure catalog-flywheel report")


def test_report_carries_the_injected_label_not_a_clock(tmp_path: Path) -> None:
    """The as-of label is the caller's, so no wall-clock leaks into the output."""
    catalog = _fixture_catalog(tmp_path)
    report = flywheel_report.build_report(
        as_of_label="MY-LABEL-XYZ",
        git_runner=_canned_git_runner(""),
        records=[],
        catalog=catalog,
    )
    assert "As of: MY-LABEL-XYZ" in report


# --- Lineage vs hand-authored attribution split (D7 test) ---------------------


def test_net_new_split_counts_lineage_and_hand_authored_separately(
    tmp_path: Path,
) -> None:
    """A tree with a lineage sidecar is flywheel; one without is hand-authored."""
    report = flywheel_report.build_report(
        as_of_label="2026-07-21",
        git_runner=_canned_git_runner(_fixture_git_log()),
        records=[],
        catalog=Catalog(entries=()),
    )
    # 2026-07: fw-alpha (has lineage) -> flywheel 1, hand 0.
    assert "| 2026-07 | 1 | 0 | 1 |" in report
    # 2026-06: hand-tree (no lineage) -> flywheel 0, hand 1.
    assert "| 2026-06 | 0 | 1 | 1 |" in report
    # Totals: 1 flywheel, 1 hand-authored.
    assert "| **Total** | **1** | **1** | **2** |" in report


def test_parse_tree_additions_ignores_contract_only_additions() -> None:
    """A ``*.contract.json`` addition is not a net-new tree (D6 parameterization)."""
    log_output = f"{_MARKER}2026-07-01\nskeletons/8-11/param-tree.contract.json\n"
    additions, lineage_slugs = flywheel_report.parse_tree_additions(log_output)
    assert additions == []
    assert lineage_slugs == set()


def test_parse_tree_additions_marks_lineage_backed_slugs() -> None:
    """A tree whose slug has a lineage sidecar addition is flywheel-attributed."""
    additions, lineage_slugs = flywheel_report.parse_tree_additions(_fixture_git_log())
    slugs = {addition.slug for addition in additions}
    assert slugs == {"fw-alpha", "hand-tree"}
    assert lineage_slugs == {"fw-alpha"}


# --- Graceful empty (D7 test) -------------------------------------------------


def test_empty_ledger_and_no_events_still_render_a_valid_report(
    tmp_path: Path,
) -> None:
    """Empty funnel/demand tables are honest notes; catalog tables stay non-empty."""
    catalog = _fixture_catalog(tmp_path)
    report = flywheel_report.build_report(
        as_of_label="2026-07-21",
        git_runner=_empty_git_log,
        records=[],
        catalog=catalog,
        demand_available=False,
    )
    # Valid document.
    assert report.startswith("# CYO Adventure catalog-flywheel report")
    # Funnel + demand are empty with an explicit honest note.
    funnel = report.split("## 4. Promotion funnel", 1)[1].split("## 5.", 1)[0]
    assert "Empty is honest" in funnel
    demand = report.split("## 6. Demand response", 1)[1].split("## 7.", 1)[0]
    assert "Empty is honest" in demand
    # Net-new has no git history -> its own fresh-system note.
    net_new = report.split("## 1.", 1)[1].split("## 2.", 1)[0]
    assert "fresh system before the first promotion" in net_new
    # Catalog-derived tables (2 and 7) are non-empty: the fixture cell has a pair.
    distinct = report.split("## 2.", 1)[1].split("## 3.", 1)[0]
    assert "band=3-5" in distinct
    hygiene = report.split("## 7.", 1)[1]
    assert "band=3-5" in hygiene
    assert "rep-alpha" in hygiene


def test_funnel_reflects_ledger_outcomes(tmp_path: Path) -> None:
    """The funnel counts each ledger outcome and the discard's failing stage."""
    records = _fixture_records(tmp_path)
    report = flywheel_report.build_report(
        as_of_label="2026-07-21",
        git_runner=_canned_git_runner(""),
        records=records,
        catalog=Catalog(entries=()),
    )
    funnel = report.split("## 4. Promotion funnel", 1)[1].split("## 5.", 1)[0]
    assert "| Distinct attempts | 4 |" in funnel
    assert "| Promotable | 1 |" in funnel
    assert "| Held (unresolved re-guidance) | 1 |" in funnel
    assert "| Shelved (survivor, not selected) | 1 |" in funnel
    assert "| Discarded | 1 |" in funnel
    assert "| Discarded at stage `stage-2-cell-assertion` | 1 |" in funnel


# --- Read-only pin (D7 test) --------------------------------------------------


def test_git_runner_refuses_a_non_read_only_subcommand() -> None:
    """The default runner rejects any git subcommand but ``log`` (read-only pin)."""
    runner = flywheel_report.default_git_runner(_REPO_ROOT)
    for mutating in (["commit"], ["push"], ["add", "."], ["checkout", "main"]):
        with pytest.raises(ValueError, match="non-read-only git subcommand"):
            _ = runner(mutating)


def test_allowed_git_subcommands_is_only_log() -> None:
    """The read-only allowlist is exactly ``{'log'}``."""
    allowlist = flywheel_report._ALLOWED_GIT_SUBCOMMANDS
    assert allowlist == {"log"}


def test_source_issues_no_mutating_git_command() -> None:
    """The report source never issues a writing git subcommand as a string literal."""
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in ('"commit"', '"push"', '"add"', '"worktree"', '"checkout"'):
        assert forbidden not in source


def test_build_report_writes_no_file(tmp_path: Path) -> None:
    """Assembling the report writes nothing; only ``main`` writes the --out file."""
    before = set(tmp_path.rglob("*"))
    _ = flywheel_report.build_report(
        as_of_label="2026-07-21",
        git_runner=_canned_git_runner(""),
        records=[],
        catalog=Catalog(entries=()),
    )
    assert set(tmp_path.rglob("*")) == before


def test_main_writes_only_the_out_file(tmp_path: Path) -> None:
    """``main`` writes exactly its --out file and prints the path (read-only else)."""
    out_path = tmp_path / "report.md"
    exit_code = flywheel_report.main(["--as-of", "test-label", "--out", str(out_path)])
    assert exit_code == 0
    assert out_path.is_file()
    assert out_path.read_text(encoding="utf-8").startswith(
        "# CYO Adventure catalog-flywheel report"
    )
    # No stray report left under the committed report home for this label.
    stray = (
        _REPO_ROOT
        / "docs"
        / "planning"
        / "flywheel-reports"
        / ("flywheel-report-test-label.md")
    )
    assert not stray.is_file()
