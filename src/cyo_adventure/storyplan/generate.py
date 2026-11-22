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

Chunked writing (AL-844, AL-855)
================================

Before the first plan call the plan's output is estimated from the shape
(:func:`~cyo_adventure.storyplan.chunking.estimate_plan_size`: nodes, choices
and threads, plus a reasoning allowance) and compared with the output cap.
A plan that fits is written in one call exactly as above. A plan that does not
is written in parts: one **spine** call (cast, truth, the fact ledger,
threads, endings' gifts and a summary per scene of a partition computed from
the graph), then one call per **scene**, in reading order, each writing that
scene's node and choice entries from the spine and the facts guaranteed on
entry to the scene's boundary nodes. The parts are stitched, the shape-fixed
fields filled in, and SP-0 to SP-9 run as usual; each finding is sent back
only to the part that owns it, and each part re-written counts as one repair
against the same ``max_repairs`` budget. An answer cut off at the output cap
is never repaired as it stands: a one-call plan falls back once to chunked
writing, a cut-off scene is split in two and written again once, and a
cut-off spine is retried once asking for a shorter ledger.
``Settings.story_plan_write_mode`` forces either mode.

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
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal, TypeAlias, cast

import httpx
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.exceptions import ProviderError, ValidationError
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.pii import assert_prompt_pii_safe
from cyo_adventure.generation.prompts import (
    build_pitch_prompt,
    build_plan_chunk_prompt,
    build_plan_chunk_repair_prompt,
    build_plan_prompt,
    build_plan_repair_prompt,
    build_plan_spine_prompt,
    build_plan_spine_repair_prompt,
)
from cyo_adventure.generation.reasoning import explicit_reasoning
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
from cyo_adventure.storyplan.checks import (
    COST_REUSE_MAX,
    DENSITY_MIN_DECISION_CHOICES,
    DENSITY_MIN_NODES,
    DENSITY_RULE,
    EMPTY_NODE_SHARE_MAX,
    INTENT_REUSE_MAX,
    LEDGER_DENSITY_MIN,
    check_plan,
    plan_density,
    text_floor_violations,
)
from cyo_adventure.storyplan.chunking import (
    SPINE,
    ChunkEntries,
    PlanSizeEstimate,
    PlanWriteMode,
    Routed,
    Scene,
    boundary_nodes,
    choose_write_mode,
    entry_knowledge,
    estimate_plan_size,
    estimate_spine_size,
    owners,
    partition_scenes,
    route_findings,
    route_load_errors,
    scene_content,
    split_scene,
    stitch,
)
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
    from cyo_adventure.generation.prompts import StagePrompt
    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.generation.reasoning import ReasoningControl
    from cyo_adventure.moderation.report import Finding
    from cyo_adventure.storybook.models import Choice, Node, Variable
    from cyo_adventure.storyplan.shapes import RetainedShape
    from cyo_adventure.validator.report import ValidationReport

