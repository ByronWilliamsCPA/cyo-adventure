"""Unit tests for scripts/measure_sentinel_survival.py (plan 3.4 CLI runner).

Exercises the callable core (`main(argv)`) directly, never a subprocess, per
this repo's `scripts/mutate_skeleton.py` precedent. Covers: a full
`--providers mock` dry run over a handful of specimens (the plumbing proof,
end to end), the out-dir-under-skeletons/ refusal, and malformed-argument
handling. Never invokes a live, paid provider.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts.measure_sentinel_survival import (
    _select_fixture_pairs,  # pyright: ignore[reportPrivateUsage]
    main,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.unit
def test_mock_dry_run_writes_a_labeled_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A --providers mock run writes report.json/report.md, banner included."""
    out_dir = tmp_path / "results"
    exit_code = main(
        [
            "--providers",
            "mock",
            "--out-dir",
            str(out_dir),
            "--skeletons",
            "3-5:puddle-jumping-day",
            "--skeletons",
            "5-8:the-night-market",
            "--count",
            "3",
        ]
    )
    assert exit_code == 0

    run_dirs = list(out_dir.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    report_json = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report_json["dry_run"] is True
    assert report_json["dry_run_banner"] == "PLUMBING DRY-RUN, not a survival number."
    assert report_json["total_runs"] == 3

    report_md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "PLUMBING DRY-RUN, not a survival number." in report_md

    captured = capsys.readouterr()
    assert "sentinel-survival:" in captured.out


@pytest.mark.unit
def test_refuses_out_dir_under_skeletons(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--out-dir resolving under skeletons/ is refused, never written to."""
    out_dir = tmp_path / "skeletons" / "scratch"
    exit_code = main(
        [
            "--providers",
            "mock",
            "--out-dir",
            str(out_dir),
            "--count",
            "1",
        ]
    )
    assert exit_code == 1
    assert not out_dir.exists()
    captured = capsys.readouterr()
    assert "refusing" in captured.err


@pytest.mark.unit
def test_malformed_skeletons_argument_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A --skeletons entry missing the BAND:SLUG colon errors cleanly."""
    exit_code = main(
        [
            "--providers",
            "mock",
            "--out-dir",
            str(tmp_path / "results"),
            "--skeletons",
            "not-a-valid-entry",
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "BAND:SLUG" in captured.err


@pytest.mark.unit
def test_select_fixture_pairs_band_filter() -> None:
    """--band restricts the default fixture set to matching bands only."""
    pairs = _select_fixture_pairs(None, ["3-5", "8-11"])
    assert pairs
    assert all(band in {"3-5", "8-11"} for band, _ in pairs)


@pytest.mark.unit
def test_select_fixture_pairs_explicit_skeletons_override_band() -> None:
    """An explicit --skeletons list overrides the default fixture set entirely."""
    pairs = _select_fixture_pairs(["10-13:the-midnight-museum"], ["3-5"])
    assert pairs == [("10-13", "the-midnight-museum")]
