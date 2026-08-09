"""Unit tests for scripts/analyze_sibling_exposure.py.

Exercises the callable core directly (never a subprocess), per this repo's
``scripts/measure_sentinel_survival.py`` precedent. The probability computation
is checked against closed-form values the shipped weighting implies, under a
fixed seed, so a change to either the weight formula or the simulation's history
reconstruction breaks a test rather than silently moving the exposure estimate.

Closed forms used below, for a family's SECOND request into a cell of size ``M``
after one prior pick (weights from ``skeleton_match._weight`` and
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
    ExposureCurve,
    find_cell,
    iter_cells,
    main,
    pad_pool,
    required_pool_size,
    simulate_exposure,
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
def test_main_runs_the_pool_section(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI's pool section runs clean against the committed catalog."""
    exit_code = main(["--section", "pools"])

    assert exit_code == 0
    assert "per-cell candidate pools" in capsys.readouterr().out


@pytest.mark.unit
def test_main_rejects_an_unknown_cell(capsys: pytest.CaptureFixture[str]) -> None:
    """A cell selector naming no real cell exits 2 rather than reporting zeros."""
    exit_code = main(["--section", "curves", "--cell", "99-100/short/prose"])

    assert exit_code == 2
    assert "unknown cell" in capsys.readouterr().err
