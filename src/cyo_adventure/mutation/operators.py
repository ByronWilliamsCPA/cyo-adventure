"""Structural mutation operators (WS-5 D2 onward).

This module carries the concrete :class:`~cyo_adventure.mutation.ops.MutationOp`
implementations that the D1 framework (``ops.py``) declares only as a protocol.
D2 ships M1, the sibling-subtree swap (design section 4.2); later deliverables
add M2-M5 alongside it and register them in the same default registry.

Pure module: standard library, ``networkx``, and lower project layers only. It
imports from ``validator`` solely to *call* the validator's read-only budget and
floor lookups (``resolve_node_budget``, ``min_complete_floor``) as cheap
pre-checks, never to construct a report or move a threshold (design CR-2). It
imports nothing from ``db``, ``generation`` (beyond the pure surfaces), or
``network``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import networkx as nx

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.identity import recompute_tier, resync_metadata
from cyo_adventure.mutation.ops import (
    REGISTRY,
    MutationResult,
    OpParams,
    PreconditionReport,
    ReguideItem,
    ReguideTarget,
)
from cyo_adventure.mutation.subtree import adjacency, extract_subtree, node_ids
from cyo_adventure.validator.band_profile import min_complete_floor
from cyo_adventure.validator.layer1 import ScalePlacement, resolve_node_budget

if TYPE_CHECKING:
    import random
    from collections.abc import Mapping

# The M1 operator id, recorded in every lineage manifest and used as the
# registry key. Kept as a module constant so the CLI and tests never spell the
# string literal.
M1_OP_ID = "M1"

# The satisfying-ending kinds (a full-arc completion) the PL-20 arc floor
# targets, per ADR-011 section 4. Read from the raw ending block, so the
# pre-check matches ``validator.policy._SATISFYING_KINDS`` without importing it.
_SATISFYING_KINDS = frozenset({"success", "completion"})

# Static precondition and error messages, kept as single-line module constants
# so a long fixed string never needs a plain-string line wrap.
_TIER1_ONLY_MSG = "M1 (D2) is restricted to Tier-1 parents; Tier-2 is a later extension"
_PRODUCTION_ONLY_MSG = (
    "M1 requires a production-eligible parent; MVP seeds are out of scope"
)
_CHOICE_PARAMS_MSG = "M1 requires both 'choice1' and 'choice2' parameters as choice ids"


def _nodes_of(story: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return the story's node dicts, skipping any malformed entries."""
    raw = story.get("nodes")
    if not isinstance(raw, list):
        return []
    return [
        cast("Mapping[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    ]


def _choices_of(node: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return a node's choice dicts, skipping any malformed entries."""
    raw = node.get("choices")
    if not isinstance(raw, list):
        return []
    return [
        cast("Mapping[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    ]


def _str_field(container: Mapping[str, object], key: str) -> str | None:
    """Return a string-valued field of a mapping, or None when not a string."""
    value = container.get(key)
    return value if isinstance(value, str) else None


def _metadata_of(story: Mapping[str, object]) -> Mapping[str, object]:
    """Return the story's metadata block, or an empty mapping when absent."""
    meta = story.get("metadata")
    return cast("Mapping[str, object]", meta) if isinstance(meta, dict) else {}


def _node_body(story: Mapping[str, object], node_id: str) -> str:
    """Return a node's body text, or the empty string when absent."""
    for node in _nodes_of(story):
        if _str_field(node, "id") == node_id:
            return _str_field(node, "body") or ""
    return ""


@dataclass(frozen=True, slots=True)
class _ChoiceRef:
    """A choice located in the story, with the facts a swap needs.

    Attributes:
        choice_id: The choice's id (unique across the story per the schema).
        node_id: The decision node that holds the choice.
        target: The choice's target node id (the subtree root it enters).
        label: The choice's reader-facing label (for the re-guidance record).
    """

    choice_id: str
    node_id: str
    target: str
    label: str


@dataclass(frozen=True, slots=True)
class _SwapPair:
    """A validated pair of choices whose subtrees M1 will swap.

    Canonical order: ``choice1_id < choice2_id``, so a swap is a pure function
    of the unordered pair and any two equivalent parameterizations produce a
    byte-identical candidate.

    Attributes:
        choice1_id: The lexicographically smaller choice id.
        node1_id: The decision node holding ``choice1_id``.
        root1: The subtree root ``choice1_id`` currently targets.
        choice2_id: The lexicographically larger choice id.
        node2_id: The decision node holding ``choice2_id``.
        root2: The subtree root ``choice2_id`` currently targets.
    """

    choice1_id: str
    node1_id: str
    root1: str
    choice2_id: str
    node2_id: str
    root2: str


def _choice_refs(story: Mapping[str, object]) -> dict[str, _ChoiceRef]:
    """Return every choice in the story keyed by its id.

    Args:
        story: The raw story document.

    Returns:
        dict[str, _ChoiceRef]: Each choice id mapped to its located reference.
    """
    refs: dict[str, _ChoiceRef] = {}
    for node in _nodes_of(story):
        node_id = _str_field(node, "id")
        if node_id is None:
            continue
        for choice in _choices_of(node):
            choice_id = _str_field(choice, "id")
            target = _str_field(choice, "target")
            if choice_id is None or target is None:
                continue
            refs[choice_id] = _ChoiceRef(
                choice_id=choice_id,
                node_id=node_id,
                target=target,
                label=_str_field(choice, "label") or "",
            )
    return refs


def _parent_graph(story: Mapping[str, object]) -> nx.DiGraph[str]:
    """Build the directed choice graph over the story's node ids."""
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(node_ids(story))
    for source, targets in adjacency(story).items():
        for target in targets:
            graph.add_edge(source, target)
    return graph


def _post_swap_graph(story: Mapping[str, object], pair: _SwapPair) -> nx.DiGraph[str]:
    """Build the choice graph the story would have after applying ``pair``.

    Rewrites only the two swapped choice targets, at the choice level, so the
    result is exact even when a decision node has several choices sharing a
    target. No document is copied; this is the cheap graph the acyclicity,
    depth, and arc-floor pre-checks read.

    Args:
        story: The raw parent story document.
        pair: The swap to model.

    Returns:
        nx.DiGraph[str]: The post-swap choice graph.
    """
    present = node_ids(story)
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(present)
    for node in _nodes_of(story):
        source = _str_field(node, "id")
        if source is None:
            continue
        for choice in _choices_of(node):
            choice_id = _str_field(choice, "id")
            target = _str_field(choice, "target")
            if choice_id == pair.choice1_id:
                target = pair.root2
            elif choice_id == pair.choice2_id:
                target = pair.root1
            if target is not None and target in present:
                graph.add_edge(source, target)
    return graph


def _branch_depth(graph: nx.DiGraph[str], start: str | None) -> int | None:
    """Return the longest start-to-reachable path length, or None if cyclic.

    Mirrors ``validator.layer1._branch_depth`` exactly (longest path in hops
    over the reachable subgraph, skipped when that subgraph is cyclic), so the
    depth pre-check agrees with the L1-7 gate rule it anticipates.
    """
    if start is None or start not in graph:
        return None
    reachable = nx.descendants(graph, start) | {start}
    subgraph = graph.subgraph(reachable)
    if not nx.is_directed_acyclic_graph(subgraph):
        return None
    return int(nx.dag_longest_path_length(subgraph))


def _cell_max_depth(story: Mapping[str, object]) -> int | None:
    """Return the inherited cell's ``max_depth`` budget, or None when unbudgeted.

    Reuses ``validator.layer1.resolve_node_budget`` (the single budget path the
    L1-7 gate uses) so the depth ceiling is the exact one the gate enforces.
    """
    meta = _metadata_of(story)
    band = _str_field(meta, "age_band")
    if band is None:
        return None
    placement = ScalePlacement(
        length=_str_field(meta, "length"),
        narrative_style=_str_field(meta, "narrative_style") or "prose",
        production_eligible=meta.get("production_eligible") is not False,
    )
    budget = resolve_node_budget(band, placement, scale="standard")
    return budget[2] if budget is not None else None


def _satisfying_ending_ids(story: Mapping[str, object]) -> set[str]:
    """Return the node ids of success/completion endings (PL-20 targets)."""
    targets: set[str] = set()
    for node in _nodes_of(story):
        if node.get("is_ending") is not True:
            continue
        node_id = _str_field(node, "id")
        ending = node.get("ending")
        if node_id is None or not isinstance(ending, dict):
            continue
        kind = _str_field(cast("Mapping[str, object]", ending), "kind")
        if kind in _SATISFYING_KINDS:
            targets.add(node_id)
    return targets


def _shortest_satisfying_nodes(
    graph: nx.DiGraph[str], start: str | None, targets: set[str]
) -> int | None:
    """Return the fewest nodes on any path from start to a satisfying ending.

    Path length is measured in nodes (hops + 1), matching
    ``validator.policy._shortest_path_nodes``. Returns None when no satisfying
    ending is reachable.
    """
    if start is None:
        return None
    best: int | None = None
    for target in targets:
        if start not in graph or target not in graph:
            continue
        if not nx.has_path(graph, start, target):
            continue
        nodes = int(nx.shortest_path_length(graph, start, target)) + 1
        if best is None or nodes < best:
            best = nodes
    return best


def _pl20_floor(story: Mapping[str, object]) -> int | None:
    """Return the inherited cell's PL-20 arc floor, or None when it does not apply.

    PL-20 applies only to a scale-classified, production-eligible story (one
    that declares a ``length``), matching ``validator.policy._check_min_to_complete``.
    """
    meta = _metadata_of(story)
    band = _str_field(meta, "age_band")
    length = _str_field(meta, "length")
    style = _str_field(meta, "narrative_style") or "prose"
    if band is None or length is None or meta.get("production_eligible") is False:
        return None
    return min_complete_floor(band, length, style)


def _resolve_swap_refs(
    story: Mapping[str, object], choice_a: str, choice_b: str
) -> tuple[_ChoiceRef, _ChoiceRef] | str:
    """Resolve two choice ids to their located refs, or a failure reason.

    Canonicalizes the order (``choice1_id < choice2_id``) and enforces the cheap
    identity preconditions: distinct choices, both present, both targeting an
    existing but distinct node.

    Args:
        story: The raw parent story document.
        choice_a: One choice id.
        choice_b: The other choice id.

    Returns:
        tuple[_ChoiceRef, _ChoiceRef] | str: The canonical ref pair, or a reason.
    """
    if choice_a == choice_b:
        return "M1 needs two distinct choices to swap"
    first, second = sorted((choice_a, choice_b))
    refs = _choice_refs(story)
    ref1 = refs.get(first)
    ref2 = refs.get(second)
    if ref1 is None:
        return f"choice '{first}' is not a choice in this story"
    if ref2 is None:
        return f"choice '{second}' is not a choice in this story"
    present = node_ids(story)
    if ref1.target not in present or ref2.target not in present:
        return "a swapped choice targets a node that does not exist"
    if ref1.target == ref2.target:
        return "both choices already target the same subtree; the swap is a no-op"
    return ref1, ref2


def _build_disjoint_pair(
    story: Mapping[str, object], ref1: _ChoiceRef, ref2: _ChoiceRef
) -> _SwapPair | str:
    """Build a swap pair from two refs, or return a self-containment/overlap reason.

    Args:
        story: The raw parent story document.
        ref1: The canonically first choice ref.
        ref2: The canonically second choice ref.

    Returns:
        _SwapPair | str: The validated pair, or the failing reason.
    """
    subtree1 = extract_subtree(story, ref1.target)
    if not subtree1.self_contained:
        sources1 = [edge.source for edge in subtree1.external_in_edges]
        return (
            f"subtree rooted at '{ref1.target}' is not self-contained "
            f"(external in-edges: {sources1})"
        )
    subtree2 = extract_subtree(story, ref2.target)
    if not subtree2.self_contained:
        sources2 = [edge.source for edge in subtree2.external_in_edges]
        return (
            f"subtree rooted at '{ref2.target}' is not self-contained "
            f"(external in-edges: {sources2})"
        )

    # #CRITICAL: data-integrity: node-set disjointness is what makes the swap a
    # safe re-pairing. Two overlapping (for example nested) subtrees would, once
    # swapped, either duplicate a region or route a choice back into an ancestor
    # and close a cycle. Rejecting overlap here is the primary cycle guard; the
    # acyclicity check in _post_swap_reason is the belt-and-braces backstop, and
    # the full gate (stage 1) is the fail-closed authority.
    # #VERIFY: tests/unit/test_mutation_m1.py pins that an overlapping pair is
    # rejected at preconditions and that the accepted output is never gate-blocked.
    if subtree1.node_ids & subtree2.node_ids:
        return (
            "the two subtrees share nodes (not node-disjoint); swapping them "
            "could duplicate a region or create a cycle"
        )

    return _SwapPair(
        choice1_id=ref1.choice_id,
        node1_id=ref1.node_id,
        root1=ref1.target,
        choice2_id=ref2.choice_id,
        node2_id=ref2.node_id,
        root2=ref2.target,
    )


def _post_swap_reason(story: Mapping[str, object], pair: _SwapPair) -> str | None:
    """Return the first post-swap precondition failure, or None when all hold.

    Checks post-swap acyclicity (when the parent is acyclic), post-swap depth
    within the cell budget (L1-7), and the post-swap arc floor (PL-20). All are
    pre-computed to avoid a wasted gate run, and all are re-proven by the gate at
    stage 1 regardless.

    Args:
        story: The raw parent story document.
        pair: The candidate swap.

    Returns:
        str | None: The first failing reason, or None.
    """
    # #CRITICAL: concurrency-free structural integrity: a swap on an acyclic
    # parent must stay acyclic; a back-edge into an ancestor would make the story
    # non-terminating for a reader. For closed, disjoint, self-contained subtrees
    # this cannot happen (a closed region has no out-edges), but the explicit
    # post-swap DAG check is retained as defense in depth and is what a future
    # non-closed extension will rely on.
    # #VERIFY: test_mutation_m1.py exercises _post_swap_is_acyclic directly on a
    # crafted cycle and asserts the acyclic-parent branch rejects it.
    if not _post_swap_is_acyclic(story, pair):
        return "the swap would create a cycle in an otherwise acyclic story"

    start = _str_field(story, "start_node")
    post_graph = _post_swap_graph(story, pair)
    max_depth = _cell_max_depth(story)
    if max_depth is not None:
        depth = _branch_depth(post_graph, start)
        if depth is not None and depth > max_depth:
            return f"post-swap branch depth {depth} exceeds cell max_depth {max_depth}"

    floor = _pl20_floor(story)
    if floor is not None:
        targets = _satisfying_ending_ids(story)
        shortest = _shortest_satisfying_nodes(post_graph, start, targets)
        if shortest is not None and shortest < floor:
            return (
                f"post-swap shortest satisfying path is {shortest} node(s), below "
                f"the PL-20 floor {floor}"
            )
    return None


def _evaluate_pair(
    story: Mapping[str, object], choice_a: str, choice_b: str
) -> tuple[_SwapPair | None, str | None]:
    """Validate a candidate swap of two choices' subtrees (design section 4.2).

    Runs the full precondition set in three stages: cheap identity resolution
    (:func:`_resolve_swap_refs`), self-containment and disjointness
    (:func:`_build_disjoint_pair`), then the post-swap acyclicity, depth, and arc
    checks (:func:`_post_swap_reason`).

    Args:
        story: The raw parent story document.
        choice_a: One choice id.
        choice_b: The other choice id.

    Returns:
        tuple[_SwapPair | None, str | None]: ``(pair, None)`` when eligible,
            else ``(None, reason)``.
    """
    resolved = _resolve_swap_refs(story, choice_a, choice_b)
    if isinstance(resolved, str):
        return None, resolved
    ref1, ref2 = resolved
    pair_or_reason = _build_disjoint_pair(story, ref1, ref2)
    if isinstance(pair_or_reason, str):
        return None, pair_or_reason
    reason = _post_swap_reason(story, pair_or_reason)
    if reason is not None:
        return None, reason
    return pair_or_reason, None


def _post_swap_is_acyclic(story: Mapping[str, object], pair: _SwapPair) -> bool:
    """Return whether the swap keeps an acyclic parent acyclic.

    A cyclic parent (an ``open_map`` or ``loop_and_grow`` tree whose loops are
    legitimate) is not constrained by this check: the parent already carries
    cycles and the closed-subtree rule prevents the swap from adding a new one.
    Only when the parent is acyclic does the post-swap graph have to stay so.

    Args:
        story: The raw parent story document.
        pair: The swap to model.

    Returns:
        bool: True when the parent is cyclic, or when both parent and post-swap
            graphs are acyclic; False when an acyclic parent would gain a cycle.
    """
    if not nx.is_directed_acyclic_graph(_parent_graph(story)):
        return True
    return nx.is_directed_acyclic_graph(_post_swap_graph(story, pair))


def _self_contained_root_sets(
    story: Mapping[str, object],
) -> dict[str, frozenset[str]]:
    """Return each self-contained subtree root mapped to its node set.

    Computed once per parent (one BFS per distinct choice-target root), so the
    cheap pairwise disjointness filter runs on precomputed sets.

    Args:
        story: The raw parent story document.

    Returns:
        dict[str, frozenset[str]]: Self-contained root id to its subtree node set.
    """
    present = node_ids(story)
    roots: dict[str, frozenset[str]] = {}
    for ref in _choice_refs(story).values():
        root = ref.target
        if root in roots or root not in present:
            continue
        subtree = extract_subtree(story, root)
        if subtree.self_contained:
            roots[root] = subtree.node_ids
    return roots


def _cheap_candidate_pairs(story: Mapping[str, object]) -> list[tuple[str, str]]:
    """Return the deterministically ordered choice-id pairs worth full evaluation.

    Applies only the cheap filters (both roots self-contained, distinct, and
    node-disjoint); the expensive post-swap acyclicity, depth, and arc-floor
    checks are deferred to :func:`_evaluate_pair` on the pairs the caller
    actually tries. Ordered by ``(choice1_id, choice2_id)`` so any seeded
    selection over the list is reproducible.

    Args:
        story: The raw parent story document.

    Returns:
        list[tuple[str, str]]: Canonically ordered ``(choice1_id, choice2_id)``
            candidate pairs.
    """
    roots = _self_contained_root_sets(story)
    ordered = sorted(_choice_refs(story).values(), key=lambda ref: ref.choice_id)
    candidates: list[tuple[str, str]] = []
    for index, ref_a in enumerate(ordered):
        if ref_a.target not in roots:
            continue
        for ref_b in ordered[index + 1 :]:
            if ref_b.target not in roots:
                continue
            if ref_a.target == ref_b.target:
                continue
            if roots[ref_a.target] & roots[ref_b.target]:
                continue
            candidates.append((ref_a.choice_id, ref_b.choice_id))
    return candidates


def _has_eligible_pair(story: Mapping[str, object]) -> bool:
    """Return whether any cheap candidate pair passes full evaluation.

    Short-circuits at the first eligible pair, so a precondition check is cheap
    even on a large parent with many self-contained subtrees.
    """
    return any(
        _evaluate_pair(story, choice_a, choice_b)[0] is not None
        for choice_a, choice_b in _cheap_candidate_pairs(story)
    )


def _apply_swap(parent: Mapping[str, object], pair: _SwapPair) -> dict[str, object]:
    """Return a deep copy of ``parent`` with the two choice targets swapped.

    Args:
        parent: The raw parent story document (never mutated).
        pair: The validated swap.

    Returns:
        dict[str, object]: The candidate graph, pre-metadata-resync.

    Raises:
        ValidationError: If the parent has no node list.
    """
    candidate = copy.deepcopy(dict(parent))
    nodes = candidate.get("nodes")
    if not isinstance(nodes, list):
        msg = "parent story has no nodes list to swap"
        raise ValidationError(msg, field="nodes", value=None)
    for raw_node in cast("list[object]", nodes):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        raw_choices = node.get("choices")
        if not isinstance(raw_choices, list):
            continue
        for raw_choice in cast("list[object]", raw_choices):
            if not isinstance(raw_choice, dict):
                continue
            choice = cast("dict[str, object]", raw_choice)
            choice_id = choice.get("id")
            if choice_id == pair.choice1_id:
                choice["target"] = pair.root2
            elif choice_id == pair.choice2_id:
                choice["target"] = pair.root1
    return candidate


def _reguide_items(
    parent: Mapping[str, object], pair: _SwapPair
) -> tuple[ReguideItem, ...]:
    """Return the four re-guidance items a swap invalidates (design section 4.2).

    The two swapped choice labels describe an approach that now leads elsewhere,
    and the two moved subtree-root entry beats now begin from a different
    decision context; all four need re-authoring before the mutant is promotable.

    Args:
        parent: The raw parent story document.
        pair: The validated swap.

    Returns:
        tuple[ReguideItem, ...]: The two choice-label items then the two
            subtree-root beat items.
    """
    refs = _choice_refs(parent)
    ref1 = refs[pair.choice1_id]
    ref2 = refs[pair.choice2_id]
    choice_reason = (
        "swapped choice now leads to a different subtree; re-check its label"
    )
    node_reason = "subtree root now hangs from a different decision; re-check its beats"
    return (
        ReguideItem(
            target=ReguideTarget.CHOICE,
            target_id=pair.choice1_id,
            reason=choice_reason,
            current_text=ref1.label,
        ),
        ReguideItem(
            target=ReguideTarget.CHOICE,
            target_id=pair.choice2_id,
            reason=choice_reason,
            current_text=ref2.label,
        ),
        ReguideItem(
            target=ReguideTarget.NODE,
            target_id=pair.root1,
            reason=node_reason,
            current_text=_node_body(parent, pair.root1),
        ),
        ReguideItem(
            target=ReguideTarget.NODE,
            target_id=pair.root2,
            reason=node_reason,
            current_text=_node_body(parent, pair.root2),
        ),
    )


class M1SiblingSubtreeSwap:
    """M1: swap two sibling subtrees between decision choices (design section 4.2).

    Given choices ``c1`` and ``c2`` whose targets root self-contained,
    node-disjoint subtrees ``T1`` and ``T2``, retarget ``c1`` to ``root(T2)`` and
    ``c2`` to ``root(T1)``: the same materials, a different map. The node set,
    node count, ending multiset, ending count, and every in-degree are preserved
    by construction; depth, fastest-finish, and reconvergence may change and are
    re-proven by the full gate at acceptance.

    The swap is selected either from explicit ``choice1``/``choice2`` id
    parameters or, when those are absent, reproducibly from the seeded rng over
    the deterministically ordered eligible-pair list. D2 restricts M1 to Tier-1
    parents; the Tier-2 extension (effect/condition-free subtree pairs) is later.
    """

    op_id: str = M1_OP_ID

    def preconditions(
        self, parent: Mapping[str, object], params: OpParams
    ) -> PreconditionReport:
        """Return whether M1 may attempt a swap on ``parent`` (design section 4.2).

        Args:
            parent: The raw parent story document.
            params: The operator parameters (optional ``choice1``/``choice2``).

        Returns:
            PreconditionReport: Satisfied when a swap is eligible, else a report
                carrying every failing reason.
        """
        failures: list[str] = []
        meta = _metadata_of(parent)
        if recompute_tier(parent) != 1:
            failures.append(_TIER1_ONLY_MSG)
        if meta.get("series") is not None:
            failures.append(
                "M1 requires metadata.series to be None; series books are out of scope"
            )
        if meta.get("production_eligible") is False:
            failures.append(_PRODUCTION_ONLY_MSG)

        choice1 = params.get("choice1")
        choice2 = params.get("choice2")
        if choice1 is not None or choice2 is not None:
            if not (isinstance(choice1, str) and isinstance(choice2, str)):
                failures.append(_CHOICE_PARAMS_MSG)
            else:
                _pair, reason = _evaluate_pair(parent, choice1, choice2)
                if reason is not None:
                    failures.append(
                        f"swap ({choice1}, {choice2}) is ineligible: {reason}"
                    )
        elif not _has_eligible_pair(parent):
            failures.append("no eligible sibling-subtree swap exists for this parent")

        if failures:
            return PreconditionReport.failed(*failures)
        return PreconditionReport.passed()

    def apply(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> MutationResult:
        """Apply the swap and return the resynced candidate plus its re-guidance.

        Args:
            parent: The raw parent story document (never mutated).
            params: The operator parameters (optional ``choice1``/``choice2``).
            rng: The injected random source; a recorded seed reproduces the
                exact candidate when the pair is rng-selected.

        Returns:
            MutationResult: The candidate (metadata resynced) and its four
                re-guidance items.

        Raises:
            ValidationError: If no eligible swap exists or the explicit choice
                parameters are ineligible.
        """
        pair = self._select_pair(parent, params, rng)
        candidate = resync_metadata(_apply_swap(parent, pair))
        reguide = _reguide_items(parent, pair)
        note = (
            f"M1 sibling-subtree swap: choice '{pair.choice1_id}' on "
            f"'{pair.node1_id}' retargeted to '{pair.root2}'; choice "
            f"'{pair.choice2_id}' on '{pair.node2_id}' retargeted to '{pair.root1}'"
        )
        return MutationResult(candidate=candidate, reguide=reguide, notes=(note,))

    def _select_pair(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> _SwapPair:
        """Resolve the swap from explicit parameters or the seeded rng.

        Args:
            parent: The raw parent story document.
            params: The operator parameters.
            rng: The injected random source.

        Returns:
            _SwapPair: The validated swap.

        Raises:
            ValidationError: If the explicit parameters are ineligible or no
                eligible swap exists.
        """
        choice1 = params.get("choice1")
        choice2 = params.get("choice2")
        if choice1 is not None or choice2 is not None:
            if not (isinstance(choice1, str) and isinstance(choice2, str)):
                raise ValidationError(
                    _CHOICE_PARAMS_MSG, field="choice1", value=choice1
                )
            pair, reason = _evaluate_pair(parent, choice1, choice2)
            if pair is None:
                msg = f"M1 swap ({choice1}, {choice2}) is ineligible: {reason}"
                raise ValidationError(msg, field="choice1", value=choice1)
            return pair
        # Reproducible selection without evaluating every pair: shuffle the cheap
        # candidate list under the seeded rng, then return the first that passes
        # full evaluation. Same seed => same order => same first-passing pair.
        candidates = _cheap_candidate_pairs(parent)
        rng.shuffle(candidates)
        for choice_a, choice_b in candidates:
            pair, _reason = _evaluate_pair(parent, choice_a, choice_b)
            if pair is not None:
                return pair
        msg = "M1 found no eligible sibling-subtree swap for this parent"
        raise ValidationError(msg, field="parent", value=None)


# Register the singleton M1 operator in the default catalog registry. Import of
# this module is the registration side effect the CLI relies on.
M1 = REGISTRY.register(M1SiblingSubtreeSwap())
