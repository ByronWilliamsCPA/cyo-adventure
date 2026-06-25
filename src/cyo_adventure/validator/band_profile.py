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
