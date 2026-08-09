"""Unit tests for scripts/check_outcome_spread.py (ruled 2026-08-09, R1)."""

from __future__ import annotations

import pytest

import scripts.check_outcome_spread as spread


def _story(endings: list[tuple[str, str]]) -> dict[str, object]:
    nodes: list[dict[str, object]] = [
        {"id": f"e{i}", "ending": {"kind": kind, "valence": valence}}
        for i, (kind, valence) in enumerate(endings)
    ]
    return {"nodes": nodes}


@pytest.mark.unit
def test_outcome_signature_is_share_based_so_size_cancels() -> None:
    small = spread.outcome_signature(
        _story([("death", "negative"), ("success", "positive")])
    )
    large = spread.outcome_signature(
        _story([("death", "negative")] * 50 + [("success", "positive")] * 50)
    )
    assert small is not None
    assert large is not None
    assert small == pytest.approx(large)


@pytest.mark.unit
def test_signature_distance_zero_for_identical_and_one_for_disjoint() -> None:
    a = spread.outcome_signature(_story([("death", "negative")] * 9))
    b = spread.outcome_signature(_story([("success", "positive")] * 4))
    assert a is not None
    assert b is not None
    assert spread.signature_distance(a, a) == pytest.approx(0.0)
    assert spread.signature_distance(a, b) == pytest.approx(1.0)


@pytest.mark.unit
def test_signature_distance_flags_same_economy_shapes() -> None:
    """Two 2-wins/death-dominant trees are the same read regardless of size."""
    a = spread.outcome_signature(
        _story([("death", "negative")] * 78 + [("success", "positive")] * 2)
    )
    b = spread.outcome_signature(
        _story([("death", "negative")] * 145 + [("success", "positive")] * 4)
    )
    assert a is not None
    assert b is not None
    assert spread.signature_distance(a, b) < spread.DEFAULT_TAU


@pytest.mark.unit
def test_outcome_signature_none_for_endingless_story() -> None:
    assert spread.outcome_signature({"nodes": [{"id": "a", "choices": []}]}) is None
