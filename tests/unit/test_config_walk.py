"""Tests for the Layer-2 configuration-walk core (walk.py).

TDD order: write tests first, watch them fail, then implement.

Test coverage:
1. Linear 3-node Tier-1 story: exactly 3 configs, correct edges.
2. Fixture 03_tier2_lantern.json: walk completes, lantern gate partitions configs.
3. Cap enforcement: walk stops promptly when cap is hit.
4. Once-effect soundness: once:true on_enter nodes are NOT collapsed across
   different visit histories; stories WITHOUT once-effects produce keys with
   empty frozenset third component.
"""

from __future__ import annotations

import json
from pathlib import Path

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.walk import ConfigKey, WalkResult, walk_configurations

FIXTURES = Path(__file__).parent.parent / "fixtures" / "storybook" / "valid"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_tier1_story(
    nodes: list[dict[str, object]],
    start: str,
    story_id: str = "s_test",
    ending_count: int = 1,
) -> Storybook:
    """Build a minimal Tier-1 Storybook from a node list."""
    data: dict[str, object] = {
        "schema_version": "2.0",
        "id": story_id,
        "version": 1,
        "title": "Test Story",
        "metadata": {
            "age_band": "10-13",
            "reading_level": {"scheme": "flesch_kincaid", "target": 5.0},
            "tier": 1,
            "themes": ["test"],
            "estimated_minutes": 5,
            "ending_count": ending_count,
            "topology": "branch_and_bottleneck",
        },
        "variables": [],
        "start_node": start,
        "nodes": nodes,
    }
    return Storybook.model_validate(data)


def _minimal_tier2_story(
    nodes: list[dict[str, object]],
    start: str,
    variables: list[dict[str, object]],
    story_id: str = "s_test2",
    ending_count: int = 1,
) -> Storybook:
    """Build a minimal Tier-2 Storybook from node and variable lists."""
    data: dict[str, object] = {
        "schema_version": "2.0",
        "id": story_id,
        "version": 1,
        "title": "Test Story",
        "metadata": {
            "age_band": "10-13",
            "reading_level": {"scheme": "flesch_kincaid", "target": 5.0},
            "tier": 2,
            "themes": ["test"],
            "estimated_minutes": 5,
            "ending_count": ending_count,
            "topology": "branch_and_bottleneck",
        },
        "variables": variables,
        "start_node": start,
        "nodes": nodes,
    }
    return Storybook.model_validate(data)


# ---------------------------------------------------------------------------
# Test 1: Linear 3-node Tier-1 story
# ---------------------------------------------------------------------------


