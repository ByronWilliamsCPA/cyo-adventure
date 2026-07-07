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

from cyo_adventure.generation import worker_main

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class _FakeSession:
    """Marker object standing in for an AsyncSession; never touches a DB."""


def _install_fake_engine(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace worker_main.get_engine with one returning a dispose-mocked engine.

    Returns:
        The fake engine whose ``dispose`` is an ``AsyncMock``.
    """
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    monkeypatch.setattr(worker_main, "get_engine", lambda: fake_engine)
    return fake_engine


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reclaim_stranded_jobs_uses_a_fresh_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_reclaim_stranded_jobs opens a session and returns requeue_stranded_jobs' count."""

    @asynccontextmanager
    async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
        yield _FakeSession()

    async def _fake_requeue(session: object, **_kwargs: object) -> int:
        assert isinstance(session, _FakeSession)
        return 3

    monkeypatch.setattr(worker_main, "get_session", _fake_get_session)
    monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
    fake_engine = _install_fake_engine(monkeypatch)

    count = await worker_main._reclaim_stranded_jobs()

    assert count == 3
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reclaim_stranded_jobs_disposes_engine_even_on_sweep_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The engine pool is disposed inside the sweep's loop even if the sweep raises."""

    @asynccontextmanager
    async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
        yield _FakeSession()

    async def _fake_requeue(session: object, **_kwargs: object) -> int:
        _ = session
        msg = "sweep exploded"
        raise RuntimeError(msg)

    monkeypatch.setattr(worker_main, "get_session", _fake_get_session)
    monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
    fake_engine = _install_fake_engine(monkeypatch)

    with pytest.raises(RuntimeError, match="sweep exploded"):
        await worker_main._reclaim_stranded_jobs()

    fake_engine.dispose.assert_awaited_once()


@pytest.mark.unit
def test_main_sweeps_before_starting_the_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() runs the reclaim sweep, then constructs and starts the RQ worker.

    #CRITICAL: timing: a job stranded by a prior crash must be requeued
    before this same process would otherwise sit idle waiting for new work;
    this test locks in that ordering.
    """
    calls: list[str] = []

    async def _fake_sweep() -> int:
        calls.append("sweep")
        return 2

    fake_queue = MagicMock()
    fake_queue.connection = "fake-connection"
    fake_worker_instance = MagicMock()

    def _fake_get_queue(settings: object) -> MagicMock:
        _ = settings
        return fake_queue

    def _fake_worker_cls(queues: object, *, connection: object) -> MagicMock:
        calls.append("worker_constructed")
        assert queues == [fake_queue]
        assert connection == "fake-connection"
        return fake_worker_instance

    monkeypatch.setattr(worker_main, "_reclaim_stranded_jobs", _fake_sweep)
    monkeypatch.setattr(worker_main, "get_queue", _fake_get_queue)
    monkeypatch.setattr(worker_main, "Worker", _fake_worker_cls)

    worker_main.main()

    assert calls == ["sweep", "worker_constructed"]
    fake_worker_instance.work.assert_called_once()


@pytest.mark.unit
def test_main_disposes_engine_after_sweep_and_before_worker_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() awaits engine.dispose() after the sweep, before Worker.work().

    #CRITICAL: concurrency: this locks in the fix for issue #150. The sweep's
    asyncio.run() loop dies before the worker loop starts; any connection left
    in the engine pool at that point stays bound to the dead loop and crashes
    the first RQ job cross-loop. dispose() must run inside the sweep's own
    loop, before Worker.work() starts (and before any RQ work horse forks).

    Unlike the ordering test above, this one runs the REAL
    _reclaim_stranded_jobs so the dispose call inside it is exercised.
    """
    calls: list[str] = []

    @asynccontextmanager
    async def _fake_get_session() -> AsyncGenerator[_FakeSession]:
        yield _FakeSession()

    async def _fake_requeue(session: object, **_kwargs: object) -> int:
        _ = session
        calls.append("sweep")
        return 1

    async def _fake_dispose() -> None:
        calls.append("dispose")

    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock(side_effect=_fake_dispose)

    fake_queue = MagicMock()
    fake_queue.connection = "fake-connection"
    fake_worker_instance = MagicMock()
    fake_worker_instance.work = MagicMock(
        side_effect=lambda: calls.append("worker_work")
    )

    def _fake_get_queue(settings: object) -> MagicMock:
        _ = settings
        return fake_queue

    def _fake_worker_cls(queues: object, *, connection: object) -> MagicMock:
        _ = queues, connection
        return fake_worker_instance

    monkeypatch.setattr(worker_main, "get_session", _fake_get_session)
    monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)
    monkeypatch.setattr(worker_main, "get_engine", lambda: fake_engine)
    monkeypatch.setattr(worker_main, "get_queue", _fake_get_queue)
    monkeypatch.setattr(worker_main, "Worker", _fake_worker_cls)

    worker_main.main()

    assert calls == ["sweep", "dispose", "worker_work"]
    fake_engine.dispose.assert_awaited_once()
