"""Hold `_count_syllables` to known answers, and to the accuracy it was fixed to.

History, because the numbers below only mean something against it. `AL-378`
reported one defect: the reading-level checker over-counted every regular
``-ed`` past, and four independent drafting agents had responded by swapping
regular verbs for irregular ones to satisfy a band the counter was
misreporting. Characterising it (`AL-383`) found three error classes rather
than one, pointing in two directions: ``-ed`` over-counting, and ``-Cle`` and
vowel-run under-counting. This file first landed asserting all of those WRONG
answers on purpose, so the fix could not arrive quietly.

`AL-388` is that fix, and it was built against ground truth rather than
intuition: CMUdict's 115,901 unambiguously-syllabified words, plus this
corpus's own 390,334 tokens for a use-weighted view. Every rule in the counter
earned its place by improving accuracy on that set, and several plausible ones
were measured and thrown away for making it worse (splitting ``ea``, ``ie`` or
``io``, all majority-digraph in English).

    accuracy          before     after
    dictionary types  83.03%     90.32%
    corpus tokens     94.21%     99.14%
    FK grade bias     +0.268     -0.031

The bias line is the one that mattered: the counter was adding a quarter of a
grade to every passage it scored, which is a fifth of the 3-to-5 band's entire
tolerance.

This file now asserts the true answer wherever the counter reaches it, and
pins the three it still misses with the measurement that says leaving them is
correct. `AL-356` remains the standing rule: a deterministic measure does not
get to arbitrate before its accuracy has been checked, and "checked" means
against an external answer key, not against the account of it in a bug report.
"""

from __future__ import annotations

import pytest

from cyo_adventure.validator.reading_level import (
    _count_syllables,  # pyright: ignore[reportPrivateUsage]
)

# (word, true syllables). Grouped by the phonological rule that governs them, so
# a regression names its own cause.
_REGULAR_ED_SILENT: tuple[tuple[str, int], ...] = (
    # "-ed" after a non-t/d consonant is silent: one syllable, not two. This was
    # the reported defect, and it is the largest single class by corpus
    # frequency: `turned`, `looked`, `reached`, `climbed`, `opened`, `stopped`,
    # `closed` and `sealed` together account for over 1,500 tokens here.
    ("walked", 1),
    ("asked", 1),
    ("jumped", 1),
    ("reached", 1),
    ("stacked", 1),
    ("watched", 1),
    ("laughed", 1),
    # The doubled-l pair. These look like the syllabic "-Cled" case below
    # (`settled`, `sparkled`) and are not it, so the rule has to tell `pulled`
    # from `settled` on the letter before the l.
    ("pulled", 1),
    ("filled", 1),
    ("turned", 1),
)

_ED_SYLLABIC: tuple[tuple[str, int], ...] = (
    # "-ed" after t or d IS pronounced. Correct before the fix and after it; the
    # naive repair would have been to key on the preceding letter alone, and
    # these are half of why that fails.
    ("wanted", 2),
    ("landed", 2),
    ("counted", 2),
    ("waited", 2),
    ("needed", 2),
)

_ED_ADJECTIVAL: tuple[tuple[str, int], ...] = (
    # The other half. These end in "-ed" after a non-t/d consonant, exactly like
    # `walked`, and pronounce it anyway. No spelling rule separates them, so the
    # counter carries a list. The list is not from memory: of 1,810 "-ed" words
    # whose stem is also in CMUdict, these are essentially all of the exceptions,
    # which is what makes a 19-entry list a complete answer rather than a patch.
    ("sacred", 2),
    ("naked", 2),
    ("wicked", 2),
    ("ragged", 2),
    ("crooked", 2),
    ("rugged", 2),
)

