"""Unit tests for the Storybook schema models and condition DSL.

These tests pin the *schema-level* invariants: structural rules the Pydantic
models enforce at parse time. Graph-level rules (reachability, dangling targets,
trap loops) are validated in later phases and are not asserted here.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from cyo_adventure.storybook import (
    WHITELISTED_OPERATORS,
    Storybook,
    referenced_vars,
    validate_condition,
)
from cyo_adventure.storybook.schema_export import build_schema, export_schema


def _minimal_tier1() -> dict[str, Any]:
    """Return a minimal, schema-valid Tier 1 story as a plain dict."""
    return {
        "schema_version": "1.0",
        "id": "s_min",
        "version": 1,
        "title": "Minimal",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "branch_and_bottleneck",
        },
        "variables": [],
        "start_node": "start",
        "nodes": [
            {
                "id": "start",
                "body": "You stand at a door.",
                "is_ending": False,
                "choices": [{"id": "c1", "label": "Open it", "target": "end"}],
            },
            {
                "id": "end",
                "body": "The end.",
                "is_ending": True,
                "ending": {
                    "id": "e_good",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Home",
                },
            },
        ],
    }


def _tier2_with_state() -> dict[str, Any]:
    """Return a minimal, schema-valid Tier 2 story that uses state."""
    story = _minimal_tier1()
    story["id"] = "s_state"
    story["metadata"]["tier"] = 2
    story["variables"] = [
        {"name": "has_lantern", "type": "bool", "initial": False},
        {"name": "courage", "type": "int", "initial": 0, "min": 0, "max": 5},
    ]
    story["nodes"][0]["choices"][0]["condition"] = {
        "and": [
            {"==": [{"var": "has_lantern"}, True]},
            {">=": [{"var": "courage"}, 3]},
        ]
    }
    story["nodes"][0]["choices"][0]["effects"] = [
        {"op": "set", "var": "has_lantern", "value": True},
        {"op": "inc", "var": "courage", "value": 1},
    ]
    return story


@pytest.mark.unit
def test_minimal_tier1_is_valid() -> None:
    """A minimal Tier 1 story parses without error."""
    book = Storybook.model_validate(_minimal_tier1())
    assert book.id == "s_min"
    assert book.metadata.tier == 1


@pytest.mark.unit
def test_tier2_with_state_is_valid() -> None:
    """A Tier 2 story with variables, a condition, and effects parses."""
    book = Storybook.model_validate(_tier2_with_state())
    assert len(book.variables) == 2
    assert book.nodes[0].choices[0].condition is not None


@pytest.mark.unit
def test_duplicate_node_id_rejected() -> None:
    """Two nodes sharing an id fail validation."""
    story = _minimal_tier1()
    story["nodes"][1]["id"] = "start"
    story["nodes"][1]["choices"] = []  # keep ending node shape valid otherwise
    with pytest.raises(ValidationError, match="duplicate node id"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_duplicate_choice_id_rejected() -> None:
    """Two choices sharing an id fail validation."""
    story = _tier2_with_state()
    story["nodes"][0]["choices"].append({"id": "c1", "label": "Wait", "target": "end"})
    with pytest.raises(ValidationError, match="duplicate choice id"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_duplicate_ending_id_rejected() -> None:
    """Two ending nodes sharing an ending id fail validation."""
    story = _minimal_tier1()
    story["metadata"]["ending_count"] = 2
    story["nodes"][0]["choices"].append({"id": "c2", "label": "Run", "target": "end2"})
    story["nodes"].append(
        {
            "id": "end2",
            "body": "Also the end.",
            "is_ending": True,
            "ending": {
                "id": "e_good",
                "valence": "positive",
                "kind": "success",
                "title": "Home Again",
            },
        }
    )
    with pytest.raises(ValidationError, match="duplicate ending id"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_missing_ending_block_rejected() -> None:
    """An ending node without an ending block fails validation."""
    story = _minimal_tier1()
    del story["nodes"][1]["ending"]
    with pytest.raises(ValidationError, match="requires an ending block"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_non_ending_with_ending_block_rejected() -> None:
    """A non-ending node carrying an ending block fails validation."""
    story = _minimal_tier1()
    story["nodes"][0]["ending"] = {
        "id": "e_x",
        "valence": "positive",
        "kind": "success",
        "title": "X",
    }
    with pytest.raises(ValidationError, match="must not carry an ending block"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_non_ending_without_choices_rejected() -> None:
    """A non-ending node with no choices fails validation."""
    story = _minimal_tier1()
    story["nodes"][0]["choices"] = []
    with pytest.raises(ValidationError, match="must have at least one choice"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_start_node_must_exist() -> None:
    """A start_node that names no node fails validation."""
    story = _minimal_tier1()
    story["start_node"] = "nowhere"
    with pytest.raises(ValidationError, match="is not an existing node id"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_tier1_with_variables_rejected() -> None:
    """A Tier 1 story declaring variables fails validation."""
    story = _minimal_tier1()
    story["variables"] = [{"name": "x", "type": "bool", "initial": False}]
    with pytest.raises(ValidationError, match="tier 1 stories must not declare"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_undeclared_variable_rejected() -> None:
    """A condition referencing an undeclared variable fails validation."""
    story = _tier2_with_state()
    story["nodes"][0]["choices"][0]["condition"] = {"==": [{"var": "undeclared"}, True]}
    with pytest.raises(ValidationError, match="undeclared variable 'undeclared'"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_non_whitelisted_operator_rejected() -> None:
    """A condition using a forbidden operator fails validation."""
    story = _tier2_with_state()
    story["nodes"][0]["choices"][0]["condition"] = {"+": [{"var": "courage"}, 1]}
    with pytest.raises(ValidationError, match="not whitelisted"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_ending_count_mismatch_rejected() -> None:
    """A declared ending_count that disagrees with reality fails validation."""
    story = _minimal_tier1()
    story["metadata"]["ending_count"] = 3
    with pytest.raises(ValidationError, match="does not match"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_bool_variable_needs_bool_initial() -> None:
    """A bool variable with a non-bool initial value fails validation."""
    story = _tier2_with_state()
    story["variables"][0]["initial"] = 1
    with pytest.raises(ValidationError, match="needs a boolean initial"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_int_variable_initial_out_of_bounds_rejected() -> None:
    """An int variable whose initial exceeds max fails validation."""
    story = _tier2_with_state()
    story["variables"][1]["initial"] = 9
    with pytest.raises(ValidationError, match="is above max"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_set_effect_requires_value() -> None:
    """A set effect with no value fails validation."""
    story = _tier2_with_state()
    story["nodes"][0]["choices"][0]["effects"] = [{"op": "set", "var": "has_lantern"}]
    with pytest.raises(ValidationError, match="requires a value"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_inc_effect_requires_integer_value() -> None:
    """An inc effect with a non-integer (boolean) value fails validation."""
    story = _tier2_with_state()
    story["nodes"][0]["choices"][0]["effects"] = [
        {"op": "inc", "var": "courage", "value": True}
    ]
    with pytest.raises(ValidationError, match="requires an integer value"):
        Storybook.model_validate(story)


@pytest.mark.unit
@pytest.mark.parametrize(
    "operator",
    sorted(WHITELISTED_OPERATORS - {"var", "!", "and", "or"}),
)
def test_validate_condition_accepts_comparisons(operator: str) -> None:
    """Every whitelisted comparison operator is accepted in canonical shape."""
    assert validate_condition({operator: [{"var": "x"}, 1]}) == {
        operator: [{"var": "x"}, 1]
    }


@pytest.mark.unit
def test_validate_condition_rejects_extra_keys() -> None:
    """A condition object with more than one operator key is rejected."""
    with pytest.raises(ValueError, match="exactly one operator key"):
        validate_condition({"==": [{"var": "x"}, 1], "!": {"var": "y"}})


@pytest.mark.unit
def test_validate_condition_rejects_bad_comparison_arity() -> None:
    """A comparison with the wrong number of operands is rejected."""
    with pytest.raises(ValueError, match="2-item list"):
        validate_condition({"==": [{"var": "x"}, 1, 2]})


@pytest.mark.unit
def test_referenced_vars_collects_nested_names() -> None:
    """referenced_vars returns every variable a nested condition reads."""
    condition = {
        "and": [
            {"==": [{"var": "has_lantern"}, True]},
            {"!": {">=": [{"var": "courage"}, 3]}},
        ]
    }
    assert referenced_vars(condition) == {"has_lantern", "courage"}


@pytest.mark.unit
def test_validate_condition_accepts_negation_and_nested_operand() -> None:
    """The ``!`` operator and a nested-condition operand are both accepted."""
    condition = {"!": {"==": [{"var": "x"}, {"var": "y"}]}}
    assert validate_condition(condition) == condition


@pytest.mark.unit
def test_validate_condition_rejects_non_object() -> None:
    """A condition that is not a JSON object is rejected."""
    with pytest.raises(ValueError, match="must be a JSON object"):
        validate_condition([{"var": "x"}])  # type: ignore[arg-type]


@pytest.mark.unit
def test_validate_condition_rejects_empty_var_name() -> None:
    """A ``var`` operator with an empty name is rejected."""
    with pytest.raises(ValueError, match="non-empty variable name"):
        validate_condition({"var": ""})


@pytest.mark.unit
def test_validate_condition_rejects_non_literal_operand() -> None:
    """A comparison operand that is neither literal nor condition is rejected."""
    with pytest.raises(ValueError, match="literal or a nested condition"):
        validate_condition({"==": [{"var": "x"}, None]})


@pytest.mark.unit
@pytest.mark.parametrize("bad_operand", [{"and": "not_a_list"}, {"or": [{"var": "x"}]}])
def test_validate_condition_rejects_bad_nary(bad_operand: dict[str, Any]) -> None:
    """An n-ary boolean needs a list of at least two conditions."""
    with pytest.raises(ValueError, match="at least two conditions"):
        validate_condition(bad_operand)


@pytest.mark.unit
def test_bool_variable_rejects_bounds() -> None:
    """A bool variable that declares min/max is rejected."""
    story = _tier2_with_state()
    story["variables"][0]["min"] = 0
    with pytest.raises(ValidationError, match="must not declare min/max"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_int_variable_rejects_non_int_initial() -> None:
    """An int variable with a boolean initial value is rejected."""
    story = _tier2_with_state()
    story["variables"][1]["initial"] = True
    with pytest.raises(ValidationError, match="needs an integer initial"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_int_variable_rejects_min_greater_than_max() -> None:
    """An int variable with min greater than max is rejected."""
    story = _tier2_with_state()
    story["variables"][1]["min"] = 5
    story["variables"][1]["max"] = 2
    story["variables"][1]["initial"] = 5
    with pytest.raises(ValidationError, match="min greater than max"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_int_variable_rejects_initial_below_min() -> None:
    """An int variable whose initial is below min is rejected."""
    story = _tier2_with_state()
    story["variables"][1]["min"] = 2
    story["variables"][1]["initial"] = 0
    with pytest.raises(ValidationError, match="is below min"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_unknown_variable_type_rejected() -> None:
    """A variable using a removed/unknown type (string, enum) is rejected.

    v1 supports only ``bool`` and ``int``; ``string`` and ``enum`` are not
    valid VariableType members and must fail at parse time.
    """
    story = _tier2_with_state()
    story["variables"].append({"name": "color", "type": "string", "initial": "red"})
    with pytest.raises(ValidationError):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_dec_effect_rejects_negative_value() -> None:
    """A dec effect with a negative value is rejected."""
    story = _tier2_with_state()
    story["nodes"][0]["choices"][0]["effects"] = [
        {"op": "dec", "var": "courage", "value": -1}
    ]
    with pytest.raises(ValidationError, match="must be non-negative"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_on_enter_effect_referencing_undeclared_var_rejected() -> None:
    """An on_enter effect on an undeclared variable is rejected."""
    story = _tier2_with_state()
    story["nodes"][1]["choices"] = []
    story["nodes"][0]["on_enter"] = [{"op": "set", "var": "ghost", "value": True}]
    with pytest.raises(ValidationError, match="undeclared variable 'ghost'"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_schema_export_round_trip(tmp_path: Any) -> None:
    """The exported JSON Schema is valid JSON with the expected top-level keys."""
    schema = build_schema()
    assert schema["title"] == "Storybook"
    assert "properties" in schema
    assert "nodes" in schema["properties"]

    target = tmp_path / "storybook.schema.json"
    written = export_schema(target)
    assert written == target
    reloaded = json.loads(target.read_text(encoding="utf-8"))
    assert reloaded == schema


@pytest.mark.unit
def test_extra_fields_are_forbidden() -> None:
    """Unknown top-level fields are rejected (extra=forbid)."""
    story = _minimal_tier1()
    story["unexpected"] = True
    with pytest.raises(ValidationError):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_deepcopy_helpers_are_independent() -> None:
    """The story builders return independent dicts (guards test isolation)."""
    one = _minimal_tier1()
    two = deepcopy(one)
    one["nodes"][0]["choices"][0]["label"] = "changed"
    assert two["nodes"][0]["choices"][0]["label"] == "Open it"


@pytest.mark.unit
def test_ending_node_with_choices_rejected() -> None:
    """An ending node that also declares choices is rejected."""
    story = _minimal_tier1()
    story["nodes"][1]["choices"] = [{"id": "c2", "label": "Linger", "target": "start"}]
    with pytest.raises(ValidationError, match="must have no choices"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_choice_effect_referencing_undeclared_var_rejected() -> None:
    """A choice effect mutating an undeclared variable is rejected."""
    story = _tier2_with_state()
    story["nodes"][0]["choices"][0]["effects"] = [
        {"op": "set", "var": "ghost", "value": True}
    ]
    with pytest.raises(ValidationError, match="undeclared variable 'ghost'"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_inc_effect_on_non_int_variable_rejected() -> None:
    """An inc effect targeting a bool variable is rejected."""
    story = _tier2_with_state()
    story["nodes"][0]["choices"][0]["effects"] = [
        {"op": "inc", "var": "has_lantern", "value": 1}
    ]
    with pytest.raises(ValidationError, match="inc effect requires an int variable"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_set_effect_type_mismatch_rejected() -> None:
    """A set effect whose value type disagrees with the variable is rejected."""
    story = _tier2_with_state()
    story["nodes"][0]["choices"][0]["effects"] = [
        {"op": "set", "var": "courage", "value": True}
    ]
    with pytest.raises(ValidationError, match="requires an integer value"):
        Storybook.model_validate(story)


@pytest.mark.unit
def test_unsupported_schema_version_rejected() -> None:
    """A story declaring an unsupported schema_version is rejected."""
    story = _minimal_tier1()
    story["schema_version"] = "2.0"
    with pytest.raises(ValidationError, match="unsupported schema_version"):
        Storybook.model_validate(story)


@pytest.mark.unit
@pytest.mark.parametrize("band", ["3-5", "5-8", "16+"])
def test_new_age_bands_are_valid(band: str) -> None:
    """The three added bands parse on a minimal Tier 1 story."""
    story = _minimal_tier1()
    story["metadata"]["age_band"] = band
    book = Storybook.model_validate(story)
    assert book.metadata.age_band == band


@pytest.mark.unit
def test_committed_schema_is_current() -> None:
    """The committed JSON Schema matches the model (guards against drift)."""
    committed_path = (
        Path(__file__).resolve().parents[2] / "schema" / "storybook.schema.json"
    )
    committed = committed_path.read_text(encoding="utf-8")
    regenerated = json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"
    assert committed == regenerated, (
        "schema/storybook.schema.json is stale; regenerate via "
        "`python -m cyo_adventure.storybook.schema_export`"
    )
