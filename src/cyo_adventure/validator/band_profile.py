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

# PL-25 requires every story to establish its situation before the first
# decision (its floor is 2: the first decision is no earlier than the second
# node). That stop costs one node of branch depth, and the two depth budgets
# account for it differently:
#   - A production cell's max_depth is ~2.5x its min_complete floor, and those
#     floors already account for the opening, so the establishing stop is inside
#     the cell budget.
#     CORRECTED 2026-08-18: this comment used to call the `_MIN_COMPLETE` values
#     "JHM *page* counts for a whole playthrough". They are not. The audit that
#     went looking for exactly that unit error checked and REFUTED it: for all 18
#     cells, `min_complete x mean words/node / band pace` reproduces the ADR's own
#     "fastest finish" minutes column, so they are node counts derived from the
#     section 3 table. The mis-citation had no downstream effect, since nothing
#     read it as pages, but it is the kind of wrong provenance note that seeds a
#     real unit error later (`UW-C277`).
#   - The band-level max_depth triple predates ADR-011 and derives from nothing
#     measured. ``mvp_node_budget`` below is the ONLY consumer that grants it
#     the establishing-stop allowance: ``resolve_node_budget``'s step-3
#     band-level fallback (a production-eligible story with no length, or an
#     off-matrix length), ``layer1._COMPACT_BUDGETS``, and
#     ``generation.prompts._budget_block`` (which reads ``resolve_node_budget``
#     transitively) all use the same band-level max_depth with no allowance.
#     The validator therefore allows ``max_depth + 1`` on the MVP path only,
#     while those three other consumers state and enforce the un-allowanced
#     max_depth; a production story that lands on the band-level fallback is
#     told one less depth than an MVP shell gets for the identical
#     opening-stop cost.
# Without this allowance PL-25 and L1-7 contradict each other for any MVP shell
# authored to its band depth cap: satisfying the opening rule puts it one node
# over budget. See AL-087.
ESTABLISHING_STOP_DEPTH = 1


def mvp_node_budget(age_band: str) -> tuple[int, int, int] | None:
    """Return the MVP/Test ``(min_nodes, max_nodes, max_depth)`` for a band.

    The node-count envelope is band-independent (``MVP_MIN_NODES`` ..
    ``MVP_MAX_NODES``); the branch-depth cap stays anchored to the band's
    production profile so an MVP shell keeps its band's structural depth, plus
    ``ESTABLISHING_STOP_DEPTH`` for the opening stop PL-25 requires.

    Args:
        age_band: The story age band value (for example ``"10-13"``).

    Returns:
        The ``(min_nodes, max_nodes, max_depth)`` triple, or ``None`` when the
        band is not configured (which keeps the depth cap band-anchored).
    """
    profile = profile_for(age_band)
    if profile is None:
        return None
    return (MVP_MIN_NODES, MVP_MAX_NODES, profile.max_depth + ESTABLISHING_STOP_DEPTH)


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
# Per-band Flesch-Kincaid grade target, the SINGLE source of record.
#
# RULED 2026-08-18 (owner). Four sites stated per-band FK targets and disagreed:
# `story_requests/brief.py`, `frontend/src/guardian/intakeApi.ts`,
# `generation/templates/drafting_guide.md` (which is spliced into every
# structure, prose and fill prompt and calls ITSELF "the FK-target source of
# record"), and `docs/planning/drafting-guide.md`. See
# `docs/planning/reading-level-source-table.md` for the full comparison.
#
# The values are what the committed catalog DECLARES, because that is what RL-13
# actually grades each story against, and because they are demonstrably
# achievable: 31 committed books sit near them. The injected prompt guide asked
# for 8.0 at 13-16 and 10.0 at 16+ against declared 7.0 and 8.0-9.0, so prose
# written to its own centre landed a full grade outside the window the validator
# measures, and four of five 13-16 books fell below its stated floor.
#
# Achievability alone would be a circular argument (books written to their own
# declarations cannot refute those declarations), so the external anchor is
# `docs/planning/research/cyoa-research-reconciliation.md` item 4: it sets the
# gate by age band, places core CYOA at roughly 500-710L, and puts teen
# gamebooks at middle-grade prose. That favours these values over the injected
# guide's at exactly the bands where the two diverge.
#
# #ASSUME: data-integrity: this table is the single source for per-band FK
# targets. `reading_level_target_for` below is the only reader; a story's own
# `metadata.reading_level.target` still governs RL-13, and this is the default
# it should be authored from.
# #VERIFY: test_reading_level_sources.py::test_reading_level_target_covers_every_band
# and ::test_declared_catalog_targets_sit_inside_their_band_window.
_READING_LEVEL_TARGET: dict[str, float] = {
    "3-5": 1.0,
    "5-8": 2.5,
    "8-11": 4.5,
    "10-13": 5.5,
    "13-16": 7.0,
    "16+": 9.0,
}


