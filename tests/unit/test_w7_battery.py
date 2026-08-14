"""Unit tests for the W7 known-bad battery's scoring rule.

The battery decides which judge criteria are worth trusting, so a bug here
retires a working criterion or keeps a blind one, and either outcome propagates
into every ranking-shaped claim the panel supports. The tests therefore drive
three synthetic instruments whose behaviour is known by construction: one that
detects every defect, one that notices nothing, and one that fires on defects it
does not own.
"""

from __future__ import annotations

import itertools

from scripts.judge_books import Verdict
from scripts.w7_battery import (
    DEFECT_CRITERION,
    cohens_kappa,
    score_battery,
)

_CRITERIA_NAMES = (
    "age_fit",
    "imagery",
    "voice",
    "dialogue",
    "choice_quality",
    "ending_quality",
    "engagement",
)
_BOOKS = ("bookA", "bookB", "bookC")
_DEFECTS = ("dialogue_flat", "tense_break", "false_choice", "reading_level_up")
_JUDGES = ("judge-a", "judge-b", "judge-c")


def _pool(scorer: object) -> tuple[list[Verdict], list[tuple[str, str]]]:
    """Build a verdict pool from a scoring function.

    Args:
        scorer: Callable taking ``(arm, criterion)`` and returning a score.

    Returns:
        Every verdict, and the arm list describing what each book is.
    """
    verdicts: list[Verdict] = []
    arms: list[tuple[str, str]] = []
    for book, arm in itertools.product(_BOOKS, ("control", *_DEFECTS)):
        arms.append((book, arm))
        verdicts.extend(
            Verdict(
                book=f"{book}__{arm}",
                leg=f"{book}__{arm}",
                family="w7",
                judge=judge,
                self_family=False,
                scores={
                    name: scorer(arm, name)  # pyright: ignore[reportCallIssue]
                    for name in _CRITERIA_NAMES
                },
                notes={},
                error=None,
            )
            for judge in _JUDGES
        )
    return verdicts, arms


def test_a_criterion_that_detects_its_own_defect_is_kept() -> None:
    """The instrument that works must not be retired."""

    def perfect(arm: str, criterion: str) -> float:
        return 2.5 if DEFECT_CRITERION.get(arm) == criterion else 4.0

    results = score_battery(*_pool(perfect))

    by_name = {r.criterion: r for r in results}
    assert by_name["dialogue"].verdict.startswith("KEEP")
    assert by_name["dialogue"].detection_rate == 1.0
    assert by_name["voice"].detections == len(_BOOKS)


def test_a_criterion_blind_to_its_own_defect_is_retired() -> None:
    """The rule's whole purpose: a criterion that misses its defect goes.

    This is the dialogue criterion's hypothesis stated as a fixture. A judge
    returning the same score whatever was done to the book carries no ordering
    information, and pooling it into a composite mean dilutes the criteria that
    do discriminate.
    """

    def blind(_arm: str, _criterion: str) -> float:
        return 3.0

    results = score_battery(*_pool(blind))

    by_name = {r.criterion: r for r in results}
    assert by_name["dialogue"].verdict.startswith("RETIRE")
    assert by_name["dialogue"].detections == 0
    assert by_name["dialogue"].opportunities == len(_BOOKS)


def test_a_criterion_firing_on_a_defect_it_does_not_own_is_counted() -> None:
    """The second half of the rule: reacting to everything is not discrimination.

    A criterion that drops on every seeded book, including the ones carrying a
    defect some other criterion owns, is responding to "this book was touched"
    rather than to the property it claims to measure.
    """

    def indiscriminate(arm: str, _criterion: str) -> float:
        return 4.0 if arm == "control" else 2.5

    results = score_battery(*_pool(indiscriminate))

    by_name = {r.criterion: r for r in results}
    # It "detects" its own defect, but it also moved on every other arm.
    assert by_name["dialogue"].detections == len(_BOOKS)
    assert by_name["dialogue"].false_positives > 0
    assert by_name["imagery"].false_positives > 0


def test_a_criterion_no_defect_targets_is_reported_untested() -> None:
    """Silence about a criterion must not read as approval of it."""

    def perfect(arm: str, criterion: str) -> float:
        return 2.5 if DEFECT_CRITERION.get(arm) == criterion else 4.0

    results = score_battery(*_pool(perfect))

    by_name = {r.criterion: r for r in results}
    assert by_name["imagery"].verdict.startswith("UNTESTED")
    assert by_name["imagery"].detection_rate is None


def test_a_criterion_moving_the_wrong_way_is_not_a_detection() -> None:
    """A seeded defect raising a score is not the criterion noticing it.

    Direction is the whole signal. A criterion that reliably moves on the defect
    but upward has found something, and it is not the defect.
    """

    def inverted(arm: str, criterion: str) -> float:
        return 5.0 if DEFECT_CRITERION.get(arm) == criterion else 4.0

    results = score_battery(*_pool(inverted))

    by_name = {r.criterion: r for r in results}
    assert by_name["dialogue"].detections == 0
    assert by_name["dialogue"].verdict.startswith("RETIRE")


def test_kappa_is_high_when_two_judges_agree_and_low_when_they_do_not() -> None:
    """The agreement statistic has to be able to separate the two cases."""
    agree_a = [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0]
    agree_b = list(agree_a)
    disagree = [5.0, 4.0, 3.0, 2.0, 1.0, 5.0, 4.0, 3.0]

    high = cohens_kappa(agree_a, agree_b)
    low = cohens_kappa(agree_a, disagree)

    assert high is not None
    assert high > 0.9
    assert low is not None
    assert low < high


def test_kappa_is_undefined_rather_than_zero_when_both_judges_used_one_score() -> None:
    """Two judges agreeing on everything must not be reported as total disagreement.

    Kappa's chance-correction divides by ``1 - expected``, and with one category
    the expected agreement is 1. Returning ``0.0`` there would read as "no
    agreement beyond chance" for a pair that agreed on every single book, and
    would drag a panel below its floor for being consistent.
    """
    flat = [3.0] * 8

    assert cohens_kappa(flat, flat) is None


def test_kappa_refuses_a_sample_too_small_to_mean_anything() -> None:
    """One book is not an agreement measurement."""
    assert cohens_kappa([3.0], [3.0]) is None
    assert cohens_kappa([3.0, 4.0], [3.0]) is None
