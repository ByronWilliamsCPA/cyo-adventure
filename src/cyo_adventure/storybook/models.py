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

import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from cyo_adventure.storybook.condition import (
    MAX_ABS_STORY_INT,
    Condition,
    ordering_var_refs,
    referenced_vars,
)

# ADR-025 minor 1 (2026-08-06) adds Storybook.accepts_character. Every field
# introduced at a minor must be registered in storybook/field_minors.py, which
# is what L1-8 checks a document's declared version against.
# #CRITICAL: data integrity: a field added here without a matching
# storybook/field_minors.py entry lets a document under-declare its
# schema_version while still using the field; L1-8
# (validator/layer1.py::_check_field_minors, which ships on this same
# change) reads that registry to catch exactly this, so a missed
# registration is silently unenforceable rather than merely undertested.
# #VERIFY: tests/unit/test_field_minor_floor.py covers L1-8 end to end,
# including test_l1_8_alone_sets_blocked_true_through_the_gate. The
# registration itself is held by the two-direction lockstep pair in that
# file: test_every_storybook_field_is_registered_or_baselined (no field
# escapes the registry) and test_no_field_minors_entry_names_a_field_that_
# does_not_exist (no registry entry outlives its field). Adding a field
# here without registering it fails the first of those. Tracked by UW-A45
# in docs/planning/unscheduled-work-register.md.
SCHEMA_MAJOR = 2
SCHEMA_MINOR = 1
SCHEMA_VERSION = f"{SCHEMA_MAJOR}.{SCHEMA_MINOR}"

_SCHEMA_VERSION_RE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)", re.ASCII)


def parse_schema_version(value: str) -> tuple[int, int]:
    """Split a ``MAJOR.MINOR`` schema version into its integer parts.

    Args:
        value: The raw ``schema_version`` string from a document.

    Returns:
        tuple[int, int]: The major and minor components.

    Raises:
        ValueError: If ``value`` is not exactly two dot-separated
            non-negative integers.
        TypeError: If ``value`` is not a string. This is deliberately not
            caught here: a non-string reaching a parser typed ``str`` is a
            caller bug, not a malformed document. Callers holding untrusted
            JSON should use :func:`is_supported_schema_version`, which takes
            ``object`` and folds both cases into ``False``.
    """
    match = _SCHEMA_VERSION_RE.fullmatch(value)
    if match is None:
        msg = f"malformed schema_version {value!r}; expected MAJOR.MINOR"
        raise ValueError(msg)
    return int(match.group(1)), int(match.group(2))


def is_supported_schema_version(
    value: object, *, major: int = SCHEMA_MAJOR, minor: int = SCHEMA_MINOR
) -> bool:
    """Report whether this build can parse a document at ``value``.

    ADR-025 accepts any same-major version whose minor is at or below the
    deployed minor. A newer minor is refused explicitly here rather than
    left for ``extra="forbid"`` to catch: with ``extra="forbid"`` everywhere,
    a newer-minor document that actually uses one of its new fields already
    fails at the model boundary, just with a confusing "extra fields not
    permitted" error instead of a version-specific one. This check buys two
    things ``extra="forbid"`` alone cannot: a clearer refusal that names the
    version rather than a field, and rejection of a newer-minor document
    that happens not to populate any new field, which is otherwise
    indistinguishable from a valid document at the deployed minor.

    ``value`` is typed ``object`` rather than ``str`` on purpose. Callers hold
    a raw JSON value whose type is not yet established (a document may carry
    ``"schema_version": null`` or a bare number), and a total predicate that
    answers False is more useful at a trust boundary than one that raises
    ``TypeError``.

    Args:
        value: The raw ``schema_version`` value from a document, of any type.
        major: The major version this build implements.
        minor: The highest minor version this build implements.

    Returns:
        bool: True if the document can be parsed by this build.
    """
    # #CRITICAL: data integrity: a malformed or non-string version must never
    # be treated as supported, or an unparseable document reaches the model as
    # if valid.
    # #VERIFY: covered by test_supported_version_rejects_malformed_without_raising
    # and test_supported_version_rejects_non_string_without_raising
    if not isinstance(value, str):
        return False
    try:
        doc_major, doc_minor = parse_schema_version(value)
    except ValueError:
        return False
    return doc_major == major and doc_minor <= minor


