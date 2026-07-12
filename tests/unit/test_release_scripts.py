"""Unit tests for scripts/promote_changelog.py and extract_changelog_section.py.

scripts/ is not an importable package (no __init__.py, by design; see
per-file-ignores INP for scripts/**/*.py in pyproject.toml), so the modules
are loaded directly from their file paths via importlib.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

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


promote_changelog = _load("promote_changelog")
extract_changelog_section = _load("extract_changelog_section")

pytestmark = pytest.mark.unit

_REPO = "https://github.com/ByronWilliamsCPA/cyo-adventure"

_SAMPLE = f"""# Changelog

All notable changes.

## [Unreleased]

### Added
- A new thing.

### Fixed
- A bug.

## [0.1.0] - TBD

### Added
- Initial release.

[Unreleased]: {_REPO}/compare/v0.1.0...HEAD
[0.1.0]: {_REPO}/releases/tag/v0.1.0
"""


@pytest.fixture
def changelog(tmp_path: Path) -> Path:
    """Write the sample changelog to a temp file and return its path."""
    path = tmp_path / "CHANGELOG.md"
    path.write_text(_SAMPLE, encoding="utf-8")
    return path


class TestPromote:
    """promote_changelog.promote behavior."""

    def test_inserts_version_heading_under_unreleased(self, changelog: Path) -> None:
        """The new version heading lands directly below [Unreleased]."""
        assert promote_changelog.promote("0.2.0", changelog) is True
        text = changelog.read_text(encoding="utf-8")
        unreleased_idx = text.index("## [Unreleased]")
        version_idx = text.index("## [0.2.0] - ")
        added_idx = text.index("### Added")
        assert unreleased_idx < version_idx < added_idx

    def test_updates_link_references(self, changelog: Path) -> None:
        """[Unreleased] compares against the new tag; new compare link added."""
        promote_changelog.promote("0.2.0", changelog)
        text = changelog.read_text(encoding="utf-8")
        assert f"[Unreleased]: {_REPO}/compare/v0.2.0...HEAD" in text
        assert f"[0.2.0]: {_REPO}/compare/v0.1.0...v0.2.0" in text

    def test_idempotent_when_version_exists(self, changelog: Path) -> None:
        """A second run with the same version changes nothing."""
        promote_changelog.promote("0.2.0", changelog)
        first = changelog.read_text(encoding="utf-8")
        assert promote_changelog.promote("0.2.0", changelog) is False
        assert changelog.read_text(encoding="utf-8") == first

    def test_missing_unreleased_heading_exits(self, tmp_path: Path) -> None:
        """A changelog without [Unreleased] is a hard error."""
        path = tmp_path / "CHANGELOG.md"
        path.write_text("# Changelog\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            promote_changelog.promote("0.2.0", path)

    def test_missing_unreleased_link_exits(self, tmp_path: Path) -> None:
        """A changelog without the [Unreleased]: compare link is a hard error."""
        path = tmp_path / "CHANGELOG.md"
        path.write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            promote_changelog.promote("0.2.0", path)

    def test_insertion_is_line_anchored_not_prose(self, tmp_path: Path) -> None:
        """A bare '## [Unreleased]' in prose does not misplace the insertion."""
        text = (
            "# Changelog\n\n"
            "This project keeps a ## [Unreleased] section, described here.\n\n"
            "## [Unreleased]\n\n"
            "### Added\n- A new thing.\n\n"
            "## [0.1.0] - TBD\n\n### Added\n- Initial release.\n\n"
            f"[Unreleased]: {_REPO}/compare/v0.1.0...HEAD\n"
            f"[0.1.0]: {_REPO}/releases/tag/v0.1.0\n"
        )
        path = tmp_path / "CHANGELOG.md"
        path.write_text(text, encoding="utf-8")

        assert promote_changelog.promote("0.2.0", path) is True
        result = path.read_text(encoding="utf-8")

        # The version heading lands under the real heading line, not the prose
        # mention (an unanchored replace would insert it into the prose line).
        real_heading_idx = result.index("\n## [Unreleased]\n")
        version_idx = result.index("## [0.2.0] - ")
        assert real_heading_idx < version_idx
        assert result.count("## [0.2.0] - ") == 1
        # The prose sentence is untouched.
        assert "keeps a ## [Unreleased] section, described here." in result


class TestExtract:
    """extract_changelog_section.extract behavior."""

    def test_extracts_promoted_section(self, changelog: Path) -> None:
        """After promotion, extraction returns exactly the released entries."""
        promote_changelog.promote("0.2.0", changelog)
        section = extract_changelog_section.extract("0.2.0", changelog)
        assert "A new thing." in section
        assert "A bug." in section
        assert "Initial release." not in section
        assert "[Unreleased]" not in section

    def test_fresh_unreleased_section_is_empty_after_promotion(
        self, changelog: Path
    ) -> None:
        """Promotion leaves an empty [Unreleased] section on top."""
        promote_changelog.promote("0.2.0", changelog)
        text = changelog.read_text(encoding="utf-8")
        between = text.split("## [Unreleased]")[1].split("## [0.2.0]")[0]
        assert between.strip() == ""

    def test_existing_version_section(self, changelog: Path) -> None:
        """Extraction works for already-released sections."""
        section = extract_changelog_section.extract("0.1.0", changelog)
        assert "Initial release." in section
        assert "A new thing." not in section

    def test_unknown_version_exits(self, changelog: Path) -> None:
        """Asking for a version that is not in the changelog is a hard error."""
        with pytest.raises(SystemExit):
            extract_changelog_section.extract("9.9.9", changelog)

    def test_fenced_pseudo_heading_does_not_truncate(self, tmp_path: Path) -> None:
        """A '## [' line inside a fenced code block is not a section boundary."""
        text = (
            "# Changelog\n\n"
            "## [Unreleased]\n\n"
            "## [0.2.0] - 2026-01-01\n\n"
            "### Added\n"
            "- Documented the changelog format:\n\n"
            "```\n"
            "## [Example] - not a real heading\n"
            "```\n\n"
            "- A trailing entry after the fence.\n\n"
            "## [0.1.0] - 2025-01-01\n\n"
            "### Added\n- Initial release.\n\n"
            f"[Unreleased]: {_REPO}/compare/v0.2.0...HEAD\n"
            f"[0.2.0]: {_REPO}/compare/v0.1.0...v0.2.0\n"
            f"[0.1.0]: {_REPO}/releases/tag/v0.1.0\n"
        )
        path = tmp_path / "CHANGELOG.md"
        path.write_text(text, encoding="utf-8")

        section = extract_changelog_section.extract("0.2.0", path)
        # The fenced pseudo-heading and the entry after it are both retained.
        assert "## [Example] - not a real heading" in section
        assert "A trailing entry after the fence." in section
        # The genuine next release section is still excluded.
        assert "Initial release." not in section


class TestPromoteCLI:
    """promote_changelog.main argument handling and dispatch."""

    def test_usage_error_on_wrong_argc(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A missing version argument returns exit code 2 with a usage line."""
        monkeypatch.setattr(sys, "argv", ["promote_changelog.py"])
        assert promote_changelog.main() == 2
        assert "usage:" in capsys.readouterr().err

    def test_strips_v_prefix_and_reports_promotion(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A 'vX.Y.Z' argument is normalized before promote() is called."""
        seen: dict[str, str] = {}

        def _spy(version: str) -> bool:
            seen["version"] = version
            return True

        monkeypatch.setattr(promote_changelog, "promote", _spy)
        monkeypatch.setattr(sys, "argv", ["promote_changelog.py", "v0.2.0"])
        assert promote_changelog.main() == 0
        assert seen["version"] == "0.2.0"
        assert "promoted" in capsys.readouterr().out

    def test_idempotent_no_op_is_reported(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When promote() returns False, main reports the no-op and exits 0."""

        def _noop(_version: str) -> bool:
            return False

        monkeypatch.setattr(promote_changelog, "promote", _noop)
        monkeypatch.setattr(sys, "argv", ["promote_changelog.py", "0.2.0"])
        assert promote_changelog.main() == 0
        assert "already present" in capsys.readouterr().out


class TestExtractCLI:
    """extract_changelog_section.main argument handling and output."""

    def test_usage_error_on_wrong_argc(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A missing version argument returns exit code 2 with a usage line."""
        monkeypatch.setattr(sys, "argv", ["extract_changelog_section.py"])
        assert extract_changelog_section.main() == 2
        assert "usage:" in capsys.readouterr().err

    def test_prints_section_body(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A non-empty section is printed verbatim."""

        def _body(_version: str) -> str:
            return "- A bug."

        monkeypatch.setattr(extract_changelog_section, "extract", _body)
        monkeypatch.setattr(sys, "argv", ["extract_changelog_section.py", "0.2.0"])
        assert extract_changelog_section.main() == 0
        assert "- A bug." in capsys.readouterr().out

    def test_empty_section_substitutes_placeholder(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An empty section prints the no-entries placeholder, never nothing."""

        def _empty(_version: str) -> str:
            return ""

        monkeypatch.setattr(extract_changelog_section, "extract", _empty)
        monkeypatch.setattr(sys, "argv", ["extract_changelog_section.py", "0.2.0"])
        assert extract_changelog_section.main() == 0
        assert "_No curated changelog entries" in capsys.readouterr().out


class TestRealChangelog:
    """Smoke tests against the repository's actual CHANGELOG.md.

    The synthetic fixtures above never exercise the ~1300-line file that is the
    scripts' only real consumer; these tests catch format drift the scripts
    could not otherwise detect until a live release run.
    """

    _REAL = Path(__file__).resolve().parents[2] / "CHANGELOG.md"

    def test_real_changelog_promotes_and_extracts_bounded_section(
        self, tmp_path: Path
    ) -> None:
        """Promoting then extracting the real file yields a bounded section."""
        copied = tmp_path / "CHANGELOG.md"
        copied.write_text(self._REAL.read_text(encoding="utf-8"), encoding="utf-8")

        assert promote_changelog.promote("9.9.9", copied) is True
        section = extract_changelog_section.extract("9.9.9", copied)

        # Non-empty: the real Unreleased section currently carries entries.
        assert section
        # Bounded: no later release heading line or trailing link-block line
        # leaked in. Checked line-anchored (a '## [' may appear inline in an
        # entry's prose without being a section boundary).
        lines = section.splitlines()
        assert not any(line.startswith("## [") for line in lines)
        assert not any(line.startswith("[Unreleased]:") for line in lines)
        assert not any(line.startswith("[9.9.9]:") for line in lines)

    def test_real_changelog_parses_cleanly_under_both_scripts(self) -> None:
        """The real CHANGELOG satisfies the structure both scripts require."""
        text = self._REAL.read_text(encoding="utf-8")
        # Exactly one bare '## [Unreleased]' heading line for promote to anchor.
        assert text.count("\n## [Unreleased]\n") == 1
        # The [Unreleased] compare link promote rewrites is present.
        assert promote_changelog.UNRELEASED_LINK_RE.search(text) is not None
