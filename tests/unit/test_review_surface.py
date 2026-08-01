"""Unit tests for the C3-4 review-surface projection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api import review_surface
from cyo_adventure.api.review_surface import (
    build_content_summary,
    build_review_queue_item,
    build_review_surface,
)
from cyo_adventure.api.schemas import FindingView, ReviewSurfaceView
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.moderation.report import FindingSeverity, Source, Verdict
from cyo_adventure.moderation.thresholds import ThresholdPolicy

_DEFAULT_POLICY = ThresholdPolicy(rows={})


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
def test_old_shape_finding_projects_with_default_new_fields() -> None:
    """A pre-Stage-B finding dict, with none of the four new keys, still
    projects; the additive fields fall back to their documented defaults
    rather than raising (design doc 2.1: old persisted reports must keep
    reading through unmodified reader code)."""
    report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_start",
                "verdict": "flag",
                "score": None,
                "message": "mild peril",
            }
        ],
        "summary": None,
    }
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=report,
    )
    finding = view.flagged_passages[0].findings[0]
    assert finding.severity is None
    assert finding.node_ids is None
    assert finding.structural is False
    assert finding.concern is None


@pytest.mark.unit
def test_new_shape_finding_round_trips_additive_fields() -> None:
    """A merged, Stage-B-shaped finding carries severity, node_ids,
    structural, and concern through the projection unchanged."""
    report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_start",
                "verdict": "flag",
                "score": None,
                "message": "mild peril (3 findings merged)",
                "severity": "high",
                "node_ids": ["n_start", "n_end"],
                "structural": False,
                "concern": "frightening_content",
            }
        ],
        "summary": None,
    }
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=report,
    )
    finding = view.flagged_passages[0].findings[0]
    assert finding.severity is FindingSeverity.HIGH
    assert finding.node_ids == ["n_start", "n_end"]
    assert finding.structural is False
    assert finding.concern == "frightening_content"


@pytest.mark.unit
def test_corrupt_severity_string_degrades_to_none() -> None:
    """Unlike source/verdict, an unrecognized severity string is a ranking
    hint, not a gate; it degrades to None rather than raising, since old
    reports legitimately lack it and a bad value should not block review."""
    report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_start",
                "verdict": "flag",
                "score": None,
                "message": "x",
                "severity": "not_a_real_severity",
            }
        ],
        "summary": None,
    }
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=report,
    )
    assert view.flagged_passages[0].findings[0].severity is None


@pytest.mark.unit
def test_non_list_node_ids_degrades_to_none() -> None:
    """A corrupt-at-rest node_ids value (not a list) degrades to None rather
    than raising, matching the severity coercion's non-gating posture."""
    report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_start",
                "verdict": "flag",
                "score": None,
                "message": "x",
                "node_ids": "not-a-list",
            }
        ],
        "summary": None,
    }
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=report,
    )
    assert view.flagged_passages[0].findings[0].node_ids is None


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
    blob = _blob()
    with pytest.raises(ValidationError):
        build_review_surface(
            status="in_review",
            storybook_id="s1",
            version=1,
            blob=blob,
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
    blob = _blob()
    with pytest.raises(ValidationError):
        build_review_surface(
            status="in_review",
            storybook_id="s1",
            version=1,
            blob=blob,
            moderation_report=report,
        )


@pytest.mark.unit
def test_as_source_valid_string_returns_source() -> None:
    """A recognized source string narrows to the matching Source member."""
    assert review_surface._as_source("llm_safety") is Source.LLM_SAFETY


@pytest.mark.unit
def test_as_source_non_string_value_rejected() -> None:
    """A non-string source value (corrupt-at-rest JSON) is rejected outright,
    without ever reaching the Source(value) enum lookup."""
    with pytest.raises(ValidationError, match="unrecognized source"):
        review_surface._as_source(42)


@pytest.mark.unit
def test_as_verdict_valid_string_returns_verdict() -> None:
    """A recognized verdict string narrows to the matching Verdict member."""
    assert review_surface._as_verdict("flag") is Verdict.FLAG


@pytest.mark.unit
def test_as_verdict_non_string_value_rejected() -> None:
    """A non-string verdict value (corrupt-at-rest JSON) is rejected outright,
    without ever reaching the Verdict(value) enum lookup."""
    with pytest.raises(ValidationError, match="unrecognized verdict"):
        review_surface._as_verdict(None)


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
    blob = _blob()
    with pytest.raises(ValidationError):
        build_review_surface(
            status="in_review",
            storybook_id="s1",
            version=1,
            blob=blob,
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
def test_queue_item_carries_age_band_and_waiting_since() -> None:
    """UX-A3: the queue item surfaces triage metadata from the blob + version."""
    from datetime import UTC, datetime

    created = datetime(2026, 7, 1, tzinfo=UTC)
    item = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=1,
        blob={
            "title": "The Lantern",
            "metadata": {"age_band": "6-8"},
            "nodes": [{"id": "n1", "body": "Hi."}],
        },
        moderation_report=None,
        created_at=created,
    )
    assert item.age_band == "6-8"
    assert item.waiting_since == created


@pytest.mark.unit
def test_queue_item_age_band_absent_when_metadata_missing() -> None:
    """A blob with no metadata leaves age_band/waiting_since None (still valid)."""
    item = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=1,
        blob={"title": "T", "nodes": [{"id": "n1", "body": "Hi."}]},
        moderation_report=None,
    )
    assert item.age_band is None
    assert item.waiting_since is None


