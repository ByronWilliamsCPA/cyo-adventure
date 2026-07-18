"""Structure fingerprint and graded structural distance (diversity/structure.py).

Reuses the ``check_fill_integrity.py`` convention for identity (strip leaf
content, canonicalize, hash) and builds a graded feature-vector distance on
top of it for cases where two stories are NOT the same skeleton (WS-0 design
doc section 2.4).

Pure module: stdlib, ``networkx``, and ``cyo_adventure.storybook.models``
only. Never imports ``db``, ``generation``, or ``sqlalchemy``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import networkx as nx

from cyo_adventure.diversity.normalize import coerce_storybook
from cyo_adventure.storybook.models import EndingKind, Valence

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from cyo_adventure.storybook.models import Node, Storybook

# Fixed bin order for the ending-kind and valence histograms, so two
# StructureFeatures instances are always directly comparable positionally.
_ENDING_KIND_ORDER: tuple[EndingKind, ...] = (
    EndingKind.SUCCESS,
    EndingKind.SETBACK,
    EndingKind.DEATH,
    EndingKind.CAPTURE,
    EndingKind.COMPLETION,
    EndingKind.DISCOVERY,
)
_VALENCE_ORDER: tuple[Valence, ...] = (
    Valence.POSITIVE,
    Valence.NEUTRAL,
    Valence.NEGATIVE,
)

# struct_dist weighting (WS-0 design doc section 2.4): numeric feature
# canberra mean, histogram L1 (kind + valence, averaged), topology flag.
_NUMERIC_WEIGHT = 0.5
_HISTOGRAM_WEIGHT = 0.3
_TOPOLOGY_WEIGHT = 0.2


def _strip_leaf_content(data: dict[str, object]) -> dict[str, object]:
    """Return a deep copy of a story dump with title/body/ending-title removed.

    Args:
        data: A ``Storybook.model_dump(mode="json")`` result.

    Returns:
        dict[str, object]: The same structure with every piece of prose
            content stripped, leaving only the graph shape.
    """
    stripped = copy.deepcopy(data)
    stripped.pop("title", None)
    nodes = stripped.get("nodes")
    if isinstance(nodes, list):
        for raw_node in cast("list[object]", nodes):
            if isinstance(raw_node, dict):
                node = cast("dict[str, object]", raw_node)
                node.pop("body", None)
                ending = node.get("ending")
                if isinstance(ending, dict):
                    cast("dict[str, object]", ending).pop("title", None)
    return stripped


def structure_fingerprint(story: Storybook | Mapping[str, object]) -> str:
    """Return a stable hash of a story's structure, ignoring prose.

    Args:
        story: A validated Storybook, or a raw blob to coerce.

    Returns:
        str: A sha256 hex digest of the canonicalized, leaf-content-free
            story. Two fills of one skeleton hash equal by construction
            (the fill contract forbids touching anything but bodies); a
            titled ending or story title does not affect the fingerprint,
            since titles are leaf content, not structure.
    """
    model = coerce_storybook(story)
    canonical = _strip_leaf_content(model.model_dump(mode="json"))
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StructureFeatures:
    """The graded structural feature vector for one story (WS-0 section 2.4)."""

    n_nodes: int
    n_endings: int
    n_choices: int
    mean_branching: float
    decision_ratio: float
    max_depth: int
    min_ending_depth: int
    reconvergence_ratio: float
    n_variables: int
    n_conditions: int
    n_effects: int
    ending_kind_hist: tuple[float, ...]
    valence_hist: tuple[float, ...]
    topology: str


def _build_choice_graph(story: Storybook) -> nx.DiGraph[str]:
    """Build the directed choice graph over a story's node ids.

    Args:
        story: The validated story.

    Returns:
        nx.DiGraph[str]: Nodes are node ids; edges are choice targets.
    """
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(node.id for node in story.nodes)
    for node in story.nodes:
        for choice in node.choices:
            if choice.target in graph:
                graph.add_edge(node.id, choice.target)
    return graph


def _decision_stats(non_ending_nodes: Sequence[Node]) -> tuple[float, float]:
    """Return ``(mean_branching, decision_ratio)`` over non-ending nodes.

    Args:
        non_ending_nodes: Every node with ``is_ending`` False.

    Returns:
        tuple[float, float]: Mean out-degree over decision nodes
            (out-degree >= 2), and the fraction of non-ending nodes that
            are decision nodes; both 0.0 when there are none.
    """
    decision_nodes = [node for node in non_ending_nodes if len(node.choices) >= 2]
    mean_branching = (
        sum(len(node.choices) for node in decision_nodes) / len(decision_nodes)
        if decision_nodes
        else 0.0
    )
    decision_ratio = (
        len(decision_nodes) / len(non_ending_nodes) if non_ending_nodes else 0.0
    )
    return mean_branching, decision_ratio


def _depth_stats(
    graph: nx.DiGraph[str], start_node: str, ending_ids: set[str]
) -> tuple[int, int]:
    """Return ``(max_depth, min_ending_depth)`` via BFS from the start node.

    Args:
        graph: The story's choice graph.
        start_node: The story's declared start node id.
        ending_ids: Ids of every ending node.

    Returns:
        tuple[int, int]: The longest and shortest shortest-path depths from
            ``start_node``; BFS-based, so cyclic topologies (open_map,
            loop_and_grow) terminate safely instead of looping. Both are
            0 when the start node is absent from the graph or no ending is
            reachable (defensive; should not occur for a schema-valid,
            gate-passed story).
    """
    depths: dict[str, int] = (
        cast("dict[str, int]", nx.single_source_shortest_path_length(graph, start_node))
        if start_node in graph
        else {}
    )
    max_depth = max(depths.values()) if depths else 0
    ending_depths = [
        depth for node_id, depth in depths.items() if node_id in ending_ids
    ]
    min_ending_depth = min(ending_depths) if ending_depths else 0
    return max_depth, min_ending_depth


def _ending_histograms(
    ending_nodes: Sequence[Node],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return the normalized ``(ending_kind_hist, valence_hist)`` pair.

    Args:
        ending_nodes: Every node with ``is_ending`` True.

    Returns:
        tuple[tuple[float, ...], tuple[float, ...]]: Each histogram sums to
            1.0 (or is all-zero when there are no endings), in the fixed
            bin order of :data:`_ENDING_KIND_ORDER` / :data:`_VALENCE_ORDER`.
    """
    n_endings = len(ending_nodes)
    kind_counts = dict.fromkeys(_ENDING_KIND_ORDER, 0)
    valence_counts = dict.fromkeys(_VALENCE_ORDER, 0)
    for node in ending_nodes:
        ending = node.ending
        if ending is None:
            continue
        kind_counts[ending.kind] += 1
        valence_counts[ending.valence] += 1
    kind_hist = tuple(
        kind_counts[kind] / n_endings if n_endings else 0.0
        for kind in _ENDING_KIND_ORDER
    )
    valence_hist = tuple(
        valence_counts[valence] / n_endings if n_endings else 0.0
        for valence in _VALENCE_ORDER
    )
    return kind_hist, valence_hist


