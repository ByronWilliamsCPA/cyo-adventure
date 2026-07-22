"""Inject a Keep-a-Changelog compare-link footer for a freshly released version.

python-semantic-release renders the ``## [X.Y.Z] - DATE`` section heading (via
the patched templates in ``templates/``) but does not emit the trailing
reference-style compare link (``[X.Y.Z]: .../compare/vPREV...vX.Y.Z``) that
makes the bracketed heading resolve as a hyperlink. This script adds that one
footer line so a generated version renders like every hand-curated entry that
preceded the migration.

Used by the release workflow's propose job (.github/workflows/release.yml),
run immediately after ``semantic-release version`` writes the changelog.

The compare-URL base is derived from an existing footer link rather than
hardcoded, so the repository can be renamed or forked without editing this
script. The new link is inserted as the first (newest) footer entry, matching
the newest-first ordering of the block.

Idempotent: if the version's footer link already exists, the file is untouched.

Usage:
    uv run python scripts/inject_changelog_footer_link.py 0.28.0 0.27.0
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

# A reference-style footer link: '[0.27.0]: https://host/owner/repo/compare/...'
# or the first-release '[0.1.0]: https://host/owner/repo/releases/tag/v0.1.0'.
# The base group captures everything up to (excluding) '/compare' or
# '/releases', i.e. the repository URL.
_FOOTER_LINK_RE = re.compile(
    r"^\[(?P<version>[^\]]+)\]: "
    r"(?P<base>https://\S+?)/(?:compare|releases/tag)/\S+$",
    re.MULTILINE,
)


def _footer_link_re(version: str) -> re.Pattern[str]:
    """Return a line-anchored matcher for this version's footer link."""
    return re.compile(rf"^\[{re.escape(version)}\]: ", re.MULTILINE)


def inject(version: str, prev: str, changelog: Path = CHANGELOG) -> bool:
    """Insert the compare-link footer for ``version`` into ``changelog``.

    Args:
        version: The bare semver string just released (no ``v`` prefix).
        prev: The previous released version, used as the compare base.
        changelog: The changelog file to rewrite (overridable for tests).

    Returns:
        True if the file was modified, False if the footer link already
        existed (idempotent no-op).

    Raises:
        SystemExit: If no existing footer link is present to derive the
            repository compare-URL base from.
    """
    text = changelog.read_text(encoding="utf-8")

    # #ASSUME data-integrity: one footer link per line, newest first, at the
    # bottom of the file. #VERIFY match line-anchored so a bracketed version
    # inside a prose entry cannot be mistaken for a footer link.
    if _footer_link_re(version).search(text):
        return False

    first_link = _FOOTER_LINK_RE.search(text)
    if first_link is None:
        msg = (
            f"{changelog.name} has no existing '[X.Y.Z]: .../compare/...' footer "
            "link to derive the repository URL from"
        )
        raise SystemExit(msg)

    base = first_link.group("base")
    new_link = f"[{version}]: {base}/compare/v{prev}...v{version}"

    # Insert as the first (newest) footer entry, directly above the current
    # highest link. String slicing keeps everything else byte-for-byte intact.
    insert_at = first_link.start()
    text = f"{text[:insert_at]}{new_link}\n{text[insert_at:]}"

    changelog.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    """CLI entry point.

    Returns:
        Process exit code (0 on success, including the idempotent no-op).
    """
    if len(sys.argv) != 3:  # script name + two positional args
        print(
            "usage: inject_changelog_footer_link.py <version> <prev-version>",
            file=sys.stderr,
        )
        return 2
    version = sys.argv[1].lstrip("v")
    prev = sys.argv[2].lstrip("v")
    if inject(version, prev):
        print(f"CHANGELOG.md: inserted compare-link footer for [{version}]")
    else:
        print(f"CHANGELOG.md: [{version}] footer link already present; nothing to do")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
