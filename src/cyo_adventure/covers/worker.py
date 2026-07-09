"""RQ entrypoint and enqueue helper for cover generation."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from cyo_adventure.generation.queue import get_queue

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings

_COVER_ENTRYPOINT = "cyo_adventure.covers.worker.run_cover_job_sync"


def enqueue_cover(storybook_id: str, version: int, settings: Settings) -> str:
    """Enqueue a cover job on the shared "generation" queue; return the RQ id."""
    queue = get_queue(settings)
    job = queue.enqueue(
        _COVER_ENTRYPOINT,
        storybook_id,
        version,
        job_timeout=settings.cover_job_timeout_seconds,
    )
    return job.id


def run_cover_job_sync(storybook_id: str, version: int) -> None:
    """Sync RQ entrypoint: run the async cover job in its own session."""
    asyncio.run(_run(storybook_id, version))


async def _run(storybook_id: str, version: int) -> None:
    from cyo_adventure.core.config import settings
    from cyo_adventure.core.database import get_session
    from cyo_adventure.covers.service import generate_cover

    async with get_session() as session:
        await generate_cover(storybook_id, version, session=session, settings=settings)
