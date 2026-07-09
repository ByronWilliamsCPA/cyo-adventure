"""Cell-aware skeleton selection for a story's (band, length, style) cell.

Replaces the old band-only, style/length-blind ``select_skeleton_for_band``
(WS-C PR2). Splits into a pure core (metadata loading, cell matching, the
weighted pick) and one impure recency query
(:func:`recent_skeleton_usage`), so the selection logic itself is fully
unit-testable without a database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.storybook.models import StoryMetadata

# #ASSUME: external-resources: the skeleton library is read cwd-relative
# ("skeletons/<band>/*.json"), matching the existing discovery convention in
# tests/unit/test_skeleton.py (Path("skeletons").glob(...)); the app and test
# suite are always invoked from the repository root.
# #VERIFY: a deployment that changes the working directory must mount or copy
# skeletons/ at that same relative path, or cell matching silently finds
# nothing (returns an empty list, surfaced by the caller as a 422, not a
# crash).
_SKELETON_ROOT = Path("skeletons")

# Bands where the narrative-style axis is meaningful (ADR-011); below these,
# style collapses to prose and is not matched.
_STYLE_AWARE_BANDS = frozenset({"13-16", "16+"})


@dataclass(frozen=True, slots=True)
class Selection:
    """A weighted-random skeleton pick plus the full in-cell candidate list."""

    slug: str
    alternatives: list[str]


def _load_metadata(path: Path) -> StoryMetadata | None:
    """Return the typed metadata for a skeleton file, or None if unreadable.

    Mirrors the old select_skeleton_for_band contract: a corrupt or
    unreadable file must not crash the scan (this runs synchronously inside
    POST /authoring-plan). Malformed or schema-invalid metadata is treated
    the same as a missing file: skipped, not raised.

    Args:
        path: Path to a skeleton JSON file.

    Returns:
        The typed StoryMetadata, or None on any read/parse/schema failure.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        data = cast("dict[str, object]", json.loads(raw))
    except (OSError, json.JSONDecodeError):
        return None
    meta = data.get("metadata") if isinstance(data, dict) else None
    if not isinstance(meta, dict):
        return None
    try:
        return StoryMetadata.model_validate(meta)
    except PydanticValidationError:
        return None


def _production_candidates(band: str) -> list[tuple[str, StoryMetadata]]:
    """Return (slug, metadata) for every production-eligible skeleton in a band.

    Args:
        band: The age band directory name (e.g. "8-11").

    Returns:
        Sorted-by-filename (slug, metadata) pairs; empty if the band
        directory does not exist or has no production-eligible skeleton.
    """
    band_dir = _SKELETON_ROOT / band
    if not band_dir.is_dir():
        return []
    candidates: list[tuple[str, StoryMetadata]] = []
    for path in sorted(band_dir.glob("*.json")):
        metadata = _load_metadata(path)
        if metadata is None or not metadata.production_eligible:
            continue
        candidates.append((path.stem, metadata))
    return candidates


def skeleton_matches_cell(
    metadata: StoryMetadata, *, band: str, length: str, style: str
) -> bool:
    """Return whether a skeleton's metadata matches a (band, length, style) cell.

    Args:
        metadata: The skeleton's typed metadata.
        band: The request's age band.
        length: The request's length ("short"/"medium"/"long"); a null
            request length must already be collapsed to a default by the
            caller (see story_requests/authoring_plan.py::_length_of).
        style: The request's narrative style; ignored for every band except
            "13-16" and "16+" (ADR-011: style collapses to prose below the
            teen bands).

    Returns:
        True if age_band and length match, and (for the two teen bands only)
        narrative_style also matches.
    """
    if metadata.age_band != band:
        return False
    metadata_length = metadata.length if metadata.length is not None else None
    if metadata_length != length:
        return False
    return band not in _STYLE_AWARE_BANDS or metadata.narrative_style == style


def candidates_for_cell(band: str, length: str, style: str) -> list[str]:
    """Return slugs of every production-eligible skeleton matching a cell.

    Args:
        band: The request's age band.
        length: The request's length, already defaulted if the request's own
            length was null.
        style: The request's narrative style.

    Returns:
        Sorted-by-filename slugs; empty if no skeleton matches (the caller
        must treat an empty list as "no skeleton available", exactly as the
        old select_skeleton_for_band's None return was treated).
    """
    return [
        slug
        for slug, metadata in _production_candidates(band)
        if skeleton_matches_cell(metadata, band=band, length=length, style=style)
    ]


def find_skeleton_metadata(slug: str) -> StoryMetadata | None:
    """Return a skeleton's typed metadata by scanning every band directory.

    Used for the admin's unconstrained skeleton_slug override (decision C-6),
    which may name a skeleton outside the request's own band directory (an
    explicitly out-of-cell pick), or a non-production-eligible one.

    Args:
        slug: The skeleton's filename stem, as supplied by the admin.

    Returns:
        The typed metadata, or None if no band directory has a file named
        "<slug>.json" (or that file is unreadable/malformed).
    """
    if not _SKELETON_ROOT.is_dir():
        return None
    for band_dir in sorted(_SKELETON_ROOT.iterdir()):
        if not band_dir.is_dir():
            continue
        path = band_dir / f"{slug}.json"
        if path.is_file():
            return _load_metadata(path)
    return None
