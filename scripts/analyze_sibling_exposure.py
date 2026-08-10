#!/usr/bin/env python
"""Sibling-skeleton exposure analysis: how often does one CHILD repeat a tree?

    uv run python scripts/analyze_sibling_exposure.py               # full report
    uv run python scripts/analyze_sibling_exposure.py --section pools
    uv run python scripts/analyze_sibling_exposure.py --trials 50000

The question
------------
Three story-diversity pilots found that two stories filled from the SAME
skeleton read as "same adventure, new world" to a 10-13 reader. That finding
only justifies replacing skeletons if a real READER meets the same tree twice.
Recognition is a property of one reader's memory, so the unit of exposure is
the child, not the household: two siblings can each read a skeleton once with
no recognition event between them.

That distinction cuts both ways, and it is the analysis's spine:

- A skeleton is **consumable within a child** (the second read is the
  recognition event) but **reusable across children** (each new reader gets a
  fresh first read). Required catalog size therefore scales with per-child
  lifetime consumption inside a band, NOT with how many families sign up.
- The shipped anti-repeat weighting is scoped to the FAMILY, not the child.
  ``skeleton_match.recent_skeleton_usage`` filters on ``Storybook.family_id``
  over a twenty-row window, and ``diversity.history.load_family_history`` does
  the same; no query anywhere narrows prior ``skeleton_slug`` to the requesting
  child, even though ``story_request.profile_id``, ``storybook_assignment`` and
  ``reading_state`` all carry the per-child link. So the protection a child
  gets is diluted by their siblings' reading, and a child is simultaneously
  steered away from skeletons only a sibling has read.

The method
----------
1. **Pools.** Enumerate every ``(band, length, narrative_style)`` cell through
   the real ``generation.skeleton_match.candidates_for_cell``, so the counts
   reflect ``production_eligible``, the sidecar skip, the length wildcard, the
   style-aware-band rule (ADR-011), and the continuation exclusion (AL-045)
   exactly as selection sees them. Styles that do not partition a cell (every
   band below 13-16) are collapsed into one row rather than counted twice,
   matching ``diversity/incell.py``'s convention.
2. **Curves.** Simulate a family issuing N successive requests into the SAME
   cell, drawing each pick with the real ``select_skeleton_for_cell`` and the
   real weighting. History state is rebuilt between draws exactly as the
   production caller builds it (see ``_family_state``), including the
   twenty-row recency window. Reported per N: P(a child has met a repeat by
   their Nth request), the expected number of distinct skeletons THAT CHILD has
   seen, and the first N at which a repeat is more likely than not.
3. **Siblings.** The same curve with 1, 2 and 3 readers sharing the family
   history, run once under the shipped family scope and once under a
   child-scoped counterfactual, so the cost of the scoping choice is a number
   rather than an argument.
4. **Bands and sizing.** Per-band catalog counts, cell structure and the tenure
   implied by the band labels, then the catalog a single child's consumption
   implies at several reading rates, reported both per band and per cell
   (cell matching forbids cross-length and cross-style substitution, so a band
   total that is large enough can still leave a cell starved).
5. **Counterfactual.** Grow a real pool with synthetic candidates, holding the
   weighting fixed, and find the smallest pool that pushes the
   more-likely-than-not repeat past a child's 5th, 10th and 25th request. That
   is the catalog size a "grow the catalog" program would have to buy.

Every number here is stochastic: it is a Monte Carlo estimate over ``--trials``
independent families, reproducible under ``--seed`` but not exact. The standard
error on a probability estimate is at most ``0.5 / sqrt(trials)``.

Two regimes bracket the theme signal, which the simulation cannot know in
advance for a real family:

- ``distinct-theme``: every request is thematically unrelated to the family's
  prior stories, so ``similar_usage`` stays all-zero and only the recency
  penalty applies. This is the selector's WEAKEST anti-repeat setting.
- ``same-theme``: every request is similar to every prior story (a child who
  keeps asking for dragons), so ``similar_usage`` equals the recency counts and
  the ``_THEME_REUSE_PENALTY`` multiplier bites on every prior pick. This is the
  selector's STRONGEST anti-repeat setting.

Real families sit between the two, so the two curves bound the true rate.

Length demand is NOT uniform
----------------------------
Sections 2-5 above answer "how fast does ONE cell wear out". They implicitly
assumed a child's requests either all land in one cell or spread evenly over a
band's length tiers. The owner has corrected that: demand concentrates on
MEDIUM. Few guardians ask for a very short or a very long book; the bulk sit in
the middle. The catalog is flat (3 or 4 skeletons in every populated cell), so a
peaked demand shape means the medium cell is the binding constraint and burns
out first while short and long sit under-used.

The ``demand``, ``demand-sizing`` and ``budget`` sections model that, over a
named length-demand regime (``--length-demand``):

- ``flat``                      1/3, 1/3, 1/3   (the implicit prior model)
- ``medium-weighted``           0.25/0.60/0.15
- ``strongly-medium-weighted``  0.15/0.75/0.10
- ``current-default-dominated`` 0.70/0.25/0.05

EVERY ONE OF THESE IS AN ASSUMPTION, NOT A FINDING. This deployment has
published no story yet, so no request-length distribution has been measured.
The four regimes are a sweep whose job is to show how much the answer moves
with the demand shape; they must be replaced by a ``select length, count(*)
from story_request group by length`` once real requests exist.

Two structural facts drive most of what these sections report:

- Not every band has all three tiers. ADR-011 section 5's master cell table
  declares eighteen production cells: 3-5 and 5-8 "cap at Medium" and have no
  long tier, and 13-16 and 16+ start at Medium and have no short tier. The
  committed catalog populates exactly those eighteen. So a band's demand is
  renormalized onto the tiers ADR-011 gives it (``--length-demand-scope
  declared``, the default): a missing 3-5 long cell is a DESIGN DECISION, not a
  catalog gap, and must not be sized as one.

  ``--length-demand-scope all-lengths`` applies the regime raw instead and
  reports the mass landing on an undeclared tier as "unservable". That is not a
  catalog measurement, it is an INTAKE measurement: nothing in the request path
  enforces ADR-011's band-by-length rule. ``StoryRequestSpecBody`` validates
  band-by-STYLE (gamebook is teen-only) and nothing else, and both length
  ``<select>``s (guardian intake and the approve strip) offer all three tiers
  for every band, so an adult can approve a "long" 3-5 book. That request 422s
  much later, at the admin authoring-plan step, on the empty-cell guard.
- Cross-length substitution is impossible. ``skeleton_matches_cell`` treats only
  a NULL ``length`` as a wildcard, and no production-eligible skeleton on disk
  declares a NULL length, so a medium request can never be served by a short or
  long skeleton. Cell shortfalls therefore do not net out against cell
  surpluses.
"""

from __future__ import annotations

import argparse
import collections
import math
import random
import statistics
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from cyo_adventure.generation.skeleton_match import (
    _RECENT_WINDOW,  # pyright: ignore[reportPrivateUsage]
    candidates_for_cell,
    select_skeleton_for_cell,
    theme_overlap_for_candidates,
)
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

# A cell with fewer candidates than this is called out in the pool table: below
# it, the in-cell pick has almost nothing to rotate through. A reporting
# threshold only; nothing in the selector knows about it.
_THIN_CELL = 5

# Cells the curve section reports by default: the three 10-13 cells (the band
# the recognition pilots ran in, and the only band whose every length tier is
# populated) plus one 3-5 cell as a young-band control.
_DEFAULT_FOCUS: tuple[tuple[str, str, str], ...] = (
    ("10-13", "short", "prose"),
    ("10-13", "medium", "prose"),
    ("10-13", "long", "prose"),
    ("3-5", "short", "prose"),
)

# Counterfactual targets: push the first more-likely-than-not repeat PAST this
# request index, counted PER CHILD. 5 is a child's first year at roughly one
# story a season; 10 is a heavier reader's year; 25 is a multi-year tenure in
# one cell.
_COUNTERFACTUAL_TARGETS: tuple[int, ...] = (5, 10, 25)

# Upper bound on the counterfactual pool search, so an unreachable target ends
# the scan instead of running forever.
_MAX_SYNTHETIC_POOL = 600

# Which history the selector is shown. SCOPE_FAMILY is what ships today
# (skeleton_match.recent_skeleton_usage and diversity.history.load_family_history
# both filter on Storybook.family_id and nothing narrower). SCOPE_CHILD is the
# counterfactual: the same weighting fed only the requesting child's history.
SCOPE_FAMILY = "family"
SCOPE_CHILD = "child"

# Sibling counts the per-child section reports. 1 is the degenerate case where
# family scope and child scope coincide; 3 is a large-but-ordinary family.
_SIBLING_COUNTS: tuple[int, ...] = (1, 2, 3)

# Per-child reading rates (approved stories per month) the sizing table sweeps.
# Not measured from production: this deployment has no usage data yet, so the
# table is a sweep and the reader picks the column, per the plan's own rule that
# an unmeasured number is stated as a range rather than asserted as one value.
_READING_RATES: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0)

# Months a child spends inside a band, read off the band's own label
# (storybook.models.AgeBand). "16+" is open-ended; it is charged the same three
# years as the other upper bands so the table has a finite entry, and that
# choice is stated in the report rather than buried here.
_OPEN_BAND_MONTHS = 36

# Length-demand regimes: ``{name: (short, medium, long)}``, each a share of one
# child's requests inside one band.
#
# #CRITICAL: data-integrity: NONE of these is measured. This deployment has
# published no story, so no length distribution exists to fit. They are a sweep
# whose purpose is to show the SENSITIVITY of the catalog bill to the demand
# shape, and every table built from them says so in its own header.
# #VERIFY: replace with the observed distribution
# (``select length, count(*) from story_request where length is not null group
# by length``) as soon as production requests exist; the CLI already accepts an
# arbitrary triple through --length-demand-custom, so fitting the measurement
# needs no code change.
_LENGTH_REGIMES: dict[str, tuple[float, float, float]] = {
    # The prior model: demand spreads evenly over a band's length tiers.
    "flat": (1 / 3, 1 / 3, 1 / 3),
    # The owner's correction: the bulk of requests sit in the middle.
    "medium-weighted": (0.25, 0.60, 0.15),
    # The same correction, harder.
    "strongly-medium-weighted": (0.15, 0.75, 0.10),
    # What today's defaults would produce if adults mostly left length unset:
    # both null-length paths steer non-teen requests to "short" (see
    # story_requests/authoring_plan.py::_length_of and the hardcoded
    # Length.SHORT in api/story_requests.py's kid auto-approve branch).
    "current-default-dominated": (0.70, 0.25, 0.05),
}

