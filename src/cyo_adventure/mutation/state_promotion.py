"""In-place Tier promotion: give a stateless skeleton plants and payoffs.

The WS-5 design deferred "Tier promotion (adding state to a Tier-1 tree)" to a
later composer (``docs/planning/ws5-structure-state-variation-design.md``
section 5.5). This module is that backlog item, scoped narrowly: it does not
grow a new tree for the catalog (that is what the ``M1``..``M5`` operators and
their lineage/anti-clone machinery are for), it REVISES one skeleton in place so
that early choices come back later. Hence it is not registered as a mutation
operator and writes no lineage entry: the result is the same skeleton, made
stateful, and goes through the same review PR a hand edit would.

Why it exists. An editorial review of the filled catalogue found that books
stop behaving like choose-your-own-adventures by the middle: 69 of 84 committed
skeletons declared no variables, so every "branch and bottleneck" route
converged on merge nodes with nothing carried through, and a fill could only
write merge prose that hedges ("Whichever way she had come...") over forks that
rejoined with nothing changed. Five books were then revised by hand to prove a
fix that needs no engine or schema change. This module applies the structural
half of that recipe deterministically:

1. **Plants.** It reads the fork-consequence measure
   (:func:`cyo_adventure.validator.consequence.measure_consequence`) to find
   early forks whose branches reconverge quickly (the cosmetic forks), and puts
   a ``set`` effect on one or both options. When both options of one fork are
   planted they set different variables that pay off in different places, so
   the fork becomes a trade-off rather than "take the useful thing or not".
2. **Payoffs.** For each variable it picks a later decision node that readers
   reach both with and without the plant, and splits one of its choices into a
   same-label pair with opposite conditions:

   - ``rescue``: the choice used to run straight into a setback ending. Without
     the plant it still does; with it, the reader gets a short inserted payoff
     scene and carries on into the story through a sibling choice's target. This
     changes which ENDING the reader can reach, and at least one payoff per
     skeleton must be of this kind (verified on the configuration walk, not
     assumed).
   - ``pair``: the planter gets a short inserted payoff scene before the same
     next scene everyone shares. The outcome differs in what the reader sees.

   Every node that gains a conditional choice keeps at least one unconditional
   choice, so no reader is ever stranded.
3. **Directives.** Every new or affected node's ``<<FILL>>`` beats get a plain
   instruction saying what the plant and payoff mean dramatically, and every
   merge node (two or more distinct inbound nodes) is told that its body must be
   true on every inbound route and in every state, naming the variables whose
   values actually differ on arrival there.
4. **Verification.** The candidate must parse, pass the unchanged gate in
   skeleton posture, complete its configuration walk, show every payoff node in
   both states of its variable, and change ending reachability for at least one
   variable. Anything else is a refusal with a reason, never a partial write.

Pure module apart from calling the validator: standard library, ``networkx``-free,
no I/O, no LLM, no network. Given the same input it produces byte-identical
output, so a reviewer can re-derive any committed result.
"""

from __future__ import annotations

import copy
import math
import random
import re
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.mutation.identity import recompute_estimated_minutes
from cyo_adventure.storybook.fill_directive import has_v2_directives
from cyo_adventure.storybook.models import Storybook, Valence
from cyo_adventure.validator.band_profile import production_cell_budget
from cyo_adventure.validator.consequence import ForkConsequence, measure_consequence
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.layer1 import ScalePlacement, resolve_node_budget
from cyo_adventure.validator.report import Severity
from cyo_adventure.validator.walk import walk_configurations

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from cyo_adventure.storybook.models import Choice, Node
    from cyo_adventure.validator.walk import ConfigKey, WalkResult

__all__ = [
    "MAX_VARIABLES",
    "MIN_VARIABLES",
    "STATE_BANDS",
    "PayoffPlacement",
    "PlantPlacement",
    "PromotionReport",
    "StateMetrics",
    "measure_state",
    "promote_skeleton",
    "stateless_view",
]

# #ASSUME: security: the bands whose ADR-011 section 7 row permits state are
# 8-11 ("optional (T2)") and up; 3-5 and 5-8 are Tier-1 by contract, and the
# 2026-08-15 amendment (`AL-409`) forbids anything counted, collected, or referred
# back to there. Mirrors mutation/state_ops.py::_STATE_PERMITTED_BANDS, which is
# private to that module; a young-band skeleton is refused, never promoted.
# #VERIFY: tests/unit/test_state_promotion.py::test_young_band_is_refused.
STATE_BANDS: frozenset[str] = frozenset({"8-11", "10-13", "13-16", "16+"})

# The recipe's variable budget ("two to four booleans"). Four booleans multiply
# the reachable configuration space by at most 16, so even the largest committed
# skeleton (677 nodes) bounds at 10,832 configurations, an order of magnitude
# under the L2-12 cap of 100,000.
MIN_VARIABLES = 2
MAX_VARIABLES = 4
_VARIABLES_BY_LENGTH: dict[str, int] = {"short": 2, "medium": 3, "long": 4}

# A fork is a plant candidate when two of its options rejoin within this many
# nodes (the consequence measure's distance; it searches a 12-node horizon). The
# measure calls distance <= 1 a false choice, and up to 3 is still a corridor
# detour that changes nothing; longer detours are real scenes that still rejoin,
# so they qualify too but rank lower (see _COSMETIC_WEIGHT).
_PLANT_MAX_DISTANCE = 8
_COSMETIC_WEIGHT: tuple[tuple[int, float], ...] = ((1, 1.0), (3, 0.8), (8, 0.5))

# How many times to re-plan after a verification failure that names a payoff
# node (not reached in both states, or a branch-depth overrun), excluding it.
_MAX_ATTEMPTS = 8

# Payoff sites per variable (on different lanes). See _add_extra_sites for the
# measurement behind it; two keeps the conditional-choice count (two per site)
# at 8-16 for a four-variable skeleton, the range the hand-revised books use.
_SITES_PER_VARIABLE = 2

# Plants must be early: the fork's shortest depth from the start may be at most
# this fraction of the deepest non-ending node's depth.
_EARLY_FRACTION = 0.5

# A payoff must sit at least this many hops deeper than its plant fork.
_MIN_PAYOFF_GAP = 2

# A "setback corridor" is a run of at most this many single-choice nodes ending
# in an ending of one of these valences. A rescue payoff reroutes the planter
# around it.
_CORRIDOR_MAX_HOPS = 3
_SETBACK_VALENCES: frozenset[Valence] = frozenset({Valence.NEGATIVE, Valence.NEUTRAL})

# The hard options-per-decision ceiling (choice_grammar._OPTIONS_HARD_CEILING).
# A same-label pair adds one DECLARED choice while leaving the VISIBLE count
# unchanged, so the payoff node may hold at most this many minus one before.
_MAX_DECLARED_CHOICES = 4

# ADR-011 section 10 words-per-stop ceilings for the flowed bands, copied from
# validator/choice_grammar.py::_WORDS_PER_STOP_CEILING (private there). Inserted
# single-choice nodes are sized to fit under them; see _fit_stop.
# #ASSUME: data-integrity: these four values match choice_grammar's table; a
# drift only mis-sizes a words= hint (CG-3 is a strict-posture advisory), it
# cannot let a defect through the gate.
# #VERIFY: test_state_promotion.py::test_words_per_stop_table_matches_choice_grammar.
_WORDS_PER_STOP_CEILING: dict[str, int] = {
    "8-11": 135,
    "10-13": 150,
    "13-16": 200,
    "16+": 230,
}
_MIN_INSERTED_WORDS = 25

# Monte Carlo settings for visit probabilities on graphs with cycles (open_map
# hubs). Seeded, so the ranking is reproducible.
_MC_WALKS = 2000
_MC_SEED = 20261120

_NO_EXCLUSIONS: frozenset[str] = frozenset()
_FILL_RE = re.compile(r"^<<FILL role=(\S+) words=(\d+) beats='(.*)'>>$", re.DOTALL)
_EM_DASH = chr(0x2014)  # em-dash-ok: the character this check rejects
_ID_INFIX = "cq"
_NAME_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "as", "at", "be", "by", "first", "for", "from", "her",
        "his", "in", "into", "is", "it", "its", "of", "on", "or", "out", "the",
        "their", "them", "then", "to", "up", "while", "with", "you", "your",
    }
)  # fmt: skip
_SLOT_TOKEN_RE = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")

PayoffKind = Literal["rescue", "pair"]
Status = Literal["promoted", "refused", "skipped"]


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlantPlacement:
    """One variable's plant: the choice that sets it.

    Attributes:
        variable: The declared boolean variable's name.
        fork_id: The decision node the plant choice sits on.
        choice_id: The choice that now carries ``set variable true``.
        label: That choice's label, quoted in the directives.
        site_id: The node whose beats carry the plant instruction: the choice's
            own target when only this choice enters it, else an inserted arrival.
        inserted_arrival: Whether ``site_id`` is a node this module inserted.
    """

    variable: str
    fork_id: str
    choice_id: str
    label: str
    site_id: str
    inserted_arrival: bool


