"""Branch-coverage tests for the M5 state-variation module (WS-5 D6 follow-up).

These tests target the defensive, error, and edge branches of
``mutation/state_ops.py`` that the behavioral M5 suite in
``test_mutation_m5.py`` does not reach: the malformed-input dict accessors, the
``_assemble_condition`` whitelist ladder, the retune/rename/gate/add-route/
relocate precondition failures, the in-place clamp and rename helpers on crafted
condition trees, the "vanished during apply" fail-closed raises, and the
walk-derived helpers on empty or non-satisfying walks. They call the private
helpers directly with hand-built documents so each branch is exercised
deterministically without a full acceptance run.
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.ops import OpParams
from cyo_adventure.mutation.state_ops import (
    M5,
    _add_route_cycle_reason,  # pyright: ignore[reportPrivateUsage]
    _add_route_failures,  # pyright: ignore[reportPrivateUsage]
    _append_choice,  # pyright: ignore[reportPrivateUsage]
    _apply_add_route,  # pyright: ignore[reportPrivateUsage]
    _apply_gate_choice,  # pyright: ignore[reportPrivateUsage]
    _apply_retune,  # pyright: ignore[reportPrivateUsage]
    _assemble_condition,  # pyright: ignore[reportPrivateUsage]
    _base_failures,  # pyright: ignore[reportPrivateUsage]
    _choice_ref,  # pyright: ignore[reportPrivateUsage]
    _clamp_comparison_pair,  # pyright: ignore[reportPrivateUsage]
    _clamp_condition_literals,  # pyright: ignore[reportPrivateUsage]
    _clamp_int,  # pyright: ignore[reportPrivateUsage]
    _clamp_literals_for_var,  # pyright: ignore[reportPrivateUsage]
    _clamp_set_effect,  # pyright: ignore[reportPrivateUsage]
    _ending_multiset,  # pyright: ignore[reportPrivateUsage]
    _gate_choice_failures,  # pyright: ignore[reportPrivateUsage]
    _is_var_name,  # pyright: ignore[reportPrivateUsage]
    _mean_visible_ratio,  # pyright: ignore[reportPrivateUsage]
    _mint_choice_id,  # pyright: ignore[reportPrivateUsage]
    _move_on_enter_effect,  # pyright: ignore[reportPrivateUsage]
    _node_by_id,  # pyright: ignore[reportPrivateUsage]
    _nodes_of,  # pyright: ignore[reportPrivateUsage]
    _prospective_variable,  # pyright: ignore[reportPrivateUsage]
    _reguide_nodes_for_var,  # pyright: ignore[reportPrivateUsage]
    _relocate_failures,  # pyright: ignore[reportPrivateUsage]
    _rename_condition_var,  # pyright: ignore[reportPrivateUsage]
    _rename_failures,  # pyright: ignore[reportPrivateUsage]
    _rename_node_var_refs,  # pyright: ignore[reportPrivateUsage]
    _rename_var_everywhere,  # pyright: ignore[reportPrivateUsage]
    _retune_failures,  # pyright: ignore[reportPrivateUsage]
    _set_choice_condition,  # pyright: ignore[reportPrivateUsage]
    _stranding_precondition,  # pyright: ignore[reportPrivateUsage]
    _variables_of,  # pyright: ignore[reportPrivateUsage]
    clock_floor_for,
    walk_fastest_satisfying_finish,
)
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.walk import walk_configurations

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_FLOODED_QUARTER = _SKELETONS_ROOT / "10-13" / "the-flooded-quarter.json"


def _flooded_quarter() -> dict[str, object]:
    """Return the-flooded-quarter Tier-2 skeleton as a raw document."""
    return cast(
        "dict[str, object]",
        json.loads(_FLOODED_QUARTER.read_text(encoding="utf-8")),
    )


def _tiny(
    *, kind_safe: str = "success", length: str | None = "medium"
) -> dict[str, object]:
    """Return a small, schema-valid Tier-2 story for pure walk-helper tests.

    Args:
        kind_safe: The kind of the ``e_safe`` ending (``success`` is satisfying).
        length: The declared length, or None to drop it from the cell.

    Returns:
        dict[str, object]: The raw story document.
    """
    metadata: dict[str, object] = {
        "age_band": "10-13",
        "reading_level": {"scheme": "flesch_kincaid", "target": 5.0},
        "tier": 2,
        "estimated_minutes": 1,
        "ending_count": 2,
        "topology": "open_map",
        "narrative_style": "prose",
    }
    if length is not None:
        metadata["length"] = length
    return {
        "schema_version": "2.0",
        "id": "tiny",
        "version": 1,
        "title": "Tiny",
        "start_node": "s",
        "metadata": metadata,
        "variables": [{"name": "oil", "type": "int", "initial": 2, "min": 0, "max": 2}],
        "nodes": [
            {
                "id": "s",
                "body": "b",
                "choices": [
                    {
                        "id": "c1",
                        "label": "go deep",
                        "target": "e_deep",
                        "condition": {">=": [{"var": "oil"}, 2]},
                    },
                    {"id": "c2", "label": "go safe", "target": "e_safe"},
                ],
            },
            {
                "id": "e_deep",
                "body": "b",
                "is_ending": True,
                "ending": {
                    "id": "end_deep",
                    "valence": "positive",
                    "kind": "discovery",
                    "title": "Deep",
                },
            },
            {
                "id": "e_safe",
                "body": "b",
                "is_ending": True,
                "ending": {
                    "id": "end_safe",
                    "valence": "positive",
                    "kind": kind_safe,
                    "title": "Safe",
                },
            },
        ],
    }


# --- Malformed-input dict accessors ---


@pytest.mark.unit
def test_dict_accessors_tolerate_malformed_documents() -> None:
    """The tiny accessors return empty/None on non-list or absent fields."""
    assert _nodes_of({"nodes": "not-a-list"}) == []
    assert _variables_of({"variables": "not-a-list"}) == []
    assert _node_by_id({"nodes": [{"id": "a"}]}, "missing") is None


@pytest.mark.unit
def test_choice_ref_skips_idless_nodes_and_returns_none_when_absent() -> None:
    """A node without an id is skipped, and an unknown choice id yields None."""
    story: dict[str, object] = {
        "nodes": [
            {"choices": [{"id": "c1"}]},
            {"id": "n1", "choices": [{"id": "c2"}]},
        ]
    }
    assert _choice_ref(story, "missing") is None


@pytest.mark.unit
def test_ending_multiset_skips_a_non_dict_ending_block() -> None:
    """An ending node whose ``ending`` is not a dict contributes no entry."""
    story: dict[str, object] = {
        "nodes": [{"id": "e", "is_ending": True, "ending": "not-a-dict"}]
    }
    assert _ending_multiset(story) == ()


@pytest.mark.unit
def test_reguide_nodes_for_var_covers_effect_and_idless_nodes() -> None:
    """Effect-narrating and choice-narrating nodes are collected; idless skipped."""
    story: dict[str, object] = {
        "nodes": [
            {"body": "x", "on_enter": [{"var": "oil", "op": "set", "value": 1}]},
            {"id": "n1", "on_enter": [{"var": "oil", "op": "inc", "value": 1}]},
            {
                "id": "n2",
                "choices": [{"id": "c", "condition": {">=": [{"var": "oil"}, 1]}}],
            },
        ]
    }
    items = _reguide_nodes_for_var(story, "oil", "reason")
    assert {item.target_id for item in items} == {"n1", "n2"}


# --- _assemble_condition whitelist ladder ---


@pytest.mark.unit
def test_assemble_condition_rejects_each_invalid_scalar_shape() -> None:
    """Every whitelist clause returns its own reason and no condition."""
    story: dict[str, object] = {
        "variables": [{"name": "oil", "type": "int", "initial": 1, "min": 0, "max": 3}]
    }
    assert _assemble_condition(story, 5, ">=", 1) == (
        None,
        "gate_var and gate_op must be strings",
    )
    _, reason = _assemble_condition(story, "nope", ">=", 1)
    assert reason is not None
    assert "not a declared variable" in reason
    _, reason = _assemble_condition(story, "oil", "bad", 1)
    assert reason is not None
    assert "not a comparison operator" in reason
    assert _assemble_condition(story, "oil", ">=", "s") == (
        None,
        "gate_value must be an int or a bool literal",
    )
    bool_literal = True
    assert _assemble_condition(story, "oil", ">", bool_literal) == (
        None,
        "an ordering gate_op cannot compare a boolean literal",
    )
    _, reason = _assemble_condition(story, "oil", ">=", 10**11)
    assert reason is not None
    assert "magnitude must be" in reason
    condition, reason = _assemble_condition(story, "oil", ">=", 1)
    assert reason is None
    assert condition == {">=": [{"var": "oil"}, 1]}


# --- Clamp helpers ---


@pytest.mark.unit
def test_clamp_int_returns_each_bound() -> None:
    """A value below/above a bound is pulled to it; an in-range value is kept."""
    assert _clamp_int(5, 10, None) == 10
    assert _clamp_int(15, None, 10) == 10
    assert _clamp_int(7, 0, 10) == 7


@pytest.mark.unit
def test_clamp_literals_for_var_noop_when_unbounded_and_skips_junk() -> None:
    """An open range short-circuits; junk nodes/choices are skipped; literals clamp."""
    candidate: dict[str, object] = {
        "nodes": [
            42,
            {
                "on_enter": [{"var": "oil", "op": "set", "value": 100}],
                "choices": [
                    7,
                    {
                        "effects": [{"var": "oil", "op": "set", "value": 100}],
                        "condition": {">=": [{"var": "oil"}, 100]},
                    },
                ],
            },
        ]
    }
    # Open range: returns immediately, mutating nothing.
    snapshot = copy.deepcopy(candidate)
    _clamp_literals_for_var(candidate, "oil", None, None)
    assert candidate == snapshot
    # Real bounds: the out-of-range int literals are clamped to the new max.
    _clamp_literals_for_var(candidate, "oil", 0, 5)
    node = cast("dict[str, object]", cast("list[object]", candidate["nodes"])[1])
    effect = cast("dict[str, object]", cast("list[object]", node["on_enter"])[0])
    assert effect["value"] == 5
    choice = cast("dict[str, object]", cast("list[object]", node["choices"])[1])
    condition = cast("dict[str, object]", choice["condition"])
    assert condition == {">=": [{"var": "oil"}, 5]}


@pytest.mark.unit
def test_clamp_set_effect_ignores_non_matching_and_bool_values() -> None:
    """A non-target or non-set effect is left alone; a bool value is never clamped."""
    other: dict[str, object] = {"var": "water", "op": "set", "value": 100}
    _clamp_set_effect(other, "oil", 0, 5)
    assert other["value"] == 100
    boolish: dict[str, object] = {"var": "oil", "op": "set", "value": True}
    _clamp_set_effect(boolish, "oil", 0, 5)
    assert boolish["value"] is True


@pytest.mark.unit
def test_clamp_condition_literals_walks_not_and_or_and_unknown() -> None:
    """The ``!``/``and``/``or`` recursions clamp; an unknown operator is a no-op."""
    negated: dict[str, object] = {"!": {">=": [{"var": "oil"}, 100]}}
    _clamp_condition_literals(negated, "oil", 0, 5)
    inner = cast("dict[str, object]", negated["!"])
    assert inner == {">=": [{"var": "oil"}, 5]}

    conjunction: dict[str, object] = {
        "and": [
            {">=": [{"var": "oil"}, 100]},
            {"<=": [{"var": "oil"}, 100]},
        ]
    }
    _clamp_condition_literals(conjunction, "oil", 0, 5)
    clauses = cast("list[object]", conjunction["and"])
    assert cast("dict[str, object]", clauses[0]) == {">=": [{"var": "oil"}, 5]}

    unknown: dict[str, object] = {"garbage": 5}
    _clamp_condition_literals(unknown, "oil", 0, 5)
    assert unknown == {"garbage": 5}


@pytest.mark.unit
def test_clamp_condition_literals_ignores_non_dict_operands() -> None:
    """A ``!`` with a non-dict operand and an ``and`` with a junk clause are no-ops."""
    negated_junk: dict[str, object] = {"!": "not-a-dict"}
    _clamp_condition_literals(negated_junk, "oil", 0, 5)
    assert negated_junk == {"!": "not-a-dict"}
    mixed: dict[str, object] = {"and": ["not-a-dict", {">=": [{"var": "oil"}, 100]}]}
    _clamp_condition_literals(mixed, "oil", 0, 5)
    clauses = cast("list[object]", mixed["and"])
    assert clauses[0] == "not-a-dict"
    assert cast("dict[str, object]", clauses[1]) == {">=": [{"var": "oil"}, 5]}


@pytest.mark.unit
def test_clamp_comparison_pair_ignores_bad_arity_and_non_int_literal() -> None:
    """A non-2-item pair and a bool literal are both left untouched."""
    short_pair: list[object] = [{"var": "oil"}]
    _clamp_comparison_pair(short_pair, "oil", 0, 5)
    assert short_pair == [{"var": "oil"}]
    bool_pair: list[object] = [{"var": "oil"}, True]
    _clamp_comparison_pair(bool_pair, "oil", 0, 5)
    assert bool_pair == [{"var": "oil"}, True]
    int_pair: list[object] = [100, {"var": "oil"}]
    _clamp_comparison_pair(int_pair, "oil", 0, 5)
    assert int_pair == [5, {"var": "oil"}]


# --- Rename helpers on crafted trees ---


@pytest.mark.unit
def test_rename_var_everywhere_skips_non_dict_entries() -> None:
    """Non-dict variable and node entries are skipped; the real ones rename."""
    candidate: dict[str, object] = {
        "variables": [1, {"name": "oil"}],
        "nodes": [1, {"on_enter": [{"var": "oil"}]}],
    }
    _rename_var_everywhere(candidate, "oil", "fuel")
    variable = cast(
        "dict[str, object]", cast("list[object]", candidate["variables"])[1]
    )
    assert variable["name"] == "fuel"
    node = cast("dict[str, object]", cast("list[object]", candidate["nodes"])[1])
    effect = cast("dict[str, object]", cast("list[object]", node["on_enter"])[0])
    assert effect["var"] == "fuel"


@pytest.mark.unit
def test_rename_node_var_refs_renames_effect_and_skips_junk_choice() -> None:
    """An on_enter effect renames; a non-dict choice entry is skipped."""
    node: dict[str, object] = {
        "on_enter": [{"var": "oil"}],
        "choices": [
            1,
            {
                "effects": [{"var": "oil"}],
                "condition": {">=": [{"var": "oil"}, 1]},
            },
        ],
    }
    _rename_node_var_refs(node, "oil", "fuel")
    effect = cast("dict[str, object]", cast("list[object]", node["on_enter"])[0])
    assert effect["var"] == "fuel"
    choice = cast("dict[str, object]", cast("list[object]", node["choices"])[1])
    choice_effect = cast(
        "dict[str, object]", cast("list[object]", choice["effects"])[0]
    )
    assert choice_effect["var"] == "fuel"


@pytest.mark.unit
def test_rename_condition_var_recurses_into_dict_operands() -> None:
    """A dict operand renames its own var or recurses into a nested condition."""
    condition: dict[str, object] = {"!": {"!": {"var": "oil"}}}
    _rename_condition_var(condition, "oil", "fuel")
    outer = cast("dict[str, object]", condition["!"])
    inner = cast("dict[str, object]", outer["!"])
    assert inner["var"] == "fuel"


# --- _prospective_variable ---


@pytest.mark.unit
def test_prospective_variable_rejects_empty_and_schema_invalid() -> None:
    """No changes returns the empty reason; an out-of-range retune is schema-invalid."""
    current: dict[str, object] = {
        "name": "oil",
        "type": "int",
        "initial": 2,
        "min": 0,
        "max": 5,
    }
    new_decl, reason = _prospective_variable(current, OpParams.of())
    assert new_decl is None
    assert reason is not None
    assert "at least one" in reason
    new_decl, reason = _prospective_variable(current, OpParams.of(initial=5, max=3))
    assert new_decl is None
    assert reason is not None
    assert "schema-invalid" in reason


# --- Precondition-failure helpers ---


@pytest.mark.unit
def test_base_failures_flag_series_and_non_production_parents() -> None:
    """A series book and an MVP seed each add their own base failure."""
    series_parent = _flooded_quarter()
    cast("dict[str, object]", series_parent["metadata"])["series"] = {"id": "s"}
    assert any("series" in f for f in _base_failures(series_parent))
    seed_parent = _flooded_quarter()
    cast("dict[str, object]", seed_parent["metadata"])["production_eligible"] = False
    assert any("production-eligible" in f for f in _base_failures(seed_parent))


@pytest.mark.unit
def test_retune_failures_require_a_variable_name() -> None:
    """A retune with no ``variable`` parameter fails at preconditions."""
    failures = _retune_failures(_flooded_quarter(), OpParams.of(mode="retune"))
    assert any("declared variable" in f for f in failures)


@pytest.mark.unit
def test_rename_failures_cover_every_branch() -> None:
    """Missing args, unknown source, bad pattern, no-op, and collision each fail."""
    parent: dict[str, object] = {"variables": [{"name": "oil"}, {"name": "lamp"}]}
    assert _rename_failures(parent, OpParams.of())
    assert any(
        "not a declared variable" in f
        for f in _rename_failures(parent, OpParams.of(variable="nope", new_name="x"))
    )
    assert _rename_failures(parent, OpParams.of(variable="oil", new_name="Bad"))
    assert any(
        "no-op" in f
        for f in _rename_failures(parent, OpParams.of(variable="oil", new_name="oil"))
    )
    assert any(
        "already a declared variable" in f
        for f in _rename_failures(parent, OpParams.of(variable="oil", new_name="lamp"))
    )


@pytest.mark.unit
def test_is_var_name_accepts_snake_case_only() -> None:
    """The variable-name predicate rejects empties, capitals, and punctuation."""
    assert _is_var_name("ok_1") is True
    assert _is_var_name("") is False
    assert _is_var_name("Abc") is False
    assert _is_var_name("a-b") is False


@pytest.mark.unit
def test_gate_choice_failures_cover_each_branch() -> None:
    """Non-string, unknown, already-conditioned, and bad-gate choices each fail."""
    parent: dict[str, object] = {
        "variables": [{"name": "oil", "type": "int", "initial": 1, "min": 0, "max": 3}],
        "nodes": [
            {
                "id": "n",
                "choices": [
                    {
                        "id": "cond_c",
                        "target": "e",
                        "condition": {">=": [{"var": "oil"}, 1]},
                    },
                    {"id": "free_c", "target": "e"},
                    {"id": "sib", "target": "e"},
                ],
            },
            {"id": "e", "is_ending": True},
        ],
    }
    assert _gate_choice_failures(parent, OpParams.of())
    assert any(
        "not a choice" in f
        for f in _gate_choice_failures(parent, OpParams.of(choice="ghost"))
    )
    assert any(
        "already carries a condition" in f
        for f in _gate_choice_failures(
            parent,
            OpParams.of(choice="cond_c", gate_var="oil", gate_op=">=", gate_value=1),
        )
    )
    assert any(
        "not a declared variable" in f
        for f in _gate_choice_failures(
            parent,
            OpParams.of(choice="free_c", gate_var="bad", gate_op=">=", gate_value=1),
        )
    )


@pytest.mark.unit
def test_stranding_precondition_reports_a_vanished_node() -> None:
    """A stranding check against a missing node id returns the vanished reason."""
    parent: dict[str, object] = {"nodes": [{"id": "n", "choices": []}]}
    failures = _stranding_precondition(parent, "missing", "c", OpParams.of())
    assert any("vanished" in f for f in failures)


@pytest.mark.unit
def test_add_route_failures_cover_each_branch() -> None:
    """Missing args, bad host, unknown target, and a bad gate each fail."""
    parent: dict[str, object] = {
        "variables": [{"name": "oil", "type": "int", "initial": 1, "min": 0, "max": 3}],
        "nodes": [
            {"id": "n", "choices": [{"id": "c1", "target": "e"}]},
            {"id": "e", "is_ending": True},
        ],
    }
    assert _add_route_failures(parent, OpParams.of())
    assert any(
        "not a decision node" in f
        for f in _add_route_failures(parent, OpParams.of(host="e", target="n"))
    )
    assert any(
        "not a node" in f
        for f in _add_route_failures(
            parent,
            OpParams.of(
                host="n", target="ghost", gate_var="oil", gate_op=">=", gate_value=1
            ),
        )
    )
    assert any(
        "not a declared variable" in f
        for f in _add_route_failures(
            parent,
            OpParams.of(
                host="n", target="e", gate_var="bad", gate_op=">=", gate_value=1
            ),
        )
    )


@pytest.mark.unit
def test_add_route_cycle_reason_detects_a_new_cycle_on_an_acyclic_parent() -> None:
    """A back-edge on a linear parent creates a cycle; a forward edge does not."""
    parent: dict[str, object] = {
        "variables": [{"name": "oil", "type": "int", "initial": 1, "min": 0, "max": 3}],
        "nodes": [
            {"id": "a", "choices": [{"id": "ca", "target": "b"}]},
            {"id": "b", "choices": [{"id": "cb", "target": "c"}]},
            {"id": "c", "choices": [{"id": "cc", "target": "e"}]},
            {"id": "e", "is_ending": True},
        ],
    }
    reason = _add_route_cycle_reason(parent, "c", "a")
    assert reason is not None
    assert "cycle" in reason
    assert _add_route_cycle_reason(parent, "a", "c") is None


@pytest.mark.unit
def test_relocate_failures_cover_each_branch() -> None:
    """Missing args, bad source/dest, self-move, and index drift each fail."""
    parent: dict[str, object] = {
        "nodes": [
            {"id": "f", "on_enter": [{"var": "oil", "op": "set", "value": 1}]},
            {"id": "t"},
            {"id": "e", "is_ending": True},
        ]
    }
    assert _relocate_failures(parent, OpParams.of())
    assert any(
        "is not a node" in f
        for f in _relocate_failures(parent, OpParams.of(from_node="ghost", to_node="t"))
    )
    assert any(
        "non-ending node" in f
        for f in _relocate_failures(parent, OpParams.of(from_node="f", to_node="e"))
    )
    assert any(
        "same node" in f
        for f in _relocate_failures(parent, OpParams.of(from_node="f", to_node="f"))
    )
    assert any(
        "out of range" in f
        for f in _relocate_failures(
            parent, OpParams.of(from_node="f", to_node="t", effect_index=5)
        )
    )


# --- Fail-closed apply-path raises ---


@pytest.mark.unit
def test_apply_retune_raises_on_an_empty_change_and_skips_junk_vars() -> None:
    """A no-change retune raises; a junk variable entry is skipped during apply."""
    parent = _flooded_quarter()
    params = OpParams.of(variable="oil")
    with pytest.raises(ValidationError, match="ineligible"):
        _apply_retune(parent, params)
    junk_parent = _flooded_quarter()
    cast("list[object]", junk_parent["variables"]).append(99)
    result = _apply_retune(junk_parent, OpParams.of(variable="oil", max=4))
    assert result.candidate is not None


@pytest.mark.unit
def test_apply_gate_choice_raises_on_an_unassemblable_condition() -> None:
    """A gate-choice with an undeclared gate_var fails closed during apply."""
    parent = _flooded_quarter()
    params = OpParams.of(choice="c_n_hub_1", gate_var="not_declared")
    with pytest.raises(ValidationError, match="ineligible"):
        _apply_gate_choice(parent, params)


@pytest.mark.unit
def test_set_choice_condition_raises_when_the_choice_vanished() -> None:
    """A missing choice id fails closed; junk nodes/choices are skipped first."""
    candidate: dict[str, object] = {"nodes": [1, {"id": "n", "choices": [1]}]}
    with pytest.raises(ValidationError, match="vanished during apply"):
        _set_choice_condition(candidate, "missing", {">=": [{"var": "oil"}, 1]})


@pytest.mark.unit
def test_apply_add_route_raises_on_an_unassemblable_condition() -> None:
    """An add-route with an undeclared gate_var fails closed during apply."""
    parent = _flooded_quarter()
    params = OpParams.of(host="n_hub", target="e_steady", gate_var="not_declared")
    with pytest.raises(ValidationError, match="ineligible"):
        _apply_add_route(parent, params)


@pytest.mark.unit
def test_mint_choice_id_skips_a_taken_id() -> None:
    """A minted id increments past an existing collision."""
    parent: dict[str, object] = {
        "nodes": [{"id": "h", "choices": [{"id": "c_h_m5_1"}]}]
    }
    assert _mint_choice_id(parent, "h") == "c_h_m5_2"


@pytest.mark.unit
def test_append_choice_creates_a_choice_list_and_fails_closed() -> None:
    """A host without a choices list gets one; a missing host fails closed."""
    candidate: dict[str, object] = {"nodes": [1, {"id": "h"}]}
    _append_choice(candidate, "h", "cnew", "t", {">=": [{"var": "oil"}, 1]})
    host = cast("dict[str, object]", cast("list[object]", candidate["nodes"])[1])
    choices = cast("list[object]", host["choices"])
    assert cast("dict[str, object]", choices[0])["id"] == "cnew"
    with pytest.raises(ValidationError, match="vanished during apply"):
        _append_choice({"nodes": []}, "missing", "c", "t", {})


@pytest.mark.unit
def test_move_on_enter_effect_covers_missing_source_and_dest() -> None:
    """An out-of-range index and a vanished destination each fail closed."""
    oob: dict[str, object] = {"nodes": [1, {"id": "f", "on_enter": [{"var": "oil"}]}]}
    with pytest.raises(ValidationError, match="vanished during apply"):
        _move_on_enter_effect(oob, "f", "t", 5)

    dest_created: dict[str, object] = {
        "nodes": [
            {"id": "f", "on_enter": [{"var": "oil", "op": "set", "value": 1}]},
            1,
            {"id": "t"},
        ]
    }
    moved = _move_on_enter_effect(dest_created, "f", "t", 0)
    assert moved["var"] == "oil"
    dest = cast("dict[str, object]", cast("list[object]", dest_created["nodes"])[2])
    assert cast("list[object]", dest["on_enter"])

    dest_missing: dict[str, object] = {
        "nodes": [{"id": "f", "on_enter": [{"var": "oil", "op": "set", "value": 1}]}]
    }
    with pytest.raises(ValidationError, match="vanished during apply"):
        _move_on_enter_effect(dest_missing, "f", "missing", 0)


@pytest.mark.unit
def test_m5_apply_raises_on_an_unknown_mode() -> None:
    """Dispatch fails closed when the mode is not one of the five sub-ops."""
    parent = _flooded_quarter()
    params = OpParams.of(mode="bogus")
    rng = random.Random(0)
    with pytest.raises(ValidationError, match="mode"):
        M5.apply(parent, params, rng)


# --- Walk-derived helpers on empty and non-satisfying walks ---


@pytest.mark.unit
def test_mean_visible_ratio_is_zero_for_an_empty_walk() -> None:
    """With no reachable configurations the mean visible ratio is 0.0."""
    story = Storybook.model_validate(_tiny())
    assert _mean_visible_ratio(story, walk_configurations(story, cap=0)) == 0.0


@pytest.mark.unit
def test_walk_fastest_satisfying_finish_none_on_empty_and_unsatisfiable() -> None:
    """An empty walk and a walk with no satisfying ending both yield None."""
    story = Storybook.model_validate(_tiny())
    assert (
        walk_fastest_satisfying_finish(story, walk_configurations(story, cap=0)) is None
    )
    unsat = Storybook.model_validate(_tiny(kind_safe="discovery"))
    assert walk_fastest_satisfying_finish(unsat, walk_configurations(unsat)) is None


@pytest.mark.unit
def test_clock_floor_for_is_none_without_a_scale_classified_cell() -> None:
    """A length-less story is not scale-classified, so no clock floor applies."""
    story = Storybook.model_validate(_tiny(length=None))
    assert clock_floor_for(story) is None
