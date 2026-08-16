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
from typing import TYPE_CHECKING, Final

from cyo_adventure.storybook.sentinels import strip_sentinels
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

# A skeleton body is a ``<<FILL role=... words=N ...>>`` directive, not prose: it
# is a single run-on clause and therefore always scores outside any band, so
# scoring it emits one meaningless warning per node (746 for a ceiling-scale
# book) and trains reviewers to ignore RL-13 entirely. PL-19 already special-
# cases the same marker; this mirrors it.
_FILL_MARKER = "<<FILL"

# A "word" is a run of letters (optionally with internal apostrophes/hyphens).
# Numbers and standalone punctuation are not counted as words.
_WORD_RE = re.compile(r"[A-Za-z]+(?:['\-][A-Za-z]+)*")

# Sentence terminators. Runs of terminators (``...``, ``?!``) count once.
_SENTENCE_RE = re.compile(r"[.!?]+")

# Bands where prose scoring BELOW the band is not a defect, so RL-13 warns on
# the upper bound only.
#
# Flesch-Kincaid is extrapolating downward here. The formula was calibrated on
# school text and has no floor: a well-formed 3-5 sentence of six monosyllables
# scores about -1.8, which is arithmetic running off the end of its range rather
# than a grade. Measured over the committed corpus with the corrected syllable
# counter (`AL-400`), 3-5 nodes sit at 15.8 percent below their floor against
# 5.1 percent above it, and the below group is prose a four-year-old can follow,
# which is the product working rather than failing. Every other band is roughly
# symmetric and keeps both bounds.
#
# This is deliberately NOT a change to the targets. Those are claims about
# readers, they inherit the old counter's bias, and re-deriving them is a
# separate decision (`UW-C259`); shifting them to preserve the old numbers would
# bake a counting bug into the spec. This only stops reporting one direction at
# the two bands where that direction cannot mean what the finding says.
_UPPER_BOUND_ONLY_BANDS: Final[frozenset[str]] = frozenset({"3-5", "5-8"})

_VOWELS = frozenset("aeiouy")

# ``y`` is a vowel letter but a consonant sound between two vowels, which is
# what splits ``be|yond`` and ``ma|ya``. Kept separate from ``_VOWELS`` so the
# test is about the neighbours, not about ``y`` itself.
_TRUE_VOWELS = frozenset("aeiou")

# Words ending in ``-ed`` where the ``-ed`` is pronounced despite the stem not
# ending in ``t``/``d``. Two kinds, and neither is derivable from spelling:
# adjectival forms (``naked``, ``wicked``) and words that merely end in those
# letters (``hundred``, ``hatred``). Derived from CMUdict rather than from
# memory: of 1,810 ``-ed`` words whose stem is also in the dictionary, only
# these behave this way, which is why the rule below is worth having and why it
# needs a list at all.
_ED_KEEPS_SYLLABLE = frozenset(
    {
        "aged",
        "beloved",
        "blessed",
        "crooked",
        "cursed",
        "dogged",
        "hatred",
        "hundred",
        "jagged",
        "kindred",
        "learned",
        "legged",
        "naked",
        "ragged",
        "rugged",
        "sacred",
        "striped",
        "wicked",
        "wretched",
    }
)

# Consonant-initial suffixes that leave the stem's silent ``e`` stranded in the
# middle of the word, where the trailing-``e`` rule cannot see it: ``care|ful``,
# ``move|ment``, ``some|thing``, ``some|one``. Stripped repeatedly, because
# ``care|ful|ly`` stacks two of them.
_SILENT_E_SUFFIXES = (
    "ly",
    "ful",
    "ness",
    "ment",
    "less",
    "some",
    "thing",
    "where",
    "body",
    "time",
    "most",
    "hood",
    "ship",
    "one",
)

# Vowel pairs that are more often two syllables than one, measured over
# CMUdict: ``ia`` 69% (``d|ia|ry``), ``eo`` 63% (``th|eo``), ``iu`` 82%
# (``med|iu|m``). Every other pair in English is majority-digraph, including
# the tempting ones (``ea`` 12%, ``ie`` 17%, ``io`` 28%), so they are left
# alone: splitting them loses more words than it wins.
_HIATUS_PAIRS = ("ia", "eo", "iu")

