"""Per-band story policy profile (single source of truth).

Holds, for each age band, the node/depth budget (formerly ``layer1._BUDGETS``)
plus the policy the gate enforces: content-flag ceilings, forbidden ending
kinds, and the ending/decision floors. Only bands near 9-12 are research-
measured; 3-5 and 16+ ceilings and floors are product-defined and tunable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.storybook.models import ContentFlagLevel, EndingKind

if TYPE_CHECKING:
    from collections.abc import Mapping

_L = ContentFlagLevel
_K = EndingKind


@dataclass(frozen=True, slots=True)
class BandProfile:
    """Budgets and age-policy for one reading band."""

    min_nodes: int
    max_nodes: int
    max_depth: int
    content_ceiling: Mapping[str, ContentFlagLevel]
    forbidden_ending_kinds: frozenset[EndingKind]
    min_endings: int
    min_decisions: int
    reconvergence_ceiling: int | None = None


_PROFILES: dict[str, BandProfile] = {
    "3-5": BandProfile(
        8,
        20,
        4,
        {"violence": _L.NONE, "scariness": _L.MILD, "peril": _L.MILD},
        frozenset({_K.DEATH, _K.CAPTURE}),
        min_endings=2,
        min_decisions=1,
    ),
    "5-8": BandProfile(
        12,
        30,
        6,
        {"violence": _L.MILD, "scariness": _L.MILD, "peril": _L.MILD},
        frozenset({_K.DEATH, _K.CAPTURE}),
        min_endings=2,
        min_decisions=2,
    ),
    "8-11": BandProfile(
        15,
        30,
        6,
        {"violence": _L.MILD, "scariness": _L.MODERATE, "peril": _L.MODERATE},
        frozenset({_K.DEATH}),
        min_endings=3,
        min_decisions=3,
    ),
    "10-13": BandProfile(
        25,
        50,
        8,
        {"violence": _L.MODERATE, "scariness": _L.MODERATE, "peril": _L.MODERATE},
        frozenset(),
        min_endings=3,
        min_decisions=3,
    ),
    "13-16": BandProfile(
        30,
        60,
        10,
        {"violence": _L.MODERATE, "scariness": _L.INTENSE, "peril": _L.INTENSE},
        frozenset(),
        min_endings=4,
        min_decisions=4,
    ),
    "16+": BandProfile(
        30,
        60,
        12,
        {"violence": _L.MODERATE, "scariness": _L.INTENSE, "peril": _L.INTENSE},
        frozenset(),
        min_endings=4,
        min_decisions=4,
    ),
}


def profile_for(age_band: str) -> BandProfile | None:
    """Return the policy profile for a band, or ``None`` if unknown.

    Args:
        age_band: The story age band value (for example ``"10-13"``).

    Returns:
        The band's :class:`BandProfile`, or ``None`` when not configured.
    """
    return _PROFILES.get(age_band)


# MVP/Test tier: a band-independent, non-production node envelope for
# prototyping, pipeline and integration testing, and generator development. A
# story whose ``metadata.production_eligible`` is ``False`` is budgeted against
# this envelope instead of its band's production node budget; every other band
# policy (content ceiling, forbidden endings, floors, branch depth) still
# applies. See ADR-011 (story-scale framework), the MVP/Test tier.
MVP_MIN_NODES = 8
MVP_MAX_NODES = 45


def mvp_node_budget(age_band: str) -> tuple[int, int, int] | None:
    """Return the MVP/Test ``(min_nodes, max_nodes, max_depth)`` for a band.

    The node-count envelope is band-independent (``MVP_MIN_NODES`` ..
    ``MVP_MAX_NODES``); the branch-depth cap is inherited from the band's
    production profile so an MVP shell stays within its band's structural
    depth.

    Args:
        age_band: The story age band value (for example ``"10-13"``).

    Returns:
        The ``(min_nodes, max_nodes, max_depth)`` triple, or ``None`` when the
        band is not configured (which keeps the depth cap band-anchored).
    """
    profile = profile_for(age_band)
    if profile is None:
        return None
    return (MVP_MIN_NODES, MVP_MAX_NODES, profile.max_depth)


# Genre-faithful production node envelopes, keyed on the ADR-011 story-scale
# matrix cell ``(age_band, length, narrative_style)``. Each value is
# ``(min_nodes, max_nodes, max_depth)``:
#   - min/max come from the ADR-011 master-cell "total nodes" column (the derived
#     world-size envelope); below-min is a WARNING and above-max is an ERROR, per
#     the L1-7 semantics.
#   - max_depth is a product-tuned guardrail (~2.5x the cell's fastest-finish
#     floor, rounded), generous enough not to reject a legitimate genre structure
#     while still catching a runaway near-linear chain. It is NOT from research;
#     treat it as tunable, like the ADR's product-defined 3-5/16+ budgets.
# Only the cells offered by ADR-011 exist: young bands (3-5, 5-8) cap at Medium;
# 13-16/16+ start at Medium and add the gamebook style; other bands are prose.
# A story whose declared cell is absent here falls back to the band-level budget.
# #ASSUME: data-integrity: this table is the single source for per-cell production
# budgets; the Stage A generation prompt does NOT read it yet (generation stays on
# the band-level budget until a later slice teaches it to select a cell).
# #VERIFY: test_band_profile.py::test_production_cell_budget_matches_adr_envelopes.
_PRODUCTION_CELLS: dict[tuple[str, str, str], tuple[int, int, int]] = {
    ("3-5", "short", "prose"): (10, 23, 15),
    ("3-5", "medium", "prose"): (23, 45, 18),
    ("5-8", "short", "prose"): (29, 50, 18),
    ("5-8", "medium", "prose"): (50, 86, 23),
    ("8-11", "short", "prose"): (60, 100, 23),
    ("8-11", "medium", "prose"): (100, 160, 30),
    ("8-11", "long", "prose"): (160, 240, 35),
    ("10-13", "short", "prose"): (90, 140, 28),
    ("10-13", "medium", "prose"): (140, 220, 35),
    ("10-13", "long", "prose"): (220, 340, 43),
    ("13-16", "medium", "prose"): (115, 170, 38),
    ("13-16", "medium", "gamebook"): (245, 370, 60),
    ("13-16", "long", "prose"): (170, 270, 50),
    ("13-16", "long", "gamebook"): (370, 585, 80),
    ("16+", "medium", "prose"): (135, 215, 45),
    ("16+", "medium", "gamebook"): (300, 475, 73),
    ("16+", "long", "prose"): (215, 345, 58),
    ("16+", "long", "gamebook"): (475, 750, 93),
}


def production_cell_budget(
    age_band: str, length: str, narrative_style: str
) -> tuple[int, int, int] | None:
    """Return the production ``(min_nodes, max_nodes, max_depth)`` for a cell.

    Looks up the genre-faithful node envelope for a scale-classified production
    story on the ADR-011 ``(band, length, style)`` matrix.

    Args:
        age_band: The story age band value (for example ``"8-11"``).
        length: The story-scale length tier (``"short"``, ``"medium"``,
            ``"long"``).
        narrative_style: ``"prose"`` or ``"gamebook"``.

    Returns:
        The ``(min_nodes, max_nodes, max_depth)`` triple for the cell, or
        ``None`` when the combination is not an offered cell (for example a
        ``3-5`` ``long`` story, or an ``8-11`` ``gamebook``), in which case the
        caller falls back to the band-level budget.
    """
    return _PRODUCTION_CELLS.get((age_band, length, narrative_style))