def structure_features(story: Storybook | Mapping[str, object]) -> StructureFeatures:
    """Compute the graded structural feature vector for one story.

    Args:
        story: A validated Storybook, or a raw blob to coerce.

    Returns:
        StructureFeatures: The full feature vector (WS-0 design doc
            section 2.4 table).
    """
    model = coerce_storybook(story)
    graph = _build_choice_graph(model)
    ending_nodes = [node for node in model.nodes if node.is_ending]
    non_ending_nodes = [node for node in model.nodes if not node.is_ending]
    ending_ids = {node.id for node in ending_nodes}
    n_nodes = len(model.nodes)

    mean_branching, decision_ratio = _decision_stats(non_ending_nodes)
    max_depth, min_ending_depth = _depth_stats(graph, model.start_node, ending_ids)
    kind_hist, valence_hist = _ending_histograms(ending_nodes)
    reconvergence_ratio = (
        sum(1 for node_id in graph if graph.in_degree(node_id) >= 2) / n_nodes
        if n_nodes
        else 0.0
    )
    n_conditions = sum(
        1
        for node in model.nodes
        for choice in node.choices
        if choice.condition is not None
    )
    n_effects = sum(
        len(node.on_enter) + sum(len(choice.effects) for choice in node.choices)
        for node in model.nodes
    )

    return StructureFeatures(
        n_nodes=n_nodes,
        n_endings=len(ending_nodes),
        n_choices=sum(len(node.choices) for node in model.nodes),
        mean_branching=mean_branching,
        decision_ratio=decision_ratio,
        max_depth=max_depth,
        min_ending_depth=min_ending_depth,
        reconvergence_ratio=reconvergence_ratio,
        n_variables=len(model.variables),
        n_conditions=n_conditions,
        n_effects=n_effects,
        ending_kind_hist=kind_hist,
        valence_hist=valence_hist,
        topology=model.metadata.topology.value,
    )


