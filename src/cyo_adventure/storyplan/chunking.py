"""Chunked plan writing: size check, scene partition, entry facts, stitch, routing.

A Story Plan names every node and choice of its shape. After the density fixes
of 2026-11-21 a dense plan for the largest retained 8-11 shape
(``the-lantern-keepers-list``, 132 nodes and 314 choices) no longer fits one
call: the retrial stopped at ``max_tokens`` 32,000 with 11,071 reasoning
tokens spent (``AL-855``), and a reasoning token budget did not cap reasoning
on that model (``AL-856``), so the fix cannot rely on limiting reasoning. This
module holds the pure parts of writing such a plan in pieces; the calls
themselves are made by :mod:`cyo_adventure.storyplan.generate`.

* **Size check.** :func:`estimate_plan_size` estimates a one-call plan's output
  from the shape (nodes, choices, threads) plus a reasoning allowance, and
  :func:`choose_write_mode` compares it with the output cap.
* **Scene partition.** :func:`partition_scenes` cuts the shape into contiguous
  scenes deterministically from the graph (reading order by breadth-first
  depth, cut into slices of roughly equal estimated output). The model is
  given the partition; it never chooses it.
* **Entry facts.** :func:`entry_knowledge` computes what every reader is
  guaranteed to know on entry to each node from what has been planned so far,
  so a scene written after earlier scenes sees what they established at its
  boundary.
* **Stitch.** :func:`stitch` merges the spine and the scene entries into the
  model sections, merging each scene's proposed facts into the ledger and
  renaming a proposed fact whose id collides with a different fact.
* **Routing.** :func:`route_findings` and :func:`route_load_errors` send each
  finding to the part that owns it: a node or choice to its scene, a thread,
  ending, cast or truth matter to the spine, a fact to whichever part declared
  it.

Calibration (2026-11-22, ``docs/planning/evidence/plan-generation-retrial-2026-11-21``)
=====================================================================================

Visible output (output tokens less reasoning tokens) of the five completed
plan calls, split across the plan's sections by their share of characters:

====  ===================  =====  =======  =======  ===============  =================
Run   Shape                Nodes  Choices  Visible  Per node (incl.  Per choice
                                                    facts, endings)
====  ===================  =====  =======  =======  ===============  =================
1     the-locked-carousel  71     118      10,645   84               40
2     the-cave-of-echoes   65     64       8,859    98               39
3     the-locked-carousel  71     118      13,615   120              43
4     the-locked-carousel  71     118      10,735   89               37
5     the-cave-of-echoes   65     64       9,169    99               43
====  ===================  =====  =======  =======  ===============  =================

Reasoning on those calls was 849 to 3,717 tokens (0.06 to 0.41 of visible
output); run 6 (``the-lantern-keepers-list``) spent 11,071 reasoning tokens
while writing at least 20,929 visible tokens before the cap (0.53, a lower
bound). The constants below take the upper end of the per-node and per-choice
costs and a reasoning allowance above every observed ratio.
"""

from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, cast

from cyo_adventure.storyplan.checks import guaranteed_on_entry

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping, Sequence

    from cyo_adventure.storybook.models import Storybook

__all__ = [
    "CHUNK_SHARE",
    "OUTPUT_HEADROOM",
    "REASONING_FLOOR",
    "REASONING_SHARE",
    "SPINE",
    "TOKENS_FIXED",
    "TOKENS_PER_CHOICE",
    "TOKENS_PER_ENDING_GIFT",
    "TOKENS_PER_LEDGER_NODE",
    "TOKENS_PER_NODE",
    "TOKENS_PER_THREAD",
    "WRITE_MODES",
    "ChunkEntries",
    "PlanSizeEstimate",
    "PlanWriteMode",
    "Routed",
    "Scene",
    "StitchResult",
    "boundary_nodes",
    "choose_write_mode",
    "content_tokens",
    "entry_knowledge",
    "estimate_plan_size",
    "estimate_spine_size",
    "max_chunk_content",
    "owners",
    "partition_scenes",
    "reading_order",
    "reasoning_allowance",
    "route_findings",
    "route_load_errors",
    "scene_content",
    "split_scene",
    "stitch",
    "undeclared_facts",
]

PlanWriteMode = Literal["auto", "single", "chunked"]
"""``Settings.story_plan_write_mode``: force one call, force chunks, or decide."""

