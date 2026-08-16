"""Rendered-stop composition (ADR-026: rendered-stop flow of linear passages).

At bands 8-11 and up the reader flows consecutive single-choice, non-ending
nodes into one scrollable "stop" instead of stopping at every node, so every
stop a reader makes ends at a real choice (or an ending). This module is the
pure composition layer over :class:`~cyo_adventure.player.engine.StoryEngine`
that decides where one stop ends and the next begins; it introduces no new
traversal semantics of its own; every node-to-node transition inside a stop is
delegated to :meth:`StoryEngine.choose`, so a flowed run applies `on_enter`
effects, appends to `path`, and adds to `visit_set` exactly as if the reader
had tapped that single choice (ADR-026 decision 2).

This module is pure: no I/O, no async, no shared mutable state.
:func:`compose_stop` mirrors ``composeStop`` in
``frontend/src/player/stops.ts``; the shared conformance corpus at
``schema/conformance/stop_traces.json`` (run by both
``tests/unit/test_stop_conformance.py`` and
``frontend/src/player/stops.test.ts``) proves THOSE TWO stay in lock-step.

The mirror is not total, and the corpus does not claim it is. The TypeScript
side additionally exports ``flowedPrefix`` and ``composeStopWithHistory``
(UW-F38), which reconstruct a resumed stop's already-walked prefix from the
recorded ``path``. Neither has a counterpart here, and the corpus cannot reach
them: every case composes from a freshly-tapped state, never a resumed one.
That is currently harmless because :func:`compose_stop` has no production
caller on this side (only ``test_stop_conformance.py``, plus the structural
walk documented in ``validator/choice_grammar.py``), but do not read a green
corpus as cross-verification of resumed-stop behaviour.

AL-030: composing a stop walks every node in the run, so a caller (the reader)
MUST NOT call :func:`compose_stop` again on every render of an already-flowed
stop. Compose once per stop and hold on to the returned :class:`Stop` (or at
least its terminal :class:`~cyo_adventure.player.state.ReadingState`) for as
long as the reader is looking at that stop; only compose again once the reader
actually taps a choice into a new stop. This module deliberately does not
build a cache layer itself (per the ADR-026 W1.1 scope): memoization is the
caller's responsibility, this module only makes it cheap to do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.storybook.evaluator import evaluate

if TYPE_CHECKING:
    from cyo_adventure.player.engine import StoryEngine
    from cyo_adventure.player.state import ReadingState
    from cyo_adventure.storybook.models import Node, Storybook

TerminalReason = Literal["branch", "ending", "dead_end", "loop"]
"""Why a stop's composition stopped at its terminal node (ADR-026 decision 1).

* ``branch``: the terminal node offers 2+ choices (the ordinary case: a real
  decision point).
* ``ending``: the terminal node is an ending.
* ``dead_end``: the terminal node has exactly one choice and its condition
  evaluated false, so there is nothing to flow into.
  # #EDGE: data integrity: the Layer-1 validator forbids a reachable node whose
  # only choice can never be taken (an unreachable continuation), so a
  # published story should never actually produce this reason. It is handled
  # here anyway as a defensive guard, per ADR-026 decision 5's "dead-end
  # guard", rather than trusting every story that reaches the runtime to have
  # passed that gate.
  # #VERIFY: schema/conformance/stop_traces.json "condition_false_dead_end".
* ``loop``: the single true-condition choice would revisit a node already in
  this same composed stop; composition stops rather than looping forever.