# The length axis, in report order; matches the tuples above.
_LENGTH_ORDER: tuple[str, ...] = ("short", "medium", "long")

# Per-child reading rates the demand-weighted sizing table sweeps. A subset of
# _READING_RATES: the demand-weighted table is per CELL rather than per band, so
# it is several times taller and the 4.0 column buys nothing the 2.0 column does
# not already show.
_DEMAND_RATES: tuple[float, ...] = (0.5, 1.0, 2.0)

# How many successive per-child requests the mixed-cell band simulation and the
# budget optimizer look ahead. 30 covers a heavy reader's whole band tenure
# (2 stories/month for 3 years is 72, but every curve here has long since
# crossed 0.5 by 30).
_DEMAND_HORIZON = 30

# Fixed authoring budgets the budget section reports, in new skeletons per band.
_BUDGET_SIZES: tuple[int, ...] = (6, 12, 24)


@dataclass(frozen=True, slots=True)
class Cell:
    """One ``(band, length, style)`` cell and its real candidate pool.

    Attributes:
        band: The age band.
        length: The length tier.
        style: The narrative style, or ``"prose+gamebook"`` when style does not
            partition this band (every band below 13-16).
        slugs: The production-eligible in-cell candidate slugs, in the order
            ``candidates_for_cell`` returns them.
    """

    band: str
    length: str
    style: str
    slugs: tuple[str, ...]

    @property
    def label(self) -> str:
        """Return the ``band/length/style`` cell label."""
        return f"{self.band}/{self.length}/{self.style}"


@dataclass(frozen=True, slots=True)
class ExposureCurve:
    """Monte Carlo per-CHILD exposure estimates for one pool under one regime.

    Attributes:
        pool_size: How many candidates the family was drawing from.
        trials: How many independent simulated families were run.
        children: How many readers shared that family's history.
        scope: Which history the selector saw, :data:`SCOPE_FAMILY` or
            :data:`SCOPE_CHILD`.
        repeat_probability: ``P(a given child has met a repeated skeleton by
            their Nth request)`` for ``N = 1 .. requests``; index 0 is request 1
            and is always 0.0.
        expected_distinct: Expected count of distinct skeletons ONE child has
            seen by their Nth request, same indexing.
        first_more_likely_than_not: The smallest ``N`` whose repeat probability
            reaches 0.5, or ``None`` when no simulated N did.
    """

    pool_size: int
    trials: int
    children: int
    scope: str
    repeat_probability: tuple[float, ...]
    expected_distinct: tuple[float, ...]
    first_more_likely_than_not: int | None


def _dedup_styles(band: str, length: str) -> Iterator[Cell]:
    """Yield the distinct cells of one ``(band, length)`` row.

    Narrative style partitions a cell only at 13-16 and 16+; below those,
    ``skeleton_matches_cell`` ignores style and both styles return an identical
    candidate list. Yielding one collapsed row keeps a lower-band cell from
    being counted (and later simulated) twice.

    Args:
        band: The age band value.
        length: The length tier value.

    Yields:
        Cell: One entry per distinct candidate list in this row.
    """
    by_slugs: dict[tuple[str, ...], list[str]] = {}
    for style in NarrativeStyle:
        slugs = tuple(candidates_for_cell(band, length, style.value))
        by_slugs.setdefault(slugs, []).append(style.value)
    for slugs, styles in by_slugs.items():
        label = styles[0] if len(styles) == 1 else "+".join(sorted(styles))
        yield Cell(band=band, length=length, style=label, slugs=slugs)


def iter_cells() -> Iterator[Cell]:
    """Yield every ``(band, length, style)`` cell the selector recognizes.

    Yields:
        Cell: Every cell, including the empty ones (an empty cell is a real
            answer: that request shape 422s on the auto-pick path).
    """
    for band in AgeBand:
        for length in Length:
            yield from _dedup_styles(band.value, length.value)


def find_cell(band: str, length: str, style: str) -> Cell | None:
    """Return the cell matching a ``band/length/style`` triple, or None.

    Args:
        band: The age band value.
        length: The length tier value.
        style: A concrete narrative style value ("prose"/"gamebook"); it is
            matched against the possibly-collapsed cell label.

    Returns:
        Cell | None: The matching cell, or ``None`` when the triple names no
            cell the selector recognizes.
    """
    for cell in iter_cells():
        if (
            cell.band == band
            and cell.length == length
            and style in cell.style.split("+")
        ):
            return cell
    return None


def _family_state(
    history: Sequence[str], candidates: Sequence[str], *, similar_reuse: bool
) -> tuple[dict[str, int], dict[str, int] | None]:
    """Rebuild the two history inputs the production caller passes to selection.

    ``recent_usage`` mirrors ``skeleton_match.recent_skeleton_usage``: a count
    per slug over the family's most recent ``_RECENT_WINDOW`` storybook_version
    rows, every status counted, one row per authored version.

    ``similar_usage`` mirrors ``diversity.query.score_history``'s
    ``similar_count_per_slug``: a count, per in-cell candidate, of the family's
    recent history entries whose theme containment clears ``tau_theme``. Under
    ``similar_reuse`` every prior story counts as similar (the same-theme
    regime); otherwise none do and the map is all-zero, which
    ``_blended_weight`` reduces exactly to ``_weight``.

    Args:
        history: The family's prior picks, oldest first.
        candidates: The in-cell candidate slugs.
        similar_reuse: Whether prior stories count as similar-theme.

    Returns:
        The ``(recent_usage, similar_usage)`` pair to pass to
        ``select_skeleton_for_cell``.
    """
    window = list(history[-_RECENT_WINDOW:])
    recent = collections.Counter(window)
    recent_usage = dict(recent)
    if not similar_reuse:
        return recent_usage, dict.fromkeys(candidates, 0)
    return recent_usage, {slug: recent.get(slug, 0) for slug in candidates}


def simulate_exposure(
    candidates: Sequence[str],
    *,
    trials: int,
    requests: int,
    rng: random.Random,
    similar_reuse: bool = False,
    theme_overlap: Mapping[str, float] | None = None,
    children: int = 1,
    scope: str = SCOPE_FAMILY,
) -> ExposureCurve:
    """Estimate the per-CHILD sibling-exposure curve for one pool.

    Each trial is one family of ``children`` readers taking turns, round robin,
    at ``requests`` requests each into the SAME cell. Every draw goes through
    the real ``skeleton_match.select_skeleton_for_cell`` with history state
    rebuilt by :func:`_family_state`, so the weighting under test is the shipped
    weighting and not a restatement of it.

    The measured event is per reader: a repeat is a skeleton THIS child has
    already read, regardless of what a sibling read. ``children=1`` collapses
    to the single-reader case and makes both scopes identical.

    Args:
        candidates: The in-cell candidate slugs; must be non-empty.
        trials: How many independent families to simulate.
        requests: How many same-cell requests EACH child makes.
        rng: The random source, injected so a seeded run is reproducible.
        similar_reuse: When True, run the same-theme regime (every prior story
            counts as similar); when False, the distinct-theme regime.
        theme_overlap: Optional ``{slug: bonus}`` premise-overlap map, passed
            straight through to selection. ``None`` reproduces the pre-W2.2
            recency/similarity-only weighting.
        children: How many readers share the family history.
        scope: :data:`SCOPE_FAMILY` feeds selection the whole family's history
            (what the code does today) or :data:`SCOPE_CHILD` feeds it only the
            requesting child's history (the counterfactual the code does NOT
            implement).

    Returns:
        ExposureCurve: The estimated per-child curve.

    Raises:
        ValueError: If ``candidates`` is empty, if ``trials``/``requests``/
            ``children`` is below 1, or if ``scope`` is not a known scope.
    """
    if not candidates:
        msg = "simulate_exposure requires a non-empty candidate pool"
        raise ValueError(msg)
    if trials < 1 or requests < 1 or children < 1:
        msg = "trials, requests and children must all be at least 1"
        raise ValueError(msg)
    if scope not in {SCOPE_FAMILY, SCOPE_CHILD}:
        msg = f"unknown history scope {scope!r}"
        raise ValueError(msg)

    slugs = list(candidates)
    repeat_by: list[int] = [0] * requests
    distinct_total: list[int] = [0] * requests
    observations = trials * children

    for _ in range(trials):
        family_history: list[str] = []
        child_history: list[list[str]] = [[] for _ in range(children)]
        seen: list[set[str]] = [set() for _ in range(children)]
        repeated = [False] * children
        for index in range(requests):
            for child in range(children):
                history = (
                    family_history if scope == SCOPE_FAMILY else child_history[child]
                )
                recent_usage, similar_usage = _family_state(
                    history, slugs, similar_reuse=similar_reuse
                )
                selection = select_skeleton_for_cell(
                    slugs,
                    recent_usage,
                    rng,
                    similar_usage=similar_usage,
                    theme_overlap=theme_overlap,
                )
                if selection.slug in seen[child]:
                    repeated[child] = True
                seen[child].add(selection.slug)
                family_history.append(selection.slug)
                child_history[child].append(selection.slug)
                if repeated[child]:
                    repeat_by[index] += 1
                distinct_total[index] += len(seen[child])

    probabilities = tuple(count / observations for count in repeat_by)
    expected = tuple(total / observations for total in distinct_total)
    crossing = next(
        (
            index + 1
            for index, probability in enumerate(probabilities)
            if probability >= 0.5
        ),
        None,
    )
    return ExposureCurve(
        pool_size=len(slugs),
        trials=trials,
        children=children,
        scope=scope,
        repeat_probability=probabilities,
        expected_distinct=expected,
        first_more_likely_than_not=crossing,
    )


def pad_pool(base: Sequence[str], size: int) -> list[str]:
    """Return ``base`` grown to ``size`` with synthetic candidate slugs.

    Args:
        base: The real in-cell candidate slugs.
        size: The target pool size; must be at least ``len(base)``.

    Returns:
        list[str]: The real slugs followed by ``size - len(base)`` synthetic
            ones. A synthetic candidate carries no recency history and no theme
            overlap, so it enters the weighting exactly as an unused real
            skeleton would.

    Raises:
        ValueError: If ``size`` is smaller than the real pool.
    """
    if size < len(base):
        msg = "pad_pool cannot shrink a pool"
        raise ValueError(msg)
    extra = [f"synthetic-{index:03d}" for index in range(size - len(base))]
    return [*base, *extra]


