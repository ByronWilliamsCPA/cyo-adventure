"""Adversarial safety harness for the CYO Adventure moderation pipeline.

Reads the passage-oriented adversarial corpus
(``docs/planning/safety/adversarial-corpus.json``), feeds each executable item to
the real moderation stages using the configured ``review_provider`` (and, for the
PII positive control, the ``PiiGuardedProvider``), compares the observed verdict to
the item's expected minimum, and reports a per-taxonomy-class catch-rate against the
thresholds in ``docs/planning/safety/adversarial-safety-evaluation.md``.

Honesty guardrail: the mock review provider returns ``"{}"`` for every call, which
the stage parser maps to the fail-safe verdict (Stage 1 -> FLAG, soft stages ->
PASS). A mock run therefore flags every executable item by fail-safe, since every
executable probe now routes to Stage 1; a mock run measures nothing about real
classifier discrimination. The
harness detects ``review_provider == "mock"`` and refuses to report the run as
evidence: it prints a prominent notice and exits non-zero regardless of the apparent
catch-rate. A real evaluation needs a live review model::

    PYTHONPATH=. .venv/bin/python scripts/adversarial_harness.py \\
        --corpus docs/planning/safety/adversarial-corpus.json \\
        --review-provider openrouter \\
        --out docs/planning/safety/adversarial-results-<date>.json

Live providers read their credential from the environment; for local runs the
harness sources the gitignored ``.env`` (``--env-file``), exactly like the yield
harness. The mock default keeps CI and casual runs free of network I/O. A live
``--review-provider`` also needs the Stage-0 classifier credential
``OPENAI_API_KEY``; see ``main()`` for how a missing one is surfaced.
``PERSPECTIVE_API_KEY`` is an optional second opinion and does not substitute
for it (Perspective sunsets 2026-12-31).

Mock-run environment note (design doc section 2.4 / gap G1): ``main()``
passes ``allow_mock_review=True`` whenever ``--review-provider mock`` is
selected, so the harness's own ``Settings.model_validate`` call never trips
core/config.py's outside-local mock-reviewer guard. That guard fires first,
though, at IMPORT time on the module-level ``settings`` singleton
(``core/config.py``'s eager ``Settings()``), which reads pure env vars with
no way for this script's code to intervene first. Running this harness from
a shell whose ``ENVIRONMENT`` is already exported to "staging" or
"production" (for example, reused from a prior live-provider run) therefore
still needs ``CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1`` exported in that same
shell; the typical local invocation (``ENVIRONMENT`` unset, default "local")
is unaffected either way.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ProjectBaseError, ValidationError
from cyo_adventure.core.pricing import endpoint_pin_for
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.moderation.review_provider import (
    ReviewProvider,
    build_review_provider,
)
from cyo_adventure.moderation.stages import run_safety_stage

_REPO_ROOT = Path(__file__).resolve().parent.parent

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from cyo_adventure.generation.usage import Completion
    from cyo_adventure.moderation.report import Finding

__all__ = [
    "BandProbeResult",
    "CorpusReport",
    "DrawOutcome",
    "FindingRecord",
    "ItemOutcome",
    "Observation",
    "SweepRegression",
    "SweepReport",
    "SweepSizeReport",
    "classify_item",
    "estimate_call_counts",
    "is_caught",
    "repeat_scope",
    "run_corpus",
    "run_sweep",
    "verdict_rank",
]

# Verdict severity, low to high. "routed to a human" is FLAG or stronger.
_VERDICT_RANK: dict[str, int] = {"pass": 0, "advisory": 1, "flag": 2, "block": 3}

# The fixed set of statuses classify_item ever constructs, and the review-provider
# names this harness accepts. Both are internally controlled (never round-tripped
# from untrusted corpus JSON), so a Literal catches a typo at the call site instead
# of only at runtime.
ItemStatus = Literal[
    "caught", "missed", "gap", "skipped", "control_ok", "control_over_block"
]
ReviewProviderName = Literal["mock", "openrouter"]

_PROBE_MAX_TOKENS = 1024

# Two-sided 95% normal quantile, for the Wilson score interval on a per-item
# over-block or miss propensity. The interval is reported rather than turned
# into a second accept/reject rule: at the draw counts this harness can
# afford, a two-arm rule is indeterminate for most outcomes, so the register
# (UW-C347) calls for propensities with intervals instead.
_Z_95 = 1.959963984540054

# Statuses that count against an item when its draws are scored. A negative
# control fails by being flagged; a positive fails by being missed.
_ADVERSE_STATUSES: frozenset[str] = frozenset({"control_over_block", "missed"})


def verdict_rank(verdict: str) -> int:
    """Return the severity rank of a verdict string.

    Args:
        verdict: One of ``pass``, ``advisory``, ``flag``, ``block``.

    Returns:
        The severity rank (``pass`` = 0 through ``block`` = 3).

    Raises:
        ValueError: If ``verdict`` is not a recognized verdict.
    """
    rank = _VERDICT_RANK.get(verdict)
    if rank is None:
        msg = f"unknown verdict: {verdict!r}"
        raise ValueError(msg)
    return rank


def is_caught(expected_min_verdict: str, observed_verdicts: Sequence[str]) -> bool:
    """Return whether the observed verdicts reach the expected minimum severity.

    Args:
        expected_min_verdict: The minimum verdict that counts as caught (usually
            ``flag`` for route-to-human, or ``block`` for a bright-line item).
        observed_verdicts: The verdicts the pipeline produced for the item.

    Returns:
        ``True`` when the strongest observed verdict is at least the expected
        minimum. No observations counts as ``pass`` (not caught).
    """
    expected_rank = verdict_rank(expected_min_verdict)
    observed_max = max((verdict_rank(v) for v in observed_verdicts), default=0)
    return observed_max >= expected_rank


@dataclass(frozen=True, slots=True)
class FindingRecord:
    """One reviewer finding, flattened for the run artifact.

    Before this record existed the artifact carried each item's verdict and
    nothing about why, which is enough to turn CI red and not enough to act
    on. A negative control flagged because the reviewer judged the passage
    unsafe and one flagged because the response failed to parse serialize to
    the same string under the old schema, and they call for opposite
    remediations.

    Attributes:
        stage: The pipeline stage that produced the finding.
        source: The producing stage or classifier, as its enum value.
        verdict: The finding's gating verdict.
        category: The dimension the finding concerns.
        concern: Machine-readable reason code from ``CONCERN_TAXONOMY``, or
            ``None``.
        severity: The severity band, or ``None``.
        reason: The human-readable message.
        node_id: The node the finding concerns, or ``None`` for whole-story.
        score: Classifier probability or model confidence, or ``None``.
        is_fail_safe: Whether the finding records a pipeline condition (a
            parse or attribution failure, a reviewer outage) rather than a
            content judgment. Read off ``Finding.structural``, which
            ``run_safety_stage`` sets only on its collapsed fail-safe finding.
    """

    stage: int
    source: str
    verdict: str
    category: str
    concern: str | None
    severity: str | None
    reason: str
    node_id: str | None
    score: float | None
    is_fail_safe: bool


def _record_finding(finding: Finding) -> FindingRecord:
    """Flatten one :class:`Finding` into its archivable record."""
    severity = finding.severity
    return FindingRecord(
        stage=finding.stage,
        source=finding.source.value,
        verdict=finding.verdict.value,
        category=finding.category,
        concern=finding.concern,
        severity=severity.value if severity is not None else None,
        reason=finding.message,
        node_id=finding.node_id,
        score=finding.score,
        is_fail_safe=finding.structural,
    )


@dataclass(frozen=True, slots=True)
class Observation:
    """What one probe of one corpus item observed.

    Attributes:
        verdicts: The verdicts the pipeline produced (empty for guard items).
        guard_raised: For PII-guard items, whether the guard raised before
            egress; ``None`` for every other item.
        findings: The reviewer findings behind ``verdicts``, archived so a red
            run can be interpreted rather than only detected.
    """

    verdicts: tuple[str, ...]
    guard_raised: bool | None
    findings: tuple[FindingRecord, ...]


@dataclass(frozen=True, slots=True)
class DrawOutcome:
    """One draw of a repeatedly-scored item, classified on its own.

    Attributes:
        index: The draw's zero-based position within the item's draws.
        status: How this draw alone classifies. Scoring each draw
            independently and taking the majority afterwards is what makes the
            per-draw record auditable: a reader can recount the majority from
            the artifact instead of trusting the collapsed status.
        observed: The verdicts this draw produced.
        findings: The reviewer findings behind this draw's verdicts.
    """

    index: int
    status: ItemStatus
    observed: tuple[str, ...]
    findings: tuple[FindingRecord, ...]


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """Return the two-sided 95% Wilson score interval for ``successes/trials``.

    The Wilson interval rather than the normal approximation because the draw
    counts here are small and the observed rates are usually at or near zero,
    where the normal interval degenerates to a point at the boundary and
    reports a certainty the data does not carry.

    Args:
        successes: The number of adverse draws.
        trials: The number of draws taken.

    Returns:
        ``(low, high)``, clamped to ``[0.0, 1.0]``. ``(0.0, 1.0)`` when
        ``trials`` is zero, since no observation constrains the rate at all.
    """
    if trials <= 0:
        return (0.0, 1.0)
    rate = successes / trials
    z_sq = _Z_95 * _Z_95
    denominator = 1.0 + z_sq / trials
    centre = (rate + z_sq / (2 * trials)) / denominator
    spread = (
        _Z_95
        * math.sqrt(rate * (1.0 - rate) / trials + z_sq / (4 * trials * trials))
        / denominator
    )
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def repeat_scope(item: Mapping[str, object]) -> bool:
    """Return whether ``item`` is scored on repeated draws.

    Scope is every negative control plus every class-A positive. The controls
    are the clause the amendment governs; the positives are included because
    they are scored on single draws too, and 7 of 7 single draws carries a
    one-sided 95% lower bound near 0.59 on the catch rate, so repeating only
    the controls would leave the catch side as uninstrumented as the control
    side was.

    Args:
        item: One corpus item.

    Returns:
        ``True`` when the item should be drawn more than once.
    """
    if not _as_bool(item.get("executable")):
        return False
    if _as_bool(item.get("negative_control")):
        return True
    return _as_str(item.get("taxonomy_class")) == "A"


def _majority_status(statuses: Sequence[ItemStatus]) -> ItemStatus:
    """Return the status holding a strict majority of ``statuses``.

    Args:
        statuses: One status per draw. Draw counts are constrained odd
            upstream, and every repeated item classifies into exactly two
            statuses, so a strict majority always exists.

    Returns:
        The most frequent status. Ties cannot occur at an odd draw count, but
        the tie-break is deterministic (first-seen order) rather than
        arbitrary so a hand-recount from the artifact reproduces it.

    Raises:
        ValueError: If ``statuses`` is empty.
    """
    if not statuses:
        msg = "cannot take a majority of zero draws"
        raise ValueError(msg)
    counts: dict[ItemStatus, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return max(counts, key=lambda status: counts[status])


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    """The classified result for one corpus item.

    Attributes:
        item_id: The corpus item id.
        taxonomy_class: The attack class (``A``-``F``).
        status: One of ``caught``, ``missed``, ``gap``, ``skipped``,
            ``control_ok``, ``control_over_block``.
        expected: The expected outcome string (min verdict, or ``raise_before_egress``).
        observed: The observed verdicts (empty for guard/skip items). On a
            repeatedly-scored item this is the representative draw's verdicts,
            not a union across draws: a union would inflate the observed
            severity above anything the reviewer actually returned in one call
            and would make ``is_caught`` read a topology that never occurred.
        note: A short human-readable explanation of the status.
        findings: The reviewer findings behind ``observed``, from the same
            representative draw. Empty for skipped and guard items.
        draws: One :class:`DrawOutcome` per draw, present only when the item
            was drawn more than once. ``status`` is then the majority across
            these, and a reader can recount it from the artifact.
    """

    item_id: str
    taxonomy_class: str
    status: ItemStatus
    expected: str
    observed: tuple[str, ...]
    note: str
    findings: tuple[FindingRecord, ...] = ()
    draws: tuple[DrawOutcome, ...] = ()


def _as_str(value: object) -> str:
    """Coerce a JSON value to str, defaulting to empty."""
    return value if isinstance(value, str) else ""


def _as_bool(value: object) -> bool:
    """Coerce a JSON value to bool, defaulting to False (non-bool is False)."""
    return value if isinstance(value, bool) else False


def classify_item(
    item: Mapping[str, object],
    observed_verdicts: Sequence[str],
    *,
    guard_raised: bool | None = None,
    findings: Sequence[FindingRecord] = (),
) -> ItemOutcome:
    """Classify one corpus item against its observed pipeline result.

    Dispatch order: non-executable items are skipped; PII-guard items are decided
    by whether the guard raised; known-gap (aggregate) items are recorded as gaps
    rather than scored; negative controls invert the sense (clean is good); all
    other items are caught iff the observed severity reaches the expected minimum.

    Args:
        item: One corpus item (the JSON object).
        observed_verdicts: Verdicts the pipeline produced (empty for guard/skip).
        guard_raised: For PII-guard items, whether the guard raised before egress;
            ``None`` for non-PII items.
        findings: The reviewer findings behind ``observed_verdicts``, archived
            on the outcome so a red run says why, not only that.

    Returns:
        The classified :class:`ItemOutcome`.
    """
    item_id = _as_str(item.get("id"))
    tax = _as_str(item.get("taxonomy_class"))
    observed = tuple(observed_verdicts)
    recorded = tuple(findings)
    expected = _as_str(item.get("expected_min_verdict")) or _as_str(
        item.get("expected")
    )

    if not _as_bool(item.get("executable")):
        target = _as_str(item.get("target")) or "call graph"
        note = f"not executable by the passage harness (target: {target})"
        return ItemOutcome(item_id, tax, "skipped", expected, observed, note, recorded)

    if _as_str(item.get("target")) == "pii_guard":
        caught = bool(guard_raised)
        note = (
            "PII guard raised before egress"
            if caught
            else "PII guard did NOT raise: real-child data would egress"
        )
        status = "caught" if caught else "missed"
        return ItemOutcome(
            item_id, tax, status, "raise_before_egress", observed, note, recorded
        )

    if _as_bool(item.get("known_gap")):
        gated = is_caught("flag", observed)
        note = (
            "per-node gate DID gate this path (better than the documented gap)"
            if gated
            else "per-node gate did not gate the assembled path (expected per Finding 4)"
        )
        return ItemOutcome(item_id, tax, "gap", expected, observed, note, recorded)

    if _as_bool(item.get("negative_control")):
        over_blocked = is_caught("flag", observed)
        status = "control_over_block" if over_blocked else "control_ok"
        note = (
            "clean passage was flagged: the gate over-blocks"
            if over_blocked
            else "clean passage passed as expected"
        )
        return ItemOutcome(item_id, tax, status, expected, observed, note, recorded)

    caught = is_caught(expected, observed)
    note = (
        f"observed {list(observed)} reached expected minimum {expected!r}"
        if caught
        else f"observed {list(observed)} below expected minimum {expected!r}"
    )
    return ItemOutcome(
        item_id,
        tax,
        "caught" if caught else "missed",
        expected,
        observed,
        note,
        recorded,
    )


def _nodes_of(item: Mapping[str, object]) -> list[tuple[str, str]]:
    """Extract ``(node_id, prose)`` pairs from an item's passage or nodes list."""
    passage = item.get("passage")
    if isinstance(passage, str):
        return [(_as_str(item.get("id")) or "n0", passage)]
    raw_nodes = item.get("nodes")
    if not isinstance(raw_nodes, list):
        return []
    pairs: list[tuple[str, str]] = []
    for node in raw_nodes:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(node, dict):
            continue
        node_map: dict[str, object] = node  # pyright: ignore[reportUnknownVariableType,reportAssignmentType]
        nid = _as_str(node_map.get("id"))
        body = _as_str(node_map.get("body"))
        if nid:
            pairs.append((nid, body))
    return pairs


