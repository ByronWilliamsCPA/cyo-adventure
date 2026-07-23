"""Tests for the deterministic player engine (Story Runtime Semantics v1).

The lantern fixture exercises state-gated choices and endings (US-102); synthetic
stories cover the transition order, ``once: true`` first-entry semantics, bound
clamping, purity, and deterministic replay.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.player import StoryEngine
from cyo_adventure.storybook.models import Storybook

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "storybook" / "valid"
_LANTERN = _FIXTURES / "03_tier2_lantern.json"


def _lantern() -> Storybook:
    """Load the Tier-2 lantern story."""
    return Storybook.model_validate(json.loads(_LANTERN.read_text(encoding="utf-8")))


def _meta(tier: int = 2, ending_count: int = 1) -> dict[str, object]:
    """Build a minimal valid metadata block."""
    return {
        "age_band": "10-13",
        "reading_level": {"scheme": "flesch_kincaid", "target": 4.0, "tolerance": 1.0},
        "tier": tier,
        "themes": [],
        "estimated_minutes": 5,
        "ending_count": ending_count,
        "topology": "branch_and_bottleneck",
        "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
    }


def _build(
    nodes: list[dict[str, object]],
    variables: list[dict[str, object]],
    *,
    start: str,
    ending_count: int = 1,
) -> Storybook:
    """Assemble and validate a synthetic Tier-2 story."""
    return Storybook.model_validate(
        {
            "schema_version": "2.0",
            "id": "s_syn",
            "version": 1,
            "title": "Synthetic",
            "metadata": _meta(ending_count=ending_count),
            "variables": variables,
            "start_node": start,
            "nodes": nodes,
        }
    )


def _end(nid: str = "n_end", eid: str = "e_end") -> dict[str, object]:
    """Build an ending node."""
    return {
        "id": nid,
        "body": "Done.",
        "is_ending": True,
        "ending": {
            "id": eid,
            "valence": "positive",
            "kind": "success",
            "title": "End",
        },
        "choices": [],
    }


# --- Lantern fixture: state-gated choices and endings --------------------------


@pytest.mark.unit
def test_start_initializes_state() -> None:
    """A fresh read starts at start_node with initial variables and visit set."""
    engine = StoryEngine(_lantern())
    state = engine.start()
    assert state.current_node == "n_entrance"
    assert state.var_state == {"has_lantern": False}
    assert state.path == ["n_entrance"]
    assert state.visit_set == {"n_entrance"}
    assert state.version == 1


@pytest.mark.unit
def test_take_lantern_unlocks_dark_passage_to_treasure() -> None:
    """Taking the lantern makes the dark passage visible and leads to treasure."""
    engine = StoryEngine(_lantern())
    state = engine.start()
    state = engine.choose(state, "c_take_lantern")
    assert state.var_state["has_lantern"] is True
    visible = {c.id for c in engine.visible_choices(state)}
    assert visible == {"c_dark_passage", "c_bright_tunnel"}
    state = engine.choose(state, "c_dark_passage")
    assert engine.is_ending(state)
    assert engine.current_ending_id(state) == "e_treasure_found"


@pytest.mark.unit
def test_ignore_lantern_hides_dark_passage() -> None:
    """Without the lantern, the conditional dark-passage choice is hidden."""
    engine = StoryEngine(_lantern())
    state = engine.start()
    state = engine.choose(state, "c_ignore_lantern")
    assert state.var_state["has_lantern"] is False
    visible = {c.id for c in engine.visible_choices(state)}
    assert visible == {"c_bright_tunnel"}
    state = engine.choose(state, "c_bright_tunnel")
    assert engine.current_ending_id(state) == "e_safe_exit"


@pytest.mark.unit
def test_choose_hidden_choice_raises() -> None:
    """Selecting a hidden (false-condition) choice is rejected."""
    engine = StoryEngine(_lantern())
    state = engine.choose(engine.start(), "c_ignore_lantern")
    with pytest.raises(BusinessLogicError, match="not visible"):
        engine.choose(state, "c_dark_passage")


@pytest.mark.unit
def test_choose_unknown_choice_raises() -> None:
    """Selecting a non-existent choice id is rejected."""
    engine = StoryEngine(_lantern())
    with pytest.raises(BusinessLogicError, match="does not exist"):
        engine.choose(engine.start(), "c_nope")


@pytest.mark.unit
def test_choose_from_ending_raises() -> None:
    """No choice may be made from an ending node."""
    engine = StoryEngine(_lantern())
    state = engine.choose(engine.start(), "c_ignore_lantern")
    state = engine.choose(state, "c_bright_tunnel")
    with pytest.raises(BusinessLogicError, match="ending node"):
        engine.choose(state, "c_anything")


@pytest.mark.unit
def test_choose_does_not_mutate_input_state() -> None:
    """choose returns a new state and leaves the prior state intact (purity)."""
    engine = StoryEngine(_lantern())
    start = engine.start()
    _ = engine.choose(start, "c_take_lantern")
    assert start.current_node == "n_entrance"
    assert start.var_state == {"has_lantern": False}


@pytest.mark.unit
def test_deterministic_replay_reproduces_state() -> None:
    """Replaying the same choices from a fresh start yields identical state."""
    engine = StoryEngine(_lantern())

    def play() -> dict[str, object]:
        state = engine.start()
        state = engine.choose(state, "c_take_lantern")
        state = engine.choose(state, "c_dark_passage")
        return state.to_dict()

    # Bound to names rather than compared inline so pytest can report which
    # playthrough diverged; inline, the two independent calls read as a
    # tautology to static analysis (SonarCloud python:S5863).
    first_playthrough = play()
    second_playthrough = play()
    assert first_playthrough == second_playthrough


# --- Synthetic stories: once, bounds, transition order -------------------------


@pytest.mark.unit
def test_once_effect_applies_only_on_first_entry() -> None:
    """A once:true on_enter effect does not re-apply when the node is re-entered."""
    room = {
        "id": "n_room",
        "body": "A room.",
        "is_ending": False,
        "on_enter": [{"op": "inc", "var": "n", "value": 1, "once": True}],
        "choices": [
            {"id": "c_again", "label": "Stay", "target": "n_room"},
            {"id": "c_leave", "label": "Leave", "target": "n_end"},
        ],
    }
    story = _build(
        [room, _end()],
        [{"name": "n", "type": "int", "initial": 0, "min": 0, "max": 5}],
        start="n_room",
    )
    engine = StoryEngine(story)
    state = engine.start()  # first entry to n_room
    assert state.var_state["n"] == 1
    state = engine.choose(state, "c_again")  # re-enter n_room
    assert state.var_state["n"] == 1


@pytest.mark.unit
def test_non_once_effect_applies_every_entry() -> None:
    """A plain on_enter effect re-applies on every entry."""
    room = {
        "id": "n_room",
        "body": "A room.",
        "is_ending": False,
        "on_enter": [{"op": "inc", "var": "n", "value": 1}],
        "choices": [
            {"id": "c_again", "label": "Stay", "target": "n_room"},
            {"id": "c_leave", "label": "Leave", "target": "n_end"},
        ],
    }
    story = _build(
        [room, _end()],
        [{"name": "n", "type": "int", "initial": 0, "min": 0, "max": 5}],
        start="n_room",
    )
    engine = StoryEngine(story)
    state = engine.start()
    assert state.var_state["n"] == 1
    state = engine.choose(state, "c_again")
    assert state.var_state["n"] == 2


@pytest.mark.unit
def test_inc_clamps_at_declared_max() -> None:
    """An inc effect clamps at the variable's declared max (defensive fallback)."""
    room = {
        "id": "n_room",
        "body": "A room.",
        "is_ending": False,
        "on_enter": [{"op": "inc", "var": "n", "value": 1}],
        "choices": [
            {"id": "c_again", "label": "Stay", "target": "n_room"},
            {"id": "c_leave", "label": "Leave", "target": "n_end"},
        ],
    }
    story = _build(
        [room, _end()],
        [{"name": "n", "type": "int", "initial": 0, "min": 0, "max": 1}],
        start="n_room",
    )
    engine = StoryEngine(story)
    state = engine.start()  # n = 1
    state = engine.choose(state, "c_again")  # would be 2, clamps to 1
    assert state.var_state["n"] == 1


