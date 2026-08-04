"""Unit tests for the RQ worker process entry point (no Redis, no DB).

Both dependencies of :func:`~cyo_adventure.generation.worker_main.main` (the
reclaim sweep and the RQ ``Worker``) are mocked so this exercises only the
ordering contract: the stranded-job reclaim sweep must complete before the
worker starts its blocking work loop.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from rq import Queue, Worker
from sqlalchemy.ext.asyncio import AsyncEngine

from cyo_adventure.core.rls_posture import RolePosture
from cyo_adventure.generation import worker_main

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class _FakeSession:
    """Marker object standing in for an AsyncSession; never touches a DB."""


def _install_fake_engine(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace worker_main.get_engine with one returning a dispose-mocked engine.

    ADR-021: also installs a separate fake worker engine on
    ``worker_main.get_worker_engine`` (both must be disposed), but only the
    API-engine fake is returned, preserving this helper's existing call
    signature for the tests below that only assert on the API engine.

    Returns:
        The fake API engine whose ``dispose`` is an ``AsyncMock``.
    """
    fake_engine = MagicMock(spec=AsyncEngine)
    fake_engine.dispose = AsyncMock()
    monkeypatch.setattr(worker_main, "get_engine", lambda: fake_engine)

    fake_worker_engine = MagicMock(spec=AsyncEngine)
    fake_worker_engine.dispose = AsyncMock()
    monkeypatch.setattr(worker_main, "get_worker_engine", lambda: fake_worker_engine)

    return fake_engine


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_worker_startup_uses_a_fresh_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_run_worker_startup opens a session and returns requeue_stranded_jobs' count.

    Kept as a direct private-function test deliberately: the return-value
    contract (the requeued count) is consumed by main() only as a structlog
    field, so the public entry point cannot observe it without introspecting
    log output. The ordering/failure behaviors ARE driven through main() in
    the tests below.
    """

    @asynccontextmanager
    async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
        yield _FakeSession()

    async def _fake_requeue(session: object, **_kwargs: object) -> int:
        assert isinstance(session, _FakeSession)
        return 3

    monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
    monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
    fake_engine = _install_fake_engine(monkeypatch)

    count = await worker_main._run_worker_startup()

    assert count == 3
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.unit
def test_sweep_failure_disposes_engine_and_never_starts_the_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sweep failure still disposes the engine pool, and the worker never starts.

    Driven through the public entry point main() (not a direct call to the
    private ``_run_worker_startup``): the sweep's exception propagates out
    of ``asyncio.run`` and out of ``main()``, so the public path reaches this
    case deterministically. This also pins the fail-fast contract that a
    process whose reclaim sweep crashed does not go on to pull new jobs.
    """

    @asynccontextmanager
    async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
        yield _FakeSession()

    async def _fake_requeue(session: object, **_kwargs: object) -> int:
        _ = session
        msg = "sweep exploded"
        raise RuntimeError(msg)

    monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
    monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
    fake_engine = _install_fake_engine(monkeypatch)
    fake_get_queue = MagicMock()
    monkeypatch.setattr(worker_main, "get_queue", fake_get_queue)

    with pytest.raises(RuntimeError, match="sweep exploded"):
        worker_main.main()

    fake_engine.dispose.assert_awaited_once()
    fake_get_queue.assert_not_called()


