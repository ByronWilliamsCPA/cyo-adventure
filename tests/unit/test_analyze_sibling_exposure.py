"""Unit tests for scripts/analyze_sibling_exposure.py.

Exercises the callable core directly (never a subprocess), per this repo's
``scripts/measure_sentinel_survival.py`` precedent. The probability computation
is checked against closed-form values the shipped weighting implies, under a
fixed seed, so a change to either the weight formula or the simulation's history
reconstruction breaks a test rather than silently moving the exposure estimate.

The exposure event is PER CHILD, so the sibling tests below are the load-bearing
ones: they pin that a single reader makes the family and child history scopes
identical, that a correctly-scoped selector is indifferent to sibling count, and
that the shipped family-scoped selector is not.

Selection now applies a HARD same-skeleton reuse cap ahead of the weighted draw
(``skeleton_match._apply_reuse_cap``), so an already-read slug is removed from
the candidate list rather than merely de-weighted. Within one cell that makes
the first ``M`` requests repeat-free by construction and request ``M + 1`` a
certain repeat, which is what the in-cell tests below pin.

The pre-cap closed forms are kept here as the superseded baseline, because they
are what the published exposure figures were computed under. For a single
reader's SECOND request into a cell of size ``M`` after one prior pick (weights
from ``skeleton_match._weight`` and ``_blended_weight``):

- distinct-theme: the used slug weighed ``1 / 2`` and each of the ``M - 1``
  others weighed ``1``, so ``P(repeat) = 0.5 / (0.5 + M - 1) = 1 / (2M - 1)``.
  For ``M = 3`` that was ``0.2``; under the cap it is ``0``.
- same-theme: the used slug weighed ``1 / (1 + 1 + 3) = 0.2`` against the same
  ``M - 1`` ones, so ``P(repeat) = 0.2 / (0.2 + M - 1)``. For ``M = 3`` that was
  ``1 / 11``; under the cap it is also ``0``, because the cap excludes exactly
  the slugs the theme penalty de-weighted.

The non-uniform-length-demand additions are covered from the same angle: the
demand shares are checked against arithmetic that does not go through the
script, the mixed-cell simulation is checked against the single-cell one it
generalizes, and the fast survival composition the budget optimizer relies on is
pinned against the direct simulation it approximates.
"""

from __future__ import annotations

import argparse
import math
import random

import pytest

from scripts.analyze_sibling_exposure import (
    _LENGTH_ORDER,  # pyright: ignore[reportPrivateUsage]
    _LENGTH_REGIMES,  # pyright: ignore[reportPrivateUsage]
    SCOPE_CHILD,
    SCOPE_FAMILY,
    ExposureCurve,
    _allocations,  # pyright: ignore[reportPrivateUsage]
    _even_split,  # pyright: ignore[reportPrivateUsage]
    band_cells,
    band_profiles,
    band_survival,
    band_tenure_months,
    binding_cell,
    cell_demand,
    cell_survival,
    declared_lengths,
    find_cell,
    iter_cells,
    length_demand,
    lifetime_stories,
    main,
    optimal_split,
    pad_pool,
    parse_length_demand,
    requests_before_miss,
    required_for_share,
    required_per_cell,
    required_pool_size,
    simulate_band_exposure,
    simulate_exposure,
    survival_table,
    window_coverage,
)

_SEED = 20260809
_TRIALS = 20000
# 3.5 standard errors at 20000 trials (SE <= 0.5/sqrt(n) = 0.0035): tight enough
# to catch a changed weight formula, loose enough not to flake.
_TOLERANCE = 0.0125


def _curve(
    pool: list[str], *, similar_reuse: bool = False, requests: int = 4
) -> ExposureCurve:
    """Run a seeded curve for a pool."""
    return simulate_exposure(
        pool,
        trials=_TRIALS,
        requests=requests,
        rng=random.Random(_SEED),
        similar_reuse=similar_reuse,
    )


@pytest.mark.unit
def test_the_reuse_cap_exhausts_a_cell_before_it_repeats() -> None:
    """A cell of size M is repeat-free for M requests, then repeats for certain.

    This supersedes the pre-cap closed form ``1 / (2M - 1)`` at request 2 (0.2
    for ``M = 3``). The cap is a hard filter, not a weight, so the outcome is
    deterministic rather than probabilistic: exhaustion, not luck, is what
    produces the first repeat.
    """
    curve = _curve(["a", "b", "c"], requests=5)

    assert curve.pool_size == 3
    assert curve.repeat_probability[:3] == (0.0, 0.0, 0.0)
    assert curve.repeat_probability[3] == 1.0
    assert curve.repeat_probability[4] == 1.0


