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
from typing import TYPE_CHECKING, Final, cast

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.storybook.models import StoryMetadata
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import random
    import uuid
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

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
    """A weighted-random skeleton pick plus the full in-cell candidate list.

    Invariants (finding H):
        - ``alternatives`` is always non-empty. Every Selection is produced from
          at least one candidate, so an empty alternatives list is an
          internal-invariant violation rejected at construction.
        - ``slug`` need NOT appear in ``alternatives``: an admin out-of-cell
          override legitimately picks a slug that is not in the in-cell list.

    Attributes:
        slug: The chosen skeleton slug (may be an out-of-cell override).
        alternatives: Every in-cell candidate slug, as an immutable tuple.
    """

    slug: str
    alternatives: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject an empty alternatives tuple.

        Raises:
            ValidationError: If ``alternatives`` is empty (a Selection must
                carry at least one candidate).
        """
        if not self.alternatives:
            msg = "Selection.alternatives requires at least one candidate"
            raise ValidationError(msg, field="alternatives", value=None)


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
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("skeleton.unreadable", path=str(path), error=str(exc))
        return None
    meta = data.get("metadata") if isinstance(data, dict) else None
    if not isinstance(meta, dict):
        logger.warning("skeleton.missing_metadata_block", path=str(path))
        return None
    try:
        return StoryMetadata.model_validate(meta)
    except PydanticValidationError as exc:
        logger.warning("skeleton.schema_invalid", path=str(path), error=str(exc))
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
        # #ASSUME: data-integrity: a WS-2 theme-contract sidecar
        # (`<slug>.contract.json`) lives next to its skeleton and also matches
        # this `*.json` glob; without this skip it would be treated as a
        # skeleton with a missing metadata block, logging one spurious
        # `skeleton.missing_metadata_block` warning per contract on every
        # scan. Sidecars are authoring-time data, never a selectable
        # skeleton.
        # #VERIFY: test_skeleton_match.py asserts a `*.contract.json` file
        # produces no candidate and no warning log.
        if path.name.endswith(".contract.json"):
            continue
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
        metadata: The skeleton's typed metadata. A skeleton whose ``length`` is
            None is length-less (a documented valid backward-compat state on
            StoryMetadata.length: Length | None) and matches any request length.
        band: The request's age band.
        length: The request's length ("short"/"medium"/"long"); a null
            request length must already be collapsed to a default by the
            caller (see story_requests/authoring_plan.py::_length_of).
        style: The request's narrative style; ignored for every band except
            "13-16" and "16+" (ADR-011: style collapses to prose below the
            teen bands).

    Returns:
        True if age_band matches, the skeleton's length matches (or the
        skeleton declares no length, which is a wildcard that matches any
        request length), and (for the two teen bands only) narrative_style
        also matches.
    """
    if metadata.age_band != band:
        return False
    if metadata.length is not None and metadata.length != length:
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


def resolve_skeleton_path(band: str, slug: str) -> Path:
    """Return the validated ``skeletons/<band>/<slug>.json`` path.

    Resolves the candidate path and confirms it stays inside the skeleton root
    before returning it, so an admin-supplied slug cannot escape the library
    tree via path traversal.

    Args:
        band: The age band directory name (e.g. "8-11").
        slug: The skeleton's filename stem, as supplied by the admin (untrusted).

    Returns:
        The resolved, containment-checked path (it may or may not exist on
        disk; the caller checks ``is_file()``).

    Raises:
        ValidationError: If the resolved path escapes the skeleton root (a
            path-traversal attempt via ``band`` or ``slug``).
    """
    # #CRITICAL: security: ``slug`` is untrusted admin-override input
    # (decision C-6, unconstrained skeleton_slug). A slug such as
    # "../../etc/passwd" would otherwise resolve outside skeletons/ and let a
    # crafted request read or fill an arbitrary file. Reject any resolved path
    # that is not contained in the skeleton root.
    # #VERIFY: test_resolve_skeleton_path_rejects_traversing_slug and
    # test_find_skeleton_metadata_rejects_traversing_slug assert the
    # ValidationError; worker.py and import_story.py resolve through this helper.
    root = _SKELETON_ROOT.resolve()
    candidate = (_SKELETON_ROOT / band / f"{slug}.json").resolve()
    if not candidate.is_relative_to(root):
        msg = (
            f"skeleton path for band '{band}', slug '{slug}' escapes the skeleton root"
        )
        raise ValidationError(msg, field="skeleton_slug", value=slug)
    return candidate


