"""Characterise `_count_syllables` against known answers, before anyone changes it.

`AL-378` found that the reading-level checker over-counts every regular ``-ed``
past by one syllable, quietly pushing the catalogue's prose toward irregular
verbs. `UW-C254` schedules the fix. The grade figures first reported alongside it
(0.16 to 0.55) corrected only that one error and are superseded by `AL-383`:
with all three classes below corrected, the inflation runs 0.10 to 0.84 grades,
and it is LARGEST in the 3-5 band, where the whole tolerance is plus or minus
1.0.

This file exists because of `AL-356`: a deterministic measure must not arbitrate
before its own accuracy has been checked. The obvious repair, dropping the
syllable whenever the letter before ``ed`` is not ``t`` or ``d``, is wrong, and
the adjectival cases below are why. So rather than shipping a guess, this pins
what the counter does *today*, correct answers included, so that:

* the size and shape of the error is a measurement rather than an anecdote,
  which already paid for itself: writing this file found two further error
  classes pointing the OPPOSITE way, so "the counter inflates grades" was
  true on balance and incomplete as a description,
* a proposed fix can be scored against the same set instead of against intuition,
* and any fix that trades one systematic error for another is visible at once.

Words are grouped by the phonological rule that governs them. The expected
counts are ordinary British/American dictionary syllabifications; where a word is
genuinely two-way (``every`` as 2 or 3) it is excluded rather than argued about.

The suite deliberately does NOT assert that the counter is correct. It asserts
the currently-known-wrong cases are still wrong, so the fix that lands is forced
to update this file and state what it changed.
"""

from __future__ import annotations

import pytest

from cyo_adventure.validator.reading_level import (
    _count_syllables,  # pyright: ignore[reportPrivateUsage]
)

# (word, true syllables). Grouped by rule so a regression names its own cause.
_REGULAR_ED_SILENT: tuple[tuple[str, int], ...] = (
    # "-ed" after a non-t/d consonant is silent: one syllable, not two.
    ("walked", 1),
    ("asked", 1),
    ("jumped", 1),
    ("reached", 1),
    ("stacked", 1),
    ("watched", 1),
    ("laughed", 1),
    ("pulled", 1),
    ("filled", 1),
    ("turned", 1),
)

_ED_SYLLABIC: tuple[tuple[str, int], ...] = (
    # "-ed" after t or d IS pronounced, so these are already correct today and
    # a naive fix must not break them.
    ("wanted", 2),
    ("landed", 2),
    ("counted", 2),
    ("waited", 2),
    ("needed", 2),
)

_ED_ADJECTIVAL: tuple[tuple[str, int], ...] = (
    # The trap. These end in "-ed" after a non-t/d consonant, exactly like the
    # first group, and yet the "-ed" IS pronounced. Any rule keyed only on the
    # preceding letter breaks every one of them, and the counter gets them all
    # right today.
    ("sacred", 2),
    ("naked", 2),
    ("wicked", 2),
    ("ragged", 2),
    ("crooked", 2),
    ("rugged", 2),
)

_CLE_UNDER_COUNTED: tuple[tuple[str, int], ...] = (
    # A SECOND systematic error, found by writing this file rather than by
    # reading the code, and pointing the opposite way. The silent-trailing-e
    # rule fires on "-Cle" endings where the e is not silent at all: it carries
    # the syllable. These are under-counted by one, and they are exactly the
    # vocabulary a 3-to-5 book is made of.
    ("little", 2),
    ("puddle", 2),
    ("giggle", 2),
    ("bubble", 2),
    ("apple", 2),
    ("sparkle", 2),
    ("twinkle", 2),
    ("candle", 2),
    ("gentle", 2),
    ("middle", 2),
)

_VOWEL_RUN_UNDER_COUNTED: tuple[tuple[str, int], ...] = (
    # A THIRD class: adjacent vowels spanning a syllable boundary collapse into
    # one group, so every one of these loses a syllable.
    ("quiet", 2),
    ("lion", 2),
    ("poem", 2),
    ("diary", 3),
    ("cereal", 3),
)