@dataclass(frozen=True, slots=True)
class PayoffPlacement:
    """One variable's payoff: the later choice whose outcome depends on it.

    Attributes:
        variable: The variable the payoff tests.
        node_id: The decision node holding the same-label pair.
        kind: ``"rescue"`` (the ungated option runs into a setback ending, the
            gated twin recovers) or ``"pair"`` (the gated twin shows a payoff
            scene before the shared next scene).
        choice_id: The original choice, now gated ``variable == false``.
        gated_choice_id: The inserted twin, gated ``variable == true``.
        label: The label both twins share.
        scene_id: The inserted payoff scene the gated twin leads to.
        rejoin_id: Where the payoff scene continues.
        setback_ending: For a rescue, the ending the ungated twin leads into.
    """

    variable: str
    node_id: str
    kind: PayoffKind
    choice_id: str
    gated_choice_id: str
    label: str
    scene_id: str
    rejoin_id: str
    setback_ending: str | None


@dataclass(frozen=True, slots=True)
class StateMetrics:
    """The before/after numbers the pilot table reports.

    Attributes:
        nodes: Node count.
        merges: Nodes with two or more distinct inbound nodes.
        variables: Declared variables.
        conditional_choices: Choices carrying a condition.
        forks: Fork pairs the consequence measure scored.
        false_forks: Of those, the false choices.
        walk_configs: Reachable configurations (node count for a stateless book).
        walk_capped: Whether the configuration walk hit its cap.
        gate_blocked: Whether the gate blocks the document.
        gate_errors: ERROR findings.
        gate_warnings: WARNING findings by rule id.
    """

    nodes: int
    merges: int
    variables: int
    conditional_choices: int
    forks: int
    false_forks: int
    walk_configs: int
    walk_capped: bool
    gate_blocked: bool
    gate_errors: int
    gate_warnings: dict[str, int]


@dataclass(frozen=True, slots=True)
class PromotionReport:
    """The outcome of one :func:`promote_skeleton` call.

    Attributes:
        story_id: The skeleton's ``id``.
        status: ``"promoted"`` with a candidate, ``"refused"`` with a reason, or
            ``"skipped"`` when the skeleton already declares state (running the
            tool twice never adds a second set).
        reason: Why it was refused or skipped; empty when promoted.
        candidate: The promoted document, or ``None``.
        plants: The placed plants, in variable order.
        payoffs: The placed payoffs, in variable order.
        ending_changing: Variables whose payoff changes which endings a reader
            standing at the payoff node can still reach (walk-verified).
        merges_annotated: How many merge directives got the state-neutral note.
        notes: Advisory notes (metadata resyncs, skipped annotations).
    """

    story_id: str
    status: Status
    reason: str = ""
    candidate: dict[str, object] | None = None
    plants: tuple[PlantPlacement, ...] = ()
    payoffs: tuple[PayoffPlacement, ...] = ()
    ending_changing: tuple[str, ...] = ()
    merges_annotated: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Graph view over a parsed story
# ---------------------------------------------------------------------------


class _Graph:
    """Read-only structural view of a parsed story, built once per call."""

    def __init__(self, story: Storybook, depth_budget: int | None = None) -> None:
        """Index nodes, edges, depths, and visit probabilities.

        Args:
            story: The parsed story.
            depth_budget: The L1-7 branch-depth ceiling for the story's cell, or
                ``None`` when no budget applies (insertions are then unchecked
                here and left to the gate).
        """
        self.story = story
        self.nodes: dict[str, Node] = {n.id: n for n in story.nodes}
        self.order: list[str] = [n.id for n in story.nodes]
        self.succ: dict[str, list[str]] = {}
        self.preds: dict[str, set[str]] = {n.id: set() for n in story.nodes}
        for node in story.nodes:
            targets: list[str] = []
            for choice in node.choices:
                if choice.target not in targets:
                    targets.append(choice.target)
                self.preds.setdefault(choice.target, set()).add(node.id)
            self.succ[node.id] = targets
        self.depth = self._bfs_depth(story.start_node)
        self.is_dag = self._acyclic()
        self.reach = self._reach_dag() if self.is_dag else self._reach_monte_carlo()
        self.depth_budget = depth_budget
        self._reach_cache: dict[str, dict[str, float]] = {}
        self.longest_from: dict[str, int] = {}
        self.longest_to: dict[str, int] = {}
        if self.is_dag:
            self._longest_paths()

    def _longest_paths(self) -> None:
        order = self._topological()
        best_from = dict.fromkeys(self.order, -1)
        best_from[self.story.start_node] = 0
        for node_id in order:
            if best_from[node_id] < 0:
                continue
            for t in self.succ.get(node_id, []):
                best_from[t] = max(best_from[t], best_from[node_id] + 1)
        best_to = dict.fromkeys(self.order, 0)
        for node_id in reversed(order):
            targets = self.succ.get(node_id, [])
            if targets:
                best_to[node_id] = 1 + max(best_to[t] for t in targets)
        self.longest_from = best_from
        self.longest_to = best_to

    def fits_insertion(self, source: str, target: str) -> bool:
        """Whether one node inserted on the edge ``source -> target`` fits L1-7.

        Inserting a node lengthens every path through that edge by one hop, so
        the longest such path must stay at or under the cell's branch-depth cap.
        On a graph with cycles L1-7 measures the condensation instead; this
        returns ``True`` there and the gate run in verification is the authority.

        Args:
            source: The node the choice leaves from.
            target: The node the choice used to enter.

        Returns:
            Whether the lengthened path stays inside the depth budget.
        """
        if self.depth_budget is None or not self.is_dag:
            return True
        through = self.longest_from.get(source, -1)
        if through < 0:
            return True
        return through + 2 + self.longest_to.get(target, 0) <= self.depth_budget

    def _bfs_depth(self, start: str) -> dict[str, int]:
        depth = {start: 0}
        queue: deque[str] = deque([start])
        while queue:
            cur = queue.popleft()
            for nxt in self.succ.get(cur, []):
                if nxt not in depth and nxt in self.nodes:
                    depth[nxt] = depth[cur] + 1
                    queue.append(nxt)
        return depth

    def _acyclic(self) -> bool:
        indeg = dict.fromkeys(self.order, 0)
        for targets in self.succ.values():
            for t in targets:
                if t in indeg:
                    indeg[t] += 1
        queue: deque[str] = deque(n for n in self.order if indeg[n] == 0)
        seen = 0
        while queue:
            cur = queue.popleft()
            seen += 1
            for t in self.succ.get(cur, []):
                if t in indeg:
                    indeg[t] -= 1
                    if indeg[t] == 0:
                        queue.append(t)
        return seen == len(self.order)

    def _topological(self) -> list[str]:
        indeg = dict.fromkeys(self.order, 0)
        for targets in self.succ.values():
            for t in targets:
                indeg[t] += 1
        queue: deque[str] = deque(n for n in self.order if indeg[n] == 0)
        result: list[str] = []
        while queue:
            cur = queue.popleft()
            result.append(cur)
            for t in self.succ.get(cur, []):
                indeg[t] -= 1
                if indeg[t] == 0:
                    queue.append(t)
        return result

    def _reach_dag(self) -> dict[str, float]:
        """Exact probability a uniform random reader visits each node (DAG)."""
        prob = dict.fromkeys(self.order, 0.0)
        prob[self.story.start_node] = 1.0
        for node_id in self._topological():
            node = self.nodes[node_id]
            if not node.choices or prob[node_id] == 0.0:
                continue
            share = prob[node_id] / len(node.choices)
            for choice in node.choices:
                prob[choice.target] += share
        return prob

    def _reach_monte_carlo(self) -> dict[str, float]:
        """Seeded estimate of the visit probability on a graph with cycles."""
        rng = random.Random(_MC_SEED)  # noqa: S311  # nosec B311 - ranking only
        visits = dict.fromkeys(self.order, 0)
        step_cap = 4 * len(self.order)
        for _ in range(_MC_WALKS):
            seen: set[str] = set()
            cur = self.story.start_node
            for _step in range(step_cap):
                seen.add(cur)
                node = self.nodes[cur]
                if node.is_ending or not node.choices:
                    break
                cur = rng.choice(node.choices).target
            for node_id in seen:
                visits[node_id] += 1
        return {k: v / _MC_WALKS for k, v in visits.items()}

    def reach_from(self, start: str) -> dict[str, float]:
        """Visit probability of each node for a uniform reader standing at ``start``.

        Exact on a DAG; on a graph with cycles it falls back to the global
        Monte Carlo estimate (a ranking signal only). Cached per start node.
        """
        cached = self._reach_cache.get(start)
        if cached is not None:
            return cached
        if not self.is_dag:
            self._reach_cache[start] = self.reach
            return self.reach
        prob = dict.fromkeys(self.order, 0.0)
        prob[start] = 1.0
        for node_id in self._topological():
            node = self.nodes[node_id]
            if not node.choices or prob[node_id] == 0.0:
                continue
            share = prob[node_id] / len(node.choices)
            for choice in node.choices:
                prob[choice.target] += share
        self._reach_cache[start] = prob
        return prob

    def ancestors(self, root: str) -> set[str]:
        """Return every node that can reach ``root``, including ``root``."""
        seen = {root}
        queue: deque[str] = deque([root])
        while queue:
            cur = queue.popleft()
            for prev in self.preds.get(cur, set()):
                if prev not in seen:
                    seen.add(prev)
                    queue.append(prev)
        return seen

    def descendants(self, root: str) -> set[str]:
        """Return every node reachable from ``root``, including ``root``."""
        seen = {root}
        queue: deque[str] = deque([root])
        while queue:
            cur = queue.popleft()
            for nxt in self.succ.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def merges(self) -> list[str]:
        """Return node ids with two or more distinct inbound nodes, file order."""
        return [n for n in self.order if len(self.preds.get(n, set())) >= 2]

    def max_depth(self) -> int:
        """Return the deepest shortest-depth of any reachable non-ending node."""
        depths = [d for n, d in self.depth.items() if not self.nodes[n].is_ending]
        return max(depths) if depths else 0

    def setback_valence(self, target: str) -> Valence | None:
        """Return the valence of the setback ending ``target`` runs into."""
        ending_id = self.setback_corridor(target)
        if ending_id is None:
            return None
        ending = self.nodes[ending_id].ending
        return ending.valence if ending is not None else None

    def setback_corridor(self, target: str) -> str | None:
        """Return the setback ending ``target`` runs straight into, if any.

        A corridor is ``target`` itself being such an ending, or a run of at most
        :data:`_CORRIDOR_MAX_HOPS` single-choice nodes ending in one.

        Args:
            target: The node a choice leads to.

        Returns:
            The ending node id, or ``None``.
        """
        cur = target
        for _ in range(_CORRIDOR_MAX_HOPS + 1):
            node = self.nodes.get(cur)
            if node is None:
                return None
            if node.is_ending:
                ending = node.ending
                if ending is not None and ending.valence in _SETBACK_VALENCES:
                    return cur
                return None
            if len(node.choices) != 1:
                return None
            cur = node.choices[0].target
        return None


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ForkPlan:
    fork_id: str
    choices: tuple[str, str]


