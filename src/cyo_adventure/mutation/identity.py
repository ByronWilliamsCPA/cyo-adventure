"""Deterministic id renaming and metadata resync for mutated skeletons.

WS-5 D1 (design section 4.1). Two concerns live here:

- **Id renaming** for a grafted or duplicated region, under the prefix scheme
  ``m<k>_<old_id>`` for node, choice, and ending ids, collision-checked against
  the host's full id namespace so a mutant can never emit a duplicate id.
- **Metadata resync** so a structural mutation leaves the reader-facing
  metadata self-consistent: ``ending_count`` recomputed from the node list (the
  schema's ``_check_ending_count`` rejects a mismatch), ``estimated_minutes``
  recomputed from the ADR-011 words-and-pace anchors, ``tier`` recomputed from
  variable presence, and ``topology`` re-declared per design section 4.8.

Pure module: standard library, ``networkx`` (as the validator's topology
classifier already uses), and lower project layers only. It imports nothing
from ``db``, ``generation`` (beyond the allowed pure surfaces), or ``network``,
mirroring the layering discipline of ``storybook/theme_contract.py``.
"""

from __future__ import annotations

import copy
import heapq
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import networkx as nx

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation._raw import (
    choices_of as _choices_of,
)
from cyo_adventure.mutation._raw import (
    nodes_of as _nodes_of,
)
from cyo_adventure.mutation._raw import (
    str_field as _str_field,
)
from cyo_adventure.mutation.subtree import adjacency, node_ids
from cyo_adventure.storybook.models import Topology
from cyo_adventure.validator.topology import admissible_topologies

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# The satisfying-ending kinds (a full-arc completion), per ADR-011 section 4's
# fastest-finish clock; used to target the estimated-minutes computation.
_SATISFYING_KINDS = frozenset({"success", "completion"})

# Matches the ``words=<int>`` field of a ``<<FILL ...>>`` directive, so a shell
# node's word budget is read from its directive rather than its placeholder
# prose.
_FILL_WORDS_RE = re.compile(r"words\s*=\s*(\d+)")

# #ASSUME: data-integrity: reading-pace anchors (words per minute) are sourced
# from ADR-011 section 5 ("Reading-pace anchors ... 3-5 ~100 wpm (read aloud),
# 5-8 ~90, 8-11 ~120, 10-13 ~150, 13-16 ~190, 16+ ~220"). There is no
# words-per-minute table in code today (band_profile.py carries a
# words-per-NODE table, not a pace table), so the anchors are declared here as
# a single module-level source. If ADR-011 retunes these numbers, this table
# must follow (design risk 6); single-sourcing from band_profile.py is the
# preferred follow-up if a pace table is ever added there.
# #VERIFY: tests/unit/test_mutation_identity.py pins every band's anchor and
# asserts resync of every catalog skeleton yields estimated_minutes >= 1.
_READING_PACE_WPM: dict[str, int] = {
    "3-5": 100,
    "5-8": 90,
    "8-11": 120,
    "10-13": 150,
    "13-16": 190,
    "16+": 220,
}

# The pace used when a story declares a band with no configured anchor; the
# 8-11 core-research value, the same anchor the ADR uses as its baseline.
_DEFAULT_PACE_WPM = 120

# #ASSUME: data-integrity: the per-band admissible-topology rows are sourced
# from ADR-011 section 7's "Per-band topology and flow allowances" table,
# reconciled with the gate-accepted production catalog where the two disagree.
# There is no band-to-topology allowance table in code today (validator's
# admissible_topologies classifies a graph shape, it does not gate by band),
# so the rows are declared here as a single module-level source. Two
# reconciliations: (1) the ADR section 7 row for 16+ lists only
# branch_and_bottleneck/gauntlet/sorting_hat, but the shipped 16+ catalog
# includes gate-verified open_map skeletons, so open_map is admitted for 16+
# here (rejecting a valid existing tree would violate the discard-only rule);
# (2) the "sorting_hat (Medium/Long only)" length caveat is not modelled at
# this layer, because a mutant inherits its parent cell verbatim in v1 (design
# OQ-4), so sorting_hat only appears in a mutant whose parent already declared
# it, and the parent's declared topology is preserved whenever it stays
# admissible. The 16+ open_map gap is flagged for the reviewer to fold back
# into ADR-011 section 7.
# #VERIFY: tests/unit/test_mutation_identity.py asserts every catalog
# skeleton's own declared topology is preserved by redeclare_topology, and that
# redeclare output is always in both the band row and
# admissible_topologies(graph).
_BAND_TOPOLOGIES: dict[str, frozenset[Topology]] = {
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
            Topology.SORTING_HAT,
            Topology.OPEN_MAP,
        }
    ),
    "16+": frozenset(
        {
            Topology.BRANCH_AND_BOTTLENECK,
            Topology.GAUNTLET,
            Topology.SORTING_HAT,
            Topology.OPEN_MAP,
        }
    ),
}

