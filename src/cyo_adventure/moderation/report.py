"""Moderation findings: the structured verdicts every stage appends to one report.

Persisted verbatim on ``storybook_version.moderation_report`` (a JSONB column).
The report is a plain accumulator: stages add findings, the pipeline reads the
``has_hard_block`` / ``has_soft_flag`` flags to drive the state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


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


# Fixed concern taxonomy (design doc 2.1): the dedup/merge key. "other" is
# the degrade target for an unrecognized model-emitted concern (2.2 item 1).
CONCERN_TAXONOMY: frozenset[str] = frozenset(
    {
        "real_world_danger",
        "too_mature",
        "frightening_content",
        "cruelty",
        "sexual_content",
        "self_harm",
        "profanity",
        "reviewer_unavailable",
        "other",
    }
)


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
        concern: Optional machine-readable reason code for a structural
            finding (for example ``"reviewer_unavailable"``); ``None`` for
            genuine content findings.
        severity: Ranking key for the surfaced findings list (design doc
            2.1). ``None`` on old persisted reports and on findings that
            never carried a severity band.
        node_ids: Every node this finding covers, populated by the merge
            stage (design doc 2.2) when identical (category, concern)
            findings collapse into one. ``None`` on an unmerged finding;
            readers should fall back to ``node_id`` in that case.
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
            ValueError: when ``stage`` is outside 0-4 or ``score`` is outside
                ``[0.0, 1.0]`` (a non-None probability/confidence).
        """
        if not 0 <= self.stage <= 4:
            msg = f"Finding.stage must be 0-4, got {self.stage}"
            raise ValueError(msg)
        if self.score is not None and not 0.0 <= self.score <= 1.0:
            msg = f"Finding.score must be in [0.0, 1.0] or None, got {self.score}"
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
        """Return the JSONB payload persisted on the version row."""
        return {
            "findings": [f.to_dict() for f in self.findings],
            "summary": {
                "count": len(self.findings),
                "hard_block": self.has_hard_block,
                "soft_flag": self.has_soft_flag,
                "repaired": self.repaired,
                "reviewer_independent": self.reviewer_independent,
            },
        }
