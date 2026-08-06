"""CH-* character envelope rules (ADR-028 decision 5).

These rules prove that a book declaring ``accepts_character`` is safe across
exactly the states a seeded reader can arrive in. They sit in their own
namespace rather than extending ``L2-*`` because, like ``SR-*``, they prove a
cross-artifact handoff rather than a within-story property: the character comes
from outside the book.

This module ships the rules that need no state-space walk. The remaining
character rules need one and ship in later tasks of this plan, alongside the
walk machinery they depend on.

Deliberately not spelled out as literal rule ids: the catalog lockstep guard
(``tests/unit/test_validator_rules_catalog.py``) scans this file's whole text,
so naming an unimplemented id here would demand a catalog row for a rule that
does not exist yet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.storybook.character_vocabulary import (
    CANONICAL_CHARACTER_VARIABLES,
)
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)
from cyo_adventure.validator.series import _MAX_ENTRY_STATES

if TYPE_CHECKING:
    from cyo_adventure.storybook.models import CharacterRange, Storybook, Variable


def validate_character(story: Storybook) -> ValidationReport:
    """Run every CH-* rule against one story.

    Args:
        story: The parsed story to validate.

    Returns:
        ValidationReport: Findings from all CH-* rules. Empty for a book that
        neither declares ``accepts_character`` nor uses a canonical name.
    """
    report = ValidationReport()
    declared = {variable.name: variable for variable in story.variables}

    if story.accepts_character is None:
        _check_ch6_reserved_names(story, declared, report)
        return report

    _check_ch1_names_and_types(story, declared, report)
    _check_ch2_range_equality(story, declared, report)
    _check_ch5_envelope_size(story, report)
    _check_ch7_series_exclusivity(story, report)
    return report


def _finding(story: Storybook, rule_id: str, message: str) -> ValidationFinding:
    return ValidationFinding(
        rule_id=rule_id,
        severity=Severity.ERROR,
        story_id=story.id,
        message=message,
    )


def _check_ch1_names_and_types(
    story: Storybook, declared: dict[str, Variable], report: ValidationReport
) -> None:
    """CH-1: every envelope name is canonical and declared with a matching type."""
    envelope = story.accepts_character or {}
    for name in sorted(envelope):
        canonical = CANONICAL_CHARACTER_VARIABLES.get(name)
        if canonical is None:
            report.add(
                _finding(
                    story,
                    "CH-1",
                    f"CH-1 character: accepts_character declares '{name}', "
                    f"which is not in the canonical vocabulary "
                    f"{sorted(CANONICAL_CHARACTER_VARIABLES)}",
                )
            )
            continue
        variable = declared.get(name)
        if variable is None:
            report.add(
                _finding(
                    story,
                    "CH-1",
                    f"CH-1 character: accepts_character declares '{name}' but "
                    f"the story declares no variable of that name",
                )
            )
            continue
        if variable.type is not canonical.type:
            report.add(
                _finding(
                    story,
                    "CH-1",
                    f"CH-1 character: '{name}' is declared as "
                    f"{variable.type.value} but the canonical vocabulary "
                    f"defines it as {canonical.type.value}",
                )
            )


def _check_ch2_range_equality(
    story: Storybook, declared: dict[str, Variable], report: ValidationReport
) -> None:
    """CH-2: each envelope range equals the declared variable's bounds.

    Equality rather than containment, because G3's runtime clamp is to
    *declared* bounds. A narrower envelope would let the runtime silently admit
    a state the validator never walked, and the clamp is what makes that
    failure invisible.
    """
    envelope = story.accepts_character or {}
    for name in sorted(envelope):
        variable = declared.get(name)
        if variable is None:
            # CH-1 already reported this; a second finding adds no information.
            continue
        span = envelope[name]
        # #CRITICAL: data integrity: Variable.min and Variable.max default to
        # None, and you cannot equal an absent bound. Treating None as
        # "unbounded, therefore containing" would readmit exactly the silent
        # admission this rule exists to stop.
        # #VERIFY: tests/unit/test_character_rules.py::
        # test_ch2_rejects_a_variable_with_absent_bounds
        if variable.min is None or variable.max is None:
            report.add(
                _finding(
                    story,
                    "CH-2",
                    f"CH-2 character: '{name}' is in accepts_character but "
                    f"declares no min/max bounds; an opted-in variable must "
                    f"declare bounds equal to its envelope range "
                    f"{span.min}-{span.max}",
                )
            )
            continue
        if (variable.min, variable.max) != (span.min, span.max):
            report.add(
                _finding(
                    story,
                    "CH-2",
                    f"CH-2 character: accepts_character range for '{name}' is "
                    f"{span.min}-{span.max} but the variable declares "
                    f"{variable.min}-{variable.max}; they must be equal",
                )
            )


def envelope_size(envelope: dict[str, CharacterRange]) -> int:
    """Return the number of states a character envelope admits.

    The product of each variable's inclusive range width. An empty envelope is
    one state, the empty assignment, which is the mathematically consistent
    value and keeps CH-5 silent for a book that opted in and declared nothing.

    Args:
        envelope: The parsed ``accepts_character`` mapping.

    Returns:
        int: The number of distinct entry states.
    """
    size = 1
    for span in envelope.values():
        size *= span.max - span.min + 1
    return size


def _check_ch5_envelope_size(story: Storybook, report: ValidationReport) -> None:
    """CH-5: an envelope above the entry-state cap is an ERROR, never truncated.

    SR-9 truncates and warns because a series chain's entry-state count is
    emergent from the sending book and the author cannot control it directly.
    An envelope is declared, so exceeding the cap is an authoring mistake with
    an obvious fix, and validating a truncated sample of a declared envelope
    would report a book clean over states nobody walked.
    """
    envelope = story.accepts_character or {}
    size = envelope_size(envelope)
    if size > _MAX_ENTRY_STATES:
        report.add(
            _finding(
                story,
                "CH-5",
                f"CH-5 character: accepts_character admits {size} entry states, "
                f"above the {_MAX_ENTRY_STATES} cap; narrow a range or declare "
                f"fewer variables",
            )
        )


def _check_ch6_reserved_names(
    story: Storybook, declared: dict[str, Variable], report: ValidationReport
) -> None:
    """CH-6: a book that has not opted in may not use a canonical name.

    Without this rule, "a book omitting accepts_character behaves exactly as
    today" is false: G3 carry is name-match, so it seeds *any* book declaring a
    canonical name, opted in or not. The catalog scan found zero current
    clashes, so reserving the names costs nothing today.
    """
    for name in sorted(declared):
        if name in CANONICAL_CHARACTER_VARIABLES:
            report.add(
                _finding(
                    story,
                    "CH-6",
                    f"CH-6 character: '{name}' is a reserved canonical "
                    f"character variable, but this story declares no "
                    f"accepts_character envelope; rename the variable or opt in",
                )
            )


def _check_ch7_series_exclusivity(story: Storybook, report: ValidationReport) -> None:
    """CH-7: no character in a non-first book of a state-carrying series.

    Two independent sources of carried state entering one book is a
    composition this design has not proved, so v1 forbids it outright rather
    than guessing at precedence.
    """
    series = story.metadata.series
    if series is None:
        return
    if series.carries_state and series.book_index > 1:
        report.add(
            _finding(
                story,
                "CH-7",
                f"CH-7 character: book {series.book_index} of state-carrying "
                f"series '{series.series_id}' may not also declare "
                f"accepts_character",
            )
        )