WRITE_MODES: Final[tuple[str, ...]] = ("auto", "single", "chunked")

SPINE: Final = "spine"
"""The part id of the spine call (scene ids are ``S1``, ``S2`` ...)."""

TOKENS_PER_NODE: Final = 110
"""Visible output per node in one-call mode, its share of facts and endings included.

Runs 1 to 5 measured 84 to 120 (mean 98); the upper end is taken.
"""

TOKENS_PER_CHOICE: Final = 42
"""Visible output per choice (runs 1 to 5: 37 to 43, mean 40)."""

TOKENS_PER_THREAD: Final = 150
"""Visible output per thread (smoke run 6 of 2026-11-21: three threads in 1,273 characters)."""

TOKENS_FIXED: Final = 500
"""JSON framing, cast and truth not already in the per-node share."""

TOKENS_PER_LEDGER_NODE: Final = 55
"""Spine ledger output per node: the facts section ran 98 to 164 characters per node."""

TOKENS_PER_ENDING_GIFT: Final = 35
"""Spine output per ending gift (endings sections ran about 115 characters each)."""

REASONING_SHARE: Final = 0.6
"""Reasoning allowance as a share of visible output (observed 0.06 to 0.53)."""

REASONING_FLOOR: Final = 4_000
"""The least reasoning allowed for any call (the most on a completed call: 3,717)."""

OUTPUT_HEADROOM: Final = 0.9
"""Share of the output cap a call may be estimated to need and still be made."""

CHUNK_SHARE: Final = 0.5
"""Share of the headroomed cap a scene targets, so a scene that runs to twice its
estimate still fits; a truncated scene costs a split and a second call."""

_ALIAS_SUFFIX_MAX: Final = 64
_COLLISION_TEXT_SPACE: Final = re.compile(r"\s+")
_LOCATED: Final = re.compile(r"^(?P<section>nodes|choices|facts)\.(?P<key>[^.\s]+)")
_SPINE_SECTIONS: Final[tuple[str, ...]] = ("cast", "truth", "threads", "endings")
_SPINE_RULES: Final = frozenset({"SP-0", "SP-5", "SP-7"})
_TOKEN: Final = re.compile(r"[A-Za-z0-9_-]+")


# ---------------------------------------------------------------------------
# Size check
# ---------------------------------------------------------------------------


def reasoning_allowance(content: int) -> int:
    """Return the reasoning tokens to allow beside ``content`` visible tokens.

    Args:
        content: Estimated visible output.

    Returns:
        int: ``max(REASONING_FLOOR, REASONING_SHARE * content)``, rounded up.
    """
    return max(REASONING_FLOOR, math.ceil(REASONING_SHARE * content))


def content_tokens(nodes: int, choices: int, threads: int = 0) -> int:
    """Return the estimated visible output for node and choice entries.

    Args:
        nodes: Node entries to write.
        choices: Choice entries to write.
        threads: Thread entries to write.

    Returns:
        int: Estimated visible output tokens, the fixed framing included.
    """
    return (
        TOKENS_FIXED
        + TOKENS_PER_NODE * nodes
        + TOKENS_PER_CHOICE * choices
        + TOKENS_PER_THREAD * threads
    )


@dataclass(frozen=True, slots=True)
class PlanSizeEstimate:
    """An estimate of one call's output against the output cap.

    Attributes:
        nodes: Node entries the call writes.
        choices: Choice entries the call writes.
        threads: Thread entries the call writes.
        endings: Ending entries the call writes.
        content: Estimated visible output tokens.
        reasoning: The reasoning allowance (:func:`reasoning_allowance`).
        cap: The output cap the call runs under (``resolve_output_cap``).
    """

    nodes: int
    choices: int
    threads: int
    endings: int
    content: int
    reasoning: int
    cap: int

    @property
    def total(self) -> int:
        """Return visible output plus the reasoning allowance.

        Returns:
            int: The estimated tokens the call bills against the cap.
        """
        return self.content + self.reasoning

    @property
    def budget(self) -> int:
        """Return the share of the cap a call may be estimated to need.

        Returns:
            int: ``floor(cap * OUTPUT_HEADROOM)``.
        """
        return math.floor(self.cap * OUTPUT_HEADROOM)

    @property
    def fits(self) -> bool:
        """Return whether the estimate fits under the headroomed cap.

        Returns:
            bool: True when :attr:`total` is at most :attr:`budget`.
        """
        return self.total <= self.budget

    def to_dict(self) -> dict[str, object]:
        """Return the estimate as a JSON-serialisable mapping.

        Returns:
            dict[str, object]: Every field plus ``total``, ``budget``, ``fits``.
        """
        return {
            "nodes": self.nodes,
            "choices": self.choices,
            "threads": self.threads,
            "endings": self.endings,
            "content_tokens": self.content,
            "reasoning_tokens": self.reasoning,
            "total_tokens": self.total,
            "cap": self.cap,
            "budget": self.budget,
            "fits": self.fits,
        }


