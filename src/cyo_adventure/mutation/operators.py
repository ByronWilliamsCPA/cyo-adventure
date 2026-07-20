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
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import networkx as nx

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.identity import (
    host_id_namespace,
    recompute_tier,
    rename_region,
    resync_metadata,
)
from cyo_adventure.mutation.ops import (
    REGISTRY,
    MutationResult,
    OpParams,
    PreconditionReport,
    ReguideItem,
    ReguideTarget,
)
from cyo_adventure.mutation.subtree import (
    Subtree,
    adjacency,
    extract_subtree,
    node_ids,
)
from cyo_adventure.storybook.theme_contract import (
    SLOT_TOKEN_RE,
    SlotConstraints,
    SlotSpec,
    ThemeContract,
)
from cyo_adventure.validator.band_profile import (
    breadth_scaled_floors,
    min_complete_floor,
    profile_for,
)
from cyo_adventure.validator.layer1 import ScalePlacement, resolve_node_budget

if TYPE_CHECKING:
    import random
    from collections.abc import Callable, Mapping

    # A donor resolver maps a catalog slug to its decoded skeleton document. M3's
    # graft loads a donor through one of these; the default reads the git-versioned
    # catalog, and tests inject an in-memory resolver to keep the operator pure.
    DonorResolver = Callable[[str], dict[str, object]]

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

# The M2 operator id, recorded in every lineage manifest and used as the registry
# key. Kept as a module constant so the CLI and tests never spell the string
# literal.
M2_OP_ID = "M2"

# The valence classes in a fixed canonical order, so any seeded selection over
# them is reproducible. Matches ``storybook.models.Valence`` declaration order.
_VALENCE_ORDER: tuple[str, ...] = ("positive", "neutral", "negative")

# The bounded number of seeded permutation attempts M2's rng path makes per
# valence class before moving on. Exhaustive enumeration is intractable on a
# large-valence-class parent (a 28-ending Tier-2 skeleton has 28! permutations
# of one class), so M2 samples seeded shuffles instead, staying fully
# reproducible per seed while bounded in cost; a deterministic transposition
# fallback (``_first_transposition_plan``) guarantees apply succeeds whenever the
# preconditions passed.
_M2_RNG_ATTEMPTS = 128

# Static M2 precondition and error messages, kept as single-line module
# constants so a long fixed string never needs a plain-string line wrap.
_M2_SERIES_MSG = "M2 requires metadata.series to be None; series books are out of scope"
_M2_PRODUCTION_ONLY_MSG = (
    "M2 requires a production-eligible parent; MVP seeds are out of scope"
)
_M2_NO_REMAP_MSG = (
    "no valence class admits a meaningful ending re-map (a class needs >= 2 "
    "distinct ending kinds and a permutation that holds the PL-20 arc floor)"
)
_M2_PARAMS_MSG = (
    "M2 requires both 'valence' (a valence class) and 'order' (a comma-separated "
    "ending-id permutation of that class)"
)


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


# --- M2: ending re-map within a valence class (design section 4.3) ---
#
# Ending-id interpretation (design section 4.3, "ending ids stay with their
# payloads"): M2 permutes whole ending payloads. The payload it relocates is the
# entire ``ending`` block ``(id, valence, kind, title)`` moved as one unit over
# the ending-node positions of a single valence class, so the ending id travels
# WITH its ``(kind, title)`` payload rather than staying pinned to a node
# position (payload-follows-id). This is chosen precisely because a permutation
# of whole blocks is a bijection over the parent's existing ending ids, so id
# uniqueness is preserved by construction (no ``m<k>_`` renaming is needed and
# the schema's ``_check_unique_ids`` never fires). ``valence`` moves as part of
# the block, but because M2 only ever permutes WITHIN one valence class every
# block in the permuted set carries the same valence, so "valence stays with the
# leaf position" holds automatically: only ``kind`` and ``title`` (a title
# template's ``{SLOT}`` included) actually change at any position.


@dataclass(frozen=True, slots=True)
class _EndingLeaf:
    """An ending node and the payload M2 may relocate.

    Attributes:
        node_id: The ending node's id (fixed to its graph position).
        ending_id: The ending block's id (travels with the payload).
        kind: The ending kind (part of the moved payload).
        valence: The ending valence (invariant within a permuted class).
        title: The ending title or title template (part of the moved payload).
        ending: The full ending block, relocated as a unit so the ending id
            stays with its ``(kind, title)`` payload (design section 4.3).
    """

    node_id: str
    ending_id: str
    kind: str
    valence: str
    title: str
    ending: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _RemapPlan:
    """A validated within-valence permutation of ending payloads.

    Attributes:
        valence: The valence class being permuted.
        assignment: ``(node_id, source_ending_id)`` pairs in node-id order; the
            ending block whose id is ``source_ending_id`` lands on ``node_id``.
    """

    valence: str
    assignment: tuple[tuple[str, str], ...]


def _ending_leaves(story: Mapping[str, object]) -> list[_EndingLeaf]:
    """Return every well-formed ending leaf in the story, in file order.

    Args:
        story: The raw story document.

    Returns:
        list[_EndingLeaf]: One entry per ending node whose block carries an id,
            kind, valence, and title; malformed entries are skipped.
    """
    leaves: list[_EndingLeaf] = []
    for node in _nodes_of(story):
        if node.get("is_ending") is not True:
            continue
        node_id = _str_field(node, "id")
        ending = node.get("ending")
        if node_id is None or not isinstance(ending, dict):
            continue
        ending_map = cast("Mapping[str, object]", ending)
        ending_id = _str_field(ending_map, "id")
        kind = _str_field(ending_map, "kind")
        valence = _str_field(ending_map, "valence")
        title = _str_field(ending_map, "title")
        if ending_id is None or kind is None or valence is None or title is None:
            continue
        leaves.append(
            _EndingLeaf(
                node_id=node_id,
                ending_id=ending_id,
                kind=kind,
                valence=valence,
                title=title,
                ending=ending_map,
            )
        )
    return leaves


def _valence_classes(story: Mapping[str, object]) -> dict[str, list[_EndingLeaf]]:
    """Return the ending leaves grouped by valence, each sorted by node id.

    Args:
        story: The raw story document.

    Returns:
        dict[str, list[_EndingLeaf]]: Each valence value mapped to its ending
            leaves, in canonical (node-id) order so a permutation is a pure
            function of the class contents.
    """
    classes: dict[str, list[_EndingLeaf]] = {}
    for leaf in _ending_leaves(story):
        classes.setdefault(leaf.valence, []).append(leaf)
    for leaves in classes.values():
        leaves.sort(key=lambda leaf: leaf.node_id)
    return classes


def _eligible_valences(story: Mapping[str, object]) -> list[str]:
    """Return the valence classes that admit a meaningful permutation, canonically.

    A class is eligible only when it has at least two endings and at least two
    distinct ending kinds; otherwise the only permutation leaves every kind in
    place (an identity / no-op re-map).

    Args:
        story: The raw story document.

    Returns:
        list[str]: The eligible valence values, in :data:`_VALENCE_ORDER`.
    """
    classes = _valence_classes(story)
    eligible: list[str] = []
    for valence in _VALENCE_ORDER:
        leaves = classes.get(valence)
        if leaves is None or len(leaves) < 2:
            continue
        if len({leaf.kind for leaf in leaves}) >= 2:
            eligible.append(valence)
    return eligible


def _build_plan(
    class_leaves: list[_EndingLeaf], order_ids: list[str]
) -> _RemapPlan | str:
    """Build a re-map plan assigning each class node a source ending block.

    Args:
        class_leaves: The valence class's leaves, in node-id order.
        order_ids: The source ending id for each node position, in the same
            order; must be a permutation of the class's own ending ids.

    Returns:
        _RemapPlan | str: The plan, or a reason the ``order`` is not a valid
            permutation of the class.
    """
    class_ids = [leaf.ending_id for leaf in class_leaves]
    if len(order_ids) != len(class_ids) or sorted(order_ids) != sorted(class_ids):
        return (
            "order must be a permutation of exactly the valence class's ending "
            f"ids {sorted(class_ids)}"
        )
    assignment = tuple(
        (leaf.node_id, source)
        for leaf, source in zip(class_leaves, order_ids, strict=True)
    )
    return _RemapPlan(valence=class_leaves[0].valence, assignment=assignment)


def _is_meaningful(class_leaves: list[_EndingLeaf], plan: _RemapPlan) -> bool:
    """Return whether the plan changes at least one leaf's ending kind.

    Moving a payload whose kind equals the kind already at a position is not a
    diversity change (design section 4.3: the payoff is decoupling which route
    carries which mechanical outcome), so a permutation that relocates only
    same-kind blocks is treated as an identity / no-op re-map and rejected.

    Args:
        class_leaves: The valence class's leaves, in node-id order.
        plan: The candidate permutation.

    Returns:
        bool: True when some node's post-remap kind differs from its original.
    """
    kind_by_ending = {leaf.ending_id: leaf.kind for leaf in class_leaves}
    original_kind_at_node = {leaf.node_id: leaf.kind for leaf in class_leaves}
    return any(
        kind_by_ending[source] != original_kind_at_node[node_id]
        for node_id, source in plan.assignment
    )