_CLE_SYLLABIC: tuple[tuple[str, int], ...] = (
    # The second error class, found by writing this file rather than by reading
    # the code, and pointing the opposite way to the first. The silent-trailing-e
    # rule fired on "-Cle" endings where the e is not silent at all: it carries
    # the syllable. These were each under-counted by one, and they are exactly
    # the vocabulary a 3-to-5 book is made of.
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

_VOWEL_RUN_FIXED: tuple[tuple[str, int], ...] = (
    # The third class, partly repaired. Adjacent vowels spanning a syllable
    # boundary collapsed into one group. `ia` is hiatus in 69 percent of
    # dictionary words carrying it, so splitting it wins; `quiet` needed its own
    # three-vowel case.
    ("quiet", 2),
    ("diary", 3),
)

_VOWEL_RUN_STILL_WRONG: tuple[tuple[str, int], ...] = (
    # And the part deliberately left alone, which is the interesting half. These
    # need `io`, `oe` and `ea` to split, and measured over CMUdict those pairs
    # are hiatus in only 28, 12 and 12 percent of the words that carry them
    # (`nation`, `shoe`, `beach`, `bread`, `each`). Splitting any of them costs
    # more words than it wins, so the counter keeps three known-wrong answers in
    # exchange for thousands of right ones. Asserting the wrong answer here is
    # the record of that trade: if a later fix reaches them without breaking the
    # majority case, this test is where it says so.
    ("lion", 2),
    ("poem", 2),
    ("cereal", 3),
)

_CONTROL: tuple[tuple[str, int], ...] = (
    # Ordinary words, to catch a fix that fires wider than intended.
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

_SUFFIX_AND_PLURAL: tuple[tuple[str, int], ...] = (
    # Two further classes the fix had to add, both invisible to the original
    # trailing-e rule because the silent e is not at the end of the word.
    # A consonant-initial suffix strands it in the middle, and it stacks
    # (`care|ful|ly`); a plural or third-person -s hides it behind one letter.
    ("careful", 2),
    ("carefully", 3),
    ("movement", 2),
    ("something", 2),
    ("someone", 2),
    ("lovely", 2),
    ("comes", 1),
    ("takes", 1),
    ("lines", 1),
    ("gives", 1),
    # ...but -es IS its own syllable after a sibilant or a vowel, which is what
    # keeps the rule from eating these.
    ("faces", 2),
    ("boxes", 2),
    ("wishes", 2),
    ("carries", 2),
    # A vowel before -ing is a syllable boundary, and `y` between two vowels is
    # a consonant sound.
    ("going", 2),
    ("being", 2),
    ("beyond", 2),
    ("stayed", 1),
    ("settled", 2),
)

_CORRECT: tuple[tuple[str, int], ...] = (
    _REGULAR_ED_SILENT
    + _ED_SYLLABIC
    + _ED_ADJECTIVAL
    + _CLE_SYLLABIC
    + _VOWEL_RUN_FIXED
    + _CONTROL
    + _SUFFIX_AND_PLURAL
)


@pytest.mark.unit
@pytest.mark.parametrize(("word", "truth"), _CORRECT)
def test_the_counter_gets_these_right(word: str, truth: int) -> None:
    """Every word the fix reaches, in one assertion so a regression names itself.

    Six rule groups, all of which the counter got wrong or right for reasons
    worth keeping: the two "-ed" directions, the syllabic "-Cle", the hiatus
    split, the stranded silent e, and the plural rules that distinguish
    ``comes`` from ``faces``.
    """
    assert _count_syllables(word) == truth


@pytest.mark.unit
@pytest.mark.parametrize(("word", "truth"), _VOWEL_RUN_STILL_WRONG)
def test_the_deliberately_unfixed_vowel_pairs_are_still_wrong(
    word: str, truth: int
) -> None:
    """Assert the WRONG answer, because fixing it would cost more than it saves.

    ``io``, ``oe`` and ``ea`` are hiatus in a minority of the English words that
    carry them, so a rule splitting them loses ``nation``, ``shoe``, ``beach``
    and ``bread`` to win ``lion``, ``poem`` and ``cereal``. That trade was
    measured, not assumed. If a later fix separates the cases properly, this
    test fails, which is the intended signal.
    """
    assert _count_syllables(word) == truth - 1, (
        f"{word!r} now counts correctly; if the hiatus rules were extended, "
        "update this test and re-measure the dictionary accuracy"
    )


@pytest.mark.unit
def test_the_known_answer_set_is_almost_entirely_correct_now() -> None:
    """The headline: 42 of 45, against 20 of 45 before the fix.

    The curated set is deliberately adversarial, over-weighted toward the rules
    the counter had wrong, so it understates the corpus-level improvement
    (94.21 to 99.14 percent of tokens). It is the right set to hold a fix to
    precisely because it is unrepresentative in that direction.
    """
    curated = _CORRECT + _VOWEL_RUN_STILL_WRONG
    correct = sum(1 for word, truth in curated if _count_syllables(word) == truth)

    assert len(curated) == 64
    assert correct == len(curated) - len(_VOWEL_RUN_STILL_WRONG)
