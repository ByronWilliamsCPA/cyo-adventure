"""Unit tests for scripts/run_notification_digest.py (no network, no real DB).

scripts/ is not an importable package (no __init__.py, by design; see the
INP per-file-ignore for scripts/**/*.py in pyproject.toml), so the module is
loaded directly from its file path via importlib, mirroring
tests/unit/test_remoderate_books.py.

Mocked session/engine: the digest logic itself (notifications/digest.py) is
proven against a real database in
tests/integration/test_notification_digest.py; this file only proves the
script wires the session and commits correctly.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "run_notification_digest",
    Path(__file__).resolve().parents[2] / "scripts" / "run_notification_digest.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
run_notification_digest_script = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = run_notification_digest_script
_SPEC.loader.exec_module(run_notification_digest_script)

pytestmark = pytest.mark.unit


def _mock_session_factory(session: AsyncMock) -> MagicMock:
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_ctx)


@pytest.mark.asyncio
async def test_run_once_commits_after_the_whole_pass() -> None:
    """One commit for the whole pass, after run_notification_digest returns."""
    session = AsyncMock()
    now = datetime(2026, 8, 9, tzinfo=UTC)

    with patch.object(
        run_notification_digest_script,
        "run_notification_digest",
        AsyncMock(return_value=3),
    ) as mock_digest:
        written = await run_notification_digest_script.run_once(
            session_factory=_mock_session_factory(session), now=now
        )

    assert written == 3
    mock_digest.assert_awaited_once_with(session, now=now)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_once_defaults_now_to_the_real_current_time() -> None:
    """Omitting ``now`` still runs; a real UTC datetime is passed through."""
    session = AsyncMock()

    with patch.object(
        run_notification_digest_script,
        "run_notification_digest",
        AsyncMock(return_value=0),
    ) as mock_digest:
        await run_notification_digest_script.run_once(
            session_factory=_mock_session_factory(session)
        )

    passed_now = mock_digest.await_args.kwargs["now"]
    assert passed_now.tzinfo is not None
