"""Unit tests for cross-fill n-gram overlap (``diversity/grams.py``).

The module is the single definition of "how much verbatim wording do two
fills share", used by both the request-path advisory in
``moderation/leaf_diversity.py`` and the offline
``scripts/check_sibling_fills.py``. The equality test at the bottom is what
stops the two from drifting.
"""

from __future__ import annotations

from typing import Any

import pytest

from cyo_adventure.diversity import grams as grams_mod
from cyo_adventure.diversity.grams import (
    STOPWORDS,
    GramOverlap,
    RunProfile,
    content_grams,
    pairwise_overlap,
    shared_run_profile,
    story_text,
)
from scripts import check_sibling_fills
from scripts.check_sibling_fills import _STOPWORDS as _SCRIPT_STOPWORDS
from scripts.check_sibling_fills import _grams, _leaf_text

pytestmark = pytest.mark.unit


def _story(bodies: list[str], labels: list[str] | None = None) -> dict[str, Any]:
    """Build a minimal story whose node bodies and choice labels are given."""
    labels = labels or []
    return {
        "id": "s_x",
        "nodes": [
            {
                "id": f"n{i}",
                "body": body,
                "choices": [
                    {"id": f"c{i}", "label": label, "target": "n0"} for label in labels
                ],
            }
            for i, body in enumerate(bodies)
        ],
    }


def test_content_grams_drops_all_stopword_grams() -> None:
    """A 4-gram made entirely of function words carries no recognition risk."""
    assert content_grams("the of and to") == frozenset()
    assert content_grams("the lantern and to") != frozenset()


def test_content_grams_are_word_position_windows() -> None:
    """Five content words yield exactly two overlapping 4-grams."""
    grams = content_grams("lantern kestrel basin fossil grotto")
    assert grams == {
        ("lantern", "kestrel", "basin", "fossil"),
        ("kestrel", "basin", "fossil", "grotto"),
    }


def test_story_text_can_exclude_choice_labels() -> None:
    """Choice labels are separable from body prose.

    They must be, because a skeleton supplies its labels to every sibling
    fill unchanged, so including them measures the skeleton rather than the
    fill.
    """
    story = _story(["a lantern basin"], labels=["Take the brass compass"])
    assert "brass compass" in story_text(story, include_choice_labels=True)
    assert "brass compass" not in story_text(story, include_choice_labels=False)
    assert "lantern basin" in story_text(story, include_choice_labels=False)


def test_identical_labels_do_not_register_as_body_overlap() -> None:
    """The regression this module exists for.

    Two fills of one skeleton carry byte-identical choice labels by
    construction. Measured with labels, they share grams they cannot avoid
    sharing; measured on bodies alone, two genuinely re-authored fills share
    nothing.
    """
    labels = ["Squeeze past the fallen pillar", "Follow the humming corridor"]
    a = _story(["Priya checked the hydroponics pool for drifting seedlings"], labels)
    b = _story(["Theo brushed grit from the fossil ridge with a stiff brush"], labels)

    with_labels = pairwise_overlap(a, b, include_choice_labels=True)
    bodies_only = pairwise_overlap(a, b, include_choice_labels=False)

    assert with_labels.shared > 0
    assert bodies_only.shared == 0


def test_pairwise_overlap_reports_a_length_normalized_rate() -> None:
    """The rate is shared grams per 1000 mean words, not a raw count."""
    shared_run = "the lantern swung over the black water and steadied"
    a = _story([shared_run + " " + " ".join(f"alpha{i}" for i in range(50))])
    b = _story([shared_run + " " + " ".join(f"beta{i}" for i in range(50))])
    overlap = pairwise_overlap(a, b, include_choice_labels=False)
    assert isinstance(overlap, GramOverlap)
    assert overlap.shared > 0
    assert overlap.per_1000 == pytest.approx(
        overlap.shared / overlap.mean_words * 1000.0
    )


def test_pairwise_overlap_of_unrelated_prose_is_zero() -> None:
    """Two fills with no shared wording score zero, not a small positive."""
    a = _story(["Priya counted the drifting seedlings one by one"])
    b = _story(["Theo brushed grit from the ancient fossil ridge"])
    assert pairwise_overlap(a, b, include_choice_labels=False).shared == 0


def test_pairwise_overlap_survives_an_empty_story() -> None:
    """An empty fill divides by a floor, not by zero."""
    overlap = pairwise_overlap(_story([]), _story([]), include_choice_labels=False)
    assert overlap.shared == 0
    assert overlap.per_1000 == 0.0