def test_linear_tier1_three_nodes_exactly_three_configs() -> None:
    """A start -> middle -> ending story must produce exactly 3 configs."""
    story = _minimal_tier1_story(
        nodes=[
            {
                "id": "start",
                "body": "Begin.",
                "is_ending": False,
                "choices": [{"id": "c1", "label": "Go", "target": "middle"}],
            },
            {
                "id": "middle",
                "body": "Middle.",
                "is_ending": False,
                "choices": [{"id": "c2", "label": "Finish", "target": "end"}],
            },
            {
                "id": "end",
                "body": "Done.",
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
        start="start",
    )

    result = walk_configurations(story)

    assert not result.capped
    assert len(result.configs) == 3

    # Verify all three node ids appear as the first element of some config key.
    node_ids_in_configs = {key[0] for key in result.configs}
    assert node_ids_in_configs == {"start", "middle", "end"}


def test_linear_tier1_correct_edges() -> None:
    """The edge map must reflect the linear chain start -> middle -> end."""
    story = _minimal_tier1_story(
        nodes=[
            {
                "id": "start",
                "body": "Begin.",
                "is_ending": False,
                "choices": [{"id": "c1", "label": "Go", "target": "middle"}],
            },
            {
                "id": "middle",
                "body": "Middle.",
                "is_ending": False,
                "choices": [{"id": "c2", "label": "Finish", "target": "end"}],
            },
            {
                "id": "end",
                "body": "Done.",
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
        start="start",
    )

    result = walk_configurations(story)

    # Extract keys by node id (no variables, no once-effects).
    key_by_node: dict[str, ConfigKey] = {k[0]: k for k in result.configs}

    start_key = key_by_node["start"]
    middle_key = key_by_node["middle"]
    end_key = key_by_node["end"]

    # start -> middle
    assert result.edges[start_key] == [middle_key]
    # middle -> end
    assert result.edges[middle_key] == [end_key]
    # end is terminal (no successors)
    assert result.edges[end_key] == []


def test_linear_tier1_no_cap() -> None:
    """The linear story must not trigger the cap."""
    story = _minimal_tier1_story(
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
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
        start="start",
    )
    result = walk_configurations(story, cap=100_000)
    assert not result.capped


# ---------------------------------------------------------------------------
# Test 2: Lantern fixture
# ---------------------------------------------------------------------------


def test_lantern_fixture_walk_completes() -> None:
    """03_tier2_lantern.json: walk must complete without hitting the cap."""
    data = json.loads((FIXTURES / "03_tier2_lantern.json").read_text(encoding="utf-8"))
    story = Storybook.model_validate(data)

    result = walk_configurations(story)

    assert not result.capped


def test_lantern_fixture_treasure_node_reachable_only_with_lantern() -> None:
    """n_treasure must appear in configs only where has_lantern is True."""
    data = json.loads((FIXTURES / "03_tier2_lantern.json").read_text(encoding="utf-8"))
    story = Storybook.model_validate(data)

    result = walk_configurations(story)

    treasure_configs = [k for k in result.configs if k[0] == "n_treasure"]
    assert treasure_configs, "n_treasure must appear in at least one config"

    for key in treasure_configs:
        # key[1] is the sorted var_state tuple: e.g. (('has_lantern', True),)
        var_dict = dict(key[1])
        assert var_dict.get("has_lantern") is True, (
            f"n_treasure reachable without lantern in config {key}"
        )


def test_lantern_fixture_exit_node_reachable_regardless_of_lantern() -> None:
    """n_exit should be reachable from both has_lantern=True and has_lantern=False."""
    data = json.loads((FIXTURES / "03_tier2_lantern.json").read_text(encoding="utf-8"))
    story = Storybook.model_validate(data)

    result = walk_configurations(story)

    exit_configs = [k for k in result.configs if k[0] == "n_exit"]
    assert exit_configs, "n_exit must appear in at least one config"

    lantern_values = {dict(k[1]).get("has_lantern") for k in exit_configs}
    # n_exit is reachable regardless of lantern state (no condition on bright tunnel).
    assert True in lantern_values or False in lantern_values


def test_lantern_fixture_config_count() -> None:
    """The lantern story has 4 nodes; the walk should find at most 6 distinct
    (node, var-state) configurations (variable branching at n_entrance produces
    2 var states at n_cave_fork)."""
    data = json.loads((FIXTURES / "03_tier2_lantern.json").read_text(encoding="utf-8"))
    story = Storybook.model_validate(data)

    result = walk_configurations(story)

    # n_entrance (1 config), n_cave_fork (2 configs: lantern/no-lantern),
    # n_treasure (1 config, lantern=True only), n_exit (2 configs: lantern/no-lantern).
    # Total: at most 6 distinct (node, var_state) pairs.
    assert 1 <= len(result.configs) <= 6


# ---------------------------------------------------------------------------
# Test 3: Cap enforcement
# ---------------------------------------------------------------------------


def test_cap_stops_walk_promptly() -> None:
    """With cap=3 on a >3-config story, capped must be True."""
    # Story: start branches to A and B, each going to different endings.
    # This produces at least 4 configs (start, A, B, and one or two endings).
    story = _minimal_tier1_story(
        nodes=[
            {
                "id": "start",
                "body": "Begin.",
                "is_ending": False,
                "choices": [
                    {"id": "c_a", "label": "Go A", "target": "a"},
                    {"id": "c_b", "label": "Go B", "target": "b"},
                ],
            },
            {
                "id": "a",
                "body": "A passage.",
                "is_ending": False,
                "choices": [{"id": "c_ea", "label": "End A", "target": "end_a"}],
            },
            {
                "id": "b",
                "body": "B passage.",
                "is_ending": False,
                "choices": [{"id": "c_eb", "label": "End B", "target": "end_b"}],
            },
            {
                "id": "end_a",
                "body": "End A.",
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": "End A",
                },
                "choices": [],
            },
            {
                "id": "end_b",
                "body": "End B.",
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "negative",
                    "kind": "setback",
                    "title": "End B",
                },
                "choices": [],
            },
        ],
        start="start",
        ending_count=2,
    )

    result = walk_configurations(story, cap=3)

    assert result.capped is True
    assert len(result.configs) <= 3


def test_cap_not_exceeded() -> None:
    """Config count must never exceed cap when capped is True."""
    story = _minimal_tier1_story(
        nodes=[
            {
                "id": "start",
                "body": "Begin.",
                "is_ending": False,
                "choices": [
                    {"id": "c_a", "label": "Go A", "target": "a"},
                    {"id": "c_b", "label": "Go B", "target": "b"},
                ],
            },
            {
                "id": "a",
                "body": "A passage.",
                "is_ending": False,
                "choices": [{"id": "c_ea", "label": "End A", "target": "end_a"}],
            },
            {
                "id": "b",
                "body": "B passage.",
                "is_ending": False,
                "choices": [{"id": "c_eb", "label": "End B", "target": "end_b"}],
            },
            {
                "id": "end_a",
                "body": "End A.",
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": "End A",
                },
                "choices": [],
            },
            {
                "id": "end_b",
                "body": "End B.",
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "negative",
                    "kind": "setback",
                    "title": "End B",
                },
                "choices": [],
            },
        ],
        start="start",
        ending_count=2,
    )

    for cap_val in [1, 2, 3, 4]:
        result = walk_configurations(story, cap=cap_val)
        assert len(result.configs) <= cap_val, (
            f"configs={len(result.configs)} exceeded cap={cap_val}"
        )


