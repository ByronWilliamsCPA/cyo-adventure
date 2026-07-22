"""Unit tests for the WS-8 scheduled cadence runner (design section 8, D8).

The runner wires S1 (event read) -> the cap gate -> S2-S5 (grow) -> S6 (draft PR)
behind injected providers, so a test drives the whole cycle from canned state with
NO real GitHub or database call. These tests pin: the dry-run plan has no side
effect and reports capped cells with their bound; the conservative degrade when
open-PR state is unconfirmed opens nothing; and the run ENDS at a draft PR and
never merges/approves/auto-merges (a source grep plus a behavioral assertion with
an injected PR creator that the request is draft with the promotion label).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.flywheel.strategy import (  # noqa: E402
    cell_of_entry,
    load_catalog,
)
from cyo_adventure.flywheel.trigger import RawSaturationEvent  # noqa: E402
from cyo_adventure.mutation.bundle import (  # noqa: E402
    Lineage,
    OpChainEntry,
    content_sha256,
)
from scripts import flywheel_cycle as cyc  # noqa: E402
from scripts import prepare_promotion_pr as ppr  # noqa: E402

if TYPE_CHECKING:
    import pytest

    from cyo_adventure.flywheel.strategy import Catalog
    from cyo_adventure.flywheel.trigger import SaturationReading

_AS_OF = date(2026, 7, 21)


def _events() -> list[RawSaturationEvent]:
    """Return raw events that trigger exactly one cell (8-11/short/prose)."""
    return [
        RawSaturationEvent("8-11", "short", "prose", "catalog", "req-1"),
        RawSaturationEvent("8-11", "short", "prose", "catalog", "req-1"),
        RawSaturationEvent("8-11", "short", "prose", "catalog", "req-2"),
    ]


def _open_feed(confirmed: bool = True, *, global_count: int = 0) -> cyc.OpenPrFeed:
    return cyc.OpenPrFeed(
        cells=frozenset(), global_count=global_count, confirmed=confirmed
    )


def _no_history(_catalog: Catalog, _month: str) -> cyc.MergeHistory:
    return cyc.MergeHistory(last_merge_by_cell={}, month_merge_count=0)


class _RecordingCellRunner:
    """A cell runner that records calls and returns a fixed bundle dir (or None)."""

    def __init__(self, bundle_dir: Path | None) -> None:
        self.calls: list[SaturationReading] = []
        self._bundle_dir = bundle_dir

    def __call__(self, reading: SaturationReading) -> Path | None:
        self.calls.append(reading)
        return self._bundle_dir


class _RecordingPrCreator:
    """A PR creator that records requests; it has no merge/approve method at all."""

    def __init__(self) -> None:
        self.calls: list[ppr.PrRequest] = []

    def __call__(self, request: ppr.PrRequest, *, worktree_dir: Path) -> None:
        _ = worktree_dir
        self.calls.append(request)


class _FakeGitRunner:
    """A git seam that never touches git (reports a feature branch)."""

    def __init__(self, branch: str) -> None:
        self.branch = branch

    def current_branch(self) -> str:
        return self.branch

    def add_worktree(self, worktree_dir: Path, branch: str) -> None:  # pragma: no cover
        _ = (worktree_dir, branch)


def _run(
    *,
    dry_run: bool,
    open_pr_provider: cyc.OpenPrProvider,
    cell_runner: cyc.CellRunner,
    pr_preparer: cyc.PrPreparer,
    event_source: cyc.EventSource | None = None,
) -> list[str]:
    """Drive one cycle with canned providers and return the report lines."""
    return cyc.run_cycle(
        window_days=30,
        min_catalog_events=3,
        min_distinct_requests=2,
        as_of=_AS_OF,
        dry_run=dry_run,
        event_source=event_source
        if event_source is not None
        else (lambda _d: _events()),
        open_pr_provider=open_pr_provider,
        merge_history_provider=_no_history,
        cell_runner=cell_runner,
        pr_preparer=pr_preparer,
    )


def _fail_preparer(_bundle_dir: Path) -> int:  # pragma: no cover -- must not be called
    msg = "pr_preparer must not run in these cases"
    raise AssertionError(msg)


# --- dry run: no side effect, capped cells reported ---------------------------


def test_dry_run_reports_growable_cell_and_runs_no_side_effect() -> None:
    """The default dry run reports a would-prepare PR and calls no runner/preparer."""
    runner = _RecordingCellRunner(bundle_dir=None)
    lines = _run(
        dry_run=True,
        open_pr_provider=lambda _c: _open_feed(),
        cell_runner=runner,
        pr_preparer=_fail_preparer,
    )
    text = "\n".join(lines)
    assert "triggered cells: 1" in text
    assert "would prepare a DRAFT promotion PR" in text
    assert "band=8-11 length=short style=prose" in text
    assert runner.calls == []  # dry run touches no candidate machinery


def test_capped_cell_is_reported_with_its_bound_not_dropped() -> None:
    """A triggered cell blocked by the global cap is reported, never dropped."""
    runner = _RecordingCellRunner(bundle_dir=None)
    lines = _run(
        dry_run=True,
        open_pr_provider=lambda _c: _open_feed(global_count=3),
        cell_runner=runner,
        pr_preparer=_fail_preparer,
    )
    text = "\n".join(lines)
    assert "saturated but capped: open-pr-global" in text
    assert "Growable cells (0)" in text
    assert runner.calls == []


# --- conservative degrade ------------------------------------------------------


def test_unconfirmed_open_pr_state_opens_nothing_even_on_run() -> None:
    """An unconfirmed feed defers every cell and never invokes the cell runner."""
    runner = _RecordingCellRunner(bundle_dir=Path("/does/not/matter"))
    lines = _run(
        dry_run=False,
        open_pr_provider=lambda _c: _open_feed(confirmed=False),
        cell_runner=runner,
        pr_preparer=_fail_preparer,
    )
    text = "\n".join(lines)
    assert "could NOT be confirmed" in text
    assert "deferred: open-PR state unconfirmed" in text
    assert runner.calls == []  # nothing grown when capacity is unknown


# --- run ends at a draft PR ----------------------------------------------------


def _write_valid_bundle(
    bundle_dir: Path,
    skeletons_root: Path,
    *,
    band: str = "8-11",
    parent_slug: str = "p-parent",
    slug: str = "p-parent-fw-abc12345",
) -> None:
    """Write a promotable, resolved bundle whose parent verifies under skeletons_root."""
    parent_doc: dict[str, object] = {
        "id": parent_slug,
        "metadata": {"age_band": band},
        "nodes": [{"id": "n_start", "is_ending": True, "body": "x"}],
        "start_node": "n_start",
    }
    parent_dir = skeletons_root / band
    parent_dir.mkdir(parents=True, exist_ok=True)
    (parent_dir / f"{parent_slug}.json").write_text(
        json.dumps(parent_doc), encoding="utf-8"
    )
    bundle_dir.mkdir(parents=True, exist_ok=True)
    shell = {
        "id": slug,
        "metadata": {"age_band": band},
        "nodes": [{"id": "n_start", "is_ending": True, "body": "x"}],
        "start_node": "n_start",
    }
    (bundle_dir / f"{slug}.json").write_text(json.dumps(shell), encoding="utf-8")
    lineage = Lineage(
        lineage_version=1,
        mutant_slug=slug,
        parent_slug=parent_slug,
        parent_sha256=content_sha256(parent_doc),
        donor_slugs=[],
        op_chain=[OpChainEntry(op_id="M2")],
        created_at="2026-07-21T00:00:00+00:00",
        tool_version="test",
        acceptance_digest="abc123",
    )
    (bundle_dir / f"{slug}.lineage.json").write_text(
        lineage.model_dump_json(), encoding="utf-8"
    )
    (bundle_dir / "acceptance.json").write_text(
        json.dumps({"promotable": True, "stages": []}), encoding="utf-8"
    )
    (bundle_dir / "reguide.json").write_text(
        json.dumps({"fully_resolved": True, "items": []}), encoding="utf-8"
    )


def test_run_ends_at_a_draft_pr_with_the_promotion_label(tmp_path: Path) -> None:
    """A --run cycle prepares a DRAFT PR (label present) and never merges."""
    skeletons_root = tmp_path / "skeletons"
    bundle_dir = tmp_path / "bundle"
    _write_valid_bundle(bundle_dir, skeletons_root)

    recorder = _RecordingPrCreator()
    git = _FakeGitRunner("claude/ws8-planning")

    def prepare(bd: Path) -> int:
        return ppr.main(
            [str(bd), "--skeletons-root", str(skeletons_root)],
            git_runner=git,
            pr_creator=recorder,
        )

    lines = _run(
        dry_run=False,
        open_pr_provider=lambda _c: _open_feed(),
        cell_runner=_RecordingCellRunner(bundle_dir=bundle_dir),
        pr_preparer=prepare,
    )
    text = "\n".join(lines)
    assert "draft PR prepared" in text
    assert len(recorder.calls) == 1
    request = recorder.calls[0]
    assert request.draft is True
    assert ppr.PROMOTION_LABEL in request.labels
    # The recording creator has no merge/approve method: it structurally cannot.
    assert not hasattr(recorder, "merge")


def test_run_reports_no_pr_when_no_candidate_survives() -> None:
    """A growable cell whose candidate run yields no bundle prepares no PR."""
    lines = _run(
        dry_run=False,
        open_pr_provider=lambda _c: _open_feed(),
        cell_runner=_RecordingCellRunner(bundle_dir=None),
        pr_preparer=_fail_preparer,
    )
    assert "no candidate survived; no PR prepared" in "\n".join(lines)


# --- source-level automation-boundary pin -------------------------------------


def test_source_never_merges_approves_or_enables_auto_merge() -> None:
    """The runner source contains no merge/approve/auto-merge call (D4 boundary)."""
    source = (_REPO_ROOT / "scripts" / "flywheel_cycle.py").read_text(encoding="utf-8")
    for forbidden in (
        "gh pr merge",
        "pr_merge",
        "merge_pull_request",
        "enable_auto_merge",
        "enable_pr_auto_merge",
        "pr_auto_merge",
        "--merge",
        ".merge(",
        ".approve(",
    ):
        assert forbidden not in source, f"forbidden token in runner source: {forbidden}"


# --- _branch_cell edge cases ---------------------------------------------------


def test_branch_cell_non_promotion_branch_returns_none() -> None:
    """A branch outside the ``flywheel/promote-`` namespace maps to no cell."""
    catalog = load_catalog()
    assert cyc._branch_cell("feat/some-feature", catalog) is None


def test_branch_cell_unknown_parent_returns_none() -> None:
    """A promotion branch whose parent slug is not in the catalog maps to none.

    ``rsplit('-fw-', ...)`` on a slug with no ``-fw-`` marker yields the whole
    slug as the parent, which here does not resolve to any catalog entry.
    """
    catalog = load_catalog()
    assert cyc._branch_cell("flywheel/promote-no-such-parent", catalog) is None


def test_branch_cell_resolves_parent_cell() -> None:
    """A well-formed promotion branch resolves to its parent's cell."""
    catalog = load_catalog()
    parent = next(e for e in catalog.entries if cell_of_entry(e) is not None)
    branch = f"flywheel/promote-{parent.slug}-fw-deadbeef"
    assert cyc._branch_cell(branch, catalog) == cell_of_entry(parent)


