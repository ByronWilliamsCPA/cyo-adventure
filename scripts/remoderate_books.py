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

Three independent ways to pick targets, mutually exclusive:

- ``--mock-moderated``: query the database for published books whose stored
  report carries the mock-reviewer stamp (``summary.reviewer_independent is
  False``, design doc 2.4) or a fail-safe-degraded marker
  (``moderation/stages.py``'s ``reviewer_unavailable`` structural finding, or
  the literal "defaulted to fail-safe" substring, which current code and a
  pre-Stage-A report both emit; see ``FAIL_SAFE_MESSAGE_SUBSTRING`` for the
  full writer set). This is how the 18-book sweep
  itself will be selected; the exact list is not hardcoded here so it always
  reflects live database state, not a snapshot that can drift.
- ``--in-review``: query the database for every book sitting at the human
  review gate, targeting each at its LATEST version (the one the admin review
  queue shows, ``api/approval.py``). Unlike ``--mock-moderated`` this applies
  no report-content filter: an in_review book's stored report is about to be
  acted on by a reviewer whatever it says, so re-deriving it is the point
  rather than a remedy for a specific defect. This is how the seventeen books
  stuck in review since 2026-07-21 are swept.
- ``--book-id STORYBOOK_ID`` (repeatable): re-moderate specific storybooks by
  id, at each one's ``current_published_version`` or, for an in_review book,
  its latest version. For a one-off re-run, a manually curated subset, or a
  single-book canary before a full sweep.

Every executed book is bounded by ``--per-book-timeout`` (default 900s).
Exceeding it rolls that book back, which is what releases the ``FOR UPDATE``
row lock an admin's approve or send-back would otherwise queue behind, and
abandons the remaining targets rather than driving them through the same
wedged provider. Both the timed-out book and the abandoned ones are named in
the summary and force a nonzero exit.

Run against staging or production, dry-run (default, lists only)::

    ENVIRONMENT=staging CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/remoderate_books.py --mock-moderated

Actually execute the sweep::

    ENVIRONMENT=staging CYO_ADVENTURE_DATABASE_URL=... \\
        CYO_ADVENTURE_REVIEW_PROVIDER=openrouter OPENROUTER_API_KEY=... \\
        OPENAI_API_KEY=... \\
        uv run python scripts/remoderate_books.py --mock-moderated --execute

Sweep the books waiting at the review gate::

    ENVIRONMENT=staging CYO_ADVENTURE_DATABASE_URL=... \\
        CYO_ADVENTURE_REVIEW_PROVIDER=openrouter OPENROUTER_API_KEY=... \\
        OPENAI_API_KEY=... \\
        uv run python scripts/remoderate_books.py --in-review --execute

Re-moderate specific books::

    CYO_ADVENTURE_REVIEW_PROVIDER=openrouter OPENROUTER_API_KEY=... \\
        OPENAI_API_KEY=... \\
        uv run python scripts/remoderate_books.py --book-id sk_ninth_hand \\
        --execute

Unlike ``scripts/seed_moderation_qa.py``, this script carries no environment
guard: it targets whatever ``DATABASE_URL`` its caller points it at,
deliberately. That is this script's own design choice, stated here rather
than cited: an earlier version of this docstring attributed it to a "plan
decision 8" that does not exist (section 7 of
``docs/planning/safety/moderation-review-redesign-2026-07-28.md`` contains
exactly seven numbered decisions, none of them this one), and a citation that
resolves to nothing reads as authority it never had.

The basis it does have: the redesign plan's decision 5 schedules the
eighteen mock-moderated books for re-moderation right after Stage B lands,
and section 4 item 3 has published books stay published while that runs.
Production is therefore this script's intended eventual target, not an
accident to be guarded against, which is the opposite of
``seed_moderation_qa.py``'s situation (it writes new adversarial content, so
it hard-refuses anything but staging). The safety rail here is
dry-run-by-default plus the explicit ``--execute`` flag.

