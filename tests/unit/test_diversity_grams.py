"""Unit tests for cross-fill n-gram overlap (``diversity/grams.py``).

The module is the single definition of "how much verbatim wording do two
fills share", used by both the request-path advisory in
``moderation/leaf_diversity.py`` and the offline
``scripts/check_sibling_fills.py``. The equality test at the bottom is what
stops the two from drifting.
"""

from __future__ import annotations

import random
import time
from typing import Any

import pytest

from cyo_adventure.diversity import grams as grams_mod
from cyo_adventure.diversity.grams import (
    DEFAULT_MIN_RUN,
    STOPWORDS,
    GramOverlap,
    RunProfile,
    content_grams,
    pairwise_overlap,
    shared_run_profile,
    story_text,
    tokenize,
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
# paragraph is not. Run LENGTH separates them cleanly. Measured 2026-08-23 over
# all 465 pairs of the committed corpus: the 464 non-series pairs run 2 to 8
# words (median 5, one pair at 8) at 0% coverage, while the series pair
# reaches 98 words across 246
# distinct passages of 15+ words, 18.6% of book 2. Coverage is the worse of the
# two sides, not a mean: the same 6,691 covered words are 16.8% of book 1's
# 39,935 and 18.6% of book 2's 35,920, and `shared_run_profile` returns the
# larger share.


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


def test_a_long_shared_run_does_not_cost_quadratic_time() -> None:
    """The run search must stay linear per probe, because it runs under a lock.

    ``validator/series.py`` calls this once per pair of books from inside
    ``publishing/service.py::approve``, which holds the storybook row under
    ``SELECT ... FOR UPDATE``. The original implementation materialized every
    ``k``-gram as a tuple, costing O(len * k) per probe; two 16,000-word books
    sharing a half-length passage took 14.7s, all of it inside the lock. The
    rolling-hash version measures ~0.16s for the same input.

    The bound is deliberately loose (a 30x margin over the measured figure, and
    still ~100x under the old implementation) so this is a regression guard
    against reintroducing the quadratic term, not a tight performance
    assertion that would flake on a loaded CI runner.
    """
    words = [f"w{i % 3000}" for i in range(8000)]
    shared = words[:8000]
    left = [f"l{i}" for i in range(8000)] + shared
    right = [f"r{i}" for i in range(8000)] + shared

    start = time.perf_counter()
    longest = grams_mod._longest_shared_run(left, right)
    elapsed = time.perf_counter() - start

    assert longest == 8000
    assert elapsed < 5.0


def test_the_rolling_hash_agrees_with_materialized_windows() -> None:
    """The fast path must return exactly what the naive definition returns.

    Small alphabets are the adversarial case: they force both hash collisions
    and many equal windows at once, which is where a hash-based search can
    diverge from the definition it is meant to implement.
    """

    def naive(left: list[str], right: list[str]) -> int:
        best = 0
        limit = min(len(left), len(right))
        for k in range(1, limit + 1):
            windows = {tuple(left[i : i + k]) for i in range(len(left) - k + 1)}
            if any(
                tuple(right[j : j + k]) in windows for j in range(len(right) - k + 1)
            ):
                best = k
        return best

    rng = random.Random(7)
    for _ in range(300):
        alphabet = [f"w{i}" for i in range(rng.choice([1, 2, 3, 8]))]
        left = [rng.choice(alphabet) for _ in range(rng.randint(0, 30))]
        right = [rng.choice(alphabet) for _ in range(rng.randint(0, 30))]
        assert grams_mod._longest_shared_run(left, right) == naive(left, right), (
            left,
            right,
        )


def test_coverage_counts_a_run_at_the_minimum_but_not_one_below_it() -> None:
    """``DEFAULT_MIN_RUN`` is inclusive, and one word short of it counts zero.

    The threshold is the seam between "a refrain, which is legitimate" and "a
    reused passage". Nothing else pins whether it is ``>=`` or ``>``, so an
    off-by-one here would silently move which books SR-10 blocks.
    """
    at_limit = _words("shared", DEFAULT_MIN_RUN)
    below = _words("shared", DEFAULT_MIN_RUN - 1)

    exact = shared_run_profile(
        f"{at_limit} {_words('left', 200)}", f"{at_limit} {_words('right', 200)}"
    )
    assert exact.longest == DEFAULT_MIN_RUN
    assert exact.covered_words == DEFAULT_MIN_RUN

    short = shared_run_profile(
        f"{below} {_words('left', 200)}", f"{below} {_words('right', 200)}"
    )
    assert short.longest == DEFAULT_MIN_RUN - 1
    assert short.covered_words == 0
    assert short.coverage == 0.0


def test_shared_run_profile_handles_one_empty_side() -> None:
    """An empty book against a real one is zero, not a division error."""
    assert shared_run_profile("", _words("a", 50)).longest == 0
    assert shared_run_profile(_words("a", 50), "").coverage == 0.0


def test_a_story_shorter_than_the_gram_width_yields_no_grams() -> None:
    """A two-word fill produces no 4-grams rather than a malformed window."""
    assert content_grams("the lantern", 4) == frozenset()
    assert (
        pairwise_overlap(
            _story(["the lantern"]),
            _story(["the lantern"]),
            include_choice_labels=False,
        ).shared
        == 0
    )


def test_tokenize_drops_characters_outside_the_ascii_word_class() -> None:
    """Accented and hyphenated words are split, not preserved.

    ``_WORD_RE`` is ``[a-z']+`` over lowercased text, so "Renee" with an acute
    accent splits at the accent and a hyphenated word becomes two tokens. This
    is a real property of a children's-story corpus, where character names
    carry accents, so it is pinned here rather than left to be discovered.
    """
    assert tokenize("Ren\u00e9e ran") == ["ren", "e", "ran"]
    assert tokenize("half-lit lantern") == ["half", "lit", "lantern"]
    assert tokenize("don't stop") == ["don't", "stop"]


def test_story_text_degrades_malformed_shapes_to_no_text() -> None:
    """Every malformed blob shape contributes no text instead of raising.

    The `#ASSUME` on ``story_text`` enumerates these shapes by name. The test
    it used to cite passed a well-formed ``{"nodes": []}`` and asserted a
    division-by-zero guard, so none of the shapes was actually covered and a
    regression in the ``isinstance`` guards would have kept that test green.
    """
    no_text: list[Any] = [
        {},
        {"nodes": None},
        {"nodes": "garbage"},
        {"nodes": 17},
        {"nodes": [1, 2, 3]},
        {"nodes": ["not a dict"]},
        {"nodes": [{"id": "n0"}]},
    ]
    for blob in no_text:
        assert story_text(blob, include_choice_labels=False).strip() == "", blob
        assert story_text(blob, include_choice_labels=True).strip() == "", blob

    # A null body is the one shape that is not silently empty: `str(None)`
    # contributes the literal token. Harmless (it is one stopword-free token
    # shared by any two such books, far below every bound) but pinned here so
    # the behaviour is a decision rather than a surprise.
    null_body: Any = {"nodes": [{"id": "n0", "body": None}]}
    assert story_text(null_body, include_choice_labels=False).strip() == "None"

    # And the pair path built on it stays defined rather than dividing by zero.
    overlap = pairwise_overlap(
        {"nodes": "garbage"}, {"nodes": None}, include_choice_labels=False
    )
    assert overlap.shared == 0
    assert overlap.per_1000 == 0.0


@pytest.mark.unit
def test_story_text_strips_sentinels_to_their_generic_word() -> None:
    """A sentinel contributes its generic word only, never its slot id.

    An ADR-023 sentinel is ``{~SLOTID:Generic~}`` and survives verbatim through
    fill, moderation, approval and storage by design, so a published body can
    carry them once that work is flag-ON. The tokenizer lowercases and splits
    on ``[a-z']+``, so an unstripped ``{~HERO:Explorer~}`` yields BOTH ``hero``
    and ``explorer``, and the slot-id half is identical in every book that
    binds that slot. Two books of one chain would then share tokens they do not
    share as prose.

    The bias is one-directional: each sentinel inside a shared run adds exactly
    one spurious shared token, which can only lengthen a run, never shorten it.
    So SR-10 in ``validator/series.py`` errs toward a FALSE block, blocking a
    legitimate chain rather than admitting a copied one. The second half of
    this test pins that consequence, not just the string rewrite, so deleting
    the strip fails here and not only on a cosmetic assertion.
    """
    one = {"nodes": [{"body": "the {~HERO:Explorer~} walked north"}]}
    assert story_text(one, include_choice_labels=False) == "the Explorer walked north"
    assert "hero" not in tokenize(story_text(one, include_choice_labels=False))

    # Choice labels take the same path, so they cannot reintroduce slot ids.
    labelled: Any = {
        "nodes": [{"body": "b", "choices": [{"label": "follow {~FOE:Shadow~}"}]}]
    }
    assert "{~FOE:Shadow~}" not in story_text(labelled, include_choice_labels=True)
    assert "foe" not in tokenize(story_text(labelled, include_choice_labels=True))

    # The consequence the strip exists for. Twelve shared real words sits under
    # DEFAULT_MIN_RUN; two sentinels inside that run would push the unstripped
    # measurement over it, which is a false SR-10 ERROR on a chain that shares
    # no more prose than the bound already permits.
    shared = [
        "lantern",
        "swung",
        "harbor",
        "gulls",
        "circled",
        "grey",
        "stone",
        "tower",
        "dusk",
        "rope",
        "salt",
        "gull",
    ]
    n_sentinels = 2
    with_slots = list(shared)
    for offset, index in enumerate((4, 8)):
        with_slots.insert(index + offset, "{~HERO:Explorer~}")
    run = " ".join(with_slots)
    left = {"nodes": [{"body": f"alpha beta gamma {run} delta epsilon"}]}
    right = {"nodes": [{"body": f"eta theta iota {run} kappa mu"}]}

    stripped = shared_run_profile(
        story_text(left, include_choice_labels=False),
        story_text(right, include_choice_labels=False),
    )
    unstripped = shared_run_profile(
        str(left["nodes"][0]["body"]), str(right["nodes"][0]["body"])
    )

    assert stripped.longest == len(shared) + n_sentinels
    assert unstripped.longest == stripped.longest + n_sentinels
    assert stripped.longest <= DEFAULT_MIN_RUN < unstripped.longest
