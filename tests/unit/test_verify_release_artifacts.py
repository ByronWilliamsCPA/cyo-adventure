"""Unit tests for ``scripts/verify_release_artifacts.sh``.

The script is the single source of truth for "is this a well-formed release"
shared by ``release.yml``'s ``propose`` and ``publish`` jobs (issue #364). It
runs against a checked-out repo, so each test builds a minimal git repository
in ``tmp_path`` holding a generated-format ``CHANGELOG.md`` and a
``pyproject.toml``, then invokes the script via subprocess.
"""

from __future__ import annotations

import os
import re
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

# GNU-only PCRE spellings, in every form BSD grep on the macOS runner rejects. The first
# alternative matches any short-option cluster containing `P`, which is what `-P`, `-Po`, and
# `-oP` all are: an earlier version anchored on a literal `-P` and therefore missed `-oP` and
# `-qoP`, where `P` is not the first letter in the cluster. The leading lookbehind keeps it from
# firing on an unrelated token that merely ends in a hyphen plus letters, so a date like
# `2026-09-05` and a word like `non-POSIX` are both ignored. A plain `"-P" in line` substring
# test was the first attempt and is too blunt in the other direction: it fires on any prose
# mention of the flag, so documenting why the script avoids `-P` would break this guard.
_GNU_ONLY_GREP_RE = re.compile(r"(?<![\w-])-[A-Za-z]*P[A-Za-z]*|--perl-regexp|\\K")

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


def test_verify_script_uses_no_gnu_only_grep_flags() -> None:
    """The macOS matrix leg runs BSD grep, which rejects PCRE mode.

    ``python-compatibility.yml`` runs this suite on ``macos-latest``. A GNU-only
    pattern flag there makes the extraction return empty and the script report a
    bogus version mismatch, so guard the whole file rather than one call site.
    """
    source = _SCRIPT.read_text(encoding="utf-8")

    offenders = [
        (number, line)
        for number, line in enumerate(source.splitlines(), start=1)
        if _GNU_ONLY_GREP_RE.search(line)
    ]

    assert not offenders, f"GNU-only grep usage reintroduced: {offenders}"


def test_verify_script_section_with_only_a_subheading_fails(tmp_path: Path) -> None:
    """A heading with no entries must fail, not publish an empty release.

    ``### Features`` alone is non-whitespace, so a bare whitespace test passes it.
    """
    changelog = _CHANGELOG.replace("- Add a thing\n", "")
    repo = _make_repo(tmp_path, changelog=changelog)

    result = _run(repo, _VERSION)

    assert result.returncode == 1
    assert f"section '[{_VERSION}]' has a heading but no entries" in result.stdout


def test_verify_script_fails_when_a_prior_version_section_is_dropped(
    tmp_path: Path,
) -> None:
    """Losing prior history must fail even when the file grows.

    The check this replaced compared total line counts, so a rewrite that dropped
    old sections while adding more new lines passed. Keep the replacement honest
    by asserting on a changelog that is strictly longer than its baseline.
    """
    repo = _make_repo(tmp_path)
    padding = "\n".join(f"- padding entry {index}" for index in range(1, 13))
    truncated = f"""# Changelog

<!-- version list -->

## [{_VERSION}] - 2026-09-05

### Features

- Add a thing
{padding}

[{_VERSION}]: {_REPO}/compare/v0.1.0...v{_VERSION}
[0.1.0]: {_REPO}/releases/tag/v0.1.0
"""
    (repo / "CHANGELOG.md").write_text(truncated, encoding="utf-8")
    baseline_lines = len(_CHANGELOG.splitlines())
    assert len(truncated.splitlines()) > baseline_lines, (
        "fixture must be longer than the baseline, or it cannot discriminate "
        "the heading-set check from the line-count check it replaced"
    )

    result = _run(repo, _VERSION, "--baseline-ref", "HEAD")

    assert result.returncode == 1
    assert "lost version section(s)" in result.stdout
    assert "## [0.1.0]" in result.stdout
    assert "shrank from" not in result.stdout


def test_verify_script_missing_compare_link_footer_fails(tmp_path: Path) -> None:
    changelog = _CHANGELOG.replace(
        f"[{_VERSION}]: {_REPO}/compare/v0.1.0...v{_VERSION}\n", ""
    )
    repo = _make_repo(tmp_path, changelog=changelog)

    result = _run(repo, _VERSION)

    assert result.returncode == 1
    assert f"no '[{_VERSION}]: ' compare-link footer" in result.stdout


