"""The WS-5 acceptance harness: the section 6 stage table (D2 subset).

Every mutation attempt runs an ordered stage table; the first failing stage
discards the candidate with a structured ``mutation.discarded`` log. D2
implements the Tier-1 subset of that table:

- **Stage 0 (preconditions):** ``op.preconditions(parent, params)``.
- **Stage 1 (gate):** ``validator.gate.run_gate(candidate)`` at the standard
  scale, the identical, unchanged gate every hand-authored skeleton passes. A
  blocked result discards; no code path here constructs a gate result, filters
  findings, passes a non-standard scale, or overrides the block (design CR-2).
- **Stage 2 (cell assertion):** the candidate's declared ``(age_band, length,
  narrative_style, topology, tier)`` cell equals the inherited parent cell.

Beyond the stages, re-guidance is tracked: a candidate that clears stages 0-2
but still carries unresolved re-guidance items is *held*, exists and is marked
unpromotable, never promoted. Stages 3 (floors), 4 (contract acceptance), and 5
(sample fill) of the design table are out of scope for D2 and land in D6-D8; the
stage list is ordered and each stage returns a typed outcome, so those extend
cleanly at the marked points.

The safety invariant (design section 6, CR-2): the harness is structurally
incapable of marking a ``blocked=True`` gate result promotable. Promotability is
computed only after the gate stage has passed, and every discard path returns a
non-promotable result.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    from collections.abc import Mapping

    from structlog.stdlib import BoundLogger

    from cyo_adventure.mutation.ops import MutationOp, OpParams, ReguideItem

# The metadata keys that together identify a story's inherited cell (design
# section 6, stage 2; OQ-4 fixes the cell in v1). A mutant must declare exactly
# its parent's cell.
_CELL_KEYS: tuple[str, ...] = (
    "age_band",
    "length",
    "narrative_style",
    "topology",
    "tier",
)

# The empty re-guidance-resolution set, as a module constant so it is not a call
# in a parameter default (basedpyright reportCallInDefaultInitializer).
_NO_RESOLVED_REGUIDE: frozenset[str] = frozenset()


class Stage(StrEnum):
    """The ordered acceptance stages implemented in D2 (design section 6)."""

    PRECONDITIONS = "0-preconditions"
    GATE = "1-gate"
    CELL = "2-cell"


@dataclass(frozen=True, slots=True)
class StageOutcome:
    """The typed result of one acceptance stage.

    Attributes:
        stage: Which stage this outcome is for.
        passed: Whether the stage passed.
        detail: A human-readable explanation (the failing reason when not passed).
        rule_ids: The gate rule ids implicated, when the stage is the gate stage.
    """

    stage: Stage
    passed: bool
    detail: str
    rule_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    """The outcome of running the D2 acceptance stage table on one attempt.

    Attributes:
        promotable: True only when every stage passed and no re-guidance item is
            outstanding. Never True for a discarded or held candidate.
        discarded_at_stage: The stage that discarded the candidate, or None when
            the candidate cleared every implemented stage (promotable or held).
        reguide_outstanding: The count of unresolved re-guidance items.
        gate_summary: The serialized stage-1 gate report (empty before stage 1).
        discard_reason: The failing reason when discarded; empty otherwise.
        stages: The per-stage outcomes, in run order.
        candidate: The mutated shell, present once stage 1 has a candidate to
            evaluate (including a gate-blocked one, kept for debugging); None on a
            stage-0 discard.
        reguide: The re-guidance items the operator emitted.
    """

    promotable: bool
    discarded_at_stage: Stage | None
    reguide_outstanding: int
    gate_summary: Mapping[str, object]
    discard_reason: str
    stages: tuple[StageOutcome, ...]
    candidate: dict[str, object] | None
    reguide: tuple[ReguideItem, ...] = ()

    @property
    def held(self) -> bool:
        """Return True when the candidate cleared every stage but is unpromotable.

        A held candidate exists (its shell is valid and cell-correct) but carries
        unresolved re-guidance, so it is not promotable; it is the expected D2
        outcome for an accepted M1 mutant.
        """
        return (
            self.candidate is not None
            and self.discarded_at_stage is None
            and not self.promotable
        )


def _content_hash(document: Mapping[str, object]) -> str:
    """Return the SHA-256 hex digest of a document's canonical JSON form.

    Args:
        document: The document to hash.

    Returns:
        str: The hex digest, used as the parent content hash in the discard log
            and (in D8) the lineage record.
    """
    # #EDGE: data-integrity: the parent hash lets a later promotion tool detect a
    # bundle derived from a since-changed parent (design section 9.2). SHA-256 is
    # a FIPS-approved digest, so this is safe on FIPS-enabled deployments.
    # #VERIFY: identical documents hash identically; canonical (sorted-key) JSON
    # removes key-order noise.
    canonical = json.dumps(document, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _summarize_gate(
    blocked: bool, safety_flagged: bool, report_dict: object
) -> dict[str, object]:
    """Return a JSON-serializable summary of a gate result.

    Args:
        blocked: Whether the gate blocked.
        safety_flagged: Whether a SAFE-14 finding was present.
        report_dict: The gate report's own ``to_dict()`` output.

    Returns:
        dict[str, object]: The serialized summary.
    """
    return {
        "blocked": blocked,
        "safety_flagged": safety_flagged,
        "report": report_dict,
    }


def _cell_of(story: Mapping[str, object]) -> dict[str, object]:
    """Return a story's declared cell tuple as a key/value map.

    Args:
        story: The raw story document.

    Returns:
        dict[str, object]: The ``_CELL_KEYS`` values from ``story.metadata`` (a
            missing key maps to None).
    """
    meta = story.get("metadata")
    metadata: Mapping[str, object] = (
        cast("Mapping[str, object]", meta) if isinstance(meta, dict) else {}
    )
    return {key: metadata.get(key) for key in _CELL_KEYS}


def _cell_matches(
    parent: Mapping[str, object], candidate: Mapping[str, object]
) -> tuple[bool, str]:
    """Return whether the candidate declares exactly the parent's cell.

    Reimplements the design section 6 stage-2 cell assertion at the dict level.
    ``scripts.check_skeleton._check_brief`` is coupled to an ``argparse.Namespace``
    (it reads ``.band``/``.length``/... attributes), so it is not a clean import
    for a document-to-document comparison; comparing the ``_CELL_KEYS`` values
    directly is the design's stated fallback and the exact property stage 2 needs.

    Args:
        parent: The raw parent story document.
        candidate: The mutated candidate document.

    Returns:
        tuple[bool, str]: ``(matches, detail)``; ``detail`` names the first
            differing key when it does not match.
    """
    parent_cell = _cell_of(parent)
    candidate_cell = _cell_of(candidate)
    for key in _CELL_KEYS:
        if parent_cell[key] != candidate_cell[key]:
            detail = (
                f"cell drift on '{key}': parent {parent_cell[key]!r} != "
                f"candidate {candidate_cell[key]!r}"
            )
            return False, detail
    return True, "declared cell equals the inherited parent cell"


@dataclass(slots=True)
class _RunContext:
    """Mutable accumulator threaded through one acceptance run."""

    stages: list[StageOutcome] = field(default_factory=list)


def _discard(  # noqa: PLR0913 -- one cohesive discard-record builder, mostly keyword-only
    context: _RunContext,
    stage: Stage,
    reason: str,
    *,
    gate_summary: Mapping[str, object],
    candidate: dict[str, object] | None,
    rule_ids: tuple[str, ...] = (),
) -> AcceptanceResult:
    """Build a non-promotable discard result and record the failing stage.

    Every discard flows through here, so a discarded candidate is never
    promotable by construction.

    Args:
        context: The run accumulator (the failing stage outcome is appended).
        stage: The stage that discarded the candidate.
        reason: The human-readable discard reason.
        gate_summary: The serialized gate summary (empty before stage 1).
        candidate: The candidate under evaluation, or None on a stage-0 discard.
        rule_ids: The gate rule ids implicated, when discarding at the gate stage.

    Returns:
        AcceptanceResult: The non-promotable discard result.
    """
    context.stages.append(
        StageOutcome(stage=stage, passed=False, detail=reason, rule_ids=rule_ids)
    )
    return AcceptanceResult(
        promotable=False,
        discarded_at_stage=stage,
        reguide_outstanding=0,
        gate_summary=gate_summary,
        discard_reason=reason,
        stages=tuple(context.stages),
        candidate=candidate,
        reguide=(),
    )


def run_acceptance(  # noqa: PLR0913 -- one cohesive harness entry point, mostly keyword-only
    op: MutationOp,
    parent: Mapping[str, object],
    params: OpParams,
    *,
    seed: int = 0,
    parent_slug: str = "<unknown>",
    resolved_reguide_ids: frozenset[str] = _NO_RESOLVED_REGUIDE,
    logger: BoundLogger | None = None,
) -> AcceptanceResult:
    """Run the D2 acceptance stage table for one mutation attempt.

    Owns the whole cheap-to-expensive pipeline: stage 0 preconditions, then
    ``op.apply`` (reproducibly, from ``seed``), then stage 1 gate and stage 2
    cell assertion. A discard at any stage returns a non-promotable result and
    emits one ``mutation.discarded`` log line. A candidate that clears every
    stage is promotable only when no re-guidance item is outstanding; otherwise
    it is held (exists, unpromotable).

    Args:
        op: The operator to run.
        parent: The raw parent story document.
        params: The operator parameters.
        seed: The rng seed, recorded for replay (design section 3, principle 5).
        parent_slug: The parent's catalog slug, for the discard log.
        resolved_reguide_ids: Re-guidance ``target_id`` values already resolved.
            D2 never resolves any (the reguide.json flow is D8); this is the
            documented extension point.
        logger: The structlog logger to emit discards on; defaults to this
            module's logger.

    Returns:
        AcceptanceResult: The typed outcome of the run.
    """
    log = logger if logger is not None else get_logger(__name__)
    context = _RunContext()
    parent_hash = _content_hash(parent)

    def _emit_discard(stage: Stage, reason: str, rule_ids: tuple[str, ...]) -> None:
        # design section 6 opening paragraph: parent slug + content hash, op id,
        # params, seed, failing stage, and rule ids.
        log.info(
            "mutation.discarded",
            parent_slug=parent_slug,
            parent_sha256=parent_hash,
            op_id=op.op_id,
            params=params.mapping,
            seed=seed,
            failing_stage=str(stage),
            rule_ids=list(rule_ids),
            reason=reason,
        )

    # --- Stage 0: preconditions ---
    report = op.preconditions(parent, params)
    if not report.satisfied:
        reason = "; ".join(report.failures) or "preconditions not satisfied"
        _emit_discard(Stage.PRECONDITIONS, reason, ())
        return _discard(
            context,
            Stage.PRECONDITIONS,
            reason,
            gate_summary={},
            candidate=None,
        )
    context.stages.append(
        StageOutcome(
            stage=Stage.PRECONDITIONS,
            passed=True,
            detail="operator preconditions satisfied",
        )
    )

    # --- Apply the operator reproducibly from the seed ---
    try:
        result = op.apply(parent, params, random.Random(seed))  # noqa: S311 -- deterministic replay rng, not a cryptographic use
    except ValidationError as exc:
        # Preconditions passed, so this is unexpected; treat it as a stage-0
        # discard rather than letting it escape (a failed apply produces no
        # promotable artifact either way).
        reason = f"apply failed after preconditions passed: {exc}"
        _emit_discard(Stage.PRECONDITIONS, reason, ())
        return _discard(
            context,
            Stage.PRECONDITIONS,
            reason,
            gate_summary={},
            candidate=None,
        )
    candidate = result.candidate

    # --- Stage 1: the full, unchanged gate at the standard scale ---
    gate = run_gate(candidate)
    error_rule_ids = tuple(sorted({f.rule_id for f in gate.report.errors}))
    gate_summary = _summarize_gate(
        gate.blocked, gate.safety_flagged, gate.report.to_dict()
    )
    if gate.blocked:
        reason = "gate blocked the candidate: " + (
            ", ".join(error_rule_ids) or "no error rule ids"
        )
        _emit_discard(Stage.GATE, reason, error_rule_ids)
        return _discard(
            context,
            Stage.GATE,
            reason,
            gate_summary=gate_summary,
            candidate=candidate,
            rule_ids=error_rule_ids,
        )
    context.stages.append(
        StageOutcome(
            stage=Stage.GATE,
            passed=True,
            detail="gate did not block the candidate",
            rule_ids=error_rule_ids,
        )
    )

    # --- Stage 2: cell assertion ---
    cell_ok, cell_detail = _cell_matches(parent, candidate)
    if not cell_ok:
        _emit_discard(Stage.CELL, cell_detail, ())
        return _discard(
            context,
            Stage.CELL,
            cell_detail,
            gate_summary=gate_summary,
            candidate=candidate,
        )
    context.stages.append(
        StageOutcome(stage=Stage.CELL, passed=True, detail=cell_detail)
    )

    # --- Re-guidance tracking ---
    outstanding = tuple(
        item for item in result.reguide if item.target_id not in resolved_reguide_ids
    )

    # #CRITICAL: security: promotability is the single gate between a machine
    # transform and a child-facing catalog. It is computed here, only after the
    # gate stage has already passed (a blocked result returned above), and it
    # re-asserts ``not gate.blocked`` so no future refactor that reorders the
    # returns can make a blocked candidate promotable (design section 6, CR-2).
    # Floors (stage 3) and contracts (stage 4) are reject-only and land in D7;
    # they can only lower this flag, never raise it.
    # #VERIFY: test_mutation_acceptance.py monkeypatches run_gate to always block
    # and asserts the result is never promotable.
    promotable = (not gate.blocked) and cell_ok and len(outstanding) == 0

    # TODO(ws5-d7): insert stage 3 (anti-clone / state-signature floors) here;
    # reject-only, never admitting.
    # TODO(ws5-d8): insert stage 4 (contract acceptance) and stage 5 (sample
    # fill) here for parameterized parents.

    return AcceptanceResult(
        promotable=promotable,
        discarded_at_stage=None,
        reguide_outstanding=len(outstanding),
        gate_summary=gate_summary,
        discard_reason="",
        stages=tuple(context.stages),
        candidate=candidate,
        reguide=result.reguide,
    )


def acceptance_to_dict(result: AcceptanceResult) -> dict[str, object]:
    """Return a JSON-serializable view of an acceptance result.

    Used by the D2 CLI to write a minimal ``acceptance.json``. The full
    promotion bundle (lineage, sample fill, diagram) is D8; this is deliberately
    the stage transcript plus the gate summary and re-guidance list only.

    Args:
        result: The acceptance result to serialize.

    Returns:
        dict[str, object]: The serialized view.
    """
    return {
        "promotable": result.promotable,
        "held": result.held,
        "discarded_at_stage": (
            str(result.discarded_at_stage)
            if result.discarded_at_stage is not None
            else None
        ),
        "discard_reason": result.discard_reason,
        "reguide_outstanding": result.reguide_outstanding,
        "stages": [
            {
                "stage": str(outcome.stage),
                "passed": outcome.passed,
                "detail": outcome.detail,
                "rule_ids": list(outcome.rule_ids),
            }
            for outcome in result.stages
        ],
        "reguide": [
            {
                "target": str(item.target),
                "target_id": item.target_id,
                "reason": item.reason,
                "current_text": item.current_text,
            }
            for item in result.reguide
        ],
        "gate_summary": dict(result.gate_summary),
        "bundle_note": (
            "D2 minimal acceptance record; lineage.json, sample-fill, and the "
            "diagram are D8, and the anti-clone/contract stages are D7"
        ),
    }
