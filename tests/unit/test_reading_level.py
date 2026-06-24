"""Tests for the RL-13 reading-level advisory validator.

Strategy: construct minimal synthetic Storybook objects with controlled body
text so tests do not rely on fixture prose or exact FK float values.

Rules under test:
- RL-13 emits a WARNING (never ERROR) when a node's FK grade is outside
  [target - tolerance, target + tolerance].
- Nodes within the band produce no RL-13 finding.
- Nodes below the word-count floor (_MIN_WORDS_FOR_FK) are silently skipped.
- report.ok is always True (advisory check never blocks).
"""

from __future__ import annotations

import json
from pathlib import Path

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.reading_level import (
    _MIN_WORDS_FOR_FK,
    check_reading_level,
)
from cyo_adventure.validator.report import Severity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "storybook"
    / "valid"
    / "01_hello_world.json"
)

# A long, complex body clearly above FK grade 3 (many long polysyllabic words).
_HARD_BODY = (
    "The extraordinarily sophisticated philosopher contemplated the incomprehensible "
    "metaphysical implications of the multidimensional extraterrestrial manifestations "
    "with considerable perspicacity and analytical deliberation, acknowledging the "
    "phenomenological complexities that characterised the ontological investigation "
    "into transcendental consciousness, epistemological frameworks, and hermeneutical "
    "interpretation of philosophical phenomenology."
)

# A simple, short-sentence body well within FK grade 3 (low target band).
_EASY_BODY = (
    "The cat sat on the mat. "
    "She saw a big, red hat. "
    "The hat was fun. "
    "She ran and ran and ran. "
    "The cat had fun that day. "
    "She got the hat. "
    "She put it on her head. "
    "The mat was soft and nice. "
    "The cat liked the mat a lot. "
    "She lay on the mat and slept."
)

# A body that is deliberately below _MIN_WORDS_FOR_FK.
assert len(_HARD_BODY.split()) >= _MIN_WORDS_FOR_FK, "hard body must pass floor"
assert len(_EASY_BODY.split()) >= _MIN_WORDS_FOR_FK, "easy body must pass floor"


def _short_body() -> str:
    """Return a body string with fewer words than _MIN_WORDS_FOR_FK."""
    words = _HARD_BODY.split()
    return " ".join(words[: _MIN_WORDS_FOR_FK - 1])


