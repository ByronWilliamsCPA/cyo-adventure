"""Unit tests for the top-level architecture-diagram SVG generator.

Covers the pure helpers (``_is_renderable``, ``top_level_pumls``, ``is_stale``,
``find_duplicate_svgs``) and the ``main`` CLI in ``--check`` mode, which needs
no PlantUML jar. Git-backed staleness is exercised by monkeypatching
``_git_commit_time`` so the tests stay hermetic and fast.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

import tools.generate_diagram_svgs as gds
from tools.generate_diagram_svgs import (
    _is_renderable,
    find_duplicate_svgs,
    is_stale,
    main,
    top_level_pumls,
)

if TYPE_CHECKING:
    from pathlib import Path

_RENDERABLE = "@startuml demo\nA --> B\n@enduml\n"
# An include-only file: its only @startuml token sits inside a ' comment.
_INCLUDE_ONLY = "' @startuml palette\nskinparam backgroundColor #ffffff\n"


def _puml(directory: Path, name: str, body: str = _RENDERABLE) -> Path:
    path = directory / f"{name}.puml"
    path.write_text(body, encoding="utf-8")
    return path


def _svg(puml: Path, content: bytes) -> Path:
    svg = puml.with_suffix(".svg")
    svg.write_bytes(content)
    return svg


# --- _is_renderable --------------------------------------------------------


def test_is_renderable_true_for_real_diagram(tmp_path: Path) -> None:
    assert _is_renderable(_puml(tmp_path, "a")) is True


def test_is_renderable_false_for_include_only(tmp_path: Path) -> None:
    assert _is_renderable(_puml(tmp_path, "style", _INCLUDE_ONLY)) is False


def test_is_renderable_false_for_non_utf8_file(tmp_path: Path) -> None:
    path = tmp_path / "binary.puml"
    path.write_bytes(b"\xff\xfe\x00@startuml")  # invalid UTF-8, must not raise
    assert _is_renderable(path) is False


# --- top_level_pumls -------------------------------------------------------


def test_top_level_pumls_excludes_include_only_and_sorts(tmp_path: Path) -> None:
    _puml(tmp_path, "zeta")
    _puml(tmp_path, "alpha")
    _puml(tmp_path, "style", _INCLUDE_ONLY)
    assert [p.stem for p in top_level_pumls(tmp_path)] == ["alpha", "zeta"]


def test_top_level_pumls_is_non_recursive(tmp_path: Path) -> None:
    nested = tmp_path / "skeletons"
    nested.mkdir()
    _puml(nested, "buried")
    _puml(tmp_path, "top")
    assert [p.stem for p in top_level_pumls(tmp_path)] == ["top"]


# --- is_stale --------------------------------------------------------------


def test_is_stale_true_when_svg_missing(tmp_path: Path) -> None:
    assert is_stale(_puml(tmp_path, "a")) is True


def test_is_stale_uses_git_time_when_svg_older(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    puml = _puml(tmp_path, "a")
    svg = _svg(puml, b"<svg/>")
    times = {puml: 200, svg: 100}
    monkeypatch.setattr(gds, "_git_commit_time", lambda p: times[p])
    assert is_stale(puml) is True


def test_is_stale_uses_git_time_when_svg_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    puml = _puml(tmp_path, "a")
    svg = _svg(puml, b"<svg/>")
    times = {puml: 100, svg: 200}
    monkeypatch.setattr(gds, "_git_commit_time", lambda p: times[p])
    assert is_stale(puml) is False


def test_is_stale_falls_back_to_mtime_when_untracked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    puml = _puml(tmp_path, "a")
    svg = _svg(puml, b"<svg/>")
    monkeypatch.setattr(gds, "_git_commit_time", lambda _p: None)
    os.utime(svg, (1, 1))
    os.utime(puml, (100, 100))
    assert is_stale(puml) is True  # svg older than puml on disk
    os.utime(svg, (200, 200))
    assert is_stale(puml) is False  # svg newer than puml


# --- find_duplicate_svgs ---------------------------------------------------


def test_find_duplicate_svgs_detects_identical(tmp_path: Path) -> None:
    a = _puml(tmp_path, "a")
    b = _puml(tmp_path, "b")
    _svg(a, b"<svg>same</svg>")
    _svg(b, b"<svg>same</svg>")
    assert len(find_duplicate_svgs([a, b])) == 1


def test_find_duplicate_svgs_none_when_distinct(tmp_path: Path) -> None:
    a = _puml(tmp_path, "a")
    b = _puml(tmp_path, "b")
    _svg(a, b"<svg>a</svg>")
    _svg(b, b"<svg>b</svg>")
    assert find_duplicate_svgs([a, b]) == []


def test_find_duplicate_svgs_skips_missing_svg(tmp_path: Path) -> None:
    assert find_duplicate_svgs([_puml(tmp_path, "a")]) == []


# --- main --check ----------------------------------------------------------


def test_main_check_passes_when_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _puml(tmp_path, "a")
    b = _puml(tmp_path, "b")
    _svg(a, b"<svg>a</svg>")
    _svg(b, b"<svg>b</svg>")
    monkeypatch.setattr(gds, "is_stale", lambda _p: False)
    assert main(["--check", "--diagrams-dir", str(tmp_path)]) == 0


def test_main_check_fails_on_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _puml(tmp_path, "a")
    monkeypatch.setattr(gds, "is_stale", lambda _p: True)
    assert main(["--check", "--diagrams-dir", str(tmp_path)]) == 1


def test_main_check_fails_on_duplicate_svgs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _puml(tmp_path, "a")
    b = _puml(tmp_path, "b")
    _svg(a, b"<svg>dup</svg>")
    _svg(b, b"<svg>dup</svg>")
    monkeypatch.setattr(gds, "is_stale", lambda _p: False)
    # Fresh but byte-identical outputs must still fail the gate.
    assert main(["--check", "--diagrams-dir", str(tmp_path)]) == 1


def test_main_check_and_all_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--check", "--all", "--diagrams-dir", str(tmp_path)])
    assert exc.value.code == 2


def test_main_errors_when_no_pumls(tmp_path: Path) -> None:
    assert main(["--check", "--diagrams-dir", str(tmp_path)]) == 1