def reading_level_target_for(age_band: str) -> float | None:
    """Return the band's default Flesch-Kincaid grade target.

    Args:
        age_band: The story age band value (for example ``"8-11"``).

    Returns:
        The band's FK target, or ``None`` when the band is not configured.
    """
    return _READING_LEVEL_TARGET.get(age_band)


def clamp_target_to_cap(target: float, reading_level_cap: float) -> float:
    """Return the FK target a guardian's ceiling allows.

    A cap is a CEILING (``api/schemas.py``: "can only ever tighten"), and RL-13
    reads its target as the CENTRE of a plus-or-minus window. Feeding the cap in
    as the target therefore admitted prose a full grade ABOVE the maximum the
    guardian asked for: a cap of 2.0 passed FK 3.00. Clamping instead of
    substituting keeps a cap from ever raising a band's target, and keeps it
    from silently becoming a target in its own right.

    Args:
        target: The band's default target.
        reading_level_cap: The guardian's ceiling.

    Returns:
        The lower of the two, so a cap can only tighten.
    """
    return min(target, reading_level_cap)


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


# ADR-011 section 5 reading-pace anchors, in words per minute, used for the
# fastest-finish and whole-world clocks. Approximate standard fluency norms, not
# project-measured. This is the single source: mutation/identity.py's
# recompute_estimated_minutes and the PL-23 advisory both read it, so a retune of
# ADR-011 changes one table.
_READING_PACE_WPM: dict[str, int] = {
    "3-5": 100,
    "5-8": 90,
    "8-11": 120,
    "10-13": 150,
    "13-16": 190,
    "16+": 220,
}

# Pace for a band with no configured anchor: the 8-11 core-research value, which
# is the ADR's own baseline.
_DEFAULT_PACE_WPM = 120


def reading_pace_wpm(age_band: str) -> int:
    """Return the ADR-011 reading-pace anchor for a band, in words per minute.

    Args:
        age_band: The band value (for example ``"16+"``).

    Returns:
        int: The band's anchor, or the 8-11 baseline for an unknown band.
    """
    return _READING_PACE_WPM.get(age_band, _DEFAULT_PACE_WPM)


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


