# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Generative property tests for the player engine (StoryEngine).

The conformance corpus pins three hand-picked traces; these properties walk
randomly generated schema-valid storybooks (cycles, conditions, effects,
once-only on_enter, clamped int variables) and assert the engine's
structural invariants at every step:

- the engine is pure: choose() never mutates the input state;
- every reachable state is well-formed (known node, growing path, visit
  set containing the current node);
- int variables never leave their declared bounds, whatever effects fire;
- replaying the same choice sequence reproduces the same final state;
- ending nodes expose an ending id and refuse further choices;
- unknown and invisible choices raise BusinessLogicError.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.player.engine import StoryEngine
from cyo_adventure.storybook.models import Storybook

if TYPE_CHECKING:
    from cyo_adventure.player.state import ReadingState

_MAX_WALK_STEPS = 25
_VAR_NAMES = ("a", "b")
_ORDERING_OPS = ("==", "!=", "<", "<=", ">", ">=")


def _metadata(ending_count: int) -> dict[str, object]:
    """Build a minimal valid StoryMetadata payload."""
    return {
        "age_band": "8-11",
        "reading_level": {"target": 4.0},
        "tier": 2,
        "estimated_minutes": 5,
        "ending_count": ending_count,
        "topology": "time_cave",
    }


@st.composite
def _storybooks(draw: st.DrawFn) -> Storybook:
    """Generate a small schema-valid Storybook with cycles and conditions.

    Node n0 is always a branching start node; at least one node is an
    ending. Choice targets may point anywhere (including backwards), so
    generated stories contain cycles; the walk driver bounds its steps.
    """
    n_nodes = draw(st.integers(min_value=2, max_value=6))
    n_endings = draw(st.integers(min_value=1, max_value=max(1, n_nodes - 1)))
    node_ids = [f"n{i}" for i in range(n_nodes)]
    ending_ids = set(node_ids[n_nodes - n_endings :])

    n_vars = draw(st.integers(min_value=0, max_value=len(_VAR_NAMES)))
    var_names = _VAR_NAMES[:n_vars]
    variables = [
        {
            "name": name,
            "type": "int",
            "initial": draw(st.integers(min_value=0, max_value=5)),
            "min": 0,
            "max": 5,
        }
        for name in var_names
    ]

    def draw_condition() -> dict[str, object] | None:
        if not var_names or draw(st.booleans()):
            return None
        op = draw(st.sampled_from(_ORDERING_OPS))
        var = draw(st.sampled_from(var_names))
        literal = draw(st.integers(min_value=-1, max_value=6))
        return {op: [{"var": var}, literal]}

    def draw_effects() -> list[dict[str, object]]:
        if not var_names:
            return []
        effects: list[dict[str, object]] = []
        for _ in range(draw(st.integers(min_value=0, max_value=2))):
            op = draw(st.sampled_from(["set", "inc", "dec"]))
            # The Effect model requires non-negative inc/dec deltas; set
            # deliberately draws past the [0, 5] bounds so the engine's
            # clamping is exercised.
            value = (
                draw(st.integers(min_value=0, max_value=3))
                if op in ("inc", "dec")
                else draw(st.integers(min_value=-2, max_value=7))
            )
            effects.append(
                {
                    "op": op,
                    "var": draw(st.sampled_from(var_names)),
                    "value": value,
                    "once": draw(st.booleans()),
                }
            )
        return effects

    nodes: list[dict[str, object]] = []
    choice_counter = 0
    for node_id in node_ids:
        if node_id in ending_ids and node_id != "n0":
            nodes.append(
                {
                    "id": node_id,
                    "body": f"Ending prose for {node_id}.",
                    "is_ending": True,
                    "ending": {
                        "id": f"end-{node_id}",
                        "valence": draw(
                            st.sampled_from(["positive", "neutral", "negative"])
                        ),
                        "kind": draw(st.sampled_from(["success", "setback"])),
                        "title": f"The end at {node_id}",
                    },
                }
            )
            continue
        choices: list[dict[str, object]] = []
        for _ in range(draw(st.integers(min_value=1, max_value=3))):
            choice_counter += 1
            choices.append(
                {
                    "id": f"c{choice_counter}",
                    "label": f"Choice {choice_counter}",
                    "target": draw(st.sampled_from(node_ids)),
                    "condition": draw_condition(),
                    "effects": draw_effects(),
                }
            )
        nodes.append(
            {
                "id": node_id,
                "body": f"Prose for {node_id}.",
                "on_enter": draw_effects(),
                "choices": choices,
            }
        )

    actual_endings = sum(1 for node in nodes if node.get("is_ending"))
    return Storybook.model_validate(
        {
            "id": "prop-book",
            "version": 1,
            "title": "Property Book",
            "metadata": _metadata(actual_endings),
            "variables": variables,
            "start_node": "n0",
            "nodes": nodes,
        }
    )


