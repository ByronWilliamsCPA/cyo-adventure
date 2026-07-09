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
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.storybook.models import StoryMetadata

if TYPE_CHECKING:
    import random
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

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
    if metadata.length != length:
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


def _weight(recent_count: int) -> float:
    """Return the inverse-frequency weight for a candidate's recent-use count.

    Args:
        recent_count: How many times this slug appeared in the family's
            recent storybook_version history (0 if never, or no history).

    Returns:
        1 / (1 + recent_count): 1.0 for an unused candidate, strictly
        decreasing but never zero as recent_count grows (the "implicit
        nonzero floor" from decision C-4: nothing is ever fully excluded).
    """
    return 1.0 / (1 + recent_count)


def select_skeleton_for_cell(
    candidates: list[str],
    recent_usage: dict[str, int],
    rng: random.Random,
) -> Selection:
    """Weighted-random pick from an in-cell candidate list.

    Args:
        candidates: Production-eligible skeleton slugs whose metadata matches
            the request's cell (from candidates_for_cell); must be
            non-empty. The caller is responsible for the "no matching
            skeleton" 422 before ever calling this.
        recent_usage: {slug: count} of how many times each slug was recently
            used by the family (from recent_skeleton_usage); an empty map
            (no family, or no history) yields a uniform pick.
        rng: An injected random.Random, so callers get deterministic
            behavior under a seeded instance (tests) and real randomness in
            production (see story_requests/authoring_plan.py, which passes a
            random.SystemRandom() rather than random.Random()).

    Returns:
        Selection: the weighted pick, plus every in-cell candidate as
        `alternatives` (so the admin sees every option, including the ones
        not drawn).

    Raises:
        ValueError: If candidates is empty (an internal-invariant
            violation; callers must check candidates_for_cell(...) first).
    """
    if not candidates:
        msg = "select_skeleton_for_cell requires at least one candidate"
        raise ValueError(msg)
    weights = [_weight(recent_usage.get(slug, 0)) for slug in candidates]
    pick = rng.choices(candidates, weights=weights, k=1)[0]
    return Selection(slug=pick, alternatives=list(candidates))


# How many of the family's most recent storybook_version rows to weight
# selection against (decision C-4: "proposed 20", ratified as the final
# value for WS-C PR2). A module constant, not configurable, so behavior is
# stable across restarts and does not need a settings round trip.
_RECENT_WINDOW = 20


async def recent_skeleton_usage(
    session: AsyncSession, family_id: uuid.UUID | None
) -> dict[str, int]:
    """Return {slug: count} of skeleton usage over the family's recent history.

    Args:
        session: An open async session.
        family_id: The request's owning family, or None for a family-less
            (admin/catalog) request.

    Returns:
        A recency-window usage count per slug; empty when family_id is None,
        the family has no storybook_version history, or every recent version
        has a null skeleton_slug (fresh_generation/import versions).
    """
    # #ASSUME: external-resources: this issues a live database query against
    # storybook_version joined to storybook; the caller (select_skeleton_for_cell's
    # caller in authoring_plan.py) is expected to hold an open async session.
    # #VERIFY: a session that is closed or out of a transaction context raises
    # before this function runs; no defensive re-open is attempted here.
    if family_id is None:
        return {}
    stmt = (
        select(StorybookVersion.skeleton_slug)
        .join(Storybook, Storybook.id == StorybookVersion.storybook_id)
        .where(Storybook.family_id == family_id)
        .order_by(StorybookVersion.created_at.desc())
        .limit(_RECENT_WINDOW)
    )
    result = await session.execute(stmt)
    counts: dict[str, int] = {}
    for (slug,) in result.all():
        if slug is None:
            continue
        counts[slug] = counts.get(slug, 0) + 1
    return counts
