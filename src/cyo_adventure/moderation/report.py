"""Moderation findings: the structured verdicts every stage appends to one report.

Persisted verbatim on ``storybook_version.moderation_report`` (a JSONB column).
The report is a plain accumulator: stages add findings, the pipeline reads the
``has_hard_block`` / ``has_soft_flag`` flags to drive the state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import NamedTuple, cast

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.utils.logging import get_logger

_logger = get_logger(__name__)


class Source(StrEnum):
    """Which stage or classifier produced a finding."""

    OPENAI = "openai"
    PERSPECTIVE = "perspective"
    LLM_SAFETY = "llm_safety"
    LLM_READABILITY = "llm_readability"
    LLM_COHERENCE = "llm_coherence"
    LLM_ENGAGEMENT = "llm_engagement"
    PIPELINE = "pipeline"


class Verdict(StrEnum):
    """A finding's gating role.

    ``BLOCK`` is a hard gate (Stage 0 bright-line or Stage 1 block). ``FLAG`` is a
    soft gate (auto-repair then surface). ``ADVISORY`` never gates. ``PASS`` records
    a clean check.
    """

    BLOCK = "block"
    FLAG = "flag"
    ADVISORY = "advisory"
    # "pass" is a verdict value, not a credential (S105/B105 false positive).
    # Two suppressions are required: Ruff's flake8-bandit port honors its own
    # directive, but the standalone bandit binary the CI Security Gate runs
    # does not recognize that directive and only honors its own.
    PASS = "pass"  # noqa: S105  # nosec B105


class FindingSeverity(StrEnum):
    """Ranking key for surfaced findings (design doc 2.1).

    Required on FLAG/ADVISORY findings produced by Stage B code paths;
    absent (``None``) on findings from old persisted reports that predate
    this field.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Fixed concern taxonomy (design doc 2.1): part of the dedup/merge key.
# "other" is the degrade target for an unrecognized model-emitted concern
# (2.2 item 1); that degrade belongs at the parse boundary where a model
# response is turned into a Finding, so by the time a Finding is constructed
# the value must already be a member. Enforced in ``Finding.__post_init__``.
#
# "reviewer_unavailable" and "mock_reviewer_active" duplicate
# MOCK_MODERATED_CONCERNS below by design, not by drift: this set is the
# closed taxonomy every Finding.concern value must belong to (including
# these two structural ones), while MOCK_MODERATED_CONCERNS is the narrower
# subset moderation_report_unusable() treats as pipeline artifacts rather
# than genuine judgments. A concern added here for a genuinely new
# structural (pipeline-condition) reason belongs in MOCK_MODERATED_CONCERNS
# too; a new genuine-content concern must NOT be added there.
CONCERN_TAXONOMY: frozenset[str] = frozenset(
    {
        "real_world_danger",
        "too_mature",
        "frightening_content",
        "cruelty",
        "sexual_content",
        "self_harm",
        "profanity",
        # Structural concerns: pipeline conditions, not content judgments.
        # Mirrored in MOCK_MODERATED_CONCERNS below.
        "reviewer_unavailable",
        "mock_reviewer_active",
        "other",
    }
)

