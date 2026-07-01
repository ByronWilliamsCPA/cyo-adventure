"""Unit tests for moderation finding aggregation and serialization."""

from __future__ import annotations

import pytest

from cyo_adventure.moderation.report import (
    Finding,
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