# A fixed, deterministic preference order for choosing a replacement topology
# when the parent's declared value is no longer admissible. Follows the
# ``Topology`` enum declaration order so the pick is stable and reproducible.
_TOPOLOGY_PREFERENCE: tuple[Topology, ...] = tuple(Topology)


def _ending_of(node: Mapping[str, object]) -> Mapping[str, object] | None:
    """Return a node's ending block, or None when absent or malformed."""
    ending = node.get("ending")
    return cast("Mapping[str, object]", ending) if isinstance(ending, dict) else None


def _metadata_of(story: Mapping[str, object]) -> Mapping[str, object]:
    """Return the story's metadata block.

    Args:
        story: The raw story document.

    Returns:
        Mapping[str, object]: The metadata block.

    Raises:
        ValidationError: If the story carries no metadata object.
    """
    meta = story.get("metadata")
    if not isinstance(meta, dict):
        msg = "story has no metadata object to resync"
        raise ValidationError(msg, field="metadata", value=None)
    return cast("Mapping[str, object]", meta)


def host_id_namespace(story: Mapping[str, object]) -> set[str]:
    """Return every id the host story uses, across all three id namespaces.

    Args:
        story: The raw host story document.

    Returns:
        set[str]: The union of every node id, choice id, and ending id. A
            renamed region's ids are checked for disjointness against this set,
            the safe (strict) direction: no grafted id may equal any existing
            host id.
    """
    namespace: set[str] = set()
    for node in _nodes_of(story):
        node_id = _str_field(node, "id")
        if node_id is not None:
            namespace.add(node_id)
        for choice in _choices_of(node):
            choice_id = _str_field(choice, "id")
            if choice_id is not None:
                namespace.add(choice_id)
        ending = _ending_of(node)
        if ending is not None:
            ending_id = _str_field(ending, "id")
            if ending_id is not None:
                namespace.add(ending_id)
    return namespace


def _prefixed(old_id: str, k: int) -> str:
    """Return the ``m<k>_<old_id>`` renamed id."""
    return f"m{k}_{old_id}"


@dataclass(slots=True)
class _RenameState:
    """Mutable bookkeeping shared across one region-rename pass.

    Attributes:
        k: The mutation index used in the ``m<k>_`` prefix.
        host_namespace: Every id already used by the host.
        node_id_map: The ``old_node_id -> new_node_id`` map.
        region_node_ids: The old node ids that belong to the region (so a
            choice target can be recognized as in-region and rewritten).
        seen_nodes: New node ids reserved so far.
        seen_choices: New choice ids reserved so far.
        seen_endings: New ending ids reserved so far.
    """

    k: int
    host_namespace: set[str]
    node_id_map: dict[str, str]
    region_node_ids: set[str]
    seen_nodes: set[str] = field(default_factory=set)
    seen_choices: set[str] = field(default_factory=set)
    seen_endings: set[str] = field(default_factory=set)