It DOES carry a reviewer guard, which is a different axis entirely. The
absence of an environment guard is about which database a caller may point
at; this one is about whether a real reviewer exists to point at it.
``--execute`` with ``review_provider="mock"`` cannot produce a review at all:
the mock answers every call with the literal ``"{}"``, which parses cleanly
and carries no verdict, so every node lands on its stage's fail-safe default.
Such a run rewrites the exact fail-safe reports the sweep exists to clear and
then exits 0 reporting success. ``main`` refuses it, and prints the resolved
environment, database target, and provider before every executed run. ``Settings``
declares no ``env_file`` (``core/config.py``), so it reads nothing but exported
variables: a process started without them falls back to ``environment="local"``,
a localhost database, and the mock provider all at once, from one absence.

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
import re
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, cast
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.api.remoderate import (
    REMODERATABLE_STATUS_VALUES,
    RemoderateContext,
    remoderate_storybook_version,
)
from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.database import get_engine
from cyo_adventure.core.exceptions import (
    BusinessLogicError,
    ResourceNotFoundError,
)
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.events.models import Actor
from cyo_adventure.moderation.report import (
    FAIL_SAFE_MESSAGE_SUBSTRING,
    MOCK_MODERATED_CONCERNS,
)
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
# The substring and concern-marker constants themselves now live in
# moderation/report.py (see its FAIL_SAFE_MESSAGE_SUBSTRING and
# MOCK_MODERATED_CONCERNS module attributes), so this script and the
# pipeline share one definition instead of two copies drifting apart.


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

    Note:
        Deliberately NOT ``moderation.report.moderation_report_unusable()``:
        this function selects a book for re-moderation on an ANY-match (one
        fail-safe finding is enough), while that predicate is an ALL-match
        (approval blocks only when every finding is a pipeline artifact and
        no genuine judgment exists at all). The two semantics serve different
        callers and must not be collapsed into one.
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
        if entry.get("concern") in MOCK_MODERATED_CONCERNS:
            return True
        message = entry.get("message")
        if isinstance(message, str) and FAIL_SAFE_MESSAGE_SUBSTRING in message:
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


@dataclass(frozen=True, slots=True)
class InReviewListing:
    """What an in_review target listing selected, and what it had to drop.

    Attributes:
        targets: ``(storybook_id, version)`` pairs the sweep can act on.
        excluded: Ids of in_review books that could not be targeted.
    """

    targets: list[tuple[str, int]]
    excluded: list[str]


async def list_in_review_targets(session: AsyncSession) -> InReviewListing:
    """Find every in_review book, at the version its reviewer is looking at.

    Unlike the published selectors, this one applies NO report-content filter.
    A published book is swept only if its stored report looks mock-moderated,
    because a published book with a good report needs nothing. An in_review
    book is different: it is sitting at the human gate, so a reviewer is about
    to act on whatever its stored report says, however old, and re-deriving it
    is the point rather than a remedy for a specific defect.

    Args:
        session: An active session (read-only; the re-moderation call takes
            its own row lock per-book).

    Returns:
        An :class:`InReviewListing` whose ``targets`` holds
        ``(storybook_id, version)`` pairs sorted by storybook id, one per
        in_review book, at that book's HIGHEST version number, and whose
        ``excluded`` holds the sorted ids of any in_review book that had to
        be dropped for want of a version row.

    """
    # #CRITICAL: data-integrity: "the version under review" is max(version),
    # the same rule api/approval.py uses in BOTH places it needs one
    # (::_latest_version for approve/send-back, and the review queue's grouped
    # max for the listing). An in_review book has no current_published_version
    # to point the way, so any other rule here would re-derive the verdicts of
    # a version the reviewer is not looking at, and write them onto the row
    # that reviewer WILL act on.
    # #VERIFY: tests/unit/test_remoderate_books.py::
    # test_list_in_review_targets_returns_latest_version_per_book.
    stmt = select(Storybook).where(Storybook.status == Status.IN_REVIEW.value)
    storybooks = (await session.execute(stmt)).scalars().all()
    ids = [storybook.id for storybook in storybooks]
    # #EDGE: data-integrity: short-circuit before issuing a degenerate empty
    # IN query, exactly as api/approval.py's queue does for the same reason.
    if not ids:
        return InReviewListing(targets=[], excluded=[])
    latest_rows = cast(
        "list[tuple[str, int]]",
        (
            await session.execute(
                select(
                    StorybookVersion.storybook_id,
                    func.max(StorybookVersion.version),
                )
                .where(StorybookVersion.storybook_id.in_(ids))
                .group_by(StorybookVersion.storybook_id)
            )
        ).all(),
    )
    latest = dict(latest_rows)
    targets: list[tuple[str, int]] = []
    excluded: list[str] = []
    for storybook_id in ids:
        version = latest.get(storybook_id)
        # #CRITICAL: data-integrity: an in_review book with no version row is
        # a corrupt-at-rest anomaly the review queue also logs and drops. Skip
        # it rather than raising, so one anomaly cannot make the whole sweep
        # unselectable, but RETURN it as well as logging it. A log line alone
        # only reaches an operator who is separately tailing structured logs,
        # so the sweep would otherwise cover fewer books than the review queue
        # lists while printing a clean target count and exiting 0. Returning
        # the ids alongside the targets is what lets main() say so and signal
        # it in the exit code. It is deliberately returned rather than
        # recounted with a second query: a book INSERTed between two queries
        # would be misreported as excluded when it merely arrived late.
        # #VERIFY: tests/unit/test_remoderate_books.py::
        # test_list_in_review_targets_skips_books_with_no_version_row and
        # ::test_sweep_reports_books_excluded_from_the_listing.
        if version is None:
            _logger.warning(
                "remoderate_books.in_review_book_has_no_version",
                storybook_id=storybook_id,
            )
            excluded.append(storybook_id)
            continue
        targets.append((storybook_id, version))
    return InReviewListing(targets=sorted(targets), excluded=sorted(excluded))


