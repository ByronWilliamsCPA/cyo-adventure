"""Tests for the ADR-007 raw-output retention purge (M5 register item S10).

Two purge paths are covered:

- The on-publish path, which no longer purges. ``publishing.service.approve``
  used to null the originating ``GenerationJob.report`` in the same transaction
  as the publish write; ADR-007's 2026-08-11 amendment removed that, because it
  defeated the approve half of the exemption below. The tests here now assert
  the *absence* of any UPDATE on that path. Exercised the same
  Docker-independent way as ``tests/unit/test_publishing_service_unit.py``: a
  mocked ``AsyncSession``, no real database.
- The 30-day scheduled path: a pg_cron job registered by
  ``supabase/migrations/20260718000000_add_report_retention_purge.sql`` and
  amended by ``20260810000000_exempt_reviewed_generation_job_report_from_purge.sql``
  (2026-08-10, review-scorecard calibration corpus). pg_cron cannot run
  inside a unit test, so this module asserts on the migration files' text
  content instead (job name, 30-day interval, target table/column, idempotent
  unschedule-then-schedule shape, and, for the amendment, the reviewed-
  storybook exemption clause).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Update
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

_AMENDMENT_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260810000000_exempt_reviewed_generation_job_report_from_purge.sql"
)

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"

# The two single-statement files that rebuild the send-back exemption's index
# without locking pipeline_event, in the order they apply.
_INDEX_REBUILD_MIGRATIONS = (
    _MIGRATIONS_DIR / "20260811170000_drop_pipeline_event_entity_event_type_index.sql",
    _MIGRATIONS_DIR
    / "20260811170100_create_pipeline_event_entity_event_type_index_concurrently.sql",
)


def _statements(sql: str) -> list[str]:
    """Split migration SQL into statements, dropping comments and blanks.

    Deliberately naive: it strips whole-line ``--`` comments and splits on
    semicolons. That is enough for the two files it is used on, which contain
    one statement each by construction, and it stays honest about why they do
    (a multi-statement file is executed as a pgx pipeline, where CONCURRENTLY
    fails with SQLSTATE 25001 and aborts the deploy).
    """
    body = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    return [stmt.strip() for stmt in body.split(";") if stmt.strip()]


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


def _scalar_result(value: object) -> MagicMock:
    """Build a fake ``Result`` whose ``scalar_one_or_none()`` returns ``value``.

    W0.4: a bare ``AsyncMock(spec=AsyncSession)`` makes
    ``session.execute(...)`` itself return an ``AsyncMock``, so
    ``.scalar_one_or_none()`` on it is a coroutine rather than a value;
    ``_stamp_resulting_storybook_id`` (called by every ``approve()`` run)
    needs a real, sync ``Result`` double instead. Mirrors
    tests/unit/test_publishing_service_unit.py's identical helper.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_approve_does_not_purge_generation_job_report() -> None:
    """approve() issues no UPDATE, so the published job's report survives.

    ADR-007's 2026-08-11 amendment removed the on-publish purge. It had
    defeated the approve half of the migration's reviewed-storybook exemption
    outright: the sweep spares a job whose storybook reached "published", and
    approve() had already nulled that job's report before the sweep could ever
    see it, so no approval could reach the calibration corpus the exemption
    exists to build.

    Asserting on the absence of any UPDATE, rather than on the report column,
    is deliberate: a mocked session records statements but has no rows, so the
    statement stream is the only observable. It is also the assertion that
    fails loudly if a purge is reintroduced in any shape.
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
    # W0.4: see _scalar_result's own docstring for why this is needed.
    session.execute = AsyncMock(return_value=_scalar_result(None))
    principal = _principal("admin")

    await service.approve(session, principal, story, 1)

    update_calls = [
        call
        for call in session.execute.await_args_list
        if isinstance(call.args[0], Update)
    ]
    assert update_calls == [], (
        "approve() must issue no UPDATE: retention for a reviewed job is decided "
        "solely by the purge predicate in "
        "20260810000000_exempt_reviewed_generation_job_report_from_purge.sql. "
        f"Got {[str(c.args[0]) for c in update_calls]}"
    )


@pytest.mark.asyncio
async def test_approve_issues_no_update_statements() -> None:
    """The publish write still shares one transaction with the caller.

    approve() never calls session.commit() (the request unit-of-work owns that
    per api/deps.py), so asserting commit was never awaited is a proxy for "the
    publish is still uncommitted" and a caller-level rollback would undo it.
    Re-asserted at a second version because the removed purge was the only
    statement that had been version-scoped, and nothing else on this path may
    quietly become one.
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
    # W0.4: see _scalar_result's own docstring for why this is needed.
    session.execute = AsyncMock(return_value=_scalar_result(None))

    await service.approve(session, _principal("admin"), story, 2)

    session.commit.assert_not_awaited()
    assert not any(
        isinstance(call.args[0], Update) for call in session.execute.await_args_list
    ), "approve() must remain free of UPDATE statements at every version"


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