def estimate_plan_size(book: Storybook, *, cap: int) -> PlanSizeEstimate:
    """Estimate a one-call plan's output for ``book`` under ``cap``.

    Args:
        book: The shape.
        cap: The resolved output cap.

    Returns:
        PlanSizeEstimate: The estimate.
    """
    nodes = len(book.nodes)
    choices = sum(len(node.choices) for node in book.nodes)
    threads = len(book.variables)
    content = content_tokens(nodes, choices, threads)
    return PlanSizeEstimate(
        nodes=nodes,
        choices=choices,
        threads=threads,
        endings=sum(1 for node in book.nodes if node.is_ending),
        content=content,
        reasoning=reasoning_allowance(content),
        cap=cap,
    )


def estimate_spine_size(book: Storybook, *, cap: int) -> PlanSizeEstimate:
    """Estimate the spine call's output (ledger, threads, gifts, scene lines).

    Args:
        book: The shape.
        cap: The resolved output cap.

    Returns:
        PlanSizeEstimate: The estimate; ``nodes`` counts the nodes the ledger
            covers, ``choices`` is zero.
    """
    nodes = len(book.nodes)
    endings = sum(1 for node in book.nodes if node.is_ending)
    threads = len(book.variables)
    content = (
        TOKENS_FIXED
        + TOKENS_PER_LEDGER_NODE * nodes
        + TOKENS_PER_ENDING_GIFT * endings
        + TOKENS_PER_THREAD * threads
    )
    return PlanSizeEstimate(
        nodes=nodes,
        choices=0,
        threads=threads,
        endings=endings,
        content=content,
        reasoning=reasoning_allowance(content),
        cap=cap,
    )


def choose_write_mode(
    setting: PlanWriteMode, estimate: PlanSizeEstimate
) -> tuple[Literal["single", "chunked"], str]:
    """Choose single-call or chunked writing.

    Args:
        setting: ``auto``, or a forced mode.
        estimate: The one-call estimate.

    Returns:
        tuple[Literal["single", "chunked"], str]: The mode and why.
    """
    if setting == "single":
        return "single", "forced by setting"
    if setting == "chunked":
        return "chunked", "forced by setting"
    if estimate.fits:
        return "single", (
            f"estimate {estimate.total} tokens fits the budget {estimate.budget} "
            f"of cap {estimate.cap}"
        )
    return "chunked", (
        f"estimate {estimate.total} tokens exceeds the budget {estimate.budget} "
        f"of cap {estimate.cap}"
    )


# ---------------------------------------------------------------------------
# Scene partition
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Scene:
    """A contiguous slice of the shape written by one chunk call.

    Attributes:
        id: ``S1`` ... in reading order; a split scene's halves add ``a``/``b``.
        nodes: Real node ids, in reading order. A scene owns these nodes and
            every choice out of them.
        split: True for a half of a split scene, which is never split again.
    """

    id: str
    nodes: tuple[str, ...]
    split: bool = False


def reading_order(book: Storybook) -> list[str]:
    """Return node ids breadth-first from the start, then any unreached in book order.

    Args:
        book: The shape.

    Returns:
        list[str]: Every node id once.
    """
    known = {node.id for node in book.nodes}
    targets = {node.id: [c.target for c in node.choices] for node in book.nodes}
    order: list[str] = []
    seen: set[str] = set()
    queue: deque[str] = deque([book.start_node] if book.start_node in known else [])
    seen.update(queue)
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for target in targets.get(node_id, []):
            if target in known and target not in seen:
                seen.add(target)
                queue.append(target)
    order.extend(node.id for node in book.nodes if node.id not in seen)
    return order


