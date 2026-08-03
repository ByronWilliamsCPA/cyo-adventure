"""The W0.4 backfill migration links only what it can link unambiguously.

``20260801060000_backfill_story_request_resulting_storybook_id.sql`` exists
because the column-adding migration before it leaves every already-published
book at NULL while ``RequestStory.tsx`` retired the substring heuristic that
used to cover that case. Without the backfill, a child's approved request card
reads "your story is being written!" forever for a book sitting on the shelf
directly beneath it (capability-register K12).

A wrong link is worse than a missing one here: it would tell a child their
request produced someone else's book. These tests pin the four decisions that
keep the statement conservative, and re-run the file a second time to prove it
is a no-op on an already-backfilled database (forward-only, ADR-012: there is
no down script to undo a bad run).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration._migration_utils import create_migrated_database

if TYPE_CHECKING:
    from collections.abc import Mapping

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_BACKFILL = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260801060000_backfill_story_request_resulting_storybook_id.sql"
)

# Every id is spelled as a literal rather than a bind parameter, which is not a
# style choice: this script runs over asyncpg's simple query protocol (see
# _exec_script), and the extended protocol that bind parameters require rejects
# a multi-statement string outright. Every value here is a fixed literal in
# this file; none is external input.
#
# The "passed" generation-job status is likewise not arbitrary:
# ck_generation_job_status admits only queued/running/passed/needs_review/
# failed/awaiting_manual_fill, and the intuitive "succeeded" is NOT among them.
# The backfill does not filter on job status at all (it filters on the
# STORYBOOK being published, which is the fact that governs what a child may
# see); this is simply the real terminal success value.
# No f-string, so this is a plain literal rather than a "constructed" query:
# interpolating even a module-level constant here trips Ruff S608, and a
# documented suppression would be a worse trade than spelling the family id
# out. The seed is the same fixture data either way.
_SEED = """
INSERT INTO family (id, name) VALUES ('11111111-0000-4000-8000-000000000001', 'Backfill Fixture');

INSERT INTO concept (id, family_id, brief) VALUES
  ('22222222-0000-4000-8000-00000000000a', '11111111-0000-4000-8000-000000000001', '{}'),
  ('22222222-0000-4000-8000-00000000000b', '11111111-0000-4000-8000-000000000001', '{}'),
  ('22222222-0000-4000-8000-00000000000c', '11111111-0000-4000-8000-000000000001', '{}'),
  ('22222222-0000-4000-8000-00000000000d', '11111111-0000-4000-8000-000000000001', '{}');

INSERT INTO storybook (id, family_id, status, current_published_version) VALUES
  ('s_case_a',       '11111111-0000-4000-8000-000000000001', 'published', 2),
  ('s_case_b',       '11111111-0000-4000-8000-000000000001', 'draft',     1),
  ('s_case_c1',      '11111111-0000-4000-8000-000000000001', 'published', 1),
  ('s_case_c2',      '11111111-0000-4000-8000-000000000001', 'published', 1),
  ('s_case_d',       '11111111-0000-4000-8000-000000000001', 'published', 1),
  ('s_case_d_prior', '11111111-0000-4000-8000-000000000001', 'published', 1);

INSERT INTO generation_job (id, concept_id, status, storybook_id, version)
VALUES
  ('33333333-0000-4000-8000-00000000000a',
   '22222222-0000-4000-8000-00000000000a', 'passed', 's_case_a',  2),
  ('33333333-0000-4000-8000-00000000000b',
   '22222222-0000-4000-8000-00000000000b', 'passed', 's_case_b',  1),
  ('33333333-0000-4000-8000-0000000000c1',
   '22222222-0000-4000-8000-00000000000c', 'passed', 's_case_c1', 1),
  ('33333333-0000-4000-8000-0000000000c2',
   '22222222-0000-4000-8000-00000000000c', 'passed', 's_case_c2', 1),
  ('33333333-0000-4000-8000-00000000000d',
   '22222222-0000-4000-8000-00000000000d', 'passed', 's_case_d',  1);

INSERT INTO story_request
  (id, family_id, request_text, status, age_band, concept_id,
   resulting_storybook_id)
