"""Tests for the Layer-2 state-space validator (layer2.py).

TDD order: all tests are written before the implementation.

Coverage:
1. Tier-1 short-circuit: returns an empty report immediately.
2. Clean Tier-2 passes: fixture files produce no findings.
3. L2-9 dead-end: a reachable non-ending config with zero visible choices.
4. L2-10 escape: a reachable config that cannot reach any ending.
5. L2-11 dead branch: a conditional choice that is never visible.
6. L2-12 cap: walk hits the cap ceiling, returns exactly one cap finding.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.layer2 import validate_layer2

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_VALID = Path(__file__).parent.parent / "fixtures" / "storybook" / "valid"
_INVALID_GRAPH = (
    Path(__file__).parent.parent / "fixtures" / "storybook" / "invalid" / "graph"
)


def _load_fixture(path: Path) -> Storybook:
    """Load and parse a Storybook from a JSON fixture file."""
    return Storybook.model_validate(json.loads(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Story builder helpers (mirror test_config_walk.py conventions)
# ---------------------------------------------------------------------------


def _tier1_story(
    nodes: list[dict[str, object]],
    start: str,
    story_id: str = "s_tier1",
    ending_count: int = 1,
) -> Storybook:
    """Build a minimal Tier-1 Storybook."""
    data: dict[str, object] = {
        "schema_version": "1.0",
        "id": story_id,
        "version": 1,
        "title": "Tier-1 Test",
        "metadata": {
            "age_band": "10-13",
            "reading_level": {"scheme": "flesch_kincaid", "target": 5.0},
            "tier": 1,
            "themes": ["test"],
            "estimated_minutes": 5,
            "ending_count": ending_count,
        },
        "variables": [],
        "start_node": start,
        "nodes": nodes,
    }
    return Storybook.model_validate(data)


def _tier2_story(
    nodes: list[dict[str, object]],
    start: str,
    variables: list[dict[str, object]],
    story_id: str = "s_tier2",
    ending_count: int = 1,
) -> Storybook:
    """Build a minimal Tier-2 Storybook."""
    data: dict[str, object] = {
        "schema_version": "1.0",
        "id": story_id,
        "version": 1,
        "title": "Tier-2 Test",
        "metadata": {
            "age_band": "10-13",
            "reading_level": {"scheme": "flesch_kincaid", "target": 5.0},
            "tier": 2,
            "themes": ["test"],
            "estimated_minutes": 5,
            "ending_count": ending_count,
        },
        "variables": variables,
        "start_node": start,
        "nodes": nodes,
    }
    return Storybook.model_validate(data)


# ---------------------------------------------------------------------------
# Test 1: Tier-1 short-circuit
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tier1_story_returns_empty_report() -> None:
    """Layer 2 must return an empty report immediately for Tier-1 stories."""
    story = _tier1_story(
        nodes=[
            {
                "id": "start",
                "body": "Begin.",
                "is_ending": False,
                "choices": [{"id": "c1", "label": "Go", "target": "end"}],
            },
            {
                "id": "end",
                "body": "Done.",
                "is_ending": True,
                "ending": {"id": "e1", "type": "happy", "title": "The End"},
                "choices": [],
            },
        ],
        start="start",
    )
    report = validate_layer2(story)
    assert report.ok is True
    assert report.findings == []


@pytest.mark.unit
def test_tier1_story_produces_no_rule_ids() -> None:
    """Tier-1 short-circuit must produce a report with no rule ids at all."""
    story = _tier1_story(
        nodes=[
            {
                "id": "n",
                "body": "Node.",
                "is_ending": False,
                "choices": [{"id": "cx", "label": "Go", "target": "e"}],
            },
            {
                "id": "e",
                "body": "End.",
                "is_ending": True,
                "ending": {"id": "ee", "type": "happy", "title": "Done"},
                "choices": [],
            },
        ],
        start="n",
    )
    report = validate_layer2(story)
    assert report.rule_ids() == set()


# ---------------------------------------------------------------------------
# Test 2: Clean Tier-2 fixtures pass
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "filename",
    [
        "03_tier2_lantern.json",
        "04_tier2_courage_gate.json",
        "05_tier2_bottleneck.json",
        "07_tier2_clockwork_garden.json",
    ],
)
def test_valid_tier2_fixture_passes_layer2(filename: str) -> None:
    """Every valid Tier-2 fixture must produce no error-severity findings."""
    story = _load_fixture(_VALID / filename)
    report = validate_layer2(story)
    assert report.ok is True, [f.message for f in report.errors]


# ---------------------------------------------------------------------------
# Test 3: L2-9 stateful dead-end
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_l2_9_dead_end_is_detected() -> None:
    """A node reachable with a variable state where no choice is visible -> L2-9."""
    # n_silver_door is reachable with has_silver_key=false, and its only choice
    # requires has_silver_key==true. The player is stuck: not an ending, zero
    # visible choices.
    story = _load_fixture(_INVALID_GRAPH / "stateful_dead_end.json")
    report = validate_layer2(story)
    assert not report.ok
    assert "L2-9" in report.rule_ids()


@pytest.mark.unit
def test_l2_9_finding_attributes_correct_node() -> None:
    """The L2-9 finding must attribute to the dead-end node id."""
    story = _load_fixture(_INVALID_GRAPH / "stateful_dead_end.json")
    report = validate_layer2(story)
    l2_9_findings = [f for f in report.findings if f.rule_id == "L2-9"]
    assert l2_9_findings, "expected at least one L2-9 finding"
    node_ids = {f.node_id for f in l2_9_findings}
    assert "n_silver_door" in node_ids


@pytest.mark.unit
def test_l2_9_dead_end_synthetic() -> None:
    """Synthetic Tier-2 story with a guaranteed dead-end config produces L2-9."""
    # flag starts false; the only choice at the gate node requires flag==true
    # but no path ever sets flag to true. So (gate, {flag: false}) is a dead-end.
    story = _tier2_story(
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [{"id": "c_go", "label": "Go", "target": "gate"}],
            },
            {
                "id": "gate",
                "body": "Gate.",
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_open",
                        "label": "Open.",
                        "target": "end",
                        "condition": {"==": [{"var": "flag"}, True]},
                    }
                ],
            },
            {
                "id": "end",
                "body": "End.",
                "is_ending": True,
                "ending": {"id": "e_end", "type": "happy", "title": "Done"},
                "choices": [],
            },
        ],
        start="start",
        variables=[{"name": "flag", "type": "bool", "initial": False}],
        ending_count=1,
    )
    report = validate_layer2(story)
    assert not report.ok
    assert "L2-9" in report.rule_ids()
    dead_nodes = {f.node_id for f in report.findings if f.rule_id == "L2-9"}
    assert "gate" in dead_nodes


# ---------------------------------------------------------------------------
# Test 4: L2-10 stateful termination / loop escape
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_l2_10_escape_detected_in_unreachable_ending_config() -> None:
    """A config that can only cycle with no path to an ending produces L2-10."""
    # Two nodes form a cycle (loop_a -> loop_b -> loop_a) with a conditional
    # exit that can never be satisfied (requires flag==true, nothing sets it).
    # The ending is never reachable from the cyclic configurations.
    story = _tier2_story(
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [{"id": "c_enter", "label": "Enter", "target": "loop_a"}],
            },
            {
                "id": "loop_a",
                "body": "Loop A.",
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_to_end",
                        "label": "Exit (never visible).",
                        "target": "end",
                        "condition": {"==": [{"var": "flag"}, True]},
                    },
                    {"id": "c_to_b", "label": "Go B.", "target": "loop_b"},
                ],
            },
            {
                "id": "loop_b",
                "body": "Loop B.",
                "is_ending": False,
                "choices": [
                    {"id": "c_to_a", "label": "Go A.", "target": "loop_a"},
                ],
            },
            {
                "id": "end",
                "body": "End.",
                "is_ending": True,
                "ending": {"id": "e1", "type": "happy", "title": "Done"},
                "choices": [],
            },
        ],
        start="start",
        variables=[{"name": "flag", "type": "bool", "initial": False}],
        ending_count=1,
    )
    report = validate_layer2(story)
    # The cyclic configs cannot reach the ending -> L2-10
    assert "L2-10" in report.rule_ids()
    # L2-9 should also appear for loop_b because it has no exit path when flag is
    # false (loop_a has an unconditional choice to loop_b, so loop_b always has
    # the return-to-a choice, meaning loop_b is NOT a dead-end). Actually let us
    # just check L2-10 is present and attributed correctly.
    escape_nodes = {f.node_id for f in report.findings if f.rule_id == "L2-10"}
    # loop_a and loop_b configs cannot reach ending
    assert escape_nodes & {"loop_a", "loop_b"}


@pytest.mark.unit
def test_l2_10_finding_not_emitted_for_ending_configs() -> None:
    """L2-10 must NOT fire for ending configs (they are their own terminus)."""
    # A simple linear story: every reachable config has a path to the ending.
    story = _tier2_story(
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [{"id": "c1", "label": "Go", "target": "end"}],
            },
            {
                "id": "end",
                "body": "End.",
                "is_ending": True,
                "ending": {"id": "e1", "type": "happy", "title": "Done"},
                "choices": [],
            },
        ],
        start="start",
        variables=[{"name": "flag", "type": "bool", "initial": False}],
        ending_count=1,
    )
    report = validate_layer2(story)
    assert report.ok is True
    assert "L2-10" not in report.rule_ids()


# ---------------------------------------------------------------------------
# Test 5: L2-11 conditional dead branch
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_l2_11_dead_branch_detected() -> None:
    """A conditional choice whose condition is unsatisfiable in all reachable configs -> L2-11."""
    # choice c_secret requires flag==true; flag starts false and nothing sets it.
    # The choice is never visible in any reachable config.
    story = _tier2_story(
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [
                    {"id": "c_safe", "label": "Safe path.", "target": "end"},
                    {
                        "id": "c_secret",
                        "label": "Secret path (never visible).",
                        "target": "end",
                        "condition": {"==": [{"var": "flag"}, True]},
                    },
                ],
            },
            {
                "id": "end",
                "body": "End.",
                "is_ending": True,
                "ending": {"id": "e1", "type": "happy", "title": "Done"},
                "choices": [],
            },
        ],
        start="start",
        variables=[{"name": "flag", "type": "bool", "initial": False}],
        ending_count=1,
    )
    report = validate_layer2(story)
    assert not report.ok
    assert "L2-11" in report.rule_ids()
    dead_branch_findings = [f for f in report.findings if f.rule_id == "L2-11"]
    assert any(f.choice_id == "c_secret" for f in dead_branch_findings)
    assert any(f.node_id == "start" for f in dead_branch_findings)


@pytest.mark.unit
def test_l2_11_unconditional_choice_not_flagged() -> None:
    """An unconditional choice must never trigger L2-11."""
    story = _tier2_story(
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [
                    {"id": "c_go", "label": "Go.", "target": "end"},
                ],
            },
            {
                "id": "end",
                "body": "End.",
                "is_ending": True,
                "ending": {"id": "e1", "type": "happy", "title": "Done"},
                "choices": [],
            },
        ],
        start="start",
        variables=[{"name": "flag", "type": "bool", "initial": False}],
        ending_count=1,
    )
    report = validate_layer2(story)
    assert "L2-11" not in report.rule_ids()


@pytest.mark.unit
def test_l2_11_visible_conditional_not_flagged() -> None:
    """A conditional choice that IS visible in at least one config must not trigger L2-11."""
    # The condition can be satisfied because flag starts True.
    story = _tier2_story(
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_special",
                        "label": "Special (visible when flag).",
                        "target": "end",
                        "condition": {"==": [{"var": "flag"}, True]},
                    },
                    {"id": "c_safe", "label": "Safe.", "target": "end"},
                ],
            },
            {
                "id": "end",
                "body": "End.",
                "is_ending": True,
                "ending": {"id": "e1", "type": "happy", "title": "Done"},
                "choices": [],
            },
        ],
        start="start",
        variables=[{"name": "flag", "type": "bool", "initial": True}],
        ending_count=1,
    )
    report = validate_layer2(story)
    assert "L2-11" not in report.rule_ids()


# ---------------------------------------------------------------------------
# Test 6: L2-12 cap
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_l2_12_cap_returns_exactly_one_finding() -> None:
    """When the walk caps, exactly one L2-12 finding is returned with no other L2 findings."""
    # A branching Tier-2 story with enough variable combinations to trigger a
    # small cap. Two independent bool variables produce 4 possible var states;
    # the start node alone triggers at least 1 config. Using cap=1 forces a cap
    # immediately on the second config.
    story = _tier2_story(
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_a",
                        "label": "Path A.",
                        "target": "end_a",
                        "effects": [{"op": "set", "var": "flag_a", "value": True}],
                    },
                    {
                        "id": "c_b",
                        "label": "Path B.",
                        "target": "end_b",
                        "effects": [{"op": "set", "var": "flag_b", "value": True}],
                    },
                ],
            },
            {
                "id": "end_a",
                "body": "End A.",
                "is_ending": True,
                "ending": {"id": "e_a", "type": "happy", "title": "A Done"},
                "choices": [],
            },
            {
                "id": "end_b",
                "body": "End B.",
                "is_ending": True,
                "ending": {"id": "e_b", "type": "happy", "title": "B Done"},
                "choices": [],
            },
        ],
        start="start",
        variables=[
            {"name": "flag_a", "type": "bool", "initial": False},
            {"name": "flag_b", "type": "bool", "initial": False},
        ],
        ending_count=2,
    )
    # cap=1 means only the start config can be recorded; taking any choice would
    # try to add a second config, triggering the cap.
    report = validate_layer2(story, cap=1)
    l2_12_findings = [f for f in report.findings if f.rule_id == "L2-12"]
    assert len(l2_12_findings) == 1, f"expected 1 L2-12 finding, got {report.findings}"
    # No other L2 findings should appear when capped
    other_l2 = [f for f in report.findings if f.rule_id != "L2-12"]
    assert other_l2 == [], f"unexpected findings after cap: {other_l2}"


@pytest.mark.unit
def test_l2_12_finding_contains_story_id_and_cap() -> None:
    """The L2-12 message must reference the story id and cap value."""
    story = _tier2_story(
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [
                    {"id": "c1", "label": "Go.", "target": "mid"},
                ],
            },
            {
                "id": "mid",
                "body": "Mid.",
                "is_ending": False,
                "choices": [{"id": "c2", "label": "End.", "target": "end"}],
            },
            {
                "id": "end",
                "body": "End.",
                "is_ending": True,
                "ending": {"id": "e1", "type": "happy", "title": "Done"},
                "choices": [],
            },
        ],
        start="start",
        variables=[{"name": "flag", "type": "bool", "initial": False}],
        story_id="s_cap_test",
        ending_count=1,
    )
    # cap=1 to force capping
    report = validate_layer2(story, cap=1)
    l2_12 = next((f for f in report.findings if f.rule_id == "L2-12"), None)
    assert l2_12 is not None
    assert "s_cap_test" in l2_12.message
    assert "1" in l2_12.message  # cap value in message


@pytest.mark.unit
def test_l2_12_not_triggered_when_walk_completes() -> None:
    """When the walk completes without hitting the cap, L2-12 must not appear."""
    story = _load_fixture(_VALID / "03_tier2_lantern.json")
    report = validate_layer2(story, cap=100_000)
    assert "L2-12" not in report.rule_ids()


# ---------------------------------------------------------------------------
# Test 7: Message format spot-checks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_l2_9_message_format() -> None:
    """The L2-9 message must follow the exact template."""
    story = _load_fixture(_INVALID_GRAPH / "stateful_dead_end.json")
    report = validate_layer2(story)
    l2_9 = next(f for f in report.findings if f.rule_id == "L2-9")
    # Template: "L2-9 dead: node '{node_id}' with var_state {var_state} is a
    # stateful dead end (no visible choices, not an ending) in story '{story_id}'"
    assert l2_9.message.startswith("L2-9 dead:")
    assert "s_stateful_dead_end" in l2_9.message
    assert "n_silver_door" in l2_9.message


@pytest.mark.unit
def test_l2_11_message_format() -> None:
    """The L2-11 message must follow the exact template."""
    story = _tier2_story(
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [
                    {"id": "c_open", "label": "Open.", "target": "end"},
                    {
                        "id": "c_hidden",
                        "label": "Hidden.",
                        "target": "end",
                        "condition": {"==": [{"var": "flag"}, True]},
                    },
                ],
            },
            {
                "id": "end",
                "body": "End.",
                "is_ending": True,
                "ending": {"id": "e1", "type": "happy", "title": "Done"},
                "choices": [],
            },
        ],
        start="start",
        variables=[{"name": "flag", "type": "bool", "initial": False}],
        story_id="s_msg_test",
        ending_count=1,
    )
    report = validate_layer2(story)
    l2_11 = next(f for f in report.findings if f.rule_id == "L2-11")
    assert l2_11.message.startswith("L2-11 dead-branch:")
    assert "c_hidden" in l2_11.message
    assert "start" in l2_11.message
    assert "s_msg_test" in l2_11.message
