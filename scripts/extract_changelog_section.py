"""Print one released version's section from the hand-curated CHANGELOG.

Used by the release workflow's publish job (.github/workflows/release.yml)
to turn the section promote_changelog.py created into GitHub Release notes.
Prints every line after the ``## [X.Y.Z]`` heading up to (excluding) the
next ``## [`` heading or the trailing link-reference block.

Usage:
    python scripts/extract_changelog_section.py 0.2.0 > release-notes.md
"""

from __future__ import annotations

import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def extract(version: str, changelog: Path = CHANGELOG) -> str:
    """Return the CHANGELOG body for ``version``.

    Args:
        version: The bare semver string (no ``v`` prefix).
        changelog: The changelog file to read (overridable for tests).

    Returns:
        The section body, stripped of leading/trailing blank lines. Empty
        string if the section exists but has no entries.

    Raises:
        SystemExit: If the version heading is not present.
    """
    heading_prefix = f"## [{version}]"
    lines = changelog.read_text(encoding="utf-8").splitlines()

    try:
        start = next(
            i for i, line in enumerate(lines) if line.startswith(heading_prefix)
        )
    except StopIteration:
        msg = f"{changelog.name} has no '{heading_prefix}' section"
        raise SystemExit(msg) from None

    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith(("## [", f"[{version}]:", "[Unreleased]:")):
            break
        body.append(line)
    return "\n".join(body).strip()


def main() -> int:
    """CLI entry point.

    Returns:
        Process exit code.
    """
    if len(sys.argv) != 2:
        print("usage: extract_changelog_section.py <version>", file=sys.stderr)
        return 2
    version = sys.argv[1].lstrip("v")
    section = extract(version)
    if not section:
        section = "_No curated changelog entries for this release._"
    print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
