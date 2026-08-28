"""Unit tests for scripts/remoderate_books.py (no network, no real DB).

scripts/ is not an importable package (no __init__.py, by design; see the
INP per-file-ignore for scripts/**/*.py in pyproject.toml), so the module is
loaded directly from its file path via importlib, mirroring
tests/unit/test_seed_moderation_qa.py.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cyo_adventure.api.remoderate import RemoderateResult
from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import (
    BusinessLogicError,
    ResourceNotFoundError,
)
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


def _verdict(
    overall: str,
    *,
    coverage_complete: bool = True,
    block_findings: int | None = None,
) -> MagicMock:
    """A stand-in for the RemoderateResult the entry point returns.

    Every attribute the sweep reads is set explicitly. A bare MagicMock answers
    truthy for anything, so ``coverage_complete`` would read complete on a mock
    that never modelled it, and the classification this double exists to
    exercise would be untestable in the direction that matters.

    Args:
        overall: The rolled-up verdict, as ``_summarize_report`` returns it.
        coverage_complete: False for a report admitting an unjudged node. Such a
            report's ``overall`` is "block" by construction, so pass both.
        block_findings: How many findings carry a ``block`` verdict. Defaults to
            1 for a complete "block" report and 0 otherwise, which is the real
            relationship: ``summary.hard_block`` is ``any(verdict is BLOCK)``,
            and a fail-closed gap block has no such finding behind it.

    Returns:
        MagicMock: The stand-in result.
    """
    if block_findings is None:
        block_findings = 1 if overall == "block" and coverage_complete else 0
    result = MagicMock()
    result.overall_verdict = overall
    result.coverage_complete = coverage_complete
    result.verdict_counts = {"block": block_findings} if block_findings else {}
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
    assert result.incomplete == []


@pytest.mark.asyncio
async def test_sweep_separates_an_unreviewed_book_from_a_blocked_one() -> None:
    """An unjudged book and a refused book must land in different buckets.

    Both come back with ``overall_verdict == "block"``, because a coverage gap
    is fail-closed on purpose, so the verdict alone cannot separate them. The
    remedies are opposite: one needs the reviewer re-run, the other needs the
    prose rewritten. A sweep that filed both under ``blocked`` would print "act
    on these" over a story nothing has read, which is how the original
    fail-open stayed invisible.

    The third arm is the case that makes this more than a relabelling: a book
    with BOTH a real block finding and a gap belongs in both lists, because
    dropping either one loses a real signal.
    """
    ids = ["s_gap", "s_block", "s_both"]
    session, _log = _execute_session(ids)
    results = {
        "s_gap": _verdict("block", coverage_complete=False),
        "s_block": _verdict("block"),
        "s_both": _verdict("block", coverage_complete=False, block_findings=2),
    }

    async def _fake_remoderate(
        _session: object, storybook_id: str, _version: int, _ctx: object
    ) -> MagicMock:
        return results[storybook_id]

    with patch.object(
        remoderate_books,
        "remoderate_storybook_version",
        AsyncMock(side_effect=_fake_remoderate),
    ):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            book_ids=ids,
            execute=True,
        )

    assert result.incomplete == [("s_gap", 1), ("s_both", 1)]
    assert result.blocked == [("s_block", 1), ("s_both", 1)]
    assert result.flagged == []
    assert result.failed == []


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


def _settings_stub(*, provider: str, environment: str = "production") -> MagicMock:
    """A settings double carrying only what the preflight reads.

    Specced against ``Settings``' real field names, not left open: an
    unspecced MagicMock answers ANY attribute, so renaming a field on
    ``Settings`` would leave every test here passing while the script read a
    fresh Mock in place of the value. ``spec`` takes the name list rather
    than a ``Settings`` instance on purpose (see tests/CLAUDE.md, "Mock spec
    traps": a pydantic instance as ``spec`` trips ``__fields__`` on 3.12 and
    older).
    """
    return MagicMock(
        spec=list(Settings.model_fields),
        review_provider=provider,
        environment=environment,
        database_url=(
            f"postgresql+asyncpg://cyo_user:{_LEAK_CANARY}@db.example.net:5432/cyo"
        ),
    )


def _run_main(result: Any) -> None:
    """Drive main() with a canned SweepResult, bypassing argv and the DB.

    Declares a real review provider because these tests drive ``--execute``
    and measure what main REPORTS. Under the shared app settings the resolved
    provider is the mock, which main's preflight now refuses outright, so
    without this every one of them would exit on the preflight and assert
    nothing about the reporting they exist to pin. The preflight has its own
    tests below.
    """
    args = MagicMock(book_id=["s1"], mock_moderated=False, execute=True)
    with (
        patch.object(remoderate_books, "_parse_args", MagicMock(return_value=args)),
        patch.object(
            remoderate_books,
            "_default_settings",
            _settings_stub(provider="openrouter"),
        ),
        patch.object(remoderate_books, "sweep", AsyncMock(return_value=result)),
    ):
        remoderate_books.main()


def test_main_exits_retryable_when_a_book_was_reviewed_incompletely(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unjudged book exits RETRYABLE and must not read as a content block.

    Two claims, and both matter. The exit code is retryable because the gap is
    usually one flaky reviewer response and the retry is a genuinely different,
    smaller request; a human cannot fill in a judgment nobody made. And the
    stdout must NOT carry the hard-block wording, because that text tells an
    operator to act on the prose, which is precisely the wrong instruction for
    a story nothing has read yet. Asserting the exit code alone would pass on
    an implementation that printed "HARD BLOCK" over it.
    """
    result = remoderate_books.SweepResult(
        targets=[("s1", 1)],
        executed=True,
        succeeded=[("s1", 1)],
        incomplete=[("s1", 1)],
    )

    with pytest.raises(SystemExit) as excinfo:
        _run_main(result)

    assert excinfo.value.code == remoderate_books._EXIT_RETRYABLE
    captured = capsys.readouterr()
    assert "1 book(s) reviewed incompletely" in captured.err
    assert "RETRYABLE" in captured.err
    assert "NEEDS A HUMAN" not in captured.err
    out = captured.out
    assert "REVIEWED INCOMPLETELY" in out
    assert "reached NO safety judgment" in out
    assert "s1 v1" in out
    # The block wording prescribes the wrong remedy for this outcome.
    assert "HARD BLOCK" not in out
    assert "STILL readable by a child" not in out


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

    assert excinfo.value.code == remoderate_books._EXIT_NEEDS_HUMAN
    captured = capsys.readouterr()
    assert "1 book(s) hard-blocked" in captured.err
    assert "NEEDS A HUMAN" in captured.err
    out = captured.out
    assert "HARD BLOCK, status unchanged by this sweep" in out
    # The published consequence must survive verbatim: it is the half that
    # means a child can read a blocked book right now.
    assert "STILL readable by a child" in out
    assert "s1 v1" in out


