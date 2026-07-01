"""Total evaluator for the whitelisted condition DSL (ADR-006).

Phase 0 (`condition.py`) validates a condition's *shape*; this module computes
its *boolean value* against a variable state. The evaluator is **total**: every
schema-valid condition returns a boolean and never raises. Ordering comparisons
on non-numeric operands return ``False`` rather than raising, so a player and the
validator agree on every reachable configuration.

This is the Python side of the cross-implementation contract; the TypeScript
client implements the same semantics and both run the shared conformance fixture
set at ``schema/conformance/conditions.json``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from cyo_adventure.storybook.condition import BOOLEAN_NARY_OPERATORS

if TYPE_CHECKING:
    from pydantic import JsonValue

VarValue = bool | int | str
"""A runtime variable value: boolean, integer, or string."""

VarState = dict[str, VarValue]
"""A mapping from declared variable name to its current value."""


def evaluate(condition: dict[str, JsonValue], var_state: VarState) -> bool:
    """Evaluate a validated condition against a variable state.

    Args:
        condition (dict[str, JsonValue]): A shape-validated condition object.
        var_state (VarState): The current value of every declared variable.

    Returns:
        bool: The boolean value of the condition. Never raises for a
            schema-valid condition.
    """
    # #ASSUME: data integrity: callers pass a shape-validated single-key condition
    # (validate_condition / Layer-1). The single-key and operand-shape casts below
    # rely on that precondition; an unknown operator falls through to _ordered,
    # which fails closed (returns False) rather than computing an arbitrary order.
    # #VERIFY: the engine only evaluates conditions on a parsed, validated story.
    operator, operand = next(iter(condition.items()))
    if operator == "var":
        return _truthy(_lookup(cast("str", operand), var_state))
    if operator == "!":
        return not evaluate(cast("dict[str, JsonValue]", operand), var_state)
    if operator in BOOLEAN_NARY_OPERATORS:
        clauses = cast("list[dict[str, JsonValue]]", operand)
        results = [evaluate(clause, var_state) for clause in clauses]
        return all(results) if operator == "and" else any(results)
    pair = cast("list[JsonValue]", operand)
    left = _resolve(pair[0], var_state)
    right = _resolve(pair[1], var_state)
    return _compare(operator, left, right)


def _lookup(name: str, var_state: VarState) -> VarValue:
    """Read a variable's current value, defaulting to ``False`` if absent.

    Args:
        name (str): The variable name.
        var_state (VarState): The current variable state.

    Returns:
        VarValue: The variable's value, or ``False`` if it is not present.
    """
    return var_state.get(name, False)


def _truthy(value: VarValue) -> bool:
    """Coerce a variable value to a boolean.

    Args:
        value (VarValue): The value to coerce.

    Returns:
        bool: The truthiness of the value.
    """
    return bool(value)


def _resolve(operand: JsonValue, var_state: VarState) -> VarValue:
    """Resolve a comparison operand to a concrete value.

    A ``{"var": name}`` operand resolves to the variable's value; a literal
    resolves to itself. Anything unexpected resolves to ``False`` to preserve
    totality.

    Args:
        operand (JsonValue): A literal or a ``{"var": name}`` object.
        var_state (VarState): The current variable state.

    Returns:
        VarValue: The resolved value.
    """
    if isinstance(operand, dict):
        name = cast("dict[str, JsonValue]", operand).get("var")
        if isinstance(name, str):
            return _lookup(name, var_state)
    if isinstance(operand, bool | int | str):
        return operand
    return False


def _compare(operator: str, left: VarValue, right: VarValue) -> bool:
    """Apply a comparison operator to two resolved values.

    Args:
        operator (str): One of ``== != < <= > >=``.
        left (VarValue): The left operand value.
        right (VarValue): The right operand value.

    Returns:
        bool: The comparison result. Ordering on non-numeric operands is False.
    """
    if operator == "==":
        return _strict_eq(left, right)
    if operator == "!=":
        return not _strict_eq(left, right)
    return _ordered(operator, left, right)


def _strict_eq(left: VarValue, right: VarValue) -> bool:
    """Compare for equality treating ``bool`` and ``int`` as distinct types.

    Python evaluates ``True == 1`` as ``True`` because ``bool`` subclasses
    ``int``. The DSL contract requires strict equality so that ``true == 1`` is
    ``False`` and the Python evaluator agrees with the TypeScript ``===`` mirror
    on every reachable configuration. Differing boolean-ness short-circuits to
    ``False``; otherwise normal value equality applies.

    Args:
        left (VarValue): The left operand value.
        right (VarValue): The right operand value.

    Returns:
        bool: ``True`` only when both operands share boolean-ness and compare equal.
    """
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return left == right


def _ordered(operator: str, left: VarValue, right: VarValue) -> bool:
    """Apply an ordering operator, returning False on non-numeric operands.

    Booleans are NOT numeric here even though ``bool`` subclasses ``int`` in
    Python: the spec requires ordering operands to resolve to int, and the
    TypeScript mirror's ``typeof x !== 'number'`` check is false for booleans.
    Treating a bool as 0/1 would make the validator see a choice as visible
    while the player hides it (the exact divergence ADR-006 forbids), so both
    implementations fail closed. Pinned by the ``*_bool_*`` and
    ``lt_missing_var_is_false`` conformance cases (a missing variable resolves
    to ``False`` and must follow this same path).

    Args:
        operator (str): One of ``< <= > >=``.
        left (VarValue): The left operand value.
        right (VarValue): The right operand value.

    Returns:
        bool: The ordering result, or False if either operand is not numeric or
            the operator is not a recognised ordering operator.
    """
    if (
        isinstance(left, bool)
        or isinstance(right, bool)
        or not isinstance(left, int)
        or not isinstance(right, int)
    ):
        return False
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    # Unknown operator: fail closed rather than computing an arbitrary comparison.
    return False
