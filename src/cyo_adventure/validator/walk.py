"""Layer-2 configuration-walk core (Phase 2).

Enumerates every reachable story *configuration* by driving the pure
:class:`~cyo_adventure.player.engine.StoryEngine`.  A *configuration* is a
distinct (node_id, var_state, relevant_visit_set) triple that can arise from
any sequence of choices.  The walk is the foundation on which the Layer-2
state-space validator rules (L2-9..L2-12) are built.

Transition semantics remain in the engine; this module only orchestrates the
BFS closure over the reachable state space.

Beyond Layer 2, :func:`config_dag` projects that closure into a node-labelled
graph and :func:`fastest_satisfying_finish` measures the clock over it, because
PL-20, PL-25 and PL-26 all ask how far the reader travels and the story's choice
graph cannot answer that for a story with conditions (`UW-C292`). Both live here
rather than in ``policy`` so the offline mutation module can call the same
measurement the gate does: ADR-020 forbids the validator importing ``mutation``,
so the shared code has to sit on this side of that line.

ConfigKey soundness (once-effects)
-----------------------------------
The naive deduplication key ``(node_id, var_state)`` is UNSOUND when a story
has ``once: true`` on_enter effects.  Two readers at the same ``(node,
var_state)`` but with different visit histories can diverge later because a
once-effect on another node fires for one and is suppressed for the other.

The key's third element corrects this:

    visit_set INTERSECT {node ids whose on_enter contains an effect with once==True}

In stories without any once-effects the intersection is always empty, so the
key collapses to ``(node, var_state)`` with a constant ``frozenset()`` third
component -- the common-case cost is zero.  The RAD markers documenting this
soundness invariant live as standalone ``#`` comments at the relevant code
locations (``_config_key`` and ``walk_configurations``) so comment-grep audits
find them.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.player.engine import StoryEngine
from cyo_adventure.storybook.models import SATISFYING_ENDING_KINDS

if TYPE_CHECKING:
    from cyo_adventure.player.state import ReadingState
    from cyo_adventure.storybook.evaluator import VarState
    from cyo_adventure.storybook.models import Storybook

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

DEFAULT_PATH_BUDGET = 20_000_000
"""The default ceiling on total retained path entries across all configurations.

A companion bound to :data:`DEFAULT_CONFIG_CAP`, and not redundant with it.
``configs`` retains one :class:`~cyo_adventure.player.state.ReadingState` per
configuration, and each state carries its own ``path`` list, which
:meth:`~cyo_adventure.player.engine.StoryEngine.choose` copies in full on every
transition. Memory is therefore O(configurations x depth), while
``DEFAULT_CONFIG_CAP`` bounds only the first factor. A story whose depth grows
with its configuration count (an int counter incremented inside a loop is the
canonical shape) exhausts memory long before the config cap is reached: a
five-node story of that shape OOMs the process, so the gate dies instead of
reporting on the book it was asked to judge.

Bounding the product turns that crash into the walk's already-documented
degraded path: ``capped=True``, which every caller inspects.

Calibrated against the catalog rather than guessed. Measured 2026-08-19 over the
15 conditioned committed skeletons, the largest walk retains **2,277,492** path
entries across 51,241 configurations (``16+/the-longwinter-station``), and the
runner-up 1,499,693. 20,000,000 leaves roughly nine times headroom over the
worst real book while sitting about 250 times below the point where the repro
above exhausts memory. A first attempt at 2,000,000 was set from an assumed
twenty-node mean depth without measuring, and capped ``the-longwinter-station``:
a budget under the real catalog turns this guard into the false-blocking defect
it exists to prevent, so it must be re-measured whenever the catalog's deepest
conditioned book changes.
"""

# #CRITICAL: data-integrity: `validate_policy` calls this unconditionally from
# `run_gate` on the request path, so an unbounded walk is an availability defect
# in the gate that must clear every book before a child reads it. L2-15 warns on
# the int range that produces this shape, but `validate_layer2` runs AFTER
# `validate_policy`, so the crash precedes the warning.
# #VERIFY: test_state_aware_paths.py::test_a_looping_int_counter_caps_rather_than_exhausting_memory
# and ::test_the_deepest_committed_skeleton_fits_the_path_budget.

DEFAULT_CONFIG_CAP = 100_000
"""The default ceiling on distinct configurations a walk will enumerate.

