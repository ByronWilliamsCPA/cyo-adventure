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
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select

from cyo_adventure.db.models import PipelineEvent, StorybookVersion
from cyo_adventure.events import EventType
from cyo_adventure.moderation.report import Verdict

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.moderation.thresholds import ThresholdPolicy

# Suggestion gates: a proposal appears only when at least this many decided
# versions carry the (band, category) signal and at least this fraction of
# them were released despite it.
SUGGESTION_MIN_DECIDED = 5
SUGGESTION_MIN_OVERRIDE_RATE = 0.8

# Raising the surfacing bar one step: findings below min_verdict stop
# surfacing to families, so "overridden too often" moves the bar upward.
# Co-dependent with _OVERRIDABLE_VERDICTS below: a verdict added to one but
# not the other silently produces wrong suggestions.
_VERDICT_RAISE: dict[str, str] = {
    Verdict.ADVISORY.value: Verdict.FLAG.value,
    Verdict.FLAG.value: Verdict.BLOCK.value,
}

# Verdicts a guardian can override by releasing anyway; hard blocks never
# reach the guardian, so they carry no override signal.
# Co-dependent with _VERDICT_RAISE above: a verdict added to one but not
# the other silently produces wrong suggestions.
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
        # #ASSUME: timing-dependencies: pipeline_event timestamps are
        # monotonic across the moderation_completed and released/sent_back
        # writers, and at most one version per storybook awaits a decision
        # at a time; two moderations completed before one decision event
        # would double-credit that decision to both versions. Currently
        # unreachable: no code path creates version > 1 before the prior
        # version's decision lands.
        # #VERIFY: tests/unit/test_moderation_insights.py::
        # TestAttributeOutcome::test_boundary_equal_timestamp_is_decided and
        # ::test_decision_event_wins_over_approved_fallback
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


def _fold_finding_into_accumulator(
    finding: Mapping[str, object],
    record: VersionModerationRecord,
    seen_categories: set[str],
    accumulators: dict[tuple[str, str], _CategoryAccumulator],
) -> None:
    """Fold one finding into its (age_band, category) accumulator, in place.

    Extracted from ``aggregate_insights`` to keep that function's cognitive
    complexity within the project's SonarQube gate (python:S3776); behavior
    is unchanged.

    Args:
        finding: One entry from ``record``'s moderation report.
        record: The version the finding belongs to (supplies age_band,
            moderated_at, and the attributed outcome).
        seen_categories: Categories already credited for this version's
            decided/released counts; mutated to add ``finding``'s category.
        accumulators: The running per-(age_band, category) tallies; mutated
            in place.
    """
    # #EDGE: data-integrity: a findings sequence may contain an element that
    # is not a JSON object (a bare string, int, or null) in a legacy or
    # imported row; skipped here, never a crash, matching the module
    # docstring's "skipped, never a crash" contract.
    # #VERIFY: tests/unit/test_moderation_insights.py::
    # TestAggregateInsights::test_non_dict_findings_elements_are_skipped
    if not isinstance(finding, dict):
        return
    category = finding.get("category")
    verdict = finding.get("verdict")
    # #EDGE: data-integrity: moderation_report is JSONB written by
    # ModerationReport.to_dict(), but imported or legacy rows may
    # deviate; a finding missing category/verdict is skipped, never
    # a crash.
    # #VERIFY: tests/unit/test_moderation_insights.py::
    # TestAggregateInsights::test_malformed_findings_are_skipped
    if not isinstance(category, str) or verdict not in _OVERRIDABLE_VERDICTS:
        return
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
        return
    seen_categories.add(category)
    if record.outcome.decided:
        accumulator.decided_versions += 1
        if record.outcome.released:
            accumulator.released_versions += 1


def _build_category_insight(
    age_band: str, category: str, accumulator: _CategoryAccumulator
) -> CategoryInsight:
    """Convert one accumulator into its public ``CategoryInsight`` row."""
    override_rate = (
        accumulator.released_versions / accumulator.decided_versions
        if accumulator.decided_versions
        else None
    )
    return CategoryInsight(
        age_band=age_band,
        category=category,
        advisory_findings=accumulator.advisory_findings,
        flag_findings=accumulator.flag_findings,
        decided_versions=accumulator.decided_versions,
        released_versions=accumulator.released_versions,
        override_rate=override_rate,
        last_seen=accumulator.last_seen,
    )


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
            _fold_finding_into_accumulator(
                finding, record, seen_categories, accumulators
            )
    return [
        _build_category_insight(age_band, category, accumulator)
        for (age_band, category), accumulator in sorted(accumulators.items())
    ]


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

    A proposal appears only at or above the volume and rate gates and only
    when the effective threshold has a step left to raise; a (band, category)
    already at ``block`` yields nothing, which also makes an applied
    suggestion stop reappearing (F2: dismiss is a no-op, the threshold move
    retires it).

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


