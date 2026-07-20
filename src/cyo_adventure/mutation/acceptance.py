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
unpromotable, never promoted.

D6 adds one stricter, reject-only stage for Tier-2 (stateful) candidates only,
between the cell assertion and promotability (design section 5.3/5.4): a single
configuration walk (the same result the gate's Layer 2 consumed, run once here)
drives an ending-coverage check, a clock re-proof over configurations, and, for a
state-only (graph-shape-unchanged) mutant, the state-signature floor. A capped
walk is itself an acceptance failure for a Tier-2 mutant (an unexplored state
space is unproven). Tier-1 candidates skip the stage entirely, so their D2
behavior is byte-identical. Stages 4 (contract acceptance) and 5 (sample fill) of
the design table land in D7-D8 at the marked point.

The safety invariant (design section 6, CR-2): the harness is structurally
incapable of marking a ``blocked=True`` gate result promotable. Promotability is
computed only after the gate stage has passed, every discard path (including the
Tier-2 stage's) returns a non-promotable result through the one discard builder,
and the Tier-2 floors/checks are reject-only (they can lower promotability, never
raise it).
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.contract_gate import contract_acceptance_reason
from cyo_adventure.mutation.floors import load_in_cell_catalog, structural_floor_reason
from cyo_adventure.mutation.identity import recompute_tier
from cyo_adventure.mutation.state_ops import (
    clock_floor_for,
    ending_coverage_gap,
    state_signature_floor_reason,
    walk_fastest_satisfying_finish,
)
from cyo_adventure.mutation.subtree import adjacency, node_ids
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.walk import walk_configurations

if TYPE_CHECKING:
    from collections.abc import Mapping

    from structlog.stdlib import BoundLogger

    from cyo_adventure.mutation.ops import MutationOp, OpParams, ReguideItem
    from cyo_adventure.storybook.theme_contract import ThemeContract
    from cyo_adventure.validator.walk import WalkResult

# The default configuration-walk cap, matching ``validator.walk`` and so the cap
# the gate's Layer 2 used. The Tier-2 acceptance stage runs its single walk at
# this cap so it computes coverage and the clock re-proof from the SAME result the
# gate's L2 verdict was derived from (design 5.3, single-WalkResult rule).
_DEFAULT_WALK_CAP = 100_000

# The metadata keys that together identify a story's inherited cell (design
# section 6, stage 2; OQ-4 fixes the cell in v1). A mutant must declare exactly
# its parent's cell.
#
# #ASSUME: data-integrity: ``topology`` is intentionally NOT a cell key (design
# 4.8, OQ-4). Topology is MUTABLE within the band's ADR-011 section-7 row: a
# structural operator (an M1 swap, an M4 insert-decision-reconvergence) can
# change the graph shape, and ``identity.redeclare_topology`` (run inside
# ``resync_metadata``) re-declares an admissible, band-legal topology, which PL-18
# re-proves at the gate. Pinning topology into the cell key would over-reject
# those topology-changing mutants as spurious "cell drift". The fixed cell is
# ``(age_band, length, narrative_style)`` plus ``tier`` (a mutant must not change
# tier); topology honesty is enforced by redeclare_topology's band-row check and
# PL-18, not by this assertion.
# #VERIFY: tests/unit/test_mutation_acceptance.py asserts a band-legal topology
# re-declaration is NOT discarded at stage 2 while tier/band/length/style drift
# IS, and that a topology outside the band row is rejected (redeclare raises /
# the gate blocks).
_CELL_KEYS: tuple[str, ...] = (
    "age_band",
    "length",
    "narrative_style",
    "tier",
)

# The empty re-guidance-resolution set, as a module constant so it is not a call
# in a parameter default (basedpyright reportCallInDefaultInitializer).
_NO_RESOLVED_REGUIDE: frozenset[str] = frozenset()


class Stage(StrEnum):
    """The ordered acceptance stages implemented so far (design section 6)."""

    PRECONDITIONS = "0-preconditions"
    GATE = "1-gate"
    CELL = "2-cell"
    # D6: the Tier-2-only stricter checks (ending coverage, clock re-proof over a
    # single walk, and the M5-only state-signature floor). Skipped for Tier-1.
    TIER2_STATE = "3-tier2-state"
    # D7: the structural anti-clone floor for graph-shape-CHANGED candidates
    # (design 4.6). Reject-only; runs only at the promotable decision point.
    STRUCTURE = "3-structure"
    # D7: contract acceptance for a mutant of a parameterized parent (design 4.7,
    # section 6 stage 4). Reject-only.
    CONTRACT = "4-contract"


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


def _graph_shape_unchanged(
    parent: Mapping[str, object], candidate: Mapping[str, object]
) -> bool:
    """Return whether the candidate leaves the node set and choice edges unchanged.

    A True result means the mutation is state-only (M5a, gate-choice, or
    relocate-effect): no node was added or removed and no choice target changed, so
    the anti-clone floor for it is the state-signature floor (design 5.4), not the
    structural floor (which lands in D7).

    Args:
        parent: The raw parent story document.
        candidate: The mutated candidate document.

    Returns:
        bool: True when the graph shape is identical to the parent's.
    """
    return node_ids(parent) == node_ids(candidate) and adjacency(parent) == adjacency(
        candidate
    )


def _tier2_state_stage(  # noqa: PLR0911 -- one cohesive reject-only precondition ladder, one reason each
    context: _RunContext,
    parent: Mapping[str, object],
    candidate: dict[str, object],
    *,
    walk_cap: int,
) -> str | None:
    """Run the D6 Tier-2 stricter checks over a single walk, or return a discard reason.

    Skipped (returns None, appends nothing) for a Tier-1 candidate, so Tier-1
    behavior is byte-identical to D2. For a Tier-2 candidate it runs exactly one
    ``walk_configurations`` at ``walk_cap`` (the same cap the gate's Layer 2 used)
    and drives every design 5.3/5.4 check from that single result. Reject-only:
    every path either returns a discard reason or (on success) appends one passed
    stage outcome and returns None.

    Args:
        context: The run accumulator (a passed outcome is appended on success).
        parent: The raw parent story document.
        candidate: The gate-passing candidate document.
        walk_cap: The configuration-walk cap.

    Returns:
        str | None: A discard reason, or None when the candidate passes (or is
            Tier-1 and the stage does not apply).
    """
    if recompute_tier(candidate) != 2:
        return None
    try:
        story = Storybook.model_validate(dict(candidate))
    except PydanticValidationError as exc:
        return f"Tier-2 candidate failed to parse for the state walk: {exc}"

    # #CRITICAL: data-integrity: coverage and the clock re-proof are computed from
    # the SAME single WalkResult (design 5.3, single-WalkResult rule); a second
    # walk with a different cap or engine could reach an ending the gate's walk
    # never did. This one walk at the gate's default cap also confirms consistency
    # with the gate's L2 verdict: a capped walk here means the state space is
    # unproven, an acceptance failure for a Tier-2 mutant even though the gate
    # reports the cap as its own L2-12 finding.
    # #VERIFY: test_mutation_acceptance.py forces a tiny walk_cap and asserts a
    # capped-walk discard at the Tier-2 stage on a gate-passing candidate.
    walk = walk_configurations(story, cap=walk_cap)
    if walk.capped:
        return (
            f"Tier-2 configuration walk hit the cap of {walk_cap}; an unexplored "
            f"state space is an unproven mutant (design 5.3)"
        )

    gap = ending_coverage_gap(story, walk)
    if gap:
        return (
            f"ending coverage gap: {sorted(gap)} never occur in any reachable "
            f"configuration (design 5.3 ending coverage)"
        )

    clock_reason = _clock_reproof_reason(story, walk)
    if clock_reason is not None:
        return clock_reason

    if _graph_shape_unchanged(parent, candidate):
        floor_reason = _state_floor_reason(parent, story, walk)
        if floor_reason is not None:
            return floor_reason

    context.stages.append(
        StageOutcome(
            stage=Stage.TIER2_STATE,
            passed=True,
            detail=_tier2_detail(story, walk),
        )
    )
    return None


def _clock_reproof_reason(story: Storybook, walk: WalkResult) -> str | None:
    """Return why the walk-derived fastest finish fails the clock re-proof, or None.

    Design 5.3 check 2: the fastest satisfying finish must be finite and at or
    above the cell's ``min_complete_floor``. A much slower real fastest finish is
    advisory (reported in the stage detail), not blocked.
    """
    floor = clock_floor_for(story)
    if floor is None:
        return None
    finish = walk_fastest_satisfying_finish(story, walk)
    if finish is None:
        return (
            "clock re-proof: no success/completion ending is reachable in any "
            "configuration (fastest satisfying finish is infinite)"
        )
    if finish < floor:
        return (
            f"clock re-proof: walk-derived fastest satisfying finish {finish} is "
            f"below the cell min_complete_floor {floor}"
        )
    return None


def _state_floor_reason(
    parent: Mapping[str, object], story: Storybook, walk: WalkResult
) -> str | None:
    """Return the state-signature floor reason for a state-only mutant, or None."""
    try:
        parent_story = Storybook.model_validate(dict(parent))
    except PydanticValidationError:
        # The parent is a gate-passed catalog skeleton, so this is unreachable in
        # practice; if it ever occurs, skip the floor rather than discard a
        # candidate that is not itself at fault.
        return None
    return state_signature_floor_reason(parent_story, story, walk)


def _tier2_detail(story: Storybook, walk: WalkResult) -> str:
    """Return the play-feel delta summary recorded on a passed Tier-2 stage."""
    finish = walk_fastest_satisfying_finish(story, walk)
    floor = clock_floor_for(story)
    return (
        f"Tier-2 checks passed: {len(walk.configs)} configs, fastest satisfying "
        f"finish {finish} (floor {floor}), full ending coverage"
    )


def _structural_floor_stage(
    context: _RunContext,
    parent: Mapping[str, object],
    candidate: dict[str, object],
    parent_slug: str,
) -> str | None:
    """Run the D7 structural anti-clone floor, or return a discard reason.

    Applies only to a graph-shape-CHANGED candidate (the caller routes; a
    shape-unchanged candidate used the state-signature floor in the Tier-2 stage).
    Loads the in-cell sibling catalog and applies the three design-4.6 clauses.
    Reject-only: on success it appends one passed stage outcome and returns None;
    on a clone it returns the discard reason without appending.

    Args:
        context: The run accumulator (a passed outcome is appended on success).
        parent: The raw parent story document.
        candidate: The gate-passing, shape-changed candidate document.
        parent_slug: The parent's catalog slug, excluded from the in-cell cohort.

    Returns:
        str | None: A discard reason, or None when the candidate clears the floor.
    """
    in_cell = load_in_cell_catalog(candidate, parent_slug)
    reason = structural_floor_reason(parent, candidate, in_cell)
    if reason is not None:
        return reason
    context.stages.append(
        StageOutcome(
            stage=Stage.STRUCTURE,
            passed=True,
            detail=(
                f"structural anti-clone floor cleared against {len(in_cell)} in-cell "
                f"tree(s)"
            ),
        )
    )
    return None


def _contract_stage(
    context: _RunContext,
    candidate: dict[str, object],
    mutated_contract: ThemeContract,
) -> str | None:
    """Run the D7 stage-4 contract acceptance, or return a discard reason.

    Reject-only (design 4.7, CR-2/CR-4): runs the mutated contract through the
    same deterministic checks ``check_theme_contract.py`` makes, in memory. On
    success it appends one passed stage outcome and returns None; on failure it
    returns the discard reason.

    Args:
        context: The run accumulator (a passed outcome is appended on success).
        candidate: The gate-passing candidate document.
        mutated_contract: The mutant's theme contract (a parameterized parent).

    Returns:
        str | None: A discard reason, or None when the contract is accepted.
    """
    reason = contract_acceptance_reason(candidate, mutated_contract)
    if reason is not None:
        return reason
    context.stages.append(
        StageOutcome(
            stage=Stage.CONTRACT,
            passed=True,
            detail="mutated contract passed acceptance (incl. the band-mandatory floor)",
        )
    )
    return None


def run_acceptance(  # noqa: PLR0913, C901, PLR0911 -- one cohesive stage ladder, one discard return per stage
    op: MutationOp,
    parent: Mapping[str, object],
    params: OpParams,
    *,
    seed: int = 0,
    parent_slug: str = "<unknown>",
    resolved_reguide_ids: frozenset[str] = _NO_RESOLVED_REGUIDE,
    walk_cap: int = _DEFAULT_WALK_CAP,
    mutated_contract: ThemeContract | None = None,
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
            The reguide.json resolution flow is D8; this is the extension point.
        walk_cap: The configuration-walk cap for the Tier-2 stage (default the
            gate's own cap). Tests lower it to force a capped-walk discard.
        mutated_contract: The mutant's theme contract, for a parameterized
            parent. When supplied, stage 4 (contract acceptance, design 4.7)
            runs; when None, the mutant lands contract-less at parity with its
            parent (design 4.7, OQ-2). The caller supplies it (the CLI computes
            it for parameterized parents in D8).
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

    # --- Stage 3 (Tier-2 only): stricter state checks (design 5.3/5.4) ---
    # Reject-only and gated to Tier-2 candidates; a Tier-1 candidate skips it, so
    # its outcome is byte-identical to D2. Any failure routes through the one
    # discard builder, keeping the CR-2 invariant intact.
    tier2_reason = _tier2_state_stage(context, parent, candidate, walk_cap=walk_cap)
    if tier2_reason is not None:
        _emit_discard(Stage.TIER2_STATE, tier2_reason, ())
        return _discard(
            context,
            Stage.TIER2_STATE,
            tier2_reason,
            gate_summary=gate_summary,
            candidate=candidate,
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
    # Floors (stage 3) and contracts (stage 4) below are reject-only: they can
    # only lower this flag (by discarding), never raise it.
    # #VERIFY: test_mutation_acceptance.py monkeypatches run_gate to always block
    # and asserts the result is never promotable.
    would_be_promotable = (not gate.blocked) and cell_ok and len(outstanding) == 0

    # --- Stage 3 (structural anti-clone floor): shape-changed candidates only ---
    # #CRITICAL: data-integrity: the structural floor is reject-only and gates
    # ONLY the promotable decision (design 4.6). A candidate already held for
    # re-guidance stays held (it is not promotable regardless), and a
    # shape-UNCHANGED (M5-only) candidate used the state-signature floor in the
    # Tier-2 stage above; running both would double-count. So the floor runs only
    # for a would-be-promotable, graph-shape-CHANGED candidate, and it can only
    # turn that promotion into a discard, never admit anything (CR-2).
    # #VERIFY: test_mutation_acceptance.py asserts a resolved-reguide M1 swap that
    # genuinely re-shapes the tree stays promotable, and test_mutation_floors.py
    # pins the clone-rejection clauses on the floor function directly.
    if would_be_promotable and not _graph_shape_unchanged(parent, candidate):
        struct_reason = _structural_floor_stage(context, parent, candidate, parent_slug)
        if struct_reason is not None:
            _emit_discard(Stage.STRUCTURE, struct_reason, ())
            return _discard(
                context,
                Stage.STRUCTURE,
                struct_reason,
                gate_summary=gate_summary,
                candidate=candidate,
            )

    # --- Stage 4 (contract acceptance): parameterized parents only ---
    # Reject-only; runs whenever the caller supplied the mutant's contract (a
    # parameterized parent). A contract-less parent's mutant lands contract-less
    # at parity (design 4.7, OQ-2). CR-4: the band-mandatory floor is unioned
    # inside the contract check regardless of contract content.
    if mutated_contract is not None:
        contract_reason = _contract_stage(context, candidate, mutated_contract)
        if contract_reason is not None:
            _emit_discard(Stage.CONTRACT, contract_reason, ())
            return _discard(
                context,
                Stage.CONTRACT,
                contract_reason,
                gate_summary=gate_summary,
                candidate=candidate,
            )

    return AcceptanceResult(
        promotable=would_be_promotable,
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
