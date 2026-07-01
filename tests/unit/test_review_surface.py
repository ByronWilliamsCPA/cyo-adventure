"""Unit tests for the C3-4 review-surface projection."""

from __future__ import annotations

import pytest

from cyo_adventure.api.review_surface import build_review_surface


def _blob() -> dict[str, object]:
    return {
        "nodes": [
            {"id": "n_start", "body": "Start prose."},
            {"id": "n_end", "body": "End prose."},
        ]
    }


def _report() -> dict[str, object]:
    return {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_start",
                "verdict": "flag",
                "score": None,
                "message": "mild peril",
            },
            {
                "stage": 3,
                "source": "llm_coherence",
                "category": "coherence",
                "node_id": None,
                "verdict": "advisory",
                "score": None,
                "message": "slightly disjoint",
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_end",
                "verdict": "pass",
                "score": None,
                "message": "clean",
            },
        ],
        "summary": {
            "count": 3,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


@pytest.mark.unit
def test_flagged_passage_joins_prose() -> None:
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=_report(),
    )
    passages = {p.node_id: p for p in view.flagged_passages}
    assert passages["n_start"].prose == "Start prose."
    assert passages["n_start"].findings[0].category == "safety"


@pytest.mark.unit
def test_pass_findings_excluded_and_story_level_partitioned() -> None:
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=_report(),
    )
    # n_end had only a pass finding -> not a flagged passage.
    assert all(p.node_id != "n_end" for p in view.flagged_passages)
    assert len(view.story_level_findings) == 1
    assert view.story_level_findings[0].category == "coherence"


@pytest.mark.unit
def test_null_report_yields_empty_projections() -> None:
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=None,
    )
    assert view.summary is None
    assert view.flagged_passages == []
    assert view.story_level_findings == []


@pytest.mark.unit
def test_finding_on_absent_node_gets_empty_prose() -> None:
    report = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_missing",
                "verdict": "block",
                "score": None,
                "message": "x",
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": True,
            "soft_flag": False,
            "repaired": False,
            "reviewer_independent": True,
        },
    }
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=report,
    )
    passage = view.flagged_passages[0]
    assert passage.node_id == "n_missing"
    assert passage.prose == ""
