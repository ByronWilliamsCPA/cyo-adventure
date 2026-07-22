"""Unit tests for the release helper scripts.

Covers scripts/extract_changelog_section.py (turns a released section into
GitHub Release notes) and scripts/inject_changelog_footer_link.py (adds the
Keep-a-Changelog compare-link footer that python-semantic-release omits).

CHANGELOG.md is GENERATED at release time by python-semantic-release
(mode="update" splices each version in at the ``<!-- version list -->``
insertion flag). These scripts run against that generated file, so the
fixtures below model the generated format: no ``[Unreleased]`` section, an
insertion marker, already-versioned headings, and a newest-first compare-link
footer.

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


extract_changelog_section = _load("extract_changelog_section")
inject_changelog_footer_link = _load("inject_changelog_footer_link")

pytestmark = pytest.mark.unit

_REPO = "https://github.com/ByronWilliamsCPA/cyo-adventure"

# A generated-format changelog: insertion marker, versioned sections newest
# first, compare-link footer newest first. This is what PSR's mode="update"
# leaves on disk after a release.
_SAMPLE = f"""# Changelog

All notable changes to this project will be documented in this file.

<!-- version list -->

## [0.2.0] - 2026-01-02

### Added

- A new thing.

### Fixed

- A bug.

## [0.1.0] - 2026-01-01

### Added

- Initial release.

