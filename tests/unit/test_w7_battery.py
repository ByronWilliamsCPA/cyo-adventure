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
import json
import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from scripts.judge_books import Verdict
from scripts.w7_battery import (
    DEFECT_CRITERION,
    blend_to_grade,
    cohens_kappa,
    load_panel,
    score_battery,
    single_run,
    weighted_kappa,
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
# Every entry must be a defect DEFECT_CRITERION actually maps to. `tense_break`
# used to sit here and was removed with its mapping on 2026-08-14: it switches
# the narrator's tense, while the `voice` rubric it was mapped to asks about the
# main character's distinctness, so the arm tested nothing (AL-371).
_DEFECTS = (
    "dialogue_flat",
    "ending_truncated",
    "false_choice",
    "reading_level_up",
)
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
    assert by_name["ending_quality"].detections == len(_BOOKS)


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


def test_movement_on_an_arm_a_criterion_does_not_own_is_recorded_not_charged() -> None:
    """Renamed from a false-positive count, because that is not what it measures.

    The old rule read any movement on another criterion's defect arm as the
    criterion misfiring. That holds only if each arm carries one isolated
    defect, and none do: `reading_level_up` rewrites a third of the prose, so
    voice and imagery genuinely change, and the count charged them for noticing.
    It is still worth recording, so the count survives under an honest name and
    decides nothing.
    """

    def indiscriminate(arm: str, _criterion: str) -> float:
        return 4.0 if arm == "control" else 2.5

    results = score_battery(*_pool(indiscriminate))

    by_name = {r.criterion: r for r in results}
    assert by_name["dialogue"].detections == len(_BOOKS)
    assert by_name["dialogue"].cross_arm_moves > 0
    assert by_name["imagery"].cross_arm_moves > 0
    # And it does not turn a detection into a retirement.
    assert by_name["dialogue"].verdict.startswith(("KEEP", "INCONCLUSIVE"))


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


# --------------------------------------------------------------------------
# blend_to_grade
# --------------------------------------------------------------------------

_EASY = "The dog ran. The cat sat. The sun was hot. We had fun. He got up."
_HARD = (
    "The domesticated canine proceeded ambulatorily, whereupon the resident "
    "feline established a sedentary disposition beneath an atmospheric "
    "condition of considerable thermal intensity."
)


def _book(bodies: list[str], *, target: float = 1.0) -> dict[str, object]:
    """Return a minimal document `blend_to_grade` can measure."""
    return {
        "metadata": {"reading_level": {"target": target, "tolerance": 1.0}},
        "nodes": [{"id": f"n{i}", "body": b} for i, b in enumerate(bodies)],
    }


@pytest.mark.unit
def test_blending_stops_at_the_target_instead_of_using_the_whole_rewrite() -> None:
    """The generation seed overshoots, and the arm's job is a stated magnitude.

    Asked for three grades harder the rewriter delivered between 8.2 and 11.1
    across the real corpus, which makes `age_fit` detection trivial and moves
    voice and engagement genuinely. The blend exists to land the seed where it
    was aimed, so the check is that it stops early rather than that it runs.
    """
    original = _book([_EASY] * 10)
    hardened = _book([_HARD] * 10)
    arm, note = blend_to_grade(original, hardened, grades=3.0)

    swapped = sum(1 for n in arm["nodes"] if n["body"] == _HARD)  # pyright: ignore[reportIndexIssue, reportGeneralTypeIssues]
    assert 0 < swapped < 10, note


@pytest.mark.unit
def test_the_note_reports_the_achieved_delta_not_the_requested_one() -> None:
    """A seed whose strength is unreported cannot be read back against its rate.

    The blend lands on or just past the target, never exactly on it, because a
    node is the smallest unit it can swap. Reporting the request instead of the
    achievement would hide by how much.
    """
    _, note = blend_to_grade(_book([_EASY] * 10), _book([_HARD] * 10), grades=3.0)
    assert "against a +3.0 target" in note
    assert "swapped" in note


@pytest.mark.unit
def test_hardened_nodes_are_spread_rather_than_stacked_at_the_front() -> None:
    """Swapping in index order seeds a different defect from the intended one.

    A book that starts hard and softens is not a book that is too old for its
    band; it is a book with a bad opening. The low-discrepancy order is what
    keeps the two apart.
    """
    arm, _ = blend_to_grade(_book([_EASY] * 12), _book([_HARD] * 12), grades=3.0)
    indices = [i for i, n in enumerate(arm["nodes"]) if n["body"] == _HARD]  # pyright: ignore[reportIndexIssue, reportGeneralTypeIssues]
    assert indices, "nothing was swapped, so the ordering is untested"
    # Not all clustered in the opening third.
    assert max(indices) >= 4


@pytest.mark.unit
def test_a_book_with_no_declared_reading_level_falls_back_to_the_full_rewrite() -> None:
    """Unmeasurable is not zero, and the caller is told which it got."""
    original = {"nodes": [{"id": "n0", "body": _EASY}]}
    hardened = {"nodes": [{"id": "n0", "body": _HARD}]}
    arm, note = blend_to_grade(original, hardened, grades=3.0)
    assert arm["nodes"][0]["body"] == _HARD  # pyright: ignore[reportIndexIssue, reportGeneralTypeIssues]
    assert "unmeasurable" in note


# --------------------------------------------------------------------------
# The identifier join
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_arms_join_verdicts_whose_book_id_carries_a_brief_suffix() -> None:
    """`judge_book` labels every verdict "{leg}#{brief_index}"; the battery must join anyway.

    That convention is right for the vendor comparison it was written for, where
    one leg writes one book per brief. This battery passes an arm's file stem as
    the leg and has no briefs, so every verdict came back as
    `the-lost-mitten__control#0` while the battery looked up
    `the-lost-mitten__control`. Nothing matched, every criterion saw zero
    opportunities, and a run of 93 clean scorings printed seven UNTESTED
    verdicts. The tell was that the failure was total: a battery merely short of
    data reports some numbers.
    """
    arms = [("bookA", "control"), ("bookA", "ending_truncated")]
    verdicts = [
        Verdict(
            book=f"bookA__{arm}#0",
            leg=f"bookA__{arm}",
            family="f",
            judge="judge-a",
            self_family=False,
            scores=dict.fromkeys(_CRITERIA_NAMES, 4.0)
            | ({"ending_quality": 1.0} if arm == "ending_truncated" else {}),
            notes={},
            error=None,
        )
        for _, arm in arms
    ]

    scored = next(
        r for r in score_battery(verdicts, arms) if r.criterion == "ending_quality"
    )
    assert scored.opportunities == 1, "the suffixed identifier did not join"
    assert scored.detections == 1


# --------------------------------------------------------------------------
# The noise floor and the agreement statistic
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_a_detection_inside_the_panels_own_noise_is_inconclusive() -> None:
    """Crossing the margin is not the same as being distinguishable from noise.

    The replacement for the old "fires on the clean control" test. With no
    repeat scorings a judge cannot be asked twice, but three judges scoring the
    same undefected book measure directly how much a criterion moves when
    nothing moved. A detection smaller than that is not evidence.
    """
    arms = [("bookA", "control"), ("bookA", "dialogue_flat")]
    verdicts: list[Verdict] = []
    # Judges disagree wildly about the clean control, and the "detection" is
    # a bare 0.6, inside that disagreement.
    for judge, control in zip(_JUDGES, (5.0, 3.0, 1.0), strict=True):
        for arm, value in (("control", control), ("dialogue_flat", control - 0.6)):
            verdicts.append(
                Verdict(
                    book=f"bookA__{arm}#0",
                    leg=f"bookA__{arm}",
                    family="f",
                    judge=judge,
                    self_family=False,
                    scores=dict.fromkeys(_CRITERIA_NAMES, value),
                    notes={},
                    error=None,
                )
            )

    # One control book alone cannot establish a floor; add a second.
    for judge, control in zip(_JUDGES, (5.0, 3.0, 1.0), strict=True):
        verdicts.append(
            Verdict(
                book="bookB__control#0",
                leg="bookB__control",
                family="f",
                judge=judge,
                self_family=False,
                scores=dict.fromkeys(_CRITERIA_NAMES, control),
                notes={},
                error=None,
            )
        )
    arms.append(("bookB", "control"))

    dialogue = next(
        r for r in score_battery(verdicts, arms) if r.criterion == "dialogue"
    )
    assert dialogue.detections == 1, "the margin was crossed"
    assert dialogue.control_noise is not None
    assert dialogue.verdict.startswith("INCONCLUSIVE"), dialogue.verdict


@pytest.mark.unit
def test_weighted_kappa_separates_near_misses_from_far_ones() -> None:
    """A 1-to-5 rubric is ordinal; 3-against-4 is not 3-against-1.

    The unweighted form counts both as plain disagreement, which is part of why
    W7's first agreement figure was uninterpretable. Quadratic weighting is what
    makes a near miss cost less than an opposite call.
    """
    truth = [1.0, 2.0, 3.0, 4.0, 5.0]
    near = [2.0, 3.0, 4.0, 5.0, 4.0]
    far = [5.0, 4.0, 3.0, 2.0, 1.0]

    near_k = weighted_kappa(truth, near)
    far_k = weighted_kappa(truth, far)
    assert near_k is not None
    assert far_k is not None
    assert near_k > far_k

    # The unweighted form ranks these backwards. Neither sequence matches
    # `truth` exactly even once, so its observed-agreement term is 0 for both,
    # and all that separates them is how their marginals fall: the off-by-one
    # judge scores -0.25 and the judge who reverses the scale scores 0.00.
    near_unweighted = cohens_kappa(truth, near)
    far_unweighted = cohens_kappa(truth, far)
    assert near_unweighted is not None
    assert far_unweighted is not None
    assert near_unweighted < far_unweighted


@pytest.mark.unit
def test_weighted_kappa_is_undefined_not_zero_when_a_judge_never_varies() -> None:
    """Reporting 0.0 would read as total disagreement between judges who agreed."""
    assert weighted_kappa([3.0, 3.0, 3.0], [3.0, 3.0, 3.0]) is None


# --------------------------------------------------------------------------
# The concurrent-run lock
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_a_second_run_against_the_same_output_directory_is_refused(
    tmp_path: Path,
) -> None:
    """A paid run is silent for most of its life, so silence must not invite a retry.

    W7's judging pass was relaunched on the evidence of a missing log while the
    original was still running: two panels, 93 scorings each, $4.94 against
    about $2. Both would have written `verdicts.json`, so the artefact could
    not have shown it.
    """
    (tmp_path / ".run.lock").write_text(str(os.getpid()), encoding="utf-8")

    with pytest.raises(RuntimeError, match="already writing"), single_run(tmp_path):
        pass  # pragma: no cover - the raise is the assertion


@pytest.mark.unit
def test_a_lock_left_by_a_dead_process_does_not_wedge_the_harness(
    tmp_path: Path,
) -> None:
    """A killed run must not require manual cleanup before the next one.

    The lock is a guard against a *live* duplicate, not a mutex that outlives
    its holder; treating a stale file as authoritative would turn one crash
    into a permanently blocked harness.
    """
    (tmp_path / ".run.lock").write_text("999999", encoding="utf-8")

    with single_run(tmp_path):
        assert (tmp_path / ".run.lock").read_text(encoding="utf-8") == str(os.getpid())

    assert not (tmp_path / ".run.lock").exists(), "the lock outlived its run"


@pytest.mark.unit
def test_a_corrupted_lock_file_reads_as_dead(tmp_path: Path) -> None:
    """Otherwise a truncated write during a crash blocks every later run."""
    (tmp_path / ".run.lock").write_text("not-a-pid", encoding="utf-8")

    with single_run(tmp_path):
        pass

    assert not (tmp_path / ".run.lock").exists()


# --------------------------------------------------------------------------
# Panel loading
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_a_pending_judge_is_held_out_of_the_panel(tmp_path: Path) -> None:
    """A slot held open must not be silently judged, nor silently forgotten.

    `qwen/qwen3.8-27b` is a real model with zero endpoints, so it cannot be
    called today but is worth testing the moment one appears. Keeping the row
    in the slate with a flag makes the gap visible where the panel is defined;
    dropping it would lose it, and loading it would fail the run.
    """
    panel = tmp_path / "panel.json"
    panel.write_text(
        json.dumps(
            [
                {"label": "live", "model": "vendor/live", "family": "v"},
                {
                    "label": "held",
                    "model": "vendor/unserved",
                    "family": "v",
                    "pending": True,
                },
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_panel(panel)

    assert [j.label for j in loaded] == ["live"]


@pytest.mark.unit
def test_a_panel_of_nothing_but_pending_rows_is_an_error(tmp_path: Path) -> None:
    """Silently judging with zero judges would report every criterion untested."""
    panel = tmp_path / "panel.json"
    panel.write_text(
        json.dumps([{"label": "held", "model": "m", "family": "v", "pending": True}]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no judge that is not pending"):
        load_panel(panel)
