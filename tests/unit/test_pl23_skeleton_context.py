"""Unit tests for PL-23's skeleton-context direction report (UW-C256).

AL-380 found that PL-23 (``metadata.estimated_minutes`` vs the derived
fastest-finish clock) already fires against a catalog skeleton, since its
node-word count reads a ``<<FILL ... words=N ...>>`` directive's declared
``N`` instead of prose; a skeleton can therefore declare a clock its own
hints cannot satisfy before a single word is written. AL-384 measured the
catalog-wide incidence and found the breaches split into two populations
needing different remedies: an UNDER-declared skeleton is a plain metadata
error (a hint-sized fill will overrun the clock), while an OVER-declared one
more often means the author recorded a typical read rather than ADR-011's
fastest-finish definition. PL-23's own finding message does not say which
way a breach runs.

These tests cover the two new pieces this ticket adds:

* ``validator.policy.read_time_drift``: the direction-aware measurement,
  built on the same ``words_on_shortest_satisfying_path`` search PL-23
  itself uses (not a reimplementation).
* ``scripts.check_skeleton._read_time_direction_report``: the skeleton-time
  report that names the declared minutes, the derived minutes, and the
  breach direction, printed unconditionally (no ``--headroom``/``--strict``
  needed), without changing PL-23's own severity, message, or applicability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

import scripts.check_skeleton as check_skeleton
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.policy import (
    read_time_drift,
    words_on_shortest_satisfying_path,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Shared fixture: a small, gate-clean 3-5 band skeleton whose shortest
# satisfying path is a fixed 282 words (n_open 17 + n_hall 12 + the FILL
# hints below), so at the band's 100 wpm pace the derived clock is a fixed
# 3 minutes (round(282 / 100) == 3) regardless of the declared value under
# test. Only ``estimated_minutes`` varies between the under/over/in-tolerance
# cases. The three sibling "discovery" endings keep node/ending counts inside
# L1-7's MVP envelope and PL-17's band floors (3-5: min_endings=2,
# min_decisions=1) without disturbing the shortest satisfying path, which
# runs through the single "completion" ending, n_end_a.
# ---------------------------------------------------------------------------


def _make_skeleton(estimated_minutes: int, story_id: str = "sk_test") -> dict[str, Any]:
    """Build a small, gate-clean 3-5 skeleton with a fixed 282-word clock path."""
    return {
        "schema_version": "2.0",
        "id": story_id,
        "version": 1,
        "title": "Test",
        "metadata": {
            "age_band": "3-5",
            "reading_level": {"target": 1.5},
            "tier": 1,
            "estimated_minutes": estimated_minutes,
            "ending_count": 4,
            "topology": "time_cave",
        },
        "variables": [],
        "start_node": "n_open",
        "nodes": [
            {
                "id": "n_open",
                "body": (
                    "You wake up in a cozy little room and stretch your arms "
                    "wide awake now."
                ),
                "is_ending": False,
                "choices": [{"id": "c_open", "label": "Go on.", "target": "n_hall"}],
            },
            {
                "id": "n_hall",
                "body": (
                    "You walk down the little hallway toward the warm morning "
                    "kitchen light."
                ),
                "is_ending": False,
                "choices": [{"id": "c_hall", "label": "Go on.", "target": "n_start"}],
            },
            {
                "id": "n_start",
                "body": "<<FILL role=setup words=85 beats='intro'>>",
                "is_ending": False,
                "choices": [
                    {"id": "c1", "label": "Path A", "target": "n_passage"},
                    {"id": "c2", "label": "Path B", "target": "n_end_b"},
                    {"id": "c3", "label": "Path C", "target": "n_end_c"},
                    {"id": "c4", "label": "Path D", "target": "n_end_d"},
                ],
            },
            {
                "id": "n_passage",
                "body": "<<FILL role=beat words=85 beats='middle'>>",
                "is_ending": False,
                "choices": [{"id": "c3a", "label": "Continue", "target": "n_end_a"}],
            },
            {
                "id": "n_end_a",
                "body": "<<FILL role=ending words=85 beats='happy end'>>",
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "Home",
                },
            },
            {
                "id": "n_end_b",
                "body": "You found a friendly bird along the way today.",
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "neutral",
                    "kind": "discovery",
                    "title": "Bird",
                },
            },
            {
                "id": "n_end_c",
                "body": "You found a shiny pebble on the little path.",
                "is_ending": True,
                "ending": {
                    "id": "e_c",
                    "valence": "neutral",
                    "kind": "discovery",
                    "title": "Pebble",
                },
            },
            {
                "id": "n_end_d",
                "body": "You spotted a butterfly resting on a leaf nearby.",
                "is_ending": True,
                "ending": {
                    "id": "e_d",
                    "valence": "neutral",
                    "kind": "discovery",
                    "title": "Butterfly",
                },
            },
        ],
    }


# The fastest-finish clock the fixture's 282 words yield at the 3-5 band's
# 100 wpm anchor (round(282 / 100) == 3). Declared values are chosen well
# outside PL-23's 25% tolerance in each breaching direction.
_DERIVED_MINUTES = 3
_UNDER_DECLARED_MINUTES = 1  # drift 67%, declared < derived
_OVER_DECLARED_MINUTES = 30  # drift 900%, declared > derived
_IN_TOLERANCE_MINUTES = 3  # drift 0%, declared == derived


# ---------------------------------------------------------------------------
# validator.policy.read_time_drift (direct, Storybook-level)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_read_time_drift_flags_under_declared_skeleton() -> None:
    """A skeleton whose hints outrun its declared clock is under-declared."""
    story = Storybook.model_validate(_make_skeleton(_UNDER_DECLARED_MINUTES))
    drift = read_time_drift(story)
    assert drift is not None
    assert drift.declared_minutes == _UNDER_DECLARED_MINUTES
    assert drift.derived_minutes == _DERIVED_MINUTES
    assert drift.direction == "under-declared"
    assert drift.breaches_tolerance is True


@pytest.mark.unit
def test_read_time_drift_flags_over_declared_skeleton() -> None:
    """A skeleton declaring far more time than its hints need is over-declared."""
    story = Storybook.model_validate(_make_skeleton(_OVER_DECLARED_MINUTES))
    drift = read_time_drift(story)
    assert drift is not None
    assert drift.declared_minutes == _OVER_DECLARED_MINUTES
    assert drift.derived_minutes == _DERIVED_MINUTES
    assert drift.direction == "over-declared"
    assert drift.breaches_tolerance is True


@pytest.mark.unit
def test_read_time_drift_reports_no_breach_within_tolerance() -> None:
    """A declared value matching the derived clock does not breach tolerance."""
    story = Storybook.model_validate(_make_skeleton(_IN_TOLERANCE_MINUTES))
    drift = read_time_drift(story)
    assert drift is not None
    assert drift.direction == "exact"
    assert drift.drift == pytest.approx(0.0)
    assert drift.breaches_tolerance is False


@pytest.mark.unit
def test_read_time_drift_reuses_words_on_shortest_satisfying_path() -> None:
    """The derived clock is built on the same helper PL-23 itself calls.

    Locks in the "reuse, don't reimplement" requirement: the fixture's fixed
    282-word shortest satisfying path (17 + 12 real-prose words, plus the
    85 + 85 + 85 FILL hints on the path through n_start -> n_passage ->
    n_end_a) must come from the same search PL-23 uses, not a second
    implementation that could silently drift from it.
    """
    story = Storybook.model_validate(_make_skeleton(_IN_TOLERANCE_MINUTES))
    words = words_on_shortest_satisfying_path(story)
    drift = read_time_drift(story)
    assert words == 282
    assert drift is not None
    assert drift.words == words


# ---------------------------------------------------------------------------
# scripts.check_skeleton._read_time_direction_report (skeleton-context report)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_direction_report_names_declared_derived_and_under_direction() -> None:
    """The report names both minute values and says UNDER-DECLARED."""
    report = check_skeleton._read_time_direction_report(
        _make_skeleton(_UNDER_DECLARED_MINUTES)
    )
    assert report is not None
    assert "PL-23" in report
    assert f"estimated_minutes {_UNDER_DECLARED_MINUTES}" in report
    assert "UNDER-DECLARED" in report
    assert f"{_DERIVED_MINUTES} min" in report


@pytest.mark.unit
def test_direction_report_names_declared_derived_and_over_direction() -> None:
    """The report names both minute values and says OVER-DECLARED."""
    report = check_skeleton._read_time_direction_report(
        _make_skeleton(_OVER_DECLARED_MINUTES)
    )
    assert report is not None
    assert "PL-23" in report
    assert f"estimated_minutes {_OVER_DECLARED_MINUTES}" in report
    assert "OVER-DECLARED" in report
    assert f"{_DERIVED_MINUTES} min" in report


@pytest.mark.unit
def test_direction_report_is_none_within_tolerance() -> None:
    """No report is produced when the declared clock is within tolerance."""
    assert (
        check_skeleton._read_time_direction_report(
            _make_skeleton(_IN_TOLERANCE_MINUTES)
        )
        is None
    )


# ---------------------------------------------------------------------------
# End-to-end via scripts/check_skeleton.py's CLI, proving the report is
# printed on a bare invocation: no --headroom, no --strict (UW-C256's "runs
# when a skeleton is validated", not only under an authoring flag).
# ---------------------------------------------------------------------------


def _write_skeleton(tmp_path: Path, estimated_minutes: int, name: str) -> Path:
    import json

    path = tmp_path / name
    path.write_text(
        json.dumps(
            _make_skeleton(estimated_minutes, story_id=name.removesuffix(".json"))
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.unit
def test_check_skeleton_prints_under_declared_direction_without_extra_flags(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bare invocation (no --headroom/--strict) reports the direction."""
    path = _write_skeleton(tmp_path, _UNDER_DECLARED_MINUTES, "under.json")
    exit_code = check_skeleton.main([str(path), "--allow-mvp"])
    out = capsys.readouterr().out
    assert "skeleton clock: PL-23" in out
    assert "UNDER-DECLARED" in out
    # PL-23 is advisory: it must not become a blocking failure on its own.
    assert exit_code == 0