class AgeBand(StrEnum):
    """The reading age band a story targets."""

    BAND_3_5 = "3-5"
    BAND_5_8 = "5-8"
    BAND_8_11 = "8-11"
    BAND_10_13 = "10-13"
    BAND_13_16 = "13-16"
    BAND_16_PLUS = "16+"


# Ordered rank for AgeBand. StrEnum values ("3-5", "5-8", ...) do not sort
# safely by string comparison, and the age-band ceiling check (H1: a story or
# a confirmed request band must never exceed the target profile's band) needs
# "<=" semantics, so the order is defined once here, mirroring _LEVEL_RANK.
_AGE_BAND_RANK: dict[AgeBand, int] = {
    AgeBand.BAND_3_5: 0,
    AgeBand.BAND_5_8: 1,
    AgeBand.BAND_8_11: 2,
    AgeBand.BAND_10_13: 3,
    AgeBand.BAND_13_16: 4,
    AgeBand.BAND_16_PLUS: 5,
}


def age_band_rank(band: AgeBand) -> int:
    """Return the ordinal rank of an age band (3-5=0 .. 16+=5).

    Args:
        band: The age band.

    Returns:
        int: The band's rank, for ``<=`` comparisons against a ceiling.
    """
    return _AGE_BAND_RANK[band]


def parse_age_band_rank(value: str) -> int | None:
    """Best-effort parse of a raw age-band string into its rank.

    Storybook blob metadata and ``ChildProfile.age_band`` are plain strings
    (not validated ``AgeBand`` enum members at the DB layer), so callers doing
    a defense-in-depth ceiling check need a tolerant parse rather than a
    ``ValueError`` on malformed or missing data.

    Args:
        value: The raw age-band string (e.g. "8-11"), or "" / malformed.

    Returns:
        int | None: The band's rank, or None if ``value`` is not a
        recognized ``AgeBand`` value.
    """
    try:
        return _AGE_BAND_RANK[AgeBand(value)]
    except ValueError:
        return None


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


# The ending kinds that count as a *satisfying* completion: the reader finished
# the arc rather than failing out of it. One definition, because six rules and
# one runtime path all need the same answer and five separate copies of it were
# a drift waiting to happen (`UW-C292`). PL-20's arc floor, SR-9's series
# continuity, the character-progression runtime, the mutation clock re-proof and
# two mutation pre-checks all read this set.
#
# `EndingKind` is a `StrEnum`, so membership works for a raw JSON string as well
# as for a parsed enum value; the mutation module reads unparsed story dicts and
# needs the former.
# #ASSUME: data-integrity: a caller testing a raw string against this set relies
# on StrEnum hashing as its value, so `"success" in SATISFYING_ENDING_KINDS` is
# True without a parse step.
# #VERIFY: test_storybook_schema.py::test_satisfying_kinds_accept_raw_strings, and
# ::test_every_satisfying_kind_consumer_reads_this_one_set.
SATISFYING_ENDING_KINDS: frozenset[EndingKind] = frozenset(
    {EndingKind.SUCCESS, EndingKind.COMPLETION}
)


# The ending valences that count as a satisfying *outcome*: the reader was not
# defeated. Deliberately NOT the same predicate as SATISFYING_ENDING_KINDS above,
# and the two are named separately so the difference is stated once here rather
# than rediscovered as a drift between rules (`UW-C292`). Catalog-wide the two
# readings disagree on 500 of 968 endings, so which one a rule means is a real
# choice, not a formality.
#
# - By KIND (above): PL-20's arc floor, SR-9's series continuity, the character
#   runtime and the mutation clock. These ask "did the reader complete the arc",
#   so a neutral `discovery` ending is not a completion.
# - By VALENCE (here): the strict random-walk outcome floor in
#   `scripts/check_skeleton.py`. This asks "would a reader choosing at random be
#   defeated", where a neutral ending is not a defeat.
#
# RULED 2026-08-09 (owner, review Part 4 R1): the walk floor is a valence floor.
# Switching it to kind was tried and would make the teen gamebook cells
# unauthorable, since those books carry 2-7 satisfying-KIND endings out of 74-209
# (`AL-460`). Do not "unify" these by collapsing one into the other.
SATISFYING_ENDING_VALENCES: frozenset[Valence] = frozenset(
    {Valence.POSITIVE, Valence.NEUTRAL}
)


