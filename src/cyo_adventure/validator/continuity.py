"""Name the content a node cannot presuppose, for a book with no state (W6 follow-on).

Two independent Fable readers, given five new books each and told to report only
what the existing coverage misses, converged on the same class from different
book sets: a node asserts state the taken path never established, and a
revisitable node replays text contradicting what has accumulated. The provable
instance is `the-tide-pool-rescue`, which declares ``variables: []`` and whose
endings name three or four animals on paths where a reader can have met one, one
of them counting "Three rescues by you" on a path holding a single rescue.

**This is a reported statistic, not a gate**, on the same terms as
:mod:`cyo_adventure.validator.consequence`, and unlike that module it is not a
gate candidate either. Three formulations were built and measured, and none is
usable as a rule. This one is kept because it is exact and because its aggregate
says something the other two could not, not because it is nearly a checker.

Why nothing here reads the prose, and why nothing here fires
-------------------------------------------------------------
The obvious check is per-reference: for every definite noun phrase, require that
every path to it passed through a node introducing it. Measured before being
believed, it produces **3.48 findings per node** over the committed corpus,
because bridging reference is ordinary English (``the ground``, ``the light``)
and a first mention with a definite article is usually correct. A narrower
lexical version counting only cardinals attributed to the reader scores **1 true
positive in 6**. Both are the wall W15 hit (`AL-366`): separating a
presupposition from an introduction is entailment, and this project has paid for
pretending otherwise once already.

The structural formulation below is exact, and it flags **3,815 of 4,472 nodes**
across the committed corpus, which is not a bug in it. After the first
bottleneck in a branching book, almost every later node has some ancestor the
reader may have skipped; that is what branching means. So the per-node list is
correct and too coarse to hand anybody, and the finding lives one level up, in
what the aggregate separates.

What survives is the half needing no prose understanding at all, and it is
exact. A book declaring no variables, no ``on_enter`` effects and no conditional
choices cannot tell two readers apart, so any content that is *optional* on the
way into a node is content that node must not presuppose. Optional content is
the difference between two computable sets: the nodes on **every** route in (the
dominators) and the nodes on **any** route in (the ancestors). Where those are
equal, every reader arrives having read exactly the same thing and the node is
safe by construction. Where they differ, the difference is precisely the list an
author needs, and it is available before a word of prose exists.

What the aggregate actually separates
------------------------------------
Run over the committed corpus, the measure splits the catalogue cleanly in two,
and the split is by topology rather than by author care:

* All six ``time_cave`` books report **zero** optional history across 236 nodes.
  A pure branching tree never reconverges, so every reader arrives at every node
  having read exactly the same thing. History-neutrality is guaranteed by
  construction, and prose there can presuppose anything upstream of it.
* Every other topology reports nearly all of its nodes, necessarily.

Against that, ``loop_and_grow`` is the one topology whose defining mechanic is
accumulation across hub revisits, and all six skeletons carrying it declare no
state of any kind: no variables, no ``on_enter``, no conditional choices. All
six sit at 3-5 or 5-8, where the Tier-1 contract forbids the variables the
topology would need. Three of the six have already produced a verified
continuity defect in prose. That is not six authors making the same mistake; it
is a topology promising what its tier cannot represent, and the remedy is in the
skeleton catalogue rather than in any fill or any checker.

Nothing here keys on a topology name: a stateless ``open_map`` hub is measured
on identical terms. The names above are findings, not inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cyo_adventure.storybook.models import Storybook

__all__ = [
    "OptionalHistory",
    "dominating_nodes",
    "is_stateless",
    "optional_history",
]


@dataclass(frozen=True, slots=True)
class OptionalHistory:
    """One node, and the content a reader may or may not have read before it.

    Attributes:
        node_id: The node the reader arrives at.
        optional: Ids of nodes on some route in but not on every route in, in
            the story's own node order. These are exactly what the node's prose
            must not presuppose. Never empty: a node with nothing optional is
            not reported at all.
    """

    node_id: str
    optional: tuple[str, ...]


def is_stateless(story: Storybook) -> bool:
    """Return whether *story* can distinguish two readers' histories at all.

    Three mechanisms could carry history: a declared variable, an ``on_enter``
    effect, or a condition on a choice. A book with none presents identical text
    and identical options to everyone who reaches a node, whatever they did to
    get there. All six ``loop_and_grow`` skeletons in the catalogue are in this
    state, with zero of each of the three.

    Args:
        story: The story to inspect.

    Returns:
        bool: ``True`` when no state-carrying mechanism is declared.
    """
    if story.variables:
        return False
    return not any(
        node.on_enter or any(choice.condition for choice in node.choices)
        for node in story.nodes
    )


def optional_history(story: Storybook) -> list[OptionalHistory]:
    """Return each node's optional incoming content, longest list first.

    Computed as ancestors minus dominators over the node graph. Both are exact
    fixed-point computations rather than path enumeration, which matters for
    more than speed: an enumeration under a cap reports a number that is a
    statement about the cap (`AL-338`), and this answer has no cap in it.

    Unreachable nodes are omitted rather than reported with an empty history,
    since an unreachable node is L1's finding and not this module's.

    Args:
        story: The story to measure.

    Returns:
        list[OptionalHistory]: Nodes with at least one optional ancestor,
        ordered by how much is optional, descending, then by node id so the
        output is stable.
    """
    order = [node.id for node in story.nodes]
    rank = {node_id: index for index, node_id in enumerate(order)}
    successors: dict[str, set[str]] = {node.id: set() for node in story.nodes}
    predecessors: dict[str, set[str]] = {node.id: set() for node in story.nodes}
    for node in story.nodes:
        for choice in node.choices:
            if choice.target not in successors:
                continue  # a dangling target is L1-2's finding, not ours
            successors[node.id].add(choice.target)
            predecessors[choice.target].add(node.id)

    reachable = _reachable(story.start_node, successors)
    ancestors = _ancestors(order, predecessors, reachable)
    dominators = _dominators(story.start_node, order, predecessors, reachable)

    results = [
        OptionalHistory(
            node_id=node_id,
            optional=tuple(
                sorted(ancestors[node_id] - dominators[node_id], key=rank.__getitem__)
            ),
        )
        for node_id in order
        if node_id in reachable and ancestors[node_id] - dominators[node_id]
    ]
    results.sort(key=lambda item: (-len(item.optional), item.node_id))
    return results


def dominating_nodes(story: Storybook) -> dict[str, frozenset[str]]:
    """Return, for each reachable node, the nodes on EVERY route into it.

    The public face of the same exact fixed-point computation
    :func:`optional_history` uses. Exposed because a second rule needs the
    dominator half on its own: PN-1 (`validator/naming.py`) asks whether a
    node introducing a proper noun lies on every route to a node that names
    it, which is exactly a dominator question and not an optional-history one.

    Dominance here is **strict**: a node is not on a route *into* itself, so
    it never appears in its own set and the start node maps to the empty set.
    PN-1 relies on that, testing whether the node itself introduces the name
    as a separate question from whether an ancestor did.

    Args:
        story: The story whose node graph to measure.

    Returns:
        dict[str, frozenset[str]]: Reachable node id to the nodes strictly
            dominating it.
            Unreachable nodes are omitted, matching
            :func:`optional_history`; an unreachable node is L1's finding.
    """
    order = [node.id for node in story.nodes]
    successors: dict[str, set[str]] = {node.id: set() for node in story.nodes}
    predecessors: dict[str, set[str]] = {node.id: set() for node in story.nodes}
    for node in story.nodes:
        for choice in node.choices:
            # #ASSUME: data integrity: a choice may target an id no node
            # declares. That is L1-2's finding, not this module's, so it must
            # be skipped rather than indexed: predecessors only has keys for
            # declared node ids, and indexing it by a dangling target raises
            # KeyError, turning a reportable finding into a crash of the gate
            # itself.
            # #VERIFY: covered by
            # test_a_dangling_choice_target_does_not_crash_dominating_nodes
            # in tests/unit/test_continuity.py, which proves this by mutation.
            if choice.target not in successors:
                continue  # a dangling target is L1-2's finding, not ours
            successors[node.id].add(choice.target)
            predecessors[choice.target].add(node.id)

    reachable = _reachable(story.start_node, successors)
    dominators = _dominators(story.start_node, order, predecessors, reachable)
    return {node_id: frozenset(dominators[node_id]) for node_id in reachable}


def _reachable(start: str, successors: dict[str, set[str]]) -> set[str]:
    """Return the nodes reachable from *start*.

    Args:
        start: The story's start node id.
        successors: Node id to the ids it can reach in one choice.

    Returns:
        set[str]: Reachable node ids, including *start* itself.
    """
    seen = {start}
    stack = [start]
    while stack:
        for target in successors.get(stack.pop(), ()):
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


def _ancestors(
    order: list[str], predecessors: dict[str, set[str]], reachable: set[str]
) -> dict[str, set[str]]:
    """Return, for each node, every node on some route into it.

    Args:
        order: Node ids in story order.
        predecessors: Node id to the ids that can reach it in one choice.
        reachable: The nodes reachable from the start.

    Returns:
        dict[str, set[str]]: Node id to its ancestor set, excluding itself.
    """
    result: dict[str, set[str]] = {node_id: set() for node_id in order}
    changed = True
    while changed:
        changed = False
        for node_id in order:
            if node_id not in reachable:
                continue
            merged: set[str] = set()
            for parent in predecessors[node_id]:
                if parent not in reachable:
                    continue
                merged.add(parent)
                merged |= result[parent]
            merged.discard(node_id)
            if merged != result[node_id]:
                result[node_id] = merged
                changed = True
    return result


def _dominators(
    start: str, order: list[str], predecessors: dict[str, set[str]], reachable: set[str]
) -> dict[str, set[str]]:
    """Return, for each node, every node on *every* route into it.

    The standard iterative dataflow formulation: a node's dominators are the
    intersection of its predecessors' dominator sets, plus those predecessors
    themselves where they dominate. Cycles are handled by the fixed point, which
    matters here because ``loop_and_grow`` hubs are cyclic by design and a
    dominator computation that assumed a DAG would be wrong on exactly the books
    this module exists for.

    Args:
        start: The story's start node id.
        order: Node ids in story order.
        predecessors: Node id to the ids that can reach it in one choice.
        reachable: The nodes reachable from the start.

    Returns:
        dict[str, set[str]]: Node id to the nodes strictly dominating it.
    """
    live = [node_id for node_id in order if node_id in reachable]
    universe = set(live)
    result: dict[str, set[str]] = {
        node_id: (set() if node_id == start else set(universe)) for node_id in live
    }
    changed = True
    while changed:
        changed = False
        for node_id in live:
            if node_id == start:
                continue
            parents = [p for p in predecessors[node_id] if p in reachable]
            if not parents:
                continue
            merged: set[str] = {parents[0]} | result[parents[0]]
            for parent in parents[1:]:
                merged &= {parent} | result[parent]
            merged.discard(node_id)
            if merged != result[node_id]:
                result[node_id] = merged
                changed = True
    return {node_id: result.get(node_id, set()) for node_id in order}
