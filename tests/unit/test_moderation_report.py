"""Unit tests for moderation finding aggregation and serialization."""

from __future__ import annotations

from typing import cast

import pytest

from cyo_adventure.moderation.report import (
    CONCERN_TAXONOMY,
    Finding,
    FindingSeverity,
    ModerationReport,
    Source,
    Verdict,
    moderation_report_unusable,
    severe_finding_counts,
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


# ---------------------------------------------------------------------------
# Task B1.2: PASS aggregate block, PASS findings not persisted (design doc 2.1)
# ---------------------------------------------------------------------------


def test_nodes_reviewed_defaults_to_zero() -> None:
    assert ModerationReport().nodes_reviewed == 0


def test_to_dict_excludes_pass_findings_from_persisted_findings() -> None:
    report = ModerationReport(nodes_reviewed=3)
    report.add(_finding(Verdict.PASS))
    report.add(_finding(Verdict.FLAG))
    payload = report.to_dict()
    findings = cast("list[dict[str, object]]", payload["findings"])
    verdicts = [f["verdict"] for f in findings]
    assert verdicts == ["flag"]


def test_to_dict_aggregates_pass_counts_by_category() -> None:
    report = ModerationReport(nodes_reviewed=5)
    report.add(_finding(Verdict.PASS))
    report.add(_finding(Verdict.PASS))
    report.add(
        Finding(
            stage=0,
            source=Source.OPENAI,
            category="harassment",
            node_id="n2",
            verdict=Verdict.PASS,
            score=0.0,
            message="m",
        )
    )
    payload = report.to_dict()
    assert payload["aggregate"] == {
        "nodes_reviewed": 5,
        "pass_counts": {"violence": 2, "harassment": 1},
    }


def test_to_dict_summary_count_excludes_pass_findings() -> None:
    report = ModerationReport()
    report.add(_finding(Verdict.PASS))
    report.add(_finding(Verdict.PASS))
    report.add(_finding(Verdict.FLAG))
    payload = report.to_dict()
    summary = cast("dict[str, object]", payload["summary"])
    assert summary["count"] == 1


def test_gating_properties_still_see_pass_findings_in_memory() -> None:
    report = ModerationReport()
    report.add(_finding(Verdict.PASS))
    assert report.is_clean is True
    assert len(report.findings) == 1


def test_to_dict_with_no_findings_has_empty_pass_counts_and_zero_summary() -> None:
    report = ModerationReport(nodes_reviewed=2)
    payload = report.to_dict()
    assert payload["aggregate"] == {"nodes_reviewed": 2, "pass_counts": {}}
    summary = cast("dict[str, object]", payload["summary"])
    assert summary["count"] == 0


@pytest.mark.unit
def test_unknown_concern_rejected_at_construction() -> None:
    """An off-taxonomy concern must not reach a Finding.

    concern is half the documented merge key (design doc 2.2). An unrecognized
    value would silently form its own merge group and, once B2 has models
    emitting concerns, drift the taxonomy by accident. Callers that parse a
    model response degrade to "other" at the parse boundary instead.
    """
    with pytest.raises(ValueError, match="CONCERN_TAXONOMY"):
        Finding(
            stage=1,
            source=Source.LLM_SAFETY,
            category="safety",
            node_id="n1",
            verdict=Verdict.FLAG,
            message="m",
            concern="scary_clowns",
        )


@pytest.mark.unit
def test_every_taxonomy_member_is_accepted() -> None:
    """The validation admits the whole documented taxonomy, not a subset."""
    for concern in CONCERN_TAXONOMY:
        finding = Finding(
            stage=1,
            source=Source.LLM_SAFETY,
            category="safety",
            node_id="n1",
            verdict=Verdict.FLAG,
            message="m",
            concern=concern,
        )
        assert finding.concern == concern


@pytest.mark.unit
def test_absent_concern_is_still_allowed() -> None:
    """Stage 1 emits no concern until design doc 2.2 item 1 lands (B2)."""
    finding = Finding(
        stage=1,
        source=Source.LLM_SAFETY,
        category="safety",
        node_id="n1",
        verdict=Verdict.FLAG,
        message="m",
    )
    assert finding.concern is None


class TestModerationReportUnusable:
    """moderation_report_unusable() over the persisted JSONB shape."""

    def _fail_safe_finding(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "stage": "review",
            "source": "llm_safety",
            "category": "llm_safety",
            "node_id": "n1",
            "verdict": "flag",
            "score": None,
            "message": "unknown verdict; defaulted to fail-safe",
        }
        base.update(overrides)
        return base

    def _report(
        self, findings: list[dict[str, object]], *, independent: bool = True
    ) -> dict[str, object]:
        return {
            "findings": findings,
            "aggregate": {"nodes_reviewed": 1, "pass_counts": {}},
            "summary": {
                "count": len(findings),
                "hard_block": False,
                "soft_flag": bool(findings),
                "repaired": False,
                "reviewer_independent": independent,
            },
        }

    def test_none_report_is_unusable(self) -> None:
        assert moderation_report_unusable(None) is True

    def test_clean_report_is_usable(self) -> None:
        assert moderation_report_unusable(self._report([])) is False

    def test_all_fail_safe_legacy_rows_are_unusable(self) -> None:
        # Legacy pre-Stage-A rows: no "structural" key, no "concern" key.
        report = self._report(
            [self._fail_safe_finding(node_id=f"n{i}") for i in range(3)]
        )
        assert moderation_report_unusable(report) is True

    def test_parse_failed_variant_is_unusable(self) -> None:
        report = self._report(
            [
                self._fail_safe_finding(
                    message="verdict parse failed; defaulted to fail-safe"
                )
            ]
        )
        assert moderation_report_unusable(report) is True

    def test_mock_reviewer_summary_flag_is_unusable(self) -> None:
        genuine = self._fail_safe_finding(
            message="cruelty to animals", severity="medium"
        )
        assert (
            moderation_report_unusable(self._report([genuine], independent=False))
            is True
        )

    def test_structural_only_report_is_unusable(self) -> None:
        structural = self._fail_safe_finding(
            message="reviewer unavailable",
            structural=True,
            concern="reviewer_unavailable",
        )
        assert moderation_report_unusable(self._report([structural])) is True

    def test_mixed_genuine_and_fail_safe_is_usable(self) -> None:
        findings = [
            self._fail_safe_finding(),
            self._fail_safe_finding(message="frightening imagery", severity="medium"),
        ]
        assert moderation_report_unusable(self._report(findings)) is False


class TestSevereFindingCounts:
    def test_counts_blocks_and_highs_separately(self) -> None:
        report = {
            "findings": [
                {"verdict": "block", "severity": "high", "message": "a"},
                {"verdict": "flag", "severity": "high", "message": "b"},
                {"verdict": "flag", "severity": "medium", "message": "c"},
                {"verdict": "advisory", "severity": "low", "message": "d"},
            ]
        }
        assert severe_finding_counts(report) == (1, 1)

    def test_none_and_empty(self) -> None:
        assert severe_finding_counts(None) == (0, 0)
        assert severe_finding_counts({"findings": []}) == (0, 0)

    def test_high_severity_advisory_does_not_gate(self) -> None:
        # Advisories never gate (SOP contract); a stray severity=high on an
        # advisory must not force an override reason at approval.
        report = {
            "findings": [{"verdict": "advisory", "severity": "high", "message": "a"}]
        }
        assert severe_finding_counts(report) == (0, 0)
