# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Unit tests for scripts/mutation_score.py (weekly mutation scoring)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts.mutation_score import (
    collect_counts,
    main,
    render_summary,
    score_from_counts,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_meta(
    mutants_dir: Path, name: str, exit_codes: dict[str, int | None]
) -> None:
    """Write a mutmut-style .meta file with the given exit codes."""
    meta = mutants_dir / "src" / "pkg" / f"{name}.py.meta"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({"exit_code_by_key": exit_codes}), encoding="utf-8")


@pytest.mark.unit
def test_collect_counts_aggregates_statuses_across_meta_files(
    tmp_path: Path,
) -> None:
    """Exit codes from every .meta file map onto mutmut's status buckets."""
    _write_meta(tmp_path, "a", {"m1": 1, "m2": 0, "m3": 33, "m4": 36})
    _write_meta(tmp_path, "b", {"m5": 3, "m6": None, "m7": -9, "m8": 99})
    counts = collect_counts(tmp_path)
    assert counts == {
        "killed": 2,
        "survived": 1,
        "no tests": 1,
        "timeout": 1,
        "not checked": 1,
        "segfault": 1,
        "suspicious": 1,
    }


@pytest.mark.unit
def test_collect_counts_without_meta_files_raises_file_not_found(
    tmp_path: Path,
) -> None:
    """A mutants dir with no results is an error, not a silent 0/0 score."""
    with pytest.raises(FileNotFoundError):
        collect_counts(tmp_path)


@pytest.mark.unit
def test_score_counts_timeout_as_detected_and_excludes_uncovered() -> None:
    """Timeouts count toward detection; uncovered mutants leave the base."""
    counts = {"killed": 6, "timeout": 2, "survived": 2, "no tests": 90}
    score, detected, checked = score_from_counts(counts)
    assert detected == 8
    assert checked == 10
    assert score == pytest.approx(80.0)


@pytest.mark.unit
def test_score_with_zero_checked_mutants_is_zero_not_division_error() -> None:
    """An all-uncovered run scores 0.0 instead of raising ZeroDivisionError."""
    score, detected, checked = score_from_counts({"no tests": 5})
    assert (score, detected, checked) == (0.0, 0, 0)


@pytest.mark.unit
def test_render_summary_contains_score_and_status_table() -> None:
    """The Markdown summary carries the headline score and each status row."""
    summary = render_summary({"killed": 3, "survived": 1})
    assert "**Mutation score: 75.0%** (3/4 checked mutants detected)" in summary
    assert "| killed | 3 |" in summary
    assert "| survived | 1 |" in summary


@pytest.mark.unit
def test_main_fail_under_gates_on_threshold(tmp_path: Path) -> None:
    """main returns 1 below --fail-under and 0 at or above it."""
    _write_meta(tmp_path, "a", {"m1": 1, "m2": 0})  # 50% score
    base = ["--mutants-dir", str(tmp_path)]
    assert main([*base, "--fail-under", "80"]) == 1
    assert main([*base, "--fail-under", "50"]) == 0
    assert main(base) == 0


@pytest.mark.unit
def test_main_with_missing_results_returns_distinct_exit_code(
    tmp_path: Path,
) -> None:
    """Scoring an empty mutants dir exits 2 so CI can tell it from a low score."""
    assert main(["--mutants-dir", str(tmp_path / "nope")]) == 2
