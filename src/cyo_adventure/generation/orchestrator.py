"""Staged generation orchestrator with bounded repair loop (WP8).

Drives the three-stage pipeline (Structure -> Prose -> Repair) that turns a
:class:`~cyo_adventure.generation.concept.ConceptBrief` into a validated
Storybook JSON document.

Stage flow::

    Stage A (Structure): assemble prompt -> PII-guard -> call provider ->
                         parse JSON -> run_gate
        |
        +-- if blocked: skip Stage B, enter repair loop on Stage A doc
        |
        +-- if clean: continue to Stage B
        |
    Stage B (Prose):     assemble prompt -> PII-guard -> call provider ->
                         parse JSON -> run_gate
        |
    Stage C (Repair, bounded):  while blocked AND attempts < max_repairs:
        assemble repair prompt -> PII-guard -> call provider ->
        parse JSON -> run_gate -> check no-progress signature

Outcome mapping:
    - gate clean, not safety_flagged  -> "passed"
    - gate clean, safety_flagged       -> "needs_review"
    - blocked after exhausting repairs -> "needs_review" (doc produced)
    - blocked, no doc produced         -> "failed"
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, cast

from cyo_adventure.core.exceptions import ConfigurationError, ValidationError
from cyo_adventure.generation.chunking import (
    UnpartitionableSkeletonError,
    batch_request,
    merge_fill_batch,
    plan_fill_batches,
    written_prose,
)
from cyo_adventure.generation.fidelity_gate import run_stage1_gate
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.metered import ledger_of
from cyo_adventure.generation.normalize_fill import normalize_filled_story
from cyo_adventure.generation.prompts import (
    FillBatchPayload,
    build_bound_fill_prompt,
    build_fidelity_repair_prompt,
    build_fill_prompt,
    build_fill_subset_bound_prompt,
    build_fill_subset_prompt,
    build_prose_prompt,
    build_repair_prompt,
    build_structure_prompt,
)
from cyo_adventure.generation.reading_level_loop import (
    ReadingLevelContext,
    ReadingLevelResult,
    run_reading_level_loop,
)
from cyo_adventure.generation.skeleton import (
    _FEASIBILITY_MARGIN,  # pyright: ignore[reportPrivateUsage]
    MAX_FILL_OUTPUT_TOKENS,
    active_fill_model,
    estimate_input_tokens,
    expected_output_tokens,
    is_fill_feasible,
    resolve_context_window,
    resolve_output_cap,
    story_fill_rate,
)
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.gate import GateContext, GateResult, run_gate
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from cyo_adventure.core.config import Settings
    from cyo_adventure.generation.concept import ConceptBrief
    from cyo_adventure.generation.pii import PiiContext
    from cyo_adventure.generation.prompts import StagePrompt
    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.generation.usage import UsageLedger
    from cyo_adventure.validator.layer1 import Scale

__all__ = [
    "GenerationOutcome",
    "fill_skeleton",
    "generate_story",
]

# #CRITICAL: security: PiiGuardedProvider wraps the caller-supplied provider in
# generate_story() before any stage helper receives it; both system and user
# blocks are screened on every complete() call, aborting before external egress.
# #VERIFY: test_orchestrator asserts provider.calls is empty when a brief would
# leak a seeded real-child name (PII abort test case).

# #ASSUME: external-resources: provider.complete performs network I/O in real
# impls (mocked here); the orchestrator is provider-agnostic via the
# GenerationProvider protocol.
# #VERIFY: the Phase 2b adapters supply timeout/retry/backoff (see
# providers/_base.run_with_retries and the OpenRouter/Anthropic/Modal adapters);
# build_provider injects them, covered by test_providers.

# The role instruction and JSON-only directive now live in each stage template's
# system block (the cacheable region), so no shared system constant is needed
# here; the orchestrator forwards StagePrompt.system to the provider verbatim.

# Output ceilings sized to the largest briefs, NOT a budget: providers bill the
# tokens actually generated, so a high ceiling is free for small stories and only
# prevents truncation for big ones. A 2026-06-22 live run showed the old 4096/8192
# caps truncated mid-JSON for larger stories, surfacing as L1-1 "not valid JSON"
# (a 30-node Stage A even produced no parseable doc at all). The band budgets allow
# up to 60 nodes; a full-prose story of that size at 250 words/node runs well past
# 8192 output tokens, and even the one-line Stage A skeleton exceeds 4096.
_MAX_TOKENS_STRUCTURE = 16384
# Owned by generation/skeleton.py so this file and the feasibility screen in
# skeleton_match hold ONE default rather than two that drift. It is the default,
# not necessarily the cap a given call runs under: `fill_skeleton` clamps it to
# the configured model's own ceiling when it has Settings, and falls back to
# this value when it does not. See the note on `skeleton_match._FILL_MAX_TOKENS`
# for why the screen deliberately stays on the unclamped default (`AL-425`).
_MAX_TOKENS_PROSE = MAX_FILL_OUTPUT_TOKENS
# The FLOOR for a repair completion, not the value every repair uses. A repair
# prompt asks for the whole corrected document, so the effective cap is
# max(this, the cap the fill ran under); see `_RepairContext.max_tokens`.
_MAX_TOKENS_REPAIR = 32000

# Reading-level repair passes (Stage D). On by default rather than opt-in, which
# is the whole content of AL-292's proposed change: "put the reading-level repair
# loop in the harness, not the prompt, and make it non-optional". A prompt cannot
# reach this target because the model cannot count syllables (AL-288), so an
# instrumented loop is not an enhancement over the prompt, it is the only thing
# that works.
#
# Two passes rather than one because the first pass is where a body moves
# furthest and the second catches nodes that improved but not enough; and rather
# than three because acceptance is strictly monotone, so later passes hit
# diminishing returns against real per-batch spend. Costs zero provider calls
# when everything already sits in band.
_DEFAULT_READING_LEVEL_PASSES = 2

# Type alias: (sorted_findings_tuple, doc_sha256_hex)
_Signature = tuple[tuple[tuple[str, str | None, str | None, str], ...], str]

# What a caller is asking of the Stage 1 fidelity gate. See fill_skeleton's
# `stage1_gate` argument for why this is stated rather than inferred.
Stage1Posture = Literal["auto", "required", "skipped"]

_logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class GenerationOutcome:
    """The final outcome of a staged generation run.

    Attributes:
        status: ``"passed"`` if the gate is clean, ``"needs_review"`` if a
            document was produced but the gate is blocked or safety flagged,
            ``"failed"`` if no parseable document was produced at all.
        storybook: The decoded final Storybook JSON dict when any document was
            produced; ``None`` only on ``"failed"`` status.
        report: The final gate result as a serializable mapping (``to_dict()``
            output).
        attempts: Number of repair attempts performed (0 means the story
            passed without needing any repair).
        stage_log: Human-readable execution trail ordered by stage, e.g.
            ``["stage_a:gate_ok", "stage_b:blocked", "repair:1", ...]``.
        sentinel_manifest: The derived at-rest sentinel manifest
            (:func:`~cyo_adventure.storybook.reinsertion.build_manifest`'s
            shape) for `storybook`, when the skeleton-fill path ran the
            ADR-023 Stage R reinsertion transform; ``None`` for every other
            caller (:func:`generate_story`, the legacy no-sidecar fill
            path). This module never touches storage; the field is carried
            so ``generation/worker.py`` can hand it to
            ``persist_storybook``, which stamps it onto
            ``storybook_version.sentinel_manifest``. A ``None`` here
            therefore persists as a NULL column, meaning "no transform ran",
            not "the transform found nothing".
        personalization_eligible: ``True`` only when the contract that bound
            declared at least one ``personalizable`` slot AND the reinsertion
            transform actually produced a manifest for `storybook` (ADR-023
            Task D4). Computed once, at the same point `sentinel_manifest` is
            derived, and carried unchanged to ``generation/worker.py``'s
            persist step, which stamps it onto
            ``storybook_version.personalization_eligible`` verbatim. Defaults
            to ``False``, matching the column's own default and every
            non-fill early-return path in ``_run_skeleton_fill`` (e.g. the
            cannot-carry degraded-interpretation return), none of which has
            resolved a manifest yet.
    """

    status: Literal["passed", "needs_review", "failed"]
    storybook: dict[str, object] | None
    report: dict[str, object]
    attempts: int
    stage_log: list[str]
    sentinel_manifest: dict[str, object] | None = None
    personalization_eligible: bool = False


@dataclass(frozen=True, slots=True)
class _Stage1Config:
    """The Stage 1 fidelity-gate inputs the repair loop needs to run the gate.

    Present only for the authoring skeleton-fill path (constructed by
    :func:`fill_skeleton` when its Stage 1 parameters are supplied); ``None`` on
    :func:`_RepairContext` for :func:`generate_story` and every other caller,
    which do no authoring Stage 1 and so must be byte-identical to the
    pre-fold behavior.

    Attributes:
        original: The unfilled skeleton (FILL directives intact) the fill is
            checked against. This is :func:`fill_skeleton`'s own ``skeleton``
            argument.
        review_stage1_model: Optional admin-chosen review-model override for the
            semantic fidelity check.
        prep_model: The model that wrote the fill; the semantic check's
            review-model default when ``review_stage1_model`` is unset (#134).
        settings: Application settings (review-backend selection).
        pii: PII context for the egress guard on the semantic-check prompt.
        ledger: The run's usage ledger when the caller is metering, else
            ``None``. Carried so the gate's own review call is billed to the
            same job as the fill that provoked it.
    """

    original: dict[str, object]
    review_stage1_model: str | None
    prep_model: str | None
    settings: Settings
    pii: PiiContext
    ledger: UsageLedger | None = None


@dataclass(slots=True)
class _RepairContext:
    """Grouped parameters for the repair loop to stay under the arg-count limit.

    Not frozen: ``stage_log`` is mutated in place (appended to) by
    ``_run_repair_loop``. Making this frozen while holding a mutable list field
    would be a footgun (the list itself is still mutable even under ``frozen``).

    Attributes:
        provider: The PII-guarded generation provider (a :class:`PiiGuardedProvider`
            wrapping the real backend).
        max_repairs: Maximum number of repair attempts.
        stage_log: Accumulated log list; entries are appended in place.
        scale: Story-size profile forwarded to each repair stage's gate.
        context: Gate posture forwarded to each repair stage. A repair of a
            fill result is still a fill result, so PL-27 must keep applying
            across the loop; otherwise a repair attempt would launder an
            unwritten book past the floor that caught it (AL-325).
        stage1: The Stage 1 fidelity-gate config for the authoring skeleton-fill
            path, or ``None`` (the default) for callers that do no Stage 1 and
            must retain the pre-fold structural-only loop behavior.
        max_tokens: Output cap for each repair completion. Defaults to
            ``_MAX_TOKENS_REPAIR``, which is only right for a document that fits
            it. Every repair prompt asks for the WHOLE corrected Storybook back,
            so the repair cap has to be at least the cap the fill itself ran
            under; a fill at 131,072 followed by a repair at 32,000 asks the
            model to re-emit a document larger than the ceiling it is given, the
            completion stops on ``length``, nothing parses, and the loop burns
            its whole budget re-requesting a document that can never arrive.
            That was invisible while the fill cap was also 32,000, because the
            books that exceed it could not be filled at all (`AL-431`).
    """

    provider: PiiGuardedProvider
    max_repairs: int
    stage_log: list[str]
    scale: Scale = "standard"
    context: GateContext = "skeleton"
    stage1: _Stage1Config | None = None
    max_tokens: int = _MAX_TOKENS_REPAIR
    normalize: Callable[[dict[str, object]], dict[str, object]] | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _canonical_json(doc: dict[str, object]) -> bytes:
    """Return a deterministic, compact JSON encoding for hashing.

    Keys are sorted so that two semantically identical dicts with different
    insertion order produce identical bytes.

    Args:
        doc: The document to encode.

    Returns:
        UTF-8 bytes of the canonically serialised JSON.
    """
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def _doc_hash(doc: dict[str, object] | None) -> str:
    """Return a SHA-256 hex digest of the canonical JSON for ``doc``.

    Returns the digest of an empty JSON object when ``doc`` is ``None``
    (parse-error sentinel).

    Args:
        doc: The document to hash, or ``None`` for a parse-error sentinel.

    Returns:
        Hex-encoded SHA-256 digest string.
    """
    payload = _canonical_json(doc) if doc is not None else b"{}"
    return hashlib.sha256(payload).hexdigest()


def _gate_signature(
    gate_result: GateResult, doc: dict[str, object] | None
) -> _Signature:
    """Build a no-progress signature combining finding fingerprint and doc hash.

    The signature is used to detect when a repair attempt produces no change:
    if the new signature equals the previous attempt's signature, the loop
    should stop.

    Args:
        gate_result: The gate result to fingerprint.
        doc: The document produced by this stage (may be ``None`` on parse
            failure).

    Returns:
        A ``(findings_tuple, doc_hash)`` pair.
    """
    # Only ERROR findings count toward no-progress: RL-13 (and any future
    # advisory) emits WARNING findings whose message embeds the computed score,
    # so prose-only edits between repairs would change the signature and defeat
    # the abort even when the blocking errors are identical. This mirrors
    # _get_failing_findings, which the repair loop uses to drive the prompt.
    #
    # node_id and choice_id are ``str | None``; two findings sharing a rule_id
    # but differing in nullability (e.g. an L1-2 start-node finding with
    # node_id=None alongside an L1-2 dangling-choice finding with a node_id)
    # would make ``sorted`` compare ``None`` against ``str`` and raise
    # TypeError. Sort by a None-safe key while preserving the original tuples.
    findings_tuple = tuple(
        sorted(
            (
                (f.rule_id, f.node_id, f.choice_id, f.message)
                for f in gate_result.report.findings
                if f.severity is Severity.ERROR
            ),
            key=lambda finding: tuple(
                "" if field is None else field for field in finding
            ),
        )
    )
    return findings_tuple, _doc_hash(doc)


def _synthetic_blocked_gate(message: str, context: GateContext) -> GateResult:
    """Synthesise a blocked gate result carrying one ``L1-1`` ERROR finding.

    Args:
        message: The finding's message, describing why no usable document
            exists.
        context: The posture the caller was validating under, recorded on the
            synthetic result so the verdict is not reported under a laxer
            posture than the one that was asked for.

    Returns:
        A blocked :class:`~cyo_adventure.validator.gate.GateResult`.
    """
    report = ValidationReport()
    report.add(
        ValidationFinding(
            rule_id="L1-1",
            severity=Severity.ERROR,
            story_id="<unknown>",
            message=message,
        )
    )
    return GateResult(
        report=report, blocked=True, safety_flagged=False, context=context
    )


def _empty_blocked_gate(context: GateContext = "skeleton") -> GateResult:
    """Synthesise a minimal blocked gate result for parse-error cases.

    Args:
        context: The posture the caller was validating under, recorded on
            the synthetic result so a parse failure is not reported as a
            skeleton-posture verdict when the caller asked for a stricter
            one.

    Returns:
        A :class:`~cyo_adventure.validator.gate.GateResult` with one
        synthetic ``L1-1`` ERROR finding indicating a parse failure.
    """
    return _synthetic_blocked_gate(
        "L1-1 schema: provider output was not valid JSON or not a dict", context
    )


async def _run_one_stage(
    stage_prompt: StagePrompt,
    *,
    provider: PiiGuardedProvider,
    max_tokens: int,
    scale: Scale = "standard",
    context: GateContext = "skeleton",
    normalize: Callable[[dict[str, object]], dict[str, object]] | None = None,
) -> tuple[dict[str, object] | None, GateResult]:
    """Run a single generation stage: call provider, parse JSON, run gate.

    PII enforcement is structural: ``provider`` must be a
    :class:`~cyo_adventure.generation.guarded.PiiGuardedProvider` (injected by
    :func:`generate_story`). The guard screens both ``system`` and ``user``
    blocks before the inner provider is called; this function does not need to
    repeat that check.

    Args:
        stage_prompt: The assembled :class:`~cyo_adventure.generation.prompts.StagePrompt`
            for this stage (a static system block and a volatile user block).
        provider: The PII-guarded generation provider to call.
        max_tokens: Maximum tokens for the provider completion.
        scale: Story-size profile forwarded to ``run_gate`` so L1-7 is enforced
            against the same budget the prompt promised.
        context: Gate posture forwarded to ``run_gate``. Stages that produce
            prose (Stage B, the skeleton fill, and any repair of either) pass
            ``"fill_result"`` so PL-27 rejects a node whose body is still a
            ``<<FILL ...>>`` directive. Stage A keeps the ``"skeleton"``
            default because its bodies are one-line beat descriptions by
            design, not prose (see ``prompts/structure.md``).
        normalize: Optional transform applied to the parsed document BEFORE
            the gate. The skeleton-fill path passes the freeze-split
            normalizer (2026-08-21 ruling, section 8.2) so frozen-field
            drift is restored from the skeleton rather than graded; every
            other stage leaves it None.

    Returns:
        A tuple of ``(doc_or_none, gate_result)``. ``doc_or_none`` is the
        parsed dict when JSON parsing succeeded; ``None`` on a parse error.
        ``gate_result`` is always present: either the real gate result for a
        successfully parsed dict, or a synthetic blocked result for parse
        failures.

    Raises:
        ValidationError: If either block contains forbidden PII (propagated
            from :class:`~cyo_adventure.generation.guarded.PiiGuardedProvider`
            before the inner provider is called).
    """
    completion = await provider.complete(
        system=stage_prompt.system,
        prompt=stage_prompt.user,
        max_tokens=max_tokens,
    )
    raw = completion.text

    # Parse: treat any non-dict or non-JSON as a synthetic blocked gate.
    # #CRITICAL: data integrity: `raw` is untrusted model output, and a deeply
    # nested payload does not fail as a JSONDecodeError. CPython 3.14 bounds
    # JSON nesting by C stack bytes consumed, so `json.loads` raises
    # RecursionError instead, and whether it fires at a given depth varies with
    # the executing thread's stack budget: the same 100k-deep array raises at an
    # 8MB stack and parses successfully at 64MB. `addopts` carries `-n=auto`, so
    # unit runs sit under xdist workers whose budget varies by runner, which is
    # why the two paths must converge. A patch-release correlation (3.14.6 vs
    # 3.14.7) was investigated and NOT established; do not reintroduce it as an
    # explanation, and do not pin or avoid a patch release on its strength.
    # #VERIFY: catch both so a hostile or degenerate completion routes to the
    # synthetic blocked gate like every other malformed output, rather than
    # escaping generate_story as a raw builtin exception. Covered by
    # test_generation_malformed_output.py::
    # test_generate_story_deeply_nested_output_returns_failed.
    try:
        parsed: object = json.loads(raw)  # pyright: ignore[reportAny]
    except (json.JSONDecodeError, RecursionError):
        return None, _empty_blocked_gate(context)

    if not isinstance(parsed, dict):
        return None, _empty_blocked_gate(context)

    doc = cast("dict[str, object]", parsed)
    # Normalization runs BEFORE the gate (2026-08-21 freeze-split ruling,
    # live-structural-round-2026-08-21.md section 8.2): frozen-field drift is
    # restored from the skeleton rather than graded, so a retheme of a frozen
    # documentation field is a non-event instead of a blocked book or a burned
    # repair cycle. Only the skeleton-fill path passes a normalizer.
    if normalize is not None:
        doc = normalize(doc)
    return doc, run_gate(doc, scale, context=context)


def _get_failing_findings(gate_result: GateResult) -> list[dict[str, object]]:
    """Extract ERROR-severity findings from a gate result as serializable dicts.

    Args:
        gate_result: The gate result to extract ERROR findings from.

    Returns:
        A list of finding dicts (the ``to_dict()`` format) for every
        ERROR-severity finding in the report.
    """
    return [
        dict(f.to_dict())
        for f in gate_result.report.findings
        if f.severity is Severity.ERROR
    ]


def _build_outcome(
    gate_result: GateResult,
    current_doc: dict[str, object] | None,
    attempts: int,
    stage_log: list[str],
) -> GenerationOutcome:
    """Map a final gate result to a :class:`GenerationOutcome`.

    Rules:
    - Gate clean, not safety-flagged: ``"passed"``.
    - Gate clean, safety-flagged: ``"needs_review"``.
    - Gate blocked, doc present: ``"needs_review"``.
    - Gate blocked, no doc: ``"failed"``.

    A ``"passed"`` status is NEVER returned when the gate is blocked.

    Args:
        gate_result: The final gate result after all stages and repairs.
        current_doc: The last successfully parsed document, or ``None``.
        attempts: Number of repair attempts performed.
        stage_log: Accumulated stage-execution log entries.

    Returns:
        The appropriate :class:`GenerationOutcome`.
    """
    final_report = gate_result.report.to_dict()

    if not gate_result.blocked:
        status: Literal["passed", "needs_review", "failed"] = (
            "needs_review" if gate_result.safety_flagged else "passed"
        )
        return GenerationOutcome(
            status=status,
            storybook=current_doc,
            report=final_report,
            attempts=attempts,
            stage_log=stage_log,
        )

    # Blocked: needs_review when a doc was produced, failed when none was.
    blocked_status: Literal["needs_review", "failed"] = (
        "needs_review" if current_doc is not None else "failed"
    )
    return GenerationOutcome(
        status=blocked_status,
        storybook=current_doc,
        report=final_report,
        attempts=attempts,
        stage_log=stage_log,
    )


def _resolve_stage1_posture(
    stage1_gate: Stage1Posture, settings: Settings | None
) -> bool:
    """Decide whether the Stage 1 fidelity gate runs, and refuse a false promise.

    Args:
        stage1_gate: The posture the caller asked for.
        settings: The settings the gate needs, or ``None``.

    Returns:
        Whether the gate is armed for this call.

    Raises:
        ConfigurationError: If ``"required"`` was asked for without the
            ``settings`` the gate cannot run without. Raising is the point:
            the failure this closes is a caller believing it is gated and not
            being, so the one outcome that must not exist is a quiet downgrade
            to ungated.
    """
    if stage1_gate == "skipped":
        return False
    if stage1_gate == "required" and settings is None:
        msg = (
            "stage1_gate='required' needs settings; the Stage 1 fidelity gate "
            "cannot run without them, and silently skipping it would report an "
            "ungated fill as a gated one"
        )
        raise ConfigurationError(msg)
    return settings is not None


def _with_stage1_posture(
    outcome: GenerationOutcome, *, armed: bool
) -> GenerationOutcome:
    """Record which fidelity posture produced this outcome.

    Stamped unconditionally, including on a failure, because the question a
    reader asks of a ``status`` field is "what did this pass?" and the answer
    must not depend on remembering which caller supplied ``settings``. Three
    vendor-comparison books that were 100 percent unfilled were recorded
    ``passed`` and read alongside gated results as though they meant the same
    thing (`AL-324`); the field is what makes them separable after the fact.

    Args:
        outcome: The outcome to annotate.
        armed: Whether the Stage 1 fidelity gate actually ran.

    Returns:
        The outcome with a ``"stage1_gate"`` report key.
    """
    return GenerationOutcome(
        status=outcome.status,
        storybook=outcome.storybook,
        report={**outcome.report, "stage1_gate": "armed" if armed else "skipped"},
        attempts=outcome.attempts,
        stage_log=outcome.stage_log,
        sentinel_manifest=outcome.sentinel_manifest,
        personalization_eligible=outcome.personalization_eligible,
    )


def _fail_on_unfilled_skeleton(
    outcome: GenerationOutcome,
    skeleton: dict[str, object],
    stage_log: list[str],
) -> GenerationOutcome:
    """Refuse to return the caller's own unfilled skeleton as a storybook.

    A skeleton's node bodies are ``<<FILL ...>>`` directives, so a fill result
    equal to its input is not a story by any reading: no prose was produced.
    That state is reachable, and `AL-327` is what it cost. A fill whose output
    never parses seeds the repair loop with the skeleton as context, which is
    useful (a repair genuinely does recover from a parse failure and must keep
    being able to); the harm is that a repair which merely echoes its input, or
    a loop that exhausts its budget without ever parsing anything, leaves the
    skeleton sitting in ``last_valid_doc`` and hands it back as the deliverable.

    The verdict here is deliberately taken **regardless of the gate**. `PL-27`
    now blocks a retained directive, so this document currently arrives as
    ``needs_review`` rather than the ``passed`` four run-6 books recorded, but
    that is one checker standing between a total generation failure and a human
    review queue. A total failure should not depend on a rule that could be
    scoped, relaxed, or skipped later.

    Args:
        outcome: The outcome built from the final gate result.
        skeleton: The unfilled skeleton this call was asked to fill.
        stage_log: The run's stage log, appended to when this fires.

    Returns:
        The outcome unchanged, or a ``"failed"`` outcome carrying no storybook.
    """
    if outcome.storybook is None or outcome.storybook != skeleton:
        return outcome
    _logger.warning(
        "fill_returned_the_unfilled_skeleton",
        attempts=outcome.attempts,
        gate_status=outcome.status,
        reason="no stage produced prose; the input skeleton is not a result",
    )
    stage_log.append("stage_fill:unfilled_skeleton_returned")
    return GenerationOutcome(
        status="failed",
        storybook=None,
        report={**outcome.report, "unfilled_skeleton_returned": True},
        attempts=outcome.attempts,
        stage_log=stage_log,
    )


async def _repair_reading_level(
    current_doc: dict[str, object] | None,
    gate_result: GateResult,
    ctx: ReadingLevelContext,
) -> tuple[dict[str, object] | None, GateResult, ReadingLevelResult | None]:
    """Run Stage D (reading level) when there is a clean document to run it on.

    Skipped on a blocked or absent document. A document that never cleared the
    structural gate is already bound for human review, so spending provider
    calls to make its prose easier to read would be paying to polish something
    nobody will publish in this state.

    Args:
        current_doc: The document after the structural/Stage 1 loop, or ``None``.
        gate_result: That document's gate result.
        ctx: The reading-level stage context (provider, budget, log, scale).

    Returns:
        A ``(doc, gate_result, result)`` tuple. ``result`` is ``None`` when the
        stage did not run, in which case the first two elements are the inputs
        unchanged.

    Raises:
        ValidationError: If an assembled prompt contains forbidden PII.
    """
    if current_doc is None or gate_result.blocked or ctx.max_passes <= 0:
        return current_doc, gate_result, None
    result = await run_reading_level_loop(current_doc, gate_result, ctx)
    return result.doc, result.gate, result


def _with_reading_level(
    outcome: GenerationOutcome, result: ReadingLevelResult | None
) -> GenerationOutcome:
    """Attach the reading-level measurement to an outcome's report.

    The measurement is recorded even when nothing was revised, because "this
    book was measured and was already in band" and "nobody looked" are
    different facts and the report should not conflate them. ``AL-209`` is what
    happens when it does: three books shipped at whole-book FK 8.14 to 8.41
    with a not-blocked verdict and no number anywhere to contradict it.

    Args:
        outcome: The outcome built from the final gate result.
        result: The Stage D result, or ``None`` when the stage did not run.

    Returns:
        The outcome, with a ``"reading_level"`` report key when Stage D ran.
    """
    if result is None:
        return outcome
    # Constructed directly rather than via dataclasses.replace, for the same
    # reason fill_skeleton's Stage 1 downgrade does (S5886: replace()'s TypeVar
    # return can resolve to DataclassInstance rather than GenerationOutcome).
    return GenerationOutcome(
        status=outcome.status,
        storybook=outcome.storybook,
        report={**outcome.report, "reading_level": result.to_report()},
        attempts=outcome.attempts,
        stage_log=outcome.stage_log,
    )


async def _next_repair_prompt(
    gate_result: GateResult,
    current_doc: dict[str, object] | None,
    ctx: _RepairContext,
    *,
    attempts: int,
    stage1_violations: list[str],
) -> StagePrompt | None:
    """Decide the next repair prompt (structural or fidelity), or ``None`` to stop.

    Encapsulates the loop's continue-condition. A structural block always takes
    precedence: Stage 1 is only consulted on a structurally-clean, non-safety-
    flagged document (the exact set the old worker gated on ``status ==
    "passed"``), so a paid fidelity review is never spent on a fill that still
    needs structural repair.

    ``stage1_violations`` is mutated in place: it is cleared when Stage 1 passes
    and replaced with the fresh violation list when Stage 1 fails, so the caller
    always holds the Stage 1 verdict for the document it last evaluated.

    Args:
        gate_result: The current document's gate result.
        current_doc: The current document (``None`` only on a parse error, which
            is always blocked).
        ctx: Grouped repair context (provider, budget, stage_log, Stage 1).
        attempts: Repairs performed so far (used to stop before a paid retry
            once the budget is spent, while still recording the final verdict).
        stage1_violations: The mutable Stage 1 verdict list (see above).

    Returns:
        The next :class:`~cyo_adventure.generation.prompts.StagePrompt` to run,
        or ``None`` when the loop should stop (clean, budget exhausted, or no
        Stage 1 configured for a structurally-clean document).
    """
    if gate_result.blocked:
        if attempts >= ctx.max_repairs:
            return None
        failing_findings = _get_failing_findings(gate_result)
        # #EDGE: data-integrity: generate_story seeds this loop with the last
        # valid document (Stage A skeleton if Stage B parse-failed), so "{}" is
        # only reached when no stage ever produced a parseable document.
        # #VERIFY: covered by test_orchestrator stage-skeleton preservation cases.
        current_json = json.dumps(current_doc) if current_doc is not None else "{}"
        return build_repair_prompt(current_json, failing_findings)

    # Structurally clean. Stage 1 runs only for the authoring fill path, and
    # only on a document that would otherwise pass (not safety-flagged), so it
    # mirrors the old worker's ``status == "passed"`` gate exactly.
    if ctx.stage1 is None or current_doc is None or gate_result.safety_flagged:
        stage1_violations.clear()
        return None

    # #CRITICAL: data-integrity: the Stage 1 gate is the fidelity contract for
    # an authored fill; a fill that silently drifts from its skeleton's beats or
    # word-count directive must be caught here, not surfaced as a clean pass.
    # #VERIFY: test_fill_skeleton_stage1_fail_once_then_pass_returns_passed and
    # test_fill_skeleton_stage1_exhaustion_downgrades_with_key.
    # #ASSUME: external-resources: run_stage1_gate performs at most one paid
    # review-model call per structurally-clean document, and is invoked at most
    # once per loop iteration, so the Stage 1 review spend is bounded by
    # max_repairs + 1 and shares the single fill/repair budget below (it is no
    # longer the up-to-9 provider calls the removed worker-level outer loop
    # cost).
    # #VERIFY: test_fill_skeleton_stage1_exhaustion_downgrades_with_key asserts
    # exactly 1 fill + max_repairs repair provider calls for a persistent miss.
    violations = await run_stage1_gate(
        ctx.stage1.original,
        current_doc,
        review_stage1_model=ctx.stage1.review_stage1_model,
        prep_model=ctx.stage1.prep_model,
        settings=ctx.stage1.settings,
        pii=ctx.stage1.pii,
        ledger=ctx.stage1.ledger,
    )
    stage1_violations[:] = violations
    if not violations or attempts >= ctx.max_repairs:
        # Clean, or the shared budget is spent: stop. When the budget is spent
        # the fresh violations are retained so the caller can downgrade.
        return None
    return build_fidelity_repair_prompt(json.dumps(current_doc), violations)


async def _run_repair_loop(
    gate_result: GateResult,
    current_doc: dict[str, object] | None,
    ctx: _RepairContext,
) -> tuple[dict[str, object] | None, GateResult, int, list[str]]:
    """Run the bounded repair loop for structural AND Stage 1 fidelity blocks.

    Attempts up to ``ctx.max_repairs`` repairs on the current document, sharing
    ONE budget across two kinds of block:

    * a structural gate block (the pre-existing Stage C behavior), and
    * a Stage 1 fidelity miss on a structurally-clean fill (the authoring path
      only; ``ctx.stage1`` present). A fidelity miss re-enters this same loop
      with a fidelity-aware repair prompt carrying the violation text, rather
      than a blind regeneration, and counts against the same ``max_repairs``
      budget as structural repairs.

    Stops early when no-progress is detected: if a repair produces the same gate
    findings AND the same document hash as the previous state, further attempts
    cannot help.

    No-progress seeding: ``prev_signature`` is initialised from the document
    entering the loop (Stage B output, or Stage A output if Stage B was
    skipped). This means that if repair 1 returns the same document as Stage B,
    the loop stops after exactly 1 attempt.

    For :func:`generate_story` and every other caller with ``ctx.stage1 is
    None``, the loop is byte-identical to the pre-fold structural-only loop: it
    runs only while the gate is blocked and stops the instant a document is
    clean.

    Args:
        gate_result: The gate result from the fill/Stage A/Stage B document.
        current_doc: That document (may be ``None`` on parse error).
        ctx: Grouped repair context (provider, budget, stage_log, Stage 1).

    Returns:
        A ``(current_doc, gate_result, attempts, stage1_violations)`` tuple
        reflecting the state after the loop exits. ``stage1_violations`` is the
        Stage 1 verdict for the final document: empty when Stage 1 passed or was
        never run, non-empty when the final structurally-clean document still
        fails Stage 1 after the budget is spent.
    """
    # Seed with the state entering the loop so the first repair can be
    # detected as no-progress immediately if it returns an identical output.
    prev_signature: _Signature = _gate_signature(gate_result, current_doc)
    attempts = 0
    stage1_violations: list[str] = []

    while True:
        repair_prompt = await _next_repair_prompt(
            gate_result,
            current_doc,
            ctx,
            attempts=attempts,
            stage1_violations=stage1_violations,
        )
        if repair_prompt is None:
            break

        new_doc, new_gate = await _run_one_stage(
            repair_prompt,
            provider=ctx.provider,
            max_tokens=ctx.max_tokens,
            scale=ctx.scale,
            context=ctx.context,
            normalize=ctx.normalize,
        )
        attempts += 1
        ctx.stage_log.append(f"repair:{attempts}")

        current_signature = _gate_signature(new_gate, new_doc)
        if current_signature == prev_signature:
            # No-progress: same findings and same output; further attempts
            # cannot help.
            ctx.stage_log.append("repair:no_progress_abort")
            current_doc = new_doc if new_doc is not None else current_doc
            gate_result = new_gate
            break

        prev_signature = current_signature
        current_doc = new_doc if new_doc is not None else current_doc
        gate_result = new_gate

    return current_doc, gate_result, attempts, stage1_violations


def _append_stage_log(
    stage_log: list[str],
    stage: str,
    doc: dict[str, object] | None,
    gate_result: GateResult,
) -> None:
    """Append the appropriate outcome label for a stage to ``stage_log``.

    Args:
        stage_log: The log list to append to.
        stage: Stage name prefix (e.g. ``"stage_a"``).
        doc: The parsed document for the stage (``None`` on parse error).
        gate_result: The gate result for the stage.
    """
    if doc is None:
        stage_log.append(f"{stage}:parse_error")
    elif gate_result.blocked:
        stage_log.append(f"{stage}:blocked")
    else:
        stage_log.append(f"{stage}:gate_ok")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def generate_story(
    brief: ConceptBrief,
    provider: GenerationProvider,
    pii: PiiContext,
    *,
    max_repairs: int = 3,
    scale: Scale = "standard",
    reading_level_passes: int = _DEFAULT_READING_LEVEL_PASSES,
) -> GenerationOutcome:
    """Run the staged generation pipeline and return a validated outcome.

    Stages:

    1. **Stage A (Structure)**: build structure prompt, PII-guard, call
       provider, parse JSON, run gate. If blocked, skip Stage B and enter
       the repair loop directly.
    2. **Stage B (Prose)**: build prose prompt, PII-guard, call provider,
       parse JSON, run gate.
    3. **Stage C (Repair)**: while the gate is blocked and ``attempts <
       max_repairs``, build a repair prompt for the failing findings,
       PII-guard, call provider, parse JSON, run gate, check no-progress.
    4. **Stage D (Reading level)**: on an unblocked document, measure every
       node's Flesch-Kincaid grade and re-prompt the out-of-band ones toward
       the band. Never blocks: a revision is taken only when it strictly
       improves, and the whole pass is discarded if it regresses the gate.

    PII enforcement: ``provider`` is wrapped in a
    :class:`~cyo_adventure.generation.guarded.PiiGuardedProvider` at entry.
    Both ``system`` and ``prompt`` blocks are screened on every ``complete()``
    call before the inner provider is reached. A PII violation raises
    :class:`~cyo_adventure.core.exceptions.ValidationError` immediately and
    no provider call is made.

    Malformed output: if the provider returns invalid JSON or a non-dict, the
    stage is treated as a blocking gate failure (a synthetic blocked gate
    result is used). The orchestrator never raises on a parse error; all
    malformed outputs route to the repair loop.

    Args:
        brief: The validated concept brief for this generation job.
        provider: The :class:`~cyo_adventure.generation.provider.GenerationProvider`
            to call for completions.
        pii: The :class:`~cyo_adventure.generation.pii.PiiContext` carrying
            real-child names that must not appear in any prompt.
        max_repairs: Maximum number of repair attempts before giving up.
            Defaults to 3.
        scale: Story-size profile (``"standard"`` or ``"compact"``) applied to
            both the Stage A prompt budget and the L1-7 gate, so they stay in
            sync. Defaults to ``"standard"``.
        reading_level_passes: Maximum Stage D passes. ``0`` disables the stage
            entirely. Defaults to two (see ``_DEFAULT_READING_LEVEL_PASSES``);
            the stage costs no provider calls when every node is already in
            band, or when the book declares no reading-level target.

    Returns:
        A :class:`GenerationOutcome` describing the final status, the last
        produced document (if any), the final gate report, the number of
        repair attempts, and a human-readable stage log.

    Raises:
        ValidationError: If any assembled prompt contains forbidden PII. The
            provider is never called when this occurs.
    """
    stage_log: list[str] = []

    # Wrap the provider so PII enforcement is structural for the entire run.
    # Every complete() call in Stages A, B, and C screens both system and
    # prompt blocks before reaching the real provider.
    guarded_provider = PiiGuardedProvider(provider, forbidden=pii)

    # ------------------------------------------------------------------
    # Stage A: Structure skeleton
    # ------------------------------------------------------------------
    stage_a_prompt = build_structure_prompt(brief, scale)
    current_doc, gate_result = await _run_one_stage(
        stage_a_prompt,
        provider=guarded_provider,
        max_tokens=_MAX_TOKENS_STRUCTURE,
        scale=scale,
    )
    _append_stage_log(stage_log, "stage_a", current_doc, gate_result)

    # Track the most recent successfully parsed document so a later parse
    # failure does not discard a usable skeleton. Stage A's validated structure
    # is a better repair seed (and a better surfaced result) than an empty doc.
    last_valid_doc = current_doc

    # If Stage A passed, proceed to Stage B; otherwise skip straight to repair.
    if not gate_result.blocked:
        # ------------------------------------------------------------------
        # Stage B: Full prose
        # ------------------------------------------------------------------
        skeleton_json = json.dumps(current_doc)
        stage_b_prompt = build_prose_prompt(skeleton_json, brief)
        current_doc, gate_result = await _run_one_stage(
            stage_b_prompt,
            provider=guarded_provider,
            # #CRITICAL: external resources: this is the only stage whose ask
            # can exceed a model's output ceiling, and neither provider clamps:
            # `providers/openrouter.py` and `providers/anthropic.py` both put
            # `max_tokens` straight into the request payload, so an over-ask is
            # rejected by the API rather than quietly lowered. Asking 131,072 of
            # the shipped default (`anthropic/claude-haiku-4.5`, ceiling 64,000)
            # therefore fails EVERY Stage B call, not merely oversized ones, and
            # `worker.py` reaches this function on the provider-override path.
            # `generate_story` takes no Settings, but it builds `guarded_provider`
            # itself, so the provider's own declared model is available here and
            # is the authoritative answer anyway (`AL-436`).
            # #VERIFY: test_orchestrator.py::
            # test_generate_story_stage_b_asks_no_more_than_the_model_can_emit.
            max_tokens=resolve_output_cap(guarded_provider.model),
            scale=scale,
            context="fill_result",
        )
        _append_stage_log(stage_log, "stage_b", current_doc, gate_result)
        # Prefer Stage B's fuller document, but keep Stage A's skeleton if
        # Stage B failed to parse.
        if current_doc is not None:
            last_valid_doc = current_doc

    # ------------------------------------------------------------------
    # Stage C: Bounded repair loop (runs only when still blocked)
    # ------------------------------------------------------------------
    attempts = 0
    if gate_result.blocked:
        repair_ctx = _RepairContext(
            provider=guarded_provider,
            max_repairs=max_repairs,
            stage_log=stage_log,
            scale=scale,
            context="fill_result",
        )
        # Seed the loop with the last valid document so a Stage B parse failure
        # repairs from Stage A's skeleton rather than an empty object, and the
        # surfaced outcome is needs_review (skeleton present) rather than failed.
        repair_seed = current_doc if current_doc is not None else last_valid_doc
        # generate_story does no authoring Stage 1 (repair_ctx.stage1 is None),
        # so the returned stage1_violations is always empty and discarded here;
        # the loop is byte-identical to the pre-fold structural-only behavior.
        current_doc, gate_result, attempts, _stage1 = await _run_repair_loop(
            gate_result,
            repair_seed,
            repair_ctx,
        )

    # ------------------------------------------------------------------
    # Stage D: Reading-level repair (runs only when NOT blocked)
    # ------------------------------------------------------------------
    current_doc, gate_result, reading_level = await _repair_reading_level(
        current_doc,
        gate_result,
        ReadingLevelContext(
            provider=guarded_provider,
            max_passes=reading_level_passes,
            stage_log=stage_log,
            scale=scale,
        ),
    )

    return _with_reading_level(
        _build_outcome(gate_result, current_doc, attempts, stage_log),
        reading_level,
    )


def _unfillable_outcome(
    exc: ValidationError, stage_log: list[str], *, armed: bool
) -> GenerationOutcome:
    """Return the failed outcome for a skeleton no partition can fill.

    Args:
        exc: The partitioning error naming the node that does not fit.
        stage_log: The run's stage log, appended to.
        armed: Whether the Stage 1 fidelity gate was armed, stamped on the
            outcome like every other terminal state.

    Returns:
        A ``"failed"`` :class:`GenerationOutcome` with no storybook.
    """
    _logger.warning("fill_skeleton_unfillable", reason=str(exc))
    stage_log.append("stage_fill:unfillable_under_cap")
    return _with_stage1_posture(
        _build_outcome(
            _synthetic_blocked_gate(f"L1-1 schema: {exc}", "fill_result"),
            None,
            0,
            stage_log,
        ),
        armed=armed,
    )


# One re-ask for the whole chunked fill. A batch reply that will not parse is
# usually a transient formatting slip, and re-asking that one batch is the only
# repair a chunked fill can afford: the whole-document repair loop is held at
# zero here because its prompt asks back the document that did not fit
# (`AL-329`). Shared rather than per-batch so a systematically broken run costs
# one extra call, not one per batch.
_MAX_BATCH_RETRIES: Final[int] = 1


@dataclass(frozen=True, slots=True)
class _ChunkedFillContext:
    """Everything a chunked fill needs beyond the skeleton and the brief.

    Attributes:
        provider: The PII-guarded provider every batch call goes through.
        cap: The resolved output cap one batch call runs under. Batches are
            partitioned to fit it, so it is both the partitioning budget and
            the per-call ``max_tokens``.
        differentiation_directive: The trusted A6/A7 block, passed to every
            batch so anti-repetition steering is not confined to the first one.
        stage_log: The run's stage log, appended to per batch.
        slot_bindings: The WS-2 bound values when this is a bound fill, else
            None. Selects the bound batch prompt variant, and is passed to EVERY
            batch: the bound-values block is the only place a batch learns the
            theme's names, so omitting it from later batches would leave them
            re-inventing the world the first batch bound.
        max_batch_retries: Re-asks available across the whole fill, shared by
            every batch rather than allotted per batch. A per-batch allowance
            would let a run that never parses double the call count of the
            book, which is the cost profile chunking exists to avoid.
    """

    provider: PiiGuardedProvider
    cap: int
    differentiation_directive: str
    stage_log: list[str]
    slot_bindings: Mapping[str, str] | None = None
    # Total re-asks available across the WHOLE chunked fill, not per batch.
    max_batch_retries: int = _MAX_BATCH_RETRIES
    # The resolved backend model id, for the context-window bound
    # (`AL-519`/`UW-C324`); None when unknown, which constrains nothing.
    model: str | None = None


async def _merge_one_batch_attempt(
    ctx: _ChunkedFillContext,
    prompt: StagePrompt,
    *,
    ask: int,
    document: dict[str, object],
    node_ids: Sequence[str],
) -> tuple[dict[str, object] | None, str | None]:
    """Run one batch completion and fold the reply into the document.

    Split out of the batch loop so the re-ask is a two-line retry there rather
    than another level of nesting inside an already-dense function.

    Args:
        ctx: The grouped chunked-fill context.
        prompt: This batch's prompt.
        ask: The resolved ``max_tokens`` for this call.
        document: The document to merge into.
        node_ids: The ids this batch was asked to write.

    Returns:
        ``(merged_document, None)`` on success, or ``(None, reason)`` when the
        reply carried no usable prose.
    """
    # #ASSUME: external-resources: one network completion per call. A provider
    # exception propagates for rollback and RQ retry exactly as elsewhere on this
    # path; only a malformed REPLY becomes a rejection reason, and only a
    # rejection is worth re-asking, because a provider fault has already
    # exhausted the adapter's own transient retries.
    # #VERIFY: no ProviderError is caught here; tests/unit/test_chunked_fill.py::
    # test_an_unusable_batch_reply_is_re_asked_and_the_book_survives covers the
    # reply path.
    completion = await ctx.provider.complete(
        system=prompt.system, prompt=prompt.user, max_tokens=ask
    )
    try:
        payload: object = json.loads(completion.text)  # pyright: ignore[reportAny]
    except (json.JSONDecodeError, RecursionError):
        # Caught for the same reason _run_one_stage catches both: a deeply
        # nested reply raises RecursionError rather than JSONDecodeError
        # under CPython 3.14.
        payload = None
    try:
        return merge_fill_batch(document, node_ids, payload), None
    except ValidationError as exc:
        return None, str(exc)


async def _fill_in_batches(
    skeleton: dict[str, object],
    theme_brief: dict[str, object],
    ctx: _ChunkedFillContext,
) -> tuple[dict[str, object] | None, GateResult]:
    """Fill a skeleton a batch at a time and gate the reassembled document.

    Used only when the whole skeleton provably does not fit the backend's
    output cap. Each batch asks for prose covering its own nodes and nothing
    else, and every reply is folded in by
    :func:`~cyo_adventure.generation.chunking.merge_fill_batch`, which reads
    only body and choice-label text.

    # #CRITICAL: data-integrity: a batch that returns nothing usable fails the
    # whole fill here rather than merging what it can. A partially-merged
    # document is the dangerous artifact in this pipeline: every gate checker
    # SKIPS a ``<<FILL ...>>`` body rather than failing on it (`AL-325`), so a
    # document half of which is still directives can clear topology, safety,
    # choice grammar, and reading level by abstention. `PL-27` is the one rule
    # that objects, and `AL-327` is what it cost the last time a total fill
    # failure was allowed to depend on the gate's opinion of a document the
    # model never wrote.
    # #VERIFY: test_chunked_fill.py::
    # test_a_batch_that_returns_nothing_fails_the_whole_fill asserts the
    # outcome is ``failed`` with no storybook, and that no later batch is
    # attempted.

    # #ASSUME: external-resources: each batch is one network completion, so a
    # chunked fill costs as many calls as batches, each re-sending the skeleton
    # and the prose written so far. Input tokens are the price of the output
    # ceiling this path exists to work around; a provider error propagates to
    # the caller for rollback and RQ retry exactly as the one-shot call does.
    # #VERIFY: no provider exception is caught here; only a malformed reply is
    # turned into a failure.

    Args:
        skeleton: The unfilled skeleton.
        theme_brief: The concept brief driving the reskin.
        ctx: The grouped chunked-fill context.

    Returns:
        ``(document, gate_result)`` with the merged document and its
        ``"fill_result"`` gate verdict, or ``(None, blocked_gate)`` when any
        batch failed. The shape matches :func:`_run_one_stage` so the caller
        treats both fill paths identically.

    Raises:
        ValidationError: Propagated from
            :func:`~cyo_adventure.generation.chunking.plan_fill_batches` when a
            single node cannot fit the cap even alone. Handled by
            :func:`fill_skeleton`; no provider call has been made at that point.
    """
    batches = plan_fill_batches(skeleton, max_tokens=ctx.cap)
    skeleton_json = json.dumps(skeleton)
    brief_json = json.dumps(theme_brief)
    document = skeleton
    retries_left = ctx.max_batch_retries
    for index, node_ids in enumerate(batches, start=1):
        payload_for_batch = FillBatchPayload(
            nodes_to_fill_json=json.dumps(batch_request(document, node_ids)),
            prose_so_far_json=json.dumps(written_prose(document)),
            slot_bindings_json=(
                None
                if ctx.slot_bindings is None
                else json.dumps(dict(ctx.slot_bindings))
            ),
        )
        prompt = (
            build_fill_subset_bound_prompt(
                skeleton_json,
                payload_for_batch,
                brief_json,
                ctx.differentiation_directive,
            )
            if ctx.slot_bindings is not None
            else build_fill_subset_prompt(
                skeleton_json,
                payload_for_batch,
                brief_json,
                ctx.differentiation_directive,
            )
        )
        # #CRITICAL: external resources: the batch prompt carries the whole
        # document, so input grows with skeleton size while the output cap
        # stays fixed, and a provider bounds input PLUS output by its context
        # window. Nothing accounted for that: a batch call requested 58,983
        # output tokens on a 104,858-token prompt against a 163,840-token
        # window, one token over, HTTP 400 after the harness had already paid
        # for the prompt (`AL-519`/`UW-C324`). Bound the ask by the KNOWN
        # window (unknown windows constrain nothing), and refuse outright
        # when the remaining room cannot hold the batch under the SAME
        # feasibility margin `plan_fill_batches` planned it under: the batch
        # only exists because `is_fill_feasible` said its expected output fits
        # `ctx.cap` with 20 percent to spare, and reasoning tokens bill against
        # the window too (`AL-328`/`AL-329`). Testing the raw `needed` against
        # `room` here would hand the model a batch with under one percent of
        # headroom (window 163,840 minus a 111,000-token prompt leaves 52,840
        # against a `needed` of 52,428) and buy the truncation-on-`length` the
        # margin exists to prevent. Asking the canonical predicate keeps the
        # window check and the planner on one rule.
        # #VERIFY: tests/unit/test_chunked_fill.py::
        # test_a_window_too_small_for_a_batch_refuses_without_spending,
        # ::test_room_exactly_at_the_feasibility_requirement_proceeds, and
        # ::test_room_one_token_under_the_feasibility_requirement_refuses.
        ask = ctx.cap
        window = resolve_context_window(ctx.model)
        if window is not None:
            room = window - estimate_input_tokens(prompt.system, prompt.user)
            batch_id_set = set(node_ids)
            batch_nodes = [
                node
                for node in cast("list[object]", document.get("nodes") or [])
                if isinstance(node, dict)
                and cast("dict[str, object]", node).get("id") in batch_id_set
            ]
            needed = expected_output_tokens({"nodes": batch_nodes})
            # `is_fill_feasible` is the single authority on "does this batch
            # fit", shared with the one-shot path, so the 0.8 reasoning-headroom
            # margin cannot drift between the two (PR #737 review, I3).
            # `needed_with_headroom` re-expresses that same threshold as a token
            # count for the operator-facing message below. It decides nothing.
            needed_with_headroom = math.ceil(needed / _FEASIBILITY_MARGIN)
            if not is_fill_feasible({"nodes": batch_nodes}, max_tokens=room):
                _logger.warning(
                    "fill_batch_context_overflow",
                    batch=index,
                    batches=len(batches),
                    window=window,
                    room=room,
                    needed=needed,
                )
                ctx.stage_log.append(
                    f"stage_fill:batch_{index}_of_{len(batches)}_context_overflow"
                )
                failure = (
                    f"L1-1 schema: chunked fill batch {index} of {len(batches)} "
                    f"cannot fit the model's {window}-token context window: the "
                    f"prompt leaves {room} tokens of room and the batch expects "
                    f"{needed} plus reasoning headroom ({needed_with_headroom} "
                    "total); no completion was requested"
                )
                return None, _synthetic_blocked_gate(failure, "fill_result")
            ask = min(ask, room)
        merged, rejection = await _merge_one_batch_attempt(
            ctx, prompt, ask=ask, document=document, node_ids=node_ids
        )
        # A re-ask is the only repair shape this path can afford. Every
        # whole-document repair prompt asks back the thing that did not fit,
        # which is why that budget is zero here (`AL-329`); one batch fits the
        # cap by construction, because the partitioner sized it to. Without
        # this, one unusable reply threw away every batch already paid for.
        # #VERIFY: tests/unit/test_chunked_fill.py::
        # test_an_unusable_batch_reply_is_re_asked_and_the_book_survives and
        # ::test_the_batch_re_ask_budget_is_shared_across_the_whole_fill.
        while merged is None and retries_left > 0:
            retries_left -= 1
            _logger.warning(
                "fill_batch_retry",
                batch=index,
                batches=len(batches),
                remaining=retries_left,
                reason=rejection,
            )
            ctx.stage_log.append(f"stage_fill:batch_{index}_of_{len(batches)}_retry")
            merged, rejection = await _merge_one_batch_attempt(
                ctx, prompt, ask=ask, document=document, node_ids=node_ids
            )
        if merged is None:
            _logger.warning(
                "fill_batch_rejected",
                batch=index,
                batches=len(batches),
                nodes=len(node_ids),
                reason=rejection,
            )
            ctx.stage_log.append(f"stage_fill:batch_{index}_of_{len(batches)}_rejected")
            where = f"batch {index} of {len(batches)}"
            failure = (
                f"L1-1 schema: chunked fill {where} produced no usable prose: "
                f"{rejection}"
            )
            return None, _synthetic_blocked_gate(failure, "fill_result")
        document = merged
        ctx.stage_log.append(f"stage_fill:batch_{index}_of_{len(batches)}_merged")
    return document, run_gate(document, "standard", context="fill_result")


def _with_fill_rate(
    outcome: GenerationOutcome,
    skeleton: dict[str, object],
    min_fill_rate: float,
    stage_log: list[str],
) -> GenerationOutcome:
    """Stamp the story-level fill rate and force review under the floor.

    Ruled 2026-08-21 (section 9.3 of ``live-structural-round-2026-08-21.md``,
    `UW-C307`): a book delivering under the floor FORCES ``needs_review``,
    never a hard block, so a thin book cannot ship without a human while a
    0.63-class good fill is never machine-rejected (the tightest known-good
    pair sits 0.035 above the default floor). The rate is recorded on every
    outcome that carries a book, floor breach or not, so review surfaces can
    show it; floors are a per-vendor, per-band calibration question and the
    default stands until that calibration exists (`AL-516`/`AL-528`).

    A downgrade ALSO stamps ``"fill_rate_downgrade": True``, and that key, not
    the rate, is what
    :func:`~cyo_adventure.generation.worker._should_persist_storybook` reads.
    The rate is on every outcome carrying a book, so it identifies nothing; a
    key present only on the downgrade says "the base outcome was clean before
    this function touched it", which is exactly the condition under which the
    thin book must still be persisted for a human to read. Never stamp this
    key on a non-downgrade path, and never widen it to a second cause: the
    persist gate treats each such key as a proof of prior cleanliness.

    Args:
        outcome: The outcome so far.
        skeleton: The pristine skeleton carrying the ``words=`` commissions.
        min_fill_rate: The floor; a passing book below it is downgraded.
        stage_log: The run's stage log, appended to on a downgrade.

    Returns:
        GenerationOutcome: The outcome with ``fill_rate`` stamped, downgraded
        to ``needs_review`` when a passing book falls under the floor;
        unchanged when no book or no commission exists.
    """
    if outcome.storybook is None:
        return outcome
    fill_rate = story_fill_rate(skeleton, outcome.storybook)
    if fill_rate is None:
        return outcome
    downgrade = outcome.status == "passed" and fill_rate < min_fill_rate
    report: dict[str, object] = {
        **outcome.report,
        "fill_rate": round(fill_rate, 4),
        "fill_rate_floor": min_fill_rate,
    }
    if downgrade:
        stage_log.append(f"fill_rate:{fill_rate:.3f}_below_{min_fill_rate}")
        _logger.warning(
            "fill_rate_below_floor",
            fill_rate=round(fill_rate, 3),
            floor=min_fill_rate,
        )
        # #CRITICAL: data-integrity: `fill_rate` alone cannot tell a persister
        # that THIS function caused the downgrade, because the rate is stamped
        # on every outcome carrying a book, breach or not. Without a key set
        # only on the downgrade, `worker.py::_should_persist_storybook` sees a
        # `needs_review` it cannot distinguish from a safety-flagged one and
        # persists NOTHING: no Storybook, no StorybookVersion, no moderation,
        # and a job row pointing at a book nobody can reach. Ruling 9.3 says
        # this gate is never a hard block, so silence here would be stricter
        # than the hard block the ruling refused.
        # #VERIFY: tests/unit/test_orchestrator.py::
        # test_a_fill_rate_downgrade_is_marked_and_still_persists stamps the
        # key, and tests/unit/test_worker.py::
        # test_fill_rate_only_needs_review_persists_the_storybook reads it.
        report["fill_rate_downgrade"] = True
    return GenerationOutcome(
        status="needs_review" if downgrade else outcome.status,
        storybook=outcome.storybook,
        report=report,
        attempts=outcome.attempts,
        stage_log=outcome.stage_log,
    )


async def fill_skeleton(
    skeleton: dict[str, object],
    theme_brief: dict[str, object],
    provider: GenerationProvider,
    pii: PiiContext,
    *,
    max_repairs: int = 3,
    settings: Settings | None = None,
    stage1_gate: Stage1Posture = "auto",
    review_stage1_model: str | None = None,
    prep_model: str | None = None,
    slot_bindings: Mapping[str, str] | None = None,
    differentiation_directive: str = "",
    reading_level_passes: int = _DEFAULT_READING_LEVEL_PASSES,
    min_fill_rate: float = 0.6,
) -> GenerationOutcome:
    """Run the automated skeleton-fill pipeline (Fill -> Repair -> Reading level).

    A matched skeleton library file already has hand-authored, gate-validated
    structure; every node needing prose carries a
    ``<<FILL role=... words=... beats='...'>>`` placeholder body, the same
    kind of placeholder Stage A produces for :func:`generate_story`'s Stage B.
    This function reuses the same repair-loop machinery (:func:`_run_one_stage`,
    :func:`_run_repair_loop`, :func:`_build_outcome`) with no Stage A step,
    since the structure already exists on disk.

    Stage 1 fidelity gate (#133): when ``settings`` is supplied (the authoring
    ``automated_provider`` path), a structurally-clean fill is additionally
    checked by :func:`~cyo_adventure.generation.fidelity_gate.run_stage1_gate`
    INSIDE the same bounded repair loop. A fidelity miss (a node that drifts
    from its FILL directive's beat or word-count target) re-enters the loop
    with a fidelity-aware repair prompt, sharing the one ``max_repairs`` budget
    with structural repairs rather than a separate one. Only when that shared
    budget is exhausted does an otherwise-``"passed"`` fill downgrade to
    ``"needs_review"``, with the concrete violation strings recorded under the
    ``"stage1_fidelity_violations"`` report key (the signal
    ``generation/worker.py`` uses to persist the real story behind a
    Stage-1-flagged fill). When ``settings`` is ``None`` (the default), no
    Stage 1 check runs and the behavior is byte-identical to the structural-only
    fill, so any non-authoring caller is unaffected.

    Scale is always "standard": skeleton library files use genre-faithful
    authored node counts (ADR-011), never the "compact" live-model budget
    profile that exists only to bound LLM-invented structure.

    Chunked fill (portability): the fill is one-shot whenever the skeleton's
    expected output fits the resolved cap, which is every production skeleton
    on a large-output backend, and that path is unchanged. When the configured
    model's own ceiling clamps the cap below what the skeleton needs, the fill
    is instead run a batch at a time via :func:`_fill_in_batches`, so the
    catalog is not coupled to one vendor's output ceiling. Four consequences a
    caller should know about:

    * A batch that returns nothing usable fails the whole job. Merging what
      parsed would leave ``<<FILL ...>>`` directives in the book, and every
      gate checker skips a directive rather than failing on it (`AL-325`).
    * The repair budget is zero on that path. Every repair prompt asks for the
      whole document back, which is what does not fit; the Stage 1 fidelity
      CHECK still runs and can still downgrade to ``needs_review``.
    * A bound fill (``slot_bindings`` supplied) chunks too, through
      ``fill_subset_bound.md``. It did not until 2026-08-19, and that was the
      whole of `UW-C302`: a bound skeleton over the serving model's ceiling had
      no degraded path, so it truncated, parsed as nothing, and burned the
      repair budget on every retry. Seven committed skeletons were in that
      state. Every batch carries the bound values, not just the first.
    * Ending ``title`` text IS re-themed on both paths, but by different
      mechanisms. One-shot fill returns the whole document and ``fill.md`` does
      not list ``title`` among the fields it may not change. The batch merge is
      a whitelist and reads exactly three fields: ``body``, choice ``label``,
      and (since the 2026-08-21 ruling, section 8.3) an optional
      ``ending_title`` applied by
      :func:`~cyo_adventure.generation.chunking._merged_ending`, which replaces
      only ``ending.title`` and carries ``id``, ``kind``, and ``valence``
      through from the skeleton. So a chunked reply can reach ending TITLE text
      and nothing else on the ending block; the PL-15 fail-state policy fields
      stay unreachable by construction. An earlier draft of this bullet
      predated the ruling and said the merge read only ``body`` and choice
      ``label`` (PR #737 review, I5). This is reader-visible either way, and it
      is one of the things `UW-C269` compares before this path writes anything
      a child reads.

    Args:
        skeleton: The matched skeleton dict, FILL directives intact.
        theme_brief: The concept brief driving the reskin (names, setting,
            surface theme adapted; plot beats preserved).
        provider: The :class:`~cyo_adventure.generation.provider.GenerationProvider`
            to call for completions.
        pii: The :class:`~cyo_adventure.generation.pii.PiiContext` carrying
            real-child names that must not appear in any prompt.
        max_repairs: Maximum number of repair attempts before giving up.
            Defaults to 3.
        settings: Application settings enabling the Stage 1 fidelity gate. When
            ``None`` (default) the fidelity gate is off and the fill is
            structural-only, so existing non-authoring callers are unaffected.
        stage1_gate: Which fidelity posture this call is asking for.
            ``"auto"`` (default) preserves the historical rule, arming the gate
            exactly when ``settings`` is supplied. ``"required"`` arms it and
            raises when ``settings`` is absent, so a caller that means to be
            gated cannot silently not be. ``"skipped"`` states the ungated
            posture out loud and never arms it, even with ``settings`` present.
            Whichever is chosen, the resolved posture is stamped on the outcome
            report as ``"stage1_gate"``, because a ``"passed"`` from an ungated
            fill and a ``"passed"`` from a gated one are different claims and
            four harness scripts were reading them as the same one (`AL-324`).
        review_stage1_model: Optional admin-chosen review-model override for the
            Stage 1 semantic fidelity check. Ignored when ``settings`` is
            ``None``.
        prep_model: The model that wrote the fill; the Stage 1 semantic check's
            review-model default when ``review_stage1_model`` is unset (#134).
            Ignored when ``settings`` is ``None``.
        slot_bindings: WS-2 bound-fill values. When set, ``skeleton`` is
            expected to already be rendered by
            :func:`~cyo_adventure.generation.binding.render_bound_skeleton`,
            and the initial fill prompt uses the bound-fill variant
            (:func:`~cyo_adventure.generation.prompts.build_bound_fill_prompt`)
            instead of the free-text variant. ``None`` (default) preserves the
            byte-identical legacy prompt for every existing caller.
        differentiation_directive: The trusted differentiation block (A6/A7) from
            :func:`~cyo_adventure.generation.prompts.build_differentiation_directive`,
            carrying this family's escalation level, the drawn craft axis, and the
            titles of prior stories on this same skeleton. Empty by default, in
            which case the prompt renders its explicit no-context block; it is
            never left as an unfilled template token. Threaded into both the
            free-text and the bound-fill prompt variants, so contract-bound
            skeletons receive the same A6/A7 anti-repetition steering.
        reading_level_passes: Maximum Stage D (reading-level) passes over the
            filled book once it is structurally clean. ``0`` disables the
            stage. Defaults to two; see ``_DEFAULT_READING_LEVEL_PASSES``.
        min_fill_rate: Floor for the story-level fill rate (delivered words
            over commissioned ``words=`` words, per-node surplus discounted).
            A passing book below it is downgraded to ``needs_review``, never
            hard-blocked (ruled 2026-08-21, section 9.3 of
            ``live-structural-round-2026-08-21.md``, `UW-C307`); the measured
            rate is stamped on the report either way. The 0.6 default is the
            `AL-490` calibration and stands until per-vendor, per-band floors
            exist (`AL-516`/`AL-528`); pass ``0`` to measure without ever
            downgrading.

    Returns:
        A :class:`GenerationOutcome` describing the final status, the last
        produced document (if any), the final gate report, the number of
        repair attempts, and a human-readable stage log.

    Raises:
        ValidationError: If any assembled prompt contains forbidden PII. The
            provider is never called when this occurs.
    """
    # #ASSUME: data-integrity: `nan < x` is False for every x, so a NaN floor
    # silently disabled the fill-rate gate while reporting it configured
    # (PR #737 review, suggested findings). Refuse it up front, before any
    # provider spend.
    if math.isnan(min_fill_rate):
        msg = "min_fill_rate must be a number (got NaN); use 0 to measure only"
        raise ConfigurationError(msg)
    stage_log: list[str] = []
    guarded_provider = PiiGuardedProvider(provider, forbidden=pii)

    # Stage 1 is opt-in: only the authoring path supplies settings. The gate
    # needs the UNFILLED skeleton (`original`) plus the review-model resolution
    # inputs; the guarded provider above is the fill/repair provider, distinct
    # from the review provider run_stage1_gate builds internally.
    armed = _resolve_stage1_posture(stage1_gate, settings)
    stage1_config = (
        _Stage1Config(
            original=skeleton,
            review_stage1_model=review_stage1_model,
            prep_model=prep_model,
            settings=settings,
            pii=pii,
            # Derived from the provider the caller handed us, so no call site
            # has to learn about metering to be metered.
            ledger=ledger_of(provider),
        )
        if armed and settings is not None
        else None
    )

    # Resolve the cap against the model that will actually serve the call. The
    # PROVIDER is asked first, because it is the only object built with a per-job
    # model override (`worker.py` passes `model_override=` when constructing it,
    # while handing this function the module-level `_default_settings`), so
    # reading `Settings` alone silently resolves the cap for the process default
    # instead of for the job's model (`AL-432`).
    #
    # #ASSUME: external-resources: a provider that declares no `model` (a mock,
    # or `FallbackProvider`'s cascade, which has no single answer) falls back to
    # the configured default. The cascade case is a KNOWN residual gap: its
    # fallback legs can run under a cap resolved for the primary. Deciding what a
    # cascade should report is an owner call, not something to infer here, so it
    # is registered as `UW-C271` rather than guessed at.
    # #VERIFY: test_fill_output_cap.py::
    # test_the_provider_model_outranks_the_configured_default.
    provider_model: object = getattr(provider, "model", None)
    resolved_model = (
        provider_model
        if isinstance(provider_model, str)
        else (active_fill_model(settings) if settings is not None else None)
    )
    cap = (
        resolve_output_cap(resolved_model)
        if (resolved_model is not None or settings is not None)
        else _MAX_TOKENS_PROSE
    )
    # Chunking is the exception, not the rule: a skeleton takes the byte-identical
    # one-shot path whenever it fits the resolved cap. It becomes True only when
    # the backend's own output ceiling clamps the cap under what this skeleton
    # needs, which is the portability case this whole path exists for. On the
    # shipped default (`anthropic/claude-haiku-4.5`, ceiling 64,000) that is 19 of
    # the 73 production skeletons (measured 2026-08-19; it read "15 of the 55"
    # until then, which was true of a smaller catalog), so this path IS live
    # rather than theoretical. Since `UW-C302` it carries bound fills too, which
    # is what makes 7 of those 19 reachable at all.
    chunked = not is_fill_feasible(skeleton, max_tokens=cap)

    def fill_normalizer(doc: dict[str, object]) -> dict[str, object]:
        """Restore frozen fields from the skeleton (2026-08-21 ruling, 8.2).

        The chunked path never needs this (its merge is a whitelist by
        construction); the one-shot fill and every repair pass do, so the
        gate grades a document whose machine-critical fields are the
        skeleton's own and frozen-field drift stops costing repair cycles.
        Restorations are logged, not graded: measured across 16 one-shot
        fills, every frozen mutation was a theme retheme, not sabotage.
        """
        result = normalize_filled_story(skeleton, doc)
        if result.skipped_reason is not None:
            _logger.warning("fill_normalization_skipped", reason=result.skipped_reason)
        elif result.restored:
            _logger.warning(
                "fill_frozen_fields_restored",
                count=len(result.restored),
                restored=list(result.restored[:8]),
            )
        return result.document

    if chunked:
        try:
            current_doc, gate_result = await _fill_in_batches(
                skeleton,
                theme_brief,
                _ChunkedFillContext(
                    provider=guarded_provider,
                    cap=cap,
                    differentiation_directive=differentiation_directive,
                    stage_log=stage_log,
                    slot_bindings=slot_bindings,
                    model=resolved_model if isinstance(resolved_model, str) else None,
                ),
            )
        except UnpartitionableSkeletonError as exc:
            # No partition of this skeleton fits the cap, so no amount of
            # retrying changes the answer. Returned as a failed outcome rather
            # than raised, so an RQ job records a deterministic failure instead
            # of retrying a call that provably cannot succeed (`AL-329`).
            #
            # Narrowed from `except ValidationError` deliberately: that also
            # caught a PII abort from `PiiGuardedProvider.complete` and a
            # rejected model reply from `merge_fill_batch`, reporting both as
            # "unfillable under cap". The PII case is the serious one, since it
            # is a security stop that propagates on the one-shot path and must
            # do the same here rather than being recorded as a capacity limit
            # (`AL-435`).
            return _unfillable_outcome(exc, stage_log, armed=armed)
    else:
        # WS-2: a parameterized fill (slot_bindings supplied) already has its
        # beats/titles/labels rendered onto `skeleton` by render_bound_skeleton;
        # the bound-fill prompt variant carries those validated values as
        # labeled data alongside the byte-identical untrusted-brief fence.
        # `slot_bindings is None` (the default) is the only path every existing
        # caller exercises, so this keeps their prompt byte-identical.
        fill_prompt = (
            build_bound_fill_prompt(
                json.dumps(skeleton),
                json.dumps(dict(slot_bindings)),
                json.dumps(theme_brief),
                differentiation_directive,
            )
            if slot_bindings is not None
            else build_fill_prompt(
                json.dumps(skeleton),
                json.dumps(theme_brief),
                differentiation_directive,
            )
        )
        current_doc, gate_result = await _run_one_stage(
            fill_prompt,
            provider=guarded_provider,
            max_tokens=cap,
            context="fill_result",
            normalize=fill_normalizer,
        )
    _append_stage_log(stage_log, "stage_fill", current_doc, gate_result)
    if chunked and current_doc is None:
        # A batch produced nothing usable. Terminate here rather than entering
        # the repair loop: the repair prompt asks for the WHOLE document back,
        # and the whole document not fitting the cap is precisely why this fill
        # was chunked, so every repair attempt would truncate at the same
        # budget (`AL-329`). Failing is also the only honest verdict about a
        # book no model wrote (`AL-327`).
        return _with_stage1_posture(
            _build_outcome(gate_result, None, 0, stage_log), armed=armed
        )
    last_valid_doc = current_doc if current_doc is not None else skeleton

    attempts = 0
    stage1_violations: list[str] = []
    # Enter the loop when there is structural repair to do OR a Stage 1 fidelity
    # check to run on the clean fill; the loop itself decides which per iteration.
    if gate_result.blocked or stage1_config is not None:
        # A chunked fill gets no repair budget: every prompt the loop can send
        # (structural repair, fidelity repair) asks for the whole document
        # back, which is the thing that does not fit. With the budget at zero
        # the loop still runs the Stage 1 fidelity CHECK, whose own output is a
        # short violation list rather than a book, so the authoring gate is not
        # skipped and the outcome's ``stage1_gate`` posture stays truthful
        # (`AL-324`); only the un-emittable repair call is withheld.
        repair_ctx = _RepairContext(
            provider=guarded_provider,
            max_repairs=0 if chunked else max_repairs,
            stage_log=stage_log,
            stage1=stage1_config,
            context="fill_result",
            # A repair asks for the whole corrected book, so it needs at least
            # the room the fill itself had. `max` rather than plain `cap` so a
            # backend whose clamped ceiling is BELOW the 32,000 floor does not
            # also shrink the repair budget for a document that fits it.
            max_tokens=max(_MAX_TOKENS_REPAIR, cap),
            normalize=fill_normalizer,
        )
        repair_seed = current_doc if current_doc is not None else last_valid_doc
        current_doc, gate_result, attempts, stage1_violations = await _run_repair_loop(
            gate_result, repair_seed, repair_ctx
        )

    # Stage D: reading-level repair on a structurally-clean fill. Runs before
    # the Stage 1 downgrade below rather than after, because the downgrade only
    # changes a status, and a book bound for admin review still benefits from
    # prose a child can read. Skipped outright when the gate is blocked.
    current_doc, gate_result, reading_level = await _repair_reading_level(
        current_doc,
        gate_result,
        ReadingLevelContext(
            provider=guarded_provider,
            max_passes=reading_level_passes,
            stage_log=stage_log,
        ),
    )

    outcome = _with_stage1_posture(
        _fail_on_unfilled_skeleton(
            _build_outcome(gate_result, current_doc, attempts, stage_log),
            skeleton,
            stage_log,
        ),
        armed=armed,
    )

    # A structurally-clean fill that still fails Stage 1 after the shared budget
    # is exhausted downgrades from "passed" to "needs_review". The storybook is
    # kept (never discarded) and the violations are recorded so an admin can
    # reach the real story; worker.py keys its persist decision on this exact
    # report field.
    if stage1_violations and outcome.status == "passed":
        # Built via the GenerationOutcome constructor directly (not
        # dataclasses.replace): replace()'s generic TypeVar-bound return type
        # resolves to the DataclassInstance protocol under some type-checker
        # inference, not the concrete GenerationOutcome (S5886); constructing
        # the instance directly keeps the return type unambiguous everywhere.
        outcome = GenerationOutcome(
            status="needs_review",
            storybook=outcome.storybook,
            report={
                **outcome.report,
                "stage1_fidelity_violations": stage1_violations,
            },
            attempts=outcome.attempts,
            stage_log=outcome.stage_log,
        )

    outcome = _with_fill_rate(outcome, skeleton, min_fill_rate, stage_log)
    return _with_reading_level(outcome, reading_level)
