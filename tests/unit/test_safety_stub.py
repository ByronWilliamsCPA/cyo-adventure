"""Tests for the SAFE-14 safety stub validator.

SAFE-14 is a Phase-2 placeholder that establishes the call seam for Phase-3
provider moderation. The stub always returns an empty ValidationReport.
"""

from __future__ import annotations

import json
from pathlib import Path

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.safety import check_safety

_VALID_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "storybook"
    / "valid"
    / "01_hello_world.json"
)


class TestSafetyStub:
    """SAFE-14 stub: always returns empty, ok report."""

    def test_returns_empty_findings(self) -> None:
        """check_safety returns a report with no findings."""
        story = Storybook.model_validate(json.loads(_VALID_FIXTURE.read_text()))
        report = check_safety(story)
        assert report.findings == [], "SAFE-14 stub must return an empty findings list"

    def test_report_ok_is_true(self) -> None:
        """check_safety returns a report where ok is True."""
        story = Storybook.model_validate(json.loads(_VALID_FIXTURE.read_text()))
        report = check_safety(story)
        assert report.ok is True, "SAFE-14 stub must always return ok=True"

    def test_idempotent_on_multiple_calls(self) -> None:
        """Calling check_safety twice returns empty, independent reports."""
        story = Storybook.model_validate(json.loads(_VALID_FIXTURE.read_text()))
        report_a = check_safety(story)
        report_b = check_safety(story)
        assert report_a.findings == []
        assert report_b.findings == []
        # Each call should return a fresh report object.
        assert report_a is not report_b
