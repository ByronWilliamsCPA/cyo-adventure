"""Ops script: sweep-run the admin re-moderation entry point over books.

Implements moderation-review-redesign-2026-07-28.md section 4, decision 5
(the owner-confirmed remediation timing: "re-moderate the 18 mock-moderated
books right after Stage B lands") and section 4 item 1's ops-run half of
Stage D. The entry point itself (``api/remoderate.py::remoderate_storybook_version``)
is Stage D's code half; this script is the reviewable, versioned selection
logic for WHICH books get swept, so an operator (or a reviewer reading this
diff) can see the exact target list before anything runs. THE SWEEP ITSELF
IS AN OPS RUN, not part of any automated pipeline: nothing calls this script
except a human, deliberately, against a database whose ``DATABASE_URL``/
``CYO_ADVENTURE_DATABASE_URL`` they chose.

Dry-run is the default and only LISTS the target books; nothing is written
to the database and no LLM calls are made. Pass ``--execute`` to actually
call :func:`remoderate_storybook_version` for each target.

Two independent ways to pick targets, mutually exclusive:

- ``--mock-moderated``: query the database for published books whose stored
  report carries the mock-reviewer stamp (``summary.reviewer_independent is
  False``, design doc 2.4) or a fail-safe-degraded marker
  (``moderation/stages.py``'s ``reviewer_unavailable`` structural finding, or
  the literal "defaulted to fail-safe" substring, which current code and a
  pre-Stage-A report both emit; see ``_FAIL_SAFE_MESSAGE_SUBSTRING`` for the
  full writer set). This is how the 18-book sweep
  itself will be selected; the exact list is not hardcoded here so it always
  reflects live database state, not a snapshot that can drift.
- ``--book-id STORYBOOK_ID`` (repeatable): re-moderate specific storybooks by
  id, at each one's ``current_published_version``. For a one-off re-run or a
  manually curated subset.

Run against staging or production, dry-run (default, lists only)::

    ENVIRONMENT=staging CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/remoderate_books.py --mock-moderated

Actually execute the sweep::

    ENVIRONMENT=staging CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/remoderate_books.py --mock-moderated --execute

Re-moderate specific books::

    uv run python scripts/remoderate_books.py --book-id sk_ninth_hand --execute

Unlike ``scripts/seed_moderation_qa.py``, this script carries no environment
guard: it targets whatever ``DATABASE_URL`` its caller points it at,
deliberately, per plan decision 8 ("the script must hard-refuse nothing...
BUT dry-run must be the default"). The safety rail is dry-run-by-default plus
the explicit ``--execute`` flag, not an environment allowlist: production is
this script's intended eventual target once B2/B3 are merged and deployed.

Audit provenance: every re-moderation this script drives stamps
``Actor.system()`` (no human request principal exists in this context),
mirroring how ``run_moderation_pipeline``'s own internal
``MODERATION_COMPLETED`` event always uses ``Actor.system()`` for the same
reason. Compare ``api/remoderate.py::trigger_remoderate``, which stamps the
real admin's principal because an HTTP caller is present there.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.api.remoderate import RemoderateContext, remoderate_storybook_version
from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.database import get_engine
from cyo_adventure.core.exceptions import ResourceNotFoundError
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.events.models import Actor
from cyo_adventure.publishing.state_machine import Status
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from cyo_adventure.core.config import Settings

_logger = get_logger(__name__)

# The literal marker every degraded-parse path in moderation/stages.py puts
# in a Finding.message. This is NOT a legacy-only shape: current code emits
# it too, so the match is a live selector, not a historical fallback.
# #ASSUME: data-integrity: four distinct sites write this substring, and the
# ones that matter for selection are the LIVE ones:
#   - the Stage 1 collapse (stages.py:652-668) emits one structural FLAG
#     finding, "reviewer unavailable or unparseable on N node(s); defaulted
#     to fail-safe", concern="reviewer_unavailable". Live, and persisted.
#   - _structured_verdict_from_payload (stages.py:353) and
#     _parse_structured_verdict (stages.py:392) embed it per node; their
#     Stage 1 callers (stages.py:594, 636) pass fail_safe=Verdict.FLAG, so
#     those findings persist too.
#   - _parse_verdict (stages.py:284, 287) embeds it as well, but BOTH of its
#     call sites (stages.py:708, 756) pass fail_safe=Verdict.PASS, and
#     ModerationReport.to_dict drops every PASS finding, so that path can
#     never reach a stored report and never selects a book here.
# The substring match (rather than keying on the collapsed structural finding
# alone) is what also catches a pre-Stage-A report, which carries the
# per-node shape instead of the single collapsed finding.
# #VERIFY: docs/planning/safety/moderation-review-redesign-2026-07-28.md
# section 4 decision 5; `grep -n "defaulted to fail-safe"
# src/cyo_adventure/moderation/stages.py` enumerates the complete writer set
# above, and must be re-run if that file's parse paths change.
_FAIL_SAFE_MESSAGE_SUBSTRING = "defaulted to fail-safe"

# Structured concern taxonomy markers (moderation/report.py::CONCERN_TAXONOMY)
# that identify a mock-moderated or fail-safe-degraded report even when the
# message text has since changed.
_MOCK_MODERATED_CONCERNS = frozenset({"mock_reviewer_active", "reviewer_unavailable"})


def _is_mock_moderated(report: dict[str, object] | None) -> bool:
    """Return True if a persisted report shows mock or fail-safe provenance.

    Args:
        report: A ``StorybookVersion.moderation_report`` value (None if the
            version has never been moderated; such a version is never a
            re-moderation target, since it was never moderated by anything,
            mock or real).

    Returns:
        True if the report's ``summary.reviewer_independent`` is False, or
        any finding carries a mock/fail-safe concern marker, or any finding
        message contains the legacy fail-safe substring.
    """
    if report is None:
        return False
    summary = report.get("summary")
    if (
        isinstance(summary, dict)
        and cast("dict[str, object]", summary).get("reviewer_independent") is False
    ):
        return True
    findings = report.get("findings")
    if not isinstance(findings, list):
        return False
    for finding in cast("list[object]", findings):
        if not isinstance(finding, dict):
            continue
        entry = cast("dict[str, object]", finding)
        if entry.get("concern") in _MOCK_MODERATED_CONCERNS:
            return True
        message = entry.get("message")
        if isinstance(message, str) and _FAIL_SAFE_MESSAGE_SUBSTRING in message:
            return True
    return False


async def list_mock_moderated_targets(session: AsyncSession) -> list[tuple[str, int]]:
    """Find every published book whose current version looks mock-moderated.

    Args:
        session: An active session (read-only; no lock is taken here, since
            this is a listing query, not the re-moderation call itself,
            which takes its own row lock per-book).

    Returns:
        ``(storybook_id, version)`` pairs, sorted by storybook id, for every
        published book whose ``current_published_version`` row's stored
        report matches :func:`_is_mock_moderated`.
    """
    # #ASSUME: external-resources: whole-corpus scan, one extra round trip per
    # published book to fetch its version row. Deliberate at v1 catalog size
    # (tens of books) and mirrors api/moderation_dashboard.py's own no-cache
    # stance; it is an operator-invoked ops script, never a request path.
    # #EDGE: data-integrity: a book whose current_published_version points at
    # a missing StorybookVersion row is skipped silently rather than raising,
    # because one dangling pointer must not make the whole sweep unselectable.
    # Such a book is also unreadable by a child (the reader loads the same
    # row), so skipping it here hides nothing a reader would see.
    # #VERIFY: tests/unit/test_remoderate_books.py::
    # test_list_mock_moderated_targets_skips_missing_version_row and
    # ::test_list_mock_moderated_targets_skips_books_with_no_current_version.
    stmt = select(Storybook).where(
        Storybook.status == Status.PUBLISHED.value,
        Storybook.current_published_version.is_not(None),
    )
    storybooks = (await session.execute(stmt)).scalars().all()
    targets: list[tuple[str, int]] = []
    for storybook in storybooks:
        version = storybook.current_published_version
        if version is None:
            continue
        version_row = await session.get(StorybookVersion, (storybook.id, version))
        if version_row is None:
            continue
        if _is_mock_moderated(version_row.moderation_report):
            targets.append((storybook.id, version))
    return sorted(targets)


async def _resolve_book_id_targets(
    session: AsyncSession, book_ids: list[str]
) -> list[tuple[str, int]]:
    """Resolve explicit ``--book-id`` values to their current published version.

    Args:
        session: An active session.
        book_ids: Storybook ids named on the command line.

    Returns:
        ``(storybook_id, version)`` pairs in the order given, with repeated
        ids collapsed to their first occurrence.

    Raises:
        ResourceNotFoundError: If a named storybook does not exist, or has
            no ``current_published_version`` (nothing to re-moderate).
    """
    # #CRITICAL: data-integrity: unlike the --mock-moderated path, this one
    # RAISES on an unresolvable id instead of skipping it. An operator naming
    # books explicitly is asserting those exact books must be swept, so a typo
    # or an unpublished book has to abort target resolution before --execute
    # touches anything, rather than silently sweeping a shorter list the
    # operator would then read as complete.
    # #VERIFY: tests/unit/test_remoderate_books.py::
    # test_resolve_book_id_targets_raises_404_for_unknown_book and
    # ::test_resolve_book_id_targets_raises_404_for_no_published_version.
    #
    # #EDGE: external-resources: a repeated --book-id is collapsed rather than
    # swept twice. Re-moderating a book twice in one run is not merely
    # wasteful, it is EXPENSIVE and misleading: each pass makes the full
    # review-model fan-out (dozens of calls), and the second pass's report
    # overwrites the first, so the sweep would bill twice to arrive at one
    # result while reporting the book as two successes. Duplicates come from
    # an operator's long command line, not from intent, so first-occurrence
    # order is preserved and no error is raised.
    # #VERIFY: tests/unit/test_remoderate_books.py::
    # test_resolve_book_id_targets_collapses_duplicate_ids.
    targets: list[tuple[str, int]] = []
    seen: set[str] = set()
    for book_id in book_ids:
        if book_id in seen:
            continue
        seen.add(book_id)
        storybook = await session.get(Storybook, book_id)
        if storybook is None:
            msg = f"storybook {book_id!r} not found"
            raise ResourceNotFoundError(
                msg, resource_type="Storybook", resource_id=book_id
            )
        if storybook.current_published_version is None:
            msg = f"storybook {book_id!r} has no current_published_version"
            raise ResourceNotFoundError(
                msg, resource_type="StorybookVersion", resource_id=book_id
            )
        targets.append((book_id, storybook.current_published_version))
    return targets


@dataclass(frozen=True, slots=True)
class SweepResult:
    """Outcome of a (dry-run or executed) re-moderation sweep."""

    targets: list[tuple[str, int]]
    executed: bool
    succeeded: list[tuple[str, int]] = field(default_factory=list)
    failed: list[tuple[str, int]] = field(default_factory=list)
    # #CRITICAL: security: `blocked` and `flagged` exist because a
    # re-moderation that comes back dirty changes NOTHING about the book on
    # its own: ADR-005 keeps a published book published until a human acts,
    # so a hard block here leaves a child-readable book child-readable. A
    # sweep that reported only succeeded/failed counts would show a
    # freshly-blocked book as a plain success, which is precisely the signal
    # an operator needs and would not get. main() prints these lists and
    # exits nonzero on a block for the same reason.
    # #VERIFY: tests/unit/test_remoderate_books.py::
    # test_sweep_records_blocked_and_flagged_verdicts and
    # ::test_main_exits_nonzero_when_a_book_is_blocked.
    blocked: list[tuple[str, int]] = field(default_factory=list)
    flagged: list[tuple[str, int]] = field(default_factory=list)


async def sweep(
    *,
    engine: AsyncEngine | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
    settings: Settings | None = None,
    book_ids: list[str] | None = None,
    mock_moderated: bool = False,
    execute: bool = False,
) -> SweepResult:
    """Select and (optionally) re-moderate the target books.

    Exactly one of ``book_ids`` (non-empty) or ``mock_moderated`` selects the
    target set; see the module docstring's two selection modes.

    Args:
        engine: Async engine to bind the session to. Defaults to the app's
            shared engine (``get_engine()``); tests inject a mock engine.
        session_factory: Callable returning a new ``AsyncSession``. Defaults
            to a sessionmaker bound to ``engine``; tests inject a mocked
            session factory here so no real database connection is required.
        settings: Settings passed through to
            :func:`remoderate_storybook_version` (provider construction).
            Defaults to the app's shared settings.
        book_ids: Explicit storybook ids to target.
        mock_moderated: If True, target every book
            :func:`list_mock_moderated_targets` finds.
        execute: When False (default), only lists the targets; nothing is
            written and no LLM calls are made. When True, calls
            :func:`remoderate_storybook_version` for each target and commits
            after each one, so a book that succeeds is durable immediately
            and its row lock is released before the next book starts; one
            book's failure is rolled back alone and never aborts the rest of
            the sweep.

    Returns:
        SweepResult: The resolved targets and, if executed, which succeeded
        or failed, plus which came back ``block`` or ``flag``. A blocked book
        is still published and still readable (ADR-005: only a human moves
        it), so ``blocked`` is a to-do list for the operator, not a record of
        something the sweep already handled.

    Raises:
        ValueError: If neither or both of ``book_ids``/``mock_moderated`` are
            given.
    """
    if bool(book_ids) == mock_moderated:
        msg = (
            "sweep() requires exactly one of a non-empty book_ids list or "
            "mock_moderated=True, not both or neither"
        )
        raise ValueError(msg)

    active_engine = engine if engine is not None else get_engine()
    new_session = (
        session_factory
        if session_factory is not None
        else async_sessionmaker(active_engine, expire_on_commit=False)
    )
    active_settings = settings if settings is not None else _default_settings

    async with new_session() as session:
        targets = (
            await _resolve_book_id_targets(session, book_ids)
            if book_ids
            else await list_mock_moderated_targets(session)
        )

        if not execute:
            return SweepResult(targets=targets, executed=False)

        ctx = RemoderateContext(settings=active_settings, actor=Actor.system())
        succeeded: list[tuple[str, int]] = []
        failed: list[tuple[str, int]] = []
        blocked: list[tuple[str, int]] = []
        flagged: list[tuple[str, int]] = []
        for storybook_id, version in targets:
            try:
                # #CRITICAL: data-integrity: one COMMIT per book, not one
                # savepoint inside a single sweep-wide transaction. A
                # savepoint isolates a failure but gives no durability: a
                # crash on book 18 of 18 would discard all 17 prior
                # re-moderations and the LLM spend they consumed, because
                # nothing had been committed yet.
                # #CRITICAL: concurrency: committing per book is also what
                # RELEASES that book's SELECT ... FOR UPDATE row lock, which
                # remoderate_storybook_version takes. Postgres holds those
                # locks until the enclosing transaction ends, and a savepoint
                # release does not free them, so the savepoint version held a
                # lock on every already-processed book for the whole sweep,
                # blocking concurrent admin approve/archive on all of them.
                # #VERIFY: tests/unit/test_remoderate_books.py::
                # test_sweep_commits_after_each_book and
                # ::test_sweep_continues_after_one_failure.
                result = await remoderate_storybook_version(
                    session, storybook_id, version, ctx
                )
            except Exception:
                # #ASSUME: external-resources: a transient provider error on
                # one book must not abort the sweep. The rollback discards
                # only this book's partial state (every earlier book is
                # already committed), and it stays targetable by a re-run:
                # its report still carries the mock/fail-safe marker, or an
                # operator can pass it explicitly via --book-id.
                await session.rollback()
                _logger.exception(
                    "remoderate_books.sweep_failed",
                    storybook_id=storybook_id,
                    version=version,
                )
                failed.append((storybook_id, version))
            else:
                await session.commit()
                succeeded.append((storybook_id, version))
                if result.overall_verdict == "block":
                    _logger.warning(
                        "remoderate_books.book_blocked",
                        storybook_id=storybook_id,
                        version=version,
                    )
                    blocked.append((storybook_id, version))
                elif result.overall_verdict == "flag":
                    flagged.append((storybook_id, version))
        return SweepResult(
            targets=targets,
            executed=True,
            succeeded=succeeded,
            failed=failed,
            blocked=blocked,
            flagged=flagged,
        )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the re-moderation sweep script.

    Args:
        argv: Argument list, or None to use ``sys.argv``.

    Returns:
        The parsed namespace (``book_id`` list, ``mock_moderated`` bool,
        ``execute`` bool).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument(
        "--book-id",
        action="append",
        dest="book_id",
        metavar="STORYBOOK_ID",
        help="Re-moderate this storybook id (repeatable). Mutually exclusive "
        "with --mock-moderated.",
    )
    selector.add_argument(
        "--mock-moderated",
        action="store_true",
        help="Target every published book whose current version looks "
        "mock-moderated (see module docstring's selection criteria). "
        "Mutually exclusive with --book-id.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually call the re-moderation entry point for each target. "
        "Without this flag, only lists the targets; nothing is written.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point for the re-moderation sweep script.

    Prints the target list always. In dry-run (default), that is the only
    output. When ``--execute`` is given, also prints the succeeded/failed
    counts, the fresh verdicts, and exits nonzero if anything failed OR if
    any book came back hard-blocked, so neither a partial sweep nor a book
    that just failed re-moderation is ever read as a clean success.
    """
    args = _parse_args()
    result = asyncio.run(
        sweep(
            book_ids=args.book_id,
            mock_moderated=args.mock_moderated,
            execute=args.execute,
        )
    )

    if not result.targets:
        print("remoderate_books: no target books found.")
        return

    print(f"remoderate_books: {len(result.targets)} target book(s):")
    for storybook_id, version in result.targets:
        print(f"  {storybook_id} v{version}")

    if not result.executed:
        print("remoderate_books: dry run, nothing executed. Pass --execute to run.")
        return

    print(
        f"remoderate_books: {len(result.succeeded)} succeeded "
        f"({len(result.blocked)} blocked, {len(result.flagged)} flagged), "
        f"{len(result.failed)} failed."
    )
    if result.flagged:
        print(
            "remoderate_books: soft-flagged (still published, review when "
            "convenient): " + ", ".join(f"{sid} v{v}" for sid, v in result.flagged)
        )
    if result.blocked:
        # A hard block on a published book is the one outcome that needs a
        # human today: the book is STILL published and STILL readable, because
        # ADR-005 reserves every status change for a human. Print it loudly
        # and exit nonzero even though the re-moderation itself succeeded.
        print(
            "remoderate_books: HARD BLOCK, still published and readable, "
            "act on these: " + ", ".join(f"{sid} v{v}" for sid, v in result.blocked)
        )
    if result.failed:
        print(
            "remoderate_books: failed (rolled back, retry by re-running): "
            + ", ".join(f"{sid} v{v}" for sid, v in result.failed)
        )
    if result.failed or result.blocked:
        sys.exit(
            f"remoderate_books: {len(result.failed)} book(s) failed "
            f"re-moderation, {len(result.blocked)} book(s) hard-blocked."
        )


if __name__ == "__main__":
    main()
