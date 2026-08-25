"""Unit tests for scripts/check_moderation_report_health.py (no network, no real DB).

scripts/ is not an importable package (no __init__.py, by design; see the
INP per-file-ignore for scripts/**/*.py in pyproject.toml), so the module is
loaded directly from its file path via importlib, mirroring
tests/unit/test_run_notification_digest.py.

Mocked session: the shared predicate this script consumes
(moderation_report_unusable) is proven in
tests/unit/test_moderation_report.py; this file only proves the script's own
query dispatch, row-to-hit mapping, and exit-code contract.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_moderation_report_health",
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "check_moderation_report_health.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
check_script = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_script
_SPEC.loader.exec_module(check_script)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 8, 25, tzinfo=UTC)

_INDEPENDENT_CLEAN_REPORT = {
    "findings": [],
    "summary": {"reviewer_independent": True, "hard_block": False, "soft_flag": False},
}
_MOCK_REVIEWED_REPORT = {
    "findings": [],
    "summary": {
        "reviewer_independent": False,
        "hard_block": False,
        "soft_flag": False,
    },
}
_GENUINE_BLOCK_REPORT = {
    "findings": [
        {
            "stage": 1,
            "source": "llm_safety",
            "category": "violence",
            "verdict": "block",
            "message": "too intense",
            "structural": False,
        }
    ],
    "summary": {"reviewer_independent": True, "hard_block": True, "soft_flag": False},
}


def _mock_session_factory(session: AsyncMock) -> MagicMock:
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_ctx)


def _mock_result(rows: list[tuple[object, ...]]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


class TestHitsFromRows:
    """Unit tests for the pure row-to-hit mapping (the report-side logic)."""

    def test_skips_rows_with_no_moderation_report(self) -> None:
        rows = [("story-1", 1, None, _NOW)]
        assert check_script._hits_from_rows(rows, "published") == []

    def test_flags_a_mock_reviewed_report(self) -> None:
        rows = [("story-1", 3, _MOCK_REVIEWED_REPORT, _NOW)]
        hits = check_script._hits_from_rows(rows, "published")
        assert hits == [
            check_script.UnusableReportHit(
                storybook_id="story-1", version=3, status="published", moderated_at=_NOW
            )
        ]

    def test_does_not_flag_an_independent_clean_report(self) -> None:
        rows = [("story-1", 1, _INDEPENDENT_CLEAN_REPORT, _NOW)]
        assert check_script._hits_from_rows(rows, "published") == []

    def test_does_not_flag_a_genuine_block(self) -> None:
        rows = [("story-1", 2, _GENUINE_BLOCK_REPORT, _NOW)]
        assert check_script._hits_from_rows(rows, "in_review") == []

    def test_stamps_the_given_status_label(self) -> None:
        rows = [("story-1", 1, _MOCK_REVIEWED_REPORT, _NOW)]
        hits = check_script._hits_from_rows(rows, "in_review")
        assert hits[0].status == "in_review"


@pytest.mark.asyncio
class TestFindUnusableReports:
    """Unit tests for the two-population query dispatch."""

    async def test_combines_published_and_in_review_hits(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _mock_result([("pub-1", 5, _MOCK_REVIEWED_REPORT, _NOW)]),
                _mock_result([("rev-1", 2, _MOCK_REVIEWED_REPORT, _NOW)]),
            ]
        )

        hits = await check_script.find_unusable_reports(session)

        assert {(h.storybook_id, h.status) for h in hits} == {
            ("pub-1", "published"),
            ("rev-1", "in_review"),
        }

    async def test_no_hits_when_both_populations_are_clean(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _mock_result([("pub-1", 5, _INDEPENDENT_CLEAN_REPORT, _NOW)]),
                _mock_result([]),
            ]
        )

        hits = await check_script.find_unusable_reports(session)

        assert hits == []


@pytest.mark.asyncio
async def test_run_once_does_not_commit_a_read_only_pass() -> None:
    """The script only reads; it must never open a write transaction."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_mock_result([]), _mock_result([])])

    hits = await check_script.run_once(session_factory=_mock_session_factory(session))

    assert hits == []
    session.commit.assert_not_called()


def test_main_exits_nonzero_when_hits_are_found(
    capsys: pytest.CaptureFixture[str],
) -> None:
    hit = check_script.UnusableReportHit(
        storybook_id="story-1", version=1, status="published", moderated_at=_NOW
    )
    with (
        patch.object(check_script, "run_once", AsyncMock(return_value=[hit])),
        pytest.raises(SystemExit) as exc_info,
    ):
        check_script.main()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "story-1 v1 status=published" in out
    assert "unusable_reports=1" in out


def test_main_exits_zero_when_no_hits_are_found(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(check_script, "run_once", AsyncMock(return_value=[])):
        check_script.main()

    assert "unusable_reports=0" in capsys.readouterr().out
