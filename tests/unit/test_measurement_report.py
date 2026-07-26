"""Unit tests for the sentinel-survival report aggregation (plan 3.4).

Hand-builds `TrialRecord`/`RunRecord` sets (no fill, no fixtures) to assert
the overall and per-provider clean-pass rates, the taxonomy histogram, the
retry-cost projection arithmetic, and the threshold-band and dry-run-banner
logic are exactly right.
"""

from __future__ import annotations

import pytest

from cyo_adventure.measurement.report import (
    TrialRecord,
    aggregate,
    render_json,
    render_markdown,
    threshold_band,
)
from cyo_adventure.measurement.taxonomy import RunRecord, ViolationRecord


def _clean() -> RunRecord:
    return RunRecord(clean=True, violations=())


def _dirty(*, raw_kind: str, bucket: str, node_id: str = "n1") -> RunRecord:
    return RunRecord(
        clean=False,
        violations=(
            ViolationRecord(
                node_id=node_id,
                raw_kind=raw_kind,
                bucket=bucket,
                token="{~HERO:Explorer~}",
            ),
        ),
    )


@pytest.mark.unit
class TestThresholdBand:
    def test_at_or_above_95_percent_is_go(self) -> None:
        assert threshold_band(0.95) == "go"
        assert threshold_band(1.0) == "go"

    def test_between_80_and_95_percent_is_iterate(self) -> None:
        assert threshold_band(0.80) == "iterate"
        assert threshold_band(0.94) == "iterate"

    def test_below_80_percent_is_reconsider(self) -> None:
        assert threshold_band(0.79) == "reconsider"
        assert threshold_band(0.0) == "reconsider"


@pytest.mark.unit
def test_aggregate_empty_trials_raises() -> None:
    """Aggregating an empty trial sequence is a caller error, not a silent zero."""
    with pytest.raises(ValueError, match="empty trial sequence"):
        aggregate([])


@pytest.mark.unit
def test_aggregate_overall_and_per_provider_rates() -> None:
    """20 trials, 19 clean -> overall 0.95; per-provider split is exact."""
    trials = [
        TrialRecord(specimen_slug=f"story-{i}", provider="mock", record=_clean())
        for i in range(9)
    ]
    trials.append(
        TrialRecord(
            specimen_slug="story-9",
            provider="mock",
            record=_dirty(raw_kind="dropped", bucket="dropped"),
        )
    )
    trials.extend(
        TrialRecord(specimen_slug=f"story-{i}", provider="ollama", record=_clean())
        for i in range(10)
    )
    data = aggregate(trials)

    assert data.total_runs == 20
    assert data.clean_runs == 19
    assert data.clean_pass_rate == pytest.approx(0.95)
    assert data.extra_fill_spend_fraction == pytest.approx(0.05)
    assert data.threshold_band == "go"

    by_provider = {stats.provider: stats for stats in data.per_provider}
    assert by_provider["mock"].total == 10
    assert by_provider["mock"].clean == 9
    assert by_provider["mock"].clean_pass_rate == pytest.approx(0.9)
    assert by_provider["ollama"].total == 10
    assert by_provider["ollama"].clean == 10
    assert by_provider["ollama"].clean_pass_rate == pytest.approx(1.0)


@pytest.mark.unit
def test_aggregate_extra_fill_spend_at_80_percent() -> None:
    """10 trials, 8 clean -> 0.80 clean-pass rate, ~0.20 extra spend, iterate band."""
    trials = [
        TrialRecord(specimen_slug=f"s{i}", provider="mock", record=_clean())
        for i in range(8)
    ]
    trials.extend(
        TrialRecord(
            specimen_slug=f"s{8 + i}",
            provider="mock",
            record=_dirty(raw_kind="forged", bucket="mutated_wrapper_or_inner"),
        )
        for i in range(2)
    )
    data = aggregate(trials)
    assert data.clean_pass_rate == pytest.approx(0.80)
    assert data.extra_fill_spend_fraction == pytest.approx(0.20)
    assert data.threshold_band == "iterate"


@pytest.mark.unit
def test_aggregate_taxonomy_histograms() -> None:
    """Both the raw-kind and bucket histograms count every violation, per record."""
    trials = [
        TrialRecord(
            specimen_slug="s0",
            provider="mock",
            record=_dirty(raw_kind="dropped", bucket="dropped"),
        ),
        TrialRecord(
            specimen_slug="s1",
            provider="mock",
            record=_dirty(raw_kind="dropped", bucket="dropped"),
        ),
        TrialRecord(
            specimen_slug="s2",
            provider="mock",
            record=_dirty(raw_kind="malformed", bucket="mutated_wrapper"),
        ),
    ]
    data = aggregate(trials)
    assert data.raw_kind_histogram == {"dropped": 2, "malformed": 1}
    assert data.bucket_histogram == {"dropped": 2, "mutated_wrapper": 1}


@pytest.mark.unit
def test_render_markdown_dry_run_banner_present_for_mock_only() -> None:
    """The dry-run banner appears when every requested provider is mock."""
    trials = [TrialRecord(specimen_slug="s0", provider="mock", record=_clean())]
    data = aggregate(trials)
    markdown = render_markdown(data, providers=["mock"])
    assert "PLUMBING DRY-RUN, not a survival number." in markdown


@pytest.mark.unit
def test_render_markdown_no_banner_for_non_mock_providers() -> None:
    """No dry-run banner when a non-mock provider is among those requested."""
    trials = [TrialRecord(specimen_slug="s0", provider="ollama", record=_clean())]
    data = aggregate(trials)
    markdown = render_markdown(data, providers=["ollama"])
    assert "PLUMBING DRY-RUN" not in markdown


@pytest.mark.unit
def test_render_json_dry_run_flag_and_banner() -> None:
    """render_json carries a boolean dry_run flag and the banner text when applicable."""
    trials = [TrialRecord(specimen_slug="s0", provider="mock", record=_clean())]
    data = aggregate(trials)

    mock_only = render_json(data, providers=["mock"])
    assert mock_only["dry_run"] is True
    assert mock_only["dry_run_banner"] == "PLUMBING DRY-RUN, not a survival number."

    mixed = render_json(data, providers=["mock", "ollama"])
    assert mixed["dry_run"] is False
    assert "dry_run_banner" not in mixed


@pytest.mark.unit
def test_render_json_shape() -> None:
    """render_json emits every field aggregate() computed, JSON-serializable."""
    trials = [
        TrialRecord(specimen_slug="s0", provider="mock", record=_clean()),
        TrialRecord(
            specimen_slug="s1",
            provider="mock",
            record=_dirty(raw_kind="dropped", bucket="dropped"),
        ),
    ]
    data = aggregate(trials)
    payload = render_json(data, providers=["mock"])
    assert payload["total_runs"] == 2
    assert payload["clean_runs"] == 1
    assert payload["clean_pass_rate"] == pytest.approx(0.5)
    assert payload["per_provider"] == [
        {
            "provider": "mock",
            "total": 2,
            "clean": 1,
            "clean_pass_rate": pytest.approx(0.5),
        }
    ]
    assert payload["raw_kind_histogram"] == {"dropped": 1}
    assert payload["bucket_histogram"] == {"dropped": 1}
    assert payload["threshold_band"] == "reconsider"
