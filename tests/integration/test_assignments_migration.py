"""Migration round-trip for the storybook_assignment table."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from docker.errors import DockerException
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

if TYPE_CHECKING:
    from collections.abc import Iterator

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PREV_HEAD = "c3d4e5f6a7b8"
_FAMILY_A = "00000000-0000-0000-0000-00000000000a"
_FAMILY_B = "00000000-0000-0000-0000-00000000000b"
_CHILD_A = "00000000-0000-0000-0000-0000000000a1"
_CHILD_B = "00000000-0000-0000-0000-0000000000b1"

# Minimal valid rows per the initial-schema create_table definitions: family
# needs name; child_profile needs display_name/age_band/reading_level_cap/
# allowed_content_flags/tts_enabled; storybook needs a status allowed by
# ck_storybook_status ('published' and 'draft' both are).
_SEED_SQL = (
    "INSERT INTO family (id, name) VALUES "
    "('00000000-0000-0000-0000-00000000000a', 'Family A'), "
    "('00000000-0000-0000-0000-00000000000b', 'Family B')",
    "INSERT INTO child_profile (id, family_id, display_name, age_band, "
    "reading_level_cap, allowed_content_flags, tts_enabled) VALUES "
    "('00000000-0000-0000-0000-0000000000a1', "
    "'00000000-0000-0000-0000-00000000000a', 'Child A', '6-9', 3.0, "
    "'[]'::jsonb, false), "
    "('00000000-0000-0000-0000-0000000000b1', "
    "'00000000-0000-0000-0000-00000000000b', 'Child B', '6-9', 3.0, "
    "'[]'::jsonb, false)",
    "INSERT INTO storybook (id, family_id, status) VALUES "
    "('book-a-published', '00000000-0000-0000-0000-00000000000a', 'published'), "
    "('book-a-draft', '00000000-0000-0000-0000-00000000000a', 'draft'), "
    "('book-b-published', '00000000-0000-0000-0000-00000000000b', 'published')",
)


def _run_alembic(
    project_root: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    """Run an alembic command in a subprocess against the given env."""
    return subprocess.run(
        ["uv", "run", "alembic", *args],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_root),
        check=False,
    )


@pytest.fixture(scope="module")
def _migration_pg_url() -> Iterator[str]:
    """Start a fresh Postgres 16 container for the migration round-trip test."""
    try:
        container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
        container.start()
    except (DockerException, OSError) as exc:
        pytest.skip(f"Docker/Postgres testcontainer unavailable: {exc}")
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.mark.integration
def test_assignment_migration_imports_and_chains() -> None:
    """The migration file parses, exports upgrade/downgrade, and chains to head."""
    migration_dir = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    files = list(migration_dir.glob("*add_storybook_assignment*.py"))
    assert files, f"assignment migration not found in {migration_dir}"
    spec = importlib.util.spec_from_file_location("_assign_migration", files[0])
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert callable(getattr(mod, "upgrade", None))
    assert callable(getattr(mod, "downgrade", None))
    assert mod.down_revision == "c3d4e5f6a7b8", (
        f"Expected down_revision 'c3d4e5f6a7b8', got {mod.down_revision!r}"
    )


@pytest.mark.integration
def test_assignment_migration_upgrade_downgrade(
    _migration_pg_url: str,  # noqa: PT019
) -> None:
    """alembic upgrade head then downgrade -1 succeed on a clean DB."""
    project_root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": _migration_pg_url}
    up = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_root),
        check=False,
    )
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"
    assert "Running upgrade" in up.stderr
    down = subprocess.run(
        ["uv", "run", "alembic", "downgrade", "-1"],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_root),
        check=False,
    )
    assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"
    assert "Running downgrade" in down.stderr


@pytest.mark.integration
@pytest.mark.asyncio
async def test_assignment_backfill_data_integrity(
    _migration_pg_url: str,  # noqa: PT019
) -> None:
    """Backfill inserts exactly the same-family published pairs, nothing else.

    Sequence: migrate to the pre-assignment head, seed two families (one child
    each; family A has one published and one draft book, family B one published
    book), run the assignment migration, and assert the backfilled rows are
    exactly the two same-family published pairs with assigned_by NULL. Then
    downgrade and assert the table is gone. The sequence is order-independent
    with the round-trip test sharing this module's container: upgrade to
    _PREV_HEAD is a no-op if already there, and the exact-set assertion holds
    on the fresh seed data either way.
    """
    project_root = _PROJECT_ROOT
    env = {**os.environ, "CYO_ADVENTURE_DATABASE_URL": _migration_pg_url}

    base = _run_alembic(project_root, env, "upgrade", _PREV_HEAD)
    assert base.returncode == 0, f"upgrade to prev head failed:\n{base.stderr}"

    engine = create_async_engine(_migration_pg_url)
    try:
        async with engine.begin() as conn:
            for stmt in _SEED_SQL:
                await conn.execute(sa.text(stmt))

        up = _run_alembic(project_root, env, "upgrade", "head")
        assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"

        async with engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT child_profile_id::text, storybook_id, assigned_by "
                    "FROM storybook_assignment"
                )
            )
            rows = result.all()
        actual = {(r[0], r[1], r[2]) for r in rows}
        expected = {
            (_CHILD_A, "book-a-published", None),
            (_CHILD_B, "book-b-published", None),
        }
        # Exact set equality also proves the draft book produced no row and
        # that no cross-family pair was backfilled.
        assert actual == expected, f"backfill rows wrong: {actual!r}"

        down = _run_alembic(project_root, env, "downgrade", "-1")
        assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"

        async with engine.connect() as conn:
            reg = (
                await conn.execute(
                    sa.text("SELECT to_regclass('storybook_assignment')")
                )
            ).scalar()
        assert reg is None, "storybook_assignment table still exists after downgrade"
    finally:
        await engine.dispose()