def test_pairwise_overlap_matches_the_offline_script_when_labels_are_included() -> None:
    """The shared definition really is shared.

    ``scripts/check_sibling_fills.py`` measured body-plus-label text before
    this module existed. Including labels must reproduce its number exactly,
    or the offline calibration figures stop describing the code that runs.
    """
    labels = ["Squeeze past the fallen pillar", "Follow the humming corridor"]
    a = _story(["Priya checked the hydroponics pool for drifting seedlings"], labels)
    b = _story(["Theo checked the hydroponics pool for drifting seedlings"], labels)

    expected = len(_grams(_leaf_text(a)) & _grams(_leaf_text(b)))
    assert pairwise_overlap(a, b, include_choice_labels=True).shared == expected


def test_the_offline_script_holds_no_second_copy_of_the_stop_list() -> None:
    """Drift here silently invalidates the offline calibration figures.

    The 2.8 / 12.6 / 25 per-1000 arm scores were measured with the script's
    tokenizer and stop list. Equality between two copies would be the weaker
    guarantee, since a copy can be edited and the equality test updated in the
    same commit; identity is checked instead, so the only way to change the
    stop list is to change the one definition both callers read.
    """
    assert _SCRIPT_STOPWORDS is STOPWORDS
    assert check_sibling_fills.tokenize is grams_mod.tokenize
    assert check_sibling_fills.content_grams is content_grams


# ---------------------------------------------------------------------------
# Shared contiguous runs (SR-10): length, not volume
# ---------------------------------------------------------------------------
#
# The per-1000 rate above is a VOLUME measure and cannot separate one copied
# passage from many deliberate short echoes, which is precisely the question a
# series raises: a refrain repeated on purpose is legitimate, a reused
# paragraph is not. Run LENGTH separates them cleanly. Measured 2026-08-23 on
# the committed corpus: every unrelated pair's longest shared run is 4 to 8
# words, while the brass-lantern series pair reaches 98 words across 246
# distinct passages of 15+ words, 16.8% of the book.


def _words(prefix: str, count: int) -> str:
    """Return ``count`` distinct words, so nothing collides by accident."""
    return " ".join(f"{prefix}{i}" for i in range(count))


def test_shared_run_profile_measures_the_longest_contiguous_run() -> None:
    """The headline number is the length of the longest shared passage."""
    run = _words("shared", 20)
    profile = shared_run_profile(
        f"{_words('a', 40)} {run} {_words('b', 40)}",
        f"{_words('c', 40)} {run} {_words('d', 40)}",
    )
    assert isinstance(profile, RunProfile)
    assert profile.longest == 20


def test_a_short_refrain_repeated_many_times_costs_no_coverage() -> None:
    """The rule this exists to express: a phrase may repeat, a passage may not.

    A six-word refrain three times over is deliberate craft. It must register
    its true length and contribute nothing at all to coverage, because
    coverage counts only words inside runs at or above ``min_run``.
    """
    refrain = "the brass lantern never tells lies"
    left = f"{_words('a', 60)} {refrain} {_words('b', 60)} {refrain}"
    right = f"{_words('c', 60)} {refrain} {_words('d', 60)} {refrain}"
    profile = shared_run_profile(left, right)
    assert profile.longest == 6
    assert profile.coverage == 0.0


def test_coverage_counts_only_words_inside_long_runs() -> None:
    """A copied passage is counted; the noise around it is not."""
    passage = _words("shared", 30)
    profile = shared_run_profile(
        f"{passage} {_words('a', 70)}",
        f"{passage} {_words('b', 70)}",
    )
    assert profile.longest == 30
    assert profile.coverage == pytest.approx(0.3)


def test_coverage_is_measured_against_the_more_affected_book() -> None:
    """A short book copied wholesale into a long one is not diluted.

    Dividing by a mean, or by the longer text, would let a novella absorb a
    picture book's entire text and still report a small number. The measure is
    the worse of the two sides.
    """
    small = _words("shared", 40)
    profile = shared_run_profile(small, f"{small} {_words('big', 4000)}")
    assert profile.coverage == pytest.approx(1.0)


def test_shared_run_profile_of_unrelated_prose_is_clean() -> None:
    """Two texts with no long shared passage report zero, not a small number."""
    profile = shared_run_profile(_words("a", 200), _words("b", 200))
    assert profile.longest == 0
    assert profile.coverage == 0.0
    assert profile.covered_words == 0


def test_shared_run_profile_survives_empty_text() -> None:
    """An empty book divides by a floor, not by zero."""
    profile = shared_run_profile("", "")
    assert profile.longest == 0
    assert profile.coverage == 0.0
