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
from cyo_adventure.api.schemas import (
    FindingView,
    GenerationMeasuresView,
    ReviewSurfaceView,
)
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
def test_as_source_perspective_string_returns_source() -> None:
    """A historical Perspective source string still parses.

    Google Perspective was retired as a Stage-0 signal source (ratified
    sunset) and run_classifiers no longer produces it, but old persisted
    JSONB reports still carry source='perspective' findings and must keep
    deserializing (Source.PERSPECTIVE stays in the enum for this reason).
    """
    assert review_surface._as_source("perspective") is Source.PERSPECTIVE


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
    """A reviewer outage is one row, never N passage rows.

    Stage A (8ca8d1b3) collapsed N per-node fail-safe findings into a single
    structural finding to stop an outage flooding the approver's queue. Stage
    B2 populated node_ids on that finding for ranking.

    Task 4 supersedes this specific fixture's original assertions: this
    report's ONE finding is structural and nothing else is present, so
    ``moderation_report_unusable`` is True (no genuine content judgment
    anywhere in the report) and ``build_review_surface`` replaces it with the
    generic ``report_unusable`` synthetic row, routed to ``structural_findings``
    only. The invariant this test still protects is unchanged: regardless of
    which collapse produced the single row, it is never fanned across
    n_start/n_fork/n_end.
    """
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=_reviewer_outage_report(),
    )
    assert view.report_unusable is True
    assert view.flagged_passages == []
    assert view.story_level_findings == []
    assert len(view.structural_findings) == 1
    surfaced = view.structural_findings[0]
    assert surfaced.structural is True
    assert surfaced.concern == "reviewer_unavailable"