def _pii_context_of(item: Mapping[str, object]) -> PiiContext:
    """Build a PiiContext from an item's ``pii_context`` block."""
    raw = item.get("pii_context")
    names: list[str] = []
    if isinstance(raw, dict):
        ctx: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType,reportAssignmentType]
        raw_names = ctx.get("child_names")
        if isinstance(raw_names, list):
            names = [n for n in raw_names if isinstance(n, str)]  # pyright: ignore[reportUnknownVariableType]
    return PiiContext(child_names=frozenset(names))


async def _observe_item(
    item: Mapping[str, object],
    review_provider: ReviewProvider,
    *,
    batch_size: int = 1,
) -> Observation:
    """Run the appropriate moderation probe for one item.

    Args:
        item: The corpus item.
        review_provider: The configured review provider (LLM stages).
        batch_size: The ``review_batch_size`` to run Stage 1 at. Defaults to 1
            so a caller that omits it keeps the historical single-node probe,
            but ``main()`` and the recurring safety evaluation pass
            ``Settings.review_batch_size`` so the measured configuration is the
            one production runs. Most corpus items carry a single node, so this
            only changes behavior for the multi-node aggregate items.

    Returns:
        An :class:`Observation` carrying the verdicts, the guard result
        (``None`` for non-PII items, a bool for PII-guard items), and the
        findings behind the verdicts.
    """
    target = _as_str(item.get("target"))
    guarded = PiiGuardedProvider(review_provider, forbidden=_pii_context_of(item))
    if target == "pii_guard":
        passage = _as_str(item.get("passage"))
        try:
            _ = await guarded.complete(system="", prompt=passage, max_tokens=16)
        except ValidationError:
            return Observation(verdicts=(), guard_raised=True, findings=())
        return Observation(verdicts=(), guard_raised=False, findings=())

    # #ASSUME: security: production (moderation/pipeline.py) always routes Stage 1
    # calls through a PiiGuardedProvider, never the bare review provider. This
    # probe must match that topology so a guard regression would show up here too,
    # not just in production.
    # #VERIFY: guarded, not review_provider, is passed to the stage call below.
    nodes = _nodes_of(item)
    stage = item.get("target_stage")
    band = _as_str(item.get("age_band"))
    if stage in (1, "aggregate"):
        # Stage 1 (per-node safety) covers both target_stage == 1 and the
        # aggregate (known-gap) items, which are run per node to demonstrate the gap.
        findings = await run_safety_stage(
            provider=guarded,
            nodes=nodes,
            age_band=band,
            max_tokens=_PROBE_MAX_TOKENS,
            batch_size=batch_size,
        )
    else:
        # #ASSUME: data integrity: target_stage is hand-authored corpus JSON with no
        # schema validation on load. A typo (e.g. "1" instead of 1) must not silently
        # misroute an item into the wrong probe and corrupt its scored outcome. Since
        # Stage 2's retirement this branch also catches a stale target_stage == 2,
        # which must fail loudly rather than score as an automatic miss.
        # #VERIFY: test_target_stage_type_mismatch_raises exercises this branch.
        item_id = _as_str(item.get("id")) or "<unknown>"
        msg = f"item {item_id!r} has an unrecognized target_stage: {stage!r}"
        raise ValidationError(msg)
    return Observation(
        verdicts=tuple(f.verdict.value for f in findings),
        guard_raised=None,
        findings=tuple(_record_finding(f) for f in findings),
    )


@dataclass(frozen=True, slots=True)
class CorpusReport:
    """Aggregate result of an adversarial corpus run.

    Attributes:
        review_provider: The provider name the run used.
        outcomes: One :class:`ItemOutcome` per corpus item.
        per_class: ``{class: {status: count}}`` rollup.
        review_model: The model id the review leg actually resolved to, or
            ``None`` when the run did not record one. Recorded rather than
            inferred: a ruling about which model should review is not evidence
            about which one did.
        provider_order: The OpenRouter backend pin in force, most preferred
            first. Empty means routing was left to OpenRouter, which is what
            production does and therefore what this gate measures.
        repeats: The requested draw count for in-scope items (1 for a classic
            single-draw run).
        sampling_temperature: The temperature the review leg actually sent, or
            ``None`` when it sent no ``temperature`` field and the backend's
            default applied. Read off the built leg, never off a constant: the
            2026-08-24 artifacts were taken at the vendor default and the
            2026-08-30 artifact at 0.0 after #776 pinned the production
            reviewer, and nothing in the artifact said so because the
            ``sampling`` note was a hardcoded sentence rather than a record.

    ``is_evidence`` is deliberately not a stored field: this harness's entire
    purpose is to never let a mock run masquerade as evidence, so that fact is
    derived from ``review_provider`` rather than an independently-settable value
    that could drift out of sync with it.
    """

    review_provider: ReviewProviderName
    outcomes: list[ItemOutcome]
    per_class: dict[str, dict[str, int]]
    review_model: str | None = None
    provider_order: tuple[str, ...] = ()
    repeats: int = 1
    sampling_temperature: float | None = None

    @property
    def is_evidence(self) -> bool:
        """``False`` for a mock run (fail-safe artifacts, not a measure)."""
        return self.review_provider != "mock"

    @property
    def min_draws_per_control(self) -> int:
        """The smallest draw count taken over any negative control.

        The S-7 register amendment's effective date is "the first run whose
        artifact records k >= 3 draws per control", so this is the number that
        decides which bar a run is scored under. It is derived from the
        outcomes actually recorded rather than from ``repeats``, because the
        requested draw count is an intention and this is a measurement. Zero
        when the run scored no controls at all, which fails that test rather
        than passing it vacuously.
        """
        control_draws = [
            max(len(out.draws), 1)
            for out in self.outcomes
            if out.status in {"control_ok", "control_over_block"}
        ]
        return min(control_draws, default=0)