def test_main_exits_nonzero_when_a_book_was_excluded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A book the listing could not target is a coverage gap, not a clean run.

    An excluded book is neither failed nor blocked, so before this it produced
    no exit-code signal at all: the sweep printed a tidy "1 target book(s)"
    and exited 0 while a second queued book went un-re-moderated.
    """
    result = remoderate_books.SweepResult(
        targets=[("s1", 1)],
        executed=True,
        succeeded=[("s1", 1)],
        excluded=["s_versionless"],
    )

    with pytest.raises(SystemExit) as excinfo:
        _run_main(result)

    assert excinfo.value.code == remoderate_books._EXIT_NEEDS_HUMAN
    captured = capsys.readouterr()
    assert "1 book(s) excluded" in captured.err
    assert "NEEDS A HUMAN" in captured.err
    out = captured.out
    assert "EXCLUDED from the target list" in out
    # The id has to be in the SUMMARY, not only in a structured log an
    # operator would have to be tailing separately to see.
    assert "s_versionless" in out


def test_main_exits_nonzero_when_every_book_was_excluded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The all-excluded case is the worst one: it looks like an empty queue.

    With no targets at all, main() takes its "no target books found" early
    return, which is indistinguishable from a genuinely empty review queue
    unless the exclusions are reported on that path too.
    """
    result = remoderate_books.SweepResult(
        targets=[], executed=True, excluded=["s_a", "s_b"]
    )

    with pytest.raises(SystemExit) as excinfo:
        _run_main(result)

    assert excinfo.value.code == remoderate_books._EXIT_NEEDS_HUMAN
    captured = capsys.readouterr()
    assert "2 in_review book(s)" in captured.err
    assert "s_a, s_b" in captured.out


