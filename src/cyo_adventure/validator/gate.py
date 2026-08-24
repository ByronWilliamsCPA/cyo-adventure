"""Combined validation gate runner (WP4).

Orchestrates all validator layers in the correct order for a decoded story
mapping. This is the single entry point the generation orchestrator and the
API validate endpoint call.

Rule application order (per ``docs/planning/validator-rules.md``
"Rule Application Order" and tech-spec "Validation gate"):

1. Layer 1 (L1-1..L1-8): graph structure, schema conformance, logic.
2. **Early return on any L1 ERROR**: the graph must be sound before a
   state-space walk is meaningful, and the document may not even parse.
3. PL-27 and PL-28: the two rules that fire only when the caller passes
   ``context="fill_result"``. PL-27 rejects a retained ``<<FILL`` directive
   (the node was never written); PL-28 rejects an ADR-011 MVP/Test seed
   (a prototyping shell may not become a child-facing book). Both run ahead
   of the rest of the policy layer so an unwritten or non-production book's
   first finding names that cause. Under the default ``"skeleton"`` posture
   neither runs, because a catalog skeleton's bodies are directives by
   construction (AL-325) and a seed is a legitimate catalog object.
4. Policy (PL-15..PL-18): age-safety and shape invariants on the parsed
   model (forbidden ending kinds, content ceilings, floors, topology).
5. Layer 2 (L2-9..L2-13): state-space walk, Tier-2 only (Tier-1 skips). L2-13
   is a WARNING-only scale advisory and never sets ``blocked``.
6. CH-*: character envelope rules (ADR-028), participating books only (a
   book that neither declares ``accepts_character`` nor uses a reserved
   canonical name gets an empty report from this step). Not every CH-* id
   has landed yet; see ``validator/character.py``.
7. RL-13: advisory reading-level check (WARNING, never blocks).
8. CG-1..CG-4: advisory choice-grammar checks (WARNING, never blocks),
   gated behind ``enforce_grammar`` (default False; D3/D11 grandfathering,
   see ``validator/choice_grammar.py``).
9. SAFE-14: safety content check (Phase-2 stub, always empty).

Blocking semantics
------------------
``blocked`` is ``True`` when any ERROR-severity finding whose ``rule_id``
starts with ``"CH"``, ``"L1"``, ``"L2"``, or ``"PL"`` is present in the merged
report. RL-13 findings are WARNING and must not set ``blocked``. SAFE-14
findings route to human review and are tracked separately via
``safety_flagged``.

``safety_flagged`` is ``True`` when any finding with ``rule_id == "SAFE-14"``
exists in the merged report. In Phase 2 the safety stub is empty, so this
will always be ``False`` -- but the computation is honest so Phase 3 works
without changing this function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.character import validate_character
from cyo_adventure.validator.choice_grammar import check_choice_grammar
from cyo_adventure.validator.layer1 import Scale, validate_layer1
from cyo_adventure.validator.layer2 import validate_layer2
from cyo_adventure.validator.policy import (
    check_fill_residue,
    check_mvp_firewall,
    validate_policy,
)
from cyo_adventure.validator.reading_level import check_reading_level
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)
from cyo_adventure.validator.safety import check_safety

if TYPE_CHECKING:
    from collections.abc import Mapping


GateContext = Literal["skeleton", "fill_result"]
"""What the caller is validating, which decides whether PL-27 runs.

