"""Deterministic topology classifier for story choice graphs.

Returns the SET of admissible Ashwell topologies for a directed choice graph.
PL-18 passes when the authored topology is in this set, so genuinely ambiguous
shapes are not falsely rejected. Feature thresholds are calibration points.
"""

from __future__ import annotations

import networkx as nx

from cyo_adventure.storybook.models import Topology


def admissible_topologies(graph: nx.DiGraph[str]) -> set[Topology]:
    """Return the topologies consistent with a choice graph's shape.

    Args:
        graph: The directed choice graph (nodes are node ids, edges are choices).

    Returns:
        set[Topology]: Every topology the graph could legitimately be labelled.
            A cyclic graph is exactly ``{LOOP_AND_GROW}``. An acyclic graph is
            labelled from its reconvergence (in-degree >= 2) and branching.
    """
    if not nx.is_directed_acyclic_graph(graph):
        return {Topology.LOOP_AND_GROW}

    reconverging = sum(1 for n in graph if graph.in_degree(n) >= 2)
    branching = sum(1 for n in graph if graph.out_degree(n) >= 2)
    admissible: set[Topology] = set()

    if reconverging == 0:
        # A pure branching tree: many leaves, no merges.
        admissible.add(Topology.TIME_CAVE)
    else:
        # Reconvergence means bottlenecks where paths merge.
        admissible.add(Topology.BRANCH_AND_BOTTLENECK)

    if branching <= 1:
        # A near-linear spine reads as a gauntlet regardless of merges.
        admissible.add(Topology.GAUNTLET)

    return admissible
