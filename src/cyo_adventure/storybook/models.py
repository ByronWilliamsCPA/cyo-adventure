"""Storybook schema v1 (Pydantic v2).

The Storybook is the single artifact the reader plays and the pipeline produces:
a versioned JSON graph of passages and choices with optional state for older
readers. This module is the one place the schema is defined; the JSON Schema at
``schema/storybook.schema.json`` is exported from it (see ``schema_export``).

The models enforce the *local, structural* invariants of a story: unique node,
choice, and ending ids; the ``is_ending`` / ``ending`` / ``choices`` agreement;
whitelisted condition operators; declared-variable references; and value bounds.
Graph properties that require traversal (reachability, dangling targets, trap
loops, termination) are the validator's job in later phases, not the schema's.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from cyo_adventure.storybook.condition import (
    MAX_ABS_STORY_INT,
    Condition,
    ordering_var_refs,
    referenced_vars,
)

SCHEMA_VERSION = "2.0"


class AgeBand(StrEnum):
    """The reading age band a story targets."""

    BAND_3_5 = "3-5"
    BAND_5_8 = "5-8"
    BAND_8_11 = "8-11"
    BAND_10_13 = "10-13"
    BAND_13_16 = "13-16"
    BAND_16_PLUS = "16+"


class VariableType(StrEnum):
    """The type of a story state variable (v1 supports bool and int only)."""

    BOOL = "bool"
    INT = "int"


class EffectOp(StrEnum):
    """A state mutation operation."""

    SET = "set"
    INC = "inc"
    DEC = "dec"


class ContentFlagLevel(StrEnum):
    """The intensity level of a content sensitivity flag."""

    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    INTENSE = "intense"


# Ordered rank for ContentFlagLevel. StrEnum is not orderable, and the per-band
# ceiling check (PL-16) needs "<=" semantics, so the order is defined once here.
_LEVEL_RANK: dict[ContentFlagLevel, int] = {
    ContentFlagLevel.NONE: 0,
    ContentFlagLevel.MILD: 1,
    ContentFlagLevel.MODERATE: 2,
    ContentFlagLevel.INTENSE: 3,
}


def level_rank(level: ContentFlagLevel) -> int:
    """Return the ordinal rank of a content-flag level (none=0 .. intense=3).

    Args:
        level: The content-flag level.

    Returns:
        int: The level's rank, for ``<=`` comparisons against a band ceiling.
    """
    return _LEVEL_RANK[level]


class Valence(StrEnum):
    """How an ending feels, independent of what mechanically happened."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class EndingKind(StrEnum):
    """What mechanically happened at an ending (closed set)."""

    SUCCESS = "success"
    SETBACK = "setback"
    DEATH = "death"
    CAPTURE = "capture"
    COMPLETION = "completion"
    DISCOVERY = "discovery"


class Topology(StrEnum):
    """The branching shape of a story graph (Ashwell vocabulary)."""

    TIME_CAVE = "time_cave"
    GAUNTLET = "gauntlet"
    BRANCH_AND_BOTTLENECK = "branch_and_bottleneck"
    LOOP_AND_GROW = "loop_and_grow"


class SafetyScope(StrEnum):
    """A per-node hint marking a sensitive scene for the safety reviewer."""

    PERIL = "peril"
    SCARY_IMAGERY = "scary_imagery"
    CONFLICT = "conflict"
    SAD_MOMENT = "sad_moment"


class ReadingLevel(BaseModel):
    """Target readability for a story (advisory at validation time)."""

    model_config = ConfigDict(extra="forbid")

    scheme: str = "flesch_kincaid"
    target: float = Field(ge=0.0)
    tolerance: float = Field(default=1.0, ge=0.0)


class ContentFlags(BaseModel):
    """Per-story content sensitivity flags scored per age band."""

    model_config = ConfigDict(extra="forbid")

    violence: ContentFlagLevel = ContentFlagLevel.NONE
    scariness: ContentFlagLevel = ContentFlagLevel.NONE
    peril: ContentFlagLevel = ContentFlagLevel.NONE


class StoryMetadata(BaseModel):
    """Descriptive metadata carried by every Storybook."""

    model_config = ConfigDict(extra="forbid")

    age_band: AgeBand
    reading_level: ReadingLevel
    tier: int = Field(ge=1, le=2)
    themes: list[str] = Field(default_factory=list)
    estimated_minutes: int = Field(ge=1)
    ending_count: int = Field(ge=1)
    content_flags: ContentFlags = Field(default_factory=ContentFlags)
    topology: Topology
    # A non-production MVP/Test skeleton exists for prototyping, pipeline and
    # integration testing, and generator development. When ``False`` the L1-7
    # node-count budget is the band-independent MVP envelope (not the band's
    # production budget), and production story selection must exclude it. All
    # other band policy (content ceiling, forbidden endings, floors, depth)
    # still applies. Defaults to ``True`` so an omitted field means production.
    # See ADR-011 (story-scale framework), the MVP/Test tier.
    production_eligible: bool = True


