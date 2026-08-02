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
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ProjectBaseError, ValidationError
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

    from cyo_adventure.moderation.report import Finding

__all__ = [
    "CorpusReport",
    "ItemOutcome",
    "SweepReport",
    "SweepSizeReport",
    "classify_item",
    "estimate_call_counts",
    "is_caught",
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
ReviewProviderName = Literal["mock", "openrouter", "ollama"]

_PROBE_MAX_TOKENS = 1024


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
class ItemOutcome:
    """The classified result for one corpus item.

    Attributes:
        item_id: The corpus item id.
        taxonomy_class: The attack class (``A``-``F``).
        status: One of ``caught``, ``missed``, ``gap``, ``skipped``,
            ``control_ok``, ``control_over_block``.
        expected: The expected outcome string (min verdict, or ``raise_before_egress``).
        observed: The observed verdicts (empty for guard/skip items).
        note: A short human-readable explanation of the status.
    """

    item_id: str
    taxonomy_class: str
    status: ItemStatus
    expected: str
    observed: tuple[str, ...]
    note: str


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

    Returns:
        The classified :class:`ItemOutcome`.
    """
    item_id = _as_str(item.get("id"))
    tax = _as_str(item.get("taxonomy_class"))
    observed = tuple(observed_verdicts)
    expected = _as_str(item.get("expected_min_verdict")) or _as_str(
        item.get("expected")
    )

    if not _as_bool(item.get("executable")):
        target = _as_str(item.get("target")) or "call graph"
        note = f"not executable by the passage harness (target: {target})"
        return ItemOutcome(item_id, tax, "skipped", expected, observed, note)

    if _as_str(item.get("target")) == "pii_guard":
        caught = bool(guard_raised)
        note = (
            "PII guard raised before egress"
            if caught
            else "PII guard did NOT raise: real-child data would egress"
        )
        status = "caught" if caught else "missed"
        return ItemOutcome(item_id, tax, status, "raise_before_egress", observed, note)

    if _as_bool(item.get("known_gap")):
        gated = is_caught("flag", observed)
        note = (
            "per-node gate DID gate this path (better than the documented gap)"
            if gated
            else "per-node gate did not gate the assembled path (expected per Finding 4)"
        )
        return ItemOutcome(item_id, tax, "gap", expected, observed, note)

    if _as_bool(item.get("negative_control")):
        over_blocked = is_caught("flag", observed)
        status = "control_over_block" if over_blocked else "control_ok"
        note = (
            "clean passage was flagged: the gate over-blocks"
            if over_blocked
            else "clean passage passed as expected"
        )
        return ItemOutcome(item_id, tax, status, expected, observed, note)

    caught = is_caught(expected, observed)
    note = (
        f"observed {list(observed)} reached expected minimum {expected!r}"
        if caught
        else f"observed {list(observed)} below expected minimum {expected!r}"
    )
    return ItemOutcome(
        item_id, tax, "caught" if caught else "missed", expected, observed, note
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
    item: Mapping[str, object], review_provider: ReviewProvider
) -> tuple[list[str], bool | None]:
    """Run the appropriate moderation probe for one item.

    Args:
        item: The corpus item.
        review_provider: The configured review provider (LLM stages).

    Returns:
        ``(observed_verdicts, guard_raised)``. ``guard_raised`` is ``None`` for
        non-PII items, and a bool for PII-guard items.
    """
    target = _as_str(item.get("target"))
    guarded = PiiGuardedProvider(review_provider, forbidden=_pii_context_of(item))
    if target == "pii_guard":
        passage = _as_str(item.get("passage"))
        try:
            _ = await guarded.complete(system="", prompt=passage, max_tokens=16)
        except ValidationError:
            return [], True
        return [], False

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
    return [f.verdict.value for f in findings], None


@dataclass(frozen=True, slots=True)
class CorpusReport:
    """Aggregate result of an adversarial corpus run.

    Attributes:
        review_provider: The provider name the run used.
        outcomes: One :class:`ItemOutcome` per corpus item.
        per_class: ``{class: {status: count}}`` rollup.

    ``is_evidence`` is deliberately not a stored field: this harness's entire
    purpose is to never let a mock run masquerade as evidence, so that fact is
    derived from ``review_provider`` rather than an independently-settable value
    that could drift out of sync with it.
    """

    review_provider: ReviewProviderName
    outcomes: list[ItemOutcome]
    per_class: dict[str, dict[str, int]]

    @property
    def is_evidence(self) -> bool:
        """``False`` for a mock run (fail-safe artifacts, not a measure)."""
        return self.review_provider != "mock"


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


async def run_corpus(
    items: Sequence[Mapping[str, object]],
    review_provider: ReviewProvider,
    *,
    review_provider_name: ReviewProviderName,
) -> CorpusReport:
    """Run every corpus item through its probe and classify the outcome.

    Args:
        items: The corpus items.
        review_provider: The configured review provider.
        review_provider_name: The provider name (``mock`` marks a non-evidence run).

    Returns:
        A :class:`CorpusReport`. ``is_evidence`` is ``False`` for a mock run.
    """
    outcomes: list[ItemOutcome] = []
    for item in items:
        if not _as_bool(item.get("executable")):
            outcomes.append(classify_item(item, []))
            continue
        observed, guard_raised = await _observe_item(item, review_provider)
        outcomes.append(classify_item(item, observed, guard_raised=guard_raised))
    return CorpusReport(
        review_provider=review_provider_name,
        outcomes=outcomes,
        per_class=_rollup(outcomes),
    )


# ---------------------------------------------------------------------------
# Gate 3 batch-size recall-comparison sweep (design doc
# moderation-review-redesign-2026-07-28.md section 2.2 item 2's #VERIFY: run
# both single-node and batched review over the adversarial corpus and compare
# recall before enabling review_batch_size > 1 by default).
#
# ``run_corpus`` above is left completely untouched by everything below: the
# no-flag CLI path keeps calling it directly, so the classic single-run mode
# stays byte-compatible and tests/llm_eval/test_adversarial_safety_eval.py
# (which imports run_corpus directly) is unaffected.
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
    ``batch_size``; every other executable item issues exactly one call per
    size regardless, since the sweep re-runs the full corpus at each size
    (see ``_run_corpus_at_batch_size``). Pure and network-free: used for the
    preflight log printed before any provider call is made.

    Args:
        items: The corpus items.
        batch_sizes: The requested ``review_batch_size`` values.

    Returns:
        ``{batch_size: estimated_call_count}``.
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

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Delegate to the wrapped provider, incrementing ``calls`` first."""
        self.calls += 1
        return await self.inner.complete(
            system=system, prompt=prompt, max_tokens=max_tokens
        )


async def _run_stage1_sweep_band(
    band: str,
    band_items: Sequence[Mapping[str, object]],
    provider: ReviewProvider,
    batch_size: int,
) -> tuple[dict[str, list[str]], int]:
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
        ``(item_id -> observed verdict strings, structural_finding_count)``.
        ``structural_finding_count`` is the number of collapsed
        parse-failure/attribution-failure findings ``run_safety_stage``
        emitted for this band (design doc section 2.3): the batching failure
        mode this sweep exists to measure.
    """
    key_to_item: dict[str, str] = {}
    nodes: list[tuple[str, str]] = []
    by_item: dict[str, list[str]] = {}
    forbidden_names: set[str] = set()
    for idx, item in enumerate(band_items):
        item_id = _as_str(item.get("id")) or f"<band-{band}-item-{idx}>"
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
    return by_item, structural_count


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
    """

    batch_size: int
    report: CorpusReport
    call_count: int
    structural_collapse_count: int


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
    structural_total = 0
    for band, band_items in _group_by_age_band(stage1_items).items():
        by_item, structural_count = await _run_stage1_sweep_band(
            band, band_items, counting_provider, batch_size
        )
        stage1_outcomes.update(by_item)
        structural_total += structural_count

    stage1_ids = {_as_str(it.get("id")) for it in stage1_items}
    outcomes: list[ItemOutcome] = []
    for item in items:
        if not _as_bool(item.get("executable")):
            outcomes.append(classify_item(item, []))
            continue
        item_id = _as_str(item.get("id"))
        if item_id in stage1_ids:
            outcomes.append(classify_item(item, stage1_outcomes.get(item_id, [])))
            continue
        observed, guard_raised = await _observe_item(item, counting_provider)
        outcomes.append(classify_item(item, observed, guard_raised=guard_raised))

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
    )