def test_verify_script_missing_version_list_marker_fails(tmp_path: Path) -> None:
    changelog = _CHANGELOG.replace("<!-- version list -->\n", "")
    repo = _make_repo(tmp_path, changelog=changelog)

    result = _run(repo, _VERSION)

    assert result.returncode == 1
    assert "lost its '<!-- version list -->' insertion marker" in result.stdout


def test_verify_script_missing_history_tail_fails(tmp_path: Path) -> None:
    changelog = _CHANGELOG.replace(f"[0.1.0]: {_REPO}/releases/tag/v0.1.0\n", "")
    repo = _make_repo(tmp_path, changelog=changelog)

    result = _run(repo, _VERSION)

    assert result.returncode == 1
    assert "lost its history tail" in result.stdout


def test_verify_script_missing_pyproject_reports_a_tooling_failure(
    tmp_path: Path,
) -> None:
    """An unreadable pyproject must not masquerade as a version mismatch."""
    repo = _make_repo(tmp_path)
    (repo / "pyproject.toml").unlink()

    result = _run(repo, _VERSION)

    assert result.returncode == 1
    assert "pyproject.toml not found" in result.stdout
    assert "pyproject version is ''" not in result.stdout


def test_gnu_only_grep_detector_catches_every_spelling() -> None:
    """The portability guard must not be narrower than the flag it guards against.

    The first version tested for ``"-P "`` and ``"-Po"`` as substrings, which misses
    ``--perl-regexp`` and a ``-P`` followed by a tab. A guard that misses a spelling
    is worse than no guard, because it reports clean while the macOS leg breaks.
    """
    caught = [
        "ACTUAL=$(grep -Po 'version = \"\\K[^\"]+' pyproject.toml)",
        "grep -P 'pattern' file",
        "grep\t--perl-regexp 'pattern' file",
        "grep -P\t'pattern' file",
        "printf '%s' \"$x\" | grep -oP '\\K.*'",
        "grep -oP 'version = .*' pyproject.toml",
        "grep -qoP 'x' file",
    ]
    for line in caught:
        assert _GNU_ONLY_GREP_RE.search(line), f"missed a GNU-only spelling: {line!r}"

    ignored = [
        "awk -F'\"' '/^version = \"/ { print $2; exit }' pyproject.toml",
        "grep -qE '^[[:space:]]*[-*+] [^[:space:]]'",
        'grep -qFx "${heading}" CHANGELOG.md',
        "# BSD grep implements no PCRE mode, so keep every pattern POSIX.",
        "## [0.88.0] - 2026-09-05",
        "# A non-POSIX extension would break the macOS leg.",
    ]
    for line in ignored:
        assert not _GNU_ONLY_GREP_RE.search(line), f"false positive on: {line!r}"


def test_verify_script_rejects_a_nested_occurrence_of_a_removed_heading(
    tmp_path: Path,
) -> None:
    """A dropped release section is not excused by the heading appearing in prose.

    The substring form of this check (``grep -qF``) accepted any occurrence of the
    heading text anywhere in the file, so a changelog that deleted the real
    ``## [0.1.0]`` section but quoted it inside a deeper heading passed. The fixture
    below is built so the old form would have matched, which is what makes this test
    discriminating rather than merely another dropped-section case.
    """
    repo = _make_repo(tmp_path)
    padding = "\n".join(f"- padding entry {index}" for index in range(1, 13))
    nested = f"""# Changelog

<!-- version list -->

## [{_VERSION}] - 2026-09-05

### Features

- Add a thing

### ## [0.1.0] - 2026-06-20

- This heading is quoted inside a level-three heading, not a real release section.
{padding}

[{_VERSION}]: {_REPO}/compare/v0.1.0...v{_VERSION}
[0.1.0]: {_REPO}/releases/tag/v0.1.0
"""
    (repo / "CHANGELOG.md").write_text(nested, encoding="utf-8")

    assert "## [0.1.0] - 2026-06-20" in nested, (
        "fixture must contain the heading as a substring, or it cannot show that "
        "the substring form of this check would have passed"
    )
    assert len(nested.splitlines()) > len(_CHANGELOG.splitlines()), (
        "fixture must be longer than the baseline so the line-count check cannot fire"
    )

    result = _run(repo, _VERSION, "--baseline-ref", "HEAD")

    assert result.returncode == 1
    assert "lost version section(s)" in result.stdout
    assert "## [0.1.0]" in result.stdout
    assert "shrank from" not in result.stdout
