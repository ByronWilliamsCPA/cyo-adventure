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
ORDERING_OPERATORS: frozenset[str] = frozenset({"<", "<=", ">", ">="})
BOOLEAN_NARY_OPERATORS: frozenset[str] = frozenset({"and", "or"})
WHITELISTED_OPERATORS: frozenset[str] = (
    frozenset({"var", "!"}) | COMPARISON_OPERATORS | BOOLEAN_NARY_OPERATORS
)

_LITERAL_TYPES: tuple[type, ...] = (bool, int, str)

_JsonObject = dict[str, object]
"""Cast target for a shape-validated JSON object node (avoids repeating the
string literal at every ``cast`` call site; python:S1192)."""

MAX_ABS_STORY_INT: int = 1_000_000_000
"""The magnitude cap for every int literal in a story (conditions, variable
declarations, effect values).

Python ints are exact at any size but the TypeScript player computes in
IEEE-754 doubles, which are exact only up to 2**53 - 1 (~9.0e15). Capping
schema literals at 1e9 keeps every schema-representable literal float64-exact
with a ~9,000,000x margin, so the validator and the player stay in agreement
for the bounded-literal space this cap governs; see
``docs/planning/evaluator-runtime-equivalence.md`` for the residual risk on
unbounded runtime accumulation, which this cap does not address.
"""


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


def _validate_operand(operator: str, operand: object) -> None:
    """Validate a comparison operand (a literal or a ``{"var": name}`` reference).

    A nested condition is NOT a valid comparison operand: both evaluators
    resolve a non-var object operand to literal ``False`` rather than
    evaluating it, so allowing one here would let a story express a condition
    the runtime silently ignores. Ordering operators additionally reject
    boolean literals (a bool can never resolve numeric, so the comparison is
    statically meaningless), and int literals are bounded so exact Python ints
    and the client's IEEE-754 doubles can never disagree.

    Args:
        operator (str): The comparison operator this operand belongs to.
        operand (object): The operand to validate.

    Raises:
        ValueError: If the operand is not a literal or var reference, is a
            ``{"var": name}`` reference with an empty or non-string name, is a
            boolean literal under an ordering operator, or is an int literal
            beyond ``MAX_ABS_STORY_INT``.
    """
    if isinstance(operand, dict):
        typed = cast("_JsonObject", operand)
        if set(typed) != {"var"}:
            msg = (
                "comparison operand must be a literal or a var reference, "
                f"got operator object {sorted(typed)}"
            )
            raise ValueError(msg)
        _validate_var(typed["var"])
        return
    if not _is_literal(operand):
        msg = (
            "comparison operand must be a literal or a var reference, "
            f"got {type(operand).__name__}"
        )
        raise ValueError(msg)
    if isinstance(operand, bool):
        if operator in ORDERING_OPERATORS:
            msg = (
                f"ordering '{operator}' cannot compare a boolean literal; "
                "ordering operands must resolve to int"
            )
            raise ValueError(msg)
        return
    # #CRITICAL: data integrity: exact Python ints and the TypeScript player's
    # IEEE-754 doubles can never disagree about a comparison literal's value
    # if this bound is enforced on every int operand (see MAX_ABS_STORY_INT).
    # #VERIFY: conformance case eq_int_at_literal_bound_is_true pins agreement
    # at the bound; player/replay.py caps forged saves at the true
    # 2**53 - 1 line.
    if isinstance(operand, int) and abs(operand) > MAX_ABS_STORY_INT:
        msg = (
            f"comparison int literal magnitude must be <= {MAX_ABS_STORY_INT}, "
            f"got {operand}"
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
        _validate_operand(operator, item)


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
    typed = cast("_JsonObject", node)
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
        for operator, operand in cast("_JsonObject", node).items():
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


def _collect_ordering_var_refs(node: object, out: set[str]) -> None:
    """Collect variable names used as an ordering-operator operand.

    Assumes ``node`` is already shape-validated (see ``validate_condition``):
    a comparison operand is a literal or a ``{"var": name}`` reference, never
    a nested condition, so only ``!``/``and``/``or`` need recursion.

    Args:
        node (object): A shape-validated condition node.
        out (set[str]): The accumulator set to populate.
    """
    if not isinstance(node, dict):
        return
    typed = cast("_JsonObject", node)
    operator, operand = next(iter(typed.items()))
    if operator == "!":
        _collect_ordering_var_refs(operand, out)
        return
    if operator in BOOLEAN_NARY_OPERATORS:
        for clause in cast("list[object]", operand):
            _collect_ordering_var_refs(clause, out)
        return
    if operator in ORDERING_OPERATORS:
        for item in cast("list[object]", operand):
            if isinstance(item, dict):
                name = cast("_JsonObject", item).get("var")
                if isinstance(name, str):
                    out.add(name)


def ordering_var_refs(condition: dict[str, JsonValue]) -> set[str]:
    """Return variable names compared with an ordering operator.

    A bool-typed variable in this set is statically meaningless (ordering
    operands must resolve to int); the runtime evaluator already fails closed
    on it (``_ordered`` in ``evaluator.py``), but rejecting it at schema
    validation catches the story authoring mistake immediately instead of
    silently making a choice always hidden or always visible.

    Args:
        condition (dict[str, JsonValue]): A shape-validated condition object.

    Returns:
        set[str]: Variable names referenced as an operand of ``< <= > >=``
            anywhere in the condition tree.
    """
    found: set[str] = set()
    _collect_ordering_var_refs(condition, found)
    return found


Condition = Annotated[dict[str, JsonValue], AfterValidator(validate_condition)]
"""A JSONLogic condition object restricted to the whitelisted operator set."""
