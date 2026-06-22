"""Tests for the condition evaluator: conformance corpus and totality.

The conformance cases pin the exact boolean each condition must produce; the
TypeScript client runs the same `schema/conformance/conditions.json`. The
Hypothesis property proves totality: every shape-valid condition evaluates to a
boolean without raising.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cyo_adventure.storybook.condition import validate_condition
from cyo_adventure.storybook.evaluator import evaluate

CONFORMANCE_PATH = (
    Path(__file__).resolve().parents[2] / "schema" / "conformance" / "conditions.json"
)


def _load_cases() -> list[dict[str, Any]]:
    """Load the conformance cases from the shared fixture file."""
    data = json.loads(CONFORMANCE_PATH.read_text(encoding="utf-8"))
    return list(data["cases"])


@pytest.mark.unit
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: str(c["name"]))
def test_conformance_case(case: dict[str, Any]) -> None:
    """Each conformance case evaluates to its pinned expected boolean."""
    result = evaluate(case["condition"], case["var_state"])
    assert result is case["expected"], case["name"]


@pytest.mark.unit
def test_conformance_file_has_broad_coverage() -> None:
    """The conformance corpus covers every operator at least once."""
    blob = CONFORMANCE_PATH.read_text(encoding="utf-8")
    for operator in ["var", "==", "!=", "<", "<=", ">", ">=", "and", "or", "!"]:
        assert operator in blob, operator


# --- Totality property ---------------------------------------------------------

_VAR_NAMES = ["a", "b", "courage", "trust"]


def _var_states() -> st.SearchStrategy[dict[str, bool | int]]:
    """Strategy producing a populated state for the known variable pool."""
    value = st.one_of(st.booleans(), st.integers(min_value=0, max_value=5))
    return st.fixed_dictionaries(dict.fromkeys(_VAR_NAMES, value))


def _conditions() -> st.SearchStrategy[dict[str, Any]]:
    """Strategy producing shape-valid conditions over the variable pool."""
    var_ref = st.sampled_from(_VAR_NAMES).map(lambda n: {"var": n})
    literal = st.one_of(st.booleans(), st.integers(min_value=-1, max_value=6))
    operand = st.one_of(var_ref, literal)
    comparison = st.tuples(
        st.sampled_from(["==", "!=", "<", "<=", ">", ">="]),
        operand,
        operand,
    ).map(lambda t: {t[0]: [t[1], t[2]]})
    leaves = st.one_of(var_ref, comparison)
    return st.recursive(
        leaves,
        lambda children: st.one_of(
            children.map(lambda c: {"!": c}),
            st.lists(children, min_size=2, max_size=3).map(lambda cs: {"and": cs}),
            st.lists(children, min_size=2, max_size=3).map(lambda cs: {"or": cs}),
        ),
        max_leaves=8,
    )


@pytest.mark.unit
@given(condition=_conditions(), var_state=_var_states())
def test_evaluator_is_total(
    condition: dict[str, Any], var_state: dict[str, bool | int]
) -> None:
    """Every generated condition is shape-valid and evaluates to a bool."""
    validate_condition(condition)  # must not raise: the strategy is shape-valid
    result = evaluate(condition, var_state)
    assert isinstance(result, bool)


@pytest.mark.unit
def test_missing_variable_defaults_false() -> None:
    """A reference to an absent variable resolves defensively to False."""
    assert evaluate({"var": "ghost"}, {}) is False


@pytest.mark.unit
def test_non_dsl_operand_resolves_false() -> None:
    """Operands outside the DSL (float, null) resolve to False without raising."""
    assert evaluate({"==": [{"var": "x"}, 1.5]}, {"x": 1}) is False
    assert evaluate({"==": [None, {"var": "x"}]}, {"x": 1}) is False
