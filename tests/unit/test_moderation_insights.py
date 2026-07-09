"""Unit tests for the WS-F moderation insights aggregation core."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cyo_adventure.events import EventType
from cyo_adventure.moderation.insights import (
    SUGGESTION_MIN_DECIDED,
    CategoryInsight,
    VersionModerationRecord,
    VersionOutcome,
    aggregate_insights,
    attribute_outcome,
    suggest_thresholds,
)
from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.thresholds import Threshold, ThresholdPolicy

_T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
_LATER = _T0 + timedelta(hours=1)
_EARLIER = _T0 - timedelta(hours=1)

_RELEASED = EventType.RELEASED.value
_SENT_BACK = EventType.SENT_BACK.value


def _finding(category: str, verdict: str) -> dict[str, object]:
    return {"category": category, "verdict": verdict, "score": 0.5}


def _record(
    *,
    findings: list[dict[str, object]],
    outcome: VersionOutcome,
    age_band: str = "8-11",
    storybook_id: str = "s_1",
    version: int = 1,
    moderated_at: datetime = _T0,
) -> VersionModerationRecord:
    return VersionModerationRecord(
        storybook_id=storybook_id,
        version=version,
        age_band=age_band,
        findings=findings,
        moderated_at=moderated_at,
        outcome=outcome,
    )


class TestAttributeOutcome:
    def test_first_decision_after_moderation_wins(self) -> None:
        decisions = [(_LATER, _SENT_BACK), (_LATER + timedelta(hours=1), _RELEASED)]
        outcome = attribute_outcome(_T0, decisions, approved=False)
        assert outcome == VersionOutcome(decided=True, released=False)

    def test_released_decision(self) -> None:
        outcome = attribute_outcome(_T0, [(_LATER, _RELEASED)], approved=False)
        assert outcome == VersionOutcome(decided=True, released=True)

    def test_decision_before_moderation_is_ignored(self) -> None:
        outcome = attribute_outcome(_T0, [(_EARLIER, _RELEASED)], approved=False)
        assert outcome == VersionOutcome(decided=False, released=False)

    def test_approved_fallback_counts_as_released(self) -> None:
        outcome = attribute_outcome(_T0, [], approved=True)
        assert outcome == VersionOutcome(decided=True, released=True)

    def test_no_decision_and_not_approved_is_undecided(self) -> None:
        outcome = attribute_outcome(_T0, [], approved=False)
        assert outcome == VersionOutcome(decided=False, released=False)


class TestAggregateInsights:
    def test_counts_findings_and_versions_per_band_category(self) -> None:
        records = [
            _record(
                findings=[_finding("violence", "advisory")],
                outcome=VersionOutcome(decided=True, released=True),
                storybook_id="s_1",
            ),
            _record(
                findings=[_finding("violence", "flag")],
                outcome=VersionOutcome(decided=True, released=False),
                storybook_id="s_2",
                moderated_at=_LATER,
            ),
        ]
        insights = aggregate_insights(records)
        assert len(insights) == 1
        row = insights[0]
        assert (row.age_band, row.category) == ("8-11", "violence")
        assert row.advisory_findings == 1
        assert row.flag_findings == 1
        assert row.decided_versions == 2
        assert row.released_versions == 1
        assert row.override_rate == 0.5
        assert row.last_seen == _LATER

    def test_dedupes_category_within_a_version(self) -> None:
        records = [
            _record(
                findings=[
                    _finding("violence", "advisory"),
                    _finding("violence", "advisory"),
                ],
                outcome=VersionOutcome(decided=True, released=True),
            )
        ]
        row = aggregate_insights(records)[0]
        assert row.advisory_findings == 2
        assert row.decided_versions == 1
        assert row.released_versions == 1

    def test_undecided_versions_do_not_enter_the_denominator(self) -> None:
        records = [
            _record(
                findings=[_finding("violence", "advisory")],
                outcome=VersionOutcome(decided=False, released=False),
            )
        ]
        row = aggregate_insights(records)[0]
        assert row.decided_versions == 0
        assert row.override_rate is None

    def test_block_and_pass_findings_are_excluded(self) -> None:
        records = [
            _record(
                findings=[_finding("violence", "block"), _finding("fear", "pass")],
                outcome=VersionOutcome(decided=True, released=True),
            )
        ]
        assert aggregate_insights(records) == []

    def test_malformed_findings_are_skipped(self) -> None:
        records = [
            _record(
                findings=[{"verdict": "advisory"}, {"category": 3, "verdict": "flag"}],
                outcome=VersionOutcome(decided=True, released=True),
            )
        ]
        assert aggregate_insights(records) == []


def _insight(
    *,
    decided: int,
    released: int,
    age_band: str = "8-11",
    category: str = "violence",
) -> CategoryInsight:
    return CategoryInsight(
        age_band=age_band,
        category=category,
        advisory_findings=decided,
        flag_findings=0,
        decided_versions=decided,
        released_versions=released,
        override_rate=(released / decided) if decided else None,
        last_seen=_T0,
    )


class TestSuggestThresholds:
    def test_high_override_rate_raises_default_flag_to_block(self) -> None:
        policy = ThresholdPolicy(rows={})
        insights = [_insight(decided=SUGGESTION_MIN_DECIDED, released=5)]
        suggestions = suggest_thresholds(insights, policy)
        assert len(suggestions) == 1
        suggestion = suggestions[0]
        assert suggestion.current_min_verdict == "flag"
        assert suggestion.suggested_min_verdict == "block"
        assert suggestion.override_rate == 1.0
        assert suggestion.current_min_score is None

    def test_override_row_at_advisory_suggests_flag(self) -> None:
        policy = ThresholdPolicy(
            rows={
                ("8-11", "violence"): Threshold(
                    min_verdict=Verdict.ADVISORY, min_score=0.25
                )
            }
        )
        insights = [_insight(decided=6, released=6)]
        suggestion = suggest_thresholds(insights, policy)[0]
        assert suggestion.current_min_verdict == "advisory"
        assert suggestion.suggested_min_verdict == "flag"
        assert suggestion.current_min_score == 0.25

    def test_below_volume_gate_no_suggestion(self) -> None:
        policy = ThresholdPolicy(rows={})
        insights = [_insight(decided=SUGGESTION_MIN_DECIDED - 1, released=4)]
        assert suggest_thresholds(insights, policy) == []

    def test_below_rate_gate_no_suggestion(self) -> None:
        policy = ThresholdPolicy(rows={})
        insights = [_insight(decided=10, released=7)]
        assert suggest_thresholds(insights, policy) == []

    def test_current_block_has_nothing_to_raise(self) -> None:
        policy = ThresholdPolicy(
            rows={
                ("8-11", "violence"): Threshold(
                    min_verdict=Verdict.BLOCK, min_score=None
                )
            }
        )
        insights = [_insight(decided=10, released=10)]
        assert suggest_thresholds(insights, policy) == []