def rename_region(
    region_nodes: Iterable[Mapping[str, object]],
    k: int,
    host_namespace: set[str],
) -> tuple[list[dict[str, object]], dict[str, str]]:
    """Deterministically rename every id in a region and rewire its targets.

    Node, choice, and ending ids are prefixed ``m<k>_``; choice targets that
    point within the region are rewritten to the renamed node id, while targets
    that leave the region (a reconvergence edge to the host) are preserved. The
    result is a fresh set of node dicts; the input is never mutated.

    Args:
        region_nodes: The node dicts of the region to rename, in graft order.
        k: The non-negative mutation index used in the ``m<k>_`` prefix.
        host_namespace: Every id already used by the host (see
            :func:`host_id_namespace`); no renamed id may collide with it.

    Returns:
        tuple[list[dict[str, object]], dict[str, str]]: The renamed node dicts,
            and the ``old_node_id -> new_node_id`` map used to rewire the graft
            edge into the region.

    Raises:
        ValidationError: If ``k`` is negative; if a region node has no id; or if
            a renamed id collides with the host namespace or with another
            renamed id in the same namespace (node/choice/ending). Collisions
            are the safety failure this function exists to prevent.
    """
    # #CRITICAL: data-integrity: a duplicate id in the emitted document would
    # let one graph position masquerade as another (a mis-wired choice target,
    # a shadowed ending). Renamed ids are checked against the host's full
    # namespace AND for intra-region uniqueness before anything is returned, so
    # the constructive path can never emit a collision; the schema's
    # _check_unique_ids is the fail-closed backstop (design CR-3).
    # #VERIFY: tests/unit/test_mutation_identity.py proves, over the catalog,
    # that renamed ids are disjoint from the host namespace and that a seeded
    # host-id collision raises.
    if k < 0:
        msg = f"mutation index k must be non-negative, got {k}"
        raise ValidationError(msg, field="k", value=k)

    nodes = list(region_nodes)
    node_id_map: dict[str, str] = {}
    for node in nodes:
        old_node_id = _str_field(node, "id")
        if old_node_id is None:
            msg = "cannot rename a region node that has no id"
            raise ValidationError(msg, field="id", value=None)
        node_id_map[old_node_id] = _prefixed(old_node_id, k)

    state = _RenameState(
        k=k,
        host_namespace=host_namespace,
        node_id_map=node_id_map,
        region_node_ids=set(node_id_map),
    )
    renamed: list[dict[str, object]] = []
    for node in nodes:
        fresh = copy.deepcopy(dict(node))
        old_node_id = cast("str", _str_field(node, "id"))
        new_node_id = node_id_map[old_node_id]
        _reserve(new_node_id, host_namespace, state.seen_nodes, "node id")
        fresh["id"] = new_node_id
        _rename_choices(fresh, state)
        _rename_ending(fresh, state)
        renamed.append(fresh)

    return renamed, node_id_map


def _reserve(new_id: str, host_namespace: set[str], seen: set[str], label: str) -> None:
    """Reserve a freshly renamed id or raise on a collision.

    Args:
        new_id: The candidate renamed id.
        host_namespace: Every id already used by the host.
        seen: The renamed ids already reserved in this id's namespace.
        label: A human label for the namespace (for the error message).

    Raises:
        ValidationError: If ``new_id`` collides with the host namespace or with
            an already-reserved renamed id.
    """
    if new_id in host_namespace:
        msg = f"renamed {label} '{new_id}' collides with an existing host id"
        raise ValidationError(msg, field=label, value=new_id)
    if new_id in seen:
        msg = f"renamed {label} '{new_id}' is not unique within the region"
        raise ValidationError(msg, field=label, value=new_id)
    seen.add(new_id)


def _rename_choices(node: dict[str, object], state: _RenameState) -> None:
    """Rename a node's choice ids and rewire in-region targets, in place."""
    raw = node.get("choices")
    if not isinstance(raw, list):
        return
    for item in cast("list[object]", raw):
        if not isinstance(item, dict):
            continue
        # dict[str, object] has no forward reference to defer, so there is no
        # runtime cost to not quoting it in these cast() calls (see
        # review_surface.py for the same pattern); left unquoted here so the
        # type expression is not a duplicated string literal (S1192) across
        # the module.
        choice = cast(dict[str, object], item)  # noqa: TC006
        old_choice_id = _str_field(choice, "id")
        if old_choice_id is not None:
            new_choice_id = _prefixed(old_choice_id, state.k)
            _reserve(
                new_choice_id, state.host_namespace, state.seen_choices, "choice id"
            )
            choice["id"] = new_choice_id
        target = _str_field(choice, "target")
        if target is not None and target in state.region_node_ids:
            choice["target"] = state.node_id_map[target]


