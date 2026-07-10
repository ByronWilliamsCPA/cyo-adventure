"""Series position assignment at generation completion (WS-B PR 3).

``book_index`` is assigned exactly here, when the storybook row is created,
never at request time (declined or failed requests would leave holes). The
uniqueness guard is the DB constraint plus one retry, per the ratified
umbrella decision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.core.exceptions import (
    BusinessLogicError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import Series as SeriesRow
from cyo_adventure.db.models import Storybook, StorybookVersion, StoryRequest
from cyo_adventure.generation.persistence import ensure_blob_within_budget
from cyo_adventure.storybook.models import Series as SeriesBlock
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


async def embed_series_block(
    session: AsyncSession, *, story_id: str, version: int
) -> None:
    """Write the embedded document ``Series`` block for a linked series book.

    WS-G G2: ``series_entry_node`` is the document's own ``start_node``;
    ``is_final`` is always False in v1 (open chains are valid post-SR-4
    relaxation); ``carries_state`` copies the series row. No-op for a book
    with no series linkage. Same transaction as linkage; the caller commits.

    Note: ``series_entry_node`` is populated for EVERY series book, including
    book 1 (ratified WS-G G2). This intentionally differs from the embedded
    ``Series`` model docstring's "None for the first book" phrasing, which
    describes the pre-WS-G validator-input convention.

    Raises:
        BusinessLogicError: If the storybook is already published or archived;
            approved blobs are immutable and must never be rewritten.
        ResourceNotFoundError: If the series row or version row is missing
            (FK-guaranteed in the worker flow; defensive for direct callers).
        ValidationError: If the blob has no string ``start_node``, or the
            embedded blob would exceed the byte budget.
    """
    storybook = await session.get(Storybook, story_id)
    if storybook is None or storybook.series_id is None or storybook.book_index is None:
        return
    # #CRITICAL: data-integrity: the approval gate's grandfather rule reasons
    # "approved blobs are immutable, so a legacy chain can never be made to
    # pass"; enforce that invariant here structurally instead of relying on
    # call-site discipline (a future backfill/regeneration caller must not
    # silently rewrite a published blob).
    # #VERIFY: test_embed_series_block_refuses_published_blob.
    if storybook.status in {"published", "archived"}:
        msg = (
            f"storybook '{story_id}' is {storybook.status}; approved blobs "
            "are immutable and embed_series_block must not rewrite them"
        )
        raise BusinessLogicError(msg, rule="embed_into_approved_blob")
    series_row = await session.get(SeriesRow, storybook.series_id)
    if series_row is None:
        msg = f"series '{storybook.series_id}' not found for '{story_id}'"
        raise ResourceNotFoundError(msg, resource_type="Series")
    version_row = await session.get(StorybookVersion, (story_id, version))
    if version_row is None:
        msg = f"version {version} of storybook '{story_id}' not found"
        raise ResourceNotFoundError(msg, resource_type="StorybookVersion")
    blob = dict(version_row.blob)
    entry = blob.get("start_node")
    # #ASSUME: data-integrity: a persisted blob always carries a string
    # start_node (persist_storybook schema-validates at write time), so a miss
    # here is bad upstream data, not a caller type error.
    # #VERIFY: the project ValidationError propagates to the worker's failure
    # handler, which rolls back the unreviewed persist and records the job as
    # failed instead of embedding a broken block.
    if not isinstance(entry, str):
        msg = f"storybook '{story_id}' v{version} blob has no string start_node"
        raise ValidationError(msg, field="start_node")
    block = SeriesBlock(
        series_id=str(storybook.series_id),
        book_index=storybook.book_index,
        series_entry_node=entry,
        is_final=False,
        carries_state=series_row.carries_state,
    )
    raw_meta = blob.get("metadata")
    metadata: dict[str, object] = (
        dict(cast("dict[str, object]", raw_meta)) if isinstance(raw_meta, dict) else {}
    )
    metadata["series"] = block.model_dump()
    blob["metadata"] = metadata
    ensure_blob_within_budget(blob)
    # #ASSUME: data-integrity: JSONB change detection requires reassigning
    # version_row.blob to a new dict; in-place mutation is invisible to the
    # session and would silently skip the UPDATE.
    # #VERIFY: test_embed_series_block_writes_metadata re-reads after commit.
    version_row.blob = blob
    await session.flush()
