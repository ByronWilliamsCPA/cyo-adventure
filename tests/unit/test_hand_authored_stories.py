"""Acceptance tests for the two hand-authored Phase 1 stories.

Each story must load against the schema, pass the Layer-1 validator, and be
playable to each of its endings through the deterministic engine. This is the
Phase 1 deliverable "two hand-authored stories: one Tier 1, one Tier 2".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.player import StoryEngine
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator import validate_layer1

_VALID = Path(__file__).resolve().parents[1] / "fixtures" / "storybook" / "valid"
_TIER1 = _VALID / "06_tier1_tide_pools.json"
_TIER2 = _VALID / "07_tier2_clockwork_garden.json"


def _load(path: Path) -> dict[str, object]:
    """Load a story fixture as a mapping."""
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.parametrize("path", [_TIER1, _TIER2], ids=lambda p: p.name)
def test_hand_authored_story_passes_layer1(path: Path) -> None:
    """Both hand-authored stories parse and pass the Layer-1 gate."""
    data = _load(path)
    Storybook.model_validate(data)  # schema-valid
    report = validate_layer1(data)
    assert report.ok, [f.message for f in report.errors]


# (story path, choice ids to play, expected ending id)
_PLAYTHROUGHS = [
    (_TIER1, ["c_pools", "c_rock", "c_cave", "c_open_box"], "e_treasure"),
    (_TIER1, ["c_pools", "c_rock", "c_shell", "c_keep_pearl"], "e_pearl"),
    (_TIER1, ["c_gull", "c_echo", "c_seal", "c_follow_seal"], "e_safe"),
    (_TIER2, ["c_shed", "c_toolbox", "c_take_key", "c_unlock", "c_wind"], "e_clock"),
    (_TIER2, ["c_shed", "c_toolbox", "c_take_key", "c_wait"], "e_garden"),
    (_TIER2, ["c_hedge", "c_squeeze", "c_to_fountain2", "c_dive"], "e_treasure2"),
    (_TIER2, ["c_hedge", "c_path", "c_to_fountain3", "c_coin"], "e_wish"),
    (_TIER2, ["c_hedge", "c_squeeze", "c_to_gate2", "c_climb", "c_wind"], "e_clock"),
]


@pytest.mark.unit
@pytest.mark.parametrize(("path", "choices", "ending_id"), _PLAYTHROUGHS)
def test_hand_authored_story_reaches_ending(
    path: Path, choices: list[str], ending_id: str
) -> None:
    """Each scripted playthrough reaches its expected ending."""
    story = Storybook.model_validate(_load(path))
    engine = StoryEngine(story)
    state = engine.start()
    for choice_id in choices:
        visible = {c.id for c in engine.visible_choices(state)}
        assert choice_id in visible, (
            f"{choice_id} not visible at {state.current_node}: {sorted(visible)}"
        )
        state = engine.choose(state, choice_id)
    assert engine.is_ending(state)
    assert engine.current_ending_id(state) == ending_id


@pytest.mark.unit
def test_tier2_dark_choice_hidden_without_courage() -> None:
    """The courage-gated dive is hidden until courage is high enough."""
    story = Storybook.model_validate(_load(_TIER2))
    engine = StoryEngine(story)
    state = engine.start()
    # Low-courage route to the fountain: the brave dive must not be offered.
    for choice_id in ["c_hedge", "c_path", "c_to_fountain3"]:
        state = engine.choose(state, choice_id)
    visible = {c.id for c in engine.visible_choices(state)}
    assert "c_dive" not in visible
    assert "c_coin" in visible
