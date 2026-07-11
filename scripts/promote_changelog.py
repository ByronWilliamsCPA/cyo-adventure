"""Promote the CHANGELOG's [Unreleased] section to a released version.

Used by the release workflow's propose job (.github/workflows/release.yml).
CHANGELOG.md is hand-curated (Keep a Changelog): every PR appends entries
under ``## [Unreleased]``. At release time this script:

1. Inserts a ``## [X.Y.Z] - YYYY-MM-DD`` heading directly below the
   ``## [Unreleased]`` heading, so the accumulated entries fall under the
   new version and a fresh, empty Unreleased section remains on top.
2. Rewrites the ``[Unreleased]:`` compare link to diff against the new tag
   and inserts a compare link for the new version.

Idempotent: if the version heading already exists, the file is untouched.

Usage:
    uv run python scripts/promote_changelog.py 0.2.0
"""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
UNRELEASED_HEADING = "## [Unreleased]"
UNRELEASED_LINK_RE = re.compile(
    r"^\[Unreleased\]: (?P<base>https://\S+?)/compare/v(?P<prev>\S+?)\.\.\.HEAD$",
    re.MULTILINE,
)


def promote(version: str, changelog: Path = CHANGELOG) -> bool:
    """Promote the Unreleased section to ``version``.

    Args:
        version: The bare semver string being released (no ``v`` prefix).
        changelog: The changelog file to rewrite (overridable for tests).

    Returns:
        True if the file was modified, False if the version heading already
        existed (idempotent no-op).

    Raises:
        SystemExit: If the changelog lacks the Unreleased heading or link.
    """
    text = changelog.read_text(encoding="utf-8")

    if f"## [{version}]" in text:
        return False

    if UNRELEASED_HEADING not in text:
        msg = f"{changelog.name} has no '{UNRELEASED_HEADING}' heading"
        raise SystemExit(msg)

    link_match = UNRELEASED_LINK_RE.search(text)
    if link_match is None:
        msg = f"{changelog.name} has no '[Unreleased]: .../compare/vX.Y.Z...HEAD' link"
        raise SystemExit(msg)

    today = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    text = text.replace(
        UNRELEASED_HEADING,
        f"{UNRELEASED_HEADING}\n\n## [{version}] - {today}",
        1,
    )

    base = link_match.group("base")
    prev = link_match.group("prev")
    new_links = "\n".join(
        [
            f"[Unreleased]: {base}/compare/v{version}...HEAD",
            f"[{version}]: {base}/compare/v{prev}...v{version}",
        ]
    )
    text = UNRELEASED_LINK_RE.sub(new_links, text, count=1)

    changelog.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    """CLI entry point.

    Returns:
        Process exit code (0 on success, including the idempotent no-op).
    """
    if len(sys.argv) != 2:
        print("usage: promote_changelog.py <version>", file=sys.stderr)
        return 2
    version = sys.argv[1].lstrip("v")
    if promote(version):
        print(f"CHANGELOG.md: promoted [Unreleased] to [{version}]")
    else:
        print(f"CHANGELOG.md: [{version}] already present; nothing to do")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