VALUES
  ('44444444-0000-4000-8000-00000000000a', '11111111-0000-4000-8000-000000000001', 'A-happy',
   'approved', '5-8', '22222222-0000-4000-8000-00000000000a', NULL),
  ('44444444-0000-4000-8000-00000000000b', '11111111-0000-4000-8000-000000000001', 'B-draft',
   'approved', '5-8', '22222222-0000-4000-8000-00000000000b', NULL),
  ('44444444-0000-4000-8000-00000000000c', '11111111-0000-4000-8000-000000000001', 'C-ambiguous',
   'approved', '5-8', '22222222-0000-4000-8000-00000000000c', NULL),
  ('44444444-0000-4000-8000-00000000000d', '11111111-0000-4000-8000-000000000001', 'D-stamped',
   'approved', '5-8', '22222222-0000-4000-8000-00000000000d',
   's_case_d_prior'),
  ('44444444-0000-4000-8000-00000000000e', '11111111-0000-4000-8000-000000000001', 'E-no-concept',
   'approved', '5-8', NULL, NULL);
"""

_EXPECTED: Mapping[str, str | None] = {
    # The whole point: a published book resolves through
    # storybook -> generation_job -> concept -> story_request, exactly as
    # publishing/service.py::_stamp_resulting_storybook_id does at publish time.
    "A-happy": "s_case_a",
    # A draft must never surface to a child through this field, which is why
    # approve() is the only runtime writer. The backfill holds the same line.
    "B-draft": None,
    # Two published storybooks under one concept: neither
    # (generation_job.storybook_id, version) nor story_request.concept_id is
    # UNIQUE, so this is representable. Skipped rather than guessed.
    "C-ambiguous": None,
    # An existing stamp wins. This is what makes a second run a no-op, and it
    # protects a value approve() wrote from being replaced by a re-derived one.
    "D-stamped": "s_case_d_prior",
    # No concept, no chain to walk, nothing to claim.
    "E-no-concept": None,
}


async def _exec_script(url: str, script: str) -> None:
    """Run a multi-statement SQL script over asyncpg's simple query protocol.

    Uses a RAW asyncpg connection, exactly as ``_migration_utils.py`` does to
    apply the migration files themselves, and for the same reason: everything
    routed through the SQLAlchemy asyncpg dialect (including
    ``exec_driver_sql``) goes out as a prepared statement, and Postgres rejects
    a multi-statement string there with "cannot insert multiple commands into a
    prepared statement". Splitting the script on semicolons to work around that
    would be a lie about how a migration actually runs in production.

    Args:
        url: A ``postgresql+asyncpg://`` SQLAlchemy URL; the scheme is
            rewritten for asyncpg's own connect().
        script: The script text; may contain several statements.
    """
    raw = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await raw.execute(script)
    finally:
        await raw.close()


async def _stamps(url: str) -> dict[str, str | None]:
    """Read back every request's ``resulting_storybook_id`` by request text.

    Args:
        url: An asyncpg SQLAlchemy URL for the database to read.

    Returns:
        dict[str, str | None]: ``{request_text: resulting_storybook_id}``.
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT request_text, resulting_storybook_id FROM story_request")
            )
            return {str(row[0]): row[1] for row in rows}
    finally:
        await engine.dispose()


async def test_backfill_links_only_unambiguous_published_books(pg_url: str) -> None:
    """Seed all five shapes, re-run the file, and assert every decision.

    The migration chain (which includes the backfill) is applied to an empty
    database first, so the run under test is the one AFTER the seed. That
    doubles as the re-runnability check the file's header claims: a second
    application must not disturb what the first produced.

    Args:
        pg_url: The session-scoped testcontainers Postgres URL; a sibling
            database is created on the same server.
    """
    url = await create_migrated_database(pg_url, "w04_backfill")
    await _exec_script(url, _SEED)

    await _exec_script(url, _BACKFILL.read_text(encoding="utf-8"))
    assert await _stamps(url) == dict(_EXPECTED)

    # Idempotence. Asserted as a SECOND full comparison rather than a bare
    # "no exception": a statement that dropped or re-derived D-stamped would
    # run cleanly and still be wrong.
    await _exec_script(url, _BACKFILL.read_text(encoding="utf-8"))
    assert await _stamps(url) == dict(_EXPECTED)
