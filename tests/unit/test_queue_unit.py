"""Unit tests for the RQ queue wrapper (no live Redis).

Patches the Redis client and RQ Queue so ``get_queue`` and ``enqueue_generation``
are exercised without a running Redis, covering the queue module in the
Docker-less CI legs.
"""

from __future__ import annotations

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.generation import queue as queue_mod


class _FakeJob:
    """Stand-in for an RQ job with an id."""

    id = "rq-job-1"


class _FakeQueue:
    """Stand-in for ``rq.Queue`` capturing the enqueue call."""

    def __init__(self, name: str, *, connection: object) -> None:
        self.name = name
        self.connection = connection
        self.enqueued: list[tuple[str, str]] = []

    def enqueue(self, entrypoint: str, job_id: str) -> _FakeJob:
        """Record the enqueue and return a fake job."""
        self.enqueued.append((entrypoint, job_id))
        return _FakeJob()


class _FakeRedis:
    """Stand-in for ``redis.Redis`` with a from_url classmethod."""

    @staticmethod
    def from_url(url: str, **kwargs: object) -> object:
        """Return a sentinel connection, ignoring the url and timeouts."""
        _ = (url, kwargs)
        return object()


@pytest.mark.unit
def test_get_queue_builds_named_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_queue builds a 'generation' queue bound to a Redis connection."""
    monkeypatch.setattr(queue_mod.redis, "Redis", _FakeRedis)
    monkeypatch.setattr(queue_mod, "Queue", _FakeQueue)

    result = queue_mod.get_queue(Settings())

    assert isinstance(result, _FakeQueue)
    assert result.name == "generation"
    assert result.connection is not None


@pytest.mark.unit
def test_enqueue_generation_returns_rq_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """enqueue_generation pushes the worker entrypoint and returns the RQ id."""
    captured: dict[str, _FakeQueue] = {}

    def _factory(name: str, *, connection: object) -> _FakeQueue:
        q = _FakeQueue(name, connection=connection)
        captured["queue"] = q
        return q

    monkeypatch.setattr(queue_mod.redis, "Redis", _FakeRedis)
    monkeypatch.setattr(queue_mod, "Queue", _factory)

    rq_id = queue_mod.enqueue_generation("job-123", Settings())

    assert rq_id == "rq-job-1"
    assert captured["queue"].enqueued == [(queue_mod._WORKER_ENTRYPOINT, "job-123")]