@pytest.mark.unit
def test_queue_item_carries_themes_and_content_flags() -> None:
    """The book-detail popover reads themes/content_flags straight off the blob."""
    item = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=1,
        blob={
            "title": "The Lantern",
            "metadata": {
                "age_band": "6-8",
                "themes": ["friendship", "courage"],
                "content_flags": {
                    "violence": "mild",
                    "scariness": "none",
                    "peril": "moderate",
                },
            },
            "nodes": [{"id": "n1", "body": "Hi."}],
        },
        moderation_report=None,
    )
    assert item.themes == ["friendship", "courage"]
    assert item.content_flags is not None
    assert item.content_flags.violence == "mild"
    assert item.content_flags.peril == "moderate"


@pytest.mark.unit
def test_queue_item_metadata_missing_returns_empty_themes_and_none_flags() -> None:
    """A blob with no metadata leaves themes empty and content_flags None."""
    item = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=1,
        blob={"title": "T", "nodes": [{"id": "n1", "body": "Hi."}]},
        moderation_report=None,
    )
    assert item.themes == []
    assert item.content_flags is None


@pytest.mark.unit
def test_queue_item_content_flags_invalid_shape_returns_none() -> None:
    """A content_flags dict that no longer matches the schema degrades to None
    rather than failing the whole queue row for a detail-only field."""
    item = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=1,
        blob={
            "title": "T",
            "metadata": {"content_flags": {"violence": "catastrophic"}},
            "nodes": [{"id": "n1", "body": "Hi."}],
        },
        moderation_report=None,
    )
    assert item.content_flags is None


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


@pytest.mark.unit
def test_content_summary_redacts_passages_and_counts_flags() -> None:
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=_report(),
        age_band="",
        policy=_DEFAULT_POLICY,
    )
    # flagged_count counts only surfaced findings: the n_start "safety" flag
    # clears the default (FLAG) threshold; the story-level "coherence" advisory
    # does not, and the n_end pass is dropped by build_review_surface already.
    assert summary.flagged_count == 1
    # Stage B3 (design doc 2.6): the guardian view merges every threshold-
    # surfaced finding into a story-level concern list, so the surfaced
    # n_start "safety" flag appears here too -- with a node_count, never a
    # node id or passage prose. The below-threshold coherence advisory is
    # still filtered out.
    assert len(summary.findings) == 1
    finding = summary.findings[0]
    assert finding.category == "safety"
    assert finding.verdict is Verdict.FLAG
    assert finding.message == "mild peril"
    assert finding.node_count == 1
    assert finding.concern is None
    assert finding.severity is None
    assert summary.screened is True
    assert summary.summary is not None
    assert summary.summary.soft_flag is True


@pytest.mark.unit
def test_content_summary_null_report_is_unscreened() -> None:
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=None,
        age_band="",
        policy=_DEFAULT_POLICY,
    )
    assert summary.screened is False
    assert summary.summary is None
    assert summary.flagged_count == 0
    assert summary.findings == []


