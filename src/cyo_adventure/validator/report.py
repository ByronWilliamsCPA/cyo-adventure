"""Validation report types shared by every validator layer.

A :class:`ValidationReport` collects :class:`ValidationFinding` records. Each
finding carries a stable rule id (from ``docs/planning/validator-rules.md``), a
severity, and node/choice attribution so that repair-stage prompts and the
known-bad corpus can reference the exact violation. A report ``ok`` only when it
holds no error-severity findings; warning-severity findings (for example, a
story below the lower node-count bound) do not block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    """Severity of a validation finding.

    ``ERROR`` blocks the story; ``WARNING`` is advisory and never blocks.
    """

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """A single rule violation with stable id and attribution.

    Attributes:
        rule_id: The stable rule id, for example ``"L1-3"``.
        severity: Whether the finding blocks (``ERROR``) or warns (``WARNING``).
        story_id: The ``id`` of the story the finding applies to.
        message: The human-readable failure message (rule-template formatted).
        node_id: The node the finding attributes to, if any.
        choice_id: The choice the finding attributes to, if any.
    """

    rule_id: str
    severity: Severity
    story_id: str
    message: str
    node_id: str | None = None
    choice_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Return the finding as a JSON-serializable mapping.

        Returns:
            dict[str, str | None]: The finding in the report wire format.
        """
        return {
            "rule_id": self.rule_id,
            "severity": str(self.severity),
            "story_id": self.story_id,
            "node_id": self.node_id,
            "choice_id": self.choice_id,
            "message": self.message,
        }


@dataclass(slots=True)
class ValidationReport:
    """An ordered collection of validation findings.

    Attributes:
        findings: Every finding recorded, in the order rules were applied.
    """

    findings: list[ValidationFinding] = field(default_factory=list)

    def add(self, finding: ValidationFinding) -> None:
        """Append a finding to the report.

        Args:
            finding: The finding to record.
        """
        self.findings.append(finding)

    @property
    def errors(self) -> list[ValidationFinding]:
        """Return only the error-severity findings.

        Returns:
            list[ValidationFinding]: Findings that block the story.
        """
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationFinding]:
        """Return only the warning-severity findings.

        Returns:
            list[ValidationFinding]: Findings that are advisory only.
        """
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        """Report whether the story passes (no error-severity findings).

        Returns:
            bool: ``True`` when there are no error-severity findings.
        """
        return not self.errors

    def rule_ids(self) -> set[str]:
        """Return the set of rule ids present in the report.

        Returns:
            set[str]: Every distinct rule id across all findings.
        """
        return {f.rule_id for f in self.findings}

    def to_dict(self) -> dict[str, object]:
        """Return the whole report as a JSON-serializable mapping.

        Returns:
            dict[str, object]: ``ok`` plus the list of findings.
        """
        return {
            "ok": self.ok,
            "findings": [f.to_dict() for f in self.findings],
        }