def test_branch_cell_length_less_parent_returns_none() -> None:
    """A parent with no length coordinate forms no cell (calibrator rule)."""
    catalog = load_catalog()
    length_less = next((e for e in catalog.entries if cell_of_entry(e) is None), None)
    if length_less is None:
        return  # no length-less skeleton in the catalog; nothing to assert
    branch = f"flywheel/promote-{length_less.slug}-fw-deadbeef"
    assert cyc._branch_cell(branch, catalog) is None


# --- determinism ---------------------------------------------------------------


def test_dry_run_plan_is_deterministic() -> None:
    """The same inputs render the same plan (no wall-clock in the plan)."""
    runner = _RecordingCellRunner(bundle_dir=None)
    first = _run(
        dry_run=True,
        open_pr_provider=lambda _c: _open_feed(),
        cell_runner=runner,
        pr_preparer=_fail_preparer,
    )
    second = _run(
        dry_run=True,
        open_pr_provider=lambda _c: _open_feed(),
        cell_runner=runner,
        pr_preparer=_fail_preparer,
    )
    assert first == second


# --- CLI wiring ----------------------------------------------------------------


def test_main_dry_run_exits_zero_and_prints_plan(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() wires providers and prints the dry-run plan with exit code 0."""
    code = cyc.main(
        ["--as-of", "2026-07-21"],
        event_source=lambda _d: _events(),
        open_pr_provider=lambda _c: _open_feed(),
        merge_history_provider=_no_history,
        cell_runner=_RecordingCellRunner(bundle_dir=None),
        pr_preparer=_fail_preparer,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "scheduled flywheel cycle" in out
    assert "mode: DRY RUN" in out
