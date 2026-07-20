"""Subtree extraction plus self-containment and closedness checks.

WS-5 D1 (design section 4.1). A subtree ``T`` rooted at ``r`` is the forward
reachable closure of ``r`` over the story's choice edges. Two properties decide
whether an operator may move ``T`` as a block:

- **self-contained**: every edge into ``T`` from outside the region lands on
  ``r`` and nowhere else. This is the load-bearing precondition for every
  subtree move (design section 4.1 #CRITICAL block, reproduced on
  :func:`is_self_contained`).
- **closed**: no edge leaves ``T`` (equivalently, every leaf of ``T`` is an
  ending). A forward closure is always closed; the predicate is exposed
  separately so operators that propose an explicit, non-closure region can
  check it (design section 4.1).

Pure module: standard library plus the project exception hierarchy only. It
parses raw story dicts (the shape :func:`generation.skeleton.load_skeleton`
returns) rather than the Pydantic model, so it can run on an in-progress
candidate before it is schema-valid.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation._raw import (
    choices_of as _choices_of,
)
from cyo_adventure.mutation._raw import (
    nodes_of as _nodes_of,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class Edge:
    """A directed choice edge between two existing node ids."""

    source: str
    target: str


@dataclass(frozen=True, slots=True)
class Subtree:
    """The forward closure of a root node plus its move-eligibility flags.

    Attributes:
        root: The subtree's root node id.
        node_ids: Every node id in the forward closure, including ``root``.
        self_contained: Whether every external in-edge lands only on ``root``.
        closed: Whether no edge leaves the region (every leaf is an ending).
        external_in_edges: The edges that violate self-containment, sorted;
            empty when ``self_contained`` is True.
        out_edges: The edges leaving the region (its reconvergence surface),
            sorted; empty when ``closed`` is True.
    """

    root: str
    node_ids: frozenset[str]
    self_contained: bool
    closed: bool
    external_in_edges: tuple[Edge, ...]
    out_edges: tuple[Edge, ...]


def _node_id_of(node: Mapping[str, object]) -> str | None:
    """Return a node's id, or None when it is missing or not a string."""
    node_id = node.get("id")
    return node_id if isinstance(node_id, str) else None


def _choice_target_of(choice: Mapping[str, object]) -> str | None:
    """Return a choice's target node id, or None when malformed."""
    target = choice.get("target")
    return target if isinstance(target, str) else None


def node_ids(story: Mapping[str, object]) -> frozenset[str]:
    """Return the set of every node id declared in the story.

    Args:
        story: The raw story document.

    Returns:
        frozenset[str]: Every declared node id.
    """
    return frozenset(
        node_id for node in _nodes_of(story) if (node_id := _node_id_of(node))
    )


def adjacency(story: Mapping[str, object]) -> dict[str, tuple[str, ...]]:
    """Return the choice-graph adjacency over existing node ids.

    Targets that do not name an existing node (a dangling reference the gate's
    L1-2 rule rejects) are omitted, so callers reason only about real edges.

    Args:
        story: The raw story document.

    Returns:
        dict[str, tuple[str, ...]]: Each node id mapped to its in-order tuple
            of existing choice targets.
    """
    present = node_ids(story)
    graph: dict[str, tuple[str, ...]] = {}
    for node in _nodes_of(story):
        source = _node_id_of(node)
        if source is None:
            continue
        targets: list[str] = []
        for choice in _choices_of(node):
            target = _choice_target_of(choice)
            if target is not None and target in present:
                targets.append(target)
        graph[source] = tuple(targets)
    return graph


def all_edges(story: Mapping[str, object]) -> tuple[Edge, ...]:
    """Return every choice edge between existing nodes, sorted.

    Args:
        story: The raw story document.

    Returns:
        tuple[Edge, ...]: Every ``(source, target)`` edge, sorted for a
            deterministic result.
    """
    edges = [
        Edge(source=source, target=target)
        for source, targets in adjacency(story).items()
        for target in targets
    ]
    return tuple(sorted(edges, key=lambda edge: (edge.source, edge.target)))


