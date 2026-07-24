"""Unit and property tests for the M4 vary-decisions-per-path operator (WS-5 D5).

Covers design section 4.5: three effect-free, condition-free, Tier-1-only
sub-operations (insert-linear, remove-linear, insert-decision) selected by a
``mode`` parameter, each moving a tree's per-path decision count within the
ADR-011 section 6 4-8 window (design 4.8, the belt-and-braces grammar constant
the gate does not enforce).

Safety properties pinned here (design section 12 D5): the exact per-path
decision counter and the two-sided 4-8 window (an op that would push a path to 9
decisions, or drop one below 4, is discarded at preconditions); PL-20
monotonicity (insert-linear on the shortest satisfying path only ever RAISES the
measure, proven by property over real Tier-1 skeletons); the remove-linear PL-20
below-floor pre-check; insert-decision reconvergence (in-degree rises, post-op
acyclicity enforced, the band reconvergence ceiling honoured where configured);
insert-decision micro-stub (the ending multiset grows by exactly one with a
band-legal ending, PL-15/PL-17 re-checked); and the v1 state-freeness guarantee
(no M4 output introduces any variable, effect, or condition).
"""

from __future__ import annotations

import json
import random
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

import networkx as nx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation import operators as m4_ops
from cyo_adventure.mutation.acceptance import Stage, run_acceptance
from cyo_adventure.mutation.operators import (
    M4,
    M4_OP_ID,
    M4VaryDecisions,
    path_decision_counts,
)
from cyo_adventure.mutation.ops import OpParams, ReguideTarget
from cyo_adventure.validator import band_profile
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    from collections.abc import Mapping

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_CAVE_PATH = _SKELETONS_ROOT / "8-11" / "the-cave-of-echoes.json"
_ROBOT_PATH = _SKELETONS_ROOT / "8-11" / "the-robot-fair-sabotage.json"

_SATISFYING_KINDS = frozenset({"success", "completion"})


def _load(path: Path) -> dict[str, object]:
    """Return a decoded skeleton document."""
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def _cave() -> dict[str, object]:
    """Return a fresh copy of the host skeleton (the-cave-of-echoes, 8-11 short)."""
    return _load(_CAVE_PATH)


def _robot() -> dict[str, object]:
    """Return a fresh copy of a branch_and_bottleneck host (the-robot-fair-sabotage)."""
    return _load(_ROBOT_PATH)