# ---------------------------------------------------------------------------
# 2026-08-10 amendment: exempt a reviewed storybook's generation jobs
# ---------------------------------------------------------------------------


def test_amendment_migration_file_exists() -> None:
    """The review-scorecard calibration exemption migration is present."""
    assert _AMENDMENT_MIGRATION_PATH.is_file(), (
        f"expected migration at {_AMENDMENT_MIGRATION_PATH}, amending "
        "20260718000000_add_report_retention_purge.sql per ADR-007's "
        "2026-08-10 amendment"
    )


def test_amendment_migration_reschedules_same_job_name() -> None:
    """The amendment targets the SAME job name (in-place predicate change).

    Task requirement: amend the purge predicate rather than replacing the
    job wholesale -- a second job under a different name would leave the
    original, unqualified sweep still running alongside it.
    """
    sql = _AMENDMENT_MIGRATION_PATH.read_text(encoding="utf-8")
    assert "purge_generation_job_report" in sql
    assert "cron.schedule(" in sql


def test_amendment_migration_unschedules_before_scheduling() -> None:
    """Idempotent by job name: unschedule-then-schedule, not schedule-only."""
    sql = _AMENDMENT_MIGRATION_PATH.read_text(encoding="utf-8")
    unschedule_idx = sql.index("cron.unschedule(")
    schedule_idx = sql.index("cron.schedule(")
    assert unschedule_idx < schedule_idx, (
        "expected cron.unschedule(...) to appear before cron.schedule(...) "
        "so re-applying this migration replaces rather than duplicates the job"
    )


def test_amendment_migration_keeps_thirty_day_default_and_terminal_statuses() -> None:
    """The default 30-day window and terminal-status filter survive unchanged.

    Task requirement: the exemption must be narrow; jobs that never reached a
    human still purge on the original schedule.
    """
    sql = _AMENDMENT_MIGRATION_PATH.read_text(encoding="utf-8")
    assert "interval '30 days'" in sql
    job_body = sql.split("$job$")[1]
    assert "'passed', 'needs_review', 'failed'" in job_body
    assert "'queued'" not in job_body
    assert "'running'" not in job_body
    assert "'awaiting_manual_fill'" not in job_body


def test_amendment_migration_exempts_human_approved_storybooks() -> None:
    """The approve half of the exemption keys on published/archived status."""
    sql = _AMENDMENT_MIGRATION_PATH.read_text(encoding="utf-8")
    job_body = sql.split("$job$")[1]
    assert "NOT EXISTS" in job_body
    assert '"public"."storybook"' in job_body
    assert "'published', 'archived'" in job_body
    # The undecided statuses must NOT appear in the exemption's status list,
    # so a draft or still-in-review storybook's job keeps purging on schedule.
    assert "'draft'" not in job_body
    assert "'in_review'" not in job_body


def test_amendment_migration_exempts_send_back_via_event_not_status() -> None:
    """The send-back half must key on the event, never on needs_revision.

    A story reaches ``needs_revision`` without a human ever seeing it via the
    ``draft --auto_reject--> needs_revision`` hop that
    ``moderation/pipeline.py`` drives on a hard classifier BLOCK. Exempting on
    that status would preserve every machine-rejected story's raw output
    indefinitely: it widens ADR-007's retention window with no human decision
    to justify it, and fills the calibration corpus with rows carrying no
    reviewer judgment. Only ``publishing/service.py::send_back`` writes a
    SENT_BACK pipeline event, so the event is the human-only marker.
    """
    sql = _AMENDMENT_MIGRATION_PATH.read_text(encoding="utf-8")
    job_body = sql.split("$job$")[1]
    assert '"public"."pipeline_event"' in job_body
    assert "'sent_back'" in job_body
    assert "'storybook'" in job_body
    # The regression this guards: needs_revision must never gate the exemption.
    assert "needs_revision" not in job_body


