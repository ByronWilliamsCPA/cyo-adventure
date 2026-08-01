"""Unit tests for scripts/remoderate_books.py (no network, no real DB).

scripts/ is not an importable package (no __init__.py, by design; see the
INP per-file-ignore for scripts/**/*.py in pyproject.toml), so the module is
loaded directly from its file path via importlib, mirroring
tests/unit/test_seed_moderation_qa.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cyo_adventure.core.exceptions import ResourceNotFoundError
from cyo_adventure.db.models import Storybook
from cyo_adventure.events.models import SYSTEM_ACTOR_ROLE

_SPEC = importlib.util.spec_from_file_location(
    "remoderate_books",
    Path(__file__).resolve().parents[2] / "scripts" / "remoderate_books.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
remoderate_books = importlib.util.module_from_spec(_SPEC)
# scripts/remoderate_books.py declares @dataclass classes; on 3.14, dataclass
# processing looks the defining module up via sys.modules[cls.__module__] (for
# ClassVar/InitVar detection), which is only populated for modules imported
# the normal way. A dynamically loaded module needs this registration done
# manually before exec_module runs the class body, or the dataclass decorator
# raises AttributeError on a None module lookup (see
# tests/unit/test_moderation_qa_scorecard.py for the same fix).
sys.modules[_SPEC.name] = remoderate_books
_SPEC.loader.exec_module(remoderate_books)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _is_mock_moderated: pure classification logic
# ---------------------------------------------------------------------------


def test_is_mock_moderated_returns_false_for_no_report() -> None:
    assert remoderate_books._is_mock_moderated(None) is False


def test_is_mock_moderated_returns_false_for_clean_independent_report() -> None:
    report = {
        "findings": [],
        "summary": {"reviewer_independent": True, "hard_block": False},
    }
    assert remoderate_books._is_mock_moderated(report) is False


def test_is_mock_moderated_true_on_reviewer_independent_false() -> None:
    report = {"findings": [], "summary": {"reviewer_independent": False}}
    assert remoderate_books._is_mock_moderated(report) is True


def test_is_mock_moderated_true_on_mock_reviewer_active_concern() -> None:
    report = {
        "findings": [{"concern": "mock_reviewer_active", "message": "mock active"}],
        "summary": {"reviewer_independent": True},
    }
    assert remoderate_books._is_mock_moderated(report) is True


def test_is_mock_moderated_true_on_reviewer_unavailable_concern() -> None:
    report = {
        "findings": [
            {
                "concern": "reviewer_unavailable",
                "message": "reviewer unavailable or unparseable on 3 node(s); "
                "defaulted to fail-safe",
            }
        ],
        "summary": {"reviewer_independent": True},
    }
    assert remoderate_books._is_mock_moderated(report) is True


def test_is_mock_moderated_true_on_legacy_message_substring() -> None:
    """Pre-collapse reports may carry the literal message with no concern tag."""
    report = {
        "findings": [
            {"concern": None, "message": "unknown verdict; defaulted to fail-safe"}
        ],
        "summary": {"reviewer_independent": True},
    }
    assert remoderate_books._is_mock_moderated(report) is True


def test_is_mock_moderated_false_when_findings_missing_or_malformed() -> None:
    assert remoderate_books._is_mock_moderated({"summary": {}}) is False
    assert remoderate_books._is_mock_moderated({"summary": {}, "findings": "bad"}) is (
        False
    )
    assert (
        remoderate_books._is_mock_moderated({"summary": {}, "findings": ["not-a-dict"]})
        is False
    )


# ---------------------------------------------------------------------------
# list_mock_moderated_targets
# ---------------------------------------------------------------------------


def _storybook(book_id: str, *, current_published_version: int | None = 2) -> Storybook:
    return Storybook(
        id=book_id,
        status="published",
        current_published_version=current_published_version,
    )


def _version_row_stub(moderation_report: dict[str, object] | None) -> MagicMock:
    row = MagicMock()
    row.moderation_report = moderation_report
    return row


@pytest.mark.asyncio
async def test_list_mock_moderated_targets_filters_and_sorts() -> None:
    books = [_storybook("s_zebra"), _storybook("s_apple")]
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=books)
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    async def _get(_model: Any, key: tuple[str, int]) -> MagicMock:
        story_id, _version = key
        report: dict[str, object] = {
            "summary": {"reviewer_independent": story_id != "s_apple"}
        }
        return _version_row_stub(report)

    session.get = AsyncMock(side_effect=_get)

    targets = await remoderate_books.list_mock_moderated_targets(session)

    assert targets == [("s_apple", 2)]


@pytest.mark.asyncio
async def test_list_mock_moderated_targets_skips_books_with_no_current_version() -> (
    None
):
    books = [_storybook("s_draftish", current_published_version=None)]
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=books)
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    session.get = AsyncMock()

    targets = await remoderate_books.list_mock_moderated_targets(session)

    assert targets == []
    session.get.assert_not_awaited()


# ---------------------------------------------------------------------------
# _resolve_book_id_targets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_book_id_targets_returns_current_published_version() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=_storybook("s1", current_published_version=3))

    targets = await remoderate_books._resolve_book_id_targets(session, ["s1"])

    assert targets == [("s1", 3)]


@pytest.mark.asyncio
async def test_resolve_book_id_targets_raises_404_for_unknown_book() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    with pytest.raises(ResourceNotFoundError):
        await remoderate_books._resolve_book_id_targets(session, ["missing"])


@pytest.mark.asyncio
async def test_resolve_book_id_targets_raises_404_for_no_published_version() -> None:
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=_storybook("s1", current_published_version=None)
    )

    with pytest.raises(ResourceNotFoundError):
        await remoderate_books._resolve_book_id_targets(session, ["s1"])


# ---------------------------------------------------------------------------
# sweep(): selector validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sweep_raises_when_neither_selector_given() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        await remoderate_books.sweep()


@pytest.mark.asyncio
async def test_sweep_raises_when_both_selectors_given() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        await remoderate_books.sweep(book_ids=["s1"], mock_moderated=True)


# ---------------------------------------------------------------------------
# sweep(): dry-run listing (exit-gate requirement)
# ---------------------------------------------------------------------------


def _mock_engine() -> MagicMock:
    return MagicMock()


def _mock_session_factory(session: AsyncMock) -> MagicMock:
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_ctx)


@pytest.mark.asyncio
async def test_sweep_dry_run_lists_targets_without_calling_remoderate() -> None:
    """The exit-gate's 'script dry-run listing' test.

    Dry-run (execute=False, the default) must resolve and return the target
    list but never call remoderate_storybook_version and never commit: no
    row is touched, no LLM call is made.
    """
    session = AsyncMock()
    books = [_storybook("s_a"), _storybook("s_b")]
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=books)
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)
    session.execute = AsyncMock(return_value=execute_result)
    session.get = AsyncMock(
        side_effect=lambda _model, _key: _version_row_stub(
            {"summary": {"reviewer_independent": False}}
        )
    )
    session.commit = AsyncMock()

    remoderate_fn = AsyncMock()
    with patch.object(remoderate_books, "remoderate_storybook_version", remoderate_fn):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            mock_moderated=True,
            execute=False,
        )

    assert result.executed is False
    assert result.targets == [("s_a", 2), ("s_b", 2)]
    assert result.succeeded == []
    assert result.failed == []
    remoderate_fn.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_dry_run_with_explicit_book_ids_never_calls_remoderate() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=_storybook("s1", current_published_version=1))
    session.commit = AsyncMock()

    remoderate_fn = AsyncMock()
    with patch.object(remoderate_books, "remoderate_storybook_version", remoderate_fn):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            book_ids=["s1"],
            execute=False,
        )

    assert result.targets == [("s1", 1)]
    assert result.executed is False
    remoderate_fn.assert_not_awaited()
    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# sweep(): execute mode
# ---------------------------------------------------------------------------


class _FakeSavepoint:
    """Stand-in for ``AsyncSession.begin_nested()``, mirrors test_seed_moderation_qa.py."""

    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def __aenter__(self) -> _FakeSavepoint:
        self._log.append("enter")
        return self

    async def __aexit__(self, exc_type: object, _exc: object, _tb: object) -> bool:
        self._log.append("rollback" if exc_type is not None else "commit")
        return False


def _execute_session(book_ids: list[str]) -> tuple[AsyncMock, list[str]]:
    session = AsyncMock()
    session.get = AsyncMock(
        side_effect=lambda _model, book_id: _storybook(
            book_id, current_published_version=1
        )
    )
    session.commit = AsyncMock()
    log: list[str] = []
    session.begin_nested = MagicMock(side_effect=lambda: _FakeSavepoint(log))
    return session, log


@pytest.mark.asyncio
async def test_sweep_execute_calls_remoderate_with_system_actor_per_target() -> None:
    session, _log = _execute_session(["s1", "s2"])
    remoderate_fn = AsyncMock()

    with patch.object(remoderate_books, "remoderate_storybook_version", remoderate_fn):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            book_ids=["s1", "s2"],
            execute=True,
        )

    assert result.executed is True
    assert result.succeeded == [("s1", 1), ("s2", 1)]
    assert result.failed == []
    assert remoderate_fn.await_count == 2
    for call in remoderate_fn.await_args_list:
        ctx = call.args[3]
        assert ctx.actor.actor_role == SYSTEM_ACTOR_ROLE
        assert ctx.actor.actor_id is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sweep_continues_after_one_failure() -> None:
    """A single book's failure is isolated by its own savepoint, not fatal."""
    session, log = _execute_session(["s_bad", "s_good"])

    async def _fake_remoderate(
        _session: object, storybook_id: str, _version: int, _ctx: object
    ) -> None:
        if storybook_id == "s_bad":
            msg = "provider timeout"
            raise RuntimeError(msg)

    with patch.object(
        remoderate_books,
        "remoderate_storybook_version",
        AsyncMock(side_effect=_fake_remoderate),
    ):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            book_ids=["s_bad", "s_good"],
            execute=True,
        )

    assert result.succeeded == [("s_good", 1)]
    assert result.failed == [("s_bad", 1)]
    assert log == ["enter", "rollback", "enter", "commit"]
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# _parse_args
# ---------------------------------------------------------------------------


def test_parse_args_defaults_execute_to_false() -> None:
    args = remoderate_books._parse_args(["--mock-moderated"])
    assert args.execute is False
    assert args.mock_moderated is True
    assert args.book_id is None


def test_parse_args_book_id_is_repeatable() -> None:
    args = remoderate_books._parse_args(
        ["--book-id", "s1", "--book-id", "s2", "--execute"]
    )
    assert args.book_id == ["s1", "s2"]
    assert args.execute is True


def test_parse_args_rejects_both_selectors(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        remoderate_books._parse_args(["--book-id", "s1", "--mock-moderated"])
    captured = capsys.readouterr()
    assert "not allowed with" in captured.err


def test_parse_args_requires_a_selector(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        remoderate_books._parse_args([])
    captured = capsys.readouterr()
    assert "one of the arguments" in captured.err