def required_pool_size(
    base: Sequence[str],
    *,
    target_request: int,
    trials: int,
    rng: random.Random,
    similar_reuse: bool = False,
    children: int = 1,
    scope: str = SCOPE_FAMILY,
) -> int | None:
    """Return the smallest pool whose first likely repeat lands past a request.

    Returns the smallest pool size whose estimated
    ``P(repeat by target_request)`` is below 0.5, i.e. the first size at which a
    repeat is still less likely than not at that request index.

    ``P(repeat by N)`` is monotonically decreasing in pool size (adding an
    unused candidate can only spread the draw), so the search doubles to bracket
    the answer and then bisects, rather than scanning every size. The estimate is
    stochastic, so a reported size can be off by one when the true crossing sits
    within Monte Carlo noise of 0.5; raise ``trials`` to tighten it.

    Args:
        base: The real in-cell candidate slugs.
        target_request: The per-child request index the first likely repeat
            must clear.
        trials: Trials per candidate pool size.
        rng: The random source.
        similar_reuse: Which regime to hold while enlarging the pool.
        children: How many readers share the family history.
        scope: Which history the selector sees.

    Returns:
        int | None: The smallest sufficient pool size, or ``None`` when no pool
            up to :data:`_MAX_SYNTHETIC_POOL` reaches the target.
    """

    def is_sufficient(size: int) -> bool:
        curve = simulate_exposure(
            pad_pool(base, size),
            trials=trials,
            requests=target_request,
            rng=rng,
            similar_reuse=similar_reuse,
            children=children,
            scope=scope,
        )
        return curve.repeat_probability[-1] < 0.5

    # A pool smaller than the target request count repeats with certainty by
    # pigeonhole, so the search need never evaluate one.
    low = max(len(base), target_request, 1)
    if is_sufficient(low):
        return low
    high = low
    while high < _MAX_SYNTHETIC_POOL:
        high = min(high * 2, _MAX_SYNTHETIC_POOL)
        if is_sufficient(high):
            break
    else:
        return None
    while high - low > 1:
        middle = (low + high) // 2
        if is_sufficient(middle):
            high = middle
        else:
            low = middle
    return high


@dataclass(frozen=True, slots=True)
class BandProfile:
    """One band's catalog shape and the tenure a child spends inside it.

    Attributes:
        band: The age band value.
        tenure_months: Months a child sits in the band, from the band's own
            label; the open-ended top band is charged
            :data:`_OPEN_BAND_MONTHS`.
        populated_cells: The band's cells that hold at least one candidate.
        empty_cells: The band's cells that hold none.
        skeletons: Distinct production-eligible skeletons across the band's
            cells (a skeleton belongs to exactly one cell, so this is a sum).
    """

    band: str
    tenure_months: int
    populated_cells: tuple[Cell, ...]
    empty_cells: tuple[Cell, ...]
    skeletons: int


def band_tenure_months(band: str) -> int:
    """Return the months a child spends in a band, from the band label.

    ``AgeBand`` values are the tenure model: "3-5" is ages 3 up to 5, so two
    years; "16+" is open-ended and is charged :data:`_OPEN_BAND_MONTHS`. Nothing
    in the code declares a tenure, so this derives it from the only structural
    statement that exists rather than inventing a product number.

    Args:
        band: The age band value.

    Returns:
        int: Tenure in months.
    """
    if band.endswith("+"):
        return _OPEN_BAND_MONTHS
    low, _, high = band.partition("-")
    return (int(high) - int(low)) * 12


def band_profiles() -> list[BandProfile]:
    """Return the catalog shape and tenure of every band.

    Returns:
        list[BandProfile]: One entry per ``AgeBand``, in band order.
    """
    by_band: dict[str, list[Cell]] = collections.defaultdict(list)
    for cell in iter_cells():
        by_band[cell.band].append(cell)
    profiles: list[BandProfile] = []
    for band in AgeBand:
        cells = by_band[band.value]
        populated = tuple(cell for cell in cells if cell.slugs)
        profiles.append(
            BandProfile(
                band=band.value,
                tenure_months=band_tenure_months(band.value),
                populated_cells=populated,
                empty_cells=tuple(cell for cell in cells if not cell.slugs),
                skeletons=sum(len(cell.slugs) for cell in populated),
            )
        )
    return profiles


def window_coverage(
    children: int, stories_per_month: float, tenure_months: int
) -> float:
    """Return the share of a child's band reading the recency window still sees.

    ``skeleton_match._RECENT_WINDOW`` holds the family's last twenty
    ``storybook_version`` rows, family-scoped. A family of ``children`` readers
    fills that window ``children`` times faster, so the window retains only
    ``_RECENT_WINDOW / children`` of any one child's own stories. Measured
    against that child's whole consumption inside the band, this is the fraction
    of their own reading that can still de-weight a repeat; everything older is
    invisible to selection, and a skeleton the child read early in the band can
    be redrawn at full weight.

    Note the rate cancels: a faster reader produces history faster but also
    consumes more, so coverage depends only on the window, the sibling count,
    and the band lifetime.

    Args:
        children: Readers sharing the family history.
        stories_per_month: The child's approved-story rate.
        tenure_months: Months the child spends in the band.

    Returns:
        float: Coverage in ``[0, 1]``; ``1.0`` when the child's whole band
            consumption fits inside their share of the window.
    """
    lifetime = lifetime_stories(stories_per_month, tenure_months)
    if lifetime < 1:
        return 1.0
    return min(1.0, (_RECENT_WINDOW / children) / lifetime)


def lifetime_stories(stories_per_month: float, tenure_months: int) -> int:
    """Return how many stories one child consumes inside one band.

    Args:
        stories_per_month: The child's approved-story rate.
        tenure_months: Months the child spends in the band.

    Returns:
        int: Stories, rounded up: a partial story is still a request that must
            be served by some skeleton.
    """
    return math.ceil(stories_per_month * tenure_months)


def required_per_cell(lifetime: int, cells: int) -> int:
    """Return the per-cell catalog one child's band consumption implies.

    Under the owner's premise that a skeleton is consumable once per child, a
    child who reads ``lifetime`` stories in a band whose demand spreads evenly
    over ``cells`` cells needs ``ceil(lifetime / cells)`` skeletons IN EACH
    cell. Cross-cell substitution is impossible for the shipped catalog: every
    production-eligible skeleton declares a concrete length, and
    ``skeleton_matches_cell`` only treats a NULL length as a wildcard, so a
    short request can never be served by a medium skeleton.

    Args:
        lifetime: Stories the child consumes in the band.
        cells: How many populated cells the band's demand spreads over.

    Returns:
        int: Skeletons required per cell; ``lifetime`` itself when the band has
            no populated cell to spread over.
    """
    if cells < 1:
        return lifetime
    return math.ceil(lifetime / cells)


@dataclass(frozen=True, slots=True)
class DemandCell:
    """One cell plus the share of a band's requests that lands in it.

    Attributes:
        cell: The cell itself, empty pool included (an empty cell with a
            non-zero share is the single most important row in the table: that
            share of the band's requests cannot be served at all).
        share: The cell's share of one child's requests inside the band, in
            ``[0, 1]``; the shares of a band's cells sum to 1.
    """

    cell: Cell
    share: float

    @property
    def pool_size(self) -> int:
        """Return how many skeletons this cell holds today."""
        return len(self.cell.slugs)


def length_demand(name: str) -> dict[str, float]:
    """Return a named length-demand regime as a ``{length: share}`` map.

    Args:
        name: A key of :data:`_LENGTH_REGIMES`.

    Returns:
        dict[str, float]: Share per length value, summing to 1.

    Raises:
        KeyError: If the regime is not one of the named ones.
    """
    return dict(zip(_LENGTH_ORDER, _LENGTH_REGIMES[name], strict=True))


def parse_length_demand(raw: str) -> dict[str, float]:
    """Parse a ``short,medium,long`` CLI weight triple into a normalized map.

    Weights need not sum to 1; they are normalized, so ``25,60,15`` and
    ``0.25,0.60,0.15`` mean the same thing.

    Args:
        raw: The raw argument value.

    Returns:
        dict[str, float]: Share per length value, summing to 1.

    Raises:
        argparse.ArgumentTypeError: If the value is not three non-negative
            numbers with a positive total.
    """
    parts = raw.split(",")
    if len(parts) != len(_LENGTH_ORDER):
        msg = f"expected short,medium,long, got {raw!r}"
        raise argparse.ArgumentTypeError(msg)
    try:
        weights = [float(part) for part in parts]
    except ValueError as error:
        msg = f"length demand weights must be numbers, got {raw!r}"
        raise argparse.ArgumentTypeError(msg) from error
    if not all(math.isfinite(weight) for weight in weights):
        msg = f"length demand weights must be finite: {raw!r}"
        raise argparse.ArgumentTypeError(msg)
    if any(weight < 0 for weight in weights) or sum(weights) <= 0:
        msg = f"length demand weights must be non-negative and not all zero: {raw!r}"
        raise argparse.ArgumentTypeError(msg)
    total = sum(weights)
    return {
        length: weight / total
        for length, weight in zip(_LENGTH_ORDER, weights, strict=True)
    }


def band_cells(band: str) -> list[Cell]:
    """Return every cell of one band, empty cells included.

    Args:
        band: The age band value.

    Returns:
        list[Cell]: The band's cells in ``Length`` order; a length whose two
            styles share a candidate list yields one collapsed cell, and the
            two teen bands yield two cells per populated length.
    """
    return [cell for cell in iter_cells() if cell.band == band]


def declared_lengths(band: str) -> tuple[str, ...]:
    """Return the length tiers ADR-011 declares production cells for in a band.

    ADR-011 section 5's master cell table lists exactly eighteen production
    cells: 3-5 and 5-8 "cap at Medium" (no long tier at all), and 13-16 and 16+
    start at Medium (no short tier), with style splitting each of their
    populated lengths in two. The committed catalog holds a skeleton in every
    one of those eighteen and in none outside them, so reading legality off the
    catalog and reading it off the ADR give the same answer today.

    That equality is not a coincidence to rely on silently: it is asserted by
    ``test_the_catalogs_populated_cells_are_exactly_the_adr_011_cells``, so if
    the two ever diverge a test says so rather than a table quietly changing
    meaning.

    Args:
        band: The age band value.

    Returns:
        tuple[str, ...]: The band's declared length tiers, in
            :data:`_LENGTH_ORDER`.
    """
    populated = {cell.length for cell in band_cells(band) if cell.slugs}
    return tuple(length for length in _LENGTH_ORDER if length in populated)