# PL-25 depth-to-first-decision window per band, in nodes: the count of nodes on
# the shortest path from ``start_node`` up to and including the first node that
# offers two or more choices. Anchored on Adams, Beckelhymer and Marr, "Choose
# Your Own Adventure: An Analysis of Interactive Gamebooks Using Graph Theory",
# Journal of Humanistic Mathematics 9(2), 2019 (DOI 10.5642/jhummath.201902.05),
# Table 4: across the 40-book corpus, pages to the first decision have a median
# of 4 and a range of 2 to 8.25. That corpus sits in the 8-11/10-13 reading
# range, so those bands take the measured window directly; the outer bands are
# product-defined scalings and are tunable, like the ADR-011 3-5/16+ budgets.
#
# The anchor's unit is a PAGE and this table's unit is a NODE, which are not the
# same quantity: a node may hold a fifth of a page or two pages. RULED 2026-08-17
# (owner), ``policy._opening_in_word_window`` therefore also admits each bound
# converted to words through _WORDS_PER_NODE above, one-way, so a story outside
# the node window but inside the prose window it stands for passes. The numbers
# here are unchanged; only the unit they are read in widened.
#   - Below the floor is an ERROR, graded in one tier: a story
#     that opens on its first choice asks the reader to pick before any
#     situation exists, a correctness failure rather than a matter of pacing
#     degree. No book in the JHM corpus branches before page 2, which is what
#     puts the floor at 2 for every band that has measured backing. 3-5 keeps
#     a floor of 1 because a pre-reader picture book can legitimately open on
#     its first choice and no evidence covers that band.
#   - Above the ceiling is a WARNING: a buried first choice is a craft defect,
#     not an unpublishable one. Past ``ARC_CEILING_MULTIPLE`` times the
#     ceiling (the JHM corpus's own longest-to-shortest playthrough ratio) it
#     escalates to an ERROR: a story that far past the window sits outside the
#     observed genre rather than merely slow, which is the long unbranching
#     prologue this rule exists to catch and the shape an LLM generator
#     produces most readily. See ``policy._check_first_decision_depth`` for
#     the full tiering.
# #ASSUME: data-integrity: this table is the single source for the PL-25 window.
# #VERIFY: test_band_profile.py::test_first_decision_window_covers_every_band.
#   - No ceiling sits below the corpus median of 4, and the two bands the corpus
#     actually covers admit its full measured range (ceiling 9 >= the 8.25 max).
#     A threshold that blocks pacing the source corpus calls typical, or that
#     blocks a book the corpus contains, is miscalibrated by construction; both
#     defects were present in this table's first draft and both are now asserted
#     in test_band_profile.py.
_FIRST_DECISION_DEPTH: dict[str, tuple[int, int]] = {
    "3-5": (1, 5),
    "5-8": (2, 5),
    "8-11": (2, 9),
    "10-13": (2, 9),
    "13-16": (2, 10),
    "16+": (2, 10),
}


def first_decision_window(age_band: str) -> tuple[int, int] | None:
    """Return the PL-25 ``(floor, ceiling)`` depth-to-first-decision for a band.

    Args:
        age_band: The story age band value (for example ``"8-11"``).

    Returns:
        The ``(floor, ceiling)`` node-count window, or ``None`` when the band is
        not configured.
    """
    return _FIRST_DECISION_DEPTH.get(age_band)


# PL-26 decision-density advisory on the fastest-finish path: the MAXIMUM nodes
# per decision, keyed on narrative style. JHM 2019 Table 4 measures a mean of
# 3.28 pages between decisions, but that corpus is CYOA prose paperbacks, so the
# anchor is a prose anchor and applying it to a gamebook is a category error: a
# numbered-section gamebook ends nearly every section in a choice by genre
# convention. Style-keying follows _ENDINGS_FRACTION and _WORDS_PER_NODE, which
# already split the same way.
#   - prose: sits above the 3.28 anchor with room, because one corpus in one band
#     cluster cannot justify a tight bound.
#   - gamebook: product-defined and tunable. No measured gamebook corpus backs
#     it; it exists so the rule stays silent on genre-faithful section density
#     rather than firing on every gamebook in the library.
#
# A ceiling only, deliberately. PL-26 exists to catch the corridor: a story that
# satisfies every PL-17 breadth floor while walking the reader past few or no
# choices. The symmetric low bound this started as had to go, because measuring
# density along a SHORTEST path is biased toward finding high density: a decision
# node has out-degree >= 2, so it is likelier to sit on a fast route than a
# linear node is, while JHM's 3.28 was measured corpus-wide. Comparing the two on
# the low side compares different quantities, the same category error the
# style-keying above fixes. A genuine "choice gauntlet" guard would have to
# measure whole-graph density instead; see AL-084 / UW-C28.
#
# Scale-invariant by construction: it constrains a ratio, not a count, so a
# 340-node long-form world and a 23-node picture book are judged on one axis.
# This is the density companion to PL-20, which bounds the same path's length but
# says nothing about how often the reader actually steers along it.
# SCOPE, since this used to describe itself as the ceiling and no longer is.
# The gamebook entry IS the gamebook ceiling. The prose entry is a FALLBACK
# only: since the Wave 3 per-band derivation, every configured band reads
# `_BAND_NODES_PER_DECISION_CEILING` below, so `["prose"]` is reachable solely
# for a band that table does not configure, or for an unrecognized
# narrative_style. Do not read 6.0 as "the prose ceiling"; read
# `_BAND_NODES_PER_DECISION_CEILING` for that.
# #ASSUME: data-integrity: this table is the single source for the gamebook PL-26
# ceiling and for the unconfigured-band fallback, keyed on narrative_style,
# anchored on Adams, Beckelhymer and Marr, Journal of Humanistic Mathematics
# 9(2), 2019, Table 4 (mean 3.28 pages between decisions). An unrecognized
# narrative_style is not an error: nodes_per_decision_ceiling below silently
# falls back to the prose value, so a typo'd or new style is graded against the
# wrong genre convention rather than failing loudly.
# #VERIFY: test_band_profile.py::
# test_prose_density_ceiling_sits_above_the_measured_anchor,
# ::test_gamebook_density_ceiling_is_tighter_than_prose, and
# ::test_unknown_style_density_falls_back_to_prose (the silent-default case).
_NODES_PER_DECISION_CEILING: dict[str, float] = {
    "prose": 6.0,
    "gamebook": 4.0,
}