class Topology(StrEnum):
    """The branching shape of a story graph (Ashwell vocabulary).

    Six ADR-011 topologies compose from the flow primitives. ``open_map`` is a
    hub the reader explores in any order (loop/return edges make it cyclic);
    ``sorting_hat`` sorts the reader at an early branch into parallel, never
    reconverging tracks (an acyclic branching tree with no cross-track
    bottleneck). The Ashwell ``quest`` folds into ``branch_and_bottleneck``.
    """

    TIME_CAVE = "time_cave"
    GAUNTLET = "gauntlet"
    BRANCH_AND_BOTTLENECK = "branch_and_bottleneck"
    LOOP_AND_GROW = "loop_and_grow"
    OPEN_MAP = "open_map"
    SORTING_HAT = "sorting_hat"


class Length(StrEnum):
    """The story-scale (length) tier: a total-word budget, world size.

    Production stories place themselves on the ``(band, length, style)`` matrix
    from ADR-011; the node-count envelope is derived per cell. Young bands cap
    at ``MEDIUM``; epic scale is a series, not a fourth tier. A story that
    declares no length is not scale-classified and keeps the band-level budget.
    """

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class NarrativeStyle(StrEnum):
    """Prose vs gamebook chunking of one word budget (ADR-011).

    Meaningful only for ``13-16`` and ``16+``; lower bands are implicitly
    ``PROSE``. Gamebook packs the same total words into more, shorter nodes.
    """

    PROSE = "prose"
    GAMEBOOK = "gamebook"


class NarrativePerson(StrEnum):
    """The grammatical person the prose addresses the reader in.

    Ruled 2026-08-21 (`UW-C324`, section 9.4 of
    ``docs/planning/live-structural-round-2026-08-21.md``): narrative person
    was an unpinned degree of freedom, and three fills of one prose skeleton
    scattered from 0.07 to 0.72 second-person node rates because nothing
    declared which person the book is told in. Gamebooks are second-person by
    genre convention; prose books must say which they are, so same-skeleton
    siblings cannot ship in different persons.
    """

    SECOND = "second"
    THIRD = "third"


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