# The two exact messages the Stage-1 parser emits when it cannot extract a
# verdict (moderation/stages.py). They are load-bearing at rest: legacy
# pre-Stage-A reports are detected by these strings because those rows lack
# the ``structural`` and ``concern`` keys. Do not reword without a data
# migration story for stored reports.
UNKNOWN_VERDICT_FAIL_SAFE_MESSAGE = "unknown verdict; defaulted to fail-safe"
PARSE_FAILED_FAIL_SAFE_MESSAGE = "verdict parse failed; defaulted to fail-safe"
FAIL_SAFE_MESSAGE_SUBSTRING = "defaulted to fail-safe"
LEGACY_FAIL_SAFE_MESSAGES = frozenset(
    {UNKNOWN_VERDICT_FAIL_SAFE_MESSAGE, PARSE_FAILED_FAIL_SAFE_MESSAGE}
)
# The structural (pipeline-condition, not genuine-content) subset of
# CONCERN_TAXONOMY above; both members are also the two structural entries
# called out in that set's own comment. Kept as a separate frozenset
# (instead of, say, a "structural" flag on the taxonomy itself) because this
# is the exact predicate moderation_report_unusable() needs, and the two
# sets serve different questions: CONCERN_TAXONOMY answers "is this concern
# value valid at all", MOCK_MODERATED_CONCERNS answers "does this concern
# value alone fail to prove a genuine judgment happened".
MOCK_MODERATED_CONCERNS = frozenset({"mock_reviewer_active", "reviewer_unavailable"})
# The strictly narrower question ModerationReport.has_coverage_gap asks of an
# IN-FLIGHT run: did the reviewer actually see every node? Only the fail-safe
# concern answers no. "mock_reviewer_active" is deliberately absent, and the
# omission is load-bearing rather than an oversight:
#
#   * _stamp_mock_reviewer runs early in run_moderation_pipeline, before the
#     repair gate. Including the stamp here would make blocks_release true from
#     the first line of every escape-hatch run, so the repair branch could never
#     be entered under a mock reviewer and _stamp_mock_reviewer(repaired_report)
#     would become unreachable code.
#   * Nothing is lost by the omission. The real mock backend returns a fixed
#     unparseable body, so every node fail-safes and the run carries
#     "reviewer_unavailable" anyway; and the STORED predicate
#     moderation_coverage_incomplete() keeps the full MOCK_MODERATED_CONCERNS
#     set, so a mock-stamped report still cannot clear the approval gate and
#     still classifies as blocked in api/remoderate.py's verdict. The 2026-07-21
#     mock-reviewer sweep is closed at those two gates, not at this one.
COVERAGE_GAP_CONCERNS = frozenset({"reviewer_unavailable"})


