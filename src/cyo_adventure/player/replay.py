"""Reading-state replay validation (Finding 2).

Validates a PUT reading-state save against the pinned story version. Pure and
synchronous: no I/O, no async, no ``api`` imports. Two tiers:

1. Structural floor (always): the submitted ``current_node``/``path``/``visit_set``
   ids exist in the version and ``var_state`` keys are declared variables with
   in-bounds, correctly-typed values.
2. Full replay (only when ``choice_path`` is provided): replay the choices through
   the deterministic engine from ``start`` and require the resulting state to equal
   the submitted state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.exceptions import BusinessLogicError, ValidationError
from cyo_adventure.player import StoryEngine
from cyo_adventure.storybook.models import Storybook, VariableType

if TYPE_CHECKING:
    from cyo_adventure.storybook.evaluator import VarState
    from cyo_adventure.storybook.models import Variable

_MAX_FLOAT64_SAFE_INT: int = 2**53 - 1
"""The largest integer IEEE-754 doubles represent exactly (Number.MAX_SAFE_INTEGER).

Saved values above this line are exact on the Python side but round in the
TypeScript player, so the two runtimes could disagree; the structural floor
rejects them (see _check_var_value)."""


def validate_reading_state(
    blob: dict[str, object],
    *,
    current_node: str,
    var_state: VarState,
    path: list[str],
    visit_set: list[str],
    choice_path: list[str] | None,
) -> None:
    """Validate a reading-state save against its pinned version blob.

    Args:
        blob: The stored ``StorybookVersion.blob`` for the pinned version.
        current_node: The submitted current node id.
        var_state: The submitted variable state.
        path: The submitted ordered node path.
        visit_set: The submitted visited-node ids.
        choice_path: The ordered choice ids taken, or ``None`` to skip replay.

    Raises:
        ValidationError: If the blob is corrupt at rest, the state is structurally
            invalid, or (when ``choice_path`` is given) a replay does not reproduce
            the submitted state.
    """
    # #CRITICAL: data integrity: this is the ONLY gate on the reading-state write
    # path; without it a client could persist an arbitrary node id or variable key
    # that the player and conditions later read (Finding 2, red-team 2026-06-29).
    # #VERIFY: structural floor runs unconditionally; replay runs when choice_path
    # is present. Tests in tests/unit/test_replay.py.
    story = _parse(blob)
    _check_structure(story, current_node, var_state, path, visit_set)
    if choice_path is not None:
        _check_replay(story, current_node, var_state, path, visit_set, choice_path)


def _parse(blob: dict[str, object]) -> Storybook:
    """Parse a stored blob into a Storybook, mapping corruption to a 422.

    Args:
        blob: The stored ``StorybookVersion.blob`` for the pinned version.

    Returns:
        Storybook: The parsed, schema-valid story.

    Raises:
        ValidationError: If the blob no longer conforms to the schema.
    """
    # #EDGE: data integrity: a published version blob should always parse; a parse
    # failure means at-rest corruption, surfaced as a generic 422 (CWE-209).
    # #VERIFY: the pydantic detail is not forwarded to the client.
    try:
        return Storybook.model_validate(blob)
    except PydanticValidationError as exc:
        msg = "reading-state cannot be validated against a malformed story version"
        raise ValidationError(msg, field="version") from exc


def _check_structure(
    story: Storybook,
    current_node: str,
    var_state: VarState,
    path: list[str],
    visit_set: list[str],
) -> None:
    """Structural floor: node ids exist, current_node/path agree, var_state is complete.

    This is the ONLY check that runs when ``choice_path`` is omitted (the
    default while the frontend player does not send it yet), so it must
    reject more than "every id happens to exist": a forged save that sets
    ``current_node`` to a valid-but-unreached node, or omits a declared
    variable to fall back to its implicit default, is exactly the forgery
    Finding 2 was opened to close.

    Args:
        story: The parsed, schema-valid story to validate against.
        current_node: The submitted current node id.
        var_state: The submitted variable state.
        path: The submitted ordered node path.
        visit_set: The submitted visited-node ids.

    Raises:
        ValidationError: On any unknown node id, a current_node/path mismatch,
            a missing or undeclared variable, or a wrong-typed/out-of-bounds
            value.
    """
    node_ids = {node.id for node in story.nodes}
    _check_current_node(current_node, node_ids)
    _check_node_refs(path, visit_set, node_ids)
    # #CRITICAL: data integrity: a genuine engine state always has
    # current_node == path[-1] (StoryEngine.start/choose append the new node
    # to path in the same step they set current_node); rejecting a mismatch
    # here closes a forgery path the id-membership checks above miss entirely.
    # #VERIFY: tests/unit/test_replay.py::test_current_node_path_mismatch_rejected.
    if path and current_node != path[-1]:
        msg = "current_node must be the last entry of path"
        raise ValidationError(msg, field="current_node", value=current_node)
    variables = {var.name: var for var in story.variables}
    _check_var_state(var_state, variables)


def _check_current_node(current_node: str, node_ids: set[str]) -> None:
    """Reject a current_node id that does not exist in this story version.

    Args:
        current_node: The submitted current node id.
        node_ids: The set of node ids declared in this story version.

    Raises:
        ValidationError: If current_node is not a known node id.
    """
    if current_node not in node_ids:
        msg = "current_node is not a node in this story version"
        raise ValidationError(msg, field="current_node", value=current_node)


def _check_node_refs(path: list[str], visit_set: list[str], node_ids: set[str]) -> None:
    """Reject any path/visit_set entry that does not exist in this story version.

    Args:
        path: The submitted ordered node path.
        visit_set: The submitted visited-node ids.
        node_ids: The set of node ids declared in this story version.

    Raises:
        ValidationError: If a path or visit_set entry is not a known node id,
            reported with the field it actually came from.
    """
    for nid in path:
        if nid not in node_ids:
            msg = "path references a node not in this story version"
            raise ValidationError(msg, field="path", value=nid)
    for nid in visit_set:
        if nid not in node_ids:
            msg = "visit_set references a node not in this story version"
            raise ValidationError(msg, field="visit_set", value=nid)


def _check_var_state(var_state: VarState, variables: dict[str, Variable]) -> None:
    """Reject a var_state that omits a declared variable or names an unknown one.

    Args:
        var_state: The submitted variable state.
        variables: The declared variables in this story version, by name.

    Raises:
        ValidationError: If a declared variable is missing from var_state, or
            var_state names a variable this story version does not declare.
    """
    # #CRITICAL: data integrity: StoryEngine.start() seeds every declared
    # variable into var_state and no effect ever removes a key, so a genuine
    # engine state always has one entry per declared variable; a client that
    # omits a key is forging a silent fall-back to that variable's zero value.
    # #VERIFY: tests/unit/test_replay.py::test_missing_declared_variable_rejected.
    missing = sorted(variables.keys() - var_state.keys())
    if missing:
        msg = "var_state is missing a declared variable"
        raise ValidationError(msg, field="var_state", value=missing[0])
    for key, value in var_state.items():
        var = variables.get(key)
        if var is None:
            msg = "var_state contains an undeclared variable"
            raise ValidationError(msg, field="var_state", value=key)
        _check_var_value(key, value, var)


def _check_var_value(key: str, value: object, var: Variable) -> None:
    """Reject a var_state value that is wrong-typed or out of declared bounds.

    Args:
        key: The variable name, used only for the raised error's context.
        value: The submitted value for this variable.
        var: The declared variable this value must satisfy.

    Raises:
        ValidationError: If value has the wrong type for var, or an int value
            is outside var's declared bounds.
        NotImplementedError: If var.type is a VariableType member this
            function does not yet handle (fail closed on future enum growth
            rather than silently misvalidating an unknown type).
    """
    if var.type is VariableType.INT:
        if isinstance(value, bool) or not isinstance(value, int):
            msg = f"var_state[{key!r}] requires an integer value"
            raise ValidationError(msg, field="var_state", value=value)
        # #CRITICAL: data integrity: Python holds ints exactly at any size but
        # the client computes in IEEE-754 doubles (exact only to 2**53 - 1), so
        # a forged save above that line could make validator and player
        # disagree about a variable's value. Schema literals are capped at
        # MAX_ABS_STORY_INT (1e9), so no engine-reachable state comes near this
        # cap; only a forged save can trip it.
        # #VERIFY: tests/unit/test_replay.py::
        # test_unbounded_int_var_above_float64_safe_range_rejected.
        if abs(value) > _MAX_FLOAT64_SAFE_INT:
            msg = f"var_state[{key!r}] exceeds the float64-safe integer range"
            raise ValidationError(msg, field="var_state", value=value)
        if (var.min is not None and value < var.min) or (
            var.max is not None and value > var.max
        ):
            msg = f"var_state[{key!r}] is out of declared bounds"
            raise ValidationError(msg, field="var_state", value=value)
    elif var.type is VariableType.BOOL:
        if not isinstance(value, bool):
            msg = f"var_state[{key!r}] requires a boolean value"
            raise ValidationError(msg, field="var_state", value=value)
    else:
        msg = f"unsupported declared variable type: {var.type!r}"
        raise NotImplementedError(msg)


def _check_replay(
    story: Storybook,
    current_node: str,
    var_state: VarState,
    path: list[str],
    visit_set: list[str],
    choice_path: list[str],
) -> None:
    """Full replay: the choice sequence must reproduce the submitted state.

    Args:
        story: The parsed, schema-valid story to replay against.
        current_node: The submitted current node id.
        var_state: The submitted variable state.
        path: The submitted ordered node path.
        visit_set: The submitted visited-node ids.
        choice_path: The ordered choice ids to replay from ``start``.

    Raises:
        ValidationError: If a choice is illegal or the replayed state differs.
    """
    engine = StoryEngine(story)
    state = engine.start()
    for choice_id in choice_path:
        try:
            state = engine.choose(state, choice_id)
        except BusinessLogicError as exc:
            msg = "choice_path contains an illegal choice"
            raise ValidationError(msg, field="choice_path", value=choice_id) from exc
    if (
        state.current_node != current_node
        or dict(state.var_state) != dict(var_state)
        or set(state.visit_set) != set(visit_set)
        or list(state.path) != list(path)
    ):
        msg = "submitted reading state does not match a replay of choice_path"
        raise ValidationError(msg, field="choice_path")