class Variable(BaseModel):
    """A declared story state variable with a type-consistent initial value."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: VariableType
    initial: bool | int
    # `bool` is included in the union (not just `int`) so a declared `true`/
    # `false` bound survives Pydantic's coercion as an actual bool instead of
    # being silently collapsed to 1/0; _check_int then rejects it explicitly,
    # matching `initial`'s existing bool-rejection pattern.
    min: bool | int | None = None
    max: bool | int | None = None
    description: str = ""

    @model_validator(mode="after")
    def _check_type_consistency(self) -> Self:
        """Enforce that ``initial`` and bounds agree with ``type``.

        Returns:
            Self: The validated model.
        """
        if self.type is VariableType.BOOL:
            self._check_bool()
        else:  # INT
            self._check_int()
        return self

    def _reject_bounds(self) -> None:
        """Reject min/max declared on a non-integer variable.

        Raises:
            ValueError: If either bound is set.
        """
        if self.min is not None or self.max is not None:
            msg = f"{self.type.value} variable '{self.name}' must not declare min/max"
            raise ValueError(msg)

    def _check_bool(self) -> None:
        """Validate a bool variable.

        Raises:
            ValueError: If the initial value is not boolean or bounds are set.
        """
        if not isinstance(self.initial, bool):
            msg = f"bool variable '{self.name}' needs a boolean initial value"
            raise ValueError(msg)  # noqa: TRY004 - Pydantic needs ValueError
        self._reject_bounds()

    def _check_int(self) -> None:
        """Validate an integer variable and its bounds.

        Raises:
            ValueError: If the initial value or a bound is boolean, is out of
                bounds, or any of initial/min/max exceeds
                ``MAX_ABS_STORY_INT``.
        """
        if isinstance(self.initial, bool):
            msg = f"int variable '{self.name}' needs an integer initial value"
            raise ValueError(msg)  # noqa: TRY004 - Pydantic needs ValueError
        for bound_label, bound_value in (("min", self.min), ("max", self.max)):
            if isinstance(bound_value, bool):
                msg = f"int variable '{self.name}' {bound_label} must not be boolean"
                raise ValueError(msg)  # noqa: TRY004 - Pydantic needs ValueError
        # #CRITICAL: data integrity: exact Python arithmetic and the client's
        # IEEE-754 doubles can never disagree about a declared int bound if
        # every declared int is checked against MAX_ABS_STORY_INT here.
        # #VERIFY: tests/unit/test_storybook_schema.py::
        # test_int_variable_rejects_out_of_range_declaration.
        for label, declared in (
            ("initial", self.initial),
            ("min", self.min),
            ("max", self.max),
        ):
            if declared is not None and abs(declared) > MAX_ABS_STORY_INT:
                msg = (
                    f"int variable '{self.name}' {label} magnitude must be "
                    f"<= {MAX_ABS_STORY_INT}, got {declared}"
                )
                raise ValueError(msg)
        self._check_int_bounds()

    def _check_int_bounds(self) -> None:
        """Validate that an integer variable's bounds contain its initial value.

        Raises:
            ValueError: If min > max or the initial value is out of bounds.
        """
        initial = self.initial
        if self.min is not None and self.max is not None and self.min > self.max:
            msg = f"int variable '{self.name}' has min greater than max"
            raise ValueError(msg)
        if self.min is not None and initial < self.min:
            msg = (
                f"int variable '{self.name}' initial {initial} is below min {self.min}"
            )
            raise ValueError(msg)
        if self.max is not None and initial > self.max:
            msg = (
                f"int variable '{self.name}' initial {initial} is above max {self.max}"
            )
            raise ValueError(msg)


class Effect(BaseModel):
    """A state change applied on node entry or when a choice is taken."""

    model_config = ConfigDict(extra="forbid")

    op: EffectOp
    var: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: bool | int | None = None
    once: bool = False

    @model_validator(mode="after")
    def _check_value(self) -> Self:
        """Enforce value presence and type per operation.

        Returns:
            Self: The validated model.

        Raises:
            ValueError: If a set effect has no value, inc/dec is not integral
                or is negative, or the value's magnitude exceeds
                ``MAX_ABS_STORY_INT``.
        """
        if self.op is EffectOp.SET:
            if self.value is None:
                msg = f"set effect on '{self.var}' requires a value"
                raise ValueError(msg)
        elif isinstance(self.value, bool) or not isinstance(self.value, int):
            msg = f"{self.op.value} effect on '{self.var}' requires an integer value"
            raise ValueError(msg)
        elif self.value < 0:
            msg = f"{self.op.value} effect on '{self.var}' must be non-negative"
            raise ValueError(msg)
        # #CRITICAL: data integrity: exact Python arithmetic and the client's
        # IEEE-754 doubles can never disagree about an effect value's identity
        # if every int effect value is bounded like every other story int
        # literal (see MAX_ABS_STORY_INT).
        # #VERIFY: tests/unit/test_storybook_schema.py::
        # test_effect_rejects_out_of_range_value.
        if abs(self.value) > MAX_ABS_STORY_INT:
            msg = (
                f"{self.op.value} effect on '{self.var}' value magnitude must be "
                f"<= {MAX_ABS_STORY_INT}, got {self.value}"
            )
            raise ValueError(msg)
        return self


class Choice(BaseModel):
    """A reader-facing choice edge from one node to a target node."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    target: str = Field(min_length=1)
    condition: Condition | None = None
    effects: list[Effect] = Field(default_factory=list)