@dataclass(frozen=True, slots=True)
class _PayoffPlan:
    node_id: str
    kind: PayoffKind
    choice_id: str
    continue_choice_id: str
    setback_ending: str | None

    def choice_target(self, graph: _Graph) -> str:
        return _choice(graph, self.node_id, self.choice_id).target


@dataclass(slots=True)
class _VarPlan:
    name: str
    fork: _ForkPlan
    choice_id: str
    label: str
    payoffs: list[_PayoffPlan]

    @property
    def fork_id(self) -> str:
        return self.fork.fork_id

    @property
    def payoff(self) -> _PayoffPlan:
        """The primary payoff (the one planned first)."""
        return self.payoffs[0]


@dataclass(slots=True)
class _Planner:
    graph: _Graph
    target: int = MIN_VARIABLES
    used_nodes: set[str] = field(default_factory=set)
    plans: list[_VarPlan] = field(default_factory=list)
    names: set[str] = field(default_factory=set)
    diagnostics: list[str] = field(default_factory=list)


def _choice(graph: _Graph, node_id: str, choice_id: str) -> Choice:
    for choice in graph.nodes[node_id].choices:
        if choice.id == choice_id:
            return choice
    msg = f"choice {choice_id} not on node {node_id}"
    raise KeyError(msg)


def _fork_candidates(graph: _Graph) -> list[_ForkPlan]:
    """Return plantable forks, best first.

    A fork qualifies when it is an unconditioned decision node below the start,
    in the early part of the story, and two of its options rejoin within
    :data:`_PLANT_MAX_DISTANCE` nodes without either running to an ending.
    """
    # #ASSUME: data-integrity: on a stateless skeleton every declared choice is
    # visible in every configuration, so the consequence measure's per-successor
    # choice ids (it pairs the i-th visible successor with the i-th declared
    # choice) are the real choice ids. This module only plans on stateless
    # input; a stateful skeleton is skipped before planning.
    # #VERIFY: test_state_promotion.py::test_cosmetic_fork_becomes_a_plant pins a
    # fork whose planted choice ids match the declared ones.
    report = measure_consequence(graph.story)
    early_limit = max(2, math.ceil(graph.max_depth() * _EARLY_FRACTION))
    best: dict[str, ForkConsequence] = {}
    for fork in report.forks:
        if fork.outcome != "reconverged" or fork.distance is None:
            continue
        if fork.distance > _PLANT_MAX_DISTANCE or fork.reconverged_at is None:
            continue
        node = graph.nodes.get(fork.node_id)
        if node is None or node.id == graph.story.start_node:
            continue
        if graph.depth.get(node.id, early_limit + 1) > early_limit:
            continue
        ids = {c.id for c in node.choices}
        if not set(fork.choices) <= ids:
            continue
        if any(c.condition is not None or c.effects for c in node.choices):
            continue
        targets = [_choice(graph, node.id, cid).target for cid in fork.choices]
        if any(graph.nodes[t].is_ending for t in targets):
            continue
        current = best.get(node.id)
        if current is None or _fork_rank(fork) < _fork_rank(current):
            best[node.id] = fork
    plans = [
        _ForkPlan(
            fork_id=f.node_id,
            choices=(f.choices[0], f.choices[1]),
        )
        for f in best.values()
    ]
    weight = {f.node_id: _cosmetic_weight(f) for f in best.values()}
    plans.sort(
        key=lambda p: (
            -graph.reach.get(p.fork_id, 0.0) * weight[p.fork_id],
            graph.depth[p.fork_id],
            p.fork_id,
        )
    )
    return plans


def _cosmetic_weight(fork: ForkConsequence) -> float:
    distance = fork.distance or 0
    if fork.is_false_choice:
        return 1.0
    return next((w for limit, w in _COSMETIC_WEIGHT if distance <= limit), 0.0)


def _fork_rank(fork: ForkConsequence) -> tuple[int, int]:
    return (0 if fork.is_false_choice else 1, fork.distance or 0)


def _payoff_options(
    graph: _Graph, node_id: str, used: set[str]
) -> tuple[_PayoffPlan | None, _PayoffPlan | None]:
    """Return the (rescue, pair) payoff shapes a node supports, if any."""
    node = graph.nodes[node_id]
    rescue: _PayoffPlan | None = None
    pair: _PayoffPlan | None = None
    continuations = [
        c
        for c in node.choices
        if not graph.nodes[c.target].is_ending
        and graph.setback_corridor(c.target) is None
        and c.target not in used
    ]
    # A rescue may also carry on into a sibling's POSITIVE ending when the node
    # offers no continuation at all (a climax node whose options are all
    # endings): the planter's risky move then lands the good outcome.
    good_endings = [
        c
        for c in node.choices
        if graph.nodes[c.target].is_ending
        and (ending_model := graph.nodes[c.target].ending) is not None
        and ending_model.valence is Valence.POSITIVE
    ]
    # A negative setback is the better rescue target: rerouting a reader away
    # from a reflective neutral ending takes something from them, rerouting
    # away from a failure gives them something.
    ordered = sorted(
        node.choices,
        key=lambda c: 0 if graph.setback_valence(c.target) is Valence.NEGATIVE else 1,
    )
    for choice in ordered:
        ending = graph.setback_corridor(choice.target)
        if ending is None or rescue is not None:
            continue
        sibling = next(
            (c for c in [*continuations, *good_endings] if c.id != choice.id), None
        )
        if sibling is not None and graph.fits_insertion(node_id, sibling.target):
            rescue = _PayoffPlan(node_id, "rescue", choice.id, sibling.id, ending)
    fitting = [c for c in continuations if graph.fits_insertion(node_id, c.target)]
    if fitting:
        first = fitting[0]
        pair = _PayoffPlan(node_id, "pair", first.id, first.id, None)
    return rescue, pair


def _payoff_site_ok(graph: _Graph, node_id: str, unavailable: set[str]) -> bool:
    """Whether ``node_id`` can host a same-label payoff pair at all."""
    node = graph.nodes[node_id]
    return not (
        node.is_ending
        or len(node.choices) < 2
        or len(node.choices) >= _MAX_DECLARED_CHOICES
        or node_id in unavailable
        or node_id == graph.story.start_node
        or any(c.condition is not None or c.effects for c in node.choices)
    )