def test_main_reports_exclusions_on_the_dry_run_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A dry run is where an operator checks coverage BEFORE spending on LLMs."""
    result = remoderate_books.SweepResult(
        targets=[("s1", 1)], executed=False, excluded=["s_versionless"]
    )

    with pytest.raises(SystemExit):
        _run_main(result)

    assert "s_versionless" in capsys.readouterr().out


def test_main_names_the_books_the_repair_pass_rewrote(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A repaired book's stored text is no longer what the reviewer last read.

    Rolled up with plain successes it is invisible, and a reviewer would
    approve prose they never saw.
    """
    result = remoderate_books.SweepResult(
        targets=[("s1", 1)],
        executed=True,
        succeeded=[("s1", 1)],
        repaired=[("s1", 1)],
    )

    _run_main(result)

    out = capsys.readouterr().out
    assert "REPAIRED" in out
    assert "re-read before approving" in out
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
    assert (
        "1 succeeded (0 blocked, 0 flagged, 0 reviewed incompletely), 0 failed." in out
    )
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

    assert excinfo.value.code == remoderate_books._EXIT_RETRYABLE
    captured = capsys.readouterr()
    assert "1 book(s) failed" in captured.err
    assert "RETRYABLE" in captured.err
    assert "failed (rolled back, retry by re-running)" in captured.out


# ---------------------------------------------------------------------------
# Exit-code discrimination
#
# The point of these is that a retry loop can act on the code alone. Before the
# split every non-clean outcome exited 1, so `sweep.sh` retried a hard-blocked
# book three times in fifteen seconds (2026-08-27), spending an LLM review pass
# each time on a verdict that cannot move without a prose edit. Asserting the
# codes are merely "nonzero" is what let that through, so each test below pins
# the exact value and the pair test pins them as DIFFERENT.
# ---------------------------------------------------------------------------


def _exit_code_for(**outcome: object) -> int:
    """Run main() with one canned outcome and return its exit code."""
    result = remoderate_books.SweepResult(
        targets=[("s1", 1)], executed=True, **cast("Any", outcome)
    )
    with pytest.raises(SystemExit) as excinfo:
        _run_main(result)
    assert isinstance(excinfo.value.code, int)
    return excinfo.value.code


def test_blocked_and_failed_exit_codes_differ() -> None:
    """The two classes must not collide, or no caller can tell them apart.

    This is the regression test for the defect itself. Every other assertion
    here would still pass if both constants were 1; only comparing them catches
    that, which is exactly the state the script shipped in.
    """
    assert _exit_code_for(succeeded=[("s1", 1)], blocked=[("s1", 1)]) != _exit_code_for(
        failed=[("s1", 1)]
    )


def test_hard_block_exits_needs_human_not_retryable() -> None:
    """A blocked book is a SUCCESSFUL call whose answer was "no"."""
    code = _exit_code_for(succeeded=[("s1", 1)], blocked=[("s1", 1)])
    assert code == remoderate_books._EXIT_NEEDS_HUMAN
    assert code != remoderate_books._EXIT_RETRYABLE


def test_timeout_and_not_attempted_exit_retryable() -> None:
    """A timeout rolled back and left no durable state, so a retry is valid."""
    assert (
        _exit_code_for(timed_out=[("s1", 1)], not_attempted=[("s2", 1)])
        == remoderate_books._EXIT_RETRYABLE
    )


def test_retryable_wins_when_a_sweep_produced_both() -> None:
    """A mixed sweep exits retryable: there IS something a retry can fix.

    The blocked book still needs a human, but it is named on stdout and comes
    back in the next run's report, so nothing is lost by retrying first. The
    reverse precedence would strand a genuinely transient failure.
    """
    result = remoderate_books.SweepResult(
        targets=[("s1", 1), ("s2", 1)],
        executed=True,
        succeeded=[("s1", 1)],
        blocked=[("s1", 1)],
        failed=[("s2", 1)],
    )
    with pytest.raises(SystemExit) as excinfo:
        _run_main(result)
    assert excinfo.value.code == remoderate_books._EXIT_RETRYABLE


def test_soft_flag_alone_exits_clean(capsys: pytest.CaptureFixture[str]) -> None:
    """`flagged` is informational and must stay OUT of both nonzero classes.

    It is the one outcome where the status did not change AND no action is
    required, so a retry loop should treat the sweep as done.
    """
    result = remoderate_books.SweepResult(
        targets=[("s1", 1)],
        executed=True,
        succeeded=[("s1", 1)],
        flagged=[("s1", 1)],
    )

    _run_main(result)

    assert "soft-flagged" in capsys.readouterr().out


def test_needs_human_code_does_not_collide_with_argparse_usage_error() -> None:
    """argparse exits 2 on a usage error; reusing it would hide a mistyped flag.

    A caller that treated 2 as "hard block" would silently swallow every typo in
    an ops invocation, which is the failure this whole split exists to prevent.
    """
    argparse_usage_exit = 2
    assert argparse_usage_exit != remoderate_books._EXIT_NEEDS_HUMAN
    assert argparse_usage_exit != remoderate_books._EXIT_RETRYABLE

    with pytest.raises(SystemExit) as excinfo:
        remoderate_books._parse_args(["--not-a-real-flag"])
    assert excinfo.value.code == argparse_usage_exit


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

    listing = await remoderate_books.list_in_review_targets(session)

    assert listing.targets == [("s_apple", 2), ("s_zebra", 4)]
    assert listing.excluded == []


