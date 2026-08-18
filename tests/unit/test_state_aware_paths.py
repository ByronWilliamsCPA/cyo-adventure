"""PL-20, PL-25 and PL-26 must measure paths a reader can actually walk.

`policy._build_graph` adds an edge for every declared choice and never reads
`choice.condition`, so a path through it may use an edge no reachable
configuration can traverse. All three of these rules measure how far the reader
travels, so all three were wrong on any story with state (`UW-C292`). The first
gamebook draft was reported as reaching a win in 16 nodes along a route needing
an item that route never picks up; the state-aware answer was 24.

These tests pin the fix at the level that matters: a story built so the two
readings disagree, checked against both.
"""

from __future__ import annotations

from cyo_adventure.storybook.models import (
    ContentFlags,
    Ending,
    EndingKind,
    Node,
    ReadingLevel,
    Storybook,
    StoryMetadata,
    Topology,
    Valence,
    Variable,
    VariableType,
)
from cyo_adventure.validator.policy import (
    _SATISFYING_KINDS,
    _adjacency_of,
    _build_graph,
    _decision_node_ids,
    _fewest_decision_shortest_path,
    _traversal_for,
)
from cyo_adventure.validator.walk import (
    config_dag,
    fastest_satisfying_finish,
    walk_configurations,
)

# The detour the reader must take to earn the key. Long enough that the gap
# between the two readings cannot be a rounding artifact.
_DETOUR = 5


def _locked_door_story() -> Storybook:
    """A story whose shortest route to the win is closed until the key is held.

    Shape:

        n_start -> n_hall -> n_door -> n_win        (4 nodes, needs `has_key`)
        n_start -> n_key_0 .. n_key_4 -> n_hall     (the detour that sets it)

    The condition-blind graph sees `n_start -> n_hall -> n_door -> n_win` and
    reports 4. No reader can walk it: `has_key` is false at `n_door` on that
    route, so the only choice `n_door` offers is the one back into the detour.
    """
    nodes: list[Node] = [
        Node(
            id="n_start",
            body="A hall and a side passage.",
            choices=[
                {"id": "c_hall", "label": "Straight to the hall", "target": "n_hall"},
                {
                    "id": "c_detour",
                    "label": "Down the side passage",
                    "target": "n_key_0",
                },
            ],
        ),
        Node(
            id="n_hall",
            body="The hall, and the door at the end of it.",
            choices=[{"id": "c_door", "label": "To the door", "target": "n_door"}],
        ),
        Node(
            id="n_door",
            body="The door.",
            choices=[
                {
                    "id": "c_open",
                    "label": "Unlock it",
                    "target": "n_win",
                    "condition": {"var": "has_key"},
                },
                {"id": "c_back", "label": "Go back", "target": "n_key_0"},
            ],
        ),
        Node(
            id="n_win",
            body="Through.",
            is_ending=True,
            ending=Ending(
                id="e_win",
                valence=Valence.POSITIVE,
                kind=EndingKind.SUCCESS,
                title="Through the door",
            ),
        ),
    ]
    for index in range(_DETOUR):
        last = index == _DETOUR - 1
        nodes.append(
            Node(
                id=f"n_key_{index}",
                body=f"Side passage, {index}.",
                choices=[
                    {
                        "id": f"c_key_{index}",
                        "label": "On",
                        "target": "n_hall" if last else f"n_key_{index + 1}",
                        # The last step of the detour is where the key is found.
                        "effects": (
                            [{"op": "set", "var": "has_key", "value": True}]
                            if last
                            else []
                        ),
                    }
                ],
            )
        )
    return Storybook(
        id="s_locked_door",
        version=1,
        title="The Locked Door",
        start_node="n_start",
        nodes=nodes,
        variables=[
            Variable(name="has_key", type=VariableType.BOOL, initial=False),
        ],
        metadata=StoryMetadata(
            age_band="13-16",
            reading_level=ReadingLevel(target=7.0),
            tier=2,
            estimated_minutes=5,
            ending_count=1,
            content_flags=ContentFlags(),
            topology=Topology.GAUNTLET,
        ),
    )


def test_the_two_readings_disagree_on_this_story() -> None:
    """The premise of every test below: without state the answer is wrong.

    If this ever stops failing, the fixture has lost the property it exists to
    have and the tests after it prove nothing.
    """
    story = _locked_door_story()
    satisfying = {
        node.id
        for node in story.nodes
        if node.ending is not None and node.ending.kind in _SATISFYING_KINDS
    }
    blind = _fewest_decision_shortest_path(
        _adjacency_of(_build_graph(story)),
        story.start_node,
        satisfying,
        _decision_node_ids(story),
    )
    assert blind is not None
    # n_start -> n_hall -> n_door -> n_win: an edge no reader can take.
    assert len(blind) == 4

    walk = walk_configurations(story)
    assert not walk.capped
    # n_start, the five detour nodes, n_hall, n_door, n_win: the reader has to
    # walk the passage, pick the key up, and come back.
    assert fastest_satisfying_finish(story, walk) == 1 + _DETOUR + 3


def test_policy_measures_the_story_over_its_configurations() -> None:
    """A story that conditions a choice is walked, not read off the choice graph."""
    traversal = _traversal_for(_locked_door_story())
    assert traversal is not None
    assert traversal.state_aware


def test_conditionless_story_is_not_walked() -> None:
    """A story with no conditions keeps the plain choice graph.

    The configuration graph would be isomorphic to it, so walking the state space
    to learn that is pure cost in the gate's request path.
    """
    story = _locked_door_story()
    stripped = story.model_copy(
        update={
            "variables": [],
            "nodes": [
                node.model_copy(
                    update={
                        "choices": [
                            choice.model_copy(update={"condition": None, "effects": []})
                            for choice in node.choices
                        ]
                    }
                )
                for node in story.nodes
            ],
        }
    )
    traversal = _traversal_for(stripped)
    assert traversal is not None
    assert not traversal.state_aware
    # Vertices are node ids, one per node, not synthetic configuration ids.
    assert set(traversal.adjacency) == {node.id for node in stripped.nodes}


def test_a_capped_walk_falls_back_rather_than_measuring_a_fragment() -> None:
    """A capped walk holds part of the state space, so it cannot bound a path.

    Falling back to the choice graph restores the pre-`UW-C292` reading, which is
    wrong in a known direction, rather than reporting a shortest path measured
    over whichever fragment the cap happened to admit.
    """
    story = _locked_door_story()
    walk = walk_configurations(story, cap=3)
    assert walk.capped
    # The projection itself still works on a partial closure; the policy layer's
    # refusal to use one is what this documents.
    dag = config_dag(walk)
    assert dag is not None
    assert len(dag.adjacency) <= 3


def test_fastest_finish_agrees_with_the_mutation_wrapper() -> None:
    """The offline clock re-proof and PL-20 must read one implementation.

    `mutation/` is offline-only (ADR-020) so the validator cannot import it; the
    measurement therefore lives in `validator/walk.py` and the mutation operator
    wraps it, rather than each holding its own copy of the gate's own clock.
    """
    from cyo_adventure.mutation.state_ops import walk_fastest_satisfying_finish

    story = _locked_door_story()
    walk = walk_configurations(story)
    assert walk_fastest_satisfying_finish(story, walk) == fastest_satisfying_finish(
        story, walk
    )
