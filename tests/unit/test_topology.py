"""Unit tests for the deterministic topology classifier."""

import networkx as nx

from cyo_adventure.storybook.models import Topology
from cyo_adventure.validator.topology import admissible_topologies


def _path(n: int) -> nx.DiGraph:
    g: nx.DiGraph = nx.DiGraph()
    for i in range(n - 1):
        g.add_edge(f"n{i}", f"n{i + 1}")
    return g


def test_tree_with_no_reconvergence_is_time_cave():
    g: nx.DiGraph = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("a", "c"), ("b", "d"), ("b", "e")])
    assert Topology.TIME_CAVE in admissible_topologies(g)
    assert Topology.BRANCH_AND_BOTTLENECK not in admissible_topologies(g)


def test_reconverging_graph_is_branch_and_bottleneck():
    g: nx.DiGraph = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])  # d reconverges
    assert Topology.BRANCH_AND_BOTTLENECK in admissible_topologies(g)


def test_cyclic_graph_is_loop_and_grow():
    g: nx.DiGraph = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("b", "a")])
    assert admissible_topologies(g) == {Topology.LOOP_AND_GROW}


def test_linear_spine_is_gauntlet():
    assert Topology.GAUNTLET in admissible_topologies(_path(5))


def test_multi_branch_reconverging_graph_includes_gauntlet():
    # A classic gauntlet: multiple decision nodes whose branches all feed back
    # into the main spine. branching > 1 and reconverging > 0, so the old
    # branching <= 1 threshold would have excluded GAUNTLET incorrectly.
    g: nx.DiGraph = nx.DiGraph()
    # spine: a -> b -> c -> d (ending)
    # each spine node has a side-exit that reconverges at the next spine node
    g.add_edges_from(
        [
            ("a", "b"),
            ("a", "x1"),  # decision at a
            ("x1", "b"),  # side exit reconverges at b
            ("b", "c"),
            ("b", "x2"),  # decision at b
            ("x2", "c"),  # side exit reconverges at c
            ("c", "d"),
        ]
    )
    result = admissible_topologies(g)
    assert Topology.GAUNTLET in result
    assert Topology.BRANCH_AND_BOTTLENECK in result
