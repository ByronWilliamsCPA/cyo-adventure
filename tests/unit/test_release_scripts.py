"""Unit tests for scripts/promote_changelog.py and extract_changelog_section.py.

scripts/ is not an importable package (no __init__.py, by design; see
per-file-ignores INP for scripts/**/*.py in pyproject.toml), so the modules
are loaded directly from their file paths via importlib.
"""

from __future__ import annotations

import importlib.util
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
