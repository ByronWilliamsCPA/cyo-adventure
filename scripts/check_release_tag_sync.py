"""Fail when pyproject's version has no matching git tag.

Guards the release workflow's propose job against the deadlock that a failed
publish job leaves behind. The two-phase release flow keeps release state in
two places: the version in ``pyproject.toml`` (written when the release PR
merges) and the git tag (written by the publish job on the next push). A
failure between them desynchronises the pair, and the propose job then reads
the stale pair as "already released".

Concretely, on 2026-08-17 ``gh release create v0.82.0`` hit a transient
``HTTP 503`` and never created the tag. python-semantic-release computes the
next version from the last TAG, so it kept returning 0.82.0 while pyproject
already said 0.82.0. The propose job's ``NEXT == CURRENT`` gate then reported
"No release-worthy commits; nothing to do" and exited SUCCESS on every push
for a week. With ``major_on_zero = false`` no commit of any type could ever
compute past 0.82.0, so the stall was permanent and silent.

The desync is only ever reachable through that failure: in steady state the
version in pyproject always equals the newest tag, and the one legitimate
window where it does not (the ``chore(release):`` commit itself, before publish
tags it) is a push the propose job skips by its own ``if:`` guard.

Usage:
    python scripts/check_release_tag_sync.py            # reads pyproject + git
    python scripts/check_release_tag_sync.py --version 0.82.0
"""

from __future__ import annotations

import argparse
import re

# Only ever invoked with a fixed argv and shell=False; no user input reaches it.
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Mirrors python-semantic-release's default tag_format of "v{version}".
# pyproject.toml's [tool.semantic_release] does not override tag_format.
TAG_PREFIX = "v"

_VERSION_RE = re.compile(r'^version = "([^"]+)"', re.MULTILINE)


def read_pyproject_version(pyproject: Path = PYPROJECT) -> str:
    """Return the ``version`` declared in ``pyproject.toml``.

    Args:
        pyproject: The file to read (overridable for tests).

    Returns:
        The bare semver string, with no ``v`` prefix.

    Raises:
        SystemExit: If no ``version = "..."`` line is present.
    """
    match = _VERSION_RE.search(pyproject.read_text(encoding="utf-8"))
    if match is None:
        msg = f"{pyproject.name} has no 'version = \"...\"' line"
        raise SystemExit(msg)
    return match.group(1)


def git_tags(repo_root: Path = REPO_ROOT) -> list[str]:
    """Return every git tag in the repository.

    The release workflow checks out with ``fetch-depth: 0`` and
    ``fetch-tags: true``, so the full tag set is local by the time this runs.

    Args:
        repo_root: The repository to inspect (overridable for tests).

    Returns:
        Tag names, in git's default order. Empty if the repo has no tags.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_root), "tag", "--list"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def find_desync(version: str, tags: list[str]) -> str | None:
    """Return an error message if ``version`` has no tag, else ``None``.

    Args:
        version: The bare semver string from pyproject.
        tags: Every tag in the repository.

    Returns:
        A human-readable diagnosis, or ``None`` when the pair is in sync.
    """
    # A repo that has never released has a version but legitimately no tags.
    # Reporting a desync there would fail the very first release.
    if not tags:
        return None

    expected = f"{TAG_PREFIX}{version}"
    if expected in tags:
        return None

    return (
        f"pyproject.toml declares version {version} but tag {expected} does not "
        f"exist. The release pipeline is DEADLOCKED: python-semantic-release "
        f"computes the next version from the last tag, so it will keep "
        f"returning {version}, the propose job's NEXT == CURRENT gate will keep "
        f"reporting 'nothing to do', and no release PR can ever open again.\n"
        f"\n"
        f"This means a publish job failed after its release PR merged. Fix it "
        f"by creating the missing release on the 'chore(release): {expected}' "
        f"commit, which unblocks the next push:\n"
        f"    gh run rerun <failed-publish-run-id> --failed\n"
        f"See docs/operations/runbook.md section 7."
    )


def main(argv: list[str] | None = None) -> int:
    """Check pyproject's version against the git tags.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        0 when in sync, 1 when desynchronised.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        help="Version to check (defaults to the one in pyproject.toml)",
    )
    args = parser.parse_args(argv)

    version = args.version or read_pyproject_version()
    tags = git_tags()
    problem = find_desync(version, tags)

    if problem is not None:
        # ::error:: renders as a GitHub Actions annotation on the job summary.
        print(f"::error::{problem}", file=sys.stderr)
        return 1

    if not tags:
        # find_desync deliberately passes a tagless repo so the first release is
        # not blocked. Claiming a tag exists here would be false.
        print(f"No tags yet: pyproject {version} would be the first release.")
        return 0

    print(f"Release state in sync: pyproject {version} has tag {TAG_PREFIX}{version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