@pytest.mark.unit
def test_the_theme_penalty_is_inert_inside_one_cell_under_the_cap() -> None:
    """The same-theme penalty cannot move a curve once the cap runs.

    ``_family_state`` models "similar" as "the family has read THIS slug", so
    ``similar_usage`` is non-zero on exactly the slugs ``recent_usage`` is
    non-zero on, which are exactly the slugs ``_apply_reuse_cap`` now removes
    before weighting. Every surviving candidate therefore has zero similar
    usage and both regimes produce the identical curve. This holds across cells
    too, not just within one: the cap subsumes the simulator's whole notion of
    theme reuse. The penalty survives only in the relaxed case, where a cell is
    exhausted and every candidate comes back with usage of its own.
    """
    distinct = _curve(["a", "b", "c"], requests=5)
    same = _curve(["a", "b", "c"], similar_reuse=True, requests=5)

    assert same.repeat_probability == distinct.repeat_probability


@pytest.mark.unit
def test_same_theme_never_repeats_more_than_distinct_theme() -> None:
    """Theme reuse only ever strengthens the anti-repeat pressure."""
    distinct = _curve(["a", "b", "c"], requests=6)
    same = _curve(["a", "b", "c"], similar_reuse=True, requests=6)

    for lenient, strict in zip(
        distinct.repeat_probability, same.repeat_probability, strict=True
    ):
        assert strict <= lenient + _TOLERANCE


@pytest.mark.unit
def test_expected_distinct_agrees_with_the_repeat_probability() -> None:
    """At request 2, E[distinct] is exactly 2 minus P(repeat): an identity."""
    curve = _curve(["a", "b", "c"])

    assert curve.expected_distinct[0] == 1.0
    assert curve.expected_distinct[1] == pytest.approx(
        2.0 - curve.repeat_probability[1]
    )


@pytest.mark.unit
def test_pool_smaller_than_the_request_count_repeats_with_certainty() -> None:
    """Pigeonhole: request M+1 into a pool of M has already repeated."""
    curve = _curve(["a", "b", "c"], requests=4)

    assert curve.repeat_probability[3] == 1.0
    assert curve.first_more_likely_than_not is not None
    assert curve.first_more_likely_than_not <= 4


@pytest.mark.unit
def test_single_candidate_cell_repeats_on_the_second_request() -> None:
    """A one-skeleton cell is a guaranteed sibling on request 2."""
    curve = simulate_exposure(["only"], trials=64, requests=3, rng=random.Random(_SEED))

    assert curve.repeat_probability == (0.0, 1.0, 1.0)
    assert curve.expected_distinct == (1.0, 1.0, 1.0)
    assert curve.first_more_likely_than_not == 2


@pytest.mark.unit
def test_the_same_seed_reproduces_the_same_curve() -> None:
    """A seeded run is reproducible; the report's numbers can be re-derived."""
    first = _curve(["a", "b", "c", "d"])
    second = _curve(["a", "b", "c", "d"])

    assert first == second


@pytest.mark.unit
@pytest.mark.parametrize(
    ("pool", "trials", "requests"),
    [([], 10, 3), (["a"], 0, 3), (["a"], 10, 0)],
)
def test_invalid_simulation_inputs_are_rejected(
    pool: list[str], trials: int, requests: int
) -> None:
    """An empty pool or a non-positive trial/request count raises."""
    rng = random.Random(_SEED)
    with pytest.raises(ValueError, match=r"requires a non-empty|at least 1"):
        simulate_exposure(pool, trials=trials, requests=requests, rng=rng)


@pytest.mark.unit
def test_an_unknown_history_scope_is_rejected() -> None:
    """Only the two named scopes are simulatable."""
    rng = random.Random(_SEED)
    with pytest.raises(ValueError, match=r"unknown history scope"):
        simulate_exposure(
            ["a", "b"],
            trials=10,
            requests=2,
            rng=rng,
            scope="household",
        )