class Ending(BaseModel):
    """A terminal outcome, typed on two axes: how it feels and what happened."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    valence: Valence
    kind: EndingKind
    title: str = Field(min_length=1)


class Node(BaseModel):
    """A passage: prose plus either choices (branch) or an ending (terminal)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    body: str
    on_enter: list[Effect] = Field(default_factory=list)
    choices: list[Choice] = Field(default_factory=list)
    is_ending: bool = False
    ending: Ending | None = None
    tags: list[str] = Field(default_factory=list)
    safety_scope: list[SafetyScope] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_ending_consistency(self) -> Self:
        """Enforce the agreement between ``is_ending``, ``ending``, ``choices``.

        Returns:
            Self: The validated model.

        Raises:
            ValueError: If the node violates the ending/choice invariants.
        """
        if self.is_ending:
            if self.ending is None:
                msg = f"ending node '{self.id}' requires an ending block"
                raise ValueError(msg)
            if self.choices:
                msg = f"ending node '{self.id}' must have no choices"
                raise ValueError(msg)
        else:
            if self.ending is not None:
                msg = f"non-ending node '{self.id}' must not carry an ending block"
                raise ValueError(msg)
            if not self.choices:
                msg = f"non-ending node '{self.id}' must have at least one choice"
                raise ValueError(msg)
        return self


