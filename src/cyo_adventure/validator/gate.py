"""Combined validation gate runner (WP4).

Orchestrates all validator layers in the correct order for a decoded story
mapping. This is the single entry point the generation orchestrator and the
API validate endpoint call.

Rule application order (per ``docs/planning/validator-rules.md``
"Rule Application Order" and tech-spec "Validation gate"):

1. Layer 1 (L1-1..L1-7): graph structure, schema conformance, logic.
2. **Early return on any L1 ERROR**: the graph must be sound before a
   state-space walk is meaningful, and the document may not even parse.
3. Policy (PL-15..PL-18): age-safety and shape invariants on the parsed
   model (forbidden ending kinds, content ceilings, floors, topology).
4. Layer 2 (L2-9..L2-12): state-space walk, Tier-2 only (Tier-1 skips).
5. RL-13: advisory reading-level check (WARNING, never blocks).
6. SAFE-14: safety content check (Phase-2 stub, always empty).

Blocking semantics
------------------
``blocked`` is ``True`` when any ERROR-severity finding whose ``rule_id``
starts with ``"L1"``, ``"L2"``, or ``"PL"`` is present in the merged report.
RL-13 findings are WARNING and must not set ``blocked``. SAFE-14 findings
route to human review and are tracked separately via ``safety_flagged``.

``safety_flagged`` is ``True`` when any finding with ``rule_id == "SAFE-14"``
exists in the merged report. In Phase 2 the safety stub is empty, so this
will always be ``False`` -- but the computation is honest so Phase 3 works
without changing this function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.layer1 import Scale, validate_layer1
from cyo_adventure.validator.layer2 import validate_layer2
from cyo_adventure.validator.policy import validate_policy
from cyo_adventure.validator.reading_level import check_reading_level
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)
from cyo_adventure.validator.safety import check_safety

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class GateResult:
    """The combined outcome of all validation layers.

    Attributes:
        report: Merged findings across all layers run, in order: L1, L2,
            RL, SAFE.
        blocked: ``True`` when any ERROR-severity finding whose rule_id
            starts with ``"L1"``, ``"L2"``, or ``"PL"`` is present. RL-13
            warnings and SAFE-14 findings never set this flag.
        safety_flagged: ``True`` when any finding with rule_id ``"SAFE-14"``
            is present. Always ``False`` in Phase 2 (stub is empty), but
            computed honestly so Phase 3 does not require changes here.
    """

    report: ValidationReport
    blocked: bool
    safety_flagged: bool


def run_gate(data: Mapping[str, object], scale: Scale = "standard") -> GateResult:
    """Run all validation layers and return a combined gate result.

    Accepts the raw decoded story JSON (a mapping) because Layer 1 operates
    on raw JSON and must run before we can trust the document parses. Later
    layers receive the parsed ``Storybook`` if Layer 1 passes.

    Args:
        data: The raw decoded story JSON mapping.
        scale: Story-size profile the L1-7 budget is enforced against
            (``"standard"`` or ``"compact"``); forwarded to Layer 1.

    Returns:
        GateResult: The merged report, block status, and safety flag.
    """
    merged = ValidationReport()

    # --- Layer 1: graph structure, schema, logic ---
    l1_report = validate_layer1(data, scale)
    for finding in l1_report.findings:
        merged.add(finding)

    if not l1_report.ok:
        # The graph is structurally unsound; the document may not even parse.
        # Do not run Layer 2, reading-level, or safety on broken input.
        return GateResult(
            report=merged,
            blocked=True,
            safety_flagged=False,
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
        )

    # --- Policy layer: age-safety and shape invariants (PL-15..PL-18) ---
    policy_report = validate_policy(story)
    for finding in policy_report.findings:
        merged.add(finding)

    # --- Layer 2: state-space walk (Tier-2 only; Tier-1 short-circuits) ---
    l2_report = validate_layer2(story)
    for finding in l2_report.findings:
        merged.add(finding)

    # --- RL-13: advisory reading-level check (WARNING, never blocks) ---
    rl_report = check_reading_level(story)
    for finding in rl_report.findings:
        merged.add(finding)

    # --- SAFE-14: safety check (Phase-2 stub, always empty) ---
    safe_report = check_safety(story)
    for finding in safe_report.findings:
        merged.add(finding)

    # --- Compute blocked and safety_flagged from the merged report ---
    blocked = any(
        f.severity is Severity.ERROR and f.rule_id.startswith(("L1", "L2", "PL"))
        for f in merged.findings
    )
    safety_flagged = any(f.rule_id == "SAFE-14" for f in merged.findings)

    return GateResult(
        report=merged,
        blocked=blocked,
        safety_flagged=safety_flagged,
    )


def _parse_storybook(
    data: Mapping[str, object],
    merged: ValidationReport,
) -> Storybook | None:
    """Attempt to parse the raw data as a Storybook.

    Layer 1 includes L1-1 (schema conformance), so a parse failure after a
    clean L1 report should not occur in practice. This guard exists as a
    defensive backstop; it does not duplicate L1-1 logic.

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
        # #EDGE: data integrity: L1-1 passed but Pydantic still rejects the
        # document. This should not occur in practice because L1-1 validates
        # against the schema exported from the same Pydantic models, but a
        # schema-drift scenario could trigger it.
        # #VERIFY: ensure schema_export.build_schema() stays in sync with the
        # Pydantic model definitions (review whenever models.py changes).
        story_id_raw = data.get("id")
        story_id = story_id_raw if isinstance(story_id_raw, str) else "<unknown>"
        merged.add(
            ValidationFinding(
                rule_id="L1-1",
                severity=Severity.ERROR,
                story_id=story_id,
                message=(
                    f"L1-1 schema: document failed Pydantic parse after L1 "
                    f"(schema drift?): {exc}"
                ),
            )
        )
        return None
