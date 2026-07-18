"""Tests for the ADR-007 raw-output retention purge (M5 register item S10).

Two purge paths are covered:

- The on-publish path: ``publishing.service.approve`` nulls the originating
  ``GenerationJob.report`` in the same transaction as the publish write.
  Exercised the same Docker-independent way as
  ``tests/unit/test_publishing_service_unit.py``: a mocked ``AsyncSession``,
  no real database.
- The 30-day scheduled path: a pg_cron job registered by
  ``supabase/migrations/20260718000000_add_report_retention_purge.sql``.
  pg_cron cannot run inside a unit test, so this module asserts on the
  migration file's text content instead (job name, 30-day interval, target
  table/column, and idempotent unschedule-then-schedule shape).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.api.deps import Principal
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.publishing import service
from tests.conftest import make_clean_moderation_report

pytestmark = pytest.mark.unit

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260718000000_add_report_retention_purge.sql"
)


def _principal(role: str) -> Principal:
    """Build a minimal Principal with the given role."""
    return Principal(
        subject=f"{role}-x",
        user_id=uuid.uuid4(),
        role=role,
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _story(status: str, *, current: int | None = None) -> Storybook:
    """Construct a Storybook ORM instance without a session."""
    return Storybook(
        id="s1",
        family_id=uuid.uuid4(),
        status=status,
        current_published_version=current,
    )


@pytest.mark.asyncio
async def test_approve_nulls_generation_job_report() -> None:
    """approve() issues an UPDATE that nulls report for the published job.

    The UPDATE must target generation_job rows matching this storybook's id
    and the specific version being published (not every job ever run for the
    storybook), and only rows where report is currently non-null.
    """
    story = _story("in_review")
    version_row = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob={},
        moderation_report=make_clean_moderation_report(),
    )
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=version_row)
    principal = _principal("admin")

    await service.approve(session, principal, story, 1)

    # Find the report-nulling UPDATE among the calls made to session.execute
    # (record_event's internal flush does not go through session.execute, so
    # this should be the sole call, but search by shape rather than assuming
    # position for robustness against future additions).
    update_calls = [
        call
        for call in session.execute.await_args_list
        if isinstance(call.args[0], Update)
    ]
    assert len(update_calls) == 1, (
        "expected exactly one UPDATE statement against session.execute"
    )
    stmt = update_calls[0].args[0]
    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "generation_job" in compiled
    assert "SET report=NULL" in compiled or "SET report = NULL" in compiled.replace(
        "  ", " "
    )
    assert "storybook_id = 's1'" in compiled or "storybook_id='s1'" in compiled
    assert "version = 1" in compiled or "version=1" in compiled
    assert "report IS NOT NULL" in compiled


@pytest.mark.asyncio
async def test_approve_report_purge_runs_before_publish_flushes() -> None:
    """The purge UPDATE and the publish status write share one transaction.

    approve() never calls session.commit() (the request unit-of-work owns
    that per api/deps.py), so asserting commit was never awaited is a proxy
    for "the purge and the publish are still uncommitted together" -- a
    caller-level rollback would undo both.
    """
    story = _story("in_review")
    version_row = StorybookVersion(
        storybook_id="s1",
        version=2,
        blob={},
        moderation_report=make_clean_moderation_report(),
    )
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=version_row)

    await service.approve(session, _principal("admin"), story, 2)

    session.commit.assert_not_awaited()
    session.execute.assert_awaited()


def test_migration_file_exists() -> None:
    """The Phase 5 migration file is present under supabase/migrations/."""
    assert _MIGRATION_PATH.is_file(), (
        f"expected migration at {_MIGRATION_PATH}, matching the file name "
        "referenced by ADR-007 and the roadmap"
    )


def test_migration_schedules_purge_job_by_name() -> None:
    """The migration registers a pg_cron job named purge_generation_job_report."""
    sql = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert "purge_generation_job_report" in sql
    assert "cron.schedule(" in sql


def test_migration_unschedules_before_scheduling() -> None:
    """Idempotent by job name: unschedule-then-schedule, not schedule-only.

    Without this, re-running the migration (or a future migration touching
    the same job) would register duplicate cron.job rows under pg_cron.
    """
    sql = _MIGRATION_PATH.read_text(encoding="utf-8")
    unschedule_idx = sql.index("cron.unschedule(")
    schedule_idx = sql.index("cron.schedule(")
    assert unschedule_idx < schedule_idx, (
        "expected cron.unschedule(...) to appear before cron.schedule(...) "
        "so re-applying the migration replaces rather than duplicates the job"
    )


def test_migration_uses_thirty_day_interval() -> None:
    """The purge predicate uses a 30-day interval, per ADR-007's decision."""
    sql = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert "interval '30 days'" in sql


def test_migration_targets_generation_job_report_column() -> None:
    """The scheduled UPDATE nulls generation_job.report, not some other column."""
    sql = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert '"public"."generation_job"' in sql
    assert 'SET "report" = NULL' in sql


def test_migration_restricts_to_terminal_statuses() -> None:
    """Only completed/terminal jobs are purged; queued/running jobs are not.

    'awaiting_manual_fill' is also excluded -- it is a paused, pending-human
    state (generation/import_story.py::resume_manual_fill clears it), not a
    completed one, so a report parked there is still awaiting use.
    """
    sql = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert "'passed', 'needs_review', 'failed'" in sql
    # Scope the negative assertions to the scheduled SQL body (the $job$...$job$
    # dollar-quoted block), not the whole file: the header comment legitimately
    # names 'queued' and 'awaiting_manual_fill' in prose to explain why they are
    # excluded, which would otherwise make this a false-positive failure.
    job_body = sql.split("$job$")[1]
    assert "'queued'" not in job_body
    assert "'running'" not in job_body
    assert "'awaiting_manual_fill'" not in job_body


def test_migration_guards_pg_cron_availability() -> None:
    """The migration never hard-fails on a Postgres without pg_cron.

    CREATE EXTENSION is wrapped in an exception-catching DO block, and the
    schedule/unschedule calls are additionally gated on pg_extension so they
    are never reached when the extension failed to install.
    """
    sql = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS pg_cron" in sql
    assert "EXCEPTION WHEN OTHERS THEN" in sql
    assert "RAISE NOTICE" in sql
    assert "FROM pg_extension WHERE extname = 'pg_cron'" in sql


def test_migration_has_no_em_dash() -> None:
    """House style (root CLAUDE.md): never use U+2014 in any project output."""
    sql = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert "—" not in sql
