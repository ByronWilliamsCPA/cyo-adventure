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
            A cyclic graph is ``{LOOP_AND_GROW, OPEN_MAP}``: both need back-edges
            (loop growth vs a revisitable hub), and the two are not distinguished
            structurally here. An acyclic graph with no reconvergence is
            ``{TIME_CAVE}`` plus ``{GAUNTLET}`` when it is a pure linear spine, or
            plus ``{SORTING_HAT}`` when it branches (a sort into parallel,
            non-reconverging tracks). An acyclic graph with reconvergence is
            ``{BRANCH_AND_BOTTLENECK, GAUNTLET}`` because a gauntlet IS a
            reconverging structure where branches feed back into the spine;
            ``SORTING_HAT`` is excluded there because it forbids a cross-track
            bottleneck.
    """
    if not nx.is_directed_acyclic_graph(graph):
        # A back-edge is the defining primitive of both a loop_and_grow (state
        # growth per loop) and an open_map (loop/return to a revisitable hub).
        # The classifier does not distinguish the two structurally, so both are
        # admissible for any cyclic graph.
        return {Topology.LOOP_AND_GROW, Topology.OPEN_MAP}

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
            # A branching acyclic tree with no cross-track bottleneck is exactly
            # the sorting_hat shape: an early sort into parallel tracks that never
            # reconverge. It coexists with time_cave (both are branching trees).
            admissible.add(Topology.SORTING_HAT)
    else:
        # Reconvergence means bottlenecks where paths merge. A gauntlet IS a
        # reconverging graph (side branches reconnect to the spine), so both
        # labels are admissible when the graph has reconvergence. sorting_hat is
        # NOT admissible here: it forbids a cross-track bottleneck.
        admissible.add(Topology.BRANCH_AND_BOTTLENECK)
        admissible.add(Topology.GAUNTLET)

    return admissible