def cell_demand(
    band: str, weights: Mapping[str, float], *, declared_only: bool = True
) -> list[DemandCell]:
    """Spread a length-demand regime over one band's cells.

    A length's share is split evenly across the cells that length resolves to.
    That matters only for 13-16 and 16+, where narrative style partitions each
    populated length into a prose cell and a gamebook cell.

    #ASSUME: data-integrity: the even prose/gamebook split is an assumption of
    exactly the same standing as the length regime itself. Nothing measures
    style demand either, and ADR-011 offers no expectation, so an even split is
    the least-committed choice rather than a claim about teen readers.
    #VERIFY: replace alongside the length distribution once
    ``story_request.narrative_style`` has production rows to count.

    Args:
        band: The age band value.
        weights: ``{length: share}``, from :func:`length_demand` or
            :func:`parse_length_demand`.
        declared_only: When True (the default and the correct sizing model),
            the regime is renormalized onto the band's :func:`declared_lengths`,
            so a 3-5 child never "asks for long": ADR-011 caps that band at
            Medium, so a long 3-5 cell is not a catalog gap and must not be
            sized as one. When False, the regime is applied raw across all
            three tiers and the mass landing on an undeclared tier shows up as
            unservable demand, which is how the report quantifies the missing
            band-by-length intake validation (nothing in
            ``StoryRequestSpecBody`` or either length ``<select>`` stops an
            adult picking a tier their band has no cell for).

    Returns:
        list[DemandCell]: One entry per cell of the band, shares summing to 1
            (or to less than 1 only if ``weights`` itself does).
    """
    cells = band_cells(band)
    allowed = set(declared_lengths(band)) if declared_only else set(_LENGTH_ORDER)
    total = sum(weights.get(length, 0.0) for length in allowed) or 1.0
    demand: list[DemandCell] = []
    for length in _LENGTH_ORDER:
        matching = [cell for cell in cells if cell.length == length]
        if not matching:
            continue
        raw = weights.get(length, 0.0) if length in allowed else 0.0
        share = (raw / total if declared_only else raw) / len(matching)
        demand.extend(DemandCell(cell=cell, share=share) for cell in matching)
    return demand


def binding_cell(demand: Sequence[DemandCell]) -> DemandCell | None:
    """Return the cell that exhausts first: the highest demand-per-skeleton.

    The binding constraint is not the thinnest cell and not the busiest cell but
    the one with the worst ``share / pool`` ratio, because that is the cell a
    child's requests revisit most times per available skeleton. A cell with a
    non-zero share and an EMPTY pool is infinitely binding and always wins.

    Args:
        demand: The band's cells and shares.

    Returns:
        DemandCell | None: The binding cell, or ``None`` when no cell carries
            demand.
    """
    live = [entry for entry in demand if entry.share > 0]
    if not live:
        return None
    return max(
        live,
        key=lambda entry: (
            math.inf if entry.pool_size == 0 else entry.share / entry.pool_size
        ),
    )


@dataclass(frozen=True, slots=True)
class BandDemandCurve:
    """Per-CHILD exposure across a whole band under one length-demand regime.

    Attributes:
        band: The age band value.
        regime: The length-demand regime name.
        trials: How many independent simulated families were run.
        children: How many readers shared the family history.
        repeat_probability: ``P(this child has met a repeated skeleton by their
            Nth request)`` for ``N = 1 .. requests``.
        expected_distinct: Expected count of distinct skeletons ONE child has
            seen by their Nth request.
        expected_unservable: Expected count of this child's first N requests
            that named an EMPTY cell and therefore could not be served at all.
        first_more_likely_than_not: Smallest ``N`` whose repeat probability
            reaches 0.5, or ``None`` when no simulated N did.
        binding: Label of the binding cell (:func:`binding_cell`), or ``"-"``.
    """

    band: str
    regime: str
    trials: int
    children: int
    repeat_probability: tuple[float, ...]
    expected_distinct: tuple[float, ...]
    expected_unservable: tuple[float, ...]
    first_more_likely_than_not: int | None
    binding: str


def _pick_index(shares: Sequence[float], draw: float) -> int:
    """Return the index a uniform ``draw`` selects from a share vector.

    Args:
        shares: Non-negative shares summing to (approximately) 1.
        draw: A uniform draw in ``[0, 1)``.

    Returns:
        int: The selected index; the last index with a positive share when
            floating-point drift leaves the draw past the final boundary.
    """
    cumulative = 0.0
    last = 0
    for index, share in enumerate(shares):
        if share > 0:
            last = index
        cumulative += share
        if draw < cumulative:
            return index
    return last


def simulate_band_exposure(
    demand: Sequence[DemandCell],
    *,
    trials: int,
    requests: int,
    rng: random.Random,
    similar_reuse: bool = False,
    children: int = 1,
    scope: str = SCOPE_FAMILY,
    regime: str = "custom",
) -> BandDemandCurve:
    """Estimate a child's exposure across a whole band under non-uniform demand.

    This is :func:`simulate_exposure` with the single-cell assumption removed.
    Each request first draws a CELL from the demand shares, then draws a
    skeleton from that cell through the real
    ``skeleton_match.select_skeleton_for_cell``, with the family's recency
    history rebuilt by :func:`_family_state` exactly as the single-cell
    simulation does. The history is deliberately NOT partitioned by cell:
    ``recent_skeleton_usage`` reads the family's last ``_RECENT_WINDOW``
    storybook_version rows whatever cell produced them, so a request in one cell
    does spend window room that would otherwise protect another. Slugs from
    other cells simply never appear in this cell's candidate list, so they enter
    the weighting as the production caller's dict does: present but unmatched.

    A request that draws an EMPTY cell is counted as unservable and produces no
    skeleton: on the auto-pick path that request is a 422, not a repeat. It
    still consumes a request index, because the child did make it.

    Args:
        demand: The band's cells and shares, from :func:`cell_demand`.
        trials: How many independent families to simulate.
        requests: How many requests EACH child makes into the band.
        rng: The random source, injected so a seeded run is reproducible.
        similar_reuse: Whether to run the same-theme regime.
        children: How many readers share the family history.
        scope: :data:`SCOPE_FAMILY` (shipped) or :data:`SCOPE_CHILD`.
        regime: The regime name, carried onto the returned curve for reporting.

    Returns:
        BandDemandCurve: The estimated per-child curve for the whole band.

    Raises:
        ValueError: If ``demand`` carries no positive share, if
            ``trials``/``requests``/``children`` is below 1, or if ``scope`` is
            not a known scope.
    """
    shares = [entry.share for entry in demand]
    if not demand or sum(shares) <= 0:
        msg = "simulate_band_exposure requires at least one cell with demand"
        raise ValueError(msg)
    if trials < 1 or requests < 1 or children < 1:
        msg = "trials, requests and children must all be at least 1"
        raise ValueError(msg)
    if scope not in {SCOPE_FAMILY, SCOPE_CHILD}:
        msg = f"unknown history scope {scope!r}"
        raise ValueError(msg)

    pools = [list(entry.cell.slugs) for entry in demand]
    repeat_by: list[int] = [0] * requests
    distinct_total: list[int] = [0] * requests
    unservable_total: list[int] = [0] * requests
    observations = trials * children

    for _ in range(trials):
        family_history: list[str] = []
        child_history: list[list[str]] = [[] for _ in range(children)]
        seen: list[set[str]] = [set() for _ in range(children)]
        repeated = [False] * children
        unservable = [0] * children
        for index in range(requests):
            for child in range(children):
                pool = pools[_pick_index(shares, rng.random())]
                if not pool:
                    unservable[child] += 1
                else:
                    history = (
                        family_history
                        if scope == SCOPE_FAMILY
                        else child_history[child]
                    )
                    recent_usage, similar_usage = _family_state(
                        history, pool, similar_reuse=similar_reuse
                    )
                    selection = select_skeleton_for_cell(
                        pool, recent_usage, rng, similar_usage=similar_usage
                    )
                    if selection.slug in seen[child]:
                        repeated[child] = True
                    seen[child].add(selection.slug)
                    family_history.append(selection.slug)
                    child_history[child].append(selection.slug)
                if repeated[child]:
                    repeat_by[index] += 1
                distinct_total[index] += len(seen[child])
                unservable_total[index] += unservable[child]

    probabilities = tuple(count / observations for count in repeat_by)
    bottleneck = binding_cell(demand)
    return BandDemandCurve(
        band=demand[0].cell.band,
        regime=regime,
        trials=trials,
        children=children,
        repeat_probability=probabilities,
        expected_distinct=tuple(total / observations for total in distinct_total),
        expected_unservable=tuple(total / observations for total in unservable_total),
        first_more_likely_than_not=next(
            (
                index + 1
                for index, probability in enumerate(probabilities)
                if probability >= 0.5
            ),
            None,
        ),
        binding=bottleneck.cell.label if bottleneck is not None else "-",
    )


def required_for_share(lifetime: int, share: float) -> int:
    """Return the skeletons one cell needs, given its share of the demand.

    This replaces :func:`required_per_cell`'s even split. Under the owner's
    premise that a skeleton is consumable once per child, a cell that takes
    ``share`` of a child's ``lifetime`` requests in the band must hold
    ``ceil(lifetime * share)`` skeletons for that child never to exhaust it.

    Args:
        lifetime: Stories the child consumes in the band.
        share: The cell's share of the band's requests, in ``[0, 1]``.

    Returns:
        int: Skeletons required in this cell.
    """
    return math.ceil(lifetime * share)


def cell_survival(
    pool_size: int,
    *,
    horizon: int,
    trials: int,
    rng: random.Random,
    similar_reuse: bool = False,
) -> tuple[float, ...]:
    """Return ``P(no miss within j requests into a cell of this size)``.

    A "miss" is the event the catalog is built to avoid: either a repeat (the
    child draws a skeleton they have already read) or an unservable request (the
    cell is empty, so the request 422s). Index ``j`` is the number of requests
    into THIS cell, ``j = 0 .. horizon``; index 0 is 1.0 by definition.

    An empty pool has survival 0 from the first request. That is what makes the
    budget optimizer fill a missing cell before it thickens a thin one: an
    unservable request is a worse outcome than a repeated skeleton, not a
    neutral one.

    Args:
        pool_size: How many skeletons the cell holds.
        horizon: The largest per-cell request count to estimate.
        trials: Simulated families per estimate.
        rng: The random source.
        similar_reuse: Which theme regime to hold.

    Returns:
        tuple[float, ...]: Survival by per-cell request count, length
            ``horizon + 1``.
    """
    if pool_size < 1:
        return (1.0, *([0.0] * horizon))
    curve = simulate_exposure(
        pad_pool([], pool_size),
        trials=trials,
        requests=horizon,
        rng=rng,
        similar_reuse=similar_reuse,
    )
    return (1.0, *(1.0 - probability for probability in curve.repeat_probability))


