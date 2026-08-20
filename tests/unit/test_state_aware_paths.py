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

import json
from pathlib import Path

import pytest

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
    _check_min_to_complete,
    _decision_node_ids,
    _fewest_decision_shortest_path,
    _traversal_for,
)
from cyo_adventure.validator.report import Severity, ValidationReport
from cyo_adventure.validator.walk import (
    DEFAULT_PATH_BUDGET,
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


def _looping_counter_story(laps: int = 8) -> Storybook:
    """A tiny story whose reader must lap one corridor to unlock the win.

    Five distinct nodes. `n_hub` and `n_back` form a two-node loop, and the win
    is gated on an int counter the loop increments, so the CONFIGURATION space
    is large (one config per counter value) while the story a reader sees is
    five pages. This is the shape that separates the two node counts, and the
    shape whose unbounded `path` growth exhausted memory.
    """
    return Storybook(
        id="s_looping_counter",
        version=1,
        title="The Long Way Round",
        start_node="n_start",
        nodes=[
            Node(
                id="n_start",
                body="A hub, and a way out." * 4,
                choices=[
                    {"id": "c_in", "label": "In", "target": "n_hub"},
                    {"id": "c_quit", "label": "Leave", "target": "n_lose"},
                ],
            ),
            Node(
                id="n_hub",
                body="The hub again." * 4,
                choices=[
                    {
                        "id": "c_lap",
                        "label": "Round again",
                        "target": "n_back",
                        "effects": [{"op": "inc", "var": "count", "value": 1}],
                    },
                    {
                        "id": "c_out",
                        "label": "Out",
                        "target": "n_win",
                        "condition": {">=": [{"var": "count"}, laps]},
                    },
                ],
            ),
            Node(
                id="n_back",
                body="The far side." * 4,
                choices=[{"id": "c_return", "label": "Back", "target": "n_hub"}],
            ),
            Node(
                id="n_win",
                body="Out at last." * 4,
                is_ending=True,
                ending=Ending(
                    id="e_win",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="Out",
                ),
            ),
            Node(
                id="n_lose",
                body="You never went in." * 4,
                is_ending=True,
                ending=Ending(
                    id="e_lose",
                    valence=Valence.NEGATIVE,
                    kind=EndingKind.SETBACK,
                    title="Home",
                ),
            ),
        ],
        variables=[Variable(name="count", type=VariableType.INT, initial=0)],
        metadata=StoryMetadata(
            age_band="13-16",
            reading_level=ReadingLevel(target=7.0),
            tier=2,
            estimated_minutes=5,
            ending_count=2,
            content_flags=ContentFlags(),
            topology=Topology.GAUNTLET,
        ),
    )


def test_a_looping_int_counter_caps_rather_than_exhausting_memory() -> None:
    """The walk is bounded by MEMORY, not only by configuration count.

    `configs` retains one `ReadingState` per configuration and each carries its
    own `path` list, which `choose` copies in full on every transition, so
    retained state is O(configs x depth). `DEFAULT_CONFIG_CAP` bounds only the
    first factor. On a story whose depth grows with its configuration count this
    exhausted memory before the config cap was reached: `validate_policy` on a
    FIVE-node story of this shape OOM-killed the process, so the gate died
    instead of reporting on the book it was asked to judge, and it does so on the
    request path (`run_gate` calls `validate_policy` unconditionally).

    A tight budget here stands in for the default: the assertion is that the walk
    ANSWERS with its documented degraded result rather than running away.
    """
    story = _looping_counter_story(laps=10_000)

    walk = walk_configurations(story, path_budget=500)

    assert walk.capped, "an unbounded counter must trip the memory budget"
    retained = sum(len(state.path) for state in walk.configs.values())
    assert retained <= 500, f"retained {retained} path entries, budget was 500"


def test_a_capped_walk_still_reaches_the_policy_layer_as_a_fallback() -> None:
    """A budget breach degrades to the declared graph; it does not crash or skip.

    The walk's `capped` contract already says a partial closure must not be
    measured, and `_traversal_for` answers it with the pre-`UW-C292` declared
    graph. This pins that the memory guard routes into that SAME contract rather
    than into a new failure mode.
    """
    story = _looping_counter_story(laps=10_000)

    walk = walk_configurations(story, path_budget=500)
    assert walk.capped

    traversal = _traversal_for(story)
    assert traversal is not None
    assert not traversal.state_aware, (
        "a story the walk cannot close must be measured on the declared graph"
    )


def _errand_hub_story() -> Storybook:
    """Three errands off one hub, and a win that needs all three.

    Six distinct nodes. The reader must return to `n_hub` between errands, so
    the shortest walk a reader can actually take VISITS `n_hub` four times while
    reading six distinct pages. State is three bools, so the configuration space
    is finite and the walk closes: this exercises state-aware mode for real,
    unlike an unbounded counter, which always caps.
    """
    errands = ("a", "b", "c")
    nodes: list[Node] = [
        Node(
            id="n_start",
            body="The village square." * 4,
            choices=[
                {"id": "c_go", "label": "Begin", "target": "n_hub"},
                {"id": "c_home", "label": "Go home", "target": "n_lose"},
            ],
        ),
        Node(
            id="n_hub",
            body="The hub, and three lanes off it." * 4,
            choices=[
                *(
                    {
                        "id": f"c_{name}",
                        "label": f"Lane {name}",
                        "target": f"n_{name}",
                    }
                    for name in errands
                ),
                {
                    "id": "c_done",
                    "label": "Report back",
                    "target": "n_win",
                    "condition": {"and": [{"var": f"got_{name}"} for name in errands]},
                },
            ],
        ),
        Node(
            id="n_win",
            body="All three errands run." * 4,
            is_ending=True,
            ending=Ending(
                id="e_win",
                valence=Valence.POSITIVE,
                kind=EndingKind.SUCCESS,
                title="Done",
            ),
        ),
        Node(
            id="n_lose",
            body="You never started." * 4,
            is_ending=True,
            ending=Ending(
                id="e_lose",
                valence=Valence.NEGATIVE,
                kind=EndingKind.SETBACK,
                title="Home",
            ),
        ),
    ]
    nodes.extend(
        Node(
            id=f"n_{name}",
            body=f"Lane {name}, and the errand at the end of it." * 4,
            choices=[
                {
                    "id": f"c_{name}_back",
                    "label": "Back to the hub",
                    "target": "n_hub",
                    "effects": [{"op": "set", "var": f"got_{name}", "value": True}],
                }
            ],
        )
        for name in errands
    )
    return Storybook(
        id="s_errand_hub",
        version=1,
        title="Three Errands",
        start_node="n_start",
        nodes=nodes,
        variables=[
            Variable(name=f"got_{name}", type=VariableType.BOOL, initial=False)
            for name in errands
        ],
        metadata=StoryMetadata(
            age_band="8-11",
            length="short",
            narrative_style="prose",
            reading_level=ReadingLevel(target=4.5),
            tier=2,
            estimated_minutes=5,
            ending_count=2,
            content_flags=ContentFlags(),
            topology=Topology.OPEN_MAP,
        ),
    )


def test_pl20_counts_distinct_nodes_not_loop_repeats() -> None:
    """A hollow win cannot clear PL-20's floor by re-reading one page.

    PL-20 measured `len(path)` over a CONFIGURATION path, but `node_of` is
    many-to-one in state-aware mode, so a walk that returns to a hub lists that
    page once per visit. `min_complete_floor` is calibrated in distinct authored
    nodes (ADR-011 section 3), so the blocking ERROR compared a config-space
    quantity against a node-space threshold, and a story could clear its floor by
    sending the reader back through pages they had already read.
    """
    story = _errand_hub_story()
    traversal = _traversal_for(story)
    assert traversal is not None
    assert traversal.state_aware, "fixture must exercise the configuration graph"

    path = _fewest_decision_shortest_path(
        traversal.adjacency,
        traversal.start,
        {v for v, node_id in traversal.node_of.items() if node_id == "n_win"},
        traversal.decisions,
    )
    assert path is not None

    distinct = {traversal.node_of[vertex] for vertex in path}
    assert distinct == {"n_start", "n_hub", "n_a", "n_b", "n_c", "n_win"}
    assert len(distinct) == 6, "six distinct pages is what a reader reads"
    assert len(path) > len(distinct), (
        "fixture must actually revisit a page, or it cannot show the difference"
    )

    # The rule itself, not just the measurement. 8-11/short/prose floors at 9:
    # the six distinct pages the reader reads are BELOW it, while the nine
    # config-path vertices the old code counted were exactly at it. So the
    # pre-fix code reported this story compliant and the fixed code blocks it.
    report = ValidationReport()
    _check_min_to_complete(story, traversal, report)
    pl20 = [f for f in report.findings if f.rule_id == "PL-20"]
    assert pl20, "PL-20 must fire: six distinct pages is under the floor of 9"
    assert "is 6 node(s)" in pl20[0].message, pl20[0].message
    assert pl20[0].severity is Severity.ERROR


def test_the_deepest_committed_skeleton_fits_the_path_budget() -> None:
    """The memory bound must sit above the real catalog, not below it.

    A budget under the catalog turns this guard into the false-blocking defect it
    exists to prevent: the first value tried here (2,000,000) was set from an
    assumed mean depth rather than measured, and capped
    `16+/the-longwinter-station`, whose walk completes with 51,241 configurations
    but 2,277,492 retained path entries. A capped walk raises L2-12 and BLOCKS,
    so the book went from passing the full gate to rejected.

    Pinned against the committed file so the budget is re-checked whenever the
    catalog's deepest conditioned book changes, rather than rediscovered as a
    gate failure.
    """
    path = Path("skeletons/16+/the-longwinter-station.json")
    if not path.exists():  # pragma: no cover - corpus coverage, UW-F20
        pytest.skip(f"{path} is not committed")

    story = Storybook.model_validate(json.loads(path.read_text(encoding="utf-8")))
    walk = walk_configurations(story)

    assert not walk.capped, (
        "the deepest committed conditioned skeleton must complete its walk"
    )
    retained = sum(len(state.path) for state in walk.configs.values())
    assert retained < DEFAULT_PATH_BUDGET, (
        f"{path} retains {retained:,} path entries against a budget of "
        f"{DEFAULT_PATH_BUDGET:,}; the budget must stay above the real catalog"
    )
