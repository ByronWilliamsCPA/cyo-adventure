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
        # A gauntlet is admissible with or without branching. ADR-011 section 7
        # builds it from "linear spine, branch-to-fail, terminal (many),
        # restart-on-fail" and pointedly does NOT list `bottleneck`, so the
        # deadly gamebook gauntlet is a spine whose side branches END rather than
        # rejoin. This used to admit GAUNTLET only for a graph with zero
        # branching or with reconvergence, so the shape the ADR itself specifies
        # classified as `sorting_hat`/`time_cave` and drew a blocking PL-18 error
        # at 13-16 gamebook: only Ashwell's FRIENDLY gauntlet was expressible and
        # the deadly one was not (`UW-C284`).
        admissible.add(Topology.GAUNTLET)
        if branching > 0:
            # A branching acyclic tree with no cross-track bottleneck is also the
            # sorting_hat shape: an early sort into parallel tracks that never
            # reconverge. It coexists with time_cave and gauntlet, which is fine:
            # this function answers what a shape COULD be called, and PL-29's
            # per-band rows narrow that to what a band may declare.
            admissible.add(Topology.SORTING_HAT)
    else:
        # Reconvergence means bottlenecks where paths merge. A gauntlet IS a
        # reconverging graph (side branches reconnect to the spine), so both
        # labels are admissible when the graph has reconvergence. sorting_hat is
        # NOT admissible here: it forbids a cross-track bottleneck.
        admissible.add(Topology.BRANCH_AND_BOTTLENECK)
        admissible.add(Topology.GAUNTLET)

    return admissible


# ADR-011 section 7: which topologies each age band may declare. This is a
# product restriction on top of `admissible_topologies`, which only answers
# what a graph's SHAPE could legitimately be called. The two are independent
# and both must hold: `branch_and_bottleneck` is a perfectly well-formed shape
# that a 5-8 book may not use.
#
# #CRITICAL: data-integrity: this table lived only in `mutation/identity.py`,
# so the offline mutation core enforced it and the authoring gate did not.
# Three skeletons drafted 2026-08-16 declared `branch_and_bottleneck` at 3-5
# and 5-8, passed `check_skeleton --strict` clean, and were rejected only when
# the mutation operators ran over them. A rule enforced in the layer authors do
# not run is not enforced. Kept here rather than in `policy.py` because
# `validator/topology.py` is already the shared import for both PL-18 and
# `mutation/identity.py`, so one definition serves both without the offline
# core becoming a dependency of the gate.
# #VERIFY: test_policy.py::test_pl29_accepts_every_committed_skeleton asserts
# every committed skeleton satisfies its row, and
# test_policy.py::test_pl29_rejects_a_topology_the_band_forbids covers the rule.
BAND_TOPOLOGIES: dict[str, frozenset[Topology]] = {
    "3-5": frozenset({Topology.LOOP_AND_GROW, Topology.TIME_CAVE}),
    "5-8": frozenset({Topology.TIME_CAVE, Topology.LOOP_AND_GROW, Topology.OPEN_MAP}),
    "8-11": frozenset(
        {
            Topology.BRANCH_AND_BOTTLENECK,
            Topology.TIME_CAVE,
            Topology.OPEN_MAP,
            Topology.SORTING_HAT,
        }
    ),
    "10-13": frozenset(
        {
            Topology.BRANCH_AND_BOTTLENECK,
            Topology.OPEN_MAP,
            Topology.SORTING_HAT,
        }
    ),
    "13-16": frozenset(
        {
            Topology.BRANCH_AND_BOTTLENECK,
            Topology.GAUNTLET,
            Topology.OPEN_MAP,
            Topology.SORTING_HAT,
        }
    ),
    "16+": frozenset(
        {
            Topology.BRANCH_AND_BOTTLENECK,
            Topology.GAUNTLET,
            Topology.OPEN_MAP,
            Topology.SORTING_HAT,
        }
    ),
}
