"""Unit tests for scripts/moderation_qa_scorecard.py's pure comparison logic.

scripts/ is not an importable package (no __init__.py, by design; see the
INP per-file-ignore for scripts/**/*.py in pyproject.toml), so the module is
loaded directly from its file path via importlib, mirroring
tests/unit/test_seed_staging.py and tests/unit/test_seed_moderation_qa.py.

Only compare_book / story_verdict_from_report / node_verdict_from_report /
meets_floor / render_table are exercised here: these are pure functions over
in-memory report dicts, so no database is required.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "moderation_qa_scorecard",
    Path(__file__).resolve().parents[2] / "scripts" / "moderation_qa_scorecard.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
scorecard = importlib.util.module_from_spec(_SPEC)
# scripts/moderation_qa_scorecard.py declares a @dataclass; on 3.14, dataclass
# processing looks the defining module up via sys.modules[cls.__module__] (for
# ClassVar/InitVar detection), which is only populated for modules imported
# the normal way. A dynamically loaded module needs this registration done
# manually before exec_module runs the class body, or the dataclass decorator
# raises AttributeError on a None module lookup.
sys.modules[_SPEC.name] = scorecard
_SPEC.loader.exec_module(scorecard)

pytestmark = pytest.mark.unit


def _report(*findings: dict[str, object]) -> dict[str, object]:
    return {"findings": list(findings), "summary": {"count": len(findings)}}


def _finding(verdict: str, node_id: str | None = None) -> dict[str, object]:
    return {
        "stage": "stage1",
        "source": "classifier",
        "category": "test",
        "node_id": node_id,
        "verdict": verdict,
        "score": 1.0,
        "message": "test finding",
    }


# ---------------------------------------------------------------------------
# verdict_rank / meets_floor
# ---------------------------------------------------------------------------


def test_verdict_rank_orders_pass_below_block() -> None:
    assert scorecard.verdict_rank("pass") < scorecard.verdict_rank("block")
    assert scorecard.verdict_rank("advisory") < scorecard.verdict_rank("flag")


def test_meets_floor_true_when_actual_at_least_as_severe() -> None:
    assert scorecard.meets_floor("block", "flag") is True
    assert scorecard.meets_floor("flag", "flag") is True


def test_meets_floor_false_when_actual_less_severe() -> None:
    assert scorecard.meets_floor("pass", "flag") is False


# ---------------------------------------------------------------------------
# story_verdict_from_report / node_verdict_from_report
# ---------------------------------------------------------------------------


def test_story_verdict_from_report_is_pass_when_no_findings() -> None:
    assert scorecard.story_verdict_from_report(_report()) == "pass"


def test_story_verdict_from_report_takes_the_most_severe_finding() -> None:
    report = _report(_finding("advisory"), _finding("block"), _finding("flag"))
    assert scorecard.story_verdict_from_report(report) == "block"


def test_node_verdict_from_report_only_considers_matching_node() -> None:
    report = _report(
        _finding("block", node_id="n_other"), _finding("flag", node_id="n_x")
    )
    assert scorecard.node_verdict_from_report(report, "n_x") == "flag"


def test_node_verdict_from_report_is_pass_when_node_has_no_findings() -> None:
    report = _report(_finding("block", node_id="n_other"))
    assert scorecard.node_verdict_from_report(report, "n_x") == "pass"


# ---------------------------------------------------------------------------
# compare_book
# ---------------------------------------------------------------------------


def test_compare_book_reports_missing_when_report_is_none() -> None:
    entry = {
        "id": "mqa_a",
        "expected_min_verdict": "pass",
        "negative_control": True,
        "node_labels": [],
    }
    rows = scorecard.compare_book(entry, None)
    assert len(rows) == 1
    assert rows[0].status == scorecard._STATUS_MISSING
    assert rows[0].book_id == "mqa_a"


def test_compare_book_negative_control_passes_only_on_exact_pass() -> None:
    entry = {
        "id": "mqa_clean",
        "expected_min_verdict": "pass",
        "negative_control": True,
        "node_labels": [],
    }
    clean_report = _report()
    rows = scorecard.compare_book(entry, clean_report)
    assert rows[0].status == scorecard._STATUS_OK

    over_flagged_report = _report(_finding("flag"))
    rows = scorecard.compare_book(entry, over_flagged_report)
    assert rows[0].status == scorecard._STATUS_FAIL


def test_compare_book_floor_passes_when_actual_exceeds_expected() -> None:
    entry = {
        "id": "mqa_block",
        "expected_min_verdict": "flag",
        "negative_control": False,
        "node_labels": [],
    }
    report = _report(_finding("block"))
    rows = scorecard.compare_book(entry, report)
    assert rows[0].status == scorecard._STATUS_OK
    assert rows[0].actual == "block"


def test_compare_book_floor_fails_when_actual_falls_short() -> None:
    entry = {
        "id": "mqa_block",
        "expected_min_verdict": "block",
        "negative_control": False,
        "node_labels": [],
    }
    report = _report(_finding("flag"))
    rows = scorecard.compare_book(entry, report)
    assert rows[0].status == scorecard._STATUS_FAIL


def test_compare_book_checks_every_node_label() -> None:
    entry = {
        "id": "mqa_storm",
        "expected_min_verdict": "flag",
        "negative_control": False,
        "node_labels": [
            {"node_id": "n_turn", "expected_min_verdict": "flag"},
            {"node_id": "n_calm", "expected_min_verdict": "pass"},
        ],
    }
    report = _report(_finding("flag", node_id="n_turn"))
    rows = scorecard.compare_book(entry, report)

    assert len(rows) == 3
    story_row, turn_row, calm_row = rows
    assert story_row.level == "story"
    assert turn_row.level == "n_turn"
    assert turn_row.status == scorecard._STATUS_OK
    assert calm_row.level == "n_calm"
    assert calm_row.status == scorecard._STATUS_OK


def test_compare_book_flags_a_node_that_should_have_been_caught_but_was_not() -> None:
    entry = {
        "id": "mqa_block",
        "expected_min_verdict": "block",
        "negative_control": False,
        "node_labels": [{"node_id": "n_home", "expected_min_verdict": "block"}],
    }
    report = _report()  # a clean report: the pipeline missed the block case
    rows = scorecard.compare_book(entry, report)

    node_row = next(row for row in rows if row.level == "n_home")
    assert node_row.status == scorecard._STATUS_FAIL
    assert node_row.actual == "pass"


# ---------------------------------------------------------------------------
# render_table
# ---------------------------------------------------------------------------


def test_render_table_includes_summary_count() -> None:
    rows = [
        scorecard.ScorecardRow(
            book_id="mqa_a",
            level="story",
            expected="pass",
            actual="pass",
            negative_control=True,
            status="PASS",
        ),
        scorecard.ScorecardRow(
            book_id="mqa_b",
            level="story",
            expected="block",
            actual="flag",
            negative_control=False,
            status="FAIL",
        ),
    ]
    table = scorecard.render_table(rows)
    assert "mqa_a" in table
    assert "mqa_b" in table
    assert "2 row(s), 1 failed/missing" in table


def test_render_table_marks_negative_control_expected_value() -> None:
    rows = [
        scorecard.ScorecardRow(
            book_id="mqa_a",
            level="story",
            expected="pass",
            actual="pass",
            negative_control=True,
            status="PASS",
        )
    ]
    table = scorecard.render_table(rows)
    assert "(neg)" in table


# ---------------------------------------------------------------------------
# The real manifest, end to end through the pure comparison logic
# ---------------------------------------------------------------------------


def test_compare_book_against_the_real_manifest_bright_line_case() -> None:
    """A regression sanity check: a clean report on the bright-line book fails.

    Uses the real manifest entry (not a synthetic one) so a manifest edit
    that quietly weakens the bright-line expectation is caught here too.
    """
    books = scorecard.load_manifest()
    entry = next(book for book in books if book["id"] == "mqa_block_selfharm_reference")
    rows = scorecard.compare_book(entry, _report())
    assert any(row.status == scorecard._STATUS_FAIL for row in rows)
