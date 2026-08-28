"""Pin the two exact computations behind the continuity measure.

The module reads no prose, so everything here is graph shape and declared state.
That is the point: two other formulations of this measure DID read prose, were
measured, and failed (3.48 findings per node, and 1 true positive in 6). The
survivor is exact, and exact things can be tested against hand-checked answers
rather than against a corpus average.

The cyclic case is the one that matters most. ``loop_and_grow`` hubs are cyclic
by design, and a dominator computation written for a DAG would be wrong on
precisely the books this measure exists for.
"""

from __future__ import annotations

import pytest

from cyo_adventure.storybook.models import Effect, EffectOp, Node, Storybook
from cyo_adventure.validator.continuity import (
    dominating_nodes,
    is_stateless,
    optional_history,
)


def _story(
    nodes: list[Node],
    *,
    start: str = "n1",
    variables: list[object] | None = None,
    tier: int = 1,
) -> Storybook:
    """Build the smallest Storybook that carries a given graph.

    Args:
        nodes: The nodes, in the order the story declares them.
        start: The start node id.
        variables: Declared variables, or ``None`` for a stateless story.
        tier: The story tier. Tier 1 is schema-forbidden from declaring
            variables, which is why every stateful fixture here is Tier 2, and
            is the reason all six catalogue ``loop_and_grow`` skeletons are
            stateless: the constraint is structural, not an oversight.

    Returns:
        Storybook: The assembled story.
    """
    return Storybook.model_validate(
        {
            "schema_version": "2.0",
            "id": "sk_test",
            "version": 1,
            "title": "Test",
            "start_node": start,
            "variables": variables or [],
            "metadata": {
                "age_band": "5-8",
                "reading_level": {
                    "scheme": "flesch_kincaid",
                    "target": 2.5,
                    "tolerance": 1.0,
                },
                "tier": tier,
                "themes": ["play"],
                "estimated_minutes": 5,
                "ending_count": sum(1 for node in nodes if node.is_ending),
                "content_flags": {
                    "violence": "none",
                    "scariness": "none",
                    "peril": "none",
                },
                "topology": "branch_and_bottleneck",
                "length": "short",
                "narrative_style": "prose",
            },
            "nodes": [node.model_dump() for node in nodes],
        }
    )


def _node(node_id: str, targets: list[str], *, ending: bool = False) -> Node:
    """Build one node pointing at *targets*.

    Args:
        node_id: The node's id.
        targets: Ids this node offers a choice to.
        ending: Whether the node terminates a reading.

    Returns:
        Node: The assembled node.
    """
    return Node.model_validate(
        {
            "id": node_id,
            "body": "Body text long enough to be a node body and nothing more.",
            "is_ending": ending,
            "ending": (
                {
                    "id": f"end_{node_id}",
                    "title": "Done",
                    "valence": "positive",
                    "kind": "success",
                }
                if ending
                else None
            ),
            "choices": [
                {"id": f"c_{node_id}_{index}", "label": f"Go {index}", "target": target}
                for index, target in enumerate(targets)
            ],
        }
    )


@pytest.mark.unit
def test_a_pure_branching_tree_has_no_optional_history() -> None:
    """The `time_cave` shape, and why it is the one safe topology.

    Nothing reconverges, so every reader arrives at every node having read
    exactly the same nodes. All six committed `time_cave` books report zero
    across 236 nodes, and this is the shape that makes that true rather than
    lucky.
    """
    story = _story(
        [
            _node("n1", ["n2", "n3"]),
            _node("n2", ["e1"]),
            _node("n3", ["e2"]),
            _node("e1", [], ending=True),
            _node("e2", [], ending=True),
        ]
    )

    assert optional_history(story) == []


@pytest.mark.unit
def test_a_bottleneck_reports_exactly_the_branch_the_reader_may_have_skipped() -> None:
    """Two branches rejoining: each is optional, the fork and the join are not.

    This is the whole measure in one graph. ``n2`` and ``n3`` are on some route
    into ``n4`` and not on every route, so they are what ``n4`` must not
    presuppose. ``n1`` is on every route and is therefore safe to reference.
    """
    story = _story(
        [
            _node("n1", ["n2", "n3"]),
            _node("n2", ["n4"]),
            _node("n3", ["n4"]),
            _node("n4", ["e1"]),
            _node("e1", [], ending=True),
        ]
    )

    by_node = {item.node_id: item.optional for item in optional_history(story)}

    assert by_node["n4"] == ("n2", "n3")
    assert by_node["e1"] == ("n2", "n3")
    assert "n2" not in by_node
    assert "n3" not in by_node


@pytest.mark.unit
def test_a_hub_the_reader_can_re_enter_is_handled_by_the_fixed_point() -> None:
    """The `loop_and_grow` shape, cyclic on purpose.

    A DAG-only dominator computation either loops forever or reports nonsense
    here, and this is exactly the shape of every book the measure was built for.
    The side trips are optional at the hub because the reader may return having
    taken either one, or neither on the first pass.
    """
    story = _story(
        [
            _node("n1", ["hub"]),
            _node("hub", ["side_a", "side_b", "e1"]),
            _node("side_a", ["hub"]),
            _node("side_b", ["hub"]),
            _node("e1", [], ending=True),
        ]
    )

    by_node = {item.node_id: item.optional for item in optional_history(story)}

    assert by_node["hub"] == ("side_a", "side_b")
    assert by_node["e1"] == ("side_a", "side_b")