__all__ = [
    "DEFAULT_MAX_REPAIRS",
    "DEFAULT_REPAIR_DENSITY_WARNINGS",
    "DEFAULT_WRITE_MODE",
    "PITCH_COUNT",
    "REPORT_KEYS",
    "AttemptSummary",
    "PitchCandidate",
    "PitchScreen",
    "PlanDiff",
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

DEFAULT_REPAIR_DENSITY_WARNINGS: Final = True
"""Whether a checked plan with SP-D density warnings gets one repair (AL-848).

The repair comes out of the same ``max_repairs`` budget and is made at most
once per job. Density warnings never fail a plan: when the budget is spent,
or the repair does not load or check cleanly, the job keeps the checked plan
with its warnings recorded. ``Settings.story_plan_repair_density_warnings``
is the production switch.
"""

DEFAULT_WRITE_MODE: Final[PlanWriteMode] = "auto"
"""How a plan is written: ``auto`` decides from the size check (AL-855).

``single`` forces one call (a cut-off answer then fails the job rather than
spending a repair on an unchanged request); ``chunked`` forces the spine and
scene calls. ``Settings.story_plan_write_mode`` is the production switch.
"""

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
    "story_plan_attempt_summaries",
    "story_plan_write_mode",
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
        return {
            "start": self.node_alias[self.book.start_node],
            "states": self._states(),
            "nodes": [self._node(node) for node in self.book.nodes],
        }

    def render_scene(
        self, node_ids: Sequence[str], scene_of: Mapping[str, str]
    ) -> dict[str, object]:
        """Return one scene's slice of :meth:`render`, for a chunk call.

        Each node is rendered as in :meth:`render`, plus ``from`` (the aliases
        of the nodes with a choice into it). A choice whose target lies in
        another scene gains ``to_scene``. Only the states one of the scene's
        choices or ``on_enter`` effects sets or tests are listed.

        Args:
            node_ids: The scene's real node ids, in reading order.
            scene_of: Real node id to its scene id.

        Returns:
            dict[str, object]: ``start`` (only when the start node is in the
                scene), ``states`` and ``nodes``.
        """
        inside = set(node_ids)
        by_id = {node.id: node for node in self.book.nodes}
        preds: dict[str, list[str]] = {}
        for node in self.book.nodes:
            for choice in node.choices:
                sources = preds.setdefault(choice.target, [])
                if node.id not in sources:
                    sources.append(node.id)
        nodes: list[dict[str, object]] = []
        used: set[str] = set()
        for node_id in node_ids:
            node = by_id[node_id]
            rendered = self._node(node)
            rendered["from"] = [self.node_alias[p] for p in preds.get(node_id, [])]
            for choice, entry in zip(
                node.choices,
                cast("list[dict[str, object]]", rendered.get("choices", [])),
                strict=True,
            ):
                if choice.target not in inside and choice.target in scene_of:
                    entry["to_scene"] = scene_of[choice.target]
                used.add(choice.id)
            nodes.append(rendered)
        aliases = {self.choice_alias[c] for c in used}
        states = [
            state
            for state in self._states()
            if aliases & set(cast("list[str]", state["set_by"]))
            or aliases & set(cast("list[str]", state["tested_by"]))
        ]
        out: dict[str, object] = {}
        if self.book.start_node in inside:
            out["start"] = self.node_alias[self.book.start_node]
        out["states"] = states
        out["nodes"] = nodes
        return out

    def _states(self) -> list[dict[str, object]]:
        """Render every declared state with its setters and testers, aliased.

        Returns:
            list[dict[str, object]]: One entry per variable, in book order.
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
        return states

    def _node(self, node: Node) -> dict[str, object]:
        """Render one node as :meth:`render` lists it.

        Args:
            node: The node.

        Returns:
            dict[str, object]: Alias, function, words, and when present its
                ``on_enter`` effects, ending and choices.
        """
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
        return rendered

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


def _pair_key(pair: frozenset[str]) -> str:
    """Render a contradiction pair as ``"a|b"``, sorted.

    Args:
        pair: The two fact ids.

    Returns:
        str: The pair key.
    """
    return "|".join(sorted(pair))


def _fact_uses(plan: StoryPlan) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    """Return every node's and choice's ``(requires, establishes)``, sorted.

    Args:
        plan: The plan.

    Returns:
        dict[str, tuple[tuple[str, ...], tuple[str, ...]]]: Keyed by
            ``node:<id>`` and ``choice:<id>``.
    """
    uses: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
        f"node:{node_id}": (
            tuple(sorted(node.requires)),
            tuple(sorted(node.establishes)),
        )
        for node_id, node in plan.nodes.items()
    }
    uses.update(
        {
            f"choice:{choice_id}": (
                tuple(sorted(choice.requires)),
                tuple(sorted(choice.establishes)),
            )
            for choice_id, choice in plan.choices.items()
        }
    )
    return uses


@dataclass(frozen=True, slots=True)
class PlanDiff:
    """What changed in the fact ledger between two loaded plan attempts.

    Compact on purpose (AL-850): enough to see what a repair did to the
    ledger, not a full plan diff.

    Attributes:
        facts_added: Fact ids in the later plan only, sorted.
        facts_removed: Fact ids in the earlier plan only, sorted.
        contradicts_added: Contradiction pairs (``"a|b"``) in the later plan only.
        contradicts_removed: Contradiction pairs in the earlier plan only.
        fact_uses_changed: How many nodes and choices changed their
            ``requires`` or ``establishes``.
    """

    facts_added: tuple[str, ...]
    facts_removed: tuple[str, ...]
    contradicts_added: tuple[str, ...]
    contradicts_removed: tuple[str, ...]
    fact_uses_changed: int

    @classmethod
    def between(cls, before: StoryPlan, after: StoryPlan) -> PlanDiff:
        """Compare two plans' ledgers.

        Args:
            before: The earlier attempt's plan.
            after: The later attempt's plan.

        Returns:
            PlanDiff: The ledger changes.
        """
        old_pairs = {_pair_key(p) for p in before.contradiction_pairs()}
        new_pairs = {_pair_key(p) for p in after.contradiction_pairs()}
        old_uses, new_uses = _fact_uses(before), _fact_uses(after)
        return cls(
            facts_added=tuple(sorted(set(after.facts) - set(before.facts))),
            facts_removed=tuple(sorted(set(before.facts) - set(after.facts))),
            contradicts_added=tuple(sorted(new_pairs - old_pairs)),
            contradicts_removed=tuple(sorted(old_pairs - new_pairs)),
            fact_uses_changed=sum(
                1
                for key in old_uses.keys() | new_uses.keys()
                if old_uses.get(key) != new_uses.get(key)
            ),
        )

    @property
    def only_removed_marks(self) -> bool:
        """Return whether the repair's only ledger change was dropping marks.

        This is the AL-849 pattern: an SP-3 finding cleared by deleting a
        ``contradicts`` mark rather than by changing the story.

        Returns:
            bool: True when marks were removed and no fact, no other mark and
                no node or choice fact list changed.
        """
        return bool(self.contradicts_removed) and not (
            self.facts_added
            or self.facts_removed
            or self.contradicts_added
            or self.fact_uses_changed
        )

    def to_dict(self) -> dict[str, object]:
        """Return the diff as a JSON-serialisable mapping.

        Returns:
            dict[str, object]: The five fields plus ``only_removed_marks``.
        """
        return {
            "facts_added": list(self.facts_added),
            "facts_removed": list(self.facts_removed),
            "contradicts_added": list(self.contradicts_added),
            "contradicts_removed": list(self.contradicts_removed),
            "fact_uses_changed": self.fact_uses_changed,
            "only_removed_marks": self.only_removed_marks,
        }


AttemptOutcome = Literal[
    "unparseable",
    "personal_information",
    "load_errors",
    "checked",
    "failed_checks",
    "truncated",
]
"""What one plan call (or, in chunked mode, one stitched round) produced.

``truncated``: the answer stopped at the output cap or held no content; it is
never repaired as it stands (AL-855).
"""


def _counts_by_rule(findings: Sequence[object]) -> dict[str, int]:
    """Count findings by their ``rule_id``, in sorted rule order.

    Args:
        findings: Validation findings.

    Returns:
        dict[str, int]: Rule id to count.
    """
    counts: dict[str, int] = {}
    for finding in findings:
        rule = str(getattr(finding, "rule_id", "?"))
        counts[rule] = counts.get(rule, 0) + 1
    return dict(sorted(counts.items()))


@dataclass(frozen=True, slots=True)
class AttemptSummary:
    """One plan call's outcome, kept for every attempt (AL-850).

    Attributes:
        call: The plan call number, 1-based (1 is the first plan call).
        outcome: What the call produced (:data:`AttemptOutcome`).
        errors_by_rule: SP ERROR counts by rule; empty when the plan did not
            load.
        warnings_by_rule: SP WARNING counts by rule.
        load_errors: How many load errors, when the plan did not load.
        repair: Why the next call was made: ``"errors"`` (did not load, or
            had an ERROR), ``"density"`` (a checked plan with SP-D warnings,
            AL-848) or None when no further call followed.
        diff: The ledger change from the previous attempt that loaded, or
            None for the first plan that loads (or one that does not).
        density: :func:`~cyo_adventure.storyplan.checks.plan_density` of the
            loaded plan, or None.
        mode: ``single`` (one summary per plan call) or ``chunked`` (one
            summary per stitched round; ``call`` is then the running count of
            plan calls at that round).
        parts: In chunked mode, the parts written in this round (``spine``,
            ``S1`` ...); empty in single mode.
        truncated: In chunked mode, the parts whose answer was cut off in this
            round (each was split or retried, never repaired as it stood).
    """

    call: int
    outcome: AttemptOutcome
    errors_by_rule: dict[str, int] = field(default_factory=dict)
    warnings_by_rule: dict[str, int] = field(default_factory=dict)
    load_errors: int = 0
    repair: Literal["errors", "density"] | None = None
    diff: PlanDiff | None = None
    density: dict[str, object] | None = None
    mode: Literal["single", "chunked"] = "single"
    parts: tuple[str, ...] = ()
    truncated: tuple[str, ...] = ()

    @property
    def loaded(self) -> bool:
        """Return whether the attempt's plan loaded and was checked.

        Returns:
            bool: True for ``checked`` and ``failed_checks``.
        """
        return self.outcome in {"checked", "failed_checks"}

    def to_report(self) -> dict[str, object]:
        """Return the attempt's report entry.

        Returns:
            dict[str, object]: Every field, ``loaded`` included, JSON-ready.
        """
        return {
            "call": self.call,
            "outcome": self.outcome,
            "loaded": self.loaded,
            "errors_by_rule": dict(self.errors_by_rule),
            "warnings_by_rule": dict(self.warnings_by_rule),
            "load_errors": self.load_errors,
            "repair": self.repair,
            "diff": None if self.diff is None else self.diff.to_dict(),
            "density": None if self.density is None else dict(self.density),
            "mode": self.mode,
            "parts": list(self.parts),
            "truncated": list(self.truncated),
        }


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
        attempts: One summary per plan call, in order (AL-850); in chunked
            mode one per stitched round.
        write_mode: The size check and the write decision
            (``story_plan_write_mode`` on the job report): the setting, the
            mode used and why, the estimates, the scene partition, any
            fallback and any split. Empty when no plan was attempted.
        repair_calls: Repair calls made, when not simply ``plan_calls - 1``
            (chunked mode, where the spine and every scene are first calls).
    """

    status: PlanStatus
    shape: dict[str, str]
    pitches: list[PitchCandidate]
    plan: StoryPlan | None = None
    checks: ValidationReport | None = None
    load_errors: list[str] = field(default_factory=list)
    plan_calls: int = 0
    stage_log: list[str] = field(default_factory=list)
    attempts: list[AttemptSummary] = field(default_factory=list)
    write_mode: dict[str, object] = field(default_factory=dict)
    repair_calls: int | None = None

    @property
    def repairs(self) -> int:
        """Return how many repair calls were made.

        Returns:
            int: :attr:`repair_calls` when set, else plan calls after the first.
        """
        if self.repair_calls is not None:
            return self.repair_calls
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
            "story_plan_attempt_summaries": [a.to_report() for a in self.attempts],
            "story_plan_write_mode": dict(self.write_mode),
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
    """The state the repair loop carries between plan calls.

    ``plan`` and ``checks`` are the last plan that loaded; ``best`` is the
    last plan that loaded with no ERROR, kept when a density repair (AL-848)
    is attempted so that a repair which fails cannot cost the job its checked
    plan; ``summaries`` is one entry per call (AL-850).
    """

    previous: dict[str, object] | None = None
    feedback: list[str] = field(default_factory=list)
    plan: StoryPlan | None = None
    checks: ValidationReport | None = None
    load_errors: list[str] = field(default_factory=list)
    best: tuple[StoryPlan, ValidationReport] | None = None
    density_repaired: bool = False
    summaries: list[AttemptSummary] = field(default_factory=list)

    def record(
        self,
        call: int,
        outcome: AttemptOutcome,
        *,
        loaded: tuple[StoryPlan, ValidationReport, dict[str, object] | None]
        | None = None,
    ) -> None:
        """Append the summary of one plan call.

        Call it before ``plan`` is updated, so the diff is against the
        previous attempt that loaded.

        Args:
            call: The call number.
            outcome: What it produced.
            loaded: The plan, its SP report and its density metrics, when the
                answer loaded.
        """
        plan, report, density = loaded if loaded is not None else (None, None, None)
        diff = (
            None
            if plan is None or self.plan is None
            else PlanDiff.between(self.plan, plan)
        )
        self.summaries.append(
            AttemptSummary(
                call=call,
                outcome=outcome,
                errors_by_rule={} if report is None else _counts_by_rule(report.errors),
                warnings_by_rule=(
                    {} if report is None else _counts_by_rule(report.warnings)
                ),
                load_errors=0 if plan is not None else len(self.load_errors),
                diff=diff,
                density=density,
            )
        )

    def denser(
        self, plan: StoryPlan, report: ValidationReport
    ) -> tuple[StoryPlan, ValidationReport]:
        """Return the checked plan to keep: this one, unless it is thinner.

        After a density repair that checked cleanly, the repaired plan is
        kept unless it has more SP-D warnings than the plan it repaired.

        Args:
            plan: A plan with no SP ERROR.
            report: Its SP report.

        Returns:
            tuple[StoryPlan, ValidationReport]: The plan to keep and its report.
        """
        if self.best is not None and _density_findings(report) > _density_findings(
            self.best[1]
        ):
            return self.best
        return plan, report

    def take_density_repair(
        self,
        plan: StoryPlan,
        report: ValidationReport,
        *,
        enabled: bool,
        has_next: bool,
    ) -> bool:
        """Decide whether a checked plan gets its one density repair (AL-848).

        When it does, the plan is kept in ``best`` and the attempt is marked.

        Args:
            plan: A plan with no SP ERROR.
            report: Its SP report.
            enabled: The ``repair_density_warnings`` setting.
            has_next: Whether the repair budget allows another call.

        Returns:
            bool: True when the next call is a density repair.
        """
        if not (
            enabled
            and has_next
            and not self.density_repaired
            and _density_findings(report)
        ):
            return False
        self.best = (plan, report)
        self.density_repaired = True
        self.mark_repair("density")
        return True

    def mark_repair(self, reason: Literal["errors", "density"]) -> None:
        """Note why the next call is made, on the last summary.

        Args:
            reason: ``"errors"`` or ``"density"``.
        """
        if self.summaries:
            self.summaries[-1] = replace(self.summaries[-1], repair=reason)


def _density_findings(report: ValidationReport) -> int:
    """Count a report's SP-D warnings.

    Args:
        report: The SP report.

    Returns:
        int: How many density warnings it holds.
    """
    return sum(1 for f in report.warnings if f.rule_id == DENSITY_RULE)


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
    repair_density_warnings: bool = DEFAULT_REPAIR_DENSITY_WARNINGS,
    reasoning: ReasoningControl | None = None,
    write_mode: PlanWriteMode = DEFAULT_WRITE_MODE,
) -> PlanGenerationResult:
    """Run pitches, plan, checks and bounded repair for one request.

    Args:
        request: The request side.
        view: The shape (its band must be ``request.band``).
        provider: The generation provider. It is wrapped in the PII guard
            here, so every call is screened whatever the caller passed.
        pii: The family's PII context.
        screen: The Stage 0 screen for pitches.
        max_repairs: Repair calls allowed after the first plan call. In
            chunked mode each part re-written (the spine or one scene) counts
            as one repair.
        chosen_pitch: A catalog owner's pitch; when given, no pitch call is
            made and this pitch is used (still floored by SP-9 as part of the
            plan).
        model_label: The writer model id recorded in ``provenance.model``.
        repair_density_warnings: When True, a checked plan with SP-D density
            warnings gets one repair from the same budget
            (:data:`DEFAULT_REPAIR_DENSITY_WARNINGS`). The job still ends
            ``checked`` when that repair cannot be made or does not check
            cleanly; warnings never fail a plan.
        reasoning: The explicit reasoning setting every pitch and plan call
            sends on OpenRouter (AL-847), applied through
            :func:`~cyo_adventure.generation.reasoning.explicit_reasoning`
            so it reaches the adapter through any wrapper or cascade. None
            leaves each leg's own setting. The worker passes the
            ``Settings.story_plan_reasoning_*`` values.
        write_mode: ``auto`` (the size check decides), ``single`` or
            ``chunked`` (:data:`DEFAULT_WRITE_MODE`); the worker passes
            ``Settings.story_plan_write_mode``.

    Returns:
        PlanGenerationResult: The outcome. A checked plan awaits approval; it
            is never approved here. ``attempts`` summarises every plan call
            (every stitched round in chunked mode) and ``write_mode`` records
            the size check.

    Raises:
        ValidationError: From the PII guard (``field="prompt"``) when the
            request carries a child name or PII-shaped content; no provider
            call is made for the blocked prompt.
    """
    inputs = _JobInputs(
        pii=pii,
        screen=screen,
        max_repairs=max_repairs,
        chosen_pitch=chosen_pitch,
        model_label=model_label,
        repair_density_warnings=repair_density_warnings,
        write_mode=write_mode,
    )
    if reasoning is None:
        return await _generate_story_plan(request, view, provider, inputs)
    # #CRITICAL: payment/financial: the reasoning setting decides how many
    # paid reasoning tokens each call may spend (AL-847); it is scoped to this
    # job's calls by a ContextVar and reset when the block exits.
    # #VERIFY: test_storyplan_generate.py::
    # test_every_plan_job_call_carries_the_explicit_reasoning_setting.
    with explicit_reasoning(reasoning):
        return await _generate_story_plan(request, view, provider, inputs)