def _find_payoff(
    planner: _Planner,
    plant: tuple[_ForkPlan, str],
    *,
    prefer_rescue: bool,
    blocked: set[str] | None = None,
) -> _PayoffPlan | None:
    """Pick the best payoff for ``plant``, a ``(fork, planted option id)`` pair.

    Sites are ranked by how many uniform random readers arrive there HOLDING the
    plant (the visit probability propagated from the planted option's target),
    discounted when the site sits close behind the fork. Ranking by plain visit
    probability instead favoured sites the planter rarely reaches.
    """
    graph = planner.graph
    fork, planted = plant
    planted_target = _choice(graph, fork.fork_id, planted).target
    exposure = graph.reach_from(planted_target)
    fork_depth = graph.depth[fork.fork_id]
    want_gap = max(_MIN_PAYOFF_GAP + 1, graph.max_depth() // 3)
    scored: list[tuple[tuple[float, float, int, str], _PayoffPlan]] = []
    unavailable = planner.used_nodes | (blocked or set())
    # Candidates are the nodes reachable from BOTH planted options' targets,
    # i.e. on a route the planter and the other reader share. Not the
    # measure's ``reconverged_at``: it breaks ties by set iteration order, which
    # made the choice depend on PYTHONHASHSEED.
    # #CRITICAL: data-integrity: the output must be byte-identical across runs,
    # or a committed skeleton cannot be re-derived by its reviewer.
    # #VERIFY: test_state_promotion.py::test_committed_pilot_is_reproducible and
    # the PYTHONHASHSEED subprocess test.
    first, second = (_choice(graph, fork.fork_id, c).target for c in fork.choices)
    shared = graph.descendants(first) & graph.descendants(second)
    for node_id in sorted(shared):
        depth = graph.depth.get(node_id)
        if depth is None or not _payoff_site_ok(graph, node_id, unavailable):
            continue
        if depth < fork_depth + _MIN_PAYOFF_GAP:
            continue
        rescue, pair = _payoff_options(graph, node_id, planner.used_nodes)
        options = [
            o for o in ((rescue, pair) if prefer_rescue else (pair, rescue)) if o
        ]
        if not options:
            continue
        chosen = options[0]
        bonus = 1.0
        if prefer_rescue and chosen.kind == "rescue":
            negative = (
                graph.setback_valence(chosen.choice_target(graph)) is Valence.NEGATIVE
            )
            bonus = 0.0 if negative else 0.5
        gap_factor = min(1.0, (depth - fork_depth) / want_gap)
        score = exposure.get(node_id, 0.0) * gap_factor
        scored.append(((bonus, -score, -depth, node_id), chosen))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0])
    return scored[0][1]


def _variable_name(label: str, taken: set[str]) -> str:
    """Derive a lower-snake variable name from a plant label."""
    text = _SLOT_TOKEN_RE.sub(lambda m: m.group(1).lower(), label)
    found = cast("list[str]", re.findall(r"[A-Za-z]+", text))
    words = [w.lower() for w in found]
    content = [w for w in words if w not in _NAME_STOPWORDS][:3] or ["choice"]
    base = "did_" + "_".join(content)
    name = base
    suffix = 2
    while name in taken:
        name = f"{base}_{suffix}"
        suffix += 1
    taken.add(name)
    return name


def _needs_arrival(graph: _Graph, fork_id: str, choice: Choice) -> bool:
    """Whether a plant on ``choice`` needs an inserted arrival node."""
    shared = (
        graph.preds.get(choice.target, set()) != {fork_id}
        or sum(1 for c in graph.nodes[fork_id].choices if c.target == choice.target)
        != 1
    )
    return shared or _FILL_RE.match(graph.nodes[choice.target].body) is None


def _place_one(
    planner: _Planner, fork: _ForkPlan, choice_id: str, blocked: set[str]
) -> bool:
    """Try to plant one variable on ``choice_id`` and find its payoff.

    Args:
        planner: The planner, updated in place on success.
        fork: The plant fork.
        choice_id: The option to plant on.
        blocked: Node ids no payoff may use on this attempt (other forks).

    Returns:
        Whether a variable was placed.
    """
    graph = planner.graph
    if len(planner.plans) >= planner.target:
        return False
    plant_choice = _choice(graph, fork.fork_id, choice_id)
    if _needs_arrival(graph, fork.fork_id, plant_choice) and not (
        graph.fits_insertion(fork.fork_id, plant_choice.target)
    ):
        msg = (
            f"fork {fork.fork_id}: an arrival node for {choice_id} would exceed "
            "the cell's branch-depth cap"
        )
        planner.diagnostics.append(msg)
        return False
    # Odd-numbered variables (the 1st and 3rd) prefer a rescue, so a three- or
    # four-variable skeleton gets two ending-changing payoffs where the graph
    # offers them, and the rest show payoff scenes.
    rescues = sum(1 for p in planner.plans if p.payoff.kind == "rescue")
    prefer_rescue = rescues < (len(planner.plans) + 2) // 2
    payoff = _find_payoff(
        planner, (fork, choice_id), prefer_rescue=prefer_rescue, blocked=blocked
    )
    if payoff is None:
        msg = (
            f"fork {fork.fork_id}: no payoff site for {choice_id} at least "
            f"{_MIN_PAYOFF_GAP} hops deeper on the shared route"
        )
        planner.diagnostics.append(msg)
        return False
    name = _variable_name(plant_choice.label, planner.names)
    planner.plans.append(_VarPlan(name, fork, choice_id, plant_choice.label, [payoff]))
    planner.used_nodes |= {payoff.node_id, fork.fork_id}
    planner.used_nodes |= {c.target for c in graph.nodes[payoff.node_id].choices}
    return True


def _add_extra_sites(planner: _Planner, fork_ids: set[str]) -> None:
    """Give each planted variable up to :data:`_SITES_PER_VARIABLE` payoff sites.

    Measured on the 2026-11-20 pilot: with one site per variable only 2-8% of
    uniform random readers ever reached a payoff scene, because these lattice
    graphs spread readers across many parallel nodes and no single mid-story
    node is visited by more than about a sixth of them. Extra sites go on nodes
    on OTHER lanes (neither an ancestor nor a descendant of the variable's
    existing sites), so they reach readers the first site misses instead of
    paying the same reader off twice.

    Args:
        planner: The planner, updated in place.
        fork_ids: Every plant fork candidate (never a payoff site).
    """
    graph = planner.graph
    for plan in planner.plans:
        while len(plan.payoffs) < _SITES_PER_VARIABLE:
            lane = set(fork_ids)
            for site in plan.payoffs:
                lane |= graph.descendants(site.node_id) | graph.ancestors(site.node_id)
            extra = _find_payoff(
                planner, (plan.fork, plan.choice_id), prefer_rescue=False, blocked=lane
            )
            if extra is None:
                break
            plan.payoffs.append(extra)
            planner.used_nodes.add(extra.node_id)
            planner.used_nodes |= {c.target for c in graph.nodes[extra.node_id].choices}


def _plan(
    graph: _Graph, target: int, excluded: frozenset[str] = _NO_EXCLUSIONS
) -> _Planner:
    """Choose plants and payoffs on the original graph (no edits yet).

    Args:
        graph: The structural view.
        target: How many variables to aim for.
        excluded: Node ids a previous attempt's verification ruled out as
            payoff sites.

    Returns:
        The planner holding the plans and any diagnostics.
    """
    planner = _Planner(graph=graph, target=target)
    planner.used_nodes |= set(excluded)
    forks = _fork_candidates(graph)
    if not forks:
        msg = (
            f"no early fork whose options rejoin within {_PLANT_MAX_DISTANCE} "
            "nodes (every early fork diverges to different endings, so a plant "
            "could not be paid off on a route the non-planter also walks)"
        )
        planner.diagnostics.append(msg)
        return planner
    fork_ids = {f.fork_id for f in forks}
    for fork in forks:
        if len(planner.plans) >= target:
            break
        if fork.fork_id in planner.used_nodes:
            continue
        # A payoff may not sit on any fork we may still plant on later.
        blocked = fork_ids - {fork.fork_id}
        placed = [
            choice_id
            for choice_id in fork.choices
            if _place_one(planner, fork, choice_id, blocked)
        ]
        if placed:
            planner.used_nodes |= set(graph.succ.get(fork.fork_id, []))
    _add_extra_sites(planner, fork_ids)
    return planner


# ---------------------------------------------------------------------------
# Directive text (ASCII only, no em-dash, no brace except slot tokens in labels)
# ---------------------------------------------------------------------------


def _q(label: str) -> str:
    return '"' + label.strip().rstrip(".") + '"'


def _plain(label: str) -> str:
    """Return ``label`` with each ``{SLOT}`` token spelled as plain words."""
    return _SLOT_TOKEN_RE.sub(lambda m: m.group(1).lower().replace("_", " "), label)


