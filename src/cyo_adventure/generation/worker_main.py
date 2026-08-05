"""Process entry point for the RQ "generation" worker.

Run via ``python -m cyo_adventure.generation.worker_main`` in place of a bare
``rq worker generation`` invocation. The bare CLI form has no hook to run
application code before the worker starts pulling jobs off the queue, so the
stranded-job reclaim sweep (:func:`~cyo_adventure.generation.queue.requeue_stranded_jobs`)
never ran on a worker restart; this module runs it once, logs the count, and
then starts the same blocking work loop.

It also uses that hook for the worker half of the ADR-021 cutover signal: the
worker's own database role posture is probed once and logged before the sweep,
because nothing outside this process can observe which credential the worker
connects with (see :func:`_log_worker_role_posture`).

See ``docs/architecture/generation-pipeline.md`` for the pipeline this feeds.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rq import Worker

from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.database import (
    get_engine,
    get_worker_engine,
    get_worker_session,
)
from cyo_adventure.core.rls_posture import measure_role_posture
from cyo_adventure.generation.queue import get_queue, requeue_stranded_jobs
from cyo_adventure.utils.logging import get_logger, setup_logging

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

__all__ = ["main"]


async def _log_worker_role_posture(session: AsyncSession) -> None:
    """Record which database role this worker actually connects as (ADR-021).

    The worker is the half of the cutover nothing else can see. ``/health/ready``'s
    ``database_privilege`` check runs in the API process against the API engine,
    the worker serves no HTTP, and ``CYO_ADVENTURE_WORKER_DATABASE_URL`` falls
    back to ``CYO_ADVENTURE_DATABASE_URL`` in silence when unset
    (``core/config.py::worker_database_url_effective``). A forgotten worker
    credential is therefore indistinguishable from a completed cutover by
    inspection; before this line existed the only way to tell was to catch a
    generation job mid-flight and read ``pg_stat_activity``.

    Logs on ALL THREE outcomes on purpose (least-privileged, bypasses,
    unmeasurable). A probe that is silent on success makes "cut over" and
    "probe never ran" the same log, which is the ambiguity this is here to
    remove. All three are WARNING-level so they survive the production
    ``LOG_LEVEL=WARNING`` default, per ``docs/operations/security-events.md``
    section 4; an ``info`` posture line is dropped in production, which turns a
    successful cutover back into the silence this function exists to break.

    Every role-bearing event carries ``worker_dsn_explicitly_set``, because the
    role name alone cannot distinguish "cut over to cyo_worker" from "fell back
    to the API DSN and happens to be least-privileged too". ``cyo_api`` also has
    ``rolbypassrls = false`` and owns no Tier 1 table, so the fallback state
    emits the *affirmative* event; without this field an operator alerting on
    the bypass event sees green while the worker still shares the API
    credential.

    #CRITICAL: security: the probe never gates startup. A pre-cutover worker is
    an open security finding, but a worker that refuses to start is an outage,
    and refusing to process stories because a diagnostic query failed trades a
    smaller problem for a larger one. Alert on the warning events instead.
    A failed probe MUST roll the session back before returning: the probe and
    the reclaim sweep share one transaction, and PostgreSQL refuses every later
    statement on an aborted one (SQLSTATE 25P02
    ``InFailedSQLTransactionError``), so swallowing the error without a
    rollback converts a failed diagnostic into a worker that never starts, and
    with ``restart_policy: on-failure`` into an uncapped crash loop.
    #VERIFY: tests/integration/test_worker_role_posture.py::
    test_statement_error_in_probe_still_lets_the_sweep_run drives a real
    aborted transaction against PostgreSQL. A stubbed session cannot reach this
    failure mode, and neither can SQLite, so the unit test is not sufficient
    proof of the non-gating contract on its own.

    Args:
        session: A session on the WORKER engine. Passing an API-engine session
            silently answers a different question than the operator asked.
    """
    try:
        posture = await measure_role_posture(session)
    except Exception as exc:  # noqa: BLE001 -- diagnostic must not gate startup
        # Line-scoped, not a per-file-ignores entry: this is the only blind
        # catch this module is entitled to. The reclaim sweep below it must keep
        # failing fast, pinned by test_sweep_failure_disposes_engine_and_never_
        # starts_the_worker, and a file-scoped exemption would silently cover a
        # future blind catch there too.
        #
        # The posture is unmeasured, not known-good. Distinct event name from
        # the known-bad case below so an alert on "bypasses" stays actionable
        # and is not diluted by broken probes.
        logger.warning("generation_worker.rls_posture_unknown", error=str(exc))
        # A statement error has already aborted the shared transaction; without
        # this the caller's sweep dies on 25P02 and the worker never starts.
        # A no-op when the transaction was never begun or is still clean.
        await session.rollback()
        return

    # Truthiness, not "is not None": compose interpolation of an unset
    # ${WORKER_DATABASE_URL:-} injects "", which config.py's
    # worker_database_url_effective also treats as "no DSN configured".
    dsn_set = bool(_default_settings.worker_database_url)

    if posture.bypasses_rls:
        logger.warning(
            "generation_worker.role_bypasses_rls",
            role=posture.role_name,
            # An operator fixes role attributes and table ownership
            # differently, so "it bypasses" alone is not actionable.
            via_role_attribute=posture.via_role_attribute,
            via_table_ownership=posture.via_table_ownership,
            worker_dsn_explicitly_set=dsn_set,
        )
        return

    logger.warning(
        "generation_worker.role_least_privileged",
        role=posture.role_name,
        worker_dsn_explicitly_set=dsn_set,
    )


async def _run_worker_startup() -> int:
    """Probe the worker's role posture, then run the reclaim sweep once.

    Both run against the same fresh worker session, inside one event loop, so
    the posture reported is the identity the sweep and every subsequent job
    actually use.

    Disposes BOTH the worker engine's and the API engine's connection pools
    on the way out, while this coroutine's event loop is still alive, so the
    worker loop (and every forked work horse) starts from empty pools.

    Returns:
        The number of ``"queued"`` rows re-enqueued.
    """
    try:
        async with get_worker_session() as session:
            # Posture first: a sweep that crashes still leaves the cutover
            # verdict in the log for the deploy that caused the crash. This
            # ordering is safe only because the probe rolls back on failure;
            # without that, a failed probe poisons this shared transaction and
            # takes the sweep (and the worker's startup) with it.
            await _log_worker_role_posture(session)
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

    # #CRITICAL: security: the worker process has no other logging-setup hook
    # (it is started as `python -m cyo_adventure.generation.worker_main`), so
    # without this call it ran on structlog's defaults: no level filtering,
    # no JSON renderer, no correlation_context_processor, and no censoring
    # processor. It must come FIRST, before the sweep, or the sweep's own log
    # lines are emitted unconfigured.
    # #VERIFY: tests/unit/test_worker_main.py::
    # test_main_configures_logging_before_anything_else pins both the call
    # arguments and the ordering.
    """
    setup_logging(
        level=_default_settings.log_level,
        json_logs=_default_settings.json_logs,
        include_timestamp=_default_settings.include_timestamp,
    )
    requeued = asyncio.run(_run_worker_startup())
    logger.info("generation_worker.reclaim_sweep_complete", requeued_count=requeued)

    queue = get_queue(_default_settings)
    worker = Worker([queue], connection=queue.connection)
    worker.work()


if __name__ == "__main__":
    main()
