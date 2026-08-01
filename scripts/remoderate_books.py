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
  False``, design doc 2.4) or one of the pre-collapse legacy fail-safe
  concern/message markers (``moderation/stages.py``'s ``reviewer_unavailable``
  structural finding, or the literal "defaulted to fail-safe" substring a
  pre-Stage-A report may carry once per node). This is how the 18-book sweep
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

# The pre-collapse literal fail-safe messages (moderation/stages.py:168/171).
# #ASSUME: data-integrity: a report written before the Stage A collapse
# (design doc 2.3) could carry one of these strings once per unparseable
# node's Finding.message, rather than the single collapsed structural
# finding current code emits. Matched as a substring against every finding's
# message so either historical shape is caught.
# #VERIFY: docs/planning/safety/moderation-review-redesign-2026-07-28.md
# section 4 decision 5; moderation/stages.py's two `_parse_verdict` call
# sites are the only writers of this literal text.
_LEGACY_FAIL_SAFE_SUBSTRING = "defaulted to fail-safe"

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
        if isinstance(message, str) and _LEGACY_FAIL_SAFE_SUBSTRING in message:
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
        ``(storybook_id, version)`` pairs in the order given.

    Raises:
        ResourceNotFoundError: If a named storybook does not exist, or has
            no ``current_published_version`` (nothing to re-moderate).
    """
    targets: list[tuple[str, int]] = []
    for book_id in book_ids:
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
            :func:`remoderate_storybook_version` for each target, one
            SAVEPOINT per book (mirrors
            ``scripts/seed_moderation_qa.py::_moderate_new_books``), so one
            book's failure never aborts the rest of the sweep or rolls back
            an already-succeeded book earlier in the same run.

    Returns:
        SweepResult: The resolved targets and, if executed, which succeeded
        or failed.

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
        for storybook_id, version in targets:
            try:
                # #CRITICAL: data-integrity: one SAVEPOINT per book, same
                # rationale as seed_moderation_qa.py::_moderate_new_books:
                # remoderate_storybook_version can adopt a repaired blob
                # before it finishes, so a failure partway through must not
                # leave that book half-mutated, and must not roll back any
                # earlier book in the same sweep.
                # #VERIFY: tests/unit/test_remoderate_books.py::
                # test_sweep_continues_after_one_failure.
                async with session.begin_nested():
                    await remoderate_storybook_version(
                        session, storybook_id, version, ctx
                    )
            except Exception:
                # #ASSUME: external-resources: a transient provider error on
                # one book must not abort the sweep; the savepoint rolled
                # back that book's partial state, and it stays targetable by
                # a re-run (its report may still carry the mock/fail-safe
                # marker, or an operator can pass it explicitly via
                # --book-id).
                _logger.exception(
                    "remoderate_books.sweep_failed",
                    storybook_id=storybook_id,
                    version=version,
                )
                failed.append((storybook_id, version))
            else:
                succeeded.append((storybook_id, version))
        await session.commit()
        return SweepResult(
            targets=targets, executed=True, succeeded=succeeded, failed=failed
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
    counts and exits nonzero if anything failed, so a partial sweep is never
    read as a clean success.
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
        f"remoderate_books: {len(result.succeeded)} succeeded, "
        f"{len(result.failed)} failed."
    )
    if result.failed:
        print(
            "remoderate_books: failed (rolled back, retry by re-running): "
            + ", ".join(f"{sid} v{v}" for sid, v in result.failed)
        )
        sys.exit(
            f"remoderate_books: {len(result.failed)} book(s) failed re-moderation."
        )


if __name__ == "__main__":
    main()
