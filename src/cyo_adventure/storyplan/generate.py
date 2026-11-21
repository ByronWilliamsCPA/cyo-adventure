# pyright: reportImplicitStringConcatenation=false
# Ruff ISC003 requires implicit concatenation for wrapped messages and this
# BasedPyright rule forbids it; the two conflict, and Ruff is the project's gate.
"""Pitch and plan generation (ADR-033 Decisions 1 and 3, work package WP-2.3).

A request becomes a checked Story Plan in four steps, all on a retained shape
(:mod:`cyo_adventure.storyplan.shapes`):

1. **Pitches.** One model call asks for three pitches (the five
   :class:`~cyo_adventure.storyplan.models.Pitch` fields). Each pitch is
   screened in order: the five fields must be present; every string passes the
   SP-9 floors for the band (:func:`~cyo_adventure.storyplan.checks.text_floor_violations`)
   and the real-child PII guard; then the Stage 0 classifiers read it, and a
   ``BLOCK`` or ``FLAG`` verdict rejects it. On-demand jobs use the first pitch
   that passes and stop screening there; a catalog caller passes the
   owner-chosen pitch instead (ADR-033 Decision 3: picking a pitch is
   initiation, not approval).
2. **Plan.** One model call turns pitch plus shape into the plan sections
   (cast, truth, facts, nodes, choices, threads, endings). The generator adds
   what is not the model's to choose: ``request``, ``pitch``, ``provenance``
   (bound to the shape by id and hash), each node's ``function`` (a shape
   property), each thread's ``planting_choices`` (the choices whose effects set
   its variable) and each choice's ``plants`` (the mirror of those).
3. **Checks.** SP-0 to SP-9 (:func:`~cyo_adventure.storyplan.checks.check_plan`)
   against the shape.
4. **Repair.** While the plan does not load or has an SP ERROR and the budget
   allows, the findings go back to the model with the plan it wrote, and the
   whole plan is written again. The budget is bounded (``max_repairs``).

What this module does not do: approve a plan (WP-2.4 calls a validated plan
reviewer; until then every plan goes to the owner, so the worker ends every
plan job ``needs_review``), fill a book (WP-2.6), or show anything to a child.

Opaque ids (the AL-837 decision)
================================

Retained shapes keep literals of the story they were cut from in their node
ids (``cq_plant_did_knock_doors_that``, ``bs_hub``), choice ids and variable
names (``did_start_beacon_steps``), and those names are inside ``shape_hash``,
so renaming them would stale every plan bound to the shape and change the
catalog skeletons. The plan model therefore never sees them. :class:`ShapeView`
renders the shape with opaque aliases (``N1``, ``C1``, ``state_1``) in book
order, drops every label, ending title and variable description, and maps the
model's answer back to the real ids before anything is checked or stored. A
thread's meaning is supplied by the plan (its ``plant`` fact and each payoff's
``shows``); the variable name is an opaque handle the plan binds to by name.
Nothing about the shape files, the registry or ``shape_hash`` changes. The
fill stage (WP-2.5/2.6) must keep the same rule: it renders a thread's
meaning, never its variable name.

Untrusted input (OWASP LLM01)
=============================

The request brief is fenced as untrusted input in every prompt (pitch, plan,
repair), and so is the pitch, which is model text derived from it. Every
payload is neutralized against the fence terminator and the stage marker by
the builders in :mod:`cyo_adventure.generation.prompts`. Every call goes
through :class:`~cyo_adventure.generation.guarded.PiiGuardedProvider`, so a
request carrying a family's child name or PII-shaped content hard-blocks
before any provider is reached.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal, TypeAlias, cast

import httpx
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.pii import assert_prompt_pii_safe
from cyo_adventure.generation.prompts import (
    build_pitch_prompt,
    build_plan_prompt,
    build_plan_repair_prompt,
)
from cyo_adventure.generation.skeleton import resolve_output_cap
from cyo_adventure.moderation.classifiers import run_classifiers
from cyo_adventure.moderation.report import Verdict
from cyo_adventure.storybook.fill_directive import parse_fill_v2
from cyo_adventure.storybook.models import (
    AgeBand,
    EffectOp,
    Length,
    NarrativeStyle,
    Storybook,
)
from cyo_adventure.storyplan.checks import check_plan, text_floor_violations
from cyo_adventure.storyplan.models import (
    PLAN_VERSION,
    CheckRecord,
    Pitch,
    PlanRequest,
    Provenance,
    ShapeRef,
    StoryPlan,
)
from cyo_adventure.storyplan.shapes import load_registry, load_shape, shape_entry_for
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

    from cyo_adventure.generation.concept import ConceptBrief
    from cyo_adventure.generation.pii import PiiContext
    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.moderation.report import Finding
    from cyo_adventure.storybook.models import Choice, Variable
    from cyo_adventure.storyplan.shapes import RetainedShape
    from cyo_adventure.validator.report import ValidationReport

__all__ = [
    "DEFAULT_MAX_REPAIRS",
    "PITCH_COUNT",
    "REPORT_KEYS",
    "PitchCandidate",
    "PitchScreen",
    "PlanGenerationResult",
    "PlanRequestInput",
    "PlanStatus",
    "ShapeView",
    "build_shape_view",
    "classifier_screen",
    "generate_pitches",
    "generate_story_plan",
    "load_bound_shape",
    "plan_request_from_brief",
]

_logger = get_logger(__name__)

PITCH_COUNT: Final = 3
"""How many pitches the pitch call asks for (WP-2.3: "two or three")."""

DEFAULT_MAX_REPAIRS: Final = 2
"""Repair calls allowed after the first plan call, so at most three plan calls."""

_PITCH_MAX_TOKENS: Final = 2_000
# A plan names every node and choice of its shape. The largest 8-11 shape
# (the-lantern-keepers-list, 132 nodes and 314 choices) needs on the order of
# 20,000 output tokens; the ceiling is clamped to the serving model's own cap.
_PLAN_MAX_TOKENS: Final = 32_000
# Findings fed back per repair. Errors first, then warnings; the rest are
# counted, so one cascading slip cannot crowd the prompt.
_MAX_FEEDBACK_LINES: Final = 80
_PITCH_FIELDS: Final[tuple[str, ...]] = (
    "hero",
    "want",
    "obstacle",
    "stake",
    "ending_kind",
)
# The plan sections the model writes. Everything else in a StoryPlan is set
# here (request, pitch, provenance, plan_version) or derived from the shape.
_MODEL_SECTIONS: Final[tuple[str, ...]] = (
    "cast",
    "truth",
    "facts",
    "nodes",
    "choices",
    "threads",
    "endings",
)
_BLOCKING_VERDICTS: Final = frozenset({Verdict.BLOCK, Verdict.FLAG})
_PRODUCER: Final = "cyo_adventure.storyplan.generate"
_METHOD: Final = "generated"
_CLASSIFIER_CLIENT_TIMEOUT: Final = 30.0
_IDENT_TOKEN: Final = re.compile(r"[A-Za-z0-9_-]+")
_FENCE_RE: Final = re.compile(
    r"^\s*```(?:json)?\s*\n(?P<body>.*?)\n\s*```\s*$", re.DOTALL
)

PlanStatus = Literal["checked", "failed_checks", "no_passing_pitch"]
"""Where a plan job stopped.