@pytest.mark.asyncio
async def test_list_in_review_targets_skips_books_with_no_version_row() -> None:
    """A versionless in_review book is skipped, not fatal, mirroring the queue.

    It is also REPORTED. Skipping silently would let the sweep cover fewer
    books than the review queue lists while printing a clean target count, so
    the dropped id has to come back to the caller, not only to the log.
    """
    session = _grouped_max_session(
        [_in_review_storybook("s_ok"), _in_review_storybook("s_versionless")],
        [("s_ok", 1)],
    )

    listing = await remoderate_books.list_in_review_targets(session)

    assert listing.targets == [("s_ok", 1)]
    assert listing.excluded == ["s_versionless"]


@pytest.mark.asyncio
async def test_list_in_review_targets_skips_the_version_query_when_empty() -> None:
    """No in_review books means no degenerate empty IN query is issued."""
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[])
    books_result = MagicMock()
    books_result.scalars = MagicMock(return_value=scalars_result)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=books_result)

    listing = await remoderate_books.list_in_review_targets(session)

    assert listing.targets == []
    assert listing.excluded == []
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

    # BusinessLogicError, not ResourceNotFoundError: the book EXISTS. This is the
    # same error the endpoint raises for the same condition
    # (api/remoderate.py::remoderate_storybook_version), and the rule name is
    # asserted so the two paths cannot drift into describing one book two ways.
    with pytest.raises(BusinessLogicError, match="does not admit") as excinfo:
        await remoderate_books._resolve_book_id_targets(session, ["s_x"])
    # ``rule`` is folded into ``details`` by the constructor, not kept as an
    # attribute, so read it where it actually lands.
    assert excinfo.value.details["rule"] == "remoderate_requires_reviewable_status"


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


@pytest.mark.asyncio
async def test_sweep_reports_books_excluded_from_the_listing() -> None:
    """sweep() carries the listing's exclusions through to its result.

    The exclusion is discovered inside list_in_review_targets, so unless
    sweep() threads it onto SweepResult, main() has nothing to print and
    nothing to signal in its exit code.
    """
    session = _grouped_max_session(
        [_in_review_storybook("s_ok"), _in_review_storybook("s_versionless")],
        [("s_ok", 1)],
    )

    result = await remoderate_books.sweep(
        engine=_mock_engine(),
        session_factory=_mock_session_factory(session),
        in_review=True,
    )

    assert result.targets == [("s_ok", 1)]
    assert result.excluded == ["s_versionless"]


@pytest.mark.asyncio
async def test_sweep_records_repaired_books() -> None:
    """A book whose text the repair pass rewrote is recorded separately."""
    session = _grouped_max_session([_in_review_storybook("s_a")], [("s_a", 3)])
    # spec= so a renamed or dropped field on RemoderateResult fails here rather
    # than being invented by the mock. It is a slots dataclass, so its fields
    # are real class attributes and spec actually sees them.
    outcome = MagicMock(spec=RemoderateResult)
    outcome.overall_verdict = "pass"
    outcome.coverage_complete = True
    outcome.verdict_counts = {}
    outcome.repaired = True
    with patch.object(
        remoderate_books,
        "remoderate_storybook_version",
        new=AsyncMock(return_value=outcome),
    ):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            in_review=True,
            execute=True,
        )

    assert result.succeeded == [("s_a", 3)]
    assert result.repaired == [("s_a", 3)]


@pytest.mark.asyncio
async def test_sweep_leaves_repaired_empty_when_nothing_was_rewritten() -> None:
    """The repaired list must discriminate, not just mirror succeeded."""
    session = _grouped_max_session([_in_review_storybook("s_a")], [("s_a", 3)])
    # spec= so a renamed or dropped field on RemoderateResult fails here rather
    # than being invented by the mock. It is a slots dataclass, so its fields
    # are real class attributes and spec actually sees them.
    outcome = MagicMock(spec=RemoderateResult)
    outcome.overall_verdict = "pass"
    outcome.coverage_complete = True
    outcome.verdict_counts = {}
    outcome.repaired = False
    with patch.object(
        remoderate_books,
        "remoderate_storybook_version",
        new=AsyncMock(return_value=outcome),
    ):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            in_review=True,
            execute=True,
        )

    assert result.succeeded == [("s_a", 3)]
    assert result.repaired == []


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