@dataclass(frozen=True, slots=True)
class _JobInputs:
    """The keyword-only inputs of :func:`generate_story_plan`, passed through."""

    pii: PiiContext
    screen: PitchScreen
    max_repairs: int
    chosen_pitch: Pitch | None
    model_label: str | None
    repair_density_warnings: bool
    write_mode: PlanWriteMode = DEFAULT_WRITE_MODE


@dataclass(frozen=True, slots=True)
class _PlanParts:
    """What every plan attempt is assembled from, besides the model's answer."""

    request: PlanRequestInput
    pitch: Pitch
    model_label: str | None
    note: str
    pii: PiiContext


@dataclass(slots=True)
class _PlanJob:
    """One plan job's fixed inputs and the state both write modes share."""

    view: ShapeView
    candidates: list[PitchCandidate]
    guarded: PiiGuardedProvider
    max_tokens: int
    parts: _PlanParts
    inputs: _JobInputs
    state: _Attempt = field(default_factory=_Attempt)
    stage_log: list[str] = field(default_factory=list)
    calls: int = 0

    @property
    def pitch_fields(self) -> dict[str, str]:
        """Return the chosen pitch's five fields.

        Returns:
            dict[str, str]: The pitch as the prompts carry it.
        """
        return cast("dict[str, str]", self.parts.pitch.model_dump())


@dataclass(slots=True)
class _WriteLog:
    """The size check and write decision, for ``story_plan_write_mode``."""

    setting: PlanWriteMode
    mode: Literal["single", "chunked"]
    reason: str
    estimate: PlanSizeEstimate
    spine: PlanSizeEstimate | None = None
    scenes: list[dict[str, object]] = field(default_factory=list)
    fallback: bool = False
    splits: list[str] = field(default_factory=list)

    def to_report(self) -> dict[str, object]:
        """Return the decision as a JSON-serialisable mapping.

        Returns:
            dict[str, object]: Setting, mode, reason, estimates, scenes,
                fallback and splits.
        """
        return {
            "setting": self.setting,
            "mode": self.mode,
            "reason": self.reason,
            "estimate": self.estimate.to_dict(),
            "spine_estimate": None if self.spine is None else self.spine.to_dict(),
            "scenes": [dict(scene) for scene in self.scenes],
            "fallback": self.fallback,
            "splits": list(self.splits),
        }


