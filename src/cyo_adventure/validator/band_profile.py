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
