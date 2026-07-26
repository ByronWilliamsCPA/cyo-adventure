"""Aggregate classified fill trials into the plan 3.4 GO/NO-GO report.

Plan section 3.4 asks for three numbers: the overall first-attempt clean-pass
rate, the per-provider split (a survival rate that holds on one model and
collapses on another is a deployment risk, not a curiosity), and the retry-
cost projection (``extra_fill_spend_fraction = 1 - clean_pass_rate``). This
module computes all three from a flat sequence of
:class:`~cyo_adventure.measurement.taxonomy.RunRecord` results, plus the
failure-taxonomy histogram (both the checker's raw kind and the plan 3.4
bucket, kept side by side for auditability), and renders both a machine-
readable JSON view and a human-readable markdown summary.

Pure: every function here is a plain data transform with no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.measurement.taxonomy import bucket_for

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.measurement.taxonomy import RunRecord

# Plan 3.4's stated thresholds, applied to the overall clean-pass rate:
# >=~0.95 makes a single retry cheap (GO); ~0.80-0.95 still works but retries
# are a real cost line (iterate on the delimiter/prompt first); <~0.80 means
# reconsider the approach (the deterministic post-fill re-insertion fallback
# becomes worth prototyping).
_GO_THRESHOLD = 0.95
_ITERATE_THRESHOLD = 0.80

_DRY_RUN_BANNER = "PLUMBING DRY-RUN, not a survival number."


@dataclass(frozen=True, slots=True)
class TrialRecord:
    """One classified trial: a specimen run through one provider.

    Attributes:
        specimen_slug: The specimen's source skeleton slug.
        provider: The provider name the trial ran against (e.g. ``"mock"``).
        record: The classified fill outcome.
    """

    specimen_slug: str
    provider: str
    record: RunRecord


@dataclass(frozen=True, slots=True)
class ProviderStats:
    """Clean-pass statistics for one provider.

    Attributes:
        provider: The provider name.
        total: Total trials run against this provider.
        clean: Trials that passed clean on the first attempt.
        clean_pass_rate: ``clean / total``.
    """

    provider: str
    total: int
    clean: int
    clean_pass_rate: float


@dataclass(frozen=True, slots=True)
class ReportData:
    """The full aggregated survival-measurement report.

    Attributes:
        total_runs: Total trials aggregated (across every provider).
        clean_runs: Trials that passed clean on the first attempt.
        clean_pass_rate: ``clean_runs / total_runs``, the plan 3.4 headline
            number.
        per_provider: Per-provider stats, sorted by provider name.
        raw_kind_histogram: Violation counts keyed by the checker's raw
            ``.kind``.
        bucket_histogram: Violation counts keyed by the plan 3.4 taxonomy
            bucket.
        extra_fill_spend_fraction: ``1 - clean_pass_rate``, the projected
            extra fill spend a one-retry policy would add.
        threshold_band: One of ``"go"``, ``"iterate"``, ``"reconsider"``, per
            plan 3.4's stated thresholds against ``clean_pass_rate``.
    """

    total_runs: int
    clean_runs: int
    clean_pass_rate: float
    per_provider: tuple[ProviderStats, ...]
    raw_kind_histogram: dict[str, int]
    bucket_histogram: dict[str, int]
    extra_fill_spend_fraction: float
    threshold_band: str


def threshold_band(clean_pass_rate: float) -> str:
    """Return the plan 3.4 threshold band for a clean-pass rate.

    Args:
        clean_pass_rate: The measured (or projected) clean-pass rate, in
            ``[0.0, 1.0]``.

    Returns:
        str: ``"go"`` at or above :data:`_GO_THRESHOLD`, ``"iterate"`` at or
            above :data:`_ITERATE_THRESHOLD`, otherwise ``"reconsider"``.
    """
    if clean_pass_rate >= _GO_THRESHOLD:
        return "go"
    if clean_pass_rate >= _ITERATE_THRESHOLD:
        return "iterate"
    return "reconsider"


def aggregate(trials: Sequence[TrialRecord]) -> ReportData:
    """Aggregate a flat sequence of classified trials into a full report.

    Args:
        trials: Every trial run, across every specimen and provider.

    Returns:
        ReportData: The aggregated clean-pass rates, histograms, and retry-
            cost projection.

    Raises:
        ValueError: If ``trials`` is empty; there is nothing to report on.
    """
    if not trials:
        msg = "cannot aggregate an empty trial sequence"
        raise ValueError(msg)

    total_runs = len(trials)
    clean_runs = sum(1 for trial in trials if trial.record.clean)
    clean_pass_rate = clean_runs / total_runs

    per_provider_totals: dict[str, int] = {}
    per_provider_clean: dict[str, int] = {}
    raw_kind_histogram: dict[str, int] = {}
    bucket_histogram: dict[str, int] = {}

    for trial in trials:
        per_provider_totals[trial.provider] = (
            per_provider_totals.get(trial.provider, 0) + 1
        )
        if trial.record.clean:
            per_provider_clean[trial.provider] = (
                per_provider_clean.get(trial.provider, 0) + 1
            )
        for raw_kind, count in trial.record.raw_kind_counts().items():
            raw_kind_histogram[raw_kind] = raw_kind_histogram.get(raw_kind, 0) + count
        for bucket, count in trial.record.bucket_counts().items():
            bucket_histogram[bucket] = bucket_histogram.get(bucket, 0) + count

    per_provider = tuple(
        ProviderStats(
            provider=provider,
            total=total,
            clean=per_provider_clean.get(provider, 0),
            clean_pass_rate=per_provider_clean.get(provider, 0) / total,
        )
        for provider, total in sorted(per_provider_totals.items())
    )

    return ReportData(
        total_runs=total_runs,
        clean_runs=clean_runs,
        clean_pass_rate=clean_pass_rate,
        per_provider=per_provider,
        raw_kind_histogram=raw_kind_histogram,
        bucket_histogram=bucket_histogram,
        extra_fill_spend_fraction=1.0 - clean_pass_rate,
        threshold_band=threshold_band(clean_pass_rate),
    )


def _is_dry_run(providers: Sequence[str]) -> bool:
    """Return whether every requested provider is the deterministic mock.

    Args:
        providers: The provider names a run was requested against.

    Returns:
        bool: True when ``providers`` is non-empty and every entry is
            ``"mock"``.
    """
    return bool(providers) and all(provider == "mock" for provider in providers)


def render_json(data: ReportData, *, providers: Sequence[str]) -> dict[str, object]:
    """Render a report as a machine-readable JSON-serializable mapping.

    Args:
        data: The aggregated report.
        providers: The provider names the run was requested against (used
            only to decide whether the dry-run banner applies).

    Returns:
        dict[str, object]: A plain-data mapping safe to pass to ``json.dumps``.
    """
    dry_run = _is_dry_run(providers)
    payload: dict[str, object] = {
        "total_runs": data.total_runs,
        "clean_runs": data.clean_runs,
        "clean_pass_rate": data.clean_pass_rate,
        "per_provider": [
            {
                "provider": stats.provider,
                "total": stats.total,
                "clean": stats.clean,
                "clean_pass_rate": stats.clean_pass_rate,
            }
            for stats in data.per_provider
        ],
        "raw_kind_histogram": dict(data.raw_kind_histogram),
        "bucket_histogram": dict(data.bucket_histogram),
        "extra_fill_spend_fraction": data.extra_fill_spend_fraction,
        "threshold_band": data.threshold_band,
        "dry_run": dry_run,
    }
    if dry_run:
        payload["dry_run_banner"] = _DRY_RUN_BANNER
    return payload


def render_markdown(data: ReportData, *, providers: Sequence[str]) -> str:
    """Render a report as a human-readable markdown summary.

    Args:
        data: The aggregated report.
        providers: The provider names the run was requested against (used
            only to decide whether the dry-run banner applies).

    Returns:
        str: A markdown document stating the clean-pass rate, per-provider
            variance, the taxonomy histogram, the retry-cost projection, and
            which plan 3.4 threshold band the measured rate falls in.
    """
    dry_run = _is_dry_run(providers)
    lines: list[str] = ["# Sentinel-survival measurement report", ""]
    if dry_run:
        lines.append(f"**{_DRY_RUN_BANNER}**")
        lines.append(
            " ".join(
                [
                    "This run used only the deterministic `mock` provider, which echoes a",
                    "fixed canned story unrelated to any specimen's structure. It proves the",
                    "fixtures -> fill -> integrity-check -> taxonomy -> report pipeline runs",
                    "end to end without a paid call; the numbers below carry no information",
                    "about a real model's sentinel-preservation behavior.",
                ]
            )
        )
        lines.append("")

    lines.append(
        " ".join(
            [
                f"Overall first-attempt clean-pass rate: **{data.clean_pass_rate:.1%}**",
                f"({data.clean_runs}/{data.total_runs}) -> threshold band: **{data.threshold_band}**",
            ]
        )
    )
    lines.append("")
    lines.append(
        f"Projected extra fill spend from a one-retry policy: **{data.extra_fill_spend_fraction:.1%}**"
    )
    lines.append("")

    lines.append("## Per-provider variance")
    lines.append("")
    lines.append("| Provider | Clean | Total | Clean-pass rate |")
    lines.append("| --- | --- | --- | --- |")
    lines.extend(
        " ".join(
            [
                f"| {stats.provider} | {stats.clean} | {stats.total} |",
                f"{stats.clean_pass_rate:.1%} |",
            ]
        )
        for stats in data.per_provider
    )
    lines.append("")

    lines.append("## Failure taxonomy")
    lines.append("")
    lines.append("| Plan 3.4 bucket | Raw checker kind | Count |")
    lines.append("| --- | --- | --- |")
    bucket_by_raw = _bucket_labels_for_raw_kinds(data.raw_kind_histogram)
    for raw_kind in sorted(data.raw_kind_histogram):
        count = data.raw_kind_histogram[raw_kind]
        lines.append(f"| {bucket_by_raw[raw_kind]} | {raw_kind} | {count} |")
    if not data.raw_kind_histogram:
        lines.append("| (none) | (none) | 0 |")
    lines.append("")

    return "\n".join(lines)


def _bucket_labels_for_raw_kinds(raw_kind_histogram: dict[str, int]) -> dict[str, str]:
    """Return the plan 3.4 bucket label for every raw kind in a histogram.

    Reuses :func:`cyo_adventure.measurement.taxonomy.bucket_for` as the single
    canonical mapping rather than re-deriving it here.

    Args:
        raw_kind_histogram: Raw-kind-keyed violation counts.

    Returns:
        dict[str, str]: Raw kind to bucket label.
    """
    return {raw_kind: bucket_for(raw_kind) for raw_kind in raw_kind_histogram}