_CONTROL: tuple[tuple[str, int], ...] = (
    # Ordinary words the counter gets right, to catch a fix that fires wider
    # than intended.
    ("cat", 1),
    ("mitten", 2),
    ("balloon", 2),
    ("lantern", 2),
    ("adventure", 3),
    ("beautiful", 3),
    ("went", 1),
    ("came", 1),
    ("held", 1),
)


def _score(cases: tuple[tuple[str, int], ...]) -> tuple[int, int]:
    """Return (correct, total) for *cases* under the current counter."""
    correct = sum(1 for word, truth in cases if _count_syllables(word) == truth)
    return correct, len(cases)


@pytest.mark.unit
@pytest.mark.parametrize(("word", "truth"), _REGULAR_ED_SILENT)
def test_regular_ed_pasts_are_over_counted_today(word: str, truth: int) -> None:
    """The known defect, pinned so a fix has to come here and change it.

    This asserts the WRONG answer on purpose. `UW-C254`'s fix will make these
    fail, which is the point: the failure is the signal that the fix landed, and
    whoever lands it must update this file and say so.
    """
    assert _count_syllables(word) == truth + 1, (
        f"{word!r} now counts correctly; if UW-C254 has landed, update this test"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("word", "truth"), _CLE_UNDER_COUNTED + _VOWEL_RUN_UNDER_COUNTED
)
def test_two_further_error_classes_under_count_today(word: str, truth: int) -> None:
    """Also asserting the wrong answer, and these were the surprise.

    `AL-378` was reported as "the counter inflates grades", which is true on
    balance and was not the whole story. The silent-e rule strips the e from
    "-Cle" words where it is syllabic, and adjacent vowels across a syllable
    boundary collapse into one group. Both push DOWN, partly offsetting the
    "-ed" error, and the "-Cle" group is core 3-to-5 vocabulary.

    Found by writing this file. The first pass asserted these were correct,
    because the hypothesis under test was the one that had been handed to me,
    which is the same trap `AL-356` records.
    """
    assert _count_syllables(word) == truth - 1, (
        f"{word!r} now counts correctly; if UW-C254 has landed, update this test"
    )


@pytest.mark.unit
@pytest.mark.parametrize(("word", "truth"), _ED_SYLLABIC + _ED_ADJECTIVAL + _CONTROL)
def test_the_cases_a_naive_ed_fix_would_break_are_correct_today(
    word: str, truth: int
) -> None:
    """Every one of these is right now and must still be right after the fix.

    The adjectival group is the reason `UW-C254` is not a two-line change:
    ``sacred``, ``naked``, ``wicked``, ``ragged``, ``crooked`` and ``rugged``
    all end in "-ed" after a non-t/d consonant, exactly like ``walked``, and
    all pronounce it. A rule keyed on the preceding letter alone scores 10 more
    words right and 6 previously-right words wrong.
    """
    assert _count_syllables(word) == truth


@pytest.mark.unit
def test_the_error_spans_three_rules_in_two_directions() -> None:
    """Overall accuracy, so a fix's benefit can be stated as a number.

    The baseline `UW-C254` has to beat, and the reason it is not a two-line
    change: the error is not one rule but three, and they do not all point the
    same way. Correcting only the reported "-ed" case leaves fifteen of these
    words wrong and moves every grade further from truth in the other direction.
    """
    wrong_groups = _REGULAR_ED_SILENT + _CLE_UNDER_COUNTED + _VOWEL_RUN_UNDER_COUNTED
    right_groups = _ED_SYLLABIC + _ED_ADJECTIVAL + _CONTROL

    wrong_correct, wrong_total = _score(wrong_groups)
    right_correct, right_total = _score(right_groups)

    assert wrong_correct == 0, "all three known-bad groups should still be wrong"
    assert right_correct == right_total, "the known-good groups should stay right"
    # 25 of 45 words wrong, across THREE rules pointing in TWO directions. The
    # "-ed" group over-counts; the other two under-count and partly cancel it.
    # A fix that addresses only the reported "-ed" error leaves 15 wrong and
    # shifts every grade the other way.
    assert wrong_total == 25
    assert wrong_total + right_total == 45
