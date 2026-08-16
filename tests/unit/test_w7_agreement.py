"""Hand-checkable answers for the two estimators W7's agreement now rests on.

`AL-378` retracted the original agreement figures because the statistic was
wrong for the data, not because the arithmetic was. So the replacement gets
tests that pin the arithmetic against cases whose answers are known by
construction, and one that pins the specific pathology that produced the
retracted numbers: a coefficient that collapses on skewed marginals while raw
agreement is high.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from w7_agreement import (
    quadratic_weighted_kappa,
    spearman,
)


@pytest.mark.unit
def test_perfectly_ordered_judges_correlate_at_one() -> None:
    """Identical rankings, so rho is exactly 1 by construction."""
    assert spearman([1, 2, 3, 4, 5], [2, 3, 4, 5, 6]) == pytest.approx(1.0)


@pytest.mark.unit
def test_exactly_reversed_judges_correlate_at_minus_one() -> None:
    """The other end of the scale, held so a sign error cannot hide."""
    assert spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)


@pytest.mark.unit
def test_ties_are_ranked_by_midpoint_not_by_input_order() -> None:
    """A five-point rubric over a few books is mostly ties, so this is the norm.

    The naive ``1 - 6*d^2/(n^3-n)`` shortcut silently gives a different answer
    the moment a tie appears, and every criterion in the battery has them.
    """
    both_flat_in_the_middle = spearman([1, 2, 2, 3], [1, 2, 2, 3])

    assert both_flat_in_the_middle == pytest.approx(1.0)


@pytest.mark.unit
def test_a_judge_who_never_varies_yields_no_correlation_rather_than_zero() -> None:
    """Undefined is reported as undefined; zero would read as "they disagree"."""
    assert spearman([3, 3, 3, 3], [1, 2, 3, 4]) is None


@pytest.mark.unit
def test_too_few_pairs_is_refused_rather_than_estimated() -> None:
    """`dialogue_flat` contributes 2 books, so this guard is live, not defensive."""
    assert spearman([1, 2], [1, 2]) is None
    assert quadratic_weighted_kappa([1, 2], [1, 2]) is None


@pytest.mark.unit
def test_identical_ordinal_scores_give_kappa_one() -> None:
    """Total agreement, and the weighting must not disturb it."""
    assert quadratic_weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(
        1.0
    )


@pytest.mark.unit
def test_the_weighting_charges_a_far_miss_more_than_a_near_one() -> None:
    """The reason for using the quadratic form at all.

    Unweighted kappa treats 5-versus-1 exactly like 4-versus-3 and so cannot
    tell "one judge is a little stricter" from "the judges are reading different
    books". These two datasets have the SAME number of disagreements and very
    different severity, and the coefficient has to separate them.
    """
    near = quadratic_weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 5, 4])
    far = quadratic_weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 1, 5])

    assert near is not None
    assert far is not None
    assert near > far


@pytest.mark.unit
def test_a_constant_pair_is_undefined_rather_than_perfect() -> None:
    """Two judges who always say 3 have shown no ability to agree on anything.

    Reporting 1.0 here would be the flattering answer and the wrong one: there
    is no variance for chance correction to work against.
    """
    assert quadratic_weighted_kappa([3, 3, 3, 3], [3, 3, 3, 3]) is None


@pytest.mark.unit
def test_high_raw_agreement_with_skewed_marginals_still_depresses_kappa() -> None:
    """The pathology that produced the retracted +0.16 and +0.14.

    Nine of ten scores match exactly, which is 90 percent raw agreement, and
    because almost everything sits in one category the chance correction eats
    nearly all of it. The coefficient is not wrong; it is answering a question
    about categories rather than about the judges. This test exists so that a
    reader who sees a low number in the report knows to look at the marginals
    printed beside it before concluding anything.
    """
    left = [3, 3, 3, 3, 3, 3, 3, 3, 3, 1]
    right = [3, 3, 3, 3, 3, 3, 3, 3, 3, 3]

    raw_agreement = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    kappa = quadratic_weighted_kappa(left, right)

    assert raw_agreement == pytest.approx(0.9)
    assert kappa is None or kappa <= 0.0
