"""Layer-2 configuration-walk core (Phase 2).

Enumerates every reachable story *configuration* by driving the pure
:class:`~cyo_adventure.player.engine.StoryEngine`.  A *configuration* is a
distinct (node_id, var_state, relevant_visit_set) triple that can arise from
any sequence of choices.  The walk is the foundation on which the Layer-2
state-space validator rules (L2-9..L2-12) are built.

Transition semantics remain in the engine; this module only orchestrates the
BFS closure over the reachable state space.

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

if TYPE_CHECKING:
    from cyo_adventure.player.state import ReadingState
    from cyo_adventure.storybook.models import Storybook

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

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
        capped: ``True`` if the walk was aborted because the number of distinct
            configurations would have exceeded *cap*.  Partial results are still
            returned; callers must inspect ``capped`` before relying on completeness.
    """

    configs: dict[ConfigKey, ReadingState]
    edges: dict[ConfigKey, list[ConfigKey]]
    capped: bool


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def walk_configurations(story: Storybook, *, cap: int = 100_000) -> WalkResult:
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
            aborting.  Defaults to 100 000.

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
    initial = engine.start()

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
