"""Unit tests for the W2 per-path re-unit.

Two guards carry this module, and both exist because the original W2 run nearly
returned the wrong verdict without either of them: a disagreement rule that
counts the dilution direction recommends keeping a measure that is strictly
weaker than its parent, and a rate threshold re-unitted onto a smaller
denominator stops binding without erroring.
"""

from __future__ import annotations

import pytest

from scripts.measure_per_path import (
    _DISAGREEMENT_BAR,  # pyright: ignore[reportPrivateUsage]
    _TOLD_BAND_PER_1000,  # pyright: ignore[reportPrivateUsage]
    MeasureOutcome,
    told_floor,
)


def test_told_floor_is_the_rate_a_single_hit_produces() -> None:
    """The floor is what makes an inert band visible rather than merely wrong."""
    assert told_floor(1_000) == pytest.approx(1.0)
    assert told_floor(600) == pytest.approx(1.667, abs=0.001)


def test_the_calibrated_band_cannot_bind_on_a_typical_covering_path() -> None:
    """The AL-342 finding, stated as an arithmetic fact rather than a sample.

    The band is 0.5 per 1000 narration words. A passage needs more than 2,000
    words for a single hit to score under it, and covering paths run in the
    hundreds. Below that the measure has stopped being a rate and become
    presence/absence, whatever its output looks like.
    """
    assert told_floor(600) > _TOLD_BAND_PER_1000
    assert told_floor(1_856) > _TOLD_BAND_PER_1000
    # The break-even point, stated so a change to the band moves this test.
    assert told_floor(int(1_000 / _TOLD_BAND_PER_1000)) == pytest.approx(
        _TOLD_BAND_PER_1000
    )


def test_an_inert_band_reports_inert_rather_than_a_keep() -> None:
    """A measure that clears the bar for the wrong reason must not read as a keep.

    Told-emotion scored 13.2% on the original run, apparently clearing the 10%
    bar, and every one of those breaches was the smallest nonzero rate its path
    length admitted. Reporting that as a keep would have promoted a
    presence/absence check wearing the language of a rate.
    """
    outcome = MeasureOutcome(
        "told_emotion", books=20, book_in_path_out=5, band_floor_breaches=20
    )

    # It clears the bar, and that is exactly why the guard has to outrank it.
    assert outcome.disagreement >= _DISAGREEMENT_BAR
    assert outcome.verdict.startswith("INERT")


def test_a_monotone_measure_is_refused_rather_than_scored() -> None:
    """A per-path check that can only ever be laxer must not be run at all.

    A path's endings are a subset of the book's, so its moral-tag count cannot
    exceed the book's. Scoring it produced a literal 17% on the original run,
    entirely in the dilution direction, and the rule as written would have kept
    it (AL-343).
    """
    outcome = MeasureOutcome("moral_tags", refused="monotone under path-subsetting")

    assert outcome.verdict.startswith("REFUSED")


def test_only_the_defect_exposing_direction_counts_toward_the_bar() -> None:
    """Dilution is not sensitivity, however large it gets."""
    diluting = MeasureOutcome(
        "moral_tags", books=10, book_in_path_out=0, book_out_path_in=9
    )

    assert diluting.disagreement == 0.0
    assert diluting.verdict.startswith("DROP")


def test_a_measure_that_clears_the_bar_honestly_reports_keep() -> None:
    """The rule has to be able to return keep, or it is not a rule."""
    outcome = MeasureOutcome("reading_level", books=53, book_in_path_out=7)

    assert outcome.verdict.startswith("KEEP")