@pytest.mark.unit
def test_main_sweeps_before_starting_the_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() runs the reclaim sweep, then constructs and starts the RQ worker.

    #CRITICAL: timing: a job stranded by a prior crash must be requeued
    before this same process would otherwise sit idle waiting for new work;
    this test locks in that ordering.

    Runs the REAL ``_run_worker_startup`` (mocking only its session/queue
    boundaries) instead of patching the private function, so the ordering
    contract is exercised through the public ``main()`` path end to end.
    """
    calls: list[str] = []

    @asynccontextmanager
    async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
        yield _FakeSession()

    async def _fake_requeue(session: object, **_kwargs: object) -> int:
        _ = session
        calls.append("sweep")
        return 2

    fake_queue = MagicMock(spec=Queue)
    fake_queue.connection = "fake-connection"
    fake_worker_instance = MagicMock(spec=Worker)

    def _fake_get_queue(settings: object) -> MagicMock:
        _ = settings
        return fake_queue

    def _fake_worker_cls(queues: object, *, connection: object) -> MagicMock:
        calls.append("worker_constructed")
        assert queues == [fake_queue]
        assert connection == "fake-connection"
        return fake_worker_instance

    monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
    monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
    _install_fake_engine(monkeypatch)
    monkeypatch.setattr(worker_main, "get_queue", _fake_get_queue)
    monkeypatch.setattr(worker_main, "Worker", _fake_worker_cls)

    worker_main.main()

    assert calls == ["sweep", "worker_constructed"]
    fake_worker_instance.work.assert_called_once()


@pytest.mark.unit
@pytest.mark.security
def test_main_configures_logging_before_anything_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() calls setup_logging from settings before the sweep or the worker.

    Regression: worker_main imported only ``get_logger``, so the worker
    process ran on structlog's defaults, with no level filtering, no JSON
    renderer, and no ``correlation_context_processor``. The call must come
    first, or the sweep's own log lines are emitted unconfigured.
    """
    calls: list[str] = []
    setup_kwargs: list[dict[str, object]] = []

    @asynccontextmanager
    async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
        yield _FakeSession()

    async def _fake_requeue(session: object, **_kwargs: object) -> int:
        _ = session
        calls.append("sweep")
        return 0

    def _fake_setup_logging(**kwargs: object) -> None:
        calls.append("setup_logging")
        setup_kwargs.append(kwargs)

    fake_queue = MagicMock(spec=Queue)
    fake_queue.connection = "fake-connection"
    fake_worker_instance = MagicMock(spec=Worker)

    def _fake_worker_cls(queues: object, *, connection: object) -> MagicMock:
        _ = queues, connection
        calls.append("worker_constructed")
        return fake_worker_instance

    monkeypatch.setattr(worker_main, "setup_logging", _fake_setup_logging)
    monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
    monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
    _install_fake_engine(monkeypatch)
    monkeypatch.setattr(worker_main, "get_queue", lambda _settings: fake_queue)
    monkeypatch.setattr(worker_main, "Worker", _fake_worker_cls)

    worker_main.main()

    assert calls == ["setup_logging", "sweep", "worker_constructed"]
    assert setup_kwargs == [
        {
            "level": worker_main._default_settings.log_level,
            "json_logs": worker_main._default_settings.json_logs,
            "include_timestamp": worker_main._default_settings.include_timestamp,
        }
    ]


