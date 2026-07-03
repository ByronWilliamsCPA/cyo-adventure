"""Per-band story policy profile (single source of truth).

Holds, for each age band, the node/depth budget (formerly ``layer1._BUDGETS``)
plus the policy the gate enforces: content-flag ceilings, forbidden ending
kinds, and the ending/decision floors. Only bands near 9-12 are research-
measured; 3-5 and 16+ ceilings and floors are product-defined and tunable.
"""

from __future__ import annotations

import math
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
# budgets. Both the L1-7 gate (validate_layer1) and the Stage A generation prompt
# (generation.prompts._budget_block) read it transitively through
# resolve_node_budget -> production_cell_budget, so the prompt promises exactly what
# the gate enforces for an offered cell. An off-matrix declared cell is absent here
# and falls back to the band-level budget (PL-21 then rejects the off-matrix story).
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


def offered_cells() -> frozenset[tuple[str, str, str]]:
    """Return every ``(age_band, length, narrative_style)`` cell the matrix offers.

    This is the coverage-grid source: the full set of production story-scale
    cells ADR-011 defines. A tool can cross it with the authored skeleton library
    to report which cells are covered, and the PL-21 policy rule uses it to reject
    a story that declares an off-matrix combination.

    Returns:
        The frozen set of offered cell keys.
    """
    return frozenset(_PRODUCTION_CELLS)


def is_offered_cell(age_band: str, length: str, narrative_style: str) -> bool:
    """Return whether ``(band, length, style)`` is an offered production cell.

    Args:
        age_band: The story age band value (for example ``"8-11"``).
        length: The story-scale length tier (``"short"``/``"medium"``/``"long"``).
        narrative_style: ``"prose"`` or ``"gamebook"``.

    Returns:
        ``True`` when the combination is an offered cell (for example ``8-11``
        ``short`` ``prose``); ``False`` for an off-matrix combination (for example
        a ``3-5`` ``long`` or an ``8-11`` ``gamebook``).
    """
    return (age_band, length, narrative_style) in _PRODUCTION_CELLS


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


# Words-per-node envelope per ``(age_band, narrative_style)`` from ADR-011
# section 3: ``(mean, advisory_lo, advisory_hi, per_node_max)``. The mean and the
# advisory band are the story-level story-mean target (checked as a WARNING for
# scale-classified stories only); ``per_node_max`` is a hard per-node wall guard
# (checked as an ERROR for every story). There is no hard per-node minimum: a
# one-line beat is legitimate. Only 13-16/16+ have a gamebook entry; lower bands
# are prose, so a young-band gamebook falls back to the band's prose envelope.
_WORDS_PER_NODE: dict[tuple[str, str], tuple[int, int, int, int]] = {
    ("3-5", "prose"): (40, 28, 55, 90),
    ("5-8", "prose"): (70, 50, 95, 155),
    ("8-11", "prose"): (100, 70, 135, 220),
    ("10-13", "prose"): (100, 70, 135, 220),
    ("13-16", "prose"): (140, 100, 185, 310),
    ("13-16", "gamebook"): (65, 45, 90, 145),
    ("16+", "prose"): (175, 125, 230, 385),
    ("16+", "gamebook"): (80, 55, 110, 175),
}


def words_per_node_profile(
    age_band: str, narrative_style: str
) -> tuple[int, int, int, int] | None:
    """Return ``(mean, advisory_lo, advisory_hi, per_node_max)`` for a band+style.

    A young-band ``gamebook`` (an off-matrix combination) falls back to that
    band's prose envelope so the per-node wall guard still has a value.

    Args:
        age_band: The story age band value (for example ``"8-11"``).
        narrative_style: ``"prose"`` or ``"gamebook"``.

    Returns:
        The words-per-node envelope tuple, or ``None`` when the band is unknown.
    """
    return _WORDS_PER_NODE.get((age_band, narrative_style)) or _WORDS_PER_NODE.get(
        (age_band, "prose")
    )


# Fastest-finish arc floor per ADR-011 story-scale cell
# ``(age_band, length, narrative_style)``: the minimum number of nodes on the
# shortest path to a *satisfying* (success/completion) ending. Only offered
# cells exist; a story off the matrix has no arc floor.
_MIN_COMPLETE: dict[tuple[str, str, str], int] = {
    ("3-5", "short", "prose"): 6,
    ("3-5", "medium", "prose"): 7,
    ("5-8", "short", "prose"): 7,
    ("5-8", "medium", "prose"): 9,
    ("8-11", "short", "prose"): 9,
    ("8-11", "medium", "prose"): 12,
    ("8-11", "long", "prose"): 14,
    ("10-13", "short", "prose"): 11,
    ("10-13", "medium", "prose"): 14,
    ("10-13", "long", "prose"): 17,
    ("13-16", "medium", "prose"): 15,
    ("13-16", "medium", "gamebook"): 24,
    ("13-16", "long", "prose"): 20,
    ("13-16", "long", "gamebook"): 32,
    ("16+", "medium", "prose"): 18,
    ("16+", "medium", "gamebook"): 29,
    ("16+", "long", "prose"): 23,
    ("16+", "long", "gamebook"): 37,
}


def min_complete_floor(age_band: str, length: str, narrative_style: str) -> int | None:
    """Return the fastest-finish arc floor (nodes) for a story-scale cell.

    Args:
        age_band: The story age band value (for example ``"8-11"``).
        length: The story-scale length tier (``"short"``, ``"medium"``,
            ``"long"``).
        narrative_style: ``"prose"`` or ``"gamebook"``.

    Returns:
        The minimum node count on the shortest satisfying-completion path, or
        ``None`` when the combination is not an offered cell.
    """
    return _MIN_COMPLETE.get((age_band, length, narrative_style))


# Breadth-scaled PL-17 floors for a scale-classified production story. The band
# profile floors (``min_endings`` / ``min_decisions``) are absolute minimums tuned
# for band-scale stories; a large scale-classified world must not pass with a
# handful of endings or a near-linear spine, so its floors scale with node count.
# ADR-011 section 6: endings are reconvergent leaves scaling with node count
# (prose ~15-22%), and a gamebook is "few wins + many fails" (~25-35% terminals);
# the fractions below are the LOW end of those bands, so the floor is a
# non-inflating minimum. The decision fraction is a product-tuned guardrail
# (~half the prose ending fraction, since ADR-011 holds ~2-3 choices per decision
# and decisions-per-PATH constant): it bounds total decision *breadth*, not path
# depth, so it catches an almost-linear large story without inflating decisions.
# Both are tunable, like the ADR's product-defined budgets.
_ENDINGS_FRACTION: dict[str, float] = {"prose": 0.15, "gamebook": 0.25}
_DECISIONS_FRACTION = 0.08


def breadth_scaled_floors(node_count: int, narrative_style: str) -> tuple[int, int]:
    """Return ``(min_endings, min_decisions)`` scaled to a story's node count.

    Only a scale-classified production story uses these; the caller takes the
    ``max`` of the band-level floor and the scaled floor, so a small scale story
    never drops below its band minimum. An unknown style falls back to the prose
    ending fraction.

    Args:
        node_count: The total number of nodes in the story.
        narrative_style: ``"prose"`` or ``"gamebook"``.

    Returns:
        The breadth-scaled ``(min_endings, min_decisions)`` floor pair.
    """
    endings_fraction = _ENDINGS_FRACTION.get(
        narrative_style, _ENDINGS_FRACTION["prose"]
    )
    min_endings = math.ceil(node_count * endings_fraction)
    min_decisions = math.ceil(node_count * _DECISIONS_FRACTION)
    return min_endings, min_decisions
