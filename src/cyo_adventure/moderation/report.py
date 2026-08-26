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
    report = cast("dict[str, object]", report)
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