def _nodes_by_id(story: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Return every node dict keyed by its id."""
    result: dict[str, dict[str, object]] = {}
    nodes = story.get("nodes")
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if isinstance(node, dict):
                node_map = cast("dict[str, object]", node)
                node_id = node_map.get("id")
                if isinstance(node_id, str):
                    result[node_id] = node_map
    return result


def _node_ids(story: Mapping[str, object]) -> set[str]:
    """Return the set of node ids in a raw story."""
    return set(_nodes_by_id(story))


def _ending_count(story: Mapping[str, object]) -> int:
    """Return the number of ending nodes in a raw story."""
    return sum(
        1 for node in _nodes_by_id(story).values() if node.get("is_ending") is True
    )


def _ending_kinds(story: Mapping[str, object]) -> set[str]:
    """Return the set of ending kinds present in a raw story."""
    kinds: set[str] = set()
    for node in _nodes_by_id(story).values():
        ending = node.get("ending")
        if isinstance(ending, dict):
            kind = cast("dict[str, object]", ending).get("kind")
            if isinstance(kind, str):
                kinds.add(kind)
    return kinds


def _graph(story: Mapping[str, object]) -> nx.DiGraph[str]:
    """Build the directed choice graph over a raw story's node ids."""
    graph: nx.DiGraph[str] = nx.DiGraph()
    for node in _nodes_by_id(story).values():
        source = node.get("id")
        if not isinstance(source, str):
            continue
        graph.add_node(source)
        for choice in cast("list[object]", node.get("choices", [])):
            if isinstance(choice, dict):
                target = cast("dict[str, object]", choice).get("target")
                if isinstance(target, str):
                    graph.add_edge(source, target)
    return graph


def _in_degree(story: Mapping[str, object], node_id: str) -> int:
    """Return how many choice edges target ``node_id``."""
    graph = _graph(story)
    return int(graph.in_degree(node_id)) if node_id in graph else 0


def _satisfying_ids(story: Mapping[str, object]) -> set[str]:
    """Return the node ids of success/completion (PL-20 satisfying) endings."""
    ids: set[str] = set()
    for node in _nodes_by_id(story).values():
        node_id = node.get("id")
        ending = node.get("ending")
        if isinstance(node_id, str) and isinstance(ending, dict):
            kind = cast("dict[str, object]", ending).get("kind")
            if isinstance(kind, str) and kind in _SATISFYING_KINDS:
                ids.add(node_id)
    return ids


def _shortest_satisfying_nodes(story: Mapping[str, object]) -> int | None:
    """Return the fewest nodes on any path to a satisfying ending, or None.

    Measured in nodes (hops + 1), matching ``validator.policy`` and the operator's
    own PL-20 measure; recomputed here in the test so the property is proven
    against an independent implementation.
    """
    graph = _graph(story)
    start = story.get("start_node")
    if not isinstance(start, str) or start not in graph:
        return None
    best: int | None = None
    for target in _satisfying_ids(story):
        if target in graph and nx.has_path(graph, start, target):
            nodes = int(nx.shortest_path_length(graph, start, target)) + 1
            if best is None or nodes < best:
                best = nodes
    return best


def _has_state(story: Mapping[str, object]) -> bool:
    """Return whether the story declares any variable, effect, or condition."""
    variables = story.get("variables")
    if isinstance(variables, list) and variables:
        return True
    for node in _nodes_by_id(story).values():
        on_enter = node.get("on_enter")
        if isinstance(on_enter, list) and on_enter:
            return True
        for choice in cast("list[object]", node.get("choices", [])):
            if not isinstance(choice, dict):
                continue
            choice_map = cast("dict[str, object]", choice)
            if choice_map.get("condition") is not None:
                return True
            effects = choice_map.get("effects")
            if isinstance(effects, list) and effects:
                return True
    return False


def _tier1_catalog() -> list[tuple[str, dict[str, object]]]:
    """Return ``(slug, story)`` for every production Tier-1 standalone skeleton."""
    catalog: list[tuple[str, dict[str, object]]] = []
    for path in sorted(_SKELETONS_ROOT.glob("*/*.json")):
        if path.name.endswith(".contract.json"):
            continue
        story = _load(path)
        meta = story.get("metadata")
        if not isinstance(meta, dict):
            continue
        metadata = cast("dict[str, object]", meta)
        if (
            metadata.get("production_eligible") is False
            or metadata.get("tier") != 1
            or metadata.get("series") is not None
        ):
            continue
        catalog.append((path.stem, story))
    return catalog


# The PL-20 monotonicity property runs the full gate per example, so it is scoped
# to the smaller Tier-1 skeletons (<= 110 nodes) that admit an insert-linear, to
# keep the property fast while still spanning several bands and topologies.
_SMALL_TIER1 = [
    (slug, story)
    for slug, story in _tier1_catalog()
    if len(cast("list[object]", story["nodes"])) <= 110
    and M4.preconditions(story, OpParams.of(mode="insert-linear")).satisfied
]
_SMALL_TIER1_IDS = [slug for slug, _ in _SMALL_TIER1]


# --- Crafted precondition fixtures (never gate-run; preconditions/counter only) ---


def _diamond_fixture() -> dict[str, object]:
    """Return a 4-node acyclic fixture whose per-path decision counts are [1, 2, 2].

    ``d1`` (2 choices) and ``d2`` (2 choices) are decisions; ``e1``/``e2`` are
    endings. Paths: d1->e1 (1 decision), d1->d2->e1 (2), d1->d2->e2 (2).
    """
    return {
        "start_node": "d1",
        "metadata": {
            "age_band": "3-5",
            "tier": 1,
            "topology": "time_cave",
            "ending_count": 2,
        },
        "variables": [],
        "nodes": [
            {
                "id": "d1",
                "body": "b",
                "is_ending": False,
                "choices": [
                    {"id": "c1a", "label": "A", "target": "d2"},
                    {"id": "c1b", "label": "B", "target": "e1"},
                ],
            },
            {
                "id": "d2",
                "body": "b",
                "is_ending": False,
                "choices": [
                    {"id": "c2a", "label": "A", "target": "e1"},
                    {"id": "c2b", "label": "B", "target": "e2"},
                ],
            },
            {
                "id": "e1",
                "body": "x",
                "is_ending": True,
                "ending": {
                    "id": "x1",
                    "kind": "success",
                    "valence": "positive",
                    "title": "W",
                },
            },
            {
                "id": "e2",
                "body": "x",
                "is_ending": True,
                "ending": {
                    "id": "x2",
                    "kind": "setback",
                    "valence": "negative",
                    "title": "L",
                },
            },
        ],
    }


def _eight_decision_chain_fixture() -> dict[str, object]:
    """Return a 16+ MVP fixture whose longest path holds exactly 8 decisions.

    ``d1..d8`` are 2-choice decisions in a spine (the ``on`` choice continues, the
    ``off`` choice ends). Per-path decision counts run 1..8; ``e_final`` is the
    single satisfying ending. Non-production (MVP envelope 8..45), so the PL-20 and
    breadth-scaled floors do not apply and the 4-8 window is the isolated check.
    """
    nodes: list[dict[str, object]] = []
    for index in range(1, 9):
        nxt = f"d{index + 1}" if index < 8 else "e_final"
        nodes.append(
            {
                "id": f"d{index}",
                "body": "<<FILL role=choice words=80 beats='x'>>",
                "is_ending": False,
                "choices": [
                    {"id": f"c{index}_on", "label": "On", "target": nxt},
                    {"id": f"c{index}_off", "label": "Off", "target": f"e{index}"},
                ],
            }
        )
        nodes.append(
            {
                "id": f"e{index}",
                "body": "x",
                "is_ending": True,
                "ending": {
                    "id": f"end{index}",
                    "kind": "setback",
                    "valence": "negative",
                    "title": "S",
                },
            }
        )
    nodes.append(
        {
            "id": "e_final",
            "body": "x",
            "is_ending": True,
            "ending": {
                "id": "endf",
                "kind": "success",
                "valence": "positive",
                "title": "W",
            },
        }
    )
    return {
        "start_node": "d1",
        "metadata": {
            "age_band": "16+",
            "tier": 1,
            "topology": "sorting_hat",
            "ending_count": 9,
            "production_eligible": False,
        },
        "variables": [],
        "nodes": nodes,
    }


def _remove_below_floor_fixture() -> dict[str, object]:
    """Return a 3-5 short fixture where splicing ``p2`` drops PL-20 below its floor.

    The main spine ``start->p1->p2->p3->p4->e_win`` is 6 nodes (the 3-5 short arc
    floor); a 5-node side branch keeps the post-removal node count (10) at the cell
    envelope minimum, so the PL-20 pre-check is the isolated failure once ``p2`` is
    spliced (shortest satisfying path drops from 6 to 5).
    """
    nodes: list[dict[str, object]] = [
        {
            "id": "start",
            "body": "<<FILL role=setup words=40 beats='x'>>",
            "is_ending": False,
            "choices": [
                {"id": "c_main", "label": "M", "target": "p1"},
                {"id": "c_side", "label": "S", "target": "s1"},
            ],
        }
    ]
    for src, dst in (("p1", "p2"), ("p2", "p3"), ("p3", "p4"), ("p4", "e_win")):
        nodes.append(
            {
                "id": src,
                "body": "<<FILL role=rising words=40 beats='x'>>",
                "is_ending": False,
                "choices": [{"id": f"c_{src}", "label": "On", "target": dst}],
            }
        )
    nodes.append(
        {
            "id": "e_win",
            "body": "w",
            "is_ending": True,
            "ending": {
                "id": "ew",
                "kind": "success",
                "valence": "positive",
                "title": "W",
            },
        }
    )
    for src, dst in (("s1", "s2"), ("s2", "s3"), ("s3", "s4"), ("s4", "e_side")):
        nodes.append(
            {
                "id": src,
                "body": "<<FILL role=rising words=40 beats='x'>>",
                "is_ending": False,
                "choices": [{"id": f"c_{src}", "label": "On", "target": dst}],
            }
        )
    nodes.append(
        {
            "id": "e_side",
            "body": "s",
            "is_ending": True,
            "ending": {
                "id": "es",
                "kind": "setback",
                "valence": "negative",
                "title": "S",
            },
        }
    )
    return {
        "start_node": "start",
        "metadata": {
            "age_band": "3-5",
            "length": "short",
            "narrative_style": "prose",
            "tier": 1,
            "topology": "time_cave",
            "ending_count": 2,
            "production_eligible": True,
        },
        "variables": [],
        "nodes": nodes,
    }


# --- Registration and mode routing ---


@pytest.mark.unit
def test_m4_is_registered_under_its_op_id() -> None:
    """The M4 singleton is registered and exposes its stable op id."""
    assert M4.op_id == M4_OP_ID == "M4"


@pytest.mark.unit
def test_m4_requires_a_known_mode() -> None:
    """A missing or unknown mode fails preconditions and apply."""
    cave = _cave()
    report = M4.preconditions(cave, OpParams.of())
    assert report.satisfied is False
    assert any("mode" in reason for reason in report.failures)
    params = OpParams.of(mode="nonsense")
    rng = random.Random(0)
    with pytest.raises(ValidationError):
        M4.apply(cave, params, rng)


# --- Per-path decision counting (exact on acyclic fixtures) ---


@pytest.mark.unit
def test_m4_path_decision_counter_is_exact_on_a_diamond() -> None:
    """The per-path decision counter matches hand-computed values on an acyclic DAG."""
    counts, truncated = path_decision_counts(_diamond_fixture())
    assert truncated is False
    assert sorted(counts) == [1, 2, 2]


@pytest.mark.unit
def test_m4_path_decision_counter_is_exact_on_a_decision_chain() -> None:
    """An 8-decision spine yields per-path decision counts 1..8 exactly."""
    counts, truncated = path_decision_counts(_eight_decision_chain_fixture())
    assert truncated is False
    assert sorted(counts) == [1, 2, 3, 4, 5, 6, 7, 8, 8]


@pytest.mark.unit
def test_m4_path_decision_counter_never_truncates_an_acyclic_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An acyclic parent is enumerated in full, so it never sets truncated.

    The sample cap bounds only the cyclic search; the acyclic path set is
    finite and exact by design. Pinning the cap below the fixture's path count
    proves the acyclic branch ignores it: every root-to-ending path is still
    returned and ``truncated`` stays False.
    """
    monkeypatch.setattr(m4_ops, "_WALK_PATH_SAMPLE_CAP", 1)
    counts, truncated = path_decision_counts(_diamond_fixture())
    assert truncated is False
    assert sorted(counts) == [1, 2, 2]


@pytest.mark.unit
def test_m4_insert_decision_pushing_a_path_to_nine_is_discarded() -> None:
    """An insert-decision that pushes the deepest path to 9 decisions is discarded.

    The 4-8 window is enforced at preconditions (design 4.5/4.8): splitting the
    deep ``c8_on`` edge lands a 9-decision path, above the ceiling.
    """
    story = _eight_decision_chain_fixture()
    params = OpParams.of(mode="insert-decision", choice="c8_on", variant="micro-stub")
    report = M4.preconditions(story, params)
    assert report.satisfied is False
    assert any(
        "9 decisions" in reason and "window" in reason for reason in report.failures
    )
    rng = random.Random(0)
    with pytest.raises(ValidationError):
        M4.apply(story, params, rng)


@pytest.mark.unit
def test_m4_insert_decision_micro_stub_below_four_is_discarded() -> None:
    """A micro-stub whose stub path holds under 4 decisions is discarded.

    Splitting the shallow ``c_left`` edge on the cave roots a 2-decision stub path
    (``n_start`` then the new decision), below the window floor of 4.
    """
    cave = _cave()
    params = OpParams.of(mode="insert-decision", choice="c_left", variant="micro-stub")
    report = M4.preconditions(cave, params)
    assert report.satisfied is False
    assert any(
        "2 decisions" in reason and "window" in reason for reason in report.failures
    )
    rng = random.Random(0)
    with pytest.raises(ValidationError):
        M4.apply(cave, params, rng)


# --- insert-linear ---


@pytest.mark.unit
def test_m4_insert_linear_accepted_passes_gate_and_is_held() -> None:
    """An accepted insert-linear clears the gate, adds one node, and holds."""
    cave = _cave()
    result = M4.apply(
        cave, OpParams.of(mode="insert-linear", choice="c_left"), random.Random(0)
    )
    candidate = result.candidate
    assert run_gate(candidate).blocked is False
    assert len(_node_ids(candidate)) == len(_node_ids(cave)) + 1
    # The inserted passage node beats and its single choice label are re-guidance.
    assert len(result.reguide) == 2
    assert {item.target for item in result.reguide} == {
        ReguideTarget.NODE,
        ReguideTarget.CHOICE,
    }
    harness = run_acceptance(
        M4,
        cave,
        OpParams.of(mode="insert-linear", choice="c_left"),
        seed=0,
        parent_slug="cave",
    )
    assert harness.discarded_at_stage is None
    assert harness.held is True
    assert harness.reguide_outstanding == 2


@pytest.mark.unit
def test_m4_insert_linear_inserts_an_effect_free_passage_not_a_decision() -> None:
    """The inserted node is a single-choice, effect-free, non-ending passage."""
    cave = _cave()
    result = M4.apply(
        cave, OpParams.of(mode="insert-linear", choice="c_left"), random.Random(0)
    )
    new_ids = _node_ids(result.candidate) - _node_ids(cave)
    assert len(new_ids) == 1
    new_node = _nodes_by_id(result.candidate)[next(iter(new_ids))]
    assert new_node.get("is_ending") is False
    assert len(cast("list[object]", new_node["choices"])) == 1
    assert "on_enter" not in new_node
    body = new_node.get("body")
    assert isinstance(body, str)
    assert "role=passage" in body
    assert _has_state(result.candidate) is False


@pytest.mark.unit
def test_m4_insert_linear_leaves_untouched_nodes_byte_identical() -> None:
    """Only the split node changes (its choice retargets); every other node is equal."""
    cave = _cave()
    result = M4.apply(
        cave, OpParams.of(mode="insert-linear", choice="c_left"), random.Random(0)
    )
    before = _nodes_by_id(cave)
    after = _nodes_by_id(result.candidate)
    # The split node holding c_left is n_start; every other original node is equal.
    for node_id, node in before.items():
        if node_id == "n_start":
            continue
        assert json.dumps(after[node_id], sort_keys=True) == json.dumps(
            node, sort_keys=True
        )


@settings(max_examples=25, deadline=None)
@given(index=st.integers(min_value=0, max_value=max(len(_SMALL_TIER1) - 1, 0)))
@pytest.mark.unit
def test_m4_insert_linear_never_lowers_the_pl20_measure(index: int) -> None:
    """Property: insert-linear only ever RAISES or holds the PL-20 fastest-finish.

    Over real Tier-1 skeletons, a seeded insert-linear never lowers the shortest
    satisfying-path measure (adding a node can only lengthen a path), and any
    accepted output clears the gate (design 12 D5, PL-20 monotonicity).
    """
    if not _SMALL_TIER1:
        pytest.skip("no small Tier-1 catalog parent available")
    _slug, parent = _SMALL_TIER1[index]
    before = _shortest_satisfying_nodes(parent)
    result = M4.apply(parent, OpParams.of(mode="insert-linear"), random.Random(index))
    after = _shortest_satisfying_nodes(result.candidate)
    if before is not None and after is not None:
        assert after >= before
    assert run_gate(result.candidate).blocked is False


@pytest.mark.unit
def test_m4_insert_linear_on_the_shortest_path_strictly_raises_pl20() -> None:
    """Splitting an edge on the unique shortest satisfying path strictly raises PL-20.

    Uses a fixture with a single satisfying ending down one spine, so the split
    edge lies on EVERY shortest satisfying path and the measure rises by one node
    (the general non-decrease is the property test above; this pins the RAISE).
    """
    story = _remove_below_floor_fixture()
    before = _shortest_satisfying_nodes(story)
    result = M4.apply(
        story, OpParams.of(mode="insert-linear", choice="c_p1"), random.Random(0)
    )
    after = _shortest_satisfying_nodes(result.candidate)
    assert before == 6
    assert after == 7


# --- remove-linear ---


@pytest.mark.unit
def test_m4_remove_linear_accepted_passes_gate_and_shrinks() -> None:
    """An accepted remove-linear clears the gate and drops exactly one node."""
    cave = _cave()
    result = M4.apply(
        cave, OpParams.of(mode="remove-linear", node="da_bat2"), random.Random(0)
    )
    candidate = result.candidate
    assert run_gate(candidate).blocked is False
    assert len(_node_ids(candidate)) == len(_node_ids(cave)) - 1
    assert "da_bat2" not in _node_ids(candidate)
    assert _has_state(candidate) is False


@pytest.mark.unit
def test_m4_remove_linear_below_pl20_floor_is_discarded() -> None:
    """A remove-linear dropping the shortest satisfying path below PL-20 is discarded.

    Safety property (design 12 D5): remove-linear is the one M4 sub-operation that
    can lower the fastest-finish, so it is pre-checked against the arc floor.
    """
    story = _remove_below_floor_fixture()
    params = OpParams.of(mode="remove-linear", node="p2")
    report = M4.preconditions(story, params)
    assert report.satisfied is False
    assert any("PL-20" in reason and "below" in reason for reason in report.failures)
    rng = random.Random(0)
    with pytest.raises(ValidationError):
        M4.apply(story, params, rng)


@pytest.mark.unit
def test_m4_remove_linear_rejects_an_ending_node() -> None:
    """remove-linear refuses an ending node (it splices a passage, not a terminal)."""
    cave = _cave()
    report = M4.preconditions(
        cave, OpParams.of(mode="remove-linear", node="la_retreat_pool")
    )
    assert report.satisfied is False
    assert any("ending" in reason for reason in report.failures)


@pytest.mark.unit
def test_m4_remove_linear_rejects_the_start_node() -> None:
    """remove-linear refuses the start node (re-rooting is out of scope)."""
    # A fixture whose start is a single-choice passage isolates the start-node
    # guard from the exactly-one-choice guard.
    story: dict[str, object] = {
        "start_node": "start",
        "metadata": {
            "age_band": "3-5",
            "tier": 1,
            "topology": "time_cave",
            "ending_count": 1,
        },
        "variables": [],
        "nodes": [
            {
                "id": "start",
                "body": "<<FILL role=setup words=40 beats='x'>>",
                "is_ending": False,
                "choices": [{"id": "c_go", "label": "Go", "target": "mid"}],
            },
            {
                "id": "mid",
                "body": "<<FILL role=rising words=40 beats='x'>>",
                "is_ending": False,
                "choices": [{"id": "c_on", "label": "On", "target": "e"}],
            },
            {
                "id": "e",
                "body": "x",
                "is_ending": True,
                "ending": {
                    "id": "ee",
                    "kind": "success",
                    "valence": "positive",
                    "title": "W",
                },
            },
        ],
    }
    report = M4.preconditions(story, OpParams.of(mode="remove-linear", node="start"))
    assert report.satisfied is False
    assert any("start_node" in reason for reason in report.failures)


# --- insert-decision: reconvergence ---


@pytest.mark.unit
def test_m4_reconvergence_changing_topology_passes_the_cell_stage() -> None:
    """A time_cave -> branch_and_bottleneck reconvergence now clears the cell stage.

    Component-4 (design 4.8, OQ-4): topology is no longer a cell key. An
    insert-decision reconvergence on the-cave-of-echoes (8-11, time_cave) adds an
    in-edge, so the mutant graph is no longer time_cave; ``resync_metadata`` re-
    declares the admissible, band-legal ``branch_and_bottleneck`` (in the 8-11
    row), which PL-18 re-proves at the gate. Before the fix this mutant was
    discarded at stage 2 as spurious "cell drift" and was therefore only promotable
    on an already-reconverging (branch_and_bottleneck) parent; now it reaches the
    cell stage and is held on its re-guidance. No safety assertion is weakened: the
    gate (PL-18) and the band-row check in ``redeclare_topology`` still enforce
    topology honesty.
    """
    cave = _cave()
    params = OpParams.of(
        mode="insert-decision",
        choice="c_left",
        variant="reconvergence",
        target="la_fork",
    )
    candidate = M4.apply(cave, params, random.Random(0)).candidate
    assert cave["metadata"]["topology"] == "time_cave"  # pyright: ignore[reportIndexIssue]
    assert candidate["metadata"]["topology"] == "branch_and_bottleneck"  # pyright: ignore[reportIndexIssue]
    result = run_acceptance(M4, cave, params, seed=0, parent_slug="the-cave-of-echoes")
    # Reaches the cell stage (not cell-drift discarded) and is held on re-guidance.
    assert result.discarded_at_stage is None
    assert result.held is True
    cell_stage = next(o for o in result.stages if o.stage is Stage.CELL)
    assert cell_stage.passed is True


@pytest.mark.unit
def test_m4_insert_decision_reconvergence_raises_in_degree_and_passes_gate() -> None:
    """A reconvergence lifts the target's in-degree and clears the gate.

    Runs on a branch_and_bottleneck host so the added reconvergence preserves the
    declared topology; ``e_chaos`` gains an in-edge from the new decision. (A
    reconvergence that CHANGES topology within the band row is also accepted since
    the component-4 topology-cell fix; see
    test_m4_reconvergence_changing_topology_passes_the_cell_stage.)
    """
    robot = _robot()
    params = OpParams.of(
        mode="insert-decision",
        choice="c_m_mate",
        variant="reconvergence",
        target="e_chaos",
    )
    result = M4.apply(robot, params, random.Random(0))
    assert run_gate(result.candidate).blocked is False
    assert _in_degree(result.candidate, "e_chaos") == _in_degree(robot, "e_chaos") + 1
    assert _has_state(result.candidate) is False


@pytest.mark.unit
def test_m4_insert_decision_reconvergence_to_an_ancestor_is_rejected() -> None:
    """A reconvergence edge that would close a cycle on an acyclic parent is rejected."""
    robot = _robot()
    # start_node is an ancestor of every choice source, so reconverging to it
    # would create a cycle.
    params = OpParams.of(
        mode="insert-decision",
        choice="c_m_mate",
        variant="reconvergence",
        target=cast("str", robot["start_node"]),
    )
    report = M4.preconditions(robot, params)
    assert report.satisfied is False
    assert any("cycle" in reason for reason in report.failures)


@pytest.mark.unit
def test_m4_insert_decision_reconvergence_past_the_ceiling_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reconvergence past a configured band reconvergence ceiling is rejected.

    No band configures a ceiling in the shipped catalog, so the check is exercised
    by pinning the 8-11 ceiling to the host's current reconvergence count; adding
    one more then exceeds it.
    """
    robot = _robot()
    graph = _graph(robot)
    current = sum(1 for node in graph if graph.in_degree(node) >= 2)
    original = band_profile.profile_for("8-11")
    assert original is not None
    capped = replace(original, reconvergence_ceiling=current)

    def _capped_profile(band: str) -> band_profile.BandProfile | None:
        return capped if band == "8-11" else band_profile.profile_for(band)

    # M4 binds ``profile_for`` at import, so the ceiling is pinned on the operator
    # module's reference (patching band_profile.profile_for would not be seen).
    monkeypatch.setattr(m4_ops, "profile_for", _capped_profile)
    params = OpParams.of(
        mode="insert-decision",
        choice="c_m_mate",
        variant="reconvergence",
        target="e_chaos",
    )
    report = M4.preconditions(robot, params)
    assert report.satisfied is False
    assert any("reconvergence_ceiling" in reason for reason in report.failures)


# --- insert-decision: micro-stub ---


@pytest.mark.unit
def test_m4_insert_decision_micro_stub_grows_the_ending_multiset_by_one() -> None:
    """A micro-stub grows the ending count by one with a band-legal ending.

    Design 12 D5: PL-15 (band-forbidden kinds) and PL-17 (floors) are re-checked;
    the discovery/neutral micro-stub kind is legal for every band, so the gate
    does not block.
    """
    cave = _cave()
    result = M4.apply(
        cave,
        OpParams.of(mode="insert-decision", choice="c_bat", variant="micro-stub"),
        random.Random(0),
    )
    candidate = result.candidate
    assert _ending_count(candidate) == _ending_count(cave) + 1
    candidate_meta = cast("dict[str, object]", candidate["metadata"])
    assert candidate_meta["ending_count"] == _ending_count(candidate)
    # 8-11 forbids `death`; the micro-stub adds only a band-legal `discovery`.
    added_kinds = _ending_kinds(candidate) - _ending_kinds(cave)
    assert added_kinds <= {"discovery"}
    assert run_gate(candidate).blocked is False
    # A micro-stub emits five re-guidance items (decision beats, two choice
    # labels, the stub node beats, and the stub ending title).
    assert len(result.reguide) == 5


# --- Safety, determinism, and the harness ---


@pytest.mark.unit
@pytest.mark.parametrize(
    "params",
    [
        OpParams.of(mode="insert-linear", choice="c_left"),
        OpParams.of(mode="remove-linear", node="da_bat2"),
        OpParams.of(mode="insert-decision", choice="c_bat", variant="micro-stub"),
    ],
    ids=["insert-linear", "remove-linear", "micro-stub"],
)
def test_m4_no_output_introduces_state(params: OpParams) -> None:
    """Safety property (design 12 D5): no M4 output adds a variable/effect/condition."""
    cave = _cave()
    result = M4.apply(cave, params, random.Random(0))
    assert _has_state(result.candidate) is False
    candidate_meta = cast("dict[str, object]", result.candidate["metadata"])
    assert candidate_meta["tier"] == 1


@pytest.mark.unit
def test_m4_is_deterministic_per_params_and_per_seed() -> None:
    """Explicit and rng-selected M4 candidates are byte-reproducible."""
    cave = _cave()
    # Explicit params: seed is irrelevant, output is byte-identical.
    micro = OpParams.of(mode="insert-decision", choice="c_bat", variant="micro-stub")
    a = M4.apply(cave, micro, random.Random(0)).candidate
    b = M4.apply(cave, micro, random.Random(999)).candidate
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    # rng selection: the same seed reproduces the same candidate.
    c = M4.apply(cave, OpParams.of(mode="insert-linear"), random.Random(4)).candidate
    d = M4.apply(cave, OpParams.of(mode="insert-linear"), random.Random(4)).candidate
    assert json.dumps(c, sort_keys=True) == json.dumps(d, sort_keys=True)
    e = M4.apply(cave, OpParams.of(mode="remove-linear"), random.Random(2)).candidate
    f = M4.apply(cave, OpParams.of(mode="remove-linear"), random.Random(2)).candidate
    assert json.dumps(e, sort_keys=True) == json.dumps(f, sort_keys=True)


@pytest.mark.unit
def test_m4_harness_never_promotes_a_discarded_candidate() -> None:
    """The unchanged harness discards a below-floor micro-stub and never promotes it."""
    cave = _cave()
    result = run_acceptance(
        M4,
        cave,
        OpParams.of(mode="insert-decision", choice="c_left", variant="micro-stub"),
        seed=0,
        parent_slug="cave",
    )
    assert result.promotable is False
    assert result.discarded_at_stage is not None


@pytest.mark.unit
def test_m4_rejects_a_tier2_parent() -> None:
    """M4 (D5) refuses a Tier-2 parent (variables present)."""
    cave = _cave()
    cast("dict[str, object]", cave["metadata"])["tier"] = 2
    cave["variables"] = [{"name": "x", "type": "int", "initial": 0}]
    report = M4.preconditions(cave, OpParams.of(mode="insert-linear", choice="c_left"))
    assert report.satisfied is False
    assert any("Tier-1" in reason for reason in report.failures)


@pytest.mark.unit
def test_m4_operator_class_is_constructible() -> None:
    """The operator class constructs standalone (parity with the registered singleton)."""
    op = M4VaryDecisions()
    assert op.op_id == M4_OP_ID