class Storybook(BaseModel):
    """A complete, versioned branching story graph."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    title: str = Field(min_length=1)
    metadata: StoryMetadata
    variables: list[Variable] = Field(default_factory=list)
    start_node: str = Field(min_length=1)
    nodes: list[Node] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_story_invariants(self) -> Self:
        """Enforce story-wide structural invariants.

        Returns:
            Self: The validated model.
        """
        self._check_schema_version()
        self._check_unique_ids()
        self._check_start_node()
        self._check_tier_variables()
        self._check_variable_references()
        self._check_ending_count()
        return self

    def _check_schema_version(self) -> None:
        """Reject a schema_version this model does not implement.

        Raises:
            ValueError: If ``schema_version`` is not the supported version.
        """
        if self.schema_version != SCHEMA_VERSION:
            msg = (
                f"unsupported schema_version '{self.schema_version}'; "
                f"this model implements {SCHEMA_VERSION}"
            )
            raise ValueError(msg)

    def _check_unique_ids(self) -> None:
        """Reject duplicate node, choice, and ending ids."""
        node_ids = [node.id for node in self.nodes]
        _reject_duplicates(node_ids, "node id")
        choice_ids = [c.id for node in self.nodes for c in node.choices]
        _reject_duplicates(choice_ids, "choice id")
        ending_ids = [node.ending.id for node in self.nodes if node.ending is not None]
        _reject_duplicates(ending_ids, "ending id")

    def _check_start_node(self) -> None:
        """Reject a start node that is not present in the story.

        Raises:
            ValueError: If ``start_node`` is not an existing node id.
        """
        if self.start_node not in {node.id for node in self.nodes}:
            msg = f"start_node '{self.start_node}' is not an existing node id"
            raise ValueError(msg)

    def _check_tier_variables(self) -> None:
        """Enforce that Tier 1 stories declare no variables.

        Raises:
            ValueError: If a Tier 1 story declares variables.
        """
        if self.metadata.tier == 1 and self.variables:
            msg = "tier 1 stories must not declare variables"
            raise ValueError(msg)

    def _check_variable_references(self) -> None:
        """Reject effects or conditions that misuse declared variables.

        Verifies that every effect and condition references a declared variable,
        and that each effect's operation and value agree with the target
        variable's declared type: ``inc``/``dec`` require an int target, and a
        ``set`` value must match the target variable's type.
        """
        by_name = {variable.name: variable for variable in self.variables}
        declared = set(by_name)
        for node in self.nodes:
            for effect in node.on_enter:
                self._check_effect(effect, by_name, node.id)
            for choice in node.choices:
                for effect in choice.effects:
                    self._check_effect(effect, by_name, node.id)
                if choice.condition is not None:
                    for name in referenced_vars(choice.condition):
                        self._require_declared(name, declared, node.id)
                    self._check_ordering_vars(choice.condition, by_name, node.id)

    @staticmethod
    def _require_declared(name: str, declared: set[str], node_id: str) -> None:
        """Raise if ``name`` is not in the declared set.

        Args:
            name (str): The referenced variable name.
            declared (set[str]): The set of declared variable names.
            node_id (str): The node where the reference occurs (for the message).

        Raises:
            ValueError: If the variable is undeclared.
        """
        if name not in declared:
            msg = f"node '{node_id}' references undeclared variable '{name}'"
            raise ValueError(msg)

    @staticmethod
    def _check_ordering_vars(
        condition: dict[str, JsonValue], by_name: dict[str, Variable], node_id: str
    ) -> None:
        """Reject a bool-typed variable compared with an ordering operator.

        A bool can never resolve to int (ordering operands must resolve to
        int, ADR-006), so this is a story authoring mistake, caught here at
        schema validation instead of relying solely on the runtime
        evaluator's fail-closed behavior (``_ordered`` in ``evaluator.py``).

        Args:
            condition (dict[str, JsonValue]): A shape-validated condition.
            by_name (dict[str, Variable]): Declared variables, by name.
            node_id (str): The node where the reference occurs (for the message).

        Raises:
            ValueError: If an ordering operand names a bool-typed variable.
        """
        for name in ordering_var_refs(condition):
            variable = by_name.get(name)
            if variable is not None and variable.type is VariableType.BOOL:
                msg = (
                    f"node '{node_id}' compares bool-typed variable '{name}' "
                    "with an ordering operator; ordering operands must be int"
                )
                raise ValueError(msg)

    @staticmethod
    def _check_effect(
        effect: Effect, by_name: dict[str, Variable], node_id: str
    ) -> None:
        """Reject an effect targeting an undeclared or type-incompatible variable.

        Args:
            effect (Effect): The effect to validate.
            by_name (dict[str, Variable]): Declared variables keyed by name.
            node_id (str): The node where the effect occurs (for the message).

        Raises:
            ValueError: If the target is undeclared, or the operation or value
                disagrees with the target variable's declared type.
        """
        variable = by_name.get(effect.var)
        if variable is None:
            msg = f"node '{node_id}' references undeclared variable '{effect.var}'"
            raise ValueError(msg)
        if effect.op in (EffectOp.INC, EffectOp.DEC):
            if variable.type is not VariableType.INT:
                msg = (
                    f"node '{node_id}': {effect.op.value} effect requires an int "
                    f"variable, but '{effect.var}' is {variable.type.value}"
                )
                raise ValueError(msg)
        elif variable.type is VariableType.BOOL and not isinstance(effect.value, bool):
            msg = (
                f"node '{node_id}': set effect on bool variable '{effect.var}' "
                "requires a boolean value"
            )
            raise ValueError(msg)
        elif variable.type is VariableType.INT and (
            isinstance(effect.value, bool) or not isinstance(effect.value, int)
        ):
            msg = (
                f"node '{node_id}': set effect on int variable '{effect.var}' "
                "requires an integer value"
            )
            raise ValueError(msg)

    def _check_ending_count(self) -> None:
        """Enforce that the declared ending count matches the ending nodes.

        Raises:
            ValueError: If ``metadata.ending_count`` is wrong.
        """
        actual = sum(1 for node in self.nodes if node.is_ending)
        if actual != self.metadata.ending_count:
            msg = (
                f"metadata.ending_count {self.metadata.ending_count} does not match "
                f"the {actual} ending node(s)"
            )
            raise ValueError(msg)


def _reject_duplicates(values: list[str], label: str) -> None:
    """Raise if ``values`` contains any duplicate.

    Args:
        values (list[str]): The list of ids to check.
        label (str): A human label for the id namespace (for the message).

    Raises:
        ValueError: If a duplicate is found.
    """
    seen: set[str] = set()
    for value in values:
        if value in seen:
            msg = f"duplicate {label}: '{value}'"
            raise ValueError(msg)
        seen.add(value)