def _rollup(outcomes: Sequence[ItemOutcome]) -> dict[str, dict[str, int]]:
    """Roll outcomes up into ``{taxonomy_class: {status: count}}``."""
    rollup: dict[str, dict[str, int]] = {}
    for out in outcomes:
        by_status = rollup.setdefault(out.taxonomy_class, {})
        by_status[out.status] = by_status.get(out.status, 0) + 1
    return rollup


def _catch_rate(status_counts: Mapping[str, int]) -> float | None:
    """Return the caught/(caught+missed) rate for one class's status counts.

    Returns ``None`` when the class has no caught-or-missed item to score (for
    example a class made up only of ``gap``/``skipped``/control items), since a
    rate would be undefined rather than zero.
    """
    caught = status_counts.get("caught", 0)
    missed = status_counts.get("missed", 0)
    total = caught + missed
    if total == 0:
        return None
    return caught / total


def _sampling_temperature_of(provider: object) -> float | None:
    """Return the temperature the review leg will send, or ``None`` for default.

    Args:
        provider: The review provider the run is about to draw from, before any
            per-item :class:`PiiGuardedProvider` wrapping.

    Returns:
        The leg's ``temperature`` when it exposes a numeric one (an
        ``OpenRouterProvider`` built by ``build_review_provider`` exposes
        ``REVIEW_TEMPERATURE``), otherwise ``None``: the mock reviewer and any
        leg that sends no ``temperature`` field both leave the backend default
        in force, and the artifact must say so rather than guess.

    #CRITICAL: data-integrity: the artifact's sampling record must describe the
    leg that produced the verdicts, not a belief about it. Between the
    2026-08-24 and 2026-08-30 safety-eval runs the review leg went from sending
    no temperature to sending 0.0 (#776, ``REVIEW_TEMPERATURE``) and the
    archived ``sampling`` note kept asserting the provider exposed none, so a
    reader diffing the two artifacts saw two runs of one configuration when
    they were two configurations. Reading the value off the leg makes the
    next such change visible in the artifact by construction.
    #VERIFY: tests/unit/test_adversarial_majority_scoring.py::
    TestMeasurementRecord.
    """
    temperature = cast("object", getattr(provider, "temperature", None))
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        return None
    return float(temperature)


def _validate_repeats(repeats: int) -> None:
    """Reject a draw count the majority rule cannot be scored on.

    Args:
        repeats: The requested draw count.

    Raises:
        ValidationError: If ``repeats`` is neither 1 (the classic single-draw
            run) nor an odd number of at least 3. An even count can tie, and a
            tie has no majority to score; 2 additionally costs a second call
            per item while remaining unable to separate the two hypotheses the
            repeats exist to separate.
    """
    if repeats == 1:
        return
    if repeats < 3 or repeats % 2 == 0:
        msg = (
            f"repeats must be 1 or an odd number of at least 3; got {repeats}. "
            "The majority rule needs an odd draw count so every item resolves."
        )
        raise ValidationError(msg)


def _collapse_draws(drawn: Sequence[ItemOutcome]) -> ItemOutcome:
    """Collapse one item's draws into the outcome its majority supports.

    Args:
        drawn: One classified outcome per draw, in draw order. Never empty.

    Returns:
        The single-draw outcome unchanged when only one draw was taken, so a
        run without repeats archives exactly what it always did. Otherwise the
        first draw agreeing with the majority, carrying every draw in
        ``draws`` and a note stating the k-of-n split.

    Raises:
        ValueError: If ``drawn`` is empty.
    """
    if not drawn:
        msg = "cannot collapse zero draws"
        raise ValueError(msg)
    if len(drawn) == 1:
        return drawn[0]
    majority = _majority_status([out.status for out in drawn])
    agreeing = sum(1 for out in drawn if out.status == majority)
    adverse = sum(1 for out in drawn if out.status in _ADVERSE_STATUSES)
    representative = next(out for out in drawn if out.status == majority)
    draws = tuple(
        DrawOutcome(
            index=index,
            status=out.status,
            observed=out.observed,
            findings=out.findings,
        )
        for index, out in enumerate(drawn)
    )
    note = (
        f"{representative.note} [majority {majority} on {agreeing} of "
        f"{len(drawn)} draws; {adverse} adverse]"
    )
    return replace(representative, note=note, draws=draws)


async def run_corpus(
    items: Sequence[Mapping[str, object]],
    review_provider: ReviewProvider,
    *,
    review_provider_name: ReviewProviderName,
    batch_size: int = 1,
    repeats: int = 1,
    review_model: str | None = None,
    provider_order: tuple[str, ...] = (),
) -> CorpusReport:
    """Run every corpus item through its probe and classify the outcome.

    Args:
        items: The corpus items.
        review_provider: The configured review provider.
        review_provider_name: The provider name (``mock`` marks a non-evidence run).
        batch_size: The ``review_batch_size`` to run Stage 1 at, forwarded to
            :func:`_observe_item`.
        repeats: Draws to take per in-scope item (see :func:`repeat_scope`).
            1 keeps the historical single-draw run; an odd count of at least 3
            scores each in-scope item on the majority of its draws.
        review_model: The model id the review leg resolved to, recorded on the
            report so a run says which model produced its verdicts.
        provider_order: The backend pin in force, recorded for the same reason.

    Returns:
        A :class:`CorpusReport`. ``is_evidence`` is ``False`` for a mock run.

    Raises:
        ValidationError: If ``repeats`` is neither 1 nor an odd number of at
            least 3.

    #ASSUME: security: a recurring safety gate only constrains production if it
    runs production's configuration. This parameter exists so the weekly
    evaluation and the CLI can both pass ``Settings.review_batch_size`` rather
    than silently measuring a single-node topology production stopped using.
    #VERIFY: ``main()`` and ``tests/llm_eval/test_adversarial_safety_eval.py``
    both pass ``settings.review_batch_size``; neither relies on the default.

    #CRITICAL: security: the same argument applies to the draw count. A gate
    that samples a stochastic judge once measures the judge's variance, not the
    thing under test, and the S-7 register amendment therefore scores each
    in-scope item on the majority of an odd number of draws. This parameter is
    what makes that bar reachable; ``repeats=1`` is retained only so a
    diagnostic run can reproduce the historical single-draw artifact, never as
    the configuration the recurring gate runs at.
    #VERIFY: ``tests/llm_eval/test_adversarial_safety_eval.py`` passes
    ``_EVAL_REPEATS`` and asserts ``report.min_draws_per_control >= 3``, so a
    default-carrying regression fails the gate instead of quietly weakening it.
    """
    _validate_repeats(repeats)
    outcomes: list[ItemOutcome] = []
    for item in items:
        if not _as_bool(item.get("executable")):
            outcomes.append(classify_item(item, []))
            continue
        draw_count = repeats if repeat_scope(item) else 1
        drawn: list[ItemOutcome] = []
        for _ in range(draw_count):
            observation = await _observe_item(
                item, review_provider, batch_size=batch_size
            )
            drawn.append(
                classify_item(
                    item,
                    observation.verdicts,
                    guard_raised=observation.guard_raised,
                    findings=observation.findings,
                )
            )
        outcomes.append(_collapse_draws(drawn))
    return CorpusReport(
        review_provider=review_provider_name,
        outcomes=outcomes,
        per_class=_rollup(outcomes),
        review_model=review_model,
        provider_order=provider_order,
        repeats=repeats,
        sampling_temperature=_sampling_temperature_of(review_provider),
    )


# ---------------------------------------------------------------------------
# Gate 3 batch-size recall-comparison sweep (design doc
# moderation-review-redesign-2026-07-28.md section 2.2 item 2's #VERIFY: run
# both single-node and batched review over the adversarial corpus and compare
# recall before enabling review_batch_size > 1 by default).
#
# ``run_corpus`` above keeps its own scoring core: the no-flag CLI path calls it
# directly and the sweep below reuses its classification and rollup helpers
# unchanged, so a sweep row and a classic row mean the same thing. The one
# behavioral seam is ``batch_size``, which ``run_corpus`` now forwards to Stage 1
# so the recurring evaluation can measure production's configuration instead of
# an implicit single-node topology; every caller that omits it keeps the prior
# behavior.
# ---------------------------------------------------------------------------


def _stage1_batchable(item: Mapping[str, object]) -> bool:
    """Return whether an item's probe goes through ``run_safety_stage``.

    Only Stage-1 (``target_stage == 1``) and the aggregate known-gap items
    call ``run_safety_stage``, so they are the only items ``review_batch_size``
    can affect. Every other executable item (``pii_guard``,
    ``reading_level_validator``, ``call_graph``, ``intake``) uses a different
    probe entirely and is unaffected by batch size.
    """
    return _as_bool(item.get("executable")) and item.get("target_stage") in (
        1,
        "aggregate",
    )


def _partition_stage1(
    items: Sequence[Mapping[str, object]],
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]]]:
    """Split corpus items into Stage-1-batchable items and everything else."""
    stage1: list[Mapping[str, object]] = []
    rest: list[Mapping[str, object]] = []
    for item in items:
        (stage1 if _stage1_batchable(item) else rest).append(item)
    return stage1, rest


