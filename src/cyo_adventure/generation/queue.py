"""Thin RQ wrapper for enqueuing generation jobs.

Keeps the Redis/RQ wiring isolated from the worker body so the core logic in
:mod:`~cyo_adventure.generation.worker` remains callable directly without a
running Redis instance (critical for unit and integration tests).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import redis
from rq import Queue
from rq.exceptions import DuplicateJobError
from sqlalchemy import select

from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.db.models import GenerationJob
from cyo_adventure.events.models import Actor, EventType
from cyo_adventure.events.writer import record_event
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.core.config import Settings

logger = get_logger(__name__)

__all__ = [
    "enqueue_generation",
    "get_queue",
    "requeue_stranded_jobs",
]

# The import path RQ will call in worker processes. Kept as a constant so
# tests and callers always reference the same entrypoint string.
_WORKER_ENTRYPOINT = "cyo_adventure.generation.worker.run_generation_job_sync"

# Bound the synchronous Redis client so a slow or unreachable Redis fails fast
# instead of hanging the caller (the enqueue runs in a request background task;
# an unbounded connect would tie up a threadpool worker indefinitely).
_REDIS_TIMEOUT_SECONDS = 2.0

# Default staleness window for the reclaim sweep: comfortably longer than any
# legitimate queue depth for this app's job volume, short enough to recover
# quickly from a genuine Redis/worker outage.
_DEFAULT_STALE_AFTER = timedelta(minutes=30)


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
    # connection failures surface (within the bounded timeout) when the first
    # job is enqueued.
    # #VERIFY: Phase 2b adds a health-check probe for Redis on worker startup.
    conn = redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=_REDIS_TIMEOUT_SECONDS,
        socket_timeout=_REDIS_TIMEOUT_SECONDS,
    )
    return Queue("generation", connection=conn)


def enqueue_generation(
    job_id: str, settings: Settings, *, rq_job_id: str | None = None
) -> str:
    """Enqueue a generation job on the RQ ``"generation"`` queue.

    Args:
        job_id: The UUID string of the :class:`~cyo_adventure.db.models.GenerationJob`
            row to process. Must be a valid UUID string; the worker will
            re-parse it.
        settings: Application settings (used to build the queue connection,
            resolve the Redis URL, and set the per-job timeout).
        rq_job_id: Optional explicit id for RQ's own job object (distinct from
            ``job_id``, though callers pass the same value). When ``None``
            (the normal enqueue path), RQ generates its own id and no
            uniqueness check is requested. The stranded-job reclaim sweep
            (:func:`requeue_stranded_jobs`) passes ``job_id`` here so a
            re-enqueue of a row that is merely deep in the queue, not
            actually lost, reuses the same RQ job identity instead of
            creating a second, redundant execution; see the ``unique``
            RAD note below for why passing ``rq_job_id`` alone is not
            sufficient for that guarantee.

    Returns:
        The RQ job id string (equal to ``rq_job_id`` when given, otherwise
        RQ's own generated identifier).

    Raises:
        rq.exceptions.DuplicateJobError: When ``rq_job_id`` is given and a job
            with that id already exists on the queue. Callers that intend a
            re-enqueue-if-not-already-queued semantic (the reclaim sweep) must
            catch this and treat it as a no-op; see
            :func:`requeue_stranded_jobs`.
    """
    queue = get_queue(settings)
    # #CRITICAL: timing: RQ's default job_timeout (180s) is far shorter than a
    # live Ollama generation run; every enqueue call must set job_timeout
    # explicitly (see Settings.generation_job_timeout_seconds) so RQ's SIGALRM
    # never kills a still-healthy job mid-run.
    # #VERIFY: test_enqueue_generation_passes_job_timeout asserts the kwarg
    # reaches the underlying queue.enqueue() call.
    #
    # #CRITICAL: concurrency: passing job_id=<row id> alone does NOT make this
    # enqueue idempotent. RQ only atomically check-and-skips a duplicate id
    # when unique=True is ALSO passed; without it, RQ silently rpushes a
    # second list entry for the same id, so a row that is merely deep in the
    # queue (not actually lost) would get run_generation_job_sync invoked
    # TWICE concurrently (duplicate LLM calls, a persist_storybook primary-key
    # race). unique=True is set whenever rq_job_id is supplied. Both the normal
    # per-request enqueue (api/generation.py::_enqueue_safely) and the reclaim
    # sweep now pass rq_job_id=row_id, so they share one identity and RQ raises
    # DuplicateJobError rather than admit a second execution of the same row.
    # A caller that passes rq_job_id=None (none in production today) opts out.
    # #VERIFY: exercised by test_enqueue_generation_second_call_same_id_raises_duplicate,
    # which runs the REAL rq.Queue.enqueue (a Redis testcontainer, not a mock)
    # and asserts a second call with the same rq_job_id raises DuplicateJobError
    # instead of growing the queue's job_ids list to two entries.
    rq_job = queue.enqueue(
        _WORKER_ENTRYPOINT,
        job_id,
        job_timeout=settings.generation_job_timeout_seconds,
        job_id=rq_job_id,
        unique=rq_job_id is not None,
    )
    return str(rq_job.id)


async def requeue_stranded_jobs(
    session: AsyncSession,
    stale_after: timedelta = _DEFAULT_STALE_AFTER,
    running_stale_after: timedelta | None = None,
) -> int:
    """Reclaim jobs stranded by an enqueue outage or a hard worker death.

    Two failure modes leave a job unrecoverable without this sweep, and both
    permanently consume a slot of the per-family active-job cap
    (``api/generation.py::MAX_ACTIVE_JOBS_PER_FAMILY``), which counts both
    ``"queued"`` and ``"running"`` rows:

    1. **Stranded at ``"queued"``**: the background enqueue never reached Redis
       (a Redis outage; see ``api/generation.py::_enqueue_safely``) or RQ/Redis
       lost the job (a Redis restart with no persistence). These are
       re-enqueued.
    2. **Stranded at ``"running"``**: the worker was hard-killed (SIGKILL, OOM,
       power loss) after committing the ``queued -> running`` transition but
       before the pipeline's own ``finally`` guard could run. No signal unwinds
       Python in that case, so the guard never fires and the row sits
       ``"running"`` forever. These are force-failed with
       ``error="interrupted: worker died"``, mirroring the finally guard, and
       are NOT auto-re-enqueued: the job may already have spent provider budget,
       so recovery is an explicit guardian/operator retry, not a silent re-run.

    Call this once when a worker process starts, before it begins pulling jobs.

    # #CRITICAL: concurrency: a job legitimately waiting in a deep queue must
    # not be double-enqueued. enqueue_generation passes unique=True whenever
    # rq_job_id=row_id is given (below), so RQ raises DuplicateJobError instead
    # of silently pushing a second queue entry when the row is already queued
    # under this id; that is the desired outcome (the row IS still queued), so
    # it is caught per-row and treated as a no-op, not a sweep failure, and is
    # excluded from the returned reclaim count. Now that the original enqueue
    # also uses rq_job_id=row_id (api/generation.py::_enqueue_safely), the
    # sweep and the original share one identity, so a still-queued original is
    # correctly recognized as a duplicate rather than run a second time.
    # #VERIFY: test_requeue_stranded_jobs_second_sweep_same_row_is_queue_idempotent
    # and test_reclaim_after_completed_run_does_not_re_execute.

    Args:
        session: Active async session. Writes and commits when it force-fails a
            stranded ``"running"`` row; performs no writes for the queued sweep.
        stale_after: How long a row may sit at ``"queued"`` before it is
            considered lost and re-enqueued. Defaults to 30 minutes.
        running_stale_after: How long a row may sit at ``"running"`` before it
            is considered a dead worker's orphan and force-failed. Defaults to
            the configured generation job timeout plus a 5-minute margin, so a
            still-legitimately-running job is never reaped early.

    Returns:
        The number of rows reclaimed: queued rows actually re-enqueued (excluding
        already-queued no-ops) plus running rows force-failed.
    """
    now = datetime.now(UTC)
    reclaimed = 0

    # --- Sweep 1: re-enqueue rows lost while queued. -----------------------
    queued_cutoff = now - stale_after
    queued_result = await session.execute(
        select(GenerationJob).where(
            GenerationJob.status == "queued",
            GenerationJob.updated_at < queued_cutoff,
        )
    )
    for row in queued_result.scalars().all():
        row_id = str(row.id)
        try:
            enqueue_generation(row_id, _default_settings, rq_job_id=row_id)
            reclaimed += 1
        except DuplicateJobError:
            logger.info("requeue_stranded_jobs.already_queued", job_id=row_id)

    # --- Sweep 2: force-fail rows orphaned by a hard worker death. ----------
    if running_stale_after is None:
        running_stale_after = timedelta(
            seconds=_default_settings.generation_job_timeout_seconds
        ) + timedelta(minutes=5)
    running_cutoff = now - running_stale_after
    running_result = await session.execute(
        select(GenerationJob).where(
            GenerationJob.status == "running",
            GenerationJob.updated_at < running_cutoff,
        )
    )
    orphaned = list(running_result.scalars().all())
    for row in orphaned:
        row.status = "failed"
        row.error = "interrupted: worker died"
        # #CRITICAL: data-integrity: the failure event must land in the same
        # transaction as the status write (spec D1); record_event only flushes.
        # #VERIFY: test_requeue_force_fails_stranded_running_row asserts the row
        # lands "failed" with a matching generation_finished event.
        await record_event(
            session,
            Actor.system(),
            entity_type="generation_job",
            entity_id=str(row.id),
            event_type=EventType.GENERATION_FINISHED,
            from_state="running",
            to_state="failed",
            payload={"outcome": "failed"},
        )
        reclaimed += 1
        logger.warning("requeue_stranded_jobs.force_failed_orphan", job_id=str(row.id))
    if orphaned:
        await session.commit()

    return reclaimed
