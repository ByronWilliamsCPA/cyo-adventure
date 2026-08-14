"""Root-to-ending path enumeration, the reading unit our metrics were missing.

Every craft measure this repository owns is computed over a whole book: the
Flesch-Kincaid grade in :mod:`~cyo_adventure.validator.reading_level`, the tense
and told-emotion counts in ``scripts/check_prose_craft.py``, the leaf-diversity
scores in :mod:`~cyo_adventure.moderation.leaf_diversity`. A child does not read
a whole book. A child reads one path through it, and a book whose aggregate sits
comfortably inside the target band can still contain a path that does not. This
module produces the paths so those measures can be re-unitted (W1 and W2 in
``docs/planning/cyo-measurement-workplan-2026-08-12.md``).

Three design commitments, each of which a test pins down:

**Paths come from driving the engine.** Like
:mod:`~cyo_adventure.validator.walk`, this module never re-implements transition
semantics. It asks :class:`~cyo_adventure.player.engine.StoryEngine` for the
visible choices and for the next state, so conditioned-away options, ``once``
effects, and variable clamping behave here exactly as they do for a reader.

**Two path sets, never pooled.** :func:`covering_paths` answers "does *any*
reading go wrong", so it must touch every reachable choice. :func:`reader_sample_paths`
answers "does a *typical* reading go wrong", so it must be drawn the way a reader
generates one. Averaging a covering set is not an estimate of anything a reader
experiences, because the covering set deliberately over-samples rare branches.
Averaging a sample says nothing about the worst path. Keep the two apart.

**The reader sample is uniform over choices, not over paths.** At each fork the
sampler picks one visible option with equal probability. That is the reader
model we want. Uniform-over-paths would instead weight a reading by how many
distinct readings share its shape, over-representing whichever subtree happens
to branch the most, which is a property of the graph rather than of any child.

Two honesty constraints on the output:

* The covering set is **greedy, not minimal**. Finding a minimum path cover is a
  flow problem and we do not need the optimum; we need every choice read at
  least once. :attr:`PathSet.edge_coverage` is the number that matters, and the
  path count is incidental.
* A truncated enumeration reports ``complete=False`` rather than returning a
  smaller set quietly. A partial path set understates every spread computed from
  it, and a spread that is understated for an unstated reason is worse than one
  that is refused.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from cyo_adventure.player.engine import StoryEngine
from cyo_adventure.validator.walk import walk_configurations

if TYPE_CHECKING:
    from cyo_adventure.player.state import ReadingState
    from cyo_adventure.storybook.evaluator import VarState
    from cyo_adventure.storybook.models import Storybook

__all__ = [
    "Draw",
    "PathSet",
    "covering_paths",
    "path_bodies",
    "reader_sample_paths",
]

# A path-local key used only to cut cycles during depth-first enumeration.
#
# These are exactly walk.ConfigKey's semantics: ``visit_set`` folded down to its
# intersection with the once-effect nodes, because that intersection is the only
# part of visit history that changes what happens next. An earlier version keyed
# on the full ``visit_set`` on the theory that a finer key can only be safer. It
# is not safer, it is wrong: revisiting a node in an identical situation offers
# identical choices, so the finer key does not preserve any reading a child could
# take, it just refuses to notice a loop. On the 250-node
# ``the-winter-of-the-wolf-queen`` it produced 1730-step readings.
_PathKey = tuple[str, tuple[tuple[str, bool | int | str], ...], frozenset[str]]

# One choice at one node. This, and not walk's ConfigKey, is what the covering
# set covers: authoring cares that every written option gets read, not that every
# (node, variable-state) pair gets visited.
_ChoiceEdge = tuple[str, str]

_DEFAULT_PATH_CAP = 20_000
"""Maximum root-to-ending paths explored before an enumeration gives up.

Path counts are exponential in fork depth even when the configuration graph is
small, so a cap is mandatory rather than defensive.
"""

_DEFAULT_WALK_CAP = 100_000
"""Configuration cap handed to the closure walk, matching walk.py's own default."""

_STEPS_PER_NODE = 10
"""Steps allowed per node before a walk stops counting as a reading.

Ten times the node count is generous: it lets a reading revisit every node ten
times over. Anything past that is a state loop, not a story.
"""