# ``-cial``/``-tial``/``-sial`` collapse the ``ia`` back into one syllable
# (``spe|cial``, ``par|tial``), so the ``ia`` rule skips them.
_IA_DIGRAPH_ONSETS = "cts"


def _count_syllables(word: str) -> int:  # noqa: C901, PLR0912
    """Estimate the syllable count of a single word.

    Starts from the vowel-group heuristic (each maximal run of vowel letters is
    one syllable) and then applies the corrections that heuristic demonstrably
    needs. `AL-394` characterised the bare heuristic against CMUdict: it was
    right on 83.0 percent of 115,901 words and 94.2 percent of this corpus's
    tokens, and its errors were systematic in both directions rather than
    random, over-counting every regular ``-ed`` past and under-counting the
    ``-Cle`` words that 3-to-5 prose is built from. That bias reached the
    catalogue: four independent drafting agents swapped regular pasts for
    irregular ones to satisfy a band the counter was misreporting (`AL-389`).

    With the corrections below it is right on 90.3 percent of those words and
    99.1 percent of corpus tokens, and its residual grade bias is -0.02 rather
    than +0.27. Each rule was kept only because it improved accuracy against
    CMUdict; several plausible ones (splitting ``ea``, ``ie`` or ``io``) were
    measured and dropped for making it worse.

    What it still gets wrong, so the next reader does not rediscover it:
    unstressed-vowel deletion (``everything`` is 3, not 4), r-coloured
    ``-ire`` (``entire`` is 3, not 2), and names. A dictionary lookup would
    fix all three and is the obvious next step if this ever needs to arbitrate
    rather than advise.

    Args:
        word: A single alphabetic token (already stripped of surrounding
            punctuation).

    Returns:
        int: The estimated syllable count, never less than 1.
    """
    word = word.lower()

    count = 0
    prev_is_vowel = False
    for index, char in enumerate(word):
        is_vowel = char in _VOWELS
        if (
            char == "y"
            and 0 < index < len(word) - 1
            and word[index - 1] in _TRUE_VOWELS
            and word[index + 1] in _TRUE_VOWELS
        ):
            is_vowel = False
        if is_vowel and not prev_is_vowel:
            count += 1
        prev_is_vowel = is_vowel

    for pair in _HIATUS_PAIRS:
        start = 0
        while (found := word.find(pair, start)) != -1:
            start = found + 1
            if pair == "ia" and found > 0 and word[found - 1] in _IA_DIGRAPH_ONSETS:
                continue
            if pair == "eo" and word[found : found + 3] == "eop":
                continue  # people, jeopardy
            count += 1
    if "uie" in word:
        count += 1  # quiet, quietly: a three-vowel run the pair rules miss

    # A vowel before ``-ing`` is a syllable boundary: go|ing, be|ing, see|ing.
    if word.endswith("ing") and len(word) > 4 and word[-4] in _TRUE_VOWELS:
        count += 1

    if word.endswith("ed") and len(word) > 4 and word not in _ED_KEEPS_SYLLABLE:
        before = word[-3]
        # ``-Cled`` keeps the syllable the ``-Cle`` carried: sett|led, spark|led.
        # A doubled ``ll`` is not that case, so ``pulled`` and ``filled`` are one.
        syllabic_l = before == "l" and word[-4] not in _VOWELS and word[-4] != "l"
        # ``y`` after a vowel is the diphthong spelling, so ``stayed`` is one.
        consonantal = before not in _VOWELS or (
            before == "y" and word[-4] in _TRUE_VOWELS
        )
        if consonantal and before not in "td" and not syllabic_l:
            count -= 1

    stem = word
    if word.endswith("es") and len(word) > 3:
        before = word[-3]
        # ``-es`` is its own syllable after a sibilant (boxes, faces, pages)
        # and after a vowel (carries, galleries); elsewhere it is silent and
        # the ``e`` is the stem's own: comes, takes, lines, gives.
        if not (
            before in "sxzcg"
            or before in _TRUE_VOWELS
            or word.endswith(("ches", "shes"))
        ):
            stem = word[:-2] + "e"
    elif word.endswith("s") and not word.endswith(("ss", "us", "is", "as", "os", "es")):
        stem = word[:-1]

    if stem.endswith("e") and count > 1 and not _has_syllabic_l(stem):
        count -= 1

    head = word
    while True:
        for suffix in _SILENT_E_SUFFIXES:
            if head.endswith(suffix) and len(head) > len(suffix) + 2:
                head = head[: -len(suffix)]
                if head.endswith("e") and not _has_syllabic_l(head) and count > 1:
                    count -= 1
                break
        else:
            break

    return max(count, 1)