@pytest.mark.unit
def test_queue_item_flagged_count_respects_noise_floor() -> None:
    """The queue's flagged_count is denoised exactly like the detail view.

    A report whose only finding is a below-floor ADVISORY yields
    flagged_count == 0 when a noise floor is supplied, but flagged_count > 0
    when the floor is skipped (admin_noise_floor=None), since the raw finding
    still exists and is not otherwise filtered.
    """
    noisy_only: dict[str, object] = {
        "findings": [
            {
                "stage": 0,
                "source": "openai",
                "category": "toxicity",
                "node_id": None,
                "verdict": "advisory",
                "score": 0.02,
                "message": "near-zero advisory noise",
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": False,
            "soft_flag": False,
            "repaired": False,
            "reviewer_independent": True,
        },
    }
    floored = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=1,
        blob={"nodes": []},
        moderation_report=noisy_only,
        admin_noise_floor=0.05,
    )
    assert floored.screened is True
    assert floored.flagged_count == 0

    unfloored = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=1,
        blob={"nodes": []},
        moderation_report=noisy_only,
        admin_noise_floor=None,
    )
    assert unfloored.flagged_count == 1


@pytest.mark.unit
def test_content_summary_rejects_corrupt_report() -> None:
    corrupt = {
        "findings": [
            {
                "stage": 1,
                "source": "not-a-real-source",
                "category": "safety",
                "node_id": None,
                "verdict": "flag",
                "score": None,
                "message": "m",
            }
        ],
        "summary": {},
    }
    blob = _blob()
    with pytest.raises(ValidationError):
        build_content_summary(
            storybook_id="s1",
            version=1,
            blob=blob,
            moderation_report=corrupt,
            age_band="",
            policy=_DEFAULT_POLICY,
        )


# Merged findings (design doc 2.2 item 3): one finding, many covered nodes.


def _merged_blob() -> dict[str, object]:
    return {
        "title": "The Lantern",
        "nodes": [
            {"id": "n_start", "body": "Start prose."},
            {"id": "n_fork", "body": "Fork prose."},
            {"id": "n_end", "body": "End prose."},
        ],
    }


def _merged_report() -> dict[str, object]:
    return {
        "findings": [
            {
                "stage": 2,
                "source": "llm_readability",
                "category": "reading_level",
                "node_id": "n_start",
                "verdict": "flag",
                "score": None,
                "message": "reading level above band (3 findings merged)",
                "severity": "medium",
                "node_ids": ["n_start", "n_fork", "n_end"],
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


@pytest.mark.unit
def test_merged_finding_fans_out_across_every_affected_node() -> None:
    """Every node in node_ids becomes its own flagged passage, with its prose.

    Grouping on node_id alone would render only n_start and leave n_fork and
    n_end looking clean to the human approver, who is the final gate under
    ADR-005. The merge exists to shorten the list, not to hide two thirds of
    the flagged prose.
    """
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=_merged_report(),
    )
    assert len(view.flagged_passages) == 3
    passages = {p.node_id: p for p in view.flagged_passages}
    assert passages["n_start"].prose == "Start prose."
    assert passages["n_fork"].prose == "Fork prose."
    assert passages["n_end"].prose == "End prose."
    # Every rendered passage carries the same single finding, unchanged.
    for passage in view.flagged_passages:
        assert len(passage.findings) == 1
        assert passage.findings[0].category == "reading_level"
    assert view.story_level_findings == []


@pytest.mark.unit
def test_queue_item_flagged_count_counts_every_merged_node() -> None:
    """The badge must match the passages the admin sees after clicking through."""
    item = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=1,
        blob=_merged_blob(),
        moderation_report=_merged_report(),
    )
    assert item.flagged_count == 3


@pytest.mark.unit
def test_content_summary_flagged_count_counts_every_merged_node() -> None:
    """The guardian-facing count follows the same fan-out."""
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=_merged_report(),
        age_band="6-8",
        policy=_DEFAULT_POLICY,
    )
    assert summary.flagged_count == 3


