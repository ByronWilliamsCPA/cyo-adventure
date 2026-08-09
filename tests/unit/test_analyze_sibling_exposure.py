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

Closed forms used below, for a single reader's SECOND request into a cell of
size ``M`` after one prior pick (weights from ``skeleton_match._weight`` and
``_blended_weight``):

- distinct-theme: the used slug weighs ``1 / 2`` and each of the ``M - 1``
  others weighs ``1``, so ``P(repeat) = 0.5 / (0.5 + M - 1) = 1 / (2M - 1)``.
  For ``M = 3`` that is ``0.2``.
- same-theme: the used slug weighs ``1 / (1 + 1 + 3) = 0.2`` against the same
  ``M - 1`` ones, so ``P(repeat) = 0.2 / (0.2 + M - 1)``. For ``M = 3`` that is
  ``1 / 11``, about ``0.0909``.
"""

from __future__ import annotations

import random

import pytest

from scripts.analyze_sibling_exposure import (
    SCOPE_CHILD,
    SCOPE_FAMILY,
    ExposureCurve,
    band_profiles,
    band_tenure_months,
    find_cell,
    iter_cells,
    lifetime_stories,
    main,
    pad_pool,
    required_per_cell,
    required_pool_size,
    simulate_exposure,
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
def test_distinct_theme_second_request_matches_the_closed_form() -> None:
    """A three-skeleton cell repeats on request 2 with probability 1/(2M-1)."""
    curve = _curve(["a", "b", "c"])

    assert curve.pool_size == 3
    assert curve.repeat_probability[0] == 0.0
    assert curve.repeat_probability[1] == pytest.approx(0.2, abs=_TOLERANCE)


@pytest.mark.unit
def test_same_theme_regime_applies_the_theme_reuse_penalty() -> None:
    """The same-theme regime de-weights the used slug by the 3x penalty."""
    curve = _curve(["a", "b", "c"], similar_reuse=True)

    assert curve.repeat_probability[1] == pytest.approx(1 / 11, abs=_TOLERANCE)


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
    with pytest.raises(ValueError, match=r"requires a non-empty|at least 1"):
        simulate_exposure(
            pool, trials=trials, requests=requests, rng=random.Random(_SEED)
        )


@pytest.mark.unit
def test_an_unknown_history_scope_is_rejected() -> None:
    """Only the two named scopes are simulatable."""
    with pytest.raises(ValueError, match=r"unknown history scope"):
        simulate_exposure(
            ["a", "b"],
            trials=10,
            requests=2,
            rng=random.Random(_SEED),
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
    """A three-pool must grow to delay a likely repeat past request 5."""
    size = required_pool_size(
        ["a", "b", "c"],
        target_request=5,
        trials=2000,
        rng=random.Random(_SEED),
    )

    assert size is not None
    assert size > 5


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