@dataclass(frozen=True, slots=True)
class Finding:
    """One moderation result.

    Attributes:
        stage: 0-4 pipeline stage index.
        source: The producing stage/classifier.
        category: Dimension (for example ``"violence"``, ``"reading_level"``).
        node_id: The story node the finding concerns, or ``None`` for whole-story.
        verdict: Its gating role.
        score: Optional numeric score (classifier probability or model confidence).
        message: Human-readable explanation for the guardian.
        structural: True when the finding reflects a pipeline condition (a
            parse failure, a classifier outage, a mock reviewer in use)
            rather than a genuine content judgment. Additive field (Stage A
            of the moderation review redesign, design doc section 2.3/2.5):
            old persisted reports without this key load fine, since it
            defaults to ``False`` and every reader accesses findings via
            ``.get()``. Dashboard aggregates and the threshold flywheel must
            key off this flag to avoid conflating pipeline noise with real
            safety signal (gap G2a).
        concern: Optional machine-readable reason code from
            ``CONCERN_TAXONOMY``, forming part of the merge key. Currently
            set only on structural findings (for example
            ``"reviewer_unavailable"``); content findings get theirs from
            the structured-verdict work in design doc 2.2 item 1.
        severity: Ranking key for the surfaced findings list (design doc
            2.1). ``None`` on old persisted reports and on findings that
            never carried a severity band.
        node_ids: Every node this finding covers. Populated by the merge
            stage (design doc 2.2) on every finding it emits, including a
            group of one, so readers get a uniform shape; ``None`` only on
            findings that never went through the merge (pre-Stage-B reports,
            and the fresh single-node findings ``api/node_edit.py`` splices
            in). Readers must fan out across ``node_ids`` when it is present
            and fall back to ``node_id`` when it is not: ``node_id`` names
            only the FIRST covered node.
    """

    stage: int
    source: Source
    category: str
    verdict: Verdict
    message: str
    node_id: str | None = None
    score: float | None = None
    structural: bool = False
    concern: str | None = None
    severity: FindingSeverity | None = None
    node_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        """Enforce the documented field ranges at construction.

        Raises:
            ValueError: when ``stage`` is outside 0-4, ``score`` is outside
                ``[0.0, 1.0]`` (a non-None probability/confidence), or
                ``concern`` is not a member of ``CONCERN_TAXONOMY``.
        """
        if not 0 <= self.stage <= 4:
            msg = f"Finding.stage must be 0-4, got {self.stage}"
            raise ValueError(msg)
        if self.score is not None and not 0.0 <= self.score <= 1.0:
            msg = f"Finding.score must be in [0.0, 1.0] or None, got {self.score}"
            raise ValueError(msg)
        # #ASSUME: data integrity: concern is part of the merge key (design
        # doc 2.2). An unrecognized value would silently form its own group
        # and, once B2 has models emitting it, drift the taxonomy by accident.
        # Callers that parse a model response must degrade to "other" before
        # constructing the Finding rather than passing the raw string through.
        # #VERIFY: tests/unit/test_moderation_report.py::
        # test_unknown_concern_rejected_at_construction.
        if self.concern is not None and self.concern not in CONCERN_TAXONOMY:
            msg = (
                f"Finding.concern must be in CONCERN_TAXONOMY or None, "
                f"got {self.concern!r}"
            )
            raise ValueError(msg)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping for persistence."""
        return {
            "stage": self.stage,
            "source": self.source.value,
            "category": self.category,
            "node_id": self.node_id,
            "verdict": self.verdict.value,
            "score": self.score,
            "message": self.message,
            "structural": self.structural,
            "concern": self.concern,
            "severity": self.severity.value if self.severity else None,
            "node_ids": list(self.node_ids) if self.node_ids is not None else None,
        }


@dataclass(slots=True)
class ModerationReport:
    """Accumulating list of findings plus derived gating flags."""

    findings: list[Finding] = field(default_factory=list)
    repaired: bool = False
    reviewer_independent: bool = True
    nodes_reviewed: int = 0

    def add(self, finding: Finding) -> None:
        """Append a finding."""
        self.findings.append(finding)

    @property
    def has_hard_block(self) -> bool:
        """True when any finding is a hard ``BLOCK``."""
        return any(f.verdict is Verdict.BLOCK for f in self.findings)

    @property
    def has_soft_flag(self) -> bool:
        """True when any finding is a soft ``FLAG`` and none is a hard block.

        The hard-block exclusion is part of the property's contract, not just an
        accident of the call site: a blocked report has no actionable soft gate.
        """
        return not self.has_hard_block and any(
            f.verdict is Verdict.FLAG for f in self.findings
        )

    @property
    def has_coverage_gap(self) -> bool:
        """True when a node in this run was never actually judged.

        The Stage-1 safety pass batches nodes (``review_batch_size``, default
        8) and records a single fail-safe ``FLAG`` per node when a batch
        response is missing or unparseable. ``has_hard_block`` is
        ``any(verdict is BLOCK)``, so those nodes can never contribute a
        block, and the fail-safe FLAG reads downstream as an ordinary soft
        flag: "review when convenient". Node-level fail-safe composed into
        book-level fail-open, which is how four books in the live catalog
        carried exactly eight unscreened nodes each while reporting
        ``hard_block=False``.

        Detected by ``concern``, not by message text, because the message
        carries a node count and would drift. The concern set is
        :data:`COVERAGE_GAP_CONCERNS`, which is narrower than
        :data:`MOCK_MODERATED_CONCERNS`; see that constant's comment for why
        the mock-reviewer stamp is excluded from this in-flight predicate but
        not from the stored one.
        """
        return any(f.concern in COVERAGE_GAP_CONCERNS for f in self.findings)

    @property
    def blocks_release(self) -> bool:
        """True when this report must not let the story move toward a reader.

        Deliberately separate from :attr:`has_hard_block`, which does double
        duty: it drives routing AND the cost short-circuits between pipeline
        stages. Folding coverage into it would let a flaky stage-0 classifier
        skip the entire LLM safety stage, turning a transient failure into a
        wholly unreviewed story. Only the routing call sites take this
        predicate.
        """
        return self.has_hard_block or self.has_coverage_gap

    @property
    def is_clean(self) -> bool:
        """True when no finding gates (no block, no flag)."""
        return not (self.has_hard_block or self.has_soft_flag)

    def to_dict(self) -> dict[str, object]:
        """Return the JSONB payload persisted on the version row.

        PASS findings are aggregated, not persisted as rows (design doc
        2.1): the report keeps them in memory for gating, but the stored
        payload carries only gate-relevant findings plus a pass aggregate.
        """
        persisted = [f for f in self.findings if f.verdict is not Verdict.PASS]
        pass_counts: dict[str, int] = {}
        for f in self.findings:
            if f.verdict is Verdict.PASS:
                pass_counts[f.category] = pass_counts.get(f.category, 0) + 1
        return {
            "findings": [f.to_dict() for f in persisted],
            "aggregate": {
                "nodes_reviewed": self.nodes_reviewed,
                "pass_counts": pass_counts,
            },
            "summary": {
                "count": len(persisted),
                "hard_block": self.has_hard_block,
                "soft_flag": self.has_soft_flag,
                # Persisted so a gate reading the stored row months later can
                # tell a fully reviewed report from one whose reviewer never
                # saw part of the story. The 2026-07-21 mock-reviewer run
                # persisted no reviewer provenance at all, which is why those
                # reports were undetectable after the fact.
                # Literal, not a gate verdict: it answers "did the reviewer see
                # every node", so a mock-reviewer run that returned a verdict
                # for each node records True here. That is not a loophole,
                # because the gates read moderation_coverage_incomplete(), which
                # also refuses a mock-stamped report; a field that quietly
                # meant something broader than its name would be the worse
                # failure mode.
                "coverage_complete": not self.has_coverage_gap,
                "repaired": self.repaired,
                "reviewer_independent": self.reviewer_independent,
            },
        }


def moderation_report_unusable(report: dict[str, object] | None) -> bool:
    """True when a stored report carries no genuine content judgment.

    Operates on the persisted JSONB shape (``to_dict()`` output), including
    legacy pre-Stage-A rows that lack ``structural``/``concern`` keys. A
    report is unusable when it is absent, is not a mapping, when ``findings``
    is missing, is not a list, or is otherwise malformed (fail closed rather
    than treat a corrupt row as a clean pass), when the reviewer was not
    independent (mock), or when every finding is a pipeline artifact
    (structural, fail-safe message, or a MOCK_MODERATED_CONCERNS concern). A
    per-finding entry that matches none of those artifact shapes AND carries
    no recognizable genuine-judgment shape of its own (a non-empty
    ``verdict``, the one field every real ``Finding.to_dict()`` output
    always sets) is treated the same way: an artifact-or-corrupt row, never a
    rescuing judgment. An empty findings list is a genuine all-clear only
    when the report also carries a well-formed ``summary`` mapping with
    ``reviewer_independent`` exactly ``True`` (PASS findings are aggregated
    rather than persisted, see ``ModerationReport.to_dict``); an empty list
    on a report with no such evidence of an independent reviewer run is
    itself a malformed shape, not an unusable-by-content report.
    """
    if not isinstance(report, dict):
        return True
    summary = report.get("summary")
    if (
        isinstance(summary, dict)
        and cast("dict[str, object]", summary).get("reviewer_independent") is False
    ):
        return True
    findings = report.get("findings")
    # #CRITICAL: data-integrity: a missing or non-list ``findings`` key is a
    # malformed report, not a clean pass. The prior behavior returned False
    # (usable) here, which let a corrupt row slip past the approval gate as
    # though it had been genuinely reviewed. Fail closed instead: only a
    # well-formed empty list ([]) is a genuine all-clear.
    # #VERIFY: tests/unit/test_moderation_report.py::
    # TestModerationReportUnusable::test_empty_dict_report_is_unusable,
    # ::test_none_findings_value_is_unusable,
    # ::test_non_list_findings_value_is_unusable.
    if not isinstance(findings, list):
        return True
    if not findings:
        # #CRITICAL: security: an empty findings list is a genuine all-clear
        # only when it comes with evidence an independent reviewer actually
        # ran. Without this check a corrupt or hand-crafted row carrying
        # ``findings: []`` and no (or a malformed) ``summary`` would read as
        # a clean, reviewed report and clear the approval gate with zero
        # proof any review occurred.
        # #VERIFY: tests/unit/test_moderation_report.py::
        # TestModerationReportUnusable::
        # test_empty_findings_without_summary_is_unusable,
        # ::test_empty_findings_with_non_mapping_summary_is_unusable,
        # ::test_empty_findings_missing_reviewer_independent_key_is_unusable.
        return not (
            isinstance(summary, dict)
            and cast("dict[str, object]", summary).get("reviewer_independent") is True
        )
    return not any(
        _is_genuine_judgment(finding) for finding in cast("list[object]", findings)
    )


def moderation_coverage_incomplete(report: dict[str, object] | None) -> bool:
    """True when a stored report admits the reviewer did not see every node.

    The ANY-match counterpart to :func:`moderation_report_unusable`'s
    ALL-match, and the two must not be collapsed. That predicate asks "did any
    genuine judgment happen at all", which is the right question for detecting
    a wholly mock-reviewed report and the wrong one for coverage: a single real
    finding beside a coverage gap satisfies it, so a report naming eight
    unscreened nodes reads as usable. Four books in the live catalog held
    exactly that shape.

    Coverage is not a finding to be outvoted by other findings. A gap means no
    judgment exists for those nodes, so there is nothing for a human to
    override; an override reason can justify disagreeing with a verdict, never
    substitute for one that was never produced.

    Args:
        report: The stored ``moderation_report`` JSONB payload, or ``None``.

    Returns:
        bool: True when the report is absent, unreadable, or carries any
        finding whose ``concern`` is in :data:`MOCK_MODERATED_CONCERNS`
        (``reviewer_unavailable`` from the Stage-1 batch fail-safe, or
        ``mock_reviewer_active``). Fails closed on every malformed shape, for
        the same reason the sibling predicate does: absent evidence of
        coverage is not evidence of coverage.
    """
    # #CRITICAL: security: this gates the approval path, so every unreadable
    # shape must answer "incomplete". Returning False for a malformed report
    # would let a corrupt row clear the gate as fully reviewed.
    # #VERIFY: tests/unit/test_moderation_report.py::
    # TestModerationCoverageIncomplete::test_a_missing_report_is_incomplete and
    # ::test_a_malformed_report_is_incomplete.
    if not isinstance(report, dict):
        return True
    findings = report.get("findings")
    if not isinstance(findings, list):
        return True
    for finding in cast("list[object]", findings):
        if not isinstance(finding, dict):
            # A junk entry is not itself a gap, but it must not end the scan:
            # a real gap can sit behind it.
            continue
        if cast("dict[str, object]", finding).get("concern") in (
            MOCK_MODERATED_CONCERNS
        ):
            return True
    return False


def _is_genuine_judgment(finding: object) -> bool:
    """True when one finding entry is evidence of an actual content judgment.

    An entry that is a pipeline artifact (structural, a MOCK_MODERATED_CONCERNS
    concern, or a fail-safe message) is never evidence, regardless of what
    else it carries. An entry matching none of those artifact shapes still
    needs its OWN recognizable genuine-judgment shape (a non-empty
    ``verdict``, the one field every real ``Finding.to_dict()`` output always
    sets) to count: an empty dict, or a truncated row missing the field, is
    not evidence of a genuine judgment either, and must not silently mark the
    whole report usable.

    Args:
        finding: One raw entry from the report's ``findings`` list.

    Returns:
        bool: True only for an entry that is both non-artifact-shaped and
        carries a non-empty ``verdict``.
    """
    if not isinstance(finding, dict):
        return False
    entry = cast("dict[str, object]", finding)
    if entry.get("structural") is True:
        return False
    if entry.get("concern") in MOCK_MODERATED_CONCERNS:
        return False
    message = entry.get("message")
    if isinstance(message, str) and FAIL_SAFE_MESSAGE_SUBSTRING in message:
        return False
    # #CRITICAL: data-integrity: an entry with none of the three artifact
    # shapes above AND no verdict is still not evidence of a genuine
    # judgment; it must not silently mark the whole report usable.
    # #VERIFY: tests/unit/test_moderation_report.py::
    # TestModerationReportUnusable::test_empty_dict_finding_entry_is_unusable,
    # ::test_finding_entry_with_no_recognizable_shape_is_unusable.
    verdict = entry.get("verdict")
    return isinstance(verdict, str) and bool(verdict)


def report_drops_pass_findings(report: dict[str, object] | None) -> bool:
    """True when ``report`` was written by a ``to_dict`` that strips PASS rows.

    The discriminator is ``aggregate.pass_counts``. ``ModerationReport.to_dict``
    began stripping PASS findings from the persisted payload and tallying them
    into that key in ``0396507b`` (2026-08-14); no report written before that
    commit carries it, and every report written after it does, including when
    the tally is empty. Presence of the key is therefore a positive statement
    that PASS rows were removed, not an inference from their absence: a modern
    report that genuinely had no PASS findings and a legacy report that
    genuinely had none are indistinguishable by row content alone.

    Args:
        report: The stored ``moderation_report`` JSONB payload, or ``None``.

    Returns:
        bool: True when the payload carries a well-formed
        ``aggregate.pass_counts`` mapping, meaning any PASS-verdict evidence it
        once held has already been discarded.
    """
    if not isinstance(report, dict):
        return False
    aggregate = report.get("aggregate")
    if not isinstance(aggregate, dict):
        return False
    return isinstance(cast("dict[str, object]", aggregate).get("pass_counts"), dict)


class FailSafeScope(NamedTuple):
    """How much of one story a single source fail-safed invisibly.

    ``nodes`` counts only findings that NAME a node. ``whole_story`` records
    the separate case of a finding naming none, which the two whole-story soft
    stages (coherence, engagement) always produce: they judge the story as a
    unit, so their fail-safe covers every node at once. Collapsing that into
    ``nodes=1`` is what let a total stage outage render as "left 1 node
    unjudged" on a two-hundred-node book, understating coverage loss on the
    surface an ADR-005 approver reads.
    """

    nodes: int
    whole_story: bool


def legacy_hidden_fail_safe_node_counts(
    report: dict[str, object] | None,
) -> dict[str, FailSafeScope]:
    """Count nodes a stage fail-safed INVISIBLY, per source, on LEGACY reports only.

    RETRO-ONLY, and the name says so deliberately. This reads PASS-verdict
    finding rows, and ``ModerationReport.to_dict`` has not persisted a PASS row
    since ``0396507b`` (2026-08-14): they survive only as a category tally in
    ``aggregate.pass_counts``. On any report the pipeline writes today this
    returns ``{}`` no matter how much of the story went unjudged. Its entire
    population is the pre-``0396507b`` backlog this branch exists to
    remediate, and that population SHRINKS to nothing as those books are
    re-moderated into the new shape.

    Forward detection is a different mechanism and is not implemented here:
    it has to live where the information survives persistence, as an
    ``aggregate.fail_safe_counts`` written alongside ``pass_counts`` at
    ``to_dict`` time. Tracked as ``UW-C390``.

    ``moderation_report_unusable`` answers a whole-report question and
    returns ``False`` as soon as ONE genuine finding exists anywhere. That is
    the right shape for the approval gate, but it says nothing about how much
    of the story went unjudged: a report whose ``llm_safety`` stage judged
    every node while ``llm_readability`` defaulted to fail-safe on 88% of
    them is "usable" by that predicate and looks fully reviewed.

    Only the INVISIBLE half of that remainder is counted, and the
    distinction is the fail-safe verdict each stage chooses. Stage 1 safety
    fails safe to FLAG, so its fail-safe rows gate, survive the review
    surface's PASS filter, and already render as flagged passages the
    approver reads. The soft stages fail safe to PASS, so their rows are
    dropped before rendering and vanish. Counting the FLAG rows too would
    describe the same outage twice, once per passage and once in aggregate.

    Structural findings are excluded for the same reason: the pipeline
    already collapses a stage-wide outage into one structural finding that
    carries a gating verdict and surfaces on its own.

    Args:
        report: The stored ``moderation_report`` JSONB payload, or ``None``.

    Returns:
        dict[str, FailSafeScope]: Producing source (or ``"unknown"`` for a row
        naming neither a source nor a category) mapped to that source's
        invisible fail-safe coverage: the count of distinct NAMED nodes, and
        separately whether any matching finding named no node at all and so
        covered the whole story. The two are reported apart rather than summed
        because a whole-story scope is not one more node. An empty dict does
        NOT mean "nothing fell back": it means nothing fell back that this
        scan could see. A malformed or absent report returns empty here on
        purpose, since failing closed on report-level corruption is
        ``moderation_report_unusable``'s job and duplicating it would report a
        corrupt row as an unjudged-node problem it is not. Per-finding
        corruption is the case that predicate does NOT cover, because one
        surviving genuine finding rescues the whole report from it, so the
        rows that are too malformed to classify are counted and logged
        (``hidden_fail_safe_scan_skipped_rows``) rather than passed over in
        silence. The log is the only witness; the return value cannot carry
        the distinction.
    """
    # #CRITICAL: data-integrity: the empty dict this returns is ambiguous by
    # construction. It means "nothing fell back invisibly" on a legacy report
    # and "cannot tell, the evidence was stripped at persist time" on a modern
    # one, and the caller cannot distinguish them from the value. Emit a log on
    # the second case so a silent all-clear over a re-moderated (or freshly
    # generated) book leaves a trace, rather than reading as a clean result.
    # This is a witness, NOT a gate: the notice is display-only and never
    # reaches `severe_finding_counts`, so nothing here can fail closed.
    # #VERIFY: tests/unit/test_moderation_report.py::
    # TestLegacyHiddenFailSafeNodeCounts::
    # test_round_trip_through_to_dict_finds_nothing_and_logs_the_blind_spot.
    if not isinstance(report, dict):
        return {}
    findings = report.get("findings")
    if not isinstance(findings, list):
        return {}
    scopes, malformed_rows = _scan_legacy_fail_safe_rows(cast("list[object]", findings))
    counts = {
        key: FailSafeScope(
            nodes=len({node for node in nodes if node is not None}),
            whole_story=None in nodes,
        )
        for key, nodes in scopes.items()
    }
    if malformed_rows:
        _logger.warning(
            "hidden_fail_safe_scan_skipped_rows",
            malformed_rows=malformed_rows,
            reason=(
                "finding rows that are not well-formed enough to classify "
                "(not a mapping, or a PASS row with a non-string message); "
                "counted here rather than silently treated as absent"
            ),
        )
    if not counts and report_drops_pass_findings(report):
        _logger.info(
            "hidden_fail_safe_scan_blind_on_modern_report",
            reason=(
                "report carries aggregate.pass_counts, so PASS-verdict "
                "fail-safe rows were stripped at persist time; an empty "
                "result here is 'undetectable', not 'none'"
            ),
            follow_up="UW-C390",
        )
    return counts


def _scan_legacy_fail_safe_rows(
    findings: list[object],
) -> tuple[dict[str, set[str | None]], int]:
    """Bucket invisible fail-safe rows by source, counting what it could not read.

    # #CRITICAL: data-integrity: every `continue` below is a row this scan
    # DECLINED to classify, and until the counter existed each one was
    # indistinguishable from "no such row". A stored report whose fail-safe
    # rows were corrupted at rest therefore rendered as a clean, fully judged
    # book. Report-level corruption is covered elsewhere
    # (`moderation_report_unusable` fails closed on it), but per-finding
    # corruption is not: one surviving genuine finding rescues the whole
    # report from that predicate. Counting the declines is the witness that
    # closes the silent half. It is deliberately NOT a gate: this notice is
    # display-only and never reaches `severe_finding_counts`, so there is
    # nothing here to fail closed.
    #
    # Only the DECIDABLE declines are counted. A non-structural PASS row whose
    # message is a string that simply does not match is far more often a
    # genuine clean judgment than a drifted fail-safe row, and counting those
    # would fire on almost every legacy report, which is how a witness becomes
    # noise and stops being read. A structural fail-safe row is likewise
    # excluded on purpose rather than counted: the pipeline collapses a
    # stage-wide outage into exactly one structural finding that carries a
    # gating verdict and surfaces on its own, so it is reported, not hidden.
    # #VERIFY: tests/unit/test_moderation_report.py::
    # TestLegacyHiddenFailSafeNodeCounts::
    # test_a_non_dict_finding_row_is_counted_and_logged,
    # ::test_a_pass_row_with_a_non_string_message_is_counted_and_logged,
    # ::test_ordinary_pass_rows_do_not_trip_the_skipped_row_log.

    Args:
        findings: The raw ``findings`` list from a stored report.

    Returns:
        tuple[dict[str, set[str | None]], int]: Per-source covered scopes
        (``None`` standing for whole-story), and the number of rows too
        malformed to classify either way.
    """
    scopes: dict[str, set[str | None]] = {}
    malformed_rows = 0
    for finding in findings:
        if not isinstance(finding, dict):
            malformed_rows += 1
            continue
        entry = cast("dict[str, object]", finding)
        if entry.get("structural") is True:
            continue
        if entry.get("verdict") != Verdict.PASS.value:
            continue
        message = entry.get("message")
        if not isinstance(message, str):
            # A real Finding always carries a str message, so a PASS row
            # whose message is not one is corrupt at rest rather than clean.
            # Left uncounted, it read as an ordinary judged node.
            malformed_rows += 1
            continue
        if FAIL_SAFE_MESSAGE_SUBSTRING not in message:
            continue
        # Not `entry.get("source") or entry.get("category")`: that form
        # short-circuits on ANY truthy source, so a corrupt non-string one
        # (a list, a number) consumed the slot and the category fallback
        # never ran, silently bucketing the row under "unknown".
        key = _first_usable_label(entry.get("source"), entry.get("category"))
        scopes.setdefault(key, set()).update(_covered_scopes(entry))
    return scopes, malformed_rows


def _first_usable_label(*candidates: object) -> str:
    """Return the first candidate that is a non-empty string.

    Args:
        candidates: Values to try in order, most specific first.

    Returns:
        str: The first usable label, or ``"unknown"`` when none qualifies.
    """
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return "unknown"


def _covered_scopes(entry: dict[str, object]) -> set[str | None]:
    """Return every node one finding covers, or ``{None}`` for whole-story.

    ``node_id`` names only the FIRST node of a merged finding (see
    ``Finding.node_ids``), so counting it alone would under-report a merged
    fail-safe finding by its entire group.

    Args:
        entry: One raw finding entry from a stored report.

    Returns:
        set[str | None]: The distinct node ids covered, or ``{None}`` when
        the finding names no node and therefore covers the whole story.
    """
    node_ids = entry.get("node_ids")
    if isinstance(node_ids, list):
        named = {nid for nid in cast("list[object]", node_ids) if isinstance(nid, str)}
        if named:
            return cast("set[str | None]", named)
    node_id = entry.get("node_id")
    return {node_id if isinstance(node_id, str) else None}


class SevereFindingCounts(NamedTuple):
    """``(block_count, high_severity_flag_count)`` for a stored report.

    A named return type rather than a bare tuple so a transposed unpack at a
    call site (``highs, blocks = severe_finding_counts(...)``) is at least
    visible in review as two same-typed positions instead of an anonymous
    ``tuple[int, int]``; callers should prefer attribute access
    (``counts.block_count``) over positional unpacking entirely.
    """

    block_count: int
    high_severity_flag_count: int


def severe_finding_counts(report: dict[str, object] | None) -> SevereFindingCounts:
    """Return block/high-severity-flag counts for an already-validated report.

    A ``block`` verdict counts once in the first slot regardless of its
    severity; a ``flag`` verdict with ``severity == "high"`` counts in the
    second. Advisories NEVER count here regardless of severity: advisories
    must never gate, and this function feeds the approval override gate and
    its audit payload.

    Args:
        report: The stored ``moderation_report`` JSONB payload. Must already
            have passed ``moderation_report_unusable`` (returning ``False``)
            in the same call; see the ``Raises`` note below.

    Returns:
        SevereFindingCounts: The two counts.

    Raises:
        BusinessLogicError: If ``report`` is not a well-formed mapping with a
            list ``findings`` key, that is, if it is any shape
            ``moderation_report_unusable`` would have rejected. This
            function is always called after that gate (see
            ``publishing/service.py::approve``), so reaching this branch
            means the ordering invariant itself was violated somewhere, not
            that this particular report is malformed content. A loud failure
            here is strictly better than the silent ``(0, 0)`` fail-open
            this function used to return for exactly that case, on a gate
            that exists to keep unreviewed content away from children.
    """
    if not isinstance(report, dict) or not isinstance(report.get("findings"), list):
        msg = (
            "severe_finding_counts requires an already-validated report "
            "(moderation_report_unusable must have returned False first); "
            "got a report shape that gate would have rejected"
        )
        raise BusinessLogicError(msg, rule="severe_finding_counts_precondition")
    findings = cast("list[object]", report["findings"])
    blocks = 0
    highs = 0
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        entry = cast("dict[str, object]", finding)
        if entry.get("verdict") == "block":
            blocks += 1
        elif entry.get("verdict") == "flag" and entry.get("severity") == "high":
            highs += 1
    return SevereFindingCounts(block_count=blocks, high_severity_flag_count=highs)