def _reviewer_outage_report() -> dict[str, object]:
    """A Stage-1 fail-safe structural finding covering all three nodes.

    Shaped exactly as ``stages.py::run_safety_stage`` emits it when the review
    model is unreachable or returns unparseable output: one collapsed finding
    naming every affected node in ``node_ids``, with ``structural`` set.
    """
    return {
        "findings": [
            {
                "stage": 1,
                "source": "pipeline",
                "category": "pipeline",
                "node_id": "n_start",
                "verdict": "flag",
                "score": None,
                "message": (
                    "reviewer unavailable or unparseable on 3 node(s); "
                    "defaulted to fail-safe"
                ),
                "severity": "high",
                "structural": True,
                "concern": "reviewer_unavailable",
                "node_ids": ["n_start", "n_fork", "n_end"],
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


@pytest.mark.unit
def test_structural_finding_with_node_ids_stays_story_level() -> None:
    """A reviewer outage is one story-level notice, never N passage rows.

    Stage A (8ca8d1b3) collapsed N per-node fail-safe findings into a single
    structural finding to stop an outage flooding the approver's queue. Stage
    B2 populated node_ids on that finding for ranking; routing it through the
    per-node fan-out on the strength of those ids would undo Stage A and put
    the identical notice back on every node.
    """
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=_reviewer_outage_report(),
    )
    assert view.flagged_passages == []
    assert len(view.story_level_findings) == 1
    surfaced = view.story_level_findings[0]
    assert surfaced.structural is True
    # node_ids must SURVIVE on the view: the admin detail panel and the
    # ranking stage both read it. Only the routing is guarded, not the data.
    assert surfaced.node_ids == ["n_start", "n_fork", "n_end"]
    # The structural guard and the ranker read the SAME view from two lists.
    # Hoisting the guard above `all_views.append(view)` would silently empty
    # structural_findings while every assertion above still passed, so pin the
    # second half here: routed out of the fan-out AND still ranked.
    assert view.structural_findings == [surfaced]


@pytest.mark.unit
def test_structural_finding_reaches_the_guardian_content_summary() -> None:
    """The outage notice must appear in findings, not just inflate the count.

    build_content_summary derives ``findings`` solely from
    story_level_findings while ``flagged_count`` counts passages too. A
    structural finding routed into the fan-out therefore lands in the worst
    possible place: it raises the guardian's "N flagged" badge to 3 while the
    sentence explaining WHY is absent from the list under it.
    """
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=_reviewer_outage_report(),
        age_band="6-8",
        policy=_DEFAULT_POLICY,
    )
    assert summary.flagged_count == 1
    assert len(summary.findings) == 1
    assert "reviewer unavailable" in summary.findings[0].message


@pytest.mark.unit
def test_content_summary_merges_fanned_finding_into_one_row_with_node_count() -> None:
    """A single admin finding fanned across 3 nodes is ONE guardian row.

    Design doc 2.6: the guardian never sees per-node rows or node ids, only a
    node_count. The 3 flagged_passages occurrences this finding produces on
    the admin surface must collapse to exactly one GuardianFinding here, with
    node_count == 3 (never 3 separate rows and never a bare node id).
    """
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=_merged_report(),
        age_band="6-8",
        policy=_DEFAULT_POLICY,
    )
    assert len(summary.findings) == 1
    finding = summary.findings[0]
    assert finding.category == "reading_level"
    assert finding.verdict is Verdict.FLAG
    assert finding.severity is FindingSeverity.MEDIUM
    assert finding.node_count == 3
    assert finding.concern is None
    assert not hasattr(finding, "node_id")
    assert not hasattr(finding, "node_ids")


@pytest.mark.unit
def test_merged_finding_with_null_node_ids_stays_story_level() -> None:
    """A whole-story merged finding has no nodes to fan out to."""
    report = _merged_report()
    findings = report["findings"]
    assert isinstance(findings, list)
    findings[0]["node_id"] = None
    findings[0]["node_ids"] = None
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=report,
    )
    assert view.flagged_passages == []
    assert len(view.story_level_findings) == 1


# Ranking, structural block, and low-ADVISORY toggle (Stage B3, design doc 2.6).


def _ranking_blob() -> dict[str, object]:
    return {
        "nodes": [
            {"id": "n1", "body": "One."},
            {"id": "n2", "body": "Two."},
            {"id": "n3", "body": "Three."},
            {"id": "n4", "body": "Four."},
        ]
    }


def _ranking_report() -> dict[str, object]:
    return {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n1",
                "verdict": "advisory",
                "score": None,
                "message": "low advisory noise",
                "severity": "low",
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n2",
                "verdict": "flag",
                "score": None,
                "message": "medium flag",
                "severity": "medium",
            },
            {
                "stage": 0,
                "source": "openai",
                "category": "toxicity",
                "node_id": "n1",
                "verdict": "block",
                "score": 0.9,
                "message": "hard block spans 3 nodes",
                "severity": "high",
                "node_ids": ["n1", "n2", "n3"],
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n4",
                "verdict": "flag",
                "score": None,
                "message": "high-severity single-node flag",
                "severity": "high",
            },
        ],
        "summary": {
            "count": 4,
            "hard_block": True,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


@pytest.mark.unit
def test_ranked_findings_orders_by_verdict_then_severity_then_node_count() -> None:
    """Verdict outranks severity outranks node count (design doc 2.6)."""
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_ranking_blob(),
        moderation_report=_ranking_report(),
    )
    messages = [f.message for f in view.ranked_findings]
    assert messages == [
        "hard block spans 3 nodes",  # BLOCK, high, 3 nodes
        "high-severity single-node flag",  # FLAG, high, 1 node
        "medium flag",  # FLAG, medium, 1 node
    ]
    # The low-severity advisory is diverted to its own bucket, never ranked.
    assert "low advisory noise" not in messages