_TRUNCATED_FEEDBACK: Final = "the answer was cut off at the output limit"
_LENGTH_STOP_MARKER: Final = "finish_reason=length"


def _is_length_stop(exc: BaseException) -> bool:
    """Return whether a provider error is an empty answer stopped at the cap.

    Args:
        exc: The provider error.

    Returns:
        bool: True when it, or an error it was raised from, names a
            ``finish_reason=length`` stop.
    """
    # #ASSUME: external-resources: the OpenRouter and Modal adapters raise a
    # leg-fatal ProviderError whose message names "finish_reason=length" for
    # an EMPTY body at the cap (providers/openrouter.py
    # _empty_content_message); a FallbackProvider re-raises "all legs
    # exhausted" from it, so the cause chain is walked. A truncated NON-empty
    # body arrives as an ordinary Completion with finish_reason "length".
    # #VERIFY: test_storyplan_chunked.py::
    # test_a_length_stop_provider_error_counts_as_truncation.
    current: BaseException | None = exc
    seen = 0
    while current is not None and seen < 8:
        if _LENGTH_STOP_MARKER in str(current):
            return True
        current = current.__cause__
        seen += 1
    return False


async def _complete(job: _PlanJob, system: str, user: str) -> str | None:
    """Make one plan-model call; None when the answer was cut off or empty.

    Args:
        job: The plan job.
        system: The system block.
        user: The user block.

    Returns:
        str | None: The answer text, or None for a truncated answer (stopped
            at ``max_tokens``, or no content).

    Raises:
        ProviderError: Any provider failure other than a length stop. The
            PII guard's ValidationError propagates unchanged as well.
    """
    # #CRITICAL: payment/financial: a truncated answer parses as nothing, and
    # repairing it with an unchanged request buys the same wall at the same
    # cap (AL-329, AL-855); it is reported as None so the caller changes the
    # request (falls back to chunks, splits the scene) instead of repairing.
    # #VERIFY: test_storyplan_chunked.py::
    # test_a_truncated_single_call_falls_back_to_chunks_once.
    try:
        completion = await job.guarded.complete(
            system=system, prompt=user, max_tokens=job.max_tokens
        )
    except ProviderError as exc:
        if _is_length_stop(exc):
            return None
        raise
    if completion.finish_reason == "length" or not completion.text.strip():
        return None
    return completion.text


async def _generate_story_plan(
    request: PlanRequestInput,
    view: ShapeView,
    provider: GenerationProvider,
    inputs: _JobInputs,
) -> PlanGenerationResult:
    """Run one plan job; see :func:`generate_story_plan`.

    Args:
        request: The request side.
        view: The shape.
        provider: The generation provider.
        inputs: The job's keyword inputs.

    Returns:
        PlanGenerationResult: The outcome.
    """
    pii, screen = inputs.pii, inputs.screen
    chosen_pitch = inputs.chosen_pitch
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

    max_tokens = resolve_output_cap(
        cast("str | None", getattr(provider, "model", None)), default=_PLAN_MAX_TOKENS
    )
    estimate = estimate_plan_size(view.book, cap=max_tokens)
    mode, reason = choose_write_mode(inputs.write_mode, estimate)
    write = _WriteLog(
        setting=inputs.write_mode, mode=mode, reason=reason, estimate=estimate
    )
    _logger.info(
        "story_plan.write_mode",
        shape_id=view.shape_id,
        setting=inputs.write_mode,
        mode=mode,
        estimate_tokens=estimate.total,
        budget=estimate.budget,
        cap=max_tokens,
    )
    job = _PlanJob(
        view=view,
        candidates=candidates,
        guarded=PiiGuardedProvider(provider, forbidden=pii),
        max_tokens=max_tokens,
        parts=_PlanParts(
            request,
            chosen.pitch,
            inputs.model_label,
            _pitch_note(candidates, chosen),
            pii,
        ),
        inputs=inputs,
        stage_log=stage_log,
    )
    if mode == "single":
        result = await _run_single(job, allow_fallback=inputs.write_mode == "auto")
        if result is not None:
            return replace(result, write_mode=write.to_report())
        # #ASSUME: payment/financial: the cut-off call is not repaired; the
        # chunked run that replaces it inherits the repairs already spent, so
        # the job's repair budget is the same in both modes.
        # #VERIFY: test_storyplan_chunked.py::
        # test_a_truncated_single_call_falls_back_to_chunks_once.
        write.mode, write.fallback = "chunked", True
        write.reason = f"{reason}; the single call was cut off, fell back to chunks"
        stage_log.append("plan:fallback=chunked")
        _logger.info("story_plan.fallback_chunked", shape_id=view.shape_id)
    runner = _ChunkedRun(job=job, write=write, repairs=max(job.calls - 1, 0))
    return await runner.run()


async def _run_single(
    job: _PlanJob, *, allow_fallback: bool
) -> PlanGenerationResult | None:
    """Write the plan in one call with bounded whole-plan repair.

    Args:
        job: The plan job.
        allow_fallback: Whether a cut-off answer hands over to chunked writing.

    Returns:
        PlanGenerationResult | None: The outcome, or None when an answer was
            cut off and ``allow_fallback`` is set (the caller writes in chunks).
    """
    view, state, stage_log = job.view, job.state, job.stage_log
    max_repairs = job.inputs.max_repairs
    calls = 0
    for call, system, user in _iter_plan_prompts(
        view,
        request=job.parts.request,
        pitch=job.parts.pitch,
        state=state,
        max_repairs=max_repairs,
    ):
        calls = job.calls = call
        # #CRITICAL: external-resources: each iteration is one paid provider
        # call; the loop is bounded by max_repairs + 1 calls and never retries
        # a provider error (that propagates to the worker, which records the
        # job failed). A PII hit in a repair prompt (a model-invented child
        # name echoed back) raises here the same way.
        # #VERIFY: test_storyplan_generate.py asserts the call count on the
        # exhausted path equals max_repairs + 1.
        text = await _complete(job, system, user)
        has_next = call <= max_repairs
        if text is None:
            state.load_errors = [_TRUNCATED_FEEDBACK]
            state.record(call, "truncated")
            stage_log.append(f"plan:{call}:truncated")
            if allow_fallback:
                return None
            # A forced single call is never repaired with the same request.
            break
        loaded = _load_plan(view, text, job.parts, state, call, stage_log)
        if loaded is None:
            if has_next:
                state.mark_repair("errors")
            continue
        plan, report = _check_attempt(view, loaded, state, call, stage_log)
        if not report.ok:
            state.previous = _sections_for_repair(view, plan)
            state.feedback = _feedback(view, report)
            if has_next:
                state.mark_repair("errors")
            continue
        plan, report = state.denser(plan, report)
        # #ASSUME: payment/financial: a density repair is one more paid call,
        # taken only from the remaining max_repairs budget and at most once
        # per job (AL-848); the checked plan is kept in state.best so a failed
        # repair cannot cost the job its plan.
        # #VERIFY: test_storyplan_generate.py::
        # test_density_warnings_get_one_repair_within_the_budget and
        # ::test_a_failed_density_repair_keeps_the_checked_plan.
        if state.take_density_repair(
            plan,
            report,
            enabled=job.inputs.repair_density_warnings,
            has_next=has_next,
        ):
            state.previous = _sections_for_repair(view, plan)
            state.feedback = _feedback(view, report)
            stage_log.append(f"plan:{call}:density_repair={_density_findings(report)}")
            continue
        return _checked(view, job.candidates, plan, report, call, stage_log, state)
    return _unfinished(job, calls)


