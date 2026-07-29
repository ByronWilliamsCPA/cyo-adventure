"""Offline measurement glue for the sentinel re-insertion transform (plan 3.4).

The pure strip-all-then-reinsert transform lives in
`cyo_adventure.storybook.reinsertion` (ADR-023 Stage R Task R2 promoted it
out of this module so the production fill path, Task R3, can call the same
deterministic algorithm the offline measurement tooling proves out here).
This module keeps only what is specific to OFFLINE MEASUREMENT: wrapping one
`reinsert_storybook` call into a trial/report-shaped `ReinsertionResult`
(including the legacy fidelity proof described below), aggregating many
trials into `ReinsertionAggregate`, and rendering that aggregate as JSON or
markdown for `scripts/prototype_sentinel_reinsertion.py`.

**Why `round_trip_ok` needs its own glue here.** The domain package's
`verify_manifest` proves "does this document still match the manifest that
was derived FROM it" (at-rest corruption detection; trivially true
immediately after `reinsert_storybook` runs, since the manifest is scanned
straight off the document). That is not the same question this module's
`round_trip_ok` statistic answers, which is measurement-specific: "did this
reinsertion fully realize every token the ORIGINAL pre-fill bound skeleton
declared, allowing only for the sentence-start capitalization widening the
transform itself deliberately applies." Answering that needs the raw
`bound_skeleton` (never available to `verify_manifest`, and never persisted
alongside the production blob `manifest` accompanies), so `_fidelity_reference`
below reconstructs the same casing-tolerant reference `check_sentinel_integrity`
compares against, built from data `ReinsertionOutcome` already returns
(`document`, `token_outcomes`) plus the caller's own `bound_skeleton`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from cyo_adventure.storybook.reinsertion import (
    TokenOutcome,
    reinsert_storybook,
)
from cyo_adventure.storybook.sentinels import find_sentinels, wrap
from cyo_adventure.validator.sentinel_integrity import check_sentinel_integrity

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# The occurrence-multiplicity buckets `_multiplicity_bucket` sorts a
# reinsertable token's count into (plan 3.4 prototype: high multiplicity is a
# proxy for mis-target risk, since a common generic word used in more than a
# handful of unrelated senses is more likely to also collect a false-positive
# wrap somewhere in the same node).
_MULTIPLICITY_SINGLE = "1"
_MULTIPLICITY_FEW = "2-3"
_MULTIPLICITY_MANY = "4+"


@dataclass(frozen=True, slots=True)
class ReinsertionResult:
    """One `reinsert_sentinels` call's full result, report-shaped.

    Attributes:
        document: The finished, sentinel-reinserted document
            (`cyo_adventure.storybook.reinsertion.ReinsertionOutcome.document`).
        manifest: The derived at-rest sentinel manifest for `document`
            (`cyo_adventure.storybook.reinsertion.ReinsertionOutcome.manifest`).
        token_outcomes: One `TokenOutcome` per `(node, token)` pair the
            pre-fill bound skeleton expected, in a stable order (node id,
            then slot id, then value).
        reinsertion_clean: True only when `token_outcomes` is non-empty and
            every entry is `"reinsertable"`. An empty `token_outcomes` (a
            bound skeleton with no expected tokens at all) is deliberately
            NOT clean: there is nothing to prove re-insertion viable on, so
            treating it as a vacuous pass would silently inflate the
            clean-rate with non-data-points.
        round_trip_ok: Whether the reinsertion fully realized every token the
            original `bound_skeleton` declared, checked via
            `check_sentinel_integrity` against a reference patched (see
            `_fidelity_reference`) to allow the sentence-start
            capitalization widening `reinsert_storybook` itself applies. A
            token that stayed `not_found` still fails this check exactly as
            `check_sentinel_integrity` against the raw `bound_skeleton`
            would.
        sentence_start_hits: How many occurrences across the whole document
            were classified `"reinsertable"` only because a sentence-start
            capitalized variant of a lowercase-starting expected value was
            matched.
        plural_occurrences: How many `<value>s` occurrences were found but
            deliberately left unwrapped.
    """

    document: dict[str, object]
    manifest: dict[str, object]
    token_outcomes: tuple[TokenOutcome, ...]
    reinsertion_clean: bool
    round_trip_ok: bool
    sentence_start_hits: int
    plural_occurrences: int


@dataclass(frozen=True, slots=True)
class ReinsertionTrial:
    """One `reinsert_sentinels` result, tagged with which specimen/provider produced it.

    Mirrors `cyo_adventure.measurement.report.TrialRecord`'s shape for the
    sentinel-survival report, so the two CLIs read alike.

    Attributes:
        specimen_slug: The source skeleton slug the fill was run against.
        provider: The provider name the fill was produced by.
        result: The classified re-insertion outcome.
    """

    specimen_slug: str
    provider: str
    result: ReinsertionResult


@dataclass(frozen=True, slots=True)
class ReinsertionProviderStats:
    """Reinsertion-clean statistics for one provider.

    Attributes:
        provider: The provider name.
        total: Total trials aggregated for this provider.
        clean: Trials with `ReinsertionResult.reinsertion_clean` True.
        clean_rate: ``clean / total``.
    """

    provider: str
    total: int
    clean: int
    clean_rate: float


@dataclass(frozen=True, slots=True)
class ReinsertionAggregate:
    """The full aggregated re-insertion-viability report.

    Attributes:
        total_trials: Total trials aggregated.
        clean_trials: Trials with `reinsertion_clean` True.
        reinsertion_clean_rate: ``clean_trials / total_trials``.
        round_trip_ok_trials: Trials with `round_trip_ok` True.
        round_trip_ok_rate: ``round_trip_ok_trials / total_trials``.
        per_provider: Per-provider reinsertion-clean stats, sorted by
            provider name.
        outcome_histogram: Counts of every `(node, token)` pair's `status`
            across every trial, keyed by ``"reinsertable"`` /
            ``"not_found"``. Deliberately NOT keyed by the literal node id or
            token value: those are only unique within one specimen's own
            skeleton (two different stories both have a node called "n1"),
            so grouping by literal identity across trials would conflate
            unrelated nodes rather than measure the outcome distribution.
        multiplicity_histogram: Counts of every reinsertable token's
            `occurrence_count`, bucketed into ``"1"``, ``"2-3"``, ``"4+"``
            (a `not_found` token, count 0, is never bucketed here; it is
            already captured in `outcome_histogram`).
        sentence_start_hits: Sum of `ReinsertionResult.sentence_start_hits`
            across every trial: how many occurrence-level matches were only
            found via the sentence-start capitalization widening.
        plural_occurrences: Sum of `ReinsertionResult.plural_occurrences`
            across every trial: how many `<value>s` occurrences were seen
            but deliberately left unwrapped.
    """

    total_trials: int
    clean_trials: int
    reinsertion_clean_rate: float
    round_trip_ok_trials: int
    round_trip_ok_rate: float
    per_provider: tuple[ReinsertionProviderStats, ...]
    outcome_histogram: dict[str, int]
    multiplicity_histogram: dict[str, int]
    sentence_start_hits: int
    plural_occurrences: int


# ---------------------------------------------------------------------------
# The legacy fidelity proof: reinsertion against the ORIGINAL bound_skeleton.
# ---------------------------------------------------------------------------


def _reinsertable_variants(
    document: Mapping[str, object], node_id: str, slot_id: str
) -> frozenset[str]:
    """Return every distinct value string actually wrapped for `slot_id` in one node.

    Scans `document` itself (the finished, reinserted document), not any
    intermediate bookkeeping, so this reads the same ground truth
    `build_manifest` reads from.

    Args:
        document: The finished, reinserted document.
        node_id: The node to scan.
        slot_id: The slot id to filter to.

    Returns:
        frozenset[str]: Every distinct wrapped value string found for
            `slot_id` in that node's body and ending title combined; empty
            if the node is missing or has none.
    """
    nodes = document.get("nodes")
    if not isinstance(nodes, list):
        return frozenset()
    for raw_node in nodes:
        if not isinstance(raw_node, dict) or raw_node.get("id") != node_id:
            continue
        values: set[str] = set()
        body = raw_node.get("body")
        if isinstance(body, str):
            values.update(
                value for sid, value in find_sentinels(body) if sid == slot_id
            )
        ending = raw_node.get("ending")
        if isinstance(ending, dict):
            title = ending.get("title")
            if isinstance(title, str):
                values.update(
                    value for sid, value in find_sentinels(title) if sid == slot_id
                )
        return frozenset(values)
    return frozenset()


def _patch_node_reference(
    node: dict[str, object],
    slot_id: str,
    canonical_value: str,
    variants: frozenset[str],
) -> None:
    """Patch one raw reference node to declare every variant actually wrapped.

    `check_sentinel_integrity` expects a node's reference text to declare
    the exact set of sentinel tokens the corresponding document node's text
    contains. The sentence-start widening intentionally wraps a
    verbatim-cased variant of a token's declared value (e.g. ``The pup``
    where the bound skeleton declared ``the pup``); this patches a private,
    per-call deep copy of the bound skeleton (never the caller's own
    `bound_skeleton`) so it additionally declares any such variant, leaving
    every genuinely dropped or forged token's mismatch intact for
    `check_sentinel_integrity` to catch.

    A token whose only wrapped variant equals its declared canonical value
    (the ordinary, unwidened case) is left untouched: nothing to patch.

    Args:
        node: One node dict from the reference document (mutated in place).
        slot_id: The token's slot id.
        canonical_value: The token's declared canonical value.
        variants: Every distinct verbatim variant string actually wrapped
            for this token (see `_reinsertable_variants`).

    Returns:
        None. `node` is mutated in place.
    """
    if variants == frozenset((canonical_value,)):
        return
    canonical_token = wrap(slot_id, canonical_value)
    replacement = "".join(wrap(slot_id, variant) for variant in sorted(variants))

    body = node.get("body")
    if isinstance(body, str) and canonical_token in body:
        node["body"] = body.replace(canonical_token, replacement, 1)
    ending = node.get("ending")
    if isinstance(ending, dict):
        title = ending.get("title")
        if isinstance(title, str) and canonical_token in title:
            ending["title"] = title.replace(canonical_token, replacement, 1)


def _fidelity_reference(
    bound_skeleton: Mapping[str, object],
    document: Mapping[str, object],
    token_outcomes: tuple[TokenOutcome, ...],
) -> dict[str, object]:
    """Build the patched reference `round_trip_ok` compares `document` against.

    Starts from a deep copy of `bound_skeleton` (so every `"not_found"`
    token stays declared exactly as the pre-fill skeleton wrote it, which is
    what makes it correctly show up as ``"dropped"``), then patches in every
    `"reinsertable"` token's actually-wrapped variant(s) via
    `_patch_node_reference`.

    Args:
        bound_skeleton: The raw pre-fill bound skeleton.
        document: The finished, reinserted document.
        token_outcomes: `reinsert_storybook`'s per-token outcomes for this
            same `(bound_skeleton, document)` pair.

    Returns:
        dict[str, object]: The patched reference mapping.
    """
    reference = cast("dict[str, object]", copy.deepcopy(bound_skeleton))
    nodes_by_id: dict[str, dict[str, object]] = {}
    nodes = reference.get("nodes")
    if isinstance(nodes, list):
        for raw_node in nodes:
            if isinstance(raw_node, dict):
                node_id = raw_node.get("id")
                if isinstance(node_id, str):
                    nodes_by_id[node_id] = cast("dict[str, object]", raw_node)

    for outcome in token_outcomes:
        if outcome.status != "reinsertable":
            continue
        node = nodes_by_id.get(outcome.node_id)
        if node is None:
            continue
        variants = _reinsertable_variants(document, outcome.node_id, outcome.slot_id)
        _patch_node_reference(node, outcome.slot_id, outcome.value, variants)
    return reference


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def reinsert_sentinels(
    bound_skeleton: Mapping[str, object], filled_blob: Mapping[str, object]
) -> ReinsertionResult:
    """Run `reinsert_storybook` and wrap its outcome into a report-shaped result.

    Args:
        bound_skeleton: The pre-fill bound skeleton the fill was given (a
            `cyo_adventure.measurement.fixtures.Specimen`'s
            `bound_skeleton`).
        filled_blob: The fill's output document
            (`cyo_adventure.generation.orchestrator.GenerationOutcome.storybook`).

    Returns:
        ReinsertionResult: The finished document, its manifest, every
            `(node, token)` outcome, and the `reinsertion_clean` /
            `round_trip_ok` verdicts.
    """
    outcome = reinsert_storybook(bound_skeleton, filled_blob)

    reinsertion_clean = bool(outcome.token_outcomes) and all(
        token_outcome.status == "reinsertable"
        for token_outcome in outcome.token_outcomes
    )
    reference = _fidelity_reference(
        bound_skeleton, outcome.document, outcome.token_outcomes
    )
    round_trip_ok = check_sentinel_integrity(reference, outcome.document).ok

    return ReinsertionResult(
        document=outcome.document,
        manifest=outcome.manifest,
        token_outcomes=outcome.token_outcomes,
        reinsertion_clean=reinsertion_clean,
        round_trip_ok=round_trip_ok,
        sentence_start_hits=outcome.sentence_start_hits,
        plural_occurrences=outcome.plural_occurrences,
    )


# ---------------------------------------------------------------------------
# Aggregation across many trials
# ---------------------------------------------------------------------------


def _multiplicity_bucket(count: int) -> str:
    """Sort one reinsertable token's occurrence count into a multiplicity bucket.

    Args:
        count: A reinsertable token's `occurrence_count` (always >= 1; a
            `not_found` token, count 0, is never passed here).

    Returns:
        str: `_MULTIPLICITY_SINGLE` for exactly 1, `_MULTIPLICITY_FEW` for 2
            or 3, `_MULTIPLICITY_MANY` for 4 or more.

    Raises:
        ValueError: If `count` is not positive; a non-positive count has no
            defined bucket (it belongs in `outcome_histogram` as
            ``"not_found"`` instead).
    """
    if count < 1:
        msg = f"multiplicity bucket undefined for non-positive count: {count}"
        raise ValueError(msg)
    if count == 1:
        return _MULTIPLICITY_SINGLE
    if count <= 3:
        return _MULTIPLICITY_FEW
    return _MULTIPLICITY_MANY


def aggregate_reinsertion(trials: Sequence[ReinsertionTrial]) -> ReinsertionAggregate:
    """Aggregate a flat sequence of re-insertion trials into a full report.

    Args:
        trials: Every trial run, across every specimen and provider.

    Returns:
        ReinsertionAggregate: The aggregated clean rates, per-provider split,
            outcome histogram, and occurrence-multiplicity distribution.

    Raises:
        ValueError: If `trials` is empty; there is nothing to report on.
    """
    if not trials:
        msg = "cannot aggregate an empty reinsertion trial sequence"
        raise ValueError(msg)

    total_trials = len(trials)
    clean_trials = sum(1 for trial in trials if trial.result.reinsertion_clean)
    round_trip_ok_trials = sum(1 for trial in trials if trial.result.round_trip_ok)
    sentence_start_hits = sum(trial.result.sentence_start_hits for trial in trials)
    plural_occurrences = sum(trial.result.plural_occurrences for trial in trials)

    per_provider_totals: dict[str, int] = {}
    per_provider_clean: dict[str, int] = {}
    outcome_histogram: dict[str, int] = {}
    multiplicity_histogram: dict[str, int] = {}

    for trial in trials:
        per_provider_totals[trial.provider] = (
            per_provider_totals.get(trial.provider, 0) + 1
        )
        if trial.result.reinsertion_clean:
            per_provider_clean[trial.provider] = (
                per_provider_clean.get(trial.provider, 0) + 1
            )
        for outcome in trial.result.token_outcomes:
            outcome_histogram[outcome.status] = (
                outcome_histogram.get(outcome.status, 0) + 1
            )
            if outcome.status == "reinsertable":
                bucket = _multiplicity_bucket(outcome.occurrence_count)
                multiplicity_histogram[bucket] = (
                    multiplicity_histogram.get(bucket, 0) + 1
                )

    per_provider = tuple(
        ReinsertionProviderStats(
            provider=provider,
            total=total,
            clean=per_provider_clean.get(provider, 0),
            clean_rate=per_provider_clean.get(provider, 0) / total,
        )
        for provider, total in sorted(per_provider_totals.items())
    )

    return ReinsertionAggregate(
        total_trials=total_trials,
        clean_trials=clean_trials,
        reinsertion_clean_rate=clean_trials / total_trials,
        round_trip_ok_trials=round_trip_ok_trials,
        round_trip_ok_rate=round_trip_ok_trials / total_trials,
        per_provider=per_provider,
        outcome_histogram=outcome_histogram,
        multiplicity_histogram=multiplicity_histogram,
        sentence_start_hits=sentence_start_hits,
        plural_occurrences=plural_occurrences,
    )


# ---------------------------------------------------------------------------
# Report rendering (mirrors cyo_adventure.measurement.report's style)
# ---------------------------------------------------------------------------


def render_json(data: ReinsertionAggregate) -> dict[str, object]:
    """Render a re-insertion report as a machine-readable JSON-serializable mapping.

    Args:
        data: The aggregated report.

    Returns:
        dict[str, object]: A plain-data mapping safe to pass to ``json.dumps``.
    """
    return {
        "total_trials": data.total_trials,
        "clean_trials": data.clean_trials,
        "reinsertion_clean_rate": data.reinsertion_clean_rate,
        "round_trip_ok_trials": data.round_trip_ok_trials,
        "round_trip_ok_rate": data.round_trip_ok_rate,
        "per_provider": [
            {
                "provider": stats.provider,
                "total": stats.total,
                "clean": stats.clean,
                "clean_rate": stats.clean_rate,
            }
            for stats in data.per_provider
        ],
        "outcome_histogram": dict(data.outcome_histogram),
        "multiplicity_histogram": dict(data.multiplicity_histogram),
        "sentence_start_hits": data.sentence_start_hits,
        "plural_occurrences": data.plural_occurrences,
    }


def render_markdown(data: ReinsertionAggregate) -> str:
    """Render a re-insertion report as a human-readable markdown summary.

    Args:
        data: The aggregated report.

    Returns:
        str: A markdown document stating the reinsertion-clean rate, the
            round-trip-ok rate, per-provider variance, the per-(node, token)
            outcome histogram, and the occurrence-multiplicity distribution.
    """
    lines: list[str] = ["# Sentinel re-insertion prototype report", ""]
    lines.append(
        " ".join(
            [
                "Strip-all-then-reinsert clean rate:",
                f"**{data.reinsertion_clean_rate:.1%}**",
                f"({data.clean_trials}/{data.total_trials})",
            ]
        )
    )
    lines.append("")
    lines.append(
        " ".join(
            [
                "Round-trip integrity-check pass rate (proves a clean",
                "reinsertion restores the exact expected token multiset):",
                f"**{data.round_trip_ok_rate:.1%}**",
                f"({data.round_trip_ok_trials}/{data.total_trials})",
            ]
        )
    )
    lines.append("")
    lines.append(
        " ".join(
            [
                "Sentence-start capitalization widening matches:",
                f"**{data.sentence_start_hits}**",
            ]
        )
    )
    lines.append("")
    lines.append(
        " ".join(
            [
                "Plural occurrences seen but left unwrapped:",
                f"**{data.plural_occurrences}**",
            ]
        )
    )
    lines.append("")

    lines.append("## Per-provider variance")
    lines.append("")
    lines.append("| Provider | Clean | Total | Clean rate |")
    lines.append("| --- | --- | --- | --- |")
    lines.extend(
        f"| {stats.provider} | {stats.clean} | {stats.total} | {stats.clean_rate:.1%} |"
        for stats in data.per_provider
    )
    lines.append("")

    lines.append("## Per-(node, token) outcome histogram")
    lines.append("")
    lines.append("| Outcome | Count |")
    lines.append("| --- | --- |")
    lines.extend(
        f"| {status} | {data.outcome_histogram[status]} |"
        for status in sorted(data.outcome_histogram)
    )
    if not data.outcome_histogram:
        lines.append("| (none) | 0 |")
    lines.append("")

    lines.append("## Occurrence-multiplicity distribution (reinsertable tokens only)")
    lines.append("")
    lines.append("| Occurrences | Count |")
    lines.append("| --- | --- |")
    lines.extend(
        f"| {bucket} | {data.multiplicity_histogram.get(bucket, 0)} |"
        for bucket in (_MULTIPLICITY_SINGLE, _MULTIPLICITY_FEW, _MULTIPLICITY_MANY)
    )
    lines.append("")

    return "\n".join(lines)
