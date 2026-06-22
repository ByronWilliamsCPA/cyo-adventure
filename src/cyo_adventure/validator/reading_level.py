"""RL-13 advisory reading-level validator.

Computes the Flesch-Kincaid grade level for each node body in a story and
compares it against the story's target reading level. Findings are always
``WARNING`` severity: RL-13 is advisory only and never blocks a story.

Word-count floor
----------------
FK scores are unreliable on short passages (< 20 words), so nodes whose body
falls below ``_MIN_WORDS_FOR_FK`` are silently skipped. The floor is a module
constant so callers can inspect it in tests.

Usage::

    from cyo_adventure.validator.reading_level import check_reading_level

    report = check_reading_level(story)
    # report.ok is always True; report.warnings lists any RL-13 advisories.

Rule source: ``docs/planning/validator-rules.md`` section RL-13.

#ASSUME: external-resources: textstat is installed as a runtime dependency.
#VERIFY: ``uv add textstat`` and confirm importable before deployment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

# textstat has no PEP 561 type stubs; the direct import avoids the
# reportAttributeAccessIssue basedpyright raises on the module attribute.
# The return value is cast to float because textstat's public API is typed
# in documentation as ``float`` but the package ships no inline types.
from textstat import (
    flesch_kincaid_grade as _fk_grade_fn,  # type: ignore[import-untyped]
)

from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)

if TYPE_CHECKING:
    from cyo_adventure.storybook.models import Storybook

# FK scores on bodies shorter than this word count are statistically noisy.
# The threshold matches the minimum recommended by most readability literature
# for Flesch-Kincaid stability (roughly one paragraph of prose).
_MIN_WORDS_FOR_FK: int = 20


def check_reading_level(story: Storybook) -> ValidationReport:
    """Run the RL-13 advisory reading-level check over all story nodes.

    For each node whose body meets the word-count floor, the Flesch-Kincaid
    grade is computed via ``textstat.flesch_kincaid_grade``. If the grade falls
    outside ``[target - tolerance, target + tolerance]`` a WARNING finding is
    recorded. The report's ``ok`` property is always ``True`` because this
    check never emits ERROR findings.

    Nodes with fewer than ``_MIN_WORDS_FOR_FK`` words in their body are skipped
    because FK scores are unreliable on very short passages.

    Args:
        story: The validated Storybook to check.

    Returns:
        ValidationReport: All RL-13 advisory findings; ``report.ok`` is
            always ``True``.
    """
    report = ValidationReport()
    target = story.metadata.reading_level.target
    tolerance = story.metadata.reading_level.tolerance
    lower = target - tolerance
    upper = target + tolerance

    for node in story.nodes:
        body = node.body
        if len(body.split()) < _MIN_WORDS_FOR_FK:
            continue
        fk_grade: float = cast("float", _fk_grade_fn(body))
        if fk_grade < lower or fk_grade > upper:
            report.add(
                ValidationFinding(
                    rule_id="RL-13",
                    severity=Severity.WARNING,
                    story_id=story.id,
                    node_id=node.id,
                    message=(
                        f"RL-13 level: node '{node.id}' FK grade {fk_grade:.1f} "
                        f"outside target {target} +/- {tolerance} "
                        f"in story '{story.id}' (advisory only)"
                    ),
                )
            )

    return report
