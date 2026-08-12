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

from decimal import Decimal
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cost_usd_round_trips_as_decimal(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A persisted cost comes back as an exact Decimal, not a float.

    The NUMERIC(12,6) column choice only buys anything if the driver's type
    mapping preserves it end to end. A float round-trip would not fail here in
    any obvious way; it would return a value that compares unequal to the
    Decimal that was written, and the drift it introduces only becomes visible
    once thousands of these are summed, by which point no reader can attribute
    it. So the assertion is on both the type and the exact value.

    Args:
        sessions: Async session factory bound to the test engine.
    """
    amount = Decimal("0.004237")

    async with sessions() as session:
        family = Family(name="Test Family for Cost Accounting")
        session.add(family)
        await session.flush()

        concept = Concept(family_id=family.id, brief={"age_band": "6-9"})
        session.add(concept)
        await session.flush()

        job = GenerationJob(
            concept_id=concept.id,
            status="passed",
            provider_call_count=7,
            provider_unknown_calls=0,
            input_tokens=1234,
            output_tokens=5678,
            provider_duration_ms=9012,
            cost_usd=amount,
            cost_complete=False,
        )
        session.add(job)
        await session.flush()
        job_id = job.id
        await session.commit()

    async with sessions() as session:
        retrieved = await session.get(GenerationJob, job_id)
        assert retrieved is not None, "GenerationJob row not found after commit"
        assert isinstance(retrieved.cost_usd, Decimal), (
            "cost_usd came back as a non-Decimal; the NUMERIC column is not "
            "being mapped as an exact type"
        )
        assert retrieved.cost_usd == amount
        assert retrieved.provider_call_count == 7
        assert retrieved.provider_unknown_calls == 0
        assert retrieved.input_tokens == 1234
        assert retrieved.output_tokens == 5678
        assert retrieved.provider_duration_ms == 9012
        # False is a recorded answer; it must survive as False, not as None.
        assert retrieved.cost_complete is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_provider_accounting_defaults_to_null_not_zero(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A job with no accounting reads back NULL, keeping "unrecorded" reachable.

    NULL and 0 mean different things in these columns: NULL is "nothing was
    recorded" (a row predating the instrumentation, or a run whose provider was
    never metered) and 0 is "measured, and it was zero". A column defaulting to
    0 would erase that difference permanently and make every unrecorded job
    look like a free one.

    Args:
        sessions: Async session factory bound to the test engine.
    """
    async with sessions() as session:
        family = Family(name="Test Family for Unrecorded Accounting")
        session.add(family)
        await session.flush()

        concept = Concept(family_id=family.id, brief={"age_band": "6-9"})
        session.add(concept)
        await session.flush()

        job = GenerationJob(concept_id=concept.id, status="queued")
        session.add(job)
        await session.flush()
        job_id = job.id
        await session.commit()

    async with sessions() as session:
        retrieved = await session.get(GenerationJob, job_id)
        assert retrieved is not None, "GenerationJob row not found after commit"
        assert retrieved.provider_call_count is None
        assert retrieved.provider_unknown_calls is None
        assert retrieved.input_tokens is None
        assert retrieved.output_tokens is None
        assert retrieved.provider_duration_ms is None
        assert retrieved.cost_usd is None
        assert retrieved.cost_complete is None
