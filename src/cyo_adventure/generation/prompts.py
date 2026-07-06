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
from cyo_adventure.validator.layer1 import Scale, ScalePlacement, resolve_node_budget

if TYPE_CHECKING:
    from cyo_adventure.generation.concept import ConceptBrief

__all__ = [
    "StagePrompt",
    "build_fill_prompt",
    "build_prose_prompt",
    "build_repair_prompt",
    "build_structure_prompt",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TEMPLATES = files("cyo_adventure.generation.templates")

# Marker line separating the static (cacheable) system region of a template from
# the volatile (per-job) user region. Everything before the marker is the system
# block; everything after is the user block.
_USER_MARKER = "<!-- @user -->"

# Placeholder tokens shared by every stage template (structure/prose/fill). Named
# once so the substitution sites cannot drift from the template text.
_SCHEMA_RULES_PLACEHOLDER = "{schema_rules}"
_DRAFTING_GUIDE_PLACEHOLDER = "{drafting_guide}"


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
        f"\n- Story scale: this is a {brief.length.value} {style} story for the "
        f"{band} band. Size the world to that scale cell, not the band minimum."
    ]
    words = words_per_node_profile(band, style)
    if words is not None:
        mean, _advisory_lo, _advisory_hi, per_node_max = words
        lines.append(
            f"\n- Words per node: aim for a story-mean of about {mean} words per "
            f"node, and keep every single node at or under {per_node_max} words "
            f"(rule PL-19). A one-line beat is fine; no node may exceed the max."
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
        .replace("{concept_brief}", brief.model_dump_json(indent=2))
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
        .replace("{approved_skeleton}", skeleton_json)
    )
    return _split_stage_prompt(text)


def build_fill_prompt(skeleton_json: str, theme_brief: str) -> StagePrompt:
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
        .replace("{skeleton_with_fill_directives}", skeleton_json)
        .replace("{theme_brief}", theme_brief)
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
        .replace("{approved_skeleton}", storybook_json)
        .replace("{validator_report}", validator_report)
        .replace("{failing_node_ids}", failing_node_ids)
    )
    return _split_stage_prompt(text)
