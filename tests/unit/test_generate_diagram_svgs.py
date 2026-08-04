"""Unit tests for the top-level architecture-diagram SVG generator.

Covers the pure helpers (``_is_renderable``, ``top_level_pumls``, ``is_stale``,
``find_duplicate_svgs``) and the ``main`` CLI in both modes: ``--check``, which
needs no PlantUML jar, and the render branch, where ``resolve_jar`` and
``render_svgs`` are patched so no jar is downloaded and no subprocess runs.
Git-backed staleness is exercised by monkeypatching ``_git_commit_time`` so the
tests stay hermetic and fast.
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
    args = ["--check", "--all", "--diagrams-dir", str(tmp_path)]
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2


def test_main_errors_when_no_pumls(tmp_path: Path) -> None:
    assert main(["--check", "--diagrams-dir", str(tmp_path)]) == 1


# --- main render branch ----------------------------------------------------
#
# ``render_svgs`` and ``resolve_jar`` are patched on the ``gds`` module rather
# than at their definition site: the tool imports them by name at module load,
# so its module globals are the only binding ``main`` actually reads. Patching
# ``scripts.render_skeleton_diagrams`` would leave the tool's copies untouched
# and the test would silently shell out to a real PlantUML jar.


def _jar(tmp_path: Path) -> Path:
    """Return a stand-in jar path; it is never executed, only truthiness-checked."""
    return tmp_path / "plantuml.jar"


def test_main_render_fails_when_jar_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _puml(tmp_path, "a")
    monkeypatch.setattr(gds, "is_stale", lambda _p: True)
    monkeypatch.setattr(gds, "resolve_jar", lambda: None)
    assert main(["--diagrams-dir", str(tmp_path)]) == 1


def test_main_render_succeeds_when_every_target_rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _puml(tmp_path, "a")
    _svg(a, b"<svg>a</svg>")
    monkeypatch.setattr(gds, "is_stale", lambda _p: True)
    monkeypatch.setattr(gds, "resolve_jar", lambda: _jar(tmp_path))

    def _render(
        puml_paths: list[Path], *, jar: Path | None
    ) -> tuple[list[Path], list[Path]]:
        assert jar is not None
        return [p.with_suffix(".svg") for p in puml_paths], []

    monkeypatch.setattr(gds, "render_svgs", _render)
    assert main(["--diagrams-dir", str(tmp_path)]) == 0


def test_main_render_fails_and_names_the_file_on_corrupt_svg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    a = _puml(tmp_path, "a")
    # PlantUML wrote an error card: the SVG exists, so it is not "missing".
    svg = _svg(a, b"<svg>error card</svg>")
    monkeypatch.setattr(gds, "is_stale", lambda _p: True)
    monkeypatch.setattr(gds, "resolve_jar", lambda: _jar(tmp_path))

    def _render(
        puml_paths: list[Path], *, jar: Path | None
    ) -> tuple[list[Path], list[Path]]:
        assert jar is not None
        return [], [p.with_suffix(".svg") for p in puml_paths]

    monkeypatch.setattr(gds, "render_svgs", _render)

    assert main(["--diagrams-dir", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "corrupt SVG" in err
    assert svg.name in err
    # The bad file is on disk and newer than its source, so it would sail
    # through a later --check. "did not render" names the wrong remedy.
    assert "did not render" not in err


def test_main_render_reports_unrendered_targets_separately_from_corrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    a = _puml(tmp_path, "a")
    _puml(tmp_path, "b")
    _svg(a, b"<svg>a</svg>")
    monkeypatch.setattr(gds, "is_stale", lambda _p: True)
    monkeypatch.setattr(gds, "resolve_jar", lambda: _jar(tmp_path))

    def _render(
        puml_paths: list[Path], *, jar: Path | None
    ) -> tuple[list[Path], list[Path]]:
        assert jar is not None
        # b hard-failed: no output was written at all, and nothing is corrupt.
        return [puml_paths[0].with_suffix(".svg")], []

    monkeypatch.setattr(gds, "render_svgs", _render)

    assert main(["--diagrams-dir", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "did not render" in err
    assert "corrupt SVG" not in err


def test_main_all_renders_every_diagram_even_when_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _puml(tmp_path, "a")
    b = _puml(tmp_path, "b")
    _svg(a, b"<svg>a</svg>")
    _svg(b, b"<svg>b</svg>")
    monkeypatch.setattr(gds, "is_stale", lambda _p: False)
    monkeypatch.setattr(gds, "resolve_jar", lambda: _jar(tmp_path))
    seen: list[list[Path]] = []

    def _render(
        puml_paths: list[Path], *, jar: Path | None
    ) -> tuple[list[Path], list[Path]]:
        assert jar is not None
        seen.append(list(puml_paths))
        return [p.with_suffix(".svg") for p in puml_paths], []

    monkeypatch.setattr(gds, "render_svgs", _render)

    assert main(["--all", "--diagrams-dir", str(tmp_path)]) == 0
    assert seen == [[a, b]]
