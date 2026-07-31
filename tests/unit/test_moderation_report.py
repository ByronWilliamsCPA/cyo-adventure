"""Unit tests for moderation finding aggregation and serialization."""

from __future__ import annotations

import pytest

from cyo_adventure.moderation.report import (
    Finding,
    FindingSeverity,
    ModerationReport,
    Source,
    Verdict,
)

pytestmark = pytest.mark.unit


def _finding(verdict: Verdict, *, source: Source = Source.LLM_SAFETY) -> Finding:
    return Finding(
        stage=1,
        source=source,
        category="violence",
        node_id="n1",
        verdict=verdict,
        score=0.9,
        message="m",
    )


def test_empty_report_is_clean_and_not_blocked() -> None:
    report = ModerationReport()
    assert report.is_clean is True
    assert report.has_hard_block is False
    assert report.has_soft_flag is False


def test_block_finding_marks_hard_block() -> None:
    report = ModerationReport()
    report.add(_finding(Verdict.BLOCK))
    assert report.has_hard_block is True
    assert report.is_clean is False


def test_flag_finding_marks_soft_flag_only() -> None:
    report = ModerationReport()
    report.add(_finding(Verdict.FLAG))
    assert report.has_hard_block is False
    assert report.has_soft_flag is True


def test_to_dict_round_trips_findings() -> None:
    report = ModerationReport()
    report.add(_finding(Verdict.ADVISORY, source=Source.LLM_ENGAGEMENT))
    payload = report.to_dict()
    assert payload["findings"][0]["source"] == "llm_engagement"
    assert payload["findings"][0]["verdict"] == "advisory"
    assert payload["summary"]["count"] == 1


@pytest.mark.parametrize(
    "stage",
    [-1, 5],
    ids=["below_range", "above_range"],
)
def test_finding_stage_out_of_range_raises_value_error(stage: int) -> None:
    with pytest.raises(ValueError, match=r"Finding\.stage must be 0-4"):
        Finding(
            stage=stage,
            source=Source.LLM_SAFETY,
            category="violence",
            node_id="n1",
            verdict=Verdict.ADVISORY,
            score=0.5,
            message="m",
        )


@pytest.mark.parametrize(
    "stage",
    [0, 4],
    ids=["lower_bound", "upper_bound"],
)
def test_finding_stage_at_boundary_does_not_raise(stage: int) -> None:
    finding = Finding(
        stage=stage,
        source=Source.LLM_SAFETY,
        category="violence",
        node_id="n1",
        verdict=Verdict.ADVISORY,
        score=0.5,
        message="m",
    )
    assert finding.stage == stage


@pytest.mark.parametrize(
    "score",
    [-0.1, 1.1],
    ids=["below_range", "above_range"],
)
def test_finding_score_out_of_range_raises_value_error(score: float) -> None:
    with pytest.raises(ValueError, match=r"Finding\.score must be in \[0\.0, 1\.0\]"):
        Finding(
            stage=1,
            source=Source.LLM_SAFETY,
            category="violence",
            node_id="n1",
            verdict=Verdict.ADVISORY,
            score=score,
            message="m",
        )


def test_finding_score_none_does_not_raise() -> None:
    finding = Finding(
        stage=1,
        source=Source.LLM_SAFETY,
        category="violence",
        node_id="n1",
        verdict=Verdict.PASS,
        score=None,
        message="m",
    )
    assert finding.score is None


# ---------------------------------------------------------------------------
# Task B1.1: FindingSeverity + Finding.severity/node_ids (design doc 2.1)
# ---------------------------------------------------------------------------


def test_finding_severity_and_node_ids_default_to_none() -> None:
    finding = _finding(Verdict.FLAG)
    assert finding.severity is None
    assert finding.node_ids is None


def test_finding_severity_and_node_ids_round_trip_construction() -> None:
    finding = Finding(
        stage=1,
        source=Source.LLM_SAFETY,
        category="reading_level",
        node_id="n1",
        verdict=Verdict.FLAG,
        score=None,
        message="m",
        severity=FindingSeverity.HIGH,
        node_ids=("n1", "n2", "n3"),
    )
    assert finding.severity is FindingSeverity.HIGH
    assert finding.node_ids == ("n1", "n2", "n3")


def test_finding_to_dict_serializes_severity_and_node_ids() -> None:
    finding = Finding(
        stage=1,
        source=Source.LLM_SAFETY,
        category="reading_level",
        node_id="n1",
        verdict=Verdict.FLAG,
        score=None,
        message="m",
        severity=FindingSeverity.MEDIUM,
        node_ids=("n1", "n2"),
    )
    payload = finding.to_dict()
    assert payload["severity"] == "medium"
    assert payload["node_ids"] == ["n1", "n2"]


def test_finding_to_dict_serializes_absent_severity_and_node_ids_as_none() -> None:
    payload = _finding(Verdict.PASS).to_dict()
    assert payload["severity"] is None
    assert payload["node_ids"] is None


def test_finding_severity_enum_values() -> None:
    assert FindingSeverity.HIGH.value == "high"
    assert FindingSeverity.MEDIUM.value == "medium"
    assert FindingSeverity.LOW.value == "low"