# PL-26 per BAND, because the anchor is a page count and a node is not a page.
#
# The flat prose ceiling above is 6.0 NODES per decision against an anchor of
# 3.28 PAGES between decisions. Measured 2026-08-18, converting each band's
# ceiling into the anchor's own unit through _WORDS_PER_NODE at ~100 words to a
# CYOA page, one flat number spans 4.4x in the quantity it claims to bound:
#
#   3-5    240 words between decisions   0.73x the anchor
#   8-11   600 words                     1.83x
#   16+   1050 words                     3.20x
#
# So the same rule is tighter than the research at 3-5 and three times looser at
# 16+, and the ordering inverts on the real corpus (`UW-C277`).
#
# The fix holds the bound constant in WORDS rather than in nodes, which is the
# reader-facing quantity the rule is about: how much prose you meet between two
# choices. 8-11 keeps exactly its current value because the JHM corpus sits in
# the 8-11/10-13 reading range, so that is the calibrated band; every other band
# is derived from it. That preserves the deliberate looseness the flat value was
# chosen for (1.83x the anchor, "above the 3.28 anchor with room") instead of
# snapping every band onto the raw anchor, which would have tightened 16+ from
# 6.0 to 1.87 on one corpus in one band cluster.
# #ASSUME: data-integrity: derived, not transcribed; changing _WORDS_PER_NODE
# moves these. The gamebook style keeps its flat 4.0, which is product-defined
# and has no page anchor to convert.
# #VERIFY: test_band_profile.py::test_band_density_ceilings_hold_the_bound_in_words.
_BAND_NODES_PER_DECISION_CEILING: dict[str, float] = {
    "3-5": 15.0,
    "5-8": 8.57,
    "8-11": 6.0,
    "10-13": 6.0,
    "13-16": 4.29,
    "16+": 3.43,
}


def nodes_per_decision_ceiling(
    narrative_style: str, age_band: str | None = None
) -> float:
    """Return the PL-26 maximum nodes-per-decision for a narrative style.

    Args:
        narrative_style: ``"prose"`` or ``"gamebook"``.
        age_band: The story's band. When given and configured, a prose story is
            graded against the per-band ceiling that holds the bound constant in
            words; without it the flat prose value applies, which is the old
            band-blind behaviour.

    Returns:
        The advisory ceiling. A prose story with a configured band gets the
        per-band value; the flat prose entry is reached only for an unconfigured
        band or an unknown style, which is the whole of its remaining role.
    """
    if narrative_style == "gamebook":
        return _NODES_PER_DECISION_CEILING["gamebook"]
    if age_band is not None:
        band_ceiling = _BAND_NODES_PER_DECISION_CEILING.get(age_band)
        if band_ceiling is not None:
            return band_ceiling
    return _NODES_PER_DECISION_CEILING["prose"]