class Series(BaseModel):
    """Campaign-continuity metadata chaining a story into a multi-book series.

    A series is a meta-skeleton (books are nodes, and the completion-to-entry
    continuations are edges); v1 is a linear chain. Each book is a standalone
    Storybook that passes its own gate; these fields let the cross-book
    meta-validator check the ADR-011 section-8 invariant: in any non-final book,
    every successful-completion ending converges on the next book's single
    ``series_entry_node`` (many endings -> one entry), with declared state carried
    across. Young or Tier-1 bands run **episodic** series that carry no state.
    """

    model_config = ConfigDict(extra="forbid")

    series_id: str = Field(min_length=1)
    # 1-based position of this book in the linear chain.
    book_index: int = Field(ge=1)
    # The node continuation from the previous book lands on. ``None`` for the
    # first book (entered at ``start_node``); required for a continued-into book.
    series_entry_node: str | None = None
    # ``True`` marks a book that closes its chain (no next book). Only the
    # top-index book may carry it (SR-4); since the WS-G relaxation the top
    # book may also stay non-final, leaving the chain open for continuations.
    is_final: bool = False
    # The state-export contract: ``True`` carries declared state to the next book;
    # ``False`` is an episodic series (mandatory for young/Tier-1 bands).
    carries_state: bool = True


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
    # Story-scale placement on the ADR-011 (band, length, style) matrix. When a
    # production story declares ``length``, the L1-7 node-count budget is that
    # cell's genre-faithful envelope; a story with no length keeps the band-level
    # budget (backward compatible). ``narrative_style`` chunks the word budget and
    # only changes the envelope for 13-16/16+; lower bands are implicitly prose.
    length: Length | None = None
    narrative_style: NarrativeStyle = NarrativeStyle.PROSE
    # The declared grammatical person (`UW-C324`, ruled 2026-08-21). ``None``
    # means undeclared (legacy); the catalog is backfilled mechanically and a
    # fill must honor the declaration where present. Gamebooks default to
    # second person by convention; the checker in
    # ``scripts/check_prose_craft.py`` keys on this field.
    narrative_person: NarrativePerson | None = None

    @model_validator(mode="after")
    def _check_person_style_consistency(self) -> Self:
        """Reject a third-person gamebook, which is a contract contradiction.

        The gamebook genre addresses the reader ("you"), and the person
        checker holds declared-third books to a second-person ceiling; a
        representable ``gamebook`` + ``third`` combination therefore
        inverted the gate against a correctly-written second-person gamebook
        (PR #737 review, I10). Making the state unrepresentable is cheaper
        than teaching every consumer the precedence.

        Returns:
            Self: The validated model.

        Raises:
            ValueError: If a gamebook declares third person.
        """
        if (
            self.narrative_style is NarrativeStyle.GAMEBOOK
            and self.narrative_person is NarrativePerson.THIRD
        ):
            msg = (
                "narrative_style 'gamebook' cannot declare narrative_person "
                "'third': gamebooks address the reader in second person"
            )
            raise ValueError(msg)
        return self

    # A non-production MVP/Test skeleton exists for prototyping, pipeline and
    # integration testing, and generator development. When ``False`` the L1-7
    # node-count budget is the band-independent MVP envelope (not the band's
    # production budget), and production story selection must exclude it. All
    # other band policy (content ceiling, forbidden endings, floors, depth)
    # still applies. Defaults to ``True`` so an omitted field means production.
    # See ADR-011 (story-scale framework), the MVP/Test tier.
    production_eligible: bool = True
    # ADR-011 decision D11: a retired skeleton. Distinct from
    # ``production_eligible``, which marks the MVP/Test prototyping tier and
    # also loosens the L1-7 budget. A deprecated skeleton was a legitimate
    # production skeleton; it is simply superseded, so it keeps its band budget
    # and every other policy, and only stops being SELECTABLE for new stories.
    #
    # #CRITICAL: data-integrity: retirement must not be expressed by flipping
    # `production_eligible`, which would silently rebudget the story against
    # the band-independent MVP envelope and make a retired book easier to
    # validate than a live one. The two flags answer different questions and
    # are deliberately separate.
    # #VERIFY: test_skeleton_match.py::test_a_deprecated_skeleton_is_not_a_candidate
    # and test_policy.py::test_deprecation_does_not_change_the_node_budget.
    #
    # Books already published from a now-deprecated skeleton are unaffected:
    # this gates selection, not anything already in a child's library.
    deprecated: bool = False
    # Optional campaign-continuity placement. When set, this story is one book of
    # a linear multi-book series; the cross-book meta-validator (validator.series)
    # checks the ADR-011 section-8 continuity invariant across the chain. A story
    # with no ``series`` is a standalone book (backward compatible).
    series: Series | None = None


def _check_story_int_bound(value: bool | int, *, subject: str, label: str) -> None:
    """Reject a boolean-typed bound and enforce the story-wide int magnitude cap.

    Shared by ``Variable._check_int`` and ``CharacterRange`` so both apply the
    same two invariants to every declared int: a bound typed ``bool | int``
    (not plain ``int``) lets a JSON ``true``/``false`` survive Pydantic's
    coercion as an actual bool instead of being silently collapsed to
    ``1``/``0``, so it can be rejected explicitly here rather than admitted as
    an integer; and every declared int must stay within ``MAX_ABS_STORY_INT``.

    Args:
        value: The declared bound, typed ``bool | int`` so a boolean literal
            is distinguishable from an integer one.
        subject: Human-readable name of the field being validated; used only
            to compose the raised message.
        label: Which bound this is (for example ``"min"`` or ``"initial"``);
            used only to compose the raised message.

    Raises:
        ValueError: If ``value`` is a bool, or its magnitude exceeds
            ``MAX_ABS_STORY_INT``.
    """
    if isinstance(value, bool):
        msg = f"{subject} {label} must not be boolean"
        raise ValueError(msg)  # noqa: TRY004 - Pydantic needs ValueError
    # #CRITICAL: data integrity: exact Python arithmetic and the client's
    # IEEE-754 doubles can never disagree about a declared int bound's value
    # if every caller of this shared check (Variable's initial/min/max and
    # CharacterRange's min/max) is bounded against MAX_ABS_STORY_INT here.
    # #VERIFY: tests/unit/test_storybook_schema.py::
    # test_int_variable_rejects_out_of_range_declaration and
    # tests/unit/test_models.py::test_character_range_rejects_out_of_range_bound.
    if abs(value) > MAX_ABS_STORY_INT:
        msg = f"{subject} {label} magnitude must be <= {MAX_ABS_STORY_INT}, got {value}"
        raise ValueError(msg)


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
        subject = f"int variable '{self.name}'"
        _check_story_int_bound(self.initial, subject=subject, label="initial")
        for label, bound in (("min", self.min), ("max", self.max)):
            if bound is not None:
                _check_story_int_bound(bound, subject=subject, label=label)
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