@pytest.mark.unit
def test_one_child_makes_the_two_scopes_identical() -> None:
    """With a single reader, family history IS that child's history.

    This is the control for the sibling comparison below: any difference the
    report shows between the scopes must come from siblings, not from the
    simulation treating the two code paths differently.
    """
    family = simulate_exposure(
        ["a", "b", "c"],
        trials=2000,
        requests=4,
        rng=random.Random(_SEED),
        scope=SCOPE_FAMILY,
        children=1,
    )
    child = simulate_exposure(
        ["a", "b", "c"],
        trials=2000,
        requests=4,
        rng=random.Random(_SEED),
        scope=SCOPE_CHILD,
        children=1,
    )

    assert family.repeat_probability == child.repeat_probability
    assert family.expected_distinct == child.expected_distinct


@pytest.mark.unit
def test_child_scoped_history_is_insensitive_to_sibling_count() -> None:
    """Under child scope, a sibling's reading does not touch this child's curve.

    The economic asymmetry in one assertion: a skeleton is reusable across
    readers, so adding readers costs a correctly-scoped selector nothing.
    """
    alone = simulate_exposure(
        ["a", "b", "c"],
        trials=8000,
        requests=3,
        rng=random.Random(_SEED),
        scope=SCOPE_CHILD,
        children=1,
    )
    crowded = simulate_exposure(
        ["a", "b", "c"],
        trials=8000,
        requests=3,
        rng=random.Random(_SEED),
        scope=SCOPE_CHILD,
        children=3,
    )

    assert crowded.repeat_probability[1] == pytest.approx(
        alone.repeat_probability[1], abs=0.02
    )


@pytest.mark.unit
def test_family_scoped_history_degrades_with_more_siblings() -> None:
    """Under the shipped family scope, a sibling raises this child's repeat rate.

    The shared twenty-row window is spent on whoever requested last, so a
    child's own anti-repeat protection is diluted by their siblings.
    """
    alone = simulate_exposure(
        ["a", "b", "c"],
        trials=8000,
        requests=3,
        rng=random.Random(_SEED),
        similar_reuse=True,
        scope=SCOPE_FAMILY,
        children=1,
    )
    crowded = simulate_exposure(
        ["a", "b", "c"],
        trials=8000,
        requests=3,
        rng=random.Random(_SEED),
        similar_reuse=True,
        scope=SCOPE_FAMILY,
        children=3,
    )

    assert crowded.repeat_probability[1] > alone.repeat_probability[1]


@pytest.mark.unit
def test_pad_pool_extends_without_touching_the_real_slugs() -> None:
    """Synthetic candidates are appended; the real ones keep their order."""
    padded = pad_pool(["a", "b"], 5)

    assert padded[:2] == ["a", "b"]
    assert len(padded) == 5
    assert len(set(padded)) == 5
    with pytest.raises(ValueError, match="cannot shrink"):
        pad_pool(["a", "b"], 1)


@pytest.mark.unit
def test_required_pool_size_accepts_a_pool_that_already_clears_the_target() -> None:
    """A three-pool already keeps a request-2 repeat below even odds (0.2)."""
    size = required_pool_size(
        ["a", "b", "c"],
        target_request=2,
        trials=2000,
        rng=random.Random(_SEED),
    )

    assert size == 3


@pytest.mark.unit
def test_required_pool_size_grows_a_pool_that_does_not() -> None:
    """A three-pool must grow to delay a likely repeat past request 5.

    Under the reuse cap the answer is exact rather than probabilistic: a pool
    of ``N`` is repeat-free for its first ``N`` requests, so clearing request 5
    needs exactly 5 and no more. Before the cap the search had to overshoot,
    because a repeat was merely unlikely at each step and the tail accumulated.
    """
    size = required_pool_size(
        ["a", "b", "c"],
        target_request=5,
        trials=2000,
        rng=random.Random(_SEED),
    )

    assert size == 5


@pytest.mark.unit
def test_cells_come_from_the_real_catalog() -> None:
    """Cell enumeration goes through the shipped candidate matching."""
    cells = list(iter_cells())

    assert cells
    assert any(cell.slugs for cell in cells)
    cell = find_cell("10-13", "short", "prose")
    assert cell is not None
    assert cell.label.startswith("10-13/short/")
    assert len(cell.slugs) >= 2
    assert find_cell("10-13", "short", "not-a-style") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("band", "expected"),
    [("3-5", 24), ("5-8", 36), ("8-11", 36), ("10-13", 36), ("16+", 36)],
)
def test_band_tenure_comes_from_the_band_label(band: str, expected: int) -> None:
    """Tenure is derived from AgeBand, not from an invented product number."""
    assert band_tenure_months(band) == expected