``checked``: the plan loads and SP-0 to SP-9 report no ERROR; it awaits
approval (WP-2.4). ``failed_checks``: the repair budget ran out with a plan
that does not load or has an SP ERROR. ``no_passing_pitch``: no pitch survived
screening, so no plan was attempted.
"""

PitchScreen: TypeAlias = Callable[
    [Sequence[tuple[str, str]]], Awaitable[Sequence["Finding"]]
]
"""Screens ``(item_id, text)`` pairs; production is :func:`classifier_screen`."""

REPORT_KEYS: Final[tuple[str, ...]] = (
    "authoring_method",
    "story_plan_status",
    "story_plan",
    "story_plan_checks",
    "story_plan_load_errors",
    "story_plan_attempts",
    "story_plan_shape",
    "story_plan_pitches",
    "story_plan_approval",
)
"""The ``GenerationJob.report`` keys a plan job writes (see :meth:`PlanGenerationResult.report`)."""


# ---------------------------------------------------------------------------
# The shape, as the plan model sees it
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ShapeView:
    """A retained shape with opaque ids, and the maps back to the real ones.

    Attributes:
        shape_id: The registry id.
        shape_hash: The registry hash (equal to the shape's ``shape_hash``).
        book: The parsed shape.
        functions: Real node id to its v2 ``function``.
        words: Real node id to its v2 word budget.
        node_alias: Real node id to alias (``N1`` ...), in book order.
        choice_alias: Real choice id to alias (``C1`` ...), in book order.
        variable_alias: Real variable name to alias (``state_1`` ...).
        band: The registry cell's band.
        length: The registry cell's length tier.
        style: The registry cell's narrative style.
    """

    shape_id: str
    shape_hash: str
    book: Storybook
    functions: dict[str, str]
    words: dict[str, int]
    node_alias: dict[str, str]
    choice_alias: dict[str, str]
    variable_alias: dict[str, str]
    band: AgeBand
    length: Length
    style: NarrativeStyle

    def _inverse(self) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        """Return the alias-to-real maps for nodes, choices and variables.

        Returns:
            tuple[dict[str, str], dict[str, str], dict[str, str]]: The three
                inverse maps.
        """
        return (
            {alias: real for real, alias in self.node_alias.items()},
            {alias: real for real, alias in self.choice_alias.items()},
            {alias: real for real, alias in self.variable_alias.items()},
        )

    def setters(self, variable: Variable) -> list[str]:
        """Return the real ids of the choices whose effects plant ``variable``.

        Args:
            variable: A declared variable of the shape.

        Returns:
            list[str]: Choice ids in book order (the same rule SP-1 applies).
        """
        return [
            choice.id
            for node in self.book.nodes
            for choice in node.choices
            if any(
                effect.var == variable.name
                and (
                    effect.value != variable.initial
                    if effect.op is EffectOp.SET
                    else effect.value != 0
                )
                for effect in choice.effects
            )
        ]

    def render(self) -> dict[str, object]:
        """Return the prose-free, alias-only graph the plan model reads.

        Kept: start node, states (alias, type, initial, bounds, which choices
        set them and which test them), and per node its alias, function, word
        budget, ending valence and kind, and per choice its alias, target,
        aliased condition and aliased effects. Dropped: every body, label,
        ending title, ending id, tag and variable description.

        Returns:
            dict[str, object]: The JSON-serialisable view.
        """
        states: list[dict[str, object]] = []
        for variable in self.book.variables:
            entry = variable.model_dump(
                mode="json", exclude={"name", "description"}, exclude_none=True
            )
            tested = [
                self.choice_alias[choice.id]
                for node in self.book.nodes
                for choice in node.choices
                if choice.condition is not None
                and variable.name in _condition_vars(choice.condition)
            ]
            states.append(
                {
                    "name": self.variable_alias[variable.name],
                    **entry,
                    "set_by": [self.choice_alias[c] for c in self.setters(variable)],
                    "tested_by": tested,
                }
            )
        nodes: list[dict[str, object]] = []
        for node in self.book.nodes:
            rendered: dict[str, object] = {
                "id": self.node_alias[node.id],
                "function": self.functions[node.id],
                "words": self.words[node.id],
            }
            if node.on_enter:
                rendered["on_enter"] = [
                    self._effect(e.model_dump(mode="json")) for e in node.on_enter
                ]
            if node.ending is not None:
                rendered["ending"] = {
                    "valence": node.ending.valence.value,
                    "kind": node.ending.kind.value,
                }
            if node.choices:
                rendered["choices"] = [self._choice(choice) for choice in node.choices]
            nodes.append(rendered)
        return {
            "start": self.node_alias[self.book.start_node],
            "states": states,
            "nodes": nodes,
        }

    def _choice(self, typed: Choice) -> dict[str, object]:
        """Render one choice with aliases.

        Args:
            typed: The choice.

        Returns:
            dict[str, object]: Alias, target, condition and effects.
        """
        out: dict[str, object] = {
            "id": self.choice_alias[typed.id],
            "to": self.node_alias.get(typed.target, typed.target),
        }
        if typed.condition is not None:
            out["when"] = _alias_condition(typed.condition, self.variable_alias)
        if typed.effects:
            out["sets"] = [
                self._effect(e.model_dump(mode="json")) for e in typed.effects
            ]
        return out

    def _effect(self, effect: dict[str, object]) -> dict[str, object]:
        """Alias an effect's variable.

        Args:
            effect: A dumped effect.

        Returns:
            dict[str, object]: The effect with ``var`` replaced by its alias.
        """
        var = effect.get("var")
        if isinstance(var, str):
            return {**effect, "var": self.variable_alias.get(var, var)}
        return effect

    def to_real(self, doc: Mapping[str, object]) -> dict[str, object]:
        """Map a model plan (alias ids) back to the shape's real ids.

        An id that is not an alias is left as it is, so SP-1 reports it.

        Args:
            doc: The plan sections as the model wrote them.

        Returns:
            dict[str, object]: The same sections keyed by real ids.
        """
        nodes, choices, variables = self._inverse()
        return _remap_sections(doc, nodes, choices, variables)

    def to_alias(self, doc: Mapping[str, object]) -> dict[str, object]:
        """Map plan sections keyed by real ids to aliases, for a repair prompt.

        Args:
            doc: Plan sections keyed by real ids.

        Returns:
            dict[str, object]: The same sections keyed by aliases.
        """
        return _remap_sections(
            doc, self.node_alias, self.choice_alias, self.variable_alias
        )

    def alias_text(self, text: str) -> str:
        """Replace every real node, choice and variable id in ``text``.

        Used on checker and loader messages before they go back to the model,
        so the real ids (story literals) never reach a prompt.

        Args:
            text: A message.

        Returns:
            str: The message with each real id token replaced by its alias.
        """
        table = {**self.variable_alias, **self.choice_alias, **self.node_alias}
        return _IDENT_TOKEN.sub(lambda m: table.get(m.group(0), m.group(0)), text)


def _condition_vars(condition: object) -> set[str]:
    """Return every variable name a JSONLogic condition references.

    Args:
        condition: A condition (dicts, lists and scalars).

    Returns:
        set[str]: The referenced names.
    """
    found: set[str] = set()
    if isinstance(condition, dict):
        typed = cast("dict[str, object]", condition)
        var = typed.get("var")
        if len(typed) == 1 and isinstance(var, str):
            found.add(var)
        for value in typed.values():
            found |= _condition_vars(value)
    elif isinstance(condition, list):
        for item in cast("list[object]", condition):
            found |= _condition_vars(item)
    return found


def _alias_condition(condition: object, aliases: Mapping[str, str]) -> object:
    """Return a JSONLogic condition with its variable names aliased.

    Args:
        condition: A condition.
        aliases: Real variable name to alias.

    Returns:
        object: A copy with every ``{"var": name}`` aliased.
    """
    if isinstance(condition, dict):
        typed = cast("dict[str, object]", condition)
        var = typed.get("var")
        if len(typed) == 1 and isinstance(var, str):
            return {"var": aliases.get(var, var)}
        return {key: _alias_condition(value, aliases) for key, value in typed.items()}
    if isinstance(condition, list):
        return [
            _alias_condition(item, aliases) for item in cast("list[object]", condition)
        ]
    return condition


def _remap_keys(section: object, mapping: Mapping[str, str]) -> object:
    """Rename the keys of an id-keyed section.

    Args:
        section: The section (an object keyed by id, or anything else).
        mapping: Old id to new id.

    Returns:
        object: The renamed object, or ``section`` unchanged when not an object.
    """
    if not isinstance(section, dict):
        return section
    typed = cast("dict[str, object]", section)
    return {mapping.get(key, key): value for key, value in typed.items()}


def _remap_list(values: object, mapping: Mapping[str, str]) -> object:
    """Rename each string in a list of ids.

    Args:
        values: The list (or anything else).
        mapping: Old id to new id.

    Returns:
        object: The renamed list, or ``values`` unchanged when not a list.
    """
    if not isinstance(values, list):
        return values
    return [
        mapping.get(v, v) if isinstance(v, str) else v
        for v in cast("list[object]", values)
    ]


def _remap_thread(
    thread: object,
    nodes: Mapping[str, str],
    choices: Mapping[str, str],
    variables: Mapping[str, str],
) -> object:
    """Rename the node, choice and variable ids inside one thread.

    Args:
        thread: The thread object (or anything else).
        nodes: Node id map.
        choices: Choice id map.
        variables: Variable name map.

    Returns:
        object: The renamed thread.
    """
    if not isinstance(thread, dict):
        return thread
    out = dict(cast("dict[str, object]", thread))
    variable = out.get("variable")
    if isinstance(variable, str):
        out["variable"] = variables.get(variable, variable)
    if "planting_choices" in out:
        out["planting_choices"] = _remap_list(out["planting_choices"], choices)
    sites = out.get("payoff_sites")
    if isinstance(sites, list):
        renamed: list[object] = []
        for site in cast("list[object]", sites):
            if isinstance(site, dict):
                typed = dict(cast("dict[str, object]", site))
                node = typed.get("node")
                choice = typed.get("choice")
                if isinstance(node, str):
                    typed["node"] = nodes.get(node, node)
                if isinstance(choice, str):
                    typed["choice"] = choices.get(choice, choice)
                renamed.append(typed)
            else:
                renamed.append(site)
        out["payoff_sites"] = renamed
    return out


def _remap_sections(
    doc: Mapping[str, object],
    nodes: Mapping[str, str],
    choices: Mapping[str, str],
    variables: Mapping[str, str],
) -> dict[str, object]:
    """Rename every node, choice and variable id in the model sections.

    Args:
        doc: The plan sections.
        nodes: Node id map.
        choices: Choice id map.
        variables: Variable name map.

    Returns:
        dict[str, object]: The renamed sections; other keys are copied.
    """
    out = dict(doc)
    for key, mapping in (("nodes", nodes), ("choices", choices), ("endings", nodes)):
        if key in out:
            out[key] = _remap_keys(out[key], mapping)
    threads = out.get("threads")
    if isinstance(threads, dict):
        out["threads"] = {
            thread_id: _remap_thread(thread, nodes, choices, variables)
            for thread_id, thread in cast("dict[str, object]", threads).items()
        }
    return out


def build_shape_view(entry: RetainedShape, shape: Mapping[str, object]) -> ShapeView:
    """Parse a retained shape and assign its opaque ids.

    Args:
        entry: The registry entry.
        shape: The decoded shape file (as :func:`load_shape` returns it).

    Returns:
        ShapeView: The view.

    Raises:
        ValidationError: If the shape does not parse, a node body is not a v2
            directive, or a real id collides with an alias.
    """
    try:
        book = Storybook.model_validate(shape)
    except PydanticValidationError as exc:
        msg = f"shape {entry.id!r} does not parse as a Storybook"
        raise ValidationError(msg, field="story_plan_shape", value=entry.id) from exc
    functions: dict[str, str] = {}
    words: dict[str, int] = {}
    for node in book.nodes:
        directive = parse_fill_v2(node.body)
        if directive is None:
            msg = f"shape {entry.id!r} node {node.id!r} is not a v2 directive"
            raise ValidationError(msg, field="story_plan_shape", value=entry.id)
        functions[node.id] = directive.function
        words[node.id] = directive.words
    node_alias = {node.id: f"N{i}" for i, node in enumerate(book.nodes, start=1)}
    choice_ids = [choice.id for node in book.nodes for choice in node.choices]
    choice_alias = {cid: f"C{i}" for i, cid in enumerate(choice_ids, start=1)}
    variable_alias = {
        variable.name: f"state_{i}" for i, variable in enumerate(book.variables, 1)
    }
    real = set(node_alias) | set(choice_alias) | set(variable_alias)
    aliases = (
        set(node_alias.values())
        | set(choice_alias.values())
        | set(variable_alias.values())
    )
    # #ASSUME: data-integrity: real ids in the retained shapes are lower-case
    # story slugs, so an upper-case alias cannot collide; a collision would
    # make the alias-to-real map ambiguous, so it fails closed.
    # #VERIFY: test_storyplan_generate.py builds a view of every retained shape.
    if real & aliases:
        msg = f"shape {entry.id!r} has an id that collides with an opaque alias"
        raise ValidationError(msg, field="story_plan_shape", value=entry.id)
    return ShapeView(
        shape_id=entry.id,
        shape_hash=entry.hash,
        book=book,
        functions=functions,
        words=words,
        node_alias=node_alias,
        choice_alias=choice_alias,
        variable_alias=variable_alias,
        band=entry.band,
        length=entry.length,
        style=entry.narrative_style,
    )


def load_bound_shape(
    shape_id: str, expected_hash: str, *, root: Path | None = None
) -> ShapeView:
    """Load a retained shape by id and check it is the one a job was bound to.

    Args:
        shape_id: The registry id recorded on the job.
        expected_hash: The registry hash recorded on the job.
        root: The repository root (defaults to the working directory).

    Returns:
        ShapeView: The view of the shape.

    Raises:
        ValidationError: If the registry or shape cannot be read, the id is no
            longer retained, or its hash changed since the job was created.
    """
    # #CRITICAL: data-integrity: a job records the shape id and hash chosen
    # when it was planned; a registry edit in between (a re-conversion, a
    # removed shape) must not hand the plan model a different graph than the
    # one the plan will claim to be bound to. Fails closed; no provider call.
    # #VERIFY: test_storyplan_generate.py::test_load_bound_shape_refuses_a_changed_hash.
    registry = load_registry(root)
    entry = shape_entry_for(registry, shape_id)
    if entry is None:
        msg = f"shape {shape_id!r} is not in the retained-shape registry"
        raise ValidationError(msg, field="story_plan_shape", value=shape_id)
    if entry.hash != expected_hash:
        msg = (
            f"shape {shape_id!r} changed since the job was planned: registry "
            f"hash {entry.hash}, job hash {expected_hash}"
        )
        raise ValidationError(msg, field="story_plan_shape", value=shape_id)
    return build_shape_view(entry, load_shape(entry, root))


# ---------------------------------------------------------------------------
# Request and pitches
# ---------------------------------------------------------------------------


_BRIEF_KEYS: Final[tuple[str, ...]] = (
    "title",
    "premise",
    "protagonist",
    "point_of_view",
    "age_band",
    "tone",
    "themes_allowed",
    "content_nogo",
)


@dataclass(frozen=True, slots=True)
class PlanRequestInput:
    """The request side of a plan job.

    Attributes:
        text: The request text (untrusted), stored as ``request.text``.
        band: The band, which must be the shape's band (SP-0).
        length: The shape's length tier.
        style: The shape's narrative style.
        brief: The fields of the request brief the model may read, fenced as
            untrusted input in every prompt. Shape-deciding fields of a concept
            brief (tier, pattern, node and ending counts) are left out: the
            shape decides those.
    """

    text: str | None
    band: AgeBand
    length: Length
    style: NarrativeStyle
    brief: dict[str, object]


def plan_request_from_brief(brief: ConceptBrief, view: ShapeView) -> PlanRequestInput:
    """Build a plan job's request side from a concept brief and its shape.

    Band, length and style come from the shape's registry cell, so the plan's
    ``request.band`` always equals the shape's band (SP-0), including for an
    admin's out-of-cell shape override.

    Args:
        brief: The concept brief (its premise is the request text).
        view: The shape view.

    Returns:
        PlanRequestInput: The request side.
    """
    dumped = brief.model_dump(mode="json")
    return PlanRequestInput(
        text=brief.premise,
        band=view.band,
        length=view.length,
        style=view.style,
        brief={key: dumped[key] for key in _BRIEF_KEYS if dumped.get(key) is not None},
    )


@dataclass(frozen=True, slots=True)
class PitchCandidate:
    """One pitch and the verdict of its screening.

    Attributes:
        index: Position in the model's answer (0-based), or 0 for an owner pitch.
        pitch: The parsed pitch, or None when it did not parse.
        reasons: Why it was rejected (rule names, never the text); empty when
            it passed. A pitch not screened because an earlier one passed
            carries ``("not screened",)``.
        advisories: Non-blocking classifier categories recorded on it.
        source: ``"model"`` or ``"owner"``.
    """

    index: int
    pitch: Pitch | None
    reasons: tuple[str, ...] = ()
    advisories: tuple[str, ...] = ()
    source: Literal["model", "owner"] = "model"

    @property
    def passed(self) -> bool:
        """Return whether the pitch passed every screen.

        Returns:
            bool: True when parsed and no reason was recorded.
        """
        return self.pitch is not None and not self.reasons

    def to_report(self) -> dict[str, object]:
        """Return the pitch's report entry (admin surfaces only).

        Returns:
            dict[str, object]: Index, source, verdict, reasons, advisories and
                the pitch fields.
        """
        return {
            "index": self.index,
            "source": self.source,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "advisories": list(self.advisories),
            "pitch": None if self.pitch is None else self.pitch.model_dump(),
        }


def classifier_screen(openai_key: str | None) -> PitchScreen:
    """Return the production pitch screen: the Stage 0 classifiers.

    Args:
        openai_key: The OpenAI Moderation key, or None (the classifier is then
            skipped and reported as a degraded advisory, as at intake).

    Returns:
        PitchScreen: An async callable screening ``(item_id, text)`` pairs.
    """

    async def screen(items: Sequence[tuple[str, str]]) -> Sequence[Finding]:
        # #CRITICAL: external-resources: Stage 0 is a network call. As at
        # request intake (story_requests/screening.py), a classifier outage
        # fails open with a degraded advisory: a pitch is internal text that
        # never reaches a child, and the finished book is screened again by
        # the full moderation pipeline before anyone reads it. A BLOCK or FLAG
        # verdict still rejects the pitch.
        # #VERIFY: test_storyplan_generate.py drives the screen with a fake
        # that returns BLOCK and asserts the pitch is rejected.
        async with httpx.AsyncClient(timeout=_CLASSIFIER_CLIENT_TIMEOUT) as client:
            return await run_classifiers(
                nodes=list(items),
                openai_key=openai_key,
                client=client,
                report_coverage=False,
            )

    return screen


async def _screen_pitch(  # noqa: PLR0913 - keyword-only screening inputs
    index: int,
    raw: object,
    *,
    band: AgeBand,
    pii: PiiContext,
    screen: PitchScreen,
) -> PitchCandidate:
    """Screen one raw pitch: fields, floors, PII, then Stage 0.

    Args:
        index: Its position in the answer.
        raw: The decoded pitch object.
        band: The band whose floors apply.
        pii: The family's PII context.
        screen: The Stage 0 screen.

    Returns:
        PitchCandidate: The verdict. Cheap local checks run first, and the
            classifiers are called only for a pitch that passes them.
    """
    if not isinstance(raw, dict):
        return PitchCandidate(index=index, pitch=None, reasons=("not a JSON object",))
    typed = cast("dict[str, object]", raw)
    try:
        pitch = Pitch.model_validate({key: typed.get(key) for key in _PITCH_FIELDS})
    except PydanticValidationError as exc:
        missing = sorted({str(err["loc"][0]) for err in exc.errors() if err["loc"]})
        return PitchCandidate(
            index=index,
            pitch=None,
            reasons=tuple(f"{name}: missing, empty or not text" for name in missing),
        )
    values = cast("dict[str, str]", pitch.model_dump())
    reasons: list[str] = []
    for name in _PITCH_FIELDS:
        value = values[name]
        reasons.extend(f"{name}: {v}" for v in text_floor_violations(value, band))
        # #CRITICAL: security: a pitch is model text and becomes part of the
        # plan prompt; a family's child name must not enter it even by the
        # model's invention. The provider guard would block the next call,
        # failing the whole job; rejecting the pitch here keeps the request
        # usable when another pitch is clean.
        # #VERIFY: test_storyplan_generate.py::
        # test_pitch_screening_skips_floored_and_blocked_pitches.
        try:
            assert_prompt_pii_safe(value, forbidden=pii)
        except ValidationError:
            reasons.append(f"{name}: personal information")
    if reasons:
        return PitchCandidate(index=index, pitch=pitch, reasons=tuple(reasons))
    findings = await screen(
        [(f"pitch_{index}.{name}", values[name]) for name in _PITCH_FIELDS]
    )
    blocking = sorted(
        {
            f"stage0 {f.category}: {f.verdict.value}"
            for f in findings
            if f.verdict in _BLOCKING_VERDICTS
        }
    )
    advisories = sorted({f.category for f in findings if f.verdict is Verdict.ADVISORY})
    return PitchCandidate(
        index=index,
        pitch=pitch,
        reasons=tuple(blocking),
        advisories=tuple(advisories),
    )


def _cell_block(view: ShapeView, request: PlanRequestInput) -> dict[str, object]:
    """Return the code-derived description of the book a pitch must fit.

    Args:
        view: The shape view.
        request: The request side.

    Returns:
        dict[str, object]: Band, length, style, passages, endings by valence,
            and the number of on/off states.
    """
    endings: dict[str, int] = {}
    for node in view.book.nodes:
        if node.ending is not None:
            key = node.ending.valence.value
            endings[key] = endings.get(key, 0) + 1
    return {
        "age_band": request.band.value,
        "length": request.length.value,
        "narrative_style": request.style.value,
        "passages": len(view.book.nodes),
        "endings_by_valence": dict(sorted(endings.items())),
        "states": len(view.book.variables),
    }


def _decode_object(raw: str) -> tuple[dict[str, object] | None, str | None]:
    """Decode a model answer as one JSON object.

    A single surrounding markdown code fence is tolerated; nothing else is.

    Args:
        raw: The completion text (untrusted).

    Returns:
        tuple[dict[str, object] | None, str | None]: The object and None, or
            None and a short reason.
    """
    match = _FENCE_RE.match(raw)
    text = match.group("body") if match else raw
    # #CRITICAL: data-integrity: model output is untrusted; a deeply nested
    # payload raises RecursionError rather than JSONDecodeError (see
    # generation/orchestrator.py::_run_one_stage), so both are caught and the
    # answer is treated as unparseable.
    # #VERIFY: test_storyplan_generate.py::test_unparseable_plan_is_repaired.
    try:
        decoded: object = json.loads(text)  # pyright: ignore[reportAny]
    except (json.JSONDecodeError, RecursionError):
        return None, "the answer was not valid JSON"
    if not isinstance(decoded, dict):
        return None, "the answer was not a JSON object"
    return cast("dict[str, object]", decoded), None


async def generate_pitches(  # noqa: PLR0913 - keyword-only job inputs
    request: PlanRequestInput,
    view: ShapeView,
    provider: GenerationProvider,
    *,
    pii: PiiContext,
    screen: PitchScreen,
    stop_at_first_pass: bool = True,
) -> list[PitchCandidate]:
    """Ask for :data:`PITCH_COUNT` pitches and screen them in order.

    Args:
        request: The request side.
        view: The shape the book will use.
        provider: The generation provider (wrapped in the PII guard here).
        pii: The family's PII context.
        screen: The Stage 0 screen.
        stop_at_first_pass: True for on-demand jobs, which use the first pitch
            that passes; the pitches after it are recorded as not screened.
            False for a catalog caller choosing among them.

    Returns:
        list[PitchCandidate]: One entry per pitch the model returned (at most
            :data:`PITCH_COUNT`), or a single unparsed entry when the answer
            held no pitch list.

    Raises:
        ValidationError: From the PII guard, if the request carries a child
            name or PII-shaped content (no provider call is made).
    """
    guarded = PiiGuardedProvider(provider, forbidden=pii)
    prompt = build_pitch_prompt(request.brief, _cell_block(view, request))
    completion = await guarded.complete(
        system=prompt.system, prompt=prompt.user, max_tokens=_PITCH_MAX_TOKENS
    )
    decoded, problem = _decode_object(completion.text)
    raw_pitches = None if decoded is None else decoded.get("pitches")
    if not isinstance(raw_pitches, list) or not raw_pitches:
        reason = problem or "the answer held no pitches list"
        return [PitchCandidate(index=0, pitch=None, reasons=(reason,))]
    candidates: list[PitchCandidate] = []
    passed = False
    for index, raw in enumerate(cast("list[object]", raw_pitches)[:PITCH_COUNT]):
        if passed and stop_at_first_pass:
            candidates.append(
                PitchCandidate(index=index, pitch=None, reasons=("not screened",))
            )
            continue
        candidate = await _screen_pitch(
            index, raw, band=request.band, pii=pii, screen=screen
        )
        passed = passed or candidate.passed
        candidates.append(candidate)
    return candidates


# ---------------------------------------------------------------------------
# Plan, checks and repair
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlanGenerationResult:
    """What a plan job produced.

    Attributes:
        status: Where the job stopped (:data:`PlanStatus`).
        shape: The shape binding, ``{"id", "hash"}``.
        pitches: Every pitch considered, with its verdict.
        plan: The last plan that loaded, checked or not, or None.
        checks: Its SP report, or None when no plan loaded.
        load_errors: Why the last answer did not load, when it did not.
        plan_calls: Plan calls made (the first plus repairs).
        stage_log: A short trail, e.g. ``["pitch:1", "plan:errors=3", ...]``.
    """

    status: PlanStatus
    shape: dict[str, str]
    pitches: list[PitchCandidate]
    plan: StoryPlan | None = None
    checks: ValidationReport | None = None
    load_errors: list[str] = field(default_factory=list)
    plan_calls: int = 0
    stage_log: list[str] = field(default_factory=list)

    @property
    def repairs(self) -> int:
        """Return how many repair calls were made.

        Returns:
            int: Plan calls after the first.
        """
        return max(self.plan_calls - 1, 0)

    @property
    def plan_json(self) -> dict[str, object] | None:
        """Return the plan as stored (JSON mode), or None.

        Returns:
            dict[str, object] | None: ``StoryPlan.model_dump(mode="json")``.
        """
        return None if self.plan is None else self.plan.model_dump(mode="json")

    def report(self) -> dict[str, object]:
        """Return the ``GenerationJob.report`` entries for this result.

        Every key is in :data:`REPORT_KEYS`. ``story_plan_approval`` is
        ``"pending_owner"`` for a checked plan: until the WP-2.4 reviewer is
        validated, every plan goes to the owner (ADR-033 Decision 3 as
        amended), so nothing here approves a plan.

        Returns:
            dict[str, object]: The report entries.
        """
        return {
            "authoring_method": "plan_fill",
            "story_plan_status": self.status,
            "story_plan": self.plan_json,
            "story_plan_checks": None if self.checks is None else self.checks.to_dict(),
            "story_plan_load_errors": list(self.load_errors),
            "story_plan_attempts": self.plan_calls,
            "story_plan_shape": dict(self.shape),
            "story_plan_pitches": [p.to_report() for p in self.pitches],
            "story_plan_approval": (
                "pending_owner" if self.status == "checked" else "not_applicable"
            ),
        }


def _normalize(
    view: ShapeView, doc: Mapping[str, object]
) -> tuple[dict[str, object], list[str]]:
    """Keep the model sections and add the shape-derived bookkeeping.

    Sets each node's ``function`` from the shape, each thread's
    ``planting_choices`` from the choices that set its variable, and each
    choice's ``plants`` as the mirror of those. All three are properties of
    the shape, not meaning, so the model is not asked to copy them (a copy
    error would only cost a repair).

    Args:
        view: The shape view.
        doc: The model sections, already mapped to real ids.

    Returns:
        tuple[dict[str, object], list[str]]: The sections, and the names of
            any top-level keys dropped because they are not the model's to
            write.
    """
    dropped = sorted(key for key in doc if key not in _MODEL_SECTIONS)
    out = {key: doc[key] for key in _MODEL_SECTIONS if key in doc}
    nodes = out.get("nodes")
    if isinstance(nodes, dict):
        out["nodes"] = {
            node_id: (
                {
                    **cast("dict[str, object]", entry),
                    "function": view.functions[node_id],
                }
                if isinstance(entry, dict) and node_id in view.functions
                else entry
            )
            for node_id, entry in cast("dict[str, object]", nodes).items()
        }
    by_name = {variable.name: variable for variable in view.book.variables}
    planted_by: dict[str, list[str]] = {}
    threads = out.get("threads")
    if isinstance(threads, dict):
        fixed: dict[str, object] = {}
        for thread_id, thread in cast("dict[str, object]", threads).items():
            if not isinstance(thread, dict):
                fixed[thread_id] = thread
                continue
            typed = dict(cast("dict[str, object]", thread))
            variable = by_name.get(str(typed.get("variable")))
            if variable is not None:
                setters = view.setters(variable)
                typed["planting_choices"] = setters
                for choice_id in setters:
                    planted_by.setdefault(choice_id, []).append(thread_id)
            fixed[thread_id] = typed
        out["threads"] = fixed
    choices = out.get("choices")
    if isinstance(choices, dict):
        out["choices"] = {
            choice_id: (
                {
                    **cast("dict[str, object]", entry),
                    "plants": planted_by.get(choice_id, []),
                }
                if isinstance(entry, dict)
                else entry
            )
            for choice_id, entry in cast("dict[str, object]", choices).items()
        }
    return out, dropped


_PII_FEEDBACK: Final = (
    "the plan used a real person's name or personal details; invent every name"
)


def _carries_pii(sections: Mapping[str, object], pii: PiiContext) -> bool:
    """Return whether the model's plan sections hold PII.

    Args:
        sections: The model sections (real ids).
        pii: The family's PII context.

    Returns:
        bool: True when the PII guard rejects the serialized sections.
    """
    try:
        assert_prompt_pii_safe(json.dumps(sections, ensure_ascii=False), forbidden=pii)
    except ValidationError:
        return True
    return False


def _load_errors(view: ShapeView, exc: PydanticValidationError) -> list[str]:
    """Render a plan load failure as aliased messages without input values.

    Args:
        view: The shape view (for aliasing).
        exc: The Pydantic error.

    Returns:
        list[str]: ``"<location>: <message>"`` per error.
    """
    messages: list[str] = []
    for err in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in err["loc"]) or "plan"
        messages.append(view.alias_text(f"{location}: {err['msg']}"))
    return messages


def _feedback(view: ShapeView, report: ValidationReport) -> list[str]:
    """Render SP findings for a repair prompt, errors first, aliased.

    Args:
        view: The shape view.
        report: The SP report.

    Returns:
        list[str]: One line per finding, at most :data:`_MAX_FEEDBACK_LINES`
            plus a count of the rest.
    """
    ordered = [*report.errors, *report.warnings]
    lines: list[str] = []
    for finding in ordered[:_MAX_FEEDBACK_LINES]:
        data = finding.to_dict()
        parts = [f"{data['rule_id']} {data['severity']}: {data['message']}"]
        for key in ("node_id", "choice_id", "fact_id", "state", "route"):
            value = data.get(key)
            if value:
                parts.append(f"{key}={value}")
        lines.append(view.alias_text("; ".join(parts)))
    if len(ordered) > _MAX_FEEDBACK_LINES:
        lines.append(f"... and {len(ordered) - _MAX_FEEDBACK_LINES} more findings")
    return lines


def _assemble(  # noqa: PLR0913 - every argument is a distinct plan section source
    view: ShapeView,
    sections: Mapping[str, object],
    *,
    request: PlanRequestInput,
    pitch: Pitch,
    model_label: str | None,
    note: str,
) -> dict[str, object]:
    """Return a full plan document from the model sections.

    Args:
        view: The shape view.
        sections: The normalized model sections (real ids).
        request: The request side.
        pitch: The chosen pitch.
        model_label: The writer model id, for ``provenance.model``.
        note: A provenance note naming the pitch used.

    Returns:
        dict[str, object]: A document for :meth:`StoryPlan.model_validate`.
    """
    plan_request = PlanRequest(
        text=request.text,
        band=request.band,
        length=request.length,
        style=request.style,
    )
    provenance = Provenance(
        producer=_PRODUCER,
        model=model_label,
        method=_METHOD,
        shape=ShapeRef(id=view.shape_id, hash=view.shape_hash),
        authored=datetime.now(UTC).date(),
        notes=[note],
    )
    return {
        **sections,
        "plan_version": PLAN_VERSION,
        "request": plan_request.model_dump(mode="json"),
        "pitch": pitch.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
    }


def _sections_for_repair(view: ShapeView, plan: StoryPlan) -> dict[str, object]:
    """Return a loaded plan's model sections in alias form.

    Args:
        view: The shape view.
        plan: The plan.

    Returns:
        dict[str, object]: Cast to endings, keyed by aliases.
    """
    dumped = plan.model_dump(mode="json")
    return view.to_alias({key: dumped[key] for key in _MODEL_SECTIONS})


@dataclass(slots=True)
class _Attempt:
    """The state the repair loop carries between plan calls."""

    previous: dict[str, object] | None = None
    feedback: list[str] = field(default_factory=list)
    plan: StoryPlan | None = None
    checks: ValidationReport | None = None
    load_errors: list[str] = field(default_factory=list)


def _pitch_note(candidates: Sequence[PitchCandidate], chosen: PitchCandidate) -> str:
    """Return the provenance note naming the pitch the plan was built from.

    Args:
        candidates: Every pitch considered.
        chosen: The one used.

    Returns:
        str: A short note.
    """
    return f"built from {chosen.source} pitch {chosen.index + 1} of {len(candidates)}"


def _iter_plan_prompts(  # noqa: PLR0913 - keyword-only loop inputs
    view: ShapeView,
    *,
    request: PlanRequestInput,
    pitch: Pitch,
    state: _Attempt,
    max_repairs: int,
) -> Iterator[tuple[int, str, str]]:
    """Yield ``(call_number, system, user)`` for each plan call in turn.

    The generator reads ``state`` after each yield, so a repair prompt always
    carries the previous call's plan and findings.

    Args:
        view: The shape view.
        request: The request side.
        pitch: The chosen pitch.
        state: The loop state, updated by the caller between yields.
        max_repairs: Repair calls allowed after the first.

    Yields:
        tuple[int, str, str]: The call number (1-based) and the two blocks.
    """
    shape_json = json.dumps(view.render(), separators=(",", ":"))
    pitch_fields = cast("dict[str, str]", pitch.model_dump())
    first = build_plan_prompt(shape_json, pitch_fields, request.brief)
    yield 1, first.system, first.user
    for call in range(2, max_repairs + 2):
        repair = build_plan_repair_prompt(
            shape_json,
            pitch_fields,
            request.brief,
            previous_plan=(
                None
                if state.previous is None
                else json.dumps(state.previous, indent=1, ensure_ascii=False)
            ),
            findings=state.feedback,
        )
        yield call, repair.system, repair.user


async def generate_story_plan(  # noqa: PLR0913 - keyword-only job inputs
    request: PlanRequestInput,
    view: ShapeView,
    provider: GenerationProvider,
    *,
    pii: PiiContext,
    screen: PitchScreen,
    max_repairs: int = DEFAULT_MAX_REPAIRS,
    chosen_pitch: Pitch | None = None,
    model_label: str | None = None,
) -> PlanGenerationResult:
    """Run pitches, plan, checks and bounded repair for one request.

    Args:
        request: The request side.
        view: The shape (its band must be ``request.band``).
        provider: The generation provider. It is wrapped in the PII guard
            here, so every call is screened whatever the caller passed.
        pii: The family's PII context.
        screen: The Stage 0 screen for pitches.
        max_repairs: Repair calls allowed after the first plan call.
        chosen_pitch: A catalog owner's pitch; when given, no pitch call is
            made and this pitch is used (still floored by SP-9 as part of the
            plan).
        model_label: The writer model id recorded in ``provenance.model``.

    Returns:
        PlanGenerationResult: The outcome. A checked plan awaits approval; it
            is never approved here.

    Raises:
        ValidationError: From the PII guard (``field="prompt"``) when the
            request carries a child name or PII-shaped content; no provider
            call is made for the blocked prompt.
    """
    shape = {"id": view.shape_id, "hash": view.shape_hash}
    stage_log: list[str] = []
    if chosen_pitch is not None:
        candidates = [PitchCandidate(index=0, pitch=chosen_pitch, source="owner")]
    else:
        candidates = await generate_pitches(
            request, view, provider, pii=pii, screen=screen
        )
    chosen = next((c for c in candidates if c.passed), None)
    stage_log.append(f"pitch:{'none' if chosen is None else chosen.index + 1}")
    if chosen is None or chosen.pitch is None:
        _logger.info("story_plan.no_passing_pitch", shape_id=view.shape_id)
        return PlanGenerationResult(
            status="no_passing_pitch",
            shape=shape,
            pitches=candidates,
            stage_log=stage_log,
        )

    guarded = PiiGuardedProvider(provider, forbidden=pii)
    max_tokens = resolve_output_cap(
        cast("str | None", getattr(provider, "model", None)), default=_PLAN_MAX_TOKENS
    )
    state = _Attempt()
    calls = 0
    note = _pitch_note(candidates, chosen)
    for call, system, user in _iter_plan_prompts(
        view,
        request=request,
        pitch=chosen.pitch,
        state=state,
        max_repairs=max_repairs,
    ):
        calls = call
        # #CRITICAL: external-resources: each iteration is one paid provider
        # call; the loop is bounded by max_repairs + 1 calls and never retries
        # a provider error (that propagates to the worker, which records the
        # job failed). A PII hit in a repair prompt (a model-invented child
        # name echoed back) raises here the same way.
        # #VERIFY: test_storyplan_generate.py asserts the call count on the
        # exhausted path equals max_repairs + 1.
        completion = await guarded.complete(
            system=system, prompt=user, max_tokens=max_tokens
        )
        decoded, problem = _decode_object(completion.text)
        if decoded is None:
            state.previous, state.feedback = None, [problem or "unparseable"]
            state.load_errors = list(state.feedback)
            stage_log.append(f"plan:{call}:unparseable")
            continue
        sections, dropped = _normalize(view, view.to_real(decoded))
        if _carries_pii(sections, pii):
            # #CRITICAL: security: a plan is persisted and later quoted into
            # fill prompts; a family's child name or PII-shaped text the model
            # invented must not be stored, and echoing it back in a repair
            # prompt would trip the provider guard and fail the job. So the
            # answer is discarded unread and the repair asks for invented names.
            # #VERIFY: test_storyplan_generate.py::test_a_plan_naming_a_child_is_rewritten.
            state.previous = None
            state.feedback = [_PII_FEEDBACK]
            state.load_errors = [_PII_FEEDBACK]
            stage_log.append(f"plan:{call}:personal_information")
            continue
        document = _assemble(
            view,
            sections,
            request=request,
            pitch=chosen.pitch,
            model_label=model_label,
            note=note,
        )
        try:
            plan = StoryPlan.model_validate(document)
        except PydanticValidationError as exc:
            state.load_errors = _load_errors(view, exc)
            state.previous = view.to_alias(sections)
            state.feedback = [
                *(f"ignored key {key!r}: not part of your answer" for key in dropped),
                *state.load_errors,
            ][:_MAX_FEEDBACK_LINES]
            stage_log.append(f"plan:{call}:load_errors={len(state.load_errors)}")
            continue
        report = check_plan(plan, view.book)
        record = CheckRecord(
            ok=report.ok, errors=len(report.errors), warnings=len(report.warnings)
        )
        plan = plan.model_copy(
            update={"provenance": plan.provenance.model_copy(update={"checks": record})}
        )
        state.plan, state.checks, state.load_errors = plan, report, []
        stage_log.append(f"plan:{call}:errors={record.errors}")
        if report.ok:
            _logger.info(
                "story_plan.checked",
                shape_id=view.shape_id,
                plan_calls=call,
                warnings=record.warnings,
            )
            return PlanGenerationResult(
                status="checked",
                shape=shape,
                pitches=candidates,
                plan=plan,
                checks=report,
                plan_calls=call,
                stage_log=stage_log,
            )
        state.previous = _sections_for_repair(view, plan)
        state.feedback = _feedback(view, report)
    _logger.info(
        "story_plan.failed_checks",
        shape_id=view.shape_id,
        plan_calls=calls,
        loaded=state.plan is not None,
    )
    return PlanGenerationResult(
        status="failed_checks",
        shape=shape,
        pitches=candidates,
        plan=state.plan,
        checks=state.checks,
        load_errors=state.load_errors,
        plan_calls=calls,
        stage_log=stage_log,
    )
