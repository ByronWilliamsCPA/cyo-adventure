"""Integration tests for the stranded-job reclaim sweep (real Postgres, no Redis).

``requeue_stranded_jobs`` filters on ``GenerationJob.updated_at`` at the SQL
level, so exercising the actual staleness cutoff needs a real database rather
than a fake session (Docker-less legs skip cleanly via the shared
``_pg_url`` fixture in conftest.py). The enqueue side is mocked at the
``enqueue_generation`` boundary so no live Redis is required (Finding 4 D2
Step 3: the reclaim sweeper).

The tests below the mocked-enqueue block instead run against a REAL
``rq.Queue`` backed by a Redis testcontainer (Finding 1, D2 review): the
mocked tests above only assert that ``enqueue_generation`` was *called* with
``rq_job_id`` equal to the row id; they never exercise what RQ itself does
with that id, which is exactly where the idempotency bug lived (``job_id=``
alone does not make RQ's enqueue idempotent; only ``unique=True`` does).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from docker.errors import DockerException
from rq.exceptions import DuplicateJobError
from testcontainers.redis import RedisContainer

from cyo_adventure.core.config import Settings
from cyo_adventure.db.models import Concept, Family, GenerationJob
from cyo_adventure.generation import queue as queue_mod

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def _seed_queued_job(
    sessions: async_sessionmaker[AsyncSession],
    *,
    updated_at: datetime | None,
) -> uuid.UUID:
    """Insert a Family/Concept/GenerationJob row, optionally backdating updated_at.

    Args:
        sessions: Session factory bound to the test's Postgres container.
        updated_at: Explicit ``updated_at`` to stamp on insert (bypasses the
            ``server_default=func.now()``), or ``None`` to use the default
            (a "just created" row).

    Returns:
        The new GenerationJob's id.
    """
    async with sessions() as session:
        fam = Family(name="Reclaim Test Family")
        session.add(fam)
        await session.flush()

        concept = Concept(family_id=fam.id, brief={"premise": "a reclaim test"})
        session.add(concept)
        await session.flush()

        job = GenerationJob(concept_id=concept.id, status="queued")
        if updated_at is not None:
            job.updated_at = updated_at
        session.add(job)
        await session.commit()
        return job.id


@pytest.mark.asyncio
async def test_requeue_stranded_jobs_requeues_stale_row(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 'queued' row stale beyond stale_after is re-enqueued exactly once.

    The re-enqueue passes rq_job_id equal to the row's own id (idempotency:
    a job merely deep in the queue must not spawn a second RQ execution).
    """
    stale_id = await _seed_queued_job(
        sessions, updated_at=datetime.now(UTC) - timedelta(hours=2)
    )

    calls: list[tuple[str, str | None]] = []

    def _fake_enqueue(
        job_id: str, settings: Settings, *, rq_job_id: str | None = None
    ) -> str:
        _ = settings
        calls.append((job_id, rq_job_id))
        return "rq-fake-id"

    monkeypatch.setattr(queue_mod, "enqueue_generation", _fake_enqueue)

    async with sessions() as session:
        count = await queue_mod.requeue_stranded_jobs(
            session, stale_after=timedelta(minutes=30)
        )

    assert count == 1
    assert calls == [(str(stale_id), str(stale_id))]