@pytest.mark.unit
def test_lifetime_stories_rounds_a_partial_story_up() -> None:
    """A partial story is still a request that some skeleton has to serve."""
    assert lifetime_stories(0.5, 24) == 12
    assert lifetime_stories(0.5, 25) == 13
    assert lifetime_stories(2.0, 36) == 72


@pytest.mark.unit
def test_required_per_cell_splits_demand_across_cells() -> None:
    """Demand spread over C cells still needs ceil(lifetime/C) in EACH cell."""
    assert required_per_cell(36, 3) == 12
    assert required_per_cell(37, 3) == 13
    assert required_per_cell(36, 0) == 36


@pytest.mark.unit
def test_window_coverage_falls_with_every_extra_sibling() -> None:
    """The shared twenty-row window is spent K times faster by K readers."""
    solo = window_coverage(1, 1.0, 36)
    pair = window_coverage(2, 1.0, 36)
    trio = window_coverage(3, 1.0, 36)

    assert solo == pytest.approx(20 / 36)
    assert pair == pytest.approx(10 / 36)
    assert trio == pytest.approx(20 / 3 / 36)
    assert solo > pair > trio


@pytest.mark.unit
def test_window_coverage_saturates_at_one() -> None:
    """A child whose whole band fits in the window is fully covered."""
    assert window_coverage(1, 0.5, 24) == 1.0
    assert window_coverage(1, 0.0, 24) == 1.0


@pytest.mark.unit
def test_band_profiles_cover_every_band_with_real_counts() -> None:
    """Band profiles read the real catalog through the real cell matching."""
    profiles = band_profiles()

    assert len(profiles) == 6
    assert {profile.band for profile in profiles} >= {"3-5", "10-13", "16+"}
    for profile in profiles:
        assert profile.skeletons == sum(
            len(cell.slugs) for cell in profile.populated_cells
        )
        assert all(cell.slugs for cell in profile.populated_cells)
        assert not any(cell.slugs for cell in profile.empty_cells)


