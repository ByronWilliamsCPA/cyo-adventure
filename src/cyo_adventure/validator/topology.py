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
            A cyclic graph is exactly ``{LOOP_AND_GROW}``. An acyclic graph
            with no reconvergence is ``{TIME_CAVE}`` (plus ``{GAUNTLET}`` when
            it is a pure linear spine with no branching). An acyclic graph with
            reconvergence is ``{BRANCH_AND_BOTTLENECK, GAUNTLET}`` because a
            gauntlet IS a reconverging structure where branches feed back into
            the spine.
    """
    if not nx.is_directed_acyclic_graph(graph):
        return {Topology.LOOP_AND_GROW}

    reconverging = sum(1 for n in graph if graph.in_degree(n) >= 2)
    branching = sum(1 for n in graph if graph.out_degree(n) >= 2)
    admissible: set[Topology] = set()

    if reconverging == 0:
        # A pure branching tree: many leaves, no merges.
        admissible.add(Topology.TIME_CAVE)
        if branching == 0:
            # A pure linear spine with no choices is the canonical gauntlet shape.
            admissible.add(Topology.GAUNTLET)
    else:
        # Reconvergence means bottlenecks where paths merge. A gauntlet IS a
        # reconverging graph (side branches reconnect to the spine), so both
        # labels are admissible when the graph has reconvergence.
        admissible.add(Topology.BRANCH_AND_BOTTLENECK)
        admissible.add(Topology.GAUNTLET)

    return admissible