def _post_remap_satisfying_ids(
    story: Mapping[str, object], plan: _RemapPlan
) -> set[str]:
    """Return the ending node ids that hold a satisfying kind AFTER the re-map.

    The graph is untouched by M2; only which node carries a success/completion
    kind can change, so the PL-20 target set is recomputed from the plan.

    Args:
        story: The raw parent story document.
        plan: The candidate permutation.

    Returns:
        set[str]: Node ids whose post-remap ending kind is success/completion.
    """
    kind_by_ending = {leaf.ending_id: leaf.kind for leaf in _ending_leaves(story)}
    new_kind_at_node = {
        node_id: kind_by_ending[source] for node_id, source in plan.assignment
    }
    targets: set[str] = set()
    for leaf in _ending_leaves(story):
        kind = new_kind_at_node.get(leaf.node_id, leaf.kind)
        if kind in _SATISFYING_KINDS:
            targets.add(leaf.node_id)
    return targets


def _pl20_remap_reason(story: Mapping[str, object], plan: _RemapPlan) -> str | None:
    """Return the post-remap PL-20 failure reason, or None when the floor holds.

    Args:
        story: The raw parent story document.
        plan: The candidate permutation.

    Returns:
        str | None: A reason when the re-map would put a satisfying ending below
            the cell's arc floor, else None.
    """
    # #CRITICAL: security: PL-20 is the fastest-finish arc floor, the one clock a
    # pure ending permutation can break. Moving a success/completion kind onto a
    # shallower leaf is the only way M2 can shorten the structural path to a
    # satisfying ending, so the check recomputes the satisfying target set from
    # the plan and compares the shortest start-to-target node count against the
    # inherited floor, discarding PRE-GATE when it drops below (direction:
    # shortest < floor is the failure). The unchanged gate re-proves PL-20 at
    # stage 1 regardless; this pre-check only avoids a wasted gate run.
    # #VERIFY: tests/unit/test_mutation_m2.py pins a crafted parent where moving a
    # success ending onto a shallow leaf is rejected at preconditions with a
    # PL-20 reason, and the multiset-invariance property proves the gate never
    # blocks an accepted M2 output.
    floor = _pl20_floor(story)
    if floor is None:
        return None
    start = _str_field(story, "start_node")
    graph = _parent_graph(story)
    targets = _post_remap_satisfying_ids(story, plan)
    shortest = _shortest_satisfying_nodes(graph, start, targets)
    if shortest is not None and shortest < floor:
        return (
            f"post-remap shortest satisfying path is {shortest} node(s), below the "
            f"PL-20 floor {floor}"
        )
    return None


def _evaluate_remap(
    story: Mapping[str, object], valence: str, order_ids: list[str]
) -> tuple[_RemapPlan | None, str | None]:
    """Validate a candidate re-map of one valence class (design section 4.3).

    Runs the precondition set: the class exists and has >= 2 leaves, the order is
    a valid permutation of the class, the permutation is meaningful (changes some
    kind), and the post-remap PL-20 arc floor holds.

    Args:
        story: The raw parent story document.
        valence: The valence class to permute.
        order_ids: The source ending id for each class node position.

    Returns:
        tuple[_RemapPlan | None, str | None]: ``(plan, None)`` when eligible,
            else ``(None, reason)``.
    """
    classes = _valence_classes(story)
    class_leaves = classes.get(valence)
    if class_leaves is None or len(class_leaves) < 2:
        return None, f"valence class '{valence}' has fewer than 2 endings to permute"
    plan_or_reason = _build_plan(class_leaves, order_ids)
    if isinstance(plan_or_reason, str):
        return None, plan_or_reason
    plan = plan_or_reason
    if not _is_meaningful(class_leaves, plan):
        return (
            None,
            "the permutation changes no ending kind (an identity / no-op re-map)",
        )
    reason = _pl20_remap_reason(story, plan)
    if reason is not None:
        return None, reason
    return plan, None


def _first_transposition_plan(story: Mapping[str, object]) -> _RemapPlan | None:
    """Return the first eligible two-leaf swap, or None when none exists.

    Enumerates, in canonical order, the differing-kind leaf pairs of each
    eligible valence class and returns the first whose transposition passes full
    evaluation. Used both to prove eligibility cheaply in ``preconditions`` and
    as the deterministic fallback that guarantees ``apply`` succeeds whenever the
    preconditions passed.

    Args:
        story: The raw parent story document.

    Returns:
        _RemapPlan | None: The first eligible transposition, or None.
    """
    classes = _valence_classes(story)
    for valence in _eligible_valences(story):
        leaves = classes[valence]
        base_ids = [leaf.ending_id for leaf in leaves]
        for i, leaf_i in enumerate(leaves):
            for j in range(i + 1, len(leaves)):
                if leaf_i.kind == leaves[j].kind:
                    continue
                order_ids = list(base_ids)
                order_ids[i], order_ids[j] = order_ids[j], order_ids[i]
                plan, _reason = _evaluate_remap(story, valence, order_ids)
                if plan is not None:
                    return plan
    return None


def _rng_plan_for_class(
    story: Mapping[str, object], class_leaves: list[_EndingLeaf], rng: random.Random
) -> _RemapPlan | None:
    """Return a seeded, eligible permutation of one valence class, or None.

    Samples up to :data:`_M2_RNG_ATTEMPTS` seeded shuffles of the class's ending
    ids and returns the first that passes full evaluation. Deterministic for a
    given rng state.

    Args:
        story: The raw parent story document.
        class_leaves: The valence class's leaves, in node-id order.
        rng: The injected random source.

    Returns:
        _RemapPlan | None: An eligible permutation, or None after the attempt cap.
    """
    base_ids = [leaf.ending_id for leaf in class_leaves]
    valence = class_leaves[0].valence
    for _attempt in range(_M2_RNG_ATTEMPTS):
        order_ids = list(base_ids)
        rng.shuffle(order_ids)
        plan, _reason = _evaluate_remap(story, valence, order_ids)
        if plan is not None:
            return plan
    return None


def _parse_order(order: str) -> list[str]:
    """Parse a comma-separated ``order`` parameter into ending ids."""
    return [token.strip() for token in order.split(",") if token.strip()]


def _predecessors(story: Mapping[str, object]) -> dict[str, list[str]]:
    """Return each node id mapped to the node ids that offer a choice into it."""
    reverse: dict[str, list[str]] = {}
    for source, targets in adjacency(story).items():
        for target in targets:
            reverse.setdefault(target, []).append(source)
    return reverse


def _remap_reguide_items(
    parent: Mapping[str, object], plan: _RemapPlan
) -> tuple[ReguideItem, ...]:
    """Return the re-guidance items a re-map invalidates (design section 4.3).

    For every leaf whose payload changed: the ending's title (or template) and
    the leaf's own entry beats now describe a different outcome. The approach
    nodes immediately upstream are emitted as advisory re-guidance items (their
    lead-in beats may telegraph the old outcome), matching M1's single re-guidance
    channel while marking the advisory ones in their reason text.

    Args:
        parent: The raw parent story document.
        plan: The validated permutation.

    Returns:
        tuple[ReguideItem, ...]: The ending-title and leaf-beat items for each
            affected leaf, then the advisory upstream-approach items.
    """
    classes = _valence_classes(parent)
    class_leaves = classes[plan.valence]
    original_id_at_node = {leaf.node_id: leaf.ending_id for leaf in class_leaves}
    source_by_id = {leaf.ending_id: leaf for leaf in _ending_leaves(parent)}
    ending_reason = (
        "ending re-mapped onto a different route; re-check its title (or template) "
        "for the new approach"
    )
    beat_reason = (
        "leaf beats were authored for the old outcome; re-check the entry beat for "
        "the re-mapped ending"
    )
    upstream_reason = (
        "advisory: this approach node leads into a re-mapped outcome; re-check the "
        "lead-in beats"
    )
    items: list[ReguideItem] = []
    affected_nodes: list[str] = []
    for node_id, source in plan.assignment:
        if source == original_id_at_node[node_id]:
            continue
        affected_nodes.append(node_id)
        moved = source_by_id[source]
        items.append(
            ReguideItem(
                target=ReguideTarget.ENDING,
                target_id=moved.ending_id,
                reason=ending_reason,
                current_text=moved.title,
            )
        )
        items.append(
            ReguideItem(
                target=ReguideTarget.NODE,
                target_id=node_id,
                reason=beat_reason,
                current_text=_node_body(parent, node_id),
            )
        )
    predecessors = _predecessors(parent)
    seen_upstream: set[str] = set()
    for node_id in affected_nodes:
        for pred in sorted(predecessors.get(node_id, ())):
            if pred in seen_upstream:
                continue
            seen_upstream.add(pred)
            items.append(
                ReguideItem(
                    target=ReguideTarget.NODE,
                    target_id=pred,
                    reason=upstream_reason,
                    current_text=_node_body(parent, pred),
                )
            )
    return tuple(items)


def _moved_count(parent: Mapping[str, object], plan: _RemapPlan) -> int:
    """Return how many class leaves receive a different ending block than before."""
    original_id_at_node = {
        leaf.node_id: leaf.ending_id for leaf in _valence_classes(parent)[plan.valence]
    }
    return sum(
        1
        for node_id, source in plan.assignment
        if source != original_id_at_node[node_id]
    )


