"""Migration round-trip for the storybook_version.skeleton_slug column (WS-C PR2)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

# Pin the round-trip to explicit revision ids rather than "head"/"-1": a
# relative target silently retargets whenever a later migration lands on top
# (the lesson from PR #108; see test_storybook_version_provider_migration.py
# for the same pattern).
_PREV_HEAD = "b4c5d6e7f8a9"
_SKELETON_SLUG_HEAD = "228c68e8f1e7"


@pytest.mark.integration
def test_skeleton_slug_migration_imports_and_chains() -> None:
    """The migration file parses, exports upgrade/downgrade, and chains onto PR1's head."""
    migration_dir = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    files = list(migration_dir.glob("*add_storybook_version_skeleton_slug*.py"))
    assert files, f"skeleton_slug migration not found in {migration_dir}"
    spec = importlib.util.spec_from_file_location("_skeleton_slug_migration", files[0])
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert callable(getattr(mod, "upgrade", None))
    assert callable(getattr(mod, "downgrade", None))
    assert mod.down_revision == _PREV_HEAD, (
        f"Expected down_revision {_PREV_HEAD!r}, got {mod.down_revision!r}"
    )


@pytest.mark.integration
def test_skeleton_slug_migration_upgrade_downgrade(
    migration_pg_url: str,
) -> None:
    """alembic upgrade then downgrade of the skeleton_slug revision succeed."""
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _SKELETON_SLUG_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"
    assert "Running upgrade" in up.stderr

    down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
    assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"
    assert "Running downgrade" in down.stderr


@pytest.mark.integration
@pytest.mark.asyncio
async def test_skeleton_slug_column_present_only_while_upgraded(
    migration_pg_url: str,
) -> None:
    """The column exists after upgrade and is gone again after downgrade."""
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _SKELETON_SLUG_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"

    engine = create_async_engine(migration_pg_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'storybook_version' "
                    "AND column_name = 'skeleton_slug'"
                )
            )
            assert result.first() is not None, (
                "storybook_version.skeleton_slug column missing after upgrade"
            )

        down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
        assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"

        async with engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'storybook_version' "
                    "AND column_name = 'skeleton_slug'"
                )
            )
            assert result.first() is None, (
                "storybook_version.skeleton_slug column still present after downgrade"
            )
    finally:
        await engine.dispose()
