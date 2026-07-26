"""The similarity signature and containment measure (A1, A2, A3, A5).

Three defects are pinned here, each of which made the shipped diversity signal
inert in a different way:

1. **A1, the vocabulary.** ``theme_signature`` passed an unrecognised curated
   theme through verbatim, so the stored side accumulated strings the request
   side could never produce and the comparison was asymmetric by construction.
2. **A2, the measure.** Symmetric Jaccard divides by the union, so a story that
   fully delivers a request lost points for also being about other things.
3. **A3, saturation.** With three-tree cells, saturation pins at 1.0 and the
   escalation ladder parks permanently, which is the same inertness wearing a
   different hat.

The echo vocabulary must not move as a side effect of any of it.

A note on why this file matters more than the pass count suggests. Swapping the
core similarity measure from Jaccard to containment broke **no** pre-existing
test: ``test_diversity_query.py`` builds signatures where the two measures agree,
so it never pinned the measure at all. Reverting A2 fails exactly one test, and
it is in this file. So the existing suite's green is not evidence this change is
safe; these tests are.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cyo_adventure.diversity.history import HistoryEntry
from cyo_adventure.diversity.normalize import (
    _THEME_TAG_MAP,
    containment,
    jaccard_similarity,
    similarity_signature,
    theme_signature,
)
from cyo_adventure.diversity.query import DifferentiationLevel, score_history
from cyo_adventure.diversity.similarity_vocab import (
    CANONICAL_TAGS,
    SIMILARITY_TAG_MAP,
)

# The 12 values the echo map produced when this split was made. Frozen here so a
# future edit to the echo map fails this test loudly instead of silently changing
# what a child is shown.
_ECHO_VALUES_AT_SPLIT = frozenset(
    {
        "castle",
        "cave",
        "dinosaur",
        "dragon",
        "fire",
        "forest",
        "knight",
        "magic",
        "ocean",
        "pirate",
        "robot",
        "space",
    }
)


# ---------------------------------------------------------------------------
# A1: two vocabularies, and the echo one stays put
# ---------------------------------------------------------------------------


def test_echo_vocabulary_is_unchanged_by_the_similarity_split() -> None:
    """The echo map's value set must not move.

    Its values are read back to a child by
    ``generation/worker.py::_degraded_set_aside_decisions``, so growing it is a
    content-safety change. A1 exists specifically so similarity work does not
    have to touch it.
    """
    assert frozenset(_THEME_TAG_MAP.values()) == _ECHO_VALUES_AT_SPLIT


def test_the_two_vocabularies_are_separate_objects() -> None:
    """A shared map would recreate the coupling A1 removed."""
    assert SIMILARITY_TAG_MAP is not _THEME_TAG_MAP
    # The similarity map is strictly richer: it must cover the abstract catalog
    # themes the echo map has no reason to know about.
    assert len(SIMILARITY_TAG_MAP) > len(_THEME_TAG_MAP)


def test_unmapped_curated_theme_is_dropped_not_passed_through() -> None:
    """The A1 defect, stated as a test.

    ``theme_signature`` emits the raw string for an unrecognised theme, which is
    what put 132 unproducible strings on the stored side.
    """
    unknown = "some theme nobody mapped"
    assert unknown in theme_signature(None, [unknown]), "documents the old behaviour"
    assert similarity_signature(None, [unknown]) == frozenset()


def test_every_similarity_tag_is_in_the_canonical_space() -> None:
    """A typo in the map would otherwise create a tag nothing can ever match."""
    assert set(SIMILARITY_TAG_MAP.values()) <= CANONICAL_TAGS


def test_both_sides_land_in_one_space() -> None:
    """A request premise and a story's curated themes must be comparable.

    The original asymmetry was not only extra tags on one side: the echo map's
    values are concrete subjects while curated themes are abstract, so the two
    sides described different axes and could not intersect at all.
    """
    request = similarity_signature({"premise": "a brave knight in a dark cave"})
    story = similarity_signature(None, ["courage", "the uncanny", "cave"])
    assert request <= CANONICAL_TAGS
    assert story <= CANONICAL_TAGS
    assert request & story, "one shared space means a real intersection is possible"


# ---------------------------------------------------------------------------
# A2: containment, not symmetric Jaccard
# ---------------------------------------------------------------------------


def test_the_exact_asymmetry_case_from_the_plan() -> None:
    """A byte-identical premise scored 0.333 against a 0.35 floor.

    Reproduced rather than asserted: one request tag, two curated themes the
    request side cannot produce, so Jaccard is 1/3 and the match is missed.
    Containment answers the caller's actual question and returns 1.0.
    """
    brief = {"premise": "a story about a dragon"}
    themes = ["courage", "friendship"]
    request = theme_signature(brief)
    story = theme_signature(brief, themes)
    assert jaccard_similarity(request, story) == 1 / 3
    assert jaccard_similarity(request, story) < 0.35, "the shipped floor missed it"

    new_request = similarity_signature(brief)
    new_story = similarity_signature(brief, themes)
    assert containment(new_request, new_story) == 1.0


def test_containment_does_not_penalise_a_richer_story() -> None:
    """Extra story themes must not lower a full match."""
    request = frozenset({"dragon"})
    lean = frozenset({"dragon"})
    rich = frozenset({"dragon", "courage", "family", "loss", "mystery"})
    assert containment(request, lean) == containment(request, rich) == 1.0
    # Jaccard is what punished the rich story.
    assert jaccard_similarity(request, rich) < jaccard_similarity(request, lean)


def test_containment_argument_order_is_request_then_story() -> None:
    """The measure is asymmetric, so argument order is load-bearing."""
    request = frozenset({"dragon"})
    story = frozenset({"dragon", "courage"})
    assert containment(request, story) == 1.0
    assert containment(story, request) == 0.5


def test_containment_of_a_partial_match() -> None:
    """Half the request delivered scores half."""
    assert containment(frozenset({"dragon", "space"}), frozenset({"dragon"})) == 0.5


def test_empty_request_is_not_similar_to_anything() -> None:
    """An empty request asked for nothing, so nothing can be covered.

    Matches ``jaccard_similarity``'s documented WS-0 intent that an empty
    signature never registers as similar, without touching that function.
    """
    assert containment(frozenset(), frozenset({"dragon"})) == 0.0
    assert containment(frozenset(), frozenset()) == 0.0


def test_containment_is_bounded() -> None:
    """A score outside [0, 1] would break every threshold comparison."""
    request = frozenset({"a", "b", "c"})
    for story in (frozenset(), request, frozenset({"a"}), frozenset({"a", "z"})):
        assert 0.0 <= containment(request, story) <= 1.0


# ---------------------------------------------------------------------------
# A3: the saturation ceiling
# ---------------------------------------------------------------------------


def _entry(slug: str, tags: set[str]) -> HistoryEntry:
    """Build a history entry with a given skeleton slug and signature."""
    return HistoryEntry(
        storybook_id=f"s_{slug}",
        version=1,
        skeleton_slug=slug,
        theme_sig=frozenset(tags),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_an_unsaturated_cell_still_recommends_a_different_tree() -> None:
    """The ordinary case: an unused tree exists, so ask for it."""
    context = score_history(
        request_theme_sig=frozenset({"dragon"}),
        history=[_entry("tree_a", {"dragon"})],
        cell_slugs=["tree_a", "tree_b", "tree_c"],
    )
    assert context.recommendation is DifferentiationLevel.TREE
    assert context.cell_theme_saturation < 1.0


def test_a_fully_saturated_three_tree_cell_escalates_past_tree() -> None:
    """A3's case: with three trees all used, TREE is no longer available.

    The ladder must move on rather than keep recommending a tree that does not
    exist, which is what made the escalation signal rank-equivalent to recency.
    """
    context = score_history(
        request_theme_sig=frozenset({"dragon"}),
        history=[
            _entry("tree_a", {"dragon"}),
            _entry("tree_b", {"dragon"}),
            _entry("tree_c", {"dragon"}),
        ],
        cell_slugs=["tree_a", "tree_b", "tree_c"],
    )
    assert context.cell_theme_saturation == 1.0
    assert context.recommendation is not DifferentiationLevel.TREE


def test_saturation_pins_at_one_after_three_reads_in_a_three_tree_cell() -> None:
    """Pins the measurement A3's guard exists because of.

    This is not a defect in itself; it is the fact that makes an unbounded
    escalation signal useless in a 3-tree cell, which 15 of 18 populated cells
    are.
    """
    history = [_entry(f"tree_{i}", {"dragon"}) for i in "abc"]
    for count in range(1, 4):
        context = score_history(
            request_theme_sig=frozenset({"dragon"}),
            history=history[:count],
            cell_slugs=["tree_a", "tree_b", "tree_c"],
        )
        assert context.cell_theme_saturation == count / 3


def test_containment_raises_the_similar_count_a_richer_history_produces() -> None:
    """A2 changes which entries clear the floor, not just their scores.

    A prior story whose curated themes swamp the request used to fall below
    tau_theme and be treated as unrelated, which is precisely how a family could
    be handed the same tree twice.
    """
    rich = _entry("tree_a", {"dragon", "courage", "family", "loss", "mystery"})
    context = score_history(
        request_theme_sig=frozenset({"dragon"}),
        history=[rich],
        cell_slugs=["tree_a", "tree_b", "tree_c"],
    )
    assert context.similar_count_per_slug["tree_a"] == 1
    assert context.used_slugs == frozenset({"tree_a"})
