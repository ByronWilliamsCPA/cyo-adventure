"""Select a production-eligible skeleton for a story's age band.

Scans the on-disk skeleton library (see generation/skeleton.py) for the first
production-eligible shell in the requested band's directory. Used by
story_requests/authoring_plan.py to auto-match a skeleton for
method="skeleton_fill".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from cyo_adventure.generation.skeleton import is_production_eligible

# #ASSUME: external-resources: the skeleton library is read cwd-relative
# ("skeletons/<band>/*.json"), matching the existing discovery convention in
# tests/unit/test_skeleton.py (Path("skeletons").glob(...)); the app and test
# suite are always invoked from the repository root.
# #VERIFY: a deployment that changes the working directory must mount or copy
# skeletons/ at that same relative path, or auto-match silently finds nothing
# (returns None, surfaced by the caller as a 422, not a crash).
_SKELETON_ROOT = Path("skeletons")


def select_skeleton_for_band(band: str) -> str | None:
    """Return the slug of the first production-eligible skeleton for a band.

    Args:
        band: The age band directory name (e.g. "8-11"), matching
            ``storybook.models.AgeBand`` values.

    Returns:
        The skeleton's filename stem (its slug), or ``None`` if the band
        directory does not exist or contains no production-eligible skeleton.
    """
    band_dir = _SKELETON_ROOT / band
    if not band_dir.is_dir():
        return None
    for path in sorted(band_dir.glob("*.json")):
        # #EDGE: external-resources: a corrupt or unreadable skeleton file must
        # not crash auto-match. This runs synchronously inside the
        # POST /authoring-plan request path, and a raw JSONDecodeError/OSError is
        # not a ProjectBaseError, so it would bypass app.py's structured handler
        # and surface as an unstructured 500. Skip the bad file and keep
        # scanning, honoring the "returns None, not a crash" contract above.
        # #VERIFY: test_select_skeleton_skips_malformed_file.
        try:
            raw = path.read_text(encoding="utf-8")
            data = cast("dict[str, object]", json.loads(raw))
        except (OSError, json.JSONDecodeError):
            continue
        if is_production_eligible(data):
            return path.stem
    return None
