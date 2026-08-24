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


def test_is_mock_moderated_true_on_fail_safe_message_substring() -> None:
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


@pytest.mark.asyncio
async def test_list_mock_moderated_targets_skips_missing_version_row() -> None:
    """A dangling current_published_version pointer is skipped, not fatal.

    One book whose version row is missing must not make the whole sweep
    unselectable. Such a book is also unreadable by a child (the reader loads
    the same row), so skipping it hides nothing a reader would see.
    """
    books = [_storybook("s_dangling"), _storybook("s_real")]
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=books)
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    async def _get(_model: Any, key: tuple[str, int]) -> MagicMock | None:
        story_id, _version = key
        if story_id == "s_dangling":
            return None
        return _version_row_stub({"summary": {"reviewer_independent": False}})

    session.get = AsyncMock(side_effect=_get)

    targets = await remoderate_books.list_mock_moderated_targets(session)

    assert targets == [("s_real", 2)]


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


@pytest.mark.asyncio
async def test_resolve_book_id_targets_collapses_duplicate_ids() -> None:
    """A repeated --book-id yields one target, in first-occurrence order.

    Sweeping the same book twice would make the full review-model fan-out
    twice to reach one result (the second report overwrites the first) while
    reporting the book as two successes.
    """
    session = AsyncMock()
    session.get = AsyncMock(
        side_effect=lambda _model, book_id: _storybook(
            book_id, current_published_version=1
        )
    )

    targets = await remoderate_books._resolve_book_id_targets(
        session, ["s2", "s1", "s2", "s1", "s2"]
    )

    assert targets == [("s2", 1), ("s1", 1)]
    assert session.get.await_count == 2


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


def _execute_session(book_ids: list[str]) -> tuple[AsyncMock, list[str]]:
    """Build a session that records the ORDER of commit/rollback calls.

    The sweep commits per book rather than once at the end, so the ordering
    is the assertion that matters: a commit between books is what makes an
    already-succeeded book durable and releases its ``FOR UPDATE`` row lock.
    """
    del book_ids
    session = AsyncMock()
    session.get = AsyncMock(
        side_effect=lambda _model, book_id: _storybook(
            book_id, current_published_version=1
        )
    )
    log: list[str] = []
    session.commit = AsyncMock(side_effect=lambda: log.append("commit"))
    session.rollback = AsyncMock(side_effect=lambda: log.append("rollback"))
    return session, log


def _verdict(overall: str) -> MagicMock:
    """A stand-in for the RemoderateResult the entry point returns."""
    result = MagicMock()
    result.overall_verdict = overall
    return result


@pytest.mark.asyncio
async def test_sweep_execute_calls_remoderate_with_system_actor_per_target() -> None:
    session, _log = _execute_session(["s1", "s2"])
    remoderate_fn = AsyncMock(return_value=_verdict("pass"))

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
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_sweep_commits_after_each_book() -> None:
    """Durability and lock release both depend on committing per book.

    A sweep-wide transaction (the savepoint-only shape) would leave every
    already-processed book uncommitted until the very end, so a crash on the
    last book would discard all prior work and the LLM spend behind it, and
    Postgres would hold each book's ``SELECT ... FOR UPDATE`` lock for the
    whole run, blocking concurrent admin actions on all of them.
    """
    session, log = _execute_session(["s1", "s2", "s3"])
    remoderate_fn = AsyncMock(return_value=_verdict("pass"))

    with patch.object(remoderate_books, "remoderate_storybook_version", remoderate_fn):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            book_ids=["s1", "s2", "s3"],
            execute=True,
        )

    assert result.succeeded == [("s1", 1), ("s2", 1), ("s3", 1)]
    assert log == ["commit", "commit", "commit"]
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_continues_after_one_failure() -> None:
    """A single book's failure rolls back alone; earlier books stay committed."""
    session, log = _execute_session(["s_bad", "s_good"])

    async def _fake_remoderate(
        _session: object, storybook_id: str, _version: int, _ctx: object
    ) -> MagicMock:
        if storybook_id == "s_bad":
            msg = "provider timeout"
            raise RuntimeError(msg)
        return _verdict("pass")

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
    assert log == ["rollback", "commit"]


