"""Tests for the shared sentence splitter (UW-C255, AL-379).

Each test pins one of the required behaviours from the register row: common
abbreviations, terminal punctuation inside a quoted utterance, a run of
terminators counting once, and a mid-sentence ellipsis. The `Mr. Fez` case is
included verbatim because it is the concrete defect that motivated this
module (CG-4 borrowing `diversity.normalize.split_sentences`, whose own
docstring says it is "crude, not linguistic sentences").
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from cyo_adventure.utils.sentences import SentenceSpan, sentence_spans, split_sentences

# ---------------------------------------------------------------------------
# Abbreviations
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mr_fez_opening_sentence_is_the_whole_sentence_not_the_abbreviation() -> None:
    """The exact CG-4 defect: `Mr.` must not be read as a whole sentence."""
    body = "Mr. Fez's table was a tiny hospital for toys."
    sentences = split_sentences(body)
    assert sentences == [body]


@pytest.mark.unit
@pytest.mark.parametrize(
    "abbreviation",
    ["Mr.", "Mrs.", "Ms.", "Dr.", "St.", "Jr.", "Sr.", "vs.", "etc.", "e.g.", "i.e."],
)
def test_common_abbreviation_does_not_end_a_sentence(abbreviation: str) -> None:
    body = f"We saw {abbreviation} Something happen next."
    assert len(split_sentences(body)) == 1


@pytest.mark.unit
def test_a_real_period_after_a_non_abbreviation_word_does_end_a_sentence() -> None:
    """Guard the other direction: this is not a splitter that never splits."""
    body = "St. Louis is nice. It rains a lot there."
    assert split_sentences(body) == ["St. Louis is nice.", "It rains a lot there."]


@pytest.mark.unit
@pytest.mark.parametrize("form", ["e.g.", "i.e."])
def test_the_first_dot_of_e_g_or_i_e_does_not_end_a_sentence_either(
    form: str,
) -> None:
    """Both dots of a two-dot abbreviation must be protected, not just the second."""
    body = f"Bring supplies, {form} water and food. Pack them well."
    assert split_sentences(body) == [
        f"Bring supplies, {form} water and food.",
        "Pack them well.",
    ]


@pytest.mark.unit
def test_a_plain_period_before_a_lowercase_word_still_ends_a_sentence() -> None:
    """The corpus's own bare, unquoted dialogue tag ("X. said Pip.") must not
    be read as a continuation: a single "." that is not a listed
    abbreviation always ends a sentence, regardless of what case follows.
    """
    body = "It was cold, cold, cold. said Pip."
    assert split_sentences(body) == ["It was cold, cold, cold.", "said Pip."]


# ---------------------------------------------------------------------------
# Terminal punctuation inside a quoted utterance
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_quoted_exclamation_followed_by_a_lowercase_tag_is_one_sentence() -> None:
    body = '"Run now!" she called.'
    assert split_sentences(body) == [body]


@pytest.mark.unit
def test_an_unquoted_tagged_line_ending_in_a_bang_is_one_sentence() -> None:
    """Mirrors the corpus's untagged-quote house style (AL-379 dialogue case)."""
    body = "Right here! he whispered."
    assert split_sentences(body) == [body]


@pytest.mark.unit
def test_two_separate_quoted_sentences_split_apart() -> None:
    body = '"Stop!" "Wait!"'
    assert split_sentences(body) == ['"Stop!"', '"Wait!"']


# ---------------------------------------------------------------------------
# Runs of terminators count once
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_bang_question_run_is_one_boundary_not_two() -> None:
    body = "Wait?! Are you sure?"
    assert split_sentences(body) == ["Wait?!", "Are you sure?"]


@pytest.mark.unit
def test_an_ellipsis_at_sentence_end_is_one_boundary() -> None:
    body = "Wait... What was that?"
    assert split_sentences(body) == ["Wait...", "What was that?"]


# ---------------------------------------------------------------------------
# Mid-sentence ellipsis
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_ellipsis_followed_by_lowercase_is_a_pause_not_a_boundary() -> None:
    body = "She waited... and then ran."
    assert split_sentences(body) == [body]


@pytest.mark.unit
def test_an_ellipsis_followed_by_uppercase_is_a_real_boundary() -> None:
    body = "She paused... Then she left."
    assert split_sentences(body) == ["She paused...", "Then she left."]


# ---------------------------------------------------------------------------
# General behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_text_yields_no_sentences() -> None:
    assert split_sentences("") == []


@pytest.mark.unit
def test_text_with_no_terminal_punctuation_is_one_sentence() -> None:
    assert split_sentences("no ending here") == ["no ending here"]


@pytest.mark.unit
def test_multiple_ordinary_sentences_split_correctly() -> None:
    body = "The cat sat. The dog ran. Nobody noticed."
    assert split_sentences(body) == [
        "The cat sat.",
        "The dog ran.",
        "Nobody noticed.",
    ]


@pytest.mark.unit
def test_sentence_spans_partition_the_whole_text_with_no_gaps() -> None:
    body = "The cat sat. The dog ran."
    spans = sentence_spans(body)
    assert spans[0].start == 0
    assert spans[-1].end == len(body)
    for previous, current in pairwise(spans):
        assert previous.end == current.start


@pytest.mark.unit
def test_sentence_spans_returns_the_dataclass_with_raw_unstripped_text() -> None:
    body = "First. Second."
    spans = sentence_spans(body)
    assert spans == [
        SentenceSpan(0, 6, "First."),
        SentenceSpan(6, 14, " Second."),
    ]