class CharacterRange(BaseModel):
    """One variable's accepted range in a book's character envelope.

    Bounds are inclusive on both ends, matching ``Variable.min``/``Variable.max``,
    including at the type level: ``min``/``max`` are typed ``bool | int`` (not
    plain ``int``) and checked with the same ``_check_story_int_bound`` helper
    ``Variable`` uses, so a declared JSON ``true``/``false`` is rejected
    explicitly instead of being silently coerced to ``1``/``0``, and the
    ``MAX_ABS_STORY_INT`` magnitude cap applies here exactly as it does to
    ``Variable``. CH-2 requires this range to *equal* the declared variable's
    bounds rather than merely sit inside them: G3's runtime clamp is to
    declared bounds, so a narrower envelope would let the runtime admit states
    the validator never walked, invisibly.
    """

    model_config = ConfigDict(extra="forbid")

    # `bool` is included in the union (not just `int`) for the same reason as
    # `Variable.min`/`Variable.max`: it lets a declared `true`/`false` bound
    # survive Pydantic's coercion as an actual bool so `_check_bounds` can
    # reject it explicitly instead of silently admitting `1`/`0`.
    min: bool | int
    max: bool | int

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        subject = "accepts_character range"
        for label, bound in (("min", self.min), ("max", self.max)):
            _check_story_int_bound(bound, subject=subject, label=label)
        if self.min > self.max:
            msg = f"accepts_character range min {self.min} exceeds max {self.max}"
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
    # Absent means the book accepts no character. This is enforced rather than
    # assumed: CH-6 reserves the canonical variable names so a book that has
    # not opted in cannot be seeded by G3 name-match through an accidental
    # collision. ``None`` and ``{}`` are therefore different states and the
    # default must not be a factory.
    # #CRITICAL: data integrity: a default_factory=dict, a
    # model_dump(exclude_none=True) added to some future serializer, or a
    # "| None" cleanup would each silently collapse the None-vs-{} states
    # CH-6 depends on, with the test suite still green if nothing pins the
    # round trip.
    # #VERIFY: tests/unit/test_models.py::
    # test_accepts_character_none_vs_empty_dict_survive_round_trip.
    accepts_character: dict[str, CharacterRange] | None = None
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
        """Reject a schema_version outside the range this build implements.

        ADR-025: any same-major version at or below ``SCHEMA_MINOR`` parses.
        A newer minor is refused explicitly here rather than left for
        ``extra="forbid"`` to catch: that guard only fails a document that
        actually populates a field the current minor does not define, and
        even then with a confusing "extra fields not permitted" error. This
        check gives a version-specific refusal and also catches a
        newer-minor document that happens not to use any new field, which
        ``extra="forbid"`` alone would let through.

        Raises:
            ValueError: If ``schema_version`` is malformed, a different
                major, or a newer minor than this build implements.
        """
        # #CRITICAL: data integrity: this is the only check that refuses a
        # document by VERSION. Field shape, unknown fields, and topology are
        # each covered elsewhere (Pydantic field validation, extra="forbid",
        # the sibling _check_* validators, and validator.gate.run_gate), so
        # this is one gate among several, not the only one; what no other
        # check does is refuse a document whose fields all happen to be
        # well-formed but whose minor this build does not implement.
        # #VERIFY: test_storybook_rejects_a_newer_minor,
        # test_storybook_rejects_a_different_major, and
        # test_storybook_rejects_a_malformed_version in tests/unit/test_models.py
        if not is_supported_schema_version(self.schema_version):
            msg = (
                f"unsupported schema_version '{self.schema_version}'; "
                f"this build implements {SCHEMA_MAJOR}.0 through "
                f"{SCHEMA_VERSION}"
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