@pytest.mark.unit
def test_main_disposes_engine_after_sweep_and_before_worker_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() awaits both engines' dispose() after the sweep, before Worker.work().

    #CRITICAL: concurrency: this locks in the fix for issue #150, widened by
    ADR-021 to both the worker and API engines. The sweep's asyncio.run()
    loop dies before the worker loop starts; any connection left in either
    engine's pool at that point stays bound to the dead loop and crashes the
    first RQ job cross-loop. Both dispose() calls must run inside the
    sweep's own loop, before Worker.work() starts (and before any RQ work
    horse forks).

    Unlike the ordering test above, this one runs the REAL
    _run_worker_startup so the dispose calls inside it are exercised.
    """
    calls: list[str] = []

    @asynccontextmanager
    async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
        yield _FakeSession()

    async def _fake_requeue(session: object, **_kwargs: object) -> int:
        _ = session
        calls.append("sweep")
        return 1

    async def _fake_dispose_worker() -> None:
        calls.append("dispose_worker")

    async def _fake_dispose_api() -> None:
        calls.append("dispose_api")

    fake_worker_engine = MagicMock(spec=AsyncEngine)
    fake_worker_engine.dispose = AsyncMock(side_effect=_fake_dispose_worker)
    fake_engine = MagicMock(spec=AsyncEngine)
    fake_engine.dispose = AsyncMock(side_effect=_fake_dispose_api)

    fake_queue = MagicMock(spec=Queue)
    fake_queue.connection = "fake-connection"
    fake_worker_instance = MagicMock(spec=Worker)
    fake_worker_instance.work = MagicMock(
        side_effect=lambda: calls.append("worker_work")
    )

    def _fake_get_queue(settings: object) -> MagicMock:
        _ = settings
        return fake_queue

    def _fake_worker_cls(queues: object, *, connection: object) -> MagicMock:
        _ = queues, connection
        return fake_worker_instance

    monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
    monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
    monkeypatch.setattr(worker_main, "get_worker_engine", lambda: fake_worker_engine)
    monkeypatch.setattr(worker_main, "get_engine", lambda: fake_engine)
    monkeypatch.setattr(worker_main, "get_queue", _fake_get_queue)
    monkeypatch.setattr(worker_main, "Worker", _fake_worker_cls)

    worker_main.main()

    assert calls == ["sweep", "dispose_worker", "dispose_api", "worker_work"]
    fake_worker_engine.dispose.assert_awaited_once()
    fake_engine.dispose.assert_awaited_once()


class TestWorkerRolePosture:
    """The worker's own ADR-021 cutover signal (issue #559).

    A worker process serves no HTTP, so ``/health/ready``'s
    ``database_privilege`` check cannot see it, and
    ``CYO_ADVENTURE_WORKER_DATABASE_URL`` falls back to the API DSN in silence
    when unset. Before this probe existed, "the worker is on ``cyo_worker``"
    and "the worker still shares the API credential" were indistinguishable
    without catching a generation job mid-flight and reading
    ``pg_stat_activity``. These tests pin the standing signal that replaced
    that.
    """

    @staticmethod
    def _fake_posture(
        *, via_role_attribute: bool = False, via_table_ownership: bool = False
    ) -> RolePosture:
        return RolePosture(
            role_name="cyo_worker",
            via_role_attribute=via_role_attribute,
            via_table_ownership=via_table_ownership,
        )

    @pytest.mark.unit
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_probe_runs_against_the_worker_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The probe gets the WORKER engine's session, not the API engine's.

        #CRITICAL: security: probing the wrong engine answers a different
        question than the operator asked and reports a clean verdict about a
        connection the worker never makes.
        """
        seen: list[object] = []
        session_sentinel = _FakeSession()

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
            yield session_sentinel

        async def _fake_measure(session: object) -> RolePosture:
            seen.append(session)
            return self._fake_posture()

        async def _fake_requeue(session: object, **_kwargs: object) -> int:
            _ = session
            return 0

        monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
        monkeypatch.setattr(worker_main, "measure_role_posture", _fake_measure)
        monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
        _install_fake_engine(monkeypatch)

        await worker_main._run_worker_startup()

        assert seen == [session_sentinel]

    @pytest.mark.unit
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_bypassing_worker_role_logs_a_warning_with_both_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A worker role that defeats RLS warns, naming which path fired."""
        fake_logger = MagicMock()

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
            yield _FakeSession()

        async def _fake_measure(session: object) -> RolePosture:
            _ = session
            return self._fake_posture(via_table_ownership=True)

        async def _fake_requeue(session: object, **_kwargs: object) -> int:
            _ = session
            return 0

        monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
        monkeypatch.setattr(worker_main, "measure_role_posture", _fake_measure)
        monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
        monkeypatch.setattr(worker_main, "logger", fake_logger)
        _install_fake_engine(monkeypatch)

        await worker_main._run_worker_startup()

        fake_logger.warning.assert_called_once()
        event, kwargs = (
            fake_logger.warning.call_args.args[0],
            fake_logger.warning.call_args.kwargs,
        )
        assert event == "generation_worker.role_bypasses_rls"
        assert kwargs["role"] == "cyo_worker"
        assert kwargs["via_table_ownership"] is True
        assert kwargs["via_role_attribute"] is False

    @pytest.mark.unit
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_least_privileged_worker_role_logs_the_positive_signal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cut-over worker logs an affirmative line, not silence.

        Silence on success would make "cut over" and "probe never ran"
        identical in the log, which is the exact ambiguity this replaces.
        """
        fake_logger = MagicMock()

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
            yield _FakeSession()

        async def _fake_measure(session: object) -> RolePosture:
            _ = session
            return self._fake_posture()

        async def _fake_requeue(session: object, **_kwargs: object) -> int:
            _ = session
            return 0

        monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
        monkeypatch.setattr(worker_main, "measure_role_posture", _fake_measure)
        monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
        monkeypatch.setattr(worker_main, "logger", fake_logger)
        _install_fake_engine(monkeypatch)

        await worker_main._run_worker_startup()

        fake_logger.warning.assert_not_called()
        events = [call.args[0] for call in fake_logger.info.call_args_list]
        assert "generation_worker.role_least_privileged" in events

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_probe_failure_never_stops_the_worker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A broken probe degrades to a warning; the sweep and worker proceed.

        The posture probe is an observability signal, not a gate. A
        pre-cutover worker is an open security finding, but a worker that
        refuses to start is an outage, and refusing to process stories because
        a diagnostic query failed trades a smaller problem for a larger one.
        """
        fake_logger = MagicMock()
        swept: list[str] = []

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
            yield _FakeSession()

        async def _fake_measure(session: object) -> RolePosture:
            _ = session
            msg = "relation pg_roles does not exist"
            raise RuntimeError(msg)

        async def _fake_requeue(session: object, **_kwargs: object) -> int:
            _ = session
            swept.append("sweep")
            return 0

        monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
        monkeypatch.setattr(worker_main, "measure_role_posture", _fake_measure)
        monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
        monkeypatch.setattr(worker_main, "logger", fake_logger)
        _install_fake_engine(monkeypatch)

        assert await worker_main._run_worker_startup() == 0
        assert swept == ["sweep"]
        events = [call.args[0] for call in fake_logger.warning.call_args_list]
        assert "generation_worker.rls_posture_unknown" in events

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_posture_is_probed_before_the_reclaim_sweep(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ordering: a sweep that crashes still leaves the posture recorded."""
        order: list[str] = []

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
            yield _FakeSession()

        async def _fake_measure(session: object) -> RolePosture:
            _ = session
            order.append("posture")
            return self._fake_posture()

        async def _fake_requeue(session: object, **_kwargs: object) -> int:
            _ = session
            order.append("sweep")
            return 0

        monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
        monkeypatch.setattr(worker_main, "measure_role_posture", _fake_measure)
        monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
        _install_fake_engine(monkeypatch)

        await worker_main._run_worker_startup()

        assert order == ["posture", "sweep"]
