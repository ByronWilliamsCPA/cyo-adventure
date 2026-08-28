"""Unit tests for moderation finding aggregation and serialization."""

from __future__ import annotations

from typing import ClassVar, cast
from unittest.mock import ANY, call, patch

import pytest

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.moderation import report as report_module
from cyo_adventure.moderation.pipeline import _stamp_mock_reviewer
from cyo_adventure.moderation.report import (
    CONCERN_TAXONOMY,
    COVERAGE_GAP_CONCERNS,
    FAIL_SAFE_MESSAGE_SUBSTRING,
    MOCK_MODERATED_CONCERNS,
    FailSafeScope,
    Finding,
    FindingSeverity,
    ModerationReport,
    SevereFindingCounts,
    Source,
    Verdict,
    legacy_hidden_fail_safe_node_counts,
    moderation_coverage_gap,
    moderation_coverage_incomplete,
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


def _provenance() -> dict[str, object]:
    """A well-formed reviewer provenance block, for reports that must record one.

    ``moderation_report_unusable`` gates a post-``coverage_complete`` report
    with no recorded reviewer (see that predicate's docstring), so any test
    fixture built via ``ModerationReport()`` that expects to read as usable
    now needs one.
    """
    return {
        "provider": "openrouter",
        "model": "test-model",
        "endpoint": [],
        "temperature": 0.0,
        "batch_size": 8,
    }


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


class TestBlocksRelease:
    """The in-memory counterpart to :func:`moderation_coverage_incomplete`.

    ``has_hard_block`` is ``any(verdict is BLOCK)``, so a node the reviewer
    never saw cannot contribute a BLOCK; the Stage-1 fail-safe records FLAG
    instead. That makes an unreviewed batch read as a soft flag, which the
    re-moderation sweep reports as "review when convenient" and exits 0 on.
    ``blocks_release`` is the predicate that closes that fail-open, and it must
    stay distinct from ``has_hard_block``, which also drives cost
    short-circuits between stages.
    """

    @staticmethod
    def _gap(concern: str = "reviewer_unavailable") -> Finding:
        return Finding(
            stage=1,
            source=Source.PIPELINE,
            category="pipeline",
            node_id="n1",
            verdict=Verdict.FLAG,
            message="reviewer unavailable or unparseable on 8 node(s)",
            structural=True,
            concern=concern,
            severity=FindingSeverity.HIGH,
            node_ids=("n1", "n2"),
        )

    def test_a_coverage_gap_blocks_release_without_a_hard_block(self) -> None:
        report = ModerationReport()
        report.add(self._gap())
        assert report.has_hard_block is False, (
            "precondition: the fail-safe records FLAG, so the block predicate "
            "cannot see an unreviewed node; that is the fail-open being closed"
        )
        assert report.has_coverage_gap is True
        assert report.blocks_release is True

    def test_a_classifier_unavailable_gap_blocks_release_too(self) -> None:
        """Stage-0 coverage shortfalls gate the same way Stage-1 ones do.

        Before ``classifier_unavailable`` joined ``COVERAGE_GAP_CONCERNS``,
        ``classifiers.py::_incomplete_coverage_finding`` built its ``Finding``
        with no ``concern=`` argument at all, so it defaulted to ``None``.
        Neither ``has_coverage_gap`` nor ``moderation_coverage_incomplete()``
        could see a ``None`` concern, so a book whose Stage-0 bright-line
        classifier never screened most of its nodes routed to ``submit()``
        and became eligible for auto-repair instead of being blocked.
        """
        report = ModerationReport()
        report.add(self._gap("classifier_unavailable"))
        assert report.has_coverage_gap is True
        assert report.blocks_release is True
        assert moderation_coverage_incomplete(report.to_dict()) is True

    def test_a_mock_reviewer_stamp_is_left_to_the_stored_gate(self) -> None:
        """The in-flight predicate asks only "did the reviewer see every node".

        The mock stamp is applied early in the pipeline, before the repair
        gate, so folding it in here would make the repair branch unreachable
        under the escape hatch and strand
        ``_stamp_mock_reviewer(repaired_report)`` as dead code. Nothing escapes:
        the real mock backend fail-safes every node (so an actual mock run
        carries ``reviewer_unavailable`` anyway), and the STORED predicate
        keeps the broader concern set, which is what the approval gate and the
        sweep's verdict both read.
        """
        report = ModerationReport()
        report.add(self._gap("mock_reviewer_active"))
        assert report.has_coverage_gap is False
        assert report.blocks_release is False
        assert moderation_coverage_incomplete(report.to_dict()) is True, (
            "the stored gate must still refuse a mock-stamped report"
        )

    def test_a_hard_block_blocks_release_with_no_coverage_gap(self) -> None:
        report = ModerationReport()
        report.add(_finding(Verdict.BLOCK))
        assert report.has_coverage_gap is False
        assert report.blocks_release is True

    def test_an_ordinary_flag_does_not_block_release(self) -> None:
        report = ModerationReport()
        report.add(_finding(Verdict.FLAG))
        assert report.has_coverage_gap is False
        assert report.blocks_release is False
        assert report.has_soft_flag is True, (
            "an ordinary flag must keep routing to the bounded repair path"
        )

    def test_a_clean_report_does_not_block_release(self) -> None:
        report = ModerationReport()
        report.add(_finding(Verdict.PASS))
        assert report.has_coverage_gap is False
        assert report.blocks_release is False
        assert report.is_clean is True

    def test_a_coverage_gap_beside_genuine_findings_still_blocks(self) -> None:
        """Coverage is not a finding other findings can outvote.

        The stored-report predicate had exactly this hole: one real judgment
        beside a gap made the report read as usable.
        """
        report = ModerationReport()
        report.add(_finding(Verdict.FLAG))
        report.add(self._gap())
        assert report.blocks_release is True

    def test_coverage_complete_is_persisted_in_the_payload(self) -> None:
        """The flag must survive to the stored row, or no gate downstream sees it.

        The 2026-07-21 mock-reviewer run is the precedent: nothing about the
        reviewer was persisted, so a report produced by a stub was
        indistinguishable from a real one months later.
        """
        clean = ModerationReport()
        clean.add(_finding(Verdict.PASS))
        summary = cast("dict[str, object]", clean.to_dict()["summary"])
        assert summary["coverage_complete"] is True

        gapped = ModerationReport()
        gapped.add(self._gap())
        summary = cast("dict[str, object]", gapped.to_dict()["summary"])
        assert summary["coverage_complete"] is False

        # The field is literal about coverage, so a mock run that answered for
        # every node records True. The stored GATE is broader, which is the
        # assertion in test_a_mock_reviewer_stamp_is_left_to_the_stored_gate.
        mocked = ModerationReport()
        mocked.add(self._gap("mock_reviewer_active"))
        summary = cast("dict[str, object]", mocked.to_dict()["summary"])
        assert summary["coverage_complete"] is True

    def test_the_persisted_payload_round_trips_to_the_stored_predicate(self) -> None:
        """The two predicates must agree across the persistence boundary.

        Otherwise the pipeline can block a release the approval gate would
        happily clear, which is how a gap reaches a reader in the first place.
        """
        gapped = ModerationReport()
        gapped.add(self._gap())
        assert moderation_coverage_incomplete(gapped.to_dict()) is True

        clean = ModerationReport()
        clean.add(_finding(Verdict.FLAG))
        assert moderation_coverage_incomplete(clean.to_dict()) is False


@pytest.mark.unit
def test_coverage_gap_concerns_omits_only_the_mock_stamp() -> None:
    """Pin the DERIVATION's intent, not just its current membership.

    ``COVERAGE_GAP_CONCERNS`` is computed from ``MOCK_MODERATED_CONCERNS``
    (see that constant's comment) rather than written out as its own
    literal, so a future structural concern added to the broader set lands
    in the narrower one automatically. That makes an equality check against
    a second independent literal insufficient to catch a broken derivation;
    this asserts the one omission the derivation exists to make, by name.
    """
    assert MOCK_MODERATED_CONCERNS - {"mock_reviewer_active"} == COVERAGE_GAP_CONCERNS
    assert "mock_reviewer_active" in MOCK_MODERATED_CONCERNS
    assert "mock_reviewer_active" not in COVERAGE_GAP_CONCERNS
    assert "reviewer_unavailable" in COVERAGE_GAP_CONCERNS
    assert "classifier_unavailable" in COVERAGE_GAP_CONCERNS


class TestModerationCoverageIncomplete:
    """moderation_coverage_incomplete() over the persisted JSONB shape.

    Distinct from ``moderation_report_unusable`` on purpose, and the pair of
    tests below is the whole reason a second predicate exists: the usable
    predicate is an ALL-match (no genuine judgment anywhere), so one real
    finding beside a coverage gap makes the report "usable" while eight nodes
    went unscreened. Coverage is an ANY-match question.
    """

    def _gap_finding(self, nodes: int = 8, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "stage": 1,
            "source": "pipeline",
            "category": "pipeline",
            "node_id": "n1",
            "verdict": "flag",
            "severity": "high",
            "structural": True,
            "concern": "reviewer_unavailable",
            "message": (
                f"reviewer unavailable or unparseable on {nodes} node(s); "
                "defaulted to fail-safe"
            ),
            "node_ids": [f"n{i}" for i in range(1, nodes + 1)],
        }
        base.update(overrides)
        return base

    def _genuine_finding(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "stage": 1,
            "source": "llm_safety",
            "category": "llm_safety",
            "node_id": "n9",
            "verdict": "flag",
            "severity": "medium",
            "concern": "frightening_content",
            "message": "a real judgment about real prose",
        }
        base.update(overrides)
        return base

    def test_a_coverage_gap_beside_genuine_findings_is_incomplete(self) -> None:
        """The exact shape production produced on four books.

        28 genuine findings plus one reviewer_unavailable made
        ``moderation_report_unusable`` return False, so the approval gate saw
        nothing wrong with a book whose reviewer never saw eight of its nodes.
        """
        report: dict[str, object] = {
            "findings": [self._genuine_finding(), self._gap_finding(nodes=8)],
            "summary": {"reviewer_independent": True},
        }
        assert moderation_report_unusable(report) is False, (
            "precondition: the all-match predicate calls this report usable, "
            "which is what makes a separate coverage predicate necessary"
        )
        assert moderation_coverage_incomplete(report) is True

    def test_a_fully_reviewed_report_is_complete(self) -> None:
        """A report with real findings and no gap must not be held back."""
        report: dict[str, object] = {
            "findings": [self._genuine_finding()],
            "summary": {"reviewer_independent": True},
        }
        assert moderation_coverage_incomplete(report) is False

    def test_a_clean_report_is_complete(self) -> None:
        """An empty findings list from an independent reviewer is full coverage."""
        report: dict[str, object] = {
            "findings": [],
            "summary": {"reviewer_independent": True},
        }
        assert moderation_coverage_incomplete(report) is False

    def test_a_missing_report_is_incomplete(self) -> None:
        """Absent evidence of coverage is not evidence of coverage."""
        assert moderation_coverage_incomplete(None) is True

    def test_a_malformed_report_is_incomplete(self) -> None:
        """Fail closed on any shape we cannot read, as the sibling predicate does."""
        assert moderation_coverage_incomplete({}) is True
        assert moderation_coverage_incomplete({"findings": "not-a-list"}) is True
        assert (
            moderation_coverage_incomplete(cast("dict[str, object]", "not-a-mapping"))
            is True
        )

    def test_a_mock_reviewer_concern_is_also_incomplete(self) -> None:
        """mock_reviewer_active means nothing real was screened either."""
        report: dict[str, object] = {
            "findings": [self._gap_finding(concern="mock_reviewer_active")],
            "summary": {"reviewer_independent": True},
        }
        assert moderation_coverage_incomplete(report) is True

    def test_a_non_mapping_finding_entry_does_not_mask_a_gap(self) -> None:
        """A junk entry beside a real gap must not make the report look covered."""
        report: dict[str, object] = {
            "findings": ["junk", self._gap_finding()],
            "summary": {"reviewer_independent": True},
        }
        assert moderation_coverage_incomplete(report) is True


class TestModerationCoverageGap:
    """moderation_coverage_gap() over the persisted JSONB shape.

    The narrow predicate. It exists because a REPORTING caller and the
    APPROVAL gate ask different questions of the same report, and the mock
    stamp is the one input where the two answers must diverge: every node was
    screened (no coverage gap), by a reviewer whose output proves nothing (not
    approvable). Answering a reporting field from the approval predicate made
    ``api/remoderate.py`` return ``coverage_complete: false`` beside the
    ``"coverage_complete": true`` its own pipeline had just persisted.
    """

    _MOCK_STAMP: ClassVar[dict[str, object]] = {
        # The literal shape run_moderation_pipeline's _stamp_mock_reviewer
        # persists, taken from an observed local run rather than invented.
        "concern": "mock_reviewer_active",
        "verdict": "advisory",
        "structural": True,
        "category": "pipeline",
        "message": "moderated with the mock reviewer; no real safety review ran",
    }

    def test_a_mock_stamp_alone_is_not_a_coverage_gap(self) -> None:
        """A mock reviewer screened every node; it is provenance, not coverage."""
        report: dict[str, object] = {
            "findings": [dict(self._MOCK_STAMP)],
            "summary": {"reviewer_independent": False, "coverage_complete": True},
        }
        assert moderation_coverage_gap(report) is False

    def test_the_approval_predicate_still_refuses_that_same_report(self) -> None:
        """The discriminator: one input, two predicates, opposite answers.

        Without this pairing the narrow predicate could be quietly swapped in
        at the approval gate and every test would still pass. Both assertions
        are made on the SAME dict so the divergence is a property of the
        predicates, not of two fixtures that happen to differ.
        """
        report: dict[str, object] = {
            "findings": [dict(self._MOCK_STAMP)],
            "summary": {"reviewer_independent": False, "coverage_complete": True},
        }
        assert moderation_coverage_gap(report) is False
        assert moderation_coverage_incomplete(report) is True
        assert moderation_report_unusable(report) is True, (
            "and the approval gate refuses it a second way, which is why "
            "narrowing the reporting predicate concedes no safety"
        )

    @pytest.mark.parametrize("concern", sorted(COVERAGE_GAP_CONCERNS))
    def test_every_genuine_gap_concern_is_a_gap(self, concern: str) -> None:
        """Parametrized over the set itself, so a new member cannot be forgotten."""
        report: dict[str, object] = {
            "findings": [{"concern": concern, "structural": True, "verdict": "flag"}],
            "summary": {"reviewer_independent": True},
        }
        assert moderation_coverage_gap(report) is True

    def test_a_clean_report_has_no_gap(self) -> None:
        """An empty findings list from an independent reviewer is full coverage."""
        report: dict[str, object] = {
            "findings": [],
            "summary": {"reviewer_independent": True},
        }
        assert moderation_coverage_gap(report) is False

    def test_a_missing_or_malformed_report_is_a_gap(self) -> None:
        """Fails closed on every shape it cannot read, as its sibling does."""
        assert moderation_coverage_gap(None) is True
        assert moderation_coverage_gap({}) is True
        assert moderation_coverage_gap({"findings": "not-a-list"}) is True
        assert (
            moderation_coverage_gap(cast("dict[str, object]", "not-a-mapping")) is True
        )

    def test_a_non_mapping_finding_entry_does_not_mask_a_gap(self) -> None:
        """A junk entry beside a real gap must not make the report look covered."""
        report: dict[str, object] = {
            "findings": ["junk", {"concern": "reviewer_unavailable"}],
            "summary": {"reviewer_independent": True},
        }
        assert moderation_coverage_gap(report) is True


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
        self,
        findings: list[dict[str, object]],
        *,
        independent: bool = True,
        coverage_complete: bool | None = None,
        reviewer_present: bool = False,
        reviewer: object = None,
    ) -> dict[str, object]:
        """Build a persisted report dict.

        ``coverage_complete`` and ``reviewer_present`` default to the LEGACY
        shape (neither key present), matching every pre-existing test in this
        class. Pass ``coverage_complete=`` to opt a test into the
        post-``coverage_complete`` shape the ``reviewer``-provenance gate
        keys off; ``reviewer_present=True`` then controls whether the
        top-level ``reviewer`` key itself is present (with ``reviewer=`` as
        its value, ``None`` by default), separately from whether it is
        merely absent.
        """
        summary: dict[str, object] = {
            "count": len(findings),
            "hard_block": False,
            "soft_flag": bool(findings),
            "repaired": False,
            "reviewer_independent": independent,
        }
        if coverage_complete is not None:
            summary["coverage_complete"] = coverage_complete
        report: dict[str, object] = {
            "findings": findings,
            "aggregate": {"nodes_reviewed": 1, "pass_counts": {}},
            "summary": summary,
        }
        if reviewer_present:
            report["reviewer"] = reviewer
        return report

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

    def test_a_post_reviewer_field_report_with_no_reviewer_is_unusable(self) -> None:
        """A writer that knows about ``coverage_complete`` must also record a reviewer.

        This is the FIX-2 gate: ``reviewer`` was write-only before it, a
        persisted report could carry ``reviewer_independent`` at its default
        ``True`` and one genuine-looking finding and still clear this gate
        with no reviewer ever recorded.
        """
        genuine = self._fail_safe_finding(message="cruelty to animals")
        report = self._report([genuine], coverage_complete=True, reviewer_present=False)
        assert moderation_report_unusable(report) is True

    def test_a_post_reviewer_field_report_with_non_mapping_reviewer_is_unusable(
        self,
    ) -> None:
        """A ``reviewer`` key present but corrupt (not a mapping) is not evidence."""
        genuine = self._fail_safe_finding(message="cruelty to animals")
        report = self._report(
            [genuine],
            coverage_complete=True,
            reviewer_present=True,
            reviewer="not a mapping",
        )
        assert moderation_report_unusable(report) is True

    def test_a_legacy_report_with_no_coverage_complete_key_tolerates_a_missing_reviewer(
        self,
    ) -> None:
        """A report predating both fields is unaffected: no reviewer signal to read.

        Without this, the FIX-2 gate would retroactively unapprove the
        entire pre-``reviewer``-field catalog.
        """
        genuine = self._fail_safe_finding(message="cruelty to animals")
        report = self._report([genuine], coverage_complete=None, reviewer_present=False)
        assert "coverage_complete" not in cast("dict[str, object]", report["summary"])
        assert moderation_report_unusable(report) is False

    def test_a_post_reviewer_field_report_with_a_recorded_reviewer_is_usable(
        self,
    ) -> None:
        """The positive case: a recorded reviewer clears this gate."""
        genuine = self._fail_safe_finding(message="cruelty to animals")
        report = self._report(
            [genuine],
            coverage_complete=True,
            reviewer_present=True,
            reviewer={"provider": "openrouter", "model": "m"},
        )
        assert moderation_report_unusable(report) is False

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

    def test_a_non_dict_finding_row_is_counted_and_logged(self) -> None:
        """At-rest corruption must leave a trace, not read as a judged node.

        The scan skips a row it cannot index into, and for as long as that
        skip was silent, a report whose findings list had been corrupted
        rendered as a clean, fully judged book. Nothing above catches it:
        ``moderation_report_unusable`` stops at the first genuine finding, so
        the FLAG row here rescues the whole report from that predicate.
        """
        report = {
            "findings": [
                "not a finding at all",
                {
                    "source": "llm_safety",
                    "node_id": "n1",
                    "verdict": "flag",
                    "message": "too scary",
                },
            ]
        }

        with patch.object(report_module, "_logger") as logger:
            counts = legacy_hidden_fail_safe_node_counts(report)

        assert counts == {}
        assert logger.warning.call_args_list == [
            call(
                "hidden_fail_safe_scan_skipped_rows",
                malformed_rows=1,
                reason=ANY,
            )
        ]

    def test_a_pass_row_with_a_non_string_message_is_counted_and_logged(
        self,
    ) -> None:
        """A PASS row whose message is not a string is corrupt, not clean.

        Every real ``Finding`` carries a ``str`` message, so this shape can
        only come from corruption at rest. Before the counter it fell through
        the same silent path as a genuine clean judgment.
        """
        report = {
            "findings": [
                {
                    "source": "llm_readability",
                    "node_id": "n1",
                    "verdict": "pass",
                    "message": {"unknown verdict": "defaulted to fail-safe"},
                }
            ]
        }

        with patch.object(report_module, "_logger") as logger:
            counts = legacy_hidden_fail_safe_node_counts(report)

        assert counts == {}
        assert logger.warning.call_args_list == [
            call(
                "hidden_fail_safe_scan_skipped_rows",
                malformed_rows=1,
                reason=ANY,
            )
        ]

    def test_ordinary_pass_rows_do_not_trip_the_skipped_row_log(self) -> None:
        """The witness must stay quiet on the shape it will see most often.

        A legacy report is full of genuine PASS rows whose messages are
        ordinary judgments. Warning on those would fire on nearly every
        report the scan reads, and a warning that always fires is one nobody
        reads: the counter would stop being evidence of anything.
        """
        report = {
            "findings": [
                {
                    "source": "llm_readability",
                    "node_id": "n1",
                    "verdict": "pass",
                    "message": "reads cleanly for the band",
                },
                {
                    "source": "llm_safety",
                    "node_id": "n2",
                    "verdict": "pass",
                    "message": "nothing unsafe here",
                },
            ]
        }

        with patch.object(report_module, "_logger") as logger:
            counts = legacy_hidden_fail_safe_node_counts(report)

        assert counts == {}
        logger.warning.assert_not_called()

    def test_a_corrupt_non_string_source_falls_back_to_the_category(self) -> None:
        """`source or category` short-circuited on any truthy source.

        A corrupt non-string source consumed the slot, so the category
        fallback never ran and the row was bucketed under "unknown" with the
        usable label sitting right beside it.
        """
        report = {
            "findings": [
                {
                    "source": ["llm_readability"],
                    "category": "llm_readability",
                    "node_id": "n1",
                    "verdict": "pass",
                    "message": FAIL_SAFE_MESSAGE_SUBSTRING,
                }
            ]
        }

        assert legacy_hidden_fail_safe_node_counts(report) == {
            "llm_readability": FailSafeScope(nodes=1, whole_story=False)
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
        report.reviewer = _provenance()
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


class TestMockStampMakesAReportUnapprovable:
    """The stamp's second half is a hard gate, and nothing tested that.

    ``_stamp_mock_reviewer`` does two things: it adds an ADVISORY finding,
    which never gates, and it sets ``reviewer_independent = False``, which
    ``moderation_report_unusable`` treats as decisive on its own. Since this
    PR made the stamp unconditional, every story moderated locally with the
    mock reviewer is permanently unapprovable, including the local
    cyo-author authoring loop and ``scripts/series_e2e_local.py``'s
    import-then-approve path.

    That is the intended posture (a mock run was never a review), but it was
    an undocumented and untested consequence of widening the predicate. These
    tests pin it, so the behavior is a decision on record rather than a side
    effect nobody wrote down.
    """

    @staticmethod
    def _report_with_one_genuine_finding() -> ModerationReport:
        """A report that ``moderation_report_unusable`` accepts on its own.

        A genuine, non-structural finding carrying a real verdict is what
        makes this report the right control: it rules out the "every finding
        is a pipeline artifact" arm, so any unusable verdict below can only
        come from the ``reviewer_independent`` arm.

        Returns:
            ModerationReport: An unstamped report with one ADVISORY finding.
        """
        report = ModerationReport()
        report.add(
            Finding(
                stage=0,
                source=Source.PIPELINE,
                category="prose_craft_sameness",
                verdict=Verdict.ADVISORY,
                message="self-repetition: 3 nodes repeat another node's body",
                node_id=None,
            )
        )
        report.reviewer = _provenance()
        return report

    def test_the_control_report_is_approvable_before_stamping(self) -> None:
        """Without this, the stamped assertion below proves nothing.

        A report that was already unusable would satisfy the next test no
        matter what the stamp did.
        """
        report = self._report_with_one_genuine_finding()

        assert moderation_report_unusable(report.to_dict()) is False

    def test_stamping_alone_flips_it_to_unusable(self) -> None:
        """Same report, same findings, one stamp: no longer approvable.

        ``publishing/service.py::approve`` raises ``BusinessLogicError``
        (rule ``approve_with_unusable_moderation``) on exactly this
        predicate, which is what makes the flip an approval-gate decision
        rather than a cosmetic label.
        """
        report = self._report_with_one_genuine_finding()

        _stamp_mock_reviewer(report)

        assert moderation_report_unusable(report.to_dict()) is True

    def test_the_advisory_half_is_not_what_gates(self) -> None:
        """Attribute the flip to the right half of the stamp.

        Adding the stamp's ADVISORY finding without its
        ``reviewer_independent`` half leaves the report approvable. Without
        this, a future change that dropped the flag and kept the finding
        would still pass the test above via the other arm, and the gate would
        be gone with every test still green.
        """
        report = self._report_with_one_genuine_finding()
        _stamp_mock_reviewer(report)
        report.reviewer_independent = True

        assert moderation_report_unusable(report.to_dict()) is False