def _unfinished(job: _PlanJob, calls: int) -> PlanGenerationResult:
    """Return the result when the budget ran out without a final checked plan.

    Args:
        job: The plan job.
        calls: Plan calls made in all.

    Returns:
        PlanGenerationResult: ``checked`` with the kept plan when a density
            repair did not check cleanly, else ``failed_checks``.
    """
    view, state, stage_log = job.view, job.state, job.stage_log
    if state.best is not None:
        # Warnings never fail a plan: the density repair did not check
        # cleanly within the budget, so the job keeps the checked plan.
        best_plan, best_report = state.best
        stage_log.append("plan:kept_checked")
        return _checked(
            view, job.candidates, best_plan, best_report, calls, stage_log, state
        )
    _logger.info(
        "story_plan.failed_checks",
        shape_id=view.shape_id,
        plan_calls=calls,
        loaded=state.plan is not None,
    )
    return PlanGenerationResult(
        status="failed_checks",
        shape={"id": view.shape_id, "hash": view.shape_hash},
        pitches=job.candidates,
        plan=state.plan,
        checks=state.checks,
        load_errors=state.load_errors,
        plan_calls=calls,
        stage_log=stage_log,
        attempts=list(state.summaries),
    )


# ---------------------------------------------------------------------------
# Chunked writing (AL-844, AL-855)
# ---------------------------------------------------------------------------


def _real_load_errors(exc: PydanticValidationError) -> list[str]:
    """Render a plan load failure as real-id messages without input values.

    Args:
        exc: The Pydantic error.

    Returns:
        list[str]: ``"<location>: <message>"`` per error (aliased only when
            fed back to the model).
    """
    return [
        f"{'.'.join(str(part) for part in err['loc']) or 'plan'}: {err['msg']}"
        for err in exc.errors(include_input=False, include_url=False)
    ]


def _str_list(value: object) -> list[str]:
    """Return the strings in a list value, or an empty list.

    Args:
        value: A JSON value.

    Returns:
        list[str]: Its string items.
    """
    if not isinstance(value, list):
        return []
    return [v for v in cast("list[object]", value) if isinstance(v, str)]


def _establishes_of(section: object) -> dict[str, list[str]]:
    """Return each entry's ``establishes`` list from a nodes or choices section.

    Args:
        section: An id-keyed section.

    Returns:
        dict[str, list[str]]: Entry id to its established fact ids.
    """
    if not isinstance(section, dict):
        return {}
    return {
        key: _str_list(cast("dict[str, object]", entry).get("establishes"))
        for key, entry in cast("dict[str, object]", section).items()
        if isinstance(entry, dict)
    }


def _subset(entries: ChunkEntries, scene: Scene, view: ShapeView) -> ChunkEntries:
    """Return the entries a half of a split scene owns.

    Args:
        entries: The whole scene's entries.
        scene: The half.
        view: The shape view.

    Returns:
        ChunkEntries: Its nodes and choices; every proposed fact is kept.
    """
    inside = set(scene.nodes)
    choices = {
        c.id for node in view.book.nodes if node.id in inside for c in node.choices
    }
    return ChunkEntries(
        nodes={k: v for k, v in entries.nodes.items() if k in inside},
        choices={k: v for k, v in entries.choices.items() if k in choices},
        new_facts=dict(entries.new_facts),
    )