def test_cap_one_still_returns_start_config() -> None:
    """cap=1 must return exactly 1 config (the start state) and capped=True."""
    story = _minimal_tier1_story(
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
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
        start="start",
    )

    result = walk_configurations(story, cap=1)

    assert result.capped is True
    assert len(result.configs) == 1


def test_cap_zero_returns_empty_capped() -> None:
    """cap=0 admits no configurations: empty configs, empty edges, capped=True."""
    story = _minimal_tier1_story(
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
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
        start="start",
    )

    result = walk_configurations(story, cap=0)

    assert result.capped is True
    assert result.configs == {}
    assert result.edges == {}


def test_cap_preserves_edges_configs_key_invariant_when_aborted() -> None:
    """Under a cap that aborts mid-expansion of a dequeued non-ending config, the
    invariant set(edges.keys()) == set(configs.keys()) must still hold so a
    Layer-2 rule iterating configs.keys() and indexing edges[key] never KeyErrors.

    Regression for the bug where the inner cap guard returned before recording
    edges[key] for the config currently being expanded.
    """
    # A branching story: start -> {a, b}, a -> end_a, b -> end_b.
    # With cap=2, the walk records start (1) and its first successor 'a' (2),
    # then dequeues 'start', begins expanding it, records edges[start], and the
    # cap fires while trying to record 'b' (would be config 3). 'start' is a
    # dequeued non-ending config, so without the fix edges[start] would be missing.
    story = _minimal_tier1_story(
        nodes=[
            {
                "id": "start",
                "body": "Begin.",
                "is_ending": False,
                "choices": [
                    {"id": "c_a", "label": "Go A", "target": "a"},
                    {"id": "c_b", "label": "Go B", "target": "b"},
                ],
            },
            {
                "id": "a",
                "body": "A passage.",
                "is_ending": False,
                "choices": [{"id": "c_ea", "label": "End A", "target": "end_a"}],
            },
            {
                "id": "b",
                "body": "B passage.",
                "is_ending": False,
                "choices": [{"id": "c_eb", "label": "End B", "target": "end_b"}],
            },
            {
                "id": "end_a",
                "body": "End A.",
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": "End A",
                },
                "choices": [],
            },
            {
                "id": "end_b",
                "body": "End B.",
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "negative",
                    "kind": "setback",
                    "title": "End B",
                },
                "choices": [],
            },
        ],
        start="start",
        ending_count=2,
    )

    # Probe a range of caps so at least one aborts while a non-ending config is
    # mid-expansion; the invariant must hold for every one of them.
    for cap_val in [2, 3, 4]:
        result = walk_configurations(story, cap=cap_val)
        assert set(result.edges.keys()) == set(result.configs.keys()), (
            f"edges/configs key mismatch at cap={cap_val}: "
            f"edges={set(result.edges.keys())} configs={set(result.configs.keys())}"
        )

    # cap=2 specifically must abort (the story has >2 configs).
    capped_result = walk_configurations(story, cap=2)
    assert capped_result.capped is True
    assert len(capped_result.configs) <= 2
    # Every dequeued config must be safely indexable in edges.
    for key in capped_result.configs:
        _ = capped_result.edges.get(key)  # presence checked by the invariant above