def _append_beats(body: str, text: str) -> str | None:
    """Return ``body`` with ``text`` appended inside its beats, or ``None``."""
    match = _FILL_RE.match(body)
    if match is None:
        return None
    beats = match.group(3).rstrip()
    sep = "" if not beats else (" " if beats.endswith((".", ";", ":")) else "; ")
    return (
        f"<<FILL role={match.group(1)} words={match.group(2)} "
        f"beats='{beats}{sep}{text}'>>"
    )


def _directive(role: str, words: int, beats: str) -> str:
    return f"<<FILL role={role} words={words} beats='{beats}'>>"


def _median_words(story: Storybook) -> int:
    values: list[int] = []
    for node in story.nodes:
        if node.is_ending:
            continue
        match = _FILL_RE.match(node.body)
        if match is not None:
            values.append(int(match.group(2)))
    return int(statistics.median(values)) if values else 90


def _plant_text(plan: _VarPlan, graph: _Graph) -> str:
    """Return the plant beat, naming every later move the plant must serve."""
    moves = " or ".join(
        f"{_q(_choice(graph, p.node_id, p.choice_id).label)} (node {p.node_id})"
        for p in plan.payoffs
    )
    return (
        f"PLANT ({plan.name}): the hero has just made this choice, and something "
        "concrete comes of it that a reader will remember: an object kept, a "
        "person helped, or a fact learned, named plainly in the prose. Invent it "
        "so that it would plausibly help much later, when the hero tries "
        f"{moves}: there it changes how that moment goes."
    )


def _fork_text(entries: list[tuple[str, str, str]]) -> str:
    """Return the fork note naming what each planted option sets."""
    planted = "; ".join(
        f"{_q(label)} plants {var} (pays off at {payoff})"
        for label, var, payoff in entries
    )
    tail = (
        "Stage every option as appealing, with none the obviously right answer."
        if len(entries) > 1
        else "The other options must keep their own appeal, so this is a real trade-off."
    )
    return f"PLANT SITE: these options are no longer cosmetic: {planted}. {tail}"


def _payoff_site_text(plan: _VarPlan, payoff: _PayoffPlan, label: str) -> str:
    """Return the note for the node that holds a same-label pair."""
    base = (
        f"PAYOFF SITE ({plan.name}): readers arrive here both having and not "
        f"having chosen {_q(plan.label)} earlier, so this body must be true "
        f"either way and must not say which. The option {_q(label)} plays out "
        "differently for the two"
    )
    if payoff.kind == "rescue":
        return (
            f"{base}: without that earlier choice it leads to the setback "
            f"({payoff.setback_ending}); with it, to a recovery."
        )
    return f"{base}: with that earlier choice the reader first sees a payoff scene."


def _scene_text(plan: _VarPlan, payoff: _PayoffPlan, label: str, onward: Choice) -> str:
    """Return the inserted payoff scene's beats."""
    next_label, next_node = onward.label, onward.target
    head = (
        f"PAYOFF ({plan.name}): only a reader who earlier chose "
        f"{_q(plan.label)} (node {plan.fork_id}) reaches this scene. The hero "
        f"tries {_q(label)}."
    )
    if payoff.kind == "rescue":
        return (
            f"{head} For a reader without that earlier choice the same move ends "
            f"the story early ({payoff.setback_ending}). Here the thing that "
            "came of it turns the moment around: show it returning concretely and "
            f"making the difference. End with the hero moving on to "
            f"{_q(next_label)}, leading into the next scene (node {next_node}), "
            "which other readers also reach, without contradicting it."
        )
    return (
        f"{head} The thing that came of that earlier choice changes how it goes: "
        "show it returning concretely in a few sentences, a moment only this "
        f"reader gets. Then lead into the next scene (node {next_node}), which "
        "every reader who makes this move reaches, without contradicting it."
    )


def _setback_hint_text(var: str, plant_label: str) -> str:
    return (
        f"SETBACK HINT ({var}): every reader who reaches this ending did NOT "
        f"choose {_q(plant_label)} earlier. Let the ending glimpse what would "
        "have helped, so the reader has a concrete reason to try again; do not "
        "scold."
    )


def _merge_text(differing: list[str]) -> str:
    """Return the state-neutral merge note, naming the plants that differ."""
    text = (
        "MERGE: readers reach this scene by more than one route; open in the "
        "moment, assert only what is true on every route, and never say which "
        "way the hero came."
    )
    if len(differing) == 1:
        text += (
            f" Some readers earlier chose {differing[0]} and some did not, so the "
            "body must not depend on it."
        )
    elif differing:
        text += (
            " Readers also differ in what they chose earlier ("
            + "; ".join(differing)
            + "), so the body must not depend on any of it."
        )
    return text


# ---------------------------------------------------------------------------
# Applying a plan to the raw document
# ---------------------------------------------------------------------------