@pytest.mark.unit
def test_an_unreachable_node_is_not_this_measures_finding() -> None:
    """L1 owns unreachability; reporting it here would double-count it."""
    story = _story(
        [
            _node("n1", ["e1"]),
            _node("orphan", ["e1"]),
            _node("e1", [], ending=True),
        ]
    )

    assert [item.node_id for item in optional_history(story)] == []


@pytest.mark.unit
def test_a_dangling_choice_target_does_not_crash_the_measure() -> None:
    """A missing target is L1-2's finding, so this must survive it, not report it."""
    story = _story(
        [
            _node("n1", ["nowhere", "e1"]),
            _node("e1", [], ending=True),
        ]
    )

    assert optional_history(story) == []


@pytest.mark.unit
def test_a_story_with_no_declared_mechanism_is_stateless() -> None:
    """The baseline: no variables, no on_enter, no conditions."""
    story = _story([_node("n1", ["e1"]), _node("e1", [], ending=True)])

    assert is_stateless(story) is True


@pytest.mark.unit
def test_an_on_enter_effect_alone_makes_a_story_stateful() -> None:
    """All three mechanisms count, because any one of them can carry history.

    Checking ``variables`` alone would call a book stateless while an
    ``on_enter`` effect was quietly tracking exactly what the measure assumes
    nothing tracks.
    """
    plain = _node("n1", ["e1"])
    with_effect = plain.model_copy(
        update={"on_enter": [Effect(op=EffectOp.SET, var="seen", value=1)]}
    )
    story = _story(
        [with_effect, _node("e1", [], ending=True)],
        variables=[{"name": "seen", "type": "int", "min": 0, "max": 3, "initial": 0}],
        tier=2,
    )

    assert story.variables
    assert is_stateless(story) is False


@pytest.mark.unit
def test_a_declared_variable_makes_a_story_stateful() -> None:
    """The simplest case, held separately so the parametrised test stays readable."""
    story = _story(
        [_node("n1", ["e1"]), _node("e1", [], ending=True)],
        variables=[{"name": "seen", "type": "int", "min": 0, "max": 3, "initial": 0}],
        tier=2,
    )

    assert is_stateless(story) is False


@pytest.mark.unit
def test_dominance_is_strict_and_the_fork_dominates_the_join() -> None:
    """The dominator half on its own, which PN-1 consumes without the ancestors.

    Exposed as public API for `validator/naming.py`, so it needs its own
    contract rather than only the one `optional_history` implies. On the
    bottleneck shape: the fork is on every route to the join and neither
    branch is. Dominance is strict, so no node appears in its own set and the
    start node maps to the empty set; PN-1 depends on that, because it asks
    separately whether the node itself introduces the name.
    """
    story = _story(
        [
            _node("n1", ["n2", "n3"]),
            _node("n2", ["n4"]),
            _node("n3", ["n4"]),
            _node("n4", ["e1"]),
            _node("e1", [], ending=True),
        ]
    )

    dominators = dominating_nodes(story)

    assert dominators["n1"] == frozenset()
    assert dominators["n4"] == frozenset({"n1"})
    assert dominators["n2"] == frozenset({"n1"})
    assert dominators["e1"] == frozenset({"n1", "n4"})


@pytest.mark.unit
def test_an_unreachable_node_is_absent_from_the_dominator_map() -> None:
    """Matching `optional_history`: an unreachable node is L1's finding, not ours.

    PN-1 relies on this to decide membership with `node_id in dominators`, so
    an unreachable node must be absent rather than present with an empty set.
    """
    story = _story(
        [
            _node("n1", ["e1"]),
            _node("orphan", ["e1"]),
            _node("e1", [], ending=True),
        ]
    )

    dominators = dominating_nodes(story)

    assert "orphan" not in dominators
    assert set(dominators) == {"n1", "e1"}


@pytest.mark.unit
def test_a_dangling_choice_target_does_not_crash_dominating_nodes() -> None:
    """The dominator half needs its own crash-survival pin, not just the pair's.

    `optional_history` and `dominating_nodes` build independent copies of the
    same successor/predecessor scan, each with its own dangling-target guard.
    A dangling target is L1-2's finding, so this must survive it rather than
    raise `KeyError` while indexing `predecessors` by an id nothing declared.
    """
    story = _story(
        [
            _node("n1", ["nowhere", "e1"]),
            _node("e1", [], ending=True),
        ]
    )

    dominators = dominating_nodes(story)

    assert dominators["n1"] == frozenset()
    assert dominators["e1"] == frozenset({"n1"})


@pytest.mark.unit
def test_dominance_over_a_re_enterable_hub_is_the_fixed_point() -> None:
    """The dominator half over the same cyclic shape, unpinned until now.

    A dominator fixed-point over a cyclic graph is exactly where an iteration
    bug hides, and `loop_and_grow` hubs are cyclic by design. Every route to
    `hub`, `side_a`, `side_b`, and `e1` passes through `n1`; every route to
    `side_a`, `side_b`, and `e1` additionally passes through `hub`, since it
    is their only predecessor. Neither side branch dominates anything: a
    reader can reach `hub` again, and `e1`, having taken either one or
    neither on the first pass.
    """
    story = _story(
        [
            _node("n1", ["hub"]),
            _node("hub", ["side_a", "side_b", "e1"]),
            _node("side_a", ["hub"]),
            _node("side_b", ["hub"]),
            _node("e1", [], ending=True),
        ]
    )

    dominators = dominating_nodes(story)

    assert dominators["n1"] == frozenset()
    assert dominators["hub"] == frozenset({"n1"})
    assert dominators["side_a"] == frozenset({"n1", "hub"})
    assert dominators["side_b"] == frozenset({"n1", "hub"})
    assert dominators["e1"] == frozenset({"n1", "hub"})