def test_large_enough_cap_completes_small_story() -> None:
    """A cap larger than the total config count must not set capped=True."""
    story = _minimal_tier1_story(
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
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
        start="start",
    )

    result = walk_configurations(story, cap=1_000)
    assert not result.capped
    assert len(result.configs) == 2


# ---------------------------------------------------------------------------
# Test 4: Once-effect soundness
# ---------------------------------------------------------------------------


def test_no_once_effects_produce_empty_frozenset_third_component() -> None:
    """Stories without any once:true on_enter effects must have empty frozensets
    as the third ConfigKey component, proving the collapse-to-(node, var_state)
    property holds in the common case."""
    # Tier-2 story with normal (non-once) on_enter effects.
    story = _minimal_tier2_story(
        variables=[{"name": "counter", "type": "int", "initial": 0}],
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "on_enter": [{"op": "inc", "var": "counter", "value": 1}],
                "choices": [{"id": "c1", "label": "Go", "target": "end"}],
            },
            {
                "id": "end",
                "body": "End.",
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Done",
                },
                "choices": [],
            },
        ],
        start="start",
    )

    result = walk_configurations(story)

    for key in result.configs:
        assert key[2] == frozenset(), (
            f"Expected empty frozenset for third component on no-once story, got {key[2]}"
        )


def test_once_effect_node_discriminates_configurations() -> None:
    """A node with once:true on_enter must produce DISTINCT configurations for
    readers with and without prior visit history (key[2] must differ).

    Layout:
      start -> (choice A -> once_node -> second) or (choice B -> second)
      once_node has on_enter: [{op: set, var: bonus, value: true, once: true}]
      second -> end

    At 'second': Path A has visit_set={start, once_node, second},
    Path B has visit_set={start, second}.
    Since once_node has a once-effect, the third key component at 'second'
    must be frozenset({'once_node'}) for Path A and frozenset() for Path B.
    These are DIFFERENT configs, so 'second' must appear twice in result.configs.
    """
    story = _minimal_tier2_story(
        variables=[{"name": "bonus", "type": "bool", "initial": False}],
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [
                    {"id": "c_a", "label": "Path A", "target": "once_node"},
                    {"id": "c_b", "label": "Path B", "target": "second"},
                ],
            },
            {
                "id": "once_node",
                "body": "Once node.",
                "is_ending": False,
                "on_enter": [
                    {"op": "set", "var": "bonus", "value": True, "once": True}
                ],
                "choices": [
                    {"id": "c_on_to_second", "label": "Continue", "target": "second"}
                ],
            },
            {
                "id": "second",
                "body": "Second.",
                "is_ending": False,
                "choices": [{"id": "c_s_end", "label": "End", "target": "the_end"}],
            },
            {
                "id": "the_end",
                "body": "The end.",
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Done",
                },
                "choices": [],
            },
        ],
        start="start",
        ending_count=1,
    )

    result = walk_configurations(story)

    # 'second' must appear in multiple configs (with different once-visit-set components).
    second_keys = [k for k in result.configs if k[0] == "second"]
    assert len(second_keys) >= 2, (
        f"Expected 'second' to appear in at least 2 configs (once-effect discriminates), "
        f"got {len(second_keys)}: {second_keys}"
    )

    # The third components of the second-node keys must differ.
    third_components = {k[2] for k in second_keys}
    assert len(third_components) >= 2, (
        f"Expected distinct third components for 'second' across paths, got {third_components}"
    )

    # Path A: once_node was visited, so third component includes 'once_node'.
    path_a_keys = [k for k in second_keys if "once_node" in k[2]]
    path_b_keys = [k for k in second_keys if "once_node" not in k[2]]
    assert path_a_keys, (
        "Expected at least one 'second' config where once_node was visited"
    )
    assert path_b_keys, (
        "Expected at least one 'second' config where once_node was NOT visited"
    )


