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
    """Stand-in for ``rq.Queue`` capturing the enqueue call.

    Mirrors ``rq.Queue.enqueue``'s real ``(f, *args, **kwargs)`` shape so
    callers can pass ``job_timeout``/``job_id`` as keywords the same way the
    real RQ client does, with no risk of a positional/keyword name collision.
    """

    def __init__(self, name: str, *, connection: object) -> None:
        self.name = name
        self.connection = connection
        self.enqueued: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def enqueue(self, entrypoint: str, *args: object, **kwargs: object) -> _FakeJob:
        """Record the enqueue and return a fake job."""
        self.enqueued.append((entrypoint, args, kwargs))
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
    assert captured["queue"].enqueued == [
        (
            queue_mod._WORKER_ENTRYPOINT,
            ("job-123",),
            {"job_timeout": 1800, "job_id": None, "unique": False},
        )
    ]


@pytest.mark.unit
def test_enqueue_generation_passes_job_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """enqueue_generation always sets job_timeout from settings (D2 Finding 4).

    RQ's own default job_timeout is 180s, far shorter than a live Ollama run;
    an unset value would let RQ SIGALRM-kill a still-healthy job.
    """
    captured: dict[str, _FakeQueue] = {}

    def _factory(name: str, *, connection: object) -> _FakeQueue:
        q = _FakeQueue(name, connection=connection)
        captured["queue"] = q
        return q

    monkeypatch.setattr(queue_mod.redis, "Redis", _FakeRedis)
    monkeypatch.setattr(queue_mod, "Queue", _factory)

    settings = Settings(generation_job_timeout_seconds=900)  # type: ignore[call-arg]
    queue_mod.enqueue_generation("job-123", settings)

    _entrypoint, _args, kwargs = captured["queue"].enqueued[0]
    assert kwargs["job_timeout"] == 900


@pytest.mark.unit
def test_enqueue_generation_passes_rq_job_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """The optional rq_job_id kwarg reaches queue.enqueue() as RQ's job_id.

    The stranded-job reclaim sweep passes this so a re-enqueue of a row that
    is merely deep in the queue (not actually lost) reuses the same RQ job
    identity instead of creating a second, redundant execution.
    """
    captured: dict[str, _FakeQueue] = {}

    def _factory(name: str, *, connection: object) -> _FakeQueue:
        q = _FakeQueue(name, connection=connection)
        captured["queue"] = q
        return q

    monkeypatch.setattr(queue_mod.redis, "Redis", _FakeRedis)
    monkeypatch.setattr(queue_mod, "Queue", _factory)

    queue_mod.enqueue_generation("job-123", Settings(), rq_job_id="job-123")

    _entrypoint, _args, kwargs = captured["queue"].enqueued[0]
    assert kwargs["job_id"] == "job-123"


@pytest.mark.unit
def test_enqueue_generation_sets_unique_only_when_rq_job_id_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unique=True reaches queue.enqueue() only when rq_job_id is given (Finding 1).

    Passing job_id= alone does not make RQ's enqueue idempotent: RQ only
    atomically check-and-skips a duplicate id when unique=True is ALSO
    passed, else it silently rpushes a second queue entry for the same id.
    This is a fast unit check on the kwarg reaching queue.enqueue(); the
    real dedup behavior against a live RQ/Redis is exercised by
    test_enqueue_generation_second_call_same_id_raises_duplicate in
    tests/integration/test_queue_reclaim.py.
    """
    captured: dict[str, _FakeQueue] = {}

    def _factory(name: str, *, connection: object) -> _FakeQueue:
        q = _FakeQueue(name, connection=connection)
        captured["queue"] = q
        return q

    monkeypatch.setattr(queue_mod.redis, "Redis", _FakeRedis)
    monkeypatch.setattr(queue_mod, "Queue", _factory)

    queue_mod.enqueue_generation("job-123", Settings(), rq_job_id="job-123")
    _entrypoint, _args, kwargs = captured["queue"].enqueued[0]
    assert kwargs["unique"] is True

    # get_queue() builds a fresh Queue per call, so the second enqueue_generation
    # call replaces captured["queue"] with a new _FakeQueue instance.
    queue_mod.enqueue_generation("job-456", Settings())
    _entrypoint, _args, kwargs = captured["queue"].enqueued[0]
    assert kwargs["unique"] is False