async def _resolve_in_review_version(session: AsyncSession, book_id: str) -> int:
    """Return the version an explicitly named in_review book is reviewed at.

    Args:
        session: An active session.
        book_id: The storybook id named on the command line.

    Returns:
        int: The book's highest version number.

    Raises:
        ResourceNotFoundError: If the book has no version rows at all.
    """
    latest = await session.scalar(
        select(func.max(StorybookVersion.version)).where(
            StorybookVersion.storybook_id == book_id
        )
    )
    if latest is None:
        msg = f"storybook {book_id!r} is in_review but has no versions"
        raise ResourceNotFoundError(
            msg, resource_type="StorybookVersion", resource_id=book_id
        )
    return latest


async def _resolve_book_id_targets(
    session: AsyncSession, book_ids: list[str]
) -> list[tuple[str, int]]:
    """Resolve explicit ``--book-id`` values to the version to re-moderate.

    Which version that is depends on status, because the two re-moderatable
    statuses point at their subject differently: a published book names it in
    ``current_published_version``, while an in_review book has no such pointer
    and is reviewed at its highest version.

    Args:
        session: An active session.
        book_ids: Storybook ids named on the command line.

    Returns:
        ``(storybook_id, version)`` pairs in the order given, with repeated
        ids collapsed to their first occurrence.

    Raises:
        ResourceNotFoundError: If a named storybook does not exist, or exists
            but has no version to re-moderate (no ``current_published_version``
            when published, no version rows at all when in_review).
        BusinessLogicError: If a named storybook exists but is in a status
            re-moderation does not admit. Kept distinct from the not-found case
            on purpose: a caller that catches ResourceNotFoundError to mean
            "that id is gone, skip it" must not also swallow "you named a
            draft", which is an operator mistake worth stopping for.
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
        # #CRITICAL: security: the status check happens HERE, before
        # --execute touches anything, even though api/remoderate.py rejects an
        # inadmissible status too. Deferring to the endpoint would abort the
        # sweep mid-flight, after earlier books had already committed their
        # re-moderations and spent the LLM calls, leaving the operator to
        # work out which half ran. Checking early is about WHERE the sweep
        # stops; it says nothing about which error to raise, so this mirrors
        # the endpoint's BusinessLogicError and its rule name rather than
        # reporting an existing book as missing. Both the admissible set and
        # the rule name come from the endpoint rather than being restated, so
        # the two paths cannot drift into disagreeing about the same book.
        # #VERIFY: tests/unit/test_remoderate_books.py::
        # test_resolve_book_id_targets_refuses_a_status_remoderation_rejects.
        if storybook.status not in REMODERATABLE_STATUS_VALUES:
            msg = (
                f"storybook {book_id!r} has status {storybook.status!r}, which "
                f"re-moderation does not admit (allowed: "
                f"{', '.join(sorted(REMODERATABLE_STATUS_VALUES))})"
            )
            raise BusinessLogicError(
                msg,
                rule="remoderate_requires_reviewable_status",
                context={"storybook_id": book_id, "status": storybook.status},
            )
        if storybook.status == Status.IN_REVIEW.value:
            targets.append(
                (book_id, await _resolve_in_review_version(session, book_id))
            )
            continue
        if storybook.current_published_version is None:
            msg = f"storybook {book_id!r} has no current_published_version"
            raise ResourceNotFoundError(
                msg, resource_type="StorybookVersion", resource_id=book_id
            )
        targets.append((book_id, storybook.current_published_version))
    return targets


# #CRITICAL: concurrency: an unbounded per-book call is an unbounded row-lock
# hold. remoderate_storybook_version takes SELECT ... FOR UPDATE on the
# storybook row (api/remoderate.py) and Postgres holds it until this loop's
# COMMIT, so a wedged provider call does not merely stall the sweep: it blocks
# api/approval.py::_load_admin_story, and therefore an admin's approve,
# send-back, or archive on that exact book, for as long as it hangs. That
# contention is new with the in_review widening, because in_review books are
# precisely the ones a reviewer is working on.
#
# 900s is derived, not picked: core/config.py bounds a FULL multi-stage
# generation at generation_job_timeout_seconds = 1800, and re-moderation is
# strictly less work than generation (a review fan-out plus optional repair,
# plus two run_fill_gate passes at ~50s worst case each). Half the generation
# bound leaves ample headroom over any healthy run while still being an order
# of magnitude below "forever".
# #VERIFY: tests/unit/test_remoderate_books.py::
# test_sweep_times_out_a_wedged_book_and_releases_its_lock and
# ::test_sweep_abandons_remaining_targets_after_a_timeout.
_PER_BOOK_TIMEOUT_SECONDS: Final = 900.0

# Exit codes. A retry loop (`sweep.sh`, or any operator's `until` wrapper) reads
# these to decide whether re-running can change the outcome, so the split is
# part of this script's contract and not an implementation detail.
#
# The distinction that matters is NOT success versus failure, it is retryable
# versus not. Before this split every non-clean outcome exited 1, because
# `sys.exit(<str>)` prints its argument to stderr and exits 1 whatever the
# string says. A caller could therefore see that a sweep was unhappy but never
# why, and the only discriminator was prose on stdout. Measured cost, 2026-08-27:
# `sweep.sh` retried a hard-blocked book three times in fifteen seconds, spending
# an LLM review pass each time to re-derive a verdict that cannot move without a
# prose edit.
#
# `NEEDS_HUMAN` is 3, not 2, because argparse already exits 2 on a usage error.
# Reusing 2 would make a mistyped flag indistinguishable from a hard block.
_EXIT_RETRYABLE: Final = 1
_EXIT_NEEDS_HUMAN: Final = 3


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
    repaired: list[tuple[str, int]] = field(default_factory=list)
    # #CRITICAL: data-integrity: a book the listing dropped is neither
    # `failed` nor `blocked`, so before this field it produced NO exit-code
    # signal and NO summary line: a sweep could cover fewer books than the
    # review queue lists and still print a clean count and exit 0. The
    # structured warning alone only reaches an operator who is separately
    # tailing logs, which is exactly the person a sweep summary exists to
    # spare.
    # #VERIFY: tests/unit/test_remoderate_books.py::
    # test_sweep_reports_books_excluded_from_the_listing and
    # ::test_main_exits_nonzero_when_a_book_was_excluded.
    excluded: list[str] = field(default_factory=list)
    # #CRITICAL: data-integrity: a timeout abandons the rest of the sweep, so
    # without these two lists the abandoned books would produce no exit-code
    # signal and no summary line, which is the same silent-gap failure the
    # `excluded` field above exists to prevent. `timed_out` is kept out of
    # `failed` on purpose: a provider error is worth re-running, a timeout is
    # worth investigating first, and collapsing them hides which happened.
    # #VERIFY: tests/unit/test_remoderate_books.py::
    # test_sweep_abandons_remaining_targets_after_a_timeout and
    # ::test_main_exits_nonzero_when_a_book_timed_out.
    timed_out: list[tuple[str, int]] = field(default_factory=list)
    not_attempted: list[tuple[str, int]] = field(default_factory=list)


async def sweep(
    *,
    engine: AsyncEngine | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
    settings: Settings | None = None,
    book_ids: list[str] | None = None,
    mock_moderated: bool = False,
    in_review: bool = False,
    execute: bool = False,
    per_book_timeout_seconds: float = _PER_BOOK_TIMEOUT_SECONDS,
) -> SweepResult:
    """Select and (optionally) re-moderate the target books.

    Exactly one of ``book_ids`` (non-empty), ``mock_moderated``, or
    ``in_review`` selects the target set; see the module docstring's three
    selection modes.

    Args:
        engine: Async engine to bind the session to. Defaults to the app's
            shared engine (``get_engine()``); tests inject a mock engine.
        session_factory: Callable returning a new ``AsyncSession``. Defaults
            to a sessionmaker bound to ``engine``; tests inject a mocked
            session factory here so no real database connection is required.
        per_book_timeout_seconds: Wall-clock bound on ONE book's
            re-moderation. Exceeding it rolls that book back (releasing its
            row lock) and abandons the remaining targets; see
            :data:`_PER_BOOK_TIMEOUT_SECONDS`.
        settings: Settings passed through to
            :func:`remoderate_storybook_version` (provider construction).
            Defaults to the app's shared settings.
        book_ids: Explicit storybook ids to target.
        mock_moderated: If True, target every book
            :func:`list_mock_moderated_targets` finds.
        in_review: If True, target every book
            :func:`list_in_review_targets` finds.
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
        ValueError: If zero, or more than one, of
            ``book_ids``/``mock_moderated``/``in_review`` is given.
    """
    # #CRITICAL: data-integrity: counting selectors, not the two-way equality
    # this replaced. `bool(book_ids) == mock_moderated` happened to be a
    # correct XOR for two flags and silently stops being one for three: with
    # in_review added it would accept `--mock-moderated --in-review` together
    # and then quietly run whichever branch the if/elif chain reached first.
    # #VERIFY: tests/unit/test_remoderate_books.py::
    # test_sweep_raises_when_two_of_three_selectors_given.
    chosen = [bool(book_ids), mock_moderated, in_review]
    if sum(chosen) != 1:
        msg = (
            "sweep() requires exactly one selector: a non-empty book_ids "
            "list, mock_moderated=True, or in_review=True"
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
        excluded: list[str] = []
        if book_ids:
            targets = await _resolve_book_id_targets(session, book_ids)
        elif in_review:
            listing = await list_in_review_targets(session)
            targets = listing.targets
            excluded = listing.excluded
        else:
            targets = await list_mock_moderated_targets(session)

        if not execute:
            return SweepResult(targets=targets, executed=False, excluded=excluded)

        ctx = RemoderateContext(settings=active_settings, actor=Actor.system())
        succeeded: list[tuple[str, int]] = []
        failed: list[tuple[str, int]] = []
        blocked: list[tuple[str, int]] = []
        flagged: list[tuple[str, int]] = []
        repaired: list[tuple[str, int]] = []
        timed_out: list[tuple[str, int]] = []
        not_attempted: list[tuple[str, int]] = []
        for index, (storybook_id, version) in enumerate(targets):
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
                async with asyncio.timeout(per_book_timeout_seconds):
                    result = await remoderate_storybook_version(
                        session, storybook_id, version, ctx
                    )
            except TimeoutError:
                # #CRITICAL: concurrency: caught BEFORE the generic handler and
                # handled differently on purpose. asyncio.timeout raises the
                # builtin TimeoutError, which `except Exception` below would
                # otherwise swallow into the ordinary retry-me bucket.
                #
                # The rollback is what actually releases the row lock, so it
                # runs first and unconditionally. The sweep then STOPS rather
                # than continuing: a timeout is a statement about the provider
                # or the pipeline, not about this book, so pushing the next
                # sixteen through the same wedged path would spend real LLM
                # budget to collect sixteen more timeouts, each holding another
                # row lock on another book a reviewer may be waiting on. It
                # also avoids reusing a session whose connection was cancelled
                # mid-statement.
                # #VERIFY: tests/unit/test_remoderate_books.py::
                # test_sweep_times_out_a_wedged_book_and_releases_its_lock and
                # ::test_sweep_abandons_remaining_targets_after_a_timeout.
                await session.rollback()
                _logger.error(
                    "remoderate_books.sweep_timed_out",
                    storybook_id=storybook_id,
                    version=version,
                    timeout_seconds=per_book_timeout_seconds,
                    abandoned=len(targets) - index - 1,
                )
                timed_out.append((storybook_id, version))
                not_attempted = list(targets[index + 1 :])
                break
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
                if result.repaired:
                    # #ASSUME: data-integrity: a repaired book has had its
                    # stored text REWRITTEN by the repair pass, so the verdict
                    # an operator reads describes prose that is no longer what
                    # they last reviewed. Rolled up with plain successes it is
                    # invisible; called out, it tells them which books need a
                    # fresh read before approval.
                    # #VERIFY: tests/unit/test_remoderate_books.py::
                    # test_sweep_records_repaired_books.
                    repaired.append((storybook_id, version))
        return SweepResult(
            targets=targets,
            executed=True,
            succeeded=succeeded,
            failed=failed,
            blocked=blocked,
            flagged=flagged,
            repaired=repaired,
            excluded=excluded,
            timed_out=timed_out,
            not_attempted=not_attempted,
        )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the re-moderation sweep script.

    Args:
        argv: Argument list, or None to use ``sys.argv``.

    Returns:
        The parsed namespace (``book_id`` list, ``mock_moderated`` bool,
        ``in_review`` bool, ``execute`` bool).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument(
        "--book-id",
        action="append",
        dest="book_id",
        metavar="STORYBOOK_ID",
        help="Re-moderate this storybook id (repeatable), at its current "
        "published version or, for an in_review book, its latest version. "
        "Mutually exclusive with the other selectors.",
    )
    selector.add_argument(
        "--mock-moderated",
        action="store_true",
        help="Target every published book whose current version looks "
        "mock-moderated (see module docstring's selection criteria). "
        "Mutually exclusive with the other selectors.",
    )
    selector.add_argument(
        "--in-review",
        action="store_true",
        dest="in_review",
        help="Target every in_review book, at its latest version, with no "
        "report-content filter. Mutually exclusive with the other selectors.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually call the re-moderation entry point for each target. "
        "Without this flag, only lists the targets; nothing is written.",
    )
    parser.add_argument(
        "--per-book-timeout",
        type=float,
        default=_PER_BOOK_TIMEOUT_SECONDS,
        dest="per_book_timeout",
        metavar="SECONDS",
        help="Wall-clock bound on one book's re-moderation (default: "
        f"{_PER_BOOK_TIMEOUT_SECONDS:.0f}). Exceeding it rolls that book back, "
        "releasing the row lock that would otherwise block an admin's "
        "approve or send-back on it, and abandons the remaining targets.",
    )
    return parser.parse_args(argv)


def _exit_on_excluded(result: SweepResult) -> None:
    """Exit nonzero when the sweep could not see every eligible book.

    Exits ``_EXIT_NEEDS_HUMAN``: an excluded book has no version row, and it
    will not grow one because a caller asked a second time. Retrying is pure
    waste, so the code says so.

    Args:
        result: The sweep outcome to inspect.
    """
    if result.excluded:
        print(
            f"remoderate_books: {len(result.excluded)} in_review book(s) "
            "were excluded from this sweep and remain un-re-moderated.",
            file=sys.stderr,
        )
        sys.exit(_EXIT_NEEDS_HUMAN)


# A database name and nothing else: one path segment, no separator that could
# only be there because the authority split went wrong.
_SAFE_DATABASE_PATH: Final = re.compile(r"\A(?:/[^/@:?#]*)?\Z")


# #CRITICAL: security: this renders a DSN for a banner that goes to a terminal
# and is scraped into CI logs, so it must be IMPOSSIBLE for a password to
# reach the output, not merely unlikely on a well-formed URL. Nothing upstream
# validates the DSN: `database_url` is a bare `str` on Settings. The previous
# form fell back to `parts.path` whenever there was no authority, so a URL
# missing `//` (or a scheme) put the ENTIRE credential-bearing remainder into
# the banner verbatim, and an unescaped `/` inside a password ended the netloc
# early and did the same on a URL that looked well-formed. The rule now is
# whitelist-then-refuse: emit only fields that a real authority positively
# yielded, and return "unparseable" the moment any part of the split looks
# like it landed somewhere it should not have. Refusing to describe the target
# is always safe here; the operator can still read the environment and
# provider from the same banner.
# #VERIFY: tests/unit/test_remoderate_books.py::
# TestDatabaseTarget::test_no_credential_survives_any_malformed_url and
# ::test_preflight_banner_never_prints_credentials_end_to_end.
def _database_target(database_url: str) -> str:
    """Render a connection URL as ``host:port/name``, dropping credentials.

    Args:
        database_url: The resolved async SQLAlchemy connection URL.

    Returns:
        str: A credential-free description of what this run will write to, or
        ``"unparseable"``. Never the password: this string is printed to a
        terminal and scraped into CI logs. ``"unparseable"`` covers three
        distinct refusals, deliberately collapsed into one opaque answer
        because telling them apart would itself describe the malformed URL:
        the URL does not split at all, it splits but yields no authority to
        read a host from, or it splits in a way that proves the authority
        boundary was misplaced (a truncated netloc, or a path that is not a
        bare database name).
    """
    try:
        parts = urlsplit(database_url)
        host = parts.hostname
        # #CRITICAL: data-integrity: `.port` is a lazy property that CASTS on
        # access, so it raises for a non-numeric or out-of-range port. Reading
        # it outside this `try` (as the previous form did) left the documented
        # "unparseable" contract unreachable for the likeliest malformed URLs,
        # since `urlsplit` itself does not validate the port at all.
        port = parts.port
    except ValueError:
        return "unparseable"
    if not host or not _SAFE_DATABASE_PATH.match(parts.path):
        return "unparseable"
    # If the URL carried userinfo, the netloc must still carry it. When it does
    # not, urlsplit ended the authority early (a `?`, `#`, or `/` inside the
    # password) and whatever "host" it produced is really a credential
    # fragment.
    if "@" in database_url and "@" not in parts.netloc:
        return "unparseable"
    # `hostname` strips the brackets an IPv6 literal needs; put them back
    # rather than emitting `::1:5432`, which reads as a different address.
    rendered_host = f"[{host}]" if ":" in host else host
    return f"{rendered_host}{f':{port}' if port else ''}{parts.path}"


# #CRITICAL: security: this preflight is the reason a canary run is worth
# anything. config.py's _require_real_reviewer_outside_local and the
# pipeline's mock-reviewer stamp were both once gated on
# environment != "local", and both read review_provider and environment from
# the process environment via a Settings object that declares no env_file, so
# a process started without those variables exported got
# review_provider="mock" and environment="local" together, from one absence,
# and disabled both at once. Printing what THIS run resolved, rather than
# trusting what the operator meant to set, is what makes that failure visible
# before a sweep rather than after one that appeared to succeed.
# #VERIFY: tests/unit/test_remoderate_books.py::
# test_main_refuses_to_execute_with_the_mock_reviewer,
# ::test_main_refusal_happens_before_the_sweep_runs,
# ::test_main_prints_the_resolved_target_before_executing,
# ::test_main_preflight_never_prints_database_credentials.
def _preflight(settings: Settings, *, execute: bool) -> None:
    """Print the resolved run target and refuse an execute with no reviewer.

    Scoped to ``main`` rather than ``sweep`` on purpose: a programmatic
    caller passing explicit settings has already declared its provider, and
    the pipeline stamps any mock-produced report as non-independent in every
    environment regardless. This guards the human at a terminal, who is the
    one who cannot see which variables the shell actually exported.

    Args:
        settings: The settings this run resolved, which are the same ones
            ``sweep`` will use when ``main`` does not pass its own.
        execute: Whether the run will write. A dry run makes no review calls,
            so the provider is irrelevant to it and nothing is printed.

    Raises:
        SystemExit: When ``execute`` is set and the resolved provider is the
            mock, which cannot produce a review.
    """
    if not execute:
        return
    # stderr, not stdout: the refusal below exits through `sys.exit(str)`,
    # which writes to stderr, and the banner is the context that refusal
    # refers to ("the resolved environment above"). Splitting the pair across
    # two streams meant a CI step or an operator redirecting either one kept
    # only half the safety story. Results stay on stdout; safety diagnostics
    # travel together on stderr.
    print(
        f"remoderate_books: environment={settings.environment} "
        f"database={_database_target(settings.database_url)} "
        f"review_provider={settings.review_provider}",
        file=sys.stderr,
    )
    if settings.review_provider == "mock":
        sys.exit(
            "remoderate_books: REFUSING --execute, the resolved "
            'review_provider is "mock", which returns no verdict and would '
            "rewrite every targeted node as a fail-safe default. Set "
            "CYO_ADVENTURE_REVIEW_PROVIDER to a real backend (and check the "
            f"resolved environment above, {settings.environment}, is the one "
            "you meant) before re-running."
        )


def main() -> None:
    """Entry point for the re-moderation sweep script.

    An ``--execute`` run passes through ``_preflight`` first, which prints the
    resolved environment, database, and reviewer to stderr and refuses the run
    outright when that reviewer is the mock. That refusal is the earliest exit
    in the script: it happens before any database work, so a mock-provider
    ``--execute`` produces the banner, the refusal, and no target list at all.

    Otherwise, prints the target list always, preceded by an exclusion warning
    whenever the sweep covered fewer books than the review queue holds. In dry-run
    (default), that is the only output. When ``--execute`` is given, also
    prints the succeeded/failed counts, the fresh verdicts, which books the
    repair pass rewrote, and exits nonzero if anything failed OR if any book
    came back hard-blocked OR if any book was excluded, so neither a partial
    sweep nor a book that just failed re-moderation is ever read as a clean
    success.

    The nonzero code distinguishes the two cases a retry loop must tell apart:
    ``1`` for a retryable failure and ``3`` for an outcome that needs a person.
    See :func:`_exit_on_outcome`.
    """
    args = _parse_args()
    _preflight(_default_settings, execute=args.execute)
    result = asyncio.run(
        sweep(
            book_ids=args.book_id,
            mock_moderated=args.mock_moderated,
            in_review=args.in_review,
            execute=args.execute,
            per_book_timeout_seconds=args.per_book_timeout,
        )
    )

    if result.excluded:
        # Printed before the target count, because the target count is exactly
        # the number this line corrects: without it, a sweep covering 15 of 17
        # queued books reads as a complete pass over "15 target book(s)".
        print(
            f"remoderate_books: WARNING, {len(result.excluded)} in_review "
            "book(s) were EXCLUDED from the target list because they have no "
            "version row, and were NOT re-moderated: " + ", ".join(result.excluded)
        )

    if not result.targets:
        print("remoderate_books: no target books found.")
        _exit_on_excluded(result)
        return

    print(f"remoderate_books: {len(result.targets)} target book(s):")
    for storybook_id, version in result.targets:
        print(f"  {storybook_id} v{version}")

    if not result.executed:
        print("remoderate_books: dry run, nothing executed. Pass --execute to run.")
        _exit_on_excluded(result)
        return

    print(
        f"remoderate_books: {len(result.succeeded)} succeeded "
        f"({len(result.blocked)} blocked, {len(result.flagged)} flagged), "
        f"{len(result.failed)} failed."
    )
    if result.flagged:
        print(
            "remoderate_books: soft-flagged (status unchanged by this sweep, "
            "review when convenient): "
            + ", ".join(f"{sid} v{v}" for sid, v in result.flagged)
        )
    if result.repaired:
        print(
            "remoderate_books: REPAIRED, the stored text of these books was "
            "rewritten by the repair pass and differs from what was last "
            "reviewed; re-read before approving: "
            + ", ".join(f"{sid} v{v}" for sid, v in result.repaired)
        )
    if result.blocked:
        # A hard block is the one outcome that needs a human today, and this
        # sweep does not provide one: ADR-005 reserves every status change for
        # a person, so each blocked book is exactly where it was. What that
        # means depends on which population was swept, and main() deliberately
        # spells out both rather than naming the mode, because --book-id can
        # mix them: a published book is still readable by a child RIGHT NOW,
        # while an in_review book is merely still queued. Print it loudly and
        # exit nonzero even though the re-moderation itself succeeded.
        print(
            "remoderate_books: HARD BLOCK, status unchanged by this sweep. A "
            "published book here is STILL published and STILL readable by a "
            "child; an in_review book is still waiting in the review queue. "
            "Act on these: " + ", ".join(f"{sid} v{v}" for sid, v in result.blocked)
        )
    if result.failed:
        print(
            "remoderate_books: failed (rolled back, retry by re-running): "
            + ", ".join(f"{sid} v{v}" for sid, v in result.failed)
        )
    if result.timed_out:
        # Printed separately from `failed` because the operator's next action
        # differs: a failure says re-run, a timeout says find out what is
        # wedged before spending more.
        print(
            "remoderate_books: TIMED OUT (rolled back, row lock released): "
            + ", ".join(f"{sid} v{v}" for sid, v in result.timed_out)
            + ". The sweep stopped here rather than driving the rest through"
            + " the same wedged path."
        )
    if result.not_attempted:
        print(
            "remoderate_books: not attempted after the timeout: "
            + ", ".join(f"{sid} v{v}" for sid, v in result.not_attempted)
        )
    _exit_on_outcome(result)


def _exit_on_outcome(result: SweepResult) -> None:
    """Exit with a code that says whether re-running could change the outcome.

    Splits the five non-clean outcomes into two classes:

    - Retryable (``_EXIT_RETRYABLE``): ``failed``, ``timed_out`` and
      ``not_attempted``. Each rolled back cleanly and left no durable state, so
      the same invocation may well succeed next time. A dropped pooler
      connection or a statement timeout lands here.
    - Needs a human (``_EXIT_NEEDS_HUMAN``): ``blocked`` and ``excluded``. The
      call SUCCEEDED and the answer was "no". A hard block moves only when a
      person edits prose or changes status, and an excluded book has no version
      row to re-moderate. Re-running re-derives the identical answer at full
      LLM cost.

    Retryable wins when a sweep produced both, because then there really is
    something a retry can fix; the blocked books are still named on stdout and
    survive into the next run's report.

    Note that soft ``flagged`` is deliberately absent from both classes and
    exits clean. It is informational: the status did not change and no action
    is required before the book can be read.

    Args:
        result: The sweep outcome to inspect.
    """
    retryable = result.failed or result.timed_out or result.not_attempted
    needs_human = result.blocked or result.excluded
    if not retryable and not needs_human:
        return

    print(
        f"remoderate_books: {len(result.failed)} book(s) failed "
        f"re-moderation, {len(result.blocked)} book(s) hard-blocked, "
        f"{len(result.excluded)} book(s) excluded, "
        f"{len(result.timed_out)} book(s) timed out, "
        f"{len(result.not_attempted)} book(s) not attempted.",
        file=sys.stderr,
    )
    if retryable:
        print(
            "remoderate_books: exit 1, RETRYABLE. Re-running may change this.",
            file=sys.stderr,
        )
        sys.exit(_EXIT_RETRYABLE)
    # Three short lines rather than one wrapped string: ruff's ISC003 requires
    # implicit concatenation and basedpyright's reportImplicitStringConcatenation
    # forbids it, so any two-part message here trips one tool or the other.
    print("remoderate_books: exit 3, NEEDS A HUMAN.", file=sys.stderr)
    print("  Retrying re-derives the same answer at full LLM cost.", file=sys.stderr)
    print("  Act on the books named above instead.", file=sys.stderr)
    sys.exit(_EXIT_NEEDS_HUMAN)


if __name__ == "__main__":
    main()
