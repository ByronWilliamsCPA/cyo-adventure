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


def test_cyclic_graph_is_loop_and_grow_or_open_map():
    """A back-edge admits both loop_and_grow and open_map (both need loops)."""
    g: nx.DiGraph = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("b", "a")])
    assert admissible_topologies(g) == {Topology.LOOP_AND_GROW, Topology.OPEN_MAP}


def test_open_map_hub_is_admissible():
    """A revisitable hub (return edges to a central node) admits open_map."""
    g: nx.DiGraph = nx.DiGraph()
    # hub 'h' reaches three rooms; each room returns to the hub (loop/return).
    g.add_edges_from(
        [
            ("h", "r1"),
            ("h", "r2"),
            ("h", "r3"),
            ("r1", "h"),
            ("r2", "h"),
            ("r3", "h"),
            ("h", "end"),
        ]
    )
    result = admissible_topologies(g)
    assert Topology.OPEN_MAP in result
    assert Topology.LOOP_AND_GROW in result


def test_branching_tree_admits_sorting_hat():
    """A branching acyclic tree with no reconvergence admits sorting_hat."""
    g: nx.DiGraph = nx.DiGraph()
    # Early sort at 'a' into two parallel tracks that never reconverge.
    g.add_edges_from([("a", "b"), ("a", "c"), ("b", "d"), ("b", "e"), ("c", "f")])
    result = admissible_topologies(g)
    assert Topology.SORTING_HAT in result
    assert Topology.TIME_CAVE in result


def test_linear_spine_excludes_sorting_hat():
    """A pure linear spine has no sort branch, so sorting_hat is inadmissible."""
    result = admissible_topologies(_path(5))
    assert Topology.SORTING_HAT not in result
    assert Topology.GAUNTLET in result


def test_reconverging_graph_excludes_sorting_hat():
    """Reconvergence is a cross-track bottleneck, which sorting_hat forbids."""
    g: nx.DiGraph = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])  # d reconverges
    assert Topology.SORTING_HAT not in admissible_topologies(g)


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
