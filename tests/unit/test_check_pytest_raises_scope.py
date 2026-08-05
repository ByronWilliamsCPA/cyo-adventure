"""Unit tests for scripts/check_pytest_raises_scope.py.

scripts/ is not an importable package (no __init__.py, by design; see per-file-ignores INP for
scripts/**/*.py in pyproject.toml), so the module is loaded directly from its file path via
importlib, matching tests/unit/test_check_work_linkage.py and tests/unit/test_check_lessons_log.py.

Covers the S5778 detection logic (body-only counting, header calls never counting, the SAFE
builtin exclusion including the newly added ``Path`` and ``frozenset``), ``async with`` handling,
and ``main``'s exit codes and no-paths behaviour.

Self-consistency note: every real ``with pytest.raises(...)`` block written below (as opposed to
the ones embedded in fixture source strings, which are not executed as code in this file) has
exactly one non-safe call in its body, so this file itself passes the checker it tests. That is
asserted directly by ``test_script_is_clean_against_its_own_file``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str) -> ModuleType:
    """Load a scripts/ module from its file path.

    Registered in ``sys.modules`` before execution: the checked-in module defines a frozen
    ``dataclass`` under ``from __future__ import annotations``, and dataclass field
    resolution on 3.14 looks its own module up in ``sys.modules`` by ``__module__`` name,
    which fails with an opaque ``AttributeError`` on ``None`` if the module was never
    registered there.

    Args:
        name: The module's file stem under scripts/.

    Returns:
        ModuleType: The imported module.
    """
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load("check_pytest_raises_scope")


def _write(path: Path, content: str) -> Path:
    """Write dedented text to a file and return its path, for compact fixture setup.

    Args:
        path: The file to write.
        content: The text to write; dedented before writing so callers can indent fixture
            source naturally inside a test function.

    Returns:
        Path: The same path, for chaining into a function call.
    """
    path.write_text(dedent(content), encoding="utf-8")
    return path


def test_find_violations_allows_a_single_body_call(tmp_path: Path) -> None:
    """A body with exactly one non-safe call is not a violation."""
    path = _write(
        tmp_path / "test_single.py",
        """
        import pytest


        def do_work() -> None:
            raise ValueError("boom")


        def test_example() -> None:
            with pytest.raises(ValueError):
                do_work()
        """,
    )
    assert _MODULE.find_violations(path) == []


def test_find_violations_flags_two_body_calls(tmp_path: Path) -> None:
    """A body with two non-safe calls is flagged, with both calls reported."""
    path = _write(
        tmp_path / "test_double.py",
        """
        import pytest


        def setup() -> None:
            pass


        def do_work() -> None:
            raise ValueError("boom")


        def test_example() -> None:
            with pytest.raises(ValueError):
                setup()
                do_work()
        """,
    )
    violations = _MODULE.find_violations(path)
    assert len(violations) == 1
    assert violations[0].calls == ("setup()", "do_work()")


def test_find_violations_ignores_calls_in_the_with_header(tmp_path: Path) -> None:
    """Calls inside the ``pytest.raises(...)`` header never count, however many there are.

    This is the load-bearing case that the empirically-derived rule gets right and both
    plausible readings of the published rule text got wrong: the header below has two
    non-safe calls (``make_pattern`` and ``extra_call``), and the body has exactly one
    (``do_work``). If header calls counted, this would be flagged; per S5778's actual
    behaviour in this repository, it must not be.
    """
    path = _write(
        tmp_path / "test_header.py",
        """
        import pytest


        def make_pattern(extra: str) -> str:
            return extra


        def extra_call() -> str:
            return "boom"


        def do_work() -> None:
            raise ValueError("boom")


        def test_example() -> None:
            with pytest.raises(ValueError, match=make_pattern(extra_call())):
                do_work()
        """,
    )
    assert _MODULE.find_violations(path) == []


def test_find_violations_excludes_safe_builtins_from_the_count(tmp_path: Path) -> None:
    """SAFE builtins, including the newly added Path and frozenset, do not count.

    The body below has four statements; three call SAFE builtins (``str``, ``Path``,
    ``frozenset``) and only ``do_work`` is a real, non-safe call. The non-safe count is 1,
    so this must not be flagged.
    """
    path = _write(
        tmp_path / "test_safe.py",
        """
        import pytest
        from pathlib import Path


        def do_work() -> None:
            raise ValueError("boom")


        def test_example() -> None:
            with pytest.raises(ValueError) as exc_info:
                do_work()
                str(exc_info.value)
                Path("some/path")
                frozenset({1, 2})
        """,
    )
    assert _MODULE.find_violations(path) == []


def test_find_violations_still_flags_two_non_safe_calls_alongside_a_safe_one(
    tmp_path: Path,
) -> None:
    """A SAFE call plus two non-safe calls is still a violation of exactly two."""
    path = _write(
        tmp_path / "test_mixed.py",
        """
        import pytest


        def setup() -> None:
            pass


        def do_work() -> None:
            raise ValueError("boom")


        def test_example() -> None:
            with pytest.raises(ValueError):
                setup()
                do_work()
                str(1)
        """,
    )
    violations = _MODULE.find_violations(path)
    assert len(violations) == 1
    assert violations[0].calls == ("setup()", "do_work()")


def test_find_violations_handles_async_with(tmp_path: Path) -> None:
    """An ``async with pytest.raises(...)`` block is checked the same way as a sync one."""
    path = _write(
        tmp_path / "test_async.py",
        """
        import pytest


        async def do_work() -> None:
            raise ValueError("boom")


        async def test_example() -> None:
            async with pytest.raises(ValueError):
                await do_work()
                await do_work()
        """,
    )
    violations = _MODULE.find_violations(path)
    assert len(violations) == 1
    assert violations[0].calls == ("do_work()", "do_work()")


def test_find_violations_accepts_bare_raises_import(tmp_path: Path) -> None:
    """A bare ``raises(...)`` (via ``from pytest import raises``) is recognised too."""
    path = _write(
        tmp_path / "test_bare.py",
        """
        from pytest import raises


        def setup() -> None:
            pass


        def do_work() -> None:
            raise ValueError("boom")


        def test_example() -> None:
            with raises(ValueError):
                setup()
                do_work()
        """,
    )
    violations = _MODULE.find_violations(path)
    assert len(violations) == 1


def test_find_violations_ignores_with_blocks_that_are_not_raises(
    tmp_path: Path,
) -> None:
    """A ``with`` block guarding something other than ``raises`` is never inspected."""
    path = _write(
        tmp_path / "test_other.py",
        """
        def test_example() -> None:
            with open("some/file") as handle:
                handle.read()
                handle.seek(0)
        """,
    )
    assert _MODULE.find_violations(path) == []


def test_find_violations_propagates_syntax_error(tmp_path: Path) -> None:
    """An unparsable file raises SyntaxError rather than being silently skipped."""
    path = _write(tmp_path / "broken.py", "def broken(:\n")
    with pytest.raises(SyntaxError):
        _MODULE.find_violations(path)


def test_main_returns_0_with_no_paths() -> None:
    """A pre-commit run with no matching staged files must not fail the commit."""
    assert _MODULE.main([]) == 0


def test_main_returns_0_with_no_violations(tmp_path: Path) -> None:
    """A clean file exits 0."""
    path = _write(
        tmp_path / "test_clean.py",
        """
        import pytest


        def do_work() -> None:
            raise ValueError("boom")


        def test_example() -> None:
            with pytest.raises(ValueError):
                do_work()
        """,
    )
    assert _MODULE.main([str(path)]) == 0


def test_main_returns_1_with_a_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file with a violation exits 1 and reports the file, line, and offending calls."""
    path = _write(
        tmp_path / "test_dirty.py",
        """
        import pytest


        def setup() -> None:
            pass


        def do_work() -> None:
            raise ValueError("boom")


        def test_example() -> None:
            with pytest.raises(ValueError):
                setup()
                do_work()
        """,
    )
    exit_code = _MODULE.main([str(path)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert str(path) in captured.out
    assert "setup()" in captured.out
    assert "do_work()" in captured.out


def test_main_reports_an_unreadable_file_as_a_problem_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing file is reported by name and fails the run rather than being skipped."""
    missing = tmp_path / "does_not_exist.py"
    exit_code = _MODULE.main([str(missing)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "cannot check" in captured.out
    assert str(missing) in captured.out


def test_script_is_clean_against_its_own_file() -> None:
    """The checker's own module has no S5778 violations (it takes no pytest.raises at all)."""
    module_path = _SCRIPTS / "check_pytest_raises_scope.py"
    assert _MODULE.find_violations(module_path) == []


def test_script_is_clean_against_its_own_test_file() -> None:
    """This test file passes its own checker: every real pytest.raises block has one call.

    Fixture source embedded as triple-quoted strings above is not executed AST in this
    file, so it does not count; only the real ``with pytest.raises(SyntaxError)`` block in
    ``test_find_violations_propagates_syntax_error`` is a live site, and it has exactly one
    call in its body.
    """
    this_file = Path(__file__).resolve()
    assert _MODULE.find_violations(this_file) == []