@pytest.mark.unit
def test_choice_effect_then_on_enter_order() -> None:
    """Choice effects apply before the target's on_enter effects (section 1)."""
    start = {
        "id": "n_start",
        "body": "Start.",
        "is_ending": False,
        "choices": [
            {
                "id": "c_go",
                "label": "Go",
                "target": "n_mid",
                "effects": [{"op": "set", "var": "step", "value": 1}],
            }
        ],
    }
    mid = {
        "id": "n_mid",
        "body": "Middle.",
        "is_ending": False,
        "on_enter": [{"op": "inc", "var": "step", "value": 10}],
        "choices": [{"id": "c_end", "label": "End", "target": "n_end"}],
    }
    story = _build(
        [start, mid, _end()],
        [{"name": "step", "type": "int", "initial": 0, "min": 0, "max": 99}],
        start="n_start",
    )
    engine = StoryEngine(story)
    state = engine.choose(engine.start(), "c_go")
    # choice set step=1, then on_enter added 10 -> 11
    assert state.var_state["step"] == 11
    assert state.current_node == "n_mid"
    assert state.path == ["n_start", "n_mid"]


@pytest.mark.unit
def test_start_node_on_enter_applies() -> None:
    """Entering the start node applies its on_enter effects."""
    start = {
        "id": "n_start",
        "body": "Start.",
        "is_ending": False,
        "on_enter": [{"op": "set", "var": "flag", "value": True}],
        "choices": [{"id": "c_end", "label": "End", "target": "n_end"}],
    }
    story = _build(
        [start, _end()],
        [{"name": "flag", "type": "bool", "initial": False}],
        start="n_start",
    )
    engine = StoryEngine(story)
    state = engine.start()
    assert state.var_state["flag"] is True