def _apply_remap(parent: Mapping[str, object], plan: _RemapPlan) -> dict[str, object]:
    """Return a deep copy of ``parent`` with one valence class's endings permuted.

    Args:
        parent: The raw parent story document (never mutated).
        plan: The validated permutation.

    Returns:
        dict[str, object]: The candidate graph, pre-metadata-resync.

    Raises:
        ValidationError: If the parent has no node list.
    """
    # #CRITICAL: data-integrity: M2 is a permutation of ending payloads, so the
    # (kind, valence) ending multiset is invariant by construction, which is the
    # safety property that keeps PL-15 (forbidden kinds), PL-16, and PL-17
    # unaffected: no kind or valence that was not already in the parent's ending
    # set can appear in the candidate. Whole blocks are relocated within one
    # valence class, so ending ids stay unique (a bijection over existing ids) and
    # every leaf keeps its valence. The unchanged gate re-proves PL-15/16/17 at
    # stage 1 regardless.
    # #VERIFY: tests/unit/test_mutation_m2.py proves, over the catalog, that the
    # (kind, valence) multiset is invariant, that no candidate introduces a kind
    # absent from the parent, and that run_gate never blocks an accepted output.
    candidate = copy.deepcopy(dict(parent))
    nodes = candidate.get("nodes")
    if not isinstance(nodes, list):
        msg = "parent story has no nodes list to re-map"
        raise ValidationError(msg, field="nodes", value=None)
    source_blocks = {leaf.ending_id: leaf.ending for leaf in _ending_leaves(parent)}
    new_block_for_node = {
        node_id: copy.deepcopy(dict(source_blocks[source]))
        for node_id, source in plan.assignment
    }
    for raw_node in cast("list[object]", nodes):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        node_id = node.get("id")
        if isinstance(node_id, str) and node_id in new_block_for_node:
            node["ending"] = new_block_for_node[node_id]
    return candidate


