"""Unit tests for moderation finding aggregation and serialization."""

from __future__ import annotations

from typing import cast
from unittest.mock import ANY, call, patch

import pytest

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.moderation import report as report_module
from cyo_adventure.moderation.report import (
    CONCERN_TAXONOMY,
    FAIL_SAFE_MESSAGE_SUBSTRING,
    FailSafeScope,
    Finding,
    FindingSeverity,
    ModerationReport,
    SevereFindingCounts,
    Source,
    Verdict,
    legacy_hidden_fail_safe_node_counts,
    moderation_report_unusable,
    report_drops_pass_findings,
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

    def test_non_dict_report_is_unusable(self) -> None:
        """A top-level JSONB value that isn't even a mapping fails closed."""
        assert (
            moderation_report_unusable(cast("dict[str, object]", ["not", "a", "dict"]))
            is True
        )

    def test_empty_dict_report_is_unusable(self) -> None:
        """A report with no ``findings`` key at all fails closed, not open."""
        assert moderation_report_unusable({}) is True

    def test_none_findings_value_is_unusable(self) -> None:
        """A ``findings`` key present but ``None`` fails closed."""
        assert moderation_report_unusable({"findings": None}) is True

    def test_non_list_findings_value_is_unusable(self) -> None:
        """A corrupt, non-list ``findings`` value fails closed."""
        assert moderation_report_unusable({"findings": "corrupt"}) is True

    def test_clean_report_is_usable(self) -> None:
        """A well-formed empty findings list on an independent report is a
        genuine all-clear, not the malformed shape the tests above cover.
        """
        assert moderation_report_unusable(self._report([])) is False

    def test_empty_findings_without_summary_is_unusable(self) -> None:
        """An empty findings list with NO summary key is not a genuine
        all-clear: nothing evidences an independent reviewer actually ran.
        """
        assert moderation_report_unusable({"findings": []}) is True

    def test_empty_findings_with_non_mapping_summary_is_unusable(self) -> None:
        """An empty findings list with a corrupt, non-mapping summary fails
        closed rather than treating the report as clean.
        """
        assert (
            moderation_report_unusable({"findings": [], "summary": "corrupt"}) is True
        )

    def test_empty_findings_missing_reviewer_independent_key_is_unusable(
        self,
    ) -> None:
        """An empty findings list with a summary that omits
        ``reviewer_independent`` entirely fails closed: absence of the key is
        not evidence of independence.
        """
        report = {"findings": [], "summary": {"count": 0, "hard_block": False}}
        assert moderation_report_unusable(report) is True

    def test_empty_dict_finding_entry_is_unusable(self) -> None:
        """A finding entry with no keys at all must not rescue the report.

        Before the verdict-recognizer, an entry matching none of the three
        artifact shapes (structural/concern/fail-safe-message) fell through
        the loop's ``continue`` chain to the trailing ``return False``,
        marking the whole report usable on the strength of a finding that
        proves nothing.
        """
        assert moderation_report_unusable(self._report([{}])) is True

    def test_finding_entry_with_no_recognizable_shape_is_unusable(self) -> None:
        """A truncated finding entry (missing ``verdict``) does not rescue
        the report even when it also fails to match any artifact shape.
        """
        entry = {"message": "something", "score": 0.5}
        assert moderation_report_unusable(self._report([entry])) is True

    def test_concern_only_mock_marker_without_structural_flag_is_unusable(
        self,
    ) -> None:
        """A finding recognized solely by its concern is still a pipeline
        artifact, in isolation from the ``structural`` and fail-safe-message
        arms.

        Neither ``structural`` nor the fail-safe message substring is present
        on this finding; only ``concern`` is a MOCK_MODERATED_CONCERNS
        member, so this exercises that OR-arm on its own.
        """
        finding = self._fail_safe_finding(
            message="mock reviewer flagged this passage",
            concern="mock_reviewer_active",
        )
        assert "structural" not in finding
        assert moderation_report_unusable(self._report([finding])) is True

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

    def test_pre_stage_a_legacy_report_is_unusable_via_message_substring_only(
        self,
    ) -> None:
        """AL-624: pin the message substring as the sole live detection arm
        for a report shaped exactly like a pre-2026-07-30 mock run stored one.

        Both the "structural" key and the "reviewer_independent: False"
        stamp were introduced by ``_stamp_mock_reviewer`` (8ca8d1b3,
        2026-07-30, PR #496); the 12 in-review books produced by the
        2026-07-21 incident predate that commit and so carry NEITHER. The
        distinguishing signal for that legacy corpus has to come from the
        finding's own content (the fail-safe message literal), never from
        field presence or recency (AL-624's own conclusion). This fixture
        therefore omits ``structural``, omits ``concern``, and sets
        ``reviewer_independent: True`` in the summary (a legacy row predates
        the stamp; it was never marked False), so every OTHER arm of
        ``moderation_report_unusable`` is inert and only the
        ``FAIL_SAFE_MESSAGE_SUBSTRING`` match can catch it.

        A future rename of ``FAIL_SAFE_MESSAGE_SUBSTRING`` or of the message
        text ``moderation/stages.py`` actually emits
        (``UNKNOWN_VERDICT_FAIL_SAFE_MESSAGE`` /
        ``PARSE_FAILED_FAIL_SAFE_MESSAGE``) without updating the other in
        lockstep breaks this test, not the legacy corpus silently.
        """
        legacy_finding: dict[str, object] = {
            "stage": 1,
            "source": "llm_safety",
            "category": "llm_safety",
            "node_id": "n1",
            "verdict": "flag",
            "score": None,
            "message": "unknown verdict; defaulted to fail-safe",
        }
        assert "structural" not in legacy_finding
        assert "concern" not in legacy_finding
        assert FAIL_SAFE_MESSAGE_SUBSTRING in cast("str", legacy_finding["message"])
        report = self._report([legacy_finding], independent=True)
        assert moderation_report_unusable(report) is True


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

    def test_empty_findings_returns_zero_counts(self) -> None:
        """A well-formed empty findings list (an already-validated clean
        report) legitimately returns SevereFindingCounts(0, 0).
        """
        assert severe_finding_counts({"findings": []}) == SevereFindingCounts(0, 0)

    def test_none_report_raises(self) -> None:
        """None is a shape moderation_report_unusable would have rejected;
        reaching severe_finding_counts with it means the ordering invariant
        (moderation_report_unusable must run first) was violated, and this
        must fail loudly rather than silently return (0, 0).
        """
        with pytest.raises(BusinessLogicError):
            severe_finding_counts(None)

    def test_non_dict_report_raises(self) -> None:
        # The cast is hoisted out of the raises block so the block invokes
        # exactly one call (Sonar S5778): otherwise a BusinessLogicError from
        # the cast itself would satisfy the assertion just as well as one from
        # severe_finding_counts, which is the behaviour under test.
        not_a_dict = cast("dict[str, object]", "also not a dict")
        with pytest.raises(BusinessLogicError):
            severe_finding_counts(not_a_dict)

    def test_non_list_findings_raises(self) -> None:
        with pytest.raises(BusinessLogicError):
            severe_finding_counts({"findings": "corrupt"})

    def test_missing_findings_key_raises(self) -> None:
        with pytest.raises(BusinessLogicError):
            severe_finding_counts({})

    def test_high_severity_advisory_does_not_gate(self) -> None:
        # Advisories never gate (SOP contract); a stray severity=high on an
        # advisory must not force an override reason at approval.
        report = {
            "findings": [{"verdict": "advisory", "severity": "high", "message": "a"}]
        }
        assert severe_finding_counts(report) == (0, 0)


class TestLegacyHiddenFailSafeNodeCounts:
    """Per-source coverage for LEGACY reports that are only PARTIALLY fail-safe.

    ``moderation_report_unusable`` answers a whole-report question and stops
    at the first genuine finding, so a report where one stage judged every
    node and another stage defaulted to fail-safe on most of them reads as
    fully usable. Production carries exactly that shape: of the five books the
    first census called "genuinely moderated", four have it (the fifth,
    ``sk_clover_butterfly``, has zero fail-safe nodes). Their ``llm_safety``
    stage returned real verdicts throughout while ``llm_readability`` fell
    back to ``unknown verdict; defaulted to fail-safe`` on up to 88% of their
    nodes. These counts are what makes that unreviewed remainder countable
    rather than invisible.

    Every report in this class is hand-built in the PRE-``0396507b`` shape,
    where PASS findings were persisted as rows. That is the only shape this
    predicate can read, and
    ``test_round_trip_through_to_dict_finds_nothing_and_logs_the_blind_spot``
    is the control that says so out loud.
    """

    def test_fully_reviewed_report_counts_nothing(self) -> None:
        report = {
            "findings": [
                {
                    "source": "llm_safety",
                    "node_id": "n1",
                    "verdict": "flag",
                    "message": "too scary",
                }
            ]
        }
        assert legacy_hidden_fail_safe_node_counts(report) == {}

    def test_fail_safe_nodes_are_counted_per_source(self) -> None:
        report = {
            "findings": [
                {
                    "source": "llm_safety",
                    "node_id": "n1",
                    "verdict": "flag",
                    "message": "too scary",
                },
                {
                    "source": "llm_readability",
                    "node_id": "n1",
                    "verdict": "pass",
                    "message": FAIL_SAFE_MESSAGE_SUBSTRING,
                },
                {
                    "source": "llm_readability",
                    "node_id": "n2",
                    "verdict": "pass",
                    "message": "unknown verdict; defaulted to fail-safe",
                },
            ]
        }
        assert legacy_hidden_fail_safe_node_counts(report) == {
            "llm_readability": FailSafeScope(nodes=2, whole_story=False)
        }

    def test_pass_verdict_does_not_hide_a_fail_safe_row(self) -> None:
        # The production shape: the stored verdict is "pass", which the
        # review surface filters out before rendering. If this predicate
        # keyed off the verdict rather than the message it would agree with
        # that filter and the row would stay invisible.
        report = {
            "findings": [
                {
                    "source": "llm_readability",
                    "node_id": "n1",
                    "verdict": "pass",
                    "message": "verdict parse failed; defaulted to fail-safe",
                }
            ]
        }
        assert legacy_hidden_fail_safe_node_counts(report) == {
            "llm_readability": FailSafeScope(nodes=1, whole_story=False)
        }

    def test_same_node_twice_counts_once(self) -> None:
        report = {
            "findings": [
                {
                    "source": "llm_readability",
                    "node_id": "n1",
                    "verdict": "pass",
                    "message": FAIL_SAFE_MESSAGE_SUBSTRING,
                },
                {
                    "source": "llm_readability",
                    "node_id": "n1",
                    "verdict": "pass",
                    "message": FAIL_SAFE_MESSAGE_SUBSTRING,
                },
            ]
        }
        assert legacy_hidden_fail_safe_node_counts(report) == {
            "llm_readability": FailSafeScope(nodes=1, whole_story=False)
        }

    def test_merged_finding_counts_every_node_it_covers(self) -> None:
        # node_id names only the FIRST covered node; counting it alone would
        # under-report a merged fail-safe finding by its whole group.
        report = {
            "findings": [
                {
                    "source": "llm_readability",
                    "node_id": "n1",
                    "node_ids": ["n1", "n2", "n3"],
                    "verdict": "pass",
                    "message": FAIL_SAFE_MESSAGE_SUBSTRING,
                }
            ]
        }
        assert legacy_hidden_fail_safe_node_counts(report) == {
            "llm_readability": FailSafeScope(nodes=3, whole_story=False)
        }

    def test_structural_finding_is_not_counted_again(self) -> None:
        # A collapsed structural fail-safe finding already survives the
        # surface's PASS filter and renders on its own; counting it here too
        # would render the same outage twice.
        report = {
            "findings": [
                {
                    "source": "pipeline",
                    "node_id": "n1",
                    "node_ids": ["n1", "n2"],
                    "verdict": "pass",
                    "structural": True,
                    "concern": "reviewer_unavailable",
                    "message": FAIL_SAFE_MESSAGE_SUBSTRING,
                }
            ]
        }
        assert legacy_hidden_fail_safe_node_counts(report) == {}

    def test_fail_safe_finding_with_no_node_is_whole_story_not_one_node(self) -> None:
        # A nodeless finding is how the two whole-story soft stages (coherence,
        # engagement) fail safe: they judge the story as a unit, so the outage
        # covers everything. Reporting it as nodes=1 understated a total stage
        # outage as "left 1 node unjudged" on the approver's surface.
        report = {
            "findings": [
                {
                    "source": "llm_safety",
                    "node_id": None,
                    "verdict": "pass",
                    "message": FAIL_SAFE_MESSAGE_SUBSTRING,
                }
            ]
        }
        assert legacy_hidden_fail_safe_node_counts(report) == {
            "llm_safety": FailSafeScope(nodes=0, whole_story=True)
        }

    def test_source_falls_back_to_category_then_unknown(self) -> None:
        report = {
            "findings": [
                {
                    "category": "llm_readability",
                    "node_id": "n1",
                    "verdict": "pass",
                    "message": FAIL_SAFE_MESSAGE_SUBSTRING,
                },
                {
                    "node_id": "n2",
                    "verdict": "pass",
                    "message": FAIL_SAFE_MESSAGE_SUBSTRING,
                },
            ]
        }
        assert legacy_hidden_fail_safe_node_counts(report) == {
            "llm_readability": FailSafeScope(nodes=1, whole_story=False),
            "unknown": FailSafeScope(nodes=1, whole_story=False),
        }

    @pytest.mark.parametrize(
        "report",
        [None, {}, {"findings": None}, {"findings": "nope"}, {"findings": []}],
        ids=["none", "empty", "null-findings", "non-list", "empty-list"],
    )
    def test_malformed_or_empty_reports_count_nothing(self, report: object) -> None:
        # These shapes are moderation_report_unusable's job to fail closed
        # on; this predicate answers the narrower "which nodes did a stage
        # skip" question and must not double as a second corruption gate.
        assert (
            legacy_hidden_fail_safe_node_counts(
                cast("dict[str, object] | None", report)
            )
            == {}
        )

    def test_non_mapping_finding_entry_is_skipped(self) -> None:
        report = {"findings": ["nope", 7, None]}
        assert (
            legacy_hidden_fail_safe_node_counts(cast("dict[str, object]", report)) == {}
        )

    @pytest.mark.parametrize("verdict", ["flag", "block"], ids=["flag", "block"])
    def test_gating_fail_safe_row_is_not_counted(self, verdict: str) -> None:
        # Stage 1 safety fails safe to FLAG, so its fail-safe rows gate,
        # clear the review surface's PASS filter, and already render as
        # flagged passages. Counting them here would describe one outage
        # twice: once per passage and once in aggregate.
        report = {
            "findings": [
                {
                    "source": "llm_safety",
                    "node_id": "n1",
                    "verdict": verdict,
                    "message": "verdict parse failed; defaulted to fail-safe",
                }
            ]
        }
        assert legacy_hidden_fail_safe_node_counts(report) == {}

    def test_row_with_no_verdict_is_not_counted(self) -> None:
        # Absent is not PASS. A row with no verdict at all never reaches this
        # predicate from the API in the first place: `_as_verdict` raises a 422
        # while parsing the stored report, so a missing verdict is rejected at
        # the boundary rather than counted here. (This is NOT
        # moderation_report_unusable's doing: that predicate answers a
        # whole-report question and a single genuine finding elsewhere makes it
        # return False.)
        report = {
            "findings": [
                {
                    "source": "llm_readability",
                    "node_id": "n1",
                    "message": FAIL_SAFE_MESSAGE_SUBSTRING,
                }
            ]
        }
        assert legacy_hidden_fail_safe_node_counts(report) == {}

    def test_round_trip_through_to_dict_finds_nothing_and_logs_the_blind_spot(
        self,
    ) -> None:
        """A report the CURRENT pipeline writes carries no readable evidence.

        Every other test in this class hand-builds the persisted dict with
        ``"verdict": "pass"`` rows, which is the pre-``0396507b`` shape. This
        one is the round trip: build a real ``ModerationReport`` in which both
        whole-story soft stages fail-safed exactly as ``stages.py`` emits them
        (``fail_safe=Verdict.PASS``, ``node_id=None``), persist it through the
        real ``to_dict()``, and read it back.

        The answer is ``{}``, the same value as "nothing fell back", because
        ``to_dict`` strips PASS rows. That is the whole reason this predicate
        is named ``legacy_``. Asserting it here means the limit is a pinned,
        visible property of the code rather than something a future reader
        rediscovers from a book that rendered clean. The log is what makes the
        empty answer distinguishable from a real all-clear at runtime.
        """
        report = ModerationReport()
        report.add(
            Finding(
                stage=1,
                source=Source.LLM_SAFETY,
                category="violence",
                node_id="n1",
                verdict=Verdict.FLAG,
                score=0.9,
                message="a genuine judgment, so the report is USABLE",
            )
        )
        for source in (Source.LLM_COHERENCE, Source.LLM_ENGAGEMENT):
            report.add(
                Finding(
                    stage=3,
                    source=source,
                    category=source.value,
                    node_id=None,
                    verdict=Verdict.PASS,
                    message=f"unknown verdict; {FAIL_SAFE_MESSAGE_SUBSTRING}",
                )
            )

        persisted = report.to_dict()

        # Precondition: the two fail-safe rows really were dropped, and the
        # report really does read as usable. Without this the assertion below
        # could pass for the wrong reason.
        assert persisted["findings"] == [
            f.to_dict() for f in report.findings if f.verdict is not Verdict.PASS
        ]
        assert moderation_report_unusable(persisted) is False
        assert report_drops_pass_findings(persisted) is True

        with patch.object(report_module, "_logger") as logger:
            counts = legacy_hidden_fail_safe_node_counts(persisted)

        assert counts == {}
        assert logger.info.call_args_list == [
            call(
                "hidden_fail_safe_scan_blind_on_modern_report",
                reason=ANY,
                follow_up="UW-C390",
            )
        ]

    def test_legacy_shaped_report_does_not_log_the_blind_spot(self) -> None:
        # The negative control for the test above: a report with no
        # aggregate.pass_counts is a legacy report, its empty result is a
        # genuine all-clear, and logging there would cry wolf on every
        # fully-reviewed book.
        report = {"findings": [], "aggregate": {"nodes_reviewed": 3}}
        with patch.object(report_module, "_logger") as logger:
            assert legacy_hidden_fail_safe_node_counts(report) == {}
        logger.info.assert_not_called()


class TestReportDropsPassFindings:
    """The discriminator between the two persisted report shapes."""

    def test_current_to_dict_output_is_recognized(self) -> None:
        assert report_drops_pass_findings(ModerationReport().to_dict()) is True

    @pytest.mark.parametrize(
        "report",
        [
            None,
            {},
            {"aggregate": None},
            {"aggregate": "nope"},
            {"aggregate": {}},
            {"aggregate": {"nodes_reviewed": 3}},
            {"aggregate": {"pass_counts": None}},
            {"aggregate": {"pass_counts": []}},
        ],
        ids=[
            "none",
            "empty",
            "null-aggregate",
            "non-mapping-aggregate",
            "empty-aggregate",
            "legacy-aggregate",
            "null-pass-counts",
            "non-mapping-pass-counts",
        ],
    )
    def test_absent_or_malformed_pass_counts_is_not_the_modern_shape(
        self, report: object
    ) -> None:
        # Presence of a well-formed mapping is the only positive signal. Every
        # other shape is treated as legacy, which is the conservative
        # direction: it suppresses the blind-spot log rather than claiming a
        # report is modern on evidence that is not there.
        assert (
            report_drops_pass_findings(cast("dict[str, object] | None", report))
            is False
        )

    def test_an_empty_pass_counts_mapping_still_counts_as_modern(self) -> None:
        # to_dict always writes the key, even when no stage returned PASS, so
        # an empty mapping is a modern report that happened to have no PASS
        # rows, not a legacy one.
        assert report_drops_pass_findings({"aggregate": {"pass_counts": {}}}) is True