# PL-20 companion ceiling: how far the shortest satisfying path may exceed the
# cell's ``min_complete_floor`` before warning. JHM 2019 records a longest
# playthrough of 27.5 pages against a shortest of 11; that 2.5 ratio is the
# multiple used here, applied against the cell floor rather than as an absolute
# node count so it stays meaningful from a 10-node picture book to a 750-node
# gamebook. Tunable.
# #ASSUME: data-integrity: this is the single source for the ceiling multiple
# PL-20's arc ceiling, PL-25's ceiling escalation, and PL-25's hard limit all
# read; a change here moves all three at once. Anchored on Adams, Beckelhymer
# and Marr, Journal of Humanistic Mathematics 9(2), 2019, Table 4: the
# longest-vs-shortest playthrough ratio in the 40-book corpus is exactly
# 27.5 / 11 = 2.5.
# #VERIFY: test_band_profile.py::
# test_arc_ceiling_multiple_matches_the_measured_playthrough_ratio.
ARC_CEILING_MULTIPLE = 2.5


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
# SCOPE: this binds in the four gamebook cells and essentially nowhere else.
# Since Wave 3 (`UW-C283`) `breadth_scaled_floors` caps the scaled prose floor by
# the cell's own stated maximum from ADR-011 section 5, and that cap is the
# binding constraint in every prose cell, so the 0.15 here is a floor the cell
# bounds already dominate. The ADR gives the gamebook cells no ending numbers, so
# the gamebook entry is the only value still deciding a verdict on its own.
#
# The gamebook fraction was 0.25 until 2026-08-18, implementing ADR-011 section
# 5's ASSERTION that gamebook terminals run 25-35% of nodes. RULED 2026-08-18
# (owner): 0.12, from the only measurement taken in the units the floor is
# expressed in.
#
# Three floor-independent corpus points exist and they span fifteen-fold:
# Fighting Fantasy's *Warlock of Firetop Mountain* at ~0.8% (3 of 400,
# REPORTED), Project Aon's Lone Wolf #1 at 4.9% (17 of 350, our own 2026-08-02
# crawl), and a story-first gamebook drafted without the floor stated at 12.4%
# (31 of 250). The two published books are NOT commensurable with this rule:
# both kill the reader mainly through dice, so their graphs carry only the
# failures their authors chose to make structural. This format has no dice, so
# every failure it wants must be a terminal node. Their shares are a lower bound
# on what a diceless book needs, not a target. That leaves the diceless draft.
#
# A second measurement agrees on the direction. Our committed prose median is
# 20.1% over 54 skeletons, matching the breadth-form corpus (CYOA #53 at 19
# endings in 115 pages; JHM 2019's median 20 endings over ~90-120 nodes) it was
# calibrated against. Our committed gamebook median is 29.8% over 14, six times
# the length-form corpus this style is modelled on. Quest books end rarely and
# time-cave books end often, so 0.25 sitting ABOVE the prose fraction had the
# genre relationship backwards.
#
# PROVISIONAL, and the register row says so: the draft clears 0.12 by a single
# ending, so this is calibrated to the edge of an n=1 sample. A second diceless
# gamebook is what would settle it. Lowering the floor cannot break committed
# content (all 14 gamebooks sit at 27.6% or above, clearing 0.12 by at least 15
# points); the question it answers is only what ELSE to admit.
# #ASSUME: data-integrity: one number reaches six callers, including the
# generation prompt's "EXACTLY N endings" instruction via
# `story_requests/brief.py`. Two-tier grading (block low, advise high) was
# considered and rejected for exactly that reason: it would force each caller to
# pick a tier and reopen the prompt-versus-gate divergence `UW-C278`/`UW-C279`
# closed.
# #VERIFY: test_band_profile.py::test_gamebook_endings_fraction_admits_the_
# diceless_corpus_point and ::test_breadth_scaled_floors_gamebook_endings_higher.
# See `docs/planning/gamebook-thresholds-options.md` and `UW-C291`.
_ENDINGS_FRACTION: dict[str, float] = {"prose": 0.15, "gamebook": 0.12}
_DECISIONS_FRACTION = 0.08


