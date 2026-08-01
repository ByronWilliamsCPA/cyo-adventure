"""Unit tests for the C3-4 review-surface projection."""

from __future__ import annotations

import pytest

from cyo_adventure.api import review_surface
from cyo_adventure.api.review_surface import (
    build_content_summary,
    build_review_queue_item,
    build_review_surface,
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
    # The advisory falls below the default threshold, so it is filtered out.
    assert summary.findings == []
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
