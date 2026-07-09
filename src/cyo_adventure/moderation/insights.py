"""Aggregation of moderation evidence into threshold insights (WS-F).

Read side of the moderation learning loop: correlates the per-version
moderation reports persisted on ``storybook_version.moderation_report`` with
the ``released`` / ``sent_back`` decision events in the append-only
``pipeline_event`` log, and derives admin-facing override rates and threshold
suggestions. Pure computation lives in module-level functions so it unit
tests without a database; ``load_version_records`` is the only DB read.
This module never writes (umbrella decision 3: no auto-calibration).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.events import EventType
from cyo_adventure.moderation.report import Verdict

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from cyo_adventure.moderation.thresholds import ThresholdPolicy

# Suggestion gates: a proposal appears only when at least this many decided
# versions carry the (band, category) signal and at least this fraction of
# them were released despite it.
SUGGESTION_MIN_DECIDED = 5
SUGGESTION_MIN_OVERRIDE_RATE = 0.8

# Raising the surfacing bar one step: findings below min_verdict stop
# surfacing to families, so "overridden too often" moves the bar upward.
_VERDICT_RAISE: dict[str, str] = {
    Verdict.ADVISORY.value: Verdict.FLAG.value,
    Verdict.FLAG.value: Verdict.BLOCK.value,
}

# Verdicts a guardian can override by releasing anyway; hard blocks never
# reach the guardian, so they carry no override signal.
_OVERRIDABLE_VERDICTS = frozenset({Verdict.ADVISORY.value, Verdict.FLAG.value})


@dataclass(frozen=True, slots=True)
class VersionOutcome:
    """Terminal review decision attributed to one storybook version."""

    decided: bool
    released: bool


_UNDECIDED = VersionOutcome(decided=False, released=False)


def attribute_outcome(
    moderated_at: datetime,
    decisions: Sequence[tuple[datetime, str]],
    *,
    approved: bool,
) -> VersionOutcome:
    """Attribute a per-storybook decision stream to one version.

    ``released`` and ``sent_back`` events carry only the storybook id, so the
    version they decide is the one whose moderation completed most recently
    before them: the first decision at or after ``moderated_at`` belongs to
    this version.

    Args:
        moderated_at: When this version's moderation completed (event time,
            falling back to the version row's ``created_at``).
        decisions: ``(occurred_at, event_type)`` pairs for the version's
            storybook, sorted ascending by ``occurred_at``.
        approved: Whether the version row has ``approved_by`` set.

    Returns:
        The attributed outcome; undecided when no decision follows and the
        version was never approved.
    """
    for occurred_at, event_type in decisions:
        if occurred_at >= moderated_at:
            return VersionOutcome(
                decided=True, released=event_type == EventType.RELEASED.value
            )
    if approved:
        # #ASSUME: data-integrity: pre-WS-D history has approvals but no
        # decision events; approved_by on the version row is the release
        # record for those. There is no equivalent sent-back record, so
        # unapproved event-less versions stay out of the denominator.
        # #VERIFY: tests/unit/test_moderation_insights.py::TestAttributeOutcome
        return VersionOutcome(decided=True, released=True)
    return _UNDECIDED


@dataclass(frozen=True, slots=True)
class VersionModerationRecord:
    """One moderated version: band, findings, and attributed outcome."""

    storybook_id: str
    version: int
    age_band: str
    findings: Sequence[Mapping[str, object]]
    moderated_at: datetime
    outcome: VersionOutcome


@dataclass(frozen=True, slots=True)
class CategoryInsight:
    """Override evidence for one (age_band, category) pair."""

    age_band: str
    category: str
    advisory_findings: int
    flag_findings: int
    decided_versions: int
    released_versions: int
    override_rate: float | None
    last_seen: datetime


@dataclass(slots=True)
class _CategoryAccumulator:
    last_seen: datetime
    advisory_findings: int = 0
    flag_findings: int = 0
    decided_versions: int = 0
    released_versions: int = 0


def aggregate_insights(
    records: Sequence[VersionModerationRecord],
) -> list[CategoryInsight]:
    """Aggregate per-version records into per-(band, category) evidence.

    Finding counts tally every advisory/flag finding; version counts
    (``decided_versions`` / ``released_versions``) count each version at most
    once per category, since one release decision overrides every advisory on
    that version together (accepted F1 coarseness).

    Args:
        records: Version records from ``load_version_records`` (or built
            directly in tests).

    Returns:
        Insights sorted by (age_band, category).
    """
    accumulators: dict[tuple[str, str], _CategoryAccumulator] = {}
    for record in records:
        seen_categories: set[str] = set()
        for finding in record.findings:
            category = finding.get("category")
            verdict = finding.get("verdict")
            # #EDGE: data-integrity: moderation_report is JSONB written by
            # ModerationReport.to_dict(), but imported or legacy rows may
            # deviate; a finding missing category/verdict is skipped, never
            # a crash.
            # #VERIFY: tests/unit/test_moderation_insights.py::
            # TestAggregateInsights::test_malformed_findings_are_skipped
            if not isinstance(category, str) or verdict not in _OVERRIDABLE_VERDICTS:
                continue
            key = (record.age_band, category)
            accumulator = accumulators.get(key)
            if accumulator is None:
                accumulator = _CategoryAccumulator(last_seen=record.moderated_at)
                accumulators[key] = accumulator
            else:
                accumulator.last_seen = max(record.moderated_at, accumulator.last_seen)
            if verdict == Verdict.ADVISORY.value:
                accumulator.advisory_findings += 1
            else:
                accumulator.flag_findings += 1
            if category in seen_categories:
                continue
            seen_categories.add(category)
            if record.outcome.decided:
                accumulator.decided_versions += 1
                if record.outcome.released:
                    accumulator.released_versions += 1
    insights: list[CategoryInsight] = []
    for (age_band, category), accumulator in sorted(accumulators.items()):
        override_rate = (
            accumulator.released_versions / accumulator.decided_versions
            if accumulator.decided_versions
            else None
        )
        insights.append(
            CategoryInsight(
                age_band=age_band,
                category=category,
                advisory_findings=accumulator.advisory_findings,
                flag_findings=accumulator.flag_findings,
                decided_versions=accumulator.decided_versions,
                released_versions=accumulator.released_versions,
                override_rate=override_rate,
                last_seen=accumulator.last_seen,
            )
        )
    return insights


@dataclass(frozen=True, slots=True)
class ThresholdSuggestion:
    """A computed proposal to raise one (band, category) surfacing bar."""

    age_band: str
    category: str
    current_min_verdict: str
    current_min_score: float | None
    suggested_min_verdict: str
    override_rate: float
    decided_versions: int
    released_versions: int


def suggest_thresholds(
    insights: Sequence[CategoryInsight],
    policy: ThresholdPolicy,
) -> list[ThresholdSuggestion]:
    """Derive threshold proposals from override evidence.

    A proposal appears only above the volume and rate gates and only when the
    effective threshold has a step left to raise; a (band, category) already
    at ``block`` yields nothing, which also makes an applied suggestion stop
    reappearing (F2: dismiss is a no-op, the threshold move retires it).

    Args:
        insights: Output of ``aggregate_insights``.
        policy: The resolved surfacing policy (rows over the code default).

    Returns:
        Proposals in the insights' (age_band, category) order.
    """
    suggestions: list[ThresholdSuggestion] = []
    for insight in insights:
        if insight.decided_versions < SUGGESTION_MIN_DECIDED:
            continue
        if (
            insight.override_rate is None
            or insight.override_rate < SUGGESTION_MIN_OVERRIDE_RATE
        ):
            continue
        threshold = policy.resolve(insight.age_band, insight.category)
        current = threshold.min_verdict.value
        suggested = _VERDICT_RAISE.get(current)
        if suggested is None:
            continue
        suggestions.append(
            ThresholdSuggestion(
                age_band=insight.age_band,
                category=insight.category,
                current_min_verdict=current,
                current_min_score=threshold.min_score,
                suggested_min_verdict=suggested,
                override_rate=insight.override_rate,
                decided_versions=insight.decided_versions,
                released_versions=insight.released_versions,
            )
        )
    return suggestions
