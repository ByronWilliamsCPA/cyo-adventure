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
            "zero-overlap request, which the selector treats as pre-W2.2"
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
    return parser


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

    if trials < 1 or requests < 1 or counterfactual_trials < 1:
        sys.stderr.write("error: --trials/--requests must be at least 1\n")
        return 2

    cells = list(iter_cells())
    if not any(cell.slugs for cell in cells):
        sys.stderr.write("error: no production-eligible skeleton found; is the ")
        sys.stderr.write("catalog present and the cwd the repository root?\n")
        return 2

    focus_selectors = selectors or list(_DEFAULT_FOCUS)
    focus, missing = _resolve_focus(focus_selectors)
    if missing:
        sys.stderr.write(f"error: unknown cell(s): {', '.join(missing)}\n")
        return 2

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