@pytest.mark.asyncio
async def test_sweep_times_out_a_wedged_book_and_releases_its_lock() -> None:
    """A wedged book is bounded, rolled back, and kept out of ``failed``.

    The rollback is the assertion that matters, not the bucket. Postgres holds
    ``remoderate_storybook_version``'s ``SELECT ... FOR UPDATE`` on the
    storybook row until the transaction ends, so until this rollback runs, an
    admin's approve or send-back on THIS book blocks behind a hung provider
    call with no timeout of its own. ``log == ["rollback"]`` is the closest a
    unit test gets to observing that release.
    """
    session, log = _execute_session(["s_wedged"])

    async def _wedged(
        _session: object, _storybook_id: str, _version: int, _ctx: object
    ) -> object:
        await asyncio.sleep(5)
        msg = "unreachable: the timeout must fire first"
        raise AssertionError(msg)

    with patch.object(
        remoderate_books,
        "remoderate_storybook_version",
        AsyncMock(side_effect=_wedged),
    ):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            book_ids=["s_wedged"],
            execute=True,
            per_book_timeout_seconds=0.01,
        )

    assert log == ["rollback"]
    assert result.timed_out == [("s_wedged", 1)]
    # Deliberately NOT in `failed`: a provider error says re-run, a timeout
    # says find out what is wedged first, and collapsing them hides which
    # happened.
    assert result.failed == []
    assert result.succeeded == []


@pytest.mark.asyncio
async def test_sweep_abandons_remaining_targets_after_a_timeout() -> None:
    """A timeout stops the sweep, and the books it skipped are still reported.

    Two properties, and the second is the one a summary-only assertion would
    miss. The call count proves the sweep STOPPED rather than racing through
    the rest; ``not_attempted`` proves the skipped books still produce an
    operator-visible signal instead of vanishing between ``targets`` and
    ``succeeded``.
    """
    session, _log = _execute_session(["s_a", "s_b", "s_c"])
    calls: list[str] = []

    async def _wedge_the_first(
        _session: object, storybook_id: str, _version: int, _ctx: object
    ) -> object:
        calls.append(storybook_id)
        await asyncio.sleep(5)
        msg = "unreachable: the timeout must fire first"
        raise AssertionError(msg)

    with patch.object(
        remoderate_books,
        "remoderate_storybook_version",
        AsyncMock(side_effect=_wedge_the_first),
    ):
        result = await remoderate_books.sweep(
            engine=_mock_engine(),
            session_factory=_mock_session_factory(session),
            book_ids=["s_a", "s_b", "s_c"],
            execute=True,
            per_book_timeout_seconds=0.01,
        )

    assert calls == ["s_a"]
    assert result.timed_out == [("s_a", 1)]
    assert result.not_attempted == [("s_b", 1), ("s_c", 1)]


