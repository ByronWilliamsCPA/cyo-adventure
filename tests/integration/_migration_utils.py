"""Shared helpers for migration round-trip tests.

Underscore-prefixed module name so pytest does not collect it as a test
module. ``PROJECT_ROOT`` and ``run_alembic`` were previously duplicated
verbatim across every migration-test file; the module-scoped
``migration_pg_url`` fixture lives in ``tests/integration/conftest.py``
instead, since conftest fixtures are auto-discovered without an import.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_alembic(
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
