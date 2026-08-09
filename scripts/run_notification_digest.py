"""Ops script: run the S9 server-scheduled notification digest job once.

Implements the "server-scheduled digest job" capability register/roadmap.md
Phase 4c left open: a periodic, batched per-family summary distinct from the
real-time poll and SSE push, neither of which is scheduled infrastructure
(see ``notifications/digest.py`` for the digest logic itself). This script
is the invocation shell: connect to the database, run one digest pass, print
a summary, exit nonzero on failure so a scheduled workflow reports it as a
failed run rather than a silent no-op.

Not a dry-run script like ``remoderate_books.py``: a digest write is cheap,
additive, and creates no externally-visible side effect beyond one more row
in a family's own in-app feed (no email, no push; see the module docstring
in ``notifications/digest.py`` for why), so there is no destructive action
to gate behind an explicit flag.

Run once, ad hoc::

    CYO_ADVENTURE_DATABASE_URL=... uv run python scripts/run_notification_digest.py

Scheduled via .github/workflows/notification-digest.yml.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.core.database import get_engine
from cyo_adventure.notifications.digest import run_notification_digest
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_logger = get_logger(__name__)


async def run_once(
    *,
    engine: AsyncEngine | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
    now: datetime | None = None,
) -> int:
    """Run one digest pass in its own transaction and commit.

    Args:
        engine: Async engine to bind the session to. Defaults to the app's
            shared engine; tests inject a mock engine.
        session_factory: Callable returning a new ``AsyncSession``. Defaults
            to a sessionmaker bound to ``engine``; tests inject a mocked
            session factory here so no real database connection is required.
        now: The wall-clock time to pass through to
            :func:`run_notification_digest`. Defaults to the real current
            time; tests pass a fixed value.

    Returns:
        int: The number of families a digest event was written for.
    """
    active_engine = engine if engine is not None else get_engine()
    new_session = (
        session_factory
        if session_factory is not None
        else async_sessionmaker(active_engine, expire_on_commit=False)
    )
    active_now = now if now is not None else datetime.now(UTC)

    async with new_session() as session:
        written = await run_notification_digest(session, now=active_now)
        # #CRITICAL: data-integrity: a single commit for the whole pass, not
        # per-family. Unlike remoderate_books.py's per-book commit (which
        # protects expensive, individually-retryable LLM work), a digest
        # write is cheap and the whole pass is idempotent to re-run from
        # scratch on failure (each family's own cursor just does not
        # advance), so there is nothing gained by partial durability here
        # and it keeps the pass atomic: either every family that had
        # something pending gets a digest, or (on failure) none do.
        # #VERIFY: tests/unit/test_run_notification_digest.py::
        # test_run_once_commits_after_the_whole_pass.
        await session.commit()
    return written


def main() -> None:
    """Entry point: run one digest pass and print/exit based on the result."""
    written = asyncio.run(run_once())
    print(f"run_notification_digest: wrote {written} digest event(s).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _logger.exception("run_notification_digest.failed")
        sys.exit(f"run_notification_digest: failed: {exc}")
