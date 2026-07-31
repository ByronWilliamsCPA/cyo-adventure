"""Unit tests for the deterministic post-review merge stage (design doc 2.2)."""

from __future__ import annotations

import pytest

from cyo_adventure.moderation.report import (
    Finding,
    FindingSeverity,
    ModerationReport,
    Source,
    Verdict,
)
from cyo_adventure.moderation.synthesis import merge_findings

pytestmark = pytest.mark.unit


def _reading_level_flag(
    node_id: str, *, severity: FindingSeverity = FindingSeverity.MEDIUM
) -> Finding:
    return Finding(
        stage=2,
        source=Source.LLM_READABILITY,
        category="reading_level",
        node_id=node_id,
        verdict=Verdict.FLAG,
        message="reading level above band",
        concern="too_mature",
        severity=severity,
    )


def test_identical_findings_across_twelve_nodes_merge_to_one() -> None:
    findings = [_reading_level_flag(f"n{i}") for i in range(12)]
    merged = merge_findings(findings)
    assert len(merged) == 1
    assert merged[0].node_ids == tuple(f"n{i}" for i in range(12))
    assert merged[0].message == "reading level above band (12 findings merged)"


def test_single_finding_group_still_gains_node_ids() -> None:
    findings = [_reading_level_flag("n1")]
    merged = merge_findings(findings)
    assert len(merged) == 1
    assert merged[0].node_ids == ("n1",)
    assert merged[0].message == "reading level above band"


def test_differing_severity_keeps_findings_separate() -> None:
    """Severity is part of the merge key, so bands never collapse into one row.

    Collapsing them would have to pick a survivor, and either direction is
    wrong: taking the max relabels two genuinely LOW nodes as HIGH, and taking
    anything less than the max downgrades a HIGH node in the surfaced ranking
    the human approver reads (design doc 2.1).
    """
    findings = [
        _reading_level_flag("n1", severity=FindingSeverity.LOW),
        _reading_level_flag("n2", severity=FindingSeverity.HIGH),
        _reading_level_flag("n3", severity=FindingSeverity.MEDIUM),
    ]
    merged = merge_findings(findings)
    assert len(merged) == 3
    assert {f.severity for f in merged} == {
        FindingSeverity.LOW,
        FindingSeverity.HIGH,
        FindingSeverity.MEDIUM,
    }
    assert {f.node_ids for f in merged} == {("n1",), ("n2",), ("n3",)}


def test_differing_severity_within_one_node_set_still_merges() -> None:
    """The bands that DO match still collapse, so the merge keeps its purpose."""
    findings = [
        _reading_level_flag("n1", severity=FindingSeverity.LOW),
        _reading_level_flag("n2", severity=FindingSeverity.HIGH),
        _reading_level_flag("n3", severity=FindingSeverity.LOW),
    ]
    merged = merge_findings(findings)
    assert len(merged) == 2
    by_severity = {f.severity: f for f in merged}
    assert by_severity[FindingSeverity.LOW].node_ids == ("n1", "n3")
    assert by_severity[FindingSeverity.HIGH].node_ids == ("n2",)


def test_differing_verdict_keeps_findings_separate() -> None:
    """A BLOCK never absorbs a FLAG, and never lends its message to one.

    Merging these would put the BLOCK verdict and the word "severe" onto n1,
    whose actual finding was a FLAG reading "mild". That misattribution is
    unrecoverable: raw reviewer output is not retained per finding, so the
    discarded message cannot be reconstructed for the guardian who is the
    final gate under ADR-005.
    """
    findings = [
        Finding(
            stage=1,
            source=Source.LLM_SAFETY,
            category="safety",
            node_id="n1",
            verdict=Verdict.FLAG,
            message="mild",
            concern="too_mature",
            severity=FindingSeverity.LOW,
        ),
        Finding(
            stage=1,
            source=Source.LLM_SAFETY,
            category="safety",
            node_id="n2",
            verdict=Verdict.BLOCK,
            message="severe",
            concern="too_mature",
            severity=FindingSeverity.HIGH,
        ),
    ]
    merged = merge_findings(findings)
    assert len(merged) == 2
    by_node = {f.node_id: f for f in merged}
    assert by_node["n1"].verdict is Verdict.FLAG
    assert by_node["n1"].message == "mild"
    assert by_node["n2"].verdict is Verdict.BLOCK
    assert by_node["n2"].message == "severe"


