"""Fail when any current storybook version carries an unusable moderation report.

Scope: for published books, the current_published_version; for in_review
books, the latest version. Reports are write-once, so any hit means either
the backfill sweep has not covered the book yet or the mock-reviewer
regression has recurred.

Defense-in-depth behind the approval gate in publishing/service.py::approve(),
which already refuses to approve a version whose report is unusable
(moderation.report.moderation_report_unusable): this script instead catches
a regression across the whole catalog on a schedule, so a future
mock-reviewer bug that slips past the gate (or a book that reached
"published" before the gate existed) surfaces the week it happens rather
than at the next human review.

``moderated_at`` in the printed line is the version row's created_at, a
deliberate simplification versus moderation/insights.py's more precise
MODERATION_COMPLETED event-timestamp derivation: that precision serves the
moderation dashboard's per-category trend analysis, but this script only
needs "roughly when" for a human triaging a rare, unexpected hit.

Run once, ad hoc::

    CYO_ADVENTURE_DATABASE_URL=... uv run python scripts/check_moderation_report_health.py

Scheduled via .github/workflows/moderation-report-health.yml.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.core.database import get_engine
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.moderation.report import moderation_report_unusable
from cyo_adventure.publishing.state_machine import Status
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_logger = get_logger(__name__)

# (storybook_id, version, moderation_report, created_at) as returned by both
# population queries below.
_VersionRow = tuple[str, int, "dict[str, object] | None", datetime]


@dataclass(frozen=True, slots=True)
class UnusableReportHit:
    """One current/latest version whose stored moderation report is unusable."""

    storybook_id: str
    version: int
    status: str
    moderated_at: datetime


def _hits_from_rows(
    rows: Iterable[_VersionRow], status_label: str
) -> list[UnusableReportHit]:
    """Return one hit per row whose moderation_report is unusable.

    Args:
        rows: (storybook_id, version, moderation_report, created_at) tuples
            for one population (either the current published version of
            every published book, or the latest version of every in_review
            book).
        status_label: The storybook status these rows were queried for
            ("published" or "in_review"), stamped onto each hit.

    Returns:
        A hit for every row whose report is unusable. Rows carrying a
        ``None`` report are skipped: unscreened is a different condition
        than unusable, already gated at approve time.
    """
    hits: list[UnusableReportHit] = []
    for storybook_id, version, moderation_report, created_at in rows:
        if moderation_report is None:
            continue
        if moderation_report_unusable(moderation_report):
            hits.append(
                UnusableReportHit(
                    storybook_id=storybook_id,
                    version=version,
                    status=status_label,
                    moderated_at=created_at,
                )
            )
    return hits


async def _load_published_rows(session: AsyncSession) -> Sequence[_VersionRow]:
    """Current published version of every published book."""
    result = await session.execute(
        select(
            StorybookVersion.storybook_id,
            StorybookVersion.version,
            StorybookVersion.moderation_report,
            StorybookVersion.created_at,
        )
        .join(
            Storybook,
            and_(
                StorybookVersion.storybook_id == Storybook.id,
                StorybookVersion.version == Storybook.current_published_version,
            ),
        )
        .where(
            Storybook.status == Status.PUBLISHED.value,
            Storybook.current_published_version.is_not(None),
        )
    )
    # Rebuilt as plain tuples via positional unpacking (not the SQLAlchemy Row
    # objects .all() returns directly, and not Row attribute access, which
    # basedpyright types as Any) so the return type matches _VersionRow
    # exactly, mirroring moderation/insights.py::load_version_records.
    return [
        (storybook_id, version, moderation_report, created_at)
        for storybook_id, version, moderation_report, created_at in result.all()
    ]


async def _load_in_review_rows(session: AsyncSession) -> Sequence[_VersionRow]:
    """Latest version of every in_review book."""
    latest_version = (
        select(
            StorybookVersion.storybook_id,
            func.max(StorybookVersion.version).label("latest_version"),
        )
        .group_by(StorybookVersion.storybook_id)
        .subquery()
    )
    result = await session.execute(
        select(
            StorybookVersion.storybook_id,
            StorybookVersion.version,
            StorybookVersion.moderation_report,
            StorybookVersion.created_at,
        )
        .join(
            latest_version,
            and_(
                latest_version.c.storybook_id == StorybookVersion.storybook_id,
                latest_version.c.latest_version == StorybookVersion.version,
            ),
        )
        .join(Storybook, Storybook.id == StorybookVersion.storybook_id)
        .where(Storybook.status == Status.IN_REVIEW.value)
    )
    return [
        (storybook_id, version, moderation_report, created_at)
        for storybook_id, version, moderation_report, created_at in result.all()
    ]


async def find_unusable_reports(session: AsyncSession) -> list[UnusableReportHit]:
    """Find every current/latest version whose moderation report is unusable.

    Args:
        session: The async session to query with.

    Returns:
        Hits across both populations: published books' current_published_version,
        and in_review books' latest version.
    """
    published_rows = await _load_published_rows(session)
    in_review_rows = await _load_in_review_rows(session)
    return _hits_from_rows(published_rows, "published") + _hits_from_rows(
        in_review_rows, "in_review"
    )


async def run_once(
    *,
    engine: AsyncEngine | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> list[UnusableReportHit]:
    """Run one health-check pass.

    Args:
        engine: Async engine to bind the session to. Defaults to the app's
            shared engine; tests inject a mock engine.
        session_factory: Callable returning a new ``AsyncSession``. Defaults
            to a sessionmaker bound to ``engine``; tests inject a mocked
            session factory here so no real database connection is required.

    Returns:
        list[UnusableReportHit]: Every hit found across both populations.
    """
    active_engine = engine if engine is not None else get_engine()
    new_session = (
        session_factory
        if session_factory is not None
        else async_sessionmaker(active_engine, expire_on_commit=False)
    )

    # #ASSUME: concurrency: read-only, no commit. Nothing here writes, so
    # unlike run_notification_digest.py there is no transaction to make
    # atomic; a plain scoped session for the duration of the two queries is
    # sufficient.
    # #VERIFY: tests/unit/test_check_moderation_report_health.py::
    # test_run_once_does_not_commit_a_read_only_pass.
    async with new_session() as session:
        return await find_unusable_reports(session)


def main() -> None:
    """Entry point: run one health-check pass, print, and exit on findings."""
    hits = asyncio.run(run_once())
    for hit in hits:
        print(
            f"{hit.storybook_id} v{hit.version} status={hit.status} "
            f"moderated_at={hit.moderated_at.isoformat()}"
        )
    print(f"unusable_reports={len(hits)}")
    if hits:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _logger.exception("check_moderation_report_health.failed")
        sys.exit(f"check_moderation_report_health: failed: {exc}")