@pytest.mark.unit
def test_low_advisory_findings_collapsed_behind_toggle() -> None:
    """A low-severity ADVISORY finding surfaces only in low_advisory_findings."""
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_ranking_blob(),
        moderation_report=_ranking_report(),
    )
    assert len(view.low_advisory_findings) == 1
    assert view.low_advisory_findings[0].message == "low advisory noise"
    assert view.low_advisory_findings[0].severity is FindingSeverity.LOW
    assert view.low_advisory_findings[0].verdict is Verdict.ADVISORY


@pytest.mark.unit
def test_ranking_is_stable_on_ties() -> None:
    """Two findings tied on (verdict, severity, node_count) keep report order."""
    tied_report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n1",
                "verdict": "flag",
                "score": None,
                "message": "first",
                "severity": "medium",
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n2",
                "verdict": "flag",
                "score": None,
                "message": "second",
                "severity": "medium",
            },
        ],
        "summary": {
            "count": 2,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_ranking_blob(),
        moderation_report=tied_report,
    )
    assert [f.message for f in view.ranked_findings] == ["first", "second"]


@pytest.mark.unit
def test_structural_findings_split_into_own_block() -> None:
    """A structural finding never appears in ranked_findings or low_advisory."""
    structural_report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "pipeline",
                "category": "structural",
                "node_id": None,
                "verdict": "flag",
                "score": None,
                "message": "reviewer unavailable",
                "severity": "high",
                "structural": True,
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n1",
                "verdict": "flag",
                "score": None,
                "message": "ordinary content flag",
                "severity": "medium",
            },
        ],
        "summary": {
            "count": 2,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_ranking_blob(),
        moderation_report=structural_report,
    )
    assert len(view.structural_findings) == 1
    assert view.structural_findings[0].message == "reviewer unavailable"
    assert [f.message for f in view.ranked_findings] == ["ordinary content flag"]
    assert view.low_advisory_findings == []


@pytest.mark.unit
def test_ranked_and_structural_findings_still_reject_pass_verdict() -> None:
    """The pass-verdict guard rejects a leak through the new B3 buckets too."""
    with pytest.raises(PydanticValidationError, match="pass-verdict"):
        ReviewSurfaceView(
            storybook_id="s1",
            version=1,
            status="in_review",
            blob={},
            screened=True,
            summary=None,
            flagged_passages=[],
            story_level_findings=[],
            ranked_findings=[
                FindingView(
                    stage=1,
                    source=Source.LLM_SAFETY,
                    category="safety",
                    node_id=None,
                    verdict=Verdict.PASS,
                    score=None,
                    message="clean",
                )
            ],
        )


# Validator findings (design doc 2.7 option (a)): read-only RL-13/PL-19 projection.


@pytest.mark.unit
def test_validator_findings_projects_only_rl13_and_pl19() -> None:
    validation_report: dict[str, object] = {
        "ok": False,
        "findings": [
            {
                "rule_id": "RL-13",
                "severity": "warning",
                "story_id": "s1",
                "node_id": "n1",
                "choice_id": None,
                "message": "RL-13 level: node 'n1' FK grade too high",
            },
            {
                "rule_id": "PL-19",
                "severity": "error",
                "story_id": "s1",
                "node_id": "n2",
                "choice_id": None,
                "message": "PL-19 words: node 'n2' over budget",
            },
            {
                "rule_id": "L1-7",
                "severity": "error",
                "story_id": "s1",
                "node_id": None,
                "choice_id": None,
                "message": "unrelated topology rule, must not surface here",
            },
        ],
    }
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_ranking_blob(),
        moderation_report=None,
        validation_report=validation_report,
    )
    rule_ids = {f.rule_id for f in view.validator_findings}
    assert rule_ids == {"RL-13", "PL-19"}
    by_rule = {f.rule_id: f for f in view.validator_findings}
    assert by_rule["RL-13"].node_id == "n1"
    assert by_rule["RL-13"].severity == "warning"
    assert by_rule["PL-19"].node_id == "n2"
    assert by_rule["PL-19"].severity == "error"