def survival_table(
    largest: int,
    *,
    horizon: int,
    trials: int,
    rng: random.Random,
    similar_reuse: bool = False,
) -> dict[int, tuple[float, ...]]:
    """Return :func:`cell_survival` for every pool size up to ``largest``.

    A pool of ``m`` interchangeable candidates behaves identically whatever its
    slugs are: the selector reads only the recency and similarity COUNTS, never
    the slug. So one curve per pool size serves every cell of that size in every
    band, and the budget search re-uses this table instead of re-simulating.

    Args:
        largest: The largest pool size to cover.
        horizon: The largest per-cell request count to estimate.
        trials: Simulated families per estimate.
        rng: The random source; drawn from in ascending size order, so a seeded
            run is reproducible.
        similar_reuse: Which theme regime to hold.

    Returns:
        dict[int, tuple[float, ...]]: Survival curve per pool size, ``0`` up to
            and including ``largest``.
    """
    return {
        size: cell_survival(
            size, horizon=horizon, trials=trials, rng=rng, similar_reuse=similar_reuse
        )
        for size in range(max(largest, 0) + 1)
    }


def band_survival(
    shares: Sequence[float], survivals: Sequence[Sequence[float]], horizon: int
) -> tuple[float, ...]:
    """Compose per-cell survival curves into a whole-band survival curve.

    A child's ``N`` requests split over the cells multinomially, so

        ``P(no miss in N) = sum over (j_1..j_k) summing to N of
        multinomial(N; j) * prod_i share_i^j_i * survival_i(j_i)``

    which is the ``x^N`` coefficient of ``prod_i sum_j survival_i(j) *
    (share_i x)^j / j!``, scaled by ``N!``. Evaluating it as a polynomial
    product costs ``O(k * horizon^2)`` instead of enumerating compositions, so
    the budget optimizer can score hundreds of allocations.

    #ASSUME: data-integrity: this composition treats the cells as independent,
    which the direct simulation does not: cells share one ``_RECENT_WINDOW``, so
    heavy traffic in one cell can evict another cell's protective history. At
    the pool sizes in play (3-4 real, up to a few dozen synthetic) a child's last
    twenty family rows still carry every slug of every cell they have used, so
    the coupling is second-order.
    #VERIFY: test_band_survival_agrees_with_the_direct_band_simulation pins the
    two against each other on a real band.

    Args:
        shares: Each cell's share of the band's requests.
        survivals: Each cell's survival curve, from :func:`cell_survival`;
            must be at least ``horizon + 1`` long.
        horizon: The largest total request count to compute.

    Returns:
        tuple[float, ...]: ``P(no miss by N)`` for ``N = 0 .. horizon``.

    Raises:
        ValueError: If the two sequences differ in length or a survival curve
            is shorter than the horizon.
    """
    if len(shares) != len(survivals):
        msg = "shares and survivals must describe the same cells"
        raise ValueError(msg)
    if any(len(curve) < horizon + 1 for curve in survivals):
        msg = "every survival curve must cover the horizon"
        raise ValueError(msg)
    factorial = [math.factorial(index) for index in range(horizon + 1)]
    product = [0.0] * (horizon + 1)
    product[0] = 1.0
    for share, curve in zip(shares, survivals, strict=True):
        term = [
            curve[index] * share**index / factorial[index]
            for index in range(horizon + 1)
        ]
        convolved = [0.0] * (horizon + 1)
        for left in range(horizon + 1):
            if product[left] == 0.0:
                continue
            for right in range(horizon + 1 - left):
                convolved[left + right] += product[left] * term[right]
        product = convolved
    return tuple(
        min(1.0, max(0.0, factorial[index] * product[index]))
        for index in range(horizon + 1)
    )


def requests_before_miss(survival: Sequence[float]) -> float:
    """Return the expected requests a child makes before their first miss.

    ``E[T] = sum_{N >= 0} P(T > N)`` and ``P(T > N)`` is exactly the survival
    curve, so the expectation is the curve's sum. It is truncated at the
    horizon, so a very large catalog reports a value capped near
    ``len(survival)``; the report says so rather than pretending the tail was
    integrated.

    Args:
        survival: ``P(no miss by N)`` for ``N = 0 .. horizon``.

    Returns:
        float: Expected requests before the first repeat-or-unservable event.
    """
    return sum(survival)


def _even_split(budget: int, parts: int) -> tuple[int, ...]:
    """Return ``budget`` divided as evenly as possible into ``parts`` shares."""
    if parts < 1:
        return ()
    base, remainder = divmod(budget, parts)
    return tuple(base + (1 if index < remainder else 0) for index in range(parts))


def _allocations(budget: int, parts: int) -> Iterator[tuple[int, ...]]:
    """Yield every way to split ``budget`` whole skeletons into ``parts``."""
    if parts == 1:
        yield (budget,)
        return
    for taken in range(budget + 1):
        for rest in _allocations(budget - taken, parts - 1):
            yield (taken, *rest)


@dataclass(frozen=True, slots=True)
class BudgetSplit:
    """One allocation of a fixed authoring budget across a band's length tiers.

    Attributes:
        per_length: New skeletons added to short, medium and long.
        expected_requests: Expected per-child requests before the first miss
            (repeat or unservable), truncated at the horizon.
        first_more_likely_than_not: Smallest ``N`` whose miss probability
            reaches 0.5, or ``None`` when no ``N`` within the horizon did.
    """

    per_length: tuple[int, ...]
    expected_requests: float
    first_more_likely_than_not: int | None


def score_allocation(
    demand: Sequence[DemandCell],
    per_length: Sequence[int],
    survivals: Mapping[int, Sequence[float]],
    horizon: int,
) -> BudgetSplit:
    """Score one budget allocation across a band's length tiers.

    A tier's allocation is spread evenly over that tier's cells, which matters
    only in the two teen bands where narrative style splits each populated
    length in two.

    Args:
        demand: The band's cells and shares.
        per_length: New skeletons for short, medium and long, in
            :data:`_LENGTH_ORDER`.
        survivals: ``{pool_size: survival curve}``, covering every pool size
            this allocation produces.
        horizon: The largest total request count to compute.

    Returns:
        BudgetSplit: The scored allocation.

    Raises:
        KeyError: If ``survivals`` is missing a pool size the allocation needs.
    """
    added = dict(zip(_LENGTH_ORDER, per_length, strict=True))
    sizes: list[int] = []
    for length in _LENGTH_ORDER:
        entries = [entry for entry in demand if entry.cell.length == length]
        if not entries:
            continue
        extra = _even_split(added[length], len(entries))
        sizes.extend(
            entry.pool_size + gain for entry, gain in zip(entries, extra, strict=True)
        )
    ordered = [
        entry
        for length in _LENGTH_ORDER
        for entry in demand
        if entry.cell.length == length
    ]
    survival = band_survival(
        [entry.share for entry in ordered],
        [survivals[size] for size in sizes],
        horizon,
    )
    return BudgetSplit(
        per_length=tuple(per_length),
        expected_requests=requests_before_miss(survival),
        first_more_likely_than_not=next(
            (index for index, value in enumerate(survival) if value < 0.5), None
        ),
    )


def optimal_split(
    demand: Sequence[DemandCell],
    *,
    budget: int,
    horizon: int,
    trials: int,
    rng: random.Random,
    similar_reuse: bool = False,
    survivals: Mapping[int, Sequence[float]] | None = None,
) -> tuple[BudgetSplit, BudgetSplit]:
    """Return the best and the even split of a fixed per-band authoring budget.

    Every composition of ``budget`` into the three length tiers is scored
    through :func:`score_allocation`.

    Args:
        demand: The band's cells and shares, from :func:`cell_demand`.
        budget: New skeletons available for this band.
        horizon: The largest per-child request count to compute.
        trials: Simulated families per per-cell survival estimate.
        rng: The random source.
        similar_reuse: Which theme regime to hold.
        survivals: A pre-built :func:`survival_table`, so a caller sweeping
            several bands and budgets simulates each pool size once. Built
            here when omitted.

    Returns:
        The ``(best, even)`` pair, so the caller can report the gain.

    Raises:
        ValueError: If ``budget`` is negative.
    """
    if budget < 0:
        msg = "an authoring budget cannot be negative"
        raise ValueError(msg)
    if survivals is None:
        survivals = survival_table(
            max((entry.pool_size for entry in demand), default=0) + budget,
            horizon=horizon,
            trials=trials,
            rng=rng,
            similar_reuse=similar_reuse,
        )
    scored = [
        score_allocation(demand, allocation, survivals, horizon)
        for allocation in _allocations(budget, len(_LENGTH_ORDER))
    ]
    best = max(scored, key=lambda split: split.expected_requests)
    even = score_allocation(
        demand, _even_split(budget, len(_LENGTH_ORDER)), survivals, horizon
    )
    return best, even


def _write(line: str) -> None:
    """Write one report line to stdout."""
    sys.stdout.write(f"{line}\n")


def _report_pools() -> list[Cell]:
    """Print the per-cell pool table and return the cells.

    Returns:
        list[Cell]: Every cell, in report order.
    """
    cells = list(iter_cells())
    populated = [cell for cell in cells if cell.slugs]
    sizes = [len(cell.slugs) for cell in populated]
    _write("== per-cell candidate pools (real catalog, real cell matching) ==")
    _write(f"{'cell':34s} {'pool':>4s}  flag  slugs")
    for cell in cells:
        size = len(cell.slugs)
        if size == 0:
            flag = "EMPTY"
        elif size < _THIN_CELL:
            flag = "THIN "
        else:
            flag = "     "
        _write(f"{cell.label:34s} {size:4d}  {flag} {', '.join(cell.slugs)}")
    _write("")
    _write(
        " ".join(
            [
                f"cells: {len(cells)}",
                f"populated: {len(populated)}",
                f"empty: {len(cells) - len(populated)}",
                f"thin (<{_THIN_CELL}): {sum(1 for size in sizes if size < _THIN_CELL)}",
                f"min={min(sizes)}",
                f"median={statistics.median(sizes):.1f}",
                f"max={max(sizes)}",
            ]
        )
    )
    _write("")
    return cells


def _report_curve(cell: Cell, curve: ExposureCurve, regime: str) -> None:
    """Print one exposure curve."""
    crossing = (
        str(curve.first_more_likely_than_not)
        if curve.first_more_likely_than_not is not None
        else f">{len(curve.repeat_probability)}"
    )
    _write(
        f"-- {cell.label} pool={curve.pool_size} regime={regime} "
        f"trials={curve.trials} first-likely-repeat=N{crossing}"
    )
    _write(f"   {'N':>3s} {'P(repeat by N)':>15s} {'E[distinct]':>12s}")
    for index, probability in enumerate(curve.repeat_probability):
        if index == 0:
            continue
        _write(
            f"   {index + 1:3d} {probability:15.4f} "
            f"{curve.expected_distinct[index]:12.3f}"
        )
    _write("")


