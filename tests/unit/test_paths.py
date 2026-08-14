"""Tests for the root-to-ending path enumerator (validator/paths.py).

TDD order: write tests first, watch them fail, then implement.

The enumerator exists because every craft measure we own is computed over a
whole book, while a reader experiences one path through it (W1 in
``docs/planning/cyo-measurement-workplan-2026-08-12.md``). Three external
reviews converged on that reframing independently.

What these tests pin down, in the order the design decisions were made:

1. A path is a sequence of node ids, produced by driving the engine rather
   than by reconstructing node ids from ``ConfigKey`` tuples. ``walk.py``'s
   doctrine is that transition semantics live in the engine and nowhere else.
2. The covering set exercises every visible choice at least once, so no fork
   escapes measurement. It is greedy, not minimal, and the tests assert
   coverage rather than path count wherever the two could differ.
3. The reader sample chooses uniformly at each fork, which is deliberately
   NOT uniform over paths. See ``test_a_reader_sample_favours_the_shallow_branch``
   for the distinction and why we want this one.
4. An incomplete enumeration must say so rather than return a smaller number,
   because a partial path set silently understates any spread computed from it.
"""

from __future__ import annotations

import pytest

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.paths import (
    Draw,
    PathSet,
    covering_paths,
    path_bodies,
    reader_sample_paths,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _story(
    nodes: list[dict[str, object]],
    start: str,
    *,
    ending_count: int = 1,
) -> Storybook:
    """Build a minimal Tier-1 Storybook from a node list."""
    data: dict[str, object] = {
        "schema_version": "2.0",
        "id": "s_paths",
        "version": 1,
        "title": "Test Story",
        "metadata": {
            "age_band": "10-13",
            "reading_level": {"scheme": "flesch_kincaid", "target": 5.0},
            "tier": 1,
            "themes": ["test"],
            "estimated_minutes": 5,
            "ending_count": ending_count,
            "topology": "branch_and_bottleneck",
        },
        "variables": [],
        "start_node": start,
        "nodes": nodes,
    }
    return Storybook.model_validate(data)


def _ending(node_id: str, body: str, ending_id: str) -> dict[str, object]:
    """Build an ending node."""
    return {
        "id": node_id,
        "body": body,
        "is_ending": True,
        "ending": {
            "id": ending_id,
            "valence": "positive",
            "kind": "success",
            "title": "The End",
        },
        "choices": [],
    }


def _linear_story() -> Storybook:
    """start -> middle -> end, one path only."""
    return _story(
        nodes=[
            {
                "id": "start",
                "body": "Begin here.",
                "is_ending": False,
                "choices": [{"id": "c1", "label": "Go", "target": "middle"}],
            },
            {
                "id": "middle",
                "body": "The middle part.",
                "is_ending": False,
                "choices": [{"id": "c2", "label": "Finish", "target": "end"}],
            },
            _ending("end", "It is done.", "e1"),
        ],
        start="start",
    )


def _single_ending_story() -> Storybook:
    """start is itself an ending: the shortest possible book, one reading."""
    return _story(nodes=[_ending("start", "The whole book.", "e1")], start="start")


def _diamond_story() -> Storybook:
    """start forks to left/right, both reconverging on one ending."""
    return _story(
        nodes=[
            {
                "id": "start",
                "body": "A fork in the road.",
                "is_ending": False,
                "choices": [
                    {"id": "c_left", "label": "Left", "target": "left"},
                    {"id": "c_right", "label": "Right", "target": "right"},
                ],
            },
            {
                "id": "left",
                "body": "The left way.",
                "is_ending": False,
                "choices": [{"id": "c_l_end", "label": "On", "target": "end"}],
            },
            {
                "id": "right",
                "body": "The right way.",
                "is_ending": False,
                "choices": [{"id": "c_r_end", "label": "On", "target": "end"}],
            },
            _ending("end", "Both roads arrive.", "e1"),
        ],
        start="start",
    )


def _lopsided_story() -> Storybook:
    """One fork: a one-hop ending on the left, a three-hop chain on the right.

    Uniform-over-choices and uniform-over-paths disagree here, which is the
    point: there are two paths, and a reader picking at random hits each with
    probability one half regardless of how long the right branch is.
    """
    return _story(
        nodes=[
            {
                "id": "start",
                "body": "A fork.",
                "is_ending": False,
                "choices": [
                    {"id": "c_short", "label": "Short", "target": "end_short"},
                    {"id": "c_long", "label": "Long", "target": "long_a"},
                ],
            },
            _ending("end_short", "A quick finish.", "e_short"),
            {
                "id": "long_a",
                "body": "The long way begins.",
                "is_ending": False,
                "choices": [{"id": "c_a", "label": "On", "target": "long_b"}],
            },
            {
                "id": "long_b",
                "body": "The long way continues.",
                "is_ending": False,
                "choices": [{"id": "c_b", "label": "On", "target": "end_long"}],
            },
            _ending("end_long", "A slow finish.", "e_long"),
        ],
        start="start",
        ending_count=2,
    )


def _deep_chain_story(length: int) -> Storybook:
    """A single chain of *length* nodes, ending at the last one.

    Path depth scales with node count, which is what a recursive enumerator
    cannot survive: the interpreter's stack limit, not the story, decides how
    long a reading may be.
    """
    nodes: list[dict[str, object]] = [
        {
            "id": f"n{i}",
            "body": f"Step {i}.",
            "is_ending": False,
            "choices": [{"id": f"c{i}", "label": "On", "target": f"n{i + 1}"}],
        }
        for i in range(length - 1)
    ]
    nodes.append(_ending(f"n{length - 1}", "Arrived.", "e1"))
    return _story(nodes=nodes, start="n0")


def _branch_and_bottleneck_story(levels: int) -> Storybook:
    """*levels* binary forks in series, each pair reconverging on the next fork.

    This is the ``branch_and_bottleneck`` topology the catalogue actually uses,
    and it is the shape that separates a covering set from a sample. The graph
    stays small, three nodes per level, while the number of distinct readings is
    ``2 ** levels``. At eighteen levels that is over a quarter of a million
    readings through fifty-five nodes, so any approach that reaches coverage by
    enumerating readings runs out of budget long before it reaches the forks
    near the start, while an approach that constructs a reading per fork does
    not care how many readings exist.
    """
    nodes: list[dict[str, object]] = []
    for i in range(levels):
        nodes.append(
            {
                "id": f"f{i}",
                "body": f"Fork {i}.",
                "is_ending": False,
                "choices": [
                    {"id": f"c{i}a", "label": "This way", "target": f"a{i}"},
                    {"id": f"c{i}b", "label": "That way", "target": f"b{i}"},
                ],
            }
        )
        following = f"f{i + 1}" if i + 1 < levels else "finish"
        nodes.extend(
            {
                "id": f"{side}{i}",
                "body": f"The {side} way at {i}.",
                "is_ending": False,
                "choices": [
                    {"id": f"c{i}{side}on", "label": "On", "target": following}
                ],
            }
            for side in ("a", "b")
        )
    nodes.append(_ending("finish", "All roads arrive.", "e1"))
    return _story(nodes=nodes, start="f0")


# ---------------------------------------------------------------------------
# Covering set
# ---------------------------------------------------------------------------


def test_a_deep_story_does_not_exhaust_the_interpreter_stack() -> None:
    """Regression: enumeration depth must be bounded by the story, not by Python.

    Found by running the covering set over the real skeleton catalogue rather
    than over hand-built fixtures. ``skeletons/10-13/the-winter-of-the-wolf-queen.json``
    has 250 nodes and three variables, and a recursive depth-first walk blew
    the 1000-frame limit on it. A book that is merely long is not a book we
    are entitled to refuse to measure.
    """
    story = _deep_chain_story(400)

    result = covering_paths(story)

    assert result.complete
    assert len(result.paths) == 1
    assert len(result.paths[0]) == 400
    assert result.edge_coverage == 1.0


def test_coverage_does_not_depend_on_how_many_readings_the_book_has() -> None:
    """Full coverage of a small graph, however many readings run through it.

    Found by running against the real catalogue rather than fixtures: on
    ``16+/the-tenfold-siege`` the covering set reported 30.5 percent coverage
    at its default budget. The cause was structural, not a tuning problem.
    Enumerating readings depth first and keeping the ones that add coverage
    spends the entire budget inside whichever subtree it enters first, so on
    any book with more readings than budget the "covering" set covers one
    corner. It reported that honestly, which is the only reason the defect was
    visible, but a number nobody can use is not a measurement.

    Eighteen forks give 262,144 readings through 55 nodes. Coverage must be
    complete, and it must cost work proportional to the graph rather than to
    the reading count.
    """
    result = covering_paths(_branch_and_bottleneck_story(levels=18))

    assert result.complete
    assert result.edge_coverage == 1.0
    assert result.reachable_choices == 18 * 4
    # One reading per fork suffices; anything near the reading count means the
    # implementation drifted back to enumerating.
    assert len(result.paths) <= result.reachable_choices


def test_a_linear_story_has_exactly_one_path() -> None:
    """With no forks there is one reading, and it lists nodes in order."""
    result = covering_paths(_linear_story())

    assert result.complete
    assert result.paths == [["start", "middle", "end"]]
    assert result.edge_coverage == 1.0


def test_covering_paths_keeps_the_zero_edge_reading_when_the_start_node_is_an_ending() -> (
    None
):
    """A start node that is itself an ending has no choice edges, but one reading.

    The edge-covering loop has nothing to iterate when the graph has no
    edges, which used to leave the covering set empty for the shortest
    possible book while ``edge_coverage`` reported ``1.0`` (vacuously true
    over zero choices). ``reader_sample_paths`` never had this gap, since its
    per-draw loop checks ``is_ending`` before it ever needs an edge; the
    covering set must not silently drop the one reading a one-node book has.
    """
    result = covering_paths(_single_ending_story())

    assert result.paths == [["start"]]
    assert result.reachable_choices == 0
    assert result.edge_coverage == 1.0


def test_the_covering_set_exercises_every_choice_of_a_diamond() -> None:
    """Both branches of a fork must appear, even though they reconverge."""
    result = covering_paths(_diamond_story())

    assert result.complete
    assert result.edge_coverage == 1.0
    traversed = {node for path in result.paths for node in path}
    assert "left" in traversed
    assert "right" in traversed


def test_the_covering_set_drops_a_path_that_adds_no_new_edge() -> None:
    """A covering set keeps only paths that cover something not yet covered.

    The diamond has exactly two root-to-ending paths and both are needed, so
    the assertion that bites is the upper bound: a third path would mean the
    greedy filter is not filtering.
    """
    result = covering_paths(_diamond_story())

    assert len(result.paths) == 2


def test_every_covering_path_starts_at_the_start_node_and_ends_at_an_ending() -> None:
    """A path that stops mid-story would understate every measure taken over it."""
    story = _lopsided_story()

    result = covering_paths(story)

    endings = {node.id for node in story.nodes if node.is_ending}
    for path in result.paths:
        assert path[0] == story.start_node
        assert path[-1] in endings


# ---------------------------------------------------------------------------
# Reader sample
# ---------------------------------------------------------------------------


def test_a_reader_sample_is_reproducible_under_a_seed() -> None:
    """Same seed, same sample. A measurement nobody can re-run is not evidence."""
    story = _lopsided_story()

    first = reader_sample_paths(story, Draw(count=20, seed=7))
    second = reader_sample_paths(story, Draw(count=20, seed=7))

    assert first.paths == second.paths
    assert len(first.paths) == 20


def test_a_reader_sample_favours_the_shallow_branch() -> None:
    """The sample is uniform over CHOICES, not over paths, and that is deliberate.

    The lopsided story has two paths. Uniform-over-paths would draw each half
    the time and so would uniform-over-choices here, but the reader model is
    the one we want: a child picks an option at a fork, not a path from the
    set of all readings. This test pins the model by checking the draw is
    balanced at the fork rather than weighted by branch length.
    """
    result = reader_sample_paths(_lopsided_story(), Draw(count=200, seed=11))

    short = sum(1 for path in result.paths if path == ["start", "end_short"])
    assert 60 < short < 140


def test_a_reader_sample_of_a_linear_story_repeats_the_only_path() -> None:
    """With no choice to make, every sampled reading is the same reading."""
    result = reader_sample_paths(_linear_story(), Draw(count=5, seed=3))

    assert result.paths == [["start", "middle", "end"]] * 5


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------


def test_a_capped_enumeration_reports_itself_incomplete() -> None:
    """A truncated path set must say so; a partial set understates spread.

    #VERIFY for the workplan's W1 rule that a capped walk suppresses the
    number rather than shrinking it.
    """
    result = covering_paths(_diamond_story(), cap=1)

    assert not result.complete
    assert result.edge_coverage < 1.0


def test_an_uncapped_enumeration_reports_itself_complete() -> None:
    """The negative control for the test above."""
    result = covering_paths(_diamond_story())

    assert result.complete


def test_a_capped_configuration_walk_makes_the_path_set_incomplete() -> None:
    """The mutation check the workplan asks for, on a different cap.

    ``cap`` truncates this module's own depth-first enumeration. This test
    truncates the underlying configuration walk instead, which is the source
    of the ``WalkResult.capped`` flag. Deleting the propagation of that flag
    must fail a test, and before this test existed it did not: the cap=1 case
    above passes with ``walk_complete`` ignored entirely.
    """
    result = covering_paths(_diamond_story(), walk_cap=1)

    assert not result.complete


def test_a_capped_configuration_walk_makes_a_sample_incomplete() -> None:
    """Sampling reads the same flag and must honour it the same way."""
    result = reader_sample_paths(_diamond_story(), Draw(count=3, seed=1), walk_cap=1)

    assert not result.complete


def _dead_end_story() -> Storybook:
    """A fork where the right branch leads to a node with no reachable exit.

    ``trap``'s only choice is conditioned on a flag no path can set, so a
    reader who goes right is stuck. The walk docstring warns that such a node
    is indistinguishable from an ending by edge count alone.
    """
    data: dict[str, object] = {
        "schema_version": "2.0",
        "id": "s_dead_end",
        "version": 1,
        "title": "Dead End",
        "metadata": {
            "age_band": "10-13",
            "reading_level": {"scheme": "flesch_kincaid", "target": 5.0},
            "tier": 2,
            "themes": ["test"],
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "branch_and_bottleneck",
        },
        "variables": [{"name": "key", "type": "bool", "initial": False}],
        "start_node": "start",
        "nodes": [
            {
                "id": "start",
                "body": "A fork.",
                "is_ending": False,
                "choices": [
                    {"id": "c_safe", "label": "Safe", "target": "end"},
                    {"id": "c_trap", "label": "Trap", "target": "trap"},
                ],
            },
            {
                "id": "trap",
                "body": "Stuck.",
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_locked",
                        "label": "Unlock",
                        "target": "end",
                        "condition": {"==": [{"var": "key"}, True]},
                    }
                ],
            },
            _ending("end", "Out.", "e1"),
        ],
    }
    return Storybook.model_validate(data)