def find_skeleton_metadata(slug: str) -> StoryMetadata | None:
    """Return a skeleton's typed metadata by scanning every band directory.

    Used for the admin's unconstrained skeleton_slug override (decision C-6),
    which may name a skeleton outside the request's own band directory (an
    explicitly out-of-cell pick), or a non-production-eligible one. Every
    candidate path is routed through :func:`resolve_skeleton_path` so a
    traversing slug is rejected rather than read.

    A genuinely-absent slug (no band has "<slug>.json") returns None so the
    caller can surface the standard "does not exist" 422. A slug that exists
    but is corrupt, or exists in more than one band, raises so the caller does
    not misreport a real, distinct failure as "does not exist".

    Args:
        slug: The skeleton's filename stem, as supplied by the admin.

    Returns:
        The typed metadata, or None if no band directory has a file named
        "<slug>.json".

    Raises:
        ValidationError: If ``slug`` traverses outside the skeleton root
            (via :func:`resolve_skeleton_path`); if the same "<slug>.json"
            exists in two or more bands (ambiguous); or if exactly one exists
            but is unreadable or has invalid metadata (present-but-corrupt).
    """
    if not _SKELETON_ROOT.is_dir():
        return None
    matches: list[tuple[str, Path]] = []
    for band_dir in sorted(_SKELETON_ROOT.iterdir()):
        if not band_dir.is_dir():
            continue
        path = resolve_skeleton_path(band_dir.name, slug)
        if path.is_file():
            matches.append((band_dir.name, path))
    if len(matches) > 1:
        bands = ", ".join(sorted(band for band, _ in matches))
        msg = f"ambiguous skeleton_slug '{slug}' present in multiple bands: {bands}"
        raise ValidationError(msg, field="skeleton_slug", value=slug)
    if not matches:
        return None
    metadata = _load_metadata(matches[0][1])
    if metadata is None:
        msg = f"skeleton_slug '{slug}' exists but is unreadable or has invalid metadata"
        raise ValidationError(msg, field="skeleton_slug", value=slug)
    return metadata


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


# De-weights a similar-theme reuse of a tree like 3 plain recent uses (WS-4,
# docs/planning/story-flexibility-plan.md section "WS-4: Similarity-driven,
# escalating selection"): a family's second dragon story on a skeleton it
# already used for a dragon story should feel like a much heavier repeat than
# an unrelated-theme recent use of that same skeleton. A starting heuristic,
# not calibrated data, tunable once WS-0 metrics accumulate; mirrors the
# `_HARD_BANDS`-style heuristics in story_requests/authoring_plan.py.
_THEME_REUSE_PENALTY: Final[int] = 3


def _blended_weight(recent_count: int, similar_count: int) -> float:
    """Return an inverse-frequency weight blending recency and theme reuse.

    Args:
        recent_count: How many times this slug appeared in the family's
            recent storybook_version history (see recent_skeleton_usage).
        similar_count: How many of the family's recent similar-theme
            stories used this slug (see
            diversity.query.similarity_context's
            ``similar_count_per_slug``).

    Returns:
        1 / (1 + recent_count + _THEME_REUSE_PENALTY * similar_count): 1.0
        for a wholly-unused candidate, strictly decreasing but never zero as
        either count grows (the same never-zero novelty floor as
        :func:`_weight`, decision C-4).
    """
    return 1.0 / (1 + recent_count + _THEME_REUSE_PENALTY * similar_count)


def select_skeleton_for_cell(
    candidates: list[str],
    recent_usage: dict[str, int],
    rng: random.Random,
    *,
    similar_usage: Mapping[str, int] | None = None,
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
        similar_usage: {slug: count} of how many of the family's recent
            similar-theme stories (WS-4, from
            diversity.query.SimilarityContext.similar_count_per_slug) used
            each slug. When None (the default), weights are exactly
            ``_weight(recent_usage[slug])``, unchanged from the pre-WS-4
            behavior. When provided, weights blend recency and theme reuse
            via :func:`_blended_weight`.

    Returns:
        Selection: the weighted pick, plus every in-cell candidate as
        `alternatives` (an immutable tuple, so the admin sees every option,
        including the ones not drawn).

    Raises:
        ValidationError: If candidates is empty (an internal-invariant
            violation; callers must check candidates_for_cell(...) first).
            Built-in exceptions are disallowed in this service module per
            src/CLAUDE.md, so this raises the project ValidationError.
    """
    if not candidates:
        msg = "select_skeleton_for_cell requires at least one candidate"
        raise ValidationError(msg, field="candidates", value=None)
    if similar_usage is None:
        weights = [_weight(recent_usage.get(slug, 0)) for slug in candidates]
    else:
        weights = [
            _blended_weight(recent_usage.get(slug, 0), similar_usage.get(slug, 0))
            for slug in candidates
        ]
    pick = rng.choices(candidates, weights=weights, k=1)[0]
    return Selection(slug=pick, alternatives=tuple(candidates))


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
    #
    # #ASSUME: data-integrity: the recency window counts EVERY authored
    # storybook_version row (all statuses, and multiple versions of the same
    # storybook count separately) as "recently used". StorybookVersion has no
    # per-version delivered/approved status column; a version's delivered state
    # is only inferrable from the parent Storybook.status or approved_by. The
    # deliberate choice here is that skeleton diversity should reflect authoring
    # activity, not delivery: a skeleton the family just authored against is
    # "recently used" whether or not that version shipped. Narrowing this to
    # approved-only or distinct-storybook counting is a product decision, not a
    # bug, and is intentionally NOT done here.
    # #VERIFY: tests/unit/test_skeleton_recency.py pins the exact query and the
    # returned counts; any status filter or dedupe would break those and must be
    # a deliberate, tested product change.
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
