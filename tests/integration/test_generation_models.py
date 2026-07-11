"""Integration tests for the Concept and GenerationJob ORM models.

ORM round-trip: inserts a Family + User, then a Concept and a GenerationJob
referencing it, commits, reads both back, and asserts fields round-trip
correctly including the FK relationship from generation_job.concept_id.

The harness uses the ``engine`` and ``sessions`` fixtures from
``tests/integration/conftest.py``, which start a testcontainers Postgres 16
container and skip automatically when Docker is unavailable. Schema is built
via ``Base.metadata.create_all``; schema/migration parity itself is covered by
``test_schema_parity.py`` against ``supabase/migrations/*.sql``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Concept, Family, GenerationJob, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


# ---------------------------------------------------------------------------
# ORM round-trip tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concept_and_generation_job_roundtrip(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Insert a Concept + GenerationJob and read them back; assert field fidelity.

    The engine and sessions fixtures (from conftest.py) create the full schema
    via Base.metadata.create_all, which includes the new ``concept`` and
    ``generation_job`` tables.

    Args:
        sessions: Async session factory bound to the test engine.
    """
    brief_payload: dict[str, object] = {
        "topic": "dragons",
        "age_band": "6-9",
        "protagonist_name": "Pip",
        "reading_level": 2.5,
    }

    async with sessions() as session:
        # Insert a family and user as required FK parents.
        family = Family(name="Test Family for Generation")
        session.add(family)
        await session.flush()

        guardian = User(
            family_id=family.id,
            role="guardian",
            authn_subject="guardian-gen-test",
        )
        session.add(guardian)
        await session.flush()

        # Insert a Concept with a JSON brief and a creator FK.
        concept = Concept(
            family_id=family.id,
            brief=brief_payload,
            created_by=guardian.id,
        )
        session.add(concept)
        await session.flush()

        concept_id = concept.id
        family_id = family.id
        guardian_id = guardian.id

        # Insert a GenerationJob referencing the concept.
        job = GenerationJob(
            concept_id=concept.id,
            status="queued",
            model="claude-opus-4-8",
            provider="anthropic",
            prompt_version="1.0.0",
        )
        session.add(job)
        await session.flush()

        job_id = job.id
        await session.commit()

    # Read back in a fresh session to confirm persistence.
    async with sessions() as session:
        retrieved_concept = await session.get(Concept, concept_id)
        assert retrieved_concept is not None, "Concept row not found after commit"
        assert retrieved_concept.family_id == family_id
        assert retrieved_concept.brief == brief_payload
        assert retrieved_concept.created_by == guardian_id
        assert retrieved_concept.created_at is not None

        retrieved_job = await session.get(GenerationJob, job_id)
        assert retrieved_job is not None, "GenerationJob row not found after commit"
        assert retrieved_job.concept_id == concept_id, (
            "concept_id FK did not resolve correctly"
        )
        assert retrieved_job.status == "queued"
        assert retrieved_job.model == "claude-opus-4-8"
        assert retrieved_job.provider == "anthropic"
        assert retrieved_job.prompt_version == "1.0.0"
        assert retrieved_job.report is None
        assert retrieved_job.storybook_id is None
        assert retrieved_job.version is None
        assert retrieved_job.error is None
        assert retrieved_job.created_at is not None
        assert retrieved_job.updated_at is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generation_job_status_update(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Update a GenerationJob status and assert the updated fields persist.

    Args:
        sessions: Async session factory bound to the test engine.
    """
    async with sessions() as session:
        family = Family(name="Test Family Status")
        session.add(family)
        await session.flush()

        concept = Concept(
            family_id=family.id,
            brief={"topic": "robots"},
        )
        session.add(concept)
        await session.flush()

        job = GenerationJob(concept_id=concept.id, status="queued")
        session.add(job)
        await session.commit()
        job_id = job.id

    # Update status to passed and set storybook linkage + report.
    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        job.status = "passed"
        job.storybook_id = "story-abc-123"
        job.version = 1
        job.report = {"gate": "pass", "score": 0.95}
        await session.commit()

    # Verify the updates were persisted.
    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "passed"
        assert job.storybook_id == "story-abc-123"
        assert job.version == 1
        assert job.report == {"gate": "pass", "score": 0.95}
