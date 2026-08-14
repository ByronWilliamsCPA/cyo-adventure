"""Pin the dialogue detector against the corpus convention that defeated three others.

The module exists because `evaluate_books.py`, `check_prose_craft.py` and
`seed_defects.py` each counted dialogue by looking for a quotation mark, and the
catalogue writes its speech without them. These tests are therefore mostly about
the *unquoted* case; the quoted cases are here so a later tightening of the tag
patterns cannot quietly cost the easy half.
"""

from __future__ import annotations

import pytest

from cyo_adventure.validator.dialogue import (
    dialogue_share,
    flatten,
    has_dialogue,
    sentence_share,
    spoken_spans,
    strip_dialogue,
    strip_tagged,
)

# Verbatim from `the-backyard-treasure-map`, the book that scored 0.000 on every
# quote-based measure in this repository while carrying fifteen spoken lines.
_UNQUOTED = "Let's try this one, they said. Right here! he whispered."


@pytest.mark.unit
def test_tagged_speech_without_quotation_marks_is_dialogue() -> None:
    """The whole point: the corpus convention must not read as narration."""
    assert spoken_spans(_UNQUOTED) == [
        "Let's try this one, they said.",
        "Right here! he whispered.",
    ]


@pytest.mark.unit
def test_a_bare_speech_verb_is_narration_not_dialogue() -> None:
    """Guard the other failure mode: a detector that fires on everything.

    "asked" and "told" appear constantly in ordinary narration. Without the
    tag-position requirement this module would replace an insensitive measure
    with a saturated one, which is worse: an insensitive measure at least
    reports zero honestly.
    """
    assert not has_dialogue("She asked for help and nobody came.")
    assert not has_dialogue("The map told a different story that morning.")


@pytest.mark.unit
def test_a_spoken_line_ending_in_a_bang_is_one_span_not_two() -> None:
    """A quoted line ending in "!" is where the first implementation broke.

    Splitting into sentences before locating quoted spans cuts through the
    utterance, leaving two fragments with one unbalanced quote each and matching
    neither. It halved a book measuring 0.818 to 0.273.
    """
    assert spoken_spans('"Run now!" she called.') == ['"Run now!" she called.']


@pytest.mark.unit
def test_the_two_shares_use_different_units_and_do_not_agree() -> None:
    """`dialogue_share` counts bodies, `sentence_share` counts sentences.

    Both units are live in this repository. The check is that they are not
    silently interchangeable, because a caller reading 0.29 as a sentence rate
    is reading a different measure than the one it produced.
    """
    bodies = [_UNQUOTED, "The gate stood open. Nobody was waiting."]
    assert dialogue_share(bodies) == 0.5
    # 3 of 5 sentences, because "Right here!" and "he whispered." are two
    # sentences of one utterance. The utterance count is 2 (`spoken_spans`);
    # the two measures answer different questions and this pins the gap.
    assert sentence_share(" ".join(bodies)) == pytest.approx(0.6)
    assert len(spoken_spans(" ".join(bodies))) == 2

    # One line in a long narrated body separates the units furthest.
    long_body = _UNQUOTED.split(".", maxsplit=1)[0] + ". " + "The wind rose. " * 9
    assert dialogue_share([long_body]) == 1.0
    share = sentence_share(long_body)
    assert share is not None
    assert share == pytest.approx(0.1)


@pytest.mark.unit
def test_sentence_share_of_textless_input_is_none_not_zero() -> None:
    """Nothing-to-measure and measured-zero are different answers.

    The callers this replaces already used ``None`` for the former, and the
    conflation is what `UW-C231` is open about elsewhere in the gate.
    """
    assert sentence_share("   ") is None
    assert sentence_share("The gate stood open.") == 0.0


@pytest.mark.unit
def test_strip_tagged_drops_the_tag_clause_with_its_utterance() -> None:
    """The tag is narration, and removing it is the deliberate, safe direction.

    A caller stripping dialogue is exempting it from a false-positive-prone
    detector, so over-removal costs denominator and under-removal costs a false
    finding. Leaving "he whispered." behind also hands a tense detector a vote
    per spoken line, which is the defect this fixed in `check_prose_craft.py`.
    """
    assert strip_tagged(f"{_UNQUOTED} The gate stood open.") == "The gate stood open."


@pytest.mark.unit
def test_strip_dialogue_removes_quoted_and_tagged_together() -> None:
    assert (
        strip_dialogue('The gate stood open. "Run now!" she called.')
        == "The gate stood open."
    )


@pytest.mark.unit
def test_flatten_keeps_the_events_a_spoken_line_carries() -> None:
    """Seeding `dialogue_flat` must not also shorten the book.

    Deleting the lines would confound the criterion under test with every
    length-sensitive criterion beside it, which is the confound W7's within-book
    pairing exists to avoid.
    """
    flat = flatten(_UNQUOTED)
    assert not has_dialogue(flat)
    assert "Let's try this one" in flat
    assert "Right here" in flat