def _report_curves(
    cells: Sequence[Cell], *, trials: int, requests: int, seed: int, premise: str | None
) -> None:
    """Print the exposure curves for the focus cells under both regimes."""
    _write("== sibling-exposure curves (same cell, N successive requests) ==")
    error = 0.5 / math.sqrt(trials)
    _write(f"Monte Carlo; max standard error on a probability: {error:.4f}")
    if premise:
        _write(f"theme_overlap computed from premise: {premise!r}")
    _write("")
    for cell in cells:
        if not cell.slugs:
            _write(f"-- {cell.label}: empty cell, nothing to draw")
            continue
        overlap = (
            theme_overlap_for_candidates(premise, cell.band, list(cell.slugs))
            if premise
            else None
        )
        for regime, similar_reuse in (("distinct-theme", False), ("same-theme", True)):
            curve = simulate_exposure(
                cell.slugs,
                trials=trials,
                requests=requests,
                rng=random.Random(seed),
                similar_reuse=similar_reuse,
                theme_overlap=overlap,
            )
            _report_curve(cell, curve, regime)


def _report_counterfactual(cells: Sequence[Cell], *, trials: int, seed: int) -> None:
    """Print, per distinct real pool size, the pool a target would require."""
    _write("== counterfactual: pool size needed to delay the first likely repeat ==")
    _write(
        "Synthetic candidates are added to a real pool; the weighting is held "
        "exactly as it ships."
    )
    _write("")
    # One representative base pool: the modal real cell size. The search result
    # is dominated by the synthetic padding, so a base of 3 and a base of 4
    # land within a pool size or two of each other; running every distinct base
    # multiplies the runtime without moving the answer.
    sizes = collections.Counter(len(cell.slugs) for cell in cells if cell.slugs)
    modal_size = sizes.most_common(1)[0][0]
    bases: dict[int, Cell] = {
        modal_size: next(cell for cell in cells if len(cell.slugs) == modal_size)
    }
    _write(f"representative base pool: the modal real cell size ({modal_size})")
    _write(
        f"{'base pool':>9s} {'kids':>4s} {'scope':>7s} {'regime':>14s} "
        f"{'target':>9s} {'pool needed':>11s}"
    )
    for size, cell in sorted(bases.items()):
        for children, scope in ((1, SCOPE_FAMILY), (3, SCOPE_FAMILY)):
            for regime, similar_reuse in (
                ("distinct-theme", False),
                ("same-theme", True),
            ):
                for target in _COUNTERFACTUAL_TARGETS:
                    needed = required_pool_size(
                        cell.slugs,
                        target_request=target,
                        trials=trials,
                        rng=random.Random(seed),
                        similar_reuse=similar_reuse,
                        children=children,
                        scope=scope,
                    )
                    shown = (
                        str(needed) if needed is not None else f">{_MAX_SYNTHETIC_POOL}"
                    )
                    _write(
                        f"{size:9d} {children:4d} {scope:>7s} {regime:>14s} "
                        f"{f'past N{target}':>9s} {shown:>11s}"
                    )
    _write("")


def _report_siblings(
    cells: Sequence[Cell], *, trials: int, requests: int, seed: int
) -> None:
    """Print per-child curves for family-scoped versus child-scoped history."""
    _write("== per-child exposure: family-scoped vs child-scoped history ==")
    _write(
        "The event is PER READER: a repeat is a skeleton this child has already "
        "read. 'family' is what ships (recent_skeleton_usage filters on "
        "Storybook.family_id); 'child' is the counterfactual the code does not "
        "implement."
    )
    _write("")
    header = f"{'cell':26s} {'pool':>4s} {'kids':>4s} {'scope':>7s} {'regime':>14s}"
    steps = [2, 3, 5, min(requests, 8), requests]
    marks = sorted({step for step in steps if 2 <= step <= requests})
    _write(header + "".join(f" {f'P@{mark}':>7s}" for mark in marks) + f" {'N50':>4s}")
    for cell in cells:
        if not cell.slugs:
            continue
        for children in _SIBLING_COUNTS:
            for scope in (SCOPE_FAMILY, SCOPE_CHILD):
                if children == 1 and scope == SCOPE_CHILD:
                    # Identical to family scope by construction; the test suite
                    # pins that identity, so printing it twice adds no signal.
                    continue
                for regime, similar_reuse in (
                    ("distinct-theme", False),
                    ("same-theme", True),
                ):
                    curve = simulate_exposure(
                        cell.slugs,
                        trials=trials,
                        requests=requests,
                        rng=random.Random(seed),
                        similar_reuse=similar_reuse,
                        children=children,
                        scope=scope,
                    )
                    crossing = (
                        str(curve.first_more_likely_than_not)
                        if curve.first_more_likely_than_not is not None
                        else f">{requests}"
                    )
                    row = (
                        f"{cell.label:26s} {curve.pool_size:4d} {children:4d} "
                        f"{scope:>7s} {regime:>14s}"
                    )
                    row += "".join(
                        f" {curve.repeat_probability[mark - 1]:7.3f}" for mark in marks
                    )
                    _write(f"{row} {crossing:>4s}")
        _write("")


def _report_window_burn(profiles: Sequence[BandProfile]) -> None:
    """Print how much of a child's own band reading the shared window retains."""
    _write("== recency-window burn (family-scoped window, per-child coverage) ==")
    _write(
        f"_RECENT_WINDOW is {_RECENT_WINDOW} storybook_version rows, family "
        "scoped. Coverage is the share of a child's own band-lifetime reading "
        "that still sits inside the window and can de-weight a repeat."
    )
    _write("")
    _write(
        f"{'band':6s} {'S/mo':>5s} {'lifetime':>8s}"
        + "".join(f" {f'{kids} kid(s)':>9s}" for kids in _SIBLING_COUNTS)
    )
    for profile in profiles:
        for rate in _READING_RATES:
            lifetime = lifetime_stories(rate, profile.tenure_months)
            row = f"{profile.band:6s} {rate:5.1f} {lifetime:8d}"
            row += "".join(
                f" {window_coverage(kids, rate, profile.tenure_months):9.2f}"
                for kids in _SIBLING_COUNTS
            )
            _write(row)
        _write("")


def _report_bands() -> list[BandProfile]:
    """Print per-band catalog counts, cell structure, and tenure.

    Returns:
        list[BandProfile]: The profiles, for the sizing section to reuse.
    """
    profiles = band_profiles()
    _write("== per-band catalog shape and tenure ==")
    _write(
        "Tenure is read off the band label (AgeBand); '16+' is open-ended and "
        f"charged {_OPEN_BAND_MONTHS} months so the table terminates."
    )
    _write("")
    _write(
        f"{'band':6s} {'tenure_mo':>9s} {'cells':>5s} {'empty':>5s} "
        f"{'skeletons':>9s} {'per-cell':>10s}"
    )
    for profile in profiles:
        sizes = [len(cell.slugs) for cell in profile.populated_cells]
        span = f"{min(sizes)}-{max(sizes)}" if sizes else "-"
        _write(
            f"{profile.band:6s} {profile.tenure_months:9d} "
            f"{len(profile.populated_cells):5d} {len(profile.empty_cells):5d} "
            f"{profile.skeletons:9d} {span:>10s}"
        )
    _write("")
    return profiles


def _report_sizing(profiles: Sequence[BandProfile]) -> None:
    """Print the catalog sizing table over per-child reading rates."""
    _write("== catalog sizing: one skeleton serves each child once ==")
    _write(
        "Required-per-band is one child's lifetime consumption in that band; "
        "required-per-cell spreads that demand evenly over the band's populated "
        "cells. Shortfall sums the per-cell gap over the band's cells (a surplus "
        "in one cell cannot cover a deficit in another: cell matching forbids "
        "cross-length and cross-style substitution)."
    )
    _write("")
    _write(
        f"{'band':6s} {'S/mo':>5s} {'lifetime':>8s} {'cells':>5s} "
        f"{'need/cell':>9s} {'have/cell':>9s} {'need band':>9s} "
        f"{'have band':>9s} {'shortfall':>9s}"
    )
    for profile in profiles:
        cells = len(profile.populated_cells)
        for rate in _READING_RATES:
            lifetime = lifetime_stories(rate, profile.tenure_months)
            per_cell = required_per_cell(lifetime, cells)
            have = ", ".join(str(len(cell.slugs)) for cell in profile.populated_cells)
            shortfall = sum(
                max(per_cell - len(cell.slugs), 0) for cell in profile.populated_cells
            )
            band_need = per_cell * cells if cells else lifetime
            _write(
                f"{profile.band:6s} {rate:5.1f} {lifetime:8d} {cells:5d} "
                f"{per_cell:9d} {have:>9s} {band_need:9d} "
                f"{profile.skeletons:9d} {shortfall:9d}"
            )
        _write("")


def _regime_maps(names: Sequence[str]) -> list[tuple[str, dict[str, float]]]:
    """Return ``(name, {length: share})`` pairs for the requested regimes."""
    return [(name, length_demand(name)) for name in names]


def _scope_note(*, declared_only: bool) -> str:
    """Return the one-line explanation of the active length-demand scope."""
    if declared_only:
        return (
            "Scope DECLARED: each band's regime is renormalized onto the length "
            "tiers ADR-011 section 5 gives it a production cell for, so the "
            "shares below differ from the raw regime for 3-5, 5-8, 13-16 and "
            "16+, and an undeclared tier carries no demand and no requirement."
        )
    return (
        "Scope ALL-LENGTHS: the raw regime is applied to all three tiers, so a "
        "band's UNDECLARED tiers carry demand they have no cell for. Read that "
        "as a measure of the missing band-by-length INTAKE validation, not as a "
        "catalog gap: ADR-011 says those cells should not exist, and nothing in "
        "StoryRequestSpecBody or either length <select> stops an adult asking "
        "for one."
    )


def _assumption_banner() -> None:
    """Print the standing caveat every demand-shaped table carries."""
    _write(
        "ASSUMPTION, NOT MEASUREMENT: no length distribution has been observed "
        "in this deployment (no story has shipped). The regimes below are a "
        "sensitivity sweep and must be replaced by a count over "
        "story_request.length once production rows exist."
    )


