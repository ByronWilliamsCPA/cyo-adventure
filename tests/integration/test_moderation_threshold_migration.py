"""Migration round-trip for the WS-A moderation threshold tables."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

# Pin the round-trip to explicit revision ids rather than "head"/"-1": a
# relative target silently retargets whenever a later migration lands on top,
# which is the lesson from PR #108 (see test_storybook_version_provider_migration.py
# for the same pattern).
_PREV_HEAD = "a7b8c9d0e1f2"
_THRESHOLD_HEAD = "b8c9d0e1f2a3"


@pytest.mark.integration
def test_threshold_migration_imports_and_chains() -> None:
    """The migration file parses, exports upgrade/downgrade, and chains to head."""
    migration_dir = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    files = list(migration_dir.glob("*add_moderation_threshold*.py"))
    assert files, f"threshold migration not found in {migration_dir}"
    spec = importlib.util.spec_from_file_location("_threshold_migration", files[0])
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
def test_threshold_migration_upgrade_downgrade(
    migration_pg_url: str,
) -> None:
    """alembic upgrade then downgrade of the threshold revision succeed."""
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _THRESHOLD_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"
    assert "Running upgrade" in up.stderr

    down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
    assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"
    assert "Running downgrade" in down.stderr


@pytest.mark.integration
@pytest.mark.asyncio
async def test_threshold_tables_present_only_while_upgraded(
    migration_pg_url: str,
) -> None:
    """The tables exist after upgrade and are gone again after downgrade.

    Shares this module's container with the round-trip test above: upgrading
    to _THRESHOLD_HEAD is a no-op if already there, so this is order-independent.
    """
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _THRESHOLD_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"

    engine = create_async_engine(migration_pg_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'moderation_threshold'"
                )
            )
            assert result.first() is not None, (
                "moderation_threshold table missing after upgrade"
            )

            result = await conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'moderation_threshold_audit'"
                )
            )
            assert result.first() is not None, (
                "moderation_threshold_audit table missing after upgrade"
            )

        down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
        assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"

        async with engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'moderation_threshold'"
                )
            )
            assert result.first() is None, (
                "moderation_threshold table still present after downgrade"
            )

            result = await conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'moderation_threshold_audit'"
                )
            )
            assert result.first() is None, (
                "moderation_threshold_audit table still present after downgrade"
            )
    finally:
        await engine.dispose()