def _sweep_has_misses(sweep: SweepReport) -> bool:
    """Return whether any requested size failed the harness's existing thresholds."""
    return any(_has_misses(sr.report) for sr in sweep.sizes)


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
        line = (
            f"  batch_size={size_report.batch_size}: "
            f"{size_report.call_count} calls, "
            f"{size_report.structural_collapse_count} structural-collapse finding(s)"
        )
        print(line)
    print("=" * 64)


def _sweep_to_json(sweep: SweepReport) -> dict[str, object]:
    """Build the machine-readable ``--out`` payload for a sweep run."""
    return {
        "baseline_batch_size": sweep.baseline.batch_size,
        "rows": _sweep_rows(sweep),
        "sizes": [
            {
                "batch_size": sr.batch_size,
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
    """Write the sweep results as JSON (rows plus full per-size detail)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(_sweep_to_json(sweep), indent=2) + "\n", encoding="utf-8"
    )


def _load_items(corpus_path: Path) -> list[dict[str, object]]:
    """Load the corpus items array from the corpus JSON file.

    Args:
        corpus_path: Path to the corpus JSON.

    Returns:
        The list of item dicts.

    Raises:
        SystemExit: If the file cannot be read or parsed, or has no items array.
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
    return [
        cast("dict[str, object]", entry)
        for entry in raw_items  # pyright: ignore[reportUnknownVariableType]
        if isinstance(entry, dict)
    ]


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
    if not report.is_evidence:
        print()
        print("!!! MOCK RUN: NOT EVIDENCE !!!")
        print("The mock review provider returns fail-safe verdicts (Stage 1 -> FLAG,")
        print("soft stages -> PASS), so results are deterministic artifacts of that")
        print("fail-safe mapping, not real classifier discrimination.")
        print("Re-run with --review-provider openrouter (or ollama) for a real result.")
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


def _write_results(out_path: Path, report: CorpusReport) -> None:
    """Write the run results as JSON (metadata plus per-item outcomes)."""
    payload: dict[str, object] = {
        "review_provider": report.review_provider,
        "is_evidence": report.is_evidence,
        "per_class": report.per_class,
        "catch_rate": {
            tax: _catch_rate(counts) for tax, counts in report.per_class.items()
        },
        "items": [
            {
                "id": out.item_id,
                "taxonomy_class": out.taxonomy_class,
                "status": out.status,
                "expected": out.expected,
                "observed": list(out.observed),
                "note": out.note,
            }
            for out in report.outcomes
        ],
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
        choices=("mock", "openrouter", "ollama"),
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
    return parser.parse_args()


def _build_review_provider_for_cli(
    provider_name: str,
) -> tuple[ReviewProvider, ReviewProviderName]:
    """Build ``Settings`` and the review provider for a CLI invocation.

    Shared by the single-run and sweep code paths so the mock-review escape
    hatch below is applied identically in both.

    Args:
        provider_name: The raw ``--review-provider`` CLI value.

    Returns:
        ``(review_provider, provider_name)``, the latter narrowed to the
        harness's own ``ReviewProviderName`` literal.

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
    # (openrouter/ollama) is unaffected and still requires a real
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
    return review_provider, cast("ReviewProviderName", provider_name)


def _run_sweep_cli(
    items: list[dict[str, object]],
    provider_name: str,
    out_path: Path | None,
    batch_sizes: list[int],
) -> None:
    """Sweep-mode CLI body: preflight log, run, report, and exit.

    Exit codes mirror ``main()``'s single-run semantics: 0 clean, 1 if any
    requested size missed the harness's existing per-class thresholds, 2 if
    a batch size is out of range or the provider could not be built, 3 for a
    non-evidence (mock) run.

    Args:
        items: The loaded corpus items.
        provider_name: The raw ``--review-provider`` CLI value.
        out_path: Optional resolved ``--out`` path for the JSON results.
        batch_sizes: The requested ``review_batch_size`` values, in order.
    """
    for size in batch_sizes:
        if not 1 <= size <= 50:
            msg = (
                f"Error: --batch-size {size} is outside the supported range "
                "1-50 (matches Settings.review_batch_size)."
            )
            print(msg, file=sys.stderr)
            sys.exit(2)

    _print_sweep_preflight(items, batch_sizes)

    try:
        review_provider, resolved_name = _build_review_provider_for_cli(provider_name)
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
        print("openrouter (or ollama) for a real recall comparison.")
        print()

    _print_sweep_report(sweep)
    if out_path is not None:
        _write_sweep_results(out_path, sweep)
        print(f"Wrote sweep results to {out_path}")

    if not is_evidence:
        sys.exit(3)
    sys.exit(1 if _sweep_has_misses(sweep) else 0)


def main() -> None:
    """CLI entry point.

    Loads the corpus, builds the review provider, runs the corpus, prints and
    optionally writes results. Exits 0 only for an evidence run with no misses and
    no control over-blocks; exits 1 on a miss; exits 2 if the settings or review
    provider could not be built (for example a missing live-provider credential);
    exits 3 for a non-evidence mock run.

    When ``--batch-size`` is given one or more times, delegates to the Gate 3
    batch-size recall-comparison sweep (``_run_sweep_cli``) instead of the
    single classic run; the no-flag path below is otherwise untouched, so it
    stays byte-compatible with every prior invocation.
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

    items = _load_items(corpus_path)

    if provider_name != "mock":
        _load_env_file(env_path)

    if batch_sizes:
        _run_sweep_cli(items, provider_name, out_path, batch_sizes)
        return

    try:
        review_provider, resolved_name = _build_review_provider_for_cli(provider_name)
        report = asyncio.run(
            run_corpus(
                items,
                review_provider,
                review_provider_name=resolved_name,
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