def test_main_exits_nonzero_when_a_book_timed_out(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A timeout and its abandoned books are a summary line and a nonzero exit.

    Same reasoning as the excluded-book case: a book that produced neither a
    success nor a failure would otherwise leave a sweep printing a tidy count
    and exiting 0 with most of its work undone.
    """
    result = remoderate_books.SweepResult(
        targets=[("s_a", 1), ("s_b", 1)],
        executed=True,
        timed_out=[("s_a", 1)],
        not_attempted=[("s_b", 1)],
    )

    with pytest.raises(SystemExit) as excinfo:
        _run_main(result)

    assert excinfo.value.code == remoderate_books._EXIT_RETRYABLE
    captured = capsys.readouterr()
    err = captured.err
    assert "1 book(s) timed out" in err
    assert "1 book(s) not attempted" in err
    assert "RETRYABLE" in err
    out = captured.out
    assert "TIMED OUT" in out
    # Both ids in the SUMMARY, not only in a structured log.
    assert "s_a" in out
    assert "s_b" in out


def test_parse_args_defaults_the_per_book_timeout() -> None:
    """The bound is on by default; an operator has to opt OUT, not opt in."""
    args = remoderate_books._parse_args(["--in-review"])

    assert args.per_book_timeout == remoderate_books._PER_BOOK_TIMEOUT_SECONDS
    assert remoderate_books._PER_BOOK_TIMEOUT_SECONDS > 0


# ---------------------------------------------------------------------------
# main(): the reviewer preflight
# ---------------------------------------------------------------------------


def _run_main_with_settings(
    settings: MagicMock, *, execute: bool, result: Any = None
) -> MagicMock:
    """Drive main() with a settings double; return the patched sweep mock."""
    args = MagicMock(
        book_id=["s1"],
        mock_moderated=False,
        in_review=False,
        execute=execute,
        per_book_timeout=900,
    )
    canned = result or remoderate_books.SweepResult(
        targets=[("s1", 1)], executed=execute, succeeded=[("s1", 1)]
    )
    sweep_mock = AsyncMock(return_value=canned)
    with (
        patch.object(remoderate_books, "_parse_args", MagicMock(return_value=args)),
        patch.object(remoderate_books, "_default_settings", settings),
        patch.object(remoderate_books, "sweep", sweep_mock),
    ):
        remoderate_books.main()
    return sweep_mock


def test_main_refuses_to_execute_with_the_mock_reviewer() -> None:
    """--execute with the mock backend must abort before touching anything.

    The mock answers every review call with the literal "{}", which parses
    cleanly and carries no verdict, so every node lands on the fail-safe
    default. Running this sweep with it would rewrite the exact reports the
    sweep exists to clear, and exit 0 reporting success. Twelve production
    books, 2,916 nodes, are in that state now.
    """
    settings = _settings_stub(provider="mock")

    with pytest.raises(SystemExit) as excinfo:
        _run_main_with_settings(settings, execute=True)

    assert "mock" in str(excinfo.value.code)


def test_main_refusal_happens_before_the_sweep_runs() -> None:
    """The refusal is a preflight, not a post-hoc complaint."""
    settings = _settings_stub(provider="mock")
    args = MagicMock(
        book_id=["s1"],
        mock_moderated=False,
        in_review=False,
        execute=True,
        per_book_timeout=900,
    )
    sweep_mock = AsyncMock()
    with (
        patch.object(remoderate_books, "_parse_args", MagicMock(return_value=args)),
        patch.object(remoderate_books, "_default_settings", settings),
        patch.object(remoderate_books, "sweep", sweep_mock),
        pytest.raises(SystemExit),
    ):
        remoderate_books.main()

    sweep_mock.assert_not_awaited()


def test_main_allows_a_dry_run_with_the_mock_reviewer() -> None:
    """A dry run makes no review calls, so the mock is irrelevant to it.

    Refusing here would remove the one safe way to see what a sweep would
    target from a workstation.
    """
    sweep_mock = _run_main_with_settings(
        _settings_stub(provider="mock"),
        execute=False,
        result=remoderate_books.SweepResult(targets=[("s1", 1)], executed=False),
    )
    sweep_mock.assert_awaited_once()


def test_main_executes_normally_with_a_real_reviewer() -> None:
    """The positive control for the refusal tests above.

    Those prove the preflight stops a mock ``--execute``. On their own they
    cannot distinguish a correctly conditioned guard from one that refuses
    every ``--execute``, since neither ever runs one that should succeed.
    Change only the provider and the sweep must be awaited.
    """
    sweep_mock = _run_main_with_settings(
        _settings_stub(provider="openrouter"),
        execute=True,
        result=remoderate_books.SweepResult(targets=[("s1", 1)], executed=True),
    )
    sweep_mock.assert_awaited_once()


def test_main_prints_the_resolved_target_before_executing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Print what this run actually resolved, not what the operator intended.

    ``Settings`` declares no ``env_file``: it reads exported process
    environment variables and nothing else. A shell that never exported them
    therefore resolves environment="local", a localhost database and
    review_provider="mock" together, from one absence, and every guard keyed
    on environment != "local" goes quiet at the same moment. Printing the
    resolved values is what makes that visible before the run, rather than
    after an apparently successful sweep that touched nothing.
    """
    _run_main_with_settings(
        _settings_stub(provider="openrouter", environment="production"),
        execute=True,
    )
    # stderr, not stdout: the banner shares a stream with the refusal it
    # gives context to, so an operator redirecting one keeps both halves.
    err = capsys.readouterr().err
    assert "openrouter" in err
    assert "production" in err
    assert "db.example.net" in err


def test_main_preflight_never_prints_database_credentials(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The banner names the target, never the password reaching it."""
    _run_main_with_settings(
        _settings_stub(provider="openrouter"),
        execute=True,
    )
    captured = capsys.readouterr()
    assert _LEAK_CANARY_PREFIX not in captured.out
    assert _LEAK_CANARY_PREFIX not in captured.err


# ---------------------------------------------------------------------------
# _database_target(): the banner must not be a credential-disclosure channel
# ---------------------------------------------------------------------------

# One sentinel value, embedded in every shape below and in `_settings_stub`,
# so a single containment assertion covers the whole table. Every shape that a
# leak would split the value across (a `/`, `?`, `#` or space inside it) keeps
# `_LEAK_CANARY_PREFIX` as its leading fragment, so asserting on the fragment
# catches a partial disclosure that asserting on the whole value would miss.
#
# It is deliberately named and worded as a canary rather than as a password.
# A high-entropy literal bound to a password-like name is the exact shape
# secret scanners are built to flag; a scanner finding on a fixture is
# indistinguishable from a real leak until a human reads the diff, which
# spends the alert on nothing. The value states its own purpose instead, so
# neither a scanner nor a reader can mistake it for a credential. Keep it that
# way when editing: the sentinel needs to be distinctive, not password-shaped.
_LEAK_CANARY = "must-not-print-this-value"
_LEAK_CANARY_PREFIX = "must-not-print"

# label -> (url, exactly what _database_target must render).
#
# Expectations are exact, not "does not contain the password". A function that
# returned "" for everything would satisfy a containment-only check while
# telling the operator nothing, and "unparseable" everywhere would hide a
# regression that broke the happy path. Pinning the rendered value on the
# shapes that DO resolve is what keeps the refusals meaningful.
_DATABASE_URL_SHAPES: dict[str, tuple[str, str]] = {
    # Resolves. The positive control for the whole table.
    "well_formed": (
        f"postgresql+asyncpg://cyo_user:{_LEAK_CANARY}@db.example.net:5432/cyo",
        "db.example.net:5432/cyo",
    ),
    # No scheme, but a real authority: urlsplit yields a host, so there is
    # nothing suspect to refuse and the target is nameable.
    "scheme_relative": (
        f"//cyo_user:{_LEAK_CANARY}@db.example.net/cyo",
        "db.example.net/cyo",
    ),
    # `hostname` strips the brackets an IPv6 literal needs; without them
    # "2001:db8::1:5432" reads as a different address entirely.
    "ipv6_literal": (
        f"postgresql+asyncpg://cyo_user:{_LEAK_CANARY}@[2001:db8::1]:5432/cyo",
        "[2001:db8::1]:5432/cyo",
    ),
    # A space is legal inside a netloc as far as urlsplit is concerned and
    # does not move the authority boundary, so this still resolves.
    "space_in_password": (
        "postgresql+asyncpg://cyo_user:must-not-print this-value@db.example.net:5432/cyo",
        "db.example.net:5432/cyo",
    ),
    # No "//" means no authority at all: the entire credential-bearing
    # remainder is the path. This is the shape the previous form printed
    # verbatim.
    "no_double_slash": (
        f"postgresql+asyncpg:cyo_user:{_LEAK_CANARY}@db.example.net/cyo",
        "unparseable",
    ),
    # "cyo_user" is not a valid scheme (underscore), so nothing splits and
    # the whole DSN lands in the path.
    "no_scheme": (
        f"cyo_user:{_LEAK_CANARY}@db.example.net:5432/cyo",
        "unparseable",
    ),
    # Each of these ends the netloc early, inside the password: the "host"
    # urlsplit reports is a credential fragment wearing a hostname's name.
    "slash_in_password": (
        "postgresql+asyncpg://cyo_user:must-not-print/this-value@db.example.net:5432/cyo",
        "unparseable",
    ),
    "question_in_password": (
        "postgresql+asyncpg://cyo_user:must-not-print?this-value@db.example.net:5432/cyo",
        "unparseable",
    ),
    "hash_in_password": (
        "postgresql+asyncpg://cyo_user:must-not-print#this-value@db.example.net:5432/cyo",
        "unparseable",
    ),
    # `.port` casts on access, so all three of these raise ValueError rather
    # than returning None. Reading it outside the try (as the previous form
    # did) turned a malformed port into an uncaught crash mid-preflight.
    "non_numeric_port": (
        f"postgresql+asyncpg://cyo_user:{_LEAK_CANARY}@db.example.net:notaport/cyo",
        "unparseable",
    ),
    "port_out_of_range": (
        f"postgresql+asyncpg://cyo_user:{_LEAK_CANARY}@db.example.net:99999/cyo",
        "unparseable",
    ),
    "negative_port": (
        f"postgresql+asyncpg://cyo_user:{_LEAK_CANARY}@db.example.net:-1/cyo",
        "unparseable",
    ),
    # Userinfo with nothing after the "@": there is no host to name.
    "userinfo_no_host": (
        f"postgresql+asyncpg://cyo_user:{_LEAK_CANARY}@",
        "unparseable",
    ),
    # A database name is one path segment. More than one means the authority
    # boundary landed somewhere unexpected.
    "two_path_segments": (
        f"postgresql+asyncpg://cyo_user:{_LEAK_CANARY}@db.example.net:5432/cyo/extra",
        "unparseable",
    ),
    # No structure at all: a value that is only a secret.
    "bare_secret": (_LEAK_CANARY, "unparseable"),
    # The empty string is what an unset DATABASE_URL looks like after
    # defaulting, and it must not crash the preflight it precedes.
    "empty": ("", "unparseable"),
}


class TestDatabaseTarget:
    """The preflight banner names the target and never the way in.

    This string is printed to a terminal and scraped into CI logs, so the
    requirement is that a password CANNOT reach it, not that it usually does
    not. Nothing upstream constrains the value: ``database_url`` is a bare
    ``str`` on ``Settings``, so every shape an operator can typo into a shell
    reaches this function.
    """

    @pytest.mark.parametrize("label", sorted(_DATABASE_URL_SHAPES))
    def test_no_credential_survives_any_malformed_url(self, label: str) -> None:
        """Every shape renders exactly its expectation, and never the secret.

        Parametrised per shape rather than looped so a regression names the
        one URL that broke; a loop reports only the first failure and hides
        how many of the sixteen went with it.
        """
        url, expected = _DATABASE_URL_SHAPES[label]

        rendered = remoderate_books._database_target(url)

        assert rendered == expected
        assert _LEAK_CANARY_PREFIX not in rendered

    def test_every_shape_carries_the_sentinel_it_is_scanned_for(self) -> None:
        """The table cannot go quiet by losing the secret it tests for.

        Without this, editing a URL above and dropping the password would
        leave its leak assertion trivially true, and the shape would keep
        reporting a pass while testing nothing. ``empty`` is the one
        deliberate exception: an unset DSN has no credential by definition.
        """
        carrying = {
            label
            for label, (url, _) in _DATABASE_URL_SHAPES.items()
            if _LEAK_CANARY_PREFIX in url
        }

        assert carrying == set(_DATABASE_URL_SHAPES) - {"empty"}

    def test_a_resolvable_url_is_still_named(self) -> None:
        """Refusing everything would satisfy the leak check and help nobody.

        The banner exists so an operator can see that a run resolved the
        database they meant. A ``_database_target`` that answered
        "unparseable" unconditionally would pass every assertion above.
        """
        resolved = {
            label
            for label, (_, expected) in _DATABASE_URL_SHAPES.items()
            if expected != "unparseable"
        }

        assert resolved == {
            "well_formed",
            "scheme_relative",
            "ipv6_literal",
            "space_in_password",
        }


def test_preflight_banner_never_prints_credentials_end_to_end(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Drive the real Settings and the real _preflight, not a mock of either.

    Every other preflight test here passes a ``MagicMock`` standing in for
    ``Settings``, which proves what ``_preflight`` does with a value but not
    that a real ``Settings`` carries one it can survive. This closes that
    gap on both shapes an operator can produce without noticing: a DSN whose
    "//" is missing, and one with no scheme at all. Both put the whole
    credential-bearing string into ``parts.path``, which is exactly what the
    banner used to print.

    Two other shapes cannot be covered here, and that is a finding rather
    than an omission: a "/" inside the password and an out-of-range port
    both make ``Settings`` itself raise, because ``core/config.py``'s
    ``_check_pooler_port`` reads ``urlsplit(url).port`` unguarded during
    validation. The "/" case is the worse of the two, since pydantic's error
    text then quotes the password fragment it failed to cast. That is
    tracked separately; this test pins the half that reaches the banner.
    """
    for label in ("no_double_slash", "no_scheme"):
        url, _ = _DATABASE_URL_SHAPES[label]
        settings = Settings(
            database_url=url,
            environment="local",
            review_provider="openrouter",
            openrouter_api_key="sk-or-test",
            # Required alongside the openrouter provider: omni-moderation is
            # an OpenAI call regardless of which model writes the review.
            openai_api_key="sk-test-key",
        )

        remoderate_books._preflight(settings, execute=True)

        captured = capsys.readouterr()
        assert _LEAK_CANARY_PREFIX not in captured.out, label
        assert _LEAK_CANARY_PREFIX not in captured.err, label
        # The banner still ran: an exception swallowed upstream, or a
        # preflight that printed nothing, would satisfy the two assertions
        # above while removing the safety signal entirely.
        assert "unparseable" in captured.err, label
        assert "review_provider=openrouter" in captured.err, label
