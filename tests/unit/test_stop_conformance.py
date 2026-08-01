"""Cross-implementation rendered-stop conformance (Python side, ADR-026).

Runs the shared stop-trace corpus at ``schema/conformance/stop_traces.json``
through :func:`cyo_adventure.player.stops.compose_stop`. The TypeScript side
runs the same corpus (``frontend/src/player/stops.test.ts``); both must
compose an identical :class:`~cyo_adventure.player.stops.Stop` for every case.

``back_check`` cases additionally cover go-back-by-stop, but that mechanism
is frontend-only (mirrors ``back()``/``canGoBack()`` in
``frontend/src/player/engine.ts``, which have no Python-side counterpart), so
this file only verifies the two composed stops independently rather than
exercising an actual rewind; see ``stops.ts::backOneStop`` for the rewind
itself and ``stops.test.ts`` for its conformance check.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cyo_adventure.player import StoryEngine
from cyo_adventure.player.stops import Stop, compose_stop
from cyo_adventure.storybook.models import Storybook

_TRACES = (
    Path(__file__).resolve().parents[2] / "schema" / "conformance" / "stop_traces.json"
)


def _load_cases() -> list[dict[str, Any]]:
    """Load the shared stop-trace corpus."""
    data = json.loads(_TRACES.read_text(encoding="utf-8"))
    return list(data["cases"])


def _compose(story: Storybook, engine: StoryEngine, prefix_choices: list[str]) -> Stop:
    """Reach a stop's origin via ``prefix_choices`` from a fresh read, then
    compose the stop starting there."""
    state = engine.start()
    for choice_id in prefix_choices:
        state = engine.choose(state, choice_id)
    return compose_stop(story, engine, state)


def _assert_matches(
    story: Storybook, engine: StoryEngine, stop: Stop, expected: dict[str, Any]
) -> None:
    """Assert a composed ``Stop`` matches a corpus case's ``expected`` block."""
    assert stop.origin_node == expected["origin_node"]
    assert stop.node_ids == expected["node_ids"]
    assert stop.terminal_reason == expected["terminal_reason"]
    assert stop.state.current_node == expected["current_node"]
    assert stop.state.var_state == expected["var_state"]
    assert sorted(stop.state.visit_set) == sorted(expected["visit_set"])
    assert engine.current_ending_id(stop.state) == expected["ending_id"]
    visible = [c.id for c in engine.visible_choices(stop.state)]
    assert visible == expected["visible_choice_ids"]


@pytest.mark.unit
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: str(c["name"]))
def test_stop_trace_composes_expected_stop(case: dict[str, Any]) -> None:
    """Composing a stop from a case's origin reaches the pinned expected Stop."""
    story = Storybook.model_validate(case["story"])
    engine = StoryEngine(story)
    stop = _compose(story, engine, case["prefix_choices"])
    _assert_matches(story, engine, stop, case["expected"])


@pytest.mark.unit
@pytest.mark.parametrize(
    "case",
    [c for c in _load_cases() if "back_check" in c],
    ids=lambda c: str(c["name"]),
)
def test_stop_trace_back_check_previous_stop_composes(case: dict[str, Any]) -> None:
    """The stop a go-back-by-stop should land on also composes as pinned.

    The actual rewind (``backOneStop``) is frontend-only; this only confirms
    the previous stop's own composition is stable, which is what
    ``stops.test.ts`` checks the rewind arrives at.
    """
    story = Storybook.model_validate(case["story"])
    engine = StoryEngine(story)
    back_check = case["back_check"]
    stop = _compose(story, engine, back_check["prefix_choices"])
    _assert_matches(story, engine, stop, back_check["expected"])


@pytest.mark.unit
def test_loop_back_case_terminates_without_hanging() -> None:
    """#CRITICAL regression guard: a single-choice cycle inside one composed
    stop must not hang ``compose_stop`` (ADR-026's loop-back-inside-a-run
    requirement). This re-asserts the corpus case directly by name so the
    guard fails loudly (and quickly) if the corpus case is ever removed.
    """
    cases = {c["name"]: c for c in _load_cases()}
    case = cases["loop_back_ends_stop"]
    story = Storybook.model_validate(case["story"])
    engine = StoryEngine(story)
    stop = _compose(story, engine, case["prefix_choices"])
    assert stop.terminal_reason == "loop"
    assert stop.node_ids == case["expected"]["node_ids"]