def _report_demand(
    profiles: Sequence[BandProfile],
    *,
    regimes: Sequence[tuple[str, dict[str, float]]],
    trials: int,
    requests: int,
    seed: int,
    declared_only: bool,
) -> None:
    """Print the per-band exposure curve under each length-demand regime."""
    _write("== per-band exposure under non-uniform length demand ==")
    _assumption_banner()
    _write(
        "One child issues N requests into their band; each request draws a "
        "length from the regime, then a skeleton from that cell through the "
        "shipped selector. 'unserv@N' is the expected number of the first N "
        "requests that named an EMPTY cell (a 422 on the auto-pick path, not a "
        "repeat). 'binding' is the cell with the worst demand-per-skeleton "
        "ratio; MISSING means an empty cell carries demand."
    )
    _write(
        "READ THE TWO COLUMNS TOGETHER: a low repeat probability sitting next "
        "to a high unserv@N is not good news. Those requests never produced a "
        "book, so they cannot produce a repeat either; the band looks healthy "
        "only because part of its demand is being refused."
    )
    _write(_scope_note(declared_only=declared_only))
    error = 0.5 / math.sqrt(trials)
    _write(f"Monte Carlo; max standard error on a probability: {error:.4f}")
    _write("")
    marks = sorted({mark for mark in (2, 3, 4, 6, 10) if mark <= requests})
    header = f"{'band':6s} {'regime':26s} {'theme':>14s}"
    header += "".join(f" {f'P@{mark}':>6s}" for mark in marks)
    header += f" {'N50':>4s} {'E[dst]@N':>9s} {'unserv@N':>9s}  binding"
    _write(header)
    for profile in profiles:
        for name, weights in regimes:
            demand = cell_demand(profile.band, weights, declared_only=declared_only)
            for regime, similar_reuse in (
                ("distinct-theme", False),
                ("same-theme", True),
            ):
                curve = simulate_band_exposure(
                    demand,
                    trials=trials,
                    requests=requests,
                    rng=random.Random(seed),
                    similar_reuse=similar_reuse,
                    regime=name,
                )
                crossing = (
                    str(curve.first_more_likely_than_not)
                    if curve.first_more_likely_than_not is not None
                    else f">{requests}"
                )
                bottleneck = binding_cell(demand)
                flag = (
                    f"{curve.binding} MISSING"
                    if bottleneck is not None and bottleneck.pool_size == 0
                    else curve.binding
                )
                row = f"{profile.band:6s} {name:26s} {regime:>14s}"
                row += "".join(
                    f" {curve.repeat_probability[mark - 1]:6.3f}" for mark in marks
                )
                row += (
                    f" {crossing:>4s} {curve.expected_distinct[-1]:9.2f} "
                    f"{curve.expected_unservable[-1]:9.2f}  {flag}"
                )
                _write(row)
        _write("")


def _report_demand_sizing(
    profiles: Sequence[BandProfile],
    *,
    regimes: Sequence[tuple[str, dict[str, float]]],
    declared_only: bool,
) -> None:
    """Print the demand-weighted catalog target, per cell and per band."""
    _write("== demand-weighted catalog target (need proportional to demand) ==")
    _assumption_banner()
    _write(
        "A cell that takes 'share' of a child's band-lifetime requests needs "
        "ceil(lifetime * share) skeletons for that child never to exhaust it. "
        "Empty cells are rows here, not omissions: a non-zero share on an empty "
        "cell is a cell that has to be CREATED, and its whole requirement is "
        "shortfall. Nothing nets out across cells: only a NULL-length skeleton "
        "is a cross-length wildcard and the catalog holds none."
    )
    _write(_scope_note(declared_only=declared_only))
    _write("")
    flat = length_demand("flat")
    for name, weights in regimes:
        _write(
            f"-- regime {name}: "
            + ", ".join(f"{k}={v:.2f}" for k, v in weights.items())
        )
        _write(
            f"{'band':6s} {'S/mo':>5s} {'life':>5s} {'cell':30s} {'share':>6s} "
            f"{'need':>5s} {'have':>5s} {'short':>6s}"
        )
        totals: dict[float, tuple[int, int, int]] = {}
        for rate in _DEMAND_RATES:
            catalog_need = catalog_have = catalog_short = 0
            for profile in profiles:
                lifetime = lifetime_stories(rate, profile.tenure_months)
                demand = cell_demand(profile.band, weights, declared_only=declared_only)
                band_need = band_have = band_short = 0
                for entry in demand:
                    need = required_for_share(lifetime, entry.share)
                    have = entry.pool_size
                    gap = max(need - have, 0)
                    band_need += need
                    band_have += have
                    band_short += gap
                    _write(
                        f"{profile.band:6s} {rate:5.1f} {lifetime:5d} "
                        f"{entry.cell.label:30s} {entry.share:6.3f} "
                        f"{need:5d} {have:5d} {gap:6d}"
                    )
                _write(
                    f"{profile.band:6s} {rate:5.1f} {lifetime:5d} "
                    f"{'BAND TOTAL':30s} {1.0:6.3f} "
                    f"{band_need:5d} {band_have:5d} {band_short:6d}"
                )
                catalog_need += band_need
                catalog_have += band_have
                catalog_short += band_short
            _write(
                f"{'ALL':6s} {rate:5.1f} {'':5s} {'CATALOG TOTAL':30s} {'':6s} "
                f"{catalog_need:5d} {catalog_have:5d} {catalog_short:6d}"
            )
            _write("")
            totals[rate] = (catalog_need, catalog_have, catalog_short)
        if name != "flat":
            _write(f"   {name} vs flat-demand baseline (whole catalog required):")
            for rate in _DEMAND_RATES:
                baseline = sum(
                    required_for_share(
                        lifetime_stories(rate, profile.tenure_months), entry.share
                    )
                    for profile in profiles
                    for entry in cell_demand(
                        profile.band, flat, declared_only=declared_only
                    )
                )
                _write(
                    f"   S={rate:<4.1f} flat={baseline:5d} {name}={totals[rate][0]:5d} "
                    f"delta={totals[rate][0] - baseline:+5d}"
                )
        _write("")


def _report_budget(
    profiles: Sequence[BandProfile],
    *,
    regimes: Sequence[tuple[str, dict[str, float]]],
    budgets: Sequence[int],
    horizon: int,
    trials: int,
    seed: int,
    declared_only: bool,
) -> None:
    """Print the optimal split of a fixed per-band authoring budget."""
    _write("== fixed authoring budget: how to split N new skeletons per band ==")
    _assumption_banner()
    _write(
        "The objective is a child's expected requests before their first MISS, "
        "where a miss is a repeated skeleton OR an unservable request. Counting "
        "unservable requests as misses is what makes the optimizer create a "
        "missing cell before it thickens a thin one. E[req] is truncated at the "
        f"{horizon}-request horizon, so a well-fed band reports a value near it."
    )
    _write(_scope_note(declared_only=declared_only))
    _write("")
    largest = max(
        (
            entry.pool_size + budget
            for profile in profiles
            for _, weights in regimes
            for entry in cell_demand(profile.band, weights, declared_only=declared_only)
            for budget in budgets
        ),
        default=0,
    )
    survivals = survival_table(
        largest, horizon=horizon, trials=trials, rng=random.Random(seed)
    )
    _write(
        f"{'band':6s} {'regime':26s} {'N':>3s} {'best split (s/m/l)':>19s} "
        f"{'E[req]':>7s} {'N50':>4s} | {'even split':>12s} {'E[req]':>7s} "
        f"{'N50':>4s} | {'gain':>6s}"
    )
    for profile in profiles:
        for name, weights in regimes:
            demand = cell_demand(profile.band, weights, declared_only=declared_only)
            for budget in budgets:
                best, even = optimal_split(
                    demand,
                    budget=budget,
                    horizon=horizon,
                    trials=trials,
                    rng=random.Random(seed),
                    survivals=survivals,
                )
                _write(
                    f"{profile.band:6s} {name:26s} {budget:3d} "
                    f"{'/'.join(str(n) for n in best.per_length):>19s} "
                    f"{best.expected_requests:7.2f} "
                    f"{_crossing(best.first_more_likely_than_not, horizon):>4s} | "
                    f"{'/'.join(str(n) for n in even.per_length):>12s} "
                    f"{even.expected_requests:7.2f} "
                    f"{_crossing(even.first_more_likely_than_not, horizon):>4s} | "
                    f"{best.expected_requests - even.expected_requests:+6.2f}"
                )
        _write("")


def _crossing(value: int | None, horizon: int) -> str:
    """Render a first-miss request index, or a past-the-horizon marker."""
    return str(value) if value is not None else f">{horizon}"


def _parse_cell_argument(raw: str) -> tuple[str, str, str]:
    """Parse a ``band/length/style`` CLI cell selector.

    Args:
        raw: The raw argument value.

    Returns:
        The parsed triple.

    Raises:
        argparse.ArgumentTypeError: If the value is not three slash-separated
            parts.
    """
    parts = raw.split("/")
    if len(parts) != 3:
        msg = f"expected band/length/style, got {raw!r}"
        raise argparse.ArgumentTypeError(msg)
    return parts[0], parts[1], parts[2]