@dataclass(slots=True)
class _ChunkedRun:
    """The spine, the scenes and the routed repairs of one chunked plan job.

    Scenes are written one after another, in reading order, not in
    parallel: a scene's boundary facts are computed from what the earlier
    scenes actually established (:func:`entry_knowledge`), and the ledger it
    reads includes the facts they proposed, so it can reuse their ids instead
    of inventing colliding ones. A parallel run could only give every scene
    the spine's ledger and no boundary facts beyond it, which is what makes
    SP-2 merge-closure findings at scene boundaries likely. The cost is
    latency (one call after another), which a background job can afford.
    """

    job: _PlanJob
    write: _WriteLog
    repairs: int = 0
    scenes: list[Scene] = field(default_factory=list)
    spine: dict[str, object] | None = None
    summaries: dict[str, object] = field(default_factory=dict)
    entries: dict[str, ChunkEntries] = field(default_factory=dict)
    pending: list[Routed] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    truncated: list[str] = field(default_factory=list)
    frozen: set[str] = field(default_factory=set)
    failed: str | None = None
    _shape_json: str = ""

    # -- calls ---------------------------------------------------------------

    def _budget_left(self) -> int:
        """Return how many repair calls the budget still allows.

        Returns:
            int: ``max_repairs`` less the repairs made (never negative).
        """
        return max(self.job.inputs.max_repairs - self.repairs, 0)

    async def _call(self, prompt: StagePrompt, part: str) -> str | None:
        """Make one part's call, logging it.

        Args:
            prompt: The part's prompt.
            part: ``spine`` or the scene id.

        Returns:
            str | None: The answer, or None when it was cut off.
        """
        self.job.calls += 1
        self.written.append(part)
        self.job.stage_log.append(f"plan:{self.job.calls}:write={part}")
        text = await _complete(self.job, prompt.system, prompt.user)
        if text is None:
            self.truncated.append(part)
            self.job.stage_log.append(f"plan:{self.job.calls}:truncated={part}")
        return text

    # -- payloads ------------------------------------------------------------

    def _scenes_json(self) -> str:
        """Return the partition in alias form, JSON.

        Returns:
            str: Scene id to its node aliases.
        """
        view = self.job.view
        return json.dumps(
            {s.id: [view.node_alias[n] for n in s.nodes] for s in self.scenes},
            separators=(",", ":"),
        )

    def _stitched(self, exclude: str | None = None) -> dict[str, object]:
        """Return the stitched sections, optionally leaving one scene out.

        Args:
            exclude: A scene id to leave out.

        Returns:
            dict[str, object]: The model sections (real ids).
        """
        chunks = [
            (scene, self.entries.get(scene.id))
            for scene in self.scenes
            if scene.id != exclude
        ]
        return stitch(self.spine or {}, chunks).sections

    def _spine_alias(self) -> dict[str, object]:
        """Return the spine as the spine writer wrote it, in alias form.

        Returns:
            dict[str, object]: The spine sections plus ``scenes``.
        """
        return {**self.job.view.to_alias(self.spine or {}), "scenes": self.summaries}

    def _spine_payload(self) -> dict[str, object]:
        """Return what a scene writer reads: the spine with the current ledger.

        Returns:
            dict[str, object]: Cast, truth, the ledger (the spine's facts plus
                every fact a scene has proposed so far), threads, endings and
                the scene summaries, in alias form.
        """
        spine = self.spine or {}
        sections = {
            key: spine[key]
            for key in ("cast", "truth", "threads", "endings")
            if key in spine
        }
        sections["facts"] = self._stitched()["facts"]
        return {**self.job.view.to_alias(sections), "scenes": self.summaries}

    def _entry_payload(self, scene: Scene) -> dict[str, list[str]]:
        """Return the facts guaranteed on entry to the scene's boundary nodes.

        Computed from every other scene's current entries, so on a first
        write it reflects the scenes written before this one.

        Args:
            scene: The scene.

        Returns:
            dict[str, list[str]]: Boundary node alias to sorted fact ids.
        """
        view = self.job.view
        others = self._stitched(exclude=scene.id)
        entry = entry_knowledge(
            view.book,
            _establishes_of(others.get("nodes")),
            _establishes_of(others.get("choices")),
        )
        return {
            view.node_alias[node_id]: sorted(entry.get(node_id, frozenset()))
            for node_id in boundary_nodes(view.book, scene)
        }

    def _feedback_lines(self, routed: Sequence[Routed]) -> list[str]:
        """Alias a part's routed lines, errors first, capped.

        Args:
            routed: The part's lines.

        Returns:
            list[str]: At most :data:`_MAX_FEEDBACK_LINES` lines plus a count.
        """
        ordered = [r for r in routed if r.error] + [r for r in routed if not r.error]
        lines = [
            self.job.view.alias_text(r.line) for r in ordered[:_MAX_FEEDBACK_LINES]
        ]
        if len(ordered) > _MAX_FEEDBACK_LINES:
            lines.append(f"... and {len(ordered) - _MAX_FEEDBACK_LINES} more findings")
        return lines

    # -- the spine -----------------------------------------------------------

    def _accept_spine(self, text: str) -> list[str]:
        """Decode and screen a spine answer; keep it when it is usable.

        Args:
            text: The answer.

        Returns:
            list[str]: Why it was not kept; empty when it was.
        """
        decoded, problem = _decode_object(text)
        if decoded is None:
            return [problem or "unparseable"]
        real = self.job.view.to_real(decoded)
        if not isinstance(real.get("facts"), dict):
            return ["the spine must have a facts object"]
        if _carries_pii(real, self.job.parts.pii):
            # #CRITICAL: security: the spine is quoted into every scene
            # prompt; a child name the model invented must not reach one
            # (the provider guard would fail the job), so it is discarded.
            # #VERIFY: test_storyplan_chunked.py::
            # test_a_spine_naming_a_child_is_rewritten.
            return [_PII_FEEDBACK]
        self.spine = {
            key: real[key]
            for key in ("cast", "truth", "facts", "threads", "endings")
            if key in real
        }
        scenes = real.get("scenes")
        self.summaries = (
            dict(cast("dict[str, object]", scenes)) if isinstance(scenes, dict) else {}
        )
        return []

    async def _write_spine(self, feedback: Sequence[Routed] | None = None) -> None:
        """Write (or repair) the spine; a cut-off first spine is retried once.

        Args:
            feedback: The spine's routed findings for a repair, or None.
        """
        job = self.job
        pitch, brief = job.pitch_fields, job.parts.request.brief
        if feedback is None:
            prompt = build_plan_spine_prompt(
                self._shape_json, self._scenes_json(), pitch, brief
            )
        else:
            prompt = build_plan_spine_repair_prompt(
                self._shape_json,
                self._scenes_json(),
                pitch,
                brief,
                previous=(
                    None
                    if self.spine is None
                    else json.dumps(self._spine_alias(), indent=1, ensure_ascii=False)
                ),
                findings=self._feedback_lines(feedback),
            )
        text = await self._call(prompt, SPINE)
        if text is None and feedback is None:
            # The retry changes the request: it asks for a shorter ledger.
            text = await self._call(
                build_plan_spine_prompt(
                    self._shape_json, self._scenes_json(), pitch, brief, compact=True
                ),
                SPINE,
            )
            if text is None:
                self.failed = "the spine was cut off at the output limit twice"
                return
        if text is None:
            # A cut-off spine repair keeps the previous spine and is not
            # repaired again with the same request.
            self.frozen.add(SPINE)
            return
        problems = self._accept_spine(text)
        self.pending.extend(Routed(SPINE, p) for p in problems)

    # -- scenes --------------------------------------------------------------

    def _accept_scene(
        self, scene: Scene, text: str
    ) -> tuple[list[Routed], ChunkEntries | None]:
        """Decode and screen a scene answer, keeping only the scene's entries.

        Args:
            scene: The scene.
            text: The answer.

        Returns:
            tuple[list[Routed], ChunkEntries | None]: Feedback lines, and the
                entries (None when the answer is unusable).
        """
        decoded, problem = _decode_object(text)
        if decoded is None:
            return [Routed(scene.id, problem or "unparseable")], None
        raw: dict[str, dict[str, object]] = {}
        for key in ("nodes", "choices", "new_facts"):
            value = decoded.get(key, {})
            if not isinstance(value, dict):
                return [Routed(scene.id, f"{key} must be a JSON object")], None
            raw[key] = cast("dict[str, object]", value)
        if _carries_pii(raw, self.job.parts.pii):
            return [Routed(scene.id, _PII_FEEDBACK)], None
        view = self.job.view
        real = view.to_real({"nodes": raw["nodes"], "choices": raw["choices"]})
        inside = set(scene.nodes)
        owned = {
            c.id for node in view.book.nodes if node.id in inside for c in node.choices
        }
        nodes = cast("dict[str, object]", real["nodes"])
        choices = cast("dict[str, object]", real["choices"])
        dropped = sorted({*nodes} - inside) + sorted({*choices} - owned)
        lines = [
            Routed(
                scene.id,
                f"ignored entry {key!r}: not part of this scene",
                error=False,
            )
            for key in dropped
        ]
        return lines, ChunkEntries(
            nodes={k: v for k, v in nodes.items() if k in inside},
            choices={k: v for k, v in choices.items() if k in owned},
            new_facts=dict(raw["new_facts"]),
        )

    async def _write_scene(
        self, scene: Scene, feedback: Sequence[Routed] | None = None
    ) -> None:
        """Write (or repair) one scene; a cut-off scene is split once.

        Args:
            scene: The scene.
            feedback: The scene's routed findings for a repair, or None.
        """
        job, view = self.job, self.job.view
        node_owner, _ = owners(view.book, self.scenes)
        chunk_json = json.dumps(
            view.render_scene(scene.nodes, node_owner), separators=(",", ":")
        )
        spine_json = json.dumps(
            self._spine_payload(), ensure_ascii=False, separators=(",", ":")
        )
        entry_json = json.dumps(self._entry_payload(scene), separators=(",", ":"))
        pitch, brief = job.pitch_fields, job.parts.request.brief
        previous = self.entries.get(scene.id)
        if feedback is None:
            prompt = build_plan_chunk_prompt(
                scene.id, chunk_json, spine_json, entry_json, pitch, brief
            )
        else:
            prompt = build_plan_chunk_repair_prompt(
                scene.id,
                chunk_json,
                spine_json,
                entry_json,
                pitch,
                brief,
                previous=(
                    None
                    if previous is None
                    else json.dumps(
                        view.to_alias(
                            {
                                "nodes": previous.nodes,
                                "choices": previous.choices,
                                "new_facts": previous.new_facts,
                            }
                        ),
                        indent=1,
                        ensure_ascii=False,
                    )
                ),
                findings=self._feedback_lines(feedback),
            )
        text = await self._call(prompt, scene.id)
        if text is None:
            await self._split(scene, feedback)
            return
        lines, entries = self._accept_scene(scene, text)
        self.pending.extend(lines)
        if entries is not None:
            self.entries[scene.id] = entries

    async def _split(self, scene: Scene, feedback: Sequence[Routed] | None) -> None:
        """Split a cut-off scene in two and write both halves (once).

        Args:
            scene: The scene whose answer was cut off.
            feedback: Its routed findings when the cut-off call was a repair.
        """
        # #CRITICAL: payment/financial: a cut-off scene is never re-sent as it
        # was. It is split in two and each half written once; a half that is
        # cut off again ends the job (no further split, no repair), so the
        # paid calls stay bounded by twice the scene count plus the repairs.
        # #VERIFY: test_storyplan_chunked.py::
        # test_a_truncated_chunk_is_split_and_retried.
        if scene.split or len(scene.nodes) < 2:
            self.failed = (
                f"scene {scene.id} was cut off at the output limit after one split"
            )
            return
        view = self.job.view
        halves = split_scene(view.book, scene)
        self.write.splits.append(scene.id)
        index = self.scenes.index(scene)
        self.scenes[index : index + 1] = list(halves)
        previous = self.entries.pop(scene.id, None)
        node_owner, choice_owner = owners(view.book, self.scenes)
        for half in halves:
            if previous is not None:
                self.entries[half.id] = _subset(previous, half, view)
            mine = None
            if feedback is not None:
                mine = [
                    r
                    for r in feedback
                    if r.subject is None
                    or (node_owner.get(r.subject) or choice_owner.get(r.subject))
                    == half.id
                ]
                if not mine and half.id in self.entries:
                    continue  # nothing reported in this half: keep its entries
            await self._write_scene(half, mine)
            if self.failed is not None:
                return

    # -- stitch, check, route --------------------------------------------------

    def _annotate(self) -> None:
        """Mark the last summary as a chunked round and reset the round's parts."""
        state = self.job.state
        if state.summaries:
            state.summaries[-1] = replace(
                state.summaries[-1],
                mode="chunked",
                parts=tuple(self.written),
                truncated=tuple(self.truncated),
            )
        self.written, self.truncated = [], []

    def _stitch_and_check(
        self,
    ) -> tuple[StoryPlan | None, ValidationReport | None, list[Routed]]:
        """Stitch the parts, load and check the plan, and route what failed.

        Returns:
            tuple[StoryPlan | None, ValidationReport | None, list[Routed]]:
                The checked plan and its report (None when it did not load)
                and every routed feedback line, pending ones included.
        """
        job, view = self.job, self.job.view
        state, call = job.state, job.calls
        stitched = stitch(
            self.spine or {}, [(s, self.entries.get(s.id)) for s in self.scenes]
        )
        node_owner, choice_owner = owners(view.book, self.scenes)
        routed, self.pending = list(self.pending), []
        sections, _ = _normalize(view, stitched.sections)
        document = _assemble(
            view,
            sections,
            request=job.parts.request,
            pitch=job.parts.pitch,
            model_label=job.parts.model_label,
            note=f"{job.parts.note}; written in {len(self.scenes)} scenes",
        )
        try:
            plan = StoryPlan.model_validate(document)
        except PydanticValidationError as exc:
            errors = _real_load_errors(exc)
            state.load_errors = [view.alias_text(e) for e in errors]
            state.record(call, "load_errors")
            self._annotate()
            job.stage_log.append(f"plan:{call}:load_errors={len(errors)}")
            routed.extend(
                route_load_errors(
                    errors,
                    node_owner=node_owner,
                    choice_owner=choice_owner,
                    fact_origin=stitched.fact_origin,
                )
            )
            return None, None, routed
        plan, report = _check_attempt(view, plan, state, call, job.stage_log)
        self._annotate()
        routed.extend(
            route_findings(
                [*report.errors, *report.warnings],
                node_owner=node_owner,
                choice_owner=choice_owner,
                fact_origin=stitched.fact_origin,
            )
        )
        return plan, report, routed

    def _density_targets(self, plan: StoryPlan) -> list[Routed]:
        """Route SP-D density warnings to the scenes holding the thin entries.

        Args:
            plan: A checked plan.

        Returns:
            list[Routed]: Warning lines, one per empty passage and per reused
                intent or cost, each to its scene; ledger-wide and
                unreferenced-fact lines go to every scene targeted (or to the
                spine when no scene is).
        """
        view = self.job.view
        density = plan_density(plan, view.book)
        if density is None:
            return []
        node_owner, choice_owner = owners(view.book, self.scenes)
        lines: list[Routed] = []
        if (
            density.passages >= DENSITY_MIN_NODES
            and density.empty_share > EMPTY_NODE_SHARE_MAX
        ):
            lines.extend(
                Routed(
                    node_owner[n],
                    f"SP-D warning: passage {n} neither requires nor establishes a "
                    "fact: record the clues, objects, names, possessions and states "
                    "it introduces or relies on",
                    n,
                    error=False,
                )
                for n in density.empty_passages
                if n in node_owner
            )
        if density.decision_choices >= DENSITY_MIN_DECISION_CHOICES:
            for reusers, what, limit, fix in (
                (
                    density.intent_reusers,
                    "intent",
                    INTENT_REUSE_MAX,
                    "write its intent for this decision",
                ),
                (
                    density.cost_reusers,
                    "cost",
                    COST_REUSE_MAX,
                    "name what this option gives up here",
                ),
            ):
                share = len(reusers) / density.decision_choices
                if share > limit:
                    lines.extend(
                        Routed(
                            choice_owner[c],
                            f"SP-D warning: choice {c} shares its {what} with a "
                            f"choice that leads somewhere else: {fix}",
                            c,
                            error=False,
                        )
                        for c in reusers
                        if c in choice_owner
                    )
        general: list[str] = [
            f"SP-D warning: fact {fact!r} is in the ledger but no passage or choice "
            "requires or establishes it; use it where this part tells it"
            for fact in density.unreferenced_facts
        ]
        if (
            density.passages >= DENSITY_MIN_NODES
            and density.ledger_density < LEDGER_DENSITY_MIN
        ):
            general.append(
                f"SP-D warning: the plan references {density.referenced_facts} facts for "
                f"{density.passages} passages: every clue found, thing handed over, "
                "name learned and change of state is its own fact"
            )
        parts = list(dict.fromkeys(r.part for r in lines))
        if not parts and general:
            parts = (
                [s.id for s in self.scenes]
                if density.ledger_density < LEDGER_DENSITY_MIN
                else [SPINE]
            )
        lines.extend(
            Routed(part, line, None, error=False) for part in parts for line in general
        )
        return lines

    async def _repair_round(
        self, routed: Sequence[Routed], *, warnings_too: bool
    ) -> int:
        """Re-write each part with routed feedback, within the repair budget.

        The spine goes first (scenes read its ledger), then the scenes with
        the most errors. Each part re-written counts as one repair.

        Args:
            routed: Every routed line.
            warnings_too: True for the density round, where a part with only
                warnings is repaired; otherwise only parts with an error are.

        Returns:
            int: How many parts were re-written (0 when no routed part can be).
        """
        by_part: dict[str, list[Routed]] = {}
        for item in routed:
            by_part.setdefault(item.part, []).append(item)
        order = {s.id: i for i, s in enumerate(self.scenes)}
        targets = [
            part
            for part, items in by_part.items()
            if part not in self.frozen
            and (part == SPINE or part in order)
            and (warnings_too or any(r.error for r in items))
        ]
        targets.sort(
            key=lambda part: (
                part != SPINE,
                -sum(1 for r in by_part[part] if r.error),
                order.get(part, -1),
            )
        )
        chosen = targets[: self._budget_left()]
        for part in chosen:
            self.repairs += 1
            if part == SPINE:
                await self._write_spine(by_part[part])
            else:
                scene = next(s for s in self.scenes if s.id == part)
                await self._write_scene(scene, by_part[part])
            if self.failed is not None:
                break
        return len(chosen)

    # -- the run ---------------------------------------------------------------

    async def run(self) -> PlanGenerationResult:
        """Write the spine and every scene, then check and repair.

        Returns:
            PlanGenerationResult: The outcome, with the write decision.
        """
        job, view = self.job, self.job.view
        self._shape_json = json.dumps(view.render(), separators=(",", ":"))
        self.scenes = partition_scenes(view.book, cap=job.max_tokens)
        self.write.spine = estimate_spine_size(view.book, cap=job.max_tokens)
        job.stage_log.append(f"plan:chunked:scenes={len(self.scenes)}")
        if not self.write.spine.fits:
            # #EDGE: external-resources: the spine is one call whatever the
            # partition; on the two largest 13-16 shapes its estimate exceeds
            # the budget at a 32,000 cap. It is still attempted (the estimate
            # is deliberately high) and a cut-off spine is retried once
            # asking for a shorter ledger.
            # #VERIFY: test_storyplan_chunked.py::
            # test_a_cut_off_spine_is_retried_once_asking_for_less.
            _logger.warning(
                "story_plan.spine_over_budget",
                shape_id=view.shape_id,
                estimate_tokens=self.write.spine.total,
                budget=self.write.spine.budget,
            )
        await self._write_spine()
        while self.spine is None and self.failed is None and self._budget_left():
            feedback, self.pending = self.pending, []
            self.repairs += 1
            await self._write_spine(feedback)
        if self.spine is None:
            return self._finish_unwritten()
        for scene in list(self.scenes):
            if scene in self.scenes:
                await self._write_scene(scene)
            if self.failed is not None:
                return self._finish_unwritten()
        return await self._check_loop()

    async def _check_loop(self) -> PlanGenerationResult:
        """Stitch, check and repair until checked or out of budget.

        Returns:
            PlanGenerationResult: The outcome.
        """
        job, state = self.job, self.job.state
        while True:
            plan, report, routed = self._stitch_and_check()
            has_next = self._budget_left() > 0
            if plan is not None and report is not None and report.ok:
                plan, report = state.denser(plan, report)
                targets = (
                    self._density_targets(plan)
                    if job.inputs.repair_density_warnings
                    else []
                )
                # #ASSUME: payment/financial: the density repair is taken at
                # most once per job and only from the remaining budget
                # (AL-848); in chunked mode it re-writes only the parts that
                # hold thin entries, each counted as one repair.
                # #VERIFY: test_storyplan_chunked.py::
                # test_density_warnings_repair_only_the_thin_scenes.
                if state.take_density_repair(
                    plan, report, enabled=bool(targets), has_next=has_next
                ):
                    job.stage_log.append(
                        f"plan:{job.calls}:density_repair={_density_findings(report)}"
                    )
                    repaired = await self._repair_round(targets, warnings_too=True)
                    if self.failed is not None:
                        break
                    if repaired:
                        continue
                return self._finish(
                    _checked(
                        job.view,
                        job.candidates,
                        plan,
                        report,
                        job.calls,
                        job.stage_log,
                        state,
                    )
                )
            if not has_next or not any(r.error for r in routed):
                break
            # A round that can re-write nothing (every erring part frozen
            # after a cut-off repair) ends the loop instead of spinning. The
            # round records no summary, so the stitched round's is still last.
            if not await self._repair_round(routed, warnings_too=False):
                break
            state.mark_repair("errors")
            if self.failed is not None:
                break
        if self.failed is not None:
            state.load_errors = [*state.load_errors, self.failed]
        return self._finish(_unfinished(job, job.calls))

    def _finish_unwritten(self) -> PlanGenerationResult:
        """Return ``failed_checks`` when no stitched plan could be attempted.

        Returns:
            PlanGenerationResult: The outcome, the last part's problem recorded.
        """
        job, state = self.job, self.job.state
        reasons = [self.job.view.alias_text(r.line) for r in self.pending]
        state.load_errors = [*reasons, *([self.failed] if self.failed else [])] or [
            "the spine could not be written"
        ]
        outcome: AttemptOutcome = "truncated" if self.truncated else "unparseable"
        state.record(job.calls, outcome)
        self._annotate()
        job.stage_log.append(f"plan:{job.calls}:{outcome}")
        return self._finish(_unfinished(job, job.calls))

    def _finish(self, result: PlanGenerationResult) -> PlanGenerationResult:
        """Attach the write decision and the repair count to a result.

        Args:
            result: The outcome.

        Returns:
            PlanGenerationResult: The same, with ``write_mode`` and
                ``repair_calls``.
        """
        self.write.scenes = [
            {
                "id": scene.id,
                "nodes": len(scene.nodes),
                "choices": sum(
                    len(node.choices)
                    for node in self.job.view.book.nodes
                    if node.id in set(scene.nodes)
                ),
                "content_tokens": scene_content(self.job.view.book, scene.nodes),
            }
            for scene in self.scenes
        ]
        return replace(
            result, write_mode=self.write.to_report(), repair_calls=self.repairs
        )


