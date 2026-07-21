"""Process entry point for the RQ "generation" worker.

Run via ``python -m cyo_adventure.generation.worker_main`` in place of a bare
``rq worker generation`` invocation. The bare CLI form has no hook to run
application code before the worker starts pulling jobs off the queue, so the
stranded-job reclaim sweep (:func:`~cyo_adventure.generation.queue.requeue_stranded_jobs`)
never ran on a worker restart; this module runs it once, logs the count, and
then starts the same blocking work loop.

See ``docs/architecture/generation-pipeline.md`` for the pipeline this feeds.
"""

from __future__ import annotations

import asyncio

from rq import Worker

from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.database import (
    get_engine,
    get_worker_engine,
    get_worker_session,
)
from cyo_adventure.generation.queue import get_queue, requeue_stranded_jobs
from cyo_adventure.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = ["main"]


async def _reclaim_stranded_jobs() -> int:
    """Run the stranded-job reclaim sweep once, against a fresh worker session.

    Disposes BOTH the worker engine's and the API engine's connection pools
    on the way out, while this coroutine's event loop is still alive, so the
    worker loop (and every forked work horse) starts from empty pools.

    Returns:
        The number of ``"queued"`` rows re-enqueued.
    """
    try:
        async with get_worker_session() as session:
            return await requeue_stranded_jobs(session)
    finally:
        # #CRITICAL: concurrency: the sweep checks asyncpg connections out of
        # the module-level async engines' pools; once main()'s asyncio.run()
        # loop closes, any connection still sitting in a pool stays bound to
        # that dead loop. The next asyncio.run() in this process or a forked
        # RQ work horse (run_generation_job_sync) then crashes with
        # "got Future <...> attached to a different loop" (issue #150, live
        # job 5af1239c-80a0-489e-95e3-d05f69049d46). Disposing here, inside
        # the same event loop as the sweep and before Worker.work() forks
        # anything, empties both pools so job execution opens fresh
        # connections. ADR-021 widens this from one engine to two: this
        # process now also holds the worker engine's pool (used by the sweep
        # session above and by every generation job this process runs via
        # run_generation_job_sync's default get_worker_session factory), and
        # the API engine's pool remains reachable via get_engine() for any
        # shared module-level import path; both must be emptied before the
        # loop that populated them closes, or either can crash a later job
        # with the same cross-loop Future error.
        # #VERIFY: tests/unit/test_worker_main.py asserts both dispose calls
        # are awaited after the sweep and before Worker.work() starts.
        await get_worker_engine().dispose()
        await get_engine().dispose()


def main() -> None:
    """Reclaim stranded jobs, then start the blocking RQ worker loop.

    # #CRITICAL: timing: the sweep must complete before the worker starts
    # pulling new jobs, so a job stranded by a prior crash or Redis outage is
    # requeued instead of sitting invisibly at "queued" while this same
    # process idles waiting for fresh work.
    # #VERIFY: the sweep itself is covered by
    # tests/integration/test_queue_reclaim.py; this function is a thin,
    # deliberately-untested orchestration shim (asyncio.run + a blocking
    # Worker.work() call) exercised by tests/unit/test_worker_main.py with
    # both dependencies mocked.
    """
    requeued = asyncio.run(_reclaim_stranded_jobs())
    logger.info("generation_worker.reclaim_sweep_complete", requeued_count=requeued)

    queue = get_queue(_default_settings)
    worker = Worker([queue], connection=queue.connection)
    worker.work()


if __name__ == "__main__":
    main()
