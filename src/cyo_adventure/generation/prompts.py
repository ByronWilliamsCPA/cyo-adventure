"""Deterministic prompt assembly for the three staged-generation stages.

Each builder loads its bundled template via ``importlib.resources`` and
substitutes all placeholders it is responsible for using explicit ``.replace()``
calls (never ``str.format``). This is intentional: the drafting guide and any
JSON payload both contain literal ``{`` and ``}`` characters, which would cause
``str.format`` to raise ``KeyError``. Explicit ``.replace()`` is safe because it
is a literal string match with no format-string interpretation.

Placeholders in the templates follow the ``{name}`` convention. All placeholders
are filled by the builders: ``{schema_rules}`` is substituted with the
pretty-printed Storybook JSON Schema so that no unfilled tokens reach the
provider.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

from cyo_adventure.storybook.schema_export import build_schema

if TYPE_CHECKING:
    from cyo_adventure.generation.concept import ConceptBrief

__all__ = [
    "build_prose_prompt",
    "build_repair_prompt",
    "build_structure_prompt",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TEMPLATES = files("cyo_adventure.generation.templates")


def _load_template(name: str) -> str:
    """Load a bundled template file by filename.

    Args:
        name: Filename inside the ``cyo_adventure.generation.templates`` package
            (e.g. ``"structure.md"``).

    Returns:
        The full text of the template file.
    """
    return _TEMPLATES.joinpath(name).read_text(encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_structure_prompt(brief: ConceptBrief) -> str:
    """Build the Stage A (Structure) generation prompt.

    Loads ``structure.md`` from the bundled templates package and substitutes
    all placeholders, returning a complete prompt:

    - ``{concept_brief}`` with the JSON-serialised concept brief.
    - ``{drafting_guide}`` with the full text of the bundled drafting guide.
    - ``{schema_rules}`` with the pretty-printed Storybook JSON Schema.

    Args:
        brief: The validated concept brief for this generation job.

    Returns:
        The fully assembled structure-stage prompt string (no unfilled tokens).
    """
    return (
        _load_template("structure.md")
        .replace("{concept_brief}", brief.model_dump_json(indent=2))
        .replace("{drafting_guide}", _drafting_guide())
        .replace("{schema_rules}", _schema_rules())
    )


def build_prose_prompt(skeleton_json: str, brief: ConceptBrief) -> str:
    """Build the Stage B (Prose) generation prompt.

    Loads ``prose.md`` from the bundled templates package and substitutes all
    placeholders, returning a complete prompt:

    - ``{approved_skeleton}`` with the validated skeleton JSON string.
    - ``{drafting_guide}`` with the full text of the bundled drafting guide.
    - ``{schema_rules}`` with the pretty-printed Storybook JSON Schema.

    Args:
        skeleton_json: The full JSON string of the Stage A skeleton that passed
            validation.
        brief: The concept brief for this job (reserved for future use; the
            prose template does not reference individual brief fields directly,
            but callers should pass it for forward-compatibility).

    Returns:
        The fully assembled prose-stage prompt string (no unfilled tokens).
    """
    # #ASSUME: data-integrity: skeleton_json is valid JSON and may contain
    # literal `{` / `}` characters. .replace() handles this safely.
    # #VERIFY: caller must pass a schema-validated skeleton.
    _ = brief  # reserved for future per-field prose customisation
    return (
        _load_template("prose.md")
        .replace("{approved_skeleton}", skeleton_json)
        .replace("{drafting_guide}", _drafting_guide())
        .replace("{schema_rules}", _schema_rules())
    )


def build_repair_prompt(
    storybook_json: str,
    failing_findings: list[dict[str, object]],
) -> str:
    """Build the Stage C (Repair) generation prompt.

    Loads ``repair.md`` from the bundled templates package and substitutes:

    - ``{approved_skeleton}`` with the storybook JSON string being repaired.
    - ``{validator_report}`` with a formatted summary of the failing findings.
    - ``{failing_node_ids}`` with a comma-separated list of node ids extracted
      from ``failing_findings``.

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
        The fully assembled repair-stage prompt string.
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
    return (
        _load_template("repair.md")
        .replace("{approved_skeleton}", storybook_json)
        .replace("{validator_report}", validator_report)
        .replace("{failing_node_ids}", failing_node_ids)
    )
