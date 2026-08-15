"""Unit tests for the W7 run-to-run spread analysis.

The analysis exists to answer two register rows (`UW-C258`, `UW-C255`), and
both answers are numbers a later reader will quote. So the tests here pin the
things that would make a quoted number wrong rather than merely make the script
crash: that pairing is on ``(judge, arm)`` and not on position, that a run
killed mid-flight is still readable, and that control arms are separated from
defect arms, since the whole point of the `UW-C255` restatement is that those
two populations mean different things.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts.w7_run_to_run import load_records, matched_pairs, report

if TYPE_CHECKING:
    from pathlib import Path

_SCORES = {
    "age_fit": 3.0,
    "imagery": 3.0,
    "voice": 3.0,
    "dialogue": 3.0,
    "choice_quality": 3.0,
    "ending_quality": 3.0,
    "engagement": 3.0,
}


def _record(judge: str, leg: str, **overrides: float) -> dict[str, object]:
    """Build one scored record.

    Args:
        judge: The judge label.
        leg: The arm name, ``<book>__<defect>``.
        **overrides: Per-criterion scores replacing the flat-3 default.

    Returns:
        dict[str, object]: A record shaped like the battery's own output.
    """
    return {
        "book": f"{leg}#0",
        "leg": leg,
        "family": "w7",
        "judge": judge,
        "self_family": False,
        "scores": {**_SCORES, **overrides},
        "notes": "",
        "error": None,
    }


@pytest.mark.unit
def test_pairs_match_on_judge_and_arm_not_on_position() -> None:
    """Two runs need not emit their scorings in the same order.

    The battery scores concurrently, so run order varies between runs. Pairing
    positionally would silently compare one book against another and report the
    difference between two books as run-to-run noise, which would inflate the
    spread without any error surfacing.
    """
    first = [_record("j1", "book-a__control"), _record("j1", "book-b__control")]
    second = [
        _record("j1", "book-b__control", voice=5.0),
        _record("j1", "book-a__control"),
    ]

    pairs = matched_pairs(first, second)

    assert [arm for _judge, arm, _b, _a in pairs] == [
        "book-a__control",
        "book-b__control",
    ]
    by_arm = {arm: (before, after) for _j, arm, before, after in pairs}
    assert by_arm["book-a__control"][1]["voice"] == 3.0
    assert by_arm["book-b__control"][1]["voice"] == 5.0


@pytest.mark.unit
def test_a_scoring_only_one_run_made_is_not_paired() -> None:
    """A killed run covers a subset, and the unmatched remainder must drop.

    Three consecutive runs died mid-flight in this environment, so a partial
    second run is the expected input rather than an edge case. Carrying an
    unmatched arm into the comparison would compare a score against nothing.
    """
    first = [_record("j1", "book-a__control"), _record("j1", "book-b__control")]
    second = [_record("j1", "book-a__control")]

    assert [arm for _j, arm, _b, _a in matched_pairs(first, second)] == [
        "book-a__control"
    ]


@pytest.mark.unit
def test_a_different_judge_on_the_same_arm_is_a_different_pair() -> None:
    """Judges differ in stability, so their scorings must never be conflated."""
    first = [_record("j1", "book-a__control")]
    second = [_record("j2", "book-a__control", voice=5.0)]

    assert matched_pairs(first, second) == []


@pytest.mark.unit
def test_an_errored_scoring_is_excluded(tmp_path: Path) -> None:
    """A failed call carries no scores; counting it would fake agreement."""
    path = tmp_path / "journal.jsonl"
    good = _record("j1", "book-a__control")
    bad = {**_record("j1", "book-b__control"), "error": "timeout", "scores": {}}
    path.write_text(
        "\n".join(json.dumps(r) for r in (good, bad)) + "\n", encoding="utf-8"
    )

    assert [r["leg"] for r in load_records(path)] == ["book-a__control"]


@pytest.mark.unit
def test_a_journal_and_a_verdicts_payload_load_alike(tmp_path: Path) -> None:
    """Both shapes are real inputs: one from a finished run, one from a killed one."""
    records = [_record("j1", "book-a__control")]
    journal = tmp_path / "journal.jsonl"
    journal.write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    verdicts = tmp_path / "verdicts.json"
    verdicts.write_text(json.dumps({"verdicts": records}), encoding="utf-8")

    assert load_records(journal) == load_records(verdicts)


@pytest.mark.unit
def test_control_and_defect_arms_are_counted_separately() -> None:
    """The `UW-C255` restatement rests entirely on this split.

    A criterion moving on a defect arm may be detecting real collateral change;
    the same criterion moving on a control has moved on nothing. Reporting them
    in one pool is the original defect this analysis exists to correct.
    """
    first = [_record("j1", "book-a__control"), _record("j1", "book-a__tense_break")]
    second = [
        _record("j1", "book-a__control"),
        _record("j1", "book-a__tense_break", voice=5.0),
    ]

    text = report(first, second)

    assert "control arms: 1   defect arms: 1" in text
    assert "UW-C258" in text
    assert "UW-C255" in text


@pytest.mark.unit
def test_no_overlap_between_runs_is_said_rather_than_shown_as_zero() -> None:
    """An empty comparison must not print as a clean zero-spread result.

    A spread of zero and a spread over no data read identically to someone
    skimming, and the second would be quoted as perfect reproducibility.
    """
    first = [_record("j1", "book-a__control")]
    second = [_record("j1", "book-z__control")]

    assert "nothing to compare" in report(first, second)
