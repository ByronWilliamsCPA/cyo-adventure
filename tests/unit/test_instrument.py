"""Unit tests for the uncertainty arithmetic behind W5.

Every test here is the workplan's own acceptance list for the item: an interval
must narrow as evidence accumulates, must separate a pair that genuinely differs,
must refuse to separate a pair that does not, and must never report a bound it
did not earn. The last of those is the one that carries the pre-registered
consequence, because a zero-width interval printed beside a mean is how a single
book becomes a published property of a supplier.
"""

from __future__ import annotations

import pytest

from scripts.instrument import (
    Interval,
    bootstrap_interval,
    rank_separation,
)


def test_interval_narrows_as_the_sample_grows() -> None:
    """More observations of the same quantity must buy a tighter interval."""
    small = bootstrap_interval([0.9, 1.0, 1.1, 1.0])
    large = bootstrap_interval([0.9, 1.0, 1.1, 1.0] * 8)

    assert large.width < small.width
    assert large.n == 32


def test_a_separated_pair_reports_disjoint_intervals() -> None:
    """Two clearly different legs must not have their difference hidden."""
    low = bootstrap_interval([1.0, 1.1, 0.9, 1.0, 1.05, 0.95])
    high = bootstrap_interval([5.0, 5.1, 4.9, 5.0, 5.05, 4.95])

    assert not low.overlaps(high)


def test_an_identical_pair_reports_overlapping_intervals() -> None:
    """Two legs drawn from the same values must not be reported as ordered."""
    values = [2.0, 3.0, 4.0, 2.5, 3.5, 3.0]
    left = bootstrap_interval(values)
    right = bootstrap_interval(list(reversed(values)))

    assert left.overlaps(right)


def test_a_single_observation_yields_no_interval_rather_than_a_zero_width_one() -> None:
    """One book must report incomplete, not a bound of width zero.

    This is the guard the whole module exists for. Resampling one observation
    returns that observation every time, so the arithmetic happily produces
    ``[x, x]``, which prints as the most precise measurement on the page.
    """
    interval = bootstrap_interval([3.14])

    assert interval.complete is False
    assert interval.n == 1
    assert interval.lo == interval.hi == interval.point == pytest.approx(3.14)


def test_bounds_are_identical_under_a_fixed_seed() -> None:
    """A published interval must reproduce exactly, or it cannot be checked."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    first = bootstrap_interval(values, seed=1234)
    again = bootstrap_interval(values, seed=1234)

    assert (first.lo, first.hi) == (again.lo, again.hi)


def test_the_seed_is_actually_consulted() -> None:
    """Guard against a seed argument that is accepted and then ignored.

    Percentile bounds over a small sample are stable enough that most seed pairs
    agree, which is the reassuring part of the result and also what would let an
    unwired seed pass unnoticed. These two seeds are a pair measured to disagree,
    so the test fails if the argument stops reaching the generator.
    """
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]

    assert (
        bootstrap_interval(values, seed=1234).lo
        != bootstrap_interval(values, seed=2026).lo
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"confidence": 0.0}, "confidence"),
        ({"confidence": 1.0}, "confidence"),
        ({"resamples": 0}, "resamples"),
    ],
)
def test_a_nonsensical_parameter_raises_rather_than_returning_a_number(
    kwargs: dict[str, float], message: str
) -> None:
    """A bad parameter must fail loudly, since its output would look plausible."""
    with pytest.raises(ValueError, match=message):
        bootstrap_interval([1.0, 2.0, 3.0], **kwargs)  # pyright: ignore[reportArgumentType]


def test_an_empty_sample_raises() -> None:
    """No observations is a caller error, not an interval."""
    with pytest.raises(ValueError, match="at least one observation"):
        bootstrap_interval([])


def _fixed(point: float, lo: float, hi: float, *, complete: bool = True) -> Interval:
    """Build an interval directly, for ranking tests that do not need resampling.

    Args:
        point: The point estimate.
        lo: Lower bound.
        hi: Upper bound.
        complete: Whether the interval is usable.

    Returns:
        The interval.
    """
    return Interval(point=point, lo=lo, hi=hi, n=4, complete=complete)


def test_a_slate_whose_intervals_all_overlap_is_not_a_supported_ranking() -> None:
    """The pre-registered retraction trigger must actually fire."""
    ranking = rank_separation(
        {
            "leg-a": _fixed(0.30, -0.40, 1.00),
            "leg-b": _fixed(0.10, -0.60, 0.80),
            "leg-c": _fixed(-0.40, -1.10, 0.30),
        }
    )

    assert ranking.ordered == ("leg-a", "leg-b", "leg-c")
    assert ranking.separated_pairs == 0
    assert ranking.total_pairs == 3
    assert ranking.supported is False
    assert ranking.extremes_separated is False


def test_a_slate_with_one_real_gap_is_supported_and_says_how_much() -> None:
    """Partial separation must be reported as partial, not as a clean ordering."""
    ranking = rank_separation(
        {
            "leg-a": _fixed(1.20, 0.90, 1.50),
            "leg-b": _fixed(0.10, -0.20, 0.40),
            "leg-c": _fixed(0.00, -0.30, 0.30),
        }
    )

    assert ranking.supported is True
    assert ranking.separated_pairs == 2
    assert ranking.total_pairs == 3
    assert ranking.extremes_separated is True


def test_a_leg_with_no_usable_interval_is_excluded_and_named() -> None:
    """An incomplete leg must not be silently counted as separated."""
    ranking = rank_separation(
        {
            "leg-a": _fixed(1.20, 0.90, 1.50),
            "leg-b": _fixed(0.10, -0.20, 0.40),
            "leg-thin": _fixed(9.00, 9.00, 9.00, complete=False),
        }
    )

    assert ranking.excluded == ("leg-thin",)
    assert ranking.total_pairs == 1
    assert ranking.separated_pairs == 1
    # The excluded leg still appears in the ordering, because its position is
    # exactly the claim being questioned.
    assert ranking.ordered[0] == "leg-thin"