def _numeric_vector(features: StructureFeatures) -> tuple[float, ...]:
    """Return the canberra-distance numeric feature vector, in fixed order.

    Args:
        features: One story's structural features.

    Returns:
        tuple[float, ...]: The 11 numeric features from WS-0 design doc
            section 2.4, as floats.
    """
    return (
        float(features.n_nodes),
        float(features.n_endings),
        float(features.n_choices),
        features.mean_branching,
        features.decision_ratio,
        float(features.max_depth),
        float(features.min_ending_depth),
        features.reconvergence_ratio,
        float(features.n_variables),
        float(features.n_conditions),
        float(features.n_effects),
    )


def _canberra(x: float, y: float) -> float:
    """Return the canberra term for one feature pair (0.0 when both are 0)."""
    denom = x + y
    return 0.0 if denom == 0 else abs(x - y) / denom


def _canberra_mean(a: StructureFeatures, b: StructureFeatures) -> float:
    """Return the mean canberra distance over the numeric feature vector."""
    vec_a = _numeric_vector(a)
    vec_b = _numeric_vector(b)
    diffs = [_canberra(x, y) for x, y in zip(vec_a, vec_b, strict=True)]
    return sum(diffs) / len(diffs)


def _l1(hist_a: tuple[float, ...], hist_b: tuple[float, ...]) -> float:
    """Return the L1 (sum of absolute differences) distance between histograms."""
    return sum(abs(x - y) for x, y in zip(hist_a, hist_b, strict=True))


def structural_distance(
    a: Storybook | Mapping[str, object], b: Storybook | Mapping[str, object]
) -> float:
    """Return the graded structural distance between two stories.

    Args:
        a: The first story (validated Storybook, or a raw blob to coerce).
        b: The second story.

    Returns:
        float: A value in ``[0, 1]``: canberra-mean over the numeric
            feature vector, plus the ending-kind/valence histogram L1
            distance, plus a topology-mismatch flag (WS-0 design doc
            section 2.4). Exactly ``0.0`` whenever the two stories share a
            :func:`structure_fingerprint` (same skeleton, by construction);
            this is checked directly rather than relied upon, since it is
            the pinned invariant the WS-0 tests assert.
    """
    model_a = coerce_storybook(a)
    model_b = coerce_storybook(b)
    if structure_fingerprint(model_a) == structure_fingerprint(model_b):
        return 0.0
    features_a = structure_features(model_a)
    features_b = structure_features(model_b)
    numeric_term = _canberra_mean(features_a, features_b)
    histogram_term = 0.5 * (
        _l1(features_a.ending_kind_hist, features_b.ending_kind_hist) / 2
        + _l1(features_a.valence_hist, features_b.valence_hist) / 2
    )
    topology_term = 0.0 if features_a.topology == features_b.topology else 1.0
    return (
        _NUMERIC_WEIGHT * numeric_term
        + _HISTOGRAM_WEIGHT * histogram_term
        + _TOPOLOGY_WEIGHT * topology_term
    )
