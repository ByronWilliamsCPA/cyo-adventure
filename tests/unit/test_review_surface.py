"""Unit tests for the C3-4 review-surface projection."""

from __future__ import annotations

import pytest

from cyo_adventure.api.review_surface import (
    build_review_queue_item,
    build_review_surface,
)
from cyo_adventure.core.exceptions import ValidationError


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
def test_null_report_is_reported_as_unscreened() -> None:
    """Finding 3: an unmoderated version must not look identical to a clean one.

    A screened-clean version renders empty flagged_passages/story_level_findings
    just like an unmoderated one; `screened` is the only field a consumer (the
    future C4a-4 guardian console) can trust to tell the two apart.
    """
    view = build_review_surface(
        status="draft",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=None,
    )
    assert view.screened is False


@pytest.mark.unit
def test_present_report_is_reported_as_screened() -> None:
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=_report(),
    )
    assert view.screened is True


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


@pytest.mark.unit
def test_summary_rejects_non_bool_gate_values() -> None:
    """A corrupt-at-rest summary with a Python-truthy non-bool gate value must
    not silently coerce to True via bool().
    """
    report: dict[str, object] = {
        "findings": [],
        "summary": {
            "count": 0,
            "hard_block": "false",  # truthy under naive bool(), must NOT become True
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
    assert view.summary is not None
    assert view.summary.hard_block is False


@pytest.mark.unit
def test_unrecognized_source_rejected() -> None:
    """A finding whose source is outside the declared Source enum is rejected
    as corrupt-at-rest data, not silently passed through as a plain string.
    """
    report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "not_a_real_source",
                "category": "safety",
                "node_id": "n_start",
                "verdict": "flag",
                "score": None,
                "message": "x",
            }
        ],
        "summary": None,
    }
    with pytest.raises(ValidationError):
        build_review_surface(
            status="in_review",
            storybook_id="s1",
            version=1,
            blob=_blob(),
            moderation_report=report,
        )


@pytest.mark.unit
def test_unrecognized_verdict_rejected() -> None:
    """A finding whose verdict is outside the declared Verdict enum is rejected."""
    report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_start",
                "verdict": "maybe",
                "score": None,
                "message": "x",
            }
        ],
        "summary": None,
    }
    with pytest.raises(ValidationError):
        build_review_surface(
            status="in_review",
            storybook_id="s1",
            version=1,
            blob=_blob(),
            moderation_report=report,
        )


@pytest.mark.unit
def test_out_of_range_stage_rejected() -> None:
    """A finding whose stage is outside the declared 0..4 range is rejected."""
    report: dict[str, object] = {
        "findings": [
            {
                "stage": 99,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_start",
                "verdict": "flag",
                "score": None,
                "message": "x",
            }
        ],
        "summary": None,
    }
    with pytest.raises(ValidationError):
        build_review_surface(
            status="in_review",
            storybook_id="s1",
            version=1,
            blob=_blob(),
            moderation_report=report,
        )


@pytest.mark.unit
def test_queue_item_flagged_counts_all_findings() -> None:
    """A screened story with findings reports screened=True and a flagged count."""
    item = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=2,
        blob={"title": "The Lantern", "nodes": [{"id": "n1", "body": "Hi."}]},
        moderation_report={
            "findings": [
                {
                    "stage": 1,
                    "source": "llm_safety",
                    "category": "safety",
                    "node_id": "n1",
                    "verdict": "flag",
                    "score": None,
                    "message": "m",
                },
                {
                    "stage": 2,
                    "source": "pipeline",
                    "category": "coherence",
                    "node_id": None,
                    "verdict": "advisory",
                    "score": None,
                    "message": "story-level",
                },
            ],
            "summary": {
                "count": 2,
                "hard_block": False,
                "soft_flag": True,
                "repaired": False,
                "reviewer_independent": True,
            },
        },
    )
    assert item.title == "The Lantern"
    assert item.version == 2
    assert item.screened is True
    assert item.flagged_count == 2
    assert item.summary is not None
    assert item.summary.soft_flag is True


@pytest.mark.unit
def test_queue_item_screened_clean_has_zero_flags() -> None:
    """A screened-clean story reports screened=True, flagged_count=0."""
    item = build_review_queue_item(
        storybook_id="s2",
        status="in_review",
        version=1,
        blob={"nodes": []},
        moderation_report={
            "findings": [],
            "summary": {
                "count": 0,
                "hard_block": False,
                "soft_flag": False,
                "repaired": False,
                "reviewer_independent": False,
            },
        },
    )
    assert item.title == "s2"  # falls back to the storybook id
    assert item.screened is True
    assert item.flagged_count == 0
    assert item.summary is not None


@pytest.mark.unit
def test_queue_item_unscreened_has_no_summary() -> None:
    """An unmoderated story reports screened=False and summary=None."""
    item = build_review_queue_item(
        storybook_id="s3",
        status="in_review",
        version=1,
        blob={"title": "Draft"},
        moderation_report=None,
    )
    assert item.screened is False
    assert item.summary is None
    assert item.flagged_count == 0
