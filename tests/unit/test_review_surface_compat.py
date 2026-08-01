"""Reader-compat tests over a hand-built legacy moderation report fixture.

Design doc's "#ASSUME: data integrity ... reader-compat tests over a
fixture" RAD gate (Stage B). ``legacy_flood_report.json`` is built by hand
(not exported from prod) to reproduce the pre-Stage-B persisted shape: 30
per-node findings across 3 nodes, none of the four Stage-B additive keys
(severity, node_ids, structural, concern), no "aggregate" block, and a
summary.count inflated relative to len(findings) (the PASS-inclusive count
bug Stage B fixed). Every review-surface reader must keep succeeding on
this shape without raising and without depending on the new keys.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.api.review_surface import (
    build_content_summary,
    build_review_queue_item,
    build_review_surface,
)
from cyo_adventure.moderation.thresholds import ThresholdPolicy

_FIXTURE_PATH = (
    Path(__file__).parent.parent
    / "fixtures"
    / "moderation_reports"
    / "legacy_flood_report.json"
)


def _legacy_report() -> dict[str, object]:
    with _FIXTURE_PATH.open() as f:
        data: dict[str, object] = json.load(f)
    return data


def _blob() -> dict[str, object]:
    return {
        "nodes": [
            {"id": "n_gate", "body": "Gate prose."},
            {"id": "n_hallway", "body": "Hallway prose."},
            {"id": "n_vault", "body": "Vault prose."},
        ]
    }


@pytest.mark.unit
def test_build_review_surface_succeeds_on_legacy_report() -> None:
    """The admin review surface reads a pre-Stage-B report without raising,
    and every projected finding's severity degrades to None (the field
    simply did not exist yet on this row)."""
    view = build_review_surface(
        status="in_review",
        storybook_id="s_legacy",
        version=1,
        blob=_blob(),
        moderation_report=_legacy_report(),
    )
    assert view.screened is True
    all_findings = [
        f for passage in view.flagged_passages for f in passage.findings
    ] + view.story_level_findings
    assert len(all_findings) > 0
    for finding in all_findings:
        assert finding.severity is None
        assert finding.node_ids is None
        assert finding.structural is False
        assert finding.concern is None


@pytest.mark.unit
def test_build_review_queue_item_succeeds_on_legacy_report() -> None:
    """The admin queue projection reads a pre-Stage-B report without
    raising."""
    item = build_review_queue_item(
        storybook_id="s_legacy",
        status="in_review",
        version=1,
        blob=_blob(),
        moderation_report=_legacy_report(),
    )
    assert item.screened is True
    assert item.flagged_count > 0


@pytest.mark.unit
def test_build_content_summary_succeeds_on_legacy_report() -> None:
    """The guardian content summary reads a pre-Stage-B report without
    raising, for every age band the policy resolves."""
    summary = build_content_summary(
        storybook_id="s_legacy",
        version=1,
        blob=_blob(),
        moderation_report=_legacy_report(),
        age_band="10-13",
        policy=ThresholdPolicy(rows={}),
    )
    assert summary.screened is True
    # Stage B3 (design doc 2.6): every surfaced legacy finding's additive
    # concern/severity fields degrade to None, and node_count is still a
    # non-negative count derived from the pre-Stage-B node_id-only shape
    # (never a node id or a raised error), for every row the merge produces.
    for finding in summary.findings:
        assert finding.concern is None
        assert finding.severity is None
        assert finding.node_count >= 0
    # Stage B3 follow-up (design doc 2.7 option (a)): no validation_report was
    # passed (this call predates validator persistence), so validator_notes
    # degrades to an empty aggregate rather than raising or fabricating rows.
    assert summary.validator_notes == []


@pytest.mark.unit
def test_build_review_surface_new_buckets_degrade_on_legacy_report() -> None:
    """The Stage B3 ranked/structural/low-advisory/validator fields all
    degrade cleanly on a pre-Stage-B report: every legacy finding lacks
    ``structural`` and ``severity``, so none can land in the structural or
    low-advisory buckets, and every one lands in ``ranked_findings`` instead;
    a missing ``validation_report`` (not passed here) yields an empty
    ``validator_findings`` rather than raising.
    """
    view = build_review_surface(
        status="in_review",
        storybook_id="s_legacy",
        version=1,
        blob=_blob(),
        moderation_report=_legacy_report(),
    )
    assert view.structural_findings == []
    assert view.low_advisory_findings == []
    assert view.validator_findings == []
    assert len(view.ranked_findings) > 0
    for finding in view.ranked_findings:
        assert finding.severity is None
        assert finding.structural is False


def _expected_gating_counts(report: dict[str, object]) -> dict[str, int]:
    """Return per-node counts of the findings the surface actually renders.

    PASS findings are excluded from the review surface, so they must be
    excluded here too or the expectation would not match by construction.
    """
    findings = report["findings"]
    assert isinstance(findings, list)
    counts: dict[str, int] = {}
    for entry in findings:
        assert isinstance(entry, dict)
        if entry["verdict"] == "pass":
            continue
        for node_id in entry.get("node_ids") or [entry["node_id"]]:
            counts[node_id] = counts.get(node_id, 0) + 1
    return counts


@pytest.mark.unit
def test_legacy_findings_still_route_by_node_id() -> None:
    """The node_ids fan-out must not disturb the pre-Stage-B fallback path.

    Every finding in the fixture names a node via the bare ``node_id`` key and
    carries no ``node_ids``. Each must still land on the one node it names,
    exactly as before the merge stage existed. The expected counts are derived
    from the fixture rather than hardcoded, because the surface drops PASS
    findings and only the non-PASS ones become passage findings.
    """
    view = build_review_surface(
        status="in_review",
        storybook_id="s_legacy",
        version=1,
        blob=_blob(),
        moderation_report=_legacy_report(),
    )
    per_node = {p.node_id: len(p.findings) for p in view.flagged_passages}
    assert per_node == _expected_gating_counts(_legacy_report())


@pytest.mark.unit
def test_mixed_legacy_and_merged_shapes_in_one_report() -> None:
    """The realistic mid-migration shape: both finding shapes side by side.

    ``api/node_edit.py`` splices freshly re-reviewed single-node findings (no
    ``node_ids``) into a stored report that may already hold merged findings,
    so a single persisted report legitimately carries both shapes at once.
    Each must route by its own rule rather than one shape's presence changing
    how the other is read.
    """
    report = _legacy_report()
    findings = report["findings"]
    assert isinstance(findings, list)
    findings.append(
        {
            "stage": 2,
            "source": "llm_readability",
            "category": "reading_level",
            "node_id": "n_gate",
            "verdict": "flag",
            "score": None,
            "message": "reading level above band (2 findings merged)",
            "severity": "medium",
            "node_ids": ["n_gate", "n_vault"],
        }
    )
    view = build_review_surface(
        status="in_review",
        storybook_id="s_legacy",
        version=1,
        blob=_blob(),
        moderation_report=report,
    )
    per_node = {p.node_id: len(p.findings) for p in view.flagged_passages}
    # The merged finding adds itself to both nodes it names, and to no other;
    # n_hallway is untouched, and neither shape perturbs the other's routing.
    baseline = _expected_gating_counts(_legacy_report())
    assert per_node == {
        "n_gate": baseline["n_gate"] + 1,
        "n_hallway": baseline["n_hallway"],
        "n_vault": baseline["n_vault"] + 1,
    }