@dataclass(frozen=True, slots=True)
class Draw:
    """One reproducible sampling draw: how many readings, from which seed.

    The two travel together because a count without its seed describes a
    measurement nobody can re-derive, and this module's whole argument for
    sampling rests on the draw being re-runnable by anyone who has the
    parameters. Record the whole object in any report that quotes a
    sample-derived number.

    Attributes:
        count (int): Number of readings to draw.
        seed (int): PRNG seed fully determining the draw.

    Raises:
        ValueError: If ``count`` is not positive. A zero or negative count
            would make the sampling loop below draw nothing while still
            reporting ``complete=True`` (its early-exit tracker starts
            ``True`` and the loop that could flip it false never runs), which
            reads as a valid, complete empty sample rather than a
            misconfigured draw.
    """

    count: int
    seed: int

    def __post_init__(self) -> None:
        """Reject a non-positive draw count.

        Raises:
            ValueError: If ``count`` is not positive.
        """
        if self.count <= 0:
            msg = f"Draw.count must be positive, got {self.count}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PathSet:
    """A set of root-to-ending readings through one story.

    Attributes:
        paths (list[list[str]]): Each reading as its ordered list of node ids,
            starting at the story's ``start_node`` and ending at a node with
            ``is_ending``. Sampled sets may repeat a path; that repetition
            carries the frequency information and must not be deduplicated.
        mode (Literal["covering", "sample"]): ``"covering"`` (every reachable
            choice read at least once) or ``"sample"`` (drawn as a reader would
            generate readings). Never pool the two: they answer different
            questions and are drawn from different distributions.
        complete (bool): ``False`` when the enumeration was truncated, when the
            underlying configuration walk was capped, or when a sampled walk
            failed to reach an ending. Callers must suppress any derived
            statistic rather than report one computed from a partial set.
        edge_coverage (float): Share of reachable choices read by at least one
            path in :attr:`paths`. ``1.0`` for a complete covering set. Below
            ``1.0`` in a covering set means either truncation or a choice that
            leads only into a dead-end, both of which are worth surfacing.
        reachable_choices (int): Denominator of :attr:`edge_coverage`, the
            number of distinct ``(node_id, choice_id)`` pairs visible from at
            least one reachable configuration. ``0`` for a story with no
            choices at all.
    """

    paths: list[list[str]]
    mode: Literal["covering", "sample"]
    complete: bool
    edge_coverage: float
    reachable_choices: int


def _once_effect_nodes(story: Storybook) -> frozenset[str]:
    """Ids of nodes carrying at least one ``once: true`` on-enter effect.

    Only these nodes' visit history can change what a later visit does, so only
    these belong in the cycle-cutting key.

    Args:
        story (Storybook): The story to scan.

    Returns:
        frozenset[str]: The once-effect node ids, empty for most stories.
    """
    return frozenset(
        node.id for node in story.nodes if any(effect.once for effect in node.on_enter)
    )


def _reading_length_limit(story: Storybook) -> int:
    """Maximum node count in something we are willing to call a reading.

    Shared by both enumerators so they agree on what a reading is. A story with
    variables can be walked far past its own node count by looping through
    state changes; the resulting sequence is a valid engine trace but not a
    reading any child performs, and enumerating them exhausts the path budget
    on material no measure should be taken over.

    Args:
        story (Storybook): The story being enumerated.

    Returns:
        int: The node-count ceiling for one path.
    """
    return max(len(story.nodes) * _STEPS_PER_NODE, _STEPS_PER_NODE)


def _path_key(state: ReadingState, once_nodes: frozenset[str]) -> _PathKey:
    """Build the cycle-cutting key for a state.

    Args:
        state (ReadingState): The reading state to key.
        once_nodes (frozenset[str]): Ids of nodes with ``once`` on-enter
            effects, from :func:`_once_effect_nodes`.

    Returns:
        _PathKey: ``(node_id, sorted var state, once-effect visits)``.
    """
    return (
        state.current_node,
        tuple(sorted(state.var_state.items())),
        frozenset(state.visit_set) & once_nodes,
    )