@pytest.mark.unit
def test_main_runs_the_pool_section(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI's pool section runs clean against the committed catalog."""
    exit_code = main(["--section", "pools"])

    assert exit_code == 0
    assert "per-cell candidate pools" in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize("section", ["bands", "sizing"])
def test_main_runs_the_catalog_sizing_sections(
    section: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The band and sizing sections need no simulation and must stay cheap."""
    exit_code = main(["--section", section])

    assert exit_code == 0
    assert "10-13" in capsys.readouterr().out


@pytest.mark.unit
def test_main_rejects_an_unknown_cell(capsys: pytest.CaptureFixture[str]) -> None:
    """A cell selector naming no real cell exits 2 rather than reporting zeros."""
    exit_code = main(["--section", "curves", "--cell", "99-100/short/prose"])

    assert exit_code == 2
    assert "unknown cell" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Non-uniform length demand
# --------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("name", list(_LENGTH_REGIMES))
def test_every_named_regime_is_a_probability_distribution(name: str) -> None:
    """A regime's three shares are non-negative and sum to one."""
    weights = length_demand(name)

    assert set(weights) == set(_LENGTH_ORDER)
    assert all(share >= 0 for share in weights.values())
    assert sum(weights.values()) == pytest.approx(1.0)


@pytest.mark.unit
def test_the_named_regimes_carry_the_owners_medium_weighting() -> None:
    """The regime table is the owner's stated expectation, pinned as data.

    These are ASSUMPTIONS, not measurements; the test exists so a silent edit to
    the numbers the report is built on has to be a deliberate one.
    """
    assert length_demand("flat")["medium"] == pytest.approx(1 / 3)
    assert length_demand("medium-weighted") == {
        "short": 0.25,
        "medium": 0.60,
        "long": 0.15,
    }
    assert length_demand("strongly-medium-weighted")["medium"] == 0.75
    assert length_demand("current-default-dominated")["short"] == 0.70


@pytest.mark.unit
def test_custom_length_demand_is_normalized_not_required_to_sum_to_one() -> None:
    """Percentages and fractions describe the same regime."""
    assert parse_length_demand("25,60,15") == pytest.approx(
        parse_length_demand("0.25,0.60,0.15")
    )
    assert parse_length_demand("1,1,1")["medium"] == pytest.approx(1 / 3)


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["1,2", "a,b,c", "0,0,0", "-1,2,1"])
def test_a_malformed_custom_length_demand_is_rejected(raw: str) -> None:
    """A bad weight triple fails at parse time, not inside a report."""
    with pytest.raises(argparse.ArgumentTypeError):
        parse_length_demand(raw)


@pytest.mark.unit
def test_cell_demand_shares_sum_to_one_for_every_band() -> None:
    """Every band's cells, empty ones included, carry the whole distribution."""
    weights = length_demand("medium-weighted")

    for profile in band_profiles():
        demand = cell_demand(profile.band, weights)

        assert len(demand) == len(band_cells(profile.band))
        assert sum(entry.share for entry in demand) == pytest.approx(1.0)


@pytest.mark.unit
def test_the_catalogs_populated_cells_are_exactly_the_adr_011_cells() -> None:
    """The catalog populates ADR-011 section 5's master table and nothing else.

    ``declared_lengths`` reads legality off the CATALOG; the report reasons
    about it as ADR-011's design decision ("young bands cap at Medium"). The
    two agree today, and this test is what makes that agreement checked rather
    than assumed: a skeleton dropped into a cell the ADR does not declare, or a
    declared cell emptied, breaks here instead of silently changing the meaning
    of every demand table.
    """
    adr_011_cells = {
        "3-5": ("short", "medium"),
        "5-8": ("short", "medium"),
        "8-11": ("short", "medium", "long"),
        "10-13": ("short", "medium", "long"),
        "13-16": ("medium", "long"),
        "16+": ("medium", "long"),
    }

    for band, lengths in adr_011_cells.items():
        assert declared_lengths(band) == lengths


@pytest.mark.unit
def test_a_teen_bands_length_share_splits_across_its_two_style_cells() -> None:
    """Style partitions 13-16 and 16+, so a length's demand halves per cell.

    This is the teen-band interaction: 13-16 has no short tier, so the regime
    renormalizes onto medium and long (0.60 and 0.15 become 0.80 and 0.20), and
    then style halves each of those. The same length share buys half the
    per-cell demand, but the band also has to stock twice as many cells.
    """
    weights = length_demand("medium-weighted")
    demand = {entry.cell.label: entry.share for entry in cell_demand("13-16", weights)}

    assert demand["13-16/medium/prose"] == pytest.approx(0.40)
    assert demand["13-16/medium/gamebook"] == pytest.approx(0.40)
    assert demand["13-16/long/prose"] == pytest.approx(0.10)
    assert demand["13-16/short/gamebook+prose"] == 0.0


@pytest.mark.unit
def test_an_undeclared_tier_carries_demand_only_under_the_all_lengths_scope() -> None:
    """The two scopes answer two different questions and must not be conflated.

    Under 'declared', a 3-5 long cell is ADR-011 saying that book does not
    exist, so it carries no demand and no requirement. Under 'all-lengths' it
    carries the raw 0.15, which measures the missing band-by-length intake
    validation: nothing in the request path stops an adult approving one.
    """
    weights = length_demand("medium-weighted")
    declared = {entry.cell.length: entry.share for entry in cell_demand("3-5", weights)}
    raw = {
        entry.cell.length: entry.share
        for entry in cell_demand("3-5", weights, declared_only=False)
    }

    assert declared["long"] == 0.0
    assert declared["medium"] == pytest.approx(0.60 / 0.85)
    assert raw["long"] == pytest.approx(0.15)
    assert raw["medium"] == pytest.approx(0.60)


@pytest.mark.unit
def test_a_non_teen_length_keeps_its_whole_share_in_one_cell() -> None:
    """Below 13-16 style does not partition, so a length is a single cell."""
    demand = {
        entry.cell.label: entry.share
        for entry in cell_demand("8-11", length_demand("medium-weighted"))
    }

    # 8-11 declares all three tiers, so 'declared' scope changes nothing here.
    assert demand["8-11/medium/gamebook+prose"] == pytest.approx(0.60)


@pytest.mark.unit
def test_medium_weighted_demand_makes_the_medium_cell_the_binding_one() -> None:
    """The flat catalog plus peaked demand puts the constraint on medium.

    Under flat demand 8-11's binding cell is whichever tier holds fewest
    skeletons; under the owner's medium weighting it is medium, at the same
    pool size, purely because more requests land there.
    """
    peaked = binding_cell(cell_demand("8-11", length_demand("medium-weighted")))

    assert peaked is not None
    assert peaked.cell.length == "medium"


@pytest.mark.unit
def test_an_empty_cell_carrying_demand_outranks_every_thin_cell() -> None:
    """A missing cell is infinitely binding: those requests cannot be served."""
    bottleneck = binding_cell(
        cell_demand("3-5", length_demand("medium-weighted"), declared_only=False)
    )

    assert bottleneck is not None
    assert bottleneck.pool_size == 0
    assert bottleneck.cell.length == "long"


@pytest.mark.unit
def test_a_single_cell_band_demand_reproduces_the_single_cell_curve() -> None:
    """The mixed-cell simulation generalizes the one it replaces.

    All demand on one populated cell must give exactly the single-cell curve,
    which is the control for every comparison the demand section draws.
    """
    demand = cell_demand("8-11", {"short": 0.0, "medium": 1.0, "long": 0.0})
    pool = next(entry.cell.slugs for entry in demand if entry.share == 1.0)

    band = simulate_band_exposure(
        demand, trials=4000, requests=4, rng=random.Random(_SEED)
    )
    single = simulate_exposure(pool, trials=4000, requests=4, rng=random.Random(_SEED))

    assert band.repeat_probability == pytest.approx(single.repeat_probability, abs=0.03)
    assert band.expected_unservable == (0.0, 0.0, 0.0, 0.0)


@pytest.mark.unit
def test_concentrating_demand_brings_the_first_repeat_forward() -> None:
    """The correction's whole point, as one inequality.

    Same catalog, same band, same seed: peaking demand on medium makes a child
    meet a repeated tree sooner, because the flat catalog spreads its skeletons
    evenly over demand that is not evenly spread.

    The reuse cap pushed the whole horizon out without changing that ordering,
    so the comparison moved from request 4 to request 7 and the run needs 14
    requests for the flat regime to cross even odds at all. Peaking still bites
    first, and by a wider margin than before: concentrating demand exhausts a
    cell, and exhaustion is what a capped selector repeats on.
    """
    flat = simulate_band_exposure(
        cell_demand("10-13", length_demand("flat")),
        trials=6000,
        requests=14,
        rng=random.Random(_SEED),
    )
    peaked = simulate_band_exposure(
        cell_demand("10-13", length_demand("strongly-medium-weighted")),
        trials=6000,
        requests=14,
        rng=random.Random(_SEED),
    )

    assert peaked.repeat_probability[6] > flat.repeat_probability[6]
    assert peaked.first_more_likely_than_not is not None
    assert flat.first_more_likely_than_not is not None
    assert peaked.first_more_likely_than_not <= flat.first_more_likely_than_not


@pytest.mark.unit
def test_demand_on_an_empty_cell_is_counted_unservable_not_repeated() -> None:
    """A 3-5 'long' request 422s; it must not read as a healthy non-repeat."""
    demand = cell_demand(
        "3-5", {"short": 0.0, "medium": 0.0, "long": 1.0}, declared_only=False
    )

    curve = simulate_band_exposure(
        demand, trials=200, requests=5, rng=random.Random(_SEED)
    )

    assert curve.repeat_probability == (0.0, 0.0, 0.0, 0.0, 0.0)
    assert curve.expected_distinct == (0.0, 0.0, 0.0, 0.0, 0.0)
    assert curve.expected_unservable == (1.0, 2.0, 3.0, 4.0, 5.0)
    assert curve.binding.endswith("long/gamebook+prose")


@pytest.mark.unit
def test_the_same_seed_reproduces_the_same_band_curve() -> None:
    """A seeded demand run is reproducible, like the single-cell one."""
    demand = cell_demand("10-13", length_demand("medium-weighted"))
    first = simulate_band_exposure(
        demand, trials=500, requests=4, rng=random.Random(_SEED)
    )
    second = simulate_band_exposure(
        demand, trials=500, requests=4, rng=random.Random(_SEED)
    )

    assert first == second


@pytest.mark.unit
@pytest.mark.parametrize(
    ("trials", "requests", "children"), [(0, 3, 1), (10, 0, 1), (10, 3, 0)]
)
def test_invalid_band_simulation_inputs_are_rejected(
    trials: int, requests: int, children: int
) -> None:
    """The mixed-cell simulation validates exactly what the single-cell one does."""
    demand = cell_demand("10-13", length_demand("flat"))
    rng = random.Random(_SEED)

    with pytest.raises(ValueError, match=r"at least 1"):
        simulate_band_exposure(
            demand,
            trials=trials,
            requests=requests,
            rng=rng,
            children=children,
        )


@pytest.mark.unit
def test_a_band_with_no_demand_at_all_is_rejected() -> None:
    """An all-zero regime names no cell to draw from."""
    demand = cell_demand("10-13", {"short": 0.0, "medium": 0.0, "long": 0.0})
    rng = random.Random(_SEED)

    with pytest.raises(ValueError, match=r"at least one cell with demand"):
        simulate_band_exposure(demand, trials=10, requests=2, rng=rng)


@pytest.mark.unit
def test_an_unknown_scope_is_rejected_by_the_band_simulation() -> None:
    """Only the two named history scopes are simulatable here too."""
    demand = cell_demand("10-13", length_demand("flat"))
    rng = random.Random(_SEED)

    with pytest.raises(ValueError, match=r"unknown history scope"):
        simulate_band_exposure(
            demand, trials=10, requests=2, rng=rng, scope="household"
        )


@pytest.mark.unit
def test_required_for_share_scales_the_need_with_the_demand() -> None:
    """A cell taking 60% of 36 stories needs 22 skeletons, not 12."""
    assert required_for_share(36, 0.60) == 22
    assert required_for_share(36, 1 / 3) == 12
    assert required_for_share(36, 0.0) == 0


@pytest.mark.unit
def test_an_empty_pool_never_survives_its_first_request() -> None:
    """A missing cell is a miss immediately: that is what drives the optimizer."""
    survival = cell_survival(0, horizon=4, trials=10, rng=random.Random(_SEED))

    assert survival == (1.0, 0.0, 0.0, 0.0, 0.0)


@pytest.mark.unit
def test_a_bigger_pool_survives_at_least_as_long() -> None:
    """Survival is monotone in pool size; the pool search relies on it."""
    table = survival_table(6, horizon=6, trials=3000, rng=random.Random(_SEED))

    for size in range(1, 6):
        for index in range(7):
            assert table[size + 1][index] >= table[size][index] - _TOLERANCE


@pytest.mark.unit
def test_band_survival_agrees_with_the_direct_band_simulation() -> None:
    """The optimizer's fast composition matches the slow, exact simulation.

    ``band_survival`` treats the cells as independent; the direct simulation
    does not, because the cells share one twenty-row recency window. This pins
    that the approximation is good enough to optimize against on a real band.
    """
    demand = cell_demand("8-11", length_demand("flat"))
    horizon = 6
    table = survival_table(4, horizon=horizon, trials=8000, rng=random.Random(_SEED))

    composed = band_survival(
        [entry.share for entry in demand],
        [table[entry.pool_size] for entry in demand],
        horizon,
    )
    direct = simulate_band_exposure(
        demand, trials=8000, requests=horizon, rng=random.Random(_SEED)
    )

    assert composed[0] == 1.0
    for index, probability in enumerate(direct.repeat_probability, start=1):
        assert composed[index] == pytest.approx(1.0 - probability, abs=0.02)


@pytest.mark.unit
def test_band_survival_rejects_mismatched_or_short_inputs() -> None:
    """A survival curve that does not cover the horizon is an error, not a zero."""
    with pytest.raises(ValueError, match="same cells"):
        band_survival([0.5, 0.5], [(1.0, 1.0)], 1)
    with pytest.raises(ValueError, match="cover the horizon"):
        band_survival([1.0], [(1.0, 1.0)], 4)


@pytest.mark.unit
def test_requests_before_miss_sums_the_survival_curve() -> None:
    """E[T] = sum over N of P(T > N); a certain miss at request 1 gives 1.0."""
    assert requests_before_miss((1.0, 0.0, 0.0)) == 1.0
    assert requests_before_miss((1.0, 1.0, 0.5, 0.0)) == 2.5


@pytest.mark.unit
@pytest.mark.parametrize(
    ("budget", "parts", "expected"),
    [(6, 3, (2, 2, 2)), (7, 3, (3, 2, 2)), (0, 3, (0, 0, 0)), (5, 1, (5,))],
)
def test_an_even_split_distributes_the_remainder_deterministically(
    budget: int, parts: int, expected: tuple[int, ...]
) -> None:
    """The baseline the optimizer is measured against is itself deterministic."""
    assert _even_split(budget, parts) == expected


@pytest.mark.unit
def test_the_allocation_search_enumerates_every_composition() -> None:
    """Compositions of B into 3 parts number C(B+2, 2); none may be missed."""
    for budget in (0, 3, 6):
        allocations = list(_allocations(budget, 3))

        assert len(allocations) == math.comb(budget + 2, 2)
        assert len(set(allocations)) == len(allocations)
        assert all(sum(allocation) == budget for allocation in allocations)


@pytest.mark.unit
def test_the_optimal_split_is_never_worse_than_an_even_one() -> None:
    """The even split is one of the candidates, so the best must match or beat it."""
    demand = cell_demand("10-13", length_demand("medium-weighted"))

    best, even = optimal_split(
        demand, budget=6, horizon=8, trials=800, rng=random.Random(_SEED)
    )

    assert sum(best.per_length) == 6
    assert sum(even.per_length) == 6
    assert even.per_length == (2, 2, 2)
    assert best.expected_requests >= even.expected_requests


@pytest.mark.unit
def test_a_fixed_budget_goes_to_medium_when_demand_is_peaked_there() -> None:
    """The answer that should drive the build order, pinned on a real band.

    10-13 has all three length tiers populated (see
    `docs/planning/catalog-census.md`, the one place a shell count comes from;
    a per-cell count is deliberately not transcribed here, `UW-G24`), so
    nothing is missing and the only question is where the demand is. Under a
    0.15/0.75/0.10 regime the budget belongs almost entirely in medium.
    """
    demand = cell_demand("10-13", length_demand("strongly-medium-weighted"))

    best, _ = optimal_split(
        demand, budget=6, horizon=10, trials=800, rng=random.Random(_SEED)
    )

    short, medium, long_ = best.per_length
    assert medium > short + long_


@pytest.mark.unit
def test_a_fixed_budget_creates_a_missing_cell_before_thickening_a_thin_one() -> None:
    """3-5 has no long skeleton, so part of the budget must create that cell.

    An unservable request scores as a miss, so the optimizer cannot buy a good
    score by leaving a tier empty; without that, an empty cell would look
    perfect (a cell you never draw from never repeats).
    """
    demand = cell_demand("3-5", length_demand("medium-weighted"), declared_only=False)

    best, _ = optimal_split(
        demand, budget=6, horizon=10, trials=800, rng=random.Random(_SEED)
    )

    assert best.per_length[_LENGTH_ORDER.index("long")] > 0


@pytest.mark.unit
def test_a_negative_budget_is_rejected() -> None:
    """A budget is a count of skeletons to author, never a debt."""
    demand = cell_demand("10-13", length_demand("flat"))
    rng = random.Random(_SEED)
    with pytest.raises(ValueError, match="cannot be negative"):
        optimal_split(
            demand,
            budget=-1,
            horizon=4,
            trials=10,
            rng=rng,
        )


@pytest.mark.unit
def test_main_runs_the_demand_sizing_section(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The demand-weighted sizing table needs no simulation and stays cheap."""
    exit_code = main(
        ["--section", "demand-sizing", "--length-demand", "medium-weighted"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "ASSUMPTION, NOT MEASUREMENT" in output
    assert "CATALOG TOTAL" in output
    assert "8-11/medium/gamebook+prose" in output


@pytest.mark.unit
def test_main_names_the_active_length_demand_scope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each demand table states which scope produced it, so it cannot be misread."""
    assert main(["--section", "demand-sizing", "--length-demand", "flat"]) == 0
    assert "Scope DECLARED" in capsys.readouterr().out

    assert (
        main(
            [
                "--section",
                "demand-sizing",
                "--length-demand",
                "flat",
                "--length-demand-scope",
                "all-lengths",
            ]
        )
        == 0
    )
    assert "Scope ALL-LENGTHS" in capsys.readouterr().out


@pytest.mark.unit
def test_main_runs_the_demand_and_budget_sections(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both simulation-backed demand sections run clean at a small budget."""
    exit_code = main(
        [
            "--section",
            "demand",
            "--length-demand-custom",
            "25,60,15",
            "--demand-trials",
            "60",
            "--demand-requests",
            "4",
        ]
    )
    assert exit_code == 0
    assert "binding" in capsys.readouterr().out

    exit_code = main(
        [
            "--section",
            "budget",
            "--length-demand",
            "medium-weighted",
            "--budget",
            "3",
            "--budget-trials",
            "60",
            "--demand-requests",
            "5",
        ]
    )
    assert exit_code == 0
    assert "best split" in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [
        ["--section", "demand", "--demand-trials", "0"],
        ["--section", "budget", "--budget", "-1"],
    ],
)
def test_main_rejects_invalid_demand_arguments(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Bad demand/budget arguments exit 2 rather than producing a wrong table."""
    exit_code = main(argv)

    assert exit_code == 2
    assert "error:" in capsys.readouterr().err