def _resolve_focus(
    selectors: Sequence[tuple[str, str, str]],
) -> tuple[list[Cell], list[str]]:
    """Resolve CLI cell selectors to cells, collecting unknown ones.

    Args:
        selectors: The parsed ``(band, length, style)`` triples.

    Returns:
        The resolved cells and the labels that matched nothing.
    """
    resolved: list[Cell] = []
    missing: list[str] = []
    for band, length, style in selectors:
        cell = find_cell(band, length, style)
        if cell is None:
            missing.append(f"{band}/{length}/{style}")
        else:
            resolved.append(cell)
    return resolved, missing


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--section",
        choices=(
            "all",
            "pools",
            "curves",
            "siblings",
            "bands",
            "sizing",
            "counterfactual",
            "demand",
            "demand-sizing",
            "budget",
        ),
        default="all",
        help="which report section to print (default: all)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=20000,
        help="simulated families per curve (default: 20000)",
    )
    parser.add_argument(
        "--counterfactual-trials",
        type=int,
        default=2000,
        help=(
            "simulated families per candidate pool size (default: 2000; the "
            "pool search runs many simulations, so this is deliberately looser "
            "than --trials)"
        ),
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=12,
        help="successive same-cell requests per CHILD (default: 12)",
    )
    parser.add_argument(
        "--seed", type=int, default=20260809, help="RNG seed (default: 20260809)"
    )
    parser.add_argument(
        "--premise",
        default=None,
        help=(
            "compute theme_overlap from this request premise; omitted means a "
            "zero-overlap request, which the selector treats as pre-W2.2. "
            "Only affects the curves section (--section curves); every "
            "other section ignores this flag"
        ),
    )
    parser.add_argument(
        "--cell",
        action="append",
        type=_parse_cell_argument,
        default=None,
        metavar="BAND/LENGTH/STYLE",
        help="curve cell to report; repeatable (default: the four focus cells)",
    )
    parser.add_argument(
        "--length-demand",
        action="append",
        choices=(*_LENGTH_REGIMES, "all"),
        default=None,
        help=(
            "length-demand regime for the demand/demand-sizing/budget "
            "sections; repeatable (default: all four)"
        ),
    )
    parser.add_argument(
        "--length-demand-custom",
        type=parse_length_demand,
        default=None,
        metavar="SHORT,MEDIUM,LONG",
        help=(
            "an explicit length-demand weight triple, used INSTEAD of the "
            "named regimes; weights are normalized, so '25,60,15' works"
        ),
    )
    parser.add_argument(
        "--length-demand-scope",
        choices=("declared", "all-lengths"),
        default="declared",
        help=(
            "'declared' (default) renormalizes the regime onto the length "
            "tiers ADR-011 gives the band production cells for, so 3-5/5-8 "
            "carry no long demand and the teen bands carry no short demand; "
            "'all-lengths' applies the regime raw to all three tiers and "
            "reports the mass landing on an undeclared tier as unservable, "
            "which measures the missing band-by-length intake validation"
        ),
    )
    parser.add_argument(
        "--demand-trials",
        type=int,
        default=4000,
        help=(
            "simulated families per per-band demand curve (default: 4000; "
            "looser than --trials because the demand section runs one curve "
            "per band per regime per theme regime)"
        ),
    )
    parser.add_argument(
        "--demand-requests",
        type=int,
        default=_DEMAND_HORIZON,
        help=(
            f"per-child requests the demand and budget sections look ahead "
            f"(default: {_DEMAND_HORIZON})"
        ),
    )
    parser.add_argument(
        "--budget",
        action="append",
        type=int,
        default=None,
        metavar="N",
        help=(
            "fixed per-band authoring budget to optimize; repeatable "
            f"(default: {', '.join(str(size) for size in _BUDGET_SIZES)})"
        ),
    )
    parser.add_argument(
        "--budget-trials",
        type=int,
        default=1500,
        help=(
            "simulated families per per-cell survival curve in the budget "
            "search (default: 1500)"
        ),
    )
    return parser


def _validate_run_counts(
    *,
    trials: int,
    requests: int,
    counterfactual_trials: int,
    demand_trials: int,
    demand_requests: int,
    budget_trials: int,
) -> int | None:
    """Validate the CLI trial/request counts are all at least 1.

    Args:
        trials: ``--trials``.
        requests: ``--requests``.
        counterfactual_trials: ``--counterfactual-trials``.
        demand_trials: ``--demand-trials``.
        demand_requests: ``--demand-requests``.
        budget_trials: ``--budget-trials``.

    Returns:
        Exit code 2 when any count is below 1, otherwise None.
    """
    if trials < 1 or requests < 1 or counterfactual_trials < 1:
        sys.stderr.write(
            "error: --trials/--requests/--counterfactual-trials must be at least 1\n"
        )
        return 2
    if demand_trials < 1 or demand_requests < 1 or budget_trials < 1:
        sys.stderr.write(
            "error: --demand-trials/--demand-requests/--budget-trials must be "
            "at least 1\n"
        )
        return 2
    return None


def _resolve_budgets(budgets: list[int] | None) -> tuple[list[int], int | None]:
    """Resolve the ``--budget`` list, defaulting and validating it.

    Args:
        budgets: The raw ``--budget`` values, or None when unset.

    Returns:
        The resolved budget list, and exit code 2 (with an empty list) when
        any budget is negative, otherwise None for the exit code.
    """
    resolved = list(budgets) if budgets else list(_BUDGET_SIZES)
    if any(size < 0 for size in resolved):
        sys.stderr.write("error: --budget must not be negative\n")
        return [], 2
    return resolved, None


def _resolve_regimes(
    custom: dict[str, float] | None, regime_names: list[str] | None
) -> list[tuple[str, dict[str, float]]]:
    """Resolve the length-demand regimes to report.

    Args:
        custom: A caller-supplied ``--length-demand-custom`` map, or None.
        regime_names: The ``--length-demand`` names, or None for the default.

    Returns:
        The resolved (name, map) regime pairs.
    """
    if custom is not None:
        return [("custom", custom)]
    names = list(regime_names) if regime_names else list(_LENGTH_REGIMES)
    if "all" in names:
        names = list(_LENGTH_REGIMES)
    return _regime_maps(names)


def _resolve_cells_and_focus(
    selectors: list[tuple[str, str, str]] | None,
) -> tuple[list[Cell], list[Cell], int | None]:
    """Resolve the catalog cells and the focus cells for reporting.

    Args:
        selectors: The parsed ``--cell`` selectors, or None for the default
            focus set.

    Returns:
        The full cell list, the resolved focus cells, and exit code 2 (with
        both lists empty) when the catalog is missing or a requested cell is
        unknown; otherwise None for the exit code.
    """
    cells = list(iter_cells())
    if not any(cell.slugs for cell in cells):
        sys.stderr.write("error: no production-eligible skeleton found; is the ")
        sys.stderr.write("catalog present and the cwd the repository root?\n")
        return [], [], 2
    focus_selectors = selectors or list(_DEFAULT_FOCUS)
    focus, missing = _resolve_focus(focus_selectors)
    if missing:
        sys.stderr.write(f"error: unknown cell(s): {', '.join(missing)}\n")
        return [], [], 2
    return cells, focus, None


def _dispatch_core_sections(
    section: str,
    *,
    cells: list[Cell],
    focus: list[Cell],
    trials: int,
    requests: int,
    counterfactual_trials: int,
    seed: int,
    premise: str | None,
) -> list[BandProfile]:
    """Run the pools/curves/siblings/bands/sizing/counterfactual sections.

    Args:
        section: The resolved ``--section`` choice.
        cells: The full catalog cell list (reassigned locally by the pools
            section, matching the prior inline behavior).
        focus: The resolved focus cells.
        trials: ``--trials``.
        requests: ``--requests``.
        counterfactual_trials: ``--counterfactual-trials``.
        seed: ``--seed``.
        premise: ``--premise`` (curves section only).

    Returns:
        The band profiles computed by the bands section (empty when that
        section did not run), for the demand-family sections to reuse.
    """
    if section in {"all", "pools"}:
        cells = _report_pools()
    if section in {"all", "curves"}:
        _report_curves(
            focus, trials=trials, requests=requests, seed=seed, premise=premise
        )
    if section in {"all", "siblings"}:
        _report_siblings(focus, trials=trials, requests=requests, seed=seed)
    profiles: list[BandProfile] = []
    if section in {"all", "bands"}:
        profiles = _report_bands()
        _report_window_burn(profiles)
    if section in {"all", "sizing"}:
        _report_sizing(profiles or band_profiles())
    if section in {"all", "counterfactual"}:
        _report_counterfactual(cells, trials=counterfactual_trials, seed=seed)
    return profiles


def _dispatch_demand_sections(
    section: str,
    *,
    profiles: list[BandProfile],
    regimes: list[tuple[str, dict[str, float]]],
    demand_trials: int,
    demand_requests: int,
    budgets: list[int],
    declared_only: bool,
    budget_trials: int,
    seed: int,
) -> None:
    """Run the demand/demand-sizing/budget sections.

    Args:
        section: The resolved ``--section`` choice.
        profiles: The band profiles from the core sections (recomputed here
            when empty, matching the prior inline behavior).
        regimes: The resolved length-demand regimes.
        demand_trials: ``--demand-trials``.
        demand_requests: ``--demand-requests``.
        budgets: The resolved ``--budget`` list.
        declared_only: Whether ``--length-demand-scope`` is ``declared``.
        budget_trials: ``--budget-trials``.
        seed: ``--seed``.
    """
    if section in {"all", "demand", "demand-sizing", "budget"}:
        profiles = profiles or band_profiles()
    if section in {"all", "demand"}:
        _report_demand(
            profiles,
            regimes=regimes,
            trials=demand_trials,
            requests=demand_requests,
            seed=seed,
            declared_only=declared_only,
        )
    if section in {"all", "demand-sizing"}:
        _report_demand_sizing(profiles, regimes=regimes, declared_only=declared_only)
    if section in {"all", "budget"}:
        _report_budget(
            profiles,
            regimes=regimes,
            budgets=budgets,
            horizon=demand_requests,
            trials=budget_trials,
            seed=seed,
            declared_only=declared_only,
        )


def main(argv: list[str] | None = None) -> int:
    """Run the sibling-exposure analysis.

    Args:
        argv: Argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        int: ``0`` on a clean run, ``2`` when the catalog is missing or a
            requested cell does not exist.
    """
    args = _build_parser().parse_args(argv)
    section = cast("str", args.section)
    trials = cast("int", args.trials)
    counterfactual_trials = cast("int", args.counterfactual_trials)
    requests = cast("int", args.requests)
    seed = cast("int", args.seed)
    premise = cast("str | None", args.premise)
    selectors = cast("list[tuple[str, str, str]] | None", args.cell)
    regime_names = cast("list[str] | None", args.length_demand)
    custom = cast("dict[str, float] | None", args.length_demand_custom)
    demand_trials = cast("int", args.demand_trials)
    demand_requests = cast("int", args.demand_requests)
    budgets_arg = cast("list[int] | None", args.budget)
    declared_only = cast("str", args.length_demand_scope) == "declared"
    budget_trials = cast("int", args.budget_trials)

    count_error = _validate_run_counts(
        trials=trials,
        requests=requests,
        counterfactual_trials=counterfactual_trials,
        demand_trials=demand_trials,
        demand_requests=demand_requests,
        budget_trials=budget_trials,
    )
    if count_error is not None:
        return count_error

    budgets, budget_error = _resolve_budgets(budgets_arg)
    if budget_error is not None:
        return budget_error

    regimes = _resolve_regimes(custom, regime_names)

    cells, focus, cell_error = _resolve_cells_and_focus(selectors)
    if cell_error is not None:
        return cell_error

    profiles = _dispatch_core_sections(
        section,
        cells=cells,
        focus=focus,
        trials=trials,
        requests=requests,
        counterfactual_trials=counterfactual_trials,
        seed=seed,
        premise=premise,
    )
    _dispatch_demand_sections(
        section,
        profiles=profiles,
        regimes=regimes,
        demand_trials=demand_trials,
        demand_requests=demand_requests,
        budgets=budgets,
        declared_only=declared_only,
        budget_trials=budget_trials,
        seed=seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