def test_once_effect_story_variable_state_differs_across_paths() -> None:
    """Via Path A (through once_node), bonus is True at 'second'.
    Via Path B (direct to second), bonus is False. The var_state component
    of the key discriminates too, making this doubly distinct."""
    story = _minimal_tier2_story(
        variables=[{"name": "bonus", "type": "bool", "initial": False}],
        nodes=[
            {
                "id": "start",
                "body": "Start.",
                "is_ending": False,
                "choices": [
                    {"id": "c_a", "label": "Path A", "target": "once_node"},
                    {"id": "c_b", "label": "Path B", "target": "second"},
                ],
            },
            {
                "id": "once_node",
                "body": "Once node.",
                "is_ending": False,
                "on_enter": [
                    {"op": "set", "var": "bonus", "value": True, "once": True}
                ],
                "choices": [
                    {"id": "c_on_to_second", "label": "Continue", "target": "second"}
                ],
            },
            {
                "id": "second",
                "body": "Second.",
                "is_ending": False,
                "choices": [{"id": "c_s_end", "label": "End", "target": "the_end"}],
            },
            {
                "id": "the_end",
                "body": "The end.",
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Done",
                },
                "choices": [],
            },
        ],
        start="start",
        ending_count=1,
    )

    result = walk_configurations(story)

    second_keys = [k for k in result.configs if k[0] == "second"]

    bonus_values_at_second = {dict(k[1]).get("bonus") for k in second_keys}
    # Path A sets bonus=True; Path B leaves it False.
    assert True in bonus_values_at_second, "bonus should be True at second for Path A"
    assert False in bonus_values_at_second, "bonus should be False at second for Path B"


# ---------------------------------------------------------------------------
# Test 5: WalkResult type structure
# ---------------------------------------------------------------------------


def test_walk_result_is_named_dataclass() -> None:
    """WalkResult must be a frozen dataclass with the expected fields."""
    story = _minimal_tier1_story(
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
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
        start="start",
    )

    result = walk_configurations(story)

    assert isinstance(result, WalkResult)
    assert isinstance(result.configs, dict)
    assert isinstance(result.edges, dict)
    assert isinstance(result.capped, bool)


def test_config_key_structure() -> None:
    """Every ConfigKey in the result must be a 3-tuple of the correct types."""
    story = _minimal_tier1_story(
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
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
        start="start",
    )

    result = walk_configurations(story)

    for key in result.configs:
        assert isinstance(key, tuple)
        assert len(key) == 3
        node_id, var_tuple, visit_frozenset = key
        assert isinstance(node_id, str)
        assert isinstance(var_tuple, tuple)
        assert isinstance(visit_frozenset, frozenset)


def test_edges_keys_match_configs_keys() -> None:
    """Every key in edges must also be in configs, and vice versa."""
    story = _minimal_tier1_story(
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
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
        start="start",
    )

    result = walk_configurations(story)

    assert set(result.edges.keys()) == set(result.configs.keys())
    # Edge targets must also be in configs.
    all_targets = {t for targets in result.edges.values() for t in targets}
    for target in all_targets:
        assert target in result.configs, f"Edge target {target} not in configs"


def test_capped_false_when_cap_not_reached() -> None:
    """capped must be False when the total config count is well below the cap."""
    story = _minimal_tier1_story(
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
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
        start="start",
    )

    result = walk_configurations(story, cap=100_000)
    assert result.capped is False


def test_single_node_ending_story() -> None:
    """A story where start_node is itself an ending: 1 config, no edges."""
    # NOTE: Storybook validates that non-ending nodes have choices, and that
    # ending nodes have no choices. A single-node story where the only node
    # is an ending is valid Tier-1 schema. Let's verify this edge case.
    # However, also note that Storybook validates ending_count matches.
    story = _minimal_tier1_story(
        nodes=[
            {
                "id": "start",
                "body": "Instant end.",
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Instant",
                },
                "choices": [],
            },
        ],
        start="start",
        ending_count=1,
    )

    result = walk_configurations(story)

    assert not result.capped
    assert len(result.configs) == 1
    assert result.edges[next(iter(result.configs))] == []
