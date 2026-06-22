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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from cyo_adventure.generation.pii import assert_prompt_pii_safe
from cyo_adventure.generation.prompts import (
    build_prose_prompt,
    build_repair_prompt,
    build_structure_prompt,
)
from cyo_adventure.validator.gate import GateResult, run_gate
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)

if TYPE_CHECKING:
    from cyo_adventure.generation.concept import ConceptBrief
    from cyo_adventure.generation.pii import PiiContext
    from cyo_adventure.generation.prompts import StagePrompt
    from cyo_adventure.generation.provider import GenerationProvider

__all__ = [
    "GenerationOutcome",
    "generate_story",
]

# #CRITICAL: security: assert_prompt_pii_safe runs before every provider.complete
# call; a PII violation aborts generation before any external egress.
# #VERIFY: test_orchestrator asserts provider.calls is empty when a brief would
# leak a seeded real-child name (PII abort test case).

# #ASSUME: external-resources: provider.complete performs network I/O in real
# impls (mocked here); the orchestrator is provider-agnostic via the
# GenerationProvider protocol.
# #VERIFY: Phase 2b wiring adds timeout/retry/backoff before any real provider
# is injected.

# The role instruction and JSON-only directive now live in each stage template's
# system block (the cacheable region), so no shared system constant is needed
# here; the orchestrator forwards StagePrompt.system to the provider verbatim.

_MAX_TOKENS_STRUCTURE = 4096
_MAX_TOKENS_PROSE = 8192
_MAX_TOKENS_REPAIR = 8192

