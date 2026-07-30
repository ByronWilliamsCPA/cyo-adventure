"""Cross-language pin: the frontend's fallback sentinel pattern equals the backend's.

ADR-023 plan risk R9 is "two rendering implementations drift", and this is the one
place a duplicate of the pattern legitimately exists: a strip with no values
payload has no server-supplied pattern to use, so
`frontend/src/player/personalization.ts` carries a literal fallback. This test is
what makes the duplication safe rather than latent, in the same spirit as the
migration-versus-ORM parity suite and the title-strip registry: the duplicate is
allowed, and something fails loudly when it moves.
"""

from __future__ import annotations

import re
from pathlib import Path

from cyo_adventure.storybook.sentinels import SENTINEL_RE

_RESOLVER = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "player"
    / "personalization.ts"
)

# Matches: export const SENTINEL_PATTERN_FALLBACK = "<double-quoted literal>"
_DECLARATION = re.compile(
    r'export const SENTINEL_PATTERN_FALLBACK = "((?:[^"\\]|\\.)*)"'
)


def test_frontend_fallback_pattern_matches_the_backend_pattern() -> None:
    """The TS literal decodes to exactly `SENTINEL_RE.pattern`."""
    source = _RESOLVER.read_text(encoding="utf-8")
    match = _DECLARATION.search(source)
    assert match is not None, (
        f"SENTINEL_PATTERN_FALLBACK declaration not found in {_RESOLVER}; "
        "if the constant was renamed or re-quoted, update this pin rather than "
        "deleting it"
    )
    # A TS double-quoted string escapes a backslash as `\\`; decode to the
    # regex source the JS engine actually compiles.
    decoded = match.group(1).replace("\\\\", "\\")
    assert decoded == SENTINEL_RE.pattern
