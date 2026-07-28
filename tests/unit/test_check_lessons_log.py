"""Unit tests for scripts/check_lessons_log.py.

scripts/ is not an importable package (no __init__.py, by design; see
per-file-ignores INP for scripts/**/*.py in pyproject.toml), so the module is
loaded directly from its file path via importlib.

Covers the escaped-pipe contract: the column-count error message promises
authors that a literal ``|`` inside a cell may be written ``\\|``, so
``_split_row`` must honour that escape rather than tearing the cell in two.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str) -> ModuleType:
    """Load a scripts/ module from its file path."""
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load("check_lessons_log")


def test_split_row_strips_outer_pipes_and_trims() -> None:
    """A plain row drops the leading and trailing empty cells and trims values."""
    assert _MODULE._split_row("| AL-001 | fixed | done |") == [
        "AL-001",
        "fixed",
        "done",
    ]


def test_split_row_keeps_escaped_pipe_as_one_cell() -> None:
    """An escaped pipe stays inside its cell instead of splitting the row.

    Without honouring the escape the cell ``a \\| b`` would count as two
    columns, tripping the column-count check that the error message itself tells
    authors to avoid by escaping.
    """
    assert _MODULE._split_row(r"| AL-002 | a \| b | done |") == [
        "AL-002",
        "a | b",
        "done",
    ]


def test_split_row_escaped_cell_preserves_column_count() -> None:
    """An escaped pipe leaves the row at its declared column width."""
    cells = _MODULE._split_row(
        r"| AL-003 | 2026-07-26 | run | tooling | uses \| in text "
        r"| escape it | applied | ref |"
    )
    assert len(cells) == len(_MODULE._COLUMNS)
    assert "uses | in text" in cells