# Type alias: (sorted_findings_tuple, doc_sha256_hex)
_Signature = tuple[tuple[tuple[str, str | None, str | None, str], ...], str]


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
    """

    status: Literal["passed", "needs_review", "failed"]
    storybook: dict[str, object] | None
    report: dict[str, object]
    attempts: int
    stage_log: list[str]


@dataclass(slots=True)
class _RepairContext:
    """Grouped parameters for the repair loop to stay under the arg-count limit.

    Not frozen: ``stage_log`` is mutated in place (appended to) by
    ``_run_repair_loop``. Making this frozen while holding a mutable list field
    would be a footgun (the list itself is still mutable even under ``frozen``).

    Attributes:
        pii: PII context forwarded to every :func:`_run_one_stage` call.
        provider: The generation provider.
        max_repairs: Maximum number of repair attempts.
        stage_log: Accumulated log list; entries are appended in place.
    """

    pii: PiiContext
    provider: GenerationProvider
    max_repairs: int
    stage_log: list[str]


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


def _empty_blocked_gate() -> GateResult:
    """Synthesise a minimal blocked gate result for parse-error cases.

    Returns:
        A :class:`~cyo_adventure.validator.gate.GateResult` with one
        synthetic ``L1-1`` ERROR finding indicating a parse failure.
    """
    report = ValidationReport()
    report.add(
        ValidationFinding(
            rule_id="L1-1",
            severity=Severity.ERROR,
            story_id="<unknown>",
            message="L1-1 schema: provider output was not valid JSON or not a dict",
        )
    )
    return GateResult(report=report, blocked=True, safety_flagged=False)


async def _run_one_stage(
    stage_prompt: StagePrompt,
    *,
    pii: PiiContext,
    provider: GenerationProvider,
    max_tokens: int,
) -> tuple[dict[str, object] | None, GateResult]:
    """Run a single generation stage: PII-guard, call provider, parse, gate.

    The PII guard MUST be invoked before the provider call. If it raises
    :class:`~cyo_adventure.core.exceptions.ValidationError` that exception
    propagates up immediately (no swallowing).

    Args:
        stage_prompt: The assembled :class:`~cyo_adventure.generation.prompts.StagePrompt`
            for this stage (a static system block and a volatile user block).
        pii: The PII context to guard the prompt against.
        provider: The generation provider to call.
        max_tokens: Maximum tokens for the provider completion.

    Returns:
        A tuple of ``(doc_or_none, gate_result)``. ``doc_or_none`` is the
        parsed dict when JSON parsing succeeded; ``None`` on a parse error.
        ``gate_result`` is always present: either the real gate result for a
        successfully parsed dict, or a synthetic blocked result for parse
        failures.

    Raises:
        ValidationError: If either block contains forbidden PII (propagates
            immediately; the provider is never called).
    """
    # #CRITICAL: security: assert_prompt_pii_safe runs on BOTH the system and
    # user blocks before every provider.complete call; a PII violation aborts
    # generation before any external egress. Brief-derived content lives in the
    # user block, but the system block is guarded too so no future template
    # change can smuggle PII past the guard.
    # #VERIFY: PII abort test asserts provider.calls is empty after the raise.
    assert_prompt_pii_safe(stage_prompt.system, forbidden=pii)
    assert_prompt_pii_safe(stage_prompt.user, forbidden=pii)

    raw = await provider.complete(
        system=stage_prompt.system,
        prompt=stage_prompt.user,
        max_tokens=max_tokens,
    )

    # Parse: treat any non-dict or non-JSON as a synthetic blocked gate.
    try:
        parsed: object = json.loads(raw)  # pyright: ignore[reportAny]
    except json.JSONDecodeError:
        return None, _empty_blocked_gate()

    if not isinstance(parsed, dict):
        return None, _empty_blocked_gate()

    doc = cast("dict[str, object]", parsed)
    return doc, run_gate(doc)


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


async def _run_repair_loop(
    gate_result: GateResult,
    current_doc: dict[str, object] | None,
    ctx: _RepairContext,
) -> tuple[dict[str, object] | None, GateResult, int]:
    """Run the bounded Stage C repair loop.

    Attempts up to ``ctx.max_repairs`` repairs on the current (blocked)
    document. Stops early when no-progress is detected: if a repair produces
    the same gate findings AND the same document hash as the previous state,
    further attempts cannot help.

    No-progress seeding: ``prev_signature`` is initialised from the document
    entering the loop (Stage B output, or Stage A output if Stage B was
    skipped). This means that if repair 1 returns the same document as Stage B,
    the loop stops after exactly 1 attempt.

    Args:
        gate_result: The gate result from Stage A or B (must be blocked).
        current_doc: The document from Stage A or B (may be ``None`` on parse
            error).
        ctx: Grouped repair context (pii, provider, max_repairs, stage_log).

    Returns:
        A ``(current_doc, gate_result, attempts)`` triple reflecting the state
        after the loop exits.
    """
    # Seed with the state entering the loop so the first repair can be
    # detected as no-progress immediately if it returns an identical output.
    prev_signature: _Signature = _gate_signature(gate_result, current_doc)
    attempts = 0

    while gate_result.blocked and attempts < ctx.max_repairs:
        failing_findings = _get_failing_findings(gate_result)
        # #EDGE: data-integrity: generate_story seeds this loop with the last
        # valid document (Stage A skeleton if Stage B parse-failed), so "{}" is
        # only reached when no stage ever produced a parseable document.
        # #VERIFY: covered by test_orchestrator stage-skeleton preservation cases.
        current_json = json.dumps(current_doc) if current_doc is not None else "{}"

        repair_prompt = build_repair_prompt(current_json, failing_findings)
        new_doc, new_gate = await _run_one_stage(
            repair_prompt,
            pii=ctx.pii,
            provider=ctx.provider,
            max_tokens=_MAX_TOKENS_REPAIR,
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

    return current_doc, gate_result, attempts


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

    PII guard placement: :func:`~cyo_adventure.generation.pii.assert_prompt_pii_safe`
    is called on every assembled prompt before the corresponding provider
    call. A PII violation raises
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
            real-child names and birthdates that must not appear in any prompt.
        max_repairs: Maximum number of repair attempts before giving up.
            Defaults to 3.

    Returns:
        A :class:`GenerationOutcome` describing the final status, the last
        produced document (if any), the final gate report, the number of
        repair attempts, and a human-readable stage log.

    Raises:
        ValidationError: If any assembled prompt contains forbidden PII. The
            provider is never called when this occurs.
    """
    stage_log: list[str] = []

    # ------------------------------------------------------------------
    # Stage A: Structure skeleton
    # ------------------------------------------------------------------
    stage_a_prompt = build_structure_prompt(brief)
    current_doc, gate_result = await _run_one_stage(
        stage_a_prompt,
        pii=pii,
        provider=provider,
        max_tokens=_MAX_TOKENS_STRUCTURE,
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
            pii=pii,
            provider=provider,
            max_tokens=_MAX_TOKENS_PROSE,
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
            pii=pii,
            provider=provider,
            max_repairs=max_repairs,
            stage_log=stage_log,
        )
        # Seed the loop with the last valid document so a Stage B parse failure
        # repairs from Stage A's skeleton rather than an empty object, and the
        # surfaced outcome is needs_review (skeleton present) rather than failed.
        repair_seed = current_doc if current_doc is not None else last_valid_doc
        current_doc, gate_result, attempts = await _run_repair_loop(
            gate_result,
            repair_seed,
            repair_ctx,
        )

    return _build_outcome(gate_result, current_doc, attempts, stage_log)