@dataclass(frozen=True, slots=True)
class _ConfigGraph:
    """The configuration closure indexed for targeted path construction.

    Attributes:
        out (dict[_PathKey, list[tuple[str, _PathKey]]]): Per configuration, its
            ``(choice_id, successor_key)`` transitions.
        pred (dict[_PathKey, tuple[_PathKey, str]]): Per configuration reachable
            from the start, the ``(parent_key, choice_id)`` on a shortest route
            from the start. The initial configuration is absent, being its own
            root.
        to_end (dict[_PathKey, tuple[str, _PathKey]]): Per configuration that can
            still reach an ending, the ``(choice_id, successor_key)`` first step
            of a shortest route to one. Ending configurations are absent, having
            arrived.
        by_edge (dict[_ChoiceEdge, list[tuple[_PathKey, _PathKey]]]): Per
            ``(node_id, choice_id)``, the configurations at which that choice is
            visible, in walk order so selection stays deterministic.
        initial (_PathKey): The starting configuration's key.
        endings (set[_PathKey]): Keys of configurations at an ending node.
        complete (bool): ``False`` when the closure walk hit its cap.
    """

    out: dict[_PathKey, list[tuple[str, _PathKey]]]
    pred: dict[_PathKey, tuple[_PathKey, str]]
    to_end: dict[_PathKey, tuple[str, _PathKey]]
    by_edge: dict[_ChoiceEdge, list[tuple[_PathKey, _PathKey]]]
    initial: _PathKey
    endings: set[_PathKey]
    complete: bool


def _build_config_graph(
    story: Storybook,
    *,
    carried: VarState | None,
    walk_cap: int,
) -> _ConfigGraph:
    """Walk the story's configuration closure and index it both directions.

    The forward index answers "how do I get to this configuration" and the
    backward index answers "how do I get from it to an ending". Together they
    let a caller construct a complete reading through any chosen fork without
    searching for one, which is what makes coverage independent of search order.

    Args:
        story (Storybook): The story to analyse.
        carried (VarState | None): Optional carried variable state for a series
            continuation.
        walk_cap (int): Configuration cap for the closure walk.

    Returns:
        _ConfigGraph: The indexed closure.
    """
    walk = walk_configurations(story, cap=walk_cap, carried=carried)
    engine = StoryEngine(story)
    once_nodes = _once_effect_nodes(story)

    out: dict[_PathKey, list[tuple[str, _PathKey]]] = {}
    by_edge: dict[_ChoiceEdge, list[tuple[_PathKey, _PathKey]]] = {}
    endings: set[_PathKey] = set()
    incoming: dict[_PathKey, list[tuple[_PathKey, str]]] = {}

    for state in walk.configs.values():
        key = _path_key(state, once_nodes)
        out[key] = []
        if engine.is_ending(state):
            endings.add(key)
            continue
        for choice in engine.visible_choices(state):
            successor = _path_key(engine.choose(state, choice.id), once_nodes)
            out[key].append((choice.id, successor))
            by_edge.setdefault((state.current_node, choice.id), []).append(
                (key, successor)
            )
            incoming.setdefault(successor, []).append((key, choice.id))

    initial = _path_key(engine.start_continuation(carried), once_nodes)

    # Forward breadth-first from the start: shortest route in, per configuration.
    pred: dict[_PathKey, tuple[_PathKey, str]] = {}
    frontier = deque([initial])
    reached = {initial}
    while frontier:
        key = frontier.popleft()
        for choice_id, successor in out.get(key, ()):
            if successor in reached or successor not in out:
                continue
            reached.add(successor)
            pred[successor] = (key, choice_id)
            frontier.append(successor)

    # Backward breadth-first from every ending: shortest route out, per
    # configuration. Following one step strictly decreases the distance to an
    # ending, so the route it describes can never loop.
    to_end: dict[_PathKey, tuple[str, _PathKey]] = {}
    frontier = deque(endings)
    settled = set(endings)
    while frontier:
        key = frontier.popleft()
        for parent, choice_id in incoming.get(key, ()):
            if parent in settled:
                continue
            settled.add(parent)
            to_end[parent] = (choice_id, key)
            frontier.append(parent)

    return _ConfigGraph(
        out=out,
        pred=pred,
        to_end=to_end,
        by_edge=by_edge,
        initial=initial,
        endings=endings,
        complete=not walk.capped,
    )