def _make_story(body: str, target: float, tolerance: float = 1.0) -> Storybook:
    """Build a minimal valid Storybook with a single non-ending node + one ending.

    Args:
        body: Text assigned to the first (non-ending) branch node.
        target: reading_level.target for the story.
        tolerance: reading_level.tolerance for the story.

    Returns:
        Storybook: A structurally valid Storybook for testing.
    """
    return Storybook.model_validate(
        {
            "schema_version": "1.0",
            "id": "test_story",
            "version": 1,
            "title": "Test Story",
            "metadata": {
                "age_band": "8-11",
                "reading_level": {
                    "scheme": "flesch_kincaid",
                    "target": target,
                    "tolerance": tolerance,
                },
                "tier": 1,
                "themes": [],
                "estimated_minutes": 5,
                "ending_count": 1,
                "topology": "branch_and_bottleneck",
                "content_flags": {
                    "violence": "none",
                    "scariness": "none",
                    "peril": "none",
                },
            },
            "variables": [],
            "start_node": "n_start",
            "nodes": [
                {
                    "id": "n_start",
                    "body": body,
                    "is_ending": False,
                    "choices": [
                        {"id": "c1", "label": "Go on.", "target": "n_end"},
                    ],
                },
                {
                    "id": "n_end",
                    "body": "The end.",
                    "is_ending": True,
                    "ending": {
                        "id": "e_done",
                        "valence": "positive",
                        "kind": "success",
                        "title": "Done",
                    },
                    "choices": [],
                },
            ],
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReadingLevelAboveBand:
    """RL-13 fires a WARNING when a node's FK grade exceeds the upper bound."""

    def test_warning_finding_present(self) -> None:
        """A complex body against a low target band produces an RL-13 WARNING."""
        # Use a very low target (grade 2) with tight tolerance; the hard body
        # (many polysyllabic words) scores well above grade 3 under the
        # dependency-free Flesch-Kincaid implementation.
        story = _make_story(_HARD_BODY, target=2.0, tolerance=1.0)
        report = check_reading_level(story)
        rl13_findings = [f for f in report.findings if f.rule_id == "RL-13"]
        assert len(rl13_findings) >= 1, (
            "Expected at least one RL-13 finding for a hard body against a low target"
        )

    def test_finding_severity_is_warning(self) -> None:
        """The RL-13 finding must have WARNING severity, never ERROR."""
        story = _make_story(_HARD_BODY, target=2.0, tolerance=1.0)
        report = check_reading_level(story)
        for finding in report.findings:
            assert finding.severity is Severity.WARNING, (
                f"RL-13 must only emit WARNING; got {finding.severity}"
            )

    def test_report_ok_is_true_despite_warning(self) -> None:
        """report.ok stays True even when RL-13 warnings are present."""
        story = _make_story(_HARD_BODY, target=2.0, tolerance=1.0)
        report = check_reading_level(story)
        assert report.ok is True, "advisory check must never set report.ok to False"

    def test_finding_node_id_set(self) -> None:
        """Each RL-13 finding must carry the node_id of the violating node."""
        story = _make_story(_HARD_BODY, target=2.0, tolerance=1.0)
        report = check_reading_level(story)
        for finding in report.findings:
            assert finding.node_id is not None, "RL-13 finding must have node_id set"

    def test_finding_message_template(self) -> None:
        """The finding message must contain the rule id, node id, and advisory marker."""
        story = _make_story(_HARD_BODY, target=2.0, tolerance=1.0)
        report = check_reading_level(story)
        finding = next(f for f in report.findings if f.rule_id == "RL-13")
        assert "RL-13" in finding.message
        assert "advisory only" in finding.message
        assert finding.node_id is not None
        assert finding.node_id in finding.message


class TestReadingLevelWithinBand:
    """No RL-13 finding is emitted when a node is within the tolerance band."""

    def test_no_finding_when_in_band(self) -> None:
        """Simple body against a very forgiving wide tolerance produces no finding."""
        # Use a very wide tolerance (20 grade levels) so the easy body is always inside.
        story = _make_story(_EASY_BODY, target=4.0, tolerance=20.0)
        report = check_reading_level(story)
        rl13 = [f for f in report.findings if f.rule_id == "RL-13"]
        assert rl13 == [], (
            "No RL-13 finding expected when the body is within the wide tolerance band"
        )

    def test_report_ok_when_in_band(self) -> None:
        """report.ok must be True when no findings are emitted."""
        story = _make_story(_EASY_BODY, target=4.0, tolerance=20.0)
        report = check_reading_level(story)
        assert report.ok is True


class TestReadingLevelFloor:
    """Nodes with body below _MIN_WORDS_FOR_FK are skipped regardless of content."""

    def test_short_body_skipped(self) -> None:
        """A body below the word-count floor produces no RL-13 finding."""
        short = _short_body()
        # Confirm it is actually below the floor.
        assert len(short.split()) < _MIN_WORDS_FOR_FK
        # Use a very tight band that would normally flag even a moderate text.
        story = _make_story(short, target=2.0, tolerance=0.0)
        report = check_reading_level(story)
        rl13 = [f for f in report.findings if f.rule_id == "RL-13"]
        assert rl13 == [], (
            f"Node with {len(short.split())} words (< floor {_MIN_WORDS_FOR_FK}) "
            "must be skipped"
        )

    def test_report_ok_when_floor_skips(self) -> None:
        """report.ok is True when no findings are emitted due to floor."""
        short = _short_body()
        story = _make_story(short, target=2.0, tolerance=0.0)
        report = check_reading_level(story)
        assert report.ok is True


class TestReadingLevelFromFixture:
    """Smoke-test against the hello-world fixture: advisory semantics hold."""

    def test_fixture_report_ok(self) -> None:
        """hello_world fixture: report.ok is always True regardless of FK score."""
        story = Storybook.model_validate(
            json.loads(_VALID_FIXTURE.read_text(encoding="utf-8"))
        )
        report = check_reading_level(story)
        assert report.ok is True

    def test_fixture_no_error_findings(self) -> None:
        """hello_world fixture: no ERROR findings exist in the report."""
        story = Storybook.model_validate(
            json.loads(_VALID_FIXTURE.read_text(encoding="utf-8"))
        )
        report = check_reading_level(story)
        assert report.errors == []