def _structural_with_content_report() -> dict[str, object]:
    """One structural finding with ``node_ids`` plus one genuine content finding.

    Unlike ``_reviewer_outage_report`` (whose lone finding makes the whole
    report ``moderation_report_unusable``), the second finding here is a
    genuine content judgment (not structural, not a fail-safe message, not a
    ``MOCK_MODERATED_CONCERNS`` concern). ``moderation_report_unusable``
    therefore stays False, the Task 4 read-time collapse never fires, and the
    per-finding loop actually runs, which is what
    ``test_structural_finding_with_node_ids_stays_story_level`` (now a
    wholly-collapsed fixture) can no longer exercise.
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
                "message": "reviewer unavailable on 2 node(s)",
                "severity": "high",
                "structural": True,
                "concern": "reviewer_unavailable",
                "node_ids": ["n_start", "n_fork"],
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_end",
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


@pytest.mark.unit
def test_structural_finding_node_ids_survive_alongside_content_finding() -> None:
    """A genuinely-structural finding keeps its node_ids and skips the fan-out.

    This report stays outside the Task 4 collapse path (it carries one
    genuine content finding, so ``moderation_report_unusable`` is False),
    which exercises two things the collapsed
    ``test_structural_finding_with_node_ids_stays_story_level`` fixture no
    longer can: the structural finding's ``node_ids`` survive onto the view,
    and it appears in both ``structural_findings`` (derived from
    ``all_views``) and ``story_level_findings`` (appended directly in the
    loop), which together prove ``all_views.append(view)`` ran before the
    structural ``continue`` (review_surface.py's append-before-continue
    guard, ~line 183).
    """
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=_structural_with_content_report(),
    )
    assert view.report_unusable is False
    assert len(view.structural_findings) == 1
    structural = view.structural_findings[0]
    assert structural.structural is True
    assert structural.node_ids == ["n_start", "n_fork"]
    # Same FindingView instance in both buckets: proves the all_views append
    # ran before the structural guard's `continue` routed it to story_level.
    assert view.story_level_findings == [structural]
    assert [p.node_id for p in view.flagged_passages] == ["n_end"]
    assert view.flagged_passages[0].findings[0].message == "ordinary content flag"


@pytest.mark.unit
def test_structural_finding_reaches_the_guardian_content_summary() -> None:
    """A wholly-unusable report reaches the guardian as nothing, not a notice.

    Historically (Stage A/B2) this test asserted that a collapsed
    reviewer-outage finding surfaced in the guardian's content summary. Task 4
    changes that contract for a report with no genuine content judgment
    anywhere in it: ``build_review_surface`` routes the resulting
    ``report_unusable`` synthetic row into ``structural_findings`` only, never
    into ``story_level_findings``, and ``build_content_summary``'s
    ``findings``/``flagged_count`` are derived solely from
    ``story_level_findings``/``flagged_passages``. This is deliberate (Task 4's
    guardian coordination note): after Task 2's approval gate, no book can
    publish with an unusable report, so a guardian's content summary should
    never need to explain a pipeline outage; it reads exactly as if this
    version had raised nothing at all.
    """
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=_reviewer_outage_report(),
        age_band="6-8",
        policy=_DEFAULT_POLICY,
    )
    assert summary.flagged_count == 0
    assert summary.findings == []


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
def _pass_finding() -> FindingView:
    """A PASS-verdict finding, the thing _no_pass_verdict_leaks must reject."""
    return FindingView(
        stage=1,
        source=Source.LLM_SAFETY,
        category="safety",
        node_id=None,
        verdict=Verdict.PASS,
        score=None,
        message="clean",
    )


def _surface_with_buckets(
    *,
    ranked: list[FindingView] | None = None,
    structural: list[FindingView] | None = None,
    low_advisory: list[FindingView] | None = None,
) -> ReviewSurfaceView:
    """Build a minimal surface populating exactly one of the three B3 buckets."""
    return ReviewSurfaceView(
        storybook_id="s1",
        version=1,
        status="in_review",
        blob={},
        screened=True,
        summary=None,
        flagged_passages=[],
        story_level_findings=[],
        ranked_findings=ranked if ranked is not None else [],
        structural_findings=structural if structural is not None else [],
        low_advisory_findings=low_advisory if low_advisory is not None else [],
    )


@pytest.mark.unit
def test_every_new_b3_bucket_still_rejects_pass_verdict() -> None:
    """The pass-verdict guard rejects a leak through EACH new B3 bucket.

    _no_pass_verdict_leaks gained three `or any(...)` clauses in Stage B3, one
    per new bucket. Populating only ranked_findings leaves the other two at
    their [] defaults, so a single-bucket test passes even if the other two
    clauses were dropped or misspelled. Exercise all three independently.
    """
    leaked = _pass_finding()
    with pytest.raises(PydanticValidationError, match="pass-verdict"):
        _surface_with_buckets(ranked=[leaked])
    with pytest.raises(PydanticValidationError, match="pass-verdict"):
        _surface_with_buckets(structural=[leaked])
    with pytest.raises(PydanticValidationError, match="pass-verdict"):
        _surface_with_buckets(low_advisory=[leaked])


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


@pytest.mark.unit
@pytest.mark.parametrize(
    "stored_severity",
    [None, "", "warn", "critical", 3, ["error"]],
    ids=["missing", "empty", "typo", "unknown", "int", "list"],
)
def test_validator_finding_with_unreadable_severity_defaults_to_error(
    stored_severity: object,
) -> None:
    """An unreadable severity fails toward the LOUDER tier, never the calmer one.

    PL-19 spans both validator severities (per-node word wall is `error`,
    story-mean drift is `warning`), and this projection feeds the guardian's
    assignment screen through _validator_notes. Defaulting a corrupt value to
    `warning` would silently downgrade an error to advisory text under the
    exact control a guardian uses to hand a book to a child. Over-warning is
    recoverable; under-warning is not. Degrading must also never RAISE: the
    Literal on ValidatorFindingView.severity is normalized against, not
    validated against, or one bad row would 422 the whole review surface.
    """
    validation_report: dict[str, object] = {
        "ok": False,
        "findings": [
            {
                "rule_id": "PL-19",
                "severity": stored_severity,
                "node_id": "n1",
                "message": "PL-19: node word wall",
            }
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
    assert len(view.validator_findings) == 1
    assert view.validator_findings[0].severity == "error"


@pytest.mark.unit
def test_validator_finding_readable_warning_is_not_escalated() -> None:
    """The fail-loud default must not swallow a legitimately-lower severity.

    Pairs with the test above: escalating everything would make the `warning`
    tier unreachable and the guardian note meaningless.
    """
    validation_report: dict[str, object] = {
        "ok": False,
        "findings": [
            {
                "rule_id": "RL-13",
                "severity": "warning",
                "node_id": "n1",
                "message": "RL-13: story-mean drift",
            }
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
    assert view.validator_findings[0].severity == "warning"


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


# Guardian merge identity and bucket-ordering invariants (Stage B3 review
# follow-up). Both target branches that every pre-existing test passes through
# without discriminating, so an inverted condition would have shipped silently.


def _same_message_two_concerns_report() -> dict[str, object]:
    """Two findings identical in every merge-key field EXCEPT concern.

    Isolating one dimension is the point: if any other field differed, the
    test could not tell whether concern or that other field split the rows.
    """
    shared = {
        "stage": 1,
        "source": "llm_safety",
        "category": "safety",
        "verdict": "flag",
        "score": None,
        "message": "identical message",
        "severity": "medium",
    }
    return {
        "findings": [
            {**shared, "node_id": "n_start", "concern": "frightening_content"},
            {**shared, "node_id": "n_fork", "concern": "peril"},
            # And two carrying NO concern at all, identical except for
            # category, which isolates the other half of the fallback.
            {
                "stage": 3,
                "source": "llm_coherence",
                "category": "coherence",
                "node_id": None,
                "verdict": "flag",
                "score": None,
                "message": "no concern set",
            },
            {
                "stage": 3,
                "source": "llm_coherence",
                "category": "reading_level",
                "node_id": None,
                "verdict": "flag",
                "score": None,
                "message": "no concern set",
            },
        ],
        "summary": {
            "count": 4,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


@pytest.mark.unit
def test_guardian_merge_keys_on_concern_not_category() -> None:
    """Two concerns under one category stay two guardian rows.

    _guardian_group_key uses `concern if concern is not None else category`.
    Every other guardian test uses findings whose messages already differ, so
    they merge into distinct rows no matter which half of that expression is
    used, and inverting it to `category if ... else concern` would pass them
    all. Here the two findings are identical except for concern: keying on
    category alone collapses them into ONE row and hides a distinct safety
    concern from the adult deciding whether a child may read the book.
    """
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=_same_message_two_concerns_report(),
        age_band="6-8",
        policy=_DEFAULT_POLICY,
    )
    concerns = [f.concern for f in summary.findings]
    assert "frightening_content" in concerns
    assert "peril" in concerns
    # Four surfaced occurrences, four rows: two split by concern, two split
    # by the category fallback. Keying on category alone collapses the first
    # pair to one row and yields three.
    assert summary.flagged_count == 4
    assert len(summary.findings) == 4


@pytest.mark.unit
def test_guardian_merge_falls_back_to_category_when_concern_is_absent() -> None:
    """Concern-less findings still separate, because they key on category.

    The other half of the fallback. The two concern-less findings differ ONLY
    in category, so dropping the `else category` branch keys both on None and
    merges two distinct concerns into a single guardian row.
    """
    summary = build_content_summary(
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=_same_message_two_concerns_report(),
        age_band="6-8",
        policy=_DEFAULT_POLICY,
    )
    fallback = [f for f in summary.findings if f.concern is None]
    assert len(fallback) == 2
    assert {f.category for f in fallback} == {"coherence", "reading_level"}


@pytest.mark.unit
def test_structural_beats_low_advisory_when_a_finding_is_both() -> None:
    """A structural finding that is ALSO low+advisory belongs in structural.

    _rank_and_split checks `structural` first, then the low-advisory case.
    Every other fixture's structural finding is high severity with a flag
    verdict, so it can never match the low-advisory branch and swapping the
    two conditions passes the whole suite. This finding matches BOTH, so it
    discriminates: collapsing a pipeline failure behind the low-priority
    toggle would hide a reviewer outage from the approver by default.
    """
    report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "pipeline",
                "node_id": None,
                "verdict": "advisory",
                "score": None,
                "message": "reviewer unavailable on 2 nodes",
                "severity": "low",
                "structural": True,
            }
        ],
        "summary": None,
    }
    view = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_merged_blob(),
        moderation_report=report,
    )
    assert len(view.structural_findings) == 1
    assert view.structural_findings[0].structural is True
    assert view.low_advisory_findings == []
    assert view.ranked_findings == []


@pytest.mark.unit
def test_validator_finding_with_unreadable_message_says_so() -> None:
    """A corrupt message renders as an explicit note, not an empty cell.

    Closes the Copilot review point about blank rows. Dropping the finding
    entirely was the alternative; it was rejected because rule_id, severity,
    and node_id remain independently actionable, and silently discarding a
    validator signal is the worse failure on a safety-review surface.
    """
    validation_report: dict[str, object] = {
        "ok": False,
        "findings": [
            {
                "rule_id": "RL-13",
                "severity": "warning",
                "node_id": "n1",
                "message": {"unexpected": "shape"},
            }
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
    assert len(view.validator_findings) == 1
    finding = view.validator_findings[0]
    assert finding.message == "(RL-13: stored message unreadable)"
    # The readable fields survive: the row is still actionable.
    assert finding.rule_id == "RL-13"
    assert finding.severity == "warning"
    assert finding.node_id == "n1"


# ---------------------------------------------------------------------------
# Generation measures on the approval screen (R-2, partial)
# ---------------------------------------------------------------------------
#
# "So the human gate sees what the automated gate measured." Two of the three
# measures R-2 names are covered here: the fill rate against its floor, which
# is persisted on every generated version and shown nowhere, and a safety
# roll-up over the concerns the moderation gate actually raised. The third,
# sibling-gram overlap, has no request-path producer on this branch yet.
#
# Deliberately NOT surfaced: the deterministic gate's own `safety_flagged`.
# SAFE-14 is a Phase-2 stub that returns an empty finding list by
# construction (validator/safety.py), so that field is structurally always
# False, and putting it on an approval screen would read as "safety: clean"
# from a check that never ran.


def _validation_report(**overrides: object) -> dict[str, object]:
    """Build a persisted validation report carrying the fill-rate keys."""
    return {"ok": True, "findings": [], **overrides}


def _measures(
    *,
    report: dict[str, object] | None = None,
    validation_report: dict[str, object] | None = None,
) -> GenerationMeasuresView:
    """Project a surface and return only its generation-measures block.

    Typed rather than `object` so the assertions below are checked against the
    real view: with an `object` return every `measures.fill_rate` read is
    unchecked, and a renamed field would only surface at runtime.

    The block itself is always projected; it is the individual measurements
    that degrade to `None`. Asserting that here keeps the distinction honest
    and turns a regression that dropped the block into a named failure rather
    than an `AttributeError` inside whichever test ran first.
    """
    measures = build_review_surface(
        status="needs_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=report if report is not None else _report(),
        validation_report=validation_report,
    ).generation_measures
    assert measures is not None, "the measures block must always be projected"
    return measures


def test_generation_measures_persisted_rate_and_floor_reach_the_surface() -> None:
    """The rate is persisted on every generated version and shown nowhere."""
    measures = _measures(
        validation_report=_validation_report(fill_rate=0.82, fill_rate_floor=0.6)
    )
    assert measures.fill_rate == pytest.approx(0.82)
    assert measures.fill_rate_floor == pytest.approx(0.6)
    assert measures.fill_rate_downgrade is False


def test_generation_measures_downgrade_is_distinguishable_from_a_passing_rate() -> None:
    """A downgraded book routes to review for a reason the reviewer must see.

    ``fill_rate`` alone cannot carry this: the rate is stamped on every
    outcome that carries a book, breach or not, which is why the orchestrator
    stamps a separate key on the downgrade itself.
    """
    measures = _measures(
        validation_report=_validation_report(
            fill_rate=0.41, fill_rate_floor=0.6, fill_rate_downgrade=True
        )
    )
    assert measures.fill_rate == pytest.approx(0.41)
    assert measures.fill_rate_downgrade is True


def test_generation_measures_absent_validation_report_yields_no_fill_rate() -> None:
    """An imported or pre-floor version has no rate, which is not a rate of 0."""
    measures = _measures(validation_report=None)
    assert measures.fill_rate is None
    assert measures.fill_rate_floor is None
    assert measures.fill_rate_downgrade is False


def test_generation_measures_malformed_fill_rate_degrades_to_absent() -> None:
    """``validation_report`` is a read-only annex; a bad value must not 500."""
    measures = _measures(
        validation_report=_validation_report(fill_rate="0.82", fill_rate_floor=None)
    )
    assert measures.fill_rate is None
    assert measures.fill_rate_floor is None


def test_generation_measures_boolean_fill_rate_degrades_to_absent() -> None:
    """``True`` is an int in Python, and 1.0 would read as a perfect fill."""
    measures = _measures(validation_report=_validation_report(fill_rate=True))
    assert measures.fill_rate is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_generation_measures_non_finite_fill_rate_degrades_to_absent(
    bad: float,
) -> None:
    """A non-finite rate is a `float`, so a bare type check lets it through.

    The approval screen renders the rate as ``Math.round(rate * 100)``, which
    turns these into the literal strings "NaN%" and "Infinity%" beside a real
    measurement. An approver cannot tell that from a number the gate actually
    produced, so "not recorded" is the safer projection.
    """
    measures = _measures(validation_report=_validation_report(fill_rate=bad))
    assert measures.fill_rate is None


@pytest.mark.parametrize("bad", [82, 1.5, -0.1])
def test_generation_measures_out_of_range_fill_rate_degrades_to_absent(
    bad: float,
) -> None:
    """A rate persisted as a percentage renders as "8200%", not as an error.

    The unit-interval bound is what catches a producer that stamped ``82``
    where the reader expects ``0.82``. Without it the value is a perfectly
    ordinary float and reaches the screen unchallenged.
    """
    measures = _measures(validation_report=_validation_report(fill_rate=bad))
    assert measures.fill_rate is None


def test_generation_measures_genuine_zero_fill_rate_is_kept() -> None:
    """Zero is a real, and alarming, measurement: nothing in the book filled.

    It is also the value most at risk from a falsy guard, and it is precisely
    the reading an approver most needs to see, so it must survive the range
    check that rejects the corrupt values above.
    """
    measures = _measures(
        validation_report=_validation_report(fill_rate=0.0, fill_rate_floor=0.6)
    )
    assert measures.fill_rate == pytest.approx(0.0)
    assert measures.fill_rate is not None


def test_safety_concerns_are_counted_for_the_approver() -> None:
    """The roll-up answers "what did the gate object to", not "how many rows"."""
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
                "concern": "frightening_content",
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_end",
                "verdict": "flag",
                "score": None,
                "message": "mild peril",
                "concern": "frightening_content",
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": None,
                "verdict": "advisory",
                "score": None,
                "message": "a knife is described",
                "concern": "real_world_danger",
            },
        ]
    }
    measures = _measures(report=report)
    assert [(c.concern, c.count) for c in measures.safety_concerns] == [
        ("frightening_content", 2),
        ("real_world_danger", 1),
    ]


def test_a_pipeline_concern_is_not_counted_as_a_safety_concern() -> None:
    """ "The reviewer was unavailable" is not something the book did.

    Structural findings describe the pipeline, and counting them beside
    content concerns would tell an approver a story raised a safety concern
    when what actually happened is that a backend was down.
    """
    report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "pipeline",
                "category": "reviewer_unavailable",
                "node_id": None,
                "verdict": "flag",
                "score": None,
                "message": "reviewer unavailable on 12 nodes",
                "concern": "reviewer_unavailable",
                "structural": True,
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_start",
                "verdict": "flag",
                "score": None,
                "message": "mild peril",
                "concern": "cruelty",
            },
        ]
    }
    measures = _measures(report=report)
    assert [c.concern for c in measures.safety_concerns] == ["cruelty"]


def test_a_clean_book_reports_no_safety_concerns() -> None:
    """An empty list, not an absent block: "nothing raised" is a real answer."""
    assert _measures(report={"findings": []}).safety_concerns == []


def test_a_clean_check_is_not_counted_as_a_concern() -> None:
    """A ``pass`` verdict records that a check ran, not that it objected."""
    report: dict[str, object] = {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n_start",
                "verdict": "pass",
                "score": None,
                "message": "clean",
                "concern": "frightening_content",
            }
        ]
    }
    assert _measures(report=report).safety_concerns == []


# ---------------------------------------------------------------------------
# Task 4: read-time collapse of unusable reports + tiered distinct counts
# ---------------------------------------------------------------------------


def _fail_safe_report(node_ids: list[str]) -> dict[str, object]:
    """A report whose findings are all fail-safe artifacts, none genuine.

    Shaped like a legacy pre-Stage-A report: no ``structural``/``concern``
    keys, detected purely by the fail-safe message substring (moderation/
    report.py::moderation_report_unusable).
    """
    return {
        "findings": [
            {
                "stage": "review",
                "source": "llm_safety",
                "category": "llm_safety",
                "node_id": nid,
                "verdict": "flag",
                "score": None,
                "message": "unknown verdict; defaulted to fail-safe",
            }
            for nid in node_ids
        ],
        "aggregate": {"nodes_reviewed": len(node_ids), "pass_counts": {}},
        "summary": {
            "count": len(node_ids),
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": False,
        },
    }


@pytest.mark.unit
def test_unusable_report_collapses_to_one_structural_finding() -> None:
    """A report carrying only fail-safe artifacts renders as one clear notice.

    Without this collapse, N fail-safe findings would flood the admin surface
    as N separate flagged passages, each telling the approver nothing beyond
    "the reviewer did not run here" -- noise that crowds out any genuine
    signal and makes an unusable report look like a busy, reviewed one.
    """
    surface = build_review_surface(
        status="in_review",
        storybook_id="s1",
        version=1,
        blob=_blob(),
        moderation_report=_fail_safe_report(["n1", "n2", "n3"]),
    )
    assert surface.report_unusable is True
    assert surface.flagged_passages == []
    assert len(surface.structural_findings) == 1
    only = surface.structural_findings[0]
    assert only.structural is True
    assert only.concern == "reviewer_unavailable"


@pytest.mark.unit
def test_unusable_report_queue_item_counts() -> None:
    """The queue item mirrors the surface: unusable, zero flags, zero tiers."""
    item = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=1,
        blob=_blob(),
        moderation_report=_fail_safe_report(["n1", "n2", "n3"]),
    )
    assert item.report_unusable is True
    assert item.flagged_count == 0
    assert (item.block_findings, item.flag_findings, item.advisory_findings) == (
        0,
        0,
        0,
    )


def _mixed_tier_blob() -> dict[str, object]:
    return {
        "title": "Three Nodes",
        "nodes": [
            {"id": "a", "body": "A prose."},
            {"id": "b", "body": "B prose."},
            {"id": "c", "body": "C prose."},
        ],
    }


def _mixed_tier_report() -> dict[str, object]:
    """One merged flag spanning three nodes, one block, two advisories.

    A genuinely usable report (no fail-safe messages, independent reviewer),
    so ``moderation_report_unusable`` stays False and the tiered-count logic
    is exercised on its own.
    """
    return {
        "findings": [
            {
                "stage": 2,
                "source": "llm_readability",
                "category": "reading_level",
                "node_id": "a",
                "verdict": "flag",
                "score": None,
                "message": "reading level above band (3 findings merged)",
                "severity": "medium",
                "node_ids": ["a", "b", "c"],
            },
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": None,
                "verdict": "block",
                "score": None,
                "message": "hard block",
            },
            {
                "stage": 3,
                "source": "llm_coherence",
                "category": "coherence",
                "node_id": None,
                "verdict": "advisory",
                "score": None,
                "message": "advisory one",
            },
            {
                "stage": 3,
                "source": "llm_engagement",
                "category": "engagement",
                "node_id": None,
                "verdict": "advisory",
                "score": None,
                "message": "advisory two",
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
def test_tiered_counts_are_distinct_findings_not_occurrences() -> None:
    """block/flag/advisory counts distinct findings, not fanned-out occurrences.

    One merged flag spanning 3 nodes + one block + two advisories must report
    flag_findings == 1 (distinct), not 3 (occurrences). flagged_count keeps
    counting occurrences: 3 passage cards from the merged flag's fan-out, plus
    the 3 story-level findings (the block and both advisories carry no node
    id).
    """
    item = build_review_queue_item(
        storybook_id="s1",
        status="in_review",
        version=1,
        blob=_mixed_tier_blob(),
        moderation_report=_mixed_tier_report(),
    )
    assert (item.block_findings, item.flag_findings, item.advisory_findings) == (
        1,
        1,
        2,
    )
    assert item.flagged_count == 6