def test_distinct_messages_in_one_category_all_survive() -> None:
    """The C1 regression guard: distinct safety reasons must not collapse.

    Stage 1 emits no ``concern`` until design doc 2.2 item 1 lands (B2), so a
    ``(category, concern)`` key degenerates to ``(category,)`` and every
    distinct safety reason in a book would merge into one row, destroying all
    but one reviewer message.
    """
    reasons = [
        "depicts a child alone with a stranger",
        "describes how to start a fire",
        "character drowns off-page",
    ]
    findings = [
        Finding(
            stage=1,
            source=Source.LLM_SAFETY,
            category="safety",
            node_id=f"n{i}",
            verdict=Verdict.FLAG,
            message=reason,
            severity=FindingSeverity.MEDIUM,
        )
        for i, reason in enumerate(reasons)
    ]
    merged = merge_findings(findings)
    assert len(merged) == 3
    assert {f.message for f in merged} == set(reasons)


def test_structural_findings_never_merge() -> None:
    structural = [
        Finding(
            stage=1,
            source=Source.PIPELINE,
            category="pipeline",
            node_id=None,
            verdict=Verdict.FLAG,
            message="reviewer unavailable",
            structural=True,
            concern="reviewer_unavailable",
            severity=FindingSeverity.HIGH,
        )
        for _ in range(3)
    ]
    merged = merge_findings(structural)
    assert len(merged) == 3
    assert all(f.node_ids is None for f in merged)


def test_pass_findings_never_merge_and_pass_through_unchanged() -> None:
    passes = [
        Finding(
            stage=1,
            source=Source.LLM_SAFETY,
            category="safety",
            node_id=f"n{i}",
            verdict=Verdict.PASS,
            message="clean",
        )
        for i in range(3)
    ]
    merged = merge_findings(passes)
    assert merged == passes


def test_whole_story_findings_merge_to_node_ids_none() -> None:
    findings = [
        Finding(
            stage=0,
            source=Source.OPENAI,
            category="classifier_degraded",
            node_id=None,
            verdict=Verdict.ADVISORY,
            message="classifier unavailable",
            structural=False,
            concern="other",
            severity=FindingSeverity.MEDIUM,
        )
        for _ in range(2)
    ]
    merged = merge_findings(findings)
    assert len(merged) == 1
    assert merged[0].node_ids is None


def test_different_categories_do_not_merge_together() -> None:
    findings = [
        _reading_level_flag("n1"),
        Finding(
            stage=1,
            source=Source.LLM_SAFETY,
            category="safety",
            node_id="n2",
            verdict=Verdict.FLAG,
            message="different category",
            concern="too_mature",
            severity=FindingSeverity.MEDIUM,
        ),
    ]
    merged = merge_findings(findings)
    assert len(merged) == 2


def test_different_concerns_within_same_category_do_not_merge() -> None:
    findings = [
        _reading_level_flag("n1"),
        Finding(
            stage=2,
            source=Source.LLM_READABILITY,
            category="reading_level",
            node_id="n2",
            verdict=Verdict.FLAG,
            message="different concern",
            concern="other",
            severity=FindingSeverity.MEDIUM,
        ),
    ]
    merged = merge_findings(findings)
    assert len(merged) == 2


def test_merged_report_gating_flags_equal_raw_report() -> None:
    findings = [_reading_level_flag(f"n{i}") for i in range(3)]
    raw = ModerationReport(findings=findings)
    merged = ModerationReport(findings=merge_findings(raw.findings))
    assert merged.has_soft_flag == raw.has_soft_flag
    assert merged.has_hard_block == raw.has_hard_block