L2-12 reports a breach of this number, `validate_layer2` defaults to it, and the
author-facing headroom report measures against it, so it lives here rather than
as a literal repeated at each of them.
"""

ConfigKey = tuple[str, tuple[tuple[str, bool | int | str], ...], frozenset[str]]
"""Configuration deduplication key.

``(node_id, sorted_var_state_items, once_effect_visit_intersection)``

* ``node_id``: The current node id.
* ``sorted_var_state_items``: The variable state serialised as a sorted tuple of
  ``(name, value)`` pairs so that equal states produce equal keys regardless of
  insertion order.
* ``once_effect_visit_intersection``: The intersection of ``visit_set`` with the
  set of node ids that carry at least one ``once: true`` on_enter effect.  This
  component is the empty frozenset for stories without once-effects, making the
  key equivalent to ``(node, var_state)`` in the common case.
"""


@dataclass(frozen=True, slots=True)
class WalkResult:
    """The complete configuration closure of a story.

    Attributes:
        configs: One representative :class:`~cyo_adventure.player.state.ReadingState`
            per unique :data:`ConfigKey`.  The representative is the first state
            that produced the key during BFS.
        edges: For each :data:`ConfigKey`, the ordered list of successor
            :data:`ConfigKey` values (one per visible choice at that configuration).
            Ending configurations map to an empty list.  A non-ending configuration
            whose choices are all conditioned away ALSO maps to an empty list (a
            stateful dead-end), so callers must check ``engine.is_ending`` to tell a
            true ending apart from a dead-end.  Under a capped walk an entry may hold
            a partial successor list, and a listed successor key may be absent from
            ``configs`` (it was the configuration the cap refused to record).
        capped: ``True`` if the walk was aborted because recording the next
            configuration would have exceeded either bound: the count *cap*, or
            the memory *path_budget*. Both surface through this one flag on
            purpose, because every caller's answer to an incomplete closure is
            the same regardless of which resource ran out. Partial results are
            still returned; callers must inspect ``capped`` before relying on
            completeness. Note L2-12 reports a cap as a configuration-ceiling
            breach and quotes that number, which is the common case but not the
            only one; the remedy it advises (fewer variables, tighter bounds)
            applies to a path-budget breach too.
    """

    configs: dict[ConfigKey, ReadingState]
    edges: dict[ConfigKey, list[ConfigKey]]
    capped: bool


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def walk_configurations(  # noqa: PLR0913
    # Five parameters, one over the limit: `story` plus two independent resource
    # bounds (`cap`, `path_budget`) and two independent seeding knobs (`carried`,
    # `entry_node`). All four options are keyword-only and default correctly, and
    # bundling them into a config object would force every one of the ~15 call
    # sites to construct one to change a single value. Revisit if a sixth lands.
    story: Storybook,
    *,
    cap: int = DEFAULT_CONFIG_CAP,
    path_budget: int = DEFAULT_PATH_BUDGET,
    carried: VarState | None = None,
    entry_node: str | None = None,
) -> WalkResult:
    """Enumerate every reachable configuration in *story* via BFS.

    The walk drives the pure :class:`~cyo_adventure.player.engine.StoryEngine`
    and never re-implements transition semantics.

    Cap semantics: the instant recording a new distinct configuration would push
    ``len(configs)`` above *cap*, the walk aborts immediately.  The partially
    computed ``configs`` and ``edges`` dicts (containing only the configurations
    discovered so far) are returned with ``capped=True``.  Callers should treat a
    capped result as an incomplete exploration of the state space.

    Args:
        story: The parsed, schema-valid :class:`~cyo_adventure.storybook.models.Storybook`.
        cap: Maximum number of distinct configurations to enumerate before
            aborting.  Defaults to :data:`DEFAULT_CONFIG_CAP`.
        path_budget: Maximum total retained path entries across all recorded
            configurations before aborting.  Bounds the walk's MEMORY, which
            *cap* alone does not: retained state is O(configurations x depth).
            Defaults to :data:`DEFAULT_PATH_BUDGET`.
        carried: Carried variable values to seed the start configuration with,
            for walking a series continuation entry instead of a fresh read.
            ``None`` walks the ordinary declared-initial start. Seeding uses
            :meth:`~cyo_adventure.player.engine.StoryEngine.start_continuation`,
            so the walk sees exactly the state a real continuation reader would.
        entry_node: The node the walk begins at, or ``None`` for the story's
            ``start_node``. A series continuation must pass the receiving book's
            ``series_entry_node``: the reader enters there, so a walk seeded at
            ``start_node`` explores a path nobody takes (`UW-C296`). An id absent
            from the story falls back to ``start_node``, matching the client.

    Returns:
        WalkResult: The (possibly partial) configuration closure.
    """
    once_node_ids = _once_effect_node_ids(story)

    # #ASSUME: data integrity: the engine is pure; choose() returns a fresh state
    # and does not mutate its input, so the queued parent states stay valid as the
    # walk expands their successors.
    # #VERIFY: StoryEngine._clone() copies every mutable container on each choose();
    # no containers are shared between a parent state and its child.
    engine = StoryEngine(story)
    initial = engine.start_continuation(carried, entry_node)

    configs: dict[ConfigKey, ReadingState] = {}
    edges: dict[ConfigKey, list[ConfigKey]] = {}
    queue: deque[ReadingState] = deque()

    # cap < 1 admits no configurations at all: the start config itself would
    # push len(configs) above the cap, so abort before recording anything.
    if cap < 1:
        return WalkResult(configs=configs, edges=edges, capped=True)

    # Every config is recorded with an edge-list entry at the same moment, so the
    # invariant set(edges.keys()) == set(configs.keys()) holds at every return
    # point, including the capped early return. A config that is recorded but not
    # yet dequeued keeps its empty placeholder list (its successors are simply
    # unexplored under a capped walk); the dequeue loop overwrites the placeholder
    # with the real successor list once it expands the config.
    initial_key = _config_key(initial, once_node_ids)
    configs[initial_key] = initial
    edges[initial_key] = []
    queue.append(initial)
    # Running total of retained path entries, the walk's real memory cost. Kept
    # incrementally rather than recomputed: summing over `configs` on every
    # transition would make the guard itself quadratic.
    retained_path_entries = len(initial.path)

    while queue:
        state = queue.popleft()
        key = _config_key(state, once_node_ids)

        if engine.is_ending(state):
            edges[key] = []
            continue

        successor_keys: list[ConfigKey] = []
        # Alias into edges so a partial successor list is preserved if the cap
        # guard below returns early while this config is mid-expansion.
        edges[key] = successor_keys
        for choice in engine.visible_choices(state):
            next_state = engine.choose(state, choice.id)
            next_key = _config_key(next_state, once_node_ids)
            successor_keys.append(next_key)

            if next_key not in configs:
                # Cap check: abort before recording if doing so would exceed cap.
                if len(configs) >= cap:
                    return WalkResult(configs=configs, edges=edges, capped=True)
                # Memory check, on the same abort-before-recording contract. A
                # deepening walk blows the budget long before the config count,
                # so this is the guard that actually fires on a looping counter.
                if retained_path_entries + len(next_state.path) > path_budget:
                    return WalkResult(configs=configs, edges=edges, capped=True)
                retained_path_entries += len(next_state.path)
                configs[next_key] = next_state
                edges[next_key] = []
                queue.append(next_state)

    return WalkResult(configs=configs, edges=edges, capped=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _once_effect_node_ids(story: Storybook) -> frozenset[str]:
    """Return the set of node ids that carry at least one ``once: true`` on_enter effect.

    Computed once per story at walk start to avoid repeated scanning.

    Args:
        story: The story to inspect.

    Returns:
        frozenset[str]: Node ids with at least one ``once: true`` on_enter effect.
            Empty when the story has no such effects.
    """
    return frozenset(
        node.id for node in story.nodes if any(effect.once for effect in node.on_enter)
    )


def _config_key(state: ReadingState, once_node_ids: frozenset[str]) -> ConfigKey:
    """Compute the deduplication key for a reading state.

    See the module docstring and :data:`ConfigKey` for the soundness argument.

    Args:
        state: The reading state to key.
        once_node_ids: The set of node ids with once-effects, pre-computed from
            the story.

    Returns:
        ConfigKey: The ``(node_id, sorted_var_state, once_visit_intersection)`` key.
    """
    sorted_vars = tuple(sorted(state.var_state.items()))
    # #CRITICAL: data integrity: a once:true on_enter effect makes (node, var_state)
    # an unsound dedup key; keying on the visited once-effect nodes preserves walk
    # soundness so two paths into the same node do not wrongly collapse.
    # #VERIFY: test_config_walk covers a once-effect story where two paths into the
    # same node must NOT collapse into one configuration.
    once_intersection = frozenset(state.visit_set & once_node_ids)
    return (state.current_node, sorted_vars, once_intersection)


# ---------------------------------------------------------------------------
# Node-labelled view of the closure (UW-C292)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigDag:
    """The configuration closure as a node-labelled graph over synthetic ids.

    Rules that measure *how far a reader travels* have to walk this graph rather
    than the story's choice graph. The choice graph adds an edge for every
    declared choice and ignores ``choice.condition``, so a path through it may
    use an edge no reachable configuration can traverse. PL-20, PL-25 and PL-26
    each measured such paths until `UW-C292`; the gamebook that exposed it was
    reported as finishing in 16 nodes on a route the reader could not walk, when
    the state-aware answer was 24.

    Vertices are synthetic zero-padded ids assigned in the walk's own BFS
    discovery order, not story node ids, because one story node appears once per
    reachable configuration of it. Discovery order derives from choice
    declaration order, so the ids are stable under node renaming: a lexical
    tie-break taken on them cannot flip a verdict the way a tie-break on node ids
    could.

    Held as a plain adjacency mapping rather than a ``networkx`` graph. At the
    walk's cap the graph carries ~100 000 vertices, where building the
    ``networkx`` object cost 2.3s against 3.8s for the walk that produced it: a
    60% surcharge on a rule that already sits in the gate's request path, bought
    for an interface the two consumers do not use.

    Attributes:
        adjacency: Each synthetic vertex id to its successor vertex ids, one per
            visible choice. Every vertex has an entry, so membership testing on
            this mapping is membership in the graph.
        start: The synthetic id of the initial configuration.
        node_of: Synthetic vertex id to the story node id it sits at.
        choice_count: Synthetic vertex id to the number of *visible* choices at
            that configuration. Two choices leading to the same successor
            configuration count as two, matching how the story-graph rules count
            a node's declared choices.
    """

    adjacency: dict[str, list[str]]
    start: str
    node_of: dict[str, str]
    choice_count: dict[str, int]


def config_dag(walk: WalkResult) -> ConfigDag | None:
    """Build the node-labelled configuration graph from a completed walk.

    Args:
        walk: The configuration closure to project.

    Returns:
        ConfigDag | None: The projected graph, or None when the walk recorded no
            configuration at all (a cap of zero, or a story the engine could not
            start).
    """
    if not walk.configs:
        return None
    # Zero-padded so lexical order matches discovery order; the walk's cap is
    # 100 000 by default, three orders of magnitude inside this width.
    vertex_of = {key: f"c{index:07d}" for index, key in enumerate(walk.configs)}
    node_of = {vertex: key[0] for key, vertex in vertex_of.items()}
    choice_count: dict[str, int] = {}
    adjacency: dict[str, list[str]] = {}
    for key, vertex in vertex_of.items():
        successors = walk.edges.get(key, [])
        choice_count[vertex] = len(successors)
        # A capped walk can list a successor it refused to record; those have no
        # vertex and are dropped rather than left as dangling ids.
        adjacency[vertex] = [
            vertex_of[successor] for successor in successors if successor in vertex_of
        ]
    return ConfigDag(
        adjacency=adjacency,
        start=next(iter(vertex_of.values())),
        node_of=node_of,
        choice_count=choice_count,
    )


def fastest_satisfying_finish(story: Storybook, walk: WalkResult) -> int | None:
    """Return the fewest configuration-path nodes to a satisfying finish.

    The state-aware reading of PL-20's clock: the minimum number of nodes on a
    *configuration* path from the initial configuration to any configuration at a
    ``success``/``completion`` ending. A shorter route through the story's choice
    graph does not count if no reader can hold the state that opens it.

    Args:
        story: The parsed story, read for its ending kinds.
        walk: The configuration closure to measure over.

    Returns:
        int | None: The minimum configuration-path node count (hops + 1), or None
            when no satisfying finish is reachable in any configuration.
    """
    dag = config_dag(walk)
    if dag is None:
        return None
    satisfying = {
        node.id
        for node in story.nodes
        if node.is_ending
        and node.ending is not None
        and node.ending.kind in SATISFYING_ENDING_KINDS
    }
    if not satisfying:
        return None
    seen: set[str] = {dag.start}
    queue: deque[tuple[str, int]] = deque([(dag.start, 1)])
    while queue:
        vertex, nodes = queue.popleft()
        if dag.node_of[vertex] in satisfying:
            return nodes
        for successor in dag.adjacency[vertex]:
            if successor not in seen:
                seen.add(successor)
                queue.append((successor, nodes + 1))
    return None
