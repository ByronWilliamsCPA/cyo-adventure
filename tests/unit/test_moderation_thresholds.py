"""Unit tests for the age-band moderation threshold policy."""

from __future__ import annotations

import pytest

from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.thresholds import (
    DEFAULT_THRESHOLD,
    Threshold,
    ThresholdPolicy,
)

pytestmark = pytest.mark.unit


def _policy(rows: dict[tuple[str, str], Threshold] | None = None) -> ThresholdPolicy:
    return ThresholdPolicy(rows=rows or {})


def test_default_hides_advisory() -> None:
    """With no override rows, an advisory finding does not surface."""
    assert not _policy().surfaces(
        age_band="8-11", category="toxicity", verdict=Verdict.ADVISORY, score=0.4
    )


def test_default_surfaces_flag_and_block() -> None:
    """Flag and block findings surface under the code default."""
    policy = _policy()
    assert policy.surfaces(
        age_band="8-11", category="safety", verdict=Verdict.FLAG, score=None
    )
    assert policy.surfaces(
        age_band="8-11", category="safety", verdict=Verdict.BLOCK, score=None
    )


def test_pass_never_surfaces() -> None:
    """A pass verdict never surfaces, even if a row lowers the floor."""
    rows = {("3-5", "safety"): Threshold(min_verdict=Verdict.ADVISORY, min_score=None)}
    assert not _policy(rows).surfaces(
        age_band="3-5", category="safety", verdict=Verdict.PASS, score=None
    )


def test_row_lowers_floor_to_advisory() -> None:
    """An override row can surface advisories for a specific band and category."""
    rows = {
        ("3-5", "violence"): Threshold(min_verdict=Verdict.ADVISORY, min_score=None)
    }
    policy = _policy(rows)
    assert policy.surfaces(
        age_band="3-5", category="violence", verdict=Verdict.ADVISORY, score=0.2
    )
    # Other bands still use the default.
    assert not policy.surfaces(
        age_band="13-16", category="violence", verdict=Verdict.ADVISORY, score=0.2
    )


def test_min_score_floor_applies_to_scored_findings_only() -> None:
    """min_score hides low-scored findings but never unscored ones."""
    rows = {("3-5", "violence"): Threshold(min_verdict=Verdict.ADVISORY, min_score=0.3)}
    policy = _policy(rows)
    assert not policy.surfaces(
        age_band="3-5", category="violence", verdict=Verdict.ADVISORY, score=0.1
    )
    assert policy.surfaces(
        age_band="3-5", category="violence", verdict=Verdict.ADVISORY, score=0.31
    )
    assert policy.surfaces(
        age_band="3-5", category="violence", verdict=Verdict.ADVISORY, score=None
    )


def test_string_verdict_is_coerced() -> None:
    """Callers holding serialized verdict strings get the same behavior."""
    assert _policy().surfaces(
        age_band="8-11", category="safety", verdict="flag", score=None
    )


def test_unknown_string_verdict_does_not_surface() -> None:
    """A malformed stored verdict is treated as not surfaceable, not a crash."""
    assert not _policy().surfaces(
        age_band="8-11", category="safety", verdict="banana", score=None
    )


def test_default_threshold_is_flag() -> None:
    """Lock the code default so it cannot drift silently."""
    assert Threshold(min_verdict=Verdict.FLAG, min_score=None) == DEFAULT_THRESHOLD