def test_amendment_migration_indexes_the_event_lookup() -> None:
    """The pipeline_event probe is indexed, not a nightly sequential scan."""
    sql = _AMENDMENT_MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ix_pipeline_event_entity_event_type" in sql
    assert '"entity_type", "entity_id", "event_type"' in sql


def test_amendment_migration_still_only_targets_report_column() -> None:
    """The amended UPDATE still nulls only generation_job.report."""
    sql = _AMENDMENT_MIGRATION_PATH.read_text(encoding="utf-8")
    assert '"public"."generation_job"' in sql
    assert 'SET "report" = NULL' in sql


def test_amendment_migration_guards_pg_cron_availability() -> None:
    """The amendment never hard-fails on a Postgres without pg_cron."""
    sql = _AMENDMENT_MIGRATION_PATH.read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS pg_cron" in sql
    assert "EXCEPTION WHEN OTHERS THEN" in sql
    assert "RAISE NOTICE" in sql
    assert "FROM pg_extension WHERE extname = 'pg_cron'" in sql


def test_amendment_migration_has_no_em_dash() -> None:
    """House style (root CLAUDE.md): never use U+2014 in any project output."""
    sql = _AMENDMENT_MIGRATION_PATH.read_text(encoding="utf-8")
    assert "—" not in sql


def test_pipeline_event_index_is_rebuilt_concurrently() -> None:
    """The index rebuild pair exists, is concurrent, and is one statement each.

    The single-statement rule is not style. Supabase CLI 2.109.1 executes a
    multi-statement migration file as a pgx pipeline, and a CONCURRENTLY
    statement inside a pipeline fails with SQLSTATE 25001, which aborts
    ``supabase db push`` and blocks the deploy. A later edit that folds these
    two files together, or adds a second statement to either, would ship a
    migration that cannot apply; this test is what catches that before it
    reaches an environment.
    """
    drop_path, create_path = _INDEX_REBUILD_MIGRATIONS
    for path in _INDEX_REBUILD_MIGRATIONS:
        assert path.is_file(), f"expected migration at {path}"
        statements = _statements(path.read_text(encoding="utf-8"))
        assert len(statements) == 1, (
            f"{path.name} must hold exactly one statement, found "
            f"{len(statements)}; a multi-statement file cannot use CONCURRENTLY"
        )
        assert "concurrently" in statements[0].lower()

    drop_sql = _statements(drop_path.read_text(encoding="utf-8"))[0].lower()
    create_sql = _statements(create_path.read_text(encoding="utf-8"))[0].lower()
    assert drop_sql.startswith("drop index concurrently if exists")
    assert create_sql.startswith("create index concurrently if not exists")
    # Same name and same column list as the index 20260810000000 created, so
    # the rebuild changes how it is built and nothing about what it is.
    for sql in (drop_sql, create_sql):
        assert "ix_pipeline_event_entity_event_type" in sql
    assert '"entity_type", "entity_id", "event_type"' in create_sql


def test_pipeline_event_index_rebuild_sorts_after_the_amendment() -> None:
    """The rebuild applies after the migration that first created the index.

    Supabase applies migrations in filename order and refuses one that sorts
    before the last applied version, so a rebuild timestamped earlier than
    20260810000000 would either never run or block the push.
    """
    for path in _INDEX_REBUILD_MIGRATIONS:
        assert path.name > _AMENDMENT_MIGRATION_PATH.name
    drop_path, create_path = _INDEX_REBUILD_MIGRATIONS
    assert drop_path.name < create_path.name


def test_pipeline_event_index_rebuild_has_no_em_dash() -> None:
    """House style (root CLAUDE.md): never use U+2014 in any project output."""
    for path in _INDEX_REBUILD_MIGRATIONS:
        assert "—" not in path.read_text(encoding="utf-8")
