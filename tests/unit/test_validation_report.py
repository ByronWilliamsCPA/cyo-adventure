"""Unit tests for :class:`ValidationReport`'s collection behaviour.

``report.py`` is the aggregation type every validator layer returns, but it had
no dedicated test module: its behaviour was only ever exercised incidentally
through whichever layer happened to build one. These tests cover the merge
operation directly, because ``gate.py`` composes eight sub-reports into one and
the ordering it produces is what a reader of a failing gate sees first.
"""

from __future__ import annotations

from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)


def _finding(rule_id: str) -> ValidationFinding:
    """Build a minimal finding carrying only the rule id under test."""
    return ValidationFinding(
        rule_id=rule_id,
        severity=Severity.ERROR,
        story_id="story-1",
        message=f"{rule_id} fired",
    )


def test_extend_appends_every_finding_in_source_order() -> None:
    """A merged report preserves the order rules were applied in."""
    target = ValidationReport()
    target.add(_finding("L1-1"))
    source = ValidationReport()
    source.add(_finding("PL-27"))
    source.add(_finding("PL-19"))

    target.extend(source)

    assert [f.rule_id for f in target.findings] == ["L1-1", "PL-27", "PL-19"]


def test_extend_from_an_empty_report_is_a_no_op() -> None:
    """Merging an empty sub-report leaves the target untouched.

    Most layers return an empty report on a clean story, so this is the common
    case rather than an edge case.
    """
    target = ValidationReport()
    target.add(_finding("L1-1"))

    target.extend(ValidationReport())

    assert [f.rule_id for f in target.findings] == ["L1-1"]


def test_extend_does_not_alias_the_source_list() -> None:
    """The target must copy, not adopt, the source's backing list.

    An aliased list would let a later ``add`` on either report mutate the
    other, which in ``run_gate`` would mean one layer's findings appearing in
    another layer's report.
    """
    target = ValidationReport()
    source = ValidationReport()
    source.add(_finding("PL-27"))

    target.extend(source)
    target.add(_finding("L2-9"))

    assert [f.rule_id for f in source.findings] == ["PL-27"]
