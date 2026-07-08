"""Integration tests for the Concept and GenerationJob ORM models.

Two tests are included:

1. ORM round-trip: inserts a Family + User, then a Concept and a GenerationJob
   referencing it, commits, reads both back, and asserts fields round-trip
   correctly including the FK relationship from generation_job.concept_id.

2. Migration round-trip: runs ``alembic upgrade head`` then
   ``alembic downgrade -1`` against a clean testcontainers Postgres DB in a
   subprocess, asserts exit codes are 0, and verifies the migration file itself
   imports cleanly with ``upgrade`` and ``downgrade`` callable attributes.

The harness uses the ``engine`` and ``sessions`` fixtures from
``tests/integration/conftest.py``, which start a testcontainers Postgres 16
container and skip automatically when Docker is unavailable.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Concept, Family, GenerationJob, User
from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Pin the round-trip to the concept/generation_job revision explicitly. A
# relative "head"/"-1" target silently retargets whenever a later migration is
# added on top, so the round-trip would stop exercising this migration.
_GEN_HEAD = "78336bfff81e"
_GEN_PREV = "ddf3f6d1346f"


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


# ---------------------------------------------------------------------------
# Migration round-trip tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_migration_file_imports_and_has_upgrade_downgrade() -> None:
    """Assert the migration file is importable with upgrade/downgrade defined.

    This is a lightweight structural check that does not require a live DB.
    It verifies the file at least parses and exports the expected callables,
    which would catch syntax errors or accidental stub functions.  It also
    confirms the down_revision chain points to the initial schema revision.
    """
    migration_dir = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    migration_files = list(migration_dir.glob("*add_concept_and_generation_job*.py"))
    assert migration_files, (
        f"Could not find the concept/generation_job migration file in {migration_dir}"
    )

    migration_path = migration_files[0]
    spec = importlib.util.spec_from_file_location(
        "_migration_under_test", migration_path
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    assert callable(getattr(mod, "upgrade", None)), (
        "Migration file has no callable 'upgrade'"
    )
    assert callable(getattr(mod, "downgrade", None)), (
        "Migration file has no callable 'downgrade'"
    )
    assert mod.down_revision == "ddf3f6d1346f", (
        f"Expected down_revision 'ddf3f6d1346f', got {mod.down_revision!r}"
    )


@pytest.mark.integration
def test_migration_upgrade_downgrade_on_clean_db(
    migration_pg_url: str,
) -> None:
    """Run alembic upgrade head then downgrade -1 against a clean Postgres DB.

    This verifies that both ``upgrade()`` and ``downgrade()`` execute without
    error on a live Postgres instance, confirming the SQL is syntactically and
    semantically correct.

    The test uses a subprocess invocation of ``uv run alembic`` with the
    ``CYO_ADVENTURE_DATABASE_URL`` env var set to the testcontainers URL.
    This matches the env.py pattern, which reads from settings.database_url.

    Args:
        migration_pg_url: Async DSN for the testcontainers Postgres DB.
    """
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    # Apply migrations through the concept/generation_job revision.
    up = run_alembic(project_root, env, "upgrade", _GEN_HEAD)
    assert up.returncode == 0, (
        f"alembic upgrade {_GEN_HEAD} failed:\nstdout={up.stdout}\nstderr={up.stderr}"
    )
    assert "Running upgrade" in up.stderr, (
        "Expected 'Running upgrade' in alembic stderr"
    )

    # Roll back the concept/generation_job migration to the initial schema.
    down = run_alembic(project_root, env, "downgrade", _GEN_PREV)
    assert down.returncode == 0, (
        f"alembic downgrade {_GEN_PREV} failed:\nstdout={down.stdout}\nstderr={down.stderr}"
    )
    assert "Running downgrade" in down.stderr, (
        "Expected 'Running downgrade' in alembic stderr"
    )
