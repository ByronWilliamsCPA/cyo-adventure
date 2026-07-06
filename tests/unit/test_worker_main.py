"""Unit tests for the RQ worker process entry point (no Redis, no DB).

Both dependencies of :func:`~cyo_adventure.generation.worker_main.main` (the
reclaim sweep and the RQ ``Worker``) are mocked so this exercises only the
ordering contract: the stranded-job reclaim sweep must complete before the
worker starts its blocking work loop.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from cyo_adventure.generation import worker_main

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class _FakeSession:
    """Marker object standing in for an AsyncSession; never touches a DB."""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reclaim_stranded_jobs_uses_a_fresh_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_reclaim_stranded_jobs opens a session and returns requeue_stranded_jobs' count."""

    @asynccontextmanager
    async def _fake_get_session() -> AsyncIterator[_FakeSession]:
        yield _FakeSession()

    async def _fake_requeue(session: object, **_kwargs: object) -> int:
        assert isinstance(session, _FakeSession)
        return 3

    monkeypatch.setattr(worker_main, "get_session", _fake_get_session)
    monkeypatch.setattr(worker_main, "requeue_stranded_jobs", _fake_requeue)

    count = await worker_main._reclaim_stranded_jobs()

    assert count == 3


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
