"""Unit tests for ``scripts/verify_release_artifacts.sh``.

The script is the single source of truth for "is this a well-formed release"
shared by ``release.yml``'s ``propose`` and ``publish`` jobs (issue #364). It
runs against a checked-out repo, so each test builds a minimal git repository
in ``tmp_path`` holding a generated-format ``CHANGELOG.md`` and a
``pyproject.toml``, then invokes the script via subprocess.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH"),
]

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "verify_release_artifacts.sh"
)
_VERSION = "1.2.0"
_REPO = "https://github.com/ByronWilliamsCPA/cyo-adventure"

_CHANGELOG = f"""# Changelog

<!-- version list -->

## [{_VERSION}] - 2026-09-05

### Features

- Add a thing

## [0.1.0] - 2026-06-20

- Initial release

[{_VERSION}]: {_REPO}/compare/v0.1.0...v{_VERSION}
[0.1.0]: {_REPO}/releases/tag/v0.1.0
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],  # noqa: S607 - git resolved from PATH on purpose
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    )


def _make_repo(
    tmp_path: Path, *, version: str = _VERSION, changelog: str = _CHANGELOG
) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "chore(release): seed")
    return tmp_path


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_SCRIPT), *args],  # noqa: S607 - bash resolved from PATH
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def test_verify_script_well_formed_release_passes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    result = _run(repo, _VERSION, "--baseline-ref", "HEAD")

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"verified for v{_VERSION}" in result.stdout


def test_verify_script_version_mismatch_fails_with_pyproject_message(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path, version="1.1.9")

    result = _run(repo, _VERSION)

    assert result.returncode == 1
    assert f"pyproject version is '1.1.9', expected '{_VERSION}'" in result.stdout


def test_verify_script_missing_section_heading_fails_non_zero(tmp_path: Path) -> None:
    changelog = _CHANGELOG.replace(f"## [{_VERSION}] - 2026-09-05\n", "")
    repo = _make_repo(tmp_path, changelog=changelog)

    result = _run(repo, _VERSION)

    assert result.returncode == 1
    assert f"no '## [{_VERSION}] - ' section heading" in result.stdout
