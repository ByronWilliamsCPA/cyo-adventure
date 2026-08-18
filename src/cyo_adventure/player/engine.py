"""Deterministic story player engine (Story Runtime Semantics v1).

This is the reference implementation of the canonical execution model in
``docs/planning/runtime-semantics.md``. It is pure: no I/O, no async, no shared
mutable state. The Layer-2 validator walk (Phase 2) and the TypeScript player
must reproduce its behaviour exactly, and the cross-implementation conformance
fixtures exist to prove they do.

Transition order on every choice (section 1):

1. Evaluate the choice condition against the current ``var_state``.
2. Apply the choice effects.
3. Set ``current_node`` to the choice target.
4. Apply the target node's ``on_enter`` effects (``once: true`` first-entry only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.storybook.evaluator import evaluate

if TYPE_CHECKING:
    from cyo_adventure.storybook.evaluator import VarState
    from cyo_adventure.storybook.models import Choice, Effect, Node, Storybook

from cyo_adventure.player.state import ReadingState


class StoryEngine:
    """Plays a single parsed :class:`Storybook` deterministically."""

    def __init__(self, story: Storybook) -> None:
        """Index a story for traversal.

        Args:
            story: The parsed, schema-valid Storybook to play.
        """
        self._story = story
        self._nodes: dict[str, Node] = {node.id: node for node in story.nodes}
        self._bounds: dict[str, tuple[int | None, int | None]] = {
            var.name: (var.min, var.max)
            for var in story.variables
            if var.type.value == "int"
        }

    def start(self) -> ReadingState:
        """Begin a new read at ``start_node`` with initial variable values.

        Entering the start node applies its ``on_enter`` effects (first entry).

        Returns:
            ReadingState: The initial reading state pinned to the story version.
        """
        return self.start_continuation(None)

    def start_continuation(
        self, carried: VarState | None, entry_node: str | None = None
    ) -> ReadingState:
        """Begin a read at ``entry_node``, seeding name-matched carried variables.

        Mirrors the client's ``startContinuation``
        (``frontend/src/player/engine.ts``) exactly, including the order of
        operations: carried values are merged into the declared initials
        **before** the entry node's ``on_enter`` effects run. Seeding afterwards
        would let a carried value overwrite an effect the entry node applied,
        which the client does not do, and player/validator divergence here is a
        conformance failure under runtime-semantics.md section 1.

        The entry-node parameter closes a real divergence rather than adding a
        feature (`UW-C296`). The client has taken an ``entryNode`` since WS-G and
        ``reader/ContinueSeries.tsx`` passes the receiving book's
        ``series_entry_node``; this method did not, so SR-9 validated a reader
        path that begins at ``start_node`` while the reader begins somewhere
        else. A comment here previously justified that by asserting the two are
        equal for every book, which is false on committed content: both
        brass-lantern books declare ``start_node: n_open`` against
        ``series_entry_node: n_start``.

        Fallback matches the client exactly: an entry node of ``None``, or one no
        node in the story carries, starts at ``start_node``.

        Carry rules (WS-G G3, identical to the client): a carried value is used
        only when its name matches a declared variable and its type matches;
        a wrong-typed value is skipped so the declared initial stands; a carried
        int is clamped into the receiving variable's declared bounds.

        Args:
            carried: Carried variable values from a predecessor book, or
                ``None`` for an ordinary read.
            entry_node: The node id to begin at, or ``None`` for ``start_node``.
                An id absent from the story falls back to ``start_node``.

        Returns:
            ReadingState: The initial reading state pinned to the story version.
        """
        var_state: VarState = {var.name: var.initial for var in self._story.variables}
        if carried:
            for var in self._story.variables:
                value = carried.get(var.name)
                if value is None:
                    continue
                if var.type.value == "bool" and isinstance(value, bool):
                    var_state[var.name] = value
                elif (
                    var.type.value == "int"
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                ):
                    var_state[var.name] = self._clamp(var.name, value)
        # #CRITICAL: data integrity: the node entered here must be the node the
        # reader enters, or every state-seeded rule validates a path nobody
        # walks. The existence guard mirrors the client's
        # `story.nodes.some(n => n.id === entryNode)` rather than trusting the
        # declaration, so a stale or misspelled entry node degrades to the start
        # node on both sides instead of diverging.
        # #VERIFY: test_series.py::test_sr9_walks_the_declared_series_entry_node
        # pins that a non-start entry changes SR-9's carried reachability, and
        # test_player_conformance.py covers the client parity.
        node_id = (
            entry_node
            if entry_node is not None
            and any(node.id == entry_node for node in self._story.nodes)
            else self._story.start_node
        )
        state = ReadingState(
            current_node=node_id,
            var_state=var_state,
            path=[node_id],
            visit_set=set(),
            version=self._story.version,
        )
        self._enter_node(state, node_id, first_entry=True)
        return state

    def visible_choices(self, state: ReadingState) -> list[Choice]:
        """Return the choices visible at the current node for this state.

        A choice with a condition that evaluates to false is hidden (section 4).

        Args:
            state: The current reading state.

        Returns:
            list[Choice]: The choices the reader may select right now.
        """
        node = self._node(state.current_node)
        return [c for c in node.choices if self._is_visible(c, state.var_state)]

    def is_ending(self, state: ReadingState) -> bool:
        """Report whether the current node is an ending.

        Args:
            state: The current reading state.

        Returns:
            bool: ``True`` if the current node is an ending node.
        """
        return self._node(state.current_node).is_ending

    def current_ending_id(self, state: ReadingState) -> str | None:
        """Return the stable ending id of the current node, if it is an ending.

        Args:
            state: The current reading state.

        Returns:
            str | None: The ``ending.id`` or ``None`` if not at an ending.
        """
        node = self._node(state.current_node)
        return node.ending.id if node.is_ending and node.ending is not None else None

    def choose(self, state: ReadingState, choice_id: str) -> ReadingState:
        """Apply a choice and return the resulting reading state.

        The returned state is a fresh object; the input ``state`` is not mutated,
        so a caller may keep the prior state (for example, for a save slot).

        Args:
            state: The current reading state.
            choice_id: The id of the choice to select.

        Returns:
            ReadingState: The state after the transition.

        Raises:
            BusinessLogicError: If the current node is an ending, the choice id
                is unknown at the current node, or the choice is not visible.
        """
        if self.is_ending(state):
            msg = f"cannot choose from ending node '{state.current_node}'"
            raise BusinessLogicError(msg)
        node = self._node(state.current_node)
        choice = next((c for c in node.choices if c.id == choice_id), None)
        if choice is None:
            msg = f"choice '{choice_id}' does not exist on node '{node.id}'"
            raise BusinessLogicError(msg)
        if not self._is_visible(choice, state.var_state):
            msg = f"choice '{choice_id}' is not visible in the current state"
            raise BusinessLogicError(msg)
        # Transition order (runtime-semantics section 1): the input state is
        # snapshotted so the engine stays pure and replays are deterministic.
        nxt = self._clone(state)
        for effect in choice.effects:
            self._apply_effect(nxt.var_state, effect)
        target = choice.target
        nxt.current_node = target
        first_entry = target not in nxt.visit_set
        self._enter_node(nxt, target, first_entry=first_entry)
        nxt.path.append(target)
        return nxt

    def _enter_node(
        self, state: ReadingState, node_id: str, *, first_entry: bool
    ) -> None:
        """Mark a node visited and apply its ``on_enter`` effects.

        A ``once: true`` effect applies only on the first entry to the node
        (runtime-semantics section 2).

        Args:
            state: The state to mutate in place.
            node_id: The node being entered.
            first_entry: Whether this is the first time the node is entered.
        """
        state.visit_set.add(node_id)
        node = self._node(node_id)
        for effect in node.on_enter:
            if effect.once and not first_entry:
                continue
            self._apply_effect(state.var_state, effect)

    def _apply_effect(self, var_state: VarState, effect: Effect) -> None:
        """Apply a single effect to a variable state, honoring int bounds.

        Args:
            var_state: The variable state to mutate in place.
            effect: The effect to apply.
        """
        op = effect.op.value
        if op == "set":
            value = effect.value if effect.value is not None else 0
            # A set to a bounded int variable is clamped like inc/dec so a story
            # cannot seed an out-of-range value that conditions later compare
            # against (runtime-semantics section 3); non-int values pass through.
            if isinstance(value, int) and not isinstance(value, bool):
                value = self._clamp(effect.var, value)
            var_state[effect.var] = value
            return
        current = var_state.get(effect.var, 0)
        delta = effect.value if isinstance(effect.value, int) else 0
        # #ASSUME: data integrity: schema guarantees `current` is int for inc/dec
        # targets (L1-6); clamping is a defensive fallback only (semantics 3).
        # #VERIFY: validator rejects bound-exceeding transitions before publish.
        base = current if isinstance(current, int) else 0
        updated = base + delta if op == "inc" else base - delta
        var_state[effect.var] = self._clamp(effect.var, updated)

    def _clamp(self, var_name: str, value: int) -> int:
        """Clamp a value to the variable's declared bounds, if any.

        Args:
            var_name: The variable being updated.
            value: The proposed new value.

        Returns:
            int: The value bounded by the declared ``min``/``max``.
        """
        low, high = self._bounds.get(var_name, (None, None))
        if low is not None and value < low:
            return low
        if high is not None and value > high:
            return high
        return value

    def _is_visible(self, choice: Choice, var_state: VarState) -> bool:
        """Return whether a choice is visible under the current variable state.

        Args:
            choice: The choice to test.
            var_state: The current variable state.

        Returns:
            bool: ``True`` if the choice has no condition or it evaluates true.
        """
        if choice.condition is None:
            return True
        return evaluate(choice.condition, var_state)

    def _node(self, node_id: str) -> Node:
        """Look up a node by id.

        Args:
            node_id: The node id to resolve.

        Returns:
            Node: The node.

        Raises:
            BusinessLogicError: If the node id is not in the story.
        """
        node = self._nodes.get(node_id)
        if node is None:
            msg = f"node '{node_id}' does not exist in story '{self._story.id}'"
            raise BusinessLogicError(msg)
        return node

    @staticmethod
    def _clone(state: ReadingState) -> ReadingState:
        """Return a deep-ish copy of a reading state for a pure transition.

        Args:
            state: The state to copy.

        Returns:
            ReadingState: A copy whose mutable containers are independent.
        """
        return ReadingState(
            current_node=state.current_node,
            var_state=dict(state.var_state),
            path=list(state.path),
            visit_set=set(state.visit_set),
            version=state.version,
            state_revision=state.state_revision,
            # Copy each snapshot, not just the dict, so a cloned timeline cannot
            # mutate a save slot shared with the original (purity guarantee).
            save_slots={name: snap.copy() for name, snap in state.save_slots.items()},
        )