# ADR-011 section 5's own per-cell endings column, as ``(min, max)`` counts.
# Prose cells only: the four gamebook cells state "many fails" and give no
# numbers, so they keep the fraction-only treatment.
#
# This exists because section 5 and section 6 disagree and PL-17 implemented only
# section 6. Measured 2026-08-18, PL-17's flat 0.15 floor applied at the TOP of a
# cell's node range against that cell's own stated maximum endings:
#
#   3-5/short     floor 4 vs ceiling 4   DEGENERATE (exactly one legal count)
#   3-5/medium    floor 7 vs ceiling 6   INVERTED
#   10-13/medium  floor 33 vs ceiling 32 INVERTED
#   10-13/long    floor 51 vs ceiling 48 INVERTED
#
# So a story authored to the top of three cells' own node envelopes could not
# satisfy the gate at all. The floor is now capped by this ceiling, which removes
# the inversion at zero cost to the catalog (measured: no committed skeleton
# changes verdict on the floor).
#
# The ceiling itself is NEW capability, not a tightening of an existing rule: the
# owner named "too many endings" as a real failure mode and no rule expressed it.
# It is advisory for now. The original young-band columns were suspect: applying
# them failed 7 committed skeletons, 5 of them at 3-5, including
# `the-last-blue-cup` which was authored to the strict bar. A ceiling that a
# fresh strict-bar skeleton violates is more likely miscalibrated than the
# skeleton is (`UW-C283`). The 2026-08-22 ADR-011 amendment (section 11 item 4,
# `UW-C327` audit) recalibrated the four young-band ceilings upward against the
# measured strict-bar shelf (shares 0.17-0.41; `the-big-cardboard-box` holds 18
# endings against the old cap of 6), and the rows below carry the amended values.
# #ASSUME: data-integrity: transcribed from ADR-011 section 5's table as amended
# 2026-08-22; the gamebook rows are deliberately absent rather than zero.
# #VERIFY: test_band_profile.py::test_cell_ending_bounds_match_the_adr_table and
# ::test_scaled_floor_never_exceeds_the_cell_ceiling.
_CELL_ENDING_BOUNDS: dict[tuple[str, str], tuple[int, int]] = {
    ("3-5", "short"): (2, 8),
    ("3-5", "medium"): (4, 18),
    ("5-8", "short"): (6, 16),
    ("5-8", "medium"): (10, 20),
    ("8-11", "short"): (12, 18),
    ("8-11", "medium"): (18, 28),
    ("8-11", "long"): (28, 40),
    ("10-13", "short"): (14, 22),
    ("10-13", "medium"): (22, 32),
    ("10-13", "long"): (32, 48),
    ("13-16", "medium"): (20, 32),
    ("13-16", "long"): (30, 48),
    ("16+", "medium"): (24, 40),
    ("16+", "long"): (36, 60),
}


def cell_ending_bounds(
    age_band: str, length: str | None, narrative_style: str
) -> tuple[int, int] | None:
    """Return ADR-011 section 5's ``(min, max)`` endings for a prose cell.

    Args:
        age_band: The story age band value.
        length: The declared length, or ``None`` for an unclassified story.
        narrative_style: ``"prose"`` or ``"gamebook"``.

    Returns:
        The cell's stated endings range, or ``None`` for a gamebook cell, an
        off-matrix cell, or a story with no declared length.
    """
    if length is None or narrative_style != "prose":
        return None
    return _CELL_ENDING_BOUNDS.get((age_band, length))


def breadth_scaled_floors(
    node_count: int, narrative_style: str, cell_ceiling: int | None = None
) -> tuple[int, int]:
    """Return ``(min_endings, min_decisions)`` scaled to a story's node count.

    Only a scale-classified production story uses these; the caller takes the
    ``max`` of the band-level floor and the scaled floor, so a small scale story
    never drops below its band minimum. An unknown style falls back to the prose
    ending fraction.

    Args:
        node_count: The total number of nodes in the story.
        narrative_style: ``"prose"`` or ``"gamebook"``.
        cell_ceiling: The cell's stated maximum endings, from
            :func:`cell_ending_bounds`. When given, the scaled endings floor is
            capped by it so the floor can never exceed the ceiling.

    Returns:
        The breadth-scaled ``(min_endings, min_decisions)`` floor pair.
    """
    endings_fraction = _ENDINGS_FRACTION.get(
        narrative_style, _ENDINGS_FRACTION["prose"]
    )
    min_endings = math.ceil(node_count * endings_fraction)
    min_decisions = math.ceil(node_count * _DECISIONS_FRACTION)
    if cell_ceiling is not None:
        # Never demand more endings than the cell's own stated maximum. Without
        # this the floor exceeded the ceiling in three cells and equalled it in a
        # fourth, so a story authored to the top of its own node envelope could
        # not pass. Capping costs the catalog nothing (measured).
        min_endings = min(min_endings, cell_ceiling)
    return min_endings, min_decisions
