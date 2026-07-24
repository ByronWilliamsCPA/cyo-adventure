"""Unit tests for the CWE-23 containment gate in ``scripts/run_story_gate.py``.

``run_story_gate`` accepts only a story-file path that resolves under the repo
root; a path escaping the tree (via ``..`` or an absolute out-of-repo location)
is rejected with exit code 1 before any file read. These tests pin that gate,
which otherwise had no test coverage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scripts.run_story_gate import _REPO_ROOT, _resolve_within_repo

if TYPE_CHECKING:
    from pathlib import Path


class TestResolveWithinRepo:
    """The repo-root containment gate for the story-file path argument."""

    def test_resolve_within_repo_in_repo_path_returns_resolved(self) -> None:
        """A path under the repo root is accepted and stays within it."""
        result = _resolve_within_repo(str(_REPO_ROOT / "skeletons" / "s.json"))
        assert result.is_relative_to(_REPO_ROOT)

    def test_resolve_within_repo_parent_escape_exits_1(self) -> None:
        """A ``..`` path climbing above the repo root exits with code 1."""
        with pytest.raises(SystemExit) as exc:
            _ = _resolve_within_repo(str(_REPO_ROOT / ".." / "escape.json"))
        assert exc.value.code == 1

    def test_resolve_within_repo_out_of_repo_absolute_exits_1(
        self, tmp_path: Path
    ) -> None:
        """An absolute path outside the repo tree exits with code 1."""
        with pytest.raises(SystemExit) as exc:
            _ = _resolve_within_repo(str(tmp_path / "s.json"))
        assert exc.value.code == 1