def scene_content(book: Storybook, node_ids: Iterable[str]) -> int:
    """Return the estimated visible output of a scene's entries.

    Args:
        book: The shape.
        node_ids: The scene's nodes.

    Returns:
        int: Per-node plus per-choice cost, without the fixed framing.
    """
    by_id = {node.id: node for node in book.nodes}
    return sum(
        TOKENS_PER_NODE + TOKENS_PER_CHOICE * len(by_id[n].choices) for n in node_ids
    )


def max_chunk_content(cap: int) -> int:
    """Return the most visible output one scene may be estimated to need.

    The scene's total (content plus :func:`reasoning_allowance`) must stay
    within ``CHUNK_SHARE`` of the headroomed cap.

    Args:
        cap: The resolved output cap.

    Returns:
        int: The content ceiling (at least one token).
    """
    budget = math.floor(cap * OUTPUT_HEADROOM * CHUNK_SHARE) - TOKENS_FIXED
    return max(
        1, min(budget - REASONING_FLOOR, math.floor(budget / (1 + REASONING_SHARE)))
    )


def _cut(
    order: Sequence[str], weights: Mapping[str, int], parts: int
) -> list[list[str]]:
    """Cut ``order`` into ``parts`` contiguous slices of roughly equal weight.

    Args:
        order: Node ids in reading order.
        weights: Per node, its estimated content.
        parts: How many slices.

    Returns:
        list[list[str]]: Non-empty slices, at most ``parts`` of them.
    """
    total = sum(weights[n] for n in order)
    slices: list[list[str]] = [[]]
    running = 0
    for node_id in order:
        boundary = total * len(slices) / parts
        if (
            slices[-1]
            and running + weights[node_id] / 2 > boundary
            and len(slices) < parts
        ):
            slices.append([])
        slices[-1].append(node_id)
        running += weights[node_id]
    return [s for s in slices if s]


def partition_scenes(book: Storybook, *, cap: int) -> list[Scene]:
    """Partition a shape into contiguous scenes that each fit a chunk call.

    The partition is computed, not asked for: the model would have to read
    the whole graph to cut it, and a cut it chose could leave a scene too big
    for its call. Nodes are taken in breadth-first reading order (depth bands
    from the start), so a scene's predecessors are mostly in earlier scenes
    and the facts guaranteed at its boundary are known when it is written.
    The order is cut into the fewest slices of roughly equal estimated output
    that each fit :func:`max_chunk_content`, and never fewer than two.

    Args:
        book: The shape.
        cap: The resolved output cap.

    Returns:
        list[Scene]: Scenes ``S1`` ... covering every node exactly once.
    """
    order = reading_order(book)
    by_id = {node.id: node for node in book.nodes}
    weights = {
        n: TOKENS_PER_NODE + TOKENS_PER_CHOICE * len(by_id[n].choices) for n in order
    }
    ceiling = max_chunk_content(cap)
    parts = max(2, math.ceil(sum(weights.values()) / ceiling))
    while True:
        slices = _cut(order, weights, parts)
        # #ASSUME: data-integrity: a single node heavier than the ceiling
        # cannot be split further, so the loop stops once every slice is one
        # node; a real shape's heaviest node (a hub of a dozen choices) is far
        # below any cap the plan path uses.
        # #VERIFY: test_storyplan_chunked.py partitions every retained shape
        # and checks each scene's estimate against the ceiling.
        if all(sum(weights[n] for n in s) <= ceiling or len(s) == 1 for s in slices):
            break
        parts += 1
    return [Scene(id=f"S{i}", nodes=tuple(s)) for i, s in enumerate(slices, start=1)]