def descendants(story: Mapping[str, object], root: str) -> frozenset[str]:
    """Return the forward reachable closure of ``root``, including ``root``.

    Args:
        story: The raw story document.
        root: The root node id.

    Returns:
        frozenset[str]: Every node reachable from ``root`` over choice edges,
            plus ``root`` itself. Cycles terminate safely (each node is visited
            once).

    Raises:
        ValidationError: If ``root`` is not a declared node id.
    """
    graph = adjacency(story)
    if root not in graph:
        msg = f"root '{root}' is not a node in the story"
        raise ValidationError(msg, field="root", value=root)
    seen: set[str] = {root}
    queue: deque[str] = deque([root])
    while queue:
        current = queue.popleft()
        for target in graph.get(current, ()):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return frozenset(seen)


def is_self_contained(
    story: Mapping[str, object], region: Iterable[str], root: str
) -> tuple[bool, tuple[Edge, ...]]:
    """Return whether every external in-edge into ``region`` lands only on ``root``.

    Args:
        story: The raw story document.
        region: The node ids forming the candidate region.
        root: The region's single legitimate entry node.

    Returns:
        tuple[bool, tuple[Edge, ...]]: ``(self_contained, violations)`` where
            ``violations`` are the edges from outside ``region`` into a
            non-root region node, sorted; empty when self-contained.
    """
    # #CRITICAL: data-integrity: self-containment is the load-bearing
    # precondition for every subtree move; a missed external in-edge would
    # leave a dangling or duplicated entry point and the moved region would be
    # reachable from a stale position. The check MUST enumerate in-edges over
    # the WHOLE graph, not the candidate region, so external predecessors are
    # never overlooked.
    # #VERIFY: tests/unit/test_mutation_subtree.py exhaustively scans, for
    # every node r in every catalog skeleton, that a self_contained result has
    # in-edges only at r (asserted by a full edge scan over all_edges).
    region_set = frozenset(region)
    violations = tuple(
        edge
        for edge in all_edges(story)
        if edge.target in region_set
        and edge.target != root
        and edge.source not in region_set
    )
    return (not violations, violations)


def is_closed(
    story: Mapping[str, object], region: Iterable[str]
) -> tuple[bool, tuple[Edge, ...]]:
    """Return whether no edge leaves ``region`` (every leaf is an ending).

    Args:
        story: The raw story document.
        region: The node ids forming the candidate region.

    Returns:
        tuple[bool, tuple[Edge, ...]]: ``(closed, out_edges)`` where
            ``out_edges`` are the edges from a region node to a node outside
            ``region`` (the reconvergence surface), sorted; empty when closed.
    """
    region_set = frozenset(region)
    out_edges = tuple(
        edge
        for edge in all_edges(story)
        if edge.source in region_set and edge.target not in region_set
    )
    return (not out_edges, out_edges)


def extract_subtree(story: Mapping[str, object], root: str) -> Subtree:
    """Extract the forward closure of ``root`` and evaluate its move flags.

    The returned region is the forward reachable closure of ``root``; a forward
    closure is closed by construction (no edge can leave it), so the
    discriminating flag for move-eligibility is :attr:`Subtree.self_contained`.

    Args:
        story: The raw story document.
        root: The root node id.

    Returns:
        Subtree: The closure plus its self-containment and closedness flags and
            the boundary-edge evidence for each.

    Raises:
        ValidationError: If ``root`` is not a declared node id.
    """
    region = descendants(story, root)
    self_contained, external_in_edges = is_self_contained(story, region, root)
    closed, out_edges = is_closed(story, region)
    return Subtree(
        root=root,
        node_ids=region,
        self_contained=self_contained,
        closed=closed,
        external_in_edges=external_in_edges,
        out_edges=out_edges,
    )
