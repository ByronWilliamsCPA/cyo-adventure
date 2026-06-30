"""Integration guard: committed skeleton diagrams and catalog must be in sync."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.integration
def test_committed_skeleton_diagrams_are_fresh() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/render_skeleton_diagrams.py", "--check"],
        cwd=REPO_ROOT,
        env={"PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Skeleton diagrams/catalog are stale. Run:\n"
        "  PYTHONPATH=. uv run python scripts/render_skeleton_diagrams.py\n"
        f"stderr:\n{result.stderr}"
    )