def _raw_nodes(doc: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", doc["nodes"])


def _raw_choices(node: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", node.setdefault("choices", []))


def _cond(var: str, value: bool) -> dict[str, object]:
    return {"==": [{"var": var}, value]}


@dataclass(slots=True)
class _Editor:
    doc: dict[str, object]
    graph: _Graph
    words: int
    notes: list[str] = field(default_factory=list)
    band: str = ""
    scene_words: int = _MIN_INSERTED_WORDS

    def node(self, node_id: str) -> dict[str, object]:
        for node in _raw_nodes(self.doc):
            if node.get("id") == node_id:
                return node
        msg = f"node {node_id} missing"
        raise KeyError(msg)

    def choice(self, node_id: str, choice_id: str) -> dict[str, object]:
        for choice in _raw_choices(self.node(node_id)):
            if choice.get("id") == choice_id:
                return choice
        msg = f"choice {choice_id} missing on {node_id}"
        raise KeyError(msg)

    def annotate(self, node_id: str, text: str) -> bool:
        node = self.node(node_id)
        body = node.get("body")
        updated = _append_beats(body, text) if isinstance(body, str) else None
        if updated is None:
            self.notes.append(f"node {node_id} has no FILL directive; note not added")
            return False
        node["body"] = updated
        return True

    def insert_after(self, anchor_id: str, new_node: dict[str, object]) -> None:
        nodes = _raw_nodes(self.doc)
        index = next(i for i, n in enumerate(nodes) if n.get("id") == anchor_id)
        nodes.insert(index + 1, new_node)


def _stop_words_from(graph: _Graph, start: str) -> int:
    """Words of the flowed run from ``start`` to the first decision or ending.

    Mirrors player/stops.py::compose_stop: single-choice nodes flow into the
    next node, so an inserted single-choice node joins the stop that begins at
    its target.
    """
    total = 0
    cur: str | None = start
    seen: set[str] = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        node = graph.nodes[cur]
        match = _FILL_RE.match(node.body)
        total += int(match.group(2)) if match else len(node.body.split())
        cur = node.choices[0].target if len(node.choices) == 1 else None
    return total


def _fit_stop(graph: _Graph, band: str, wanted: int, target: str) -> int:
    """Shrink an inserted node's ``words=`` so its flowed stop fits CG-3.

    CG-3 (strict posture only) caps the words of one rendered stop per band.
    An inserted single-choice node flows into ``target``'s stop, so it gets at
    most what that stop leaves under the ceiling, and never under
    :data:`_MIN_INSERTED_WORDS` (a payoff needs room to land; a stop that was
    already full stays a strict-only advisory rather than an unfillable beat).
    """
    ceiling = _WORDS_PER_STOP_CEILING.get(band)
    if ceiling is None:
        return wanted
    room = ceiling - _stop_words_from(graph, target)
    return max(_MIN_INSERTED_WORDS, min(wanted, room))


def _single_choice_node(node_id: str, body: str, onward: Choice) -> dict[str, object]:
    """Return an inserted node whose one choice copies ``onward``'s label and target.

    The copied label is what the next node's opening already acknowledges
    (CG-4), so the inserted beat flows into it without a seam.
    """
    return {
        "id": node_id,
        "body": body,
        "is_ending": False,
        "choices": [
            {"id": f"c_{node_id}", "label": onward.label, "target": onward.target}
        ],
    }


def _apply_payoff(
    editor: _Editor, plan: _VarPlan, payoff: _PayoffPlan, index: int
) -> PayoffPlacement:
    """Insert one payoff scene and split its choice into a same-label pair."""
    graph = editor.graph
    payoff_choice = _choice(graph, payoff.node_id, payoff.choice_id)
    onward = _choice(graph, payoff.node_id, payoff.continue_choice_id)
    # "_site2", not "_2": variable names already use "_2" to stay unique, so a
    # bare numeric suffix collided with the next variable's first scene.
    suffix = "" if index == 0 else f"_site{index + 1}"
    scene_id = f"{_ID_INFIX}_payoff_{plan.name}{suffix}"
    scene = _single_choice_node(
        scene_id,
        _directive(
            "payoff",
            _fit_stop(graph, editor.band, editor.scene_words, onward.target),
            _scene_text(plan, payoff, payoff_choice.label, onward),
        ),
        onward,
    )
    editor.insert_after(payoff.node_id, scene)
    raw_choices = _raw_choices(editor.node(payoff.node_id))
    original = editor.choice(payoff.node_id, payoff.choice_id)
    original["condition"] = _cond(plan.name, value=False)
    twin_id = f"{payoff.choice_id}_{_ID_INFIX}_{plan.name}"
    twin: dict[str, object] = {
        "id": twin_id,
        "label": payoff_choice.label,
        "target": scene_id,
        "condition": _cond(plan.name, value=True),
    }
    raw_choices.insert(raw_choices.index(original) + 1, twin)
    editor.annotate(
        payoff.node_id, _payoff_site_text(plan, payoff, payoff_choice.label)
    )
    return PayoffPlacement(
        variable=plan.name,
        node_id=payoff.node_id,
        kind=payoff.kind,
        choice_id=payoff.choice_id,
        gated_choice_id=twin_id,
        label=payoff_choice.label,
        scene_id=scene_id,
        rejoin_id=onward.target,
        setback_ending=payoff.setback_ending,
    )


def _apply(
    skeleton: Mapping[str, object], graph: _Graph, plans: list[_VarPlan]
) -> tuple[dict[str, object], list[PlantPlacement], list[PayoffPlacement], list[str]]:
    """Write the planned variables, effects, conditions, and directives."""
    doc = copy.deepcopy(dict(skeleton))
    editor = _Editor(doc=doc, graph=graph, words=_median_words(graph.story))
    arrival_words = max(_MIN_INSERTED_WORDS, min(70, round(editor.words * 0.5)))
    scene_words = max(_MIN_INSERTED_WORDS, min(100, round(editor.words * 0.7)))
    band = graph.story.metadata.age_band.value

    plants: list[PlantPlacement] = []
    payoffs: list[PayoffPlacement] = []
    variables: list[dict[str, object]] = []
    fork_entries: dict[str, list[tuple[str, str, str]]] = {}

    editor.band = band
    editor.scene_words = scene_words
    for plan in plans:
        fork_choice = _choice(graph, plan.fork_id, plan.choice_id)
        sites = " and ".join(p.node_id for p in plan.payoffs)
        variables.append(
            {
                "name": plan.name,
                "type": "bool",
                "initial": False,
                # Variable descriptions are not a slotted surface, so a
                # {SLOT} token copied from a parameterized label would survive
                # rendering and fail its residual-token post-condition.
                "description": (
                    f"Set when the reader chooses {_q(_plain(fork_choice.label))} "
                    f"at {plan.fork_id}; pays off at {sites}."
                ),
            }
        )
        # --- plant -------------------------------------------------------
        raw_fork_choice = editor.choice(plan.fork_id, plan.choice_id)
        raw_fork_choice["effects"] = [{"op": "set", "var": plan.name, "value": True}]
        target = fork_choice.target
        sole_entry = not _needs_arrival(graph, plan.fork_id, fork_choice)
        plant_text = _plant_text(plan, graph)
        if sole_entry and editor.annotate(target, plant_text):
            site, inserted = target, False
        else:
            site = f"{_ID_INFIX}_plant_{plan.name}"
            editor.insert_after(
                plan.fork_id,
                _single_choice_node(
                    site,
                    _directive(
                        "plant",
                        _fit_stop(graph, band, arrival_words, target),
                        (
                            "Arrival beat for this choice, two or three sentences "
                            "that show it happening and then lead straight into "
                            f"the next scene. {plant_text}"
                        ),
                    ),
                    fork_choice,
                ),
            )
            raw_fork_choice["target"] = site
            inserted = True
        plants.append(
            PlantPlacement(
                plan.name,
                plan.fork_id,
                plan.choice_id,
                fork_choice.label,
                site,
                inserted,
            )
        )
        fork_entries.setdefault(plan.fork_id, []).append(
            (fork_choice.label, plan.name, sites)
        )
        # --- payoffs -----------------------------------------------------
        payoffs.extend(
            _apply_payoff(editor, plan, payoff, index)
            for index, payoff in enumerate(plan.payoffs)
        )

    for fork_id, entries in fork_entries.items():
        editor.annotate(fork_id, _fork_text(entries))
    doc["variables"] = variables
    meta = cast("dict[str, object]", doc["metadata"])
    meta["tier"] = 2
    return doc, plants, payoffs, editor.notes


# ---------------------------------------------------------------------------
# Walk-based post-processing and verification
# ---------------------------------------------------------------------------


def _states_by_node(walk: WalkResult) -> dict[str, dict[str, set[object]]]:
    seen: dict[str, dict[str, set[object]]] = {}
    for key in walk.configs:
        per_var = seen.setdefault(key[0], {})
        for name, value in key[1]:
            per_var.setdefault(name, set()).add(value)
    return seen


def _endings_from(
    walk: WalkResult, starts: Iterable[ConfigKey], ending_ids: set[str]
) -> set[str]:
    found: set[str] = set()
    seen: set[ConfigKey] = set(starts)
    queue: deque[ConfigKey] = deque(seen)
    while queue:
        key = queue.popleft()
        if key[0] in ending_ids:
            found.add(key[0])
        for nxt in walk.edges.get(key, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return found


def _changes_endings(
    walk: WalkResult,
    at_node: list[ConfigKey],
    payoff: PayoffPlacement,
    ending_ids: set[str],
) -> bool:
    """Whether this payoff takes its setback ending off the planter's table.

    Credited only to a rescue, and only for the ending its ungated twin runs
    into: that ending must be reachable from the payoff node without the plant
    and unreachable with it. Comparing whole ending sets instead would credit a
    plain payoff scene with a difference that a correlated variable caused (two
    plants on one fork are mutually exclusive).

    Args:
        walk: The completed configuration walk.
        at_node: Every configuration at the payoff node.
        payoff: The payoff under test.
        ending_ids: All ending node ids.

    Returns:
        Whether the setback ending is reachable only without the plant.
    """
    if payoff.setback_ending is None:
        return False
    with_plant = [k for k in at_node if _var_value(k, payoff.variable) is True]
    without = [k for k in at_node if _var_value(k, payoff.variable) is False]
    return payoff.setback_ending in _endings_from(
        walk, without, ending_ids
    ) and payoff.setback_ending not in _endings_from(walk, with_plant, ending_ids)


def _var_value(key: ConfigKey, name: str) -> object:
    return dict(key[1]).get(name)


def _annotate_merges(
    doc: dict[str, object],
    walk: WalkResult,
    plants: list[PlantPlacement],
) -> tuple[int, list[str]]:
    """Append the state-neutral merge note to every merge directive."""
    story = Storybook.model_validate(doc)
    graph = _Graph(story)
    states = _states_by_node(walk)
    by_var = {p.variable: p for p in plants}
    editor = _Editor(doc=doc, graph=graph, words=0)
    count = 0
    for node_id in graph.merges():
        differing = [
            _q(by_var[name].label)
            for name, values in sorted(states.get(node_id, {}).items())
            if len(values) > 1 and name in by_var
        ]
        if editor.annotate(node_id, _merge_text(differing)):
            count += 1
    return count, editor.notes


def _gate_summary(doc: Mapping[str, object]) -> tuple[bool, int, dict[str, int]]:
    result = run_gate(doc)
    errors = 0
    warnings: dict[str, int] = {}
    for finding in result.report.findings:
        if finding.severity is Severity.ERROR:
            errors += 1
        else:
            warnings[finding.rule_id] = warnings.get(finding.rule_id, 0) + 1
    return result.blocked, errors, warnings


def measure_state(doc: Mapping[str, object]) -> StateMetrics:
    """Measure the numbers the pilot table reports for one document.

    Args:
        doc: A skeleton or filled story document.

    Returns:
        The structural, consequence, walk, and gate numbers.
    """
    story = Storybook.model_validate(doc)
    graph = _Graph(story)
    report = measure_consequence(story)
    walk = walk_configurations(story)
    blocked, errors, warnings = _gate_summary(doc)
    return StateMetrics(
        nodes=len(story.nodes),
        merges=len(graph.merges()),
        variables=len(story.variables),
        conditional_choices=sum(
            1 for n in story.nodes for c in n.choices if c.condition is not None
        ),
        forks=len(report.forks),
        false_forks=sum(1 for f in report.forks if f.is_false_choice),
        walk_configs=len(walk.configs),
        walk_capped=walk.capped,
        gate_blocked=blocked,
        gate_errors=errors,
        gate_warnings=warnings,
    )


def _verify(
    doc: dict[str, object],
    walk: WalkResult,
    payoffs: list[PayoffPlacement],
) -> tuple[str | None, tuple[str, ...], str | None]:
    """Return a refusal reason, the ending-changing variables, and a culprit.

    The culprit is a payoff node id a re-plan should exclude, or ``None``.
    """
    story = Storybook.model_validate(doc)
    for node in story.nodes:
        if any(c.condition is not None for c in node.choices) and not any(
            c.condition is None for c in node.choices
        ):
            return f"node {node.id} would have no unconditional choice", (), node.id
    if walk.capped:
        return "the configuration walk hit its cap", (), None
    ending_ids = {n.id for n in story.nodes if n.is_ending}
    changing: list[str] = []
    for payoff in payoffs:
        at_node = [k for k in walk.configs if k[0] == payoff.node_id]
        with_plant = [k for k in at_node if _var_value(k, payoff.variable) is True]
        without = [k for k in at_node if _var_value(k, payoff.variable) is False]
        if not with_plant or not without:
            return (
                (
                    f"payoff node {payoff.node_id} is not reached in both states of "
                    f"{payoff.variable}"
                ),
                (),
                payoff.node_id,
            )
        if _changes_endings(walk, at_node, payoff, ending_ids):
            changing.append(payoff.variable)
    if not changing:
        return (
            (
                "no payoff changes which endings a reader can still reach (every "
                "rescued setback ending is also reachable another way)"
            ),
            (),
            next((p.node_id for p in payoffs if p.kind == "rescue"), None),
        )
    if _EM_DASH in repr(doc):
        return "an em-dash reached the candidate", (), None
    return None, tuple(changing), None


def _setback_hints(
    doc: dict[str, object],
    walk: WalkResult,
    payoffs: list[PayoffPlacement],
    plants: list[PlantPlacement],
) -> list[str]:
    """Hint at the missing plant on setback endings only non-planters reach."""
    story = Storybook.model_validate(doc)
    editor = _Editor(doc=doc, graph=_Graph(story), words=0)
    labels = {p.variable: p.label for p in plants}
    for payoff in payoffs:
        ending = payoff.setback_ending
        if ending is None:
            continue
        values = {
            _var_value(k, payoff.variable) for k in walk.configs if k[0] == ending
        }
        if values == {False}:
            editor.annotate(
                ending, _setback_hint_text(payoff.variable, labels[payoff.variable])
            )
    return editor.notes


# ---------------------------------------------------------------------------
# Inverse: the stateless reading of a promoted skeleton
# ---------------------------------------------------------------------------

# The directive markers this module appends. None occurs in any committed
# skeleton's own beats (checked 2026-11-20 with git grep), so the first marker
# in a beats string is where the original text ended.
_MARKERS: tuple[str, ...] = (
    "PLANT SITE:",
    "PLANT (",
    "PAYOFF SITE (",
    "PAYOFF (",
    "MERGE:",
    "SETBACK HINT (",
)


def _strip_beats(body: str) -> str:
    match = _FILL_RE.match(body)
    if match is None:
        return body
    beats = match.group(3)
    cut = min((i for m in _MARKERS if (i := beats.find(m)) >= 0), default=-1)
    if cut < 0:
        return body
    head = beats[:cut]
    head = head.removesuffix("; ").removesuffix(" ")
    return f"<<FILL role={match.group(1)} words={match.group(2)} beats='{head}'>>"


def _is_promoted(doc: Mapping[str, object]) -> list[str]:
    """Return this module's variable names when ``doc`` is its output, else []."""
    raw_vars = doc.get("variables")
    raw_nodes = doc.get("nodes")
    if (
        not isinstance(raw_vars, list)
        or not raw_vars
        or not isinstance(raw_nodes, list)
    ):
        return []
    names = [
        cast("dict[str, object]", v).get("name")
        for v in cast("list[object]", raw_vars)
        if isinstance(v, dict)
    ]
    ids = {
        cast("dict[str, object]", n).get("id")
        for n in cast("list[object]", raw_nodes)
        if isinstance(n, dict)
    }
    if not all(isinstance(n, str) and f"{_ID_INFIX}_payoff_{n}" in ids for n in names):
        return []
    return [cast("str", n) for n in names]


def stateless_view(doc: Mapping[str, object]) -> dict[str, object]:
    """Return the Tier-1 reading of a skeleton :func:`promote_skeleton` produced.

    The exact structural inverse: variables, plant effects, gated twins, the
    inserted arrival and payoff nodes, the ``== false`` conditions, and every
    appended directive note are removed, and ``metadata.tier`` returns to 1. A
    document this module did not produce (a hand-authored Tier-2 skeleton, or a
    Tier-1 one) is returned as an unchanged deep copy.

    Two callers need it. The WS-5 M3 graft is state-free by design, so a
    promoted donor would otherwise offer only the small subtrees that hold no
    plant or payoff; grafting from this view instead keeps the flywheel's donor
    pool intact. And it is the round-trip check that the tool only ADDS: for
    every skeleton it promotes, ``stateless_view(promoted) == original`` (except
    ``estimated_minutes`` when a PL-23 resync was needed, which is noted).

    Args:
        doc: A skeleton document.

    Returns:
        dict[str, object]: A fresh document.
    """
    view = copy.deepcopy(dict(doc))
    names = set(_is_promoted(view))
    if not names:
        return view
    nodes = _raw_nodes(view)
    arrivals: dict[str, str] = {}
    scenes: set[str] = set()
    for node in nodes:
        node_id = cast("str", node.get("id"))
        if node_id.startswith(f"{_ID_INFIX}_plant_"):
            arrivals[node_id] = cast("str", _raw_choices(node)[0]["target"])
        elif node_id.startswith(f"{_ID_INFIX}_payoff_"):
            scenes.add(node_id)
    kept: list[dict[str, object]] = []
    for node in nodes:
        node_id = cast("str", node.get("id"))
        if node_id in arrivals or node_id in scenes:
            continue
        body = node.get("body")
        if isinstance(body, str):
            node["body"] = _strip_beats(body)
        if "choices" in node:
            node["choices"] = [
                c
                for c in _raw_choices(node)
                if _strip_choice(c, names, arrivals, scenes)
            ]
        kept.append(node)
    view["nodes"] = kept
    view["variables"] = []
    cast("dict[str, object]", view["metadata"])["tier"] = 1
    return view


def _strip_choice(
    choice: dict[str, object],
    names: set[str],
    arrivals: dict[str, str],
    scenes: set[str],
) -> bool:
    """Undo the tool's edits on one choice in place; return whether to keep it."""
    target = choice.get("target")
    if target in scenes:
        return False
    if isinstance(target, str) and target in arrivals:
        choice["target"] = arrivals[target]
    condition = choice.get("condition")
    if (
        isinstance(condition, dict)
        and set(referenced_names(cast("dict[str, object]", condition))) <= names
    ):
        del choice["condition"]
    effects = choice.get("effects")
    if isinstance(effects, list):
        rest: list[object] = [
            e
            for e in cast("list[object]", effects)
            if not (
                isinstance(e, dict) and cast("dict[str, object]", e).get("var") in names
            )
        ]
        if rest:
            choice["effects"] = rest
        else:
            del choice["effects"]
    return True


def referenced_names(condition: Mapping[str, object]) -> list[str]:
    """Return every ``{"var": name}`` name a JSONLogic condition mentions."""
    found: list[str] = []
    stack: list[object] = [condition]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            mapping = cast("dict[str, object]", item)
            var = mapping.get("var")
            if isinstance(var, str) and len(mapping) == 1:
                found.append(var)
            else:
                stack.extend(mapping.values())
        elif isinstance(item, list):
            stack.extend(cast("list[object]", item))
    return found


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _preconditions(
    skeleton: Mapping[str, object], story: Storybook, *, allow_mvp: bool
) -> tuple[Status, str] | None:
    meta = story.metadata
    if story.variables or meta.tier == 2:
        return (
            "skipped",
            (
                f"already stateful ({len(story.variables)} variable(s) declared); "
                "the tool never adds a second set"
            ),
        )
    band = meta.age_band.value
    has_state_ops = any(n.on_enter for n in story.nodes) or any(
        c.condition is not None or c.effects for n in story.nodes for c in n.choices
    )
    checks: list[tuple[bool, str]] = [
        (
            band not in STATE_BANDS,
            (
                f"band {band} is Tier-1 by ADR-011 section 7 (state first applies at "
                "8-11); nothing may be counted or referred back to here"
            ),
        ),
        (
            meta.series is not None,
            "series books carry state across books; hand-author it",
        ),
        (
            not meta.production_eligible and not allow_mvp,
            "not production_eligible (MVP seed)",
        ),
        (has_state_ops, "carries effects or conditions without declared variables"),
    ]
    for failed, reason in checks:
        if failed:
            return "refused", reason
    if run_gate(skeleton).blocked:
        return "refused", "the input skeleton does not pass the gate"
    return None


def promote_skeleton(
    skeleton: Mapping[str, object],
    *,
    target_variables: int | None = None,
    allow_mvp: bool = False,
    has_narrative_sidecar: bool = False,
) -> PromotionReport:
    """Give a stateless skeleton two to four plant/payoff variables.

    Args:
        skeleton: The raw skeleton document. Never mutated.
        target_variables: How many variables to aim for, clamped to
            :data:`MIN_VARIABLES`..:data:`MAX_VARIABLES`. Defaults by
            ``metadata.length`` (short 2, medium 3, long 4).
        allow_mvp: Accept a non-production seed.
        has_narrative_sidecar: Whether a ``.narrative.json`` sidecar exists; its
            per-node entry states would need hand updating, so it is refused.

    Returns:
        PromotionReport: ``promoted`` with a verified candidate, or ``refused``
        / ``skipped`` with the reason.
    """
    story_id = str(skeleton.get("id", "?"))
    # A v2 shape (WP-2.2) gets its state from its plan's threads, never from
    # this tool (D4 item 3), and every plant/payoff edit below writes v1 beats.
    # #VERIFY: test_fill_directive_v2.py::test_state_promotion_refuses_a_v2_shape.
    if has_v2_directives(skeleton):
        return PromotionReport(
            story_id,
            "refused",
            "a v2 shape takes its state from its Story Plan's threads (D4)",
        )
    try:
        story = Storybook.model_validate(skeleton)
    except PydanticValidationError as exc:
        return PromotionReport(
            story_id, "refused", f"does not parse: {exc.errors()[0]['msg']}"
        )
    blocked = _preconditions(skeleton, story, allow_mvp=allow_mvp)
    if blocked is not None:
        return PromotionReport(story_id, blocked[0], blocked[1])
    if has_narrative_sidecar:
        return PromotionReport(
            story_id,
            "refused",
            (
                "a .narrative.json sidecar declares per-node entry states that "
                "new nodes and conditions would invalidate; update it by hand"
            ),
        )

    length = story.metadata.length.value if story.metadata.length else "medium"
    target = target_variables or _VARIABLES_BY_LENGTH.get(length, 3)
    target = max(MIN_VARIABLES, min(MAX_VARIABLES, target))

    meta = story.metadata
    placement = ScalePlacement(
        length=meta.length.value if meta.length is not None else None,
        narrative_style=meta.narrative_style.value,
        production_eligible=meta.production_eligible,
    )
    budget = resolve_node_budget(meta.age_band.value, placement, scale="standard")
    graph = _Graph(story, depth_budget=budget[2] if budget is not None else None)
    before = _gate_summary(skeleton)

    excluded: set[str] = set()
    last_reason = ""
    for _attempt in range(_MAX_ATTEMPTS):
        outcome = _attempt_once(
            _AttemptContext(skeleton, graph, target, before), frozenset(excluded)
        )
        if isinstance(outcome, PromotionReport):
            return outcome
        last_reason, culprit = outcome
        if culprit is None or culprit in excluded:
            break
        excluded.add(culprit)
    return PromotionReport(story_id, "refused", last_reason)


@dataclass(frozen=True, slots=True)
class _AttemptContext:
    skeleton: Mapping[str, object]
    graph: _Graph
    target: int
    before: tuple[bool, int, dict[str, int]]


def _plan_problem(graph: _Graph, planner: _Planner) -> str | None:
    """Return why a plan cannot be applied, or ``None``."""
    if len(planner.plans) < MIN_VARIABLES:
        if not graph.merges():
            detail = (
                "the graph is a pure tree (no node has two inbound routes), so "
                "no plant can be paid off on a route the non-planter also walks; "
                "it needs a hand-authored bottleneck first"
            )
        else:
            detail = "; ".join(planner.diagnostics[:3]) or "no candidates"
        return (
            f"found {len(planner.plans)} plant/payoff pair(s), need "
            f"{MIN_VARIABLES}: {detail}"
        )
    if not any(o.kind == "rescue" for p in planner.plans for o in p.payoffs):
        return _no_rescue_reason(graph)
    return None


def _candidate_problem(doc: dict[str, object], graph: _Graph) -> str | None:
    """Return why an applied candidate is unusable before any walk, or ``None``."""
    meta = graph.story.metadata
    cell = (
        production_cell_budget(
            meta.age_band.value, meta.length.value, meta.narrative_style.value
        )
        if meta.length is not None
        else None
    )
    node_total = len(_raw_nodes(doc))
    if cell is not None and node_total > cell[1]:
        return f"{node_total} nodes after insertion exceeds the cell max {cell[1]}"
    try:
        Storybook.model_validate(doc)
    except PydanticValidationError as exc:
        return f"candidate does not parse: {exc.errors()[0]['msg']}"
    return None


def _attempt_once(
    ctx: _AttemptContext, excluded: frozenset[str]
) -> PromotionReport | tuple[str, str | None]:
    """Plan, apply, and verify once.

    Args:
        ctx: The skeleton, its graph view, the variable budget, and the
            pre-promotion gate summary.
        excluded: Payoff node ids earlier attempts ruled out.

    Returns:
        A final report (promoted, or a refusal no re-plan can fix), or a
        ``(reason, culprit)`` pair where ``culprit`` is a payoff node id the
        next attempt should exclude (``None`` when nothing can be retried).
    """
    graph = ctx.graph
    planner = _plan(graph, ctx.target, excluded)
    problem = _plan_problem(graph, planner)
    if problem is not None:
        return (problem, None)
    doc, plants, payoffs, notes = _apply(ctx.skeleton, graph, planner.plans)
    problem = _candidate_problem(doc, graph)
    if problem is not None:
        return (problem, None)
    walk = walk_configurations(Storybook.model_validate(doc))
    merges_annotated, merge_notes = _annotate_merges(doc, walk, plants)
    notes.extend(merge_notes)
    notes.extend(_setback_hints(doc, walk, payoffs, plants))
    reason, changing, culprit = _verify(doc, walk, payoffs)
    if reason is not None:
        return (f"verification: {reason}", culprit)
    after = _gate_summary(doc)
    if "PL-23" in after[2] and "PL-23" not in ctx.before[2]:
        meta_raw = cast("dict[str, object]", doc["metadata"])
        derived = recompute_estimated_minutes(doc)
        msg = (
            f"estimated_minutes {meta_raw.get('estimated_minutes')} -> "
            f"{derived} (PL-23 fired after insertion)"
        )
        notes.append(msg)
        meta_raw["estimated_minutes"] = derived
        after = _gate_summary(doc)
    if after[0]:
        return _gate_refusal(doc, graph, planner.plans)
    return PromotionReport(
        story_id=graph.story.id,
        status="promoted",
        candidate=doc,
        plants=tuple(plants),
        payoffs=tuple(payoffs),
        ending_changing=changing,
        merges_annotated=merges_annotated,
        notes=tuple(notes),
    )


def _no_rescue_reason(graph: _Graph) -> str:
    wide = sum(
        1
        for node in graph.story.nodes
        if len(node.choices) >= _MAX_DECLARED_CHOICES
        and any(graph.setback_corridor(c.target) for c in node.choices)
    )
    tail = ""
    if wide:
        tail = (
            f" ({wide} setback site(s) exist only on "
            f"{_MAX_DECLARED_CHOICES}-option nodes, where a twin choice would "
            "pass the option ceiling)"
        )
    return (
        "no payoff site downstream of a plant has a choice that runs into a "
        "setback ending beside a continuation, so no payoff could change which "
        f"ending is reachable without inserting a new ending{tail}"
    )


def _gate_refusal(
    doc: dict[str, object], graph: _Graph, plans: list[_VarPlan]
) -> PromotionReport | tuple[str, str | None]:
    """Explain a gate block, and name a payoff to drop when one is to blame."""
    errors = [f for f in run_gate(doc).report.findings if f.severity is Severity.ERROR]
    depth_overrun = any(
        f.rule_id == "L1-7" and "branch_depth" in f.message for f in errors
    )
    summary = "; ".join(
        f"{f.rule_id}{' at ' + f.node_id if f.node_id else ''}: {f.message[:160]}"
        for f in errors[:2]
    )
    if depth_overrun and plans:
        sites = [o.node_id for p in plans for o in p.payoffs]
        deepest = max(sites, key=lambda n: (graph.depth.get(n, 0), n))
        return (f"verification: the gate blocks the candidate: {summary}", deepest)
    touched = {o.node_id for p in plans for o in p.payoffs}
    touched |= {p.fork_id for p in plans}
    latent = [
        f
        for f in errors
        if f.rule_id.startswith("L2") and f.node_id and f.node_id not in touched
    ]
    if latent and len(latent) == len(errors):
        return (
            (
                "promotion exposes a latent Layer-2 defect the Tier-1 shell was never "
                f"walked for ({len(errors)} error(s)): {summary}. Fix the shell first"
            ),
            None,
        )
    return (
        (
            f"verification: the gate blocks the candidate ({len(errors)} error(s)): "
            f"{summary}"
        ),
        None,
    )
