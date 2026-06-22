"""RL-13 advisory reading-level validator.

Computes the Flesch-Kincaid grade level for each node body in a story and
compares it against the story's target reading level. Findings are always
``WARNING`` severity: RL-13 is advisory only and never blocks a story.

Flesch-Kincaid is computed with a small dependency-free implementation
(``_flesch_kincaid_grade``) rather than a third-party readability package. The
grade formula needs only word, sentence, and syllable counts, so a vendored
implementation avoids pulling a heavy NLP dependency tree (and its transitive
CVE surface) into the runtime for a check that never blocks. The scores are
deterministic and version-stable, which also removes a source of brittle,
library-version-dependent test expectations.

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
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

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

# A "word" is a run of letters (optionally with internal apostrophes/hyphens).
# Numbers and standalone punctuation are not counted as words.
_WORD_RE = re.compile(r"[A-Za-z]+(?:['\-][A-Za-z]+)*")

# Sentence terminators. Runs of terminators (``...``, ``?!``) count once.
_SENTENCE_RE = re.compile(r"[.!?]+")

_VOWELS = frozenset("aeiouy")


def _count_syllables(word: str) -> int:
    """Estimate the syllable count of a single word.

    Uses the standard vowel-group heuristic: each maximal run of vowel letters
    counts as one syllable, a silent trailing ``e`` is removed, and every word
    has at least one syllable. This is the same approximation used by common
    readability libraries and is accurate enough for an advisory grade.

    Args:
        word: A single alphabetic token (already stripped of surrounding
            punctuation).

    Returns:
        int: The estimated syllable count, never less than 1.
    """
    word = word.lower()
    count = 0
    prev_is_vowel = False
    for char in word:
        is_vowel = char in _VOWELS
        if is_vowel and not prev_is_vowel:
            count += 1
        prev_is_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def _flesch_kincaid_grade(text: str) -> float:
    """Compute the Flesch-Kincaid grade level for a passage of prose.

    Implements the standard formula::

        0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59

    A passage with no detectable words returns ``0.0`` (the caller's
    word-count floor means this only guards against pathological input).

    Args:
        text: The body text to score.

    Returns:
        float: The Flesch-Kincaid grade level.
    """
    # finditer yields typed ``Match[str]`` objects, so ``m.group()`` is ``str``
    # (re.findall would return ``list[Any]`` and lose the element type).
    words = [match.group() for match in _WORD_RE.finditer(text)]
    word_count = len(words)
    if word_count == 0:
        return 0.0
    # A passage always counts as at least one sentence even without terminal
    # punctuation, so the words-per-sentence term stays finite.
    sentence_count = max(len(_SENTENCE_RE.findall(text)), 1)
    syllable_count = sum(_count_syllables(word) for word in words)
    return (
        0.39 * (word_count / sentence_count)
        + 11.8 * (syllable_count / word_count)
        - 15.59
    )


def check_reading_level(story: Storybook) -> ValidationReport:
    """Run the RL-13 advisory reading-level check over all story nodes.

    For each node whose body meets the word-count floor, the Flesch-Kincaid
    grade is computed via ``_flesch_kincaid_grade``. If the grade falls outside
    ``[target - tolerance, target + tolerance]`` a WARNING finding is recorded.
    The report's ``ok`` property is always ``True`` because this check never
    emits ERROR findings.

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
        fk_grade = _flesch_kincaid_grade(body)
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