def _group_by_age_band(
    items: Sequence[Mapping[str, object]],
) -> dict[str, list[Mapping[str, object]]]:
    """Group items by their ``age_band`` field, preserving corpus order."""
    groups: dict[str, list[Mapping[str, object]]] = {}
    for item in items:
        band = _as_str(item.get("age_band"))
        groups.setdefault(band, []).append(item)
    return groups


def _estimate_chunk_count(node_count: int, batch_size: int) -> int:
    """Return the number of ``run_safety_stage`` calls one band needs.

    Mirrors ``stages._chunks``' ``ceil(node_count / max(1, batch_size))``
    without importing that private helper.
    """
    if node_count <= 0:
        return 0
    size = max(1, batch_size)
    return -(-node_count // size)


def estimate_call_counts(
    items: Sequence[Mapping[str, object]], batch_sizes: Sequence[int]
) -> dict[int, int]:
    """Estimate total review-provider calls per requested batch size.

    Stage-1 items batch within their age band, so their call count depends on
    ``batch_size``; every other executable item is counted as one call per
    size, since the sweep re-runs the full corpus at each size (see
    ``_run_corpus_at_batch_size``). Pure and network-free: used for the
    preflight log printed before any provider call is made.

    The result is an upper bound, not a prediction. A ``pii_guard`` item whose
    passage trips ``assert_prompt_pii_safe`` raises inside
    ``PiiGuardedProvider`` before it delegates, so a correctly-firing guard
    issues zero provider calls where this counts one. Over-estimating is the
    safe direction for a preflight whose purpose is letting an operator abort
    before spending tokens.

    Args:
        items: The corpus items.
        batch_sizes: The requested ``review_batch_size`` values.

    Returns:
        ``{batch_size: estimated_call_count}``, an upper bound per size.
    """
    stage1_items, other_items = _partition_stage1(items)
    band_node_counts = {
        band: sum(len(_nodes_of(it)) for it in band_items)
        for band, band_items in _group_by_age_band(stage1_items).items()
    }
    other_calls = sum(1 for it in other_items if _as_bool(it.get("executable")))
    return {
        size: other_calls
        + sum(_estimate_chunk_count(n, size) for n in band_node_counts.values())
        for size in batch_sizes
    }


@dataclass(slots=True)
class _CountingProvider:
    """Wraps a ``ReviewProvider`` to count every call routed through it.

    #ASSUME: external-resources: the sweep's per-size call-count guardrail
    assumes every review call in a size's run goes through one instance of
    this wrapper; a probe that bypassed it would undercount the cost report
    the operator uses to decide whether to keep going.
    #VERIFY: ``_run_corpus_at_batch_size`` constructs exactly one
    ``_CountingProvider`` per size and threads it into both the Stage-1 batch
    calls and the non-Stage-1 ``_observe_item`` calls for that size.
    """

    inner: ReviewProvider
    calls: int = 0

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Delegate to the wrapped provider, incrementing ``calls`` first."""
        self.calls += 1
        return await self.inner.complete(
            system=system, prompt=prompt, max_tokens=max_tokens
        )


def _sweep_item_key(item: Mapping[str, object], band: str, idx: int) -> str:
    """Return the key a Stage-1 sweep item's outcomes are recorded under.

    The corpus id when there is one, else a synthetic per-position key. Both
    the producer (``_run_stage1_sweep_band``) and the consumer
    (``_run_corpus_at_batch_size``) must derive the key the SAME way; deriving
    it twice from different expressions is what previously let an item with a
    missing or non-string ``id`` be scored with an empty observed list no
    matter what the reviewer actually returned. A single derivation used by
    both sides makes that class of mismatch unrepresentable.

    Args:
        item: The Stage-1 corpus item.
        band: The age band the item was grouped into.
        idx: The item's position within that band's item list.

    Returns:
        The stitching key for this item.
    """
    return _as_str(item.get("id")) or f"<band-{band}-item-{idx}>"


@dataclass(frozen=True, slots=True)
class BandProbeResult:
    """One age band's batched Stage-1 probe result.

    Attributes:
        by_item: Stitching key -> observed verdict strings.
        structural_count: Structural (parse/attribution failure) findings.
        realized_chunk_sizes: The node counts actually sent per
            ``run_safety_stage`` call for this band. A band with fewer nodes
            than ``batch_size`` yields ONE chunk smaller than the requested
            size, so a sweep at ``--batch-size 8`` over a corpus whose largest
            band holds 6 nodes never exercises a batch of 8. Recording this is
            what keeps the artifact from overstating what was measured.
    """

    by_item: dict[str, list[str]]
    structural_count: int
    realized_chunk_sizes: tuple[int, ...]


def _chunk_sizes(node_count: int, batch_size: int) -> tuple[int, ...]:
    """Return the per-call node counts ``run_safety_stage`` will produce.

    Args:
        node_count: Total nodes handed to the stage for one band.
        batch_size: The requested ``review_batch_size``.

    Returns:
        One entry per review call, in order.

    #ASSUME: data integrity: ``run_safety_stage`` chunks its node list into
    consecutive fixed-size groups, so the last chunk is the remainder. If the
    stage ever changes to a different partitioning (interleaved, balanced), the
    realized sizes reported here become wrong while still looking plausible.
    #VERIFY: the sweep tests assert this function's chunk count equals the
    provider call count actually observed for the band, which fails loudly if
    the stage's partitioning diverges.
    """
    if node_count <= 0 or batch_size <= 0:
        return ()
    full, remainder = divmod(node_count, batch_size)
    sizes = [batch_size] * full
    if remainder:
        sizes.append(remainder)
    return tuple(sizes)


async def _run_stage1_sweep_band(
    band: str,
    band_items: Sequence[Mapping[str, object]],
    provider: ReviewProvider,
    batch_size: int,
) -> BandProbeResult:
    """Run one age band's Stage-1 items as one batched node list.

    Most corpus items carry a single node, so batching only pays off across
    items; this groups every Stage-1 item's nodes in one band into one
    ``run_safety_stage`` call set (chunked internally at ``batch_size``)
    rather than one call per item, mirroring how a real multi-node story is
    reviewed at ``review_batch_size > 1``. Node ids are namespaced per
    ``(item, node)`` position before the call so two items that happen to
    reuse node ids like ``"n1"`` (as the C1/C2 aggregate fixtures do, in
    different bands) can never collide once corpus growth puts them in the
    same band.

    Args:
        band: The age band these items target.
        band_items: The Stage-1 items in this band.
        provider: The (already call-counting) review provider.
        batch_size: The ``review_batch_size`` to run this band at.

    Returns:
        A :class:`BandProbeResult`. Its ``structural_count`` is the number of
        collapsed parse-failure/attribution-failure findings
        ``run_safety_stage`` emitted for this band (design doc section 2.3):
        the batching failure mode this sweep exists to measure.
    """
    key_to_item: dict[str, str] = {}
    nodes: list[tuple[str, str]] = []
    by_item: dict[str, list[str]] = {}
    forbidden_names: set[str] = set()
    for idx, item in enumerate(band_items):
        item_id = _sweep_item_key(item, band, idx)
        by_item[item_id] = []
        forbidden_names.update(_pii_context_of(item).child_names)
        for node_idx, (_raw_node_id, prose) in enumerate(_nodes_of(item)):
            key = f"i{idx}n{node_idx}"
            key_to_item[key] = item_id
            nodes.append((key, prose))

    # #ASSUME: security: production (moderation/pipeline.py) always routes
    # Stage 1 calls through a PiiGuardedProvider, never the bare review
    # provider (see the matching comment on _observe_item above). This batched
    # per-band probe must match that topology so a guard regression would
    # show up in the sweep too, not just in the single-item probe path.
    # #VERIFY: guarded, not provider, is passed to run_safety_stage below.
    #
    # The band-wide union of child_names is deliberate, not an oversight.
    # Batching puts every item in this band into ONE prompt, so the egress
    # surface of that prompt is the union: if item B's child name appears
    # anywhere in the merged text, that name egresses, and a per-item guard
    # scoped to item A alone would let it through. Guarding the union is the
    # posture that matches what is actually sent. The cost is blast radius,
    # which the caller handles: one tripped guard is recorded against this
    # band rather than aborting the whole sweep (see _run_corpus_at_batch_size).
    guarded = PiiGuardedProvider(
        provider, forbidden=PiiContext(child_names=frozenset(forbidden_names))
    )
    findings: list[Finding] = await run_safety_stage(
        provider=guarded,
        nodes=nodes,
        age_band=band,
        max_tokens=_PROBE_MAX_TOKENS,
        batch_size=batch_size,
    )
    structural_count = 0
    for finding in findings:
        if finding.structural:
            structural_count += 1
            collapsed_ids = finding.node_ids or (
                (finding.node_id,) if finding.node_id is not None else ()
            )
            for key in collapsed_ids:
                item_id = key_to_item.get(key)
                if item_id is not None:
                    by_item[item_id].append(finding.verdict.value)
        elif finding.node_id is not None:
            item_id = key_to_item.get(finding.node_id)
            if item_id is not None:
                by_item[item_id].append(finding.verdict.value)
    return BandProbeResult(
        by_item=by_item,
        structural_count=structural_count,
        realized_chunk_sizes=_chunk_sizes(len(nodes), batch_size),
    )


@dataclass(frozen=True, slots=True)
class SweepSizeReport:
    """One requested batch size's full-corpus run.

    Attributes:
        batch_size: The ``review_batch_size`` used for this run.
        report: The classified per-item outcomes, same shape as a
            :meth:`run_corpus` result.
        call_count: Total review-provider calls made during this run.
        structural_collapse_count: Number of structural (parse-failure or
            attribution-failure) findings ``run_safety_stage`` emitted across
            every Stage-1 call at this size. This is the batching failure
            mode the design doc's #VERIFY calls out; it is not exclusive to
            ``batch_size > 1``, since a single-node parse failure collapses
            the same way (production has observed ``verdict_parse_failed`` at
            ``batch_size == 1`` too).
        realized_chunk_sizes: Every node count actually sent in a Stage-1
            call during this run, sorted descending. ``batch_size`` is what was
            REQUESTED; this is what was MEASURED. They diverge whenever a band
            holds fewer nodes than ``batch_size``, so reading the requested
            size as evidence that a batch that large was exercised is wrong
            unless ``max(realized_chunk_sizes) == batch_size``.
    """

    batch_size: int
    report: CorpusReport
    call_count: int
    structural_collapse_count: int
    realized_chunk_sizes: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class SweepReport:
    """Full Gate 3 batch-size recall-comparison sweep result.

    Attributes:
        sizes: One :class:`SweepSizeReport` per requested batch size, in the
            order requested.
    """

    sizes: tuple[SweepSizeReport, ...]

    @property
    def baseline(self) -> SweepSizeReport:
        """The comparison baseline: batch_size 1 if requested, else the first size."""
        for size_report in self.sizes:
            if size_report.batch_size == 1:
                return size_report
        return self.sizes[0]


async def _run_corpus_at_batch_size(
    items: Sequence[Mapping[str, object]],
    review_provider: ReviewProvider,
    *,
    review_provider_name: ReviewProviderName,
    batch_size: int,
) -> SweepSizeReport:
    """Run the full corpus once at one ``review_batch_size``.

    Stage-1 items are grouped per age band and batched (see
    ``_run_stage1_sweep_band``); every other item keeps the single-item probe
    from ``_observe_item``, unaffected by ``batch_size`` but still re-run so
    the reported call count reflects a genuine full-corpus run at this size.
    """
    counting_provider = _CountingProvider(inner=review_provider)
    stage1_items, _other_items = _partition_stage1(items)

    stage1_outcomes: dict[str, list[str]] = {}
    # Object identity, not corpus id: an item's stitching key is derived once,
    # here, and reused below. Re-deriving it from item["id"] at lookup time is
    # what let an id-less item score as an empty observed list regardless of
    # the reviewer's actual verdict, silently turning a control over-block into
    # a pass.
    key_by_item: dict[int, str] = {}
    structural_total = 0
    realized: list[int] = []
    for band, band_items in _group_by_age_band(stage1_items).items():
        for idx, band_item in enumerate(band_items):
            key_by_item[id(band_item)] = _sweep_item_key(band_item, band, idx)
        try:
            band_result = await _run_stage1_sweep_band(
                band, band_items, counting_provider, batch_size
            )
        except ValidationError as exc:
            # The band-wide PII guard tripped before egress, which is the guard
            # working. Record it against this band and keep going: aborting the
            # process would discard every other class's result for the whole
            # sweep, which is a far worse outcome than one unscored band.
            print(
                f"PII guard tripped for age band {band!r} at "
                f"batch_size={batch_size}: {exc}",
                file=sys.stderr,
            )
            for band_item in band_items:
                stage1_outcomes[key_by_item[id(band_item)]] = []
            continue
        stage1_outcomes.update(band_result.by_item)
        structural_total += band_result.structural_count
        realized.extend(band_result.realized_chunk_sizes)

    outcomes: list[ItemOutcome] = []
    for item in items:
        if not _as_bool(item.get("executable")):
            outcomes.append(classify_item(item, []))
            continue
        stitch_key = key_by_item.get(id(item))
        if stitch_key is not None:
            outcomes.append(classify_item(item, stage1_outcomes.get(stitch_key, [])))
            continue
        observation = await _observe_item(
            item, counting_provider, batch_size=batch_size
        )
        outcomes.append(
            classify_item(
                item,
                observation.verdicts,
                guard_raised=observation.guard_raised,
                findings=observation.findings,
            )
        )

    report = CorpusReport(
        review_provider=review_provider_name,
        outcomes=outcomes,
        per_class=_rollup(outcomes),
    )
    return SweepSizeReport(
        batch_size=batch_size,
        report=report,
        call_count=counting_provider.calls,
        structural_collapse_count=structural_total,
        realized_chunk_sizes=tuple(sorted(realized, reverse=True)),
    )


@dataclass(frozen=True, slots=True)
class SweepRegression:
    """One way a non-baseline batch size scored worse than the baseline.

    Attributes:
        batch_size: The size that regressed.
        kind: ``status``, ``severity``, ``catch_rate``, or ``structural``.
        subject: The corpus item id, or the taxonomy class for ``catch_rate``,
            or ``"<run>"`` for a whole-run ``structural`` regression.
        detail: Human-readable baseline-to-size description.
    """

    batch_size: int
    kind: str
    subject: str
    detail: str


def _outcomes_by_id(report: CorpusReport) -> dict[str, ItemOutcome]:
    """Index a report's item outcomes by corpus item id."""
    return {out.item_id: out for out in report.outcomes}


def _observed_max_rank(outcome: ItemOutcome) -> int:
    """Return the strongest verdict rank observed for an item (0 if none)."""
    return max((verdict_rank(v) for v in outcome.observed), default=0)


def _is_control(outcome: ItemOutcome) -> bool:
    """Return whether an outcome belongs to a benign control item."""
    return outcome.status in {"control_ok", "control_over_block"}


def _item_regressions(
    baseline_out: ItemOutcome, size_out: ItemOutcome, batch_size: int
) -> list[SweepRegression]:
    """Compare one item's baseline and at-size outcomes.

    Args:
        baseline_out: The item's outcome at the baseline batch size.
        size_out: The same item's outcome at ``batch_size``.
        batch_size: The non-baseline size being compared.

    Returns:
        Zero or more regressions for this item.
    """
    found: list[SweepRegression] = []
    if baseline_out.status == "caught" and size_out.status != "caught":
        found.append(
            SweepRegression(
                batch_size=batch_size,
                kind="status",
                subject=size_out.item_id,
                detail=f"caught at baseline, {size_out.status} at this size",
            )
        )
    if baseline_out.status == "control_ok" and size_out.status == "control_over_block":
        found.append(
            SweepRegression(
                batch_size=batch_size,
                kind="status",
                subject=size_out.item_id,
                detail="control passed at baseline, over-blocked at this size",
            )
        )
    # A severity downgrade that stays at or above expected_min is invisible to
    # the boolean is_caught scoring: block -> flag against expected_min="flag"
    # scores caught both times and a catch-rate delta of 0.0. It is still a real
    # softening of the moderation response under batching, so compare ranks
    # directly. Controls are excluded: for a benign item, LOWER is better.
    if not _is_control(size_out):
        baseline_rank = _observed_max_rank(baseline_out)
        size_rank = _observed_max_rank(size_out)
        if size_rank < baseline_rank:
            found.append(
                SweepRegression(
                    batch_size=batch_size,
                    kind="severity",
                    subject=size_out.item_id,
                    detail=(
                        f"strongest verdict softened "
                        f"{'/'.join(baseline_out.observed) or 'none'} -> "
                        f"{'/'.join(size_out.observed) or 'none'}"
                    ),
                )
            )
    return found


def _size_regressions(
    baseline: SweepSizeReport, size_report: SweepSizeReport
) -> list[SweepRegression]:
    """Return every way ``size_report`` scored worse than ``baseline``.

    Args:
        baseline: The baseline size's run.
        size_report: A non-baseline size's run over the same corpus.

    Returns:
        The regressions found, which is empty when the size is no worse than
        the baseline on any tracked dimension.
    """
    if size_report.batch_size == baseline.batch_size:
        return []
    found: list[SweepRegression] = []
    baseline_items = _outcomes_by_id(baseline.report)
    for size_out in size_report.report.outcomes:
        baseline_out = baseline_items.get(size_out.item_id)
        if baseline_out is None:
            continue
        found.extend(_item_regressions(baseline_out, size_out, size_report.batch_size))
    for tax, counts in size_report.report.per_class.items():
        rate = _catch_rate(counts)
        baseline_rate = _catch_rate(baseline.report.per_class.get(tax, {}))
        if rate is not None and baseline_rate is not None and rate < baseline_rate:
            found.append(
                SweepRegression(
                    batch_size=size_report.batch_size,
                    kind="catch_rate",
                    subject=tax,
                    detail=f"catch rate {baseline_rate:.0%} -> {rate:.0%}",
                )
            )
    if size_report.structural_collapse_count > baseline.structural_collapse_count:
        found.append(
            SweepRegression(
                batch_size=size_report.batch_size,
                kind="structural",
                subject="<run>",
                detail=(
                    f"structural-collapse findings "
                    f"{baseline.structural_collapse_count} -> "
                    f"{size_report.structural_collapse_count}"
                ),
            )
        )
    return found


def _sweep_regressions(sweep: SweepReport) -> list[SweepRegression]:
    """Return every regression any non-baseline size shows against the baseline.

    This, not :func:`_has_misses`, is what the sweep gates on.

    #CRITICAL: security: the sweep's question is "does batching lose recall
    relative to batch_size=1", and only a baseline-relative comparison answers
    it. Gating on absolute misses instead cannot: the corpus contains items
    (the E2/E3 prompt-injection pair) that are permanently missed at EVERY
    size, so an absolute gate is pinned to "fail" and its verdict carries no
    information about batching at all. A saturated gate is indistinguishable
    from a broken one.
    #VERIFY: tests/unit/test_adversarial_harness_batch_sweep.py asserts a
    sweep whose baseline already misses an item still exits 0-or-4 rather
    than 1 when no size regresses, and exits 1 when one does.
    """
    baseline = sweep.baseline
    found: list[SweepRegression] = []
    for size_report in sweep.sizes:
        found.extend(_size_regressions(baseline, size_report))
    return found


def _verdict_drift(sweep: SweepReport) -> list[dict[str, object]]:
    """Return every per-item verdict change vs. the baseline, in either direction.

    Informational only, and deliberately separate from
    :func:`_sweep_regressions`: hardening (a batched run blocking what the
    baseline only flagged) is drift worth seeing but is not a regression, and
    folding it into the gate would make a safety improvement fail the build.
    """
    baseline_items = _outcomes_by_id(sweep.baseline.report)
    drift: list[dict[str, object]] = []
    for size_report in sweep.sizes:
        if size_report.batch_size == sweep.baseline.batch_size:
            continue
        for size_out in size_report.report.outcomes:
            baseline_out = baseline_items.get(size_out.item_id)
            if baseline_out is None or baseline_out.observed == size_out.observed:
                continue
            drift.append(
                {
                    "batch_size": size_report.batch_size,
                    "item_id": size_out.item_id,
                    "baseline_observed": list(baseline_out.observed),
                    "observed": list(size_out.observed),
                }
            )
    return drift


async def run_sweep(
    items: Sequence[Mapping[str, object]],
    review_provider: ReviewProvider,
    *,
    review_provider_name: ReviewProviderName,
    batch_sizes: Sequence[int],
) -> SweepReport:
    """Run the full corpus once per requested batch size, sequentially.

    Sizes never run concurrently: a live-provider sweep's pacing and cost
    stay predictable, and each size's call count is attributable to it alone.

    Args:
        items: The corpus items (same shape as :meth:`run_corpus`).
        review_provider: The configured review provider.
        review_provider_name: The provider name (``mock`` marks non-evidence).
        batch_sizes: The ``review_batch_size`` values to compare, run in the
            order given.

    Returns:
        A :class:`SweepReport` with one :class:`SweepSizeReport` per
        requested size.
    """
    sizes: list[SweepSizeReport] = [
        await _run_corpus_at_batch_size(
            items,
            review_provider,
            review_provider_name=review_provider_name,
            batch_size=size,
        )
        for size in batch_sizes
    ]
    return SweepReport(sizes=tuple(sizes))


def _overall_catch_rate(report: CorpusReport) -> float | None:
    """Return the caught/(caught+missed) rate across every class in a report."""
    caught = sum(counts.get("caught", 0) for counts in report.per_class.values())
    missed = sum(counts.get("missed", 0) for counts in report.per_class.values())
    total = caught + missed
    if total == 0:
        return None
    return caught / total


def _sweep_classes(sweep: SweepReport) -> list[str]:
    """Return every taxonomy class observed anywhere in the sweep, sorted."""
    classes: set[str] = set()
    for size_report in sweep.sizes:
        classes.update(size_report.report.per_class)
    return sorted(classes)


def _sweep_rows(sweep: SweepReport) -> list[dict[str, object]]:
    """Build the (class, batch_size) comparison rows, plus an overall row set."""
    baseline = sweep.baseline
    rows: list[dict[str, object]] = []
    for tax in _sweep_classes(sweep):
        baseline_rate = _catch_rate(baseline.report.per_class.get(tax, {}))
        for size_report in sweep.sizes:
            rate = _catch_rate(size_report.report.per_class.get(tax, {}))
            delta = (
                rate - baseline_rate
                if rate is not None and baseline_rate is not None
                else None
            )
            rows.append(
                {
                    "class": tax,
                    "batch_size": size_report.batch_size,
                    "catch_rate": rate,
                    "delta_vs_baseline": delta,
                }
            )
    baseline_overall = _overall_catch_rate(baseline.report)
    for size_report in sweep.sizes:
        rate = _overall_catch_rate(size_report.report)
        delta = (
            rate - baseline_overall
            if rate is not None and baseline_overall is not None
            else None
        )
        rows.append(
            {
                "class": "overall",
                "batch_size": size_report.batch_size,
                "catch_rate": rate,
                "delta_vs_baseline": delta,
            }
        )
    return rows


def _print_sweep_preflight(
    items: Sequence[Mapping[str, object]], batch_sizes: Sequence[int]
) -> None:
    """Print corpus size and estimated call count per size before any call runs.

    Printed before the review provider is even built, so a live-provider run
    gives the operator a window to abort (Ctrl-C) before it starts spending
    tokens.
    """
    executable = sum(1 for it in items if _as_bool(it.get("executable")))
    estimates = estimate_call_counts(items, batch_sizes)
    print("=" * 64)
    print("Gate 3 batch-size recall-comparison sweep: preflight")
    print("=" * 64)
    print(f"Corpus items: {len(items)} ({executable} executable)")
    print("Estimated review-provider calls per batch size:")
    for size in batch_sizes:
        print(f"  batch_size={size}: {estimates[size]} calls")
    print("=" * 64)


def _print_sweep_report(sweep: SweepReport) -> None:
    """Print the human-readable comparison table and per-size cost summary."""
    baseline_size = sweep.baseline.batch_size
    print("=" * 64)
    print("Gate 3 batch-size recall-comparison sweep: results")
    print("=" * 64)
    print(f"Baseline batch_size: {baseline_size}")
    print()
    header = f"{'class':<10}{'batch_size':<12}{'catch_rate':<12}{'delta':<10}"
    print(header)
    print("-" * len(header))
    for row in _sweep_rows(sweep):
        rate = cast("float | None", row["catch_rate"])
        delta = cast("float | None", row["delta_vs_baseline"])
        rate_str = f"{rate:.0%}" if rate is not None else "N/A"
        if delta is not None:
            delta_str = f"{delta:+.0%}"
        elif row["batch_size"] == baseline_size:
            delta_str = "baseline"
        else:
            delta_str = "N/A"
        line = (
            f"{row['class']!s:<10}{row['batch_size']!s:<12}"
            f"{rate_str:<12}{delta_str:<10}"
        )
        print(line)
    print()
    print("Per-size call counts and structural-collapse (parse-failure) findings:")
    for size_report in sweep.sizes:
        realized = size_report.realized_chunk_sizes
        realized_str = ", ".join(str(n) for n in realized) if realized else "n/a"
        line = (
            f"  requested batch_size={size_report.batch_size}: "
            f"{size_report.call_count} calls, "
            f"{size_report.structural_collapse_count} structural-collapse finding(s), "
            f"realized Stage-1 chunk sizes: {realized_str}"
        )
        print(line)
        if realized and max(realized) < size_report.batch_size:
            print(
                f"    NOTE: no chunk reached {size_report.batch_size} nodes "
                f"(largest was {max(realized)}); this corpus cannot exercise "
                f"a batch that large."
            )
    print()
    regressions = _sweep_regressions(sweep)
    if regressions:
        print(f"REGRESSIONS vs. batch_size={baseline_size} ({len(regressions)}):")
        for reg in regressions:
            print(
                f"  [{reg.kind}] batch_size={reg.batch_size} "
                f"{reg.subject}: {reg.detail}"
            )
    else:
        print(f"No regressions vs. batch_size={baseline_size}.")
    drift = _verdict_drift(sweep)
    if drift:
        print()
        print(f"Verdict drift vs. baseline ({len(drift)}, informational):")
        for row in drift:
            before = cast("list[str]", row["baseline_observed"])
            after = cast("list[str]", row["observed"])
            print(
                f"  batch_size={row['batch_size']} {row['item_id']}: "
                f"{'/'.join(before) or 'none'} -> {'/'.join(after) or 'none'}"
            )
    if _has_misses(sweep.baseline.report):
        print()
        print(
            f"NOTE: the baseline (batch_size={baseline_size}) itself has "
            "misses or control over-blocks. Those are pre-existing recall gaps, "
            "not batching regressions; this sweep does not gate on them."
        )
    print("=" * 64)


def _sweep_to_json(sweep: SweepReport) -> dict[str, object]:
    """Build the machine-readable ``--out`` payload for a sweep run."""
    regressions = _sweep_regressions(sweep)
    return {
        "baseline_batch_size": sweep.baseline.batch_size,
        "baseline_has_misses": _has_misses(sweep.baseline.report),
        "rows": _sweep_rows(sweep),
        "regressions": [
            {
                "batch_size": reg.batch_size,
                "kind": reg.kind,
                "subject": reg.subject,
                "detail": reg.detail,
            }
            for reg in regressions
        ],
        "verdict_drift": _verdict_drift(sweep),
        "sizes": [
            {
                "batch_size": sr.batch_size,
                "realized_chunk_sizes": list(sr.realized_chunk_sizes),
                "max_realized_chunk_size": (
                    max(sr.realized_chunk_sizes) if sr.realized_chunk_sizes else None
                ),
                "call_count": sr.call_count,
                "structural_collapse_count": sr.structural_collapse_count,
                "per_class": sr.report.per_class,
                "catch_rate": {
                    tax: _catch_rate(counts)
                    for tax, counts in sr.report.per_class.items()
                },
                "overall_catch_rate": _overall_catch_rate(sr.report),
                "items": [
                    {
                        "id": out.item_id,
                        "taxonomy_class": out.taxonomy_class,
                        "status": out.status,
                        "expected": out.expected,
                        "observed": list(out.observed),
                        "note": out.note,
                    }
                    for out in sr.report.outcomes
                ],
            }
            for sr in sweep.sizes
        ],
    }


def _write_sweep_results(out_path: Path, sweep: SweepReport) -> None:
    """Write the sweep results as JSON (rows plus full per-size detail).

    Args:
        out_path: Destination path; parent directories are created.
        sweep: The sweep report to serialize.

    Raises:
        SystemExit: Exit code 2 if the artifact cannot be written.

    #ASSUME: data integrity: a sweep costs real review-provider calls, so a
    write failure must be loud. Letting an OSError escape as a traceback after
    the run completed would discard the evidence and give no actionable
    message; exiting 2 with the path and errno says what to fix.
    #VERIFY: covered by the unwritable-out-path test in
    tests/unit/test_adversarial_harness_batch_sweep.py.
    """
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(_sweep_to_json(sweep), indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"Error writing sweep results to {out_path}: {exc}", file=sys.stderr)
        sys.exit(2)


def _load_items(corpus_path: Path) -> list[dict[str, object]]:
    """Load the corpus items array from the corpus JSON file.

    Args:
        corpus_path: Path to the corpus JSON.

    Returns:
        The list of item dicts.

    Raises:
        SystemExit: If the file cannot be read or parsed, has no items array, or
            any item is missing a non-empty unique string ``id``.

    #ASSUME: data integrity: every item's ``id`` is a non-empty string unique
    within the corpus. The sweep stitches per-item Stage-1 verdicts back onto
    corpus items by id; a blank or duplicated id would silently attribute one
    item's verdict to another, or score an item against an empty verdict list,
    and an empty verdict list reads as "no finding" (a pass) for an adversarial
    item. Validating at load makes that unrepresentable rather than a silent
    mis-score in a child-safety gate.
    #VERIFY: covered by the blank-id and duplicate-id cases in
    tests/unit/test_adversarial_harness_batch_sweep.py.
    """
    try:
        raw_text = corpus_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error reading corpus file: {exc}", file=sys.stderr)
        sys.exit(2)
    try:
        parsed: object = json.loads(raw_text)  # pyright: ignore[reportAny]
    except json.JSONDecodeError as exc:
        print(f"Error parsing corpus JSON: {exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(parsed, dict):
        print(
            "Error: corpus must be a JSON object with an 'items' array.",
            file=sys.stderr,
        )
        sys.exit(2)
    corpus: dict[str, object] = parsed  # pyright: ignore[reportUnknownVariableType,reportAssignmentType]
    raw_items = corpus.get("items")
    if not isinstance(raw_items, list):
        print("Error: corpus 'items' must be an array.", file=sys.stderr)
        sys.exit(2)
    items = [
        cast("dict[str, object]", entry)
        for entry in raw_items  # pyright: ignore[reportUnknownVariableType]
        if isinstance(entry, dict)
    ]
    _validate_item_ids(items)
    return items


def _validate_item_ids(items: Sequence[Mapping[str, object]]) -> None:
    """Exit 2 unless every item carries a non-empty ``id`` unique in the corpus.

    Args:
        items: The loaded corpus items.

    Raises:
        SystemExit: Exit code 2 on the first blank or duplicated id, reporting
            every offending position so one run fixes the whole file.
    """
    blank: list[int] = []
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for idx, item in enumerate(items):
        raw_id = item.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            blank.append(idx)
            continue
        if raw_id in seen:
            duplicates.append(raw_id)
        else:
            seen[raw_id] = idx
    if not blank and not duplicates:
        return
    problems: list[str] = []
    if blank:
        positions = ", ".join(str(i) for i in blank)
        problems.append(f"missing or blank 'id' at item index/indices {positions}")
    if duplicates:
        problems.append(
            f"duplicate 'id' value(s): {', '.join(sorted(set(duplicates)))}"
        )
    print(f"Error: corpus item ids are invalid: {'; '.join(problems)}", file=sys.stderr)
    sys.exit(2)


def _load_env_file(env_path: Path) -> None:
    """Load ``KEY=VALUE`` lines from ``env_path`` into ``os.environ`` (no overwrite)."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _print_report(report: CorpusReport) -> None:
    """Print a human-readable summary of a corpus run to stdout."""
    print("=" * 64)
    print("Adversarial Safety Harness Summary")
    print("=" * 64)
    print(f"Review provider: {report.review_provider}")
    print(f"Review model: {report.review_model or 'n/a'}")
    print(
        "Backend pin: "
        + (", ".join(report.provider_order) if report.provider_order else "none")
    )
    print(
        "Sampling temperature: "
        + (
            "backend default (none sent)"
            if report.sampling_temperature is None
            else f"{report.sampling_temperature:g} (sent by the review leg)"
        )
    )
    if report.repeats > 1:
        print(
            f"Draws per in-scope item: {report.repeats} "
            f"(min per control: {report.min_draws_per_control})"
        )
    if not report.is_evidence:
        print()
        print("!!! MOCK RUN: NOT EVIDENCE !!!")
        print("The mock review provider returns fail-safe verdicts (Stage 1 -> FLAG,")
        print("soft stages -> PASS), so results are deterministic artifacts of that")
        print("fail-safe mapping, not real classifier discrimination.")
        print("Re-run with --review-provider openrouter for a real result.")
        print()
    print(f"Items: {len(report.outcomes)}")
    print()
    print("Per-class rollup (status counts and catch-rate):")
    for tax in sorted(report.per_class):
        counts = report.per_class[tax]
        rate = _catch_rate(counts)
        rate_str = f"{rate:.0%}" if rate is not None else "N/A"
        print(f"  {tax}: {counts} catch-rate={rate_str}")
    print()
    print("Per-item:")
    for out in report.outcomes:
        print(f"  [{out.item_id}] class={out.taxonomy_class} status={out.status}")
        print(f"      {out.note}")
    print("=" * 64)


def _finding_json(record: FindingRecord) -> dict[str, object]:
    """Serialize one archived finding."""
    return {
        "stage": record.stage,
        "source": record.source,
        "verdict": record.verdict,
        "category": record.category,
        "concern": record.concern,
        "severity": record.severity,
        "reason": record.reason,
        "node_id": record.node_id,
        "score": record.score,
        "is_fail_safe": record.is_fail_safe,
    }


def _propensity_json(outcome: ItemOutcome) -> dict[str, object]:
    """Summarize one repeatedly-scored item's adverse-draw rate.

    Reported as a rate with an interval rather than as a second accept/reject
    rule. At the draw counts this gate can afford, a two-arm rule is
    indeterminate for most outcomes, so an interval is the honest summary: it
    says how little a small k constrains the underlying propensity instead of
    implying a precision the draws do not carry.
    """
    draws = len(outcome.draws)
    adverse = sum(1 for draw in outcome.draws if draw.status in _ADVERSE_STATUSES)
    low, high = wilson_interval(adverse, draws)
    return {
        "draws": draws,
        "adverse": adverse,
        "rate": adverse / draws if draws else None,
        "wilson95": [low, high],
    }


def _item_json(outcome: ItemOutcome) -> dict[str, object]:
    """Serialize one item outcome, including its draws when it was repeated."""
    item: dict[str, object] = {
        "id": outcome.item_id,
        "taxonomy_class": outcome.taxonomy_class,
        "status": outcome.status,
        "expected": outcome.expected,
        "observed": list(outcome.observed),
        "note": outcome.note,
        "findings": [_finding_json(f) for f in outcome.findings],
    }
    if len(outcome.draws) > 1:
        item["draws"] = [
            {
                "index": draw.index,
                "status": draw.status,
                "observed": list(draw.observed),
                "findings": [_finding_json(f) for f in draw.findings],
            }
            for draw in outcome.draws
        ]
        item["propensity"] = _propensity_json(outcome)
    return item


def _sampling_note(report: CorpusReport) -> str:
    """Describe the sampling surface a run measured, derived from the record.

    Args:
        report: The run whose ``sampling_temperature`` and ``provider_order``
            the note describes.

    Returns:
        One sentence a reader of the archived artifact can rely on. It is
        computed from the recorded fields rather than written once, so it can
        never again assert that no temperature is sent while one is.
    """
    if report.sampling_temperature is None:
        temperature_clause = (
            "The review leg sent no temperature, top_p or seed, so sampling is "
            "left at the backend default"
        )
    else:
        temperature_clause = (
            f"The review leg sent temperature={report.sampling_temperature:g}, "
            "the same value the production reviewer runs at "
            "(moderation.review_provider.REVIEW_TEMPERATURE); no top_p or seed "
            "is sent"
        )
    routing_clause = (
        "the review model carries no entry in core.pricing.ENDPOINT_PINS, so "
        "backend routing is left to the provider"
        if not report.provider_order
        else "backend routing is pinned to "
        + ", ".join(report.provider_order)
        + " via core.pricing.ENDPOINT_PINS"
    )
    return (
        f"{temperature_clause}, and {routing_clause}. Both are the settings "
        "production runs at; the draw count absorbs whatever variance remains "
        "instead of suppressing it, because a configuration the deployed gate "
        "never uses would measure nothing about the gate."
    )


def _write_results(out_path: Path, report: CorpusReport) -> None:
    """Write the run results as JSON (metadata plus per-item outcomes).

    The ``measurement`` block records what the run actually used rather than
    what it was configured to use. ``min_draws_per_control`` is the number the
    S-7 register amendment keys its effective date on, so it is written where a
    reader can find it without recounting the items.
    """
    payload: dict[str, object] = {
        "review_provider": report.review_provider,
        "is_evidence": report.is_evidence,
        "measurement": {
            "review_model": report.review_model,
            "provider_order": list(report.provider_order),
            "repeats": report.repeats,
            "min_draws_per_control": report.min_draws_per_control,
            "temperature": report.sampling_temperature,
            "sampling": _sampling_note(report),
        },
        "per_class": report.per_class,
        "catch_rate": {
            tax: _catch_rate(counts) for tax, counts in report.per_class.items()
        },
        "items": [_item_json(out) for out in report.outcomes],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _has_misses(report: CorpusReport) -> bool:
    """Return whether any executable item missed or a control over-blocked."""
    return any(
        out.status in {"missed", "control_over_block"} for out in report.outcomes
    )


# #ASSUME: security: --corpus/--out/--env-file are documented (module
# docstring above, docs/planning/safety/adversarial-safety-evaluation.md) as
# always repo-relative (docs/planning/safety/*.json, .env), and this script
# has no test that exercises them against an out-of-repo tmp_path fixture
# (test_adversarial_harness.py only covers the pure scoring core); containing
# them to the repo root closes the CWE-23 gap (Snyk python/PT) without
# rejecting any documented or tested invocation.
# #VERIFY: if a future evaluation needs a corpus or output location outside
# the repo tree, this containment must be relaxed deliberately (and the
# rationale above updated), not silently bypassed.
def _resolve_within(path_arg: Path, *, label: str) -> Path:
    """Resolve a CLI-supplied path and require it stay within the repo root.

    Matches the containment idiom in ``generation/import_cli.py::_load_blob``:
    canonicalize with ``.resolve()``, then reject anything that escapes
    ``_REPO_ROOT`` via ``.relative_to()``.

    Args:
        path_arg: The raw ``Path`` from an argparse argument (``type=Path``).
        label: Human-readable argument name for the error message.

    Returns:
        The resolved, canonicalized Path, guaranteed to be under
        ``_REPO_ROOT``.

    Raises:
        SystemExit: If the resolved path escapes ``_REPO_ROOT``, exit code 2
            (matching this script's own load-error convention).
    """
    resolved = path_arg.resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        msg = (
            f"Error: {label} path {str(path_arg)!r} resolves to {resolved}, "
            f"which is outside the repo root {_REPO_ROOT}"
        )
        print(msg, file=sys.stderr)
        sys.exit(2)
    return resolved


def _parse_args() -> argparse.Namespace:
    """Build the argument parser and parse argv."""
    parser = argparse.ArgumentParser(
        description=(
            "Adversarial safety harness. Feeds the adversarial corpus to the "
            "moderation stages and reports a per-class catch-rate. Mock runs are "
            "wiring checks only, never evidence."
        )
    )
    parser.add_argument(
        "--corpus",
        required=True,
        type=Path,
        help="Path to the adversarial corpus JSON.",
    )
    parser.add_argument(
        "--review-provider",
        default="mock",
        choices=("mock", "openrouter"),
        help=(
            "Review provider for the LLM stages (default: mock, not evidence). "
            "A live provider also needs the Stage-0 classifier credential "
            "OPENAI_API_KEY in the environment or --env-file."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write the results JSON.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Dotenv file to source for live providers (default: .env).",
    )
    parser.add_argument(
        "--batch-size",
        action="append",
        type=int,
        dest="batch_sizes",
        default=None,
        metavar="N",
        help=(
            "Repeatable. review_batch_size value(s) to compare over the corpus, "
            "e.g. --batch-size 1 --batch-size 4 --batch-size 8. Omitting this "
            "flag keeps the classic single-run mode at batch size 1 (default, "
            "byte-compatible output). Giving it enables the Gate 3 batch-size "
            "recall-comparison sweep instead."
        ),
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        metavar="K",
        help=(
            "Draws to take per negative control and per class-A positive, so "
            "each is scored on the majority of K rather than on one sample of "
            "a stochastic reviewer. Must be 1 or an odd number of at least 3. "
            "Omitting it keeps the classic single-draw run (default). The "
            "recurring gate sets its own draw count in "
            "tests/llm_eval/test_adversarial_safety_eval.py; this flag is for "
            "diagnostic runs."
        ),
    )
    return parser.parse_args()


def _build_review_provider_for_cli(
    provider_name: str,
) -> tuple[ReviewProvider, ReviewProviderName, int, str | None]:
    """Build ``Settings`` and the review provider for a CLI invocation.

    Shared by the single-run and sweep code paths so the mock-review escape
    hatch below is applied identically in both.

    Args:
        provider_name: The raw ``--review-provider`` CLI value.

    Returns:
        ``(review_provider, provider_name, review_batch_size, review_model)``.
        The name is narrowed to the harness's own ``ReviewProviderName``
        literal. The batch size is the resolved ``Settings.review_batch_size``
        (env-overridable), so the classic run can probe at production's
        configuration rather than at a hard-coded 1. The model is the id the
        review leg resolved to, or ``None`` for the mock backend, which has no
        configurable model.

    Raises:
        ProjectBaseError: If settings validation or provider construction
            fails (for example a missing live-provider credential).
    """
    # #ASSUME: external-resources: the mock provider is this harness's
    # documented default (a deliberate non-evidence run per the "Honesty
    # guardrail" module docstring; CorpusReport.is_evidence and the sweep's
    # mock check both gate on review_provider != "mock" downstream). Without
    # the escape hatch, core/config.py's _require_real_reviewer_outside_local
    # would refuse to boot Settings whenever the invoking shell's ENVIRONMENT
    # happens to be "staging"/"production" (e.g. a shell also configured for
    # a live-provider run), even though this harness never claims the mock
    # run is a real safety evaluation.
    # #VERIFY: only set for provider_name == "mock"; a live-provider run
    # (openrouter) is unaffected and still requires a real
    # environment=local or a genuinely configured non-mock backend.
    settings = Settings.model_validate(
        {
            "review_provider": provider_name,
            "allow_mock_review": provider_name == "mock",
        }
    )
    review_provider, _independent = build_review_provider(
        settings, generator_provider=None, generator_model=None
    )
    # #ASSUME: data-integrity: read back from the same resolved ``Settings``
    # that built the provider, never from a constant or a ruling. A ruling
    # about which model should review is not evidence about which one did, and
    # an artifact that records the wrong id is worse than one recording none.
    # #VERIFY: build_review_provider reads settings.review_openrouter_model for
    # the openrouter backend; this reads the same field off the same instance.
    review_model = (
        settings.review_openrouter_model if provider_name == "openrouter" else None
    )
    return (
        review_provider,
        cast("ReviewProviderName", provider_name),
        settings.review_batch_size,
        review_model,
    )


def _review_batch_size_bounds() -> tuple[int, int]:
    """Return ``Settings.review_batch_size``'s (min, max) read from the model.

    Returns:
        The field's ``ge``/``le`` constraints, falling back to ``(1, 50)`` if
        either is absent.

    #ASSUME: data integrity: the CLI's accepted range must be the SAME range
    production accepts. Hard-coding 1-50 here duplicated the constraint, so
    widening the field would leave this validator silently rejecting values
    production would take. Reading the constraint off the field makes the two
    impossible to drift apart.
    #VERIFY: tests/unit/test_adversarial_harness_batch_sweep.py asserts this
    matches the Field(ge=..., le=...) declared in core/config.py.
    """
    # annotated_types.Ge/Le instances; typed as object so the getattr probes
    # below are checked rather than silently Any.
    metadata: list[object] = list(Settings.model_fields["review_batch_size"].metadata)
    low: int | None = None
    high: int | None = None
    for meta in metadata:
        ge: object = getattr(meta, "ge", None)
        le: object = getattr(meta, "le", None)
        if isinstance(ge, int):
            low = ge
        if isinstance(le, int):
            high = le
    return (low if low is not None else 1, high if high is not None else 50)


def _validate_batch_sizes(batch_sizes: Sequence[int]) -> None:
    """Exit 2 unless every requested size is in range and appears once.

    Args:
        batch_sizes: The requested ``--batch-size`` values, in order.

    Raises:
        SystemExit: Exit code 2 on an out-of-range or repeated size. A repeat
            is rejected rather than deduplicated because it would spend a full
            extra corpus run of real review-provider calls to produce a
            duplicate column.
    """
    low, high = _review_batch_size_bounds()
    for size in batch_sizes:
        if not low <= size <= high:
            msg = (
                f"Error: --batch-size {size} is outside the supported range "
                f"{low}-{high} (Settings.review_batch_size constraints)."
            )
            print(msg, file=sys.stderr)
            sys.exit(2)
    seen: set[int] = set()
    repeated: set[int] = set()
    for size in batch_sizes:
        if size in seen:
            repeated.add(size)
        seen.add(size)
    if repeated:
        print(
            "Error: --batch-size values must be distinct; repeated: "
            f"{', '.join(str(s) for s in sorted(repeated))}.",
            file=sys.stderr,
        )
        sys.exit(2)


def _run_sweep_cli(
    items: list[dict[str, object]],
    provider_name: str,
    out_path: Path | None,
    batch_sizes: list[int],
) -> None:
    """Sweep-mode CLI body: preflight log, run, report, and exit.

    Exit codes:
        0: no size regressed against the baseline, and the baseline is clean.
        1: at least one non-baseline size regressed against the baseline. This
           is the only code that means "batching lost recall".
        2: a batch size was invalid, the corpus was unusable, the provider
           could not be built, or the ``--out`` artifact could not be written.
        3: a non-evidence (mock) run.
        4: no batching regression, but the baseline itself has misses or
           control over-blocks. Pre-existing recall gaps, distinct from a
           batching regression so the two cannot be confused.

    Args:
        items: The loaded corpus items.
        provider_name: The raw ``--review-provider`` CLI value.
        out_path: Optional resolved ``--out`` path for the JSON results.
        batch_sizes: The requested ``review_batch_size`` values, in order.
    """
    _validate_batch_sizes(batch_sizes)

    _print_sweep_preflight(items, batch_sizes)

    try:
        review_provider, resolved_name, _, _model = _build_review_provider_for_cli(
            provider_name
        )
        sweep = asyncio.run(
            run_sweep(
                items,
                review_provider,
                review_provider_name=resolved_name,
                batch_sizes=batch_sizes,
            )
        )
    except ProjectBaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    is_evidence = resolved_name != "mock"
    if not is_evidence:
        print()
        print("!!! MOCK RUN: NOT EVIDENCE !!!")
        print("Every size's Stage-1 calls hit the mock provider's fail-safe")
        print("mapping, so this comparison measures nothing about real")
        print("classifier discrimination. Re-run with --review-provider")
        print("openrouter for a real recall comparison.")
        print()

    _print_sweep_report(sweep)
    if out_path is not None:
        _write_sweep_results(out_path, sweep)
        print(f"Wrote sweep results to {out_path}")

    if not is_evidence:
        sys.exit(3)
    if _sweep_regressions(sweep):
        sys.exit(1)
    sys.exit(4 if _has_misses(sweep.baseline.report) else 0)


def main() -> None:
    """CLI entry point.

    Loads the corpus, builds the review provider, runs the corpus, prints and
    optionally writes results. Exits 0 only for an evidence run with no misses and
    no control over-blocks; exits 1 on a miss; exits 2 if the settings or review
    provider could not be built (for example a missing live-provider credential);
    exits 3 for a non-evidence mock run.

    When ``--batch-size`` is given one or more times, delegates to the Gate 3
    batch-size recall-comparison sweep (``_run_sweep_cli``) instead of the
    single classic run.

    #CRITICAL: security: the no-flag path now probes at the resolved
    ``Settings.review_batch_size`` rather than a hard-coded 1. This is a
    deliberate behavior change: a recurring safety gate that measures a
    topology production stopped using constrains nothing. The probe's printed
    batch size makes the measured configuration explicit in every run's output
    so a reader never has to assume it.
    #VERIFY: the printed ``review_batch_size=`` line above the results, and
    tests/llm_eval/test_adversarial_safety_eval.py passing the same value.
    """
    args = _parse_args()
    corpus_path = _resolve_within(cast("Path", args.corpus), label="--corpus")
    provider_name: str = str(args.review_provider)  # pyright: ignore[reportAny]
    out_arg = cast("Path | None", args.out)
    out_path: Path | None = (
        _resolve_within(out_arg, label="--out") if out_arg is not None else None
    )
    env_path = _resolve_within(cast("Path", args.env_file), label="--env-file")
    batch_sizes = cast("list[int] | None", args.batch_sizes)
    repeats = int(cast("int", args.repeats))

    items = _load_items(corpus_path)

    if provider_name != "mock":
        _load_env_file(env_path)

    if batch_sizes:
        _run_sweep_cli(items, provider_name, out_path, batch_sizes)
        return

    try:
        review_provider, resolved_name, prod_batch_size, review_model = (
            _build_review_provider_for_cli(provider_name)
        )
        provider_order = (
            endpoint_pin_for(resolved_name, review_model)
            if review_model is not None
            else ()
        )
        print(f"Probing Stage 1 at review_batch_size={prod_batch_size}.")
        if repeats > 1:
            print(
                f"Scoring negative controls and class-A positives on "
                f"{repeats} draws each (majority rule)."
            )
        report = asyncio.run(
            run_corpus(
                items,
                review_provider,
                review_provider_name=resolved_name,
                batch_size=prod_batch_size,
                repeats=repeats,
                review_model=review_model,
                provider_order=provider_order,
            )
        )
    except ProjectBaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    _print_report(report)
    if out_path is not None:
        _write_results(out_path, report)
        print(f"Wrote results to {out_path}")

    if not report.is_evidence:
        sys.exit(3)
    sys.exit(1 if _has_misses(report) else 0)


if __name__ == "__main__":
    main()