def split_scene(book: Storybook, scene: Scene) -> tuple[Scene, Scene]:
    """Split a scene into two contiguous halves of roughly equal output.

    Args:
        book: The shape.
        scene: A scene of at least two nodes.

    Returns:
        tuple[Scene, Scene]: ``<id>a`` and ``<id>b``, both marked ``split``.
    """
    by_id = {node.id: node for node in book.nodes}
    weights = {
        n: TOKENS_PER_NODE + TOKENS_PER_CHOICE * len(by_id[n].choices)
        for n in scene.nodes
    }
    halves = _cut(scene.nodes, weights, 2)
    if len(halves) < 2:
        mid = max(1, len(scene.nodes) // 2)
        halves = [list(scene.nodes[:mid]), list(scene.nodes[mid:])]
    return (
        Scene(id=f"{scene.id}a", nodes=tuple(halves[0]), split=True),
        Scene(id=f"{scene.id}b", nodes=tuple(halves[1]), split=True),
    )


def owners(
    book: Storybook, scenes: Sequence[Scene]
) -> tuple[dict[str, str], dict[str, str]]:
    """Return which scene owns each node and each choice.

    Args:
        book: The shape.
        scenes: The current partition.

    Returns:
        tuple[dict[str, str], dict[str, str]]: Node id to scene id, and choice
            id to the scene of its source node.
    """
    node_owner = {node_id: scene.id for scene in scenes for node_id in scene.nodes}
    choice_owner = {
        choice.id: node_owner[node.id]
        for node in book.nodes
        if node.id in node_owner
        for choice in node.choices
    }
    return node_owner, choice_owner


# ---------------------------------------------------------------------------
# Entry facts
# ---------------------------------------------------------------------------


def entry_knowledge(
    book: Storybook,
    node_establishes: Mapping[str, Iterable[str]],
    choice_establishes: Mapping[str, Iterable[str]],
) -> dict[str, frozenset[str]]:
    """Return the facts guaranteed on entry to every node, from what is planned.

    The must-analysis of SP-2 over the node graph: a node or choice not yet
    planned establishes nothing, so the answer is a lower bound that later
    scenes can only raise. Merging all configurations of a node into one
    vertex is at least as strict as SP-2's state-aware walk, so a fact listed
    here is guaranteed there too.

    Args:
        book: The shape.
        node_establishes: Per planned node, what it establishes.
        choice_establishes: Per planned choice, what it establishes.

    Returns:
        dict[str, frozenset[str]]: Per node id, the facts every reader has on
            arrival (before the node's own ``establishes``).
    """
    vertices = [node.id for node in book.nodes]
    known = set(vertices)
    incoming: dict[str, list[tuple[str, frozenset[str]]]] = {}
    universe: set[str] = set()
    for facts in node_establishes.values():
        universe.update(facts)
    for node in book.nodes:
        for choice in node.choices:
            gen = frozenset(choice_establishes.get(choice.id, ()))
            universe |= gen
            if choice.target in known:
                incoming.setdefault(choice.target, []).append((node.id, gen))
    gen_by_node = {n: frozenset(f) for n, f in node_establishes.items()}
    reachable = set(reading_order(book)[: _reached_count(book)])
    entry = guaranteed_on_entry(
        vertices, incoming, book.start_node, gen_by_node, frozenset(universe)
    )
    # An unreachable node keeps the descent's starting value (every fact);
    # it is reported as knowing nothing rather than everything.
    return {n: (facts if n in reachable else frozenset()) for n, facts in entry.items()}


def _reached_count(book: Storybook) -> int:
    """Return how many nodes are reachable from the start by choice targets.

    Args:
        book: The shape.

    Returns:
        int: The length of the breadth-first prefix of :func:`reading_order`.
    """
    known = {node.id for node in book.nodes}
    targets = {node.id: [c.target for c in node.choices] for node in book.nodes}
    seen = {book.start_node} if book.start_node in known else set[str]()
    stack = list(seen)
    while stack:
        for target in targets.get(stack.pop(), []):
            if target in known and target not in seen:
                seen.add(target)
                stack.append(target)
    return len(seen)


def boundary_nodes(book: Storybook, scene: Scene) -> list[str]:
    """Return the scene's nodes entered from outside it (or the start node).

    Args:
        book: The shape.
        scene: The scene.

    Returns:
        list[str]: Node ids in the scene's order.
    """
    inside = set(scene.nodes)
    entered: set[str] = set()
    for node in book.nodes:
        if node.id in inside:
            continue
        entered.update(c.target for c in node.choices if c.target in inside)
    if book.start_node in inside:
        entered.add(book.start_node)
    return [n for n in scene.nodes if n in entered]


# ---------------------------------------------------------------------------
# Stitch
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ChunkEntries:
    """One scene's answer, in real ids.

    Attributes:
        nodes: Node id to its entry (``event``, ``requires``, ``establishes``).
        choices: Choice id to its entry.
        new_facts: Proposed fact id to its entry, as the scene wrote them.
    """

    nodes: dict[str, object]
    choices: dict[str, object]
    new_facts: dict[str, object]


def undeclared_facts(
    entries: ChunkEntries, known: Collection[str]
) -> dict[str, list[str]]:
    """Return the fact ids a scene's entries name that nothing declares.

    A scene may name a ledger fact, or one of its own ``new_facts``. Anything
    else fails the plan load later, after a paid stitch and check, so the
    caller can ask the scene once before stitching (``AL-873``).

    Args:
        entries: The scene's entries (real ids).
        known: Every id the ledger holds without this scene's proposals.

    Returns:
        dict[str, list[str]]: Each undeclared fact id to the sorted node and
            choice ids that name it (empty when every reference is declared).
    """
    # #ASSUME: data-integrity: entries are model output; a requires or
    # establishes value that is not a list of strings is ignored here and left
    # to the schema load, which reports it.
    # #VERIFY: test_storyplan_chunked.py::test_undeclared_facts_lists_unknown_ids.
    declared = set(known) | set(entries.new_facts)
    found: dict[str, set[str]] = {}
    for group in (entries.nodes, entries.choices):
        for subject, entry in group.items():
            if not isinstance(entry, dict):
                continue
            for key in ("requires", "establishes"):
                refs = cast("dict[str, object]", entry).get(key)
                if not isinstance(refs, list):
                    continue
                for ref in cast("list[object]", refs):
                    if isinstance(ref, str) and ref not in declared:
                        found.setdefault(ref, set()).add(subject)
    return {fact: sorted(subjects) for fact, subjects in sorted(found.items())}


@dataclass(frozen=True, slots=True)
class StitchResult:
    """The model sections assembled from the parts.

    Attributes:
        sections: ``cast``, ``truth``, ``facts``, ``nodes``, ``choices``,
            ``threads``, ``endings`` (real ids; shape-fixed fields not yet set).
        fact_origin: Per ledger fact id, the part that declared it.
        renames: Per scene id, the proposed fact ids renamed for a collision
            (old id to new id).
    """

    sections: dict[str, object]
    fact_origin: dict[str, str]
    renames: dict[str, dict[str, str]]


def _normal_text(entry: object) -> str | None:
    """Return a fact entry's text, case- and space-normalised, or None.

    Args:
        entry: A fact entry.

    Returns:
        str | None: The normalised text.
    """
    if not isinstance(entry, dict):
        return None
    text = cast("dict[str, object]", entry).get("text")
    if not isinstance(text, str):
        return None
    return _COLLISION_TEXT_SPACE.sub(" ", text).strip().lower()


def _fresh_id(base: str, scene_id: str, taken: set[str]) -> str:
    """Return a fact id derived from ``base`` and ``scene_id`` not in ``taken``.

    Args:
        base: The colliding id.
        scene_id: The proposing scene.
        taken: Every id in use.

    Returns:
        str: ``<base>_<scene>`` (with a counter if needed), at most 64 characters.
    """
    suffix = f"_{scene_id.lower()}"
    candidate = f"{base[: _ALIAS_SUFFIX_MAX - len(suffix)]}{suffix}"
    counter = 2
    while candidate in taken:
        tail = f"{suffix}_{counter}"
        candidate = f"{base[: _ALIAS_SUFFIX_MAX - len(tail)]}{tail}"
        counter += 1
    return candidate


def _rename_list(value: object, renames: Mapping[str, str]) -> object:
    """Rename fact ids inside a list.

    Args:
        value: A list of ids (or anything else).
        renames: Old id to new id.

    Returns:
        object: The renamed list, or ``value`` unchanged.
    """
    if not isinstance(value, list):
        return value
    return [
        renames.get(v, v) if isinstance(v, str) else v
        for v in cast("list[object]", value)
    ]


def _rename_entry(
    entry: object, renames: Mapping[str, str], keys: Sequence[str]
) -> object:
    """Rename fact ids in an entry's list fields.

    Args:
        entry: A node, choice or fact entry.
        renames: Old id to new id.
        keys: The list fields holding fact ids.

    Returns:
        object: The renamed entry.
    """
    if not isinstance(entry, dict) or not renames:
        return cast("object", entry)
    out = dict(cast("dict[str, object]", entry))
    for key in keys:
        if key in out:
            out[key] = _rename_list(out[key], renames)
    return out


def _merge_proposed(
    ledger: dict[str, object],
    origin: dict[str, str],
    scene_id: str,
    proposed: Mapping[str, object],
) -> dict[str, str]:
    """Merge one scene's proposed facts into the ledger, in place.

    Args:
        ledger: The ledger so far (updated).
        origin: Fact id to declaring part (updated).
        scene_id: The proposing scene.
        proposed: Its proposed facts.

    Returns:
        dict[str, str]: The scene's renamed ids (old to new).
    """
    local: dict[str, str] = {}
    additions: dict[str, object] = {}
    for fact_id, entry in proposed.items():
        if fact_id not in ledger:
            additions[fact_id] = entry
            continue
        text = _normal_text(entry)
        if text is not None and text == _normal_text(ledger[fact_id]):
            continue
        # #EDGE: data-integrity: a repaired earlier scene can claim an id a
        # later scene already uses; the later scene's fact is then renamed
        # here, and a third scene that referenced it by the old id now points
        # at the earlier scene's fact. Repairs are given the full ledger so
        # they avoid existing ids, which makes this rare.
        # #VERIFY: test_storyplan_chunked.py::
        # test_a_colliding_proposed_fact_is_renamed_in_its_scene.
        local[fact_id] = _fresh_id(
            fact_id, scene_id, set(ledger) | set(additions) | set(proposed)
        )
    for fact_id, entry in additions.items():
        ledger[fact_id] = _rename_entry(entry, local, ("contradicts",))
        origin[fact_id] = scene_id
    for old, new in local.items():
        ledger[new] = _rename_entry(proposed[old], local, ("contradicts",))
        origin[new] = scene_id
    return local


def stitch(
    spine: Mapping[str, object], chunks: Sequence[tuple[Scene, ChunkEntries | None]]
) -> StitchResult:
    """Merge the spine and the scenes' entries into one set of model sections.

    Proposed facts are merged in scene order. A proposed id not yet in the
    ledger is added. One already in the ledger with the same text (case and
    spacing aside) is the same fact and is merged. One already in the ledger
    with a different text is a different fact that reused an id: it is
    renamed ``<id>_<scene>`` and every reference to it in that scene's
    entries is renamed with it, because the scene declared it as its own.
    A scene keeps only entries for nodes and choices it owns (the caller
    filters), so no two scenes write the same entry.

    Args:
        spine: The spine sections (real ids): ``cast``, ``truth``, ``facts``,
            ``threads``, ``endings``.
        chunks: Each scene and its entries (None when it has none yet).

    Returns:
        StitchResult: The sections, each fact's origin and the renames.
    """
    raw_facts = spine.get("facts")
    ledger: dict[str, object] = (
        dict(cast("dict[str, object]", raw_facts))
        if isinstance(raw_facts, dict)
        else {}
    )
    origin = dict.fromkeys(ledger, SPINE)
    nodes: dict[str, object] = {}
    choices: dict[str, object] = {}
    renames: dict[str, dict[str, str]] = {}
    for scene, entries in chunks:
        if entries is None:
            continue
        local = _merge_proposed(ledger, origin, scene.id, entries.new_facts)
        if local:
            renames[scene.id] = local
        fields = ("requires", "establishes")
        nodes.update(
            {k: _rename_entry(v, local, fields) for k, v in entries.nodes.items()}
        )
        choices.update(
            {k: _rename_entry(v, local, fields) for k, v in entries.choices.items()}
        )
    sections: dict[str, object] = {
        key: spine[key] for key in ("cast", "truth") if key in spine
    }
    sections["facts"] = ledger
    sections["nodes"] = nodes
    sections["choices"] = choices
    for key in ("threads", "endings"):
        if key in spine:
            sections[key] = spine[key]
    return StitchResult(sections=sections, fact_origin=origin, renames=renames)


# ---------------------------------------------------------------------------
# Routing findings to the part that owns them
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Routed:
    """One feedback line for one part.

    Attributes:
        part: ``spine`` or a scene id.
        line: The message (real ids; the caller aliases it).
        subject: The node or choice id it is about, when there is one, so a
            split scene can hand the line to the half that owns it.
        error: True for an ERROR or a load error, False for a WARNING.
    """

    part: str
    line: str
    subject: str | None = None
    error: bool = True


def _finding_line(data: Mapping[str, object]) -> str:
    """Render a finding's wire dict as one feedback line.

    Args:
        data: ``PlanFinding.to_dict()``.

    Returns:
        str: ``"<rule> <severity>: <message>; key=value ..."``.
    """
    parts = [f"{data['rule_id']} {data['severity']}: {data['message']}"]
    for key in ("node_id", "choice_id", "fact_id", "state", "route"):
        value = data.get(key)
        if value:
            parts.append(f"{key}={value}")
    return "; ".join(parts)


def route_findings(
    findings: Iterable[object],
    *,
    node_owner: Mapping[str, str],
    choice_owner: Mapping[str, str],
    fact_origin: Mapping[str, str],
) -> list[Routed]:
    """Route SP findings to the part that owns what each one names.

    Spine rules (SP-0 binding, SP-5 payoff reach, SP-7 gifts) and any finding
    about a ``cast``, ``truth``, ``threads`` or ``endings`` entry go to the
    spine. Otherwise a finding naming a node goes to that node's scene, one
    naming a choice to the scene of its source node, one naming only a fact to
    the part that declared it, and anything else to the spine.

    Args:
        findings: :class:`~cyo_adventure.storyplan.checks.PlanFinding` items.
        node_owner: Node id to scene id.
        choice_owner: Choice id to scene id.
        fact_origin: Fact id to declaring part.

    Returns:
        list[Routed]: One entry per finding, in the order given.
    """
    routed: list[Routed] = []
    for finding in findings:
        to_dict = getattr(finding, "to_dict", None)
        if not callable(to_dict):
            continue
        data = cast("dict[str, object]", to_dict())
        line = _finding_line(data)
        error = str(data.get("severity")) == "error"
        message = str(data.get("message", ""))
        node_id = data.get("node_id")
        choice_id = data.get("choice_id")
        fact_id = data.get("fact_id")
        if str(data.get("rule_id")) in _SPINE_RULES or message.startswith(
            tuple(f"{s}." for s in _SPINE_SECTIONS) + _SPINE_SECTIONS
        ):
            routed.append(Routed(SPINE, line, None, error))
        elif message.startswith("facts.") and isinstance(fact_id, str):
            routed.append(Routed(fact_origin.get(fact_id, SPINE), line, None, error))
        elif isinstance(node_id, str) and node_id in node_owner:
            subject = choice_id if isinstance(choice_id, str) else node_id
            routed.append(Routed(node_owner[node_id], line, subject, error))
        elif isinstance(choice_id, str) and choice_id in choice_owner:
            routed.append(Routed(choice_owner[choice_id], line, choice_id, error))
        elif isinstance(fact_id, str):
            routed.append(Routed(fact_origin.get(fact_id, SPINE), line, None, error))
        else:
            routed.append(Routed(SPINE, line, None, error))
    return routed


def route_load_errors(
    errors: Iterable[str],
    *,
    node_owner: Mapping[str, str],
    choice_owner: Mapping[str, str],
    fact_origin: Mapping[str, str],
) -> list[Routed]:
    """Route plan load errors (real ids) to the part that owns them.

    An error located at ``nodes.<id>`` or ``choices.<id>`` goes to that
    entry's scene, one at ``facts.<id>`` to the part that declared the fact.
    Any other error that names a node or choice id goes to its owner (a
    thread naming a choice no scene wrote is the scene's omission); the rest
    go to the spine.

    Args:
        errors: ``"<location>: <message>"`` lines; a model-level error's
            message may list several problems separated by ``"; "``.
        node_owner: Node id to scene id.
        choice_owner: Choice id to scene id.
        fact_origin: Fact id to declaring part.

    Returns:
        list[Routed]: One entry per problem.
    """
    routed: list[Routed] = []
    for error in errors:
        location, _, message = error.partition(": ")
        problems = (
            [p.strip() for p in message.removeprefix("Value error, ").split("; ")]
            if location == "plan"
            else [error]
        )
        for problem in problems:
            if not problem:
                continue
            match = _LOCATED.match(problem)
            if match is not None:
                section, key = match.group("section"), match.group("key")
                owner_map = {"nodes": node_owner, "choices": choice_owner}.get(section)
                part = (
                    fact_origin.get(key, SPINE)
                    if owner_map is None
                    else owner_map.get(key, SPINE)
                )
                subject = None if owner_map is None else key
                routed.append(Routed(part, problem, subject))
                continue
            named = next(
                (
                    token
                    for token in cast("list[str]", _TOKEN.findall(problem))
                    if token in node_owner or token in choice_owner
                ),
                None,
            )
            if named is None:
                routed.append(Routed(SPINE, problem))
            else:
                part = node_owner.get(named) or choice_owner[named]
                routed.append(Routed(part, problem, named))
    return routed
