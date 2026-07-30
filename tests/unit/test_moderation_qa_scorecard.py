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
from unittest.mock import AsyncMock, patch

import pytest

from cyo_adventure.core.exceptions import ConfigurationError

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


def test_verdict_rank_degrades_on_unknown_verdict() -> None:
    """A future Verdict member must not crash the scorecard with a KeyError."""
    assert scorecard.verdict_rank("quarantine") == scorecard._UNKNOWN_VERDICT_RANK
    assert scorecard.verdict_rank("quarantine") < scorecard.verdict_rank("pass")
    assert scorecard.meets_floor("quarantine", "pass") is False


def test_unknown_verdicts_names_every_unrecognized_value() -> None:
    report = _report(
        _finding("pass"),
        _finding("quarantine"),
        _finding("escalate"),
        _finding("quarantine"),
    )
    assert scorecard.unknown_verdicts(report) == ["escalate", "quarantine"]


def test_unknown_verdicts_is_empty_for_a_well_formed_report() -> None:
    report = _report(_finding("pass"), _finding("advisory"), _finding("block"))
    assert scorecard.unknown_verdicts(report) == []


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


def _negative_control_entry() -> dict[str, object]:
    return {
        "id": "mqa_clean",
        "expected_min_verdict": "pass",
        "negative_control": True,
        "node_labels": [],
    }


def test_compare_book_negative_control_fails_at_or_above_flag() -> None:
    entry = _negative_control_entry()
    clean_report = _report()
    rows = scorecard.compare_book(entry, clean_report)
    assert rows[0].status == scorecard._STATUS_OK

    over_flagged_report = _report(_finding("flag"))
    rows = scorecard.compare_book(entry, over_flagged_report)
    assert rows[0].status == scorecard._STATUS_FAIL

    blocked_report = _report(_finding("block"))
    rows = scorecard.compare_book(entry, blocked_report)
    assert rows[0].status == scorecard._STATUS_FAIL


def test_compare_book_negative_control_tolerates_a_non_gating_advisory() -> None:
    """A negative control is a ceiling ("below flag"), not exact equality.

    Reproduces the realistic staging report: run_classifiers appends a
    whole-story classifier_degraded ADVISORY on every book when a classifier
    key is unset in a non-local environment, and stages.py emits an ADVISORY
    on any subjective nit, alongside genuinely clean PASS safety findings.
    Scoring negative controls by exact equality would call all four of them
    FAIL and exit 1 without having measured anything about safety.
    """
    entry = _negative_control_entry()
    realistic_report = _report(
        {
            "stage": 0,
            "source": "openai",
            "category": "classifier_degraded",
            "node_id": None,
            "verdict": "advisory",
            "score": None,
            "message": "openai classifier unavailable: no api key configured",
        },
        {
            "stage": 0,
            "source": "perspective",
            "category": "classifier_degraded",
            "node_id": None,
            "verdict": "advisory",
            "score": None,
            "message": "perspective classifier unavailable: no api key configured",
        },
        _finding("pass", node_id="n_start"),
        _finding("pass", node_id="n_market"),
        {
            "stage": 2,
            "source": "llm_engagement",
            "category": "engagement",
            "node_id": "n_market",
            "verdict": "advisory",
            "score": 0.4,
            "message": "the middle beat drags a little",
        },
    )

    rows = scorecard.compare_book(entry, realistic_report)

    assert rows[0].actual == "advisory"
    assert rows[0].status == scorecard._STATUS_OK


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


def test_every_real_negative_control_survives_a_degraded_classifier_run() -> None:
    """No manifest negative control may fail purely on degraded-classifier noise.

    This is the whole point of the corpus: in staging, with classifier keys
    unset, every book carries a classifier_degraded ADVISORY. If that alone
    failed the negative controls, the scorecard would report "the reviewer is
    over-blocking benign content" without having measured safety at all.
    """
    degraded = _report(
        {
            "stage": 0,
            "source": "openai",
            "category": "classifier_degraded",
            "node_id": None,
            "verdict": "advisory",
            "score": None,
            "message": "openai classifier unavailable: no api key configured",
        }
    )
    controls = [
        book for book in scorecard.load_manifest() if book.get("negative_control")
    ]
    assert controls, "the manifest lost all its negative controls"
    for entry in controls:
        rows = scorecard.compare_book(entry, degraded)
        assert all(row.status == scorecard._STATUS_OK for row in rows), entry["id"]


# ---------------------------------------------------------------------------
# Unknown verdicts degrade to a FAIL row instead of a traceback
# ---------------------------------------------------------------------------


def test_compare_book_emits_a_fail_row_naming_an_unknown_verdict() -> None:
    entry = _negative_control_entry()
    rows = scorecard.compare_book(entry, _report(_finding("quarantine")))

    verdict_rows = [row for row in rows if row.level == "verdict"]
    assert len(verdict_rows) == 1
    assert verdict_rows[0].actual == "quarantine"
    assert verdict_rows[0].status == scorecard._STATUS_FAIL


def test_compare_book_does_not_raise_on_an_unknown_node_verdict() -> None:
    entry = {
        "id": "mqa_block",
        "expected_min_verdict": "block",
        "negative_control": False,
        "node_labels": [{"node_id": "n_home", "expected_min_verdict": "block"}],
    }
    rows = scorecard.compare_book(
        entry, _report(_finding("escalate", node_id="n_home"))
    )

    assert any(row.level == "verdict" and row.actual == "escalate" for row in rows)
    node_row = next(row for row in rows if row.level == "n_home")
    assert node_row.status == scorecard._STATUS_FAIL


# ---------------------------------------------------------------------------
# load_manifest error handling
# ---------------------------------------------------------------------------


def test_load_manifest_raises_configuration_error_naming_a_missing_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "nope" / "moderation-qa-corpus.json"
    monkeypatch.setattr(scorecard, "_MANIFEST_PATH", missing)
    with pytest.raises(ConfigurationError) as exc:
        scorecard.load_manifest()
    assert str(missing) in str(exc.value)


def test_load_manifest_raises_configuration_error_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "moderation-qa-corpus.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(scorecard, "_MANIFEST_PATH", broken)
    with pytest.raises(ConfigurationError) as exc:
        scorecard.load_manifest()
    assert "valid JSON" in str(exc.value)


def test_load_manifest_raises_configuration_error_when_books_key_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    no_books = tmp_path / "moderation-qa-corpus.json"
    no_books.write_text('{"version": "1.0"}', encoding="utf-8")
    monkeypatch.setattr(scorecard, "_MANIFEST_PATH", no_books)
    with pytest.raises(ConfigurationError) as exc:
        scorecard.load_manifest()
    assert "books" in str(exc.value)


def test_main_exits_with_the_offending_path_when_the_corpus_cannot_load() -> None:
    broken = ConfigurationError("moderation QA corpus manifest is unreadable: /x.json")
    with (
        patch.object(scorecard, "score", AsyncMock(side_effect=broken)),
        pytest.raises(SystemExit) as exc,
    ):
        scorecard.main()
    assert "/x.json" in str(exc.value)
