# pyright: reportImplicitStringConcatenation=false
# Ruff ISC003 requires implicit concatenation for wrapped messages and this
# BasedPyright rule forbids it; the two conflict, and Ruff is the project's gate.
"""Structural checks on a Story Plan against its book (ADR-033 Decision 2, WP-1.2).

Every check here is an exact set operation over the book's graph, its
configuration walk and the plan. None reads prose and none calls a model, so
the checker runs on a filled book plus plan offline and deterministically. It
is not wired into the request path, the gate or moderation.

Rules
=====

``SP-0`` binding (not in ADR-033's table; it implements the ADR's sentence "a
plan whose shape hash no longer matches is stale and fails its checks"). The
plan must carry ``provenance.shape`` (whose hash must equal
:func:`~cyo_adventure.storyplan.models.shape_hash` of the book's graph),
``provenance.book_sha256`` (which must equal the SHA-256 of the book file's
bytes, verified when the caller passes them; a warning otherwise), or both.
``book.storybook_id`` and ``book.storybook_version``, when given, must match the
book; ``request.band`` must equal its age band; and the configuration walk must
not be capped, since a capped walk makes every state-aware rule incomplete.

``SP-1`` coverage: the plan's ``nodes`` keys equal the book's node ids and its
``choices`` keys equal the book's choice ids; every ``endings`` key is an ending
node; every payoff site's ``choice`` is a choice of its ``node``; every thread's
variable is declared in the book and every book variable has exactly one
thread; a thread's ``planting_choices`` equal the set of book choices whose
effects move that variable off its initial value. A variable moved by an
``on_enter`` effect is a warning (ADR-033 plants on choices). When SP-1
reports an error the graph rules SP-2 to SP-8 are skipped, because a plan that
does not cover its book would make them report noise.

``SP-2`` merge closure: in every reachable configuration ``(node, state)``,
each fact the node ``requires`` is guaranteed on entry, and each fact a visible
choice ``requires`` is guaranteed on entry or established by the node offering
it. "Guaranteed on entry" is the NC-1 must-analysis of
``scripts/check_narrative_contract.py``, moved here as
:func:`guaranteed_on_entry` and run over the configuration graph instead of
the node graph: a configuration's entry set is the intersection, over every
incoming ``(configuration, choice)`` edge, of what held after the predecessor
plus the plant facts that choice carries. The initial configuration enters with
nothing. This equals "the union of ``establishes`` of the nodes visited plus
the plant of every planting choice taken", intersected over every route that
reaches the configuration. Running it over configurations rather than nodes is
what makes the rule state-aware: a node reached only by readers holding a plant
has that plant guaranteed, and a node reached with and without it does not.

``SP-3`` single truth, for every pair of facts marked as contradicting whose
two sides are both established at some reachable site (a node's
``establishes`` or a traversed choice's plant):

- ERROR when one reading can meet both: a breadth-first search over
  ``(configuration, holds first, holds second)`` finds a route that
  establishes both, plants included. This is the Lighthouse B2 shape: a node
  saying "she has no key" reached by a reader whose choice planted the key.
- ERROR when the pair sits only on routes no single reading crosses but one
  side is a ``truth`` fact: the book gives two answers to its own question
  (the two-backstory class, AL-773), which a reader who replays meets.
- WARNING when the pair sits only on mutually exclusive routes and neither side
  is a truth fact (for example a cipher that is a three-place shift on one
  route and a shuffled table on another). It is a replay inconsistency, not a
  contradiction any one reading contains, so it advises without blocking. The
  plan writer decides by marking: a pair that must never differ should have
  one side in ``truth``.

Separately, every ``truth`` fact must be established at some reachable site.

``SP-4`` plant exclusivity: walking every configuration reachable from the
start without traversing any of a thread's planting choices, no node
establishes that thread's ``plant``.

``SP-5`` payoff reach: each payoff site ``node`` has a reachable
configuration where the thread's variable differs from its declared initial
value (planted) and one where it equals it (unplanted), and the site's
``choice`` is visible in at least one reachable configuration of the node.

``SP-6`` payoff independence: the payoff passage is the book target of the
site's ``choice``. In every configuration where that choice is visible, each
fact the choice requires, and in every configuration entered through that
choice, each fact the passage requires, is either the thread's own ``plant`` or
is guaranteed by the plant-blind analysis: :func:`guaranteed_on_entry` re-run
with no choice planting anything and with the payoff passages of every other
thread establishing nothing. A payoff that leans on another thread's plant, or
on what another payoff showed, fails here even when its gating makes that fact
guaranteed state-wise, which SP-2 alone would accept.

``SP-7`` every negative-valence ending node has an ``endings`` entry (whose
``gift`` the schema already requires to be non-empty).

``SP-8`` every reachable configuration with two or more visible choices offers
at least two distinct ``cost`` values (case-folded, whitespace-collapsed,
trailing punctuation stripped).

``SP-9`` every plan string except ``request.text``, ``request.note``, ``book``
and ``provenance`` (verbatim untrusted input and metadata) passes the
slot structural floor (non-empty, single line, no braces, no ``<<``/``>>``, no
em dash, printable, no untrusted-input fence markers) and the band-mandatory
denylist for the book's age band, both reused from
:mod:`cyo_adventure.validator.slots`. The length cap is per field (amended
2026-11-21): 120 characters for slot-like strings (pitch, cast, choice-level
strings, endings, payoff ``shows``, tone), 240 for ``facts.*.text`` and node
``event`` (record prose), 600 for ``truth.statement``.

``SP-A`` (optional, only when an assertion map is supplied): a fact the
prose of a node is recorded as asserting must not be in that node's computed
``must_not_assert``. This is the manual form of ADR-033's continuity question,
used by WP-1.4 and WP-1.5.

Every finding names its rule, node, choice, a witness ``state`` (the variable
values of the first reachable configuration, in walk order, where the rule
fails), the ``fact_id`` concerned and, for path rules, a witness ``route`` from
the start node. Findings are deduplicated to one per ``(rule, node, fact)``;
the message gives how many reachable states fail.
"""

from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Hashable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypeVar

from cyo_adventure.player.engine import StoryEngine
from cyo_adventure.storybook.models import EffectOp, Storybook, Valence
from cyo_adventure.storyplan.models import StoryPlan, shape_hash
from cyo_adventure.validator.report import Severity, ValidationFinding, ValidationReport
from cyo_adventure.validator.slots import (
    band_mandatory_bundles,
    denylisted_bundles,
    structural_value_violations,
)
from cyo_adventure.validator.walk import DEFAULT_CONFIG_CAP, walk_configurations

if TYPE_CHECKING:
    from collections.abc import (
        Callable,
        Iterable,
        Iterator,
        Mapping,
        Sequence,
    )

    from cyo_adventure.storybook.models import Effect, Variable

__all__ = [
    "ASSERT_RULE",
    "RULE_IDS",
    "WITNESSES",
    "ConfigGraph",
    "PlanFinding",
    "RuleWitness",
    "base_example",
    "build_config_graph",
    "check_assertions",
    "check_plan",
    "guaranteed_on_entry",
    "meet_of",
    "must_not_assert",
    "verify_witnesses",
]

RULE_IDS: Final[tuple[str, ...]] = (
    "SP-0",
    "SP-1",
    "SP-2",
    "SP-3",
    "SP-4",
    "SP-5",
    "SP-6",
    "SP-7",
    "SP-8",
    "SP-9",
)
ASSERT_RULE: Final = "SP-A"

_EMPTY: Final[frozenset[str]] = frozenset()

StateItems = tuple[tuple[str, bool | int | str], ...]


