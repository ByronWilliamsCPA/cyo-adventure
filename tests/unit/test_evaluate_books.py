"""Unit tests for the deterministic two-axis book evaluator.

The evaluator's job is to keep two things apart that a single Flesch-Kincaid
number silently merges: whether a leg *did what it was told* and whether its
prose *reads well*. Most of what follows pins down the first, because that is
the half a bug can quietly invert. A book that was never written must not be
able to score well by having its failures excluded from an average, and a node
that still holds a FILL directive must never be counted as prose.

No test here makes a network call.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

import pytest

from scripts.evaluate_books import (
    BookScore,
    _beat_terms,  # pyright: ignore[reportPrivateUsage]
    _directives,  # pyright: ignore[reportPrivateUsage]
    _fidelity,  # pyright: ignore[reportPrivateUsage]
    _mattr,  # pyright: ignore[reportPrivateUsage]
    _words,  # pyright: ignore[reportPrivateUsage]
    evaluate_book,
    summarize_leg,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_BAND: dict[str, Any] = {
    "scheme": "flesch_kincaid",
    "target": 2.5,
    "tolerance": 1.5,
}

# Twenty-plus words, so score_body clears its minimum and the book is scorable.
_PROSE = (
    "The small otter counted every lantern on the wide river bank and smiled "
    "at the warm light before she carried her basket home again tonight."
)


def _skeleton(*directives: tuple[str, int, str]) -> dict[str, Any]:
    """Build a skeleton whose nodes carry FILL directives.

    Args:
        directives: ``(node_id, words, beats)`` per node.

    Returns:
        A skeleton document.
    """
    return {
        "id": "s_test",
        "metadata": {"age_band": "5-8", "reading_level": _BAND},
        "nodes": [
            {
                "id": node_id,
                "body": f"<<FILL role=choice words={words} beats='{beats}'>>",
                "is_ending": False,
                "choices": [],
            }
            for node_id, words, beats in directives
        ],
    }


def _filled(*bodies: tuple[str, str]) -> dict[str, Any]:
    """Build a filled book from ``(node_id, body)`` pairs.

    Args:
        bodies: The node ids and their bodies.

    Returns:
        A filled story document.
    """
    return {
        "id": "s_test",
        "metadata": {"age_band": "5-8", "reading_level": _BAND},
        "start_node": bodies[0][0],
        "nodes": [
            {"id": node_id, "body": body, "is_ending": True, "choices": []}
            for node_id, body in bodies
        ],
    }


def test_beat_terms_drops_binding_slots_and_stopwords() -> None:
    """Only content words survive, so recall measures coverage not boilerplate.

    ``{HERO}`` is bound to a name chosen per brief, so its literal text can never
    appear in the prose; counting it would depress every book equally. Stopwords
    appear in everything and would inflate every book equally. Either one turns
    beat recall into a constant.
    """
    terms = _beat_terms("{HERO} counts the lanterns and then decides where to go")

    assert "hero" not in terms
    assert "the" not in terms
    assert {"count", "lantern", "decid"} <= terms


def test_beat_recall_credits_an_inflected_match() -> None:
    """'counted' in the prose answers a beat asking for 'counts'."""
    skeleton = _skeleton(("n1", 10, "counts the lanterns"))
    _, _, recall = _fidelity(
        [("n1", "She counted the lantern slowly.")], _directives(skeleton)
    )

    assert recall == 1.0


def test_fidelity_ignores_a_node_that_was_never_filled() -> None:
    """An unfilled node is a delivery failure, not a zero-length answer.

    Counting its FILL directive as a body would score the directive's own text
    as prose and report a word ratio for writing that does not exist.
    """
    skeleton = _skeleton(("n1", 10, "counts lanterns"), ("n2", 10, "walks home"))
    bodies = [
        ("n1", "She counted the lanterns one by one and then again."),
        ("n2", "<<FILL role=choice words=10 beats='walks home'>>"),
    ]

    ratio, on_budget, _ = _fidelity(bodies, _directives(skeleton))

    assert ratio is not None
    assert on_budget == 1.0, "the unfilled node must not enter the budget fraction"


def test_word_ratio_reports_overwriting_above_one() -> None:
    """A leg that writes twice its brief scores 2.0, not 0.5."""
    skeleton = _skeleton(("n1", 5, "x"))
    ratio, _, _ = _fidelity(
        [("n1", "one two three four five six seven eight nine ten")],
        _directives(skeleton),
    )

    assert ratio == 2.0


def test_mattr_does_not_punish_a_longer_text_for_its_length() -> None:
    """Vocabulary variety must be comparable across books of different sizes.

    Raw type-token ratio falls mechanically as a text grows, so ranking a
    2,200-word book against a 4,300-word one on TTR would measure length. Two
    texts built from the same repeating vocabulary should land close on MATTR
    however long they are.
    """
    unit = _words("alpha bravo charlie delta echo foxtrot golf hotel india juliet")
    short = unit * 20
    long = unit * 60

    short_mattr = _mattr(short)
    long_mattr = _mattr(long)
    raw_short = len(set(short)) / len(short)
    raw_long = len(set(long)) / len(long)

    assert short_mattr is not None
    assert long_mattr is not None
    assert abs(short_mattr - long_mattr) < 0.01
    assert raw_short > raw_long * 2, "raw TTR should show the length bias MATTR avoids"


def test_evaluate_book_reports_partial_delivery_as_incomplete() -> None:
    """Three unfilled nodes out of four is 0.25 complete, not a passing book.

    This is the Sonnet 5 failure from the 2026-08-12 run: the pipeline recorded
    status=passed while three quarters of the book was still authoring markers.
    """
    skeleton = _skeleton(*[(f"n{i}", 25, "counts lanterns") for i in range(4)])
    doc = _filled(
        ("n0", _PROSE),
        ("n1", "<<FILL role=choice words=25 beats='counts lanterns'>>"),
        ("n2", "<<FILL role=choice words=25 beats='counts lanterns'>>"),
        ("n3", "<<FILL role=choice words=25 beats='counts lanterns'>>"),
    )

    score = evaluate_book(doc, skeleton, leg="v", family="f", brief_index=0)

    assert score.fill_completeness == 0.25
    assert score.filled_nodes == 1
    assert score.total_words == len(_words(_PROSE))


def test_evaluate_book_flags_an_unreplaced_binding_slot() -> None:
    """A literal {HERO} reaching a child is a hard failure, so it is counted."""
    skeleton = _skeleton(("n1", 25, "x"))
    doc = _filled(("n1", f"{_PROSE} Then {{HERO}} went home with {{SPECIES}}."))

    score = evaluate_book(doc, skeleton, leg="v", family="f", brief_index=0)

    assert score.placeholder_leaks == 2


def test_summarize_leg_keeps_a_failed_book_in_the_denominator() -> None:
    """A leg cannot raise its average by producing nothing for a book.

    Prose means are taken over books that produced prose, so the guard that
    matters is that ``books`` and ``complete_books`` still expose the failure.
    A summary reporting four books and one complete one cannot be mistaken for
    a clean leg however good the surviving book's numbers are.
    """
    skeleton = _skeleton(("n1", 25, "x"))
    good = evaluate_book(
        _filled(("n1", _PROSE)), skeleton, leg="v", family="f", brief_index=0
    )
    empty_doc = _filled(("n1", "<<FILL role=choice words=25 beats='x'>>"))
    bad = [
        evaluate_book(empty_doc, skeleton, leg="v", family="f", brief_index=i)
        for i in (1, 2, 3)
    ]

    summary = summarize_leg([good, *bad])

    assert summary.books == 4
    assert summary.complete_books == 1
    assert summary.means["fill_completeness"] == 0.25


# ---------------------------------------------------------------------------
# Drop-worst: a single book must not become a property of the variable (AL-349)
# ---------------------------------------------------------------------------


def _leg_scores(in_band_values: Sequence[float]) -> list[BookScore]:
    """Build one leg's book scores with the given in-band figures.

    Every other field is held constant, so a change in the summary is
    attributable to the values under test rather than to the fixture.

    Args:
        in_band_values: One in-band share per book.

    Returns:
        The book scores.
    """
    return [
        BookScore(
            leg="alpha",
            family="alpha",
            brief_index=index,
            nodes=10,
            filled_nodes=10,
            fill_completeness=1.0,
            placeholder_leaks=0,
            l1_errors=0,
            l1_warnings=0,
            grade=3.0,
            in_band=value,
            grade_spread=0.5,
            word_ratio_median=1.0,
            word_on_budget=1.0,
            beat_recall=0.9,
            mattr=0.7,
            mean_sentence_words=9.0,
            sentence_spread=3.0,
            dialogue_share=0.0,
            total_words=800,
        )
        for index, value in enumerate(in_band_values)
    ]


def test_drop_worst_removes_the_single_book_that_carried_a_leg() -> None:
    """Reproduces run-6's fp4 headline, which was one book rather than an effect.

    `deepseek-v4-pro-fp4` read 0.70 in band against fp8's 0.92 and was written
    up as a 22-point quantisation penalty. Dropping each leg's worst book put it
    at 0.89 against unquantised 0.88, so the effect was not there (AL-349).
    """
    summary = summarize_leg(_leg_scores([0.12, 0.92, 0.86, 0.89]))

    assert summary.means["in_band"] == pytest.approx(0.6975, abs=0.001)
    assert summary.drop_worst["in_band"] == pytest.approx(0.89, abs=0.001)


def test_drop_worst_removes_the_top_of_a_lower_is_better_field() -> None:
    """Orientation is per field, and getting it backwards flatters the leg.

    ``grade_spread`` is bad when large, so its worst book is the widest one.
    Dropping the smallest instead would raise the reported spread and read as a
    robustness check while being the opposite of one.
    """
    scores = _leg_scores([1.0, 1.0, 1.0, 1.0])
    scores[0] = dataclasses.replace(scores[0], grade_spread=4.0)

    summary = summarize_leg(scores)

    # Means over 4.0, 0.5, 0.5, 0.5; dropping the 4.0 leaves 0.5.
    assert summary.means["grade_spread"] == pytest.approx(1.375, abs=0.001)
    assert summary.drop_worst["grade_spread"] == pytest.approx(0.5, abs=0.001)


def test_drop_worst_is_withheld_when_a_leg_has_too_few_books() -> None:
    """Dropping one of two leaves a single observation, not a robustness check."""
    assert summarize_leg(_leg_scores([0.9, 0.3])).drop_worst == {}


def test_drop_worst_barely_moves_a_leg_with_no_outlier() -> None:
    """The check must stay quiet when nothing is being carried by one book."""
    summary = summarize_leg(_leg_scores([0.88, 0.90, 0.89, 0.91]))

    base = summary.means["in_band"]
    robust = summary.drop_worst["in_band"]
    assert base is not None
    assert robust is not None
    assert abs(robust - base) < 0.02