@pytest.mark.asyncio
async def test_sweep_records_blocked_and_flagged_verdicts() -> None:
    """A dirty verdict is a successful call, so it needs its own bucket.

    ADR-005 means a hard block changes nothing about the book: it stays
    published and readable. Counting it as a plain success (which it is, as a
    call) would hide exactly the outcome an operator has to act on.
    """
    session, _log = _execute_session(["s_block", "s_flag", "s_ok"])
    verdicts = {"s_block": "block", "s_flag": "flag", "s_ok": "pass"}

    async def _fake_remoderate(
        _session: object, storybook_id: str, _version: int, _ctx: object
    ) -> MagicMock:
        return _verdict(verdicts[storybook_id])

    with patch.object(
        remoderate_books,
        "remoderate_storybook_version",
        AsyncMock(side_effect=_fake_remoderate),
    ):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            book_ids=["s_block", "s_flag", "s_ok"],
            execute=True,
        )

    assert result.succeeded == [("s_block", 1), ("s_flag", 1), ("s_ok", 1)]
    assert result.failed == []
    assert result.blocked == [("s_block", 1)]
    assert result.flagged == [("s_flag", 1)]


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


# ---------------------------------------------------------------------------
# main(): the operator-facing signal
# ---------------------------------------------------------------------------


def _run_main(result: Any) -> None:
    """Drive main() with a canned SweepResult, bypassing argv and the DB."""
    args = MagicMock(book_id=["s1"], mock_moderated=False, execute=True)
    with (
        patch.object(remoderate_books, "_parse_args", MagicMock(return_value=args)),
        patch.object(remoderate_books, "sweep", AsyncMock(return_value=result)),
    ):
        remoderate_books.main()


def test_main_exits_nonzero_when_a_book_is_blocked(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A hard block is a SUCCESSFUL call whose outcome still needs a human.

    The sweep never changes status (ADR-005 reserves that for a person), so a
    blocked book is exactly where it was: a published one still readable by a
    child, an in_review one still queued. A zero exit here would report "sweep
    clean" over a book that just failed moderation.
    """
    result = remoderate_books.SweepResult(
        targets=[("s1", 1)],
        executed=True,
        succeeded=[("s1", 1)],
        blocked=[("s1", 1)],
    )

    with pytest.raises(SystemExit) as excinfo:
        _run_main(result)

    assert excinfo.value.code is not None
    assert "1 book(s) hard-blocked" in str(excinfo.value.code)
    out = capsys.readouterr().out
    assert "HARD BLOCK, status unchanged by this sweep" in out
    # The published consequence must survive verbatim: it is the half that
    # means a child can read a blocked book right now.
    assert "STILL readable by a child" in out
    assert "s1 v1" in out


def test_main_exits_zero_when_every_book_comes_back_clean(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = remoderate_books.SweepResult(
        targets=[("s1", 1)],
        executed=True,
        succeeded=[("s1", 1)],
    )

    _run_main(result)

    out = capsys.readouterr().out
    assert "1 succeeded (0 blocked, 0 flagged), 0 failed." in out
    assert "HARD BLOCK" not in out


def test_main_reports_soft_flags_without_exiting_nonzero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A soft flag is worth printing but is not an emergency.

    It does not gate the exit code: unlike a hard block, a flagged book was
    already publishable under the same thresholds a human approved it under.
    """
    result = remoderate_books.SweepResult(
        targets=[("s1", 1)],
        executed=True,
        succeeded=[("s1", 1)],
        flagged=[("s1", 1)],
    )

    _run_main(result)

    out = capsys.readouterr().out
    assert "soft-flagged (status unchanged by this sweep, review when" in out


def test_main_exits_nonzero_when_a_book_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = remoderate_books.SweepResult(
        targets=[("s1", 1)],
        executed=True,
        failed=[("s1", 1)],
    )

    with pytest.raises(SystemExit) as excinfo:
        _run_main(result)

    assert "1 book(s) failed" in str(excinfo.value.code)
    assert "failed (rolled back, retry by re-running)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# list_in_review_targets and the in_review arm of _resolve_book_id_targets
# ---------------------------------------------------------------------------


def _in_review_storybook(book_id: str) -> Storybook:
    return Storybook(id=book_id, status="in_review", current_published_version=None)


def _grouped_max_session(
    books: list[Storybook], latest: list[tuple[str, int]]
) -> AsyncMock:
    """Build a session whose two execute() calls return books then max-versions.

    Args:
        books: Rows the storybook listing query returns.
        latest: ``(storybook_id, max_version)`` rows the grouped query returns.

    Returns:
        An ``AsyncMock`` session wired for exactly that two-query sequence.
    """
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=books)
    books_result = MagicMock()
    books_result.scalars = MagicMock(return_value=scalars_result)
    latest_result = MagicMock()
    latest_result.all = MagicMock(return_value=latest)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[books_result, latest_result])
    return session


