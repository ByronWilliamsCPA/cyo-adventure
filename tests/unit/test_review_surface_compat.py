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
