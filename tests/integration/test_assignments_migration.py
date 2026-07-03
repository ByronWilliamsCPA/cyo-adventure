"""Migration round-trip for the storybook_assignment table."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from docker.errors import DockerException
from testcontainers.postgres import PostgresContainer

if TYPE_CHECKING:
    from collections.abc import Iterator


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
