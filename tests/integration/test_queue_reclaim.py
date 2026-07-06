"""Integration tests for the stranded-job reclaim sweep (real Postgres, no Redis).

``requeue_stranded_jobs`` filters on ``GenerationJob.updated_at`` at the SQL
level, so exercising the actual staleness cutoff needs a real database rather
than a fake session (Docker-less legs skip cleanly via the shared
``_pg_url`` fixture in conftest.py). The enqueue side is mocked at the
``enqueue_generation`` boundary so no live Redis is required (Finding 4 D2
Step 3: the reclaim sweeper).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Concept, Family, GenerationJob
from cyo_adventure.generation import queue as queue_mod

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from cyo_adventure.core.config import Settings


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


@pytest.mark.asyncio
async def test_requeue_stranded_jobs_ignores_non_queued_status(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale row that is already 'running' (still legitimately executing) is untouched.

    Only 'queued' rows are ever candidates: a 'running' row stale beyond
    stale_after is the top-level finally guard's job (run_generation_job),
    not the reclaim sweep's.
    """
    async with sessions() as session:
        fam = Family(name="Reclaim Test Family Running")
        session.add(fam)
        await session.flush()
        concept = Concept(family_id=fam.id, brief={"premise": "a running test"})
        session.add(concept)
        await session.flush()
        job = GenerationJob(concept_id=concept.id, status="running")
        job.updated_at = datetime.now(UTC) - timedelta(hours=2)
        session.add(job)
        await session.commit()

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
