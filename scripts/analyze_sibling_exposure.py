#!/usr/bin/env python
"""Sibling-skeleton exposure analysis: how often does one family repeat a tree?

    uv run python scripts/analyze_sibling_exposure.py               # full report
    uv run python scripts/analyze_sibling_exposure.py --section pools
    uv run python scripts/analyze_sibling_exposure.py --trials 50000

The question
------------
Three story-diversity pilots found that two stories filled from the SAME
skeleton read as "same adventure, new world" to a 10-13 reader. That finding
only justifies replacing skeletons if a real family actually meets the same
tree twice. This tool measures the exposure rate under the selector that ships
today, so the decision is made against a rate rather than against an anecdote.

The method
----------
1. **Pools.** Enumerate every ``(band, length, narrative_style)`` cell through
   the real ``generation.skeleton_match.candidates_for_cell``, so the counts
   reflect ``production_eligible``, the sidecar skip, the length wildcard, the
   style-aware-band rule (ADR-011), and the continuation exclusion (AL-045)
   exactly as selection sees them. Styles that do not partition a cell (every
   band below 13-16) are collapsed into one row rather than counted twice,
   matching ``diversity/incell.py``'s convention.
2. **Curves.** Simulate one family issuing N successive requests into the SAME
   cell, drawing each pick with the real ``select_skeleton_for_cell`` and the
   real weighting. History state is rebuilt between draws exactly as the
   production caller builds it (see ``_family_state``), including the
   twenty-row recency window. Reported per N: P(at least one repeat by request
   N), the expected number of distinct skeletons seen, and the first N at which
   a repeat is more likely than not.
3. **Counterfactual.** Grow a real pool with synthetic candidates, holding the
   weighting fixed, and find the smallest pool that pushes the
   more-likely-than-not repeat past request 5 and past request 10. That is the
   catalog size a "grow the catalog" program would have to buy.

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
# request index. "past 5" is a family's first year at roughly one story a
# season; "past 10" is a family that reads through a band.
_COUNTERFACTUAL_TARGETS: tuple[int, ...] = (5, 10)

# Upper bound on the counterfactual pool search, so an unreachable target ends
# the scan instead of running forever.
_MAX_SYNTHETIC_POOL = 400


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
    """Monte Carlo exposure estimates for one pool under one regime.

    Attributes:
        pool_size: How many candidates the family was drawing from.
        trials: How many independent simulated families were run.
        repeat_probability: ``P(at least one repeat skeleton by request N)`` for
            ``N = 1 .. requests``; index 0 is request 1 and is always 0.0.
        expected_distinct: Expected count of distinct skeletons seen by request
            ``N``, same indexing.
        first_more_likely_than_not: The smallest ``N`` whose repeat probability
            reaches 0.5, or ``None`` when no simulated N did.
    """

    pool_size: int
    trials: int
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
) -> ExposureCurve:
    """Estimate the sibling-exposure curve for one pool by simulation.

    Each trial is one family issuing ``requests`` successive requests into the
    same cell. Every draw goes through the real
    ``skeleton_match.select_skeleton_for_cell`` with history state rebuilt by
    :func:`_family_state`, so the weighting under test is the shipped weighting
    and not a restatement of it.

    Args:
        candidates: The in-cell candidate slugs; must be non-empty.
        trials: How many independent families to simulate.
        requests: How many successive same-cell requests per family.
        rng: The random source, injected so a seeded run is reproducible.
        similar_reuse: When True, run the same-theme regime (every prior story
            counts as similar); when False, the distinct-theme regime.
        theme_overlap: Optional ``{slug: bonus}`` premise-overlap map, passed
            straight through to selection. ``None`` reproduces the pre-W2.2
            recency/similarity-only weighting.

    Returns:
        ExposureCurve: The estimated curve.

    Raises:
        ValueError: If ``candidates`` is empty, or ``trials``/``requests`` is
            below 1.
    """
    if not candidates:
        msg = "simulate_exposure requires a non-empty candidate pool"
        raise ValueError(msg)
    if trials < 1 or requests < 1:
        msg = "trials and requests must both be at least 1"
        raise ValueError(msg)

    slugs = list(candidates)
    repeat_by: list[int] = [0] * requests
    distinct_total: list[int] = [0] * requests

    for _ in range(trials):
        history: list[str] = []
        seen: set[str] = set()
        repeated = False
        for index in range(requests):
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
            if selection.slug in seen:
                repeated = True
            seen.add(selection.slug)
            history.append(selection.slug)
            if repeated:
                repeat_by[index] += 1
            distinct_total[index] += len(seen)

    probabilities = tuple(count / trials for count in repeat_by)
    expected = tuple(total / trials for total in distinct_total)
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
        target_request: The request index the first likely repeat must clear.
        trials: Trials per candidate pool size.
        rng: The random source.
        similar_reuse: Which regime to hold while enlarging the pool.

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
        )
        return curve.repeat_probability[-1] < 0.5

    low = max(len(base), 1)
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
    bases: dict[int, Cell] = {}
    for cell in cells:
        if cell.slugs:
            bases.setdefault(len(cell.slugs), cell)
    _write(f"{'base pool':>9s} {'regime':>14s} {'target':>8s} {'pool needed':>12s}")
    for size, cell in sorted(bases.items()):
        for regime, similar_reuse in (("distinct-theme", False), ("same-theme", True)):
            for target in _COUNTERFACTUAL_TARGETS:
                needed = required_pool_size(
                    cell.slugs,
                    target_request=target,
                    trials=trials,
                    rng=random.Random(seed),
                    similar_reuse=similar_reuse,
                )
                shown = str(needed) if needed is not None else f">{_MAX_SYNTHETIC_POOL}"
                _write(f"{size:9d} {regime:>14s} {f'past N{target}':>8s} {shown:>12s}")
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
        choices=("all", "pools", "curves", "counterfactual"),
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
        default=4000,
        help="simulated families per candidate pool size (default: 4000)",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=12,
        help="successive same-cell requests per family (default: 12)",
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
    if section in {"all", "counterfactual"}:
        _report_counterfactual(cells, trials=counterfactual_trials, seed=seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
