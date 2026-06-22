"""Thin RQ wrapper for enqueuing generation jobs.

Keeps the Redis/RQ wiring isolated from the worker body so the core logic in
:mod:`~cyo_adventure.generation.worker` remains callable directly without a
running Redis instance (critical for unit and integration tests).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis
from rq import Queue

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings

__all__ = [
    "enqueue_generation",
    "get_queue",
]

# The import path RQ will call in worker processes. Kept as a constant so
# tests and callers always reference the same entrypoint string.
_WORKER_ENTRYPOINT = "cyo_adventure.generation.worker.run_generation_job_sync"


def get_queue(settings: Settings) -> Queue:
    """Build an RQ :class:`~rq.Queue` from the application settings.

    The connection is created fresh on each call; in production a caller should
    cache the returned queue instance for the lifetime of the process.

    Args:
        settings: Application settings carrying ``redis_url``.

    Returns:
        An RQ :class:`~rq.Queue` named ``"generation"`` backed by the
        configured Redis instance.
    """
    # #ASSUME: external-resources: Redis must be reachable at settings.redis_url;
    # connection failures surface lazily when the first job is enqueued.
    # #VERIFY: Phase 2b adds a health-check probe for Redis on worker startup.
    conn = redis.Redis.from_url(settings.redis_url)
    return Queue("generation", connection=conn)


def enqueue_generation(job_id: str, settings: Settings) -> str:
    """Enqueue a generation job on the RQ ``"generation"`` queue.

    Args:
        job_id: The UUID string of the :class:`~cyo_adventure.db.models.GenerationJob`
            row to process. Must be a valid UUID string; the worker will
            re-parse it.
        settings: Application settings (used to build the queue connection and
            resolve the Redis URL).

    Returns:
        The RQ job id string (not the same as ``job_id``; this is RQ's own
        internal identifier for the enqueued task).
    """
    queue = get_queue(settings)
    rq_job = queue.enqueue(_WORKER_ENTRYPOINT, job_id)
    return str(rq_job.id)
