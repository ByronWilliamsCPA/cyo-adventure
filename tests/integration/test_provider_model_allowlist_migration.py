"""Migration round-trip for the WS-C PR1 provider allowlist tables."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from cyo_adventure.generation.allowlist import DEFAULT_ALLOWLIST
from tests.integration._migration_utils import PROJECT_ROOT, run_alembic

# Pin the round-trip to explicit revision ids rather than "head"/"-1" (lesson
# from PR #108; see test_moderation_threshold_migration.py for the same note).
_PREV_HEAD = "e1f2a3b4c5d6"
_ALLOWLIST_HEAD = "f2a3b4c5d6e7"


@pytest.mark.integration
def test_allowlist_migration_imports_and_chains() -> None:
    """The migration file parses, exports upgrade/downgrade, and chains to head."""
    migration_dir = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    files = list(migration_dir.glob("*add_provider_model_allowlist*.py"))
    assert files, f"allowlist migration not found in {migration_dir}"
    spec = importlib.util.spec_from_file_location("_allowlist_migration", files[0])
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
def test_allowlist_migration_upgrade_downgrade(migration_pg_url: str) -> None:
    """alembic upgrade then downgrade of the allowlist revision succeed."""
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _ALLOWLIST_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"
    assert "Running upgrade" in up.stderr

    down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
    assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"
    assert "Running downgrade" in down.stderr


@pytest.mark.integration
@pytest.mark.asyncio
async def test_allowlist_tables_present_only_while_upgraded(
    migration_pg_url: str,
) -> None:
    """Both tables exist after upgrade and are gone again after downgrade."""
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _ALLOWLIST_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"

    engine = create_async_engine(migration_pg_url)
    try:
        async with engine.connect() as conn:
            for table in ("provider_model_allowlist", "provider_model_allowlist_audit"):
                result = await conn.execute(
                    sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = :t"
                    ).bindparams(t=table)
                )
                assert result.first() is not None, f"{table} missing after upgrade"

        down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
        assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"

        async with engine.connect() as conn:
            for table in ("provider_model_allowlist", "provider_model_allowlist_audit"):
                result = await conn.execute(
                    sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = :t"
                    ).bindparams(t=table)
                )
                assert result.first() is None, f"{table} still present after downgrade"
    finally:
        await engine.dispose()


# The migration seeds these rows itself (see the _SEED_ROWS literal in
# 20260709_1000_add_provider_model_allowlist.py). This test is deliberately
# self-contained: it asserts against literals that mirror the migration's own
# seed literals, NOT against cyo_adventure.generation.allowlist.DEFAULT_ALLOWLIST
# (Task 4, which does not exist yet). The exact-match "seed equals
# DEFAULT_ALLOWLIST" drift-guard belongs in Task 4's test suite, where that
# constant exists; do not reintroduce that dependency here.
_EXPECTED_SEED_COUNT = 5
_SPOT_CHECK_PAIRS = (
    ("anthropic", "claude-sonnet-4-6"),
    ("openrouter", "anthropic/claude-haiku-4.5"),
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_rows_present_after_upgrade(migration_pg_url: str) -> None:
    """The migration's own seed rows land, enabled, alongside the new table."""
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _ALLOWLIST_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"

    engine = create_async_engine(migration_pg_url)
    try:
        async with engine.connect() as conn:
            count_result = await conn.execute(
                sa.text("SELECT count(*) FROM provider_model_allowlist")
            )
            assert count_result.scalar_one() == _EXPECTED_SEED_COUNT

            for provider, model_id in _SPOT_CHECK_PAIRS:
                enabled_result = await conn.execute(
                    sa.text(
                        "SELECT enabled FROM provider_model_allowlist "
                        "WHERE provider = :provider AND model_id = :model_id"
                    ).bindparams(provider=provider, model_id=model_id)
                )
                row = enabled_result.first()
                assert row is not None, f"seed row {provider}/{model_id} missing"
                assert row.enabled is True, (
                    f"seed row {provider}/{model_id} not enabled"
                )

        down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
        assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_matches_default_allowlist(migration_pg_url: str) -> None:
    """The migration's hand-synced seed literals match DEFAULT_ALLOWLIST exactly.

    This is the drift guard the migration's RAD note promises: if someone
    edits the migration's ``_SEED_ROWS`` or
    ``cyo_adventure.generation.allowlist.DEFAULT_ALLOWLIST`` without also
    updating the other, this test fails. It intentionally depends on the
    Task 4 constant, unlike the self-contained
    ``test_seed_rows_present_after_upgrade`` above.
    """
    project_root = PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": migration_pg_url}

    up = run_alembic(project_root, env, "upgrade", _ALLOWLIST_HEAD)
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"

    engine = create_async_engine(migration_pg_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT provider, model_id, enabled FROM provider_model_allowlist"
                )
            )
            seeded_rows = {
                (row.provider, row.model_id, row.enabled) for row in result.all()
            }

        expected_rows = {
            (seed.provider, seed.model_id, True) for seed in DEFAULT_ALLOWLIST
        }
        assert seeded_rows == expected_rows

        down = run_alembic(project_root, env, "downgrade", _PREV_HEAD)
        assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"
    finally:
        await engine.dispose()
