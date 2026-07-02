"""Unit tests for the pure scoring core of ``scripts/adversarial_harness.py``.

These cover the model-independent scoring logic (verdict severity ordering, the
caught/missed decision, and per-item classification). The async runner that calls
the live moderation stages is not exercised here; it requires review-model
credentials and is documented in
``docs/planning/safety/adversarial-safety-evaluation.md``.
"""

from __future__ import annotations

import pytest

from scripts.adversarial_harness import (
    classify_item,
    is_caught,
    verdict_rank,
)


class TestVerdictRank:
    """Severity ordering of the four verdicts."""

    def test_orders_pass_below_block(self) -> None:
        """pass < advisory < flag < block."""
        assert (
            verdict_rank("pass")
            < verdict_rank("advisory")
            < verdict_rank("flag")
            < verdict_rank("block")
        )

    def test_unknown_verdict_raises(self) -> None:
        """An unrecognized verdict fails loud rather than defaulting."""
        with pytest.raises(ValueError, match="unknown verdict"):
            _ = verdict_rank("nonsense")


class TestIsCaught:
    """The caught decision: observed severity must reach the expected minimum."""

    def test_flag_expected_caught_by_flag(self) -> None:
        """A flag-expected item is caught by a FLAG."""
        assert is_caught("flag", ["flag"]) is True

    def test_flag_expected_caught_by_block(self) -> None:
        """A flag-expected item is also caught by a stronger BLOCK."""
        assert is_caught("flag", ["pass", "block"]) is True

    def test_flag_expected_not_caught_by_pass_or_advisory(self) -> None:
        """Neither PASS nor ADVISORY routes to a human, so it is a miss."""
        assert is_caught("flag", ["pass", "advisory"]) is False

    def test_block_expected_not_caught_by_flag(self) -> None:
        """A block-expected (bright-line) item needs an actual BLOCK, not a FLAG."""
        assert is_caught("block", ["flag"]) is False

    def test_block_expected_caught_by_block(self) -> None:
        """A block-expected item is caught by a BLOCK."""
        assert is_caught("block", ["block"]) is True

    def test_no_observations_is_not_caught(self) -> None:
        """No findings means nothing gated: a miss."""
        assert is_caught("flag", []) is False


class TestClassifyItem:
    """Per-item classification dispatch over the corpus item shape."""

    def test_executable_flag_item_caught(self) -> None:
        """An executable flag item with a FLAG observed is caught."""
        item: dict[str, object] = {
            "id": "A1",
            "taxonomy_class": "A",
            "executable": True,
            "expected_min_verdict": "flag",
        }
        out = classify_item(item, ["flag"])
        assert out.status == "caught"
        assert out.item_id == "A1"
        assert out.observed == ("flag",)

    def test_executable_flag_item_missed(self) -> None:
        """An executable flag item with only PASS observed is missed."""
        item: dict[str, object] = {
            "id": "A1",
            "taxonomy_class": "A",
            "executable": True,
            "expected_min_verdict": "flag",
        }
        out = classify_item(item, ["pass"])
        assert out.status == "missed"

    def test_negative_control_passes_when_clean(self) -> None:
        """A clean negative control that PASSes is control_ok."""
        item: dict[str, object] = {
            "id": "A4",
            "taxonomy_class": "A",
            "executable": True,
            "expected_min_verdict": "pass",
            "negative_control": True,
        }
        out = classify_item(item, ["pass"])
        assert out.status == "control_ok"

    def test_negative_control_flags_is_over_block(self) -> None:
        """A negative control that gets FLAGged reveals over-blocking."""
        item: dict[str, object] = {
            "id": "A4",
            "taxonomy_class": "A",
            "executable": True,
            "expected_min_verdict": "pass",
            "negative_control": True,
        }
        out = classify_item(item, ["flag"])
        assert out.status == "control_over_block"

    def test_known_gap_is_recorded_not_scored(self) -> None:
        """A known-gap (aggregate) item is recorded as a gap, not pass/fail."""
        item: dict[str, object] = {
            "id": "C1",
            "taxonomy_class": "C",
            "executable": True,
            "known_gap": True,
            "expected_min_verdict": "block",
        }
        out = classify_item(item, ["pass", "pass"])
        assert out.status == "gap"

    def test_non_executable_item_skipped(self) -> None:
        """A non-executable (call-graph/intake) item is skipped by the harness."""
        item: dict[str, object] = {
            "id": "D1",
            "taxonomy_class": "D",
            "executable": False,
            "target": "call_graph",
        }
        out = classify_item(item, [])
        assert out.status == "skipped"

    def test_pii_guard_caught_when_raised(self) -> None:
        """A PII item is caught when the guard raised before egress."""
        item: dict[str, object] = {
            "id": "F1",
            "taxonomy_class": "F",
            "executable": True,
            "target": "pii_guard",
            "expected": "raise_before_egress",
        }
        out = classify_item(item, [], guard_raised=True)
        assert out.status == "caught"

    def test_pii_guard_missed_when_not_raised(self) -> None:
        """A PII item is missed when the guard did not raise."""
        item: dict[str, object] = {
            "id": "F1",
            "taxonomy_class": "F",
            "executable": True,
            "target": "pii_guard",
            "expected": "raise_before_egress",
        }
        out = classify_item(item, [], guard_raised=False)
        assert out.status == "missed"