def _reading_through(
    graph: _ConfigGraph, key: _PathKey, choice_id: str, successor: _PathKey
) -> tuple[list[str], list[_ChoiceEdge]] | None:
    """Build a complete reading that takes *choice_id* at *key*.

    Splices the shortest route in with the shortest route out, so the reading
    carries the least incidental material around the fork under test.

    Args:
        graph (_ConfigGraph): The indexed configuration closure.
        key (_PathKey): Configuration at which the choice is taken.
        choice_id (str): The choice to exercise.
        successor (_PathKey): Configuration the choice leads to.

    Returns:
        tuple[list[str], list[_ChoiceEdge]] | None: The reading's node ids and
        choice edges, or ``None`` when the configuration is unreachable from the
        start or the successor cannot reach an ending, in which case no reading
        exercises this choice.
    """
    if key != graph.initial and key not in graph.pred:
        return None
    if successor not in graph.endings and successor not in graph.to_end:
        return None

    prefix: list[tuple[_PathKey, str]] = []
    cursor = key
    while cursor != graph.initial:
        parent, taken = graph.pred[cursor]
        prefix.append((parent, taken))
        cursor = parent
    prefix.reverse()

    nodes = [parent[0] for parent, _taken in prefix]
    edges = [(parent[0], taken) for parent, taken in prefix]

    nodes.append(key[0])
    edges.append((key[0], choice_id))

    cursor = successor
    while cursor not in graph.endings:
        nodes.append(cursor[0])
        step_choice, following = graph.to_end[cursor]
        edges.append((cursor[0], step_choice))
        cursor = following
    nodes.append(cursor[0])

    return nodes, edges


def covering_paths(
    story: Storybook,
    *,
    cap: int = _DEFAULT_PATH_CAP,
    walk_cap: int = _DEFAULT_WALK_CAP,
    carried: VarState | None = None,
) -> PathSet:
    """Build a set of readings that together read every reachable choice.

    Each still-uncovered choice gets a reading constructed through it, spliced
    from the shortest route in and the shortest route out. That construction is
    what makes the result a covering set rather than a sample: coverage does not
    depend on how much budget the search had or which subtree it entered first.

    An earlier version enumerated readings depth first and kept the ones that
    added coverage. On any book with more readings than budget it spent
    everything inside one subtree, reporting 30 percent coverage on a real
    catalogue title while behaving exactly as designed. Enumerate-and-filter is
    the wrong shape for this job.

    The set is greedy, not minimal: a reading is kept whenever it covers
    something new, and no attempt is made to find the fewest such readings.
    Treat :attr:`PathSet.edge_coverage` as the result and ``len(paths)`` as
    incidental.

    Use this to answer "is any reading bad", never "is the average reading
    bad"; for the latter see :func:`reader_sample_paths`.

    Args:
        story (Storybook): The story to enumerate.
        cap (int): Maximum readings to keep before giving up.
        walk_cap (int): Configuration cap for the underlying closure walk. A
            capped walk yields an incomplete coverage denominator, so it forces
            ``complete=False``.
        carried (VarState | None): Optional carried variable state for a series
            continuation.

    Returns:
        PathSet: The covering set, in ``mode="covering"``.
    """
    graph = _build_config_graph(story, carried=carried, walk_cap=walk_cap)
    reachable = set(graph.by_edge)

    kept: list[list[str]] = []
    covered: set[_ChoiceEdge] = set()
    truncated = False

    for edge in sorted(reachable):
        if edge in covered:
            continue
        if len(kept) >= cap:
            truncated = True
            break
        for key, successor in graph.by_edge[edge]:
            reading = _reading_through(graph, key, edge[1], successor)
            if reading is None:
                continue
            nodes, edges = reading
            kept.append(nodes)
            covered.update(edges)
            break

    return PathSet(
        paths=kept,
        mode="covering",
        complete=graph.complete and not truncated,
        edge_coverage=len(covered) / len(reachable) if reachable else 1.0,
        reachable_choices=len(reachable),
    )


