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

from typing import Any

from scripts.evaluate_books import (
    _beat_terms,  # pyright: ignore[reportPrivateUsage]
    _directives,  # pyright: ignore[reportPrivateUsage]
    _fidelity,  # pyright: ignore[reportPrivateUsage]
    _mattr,  # pyright: ignore[reportPrivateUsage]
    _words,  # pyright: ignore[reportPrivateUsage]
    evaluate_book,
    summarize_leg,
)

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