@pytest.mark.asyncio
async def test_list_in_review_targets_returns_latest_version_per_book() -> None:
    """An in_review book is targeted at its HIGHEST version, sorted by id.

    That is the same version the admin review queue shows
    (api/approval.py::_latest_version), so the sweep re-derives the verdicts a
    reviewer is actually looking at rather than a superseded draft's.
    """
    session = _grouped_max_session(
        [_in_review_storybook("s_zebra"), _in_review_storybook("s_apple")],
        [("s_zebra", 4), ("s_apple", 2)],
    )

    targets = await remoderate_books.list_in_review_targets(session)

    assert targets == [("s_apple", 2), ("s_zebra", 4)]


@pytest.mark.asyncio
async def test_list_in_review_targets_skips_books_with_no_version_row() -> None:
    """A versionless in_review book is skipped, not fatal, mirroring the queue."""
    session = _grouped_max_session(
        [_in_review_storybook("s_ok"), _in_review_storybook("s_versionless")],
        [("s_ok", 1)],
    )

    targets = await remoderate_books.list_in_review_targets(session)

    assert targets == [("s_ok", 1)]


@pytest.mark.asyncio
async def test_list_in_review_targets_skips_the_version_query_when_empty() -> None:
    """No in_review books means no degenerate empty IN query is issued."""
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[])
    books_result = MagicMock()
    books_result.scalars = MagicMock(return_value=scalars_result)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=books_result)

    targets = await remoderate_books.list_in_review_targets(session)

    assert targets == []
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_resolve_book_id_targets_uses_latest_version_for_in_review_book() -> None:
    """An explicitly named in_review book resolves, at its latest version.

    Before re-moderation admitted in_review, this raised 404: the book has no
    current_published_version and there was no other rule. It must not, or an
    operator cannot canary a single book before sweeping the rest.
    """
    session = AsyncMock()
    session.get = AsyncMock(return_value=_in_review_storybook("s_review"))
    session.scalar = AsyncMock(return_value=7)

    targets = await remoderate_books._resolve_book_id_targets(session, ["s_review"])

    assert targets == [("s_review", 7)]


@pytest.mark.asyncio
async def test_resolve_book_id_targets_raises_404_for_versionless_in_review() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=_in_review_storybook("s_empty"))
    session.scalar = AsyncMock(return_value=None)

    with pytest.raises(ResourceNotFoundError):
        await remoderate_books._resolve_book_id_targets(session, ["s_empty"])


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["archived", "needs_revision", "draft"])
async def test_resolve_book_id_targets_refuses_a_status_remoderation_rejects(
    status: str,
) -> None:
    """An inadmissible status raises here rather than reaching the endpoint's 400.

    Every fixture deliberately carries a RESOLVABLE version, both a live
    ``current_published_version`` and a max(version) row. Without that, the
    test passes with the status guard deleted, because the old
    "no current_published_version" raise catches a null-pointer fixture for
    entirely unrelated reasons; the status check is then never the thing under
    test. ``archived`` is the realistic case: an archived book keeps the
    publish pointer it had, so nothing but the status guard stops it.

    Failing at target resolution keeps ``--execute`` from touching a single
    book, rather than aborting mid-sweep after earlier books have already
    committed their re-moderations and spent the LLM calls.
    """
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=Storybook(id="s_x", status=status, current_published_version=2)
    )
    session.scalar = AsyncMock(return_value=3)

    with pytest.raises(ResourceNotFoundError, match="does not admit"):
        await remoderate_books._resolve_book_id_targets(session, ["s_x"])


@pytest.mark.asyncio
async def test_sweep_raises_when_two_of_three_selectors_given() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        await remoderate_books.sweep(mock_moderated=True, in_review=True)


@pytest.mark.asyncio
async def test_sweep_in_review_selects_via_list_in_review_targets() -> None:
    """--in-review routes selection to the in_review lister, and stays dry by default."""
    session = _grouped_max_session([_in_review_storybook("s_a")], [("s_a", 3)])
    with patch.object(
        remoderate_books, "remoderate_storybook_version", new=AsyncMock()
    ) as remod:
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            in_review=True,
        )

    assert result.targets == [("s_a", 3)]
    assert result.executed is False
    remod.assert_not_awaited()


def test_parse_args_accepts_in_review() -> None:
    args = remoderate_books._parse_args(["--in-review"])

    assert args.in_review is True
    assert args.mock_moderated is False
    assert args.book_id is None


def test_parse_args_rejects_in_review_with_mock_moderated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        remoderate_books._parse_args(["--in-review", "--mock-moderated"])
    assert "not allowed with argument" in capsys.readouterr().err
