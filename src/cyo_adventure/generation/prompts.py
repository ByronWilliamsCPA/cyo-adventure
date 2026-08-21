"""Deterministic prompt assembly for the three staged-generation stages.

Each builder loads its bundled template via ``importlib.resources`` and
substitutes all placeholders it is responsible for using explicit ``.replace()``
calls (never ``str.format``). This is intentional: the drafting guide and any
JSON payload both contain literal ``{`` and ``}`` characters, which would cause
``str.format`` to raise ``KeyError``. Explicit ``.replace()`` is safe because it
is a literal string match with no format-string interpretation.

Placeholders in the templates follow the ``{name}`` convention. All placeholders
are filled by the builders so that no unfilled tokens reach the provider.

System/user split (prompt caching)
----------------------------------
Each template is divided into a static *system* region and a volatile *user*
region by a single ``<!-- @user -->`` marker line. The builders split on this
marker and return a :class:`StagePrompt` carrying the two parts separately. The
system region holds content that is identical across every job for a stage
(the role instruction, the Storybook JSON Schema, the drafting guide, and the
fixed task framing); because it is stable, a provider adapter can mark it with a
cache breakpoint (e.g. Anthropic ``cache_control``) so the large schema is not
re-billed on every call. The user region holds the per-job volatile content
(the concept brief and its budget, or the skeleton being prosed/repaired), which
differs every call and is never cached.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.storybook.schema_export import build_schema
from cyo_adventure.validator.band_profile import (
    min_complete_floor,
    words_per_node_profile,
)
from cyo_adventure.validator.choice_grammar import words_per_stop_ceiling
from cyo_adventure.validator.layer1 import Scale, ScalePlacement, resolve_node_budget

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from cyo_adventure.generation.concept import ConceptBrief
    from cyo_adventure.storybook.theme_contract import SlotSpec, ThemeContract
    from cyo_adventure.validator.slots import SlotViolation

__all__ = [
    "FillBatchPayload",
    "StagePrompt",
    "build_bind_prompt",
    "build_bound_fill_prompt",
    "build_fidelity_repair_prompt",
    "build_fill_prompt",
    "build_fill_subset_bound_prompt",
    "build_fill_subset_prompt",
    "build_interpret_bind_prompt",
    "build_prose_prompt",
    "build_reading_level_repair_prompt",
    "build_repair_prompt",
    "build_structure_prompt",
    "neutralize_prompt_payload",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TEMPLATES = files("cyo_adventure.generation.templates")

# Marker line separating the static (cacheable) system region of a template from
# the volatile (per-job) user region. Everything before the marker is the system
# block; everything after is the user block.
_USER_MARKER = "<!-- @user -->"
# Inert stand-in for a forged stage marker inside an untrusted payload; see
# `_neutralize_fence`.
_USER_MARKER_DEFANGED = "<!-- @user_NEUTRALIZED -->"

# Placeholder tokens shared by every stage template (structure/prose/fill). Named
# once so the substitution sites cannot drift from the template text.
_SCHEMA_RULES_PLACEHOLDER = "{schema_rules}"
_DRAFTING_GUIDE_PLACEHOLDER = "{drafting_guide}"

# The theme-brief placeholder recurs across the fill, bind, interpret-and-bind,
# and bound-fill templates; named once for the same reason as the two above.
_THEME_BRIEF_PLACEHOLDER = "{theme_brief}"

# Terminator of the ``<<<UNTRUSTED_USER_INPUT ... >>>END_UNTRUSTED_USER_INPUT``
# fence, and the inert form substituted for it inside a payload. The defanged
# form stays human-legible in a logged prompt (so a reviewer can see that an
# escape was attempted) while no longer matching the terminator the model is
# told to look for. See _neutralize_fence.
_FENCE_TERMINATOR = ">>>END_UNTRUSTED_USER_INPUT"
_FENCE_TERMINATOR_DEFANGED = ">>>END_UNTRUSTED_USER_INPUT_NEUTRALIZED"


@dataclass(frozen=True, slots=True)
class StagePrompt:
    """A staged-generation prompt split into a static system block and a user block.

    Attributes:
        system: The stable, per-stage reference block (role instruction, JSON
            Schema, drafting guide, fixed task framing). Identical across jobs
            for a given stage, so an adapter may mark it as a cached prefix.
        user: The volatile, per-job block (the concept brief and budget, or the
            skeleton/story being prosed or repaired). Never cached.
    """

    system: str
    user: str

    @property
    def combined(self) -> str:
        """Return the full prompt as one string (system then user).

        Convenience for logging, length checks, and tests. The provider receives
        ``system`` and ``user`` separately via
        :meth:`~cyo_adventure.generation.provider.GenerationProvider.complete`.

        Returns:
            The system block and user block joined by a blank line.
        """
        return f"{self.system}\n\n{self.user}"


def _load_template(name: str) -> str:
    """Load a bundled template file by filename.

    Args:
        name: Filename inside the ``cyo_adventure.generation.templates`` package
            (e.g. ``"structure.md"``).

    Returns:
        The full text of the template file.
    """
    return _TEMPLATES.joinpath(name).read_text(encoding="utf-8")


def _split_stage_prompt(text: str) -> StagePrompt:
    """Split fully-substituted template text into a :class:`StagePrompt`.

    Splits on the single ``<!-- @user -->`` marker line: text before the marker
    becomes the system block, text after becomes the user block. Both parts are
    stripped of surrounding whitespace.

    Args:
        text: The template text after all placeholder substitution.

    Returns:
        The :class:`StagePrompt` with the system and user blocks separated.

    Raises:
        BusinessLogicError: If the template does not contain exactly one
            ``<!-- @user -->`` marker. This is a template-authoring error, not a
            runtime input error, so failing loudly is correct.
    """
    parts = text.split(_USER_MARKER)
    if len(parts) != 2:
        msg = (
            f"template must contain exactly one '{_USER_MARKER}' marker; "
            f"found {len(parts) - 1}"
        )
        raise BusinessLogicError(msg, rule="stage_prompt_marker")
    system, user = parts
    return StagePrompt(system=system.strip(), user=user.strip())


def _neutralize_fence(text: str) -> str:
    """Defang the untrusted-input fence terminator inside a delimited payload.

    Several templates wrap untrusted content between ``<<<UNTRUSTED_USER_INPUT``
    and ``>>>END_UNTRUSTED_USER_INPUT``. A payload that itself contains the
    literal terminator closes the fence early, and everything after it reads to
    the model as trusted instruction: the classic delimiter-escape injection.

    # #CRITICAL: security: the reading-level repair prompt carries model-written
    # node prose, which descends from an untrusted guardian/child brief. A body
    # holding the literal terminator would break out of the fence and steer the
    # simplification model directly. ``moderation/stages.py`` already sanitizes
    # for exactly this reason (``_sanitize_delimited``); the generation
    # templates in this module do not, so the terminator is neutralized here at
    # the one call site that feeds prose rather than a JSON brief.
    # #VERIFY: test_reading_level_prompt_neutralizes_a_literal_fence_terminator.
    # #ASSUME: security: every DYNAMIC payload in this module is now routed
    # through this function, not just the two that fed prose. The rule is
    # uniform because the two delimiters it defangs can be forged by any
    # interpolated string, and the position of the payload relative to the
    # fence does not decide the risk: ``{slot_bindings}`` sits OUTSIDE the
    # fence in ``fill_subset_bound.md`` and is neutralized anyway, because the
    # stage marker rather than the fence is what it can forge. Closing
    # ``{theme_brief}`` here retires UW-C228, and the same pass closed
    # ``{skeleton_with_fill_directives}`` (which carries validated slot values
    # that ``validator/slots.py`` does not screen for the marker),
    # ``{approved_skeleton}``, ``{filled_story}``, ``{nodes_to_fill}`` and
    # ``{differentiation_directive}`` (whose ``prior_titles`` descend from a
    # family's own published story titles, validated only ``min_length=1``).
    # #CRITICAL: security: FAILURE FEEDBACK is dynamic too, which the first pass
    # of this rule got wrong: ``{fidelity_violations}``, ``{validator_report}``,
    # ``{violations_block}`` and ``{failing_node_ids}`` were listed as
    # code-derived and none of them is.
    # ``{fidelity_violations}`` carries ``run_semantic_fidelity_check``'s
    # ``notes``, which is unconstrained review-model text. ``{validator_report}``
    # carries ``validator/gate.py``'s L1-1 message, which interpolates a Pydantic
    # ``ValidationError`` whose ``str()`` echoes ``input_value=``, so the
    # offending document's own text lands in the prompt. ``{violations_block}``
    # carries ``_completeness_violations``'s "binding contains undeclared slot
    # '{slot_id}'", and that id is a KEY of the model's parsed bind response:
    # ``_parse_bind_response`` validates only that values are strings, never that
    # keys are declared slot ids. ``{failing_node_ids}`` looks exempt and is not:
    # the only ids this schema pattern-constrains are ``Variable.name`` and
    # ``Effect.var`` (``models.py`` ``Field(pattern=r"^[a-z][a-z0-9_]*$")``),
    # while ``Node.id``, ``Choice.id`` and ``Ending.id`` are
    # ``Field(min_length=1)`` with no pattern and no validator rule on their
    # format, so a node id spelling either delimiter is schema-VALID.
    # #VERIFY: TestFailureFeedbackCannotForgeTheMarker covers all four paths.
    # Code-derived tokens are deliberately NOT routed here: ``{slot_table}``,
    # ``{budget_constraints}`` and ``{reading_target}`` are built from contract
    # data and literals, never from free text or model-supplied ids.
    # #VERIFY: test_prompts_neutralize_every_dynamic_payload.

    Args:
        text: The payload about to be placed inside an untrusted fence.

    Returns:
        The payload with any fence terminator rendered inert.
    """
    # The stage-split marker is the second delimiter an untrusted payload can
    # forge, and forging it is worse than forging the fence: `_split_stage_prompt`
    # requires EXACTLY one marker, so a second one raises BusinessLogicError,
    # which is not a ValidationError and therefore escapes `_fill_in_batches` and
    # `fill_skeleton` entirely. An RQ job then retries a deterministic failure
    # forever. Reachable from model-written prose the moment a chunked fill runs:
    # `json.dumps` escapes quotes and newlines but leaves this literal intact.
    # Confirmed by construction, not inferred (`AL-434`).
    # #VERIFY: test_chunked_fill.py::
    # test_the_subset_prompt_neutralizes_a_literal_stage_marker.
    return text.replace(_FENCE_TERMINATOR, _FENCE_TERMINATOR_DEFANGED).replace(
        _USER_MARKER, _USER_MARKER_DEFANGED
    )


def neutralize_prompt_payload(text: str) -> str:
    """Defang the two prompt delimiters in a payload, for other assembling modules.

    Public entry point to :func:`_neutralize_fence`. It exists because
    ``flywheel/reguide_draft.py`` assembles its own prompt from the same
    ``generation/templates`` package and splits on the same ``<!-- @user -->``
    marker, so it needs the identical defang. Sharing this function rather than
    re-deriving it there is the point of `AL-501`: the forgery class reappeared
    three times precisely because neutralization was a per-site decision.

    Args:
        text: The payload about to be interpolated into a prompt template.

    Returns:
        The payload with both delimiters rendered inert.
    """
    return _neutralize_fence(text)


def _drafting_guide() -> str:
    """Return the bundled drafting guide text.

    Returns:
        Full text of ``drafting_guide.md``.
    """
    # #ASSUME: data-integrity: importlib.resources finds the file in the
    # installed or src-layout package tree.
    # #VERIFY: confirm `src/cyo_adventure/generation/templates/` is present
    # before shipping; add a smoke test in CI.
    return _load_template("drafting_guide.md")


def _schema_rules() -> str:
    """Return the Storybook JSON Schema as a pretty-printed JSON string.

    The schema is static for v1 of the Storybook format, so this helper
    builds it on each call. Callers must not mutate the returned string.

    Returns:
        Pretty-printed JSON string of the Storybook JSON Schema.
    """
    return json.dumps(build_schema(), indent=2)


def _budget_block(brief: ConceptBrief, scale: Scale = "standard") -> str:
    """Render the brief-specific L1-7 budget constraints as prompt text.

    Binds the prompt to the validator's budget table (via
    :func:`~cyo_adventure.validator.layer1.band_budget`) so the model is told the
    exact node-count, branch-depth, and ending-count limits that the gate
    enforces. Stating these inline is the primary yield lever: frontier models
    otherwise build trees deeper than the band cap and trip L1-7.

    Args:
        brief: The validated concept brief for this generation job.
        scale: Story-size profile (``"standard"`` or ``"compact"``) whose budget
            numbers are stated; must match the scale the gate enforces.

    Returns:
        A markdown block stating the hard budget limits for this brief.

    Raises:
        BusinessLogicError: If no budget is defined for the brief's age band.
    """
    # #CRITICAL: data-integrity: the prompt's promised budget must match the
    # validator's enforced budget exactly; both read resolve_node_budget so they
    # cannot drift. A None here means AgeBand and the validator budget table fell
    # out of sync (an unreachable state given AgeBand is constrained to known
    # bands and every brief is production-eligible with a valid band).
    # #VERIFY: test_prompts asserts the rendered budget numbers equal
    # resolve_node_budget(brief.age_band, ...) for every AgeBand and cell.
    placement = ScalePlacement(
        length=brief.length.value if brief.length is not None else None,
        narrative_style=brief.narrative_style.value,
        production_eligible=True,
    )
    budget = resolve_node_budget(brief.age_band, placement, scale=scale)
    if budget is None:
        msg = f"no L1-7 budget defined for age band {brief.age_band!r}"
        raise BusinessLogicError(msg, rule="band_budget_missing")
    min_nodes, max_nodes, max_depth = budget
    ending_count = brief.ending_count
    return (
        f"Your skeleton MUST satisfy ALL of these hard limits for this brief's age "
        f"band ({brief.age_band}) and tier ({brief.tier}). Exceeding any of them "
        f"fails validation (rule L1-7) and the story is rejected:\n\n"
        f"- Node count: produce between {min_nodes} and {max_nodes} nodes total. "
        f"Do not exceed {max_nodes} nodes.\n"
        f"- Branch depth: the longest path from the start node to any ending must "
        f"be at most {max_depth} choices deep. Build the story as at most "
        f"{max_depth} forward stages: every choice must advance toward an ending, "
        f"and separate branches must RECONVERGE onto shared later nodes (a "
        f"branch-and-bottleneck shape) rather than forming one long chain. Before "
        f"finishing, trace the longest start-to-ending path and count its choices; "
        f"if it exceeds {max_depth}, redirect choice targets to jump forward and "
        f"merge paths until every path fits within {max_depth}.\n"
        f"- Endings: produce EXACTLY {ending_count} ending node(s) (nodes with "
        f'`"is_ending": true`), each with a distinct ending id, and set '
        f"`metadata.ending_count` to {ending_count}. Not more, not fewer."
        f"{_scale_cell_block(brief)}"
    )


def _scale_cell_block(brief: ConceptBrief) -> str:
    """Render the scale-cell constraints for a length-declared brief, else ``""``.

    A brief with no ``length`` is not scale-classified: this returns the empty
    string so the length-less prompt is byte-identical to the pre-scale prompt.
    When a ``length`` is declared, the block states the ADR-011 words-per-node
    envelope (PL-19) and the fastest-finish arc floor (PL-20) for the brief's
    ``(band, length, style)`` cell, so the prompt promises exactly what those
    policy rules enforce.

    Args:
        brief: The validated concept brief for this generation job.

    Returns:
        A leading-newline markdown block, or ``""`` when no length is declared.
    """
    if brief.length is None:
        return ""
    band = str(brief.age_band)
    style = brief.narrative_style.value
    lines = [
        (
            f"\n- Story scale: this is a {brief.length.value} {style} story for the "
            f"{band} band. Size the world to that scale cell, not the band minimum."
        )
    ]
    words = words_per_node_profile(band, style)
    if words is not None:
        mean, _advisory_lo, _advisory_hi, per_node_max = words
        lines.append(
            f"\n- Words per node: aim for a story-mean of about {mean} words per "
            f"node, and keep every single node at or under {per_node_max} words "
            f"(rule PL-19). A one-line beat is fine; no node may exceed the max."
        )
    stop_ceiling = words_per_stop_ceiling(band)
    if stop_ceiling is not None:
        lines.append(
            f"\n- Words per rendered stop: at this band consecutive no-decision "
            f"nodes are flowed into ONE scrollable stop for the reader, so keep "
            f"the prose between two decisions at or under {stop_ceiling} words "
            f"(rule CG-3). This is a pacing bound on what the reader meets "
            f"between choices, not a bound on any single node."
        )
    floor = min_complete_floor(band, brief.length.value, style)
    if floor is not None:
        lines.append(
            f"\n- Earned ending: the shortest path from the start node to any "
            f"success or completion ending must be at least {floor} nodes long "
            f"(rule PL-20). Do not offer a hollow quick win; make the reader earn "
            f"a satisfying ending through at least {floor} passages."
        )
    return "".join(lines)


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_structure_prompt(
    brief: ConceptBrief, scale: Scale = "standard"
) -> StagePrompt:
    """Build the Stage A (Structure) generation prompt.

    Loads ``structure.md`` from the bundled templates package, substitutes all
    placeholders, and splits the result into a :class:`StagePrompt`:

    - ``{schema_rules}`` with the pretty-printed Storybook JSON Schema (system).
    - ``{drafting_guide}`` with the full text of the bundled drafting guide
      (system).
    - ``{concept_brief}`` with the JSON-serialised concept brief (user).
    - ``{budget_constraints}`` with the brief-specific L1-7 budget block (user).

    Args:
        brief: The validated concept brief for this generation job.
        scale: Story-size profile (``"standard"`` or ``"compact"``). The same
            scale MUST be passed to the gate (run_gate) so the budget the prompt
            promises matches what L1-7 enforces.

    Returns:
        The Stage A :class:`StagePrompt` (no unfilled tokens).

    Raises:
        BusinessLogicError: If no budget is defined for the brief's age band, or
            the template lacks its ``<!-- @user -->`` marker.
    """
    text = (
        _load_template("structure.md")
        .replace(_SCHEMA_RULES_PLACEHOLDER, _schema_rules())
        .replace(_DRAFTING_GUIDE_PLACEHOLDER, _drafting_guide())
        .replace("{concept_brief}", _neutralize_fence(brief.model_dump_json(indent=2)))
        .replace("{budget_constraints}", _budget_block(brief, scale))
    )
    return _split_stage_prompt(text)


def build_prose_prompt(skeleton_json: str, brief: ConceptBrief) -> StagePrompt:
    """Build the Stage B (Prose) generation prompt.

    Loads ``prose.md`` from the bundled templates package, substitutes all
    placeholders, and splits the result into a :class:`StagePrompt`:

    - ``{drafting_guide}`` with the full text of the bundled drafting guide
      (system).
    - ``{schema_rules}`` with the pretty-printed Storybook JSON Schema (system).
    - ``{approved_skeleton}`` with the validated skeleton JSON string (user).

    Args:
        skeleton_json: The full JSON string of the Stage A skeleton that passed
            validation.
        brief: The concept brief for this job (reserved for future use; the
            prose template does not reference individual brief fields directly,
            but callers should pass it for forward-compatibility).

    Returns:
        The Stage B :class:`StagePrompt` (no unfilled tokens).

    Raises:
        BusinessLogicError: If the template lacks its ``<!-- @user -->`` marker.
    """
    # #ASSUME: data-integrity: skeleton_json is valid JSON and may contain
    # literal `{` / `}` characters. .replace() handles this safely.
    # #VERIFY: caller must pass a schema-validated skeleton.
    _ = brief  # reserved for future per-field prose customisation
    text = (
        _load_template("prose.md")
        .replace(_DRAFTING_GUIDE_PLACEHOLDER, _drafting_guide())
        .replace(_SCHEMA_RULES_PLACEHOLDER, _schema_rules())
        .replace("{approved_skeleton}", _neutralize_fence(skeleton_json))
    )
    return _split_stage_prompt(text)


def build_differentiation_directive(
    *,
    level: str | None,
    axis_instruction: str | None,
    prior_titles: Sequence[str] = (),
    prior_theme_tags: Sequence[str] = (),
) -> str:
    """Render the trusted differentiation block for the fill prompt (A6, A7).

    Every input is pipeline-derived or drawn from a closed vocabulary. In
    particular this NEVER carries a prior story's premise or request text: those
    are another child's words, and routing a sibling's request into this fill's
    prompt would make one child's phrasing an input to another child's story.
    Published titles are content the family already holds, and theme tags come
    from the closed similarity vocabulary, so neither is free text.

    Args:
        level: The ``DifferentiationLevel`` value (``tree``, ``leaf``, or
            ``catalog``), or ``None`` when no similarity context was available.
        axis_instruction: The drawn variation axis's instruction, or ``None``.
        prior_titles: Published titles of this family's prior stories on this
            same skeleton.
        prior_theme_tags: Canonical similarity tags those stories carry.

    Returns:
        str: The rendered block. Never empty: when nothing is known it says so,
            because a silently absent directive is what this work is fixing.
    """
    lines: list[str] = []
    if axis_instruction:
        lines.append(f"**Craft direction for this telling.** {axis_instruction}")
        lines.append("")

    if level == "leaf":
        lines.append(
            " ".join(
                [
                    "**This family has already read every skeleton in this cell for",
                    "a similar theme.** They will recognise this structure. Your",
                    "prose is the only thing that can make this feel like a new",
                    "book: change the setting wholesale, not decoratively, and give",
                    "the cast different wants from anything the titles below",
                    "suggest.",
                ]
            )
        )
    elif level == "catalog":
        lines.append(
            " ".join(
                [
                    "**This family has read this skeleton more than once already",
                    "for a similar theme.** Treat every surface as needing",
                    "replacement: place, era, cast, the nature of the obstacle, and",
                    "the imagery used to describe it. A reskin will read as a",
                    "repeat.",
                ]
            )
        )
    elif level == "tree":
        lines.append(
            " ".join(
                [
                    "**This structure is new to this family.** Write it straight;",
                    "no extra differentiation pressure applies.",
                ]
            )
        )
    else:
        lines.append(
            " ".join(
                [
                    "**No similarity context was available for this request.**",
                    "Write it straight.",
                ]
            )
        )

    if prior_titles:
        lines.append("")
        titles = ", ".join(f"'{title}'" for title in prior_titles)
        rationale = " ".join(
            [
                "Only the titles are given, deliberately: you are being told what",
                "to differ from, not what those stories said.",
            ]
        )
        lines.append(
            " ".join(
                [
                    f"Stories this family already owns on this skeleton: {titles}.",
                    "Do not reuse their settings, character names, or central",
                    f"images. {rationale}",
                ]
            )
        )
    if prior_theme_tags:
        lines.append("")
        tags = ", ".join(sorted(prior_theme_tags))
        lines.append(f"Themes already covered for this family: {tags}.")

    return "\n".join(lines)


def build_fill_prompt(
    skeleton_json: str,
    theme_brief: str,
    differentiation_directive: str = "",
) -> StagePrompt:
    """Build the Stage B' (Fill) generation prompt for automated skeleton_fill.

    Loads ``fill.md`` from the bundled templates package, substitutes all
    placeholders, and splits the result into a :class:`StagePrompt`:

    - ``{drafting_guide}`` with the full text of the bundled drafting guide
      (system).
    - ``{schema_rules}`` with the pretty-printed Storybook JSON Schema (system).
    - ``{skeleton_with_fill_directives}`` with the matched skeleton's JSON,
      FILL directives intact (user).
    - ``{theme_brief}`` with the JSON-serialised concept brief driving the
      reskin (user).

    Args:
        skeleton_json: The full JSON string of the matched skeleton, with
            "<<FILL role=... words=... beats='...'>>" bodies still in place.
        theme_brief: JSON-serialised concept brief (the child's request) used
            to adapt the skeleton's world/characters/theme.
        differentiation_directive: The trusted differentiation block from
            :func:`build_differentiation_directive`. Defaults to the
            no-context block rather than to an empty string, so the template
            never ships an unfilled token.

    Returns:
        The Stage B' :class:`StagePrompt` (no unfilled tokens).

    Raises:
        BusinessLogicError: If the template lacks its ``<!-- @user -->`` marker.
    """
    # #ASSUME: data-integrity: skeleton_json and theme_brief are valid JSON
    # and may contain literal `{` / `}` characters. .replace() handles this safely.
    # #VERIFY: caller must pass schema-validated skeleton with FILL directives.
    text = (
        _load_template("fill.md")
        .replace(_DRAFTING_GUIDE_PLACEHOLDER, _drafting_guide())
        .replace(_SCHEMA_RULES_PLACEHOLDER, _schema_rules())
        .replace("{skeleton_with_fill_directives}", _neutralize_fence(skeleton_json))
        .replace(_THEME_BRIEF_PLACEHOLDER, _neutralize_fence(theme_brief))
        .replace(
            "{differentiation_directive}",
            _neutralize_fence(
                differentiation_directive
                or build_differentiation_directive(level=None, axis_instruction=None)
            ),
        )
    )
    return _split_stage_prompt(text)


@dataclass(frozen=True, slots=True)
class FillBatchPayload:
    """The two batch-specific JSON blocks a chunked fill prompt carries.

    Bundled rather than passed as two more arguments so the builder keeps the
    same four-parameter shape as every other prompt builder in this module.

    Attributes:
        nodes_to_fill_json: JSON for this batch's work order, as produced by
            :func:`~cyo_adventure.generation.chunking.batch_request`.
        prose_so_far_json: JSON mapping node id to already-written body, as
            produced by
            :func:`~cyo_adventure.generation.chunking.written_prose`. ``"{}"``
            for the first batch.
        slot_bindings_json: JSON ``{slot_id: value}`` for a WS-2 BOUND fill, or
            None for an unbound one. Book-level rather than batch-level, unlike
            its two siblings: it is the same string for every batch of a book,
            and it rides here so
            :func:`build_fill_subset_bound_prompt` keeps the four-parameter
            shape this class exists to preserve.
    """

    nodes_to_fill_json: str
    prose_so_far_json: str
    slot_bindings_json: str | None = None


def build_fill_subset_prompt(
    skeleton_json: str,
    batch: FillBatchPayload,
    theme_brief: str,
    differentiation_directive: str = "",
) -> StagePrompt:
    """Build the prompt for ONE batch of a chunked skeleton fill.

    The one-shot ``fill.md`` asks for the whole document back, which is exactly
    what a backend with a small output ceiling cannot emit. This variant asks
    for a mapping of ``node_id`` to prose covering only the batch, so the
    response size is bounded by the batch rather than by the book (see
    :mod:`cyo_adventure.generation.chunking`).

    The system block is identical for every batch of every job, so it stays
    cacheable: the batch-specific content lives entirely in the user block.
    That block carries four things, and each earns its input tokens:

    * the batch's work order (directives and choice labels to write now),
    * the prose earlier batches wrote, so names, world, and voice hold across
      batches rather than restarting at each one,
    * the full skeleton, so a passage is written knowing where it sits in the
      graph, and
    * the theme brief and differentiation directive, identical to one-shot.

    Args:
        skeleton_json: The full JSON string of the skeleton, for structural
            context. The model is told not to return it.
        batch: This batch's work order and the prose already written.
        theme_brief: JSON-serialised concept brief (the child's request).
        differentiation_directive: The trusted differentiation block from
            :func:`build_differentiation_directive`. Defaults to the no-context
            block rather than to an empty string, so the template never ships
            an unfilled token.

    Returns:
        The batch :class:`StagePrompt` (no unfilled tokens).

    Raises:
        BusinessLogicError: If the template lacks its ``<!-- @user -->`` marker.
    """
    # #CRITICAL: security: ``prose_so_far_json`` is model-written prose
    # descended from an untrusted guardian/child brief, and it is placed inside
    # the untrusted fence. JSON serialisation escapes quotes and newlines but
    # NOT the fence terminator, so a body carrying the literal terminator would
    # close the fence early and everything after it would read as trusted
    # instruction. This is the same hole ``build_reading_level_repair_prompt``
    # closes at the one other site that feeds prose back to a model.
    # #VERIFY: tests/unit/test_chunked_fill.py::
    # test_the_subset_prompt_neutralizes_a_literal_fence_terminator.
    text = (
        _load_template("fill_subset.md")
        .replace(_DRAFTING_GUIDE_PLACEHOLDER, _drafting_guide())
        .replace(_SCHEMA_RULES_PLACEHOLDER, _schema_rules())
        .replace("{nodes_to_fill}", _neutralize_fence(batch.nodes_to_fill_json))
        .replace("{prose_so_far}", _neutralize_fence(batch.prose_so_far_json))
        .replace("{skeleton_with_fill_directives}", _neutralize_fence(skeleton_json))
        .replace(_THEME_BRIEF_PLACEHOLDER, _neutralize_fence(theme_brief))
        .replace(
            "{differentiation_directive}",
            _neutralize_fence(
                differentiation_directive
                or build_differentiation_directive(level=None, axis_instruction=None)
            ),
        )
    )
    return _split_stage_prompt(text)


def build_fill_subset_bound_prompt(
    skeleton_json: str,
    batch: FillBatchPayload,
    theme_brief: str,
    differentiation_directive: str = "",
) -> StagePrompt:
    """Build the prompt for ONE batch of a chunked BOUND skeleton fill.

    Stands to :func:`build_fill_subset_prompt` exactly as
    :func:`build_bound_fill_prompt` stands to :func:`build_fill_prompt`:
    ``fill_subset_bound.md`` is ``fill_subset.md`` plus the same three bound-fill
    blocks, lifted verbatim from ``fill_bound.md`` so a bound book gets the same
    contract whether it is emitted in one shot or a batch at a time. Those are
    the WS-2 binding preamble, the ending-title freeze and verbatim-token rules,
    and the labeled bound-values data block.

    Without this variant a bound fill could not be chunked at all, so a bound
    skeleton over the serving model's ceiling had no degraded path and simply
    failed (`UW-C302`).

    Args:
        skeleton_json: The full JSON string of the BOUND skeleton (the output of
            :func:`~cyo_adventure.generation.binding.render_bound_skeleton`),
            for structural context. The model is told not to return it.
        batch: This batch's work order, the prose already written, and the
            ``{slot_id: value}`` map that produced the bound skeleton. Its
            ``slot_bindings_json`` must be set; an unbound payload here would
            ship the template's ``{slot_bindings}`` token unfilled.
        theme_brief: JSON-serialised concept brief (the child's request).
        differentiation_directive: The trusted differentiation block from
            :func:`build_differentiation_directive`. Defaults to the no-context
            block rather than to an empty string, so the template never ships an
            unfilled token.

    Returns:
        The bound batch :class:`StagePrompt` (no unfilled tokens).

    Raises:
        BusinessLogicError: If the template lacks its ``<!-- @user -->`` marker,
            or if ``batch.slot_bindings_json`` is None. Refused rather than
            defaulted to ``"{}"``: an empty bound-values block reads to the
            model as a book with no theme bound, which is the silent-wrong
            outcome rather than the loud one.
    """
    if batch.slot_bindings_json is None:
        msg = (
            "build_fill_subset_bound_prompt requires batch.slot_bindings_json; "
            "use build_fill_subset_prompt for an unbound fill"
        )
        raise BusinessLogicError(msg)
    # #CRITICAL: security: ``prose_so_far_json`` is model-written prose descended
    # from an untrusted guardian/child brief and is fenced, for the same reason
    # and by the same call as in :func:`build_fill_subset_prompt`; JSON escaping
    # does not escape the fence terminator.
    #
    # ``slot_bindings_json`` is fenced too, which it was NOT in the first
    # revision of this function. That revision argued the values were validated
    # data because each had passed ``validator/slots.py``. They had, but that
    # check does not cover the stage-split marker: ``_charset_violations``
    # blocks ``{``/``}``, ``<<``/``>>``, the em dash, non-printables and >120
    # chars, and ``_structural_slot_violations`` blocks only the two
    # ``UNTRUSTED_USER_INPUT`` fence markers. ``<!-- @user -->`` is fourteen
    # printable ASCII characters on one line and passes every one of them. A
    # bound value carrying it forges a second marker, and per the comment in
    # :func:`_neutralize_fence` that is worse than forging the fence:
    # ``_split_stage_prompt`` raises ``BusinessLogicError``, which is not a
    # ``ValidationError`` and so escapes both ``_fill_in_batches`` and
    # ``fill_skeleton``, leaving an RQ job retrying a deterministic failure
    # forever. Neutralising is safe for well-formed values, which contain
    # neither marker and pass through byte-identical.
    # #VERIFY: tests/unit/test_chunked_fill.py::
    # test_the_bound_subset_prompt_neutralizes_a_literal_fence_terminator and
    # ::test_a_bound_value_forging_the_stage_marker_cannot_split_the_prompt.
    text = (
        _load_template("fill_subset_bound.md")
        .replace(_DRAFTING_GUIDE_PLACEHOLDER, _drafting_guide())
        .replace(_SCHEMA_RULES_PLACEHOLDER, _schema_rules())
        .replace("{nodes_to_fill}", _neutralize_fence(batch.nodes_to_fill_json))
        .replace("{prose_so_far}", _neutralize_fence(batch.prose_so_far_json))
        .replace("{skeleton_with_fill_directives}", _neutralize_fence(skeleton_json))
        .replace("{slot_bindings}", _neutralize_fence(batch.slot_bindings_json))
        .replace(_THEME_BRIEF_PLACEHOLDER, _neutralize_fence(theme_brief))
        .replace(
            "{differentiation_directive}",
            _neutralize_fence(
                differentiation_directive
                or build_differentiation_directive(level=None, axis_instruction=None)
            ),
        )
    )
    return _split_stage_prompt(text)


def _slot_constraint_text(slot: SlotSpec) -> str:
    """Render one slot's deterministic constraints as a plain-English clause.

    Args:
        slot: The declared slot spec.

    Returns:
        A single semicolon-joined clause restating ``max_words``, ``forbid``,
        ``distinct_from``, and ``pattern`` (whichever are set) in plain words,
        for the bind prompt's slot table.
    """
    clauses = [f"at most {slot.constraints.max_words} word(s)"]
    if slot.constraints.forbid:
        bundles = ", ".join(sorted(slot.constraints.forbid))
        clauses.append(f"must not evoke: {bundles}")
    if slot.constraints.distinct_from:
        siblings = ", ".join(slot.constraints.distinct_from)
        clauses.append(f"must read as clearly distinct from: {siblings}")
    if slot.constraints.pattern is not None:
        clauses.append(f"must match the pattern: {slot.constraints.pattern}")
    return "; ".join(clauses)


def _slot_table(contract: ThemeContract) -> str:
    """Render a contract's slots as a markdown list for the bind prompt.

    Args:
        contract: The theme contract to bind against.

    Returns:
        A markdown list, one entry per declared slot, stating its id, scope,
        meaning, advisory guidance (when present), and deterministic
        constraints restated in plain words.
    """
    lines: list[str] = []
    for slot in contract.slots:
        lines.append(f"- `{slot.id}` (scope: {slot.scope.value})")
        lines.append(f"  - meaning: {slot.meaning}")
        if slot.guidance:
            lines.append(f"  - guidance: {slot.guidance}")
        lines.append(f"  - constraints: {_slot_constraint_text(slot)}")
    return "\n".join(lines)


def _violations_block(violations: list[SlotViolation] | None) -> str:
    """Render a retry's violation feedback as a markdown block, or ``""``.

    Args:
        violations: The exact violations from the previous bind attempt, or
            ``None``/empty on a first attempt.

    Returns:
        ``""`` when there is nothing to report (first attempt); otherwise a
        markdown block listing each violation's slot id, rule, and message
        verbatim, so the binder can correct without re-deriving the failure.
    """
    if not violations:
        return ""
    lines = [
        "\n## Previous Attempt Violations",
        "",
        (
            "Your previous binding failed these deterministic checks. Correct "
            "ONLY the flagged slot(s); keep every other value the same unless it "
            "shares the same violation."
        ),
        "",
    ]
    for violation in violations:
        slot_label = violation.slot_id or "(binding)"
        lines.append(
            f"- slot: `{slot_label}` | rule: {violation.rule} | {violation.message}"
        )
    return "\n".join(lines)


def build_bind_prompt(
    contract: ThemeContract,
    theme_brief: Mapping[str, object],
    *,
    violations: list[SlotViolation] | None = None,
) -> StagePrompt:
    """Build the WS-2 bind-step prompt (theme brief -> validated slot values).

    Loads ``bind.md`` from the bundled templates package, substitutes all
    placeholders, and splits the result into a :class:`StagePrompt`:

    - ``{slot_table}`` with the contract's slots (id, scope, meaning,
      guidance, and constraints restated in plain words) (system).
    - ``{theme_brief}`` with the JSON-serialised theme brief, fenced as
      untrusted input (user).
    - ``{violations_block}`` with the previous attempt's exact
      :class:`~cyo_adventure.validator.slots.SlotViolation` list when
      ``violations`` is supplied (a bounded retry), else ``""`` (user).

    Args:
        contract: The theme contract to bind against.
        theme_brief: The free-text (UNTRUSTED) child/guardian story request.
        violations: The exact violations from the previous attempt, to carry
            into a bounded retry prompt. ``None`` (default) for the first
            attempt.

    Returns:
        The bind-step :class:`StagePrompt` (no unfilled tokens).

    Raises:
        BusinessLogicError: If the template lacks its ``<!-- @user -->`` marker.
    """
    # #ASSUME: data-integrity: theme_brief may contain literal `{` / `}`
    # characters once serialised; .replace() handles this safely (never
    # str.format).
    # #VERIFY: test_prompts_bound.py asserts no unfilled `{SLOT}`-shaped or
    # named placeholder token remains in the built prompt.
    text = (
        _load_template("bind.md")
        .replace("{slot_table}", _slot_table(contract))
        .replace(
            _THEME_BRIEF_PLACEHOLDER,
            _neutralize_fence(json.dumps(dict(theme_brief), indent=2)),
        )
        .replace(
            "{violations_block}",
            _neutralize_fence(_violations_block(violations)),
        )
    )
    return _split_stage_prompt(text)


def build_interpret_bind_prompt(
    contract: ThemeContract,
    theme_brief: Mapping[str, object],
    *,
    violations: list[SlotViolation] | None = None,
) -> StagePrompt:
    """Build the WS-7 interpret-and-bind prompt (bindings + element decomposition).

    Identical to :func:`build_bind_prompt` except it loads ``interpret_bind.md``
    (``bind.md`` with only its Output section changed): the binder returns a
    single JSON object with a ``bindings`` map AND an ``elements`` list (its
    decomposition of the fenced premise into short requester-vocabulary phrases,
    each paired with the slot it was carried into or ``null``). The system/user
    split, the ``{slot_table}``/``{theme_brief}``/``{violations_block}``
    placeholders, and the byte-identical ``UNTRUSTED_USER_INPUT`` fence are all
    the same as ``bind.md`` (design section 5.2, D4).

    Args:
        contract: The theme contract to bind against.
        theme_brief: The free-text (UNTRUSTED) child/guardian story request.
        violations: The exact violations from the previous attempt, to carry
            into a bounded retry prompt. ``None`` (default) for the first
            attempt.

    Returns:
        The interpret-and-bind :class:`StagePrompt` (no unfilled tokens).

    Raises:
        BusinessLogicError: If the template lacks its ``<!-- @user -->`` marker.
    """
    # #ASSUME: data-integrity: theme_brief may contain literal `{` / `}`
    # characters once serialised; .replace() handles this safely (never
    # str.format).
    # #VERIFY: test_interpret_bind.py asserts violations retry byte-parity with
    # build_bind_prompt and that the untrusted fence is byte-identical.
    text = (
        _load_template("interpret_bind.md")
        .replace("{slot_table}", _slot_table(contract))
        .replace(
            _THEME_BRIEF_PLACEHOLDER,
            _neutralize_fence(json.dumps(dict(theme_brief), indent=2)),
        )
        .replace(
            "{violations_block}",
            _neutralize_fence(_violations_block(violations)),
        )
    )
    return _split_stage_prompt(text)


def build_bound_fill_prompt(
    skeleton_json: str,
    slot_bindings_json: str,
    theme_brief: str,
    differentiation_directive: str = "",
) -> StagePrompt:
    """Build the WS-2 bound-fill prompt for a parameterized skeleton fill.

    Loads ``fill_bound.md`` (``fill.md`` plus the ending-title freeze line and
    the bound-values data block; ``fill.md`` itself is never modified) from
    the bundled templates package, substitutes all placeholders, and splits
    the result into a :class:`StagePrompt`:

    - ``{drafting_guide}`` with the full text of the bundled drafting guide
      (system).
    - ``{schema_rules}`` with the pretty-printed Storybook JSON Schema
      (system).
    - ``{skeleton_with_fill_directives}`` with the BOUND skeleton's JSON,
      FILL directives intact, beats/titles/labels already rendered with
      validated slot values (user).
    - ``{slot_bindings}`` with the JSON-serialised slot-value map, labeled as
      validated data (user).
    - ``{theme_brief}`` with the JSON-serialised theme brief, fenced as
      untrusted input, byte-identical to ``fill.md``'s fence (user).

    Args:
        skeleton_json: The full JSON string of the bound skeleton (the output
            of :func:`~cyo_adventure.generation.binding.render_bound_skeleton`).
        slot_bindings_json: JSON-serialised ``{slot_id: value}`` map that
            produced the bound skeleton.
        theme_brief: JSON-serialised concept brief (the child's request) used
            to adapt the skeleton's world/characters/theme.
        differentiation_directive: The trusted differentiation block (A6/A7)
            from :func:`build_differentiation_directive`. Defaults to the
            no-context block rather than to an empty string, so the template
            never ships an unfilled token, matching :func:`build_fill_prompt`.

    Returns:
        The bound-fill :class:`StagePrompt` (no unfilled tokens).

    Raises:
        BusinessLogicError: If the template lacks its ``<!-- @user -->`` marker.
    """
    # #ASSUME: data-integrity: skeleton_json, slot_bindings_json, and
    # theme_brief are valid JSON and may contain literal `{` / `}`
    # characters. .replace() handles this safely.
    # #VERIFY: caller must pass a bound skeleton that already passed
    # render_bound_skeleton's post-conditions.
    # #CRITICAL: security: ``slot_bindings_json`` is neutralised for the same
    # reason as in :func:`build_fill_subset_bound_prompt`: ``validator/slots.py``
    # does not reject the ``<!-- @user -->`` stage-split marker, so a bound value
    # carrying it would forge a second marker and make ``_split_stage_prompt``
    # raise a ``BusinessLogicError`` that escapes every handler on this path.
    # Both bound builders neutralise, so the two paths still agree about what a
    # bound value is.
    # #VERIFY: tests/unit/test_chunked_fill.py::
    # test_a_bound_value_forging_the_stage_marker_cannot_split_the_prompt.
    text = (
        _load_template("fill_bound.md")
        .replace(_DRAFTING_GUIDE_PLACEHOLDER, _drafting_guide())
        .replace(_SCHEMA_RULES_PLACEHOLDER, _schema_rules())
        .replace("{skeleton_with_fill_directives}", _neutralize_fence(skeleton_json))
        .replace("{slot_bindings}", _neutralize_fence(slot_bindings_json))
        .replace(_THEME_BRIEF_PLACEHOLDER, _neutralize_fence(theme_brief))
        .replace(
            "{differentiation_directive}",
            _neutralize_fence(
                differentiation_directive
                or build_differentiation_directive(level=None, axis_instruction=None)
            ),
        )
    )
    return _split_stage_prompt(text)


def build_fidelity_repair_prompt(
    filled_json: str,
    violations: list[str],
) -> StagePrompt:
    """Build the Stage 1 fidelity-aware repair prompt for a skeleton fill.

    A structurally-clean fill can still fail the Stage 1 fidelity checks (see
    :func:`~cyo_adventure.generation.fidelity.run_fidelity_checks` and the
    semantic beat check): a node may miss its FILL directive's word-count
    target, leave the directive unfilled, or perturb a field the skeleton
    fixed. This builder carries the concrete violation strings back to the
    model so the retry is a targeted correction, not a blind re-fill.

    A dedicated template is used rather than reusing :func:`build_repair_prompt`
    because the structural ``repair.md`` contract actively conflicts with a
    fidelity fix: it instructs the model to preserve every node ``body`` and,
    when no node ids are named, to restructure the graph. A fidelity fix does
    the opposite: it must rewrite the flagged node's ``body`` prose to hit its
    directive while keeping the graph structure frozen.

    Loads ``fidelity_repair.md`` and substitutes its two volatile placeholders:

    - ``{filled_story}`` with the filled story JSON being corrected (user).
    - ``{fidelity_violations}`` with the bulleted violation messages (user).

    Args:
        filled_json: The full JSON string of the filled story that missed one
            or more Stage 1 fidelity checks.
        violations: The human-readable fidelity violation messages returned by
            :func:`~cyo_adventure.generation.fidelity_gate.run_stage1_gate`.

    Returns:
        The Stage 1 fidelity-repair :class:`StagePrompt` (no unfilled tokens).

    Raises:
        BusinessLogicError: If the template lacks its ``<!-- @user -->`` marker.
    """
    # #ASSUME: data-integrity: filled_json is valid JSON and may contain literal
    # `{` / `}` characters; substitute it first so any braces in the payload
    # cannot shadow the later `{fidelity_violations}` replacement.
    # #VERIFY: test_no_unfilled_placeholders / test_carries_violation_text_verbatim.
    violations_block = (
        "\n".join(f"  - {message}" for message in violations)
        if violations
        else "  (none)"
    )
    text = (
        _load_template("fidelity_repair.md")
        .replace("{filled_story}", _neutralize_fence(filled_json))
        .replace("{fidelity_violations}", _neutralize_fence(violations_block))
    )
    return _split_stage_prompt(text)


def build_reading_level_repair_prompt(
    nodes: Sequence[tuple[str, str, float]],
    *,
    target: float,
    tolerance: float,
) -> StagePrompt:
    """Build the node-scoped reading-level repair prompt.

    Unlike every other repair builder in this module, this one does NOT send
    the story. It sends a list of ``(node_id, body, current_grade)`` triples and
    asks for a mapping of ``node_id`` to revised body. That asymmetry is the
    point and it is a safety property rather than a token optimisation:

    * The graph is not in the prompt, so the model cannot restructure it. A
      structural change is not a thing the output channel is able to express.
      ``repair.md`` and ``fidelity_repair.md`` both take back a whole Storybook
      and therefore both have to *ask* the model not to disturb structure, and
      then re-gate to find out whether it obeyed.
    * A 101-node book with 85 out-of-band nodes costs 85 short bodies in and 85
      short bodies out, batched, instead of the entire book re-emitted once per
      attempt.

    Loads ``reading_level_repair.md`` and substitutes its two volatile
    placeholders, ``{reading_target}`` and ``{nodes_to_simplify}`` (both user).

    Args:
        nodes: The out-of-band nodes as ``(node_id, body, current_grade)``.
            Bodies are passed with their ``{~SLOT:Word~}`` sentinels intact, so
            the model can preserve them verbatim.
        target: The story's target Flesch-Kincaid grade.
        tolerance: Half-width of the acceptable band around ``target``.

    Returns:
        The reading-level repair :class:`StagePrompt` (no unfilled tokens).

    Raises:
        BusinessLogicError: If the template lacks its ``<!-- @user -->`` marker.
    """
    reading_target = (
        f"Target Flesch-Kincaid grade: {target:.1f}. "
        f"Acceptable band: {target - tolerance:.1f} to {target + tolerance:.1f}."
    )
    payload = json.dumps(
        [
            {"node_id": node_id, "current_grade": round(current, 1), "body": body}
            for node_id, body, current in nodes
        ],
        indent=2,
    )
    text = (
        _load_template("reading_level_repair.md")
        .replace("{reading_target}", reading_target)
        .replace("{nodes_to_simplify}", _neutralize_fence(payload))
    )
    return _split_stage_prompt(text)


def build_repair_prompt(
    storybook_json: str,
    failing_findings: list[dict[str, object]],
) -> StagePrompt:
    """Build the Stage C (Repair) generation prompt.

    Loads ``repair.md`` from the bundled templates package, substitutes the
    volatile placeholders, and splits the result into a :class:`StagePrompt`:

    - ``{approved_skeleton}`` with the storybook JSON string being repaired
      (user).
    - ``{validator_report}`` with a formatted summary of the failing findings
      (user).
    - ``{failing_node_ids}`` with a comma-separated list of node ids extracted
      from ``failing_findings`` (user).

    The repair template embeds no schema or drafting guide; its system block is
    the fixed repair instructions only, so it stays lean.

    Only findings that have a ``node_id`` are included in the node-id list.
    The validator report includes all findings regardless of whether they carry
    a ``node_id`` (e.g. top-level schema failures may not).

    The substitution uses ``.replace()`` for all tokens, so JSON payloads
    containing literal braces are handled safely.

    Args:
        storybook_json: The full JSON string of the story that failed validation
            (may be a Stage A skeleton or a Stage B full story).
        failing_findings: A list of finding dicts from the validation report.
            Each dict may have keys: ``rule_id``, ``node_id``, ``choice_id``,
            ``message``.  Only findings where the validator detected a failure
            should be included (passing findings must be excluded by the
            caller).

    Returns:
        The Stage C :class:`StagePrompt`.

    Raises:
        BusinessLogicError: If the template lacks its ``<!-- @user -->`` marker.
    """
    # #CRITICAL: data-integrity: only failing nodes must appear in the
    # repair prompt; including passing nodes would instruct the model to
    # change correct content.
    # #VERIFY: caller (WP8 orchestrator) must filter failing_findings to
    # exclude passing nodes before calling this builder.

    # Build the human-readable validator report.
    report_lines: list[str] = []
    for finding in failing_findings:
        rule_id = finding.get("rule_id", "unknown_rule")
        node_id = finding.get("node_id")
        choice_id = finding.get("choice_id")
        message = finding.get("message", "")
        parts = [f"rule_id: {rule_id}"]
        if node_id is not None:
            parts.append(f"node_id: {node_id}")
        if choice_id is not None:
            parts.append(f"choice_id: {choice_id}")
        parts.append(f"message: {message}")
        report_lines.append("  - " + " | ".join(parts))

    validator_report = "\n".join(report_lines) if report_lines else "  (no findings)"

    # Extract unique failing node ids, preserving insertion order.
    seen: dict[str, None] = {}
    for finding in failing_findings:
        raw = finding.get("node_id")
        if isinstance(raw, str) and raw:
            seen[raw] = None
    failing_node_ids = ", ".join(seen.keys()) if seen else "(none)"

    # Substitute all three owned placeholders. Order matters: substitute the
    # JSON blob first so that any `{...}` in the JSON cannot shadow a later
    # `.replace()` call on a different token.
    text = (
        _load_template("repair.md")
        .replace("{approved_skeleton}", _neutralize_fence(storybook_json))
        .replace("{validator_report}", _neutralize_fence(validator_report))
        .replace("{failing_node_ids}", _neutralize_fence(failing_node_ids))
    )
    return _split_stage_prompt(text)