``"skeleton"`` is catalog time: node bodies are ``<<FILL ...>>`` directives by
construction and every checker's tolerance for them is correct. ``"fill_result"``
is post-generation: a retained directive means the node was never written, and
PL-27 fails on it. One distinction, no new checker, no regression to the
catalog-time path (AL-325).
"""


@dataclass(frozen=True, slots=True)
class GateResult:
    """The combined outcome of all validation layers.

    Attributes:
        report: Merged findings across all layers run, in order: L1, L2,
            CH, RL, SAFE.
        blocked: ``True`` when any ERROR-severity finding whose rule_id
            starts with ``"CH"``, ``"L1"``, ``"L2"``, or ``"PL"`` is present.
            RL-13 warnings and SAFE-14 findings never set this flag.
        safety_flagged: ``True`` when any finding with rule_id ``"SAFE-14"``
            is present. Always ``False`` in Phase 2 (stub is empty), but
            computed honestly so Phase 3 does not require changes here.
        context: The posture this result was produced under. Recorded rather
            than inferred so a downstream reader can tell a ``blocked=False``
            that cleared PL-27 from one that never ran it; AL-324's defect was
            an optional argument that changed which checks ran while leaving
            the verdict spelled identically.
    """

    report: ValidationReport
    blocked: bool
    safety_flagged: bool
    context: GateContext = "skeleton"


def run_fill_gate(data: Mapping[str, object]) -> GateResult:
    """Run the gate over a FILLED storybook blob, the way every producer must.

    Every writer of ``storybook_version.validation_report`` must run the gate
    the same way, or the admin review surface ranks reports that were produced
    under different postures against each other and the comparison is
    meaningless. The posture that matters here is ``context="fill_result"``:
    under the default ``"skeleton"`` context a retained ``<<FILL ...>>``
    directive is expected, and a filled book judged that way silently passes
    PL-27. This is the single definition of "validate a filled book", shared by
    generation/import_story.py and api/remoderate.py rather than spelled out at
    each call site.

    ``enforce_grammar`` stays at its default. Turning it on surfaces CG-*
    findings, which are WARNING-only and never set ``blocked``, but it must be
    turned on for ALL producers in one change or the stored reports diverge
    again; see the review-surface projection allowlist in
    api/review_surface.py::_VALIDATOR_RULE_IDS.

    Args:
        data: The stored storybook blob (raw decoded JSON mapping).

    Returns:
        GateResult: The merged report, block status, safety flag, and context.
    """
    return run_gate(data, context="fill_result")


def run_gate(
    data: Mapping[str, object],
    scale: Scale = "standard",
    *,
    enforce_grammar: bool = False,
    context: GateContext = "skeleton",
) -> GateResult:
    """Run all validation layers and return a combined gate result.

    Accepts the raw decoded story JSON (a mapping) because Layer 1 operates
    on raw JSON and must run before we can trust the document parses. Later
    layers receive the parsed ``Storybook`` if Layer 1 passes.

    Args:
        data: The raw decoded story JSON mapping.
        scale: Story-size profile the L1-7 budget is enforced against
            (``"standard"`` or ``"compact"``); forwarded to Layer 1.
        enforce_grammar: Forwarded to ``choice_grammar.check_choice_grammar``.
            Defaults to ``False`` so every existing caller (the grandfathered
            61-skeleton catalog, generation, the API validate endpoint) is
            unaffected; a future skeleton-promotion path opts in explicitly
            (D3/D11). CG-* findings are WARNING-only and never set
            ``blocked`` regardless of this flag.
        context: Whether ``data`` is a catalog-time ``"skeleton"`` (the
            default, where ``<<FILL ...>>`` directives are expected) or a
            ``"fill_result"`` (where a retained directive is a blocking PL-27
            failure). Recorded on the result either way.

    Returns:
        GateResult: The merged report, block status, safety flag, and the
        context the run was made under.
    """
    merged = ValidationReport()

    # --- Layer 1: graph structure, schema, logic ---
    l1_report = validate_layer1(data, scale)
    merged.extend(l1_report)

    if not l1_report.ok:
        # The graph is structurally unsound; the document may not even parse.
        # Do not run Layer 2, reading-level, or safety on broken input.
        return GateResult(
            report=merged,
            blocked=True,
            safety_flagged=False,
            context=context,
        )

    # --- Parse: Layer 1 includes L1-1 schema conformance, so model_validate
    # should succeed. Guard defensively against any unexpected parse failure
    # rather than letting it propagate. ---
    story = _parse_storybook(data, merged)
    if story is None:
        # A synthetic finding was already added to merged by _parse_storybook.
        return GateResult(
            report=merged,
            blocked=True,
            safety_flagged=False,
            context=context,
        )

    # --- PL-27: a fill result may not retain a <<FILL directive. Runs before
    # the rest of the policy layer so the first finding a reader sees on an
    # unwritten book names the actual cause, rather than whatever downstream
    # rule happens to trip over a directive-shaped body first. ---
    if context == "fill_result":
        merged.extend(check_fill_residue(story))
        # --- PL-28: an ADR-011 MVP/Test seed is a prototyping shell and must
        # never become a child-facing book. The generation selection layer
        # already drops seeds (skeleton_match._candidates); this is the same
        # exclusion on the manual import path, which had none. ---
        merged.extend(check_mvp_firewall(story))

    # --- Policy layer: age-safety and shape invariants (PL-15..PL-18) ---
    merged.extend(validate_policy(story))

    # --- Layer 2: state-space walk (Tier-2 only; Tier-1 short-circuits) ---
    merged.extend(validate_layer2(story))

    # --- CH-*: character envelope rules (ADR-028), participating books only;
    # validate_character returns an empty report for a book that neither opts
    # in nor uses a reserved name. ---
    merged.extend(validate_character(story))

    # --- RL-13: advisory reading-level check (WARNING, never blocks) ---
    merged.extend(check_reading_level(story))

    # --- CG-1..CG-4: advisory choice-grammar checks (WARNING, never blocks,
    # gated behind enforce_grammar per D3/D11 grandfathering) ---
    merged.extend(
        check_choice_grammar(
            story,
            enforce_grammar=enforce_grammar,
            is_fill_result=context == "fill_result",
        )
    )

    # --- SAFE-14: safety check (Phase-2 stub, always empty) ---
    merged.extend(check_safety(story))

    # --- Compute blocked and safety_flagged from the merged report ---
    blocked = any(
        f.severity is Severity.ERROR and f.rule_id.startswith(("CH", "L1", "L2", "PL"))
        for f in merged.findings
    )
    safety_flagged = any(f.rule_id == "SAFE-14" for f in merged.findings)

    return GateResult(
        report=merged,
        blocked=blocked,
        safety_flagged=safety_flagged,
        context=context,
    )


def _parse_storybook(
    data: Mapping[str, object],
    merged: ValidationReport,
) -> Storybook | None:
    """Attempt to parse the raw data as a Storybook.

    Layer 1 includes L1-1 (schema conformance), but a clean L1 report does
    not imply a clean Pydantic parse. L1-1 validates against the exported
    JSON Schema, which can express field shape and nothing else; the
    ``model_validator(mode="after")`` checks on :class:`Storybook` (schema
    version, unique ids, start node, variable references, ending count) have
    no JSON Schema representation and therefore run only here. This is a
    real, reachable path, not merely a defensive backstop.

    Args:
        data: The raw decoded story JSON mapping.
        merged: The merged report to append a synthetic finding to on failure.

    Returns:
        Storybook | None: The parsed model, or ``None`` if parsing failed
            (in which case a synthetic finding has been appended to
            ``merged``).
    """
    try:
        return Storybook.model_validate(dict(data))
    except PydanticValidationError as exc:
        # #ASSUME: data integrity: L1-1 passed but Pydantic still rejects the
        # document. The common cause is a model_validator(mode="after") check
        # that the exported JSON Schema cannot express, the most frequent
        # being an unsupported schema_version: schema/storybook.schema.json
        # constrains schema_version to {"type": "string"} with no pattern or
        # enum, so "3.0" and "banana" both clear L1-1 and are refused here.
        # Keeping build_schema() in sync with models.py cannot close that gap,
        # because JSON Schema has no way to carry an after-validator.
        # #VERIFY: the finding message below must carry Pydantic's own error
        # text so the reader sees WHICH validator refused the document; see
        # test_parse_storybook_reports_unsupported_schema_version in
        # tests/unit/test_gate.py.
        story_id_raw = data.get("id")
        story_id = story_id_raw if isinstance(story_id_raw, str) else "<unknown>"
        message = f"L1-1 schema: document failed Pydantic parse after L1: {exc}"
        merged.add(
            ValidationFinding(
                rule_id="L1-1",
                severity=Severity.ERROR,
                story_id=story_id,
                message=message,
            )
        )
        return None