@pytest.mark.asyncio
async def test_requeue_stranded_jobs_skips_fresh_row(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 'queued' row updated moments ago is left alone (legitimately queued)."""
    await _seed_queued_job(sessions, updated_at=None)

    calls: list[tuple[str, str | None]] = []

    def _fake_enqueue(
        job_id: str, settings: Settings, *, rq_job_id: str | None = None
    ) -> str:
        _ = settings
        calls.append((job_id, rq_job_id))
        return "rq-fake-id"

    monkeypatch.setattr(queue_mod, "enqueue_generation", _fake_enqueue)

    async with sessions() as session:
        count = await queue_mod.requeue_stranded_jobs(
            session, stale_after=timedelta(minutes=30)
        )

    assert count == 0
    assert calls == []


async def _seed_running_job(
    sessions: async_sessionmaker[AsyncSession],
    *,
    updated_at: datetime,
) -> uuid.UUID:
    """Insert a Family/Concept/GenerationJob row at status 'running'."""
    async with sessions() as session:
        fam = Family(name="Reclaim Test Family Running")
        session.add(fam)
        await session.flush()
        concept = Concept(family_id=fam.id, brief={"premise": "a running test"})
        session.add(concept)
        await session.flush()
        job = GenerationJob(concept_id=concept.id, status="running")
        job.updated_at = updated_at
        session.add(job)
        await session.commit()
        return job.id


@pytest.mark.asyncio
async def test_requeue_force_fails_stale_running_row(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 'running' row orphaned by a hard worker death is force-failed.

    A SIGKILL/OOM leaves the row 'running' forever (the pipeline's finally
    guard never runs on a hard kill), permanently consuming a family cap slot.
    The sweep force-fails it with error 'interrupted: worker died' and does NOT
    re-enqueue it (the job may have spent provider budget).
    """
    running_id = await _seed_running_job(
        sessions, updated_at=datetime.now(UTC) - timedelta(hours=4)
    )

    calls: list[tuple[str, str | None]] = []

    def _fake_enqueue(
        job_id: str, settings: Settings, *, rq_job_id: str | None = None
    ) -> str:
        _ = settings
        calls.append((job_id, rq_job_id))
        return "rq-fake-id"

    monkeypatch.setattr(queue_mod, "enqueue_generation", _fake_enqueue)

    async with sessions() as session:
        count = await queue_mod.requeue_stranded_jobs(
            session,
            stale_after=timedelta(minutes=30),
            running_stale_after=timedelta(hours=1),
        )

    # Reclaimed via force-fail, never re-enqueued.
    assert count == 1
    assert calls == []

    async with sessions() as session:
        row = await session.get(GenerationJob, running_id)
        assert row is not None
        assert row.status == "failed"
        assert row.error == "interrupted: worker died"


@pytest.mark.asyncio
async def test_requeue_leaves_recently_running_row_alone(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 'running' row younger than running_stale_after is still executing.

    It must not be reaped early: a legitimate long generation run sits
    'running' for the whole job timeout.
    """
    running_id = await _seed_running_job(
        sessions, updated_at=datetime.now(UTC) - timedelta(minutes=10)
    )

    monkeypatch.setattr(
        queue_mod,
        "enqueue_generation",
        lambda *_a, **_k: "rq-fake-id",
    )

    async with sessions() as session:
        count = await queue_mod.requeue_stranded_jobs(
            session,
            stale_after=timedelta(minutes=30),
            running_stale_after=timedelta(hours=1),
        )

    assert count == 0
    async with sessions() as session:
        row = await session.get(GenerationJob, running_id)
        assert row is not None
        assert row.status == "running"


# ---------------------------------------------------------------------------
# Real-RQ idempotency tests (Finding 1, D2 review): a live Redis testcontainer,
# no mocking of enqueue_generation or queue.enqueue(). The mocked tests above
# only prove enqueue_generation was CALLED with rq_job_id=row_id; they cannot
# catch a bug in what RQ itself does with that id, which is exactly where the
# original finding lived.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """Start a Redis container for the session.

    Skips cleanly when no Docker daemon is reachable, mirroring the
    ``_pg_url`` Postgres fixture in conftest.py so a developer without Docker
    is not blocked; CI runners provide Docker for testcontainers.
    """
    try:
        container = RedisContainer("redis:7-alpine")
        container.start()
    except (DockerException, OSError) as exc:
        pytest.skip(f"Docker/Redis testcontainer unavailable: {exc}")
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"redis://{host}:{port}/0"
    finally:
        container.stop()


def test_enqueue_generation_second_call_same_id_raises_duplicate(
    redis_url: str,
) -> None:
    """A second enqueue_generation call with the same rq_job_id raises
    DuplicateJobError instead of silently growing the queue's job_ids list to
    a second entry for the same id.

    This is the direct proof for Finding 1: passing ``job_id=<row id>`` to
    ``queue.enqueue()`` alone does NOT make the enqueue idempotent. Before the
    fix (no ``unique=`` kwarg passed at all), the exact same two calls below
    left ``queue.job_ids`` holding the row's id TWICE, meaning
    ``run_generation_job_sync`` would have been invoked twice concurrently
    for one job.
    """
    settings = Settings(redis_url=redis_url)  # type: ignore[call-arg]
    row_id = str(uuid.uuid4())

    first_rq_id = queue_mod.enqueue_generation(row_id, settings, rq_job_id=row_id)
    assert first_rq_id == row_id

    with pytest.raises(DuplicateJobError):
        queue_mod.enqueue_generation(row_id, settings, rq_job_id=row_id)

    queue = queue_mod.get_queue(settings)
    assert queue.job_ids.count(row_id) == 1


def test_enqueue_generation_without_rq_job_id_never_collides(
    redis_url: str,
) -> None:
    """The normal per-request enqueue path (rq_job_id=None) is unaffected:
    RQ mints a fresh id each call, so unique=False here is correct, not a
    regression of the fix.
    """
    settings = Settings(redis_url=redis_url)  # type: ignore[call-arg]

    first_rq_id = queue_mod.enqueue_generation(str(uuid.uuid4()), settings)
    second_rq_id = queue_mod.enqueue_generation(str(uuid.uuid4()), settings)

    assert first_rq_id != second_rq_id


@pytest.mark.asyncio
async def test_requeue_stranded_jobs_second_sweep_same_row_is_queue_idempotent(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    redis_url: str,
) -> None:
    """Two sweeps of the same still-stale row do not create a second RQ entry,
    and the second sweep's DuplicateJobError is swallowed as a no-op, not
    raised out of requeue_stranded_jobs.

    ``requeue_stranded_jobs`` performs no writes (see its docstring), so the
    row's ``updated_at`` is still stale after the first sweep; a second call
    picks the SAME row again, which is exactly the "merely deep in the queue"
    scenario the reclaim sweep must not double-enqueue.
    """
    # requeue_stranded_jobs enqueues through the module-level _default_settings
    # (not a parameter), so point that instance at the Redis testcontainer for
    # the duration of this test.
    monkeypatch.setattr(queue_mod._default_settings, "redis_url", redis_url)

    stale_id = await _seed_queued_job(
        sessions, updated_at=datetime.now(UTC) - timedelta(hours=2)
    )

    async with sessions() as session:
        first_count = await queue_mod.requeue_stranded_jobs(
            session, stale_after=timedelta(minutes=30)
        )
    async with sessions() as session:
        second_count = await queue_mod.requeue_stranded_jobs(
            session, stale_after=timedelta(minutes=30)
        )

    # Both sweeps genuinely found the (still-stale) row a valid candidate; the
    # second sweep's RQ-level DuplicateJobError is caught internally, not
    # surfaced as a sweep failure.
    assert first_count == 1
    assert second_count == 1

    queue = queue_mod.get_queue(queue_mod._default_settings)
    assert queue.job_ids.count(str(stale_id)) == 1
