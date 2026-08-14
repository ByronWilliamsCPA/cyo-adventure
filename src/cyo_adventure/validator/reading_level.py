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
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.storybook.sentinels import strip_sentinels

# A skeleton body is a ``<<FILL role=... words=N ...>>`` directive, not prose: it
# is a single run-on clause and therefore always scores outside any band, so
# scoring it emits one meaningless warning per node (746 for a ceiling-scale
# book) and trains reviewers to ignore RL-13 entirely. PL-19 (policy.py) already
# special-cases the same marker; this mirrors it, from the same shared constant.
from cyo_adventure.validator.policy import FILL_MARKER
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cyo_adventure.storybook.models import Storybook

__all__ = [
    "BookReadingLevel",
    "check_reading_level",
    "measure_book",
    "score_body",
]

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


def score_body(body: str) -> float | None:
    """Return a node body's Flesch-Kincaid grade, or ``None`` if unscorable.

    This is the single definition of "individually scorable" in the codebase.
    A body is unscorable when it still carries an unfilled ``<<FILL ...>>``
    directive (it is an authoring marker, not prose) or when it falls below
    ``_MIN_WORDS_FOR_FK`` words after sentinel stripping (FK is statistically
    noisy on short passages). :func:`check_reading_level`, the per-node half
    of :func:`measure_book` (``scored_nodes``/``in_band``), and the
    generation-time repair loop all route through here, so those three agree
    on which nodes they grade individually. ``measure_book``'s whole-book
    ``grade``/``words`` are a separate aggregate over a broader set (every
    authored, non-``<<FILL`` body, short ones included); see
    :class:`BookReadingLevel` for why that set is intentionally wider.

    Args:
        body: The raw node body, sentinels and FILL directives intact.

    Returns:
        The Flesch-Kincaid grade, or ``None`` when the body cannot be scored.
    """
    if FILL_MARKER in body:
        return None
    stripped = strip_sentinels(body)
    if len(stripped.split()) < _MIN_WORDS_FOR_FK:
        return None
    return _flesch_kincaid_grade(stripped)


@dataclass(frozen=True, slots=True)
class BookReadingLevel:
    """A whole-book reading level: the aggregate RL-13 cannot see.

    RL-13 scores nodes one at a time and is advisory for a good reason: a
    single short body scores noisily. The consequence is that nobody watches
    the book. Three 101-node books measured at whole-book FK 8.14 to 8.41
    against a 5.5 target while the gate returned not-blocked on all three
    (``AL-209``). This type carries the measurement that finding needs.

    Attributes:
        grade: Flesch-Kincaid over every authored (non-``<<FILL``) body
            concatenated. This is the headline number, and it is NOT the mean
            of the per-node grades: a long node contributes proportionally
            more to it, which is the correct weighting for "how hard is this
            book to read". Unlike ``scored_nodes``/``in_band``, this
            concatenation deliberately keeps bodies shorter than
            ``_MIN_WORDS_FOR_FK``: a short body is too noisy to grade on its
            own, but its words still belong in the whole-book text, and the
            concatenation is long regardless of any one body's length.
        in_band: Share of *scored* nodes inside the target band. A node
            counts as scored only when :func:`score_body` returns a grade for
            it (excludes unfilled and sub-floor bodies), and unscored nodes
            are excluded from both numerator and denominator, so a book with
            many short nodes reports a higher figure than a whole-book
            reading suggests; compare ``scored_nodes`` against ``nodes`` to
            see how much of the book this number actually covers.
        nodes: Total node bodies considered.
        scored_nodes: How many of them were long enough to score individually
            (the same ``_MIN_WORDS_FOR_FK`` floor :func:`score_body` applies).
            This is a narrower set than what ``grade``/``words`` cover; see
            those attributes.
        words: Total words across every authored (non-``<<FILL``) body, the
            same set ``grade`` is computed over, not just the ``scored_nodes``
            subset.
    """

    grade: float
    in_band: float
    nodes: int
    scored_nodes: int
    words: int


def measure_book(
    bodies: Iterable[str],
    *,
    target: float,
    tolerance: float,
) -> BookReadingLevel | None:
    """Measure a book's aggregate reading level from its node bodies.

    Args:
        bodies: Every node body in the book, sentinels and FILL directives
            intact (this function strips them itself, exactly as
            :func:`score_body` does).
        target: The book's target Flesch-Kincaid grade.
        tolerance: The half-width of the acceptable band around ``target``.

    Returns:
        The aggregate measurement, or ``None`` when the whole book holds too
        little prose to score at all. ``None`` is a real finding rather than a
        pass: in a filled storybook it means the fill is empty or truncated.
    """
    all_bodies = list(bodies)
    # Every authored (non-FILL) body, short ones included: this is
    # deliberately wider than score_body's per-node floor. See
    # BookReadingLevel.grade/words for why the whole-book aggregate keeps
    # bodies scored_nodes/in_band would exclude as individually too short.
    authored_bodies = [strip_sentinels(b) for b in all_bodies if FILL_MARKER not in b]
    joined = " ".join(authored_bodies)
    if len(joined.split()) < _MIN_WORDS_FOR_FK:
        return None

    per_node = [g for g in (score_body(b) for b in all_bodies) if g is not None]
    in_band = (
        sum(1 for g in per_node if abs(g - target) <= tolerance) / len(per_node)
        if per_node
        else 0.0
    )
    return BookReadingLevel(
        grade=_flesch_kincaid_grade(joined),
        in_band=in_band,
        nodes=len(all_bodies),
        scored_nodes=len(per_node),
        words=len(joined.split()),
    )


def check_reading_level(story: Storybook) -> ValidationReport:
    """Run the RL-13 advisory reading-level check over all story nodes.

    For each node whose body meets the word-count floor, the Flesch-Kincaid
    grade is computed via ``_flesch_kincaid_grade``. If the grade falls outside
    ``[target - tolerance, target + tolerance]`` a WARNING finding is recorded.
    The report's ``ok`` property is always ``True`` because this check never
    emits ERROR findings.

    Nodes with fewer than ``_MIN_WORDS_FOR_FK`` words in their body are skipped
    because FK scores are unreliable on very short passages. Unfilled skeleton
    bodies (those carrying a ``<<FILL`` directive) are skipped too: the directive
    is not prose, so scoring it produces one guaranteed warning per node.

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
        # score_body applies both skips this rule needs, and is the same
        # predicate measure_book and the generation-time repair loop use:
        #   - an unfilled `<<FILL ...>>` marker means the node is not authored
        #     yet, so a grade over it is meaningless;
        #   - a raw `{~SLOTID:GenericWord~}` sentinel would otherwise tokenize
        #     as two words (the slot id and the value), inflating word and
        #     syllable counts, so it is stripped to its inner value before both
        #     the word-count floor and the grade computation;
        #   - FK is noisy below `_MIN_WORDS_FOR_FK` words.
        fk_grade = score_body(node.body)
        if fk_grade is None:
            continue
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
