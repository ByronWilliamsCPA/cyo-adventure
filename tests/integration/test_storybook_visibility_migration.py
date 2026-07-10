"""Migration round-trip for storybook.visibility (WS-E, decision E1)."""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

# Pinned ids per repo convention (see test_assignments_migration.py):

_PREV_HEAD = "228c68e8f1e7"
_VISIBILITY_HEAD = "9c4e7d2a5b18"


@pytest.mark.integration
def test_visibility_migration_imports_and_chains() -> None:
    """The migration file parses, exports upgrade/downgrade, and chains to head."""
    migration_dir = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    files = list(migration_dir.glob("*add_storybook_visibility*.py"))
    assert files, f"visibility migration not found in {migration_dir}"
    spec = importlib.util.spec_from_file_location("_visibility_migration", files[0])
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert callable(getattr(mod, "upgrade", None))
    assert callable(getattr(mod, "downgrade", None))
    assert mod.down_revision == _PREV_HEAD


@pytest.mark.integration
def test_visibility_migration_upgrade_downgrade(migration_pg_url: str) -> None:
    """alembic upgrade then downgrade of the visibility revision succeed."""
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}
    up = run_alembic(PROJECT_ROOT, env, "upgrade", _VISIBILITY_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"
    down = run_alembic(PROJECT_ROOT, env, "downgrade", _PREV_HEAD)
    assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_existing_rows_backfill_to_family(migration_pg_url: str) -> None:
    """A storybook row inserted before the migration reads visibility='family'."""
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}
    up = run_alembic(PROJECT_ROOT, env, "upgrade", _PREV_HEAD)
    assert up.returncode == 0, f"upgrade to prev failed:\n{up.stdout}\n{up.stderr}"
    fam_id = str(uuid.uuid4())
    engine = create_async_engine(migration_pg_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("INSERT INTO family (id, name) VALUES (:id, 'Legacy Fam')"),
                {"id": fam_id},
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO storybook (id, family_id, status) "
                    "VALUES ('legacy-book', :fam, 'published')"
                ),
                {"fam": fam_id},
            )
        up2 = run_alembic(PROJECT_ROOT, env, "upgrade", _VISIBILITY_HEAD)
        assert up2.returncode == 0, f"upgrade failed:\n{up2.stdout}\n{up2.stderr}"
        async with engine.connect() as conn:
            row = await conn.execute(
                sa.text("SELECT visibility FROM storybook WHERE id = 'legacy-book'")
            )
            assert row.scalar_one() == "family"
    finally:
        await engine.dispose()