"""


# frozen: this module's header calls itself pure, and a Stop is the pure
# result of that composition; a caller that rewrote terminal_reason or swapped
# state would silently desync from node_ids without the conformance corpus
# noticing (it only checks freshly composed stops). Mirrored on the
# TypeScript side by `readonly` fields on the Stop interface. Neither form
# deep-freezes node_ids/state, which is the same shallow guarantee on both
# sides rather than an asymmetry.
@dataclass(frozen=True, slots=True)
class Stop:
    """A rendered stop: one or more flowed node bodies ending in a real choice.

    Attributes:
        origin_node: The node id the stop started at (the id ``compose_stop``
            was called with). ``node_ids[0] == origin_node`` always.
        node_ids: The ordered node ids composing the stop, one per rendered
            segment, first to last. ``node_ids[-1] == state.current_node``.
        state: The reading state after flowing to the terminal node. Its
            ``path``/``visit_set``/``var_state`` already reflect every
            transition made while composing (ADR-026 decision 2).
        terminal_reason: Why composition stopped at the terminal node.

    Go-back-by-stop (ADR-026 decision 3): rewinding a stop means undoing the
    tap that started it, landing on the *previous* stop's terminal node (a
    real choice point), never mid-flow. Backtracking itself
    (``frontend/src/player/engine.ts::back``) is a frontend-only affordance
    with no Python-side counterpart (see that module's header comment), so
    there is no ``back``-equivalent here; ``len(node_ids)`` is the number of
    single-step ``back()`` calls a frontend caller needs to reach the previous
    stop's terminal node (``frontend/src/player/stops.ts::backOneStop`` does
    exactly that, by calling the existing ``back()`` repeatedly rather than
    reimplementing replay). This dataclass carries the same ``node_ids``/
    ``origin_node`` data on both sides purely so the composition itself stays
    provably identical; only the frontend acts on it for go-back.
    """

    origin_node: str
    node_ids: list[str]
    state: ReadingState
    terminal_reason: TerminalReason


def compose_stop(story: Storybook, engine: StoryEngine, state: ReadingState) -> Stop:
    """Compose the rendered stop starting at ``state.current_node``.

    Callers must pass a state whose ``current_node`` is a genuine stop origin:
    either a fresh read (``engine.start()``/``engine.start_continuation()``)
    or a state produced by an explicit tap on a visible choice
    (``engine.choose()``). ``compose_stop`` does not re-derive stop boundaries
    from history; it only walks forward.

    Args:
        story: The parsed, schema-valid Storybook being played. Used to look
            up each node's full (unfiltered) choice list; ``StoryEngine``
            keeps that index private, so this module keeps its own, mirroring
            how ``StoryEngine.__init__`` builds ``_nodes``.
        engine: The engine for this story. Every node-to-node transition is
            delegated to ``engine.choose()`` so a flowed run is indistinguishable
            from one node tapped at a time (ADR-026 decision 2).
        state: The state to start composing from. Not mutated; the returned
            ``Stop.state`` is a fresh state built by ``engine.choose()``, or
            ``state`` itself when the stop is length 1 (already at a branch,
            an ending, or a dead end).

    Note the arity difference from ``frontend/src/player/stops.ts::
    composeStop``, which takes ``(story, state)``: that is a consequence of the
    two engines' shapes, not a divergence in behaviour. ``StoryEngine`` is a
    class holding per-story state, so the instance must be passed in; the
    TypeScript engine exposes ``choose()`` as a free function this module
    imports directly. Both delegate every transition to the engine identically.

    Returns:
        Stop: The composed stop, terminating at a branch, an ending, or a
            dead-end/loop guard.

    Raises:
        BusinessLogicError: If ``state.current_node`` names a node the story
            does not contain (a stale state saved against an older version).
    """
    nodes: dict[str, Node] = {node.id: node for node in story.nodes}
    node_ids = [state.current_node]
    seen = {state.current_node}
    current = state
    while True:
        node = nodes.get(current.current_node)
        # Mirror engine.py::_node (and stops.ts's own guard): a dangling node
        # id is an error, not a silent stop, so a corrupt or STALE state fails
        # loudly and legibly. Reachable in production: a reading state saved
        # against an older story version can name a node a newer version
        # removed, and only the FIRST lookup here is unvalidated (every later
        # one comes back from engine.choose, which validates its own). A bare
        # ``nodes[...]`` raised KeyError('n_gone') with no story context,
        # against this package's "always raise from core/exceptions.py" rule.
        if node is None:
            msg = f"node '{current.current_node}' does not exist in the story"
            raise BusinessLogicError(msg)
        if node.is_ending:
            return Stop(node_ids[0], node_ids, current, "ending")
        choices = node.choices
        if len(choices) != 1:
            # 2+ choices is the ordinary branch stop. 0 choices on a
            # non-ending node cannot happen (Node._check_ending_consistency
            # requires >=1 choice on a non-ending node), but if it ever did,
            # treating it as a dead end is the safe fallback: there is
            # nothing to render but this node.
            reason: TerminalReason = "branch" if choices else "dead_end"
            return Stop(node_ids[0], node_ids, current, reason)
        choice = choices[0]
        if choice.condition is not None and not evaluate(
            choice.condition, current.var_state
        ):
            # The dead-end guard (ADR-026 decision 5): a single choice whose
            # condition is false has nothing to flow into, so the stop ends
            # here showing this node's (empty) visible choice list.
            return Stop(node_ids[0], node_ids, current, "dead_end")
        # #CRITICAL: timing: without this check, a single-choice cycle inside
        # one composed stop (node A's only choice targets B, B's only choice
        # targets A, with conditions that never resolve false) would recurse
        # forever: compose_stop would never return, hanging the read. A node
        # already visited within *this* stop is where the loop closes, so the
        # stop ends there instead of retaking the same edge.
        # #VERIFY: schema/conformance/stop_traces.json "loop_back_ends_stop";
        # tests/unit/test_stop_conformance.py and
        # frontend/src/player/stops.test.ts both run it.
        if choice.target in seen:
            return Stop(node_ids[0], node_ids, current, "loop")
        current = engine.choose(current, choice.id)
        node_ids.append(current.current_node)
        seen.add(current.current_node)
