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
    SCHEMA_MAJOR,
    SCHEMA_MINOR,
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
    is_supported_schema_version,
    parse_schema_version,
)

__all__ = [
    "SCHEMA_MAJOR",
    "SCHEMA_MINOR",
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
    "is_supported_schema_version",
    "ordering_var_refs",
    "parse_schema_version",
    "referenced_vars",
    "validate_condition",
]