def _rename_ending(node: dict[str, object], state: _RenameState) -> None:
    """Rename a node's ending id, in place, when it carries one."""
    ending = node.get("ending")
    if not isinstance(ending, dict):
        return
    ending_dict = cast(dict[str, object], ending)  # noqa: TC006
    old_ending_id = _str_field(ending_dict, "id")
    if old_ending_id is not None:
        new_ending_id = _prefixed(old_ending_id, state.k)
        _reserve(new_ending_id, state.host_namespace, state.seen_endings, "ending id")
        ending_dict["id"] = new_ending_id


def recompute_ending_count(story: Mapping[str, object]) -> int:
    """Return the number of ending nodes in the story.

    Matches the schema's ``_check_ending_count`` rule exactly (it counts nodes
    whose ``is_ending`` is truthy), so a resync using this value never produces
    a metadata/ending mismatch.

    Args:
        story: The raw story document.

    Returns:
        int: The count of ending nodes.
    """
    return sum(1 for node in _nodes_of(story) if node.get("is_ending") is True)


def recompute_tier(story: Mapping[str, object]) -> int:
    """Return the tier implied by the story's variable presence.

    Args:
        story: The raw story document.

    Returns:
        int: ``2`` when the story declares one or more variables (stateful),
            ``1`` otherwise. This matches the schema's tier rule, which forbids
            a Tier-1 story from declaring variables.
    """
    variables = story.get("variables")
    if isinstance(variables, list):
        return 2 if variables else 1
    return 1


def _word_estimate(node: Mapping[str, object]) -> int:
    """Return a node's word budget from its FILL directive, or its body length."""
    body = node.get("body")
    if not isinstance(body, str):
        return 0
    match = _FILL_WORDS_RE.search(body)
    if match is not None:
        return int(match.group(1))
    return len(body.split())


def _ending_target_ids(story: Mapping[str, object]) -> tuple[set[str], set[str]]:
    """Return ``(satisfying_ids, any_ending_ids)`` for the fastest-finish target.

    Args:
        story: The raw story document.

    Returns:
        tuple[set[str], set[str]]: The ids of satisfying (success/completion)
            ending nodes, and the ids of all ending nodes.
    """
    satisfying: set[str] = set()
    any_ending: set[str] = set()
    for node in _nodes_of(story):
        if node.get("is_ending") is not True:
            continue
        node_id = _str_field(node, "id")
        if node_id is None:
            continue
        any_ending.add(node_id)
        ending = _ending_of(node)
        kind = _str_field(ending, "kind") if ending is not None else None
        if kind in _SATISFYING_KINDS:
            satisfying.add(node_id)
    return satisfying, any_ending


def _fastest_finish_words(story: Mapping[str, object]) -> int:
    """Return the least node-word sum on a shortest path to a good ending.

    Uses a node-weighted uniform-cost (Dijkstra) search from the start node,
    where each node's weight is its :func:`_word_estimate`. The target set is
    the satisfying endings; it falls back to any ending, then to the start
    node's own words, so a degenerate in-progress candidate still yields a
    finite estimate.

    Args:
        story: The raw story document.

    Returns:
        int: The minimum path word sum to the nearest target, or the start
            node's words when no target is reachable.
    """
    weights = {
        node_id: _word_estimate(node)
        for node in _nodes_of(story)
        if (node_id := _str_field(node, "id")) is not None
    }
    start = _str_field(story, "start_node")
    if start is None or start not in weights:
        return 0
    graph = adjacency(story)
    satisfying, any_ending = _ending_target_ids(story)
    targets = satisfying or any_ending
    if not targets:
        return weights[start]

    settled: set[str] = set()
    frontier: list[tuple[int, str]] = [(weights[start], start)]
    while frontier:
        distance, current = heapq.heappop(frontier)
        if current in settled:
            continue
        settled.add(current)
        if current in targets:
            return distance
        for target in graph.get(current, ()):
            if target not in settled:
                heapq.heappush(frontier, (distance + weights[target], target))
    return weights[start]


