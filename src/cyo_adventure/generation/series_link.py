"""Series position assignment at generation completion (WS-B PR 3).

``book_index`` is assigned exactly here, when the storybook row is created,
never at request time (declined or failed requests would leave holes). The
uniqueness guard is the DB constraint plus one retry, per the ratified
umbrella decision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.db.models import Storybook, StoryRequest
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

_MAX_ATTEMPTS = 2
_UNIQUE_CONSTRAINT = "uq_storybook_series_book_index"


async def link_series_position(
    session: AsyncSession, *, story_id: str, concept_id: uuid.UUID
) -> None:
    """Link a freshly persisted storybook into its request's series, if any.

    Resolves the originating StoryRequest by ``concept_id``; a concept created
    outside the request flow (direct POST /concepts) has no request row and is
    a silent no-op, as is a request with no series.
    """
    request = await session.scalar(
        select(StoryRequest).where(StoryRequest.concept_id == concept_id)
    )
    # #ASSUME: data-integrity: a concept with no owning request, or a request
    # with no series, is a legitimate non-series generation and is skipped. An
    # anchored request always has series_id (ck_story_request_anchor_requires_series),
    # so this no-op cannot silently drop a continuation out of its series.
    # #VERIFY: test_series_link covers the direct/non-series no-op path.
    if request is None or request.series_id is None:
        return
    index = await assign_book_index(
        session, story_id=story_id, series_id=request.series_id
    )
    logger.info(
        "storybook.series_position_assigned",
        storybook_id=story_id,
        series_id=str(request.series_id),
        book_index=index,
    )


async def assign_book_index(
    session: AsyncSession, *, story_id: str, series_id: uuid.UUID
) -> int:
    """Assign the next book_index in a series to a storybook row.

    # #CRITICAL: concurrency: two continuations of the same series racing on book_index
    # #VERIFY: unique constraint plus one retry on conflict; concurrency test in PR 3
    The read-compute-write is not atomic: two workers can both read
    ``max(book_index) == N`` and both try ``N + 1``. Postgres blocks the
    second flush on the first transaction's unique-index entry; once the
    first commits, the second raises IntegrityError, the savepoint unwinds,
    and the single retry recomputes against the now-visible row. A second
    consecutive conflict re-raises (three-way races are not a WS-B scale
    concern; the job then fails loudly rather than corrupting the chain).

    Returns:
        int: The assigned 1-based index.

    Raises:
        IntegrityError: If both attempts conflict.
    """
    storybook = await session.get(Storybook, story_id)
    if storybook is None:
        msg = f"storybook '{story_id}' not found for series assignment"
        raise ValueError(msg)
    last_error: IntegrityError | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with session.begin_nested():
                # #CRITICAL: concurrency: the attribute writes must happen
                # *inside* the savepoint block, not before it. Session.begin_nested()
                # autoflushes any already-dirty state before the SAVEPOINT is
                # established, which would run the conflicting UPDATE against the
                # outer transaction and corrupt it instead of just the savepoint.
                # #VERIFY: test_retry_recovers_from_stale_read and
                # test_two_conflicts_raise exercise this against a real
                # IntegrityError from the unique constraint.
                next_index = await _next_index(session, series_id)
                storybook.series_id = series_id
                storybook.book_index = next_index
                await session.flush()
        except IntegrityError as exc:
            # Only the (series_id, book_index) unique conflict is a retryable
            # race. An FK or check violation is a non-transient logic/data error
            # that a retry cannot resolve; re-raise it immediately rather than
            # mislabeling it as a book_index conflict and retrying pointlessly.
            if _UNIQUE_CONSTRAINT not in str(exc.orig):
                raise
            last_error = exc
            logger.warning(
                "storybook.book_index_conflict",
                storybook_id=story_id,
                series_id=str(series_id),
                attempt=attempt,
            )
            continue
        return next_index
    if last_error is None:  # pragma: no cover - loop invariant
        msg = "retry loop exited without an error"
        raise RuntimeError(msg)
    raise last_error


async def _next_index(session: AsyncSession, series_id: uuid.UUID) -> int:
    """Compute max(book_index) + 1 for a series (module-level for testability)."""
    current = await session.scalar(
        select(func.max(Storybook.book_index)).where(Storybook.series_id == series_id)
    )
    return int(current or 0) + 1
