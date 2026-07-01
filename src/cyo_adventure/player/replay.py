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
    """Structural floor: node ids exist and var_state is well-formed.

    Raises:
        ValidationError: On any unknown node id, undeclared variable, wrong-typed
            value, or out-of-bounds int.
    """
    node_ids = {node.id for node in story.nodes}
    if current_node not in node_ids:
        msg = "current_node is not a node in this story version"
        raise ValidationError(msg, field="current_node", value=current_node)
    for nid in (*path, *visit_set):
        if nid not in node_ids:
            msg = "path/visit_set references a node not in this story version"
            raise ValidationError(msg, field="path", value=nid)
    variables = {var.name: var for var in story.variables}
    for key, value in var_state.items():
        var = variables.get(key)
        if var is None:
            msg = "var_state contains an undeclared variable"
            raise ValidationError(msg, field="var_state", value=key)
        if var.type is VariableType.INT:
            if isinstance(value, bool) or not isinstance(value, int):
                msg = "int variable requires an integer value"
                raise ValidationError(msg, field="var_state", value=key)
            if (var.min is not None and value < var.min) or (
                var.max is not None and value > var.max
            ):
                msg = "int variable value is out of declared bounds"
                raise ValidationError(msg, field="var_state", value=key)
        elif not isinstance(value, bool):
            msg = "bool variable requires a boolean value"
            raise ValidationError(msg, field="var_state", value=key)


def _check_replay(
    story: Storybook,
    current_node: str,
    var_state: VarState,
    path: list[str],
    visit_set: list[str],
    choice_path: list[str],
) -> None:
    """Full replay: the choice sequence must reproduce the submitted state.

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