def recompute_estimated_minutes(story: Mapping[str, object]) -> int:
    """Return a fastest-finish reading estimate in whole minutes.

    Implements ADR-011's fastest-finish clock as a reader-facing single
    playthrough time: the words on the shortest satisfying path divided by the
    band reading-pace anchor, rounded, and floored at 1.

    Args:
        story: The raw story document.

    Returns:
        int: The estimated minutes, always at least 1.
    """
    band = _str_field(_metadata_of(story), "age_band") or ""
    pace = _READING_PACE_WPM.get(band, _DEFAULT_PACE_WPM)
    words = _fastest_finish_words(story)
    return max(1, round(words / pace))


def _choice_graph(story: Mapping[str, object]) -> nx.DiGraph[str]:
    """Build the directed choice graph over the story's node ids."""
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(node_ids(story))
    for source, targets in adjacency(story).items():
        for target in targets:
            graph.add_edge(source, target)
    return graph


def redeclare_topology(story: Mapping[str, object]) -> Topology:
    """Return the topology the mutant should declare, per design section 4.8.

    The result must be both admissible for the graph shape (PL-18) and allowed
    for the parent band's ADR-011 section 7 row. The parent's declared topology
    is kept whenever it still satisfies both; otherwise a deterministic
    replacement is chosen from the intersection.

    Args:
        story: The raw story document.

    Returns:
        Topology: The topology to declare.

    Raises:
        ValidationError: If the story's band or declared topology is missing or
            unrecognized, or if no admissible topology is allowed for the band
            (the operator-side precondition fails and the mutant is discarded).
    """
    meta = _metadata_of(story)
    band = _str_field(meta, "age_band")
    if band is None:
        msg = "story metadata has no age_band for topology re-declaration"
        raise ValidationError(msg, field="age_band", value=None)
    declared_value = _str_field(meta, "topology")
    if declared_value is None:
        msg = "story metadata has no topology to re-declare"
        raise ValidationError(msg, field="topology", value=None)
    try:
        declared = Topology(declared_value)
    except ValueError as exc:
        msg = f"unrecognized declared topology '{declared_value}'"
        raise ValidationError(msg, field="topology", value=declared_value) from exc

    band_row = _BAND_TOPOLOGIES.get(band, frozenset())
    admissible = admissible_topologies(_choice_graph(story))
    allowed = admissible & band_row
    if declared in allowed:
        return declared
    for candidate in _TOPOLOGY_PREFERENCE:
        if candidate in allowed:
            return candidate
    msg = (
        f"no admissible topology is allowed for band '{band}': "
        f"admissible={sorted(t.value for t in admissible)}, "
        f"band_row={sorted(t.value for t in band_row)}"
    )
    raise ValidationError(msg, field="topology", value=declared_value)


def resync_metadata(story: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of ``story`` with its derived metadata recomputed.

    Recomputes ``ending_count`` (from the node list), ``tier`` (from variable
    presence), ``estimated_minutes`` (from the words-and-pace anchors), and
    re-declares ``topology`` (design section 4.8). Every other field is carried
    over unchanged. The input is never mutated.

    Args:
        story: The raw story document (its graph is assumed already mutated).

    Returns:
        dict[str, object]: A fresh document whose metadata is self-consistent
            with its graph, so it re-validates against the schema.

    Raises:
        ValidationError: If the story carries no metadata object, or topology
            re-declaration fails (see :func:`redeclare_topology`).
    """
    resynced = copy.deepcopy(dict(story))
    meta_raw = resynced.get("metadata")
    if not isinstance(meta_raw, dict):
        msg = "story has no metadata object to resync"
        raise ValidationError(msg, field="metadata", value=None)
    meta = cast(dict[str, object], meta_raw)  # noqa: TC006
    meta["ending_count"] = recompute_ending_count(story)
    meta["tier"] = recompute_tier(story)
    meta["estimated_minutes"] = recompute_estimated_minutes(story)
    meta["topology"] = redeclare_topology(story).value
    return resynced