@pytest.mark.unit
def test_validator_findings_absent_report_is_empty() -> None:
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_ranking_blob(),
        moderation_report=None,
        validation_report=None,
    )
    assert view.validator_findings == []


# Guardian validator notes (Stage B3 follow-up, design doc 2.7 option (a)):
# a story-level, node-id-free RL-13/PL-19 aggregate on ContentSummaryView.


def _validation_report_two_rl13_one_pl19() -> dict[str, object]:
    return {
        "ok": False,
        "findings": [
            {
                "rule_id": "RL-13",
                "severity": "warning",
                "story_id": "s1",
                "node_id": "n_start",
                "choice_id": None,
                "message": "RL-13 level: node 'n_start' FK grade too high",
            },
            {
                "rule_id": "RL-13",
                "severity": "warning",
                "story_id": "s1",
                "node_id": "n_end",
                "choice_id": None,
                "message": "RL-13 level: node 'n_end' FK grade too high",
            },
            {
                "rule_id": "PL-19",
                "severity": "error",
                "story_id": "s1",
                "node_id": "n_start",
                "choice_id": None,
                "message": "PL-19 words: node 'n_start' over budget",
            },
        ],
    }


@pytest.mark.unit
def test_content_summary_validator_notes_aggregate_by_rule_and_severity() -> None:
    """Two RL-13 warnings plus one PL-19 error collapse to two counted rows."""
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=None,
        age_band="",
        policy=_DEFAULT_POLICY,
        validation_report=_validation_report_two_rl13_one_pl19(),
    )
    assert len(summary.validator_notes) == 2
    by_rule = {note.rule_id: note for note in summary.validator_notes}
    assert by_rule["RL-13"].severity == "warning"
    assert by_rule["RL-13"].count == 2
    assert by_rule["PL-19"].severity == "error"
    assert by_rule["PL-19"].count == 1


@pytest.mark.unit
def test_content_summary_validator_notes_absent_report_is_empty() -> None:
    """No validation_report at all (the default) yields an empty aggregate."""
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=None,
        age_band="",
        policy=_DEFAULT_POLICY,
    )
    assert summary.validator_notes == []


@pytest.mark.unit
def test_content_summary_validator_notes_malformed_report_degrades_to_empty() -> None:
    """A malformed validation_report degrades to omission, not an error.

    Mirrors ``_validator_findings``'s tolerant parsing: ``validation_report``
    is a read-only annex, so a bad shape must not fail the whole guardian
    summary the way a corrupt moderation_report does.
    """
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=None,
        age_band="",
        policy=_DEFAULT_POLICY,
        validation_report={"findings": "not-a-list"},
    )
    assert summary.validator_notes == []


def _assert_no_node_identifiers(value: object) -> None:
    """Recursively assert no node-identifying key/marker appears in a dumped payload.

    Walks a ``model_dump()``-style structure (nested dicts/lists/scalars) and
    fails if any dict key is ``node_id`` or ``node_ids``, which is the
    concrete, non-heuristic form of "the serialized guardian payload contains
    no node identifiers."
    """
    if isinstance(value, dict):
        for key, nested in value.items():
            assert key not in {"node_id", "node_ids"}, (
                f"node identifier key {key!r} leaked into guardian payload"
            )
            _assert_no_node_identifiers(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_no_node_identifiers(item)


@pytest.mark.unit
def test_content_summary_validator_notes_carry_no_node_identifiers() -> None:
    """The serialized ContentSummaryView never leaks a node id via validator_notes.

    Design doc 2.6/2.7(a): the guardian view is story-level only. Checks both
    the typed model (no ``node_id``/``message`` attribute on the note, mirroring
    ``test_content_summary_merges_fanned_finding_into_one_row_with_node_count``'s
    ``not hasattr`` pattern) and the fully serialized payload.
    """
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=None,
        age_band="",
        policy=_DEFAULT_POLICY,
        validation_report=_validation_report_two_rl13_one_pl19(),
    )
    assert len(summary.validator_notes) > 0
    for note in summary.validator_notes:
        assert not hasattr(note, "node_id")
        assert not hasattr(note, "node_ids")
        assert not hasattr(note, "message")
    _assert_no_node_identifiers(summary.model_dump())
    _assert_no_node_identifiers(summary.model_dump(mode="json"))