def _has_syllabic_l(stem: str) -> bool:
    """Return whether *stem*'s trailing ``e`` carries a syllable rather than being silent.

    A trailing ``e`` after consonant + ``l`` is pronounced: ``lit|tle``,
    ``pud|dle``, ``ap|ple``, ``can|dle``. The bare silent-``e`` rule strips it
    and under-counts every one of them, and they are core 3-to-5 vocabulary
    (`AL-394`). A vowel before the ``l`` keeps the ``e`` silent, which is what
    separates ``candle`` from ``whole`` and ``smile``.

    Args:
        stem: A word or word stem known to end in ``e``.

    Returns:
        bool: ``True`` when the trailing ``e`` is syllabic.
    """
    min_length = 3
    return len(stem) >= min_length and stem[-2] == "l" and stem[-3] not in _VOWELS


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

    This is the single definition of "scorable" in the codebase. A body is
    unscorable when it still carries an unfilled ``<<FILL ...>>`` directive (it
    is an authoring marker, not prose) or when it falls below
    ``_MIN_WORDS_FOR_FK`` words after sentinel stripping (FK is statistically
    noisy on short passages). Both :func:`check_reading_level` and
    :func:`measure_book` route through here, so the per-node rule, the
    whole-book aggregate, and the generation-time repair loop cannot disagree
    about which nodes they are talking about.

    Args:
        body: The raw node body, sentinels and FILL directives intact.

    Returns:
        The Flesch-Kincaid grade, or ``None`` when the body cannot be scored.
    """
    if _FILL_MARKER in body:
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
        grade: Flesch-Kincaid over every scorable body concatenated. This is
            the headline number, and it is NOT the mean of the per-node
            grades: a long node contributes proportionally more to it, which
            is the correct weighting for "how hard is this book to read".
        in_band: Share of *scored* nodes inside the target band. Unscorable
            nodes are excluded from both numerator and denominator, so a book
            with many short nodes reports a higher figure than a whole-book
            reading suggests; compare ``scored_nodes`` against ``nodes`` to
            see how much of the book this number actually covers.
        nodes: Total node bodies considered.
        scored_nodes: How many of them were long enough to score.
        words: Total words across the scorable bodies.
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
    scorable = [strip_sentinels(b) for b in all_bodies if _FILL_MARKER not in b]
    joined = " ".join(scorable)
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

    At the bands in ``_UPPER_BOUND_ONLY_BANDS`` only the upper bound is
    reported: prose too easy for a 3-5 or 5-8 reader is not a defect, and FK
    is extrapolating below zero there. See that constant for the measurement.

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
    upper_bound_only = story.metadata.age_band.value in _UPPER_BOUND_ONLY_BANDS

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
        if fk_grade > upper or (fk_grade < lower and not upper_bound_only):
            report.add(
                ValidationFinding(
                    rule_id="RL-13",
                    severity=Severity.WARNING,
                    story_id=story.id,
                    node_id=node.id,
                    message=(
                        f"RL-13 level: node '{node.id}' FK grade {fk_grade:.1f} "
                        f"{'above' if upper_bound_only else 'outside'} target "
                        f"{target} +/- {tolerance} "
                        f"in story '{story.id}' (advisory only)"
                    ),
                )
            )

    return report
