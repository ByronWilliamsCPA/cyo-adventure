"""Pin the hand-duplicated frontend catalogs to their backend sources of truth.

The frontend API adapter is hand-typed (no generated client is committed), so
two closed vocabularies are duplicated across the boundary: the six-band
``AGE_BANDS`` array mirrors ``AgeBand`` and the illustrated avatar catalog
mirrors ``AvatarId``. These tests fail loudly when either side drifts, which
is the only automated sync signal the hand-typed contract has.
"""

from __future__ import annotations

import re
import typing
from pathlib import Path

from cyo_adventure.api.schemas import AvatarId
from cyo_adventure.storybook.models import AgeBand

_FRONTEND = Path(__file__).parents[2] / "frontend" / "src" / "profiles"


def _quoted_strings(source: str) -> list[str]:
    """Extract single- or double-quoted string literals from a TS snippet.

    Args:
        source: The TypeScript source fragment to scan.

    Returns:
        list[str]: The quoted literals in source order.
    """
    return re.findall(r"['\"]([^'\"]+)['\"]", source)


def test_frontend_age_bands_match_backend_enum() -> None:
    """profilesApi.ts AGE_BANDS must equal the AgeBand vocabulary, in order."""
    source = (_FRONTEND / "profilesApi.ts").read_text(encoding="utf-8")
    match = re.search(r"AGE_BANDS\s*=\s*\[([^\]]*)\]", source)
    assert match is not None, "AGE_BANDS array not found in profilesApi.ts"
    frontend_bands = _quoted_strings(match.group(1))
    assert frontend_bands == [band.value for band in AgeBand]


def test_frontend_avatar_catalog_matches_backend_literal() -> None:
    """avatars.ts catalog ids must equal the AvatarId closed vocabulary."""
    source = (_FRONTEND / "avatars.ts").read_text(encoding="utf-8")
    frontend_ids = re.findall(r"id:\s*['\"]([^'\"]+)['\"]", source)
    assert frontend_ids, "no avatar ids found in avatars.ts"
    assert frontend_ids == list(typing.get_args(AvatarId))
