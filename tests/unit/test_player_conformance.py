"""Cross-implementation player conformance (Python side).

Runs the shared player-trace corpus at ``schema/conformance/player_traces.json``
through the Python :class:`StoryEngine`. The TypeScript engine runs the same
corpus (``frontend/src/player/engine.test.ts``); both must reach an identical
state for every trace, which guarantees the player behaves the same in the test
harness and the browser.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cyo_adventure.player import StoryEngine
from cyo_adventure.storybook.models import Storybook

_TRACES = (
    Path(__file__).resolve().parents[2]
    / "schema"
    / "conformance"
    / "player_traces.json"
)


def _load_traces() -> list[dict[str, Any]]:
    """Load the shared player-trace corpus."""
    data = json.loads(_TRACES.read_text(encoding="utf-8"))
    return list(data["traces"])


@pytest.mark.unit
@pytest.mark.parametrize("trace", _load_traces(), ids=lambda t: str(t["name"]))
def test_player_trace_reaches_expected_state(trace: dict[str, Any]) -> None:
    """Replaying a trace's choices reaches the pinned expected state."""
    story = Storybook.model_validate(trace["story"])
    engine = StoryEngine(story)
    state = engine.start()
    for choice_id in trace["choices"]:
        state = engine.choose(state, choice_id)
    expected = trace["expected"]
    assert state.current_node == expected["current_node"]
    assert state.var_state == expected["var_state"]
    assert sorted(state.visit_set) == sorted(expected["visit_set"])
    assert engine.current_ending_id(state) == expected["ending_id"]