def _load_plan(  # noqa: PLR0913, PLR0917 - one attempt's inputs and loop state
    view: ShapeView,
    text: str,
    parts: _PlanParts,
    state: _Attempt,
    call: int,
    stage_log: list[str],
) -> StoryPlan | None:
    """Decode, screen and load one plan answer, recording any failure.

    Args:
        view: The shape view.
        text: The model's answer.
        parts: The request, pitch, model label, provenance note and PII context.
        state: The loop state; on failure its feedback, previous plan, load
            errors and summaries are updated.
        call: The plan call number.
        stage_log: The stage trail, appended to on failure.

    Returns:
        StoryPlan | None: The loaded (unchecked) plan, or None when the answer
            was unparseable, carried PII or did not load.
    """
    decoded, problem = _decode_object(text)
    if decoded is None:
        state.previous, state.feedback = None, [problem or "unparseable"]
        state.load_errors = list(state.feedback)
        state.record(call, "unparseable")
        stage_log.append(f"plan:{call}:unparseable")
        return None
    sections, dropped = _normalize(view, view.to_real(decoded))
    if _carries_pii(sections, parts.pii):
        # #CRITICAL: security: a plan is persisted and later quoted into
        # fill prompts; a family's child name or PII-shaped text the model
        # invented must not be stored, and echoing it back in a repair
        # prompt would trip the provider guard and fail the job. So the
        # answer is discarded unread and the repair asks for invented names.
        # #VERIFY: test_storyplan_generate.py::test_a_plan_naming_a_child_is_rewritten.
        state.previous = None
        state.feedback = [_PII_FEEDBACK]
        state.load_errors = [_PII_FEEDBACK]
        state.record(call, "personal_information")
        stage_log.append(f"plan:{call}:personal_information")
        return None
    document = _assemble(
        view,
        sections,
        request=parts.request,
        pitch=parts.pitch,
        model_label=parts.model_label,
        note=parts.note,
    )
    try:
        return StoryPlan.model_validate(document)
    except PydanticValidationError as exc:
        state.load_errors = _load_errors(view, exc)
        state.previous = view.to_alias(sections)
        state.feedback = [
            *(f"ignored key {key!r}: not part of your answer" for key in dropped),
            *state.load_errors,
        ][:_MAX_FEEDBACK_LINES]
        state.record(call, "load_errors")
        stage_log.append(f"plan:{call}:load_errors={len(state.load_errors)}")
        return None