@dataclass(frozen=True, slots=True)
class PlanFinding(ValidationFinding):
    """A :class:`~cyo_adventure.validator.report.ValidationFinding` with plan context.

    It is a subclass so a :class:`ValidationReport` holds it unchanged and the
    report wire format only gains keys. All three extras are plain strings, so
    ``to_dict`` keeps the parent's ``dict[str, str | None]`` shape.

    Attributes:
        state: The witness configuration's variables as ``name=value`` pairs,
            ``"(no variables)"`` for a stateless book, or ``None`` when the
            finding is not about a configuration.
        fact_id: The ledger fact the finding concerns, if any.
        route: A witness route from the start node, ``node > choice > node``.
    """

    state: str | None = None
    fact_id: str | None = None
    route: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Return the finding in the report wire format plus the plan keys.

        Returns:
            dict[str, str | None]: The parent's keys plus ``state``,
                ``fact_id`` and ``route``.
        """
        out = ValidationFinding.to_dict(self)
        out["state"] = self.state
        out["fact_id"] = self.fact_id
        out["route"] = self.route
        return out


# ---------------------------------------------------------------------------
# The must-analysis (NC-1's fixpoint, moved here from the script)
# ---------------------------------------------------------------------------

V = TypeVar("V", bound=Hashable)


def meet_of(sets: Iterable[frozenset[str]]) -> frozenset[str]:
    """Return the intersection of ``sets``, or the empty set when there are none.

    NC-1, NC-2 and SP-2 all use this single definition of "meet", so the
    script and the package cannot silently diverge.

    Args:
        sets: The fact sets to intersect.

    Returns:
        frozenset[str]: Their intersection; empty for an empty iterable.
    """
    result: frozenset[str] | None = None
    for item in sets:
        result = item if result is None else result & item
    return _EMPTY if result is None else result


def guaranteed_on_entry(  # noqa: PLR0913, PLR0917 - five independent fixpoint inputs
    vertices: Sequence[V],
    incoming: Mapping[V, Sequence[tuple[V, frozenset[str]]]],
    start: V,
    vertex_gen: Mapping[V, frozenset[str]],
    top: frozenset[str],
) -> dict[V, frozenset[str]]:
    """Compute the facts guaranteed on entry to every vertex (must-analysis).

    ``entry(start) = {}``; for any other vertex ``v``,
    ``entry(v) = meet over incoming (p, g) of (entry(p) | gen(p) | g)``, where
    ``g`` is what traversing that edge establishes. A vertex with no incoming
    edge enters with nothing. Non-start vertices start at ``top`` and the
    iteration descends to the greatest fixpoint, which handles cycles. The
    framework is gen-only with intersection, so it is distributive and the
    fixpoint equals the meet over all paths: a fact is missing on entry exactly
    when some path from the start reaches the vertex without establishing it.

    Args:
        vertices: Every vertex, in a fixed order (the sweep order).
        incoming: Per vertex, its ``(predecessor, edge gen)`` pairs. A missing
            key means no incoming edge.
        start: The vertex a reading begins at.
        vertex_gen: Per vertex, what entering it establishes.
        top: The universe of facts, the descent's starting value.

    Returns:
        dict[V, frozenset[str]]: Per vertex, the facts guaranteed on entry
            (before the vertex's own ``vertex_gen`` is added).
    """
    entry: dict[V, frozenset[str]] = dict.fromkeys(vertices, top)
    out: dict[V, frozenset[str]] = {
        v: top | vertex_gen.get(v, _EMPTY) for v in vertices
    }
    changed = True
    while changed:
        changed = False
        for vertex in vertices:
            if vertex == start:
                new_entry = _EMPTY
            else:
                new_entry = meet_of(
                    out[pred] | gen for pred, gen in incoming.get(vertex, ())
                )
            new_out = new_entry | vertex_gen.get(vertex, _EMPTY)
            if new_entry != entry[vertex] or new_out != out[vertex]:
                entry[vertex] = new_entry
                out[vertex] = new_out
                changed = True
    return entry


# ---------------------------------------------------------------------------
# The configuration graph
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigGraph:
    """The book's reachable configurations, indexed in walk (BFS) order.

    Vertex ``0`` is the initial configuration. Each edge carries the id of the
    choice it traverses, which the plan needs (plants live on choices) and
    :class:`~cyo_adventure.validator.walk.WalkResult` does not record.

    Attributes:
        node_of: Per configuration, its story node id.
        state_of: Per configuration, its variables as sorted ``(name, value)``.
        succ: Per configuration, its ``(choice id, successor index)`` edges in
            visible-choice order.
        capped: Whether the walk stopped at its cap, in which case the graph
            is partial and every state-aware rule is incomplete.
    """

    node_of: tuple[str, ...]
    state_of: tuple[StateItems, ...]
    succ: tuple[tuple[tuple[str, int], ...], ...]
    capped: bool

    def incoming(self) -> dict[int, list[tuple[int, str]]]:
        """Return, per configuration, its ``(predecessor, choice id)`` edges.

        Returns:
            dict[int, list[tuple[int, str]]]: Configurations without a
                predecessor are absent.
        """
        preds: dict[int, list[tuple[int, str]]] = {}
        for source, edges in enumerate(self.succ):
            for choice_id, target in edges:
                preds.setdefault(target, []).append((source, choice_id))
        return preds

    def configs_at(self) -> dict[str, list[int]]:
        """Return, per node id, its configuration indices in walk order.

        Returns:
            dict[str, list[int]]: Nodes with no reachable configuration are absent.
        """
        at: dict[str, list[int]] = {}
        for index, node_id in enumerate(self.node_of):
            at.setdefault(node_id, []).append(index)
        return at


def build_config_graph(
    book: Storybook, *, cap: int = DEFAULT_CONFIG_CAP
) -> ConfigGraph:
    """Walk a book's configurations and label each edge with its choice id.

    Args:
        book: The parsed book.
        cap: The walk's configuration cap.

    Returns:
        ConfigGraph: The labelled configuration graph.

    Raises:
        RuntimeError: If an uncapped walk's successor list disagrees in length
            with the engine's visible choices, which would mean the zip below
            labels edges with the wrong choices.
    """
    walk = walk_configurations(book, cap=cap)
    engine = StoryEngine(book)
    index = {key: position for position, key in enumerate(walk.configs)}
    succ: list[tuple[tuple[str, int], ...]] = []
    for key, state in walk.configs.items():
        successors = walk.edges.get(key, [])
        choices = [] if engine.is_ending(state) else engine.visible_choices(state)
        # #ASSUME: data-integrity: walk_configurations appends one successor
        # per engine.visible_choices(state) entry, in that order, and the
        # engine is pure, so position i of the successor list is the choice at
        # position i. A capped walk may hold a partial list, hence the check
        # only when uncapped.
        # #VERIFY: the RuntimeError below; test_storyplan_checks.py labels a
        # conditioned book's edges and asserts the gated choice id appears
        # only on planted configurations.
        if not walk.capped and len(choices) != len(successors):
            msg = f"walk and engine disagree on the choices at {key[0]!r}"
            raise RuntimeError(msg)
        succ.append(
            tuple(
                (choice.id, index[target])
                for choice, target in zip(choices, successors, strict=False)
                if target in index
            )
        )
    return ConfigGraph(
        node_of=tuple(key[0] for key in walk.configs),
        state_of=tuple(key[1] for key in walk.configs),
        succ=tuple(succ),
        capped=walk.capped,
    )


# ---------------------------------------------------------------------------
# Shared analysis context
# ---------------------------------------------------------------------------


def _render_state(state: StateItems) -> str:
    """Render configuration variables as ``name=value`` pairs.

    Args:
        state: Sorted ``(name, value)`` pairs.

    Returns:
        str: For example ``"has_key=true, steps=2"``; ``"(no variables)"`` when
            the book is stateless.
    """
    if not state:
        return "(no variables)"
    return ", ".join(f"{name}={json.dumps(value)}" for name, value in state)


@dataclass(frozen=True, slots=True)
class _Context:
    """Everything the graph rules share, computed once per check run."""

    plan: StoryPlan
    book: Storybook
    graph: ConfigGraph
    preds: dict[int, list[tuple[int, str]]]
    at: dict[str, list[int]]
    node_gen: dict[str, frozenset[str]]
    choice_gen: dict[str, frozenset[str]]
    entry: dict[int, frozenset[str]]

    @classmethod
    def build(cls, plan: StoryPlan, book: Storybook, *, cap: int) -> _Context:
        """Walk the book and run the plan's must-analysis over it.

        Args:
            plan: The plan, already SP-1 clean.
            book: The book it plans.
            cap: The walk's configuration cap.

        Returns:
            _Context: The shared analysis state.
        """
        graph = build_config_graph(book, cap=cap)
        node_gen = {
            node_id: frozenset(node.establishes) for node_id, node in plan.nodes.items()
        }
        choice_gen = plan.plants_by_choice()
        context = cls(
            plan=plan,
            book=book,
            graph=graph,
            preds=graph.incoming(),
            at=graph.configs_at(),
            node_gen=node_gen,
            choice_gen=choice_gen,
            entry={},
        )
        context.entry.update(context.entry_sets(node_gen, choice_gen))
        return context

    def entry_sets(
        self,
        node_gen: Mapping[str, frozenset[str]],
        choice_gen: Mapping[str, frozenset[str]],
    ) -> dict[int, frozenset[str]]:
        """Run :func:`guaranteed_on_entry` over the configuration graph.

        Args:
            node_gen: Per node id, what entering it establishes.
            choice_gen: Per choice id, what traversing it establishes.

        Returns:
            dict[int, frozenset[str]]: Per configuration, the facts guaranteed
                on entry.
        """
        vertices = list(range(len(self.graph.node_of)))
        incoming = {
            target: [
                (source, choice_gen.get(choice_id, _EMPTY))
                for source, choice_id in edges
            ]
            for target, edges in self.preds.items()
        }
        gen = {v: node_gen.get(self.graph.node_of[v], _EMPTY) for v in vertices}
        return guaranteed_on_entry(
            vertices, incoming, 0, gen, frozenset(self.plan.facts)
        )

    def reach(
        self, *, blocked: Callable[[str], bool], stop: Callable[[int], bool]
    ) -> dict[int, tuple[int, str] | None]:
        """Breadth-first search from the start under a route constraint.

        Args:
            blocked: Whether a choice id may not be traversed.
            stop: Whether to stop expanding at a configuration (it is still
                reached; its successors are not reached through it).

        Returns:
            dict[int, tuple[int, str] | None]: Every reached configuration with
                its BFS parent and the choice taken, ``None`` for the start.
        """
        parents: dict[int, tuple[int, str] | None] = {0: None}
        queue: deque[int] = deque([0])
        while queue:
            current = queue.popleft()
            if stop(current):
                continue
            for choice_id, target in self.graph.succ[current]:
                if target in parents or blocked(choice_id):
                    continue
                parents[target] = (current, choice_id)
                queue.append(target)
        return parents

    def entered_without(self, fact: str) -> dict[int, tuple[int, str] | None]:
        """Return the configurations some route enters without ``fact``.

        Args:
            fact: The fact id.

        Returns:
            dict[int, tuple[int, str] | None]: BFS parents, from which
                :meth:`route` rebuilds a witness route.
        """
        return self.reach(
            blocked=lambda choice_id: fact in self.choice_gen.get(choice_id, _EMPTY),
            stop=lambda config: (
                fact in self.node_gen.get(self.graph.node_of[config], _EMPTY)
            ),
        )

    def entered_via(self, choice_id: str, config: int) -> bool:
        """Report whether a configuration has an incoming edge through a choice.

        Args:
            choice_id: The choice id.
            config: The configuration index.

        Returns:
            bool: True when some predecessor reaches ``config`` by ``choice_id``.
        """
        return any(c == choice_id for _, c in self.preds.get(config, ()))

    def visible_at(self, choice_id: str, configs: Iterable[int]) -> list[int]:
        """Return the configurations among ``configs`` where a choice is visible.

        Args:
            choice_id: The choice id.
            configs: Configuration indices.

        Returns:
            list[int]: Those offering ``choice_id``, in the given order.
        """
        return [
            config
            for config in configs
            if any(c == choice_id for c, _ in self.graph.succ[config])
        ]

    def route(
        self, parents: Mapping[int, tuple[int, str] | None], config: int
    ) -> str | None:
        """Rebuild the witness route to ``config`` from BFS parents.

        Args:
            parents: The output of :meth:`reach`.
            config: The configuration to reach.

        Returns:
            str | None: ``"start > choice > node > ..."``, or None when the
                search did not reach ``config``.
        """
        if config not in parents:
            return None
        steps: list[str] = [self.graph.node_of[config]]
        link = parents[config]
        while link is not None:
            source, choice_id = link
            steps.extend((choice_id, self.graph.node_of[source]))
            link = parents[source]
        return " > ".join(reversed(steps))

    def state(self, config: int) -> str:
        """Render a configuration's variables.

        Args:
            config: The configuration index.

        Returns:
            str: See :func:`_render_state`.
        """
        return _render_state(self.graph.state_of[config])


def _finding(  # noqa: PLR0913 - mirrors the finding's optional attribution fields
    rule_id: str,
    story_id: str,
    message: str,
    *,
    severity: Severity = Severity.ERROR,
    node_id: str | None = None,
    choice_id: str | None = None,
    state: str | None = None,
    fact_id: str | None = None,
    route: str | None = None,
) -> PlanFinding:
    """Build a :class:`PlanFinding`.

    Args:
        rule_id: The SP rule id.
        story_id: The book id.
        message: The human-readable message.
        severity: ERROR blocks; WARNING advises.
        node_id: The node attributed, if any.
        choice_id: The choice attributed, if any.
        state: The witness state, if any.
        fact_id: The fact concerned, if any.
        route: The witness route, if any.

    Returns:
        PlanFinding: The finding.
    """
    return PlanFinding(
        rule_id=rule_id,
        severity=severity,
        story_id=story_id,
        message=message,
        node_id=node_id,
        choice_id=choice_id,
        state=state,
        fact_id=fact_id,
        route=route,
    )


# ---------------------------------------------------------------------------
# SP-0 and SP-1: binding and coverage (no walk needed)
# ---------------------------------------------------------------------------


def _check_binding(
    plan: StoryPlan, book: Storybook, book_digest: str | None
) -> list[PlanFinding]:
    """SP-0: the plan is bound to this book and its band.

    Args:
        plan: The plan.
        book: The book.
        book_digest: SHA-256 hex of the book file's bytes, or None when the
            caller holds only the parsed book.

    Returns:
        list[PlanFinding]: The findings.
    """
    story = book.id
    findings: list[PlanFinding] = []
    provenance = plan.provenance
    actual = shape_hash(book)
    if provenance.shape is None and provenance.book_sha256 is None:
        findings.append(
            _finding(
                "SP-0",
                story,
                "plan is not bound: set provenance.shape to "
                f'{{"id": "{book.id}", "hash": "{actual}"}} or set '
                "provenance.book_sha256 to the book file's SHA-256",
            )
        )
    if provenance.shape is not None and provenance.shape.hash != actual:
        findings.append(
            _finding(
                "SP-0",
                story,
                f"plan for shape {provenance.shape.id!r} is stale: its hash is "
                f"{provenance.shape.hash} but the book's graph hashes to {actual}",
            )
        )
    if provenance.book_sha256 is not None:
        if book_digest is None:
            findings.append(
                _finding(
                    "SP-0",
                    story,
                    "provenance.book_sha256 was not verified: no book file bytes "
                    "were given to the checker",
                    severity=Severity.WARNING,
                )
            )
        elif provenance.book_sha256 != book_digest:
            findings.append(
                _finding(
                    "SP-0",
                    story,
                    "plan is stale: provenance.book_sha256 "
                    f"{provenance.book_sha256} but the book file hashes to "
                    f"{book_digest}; the book changed after the plan was written",
                )
            )
    if plan.book is not None:
        if plan.book.storybook_id != book.id:
            findings.append(
                _finding(
                    "SP-0",
                    story,
                    f"book.storybook_id {plan.book.storybook_id!r} is not the "
                    f"book's id {book.id!r}",
                )
            )
        if plan.book.storybook_version != book.version:
            findings.append(
                _finding(
                    "SP-0",
                    story,
                    f"book.storybook_version {plan.book.storybook_version} is not "
                    f"the book's version {book.version}",
                )
            )
    if plan.request.band is not book.metadata.age_band:
        findings.append(
            _finding(
                "SP-0",
                story,
                f"request.band {plan.request.band.value!r} differs from the book's "
                f"age band {book.metadata.age_band.value!r}",
            )
        )
    return findings


def _plants_variable(effect: Effect, variable: Variable) -> bool:
    """Return whether an effect moves a variable off its initial value.

    Args:
        effect: The effect.
        variable: The declared variable.

    Returns:
        bool: True for a ``set`` to a non-initial value or a non-zero
            ``inc``/``dec`` on that variable.
    """
    if effect.var != variable.name:
        return False
    if effect.op is EffectOp.SET:
        return effect.value != variable.initial
    return effect.value != 0


def _check_coverage(plan: StoryPlan, book: Storybook) -> list[PlanFinding]:
    """SP-1: the plan covers exactly the book's nodes, choices and variables.

    Args:
        plan: The plan.
        book: The book.

    Returns:
        list[PlanFinding]: The findings.
    """
    story = book.id
    findings: list[PlanFinding] = []
    node_ids = [node.id for node in book.nodes]
    choice_ids = [choice.id for node in book.nodes for choice in node.choices]
    findings.extend(
        _finding("SP-1", story, f"book node {n!r} has no plan entry", node_id=n)
        for n in node_ids
        if n not in plan.nodes
    )
    findings.extend(
        _finding("SP-1", story, f"plan node {n!r} is not in the book", node_id=n)
        for n in plan.nodes
        if n not in set(node_ids)
    )
    findings.extend(
        _finding("SP-1", story, f"book choice {c!r} has no plan entry", choice_id=c)
        for c in choice_ids
        if c not in plan.choices
    )
    findings.extend(
        _finding("SP-1", story, f"plan choice {c!r} is not in the book", choice_id=c)
        for c in plan.choices
        if c not in set(choice_ids)
    )
    ending_nodes = {node.id for node in book.nodes if node.is_ending}
    findings.extend(
        _finding(
            "SP-1", story, f"endings.{n} is not an ending node of the book", node_id=n
        )
        for n in plan.endings
        if n in set(node_ids) and n not in ending_nodes
    )
    findings.extend(_check_ending_entries(plan, book))
    choices_of = {
        node.id: {choice.id for choice in node.choices} for node in book.nodes
    }
    for thread_id, thread in plan.threads.items():
        for index, site in enumerate(thread.payoff_sites):
            if site.node in choices_of and site.choice not in choices_of[site.node]:
                findings.append(
                    _finding(
                        "SP-1",
                        story,
                        f"threads.{thread_id}.payoff_sites[{index}].choice "
                        f"{site.choice!r} is not a choice of {site.node!r}",
                        node_id=site.node,
                        choice_id=site.choice,
                        fact_id=thread.plant,
                    )
                )
    findings.extend(_check_thread_variables(plan, book))
    return findings


def _check_ending_entries(plan: StoryPlan, book: Storybook) -> list[PlanFinding]:
    """SP-1, endings: a declared valence or kind matches the book.

    Args:
        plan: The plan.
        book: The book.

    Returns:
        list[PlanFinding]: The findings.
    """
    findings: list[PlanFinding] = []
    ending_of = {node.id: node.ending for node in book.nodes if node.ending}
    for node_id, entry in plan.endings.items():
        ending = ending_of.get(node_id)
        if ending is None:
            continue
        if entry.valence is not None and entry.valence is not ending.valence:
            findings.append(
                _finding(
                    "SP-1",
                    book.id,
                    f"endings.{node_id}.valence {entry.valence.value!r} differs "
                    f"from the book's {ending.valence.value!r}",
                    node_id=node_id,
                )
            )
        if entry.kind is not None and entry.kind is not ending.kind:
            findings.append(
                _finding(
                    "SP-1",
                    book.id,
                    f"endings.{node_id}.kind {entry.kind.value!r} differs from the "
                    f"book's {ending.kind.value!r}",
                    node_id=node_id,
                )
            )
    return findings


def _check_thread_variables(plan: StoryPlan, book: Storybook) -> list[PlanFinding]:
    """SP-1, variables: threads and book variables correspond one to one.

    Args:
        plan: The plan.
        book: The book.

    Returns:
        list[PlanFinding]: The findings.
    """
    story = book.id
    findings: list[PlanFinding] = []
    variables = {variable.name: variable for variable in book.variables}
    threaded = {thread.variable for thread in plan.threads.values()}
    findings.extend(
        _finding("SP-1", story, f"book variable {name!r} has no thread")
        for name in variables
        if name not in threaded
    )
    for thread_id, thread in plan.threads.items():
        variable = variables.get(thread.variable)
        if variable is None:
            findings.append(
                _finding(
                    "SP-1",
                    story,
                    f"threads.{thread_id} names variable {thread.variable!r}, "
                    "which the book does not declare",
                    fact_id=thread.plant,
                )
            )
            continue
        setters = [
            choice.id
            for node in book.nodes
            for choice in node.choices
            if any(_plants_variable(effect, variable) for effect in choice.effects)
        ]
        findings.extend(
            _finding(
                "SP-1",
                story,
                f"choice {c!r} sets {variable.name!r} but threads.{thread_id}"
                ".planting_choices omit it",
                choice_id=c,
                fact_id=thread.plant,
            )
            for c in setters
            if c not in thread.planting_choices
        )
        findings.extend(
            _finding(
                "SP-1",
                story,
                f"threads.{thread_id}.planting_choices lists {c!r}, which does not set "
                f"{variable.name!r} in the book",
                choice_id=c,
                fact_id=thread.plant,
            )
            for c in thread.planting_choices
            if c not in setters
        )
        findings.extend(
            _finding(
                "SP-1",
                story,
                f"node {node.id!r} sets {variable.name!r} on entry; ADR-033 plants "
                "on choices, so the plant is invisible to SP-4 and SP-6",
                severity=Severity.WARNING,
                node_id=node.id,
                fact_id=thread.plant,
            )
            for node in book.nodes
            if any(_plants_variable(effect, variable) for effect in node.on_enter)
        )
    return findings


# ---------------------------------------------------------------------------
# SP-2 to SP-8: graph rules
# ---------------------------------------------------------------------------


def _check_merge_closure(ctx: _Context) -> list[PlanFinding]:
    """SP-2: every required fact is guaranteed on entry in every configuration.

    Args:
        ctx: The analysis context.

    Returns:
        list[PlanFinding]: One finding per (node, fact), with a witness.
    """
    findings: list[PlanFinding] = []
    reached_cache: dict[str, dict[int, tuple[int, str] | None]] = {}
    for node in ctx.book.nodes:
        configs = ctx.at.get(node.id, [])
        for fact in ctx.plan.nodes[node.id].requires:
            failing = [config for config in configs if fact not in ctx.entry[config]]
            if not failing:
                continue
            parents = reached_cache.setdefault(fact, ctx.entered_without(fact))
            witness = failing[0]
            findings.append(
                _finding(
                    "SP-2",
                    ctx.book.id,
                    f"{node.id!r} requires {fact!r} ({ctx.plan.facts[fact].text}) but "
                    f"{len(failing)} of {len(configs)} reachable states can enter "
                    "without it",
                    node_id=node.id,
                    state=ctx.state(witness),
                    fact_id=fact,
                    route=ctx.route(parents, witness),
                )
            )
    findings.extend(_check_choice_requires(ctx, reached_cache))
    return findings


def _check_choice_requires(
    ctx: _Context, reached_cache: dict[str, dict[int, tuple[int, str] | None]]
) -> list[PlanFinding]:
    """SP-2 for choices: a visible choice's ``requires`` hold where it is offered.

    Args:
        ctx: The analysis context.
        reached_cache: Per fact, :meth:`_Context.entered_without` results, shared
            with the node half of SP-2.

    Returns:
        list[PlanFinding]: One finding per (choice, fact), with a witness.
    """
    findings: list[PlanFinding] = []
    for node in ctx.book.nodes:
        configs = ctx.at.get(node.id, [])
        offered_gen = ctx.node_gen.get(node.id, _EMPTY)
        for choice in node.choices:
            visible = ctx.visible_at(choice.id, configs)
            for fact in ctx.plan.choices[choice.id].requires:
                failing = [c for c in visible if fact not in ctx.entry[c] | offered_gen]
                if not failing:
                    continue
                parents = reached_cache.setdefault(fact, ctx.entered_without(fact))
                findings.append(
                    _finding(
                        "SP-2",
                        ctx.book.id,
                        f"choice {choice.id!r} at {node.id!r} requires {fact!r} "
                        f"({ctx.plan.facts[fact].text}) but {len(failing)} of "
                        f"{len(visible)} states offering it can lack it",
                        node_id=node.id,
                        choice_id=choice.id,
                        state=ctx.state(failing[0]),
                        fact_id=fact,
                        route=ctx.route(parents, failing[0]),
                    )
                )
    return findings


def _establishment_sites(ctx: _Context) -> dict[str, list[str]]:
    """Return, per fact, the reachable nodes and traversed choices establishing it.

    Args:
        ctx: The analysis context.

    Returns:
        dict[str, list[str]]: Fact id to site ids, nodes first in book order,
            then choices in book order.
    """
    reachable_nodes = set(ctx.at)
    traversed = {choice_id for edges in ctx.graph.succ for choice_id, _ in edges}
    sites: dict[str, list[str]] = {}
    for node in ctx.book.nodes:
        if node.id in reachable_nodes:
            for fact in ctx.plan.nodes[node.id].establishes:
                sites.setdefault(fact, []).append(node.id)
    for node in ctx.book.nodes:
        for choice in node.choices:
            if choice.id in traversed:
                for fact in sorted(ctx.choice_gen.get(choice.id, _EMPTY)):
                    sites.setdefault(fact, []).append(choice.id)
    return sites


_PairState = tuple[int, bool, bool]


def _co_route(
    ctx: _Context, first: str, second: str
) -> tuple[_PairState, dict[_PairState, tuple[_PairState, str] | None]] | None:
    """Search for one reading that establishes both facts of a pair.

    Args:
        ctx: The analysis context.
        first: One fact.
        second: The other fact.

    Returns:
        The first ``(config, True, True)`` state reached in breadth-first order
        and the parents map, or None when no single route establishes both.
    """
    node_of = ctx.graph.node_of

    def gains(fact: str, config: int, choice_id: str | None) -> bool:
        if choice_id is not None and fact in ctx.choice_gen.get(choice_id, _EMPTY):
            return True
        return fact in ctx.node_gen.get(node_of[config], _EMPTY)

    start: _PairState = (0, gains(first, 0, None), gains(second, 0, None))
    parents: dict[_PairState, tuple[_PairState, str] | None] = {start: None}
    queue: deque[_PairState] = deque([start])
    while queue:
        current = queue.popleft()
        config, has_first, has_second = current
        if has_first and has_second:
            return current, parents
        for choice_id, target in ctx.graph.succ[config]:
            nxt: _PairState = (
                target,
                has_first or gains(first, target, choice_id),
                has_second or gains(second, target, choice_id),
            )
            if nxt not in parents:
                parents[nxt] = (current, choice_id)
                queue.append(nxt)
    return None


def _pair_route(
    ctx: _Context,
    parents: Mapping[_PairState, tuple[_PairState, str] | None],
    state: _PairState,
) -> str:
    """Render the route to a pair-search state.

    Args:
        ctx: The analysis context.
        parents: The pair search's parents map.
        state: The state to reach.

    Returns:
        str: ``"start > choice > node > ..."``.
    """
    steps = [ctx.graph.node_of[state[0]]]
    link = parents[state]
    while link is not None:
        previous, choice_id = link
        steps.extend((choice_id, ctx.graph.node_of[previous[0]]))
        link = parents[previous]
    return " > ".join(reversed(steps))


def _check_single_truth(ctx: _Context) -> list[PlanFinding]:
    """SP-3: contradictions a reading meets, or that split the truth, block.

    Args:
        ctx: The analysis context.

    Returns:
        list[PlanFinding]: The findings.
    """
    story = ctx.book.id
    sites = _establishment_sites(ctx)
    truth = set(ctx.plan.truth.facts)
    findings: list[PlanFinding] = []
    for pair in sorted(ctx.plan.contradiction_pairs(), key=sorted):
        first, second = sorted(pair)
        if not (sites.get(first) and sites.get(second)):
            continue
        # Attribute to the non-truth side when there is one: that is the fact
        # a fix removes.
        blamed = second if first in truth and second not in truth else first
        other = second if blamed == first else first
        where = (
            f"{blamed!r} (at {', '.join(sites[blamed])}) and "
            f"{other!r} (at {', '.join(sites[other])})"
        )
        met = _co_route(ctx, blamed, other)
        if met is not None:
            state, parents = met
            config = state[0]
            link = parents[state]
            findings.append(
                _finding(
                    "SP-3",
                    story,
                    f"one reading meets both contradicting facts {where}",
                    node_id=ctx.graph.node_of[config],
                    choice_id=None if link is None else link[1],
                    state=ctx.state(config),
                    fact_id=blamed,
                    route=_pair_route(ctx, parents, state),
                )
            )
            continue
        first_site = sites[blamed][0]
        splits_truth = bool(pair & truth)
        findings.append(
            _finding(
                "SP-3",
                story,
                (
                    f"the book answers its question two ways: {where} sit on "
                    "routes no single reading crosses"
                    if splits_truth
                    else f"contradicting facts {where} sit only on routes no "
                    "single reading crosses (a replay inconsistency)"
                ),
                severity=Severity.ERROR if splits_truth else Severity.WARNING,
                node_id=first_site if first_site in ctx.plan.nodes else None,
                choice_id=first_site if first_site in ctx.plan.choices else None,
                fact_id=blamed,
            )
        )
    findings.extend(
        _finding(
            "SP-3",
            story,
            f"truth fact {fact!r} is established on no reachable route",
            fact_id=fact,
        )
        for fact in ctx.plan.truth.facts
        if not sites.get(fact)
    )
    return findings


def _check_plant_exclusivity(ctx: _Context) -> list[PlanFinding]:
    """SP-4: a planted fact is established on no route that skips the plant.

    Args:
        ctx: The analysis context.

    Returns:
        list[PlanFinding]: One finding per (thread, node), with a witness.
    """
    findings: list[PlanFinding] = []
    for thread_id, thread in ctx.plan.threads.items():
        planting = set(thread.planting_choices)
        parents = ctx.reach(
            blocked=lambda choice_id, planting=planting: choice_id in planting,
            stop=lambda _config: False,
        )
        leaked: dict[str, int] = {}
        for config in sorted(parents):
            node_id = ctx.graph.node_of[config]
            if thread.plant in ctx.node_gen.get(node_id, _EMPTY):
                leaked.setdefault(node_id, config)
            # A non-planting choice whose own ``establishes`` names the plant
            # leaks it just as a node does; attribute it to the arrival node.
            for choice_id, target in ctx.graph.succ[config]:
                if choice_id not in planting and thread.plant in ctx.choice_gen.get(
                    choice_id, _EMPTY
                ):
                    leaked.setdefault(ctx.graph.node_of[target], target)
        leaked = dict(sorted(leaked.items(), key=lambda item: item[1]))
        findings.extend(
            _finding(
                "SP-4",
                ctx.book.id,
                f"{node_id!r} establishes {thread.plant!r}, the plant of "
                f"thread {thread_id!r}, on a route that skips every planting choice",
                node_id=node_id,
                state=ctx.state(config),
                fact_id=thread.plant,
                route=ctx.route(parents, config),
            )
            for node_id, config in leaked.items()
        )
    return findings


def _is_planted(state: StateItems, variable: Variable) -> bool:
    """Return whether a configuration holds a thread's plant.

    Args:
        state: The configuration's variables.
        variable: The thread's variable.

    Returns:
        bool: True when the variable differs from its declared initial value.
    """
    # #ASSUME: data-integrity: "planted" means "moved off the declared initial
    # value", which is exact for the bool plants every catalog book uses and
    # for an int counter that only grows; a plant that is later reset to its
    # initial value reads as unplanted from then on.
    # #VERIFY: SP-1 ties each thread variable to exactly its planting choices.
    return dict(state).get(variable.name, variable.initial) != variable.initial


def _check_payoff_reach(ctx: _Context) -> list[PlanFinding]:
    """SP-5: payoff sites are reached with and without the plant, and offered.

    Args:
        ctx: The analysis context.

    Returns:
        list[PlanFinding]: The findings.
    """
    story = ctx.book.id
    variables = {variable.name: variable for variable in ctx.book.variables}
    findings: list[PlanFinding] = []
    for thread_id, thread in ctx.plan.threads.items():
        variable = variables[thread.variable]
        for site in thread.payoff_sites:
            configs = ctx.at.get(site.node, [])
            planted = [
                c for c in configs if _is_planted(ctx.graph.state_of[c], variable)
            ]
            unplanted = [c for c in configs if c not in set(planted)]
            findings.extend(
                _finding(
                    "SP-5",
                    story,
                    f"payoff site {site.node!r} of thread {thread_id!r} is never "
                    f"reached {label} the plant ({variable.name})",
                    node_id=site.node,
                    fact_id=thread.plant,
                )
                for label, present in (("with", planted), ("without", unplanted))
                if not present
            )
            if configs and not ctx.visible_at(site.choice, configs):
                findings.append(
                    _finding(
                        "SP-5",
                        story,
                        f"payoff choice {site.choice!r} of thread {thread_id!r} is "
                        f"never offered at {site.node!r}",
                        node_id=site.node,
                        choice_id=site.choice,
                        fact_id=thread.plant,
                    )
                )
    return findings


def _check_payoff_independence(ctx: _Context) -> list[PlanFinding]:
    """SP-6: a payoff leans only on shared facts and its own plant.

    Args:
        ctx: The analysis context.

    Returns:
        list[PlanFinding]: One finding per (payoff choice or passage, fact).
    """
    findings: list[PlanFinding] = []
    target_of = {c.id: c.target for node in ctx.book.nodes for c in node.choices}
    passages = {
        thread_id: {target_of[site.choice] for site in thread.payoff_sites}
        for thread_id, thread in ctx.plan.threads.items()
    }
    for thread_id, thread in ctx.plan.threads.items():
        own = passages[thread_id]
        others = set[str]().union(
            *(nodes for t, nodes in passages.items() if t != thread_id)
        )
        blind_gen = {
            node_id: (_EMPTY if node_id in others - own else gen)
            for node_id, gen in ctx.node_gen.items()
        }
        blind = ctx.entry_sets(blind_gen, {})

        def report(  # noqa: PLR0913 - one finding's attribution, kept together
            *,
            node_id: str,
            choice_id: str | None,
            fact: str,
            failing: list[int],
            total: int,
            thread_id: str = thread_id,
            blind_gen: dict[str, frozenset[str]] = blind_gen,
        ) -> PlanFinding:
            parents = ctx.reach(
                blocked=lambda _choice: False,
                stop=lambda config: (
                    fact in blind_gen.get(ctx.graph.node_of[config], _EMPTY)
                ),
            )
            subject = f"choice {choice_id!r}" if choice_id else f"passage {node_id!r}"
            return _finding(
                "SP-6",
                ctx.book.id,
                f"payoff {subject} of thread {thread_id!r} requires {fact!r}, "
                "which is neither its own plant nor shared by every reader "
                f"({len(failing)} of {total} states)",
                node_id=node_id,
                choice_id=choice_id,
                state=ctx.state(failing[0]),
                fact_id=fact,
                route=ctx.route(parents, failing[0]),
            )

        for site in thread.payoff_sites:
            offering = ctx.visible_at(site.choice, ctx.at.get(site.node, []))
            site_gen = ctx.node_gen.get(site.node, _EMPTY)
            for fact in ctx.plan.choices[site.choice].requires:
                failing = [c for c in offering if fact not in blind[c] | site_gen]
                if fact != thread.plant and failing:
                    findings.append(
                        report(
                            node_id=site.node,
                            choice_id=site.choice,
                            fact=fact,
                            failing=failing,
                            total=len(offering),
                        )
                    )
            passage = target_of[site.choice]
            entered = [
                c for c in ctx.at.get(passage, []) if ctx.entered_via(site.choice, c)
            ]
            for fact in ctx.plan.nodes[passage].requires:
                failing = [c for c in entered if fact not in blind[c]]
                if fact != thread.plant and failing:
                    findings.append(
                        report(
                            node_id=passage,
                            choice_id=None,
                            fact=fact,
                            failing=failing,
                            total=len(entered),
                        )
                    )
    return findings


def _check_ending_gifts(plan: StoryPlan, book: Storybook) -> list[PlanFinding]:
    """SP-7: every negative ending has a gift.

    Args:
        plan: The plan.
        book: The book.

    Returns:
        list[PlanFinding]: The findings.
    """
    return [
        _finding(
            "SP-7",
            book.id,
            f"negative ending {node.id!r} has no endings entry with a gift",
            node_id=node.id,
        )
        for node in book.nodes
        if node.ending is not None
        and node.ending.valence is Valence.NEGATIVE
        and node.id not in plan.endings
    ]


_COST_SPACE = re.compile(r"\s+")
_DECISION_MIN: Final = 2
"""A decision offers at least this many visible choices, and SP-8 wants this many costs."""


def _normal_cost(cost: str) -> str:
    """Normalise a cost for SP-8's distinctness comparison.

    Args:
        cost: The raw cost string.

    Returns:
        str: Case-folded, whitespace-collapsed, trailing punctuation stripped.
    """
    return _COST_SPACE.sub(" ", cost.casefold()).strip().rstrip(".!?;:,").strip()


def _check_distinct_costs(ctx: _Context) -> list[PlanFinding]:
    """SP-8: every decision offers at least two different costs.

    Args:
        ctx: The analysis context.

    Returns:
        list[PlanFinding]: One finding per node, with a witness state.
    """
    failing: dict[str, list[int]] = {}
    for config, edges in enumerate(ctx.graph.succ):
        if len(edges) < _DECISION_MIN:
            continue
        costs = {
            _normal_cost(ctx.plan.choices[choice_id].cost) for choice_id, _ in edges
        }
        if len(costs) < _DECISION_MIN:
            failing.setdefault(ctx.graph.node_of[config], []).append(config)
    findings: list[PlanFinding] = []
    for node in ctx.book.nodes:
        configs = failing.get(node.id)
        if not configs:
            continue
        witness = configs[0]
        visible = [choice_id for choice_id, _ in ctx.graph.succ[witness]]
        findings.append(
            _finding(
                "SP-8",
                ctx.book.id,
                f"decision {node.id!r} offers {', '.join(visible)} at one cost "
                f"({ctx.plan.choices[visible[0]].cost!r}) in {len(configs)} state(s)",
                node_id=node.id,
                state=ctx.state(witness),
            )
        )
    return findings


# ---------------------------------------------------------------------------
# SP-9: text floors (no walk needed)
# ---------------------------------------------------------------------------


# SP-9 length caps (2026-11-21). validator.slots hard-codes 120 characters, which
# fits slot-like strings that are bound into prompts as a short value. A Story
# Plan also holds narrative-record fields (what a node does, what a fact states,
# the canonical answer), which are sentences or short paragraphs by nature and
# are measured across the seven hand-written plans at up to 201, 253 and 1058
# characters respectively. Every other SP-9 floor still applies to all strings.
SLOT_LENGTH_CAP = 120
RECORD_LENGTH_CAP = 240
TRUTH_LENGTH_CAP = 600
_SLOT_LENGTH_MESSAGE_PREFIX = "value exceeds the 120-character limit"


@dataclass(frozen=True, slots=True)
class _PlanString:
    """One floored plan string and where it sits."""

    path: str
    value: str
    node_id: str | None = None
    choice_id: str | None = None
    fact_id: str | None = None
    cap: int = SLOT_LENGTH_CAP


def _plan_strings(plan: StoryPlan) -> Iterator[_PlanString]:
    """Yield every plan string SP-9 floors, with its location.

    ``request.text`` (verbatim untrusted input, screened upstream and fenced at
    reuse), ``request.note``, ``book`` and ``provenance`` (metadata about the
    plan, never placed in a prompt) are deliberately not yielded.

    Args:
        plan: The plan.

    Yields:
        _PlanString: Each floored string.
    """
    if plan.request.tone is not None:
        yield _PlanString("request.tone", plan.request.tone)
    pitch = plan.pitch
    for field, value in (
        ("hero", pitch.hero),
        ("want", pitch.want),
        ("obstacle", pitch.obstacle),
        ("stake", pitch.stake),
        ("ending_kind", pitch.ending_kind),
    ):
        yield _PlanString(f"pitch.{field}", value)
    for cast_id, member in plan.cast.items():
        for field, value in (
            ("name", member.name),
            ("role", member.role),
            ("want", member.want),
            ("voice", member.voice),
        ):
            yield _PlanString(f"cast.{cast_id}.{field}", value)
    yield _PlanString("truth.statement", plan.truth.statement, cap=TRUTH_LENGTH_CAP)
    if plan.truth.question is not None:
        yield _PlanString("truth.question", plan.truth.question)
    for fact_id, fact in plan.facts.items():
        yield _PlanString(
            f"facts.{fact_id}.text",
            fact.text,
            fact_id=fact_id,
            cap=RECORD_LENGTH_CAP,
        )
    yield from _graph_strings(plan)


def _graph_strings(plan: StoryPlan) -> Iterator[_PlanString]:
    """Yield the floored strings of the node, choice, thread and ending sections.

    Args:
        plan: The plan.

    Yields:
        _PlanString: Each floored string.
    """
    for node_id, node in plan.nodes.items():
        yield _PlanString(f"nodes.{node_id}.function", node.function, node_id=node_id)
        yield _PlanString(
            f"nodes.{node_id}.event",
            node.event,
            node_id=node_id,
            cap=RECORD_LENGTH_CAP,
        )
    for choice_id, choice in plan.choices.items():
        yield _PlanString(
            f"choices.{choice_id}.intent", choice.intent, choice_id=choice_id
        )
        yield _PlanString(f"choices.{choice_id}.cost", choice.cost, choice_id=choice_id)
    for thread_id, thread in plan.threads.items():
        for index, site in enumerate(thread.payoff_sites):
            yield _PlanString(
                f"threads.{thread_id}.payoff_sites[{index}].shows",
                site.shows,
                node_id=site.node,
                choice_id=site.choice,
                fact_id=thread.plant,
            )
    for node_id, ending in plan.endings.items():
        yield _PlanString(f"endings.{node_id}.gift", ending.gift, node_id=node_id)


def _check_text_floors(plan: StoryPlan, book: Storybook) -> list[PlanFinding]:
    """SP-9: every floored plan string passes the slot floors for the band.

    Args:
        plan: The plan.
        book: The book, whose age band selects the mandatory denylist.

    Returns:
        list[PlanFinding]: One finding per violation. Messages name the field
            and the rule, never the offending text.
    """
    # #CRITICAL: security: plan strings are untrusted-derived (ADR-033
    # Constraints) and later work places them in prompts as instruction; the
    # structural floor blocks template-token, FILL-directive and fence forgery
    # and the denylist blocks band-forbidden content before that happens.
    # #VERIFY: test_storyplan_checks.py trips SP-9 with a brace token, a fence
    # marker, an over-long string and a denylisted term, and asserts
    # request.text is exempt.
    bundles = band_mandatory_bundles(book.metadata.age_band)
    findings: list[PlanFinding] = []
    for item in _plan_strings(plan):
        # validator.slots always applies its fixed 120-character cap; drop that
        # one message and apply this field's own cap instead.
        messages = [
            violation.message
            for violation in structural_value_violations(item.value)
            if not violation.message.startswith(_SLOT_LENGTH_MESSAGE_PREFIX)
        ]
        if len(item.value) > item.cap:
            messages.append(
                f"value exceeds the {item.cap}-character limit "
                f"(length {len(item.value)})"
            )
        messages.extend(
            f"matches a band-mandatory denylist term in bundle {bundle!r}"
            for bundle in sorted(denylisted_bundles(item.value, bundles))
        )
        findings.extend(
            _finding(
                "SP-9",
                book.id,
                f"{item.path}: {message}",
                node_id=item.node_id,
                choice_id=item.choice_id,
                fact_id=item.fact_id,
            )
            for message in messages
        )
    return findings


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def check_plan(
    plan: StoryPlan,
    book: Storybook,
    *,
    cap: int = DEFAULT_CONFIG_CAP,
    book_digest: str | None = None,
) -> ValidationReport:
    """Run SP-0 to SP-9 on a plan and the book it plans.

    Args:
        plan: The parsed plan.
        book: The parsed book (filled or skeleton).
        cap: The configuration walk's cap.
        book_digest: SHA-256 hex of the book file's bytes
            (:func:`~cyo_adventure.storyplan.models.book_sha256`), so SP-0 can
            verify ``provenance.book_sha256``; None when only the parsed book
            is at hand.

    Returns:
        ValidationReport: Every finding, in rule order then book order. ``ok``
            is True only when no ERROR finding was recorded.
    """
    report = ValidationReport()
    binding = _check_binding(plan, book, book_digest)
    coverage = _check_coverage(plan, book)
    graph_findings: list[PlanFinding] = []
    if not any(f.severity is Severity.ERROR for f in coverage):
        ctx = _Context.build(plan, book, cap=cap)
        if ctx.graph.capped:
            binding.append(
                _finding(
                    "SP-0",
                    book.id,
                    f"the configuration walk stopped at its cap of {cap}; every "
                    "state-aware rule below is incomplete",
                )
            )
        graph_findings = [
            *_check_merge_closure(ctx),
            *_check_single_truth(ctx),
            *_check_plant_exclusivity(ctx),
            *_check_payoff_reach(ctx),
            *_check_payoff_independence(ctx),
            *_check_ending_gifts(plan, book),
            *_check_distinct_costs(ctx),
        ]
    for finding in (
        *binding,
        *coverage,
        *graph_findings,
        *_check_text_floors(plan, book),
    ):
        report.add(finding)
    return report


def _must_not_assert_by_config(ctx: _Context) -> dict[int, frozenset[str]]:
    """Return, per configuration, the facts its node's prose must not assert.

    Args:
        ctx: The analysis context.

    Returns:
        dict[int, frozenset[str]]: Every ledger fact not guaranteed on entry and
            not established by the node itself.
    """
    every = frozenset(ctx.plan.facts)
    return {
        config: every
        - ctx.entry[config]
        - ctx.node_gen.get(ctx.graph.node_of[config], _EMPTY)
        for config in range(len(ctx.graph.node_of))
    }


def must_not_assert(
    plan: StoryPlan, book: Storybook, *, cap: int = DEFAULT_CONFIG_CAP
) -> dict[str, frozenset[str]]:
    """Compute ADR-033's ``must_not_assert`` per node.

    A node's prose is shared by every state that reaches it (conditional text
    is deferred), so the node-level set is the union over its reachable
    configurations of the facts some route enters without and the node does
    not establish.

    Args:
        plan: The parsed plan; it should be SP-1 clean.
        book: The parsed book.
        cap: The configuration walk's cap.

    Returns:
        dict[str, frozenset[str]]: Per reachable node id, in book order.
    """
    ctx = _Context.build(plan, book, cap=cap)
    by_config = _must_not_assert_by_config(ctx)
    return {
        node.id: frozenset().union(*(by_config[c] for c in ctx.at[node.id]))
        for node in book.nodes
        if node.id in ctx.at
    }


def check_assertions(
    plan: StoryPlan,
    book: Storybook,
    assertions: Mapping[str, Sequence[str]],
    *,
    cap: int = DEFAULT_CONFIG_CAP,
) -> ValidationReport:
    """SP-A: compare recorded per-node prose assertions with ``must_not_assert``.

    Args:
        plan: The parsed plan; it should be SP-1 clean.
        book: The parsed book.
        assertions: Node id to the fact ids that node's prose asserts (the
            WP-1.4 assertion file).
        cap: The configuration walk's cap.

    Returns:
        ValidationReport: One ERROR per asserted fact that some reachable
            route enters the node without, with witness state and route, plus
            an ERROR per unknown node or fact in ``assertions``.
    """
    report = ValidationReport()
    ctx = _Context.build(plan, book, cap=cap)
    by_config = _must_not_assert_by_config(ctx)
    for node_id, facts in assertions.items():
        if node_id not in plan.nodes:
            report.add(
                _finding(
                    ASSERT_RULE, book.id, f"assertions name unknown node {node_id!r}"
                )
            )
            continue
        for fact in facts:
            if fact not in plan.facts:
                report.add(
                    _finding(
                        ASSERT_RULE,
                        book.id,
                        f"assertions for {node_id!r} name undeclared fact {fact!r}",
                        node_id=node_id,
                    )
                )
                continue
            configs = ctx.at.get(node_id, [])
            failing = [c for c in configs if fact in by_config[c]]
            if not failing:
                continue
            report.add(
                _finding(
                    ASSERT_RULE,
                    book.id,
                    f"prose at {node_id!r} asserts {fact!r} "
                    f"({plan.facts[fact].text}), which {len(failing)} of "
                    f"{len(configs)} reachable states enter without",
                    node_id=node_id,
                    state=ctx.state(failing[0]),
                    fact_id=fact,
                    route=ctx.route(ctx.entered_without(fact), failing[0]),
                )
            )
    return report


# ---------------------------------------------------------------------------
# Witnesses: one plan built to trip exactly each rule (blind_spots.py style)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuleWitness:
    """A rule and the book-plus-plan pair that must trip it and nothing else.

    Attributes:
        rule_id: The rule the witness exists for.
        build: Returns ``(book, plan)`` as plain JSON-shaped dicts.
    """

    rule_id: str
    build: Callable[[], tuple[dict[str, object], dict[str, object]]]


def _yes(var: str) -> dict[str, object]:
    """Return the condition ``var == true``.

    Args:
        var: The variable name.

    Returns:
        dict[str, object]: The JSONLogic condition.
    """
    return {"==": [{"var": var}, True]}


def _base_book() -> dict[str, object]:
    """Build a small book with two threads, a shared payoff site and two endings.

    Returns:
        dict[str, object]: A schema-valid Storybook document.
    """

    def choice(
        cid: str, target: str, *, sets: str | None = None, when: str | None = None
    ) -> dict[str, object]:
        out: dict[str, object] = {"id": cid, "label": f"Go ({cid}).", "target": target}
        if sets is not None:
            out["effects"] = [{"op": "set", "var": sets, "value": True}]
        if when is not None:
            out["condition"] = _yes(when)
        return out

    def node(nid: str, *choices: dict[str, object]) -> dict[str, object]:
        return {"id": nid, "body": f"Body of {nid}.", "choices": list(choices)}

    def ending(nid: str, valence: str, kind: str) -> dict[str, object]:
        return {
            "id": nid,
            "body": f"Body of {nid}.",
            "is_ending": True,
            "ending": {
                "id": f"e_{nid}",
                "valence": valence,
                "kind": kind,
                "title": nid,
            },
        }

    return {
        "schema_version": "2.0",
        "id": "s_plan_witness",
        "version": 1,
        "title": "Plan Witness",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"target": 3.0},
            "tier": 2,
            "estimated_minutes": 5,
            "ending_count": 2,
            "topology": "branch_and_bottleneck",
        },
        "variables": [
            {"name": "has_map", "type": "bool", "initial": False},
            {"name": "has_lamp", "type": "bool", "initial": False},
        ],
        "start_node": "n_start",
        "nodes": [
            node(
                "n_start",
                choice("c_take_map", "n_path", sets="has_map"),
                choice("c_skip_map", "n_path"),
            ),
            node(
                "n_path",
                choice("c_take_lamp", "n_fork", sets="has_lamp"),
                choice("c_skip_lamp", "n_fork"),
            ),
            node(
                "n_fork",
                choice("c_cave", "n_cave", when="has_map"),
                choice("c_tunnel", "n_tunnel", when="has_lamp"),
                choice("c_road", "n_home"),
                choice("c_cliff", "n_fall"),
            ),
            node("n_cave", choice("c_cave_on", "n_home")),
            node("n_tunnel", choice("c_tunnel_on", "n_home")),
            ending("n_home", "positive", "success"),
            ending("n_fall", "negative", "setback"),
        ],
    }


def _base_plan(book: dict[str, object]) -> dict[str, object]:
    """Build the SP-clean plan for :func:`_base_book`, bound to ``book``.

    Args:
        book: The book document to bind to.

    Returns:
        dict[str, object]: A schema-valid Story Plan document.
    """

    def plan_node(
        function: str, event: str, requires: list[str], establishes: list[str]
    ) -> dict[str, object]:
        return {
            "function": function,
            "event": event,
            "requires": requires,
            "establishes": establishes,
        }

    def plan_choice(
        intent: str, cost: str, plants: list[str] | None = None
    ) -> dict[str, object]:
        out: dict[str, object] = {"intent": intent, "cost": cost}
        if plants:
            out["plants"] = plants
        return out

    plan: dict[str, object] = {
        "plan_version": "0.1",
        "request": {"band": "8-11"},
        "pitch": {
            "hero": "Wren, a curious walker",
            "want": "to find who left the map",
            "obstacle": "the hill paths split and the light is going",
            "stake": "an old friend's secret stays lost",
            "ending_kind": "a warm discovery at home",
        },
        "cast": {
            "wren": {
                "name": "Wren",
                "role": "hero",
                "want": "to find who left the map",
                "voice": "short questions, quick to laugh",
                "knows": ["well_seen"],
            }
        },
        "truth": {
            "statement": "Grandpa left the map for Wren to find.",
            "question": "Who left the map by the well?",
            "facts": ["grandpa_left_map"],
        },
        "facts": {
            "well_seen": {"text": "A map lies on the old well."},
            "map_marks_cave": {"text": "The map marks a cave behind the ferns."},
            "lamp_lit": {"text": "Wren carries a lit lamp."},
            "cave_drawing": {"text": "The cave wall shows a drawing of a fox."},
            "grandpa_left_map": {"text": "Grandpa left the map for Wren."},
            "stranger_left_map": {
                "text": "A stranger dropped the map by accident.",
                "contradicts": ["grandpa_left_map"],
            },
        },
        "nodes": {
            "n_start": plan_node(
                "open", "Wren finds a map on the well.", [], ["well_seen"]
            ),
            "n_path": plan_node(
                "offer", "A lamp hangs by the gate.", ["well_seen"], []
            ),
            "n_fork": plan_node("bottleneck", "The path splits three ways.", [], []),
            "n_cave": plan_node(
                "payoff",
                "The map leads into the cave.",
                ["map_marks_cave"],
                ["cave_drawing"],
            ),
            "n_tunnel": plan_node(
                "payoff", "The lamp lights the tunnel.", ["lamp_lit"], []
            ),
            "n_home": plan_node(
                "resolve",
                "Grandpa smiles at the door.",
                ["well_seen"],
                ["grandpa_left_map"],
            ),
            "n_fall": plan_node("setback", "Wren slips and turns back.", [], []),
        },
        "choices": {
            "c_take_map": plan_choice("keep the map", "a late start", ["t_map"]),
            "c_skip_map": plan_choice("leave it", "none"),
            "c_take_lamp": plan_choice("carry the lamp", "a heavy bag", ["t_lamp"]),
            "c_skip_lamp": plan_choice("travel light", "none"),
            "c_cave": plan_choice("follow the map", "a dark climb"),
            "c_tunnel": plan_choice("light the tunnel", "a cold walk"),
            "c_road": plan_choice("take the road", "a long walk"),
            "c_cliff": plan_choice("try the cliff", "a risky edge"),
            "c_cave_on": plan_choice("go home", "none"),
            "c_tunnel_on": plan_choice("go home", "none"),
        },
        "threads": {
            "t_map": {
                "variable": "has_map",
                "plant": "map_marks_cave",
                "planting_choices": ["c_take_map"],
                "payoff_sites": [
                    {
                        "node": "n_fork",
                        "choice": "c_cave",
                        "shows": "The map opens the cave.",
                    }
                ],
            },
            "t_lamp": {
                "variable": "has_lamp",
                "plant": "lamp_lit",
                "planting_choices": ["c_take_lamp"],
                "payoff_sites": [
                    {
                        "node": "n_fork",
                        "choice": "c_tunnel",
                        "shows": "The lamp opens a tunnel.",
                    }
                ],
            },
        },
        "endings": {"n_fall": {"gift": "Wren spots the cave from below."}},
        "provenance": {"producer": "witness"},
    }
    return _bind(book, plan)


def _bind(book: dict[str, object], plan: dict[str, object]) -> dict[str, object]:
    """Set the plan's shape hash to the book's.

    Args:
        book: The book document.
        plan: The plan document, modified in place.

    Returns:
        dict[str, object]: ``plan``.
    """
    provenance = plan["provenance"]
    if isinstance(provenance, dict):
        parsed = Storybook.model_validate(book)
        provenance["shape"] = {"id": parsed.id, "hash": shape_hash(parsed)}
    return plan


def _section(doc: dict[str, object], *keys: str) -> dict[str, object]:
    """Return a nested object of a witness document, typed.

    Args:
        doc: The document.
        *keys: The path of keys.

    Returns:
        dict[str, object]: The nested object.

    Raises:
        TypeError: If the path does not lead to an object.
    """
    current: object = doc
    for key in keys:
        if not isinstance(current, dict):  # pragma: no cover - the base is well formed
            msg = f"witness path {keys!r} is not an object"
            raise TypeError(msg)
        current = current[key]  # pyright: ignore[reportUnknownVariableType]
    if not isinstance(current, dict):  # pragma: no cover - the base is well formed
        msg = f"witness path {keys!r} is not an object"
        raise TypeError(msg)
    return current  # pyright: ignore[reportUnknownVariableType]


def base_example() -> tuple[dict[str, object], dict[str, object]]:
    """Return a small book and the plan that passes every SP rule on it.

    Public so tests and documentation can start from a known-clean pair and
    change one property, the way every witness below does.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book = _base_book()
    return book, _base_plan(book)