@pytest.mark.unit
def test_check_skeleton_prints_over_declared_direction_without_extra_flags(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bare invocation (no --headroom/--strict) reports the direction."""
    path = _write_skeleton(tmp_path, _OVER_DECLARED_MINUTES, "over.json")
    exit_code = check_skeleton.main([str(path), "--allow-mvp"])
    out = capsys.readouterr().out
    assert "skeleton clock: PL-23" in out
    assert "OVER-DECLARED" in out
    assert exit_code == 0


@pytest.mark.unit
def test_check_skeleton_prints_nothing_extra_when_within_tolerance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No direction line, and no gate PL-23 finding, when within tolerance."""
    path = _write_skeleton(tmp_path, _IN_TOLERANCE_MINUTES, "in_tolerance.json")
    exit_code = check_skeleton.main([str(path), "--allow-mvp"])
    out = capsys.readouterr().out
    assert "skeleton clock: PL-23" not in out
    assert "PL-23" not in out
    assert exit_code == 0


@pytest.mark.unit
def test_check_skeleton_keeps_the_gates_own_pl23_warning_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The direction report supplements PL-23; it does not replace it.

    Regression guard for the "keep fill-time PL-23 behaviour unchanged"
    constraint: the gate's own advisory finding (identical wording to the
    fill-time check, since it is the same code) must still appear alongside
    the new direction line.
    """
    path = _write_skeleton(tmp_path, _OVER_DECLARED_MINUTES, "over.json")
    check_skeleton.main([str(path), "--allow-mvp"])
    out = capsys.readouterr().out
    assert "WARNING PL-23" in out
    assert "(advisory only)" in out
    assert "differs from the derived fastest-finish clock" in out
    assert "skeleton clock: PL-23" in out