[0.2.0]: {_REPO}/compare/v0.1.0...v0.2.0
[0.1.0]: {_REPO}/releases/tag/v0.1.0
"""


@pytest.fixture
def changelog(tmp_path: Path) -> Path:
    """Write the sample changelog to a temp file and return its path."""
    path = tmp_path / "CHANGELOG.md"
    path.write_text(_SAMPLE, encoding="utf-8")
    return path


class TestExtract:
    """extract_changelog_section.extract behavior."""

    def test_extracts_latest_released_section(self, changelog: Path) -> None:
        """Extraction returns exactly the newest version's entries."""
        section = extract_changelog_section.extract("0.2.0", changelog)
        assert "A new thing." in section
        assert "A bug." in section
        # The older release is bounded out.
        assert "Initial release." not in section

    def test_extracts_older_released_section(self, changelog: Path) -> None:
        """Extraction works for a section below the newest one."""
        section = extract_changelog_section.extract("0.1.0", changelog)
        assert "Initial release." in section
        assert "A new thing." not in section

    def test_latest_section_excludes_footer_links(self, changelog: Path) -> None:
        """The newest section (the one published) omits the compare-link block.

        The publish job only ever extracts the just-released (newest) version,
        whose scan stops at the next '## [' heading before any footer link.
        """
        section = extract_changelog_section.extract("0.2.0", changelog)
        assert f"[0.2.0]: {_REPO}" not in section
        assert "compare/" not in section

    def test_unknown_version_exits(self, changelog: Path) -> None:
        """Asking for a version that is not in the changelog is a hard error."""
        with pytest.raises(SystemExit):
            extract_changelog_section.extract("9.9.9", changelog)

    def test_fenced_pseudo_heading_does_not_truncate(self, tmp_path: Path) -> None:
        """A '## [' line inside a fenced code block is not a section boundary."""
        text = (
            "# Changelog\n\n"
            "<!-- version list -->\n\n"
            "## [0.2.0] - 2026-01-01\n\n"
            "### Added\n"
            "- Documented the changelog format:\n\n"
            "```\n"
            "## [Example] - not a real heading\n"
            "```\n\n"
            "- A trailing entry after the fence.\n\n"
            "## [0.1.0] - 2025-01-01\n\n"
            "### Added\n- Initial release.\n\n"
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


class TestInjectFooter:
    """inject_changelog_footer_link.inject behavior."""

    def test_inserts_link_newest_first(self, changelog: Path) -> None:
        """The new compare link lands above the current highest footer link."""
        assert inject_changelog_footer_link.inject("0.3.0", "0.2.0", changelog) is True
        text = changelog.read_text(encoding="utf-8")
        assert f"[0.3.0]: {_REPO}/compare/v0.2.0...v0.3.0" in text
        # Newest first: the new link precedes the previously-highest one.
        assert text.index("[0.3.0]:") < text.index("[0.2.0]:")

    def test_derives_base_from_existing_link(self, tmp_path: Path) -> None:
        """The compare-URL base is taken from an existing link, not hardcoded."""
        other = "https://example.test/team/app"
        text = (
            "# Changelog\n\n<!-- version list -->\n\n"
            "## [1.0.0] - 2026-01-01\n\n### Added\n- Thing.\n\n"
            f"[1.0.0]: {other}/releases/tag/v1.0.0\n"
        )
        path = tmp_path / "CHANGELOG.md"
        path.write_text(text, encoding="utf-8")
        assert inject_changelog_footer_link.inject("1.1.0", "1.0.0", path) is True
        assert f"[1.1.0]: {other}/compare/v1.0.0...v1.1.0" in path.read_text(
            encoding="utf-8"
        )

    def test_idempotent_when_link_exists(self, changelog: Path) -> None:
        """A second run for the same version changes nothing."""
        inject_changelog_footer_link.inject("0.3.0", "0.2.0", changelog)
        first = changelog.read_text(encoding="utf-8")
        assert inject_changelog_footer_link.inject("0.3.0", "0.2.0", changelog) is False
        assert changelog.read_text(encoding="utf-8") == first

    def test_missing_footer_links_exits(self, tmp_path: Path) -> None:
        """A changelog with no footer link to derive the base from is an error."""
        path = tmp_path / "CHANGELOG.md"
        path.write_text(
            "# Changelog\n\n<!-- version list -->\n\n## [0.1.0] - 2026-01-01\n",
            encoding="utf-8",
        )
        with pytest.raises(SystemExit):
            inject_changelog_footer_link.inject("0.2.0", "0.1.0", path)

    def test_line_anchored_not_prose(self, tmp_path: Path) -> None:
        """A bracketed version inside prose is not mistaken for a footer link."""
        text = (
            "# Changelog\n\n<!-- version list -->\n\n"
            "## [0.2.0] - 2026-01-02\n\n"
            "### Fixed\n- Referenced [0.3.0] in a note, not yet released.\n\n"
            "## [0.1.0] - 2026-01-01\n\n### Added\n- Initial release.\n\n"
            f"[0.2.0]: {_REPO}/compare/v0.1.0...v0.2.0\n"
            f"[0.1.0]: {_REPO}/releases/tag/v0.1.0\n"
        )
        path = tmp_path / "CHANGELOG.md"
        path.write_text(text, encoding="utf-8")
        # The prose "[0.3.0]" must not count as an existing footer link.
        assert inject_changelog_footer_link.inject("0.3.0", "0.2.0", path) is True
        result = path.read_text(encoding="utf-8")
        assert f"[0.3.0]: {_REPO}/compare/v0.2.0...v0.3.0" in result
        # The prose sentence is untouched.
        assert "Referenced [0.3.0] in a note, not yet released." in result


class TestInjectFooterCLI:
    """inject_changelog_footer_link.main argument handling and dispatch."""

    def test_usage_error_on_wrong_argc(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Fewer than two positional args returns exit code 2 with a usage line."""
        monkeypatch.setattr(sys, "argv", ["inject_changelog_footer_link.py", "0.2.0"])
        assert inject_changelog_footer_link.main() == 2
        assert "usage:" in capsys.readouterr().err

    def test_strips_v_prefix_on_both_args(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """'vX.Y.Z' arguments are normalized before inject() is called."""
        seen: dict[str, str] = {}

        def _spy(version: str, prev: str) -> bool:
            seen["version"] = version
            seen["prev"] = prev
            return True

        monkeypatch.setattr(inject_changelog_footer_link, "inject", _spy)
        monkeypatch.setattr(
            sys, "argv", ["inject_changelog_footer_link.py", "v0.3.0", "v0.2.0"]
        )
        assert inject_changelog_footer_link.main() == 0
        assert seen == {"version": "0.3.0", "prev": "0.2.0"}
        assert "inserted compare-link footer" in capsys.readouterr().out

    def test_idempotent_no_op_is_reported(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When inject() returns False, main reports the no-op and exits 0."""

        def _noop(_version: str, _prev: str) -> bool:
            return False

        monkeypatch.setattr(inject_changelog_footer_link, "inject", _noop)
        monkeypatch.setattr(
            sys, "argv", ["inject_changelog_footer_link.py", "0.3.0", "0.2.0"]
        )
        assert inject_changelog_footer_link.main() == 0
        assert "already present" in capsys.readouterr().out


class TestRealChangelog:
    """Smoke tests against the repository's actual CHANGELOG.md.

    The synthetic fixtures above never exercise the ~2500-line file that is the
    scripts' only real consumer; these tests catch generated-format drift the
    scripts could not otherwise detect until a live release run.
    """

    _REAL = Path(__file__).resolve().parents[2] / "CHANGELOG.md"

    def _latest_version(self) -> str:
        """Return the newest '## [X.Y.Z]' version string in the real file."""
        for line in self._REAL.read_text(encoding="utf-8").splitlines():
            if line.startswith("## ["):
                # '## [0.27.0] - 2026-07-22' -> '0.27.0'
                return line.split("[", 1)[1].split("]", 1)[0]
        pytest.fail("real CHANGELOG has no '## [X.Y.Z]' heading")

    def test_real_changelog_has_generated_format(self) -> None:
        """The real file carries the markers both scripts rely on."""
        text = self._REAL.read_text(encoding="utf-8")
        # Exactly one insertion marker for PSR's mode="update" splice.
        assert text.count("<!-- version list -->") == 1
        # At least one compare-link footer for inject to derive the base from.
        assert inject_changelog_footer_link._FOOTER_LINK_RE.search(text) is not None
        # No hand-curated Unreleased section survives the migration.
        assert "\n## [Unreleased]\n" not in text

    def test_real_changelog_extracts_bounded_latest_section(self) -> None:
        """Extracting the newest real section yields a bounded body."""
        section = extract_changelog_section.extract(self._latest_version(), self._REAL)
        lines = section.splitlines()
        # No later release heading or trailing link-block line leaked in.
        assert not any(line.startswith("## [") for line in lines)
        assert not any(line.startswith("[") and "]: http" in line for line in lines)

    def test_inject_on_real_changelog_is_bounded_and_idempotent(
        self, tmp_path: Path
    ) -> None:
        """Injecting a footer link on a copy of the real file is safe."""
        copied = tmp_path / "CHANGELOG.md"
        copied.write_text(self._REAL.read_text(encoding="utf-8"), encoding="utf-8")
        latest = self._latest_version()

        assert inject_changelog_footer_link.inject("99.0.0", latest, copied) is True
        text = copied.read_text(encoding="utf-8")
        assert "[99.0.0]: " in text
        # Newest first: inserted above the previously-latest footer link.
        assert text.index("[99.0.0]:") < text.index(f"[{latest}]:")
        # Idempotent on a second run.
        assert inject_changelog_footer_link.inject("99.0.0", latest, copied) is False