def _bounds_of(book: Storybook) -> dict[str, tuple[int, int]]:
    """Extract declared (min, max) bounds for the book's int variables.

    The generator always declares int variables with min 0 and max 5, so the
    declared bounds are asserted directly rather than re-derived loosely.
    """
    return {var.name: (0, 5) for var in book.variables if var.type.value == "int"}


def _snapshot(
    state: ReadingState,
) -> tuple[str, dict[str, object], list[str], set[str]]:
    """Deep-copy the fields choose() must not mutate."""
    return (
        state.current_node,
        dict(state.var_state),
        list(state.path),
        set(state.visit_set),
    )


@pytest.mark.unit
@given(book=_storybooks(), data=st.data())
def test_random_walk_preserves_engine_invariants(
    book: Storybook, data: st.DataObject
) -> None:
    """Every step of a random walk keeps the engine's structural invariants."""
    engine = StoryEngine(book)
    node_ids = {node.id for node in book.nodes}
    state = engine.start()
    assert state.current_node == book.start_node
    chosen: list[str] = []

    for _ in range(_MAX_WALK_STEPS):
        assert state.current_node in node_ids
        assert state.current_node in state.visit_set
        assert state.path[-1] == state.current_node
        for name, (low, high) in _bounds_of(book).items():
            value = state.var_state[name]
            assert isinstance(value, int)
            assert low <= value <= high, f"{name}={value} escaped [{low}, {high}]"

        if engine.is_ending(state):
            ending_id = engine.current_ending_id(state)
            assert isinstance(ending_id, str)
            assert ending_id
            with pytest.raises(BusinessLogicError):
                engine.choose(state, "any-choice")
            break

        visible = engine.visible_choices(state)
        node = next(node for node in book.nodes if node.id == state.current_node)
        hidden = [c for c in node.choices if c not in visible]
        if hidden:
            with pytest.raises(BusinessLogicError):
                engine.choose(state, hidden[0].id)
        with pytest.raises(BusinessLogicError):
            engine.choose(state, "no-such-choice")
        if not visible:
            # A stateful dead end: forbidden by the L1 validator gate, but the
            # engine itself must simply stop offering transitions, not crash.
            break

        before = _snapshot(state)
        choice = data.draw(st.sampled_from(visible), label="choice")
        next_state = engine.choose(state, choice.id)
        assert _snapshot(state) == before, "choose() mutated its input state"
        assert next_state is not state
        assert next_state.path == [*before[2], next_state.current_node]
        assert next_state.visit_set >= before[3]
        chosen.append(choice.id)
        state = next_state

    # Replay determinism: the identical choice sequence reproduces the state.
    replayed = engine.start()
    for choice_id in chosen:
        replayed = engine.choose(replayed, choice_id)
    assert replayed.current_node == state.current_node
    assert replayed.var_state == state.var_state
    assert replayed.path == state.path
    assert replayed.visit_set == state.visit_set


@pytest.mark.unit
@given(book=_storybooks())
def test_start_is_deterministic_and_seeds_declared_variables(
    book: Storybook,
) -> None:
    """start() always yields the declared initial state, run after run."""
    engine = StoryEngine(book)
    first = engine.start()
    second = engine.start()
    assert first.current_node == book.start_node
    assert first.path == [book.start_node]
    assert set(first.var_state) == {var.name for var in book.variables}
    assert second.current_node == first.current_node
    assert second.path == first.path