def reader_sample_paths(
    story: Storybook,
    draw: Draw,
    *,
    walk_cap: int = _DEFAULT_WALK_CAP,
    carried: VarState | None = None,
) -> PathSet:
    """Draw readings the way a reader would generate them.

    At each fork one visible option is chosen with equal probability. This is a
    uniform distribution over *choices*, which is the reader model; it is not a
    uniform distribution over *paths*, and the difference is the point. A book
    whose left branch splits four more times and whose right branch runs
    straight to an ending has five paths, but a child meets the first fork once
    and goes left half the time.

    The sample is fully determined by *seed*, so any number computed from it can
    be re-derived by anyone who has the seed. A measurement nobody can re-run is
    not evidence.

    Args:
        story (Storybook): The story to sample.
        draw (Draw): How many readings to take and from which seed. Repeats are
            kept, because the repetition is the frequency information.
            Reproducibility is the requirement here, which is exactly why a
            cryptographic generator would be the wrong choice for the draw.
        walk_cap (int): Configuration cap for the underlying closure walk. A
            capped walk yields an incomplete coverage denominator, so it forces
            ``complete=False``.
        carried (VarState | None): Optional carried variable state for a series
            continuation.

    Returns:
        PathSet: The drawn readings, in ``mode="sample"``.
    """
    graph = _build_config_graph(story, carried=carried, walk_cap=walk_cap)
    reachable = set(graph.by_edge)
    walk_complete = graph.complete
    engine = StoryEngine(story)
    # S311 false positive: the rule warns that `random` is unsuitable for
    # cryptographic purposes, and nothing here is cryptographic. This draws a
    # measurement sample whose whole value is that a reader can re-derive it
    # from `seed`, and a CSPRNG cannot be seeded to reproduce a draw. Swapping
    # in `secrets` would satisfy the linter by destroying the requirement.
    rng = random.Random(draw.seed)  # noqa: S311
    step_budget = _reading_length_limit(story)

    drawn: list[list[str]] = []
    covered: set[_ChoiceEdge] = set()
    all_reached_an_ending = True

    for _ in range(draw.count):
        state = engine.start_continuation(carried)
        nodes = [state.current_node]
        edges: list[_ChoiceEdge] = []
        steps = 0

        while not engine.is_ending(state) and steps < step_budget:
            options = engine.visible_choices(state)
            if not options:
                # A stateful dead-end. Recording the truncated walk would put a
                # partial reading into a set the caller will average over, so
                # drop it and say the set is incomplete instead.
                break
            choice = options[rng.randrange(len(options))]
            edges.append((state.current_node, choice.id))
            state = engine.choose(state, choice.id)
            nodes.append(state.current_node)
            steps += 1

        if engine.is_ending(state):
            drawn.append(nodes)
            covered.update(edges)
        else:
            all_reached_an_ending = False

    return PathSet(
        paths=drawn,
        mode="sample",
        complete=walk_complete and all_reached_an_ending,
        edge_coverage=len(covered) / len(reachable) if reachable else 1.0,
        reachable_choices=len(reachable),
    )


def path_bodies(story: Storybook, path: list[str]) -> list[str]:
    """Return the node bodies along *path*, in traversal order.

    This is the bridge to the existing measures. ``measure_book`` and the
    prose-craft counters take an iterable of bodies and do not care whether
    those bodies constitute a book or one reading through it, so per-path
    measurement is a caller change rather than a new metric.

    Args:
        story (Storybook): The story the path runs through.
        path (list[str]): Ordered node ids, as produced by
            :func:`covering_paths` or :func:`reader_sample_paths`.

    Returns:
        list[str]: One body per node id, in order.

    Raises:
        KeyError: If *path* names a node the story does not contain. Returning
            an empty body instead would silently pull a reading-level grade
            toward whatever the remaining nodes score.
    """
    by_id = {node.id: node for node in story.nodes}
    bodies: list[str] = []
    for node_id in path:
        node = by_id.get(node_id)
        if node is None:
            msg = f"node {node_id!r} is not in story {story.id!r}"
            raise KeyError(msg)
        bodies.append(node.body)
    return bodies