class M2EndingReMap:
    """M2: permute ending payloads within one valence class (design section 4.3).

    A permutation of ending payloads ``(kind, title or title template)`` over the
    terminal nodes of ONE valence class: positive endings permute among
    positives, negative among negatives, neutral among neutrals. The valence
    field stays with the leaf position and the ``(kind, valence)`` ending multiset
    is invariant by construction, so the fail-state policy surface (PL-15/16/17)
    is untouched; only the PL-20 arc floor can move, and the operator pre-checks
    it. The whole ending block is relocated, so the ending id stays with its
    payload and id uniqueness is preserved (see the module note above).

    Composition-only (design section 4.3, "Composition note"): because
    ``diversity.structure.structure_fingerprint`` strips ending titles and
    ``structural_distance``'s ending histograms are aggregate/position-blind, an
    M2-only mutant leaves every structural feature identical to its parent, so
    ``structural_distance(parent, mutant)`` is ~0 and the D7 anti-clone floor will
    (correctly) reject a standalone M2 mutant. M2's payoff is as a COMPOSITION
    operator riding with M1/M3/M4: applied to another operator's candidate it
    decouples "which route" from "which outcome". The D7 floor does not exist yet,
    so M2 adds no floor now; a length-2 chain is just applying M2 to M1's
    ``result.candidate`` (the ``op_chain`` lineage schema is D8).

    The permutation is selected either from explicit ``valence``/``order``
    parameters or, when those are absent, reproducibly from the seeded rng over a
    valence class chosen canonically; the same seed/params yield a byte-identical
    candidate.
    """

    op_id: str = M2_OP_ID

    def preconditions(
        self, parent: Mapping[str, object], params: OpParams
    ) -> PreconditionReport:
        """Return whether M2 may attempt a re-map on ``parent`` (design section 4.3).

        Args:
            parent: The raw parent story document.
            params: The operator parameters (optional ``valence``/``order``).

        Returns:
            PreconditionReport: Satisfied when a re-map is eligible, else a report
                carrying every failing reason.
        """
        failures: list[str] = []
        meta = _metadata_of(parent)
        if meta.get("series") is not None:
            failures.append(_M2_SERIES_MSG)
        if meta.get("production_eligible") is False:
            failures.append(_M2_PRODUCTION_ONLY_MSG)

        valence = params.get("valence")
        order = params.get("order")
        if valence is not None or order is not None:
            if not (isinstance(valence, str) and isinstance(order, str)):
                failures.append(_M2_PARAMS_MSG)
            else:
                _plan, reason = _evaluate_remap(parent, valence, _parse_order(order))
                if reason is not None:
                    failures.append(
                        f"re-map (valence={valence}) is ineligible: {reason}"
                    )
        elif _first_transposition_plan(parent) is None:
            failures.append(_M2_NO_REMAP_MSG)

        if failures:
            return PreconditionReport.failed(*failures)
        return PreconditionReport.passed()

    def apply(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> MutationResult:
        """Apply the re-map and return the resynced candidate plus its re-guidance.

        Args:
            parent: The raw parent story document (never mutated).
            params: The operator parameters (optional ``valence``/``order``).
            rng: The injected random source; a recorded seed reproduces the exact
                candidate when the permutation is rng-selected.

        Returns:
            MutationResult: The candidate (metadata resynced) and its re-guidance
                items.

        Raises:
            ValidationError: If no eligible re-map exists or the explicit
                parameters are ineligible.
        """
        plan = self._select_plan(parent, params, rng)
        candidate = resync_metadata(_apply_remap(parent, plan))
        reguide = _remap_reguide_items(parent, plan)
        moved = _moved_count(parent, plan)
        note = (
            f"M2 ending re-map on the '{plan.valence}' valence class: {moved} "
            f"leaf outcome(s) permuted within the class"
        )
        return MutationResult(candidate=candidate, reguide=reguide, notes=(note,))

    def _select_plan(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> _RemapPlan:
        """Resolve the re-map from explicit parameters or the seeded rng.

        Args:
            parent: The raw parent story document.
            params: The operator parameters.
            rng: The injected random source.

        Returns:
            _RemapPlan: The validated permutation.

        Raises:
            ValidationError: If the explicit parameters are ineligible or no
                eligible re-map exists.
        """
        valence = params.get("valence")
        order = params.get("order")
        if valence is not None or order is not None:
            if not (isinstance(valence, str) and isinstance(order, str)):
                raise ValidationError(_M2_PARAMS_MSG, field="valence", value=valence)
            plan, reason = _evaluate_remap(parent, valence, _parse_order(order))
            if plan is None:
                msg = f"M2 re-map (valence={valence}) is ineligible: {reason}"
                raise ValidationError(msg, field="order", value=order)
            return plan
        # Reproducible selection: shuffle the eligible valence classes under the
        # seeded rng, sample seeded permutations of the first that yields one, and
        # fall back to the deterministic first transposition so apply always
        # succeeds when the preconditions passed. Same seed => same result.
        classes = _valence_classes(parent)
        eligible = _eligible_valences(parent)
        rng.shuffle(eligible)
        for valence_choice in eligible:
            plan = _rng_plan_for_class(parent, classes[valence_choice], rng)
            if plan is not None:
                return plan
        fallback = _first_transposition_plan(parent)
        if fallback is not None:
            return fallback
        msg = "M2 found no eligible ending re-map for this parent"
        raise ValidationError(msg, field="parent", value=None)


# Register the singleton M2 operator in the default catalog registry alongside M1.
M2 = REGISTRY.register(M2EndingReMap())


# --- M3: prune/graft within the cell envelope (design section 4.4) ---
#
# One operator, two sub-operations selected by the ``mode`` parameter
# ("prune" or "graft"), matching the single-op-per-op-id shape M1/M2 use. D4 is
# Tier-1 only, over closed self-contained subtrees, with same-band donors, and
# grafts only variable-free/effect-free/condition-free regions (stateful grafts
# are deferred to the composer, design 4.4). The WS-5 envelope is treated as
# two-sided and blocking at acceptance: a prune may not exit the cell minimum and
# a graft may not exit the cell maximum, even though L1-7 only WARNs below-min.

# The M3 operator id, recorded in every lineage manifest and used as the registry
# key. Kept as a module constant so the CLI and tests never spell the literal.
M3_OP_ID = "M3"

# The two M3 sub-operation modes.
_M3_MODE_PRUNE = "prune"
_M3_MODE_GRAFT = "graft"

# ADR-011 section 6 choices-per-decision window (2-3). The gate does not
# hard-enforce choices-per-decision (design 4.8), so M3 self-enforces it as a
# graft precondition: adding the new choice must leave d within this window.
_MIN_CHOICES_PER_DECISION = 2
_MAX_CHOICES_PER_DECISION = 3

# ADR-011 section 6 prose ending-ratio band (~15-22% terminals). M3 prune treats
# this as ADVISORY only (a recorded note), never a discard, per design 4.4.
_ENDING_RATIO_LO = 0.15
_ENDING_RATIO_HI = 0.22

# The FILL directive parse, mirrored from ``generation.binding._FILL_RE`` and
# ``validator.policy`` (a local copy keeps the mutation layer from importing the
# generation layer). Used to isolate the ``beats='...'`` segment when a graft
# renames a donor region's ``{SLOT}`` tokens.
_M3_FILL_RE = re.compile(r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$", re.DOTALL)

# The placeholder label a graft's new choice carries until a reviewer authors it
# (emitted as a re-guidance item; the schema requires a non-empty label).
_M3_GRAFT_LABEL = "(graft seam: re-author this choice label)"

# Static M3 precondition and error messages.
_M3_TIER1_ONLY_MSG = (
    "M3 (D4) is restricted to Tier-1 parents; stateful grafts are deferred to the "
    "composer"
)
_M3_SERIES_MSG = "M3 requires metadata.series to be None; series books are out of scope"
_M3_PRODUCTION_ONLY_MSG = (
    "M3 requires a production-eligible parent; MVP seeds are out of scope"
)
_M3_MODE_MSG = "M3 requires a 'mode' parameter of 'prune' or 'graft'"
_M3_PRUNE_PARAMS_MSG = (
    "M3 prune's optional 'choice' parameter must be a choice id string"
)
_M3_GRAFT_PARAMS_MSG = (
    "M3 graft requires 'subtree_root' and 'host_decision' id parameters"
)
_M3_DONOR_PARAM_MSG = "M3 graft's optional 'donor' parameter must be a slug string"


def _node_by_id(
    story: Mapping[str, object], node_id: str
) -> Mapping[str, object] | None:
    """Return the node dict with ``node_id``, or None when absent."""
    for node in _nodes_of(story):
        if _str_field(node, "id") == node_id:
            return node
    return None


def _in_degree(story: Mapping[str, object], node_id: str) -> int:
    """Return how many choice edges target ``node_id`` (existing targets only)."""
    count = 0
    for targets in adjacency(story).values():
        count += sum(1 for target in targets if target == node_id)
    return count


def _ending_node_ids(story: Mapping[str, object]) -> set[str]:
    """Return the ids of every ending node in the story."""
    ids: set[str] = set()
    for node in _nodes_of(story):
        if node.get("is_ending") is not True:
            continue
        node_id = _str_field(node, "id")
        if node_id is not None:
            ids.add(node_id)
    return ids


def _cell_node_bounds(story: Mapping[str, object]) -> tuple[int, int] | None:
    """Return the inherited cell's ``(min_nodes, max_nodes)`` envelope, or None.

    Reuses ``validator.layer1.resolve_node_budget`` (the single budget path L1-7
    uses); index 0 is the envelope minimum and index 1 the maximum, so the WS-5
    two-sided check reads exactly the bounds the gate reads.
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
    if budget is None:
        return None
    return budget[0], budget[1]


def _min_endings_floor(story: Mapping[str, object], node_count: int) -> int:
    """Return the effective PL-17 min-endings floor for a given node count.

    Mirrors ``validator.policy._effective_floors``: the band floor, raised to the
    breadth-scaled floor for a scale-classified production story so a large world
    cannot pass with the band minimum. The node count is a parameter so a prune
    can evaluate the floor against its shrunken post-prune graph.
    """
    meta = _metadata_of(story)
    band = _str_field(meta, "age_band")
    profile = profile_for(band) if band is not None else None
    base = profile.min_endings if profile is not None else 0
    length = _str_field(meta, "length")
    style = _str_field(meta, "narrative_style") or "prose"
    if length is not None and meta.get("production_eligible") is not False:
        scaled_endings, _scaled_decisions = breadth_scaled_floors(node_count, style)
        return max(base, scaled_endings)
    return base


def _min_decisions_floor(story: Mapping[str, object], node_count: int) -> int:
    """Return the effective PL-17 min-decisions floor for a given node count."""
    meta = _metadata_of(story)
    band = _str_field(meta, "age_band")
    profile = profile_for(band) if band is not None else None
    base = profile.min_decisions if profile is not None else 0
    length = _str_field(meta, "length")
    style = _str_field(meta, "narrative_style") or "prose"
    if length is not None and meta.get("production_eligible") is not False:
        _scaled_endings, scaled_decisions = breadth_scaled_floors(node_count, style)
        return max(base, scaled_decisions)
    return base


def _region_cleanliness_reason(
    story: Mapping[str, object], region_ids: frozenset[str]
) -> str | None:
    """Return why a region is not graft-eligible, or None when it is clean.

    D4 grafts only variable-free, effect-free, condition-free subtrees (design
    4.4): merging state namespaces is composition, not mutation, so a region that
    carries an ``on_enter`` effect, a choice ``effect``, or a choice ``condition``
    is rejected here. A condition/effect is the only way a region references a
    variable, so this scan is the complete state-freeness check.

    Args:
        story: The donor story document.
        region_ids: The node ids forming the candidate graft region.

    Returns:
        str | None: The first disqualifying reason, or None when clean.
    """
    # #CRITICAL: data-integrity: the state-freeness scan is the load-bearing D4
    # graft precondition. Grafting a region that mutates or reads state would
    # import a variable namespace the host never declared, stranding
    # configurations the Tier-1 host cannot represent; v1 forbids it outright and
    # defers stateful grafts to the composer. The gate's L1-6 is the fail-closed
    # backstop (an effect on an undeclared variable blocks), but the operator must
    # never attempt the move.
    # #VERIFY: tests/unit/test_mutation_m3.py pins that a region carrying an
    # on_enter effect, a choice effect, or a choice condition is rejected.
    for node in _nodes_of(story):
        node_id = _str_field(node, "id")
        if node_id is None or node_id not in region_ids:
            continue
        on_enter = node.get("on_enter")
        if isinstance(on_enter, list) and on_enter:
            return f"graft region node '{node_id}' carries on_enter effects (v1 is state-free)"
        for choice in _choices_of(node):
            if choice.get("condition") is not None:
                return (
                    f"graft region choice in node '{node_id}' carries a condition "
                    f"(v1 is condition-free)"
                )
            effects = choice.get("effects")
            if isinstance(effects, list) and effects:
                return (
                    f"graft region choice in node '{node_id}' carries effects "
                    f"(v1 is effect-free)"
                )
    return None


def region_referenced_slots(nodes: list[Mapping[str, object]]) -> frozenset[str]:
    """Return the ``{SLOT}`` tokens a region references in its three surfaces.

    The three slotted surfaces are exactly those ADR-019 permits: the
    ``beats='...'`` segment of a ``<<FILL ...>>`` node body, an ending ``title``,
    and a choice ``label``. Used both to rename a grafted region's tokens and to
    drive the contract-merge transform (design 4.4).

    Args:
        nodes: The region's node dicts.

    Returns:
        frozenset[str]: The slot ids referenced anywhere in the region.
    """
    tokens: set[str] = set()
    for node in nodes:
        body = _str_field(node, "body")
        if body is not None:
            match = _M3_FILL_RE.match(body)
            if match is not None:
                tokens.update(SLOT_TOKEN_RE.findall(match.group(3)))
        ending = node.get("ending")
        if isinstance(ending, dict):
            title = _str_field(cast("Mapping[str, object]", ending), "title")
            if title is not None:
                tokens.update(SLOT_TOKEN_RE.findall(title))
        for choice in _choices_of(node):
            label = _str_field(choice, "label")
            if label is not None:
                tokens.update(SLOT_TOKEN_RE.findall(label))
    return frozenset(tokens)


def graft_slot_id(slot_id: str, k: int) -> str:
    """Return the ``M<k>_<SLOT>`` renamed slot id for a grafted slot (design 4.4)."""
    return f"M{k}_{slot_id}"


def _rename_slot_tokens_in_text(text: str, k: int) -> str:
    """Rewrite every ``{SLOT}`` token in ``text`` to ``{M<k>_SLOT}`` form."""
    return SLOT_TOKEN_RE.sub(lambda m: "{" + graft_slot_id(m.group(1), k) + "}", text)


def _rename_region_slot_tokens(nodes: list[dict[str, object]], k: int) -> None:
    """Rename a grafted region's ``{SLOT}`` tokens to ``M<k>_`` form, in place.

    Keeps the mutant's slotted surfaces consistent with the merged contract's
    renamed slot ids so ``load_contract_for``'s token-set equality holds. Only the
    beats segment inside an intact FILL directive is rewritten (role/words are
    reconstructed, never regex-substituted), plus every ending title and choice
    label; a non-FILL body is left untouched.

    Args:
        nodes: The renamed region node dicts (mutated in place).
        k: The mutation index used in the ``M<k>_`` prefix.
    """
    for node in nodes:
        body = node.get("body")
        if isinstance(body, str):
            match = _M3_FILL_RE.match(body)
            if match is not None:
                role, words, beats = match.group(1), match.group(2), match.group(3)
                new_beats = _rename_slot_tokens_in_text(beats, k)
                node["body"] = f"<<FILL role={role} words={words} beats='{new_beats}'>>"
        ending = node.get("ending")
        if isinstance(ending, dict):
            ending_map = cast("dict[str, object]", ending)
            title = ending_map.get("title")
            if isinstance(title, str):
                ending_map["title"] = _rename_slot_tokens_in_text(title, k)
        raw_choices = node.get("choices")
        if isinstance(raw_choices, list):
            for raw_choice in cast("list[object]", raw_choices):
                if not isinstance(raw_choice, dict):
                    continue
                choice = cast("dict[str, object]", raw_choice)
                label = choice.get("label")
                if isinstance(label, str):
                    choice["label"] = _rename_slot_tokens_in_text(label, k)


# --- M3 prune ---


@dataclass(frozen=True, slots=True)
class _PrunePlan:
    """A validated prune: the choice edge to cut and the subtree it roots.

    Attributes:
        choice_id: The single choice edge into the pruned subtree.
        parent_node_id: The decision node holding ``choice_id``.
        root: The pruned subtree's root node id.
        region_ids: Every node id removed by the prune (the closed subtree).
    """

    choice_id: str
    parent_node_id: str
    root: str
    region_ids: frozenset[str]


def _post_prune_decision_count(
    story: Mapping[str, object], parent_node_id: str, region: frozenset[str]
) -> int:
    """Return the decision-node count after a prune, without copying the document.

    A decision node is a non-ending node with >= 2 choices (matching
    ``validator.policy._check_floors``). Only the parent node's choice count
    changes (it loses the pruned choice); the closed region's nodes vanish.
    """
    count = 0
    for node in _nodes_of(story):
        node_id = _str_field(node, "id")
        if node_id is None or node_id in region or node.get("is_ending") is True:
            continue
        choice_count = len(_choices_of(node))
        if node_id == parent_node_id:
            choice_count -= 1
        if choice_count >= 2:
            count += 1
    return count


def _evaluate_prune(  # noqa: PLR0911 -- one cohesive precondition ladder, one reason each
    story: Mapping[str, object], choice_id: str
) -> tuple[_PrunePlan | None, str | None]:
    """Validate a prune of the subtree behind one choice edge (design 4.4).

    Runs every prune precondition in order: identity, self-containment and
    closedness, single in-edge, the parent keeping a choice, the two-sided cell
    envelope minimum, the PL-17 ending floors (count, breadth-scaled, and a
    surviving success/completion), and the PL-17 decision floor.

    Args:
        story: The raw parent story document.
        choice_id: The choice edge to cut.

    Returns:
        tuple[_PrunePlan | None, str | None]: ``(plan, None)`` when eligible,
            else ``(None, reason)``.
    """
    refs = _choice_refs(story)
    ref = refs.get(choice_id)
    if ref is None:
        return None, f"choice '{choice_id}' is not a choice in this story"
    root = ref.target
    if root not in node_ids(story):
        return None, f"prune target '{root}' does not exist"
    subtree = extract_subtree(story, root)
    if not subtree.self_contained:
        sources = [edge.source for edge in subtree.external_in_edges]
        return None, (
            f"subtree rooted at '{root}' is not self-contained "
            f"(external in-edges: {sources})"
        )
    if not subtree.closed:
        return None, (
            f"subtree rooted at '{root}' is not closed; pruning would leave "
            f"dangling out-edges"
        )
    in_degree = _in_degree(story, root)
    if in_degree != 1:
        return None, (
            f"subtree root '{root}' has {in_degree} in-edges; prune removes a "
            f"single choice edge only"
        )
    parent_node = _node_by_id(story, ref.node_id)
    if parent_node is None:
        return None, f"prune parent node '{ref.node_id}' is missing"
    if len(_choices_of(parent_node)) <= 1:
        return None, (
            f"parent decision '{ref.node_id}' would have zero choices after "
            f"removal (schema requires at least one)"
        )
    region = subtree.node_ids
    post_count = len(node_ids(story) - region)
    reason = _prune_floor_reason(story, ref.node_id, region, post_count)
    if reason is not None:
        return None, reason
    return _PrunePlan(
        choice_id=choice_id,
        parent_node_id=ref.node_id,
        root=root,
        region_ids=region,
    ), None


def _prune_floor_reason(
    story: Mapping[str, object],
    parent_node_id: str,
    region: frozenset[str],
    post_count: int,
) -> str | None:
    """Return the first envelope/floor failure a prune would cause, or None.

    Args:
        story: The raw parent story document.
        parent_node_id: The decision node losing the pruned choice.
        region: The node ids the prune removes.
        post_count: The post-prune node count.

    Returns:
        str | None: The first failing reason, or None when every floor holds.
    """
    # #CRITICAL: security: WS-5 treats the cell node envelope as two-sided and
    # BLOCKING at acceptance (design 4.4), so a prune may not drop the node count
    # below the cell minimum even though L1-7 only WARNs below-min for cell
    # budgets. Exiting the declared cell would misrepresent the story's scale to
    # selection and the reader-facing clocks; the operator rejects it here rather
    # than emit a mutant that silently changes cell.
    # #VERIFY: tests/unit/test_mutation_m3.py pins that a prune dropping below the
    # cell minimum is discarded at preconditions.
    bounds = _cell_node_bounds(story)
    if bounds is not None and post_count < bounds[0]:
        return (
            f"post-prune node count {post_count} is below the cell envelope "
            f"minimum {bounds[0]} (WS-5 two-sided blocking)"
        )
    remaining_endings = len(_ending_node_ids(story) - region)
    endings_floor = _min_endings_floor(story, post_count)
    if remaining_endings < endings_floor:
        return (
            f"post-prune endings {remaining_endings} below the PL-17 floor "
            f"{endings_floor}"
        )
    # #CRITICAL: security: a prune may never remove the last success/completion
    # ending. A story with no satisfying ending is a dead-end experience the
    # reader can never win; PL-17 requires a satisfying ending, and this operator
    # never proposes a candidate that would strip it (the gate re-proves PL-17 at
    # stage 1 regardless).
    # #VERIFY: tests/unit/test_mutation_m3.py pins that pruning the last
    # success/completion ending is discarded.
    if not (_satisfying_ending_ids(story) - region):
        return "prune would remove the last success/completion ending (PL-17)"
    post_decisions = _post_prune_decision_count(story, parent_node_id, region)
    decisions_floor = _min_decisions_floor(story, post_count)
    if post_decisions < decisions_floor:
        return (
            f"post-prune decision nodes {post_decisions} below the PL-17 floor "
            f"{decisions_floor}"
        )
    return None


def _prunable_choices(story: Mapping[str, object]) -> list[str]:
    """Return every prunable choice id, in canonical (choice-id) order."""
    prunable: list[str] = []
    for ref in sorted(_choice_refs(story).values(), key=lambda ref: ref.choice_id):
        plan, _reason = _evaluate_prune(story, ref.choice_id)
        if plan is not None:
            prunable.append(ref.choice_id)
    return prunable


def _is_choice_with_id(choice: object, choice_id: str) -> bool:
    """Return whether ``choice`` is a choice dict whose id equals ``choice_id``."""
    return (
        isinstance(choice, dict)
        and cast("dict[str, object]", choice).get("id") == choice_id
    )


def _apply_prune(parent: Mapping[str, object], plan: _PrunePlan) -> dict[str, object]:
    """Return a deep copy of ``parent`` with the pruned subtree and edge removed.

    Args:
        parent: The raw parent story document (never mutated).
        plan: The validated prune.

    Returns:
        dict[str, object]: The candidate graph, pre-metadata-resync.

    Raises:
        ValidationError: If the parent has no node list.
    """
    candidate = copy.deepcopy(dict(parent))
    nodes = candidate.get("nodes")
    if not isinstance(nodes, list):
        msg = "parent story has no nodes list to prune"
        raise ValidationError(msg, field="nodes", value=None)
    kept: list[object] = []
    for raw_node in cast("list[object]", nodes):
        if not isinstance(raw_node, dict):
            kept.append(raw_node)
            continue
        node = cast("dict[str, object]", raw_node)
        node_id = node.get("id")
        if isinstance(node_id, str) and node_id in plan.region_ids:
            continue
        if node_id == plan.parent_node_id:
            raw_choices = node.get("choices")
            if isinstance(raw_choices, list):
                node["choices"] = [
                    choice
                    for choice in cast("list[object]", raw_choices)
                    if not _is_choice_with_id(choice, plan.choice_id)
                ]
        kept.append(node)
    candidate["nodes"] = kept
    return candidate


def _ending_ratio_advisory(candidate: Mapping[str, object]) -> tuple[str, ...]:
    """Return an advisory note when the ending ratio leaves the ADR-011 band."""
    total = len(_nodes_of(candidate))
    if total == 0:
        return ()
    ratio = len(_ending_node_ids(candidate)) / total
    if _ENDING_RATIO_LO <= ratio <= _ENDING_RATIO_HI:
        return ()
    note = (
        f"advisory: post-prune ending ratio {ratio:.2f} is outside the ADR-011 "
        f"~0.15-0.22 band (non-blocking)"
    )
    return (note,)


# --- M3 graft ---


@dataclass(frozen=True, slots=True)
class _GraftPlan:
    """A validated graft of a renamed donor subtree under a new host choice.

    Attributes:
        donor_slug: The donor's catalog slug (``"<self>"`` for a same-skeleton
            graft).
        subtree_root: The donor subtree's root id (pre-rename).
        host_decision: The host decision node the new choice hangs from.
        position: The insertion index of the new choice in that node.
        k: The mutation index used in the ``m<k>_`` id / ``M<k>_`` slot prefix.
        renamed_nodes: The graft region's node dicts, ids and slot tokens renamed.
        root_new_id: The renamed graft root id (the new choice's target).
        new_choice_id: The new choice's deterministic, collision-checked id.
        new_choice_label: The placeholder label emitted as a re-guidance item.
        region_size: The number of grafted nodes.
    """

    donor_slug: str
    subtree_root: str
    host_decision: str
    position: int
    k: int
    renamed_nodes: tuple[dict[str, object], ...]
    root_new_id: str
    new_choice_id: str
    new_choice_label: str
    region_size: int


def _region_all_ids(nodes: list[Mapping[str, object]]) -> set[str]:
    """Return every node, choice, and ending id declared across a region."""
    ids: set[str] = set()
    for node in nodes:
        node_id = _str_field(node, "id")
        if node_id is not None:
            ids.add(node_id)
        for choice in _choices_of(node):
            choice_id = _str_field(choice, "id")
            if choice_id is not None:
                ids.add(choice_id)
        ending = node.get("ending")
        if isinstance(ending, dict):
            ending_id = _str_field(cast("Mapping[str, object]", ending), "id")
            if ending_id is not None:
                ids.add(ending_id)
    return ids


def _choose_graft_index(
    host_namespace: set[str], region_nodes: list[Mapping[str, object]]
) -> int:
    """Return the smallest ``k >= 1`` whose ``m<k>_`` prefix avoids all collisions.

    Deterministic: for a given host and donor region there is exactly one answer,
    so a graft is byte-reproducible. Guarantees :func:`rename_region` never has to
    raise on a host collision.
    """
    region_ids = _region_all_ids(region_nodes)
    k = 1
    while any(f"m{k}_{region_id}" in host_namespace for region_id in region_ids):
        k += 1
    return k


def _unique_graft_choice_id(
    k: int,
    host_decision: str,
    host_namespace: set[str],
    renamed: list[dict[str, object]],
) -> str:
    """Return a deterministic, collision-free id for the graft's new choice."""
    taken = set(host_namespace) | _region_all_ids(
        cast("list[Mapping[str, object]]", renamed)
    )
    base = f"m{k}_graft_into_{host_decision}"
    candidate = base
    suffix = 0
    while candidate in taken:
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate


def _post_graft_graph(
    host: Mapping[str, object],
    renamed: list[dict[str, object]],
    host_decision: str,
    root_new_id: str,
) -> nx.DiGraph[str]:
    """Return the choice graph the host would have after applying the graft.

    Renaming does not change path lengths, so depth and shortest-path measures
    over this graph equal what the L1-7 and PL-20 gate rules will measure on the
    candidate.
    """
    graph = _parent_graph(host)
    for node in renamed:
        node_id = _str_field(node, "id")
        if node_id is None:
            continue
        graph.add_node(node_id)
        for choice in _choices_of(node):
            target = _str_field(choice, "target")
            if target is not None:
                graph.add_edge(node_id, target)
    graph.add_edge(host_decision, root_new_id)
    return graph


def _satisfying_in_nodes(nodes: list[dict[str, object]]) -> set[str]:
    """Return the ids of success/completion ending nodes within a region."""
    targets: set[str] = set()
    for node in nodes:
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


def _clamp_position(position: int | None, current_len: int) -> int:
    """Clamp a requested choice-insertion index to ``[0, current_len]``."""
    if position is None or position > current_len:
        return current_len
    return max(0, position)


def _evaluate_graft(  # noqa: PLR0911, PLR0913 -- one cohesive precondition ladder, one reason each
    host: Mapping[str, object],
    donor: Mapping[str, object],
    donor_slug: str,
    subtree_root: str,
    host_decision: str,
    position: int | None,
) -> tuple[_GraftPlan | None, str | None]:
    """Validate a graft of a donor subtree under a host decision (design 4.4).

    Runs every graft precondition: the host decision exists, is non-ending, and
    stays within the 2-3 choices window after the add; the donor band equals the
    host band and the donor is a standalone book; the donor subtree exists, is
    closed, self-contained, and state-free; and the post-graft node count and
    depth stay within the cell envelope.

    Args:
        host: The raw host (parent) story document.
        donor: The donor story document (may be ``host`` for a same-skeleton graft).
        donor_slug: The donor's slug, for audit notes.
        subtree_root: The donor subtree root to copy.
        host_decision: The host decision node to attach the new choice to.
        position: The new choice's insertion index, or None to append.

    Returns:
        tuple[_GraftPlan | None, str | None]: ``(plan, None)`` when eligible,
            else ``(None, reason)``.
    """
    host_node = _node_by_id(host, host_decision)
    if host_node is None:
        return None, f"host decision '{host_decision}' does not exist"
    if host_node.get("is_ending") is True:
        return None, f"host decision '{host_decision}' is an ending node"
    post_choices = len(_choices_of(host_node)) + 1
    if not _MIN_CHOICES_PER_DECISION <= post_choices <= _MAX_CHOICES_PER_DECISION:
        # #CRITICAL: security: the gate does not hard-enforce choices-per-decision
        # (design 4.8), so the operator self-enforces the ADR-011 2-3 window: a
        # graft that would push a decision to 4+ choices is a grammar violation a
        # hand author would not make, rejected belt-and-braces before the gate.
        # #VERIFY: test_mutation_m3.py pins that grafting onto a 3-choice decision
        # is discarded at preconditions.
        return None, (
            f"grafting a choice onto '{host_decision}' yields {post_choices} "
            f"choices, outside the ADR-011 2-3 window"
        )
    # #CRITICAL: security: donor band MUST equal host band. Same-band donors mean
    # every grafted ending kind is band-legal by the donor's own PL-15 history and
    # its beats were authored to the same band's content posture, so no
    # out-of-band content can cross into the host (the K13 age guarantee, design
    # section 10). A cross-band donor is rejected here and PL-15 re-runs at the
    # gate regardless.
    # #VERIFY: test_mutation_m3.py pins that a different-band donor is rejected.
    host_band = _str_field(_metadata_of(host), "age_band")
    donor_band = _str_field(_metadata_of(donor), "age_band")
    if host_band is None or donor_band is None or host_band != donor_band:
        return None, (
            f"donor band '{donor_band}' does not equal host band '{host_band}'; "
            f"cross-band grafts are forbidden"
        )
    if _metadata_of(donor).get("series") is not None:
        return None, f"donor '{donor_slug}' is a series book; out of scope"
    if subtree_root not in node_ids(donor):
        return None, f"donor subtree root '{subtree_root}' does not exist"
    subtree = extract_subtree(donor, subtree_root)
    if not subtree.self_contained:
        return None, f"donor subtree '{subtree_root}' is not self-contained"
    if not subtree.closed:
        return None, f"donor subtree '{subtree_root}' is not closed"
    clean_reason = _region_cleanliness_reason(donor, subtree.node_ids)
    if clean_reason is not None:
        return None, clean_reason
    return _build_graft_plan(
        host, donor, donor_slug, subtree, host_decision, host_node, position
    )


def _build_graft_plan(  # noqa: PLR0913 -- the validated facts a graft plan needs
    host: Mapping[str, object],
    donor: Mapping[str, object],
    donor_slug: str,
    subtree: Subtree,
    host_decision: str,
    host_node: Mapping[str, object],
    position: int | None,
) -> tuple[_GraftPlan | None, str | None]:
    """Rename the donor region and run the post-graft envelope checks.

    Split from :func:`_evaluate_graft` so the precondition ladder stays flat. The
    subtree has already been proven closed, self-contained, and state-free.

    Args:
        host: The raw host story document.
        donor: The donor story document.
        donor_slug: The donor's slug.
        subtree: The validated donor :class:`~cyo_adventure.mutation.subtree.Subtree`.
        host_decision: The host decision node id.
        host_node: The host decision node dict.
        position: The requested new-choice insertion index, or None.

    Returns:
        tuple[_GraftPlan | None, str | None]: ``(plan, None)`` when eligible,
            else ``(None, reason)``.
    """
    region_ids = subtree.node_ids
    subtree_root = subtree.root
    region_nodes = [
        node for node in _nodes_of(donor) if _str_field(node, "id") in region_ids
    ]
    host_namespace = host_id_namespace(host)
    k = _choose_graft_index(host_namespace, region_nodes)
    # #CRITICAL: data-integrity: every grafted id is renamed under the m<k>_
    # scheme and collision-checked against the host's full namespace by
    # rename_region, so a graft can never emit a duplicate id that would let one
    # graph position shadow another; the schema's uniqueness rule is the
    # fail-closed backstop (design CR-3).
    # #VERIFY: test_mutation_m3.py asserts renamed ids are disjoint from the host
    # namespace over real catalog donors.
    renamed, node_id_map = rename_region(region_nodes, k, host_namespace)
    _rename_region_slot_tokens(renamed, k)
    root_new_id = node_id_map[subtree_root]
    new_choice_id = _unique_graft_choice_id(k, host_decision, host_namespace, renamed)

    bounds = _cell_node_bounds(host)
    post_count = len(node_ids(host)) + len(renamed)
    if bounds is not None and post_count > bounds[1]:
        return None, (
            f"post-graft node count {post_count} exceeds the cell envelope "
            f"maximum {bounds[1]} (L1-7)"
        )
    graph = _post_graft_graph(host, renamed, host_decision, root_new_id)
    start = _str_field(host, "start_node")
    max_depth = _cell_max_depth(host)
    if max_depth is not None:
        depth = _branch_depth(graph, start)
        if depth is not None and depth > max_depth:
            return None, (
                f"post-graft branch depth {depth} exceeds cell max_depth {max_depth}"
            )
    # #CRITICAL: security: a graft that lands a shallow success/completion ending
    # can undercut the PL-20 fastest-finish arc floor (a hollow quick win), so the
    # operator pre-computes the post-graft shortest satisfying path over the host
    # and grafted satisfying endings and rejects below-floor. The gate re-proves
    # PL-20 at stage 1 regardless; this avoids a wasted gate run.
    # #VERIFY: test_mutation_m3.py accepts only grafts that hold the arc floor.
    floor = _pl20_floor(host)
    if floor is not None:
        targets = _satisfying_ending_ids(host) | _satisfying_in_nodes(renamed)
        shortest = _shortest_satisfying_nodes(graph, start, targets)
        if shortest is not None and shortest < floor:
            return None, (
                f"post-graft shortest satisfying path is {shortest} node(s), below "
                f"the PL-20 floor {floor}"
            )
    plan = _GraftPlan(
        donor_slug=donor_slug,
        subtree_root=subtree_root,
        host_decision=host_decision,
        position=_clamp_position(position, len(_choices_of(host_node))),
        k=k,
        renamed_nodes=tuple(renamed),
        root_new_id=root_new_id,
        new_choice_id=new_choice_id,
        new_choice_label=_M3_GRAFT_LABEL,
        region_size=len(renamed),
    )
    return plan, None


def _apply_graft(host: Mapping[str, object], plan: _GraftPlan) -> dict[str, object]:
    """Return a deep copy of ``host`` with the renamed region and new choice added.

    Args:
        host: The raw host story document (never mutated).
        plan: The validated graft.

    Returns:
        dict[str, object]: The candidate graph, pre-metadata-resync.

    Raises:
        ValidationError: If the host has no node list.
    """
    candidate = copy.deepcopy(dict(host))
    nodes = candidate.get("nodes")
    if not isinstance(nodes, list):
        msg = "host story has no nodes list to graft into"
        raise ValidationError(msg, field="nodes", value=None)
    node_list = cast("list[object]", nodes)
    for renamed_node in plan.renamed_nodes:
        node_list.append(copy.deepcopy(renamed_node))
    for raw_node in node_list:
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        if node.get("id") != plan.host_decision:
            continue
        raw_choices = node.get("choices")
        choices = (
            list(cast("list[object]", raw_choices))
            if isinstance(raw_choices, list)
            else []
        )
        new_choice: dict[str, object] = {
            "id": plan.new_choice_id,
            "label": plan.new_choice_label,
            "target": plan.root_new_id,
        }
        choices.insert(plan.position, new_choice)
        node["choices"] = choices
        break
    return candidate


def _graft_reguide_items(plan: _GraftPlan) -> tuple[ReguideItem, ...]:
    """Return the two re-guidance items a graft emits (design 4.4).

    The new choice's label and the graft root's entry beats are the seam where
    donor content meets the host context, so both need re-authoring before the
    mutant is promotable.
    """
    root_body = ""
    for node in plan.renamed_nodes:
        if _str_field(node, "id") == plan.root_new_id:
            root_body = _str_field(node, "body") or ""
            break
    return (
        ReguideItem(
            target=ReguideTarget.CHOICE,
            target_id=plan.new_choice_id,
            reason="new graft-seam choice; author its label for the host context",
            current_text=plan.new_choice_label,
        ),
        ReguideItem(
            target=ReguideTarget.NODE,
            target_id=plan.root_new_id,
            reason="graft root now enters from a host decision; re-author its beats",
            current_text=root_body,
        ),
    )


def _load_catalog_donor(slug: str) -> dict[str, object]:
    """Load a donor skeleton document by slug from the git-versioned catalog.

    The default :class:`M3PruneGraft` donor resolver. Reuses the
    ``generation.skeleton_match`` discovery helpers rather than hand-rolling a
    glob, and is imported lazily so the mutation package's own import graph stays
    free of the db/generation layers.

    Args:
        slug: The donor skeleton slug (a reviewer-supplied scalar parameter).

    Returns:
        dict[str, object]: The decoded donor document.

    Raises:
        ValidationError: If the slug names no catalog skeleton, resolves to a
            missing file, or is not a JSON object.
    """
    # #ASSUME: external-resources: the donor is a git-versioned catalog file
    # discovered exactly the way selection discovers skeletons (design 4.4); this
    # is a deterministic read of trusted catalog data, never untrusted request
    # input (CR-5). Resolved cwd-relative like every skeleton tool.
    # #VERIFY: test_mutation_m3.py grafts real same-band donors through this
    # resolver and pins that a different-band donor is rejected at preconditions.
    import json  # noqa: PLC0415 -- lazy so mutation import stays db/generation-free

    from cyo_adventure.generation.skeleton_match import (  # noqa: PLC0415
        find_skeleton_metadata,
        resolve_skeleton_path,
    )

    metadata = find_skeleton_metadata(slug)
    if metadata is None:
        msg = f"donor skeleton '{slug}' was not found in the catalog"
        raise ValidationError(msg, field="donor", value=slug)
    path = resolve_skeleton_path(metadata.age_band.value, slug)
    if not path.is_file():
        msg = f"donor skeleton '{slug}' resolved to a missing file"
        raise ValidationError(msg, field="donor", value=slug)
    data: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    if not isinstance(data, dict):
        msg = f"donor skeleton '{slug}' is not a JSON object"
        raise ValidationError(msg, field="donor", value=slug)
    return cast("dict[str, object]", data)


# --- M3 contract-merge transform (dry in D4; wired into acceptance in D7) ---


def merge_graft_contract(  # noqa: PLR0913 -- one cohesive contract-merge transform
    host_contract: ThemeContract,
    donor_contract: ThemeContract,
    referenced_slot_ids: frozenset[str],
    k: int,
    mutant_slug: str,
) -> ThemeContract:
    """Return the host contract with a graft's donor slots imported (design 4.4).

    Every donor slot the grafted region references is imported under its renamed
    id ``M<k>_<SLOT>`` with its :class:`SlotConstraints` copied verbatim
    (``distinct_from`` references are remapped to the renamed siblings and any
    reference to a non-imported sibling is dropped so the merged contract stays
    self-consistent), and its ``default_binding`` value carried over. The result
    is a fresh contract (version 1) for the mutant.

    This is the D4 dry transform: it is unit-tested against the WS-2 models and
    the ``load_contract_for`` token-set equality rule, but is NOT wired into the
    acceptance harness (contract acceptance is D7, design section 6 stage 4).

    Args:
        host_contract: The host skeleton's theme contract.
        donor_contract: The donor skeleton's theme contract.
        referenced_slot_ids: The donor slot ids the grafted region references.
        k: The graft mutation index (the ``M<k>_`` slot prefix).
        mutant_slug: The mutant's slug (the new ``skeleton_slug``).

    Returns:
        ThemeContract: The merged contract.
    """
    donor_by_id = {slot.id: slot for slot in donor_contract.slots}
    imported: list[SlotSpec] = []
    imported_binding: dict[str, str] = {}
    for slot_id in sorted(referenced_slot_ids):
        spec = donor_by_id.get(slot_id)
        if spec is None:
            continue
        new_id = graft_slot_id(slot_id, k)
        imported.append(
            SlotSpec(
                id=new_id,
                scope=spec.scope,
                meaning=spec.meaning,
                guidance=spec.guidance,
                constraints=SlotConstraints(
                    max_words=spec.constraints.max_words,
                    forbid=list(spec.constraints.forbid),
                    distinct_from=[
                        graft_slot_id(ref, k)
                        for ref in spec.constraints.distinct_from
                        if ref in referenced_slot_ids
                    ],
                    pattern=spec.constraints.pattern,
                ),
            )
        )
        if slot_id in donor_contract.default_binding:
            imported_binding[new_id] = donor_contract.default_binding[slot_id]
    binding = dict(host_contract.default_binding)
    binding.update(imported_binding)
    return ThemeContract(
        contract_version=1,
        skeleton_slug=mutant_slug,
        age_band=host_contract.age_band,
        legacy_lexicon=sorted(
            set(host_contract.legacy_lexicon) | set(donor_contract.legacy_lexicon)
        ),
        default_binding=binding,
        slots=[*host_contract.slots, *imported],
    )


def prune_contract(
    host_contract: ThemeContract,
    surviving_slot_ids: frozenset[str],
    mutant_slug: str,
) -> ThemeContract:
    """Return the host contract with slots no surviving surface references dropped.

    A pruned region's slots are removed if and only if the mutated skeleton no
    longer references them (``surviving_slot_ids`` is the token set of the pruned
    skeleton's three surfaces). ``distinct_from`` references to dropped siblings
    are removed so the result stays self-consistent. The D4 dry transform,
    unit-tested against the WS-2 models (contract acceptance is D7).

    Args:
        host_contract: The host skeleton's theme contract.
        surviving_slot_ids: The slot tokens still present after the prune.
        mutant_slug: The mutant's slug (the new ``skeleton_slug``).

    Returns:
        ThemeContract: The pruned contract.

    Raises:
        ValidationError: If the prune would leave the contract with no slots (a
            skeleton with no tokens must ship contract-less, not with an empty
            contract).
    """
    kept: list[SlotSpec] = []
    for spec in host_contract.slots:
        if spec.id not in surviving_slot_ids:
            continue
        kept.append(
            SlotSpec(
                id=spec.id,
                scope=spec.scope,
                meaning=spec.meaning,
                guidance=spec.guidance,
                constraints=SlotConstraints(
                    max_words=spec.constraints.max_words,
                    forbid=list(spec.constraints.forbid),
                    distinct_from=[
                        ref
                        for ref in spec.constraints.distinct_from
                        if ref in surviving_slot_ids
                    ],
                    pattern=spec.constraints.pattern,
                ),
            )
        )
    if not kept:
        msg = (
            "prune would drop every slot; a token-free skeleton must ship "
            "contract-less rather than with an empty contract"
        )
        raise ValidationError(msg, field="slots", value=None)
    binding = {
        slot_id: value
        for slot_id, value in host_contract.default_binding.items()
        if slot_id in surviving_slot_ids
    }
    return ThemeContract(
        contract_version=1,
        skeleton_slug=mutant_slug,
        age_band=host_contract.age_band,
        legacy_lexicon=list(host_contract.legacy_lexicon),
        default_binding=binding,
        slots=kept,
    )


class M3PruneGraft:
    """M3: prune a closed subtree or graft a donor subtree (design section 4.4).

    Two sub-operations, selected by the ``mode`` parameter:

    - **prune** (``mode=prune``): remove a closed, self-contained subtree and the
      single choice edge into it. The pruned subtree is chosen by an explicit
      ``choice`` id, or reproducibly from the seeded rng over the canonically
      ordered prunable choices. Prune emits no re-guidance (design 4.4).
    - **graft** (``mode=graft``): attach a copy of a closed, self-contained,
      state-free subtree (from the same skeleton, or a same-band ``donor``) under
      a new choice on ``host_decision``, with every id renamed under the ``m<k>_``
      scheme and every ``{SLOT}`` token renamed to ``M<k>_`` form. Graft requires
      explicit ``subtree_root`` and ``host_decision`` ids (plus optional ``donor``
      slug and ``position``), so it is deterministic without an rng.

    D4 is Tier-1 only. The two-sided cell envelope is blocking (a prune may not
    drop below the cell minimum, a graft may not exceed the maximum), donors are
    same-band only, and grafted regions must be variable/effect/condition-free.
    The contract-merge transform (:func:`merge_graft_contract`,
    :func:`prune_contract`) is implemented and unit-tested here but is not wired
    into the acceptance harness; contract acceptance lands in D7.
    """

    op_id: str = M3_OP_ID

    def __init__(self, donor_resolver: DonorResolver | None = None) -> None:
        """Build the operator with a donor resolver.

        Args:
            donor_resolver: Maps a ``donor`` slug to its decoded document. The
                default reads the git-versioned catalog; tests inject an
                in-memory resolver to keep the operator a pure function.
        """
        self._donor_resolver: DonorResolver = (
            donor_resolver if donor_resolver is not None else _load_catalog_donor
        )

    def preconditions(
        self, parent: Mapping[str, object], params: OpParams
    ) -> PreconditionReport:
        """Return whether M3 may attempt a mutation on ``parent`` (design 4.4).

        Args:
            parent: The raw parent story document.
            params: The operator parameters (``mode`` plus mode-specific ids).

        Returns:
            PreconditionReport: Satisfied when eligible, else the failing reasons.
        """
        failures = list(self._base_failures(parent))
        mode = params.get("mode")
        if mode == _M3_MODE_PRUNE:
            failures.extend(self._prune_failures(parent, params))
        elif mode == _M3_MODE_GRAFT:
            failures.extend(self._graft_failures(parent, params))
        else:
            failures.append(_M3_MODE_MSG)
        if failures:
            return PreconditionReport.failed(*failures)
        return PreconditionReport.passed()

    def apply(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> MutationResult:
        """Apply the selected sub-operation and return the resynced candidate.

        Args:
            parent: The raw parent story document (never mutated).
            params: The operator parameters (``mode`` plus mode-specific ids).
            rng: The injected random source (used only by prune's rng fallback).

        Returns:
            MutationResult: The candidate (metadata resynced) plus re-guidance.

        Raises:
            ValidationError: If the mode is unknown or the selected mutation is
                ineligible.
        """
        mode = params.get("mode")
        if mode == _M3_MODE_PRUNE:
            return self._apply_prune_op(parent, params, rng)
        if mode == _M3_MODE_GRAFT:
            return self._apply_graft_op(parent, params)
        raise ValidationError(_M3_MODE_MSG, field="mode", value=mode)

    @staticmethod
    def _base_failures(parent: Mapping[str, object]) -> list[str]:
        """Return the parent-level (tier/series/production) precondition failures."""
        failures: list[str] = []
        meta = _metadata_of(parent)
        if recompute_tier(parent) != 1:
            failures.append(_M3_TIER1_ONLY_MSG)
        if meta.get("series") is not None:
            failures.append(_M3_SERIES_MSG)
        if meta.get("production_eligible") is False:
            failures.append(_M3_PRODUCTION_ONLY_MSG)
        return failures

    @staticmethod
    def _prune_failures(parent: Mapping[str, object], params: OpParams) -> list[str]:
        """Return prune-specific precondition failures."""
        choice = params.get("choice")
        if choice is not None:
            if not isinstance(choice, str):
                return [_M3_PRUNE_PARAMS_MSG]
            _plan, reason = _evaluate_prune(parent, choice)
            if reason is not None:
                return [f"prune of choice '{choice}' is ineligible: {reason}"]
            return []
        if not _prunable_choices(parent):
            return ["no eligible prune exists for this parent"]
        return []

    def _graft_failures(
        self, parent: Mapping[str, object], params: OpParams
    ) -> list[str]:
        """Return graft-specific precondition failures."""
        donor, donor_slug, reason = self._resolve_donor(parent, params)
        if reason is not None or donor is None:
            return [reason or _M3_DONOR_PARAM_MSG]
        subtree_root = params.get("subtree_root")
        host_decision = params.get("host_decision")
        if not (isinstance(subtree_root, str) and isinstance(host_decision, str)):
            return [_M3_GRAFT_PARAMS_MSG]
        _plan, graft_reason = _evaluate_graft(
            parent,
            donor,
            donor_slug,
            subtree_root,
            host_decision,
            _int_param(params.get("position")),
        )
        if graft_reason is not None:
            return [f"graft is ineligible: {graft_reason}"]
        return []

    def _resolve_donor(
        self, parent: Mapping[str, object], params: OpParams
    ) -> tuple[Mapping[str, object] | None, str, str | None]:
        """Resolve the graft donor document (parent for a same-skeleton graft).

        Args:
            parent: The raw parent (host) story document.
            params: The operator parameters (optional ``donor`` slug).

        Returns:
            tuple[Mapping[str, object] | None, str, str | None]: ``(donor,
                donor_slug, reason)``; ``reason`` is set (and ``donor`` None) when
                the donor could not be loaded.
        """
        donor = params.get("donor")
        if donor is None:
            return parent, "<self>", None
        if not isinstance(donor, str):
            return None, "", _M3_DONOR_PARAM_MSG
        try:
            document = self._donor_resolver(donor)
        except ValidationError as exc:
            return None, donor, f"donor '{donor}' could not be loaded: {exc}"
        return document, donor, None

    def _apply_prune_op(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> MutationResult:
        """Apply a prune and return the resynced candidate (no re-guidance)."""
        plan = self._select_prune(parent, params, rng)
        candidate = resync_metadata(_apply_prune(parent, plan))
        note = (
            f"M3 prune: removed subtree '{plan.root}' ({len(plan.region_ids)} "
            f"node(s)) and choice '{plan.choice_id}' on '{plan.parent_node_id}'"
        )
        notes = (note, *_ending_ratio_advisory(candidate))
        return MutationResult(candidate=candidate, reguide=(), notes=notes)

    @staticmethod
    def _select_prune(
        parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> _PrunePlan:
        """Resolve the prune from an explicit ``choice`` or the seeded rng."""
        choice = params.get("choice")
        if choice is not None:
            if not isinstance(choice, str):
                raise ValidationError(
                    _M3_PRUNE_PARAMS_MSG, field="choice", value=choice
                )
            plan, reason = _evaluate_prune(parent, choice)
            if plan is None:
                msg = f"M3 prune of '{choice}' is ineligible: {reason}"
                raise ValidationError(msg, field="choice", value=choice)
            return plan
        candidates = _prunable_choices(parent)
        rng.shuffle(candidates)
        for choice_id in candidates:
            plan, _reason = _evaluate_prune(parent, choice_id)
            if plan is not None:
                return plan
        msg = "M3 found no eligible prune for this parent"
        raise ValidationError(msg, field="parent", value=None)

    def _apply_graft_op(
        self, parent: Mapping[str, object], params: OpParams
    ) -> MutationResult:
        """Apply a graft and return the resynced candidate plus its re-guidance."""
        donor, donor_slug, reason = self._resolve_donor(parent, params)
        if reason is not None or donor is None:
            raise ValidationError(
                reason or _M3_DONOR_PARAM_MSG, field="donor", value=params.get("donor")
            )
        subtree_root = params.get("subtree_root")
        host_decision = params.get("host_decision")
        if not (isinstance(subtree_root, str) and isinstance(host_decision, str)):
            raise ValidationError(
                _M3_GRAFT_PARAMS_MSG, field="subtree_root", value=subtree_root
            )
        plan, graft_reason = _evaluate_graft(
            parent,
            donor,
            donor_slug,
            subtree_root,
            host_decision,
            _int_param(params.get("position")),
        )
        if plan is None:
            msg = f"M3 graft is ineligible: {graft_reason}"
            raise ValidationError(msg, field="subtree_root", value=subtree_root)
        candidate = resync_metadata(_apply_graft(parent, plan))
        note = (
            f"M3 graft: copied donor '{donor_slug}' subtree '{plan.subtree_root}' "
            f"({plan.region_size} node(s), m{plan.k}_ prefix) under new choice "
            f"'{plan.new_choice_id}' on '{plan.host_decision}'"
        )
        return MutationResult(
            candidate=candidate, reguide=_graft_reguide_items(plan), notes=(note,)
        )


def _int_param(value: object) -> int | None:
    """Return an int parameter (rejecting bool), or None when absent/off-type."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# Register the singleton M3 operator in the default catalog registry alongside
# M1 and M2. The registered instance uses the default catalog donor resolver so
# the CLI can express a graft donor as a scalar slug parameter.
M3 = REGISTRY.register(M3PruneGraft())
