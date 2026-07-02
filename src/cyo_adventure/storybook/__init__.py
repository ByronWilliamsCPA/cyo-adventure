"""Storybook schema package: the versioned JSON story format and its DSL.

Public API re-exports the models and the condition helpers so callers can do
``from cyo_adventure.storybook import Storybook``.
"""

from __future__ import annotations

from cyo_adventure.storybook.condition import (
    WHITELISTED_OPERATORS,
    Condition,
    ordering_var_refs,
    referenced_vars,
    validate_condition,
)
from cyo_adventure.storybook.evaluator import (
    VarState,
    VarValue,
    evaluate,
)
from cyo_adventure.storybook.models import (
    SCHEMA_VERSION,
    AgeBand,
    Choice,
    ContentFlagLevel,
    ContentFlags,
    Effect,
    EffectOp,
    Ending,
    Node,
    ReadingLevel,
    Storybook,
    StoryMetadata,
    Variable,
    VariableType,
)

__all__ = [
    "SCHEMA_VERSION",
    "WHITELISTED_OPERATORS",
    "AgeBand",
    "Choice",
    "Condition",
    "ContentFlagLevel",
    "ContentFlags",
    "Effect",
    "EffectOp",
    "Ending",
    "Node",
    "ReadingLevel",
    "StoryMetadata",
    "Storybook",
    "VarState",
    "VarValue",
    "Variable",
    "VariableType",
    "evaluate",
    "ordering_var_refs",
    "referenced_vars",
    "validate_condition",
]
