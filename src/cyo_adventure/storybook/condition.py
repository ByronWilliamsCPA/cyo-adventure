"""In-house condition DSL shape validation (ADR-006).

Conditions use the JSONLogic object shape restricted to a whitelisted operator
set. This module validates the structural shape at schema-parse time so a story
that uses a non-whitelisted operator fails to load. The boolean evaluation of a
condition against a variable state is the evaluator's job (Phase 1); this module
never evaluates, never parses strings, and never calls ``eval``.

Whitelisted operators:

- ``var``                       read a declared variable (operand is its name)
- ``== != < <= > >=``           binary comparison (operand is a 2-item list)
- ``and`` / ``or``              n-ary boolean (operand is a list, length >= 2)
- ``!``                         boolean negation (operand is a single condition)

Everything else (arithmetic, ``in``, string operators, array reductions,
``if``/ternary) is rejected.

Note on exception types: the validators below raise ``ValueError`` (not
``TypeError``) on a type mismatch on purpose. Pydantic v2 converts ``ValueError``
raised inside a validator into a ``ValidationError``; a ``TypeError`` would
propagate uncaught. The ``noqa: TRY004`` markers document that deliberate choice.
"""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import AfterValidator, JsonValue

COMPARISON_OPERATORS: frozenset[str] = frozenset({"==", "!=", "<", "<=", ">", ">="})
BOOLEAN_NARY_OPERATORS: frozenset[str] = frozenset({"and", "or"})
WHITELISTED_OPERATORS: frozenset[str] = (
    frozenset({"var", "!"}) | COMPARISON_OPERATORS | BOOLEAN_NARY_OPERATORS
)

_LITERAL_TYPES: tuple[type, ...] = (bool, int, str)


def _is_literal(value: object) -> bool:
    """Return True if ``value`` is an allowed comparison literal.

    Note that ``bool`` is a subclass of ``int``; both are allowed literals.

    Args:
        value (object): The candidate operand.

    Returns:
        bool: True if the value is a bool, int, or str literal.
    """
    return isinstance(value, _LITERAL_TYPES)


def _validate_var(operand: object) -> None:
    """Validate the operand of a ``var`` operator.

    Args:
        operand (object): The operand, expected to be a non-empty variable name.

    Raises:
        ValueError: If the operand is not a non-empty string.
    """
    if not isinstance(operand, str) or not operand:
        msg = f"'var' operand must be a non-empty variable name, got {operand!r}"
        raise ValueError(msg)


def _validate_operand(operand: object) -> None:
    """Validate a comparison operand (a literal or a nested condition).

    Args:
        operand (object): The operand to validate.

    Raises:
        ValueError: If the operand is neither a literal nor a valid condition.
    """
    if isinstance(operand, dict):
        _validate_node(cast("dict[str, object]", operand))
    elif not _is_literal(operand):
        msg = (
            "comparison operand must be a literal or a nested condition, "
            f"got {type(operand).__name__}"
        )
        raise ValueError(msg)


def _validate_comparison(operator: str, operand: object) -> None:
    """Validate the operand of a binary comparison operator.

    Args:
        operator (str): The comparison operator (for error messages).
        operand (object): Expected to be a 2-item list of operands.

    Raises:
        ValueError: If the operand is not a 2-item list of valid operands.
    """
    if not isinstance(operand, list):
        msg = f"comparison '{operator}' requires a 2-item list operand"
        raise ValueError(msg)  # noqa: TRY004 - Pydantic needs ValueError
    operands = cast("list[object]", operand)
    expected_arity = 2
    if len(operands) != expected_arity:
        msg = f"comparison '{operator}' requires a 2-item list operand"
        raise ValueError(msg)
    for item in operands:
        _validate_operand(item)


def _validate_nary(operator: str, operand: object) -> None:
    """Validate the operand of an n-ary boolean operator (``and`` / ``or``).

    Args:
        operator (str): The boolean operator (for error messages).
        operand (object): Expected to be a list of at least two conditions.

    Raises:
        ValueError: If the operand is not a list of two or more conditions.
    """
    min_operands = 2
    if not isinstance(operand, list):
        msg = f"boolean '{operator}' requires a list of at least two conditions"
        raise ValueError(msg)  # noqa: TRY004 - Pydantic needs ValueError
    operands = cast("list[object]", operand)
    if len(operands) < min_operands:
        msg = f"boolean '{operator}' requires a list of at least two conditions"
        raise ValueError(msg)
    for item in operands:
        _validate_node(item)


def _validate_node(node: object) -> None:
    """Recursively validate a single condition node against the whitelist.

    Args:
        node (object): The candidate condition object.

    Raises:
        ValueError: If the node is malformed or uses a non-whitelisted operator.
    """
    if not isinstance(node, dict):
        msg = f"condition must be a JSON object, got {type(node).__name__}"
        raise ValueError(msg)  # noqa: TRY004 - Pydantic validators must raise ValueError
    typed = cast("dict[str, object]", node)
    if len(typed) != 1:
        msg = (
            f"condition object must have exactly one operator key, got {sorted(typed)}"
        )
        raise ValueError(msg)
    operator, operand = next(iter(typed.items()))
    if operator not in WHITELISTED_OPERATORS:
        allowed = sorted(WHITELISTED_OPERATORS)
        msg = f"operator '{operator}' is not whitelisted; allowed: {allowed}"
        raise ValueError(msg)
    if operator == "var":
        _validate_var(operand)
    elif operator == "!":
        _validate_node(operand)
    elif operator in BOOLEAN_NARY_OPERATORS:
        _validate_nary(operator, operand)
    else:
        _validate_comparison(operator, operand)


def validate_condition(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Validate a condition object and return it unchanged.

    Args:
        value (dict[str, JsonValue]): The parsed condition object.

    Returns:
        dict[str, JsonValue]: The same object, if valid.
    """
    _validate_node(value)
    return value


def _collect_vars(node: object, out: set[str]) -> None:
    """Collect every variable name referenced by a condition into ``out``.

    Args:
        node (object): A condition node or operand.
        out (set[str]): The accumulator set to populate.
    """
    if isinstance(node, dict):
        for operator, operand in cast("dict[str, object]", node).items():
            if operator == "var" and isinstance(operand, str):
                out.add(operand)
            else:
                _collect_vars(operand, out)
    elif isinstance(node, list):
        for item in cast("list[object]", node):
            _collect_vars(item, out)


def referenced_vars(condition: dict[str, JsonValue]) -> set[str]:
    """Return the set of variable names a condition reads.

    Args:
        condition (dict[str, JsonValue]): A validated condition object.

    Returns:
        set[str]: The set of variable names referenced via ``var`` operators.
    """
    found: set[str] = set()
    _collect_vars(condition, found)
    return found


Condition = Annotated[dict[str, JsonValue], AfterValidator(validate_condition)]
"""A JSONLogic condition object restricted to the whitelisted operator set."""