def _check_attempt(  # noqa: PLR0913, PLR0917 - one attempt's inputs and loop state
    view: ShapeView,
    plan: StoryPlan,
    state: _Attempt,
    call: int,
    stage_log: list[str],
) -> tuple[StoryPlan, ValidationReport]:
    """Check a loaded plan, stamp its check record and summarise the attempt.

    Args:
        view: The shape view.
        plan: The loaded plan.
        state: The loop state; ``plan``, ``checks`` and ``summaries`` are
            updated.
        call: The plan call number.
        stage_log: The stage trail.

    Returns:
        tuple[StoryPlan, ValidationReport]: The plan with its
            ``provenance.checks`` set, and its SP report.
    """
    report = check_plan(plan, view.book)
    record = CheckRecord(
        ok=report.ok, errors=len(report.errors), warnings=len(report.warnings)
    )
    plan = plan.model_copy(
        update={"provenance": plan.provenance.model_copy(update={"checks": record})}
    )
    density = plan_density(plan, view.book)
    state.load_errors = []
    state.record(
        call,
        "checked" if report.ok else "failed_checks",
        loaded=(plan, report, None if density is None else density.to_dict()),
    )
    state.plan, state.checks = plan, report
    stage_log.append(f"plan:{call}:errors={record.errors}")
    return plan, report


def _checked(  # noqa: PLR0913, PLR0917 - the parts of one checked result
    view: ShapeView,
    candidates: list[PitchCandidate],
    plan: StoryPlan,
    report: ValidationReport,
    calls: int,
    stage_log: list[str],
    state: _Attempt,
) -> PlanGenerationResult:
    """Return the ``checked`` result for a plan with no SP ERROR.

    Args:
        view: The shape view.
        candidates: Every pitch considered.
        plan: The checked plan.
        report: Its SP report (warnings only).
        calls: Plan calls made in all.
        stage_log: The stage trail.
        state: The loop state (for the attempt summaries).

    Returns:
        PlanGenerationResult: Status ``checked``.
    """
    _logger.info(
        "story_plan.checked",
        shape_id=view.shape_id,
        plan_calls=calls,
        warnings=len(report.warnings),
        density_warnings=_density_findings(report),
    )
    return PlanGenerationResult(
        status="checked",
        shape={"id": view.shape_id, "hash": view.shape_hash},
        pitches=candidates,
        plan=plan,
        checks=report,
        plan_calls=calls,
        stage_log=stage_log,
        attempts=list(state.summaries),
    )