async def load_version_records(session: AsyncSession) -> list[VersionModerationRecord]:
    """Load every moderated version with its band, findings, and outcome.

    Three reads: version rows carrying a moderation report (band extracted
    from the blob's typed metadata in SQL, so blobs are never fetched),
    ``moderation_completed`` timestamps, and per-storybook decision events.

    Args:
        session: The request-scoped async session.

    Returns:
        One record per version whose report and band are both present.
    """
    # #ASSUME: external-resources: whole-corpus reads per request are
    # deliberate at v1 volumes, mirroring list_thresholds' no-cache stance;
    # revisit with an occurred_at window if the corpus grows past a few
    # thousand versions.
    # #VERIFY: tests/integration/test_moderation_dashboard_api.py.
    version_rows = (
        await session.execute(
            select(
                StorybookVersion.storybook_id,
                StorybookVersion.version,
                StorybookVersion.moderation_report,
                StorybookVersion.created_at,
                StorybookVersion.approved_by,
                func.jsonb_extract_path_text(
                    StorybookVersion.blob, "metadata", "age_band"
                ).label("age_band"),
            ).where(StorybookVersion.moderation_report.is_not(None))
        )
    ).all()

    moderated_at_by_version: dict[tuple[str, int], datetime] = {}
    moderation_events = (
        await session.execute(
            select(PipelineEvent.entity_id, PipelineEvent.occurred_at).where(
                PipelineEvent.entity_type == "storybook_version",
                PipelineEvent.event_type == EventType.MODERATION_COMPLETED.value,
            )
        )
    ).all()
    for entity_id, occurred_at in moderation_events:
        storybook_id, _, version_text = entity_id.rpartition(":")
        # #EDGE: data-integrity: a composite id that does not parse is
        # skipped, never a crash; that version falls back to created_at
        # ordering below.
        # #VERIFY: tests/integration/test_moderation_dashboard_api.py::
        # TestLoadVersionRecords::test_loader_skips_malformed_moderation_event_entity_ids.
        if not storybook_id or not version_text.isdigit():
            continue
        key = (storybook_id, int(version_text))
        existing = moderated_at_by_version.get(key)
        if existing is None or occurred_at > existing:
            moderated_at_by_version[key] = occurred_at

    decisions_by_storybook: dict[str, list[tuple[datetime, str]]] = {}
    decision_events = (
        await session.execute(
            select(
                PipelineEvent.entity_id,
                PipelineEvent.occurred_at,
                PipelineEvent.event_type,
            )
            .where(
                PipelineEvent.entity_type == "storybook",
                PipelineEvent.event_type.in_(
                    [EventType.RELEASED.value, EventType.SENT_BACK.value]
                ),
            )
            .order_by(PipelineEvent.occurred_at)
        )
    ).all()
    for entity_id, occurred_at, event_type in decision_events:
        decisions_by_storybook.setdefault(entity_id, []).append(
            (occurred_at, event_type)
        )

    records: list[VersionModerationRecord] = []
    for (
        storybook_id,
        version,
        report,
        created_at,
        approved_by,
        age_band,
    ) in version_rows:
        if not age_band:
            # #EDGE: data-integrity: imported or legacy blobs may lack
            # metadata.age_band; such versions cannot be attributed to a
            # band and are excluded rather than mis-bucketed.
            # #VERIFY: tests/integration/test_moderation_dashboard_api.py::
            # TestLoadVersionRecords::test_loader_skips_versions_without_band
            continue
        raw_findings = report.get("findings") if isinstance(report, dict) else None
        # #EDGE: data-integrity: a legacy or imported row's findings array may
        # hold elements that are not JSON objects (a bare string, int, or
        # null); filtering to dict elements here, before the record is built,
        # keeps aggregate_insights from ever receiving a non-Mapping finding.
        # #VERIFY: tests/unit/test_moderation_insights.py::
        # TestAggregateInsights::test_non_dict_findings_elements_are_skipped
        findings = (
            cast(
                "list[Mapping[str, object]]",
                [item for item in raw_findings if isinstance(item, dict)],
            )
            if isinstance(raw_findings, list)
            else []
        )
        moderated_at: datetime = moderated_at_by_version.get(
            (storybook_id, version), cast("datetime", created_at)
        )
        records.append(
            VersionModerationRecord(
                storybook_id=storybook_id,
                version=version,
                age_band=age_band,
                findings=findings,
                moderated_at=moderated_at,
                outcome=attribute_outcome(
                    moderated_at,
                    decisions_by_storybook.get(storybook_id, ()),
                    approved=approved_by is not None,
                ),
            )
        )
    return records