@pytest.mark.unit
def test_dec_clamps_at_declared_min() -> None:
    """A dec effect clamps at the variable's declared min."""
    room = {
        "id": "n_room",
        "body": "A room.",
        "is_ending": False,
        "on_enter": [{"op": "dec", "var": "n", "value": 5}],
        "choices": [{"id": "c_leave", "label": "Leave", "target": "n_end"}],
    }
    story = _build(
        [room, _end()],
        [{"name": "n", "type": "int", "initial": 2, "min": 0, "max": 5}],
        start="n_room",
    )
    state = StoryEngine(story).start()  # 2 - 5 = -3, clamps to 0
    assert state.var_state["n"] == 0


@pytest.mark.unit
def test_inc_lands_exactly_on_max_unclamped_then_one_past_stays_clamped() -> None:
    """An inc landing exactly on the declared max passes through unchanged; the
    next inc one past it stays clamped at max (RAD #VERIFY in ``_clamp``).

    ``test_inc_clamps_at_declared_max`` only exercises a value that overshoots
    the bound; it cannot distinguish a correct ``value > high`` clamp from an
    off-by-one ``value >= high`` clamp that would wrongly pull the boundary
    value itself down. This test observes the exact-boundary value first (via
    a separate node entry, since var_state is only inspectable between
    entries), then a second, one-past increment on a later entry.
    """
    node_a = {
        "id": "n_a",
        "body": "A.",
        "is_ending": False,
        "on_enter": [{"op": "inc", "var": "n", "value": 3}],
        "choices": [{"id": "c_go", "label": "Go", "target": "n_b"}],
    }
    node_b = {
        "id": "n_b",
        "body": "B.",
        "is_ending": False,
        "on_enter": [{"op": "inc", "var": "n", "value": 1}],
        "choices": [{"id": "c_end", "label": "End", "target": "n_end"}],
    }
    story = _build(
        [node_a, node_b, _end()],
        [{"name": "n", "type": "int", "initial": 0, "min": 0, "max": 3}],
        start="n_a",
    )
    engine = StoryEngine(story)
    state = engine.start()  # 0 + 3 = 3: exactly at max, must pass through unclamped
    assert state.var_state["n"] == 3
    state = engine.choose(state, "c_go")  # 3 + 1 = 4: one past max, clamps to 3
    assert state.var_state["n"] == 3


@pytest.mark.unit
def test_dec_lands_exactly_on_min_unclamped_then_one_past_stays_clamped() -> None:
    """A dec landing exactly on the declared min passes through unchanged; the
    next dec one past it stays clamped at min (RAD #VERIFY in ``_clamp``).

    Mirrors ``test_inc_lands_exactly_on_max_unclamped_then_one_past_stays_clamped``
    for the lower bound, so an off-by-one ``value <= low`` clamp (which would
    wrongly pull the boundary value itself up) is pinned too.
    """
    node_a = {
        "id": "n_a",
        "body": "A.",
        "is_ending": False,
        "on_enter": [{"op": "dec", "var": "n", "value": 3}],
        "choices": [{"id": "c_go", "label": "Go", "target": "n_b"}],
    }
    node_b = {
        "id": "n_b",
        "body": "B.",
        "is_ending": False,
        "on_enter": [{"op": "dec", "var": "n", "value": 1}],
        "choices": [{"id": "c_end", "label": "End", "target": "n_end"}],
    }
    story = _build(
        [node_a, node_b, _end()],
        [{"name": "n", "type": "int", "initial": 3, "min": 0, "max": 3}],
        start="n_a",
    )
    engine = StoryEngine(story)
    state = engine.start()  # 3 - 3 = 0: exactly at min, must pass through unclamped
    assert state.var_state["n"] == 0
    state = engine.choose(state, "c_go")  # 0 - 1 = -1: one past min, clamps to 0
    assert state.var_state["n"] == 0


@pytest.mark.unit
def test_choose_to_missing_target_raises() -> None:
    """A choice that targets a non-existent node fails at entry time."""
    start = {
        "id": "n_start",
        "body": "Start.",
        "is_ending": False,
        "choices": [{"id": "c_void", "label": "Go", "target": "n_ghost"}],
    }
    story = _build([start, _end()], [], start="n_start", ending_count=1)
    engine = StoryEngine(story)
    with pytest.raises(BusinessLogicError, match="does not exist"):
        engine.choose(engine.start(), "c_void")


@pytest.mark.unit
def test_snapshot_serializes_visit_set_as_sorted_list() -> None:
    """A snapshot serializes its visit set as a sorted list."""
    engine = StoryEngine(_lantern())
    snap = engine.choose(engine.start(), "c_take_lantern").snapshot()
    payload = snap.to_dict()
    assert payload["visit_set"] == ["n_cave_fork", "n_entrance"]
    assert payload["current_node"] == "n_cave_fork"


@pytest.mark.unit
def test_save_slot_snapshot_is_independent() -> None:
    """A snapshot stored in a save slot is not affected by later progress."""
    engine = StoryEngine(_lantern())
    state = engine.start()
    state.save_slots["slot1"] = state.snapshot()
    advanced = engine.choose(state, "c_take_lantern")
    assert advanced.save_slots["slot1"].current_node == "n_entrance"
    assert advanced.save_slots["slot1"].var_state == {"has_lantern": False}
