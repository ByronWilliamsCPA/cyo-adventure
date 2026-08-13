"""Tests for ``scripts/check_no_em_dash.py``.

The hook this script replaced reported success on every commit while 62 em-dashes sat in
the tree, so the cases that matter here are the ones proving detection actually fires and
that the exit code carries it. A test that only asserted "clean file passes" would have
passed against the broken hook too.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_no_em_dash.py"

# The character under test, kept out of the source lines below so each assertion reads
# as prose rather than as a literal that this project's own hook would flag.
EM_DASH = "—"  # em-dash-ok: the character under test


def _load() -> ModuleType:
    """Import the checker from its script path.

    Returns:
        ModuleType: The imported ``check_no_em_dash`` module.
    """
    spec = importlib.util.spec_from_file_location("check_no_em_dash", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_no_em_dash"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="checker")
def checker_fixture() -> ModuleType:
    """Provide the loaded checker module.

    Returns:
        ModuleType: The imported ``check_no_em_dash`` module.
    """
    return _load()


class TestScanText:
    """Detection semantics on in-memory text."""

    def test_em_dash_is_reported_with_position(self, checker: ModuleType) -> None:
        """A single em-dash yields one violation carrying its 1-indexed position."""
        text = f"first line\nsecond {EM_DASH} line\n"
        violations = checker.scan_text(Path("sample.md"), text)
        assert len(violations) == 1
        assert violations[0].line_number == 2
        assert violations[0].column == 8

    def test_every_occurrence_on_a_line_is_reported(self, checker: ModuleType) -> None:
        """Two em-dashes on one line yield two violations, not one."""
        text = f"a {EM_DASH} b {EM_DASH} c\n"
        assert len(checker.scan_text(Path("sample.md"), text)) == 2

    def test_clean_text_yields_nothing(self, checker: ModuleType) -> None:
        """Hyphens, en-dashes, and ordinary prose are untouched."""
        # The en-dash is written as an escape so Ruff's ambiguous-character rule
        # (RUF002) does not fire on a character this test needs to be literal.
        text = "a hyphen-joined word, an en-dash \u2013, and a semicolon; fine.\n"
        assert checker.scan_text(Path("sample.md"), text) == []

    def test_allow_marker_exempts_the_whole_line(self, checker: ModuleType) -> None:
        """A marked line is skipped however many em-dashes it holds."""
        text = (
            f'count = raw.count("{EM_DASH}")  # {checker.ALLOW_MARKER}: counts them\n'
        )
        assert checker.scan_text(Path("sample.md"), text) == []

    def test_allow_marker_does_not_exempt_other_lines(
        self, checker: ModuleType
    ) -> None:
        """The marker is per-line, not a file-wide suppression."""
        text = f"exempt {EM_DASH} here  # {checker.ALLOW_MARKER}: reason\nplain {EM_DASH} line\n"
        violations = checker.scan_text(Path("sample.md"), text)
        assert len(violations) == 1
        assert violations[0].line_number == 2


class TestMain:
    """Exit-code contract, which is what pre-commit actually consumes."""

    def test_violation_exits_non_zero(
        self, checker: ModuleType, tmp_path: Path
    ) -> None:
        """A file with an em-dash fails the run."""
        offender = tmp_path / "doc.md"
        offender.write_text(f"prose {EM_DASH} here\n", encoding="utf-8")
        assert checker.main([str(offender)]) == 1

    def test_clean_file_exits_zero(self, checker: ModuleType, tmp_path: Path) -> None:
        """A file without em-dashes passes."""
        clean = tmp_path / "doc.md"
        clean.write_text("prose, here\n", encoding="utf-8")
        assert checker.main([str(clean)]) == 0

    def test_no_paths_exits_zero(self, checker: ModuleType) -> None:
        """A pre-commit run with no matching staged files must not fail the commit."""
        assert checker.main([]) == 0

    def test_undecodable_file_is_skipped(
        self, checker: ModuleType, tmp_path: Path
    ) -> None:
        """A non-UTF-8 file cannot hold a UTF-8 em-dash, so it is skipped, not fatal."""
        binary = tmp_path / "blob.bin"
        binary.write_bytes(b"\xff\xfe\x00\x01")
        assert checker.main([str(binary)]) == 0

    def test_missing_file_is_skipped(self, checker: ModuleType, tmp_path: Path) -> None:
        """A path that vanished between staging and running is not a violation."""
        assert checker.main([str(tmp_path / "gone.md")]) == 0


class TestRepositoryIsClean:
    """The regression guard: the tree this hook governs must stay clean."""

    def test_tracked_authored_files_have_no_em_dashes(
        self, checker: ModuleType
    ) -> None:
        """Every authored file the hook covers is free of em-dashes.

        Scoped to the trees the pre-commit hook covers, so it mirrors the hook rather
        than asserting something the hook would not have caught. Generated pipeline
        artifacts under ``out/`` are excluded in both places.
        """
        repo_root = Path(__file__).resolve().parents[2]
        violations: list[object] = []
        for relative in ("docs", "src", "tests", "scripts", "supabase"):
            root = repo_root / relative
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                if path.suffix not in {".md", ".py", ".sh", ".sql", ".toml", ".yaml"}:
                    continue
                violations.extend(checker.scan_path(path))
        rendered = "\n".join(v.render() for v in violations)  # type: ignore[attr-defined]
        assert not violations, f"em-dashes found in authored files:\n{rendered}"