def _witness_sp0() -> tuple[dict[str, object], dict[str, object]]:
    """Bind the plan to a hash the book does not have (a stale plan).

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book, plan = base_example()
    _section(plan, "provenance", "shape")["hash"] = "sha256:" + "0" * 64
    return book, plan


def _witness_sp1() -> tuple[dict[str, object], dict[str, object]]:
    """Drop one choice's plan entry.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book, plan = base_example()
    del _section(plan, "choices")["c_road"]
    return book, plan


def _witness_sp2() -> tuple[dict[str, object], dict[str, object]]:
    """Make the shared ending presuppose the map's plant.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book, plan = base_example()
    _section(plan, "nodes", "n_home")["requires"] = ["well_seen", "map_marks_cave"]
    return book, plan


def _witness_sp3() -> tuple[dict[str, object], dict[str, object]]:
    """Tell the second backstory on the road route.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book, plan = base_example()
    _section(plan, "nodes", "n_fall")["establishes"] = ["stranger_left_map"]
    return book, plan


def _witness_sp4() -> tuple[dict[str, object], dict[str, object]]:
    """Show every reader what the map plant was meant to reveal.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book, plan = base_example()
    _section(plan, "nodes", "n_path")["establishes"] = ["map_marks_cave"]
    return book, plan


def _witness_sp5() -> tuple[dict[str, object], dict[str, object]]:
    """Put the map's payoff site behind the map's own gate.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book, plan = base_example()
    threads = _section(plan, "threads", "t_map")
    threads["payoff_sites"] = [
        {"node": "n_cave", "choice": "c_cave_on", "shows": "The map opens it."}
    ]
    return book, plan