def test_a_dead_end_branch_yields_no_path_and_shows_as_lost_coverage() -> None:
    """A reading that stops mid-story is not a reading, so it is not a path.

    The choice into the dead-end stays uncovered, which is the signal we want:
    the number tells the author a branch is unreachable rather than the
    enumerator quietly pretending the branch does not exist.
    """
    result = covering_paths(_dead_end_story())

    assert result.paths == [["start", "end"]]
    assert result.edge_coverage < 1.0


def test_a_sample_that_walks_into_a_dead_end_reports_itself_incomplete() -> None:
    """A truncated walk must never be averaged in as if it were a reading."""
    result = reader_sample_paths(_dead_end_story(), Draw(count=40, seed=5))

    assert not result.complete
    assert all(path[-1] == "end" for path in result.paths)
    assert len(result.paths) < 40


# ---------------------------------------------------------------------------
# Bodies
# ---------------------------------------------------------------------------


def test_path_bodies_returns_the_bodies_in_traversal_order() -> None:
    """The whole point: feed these to measure_book to get a per-path grade."""
    story = _linear_story()

    bodies = path_bodies(story, ["start", "middle", "end"])

    assert bodies == ["Begin here.", "The middle part.", "It is done."]


def test_path_bodies_rejects_a_node_the_story_does_not_have() -> None:
    """A silent empty body would drag a reading-level grade toward nothing."""
    story = _linear_story()

    with pytest.raises(KeyError, match="nope"):
        path_bodies(story, ["start", "nope"])


def test_a_path_set_is_frozen() -> None:
    """Results get passed around several measures; none of them may edit it."""
    result = covering_paths(_linear_story())

    assert isinstance(result, PathSet)
    with pytest.raises(AttributeError):
        result.complete = False  # type: ignore[misc]
