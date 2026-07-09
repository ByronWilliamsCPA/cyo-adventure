"""RQ entrypoint and enqueue helper for cover generation."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from structlog.contextvars import bind_contextvars

from cyo_adventure.generation.queue import get_queue

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings

_COVER_ENTRYPOINT = "cyo_adventure.covers.worker.run_cover_job_sync"


def enqueue_cover(
    storybook_id: str,
    version: int,
    settings: Settings,
    correlation_id: str | None = None,
) -> str:
    """Enqueue a cover job on the shared "generation" queue; return the RQ id."""
    # #CRITICAL: external resources: RQ enqueue talks to Redis; a broker outage
    # raises here and the caller must roll cover_status off "generating".
    # #VERIFY: api/covers.py::request_cover wraps this call and resets the row.
    queue = get_queue(settings)
    job = queue.enqueue(
        _COVER_ENTRYPOINT,
        storybook_id,
        version,
        correlation_id,
        job_timeout=settings.cover_job_timeout_seconds,
    )
    return job.id


def run_cover_job_sync(
    storybook_id: str, version: int, correlation_id: str | None = None
) -> None:
    """Sync RQ entrypoint: run the async cover job in its own session."""
    # #ASSUME: security: bind the request's correlation id into the worker log
    # context so cover_* log lines trace back to the admin request that queued
    # the job (the worker runs outside CorrelationMiddleware).
    # #VERIFY: generate_cover's log calls inherit the bound contextvar.
    if correlation_id:
        bind_contextvars(correlation_id=correlation_id)
    asyncio.run(_run(storybook_id, version))


async def _run(storybook_id: str, version: int) -> None:
    # #CRITICAL: external resources: opens its own DB session and drives the
    # Gemini + Supabase calls via generate_cover; runs outside request context.
    # #VERIFY: generate_cover never raises and always lands a terminal status.
    from cyo_adventure.core.config import settings
    from cyo_adventure.core.database import get_session
    from cyo_adventure.covers.service import generate_cover

    async with get_session() as session:
        await generate_cover(storybook_id, version, session=session, settings=settings)