def _witness_sp6() -> tuple[dict[str, object], dict[str, object]]:
    """Gate the lamp payoff on both plants and let it lean on the map's.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book, plan = base_example()
    nodes = book["nodes"]
    if isinstance(nodes, list):
        fork = nodes[2]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(fork, dict):
            choices = fork["choices"]  # pyright: ignore[reportUnknownVariableType]
            if isinstance(choices, list):
                tunnel = choices[1]  # pyright: ignore[reportUnknownVariableType]
                if isinstance(tunnel, dict):
                    tunnel["condition"] = {"and": [_yes("has_lamp"), _yes("has_map")]}
    _section(plan, "nodes", "n_tunnel")["requires"] = ["lamp_lit", "map_marks_cave"]
    return book, _bind(book, plan)


def _witness_sp7() -> tuple[dict[str, object], dict[str, object]]:
    """Drop the negative ending's gift.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book, plan = base_example()
    plan["endings"] = {}
    return book, plan


def _witness_sp8() -> tuple[dict[str, object], dict[str, object]]:
    """Give both opening choices the same cost.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book, plan = base_example()
    _section(plan, "choices", "c_take_map")["cost"] = "None."
    return book, plan


def _witness_sp9() -> tuple[dict[str, object], dict[str, object]]:
    """Forge a slot token in a fact sentence.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(book, plan)``.
    """
    book, plan = base_example()
    _section(plan, "facts", "cave_drawing")["text"] = "The cave shows {HERO} a fox."
    return book, plan


WITNESSES: Final[tuple[RuleWitness, ...]] = (
    RuleWitness("SP-0", _witness_sp0),
    RuleWitness("SP-1", _witness_sp1),
    RuleWitness("SP-2", _witness_sp2),
    RuleWitness("SP-3", _witness_sp3),
    RuleWitness("SP-4", _witness_sp4),
    RuleWitness("SP-5", _witness_sp5),
    RuleWitness("SP-6", _witness_sp6),
    RuleWitness("SP-7", _witness_sp7),
    RuleWitness("SP-8", _witness_sp8),
    RuleWitness("SP-9", _witness_sp9),
)


def verify_witnesses(witnesses: Sequence[RuleWitness] | None = None) -> list[str]:
    """Run the clean base and every witness and report any that misbehave.

    The base must raise no ERROR; each witness must raise ERRORs from its own
    rule and from no other. A rule that stops firing, or starts firing on the
    base, makes this list non-empty, so the rule table above cannot drift from
    the code unnoticed.

    Args:
        witnesses: The witnesses to run, defaulting to :data:`WITNESSES`.

    Returns:
        list[str]: One line per problem; empty means every rule still works.
    """
    problems: list[str] = []
    book, plan = base_example()
    base_report = check_plan(
        StoryPlan.model_validate(plan), Storybook.model_validate(book)
    )
    if not base_report.ok:
        fired = sorted({f.rule_id for f in base_report.errors})
        problems.append(f"base: expected no errors, got {fired}")
    for witness in witnesses if witnesses is not None else WITNESSES:
        book, plan = witness.build()
        report = check_plan(
            StoryPlan.model_validate(plan), Storybook.model_validate(book)
        )
        fired = {f.rule_id for f in report.errors}
        if fired != {witness.rule_id}:
            problems.append(
                f"{witness.rule_id}: witness should trip exactly that rule, "
                f"tripped {sorted(fired) or 'nothing'}"
            )
    return problems
