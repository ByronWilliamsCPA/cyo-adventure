"""Unit tests for the shared prose-craft detectors (``validator/prose_craft.py``).

The module is the single definition of "does this book repeat itself" and "is
the narrator in the person the book declares", read by both the request-path
advisory in ``moderation/prose_craft.py`` and the offline
``scripts/check_prose_craft.py``. The identity tests at the bottom are what
stop the two from drifting; the calibration figures in the module docstring
were measured with exactly this code, and a second copy silently invalidates
them.
"""

from __future__ import annotations

from typing import Any

import pytest

from cyo_adventure.validator import prose_craft
from cyo_adventure.validator.prose_craft import (
    MAX_THIRD_SECOND_PERSON,
    MAX_TOP3_LABEL_SHARE,
    MIN_GAMEBOOK_SECOND_PERSON,
    judge_person,
    judge_sameness,
    person_report,
    sameness_report,
)

pytestmark = pytest.mark.unit


def _story(
    bodies: list[str],
    labels: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal filled story with the given bodies and choice labels."""
    labels = labels or []
    return {
        "id": "s_x",
        "metadata": metadata or {},
        "nodes": [
            {
                "id": f"n{i}",
                "body": body,
                "choices": [
                    {"id": f"c{i}_{j}", "label": label, "target": "n0"}
                    for j, label in enumerate(labels)
                ],
            }
            for i, body in enumerate(bodies)
        ],
    }


def test_a_byte_identical_body_is_counted_as_redundant() -> None:
    """The defect that separated the two live books: 23 nodes, 11 texts."""
    report = sameness_report(_story(["same text here", "same text here", "other"]))
    assert report.repeated_texts == 1
    assert report.redundant_nodes == 1


def test_bodies_are_compared_raw_including_their_dialogue() -> None:
    """A duplicate is a duplicate whatever it quotes.

    Stripping dialogue first would merge two bodies that differ only in what
    the characters say, which is a real difference.
    """
    report = sameness_report(_story(['"Run," she said.', '"Wait," she said.']))
    assert report.redundant_nodes == 0


def test_label_collapse_is_measured_as_a_share_not_a_count() -> None:
    """A count cannot serve both an 11-node and a 551-node book."""
    report = sameness_report(_story(["a", "b"], labels=["Go on", "Go on"]))
    assert report.labels == 4
    assert report.distinct_labels == 1
    assert report.top3_share == pytest.approx(1.0)


def test_label_collapse_is_not_judged_on_a_book_too_small_to_judge() -> None:
    """Three labels covering everything is arithmetic, not a defect.

    Every book with three or fewer distinct labels scores a top-3 share of
    1.0 by construction, so the share only becomes evidence once the book has
    enough choices for it to have been otherwise.
    """
    judgment = judge_sameness(sameness_report(_story(["a"], labels=["One", "Two"])))
    assert judgment.breached is False


def test_a_collapsed_label_set_on_a_large_book_breaches() -> None:
    """The live failure: three strings covered 89.8 percent of 674 choices."""
    report = sameness_report(_story(["a"] * 25, labels=["Go on", "Go back"]))
    assert report.labels >= 40
    assert report.top3_share > MAX_TOP3_LABEL_SHARE
    assert judge_sameness(report).breached is True


def test_second_person_is_counted_over_narration_only() -> None:
    """One character saying "you" to another says nothing about the narrator."""
    report = person_report(_story(['"You go first," she said.']))
    assert report.second_person_nodes == 0


def test_a_gamebook_below_the_floor_breaches() -> None:
    """The genre is defined by addressing the reader.

    The live case: "you" in 12 of 193 nodes on beats that specify second
    person. The protagonist is absent from their own story.
    """
    story = _story(["The corridor was cold."], metadata={"narrative_style": "gamebook"})
    judgment = judge_person(story, person_report(story))
    assert judgment.breached is True
    assert "floor" in judgment.framing


def test_a_gamebook_declaring_third_person_is_a_contract_error_not_a_measurement() -> (
    None
):
    """A contradiction is reported as one rather than measured.

    Holding a correct second-person gamebook to a third-person ceiling would
    invert the gate, so the pairing is rejected before any rate is compared.
    """
    story = _story(
        ["You step into the corridor."],
        metadata={"narrative_style": "gamebook", "narrative_person": "third"},
    )
    judgment = judge_person(story, person_report(story))
    assert judgment.breached is True
    assert "contradictory" in judgment.framing


def test_prose_declaring_no_person_is_reported_but_never_breached() -> None:
    """Nothing pins an undeclared prose book's person, so nothing may fail it.

    Three fills of one prose skeleton landed at 0.07, 0.13 and 0.72 with no
    declaration; a universal floor would have failed two correct books.
    """
    story = _story(["You walk on. You look up. You wait."])
    judgment = judge_person(story, person_report(story))
    assert judgment.breached is False
    assert "reported only" in judgment.framing


def test_a_declared_third_person_book_that_drifts_second_breaches() -> None:
    """The ceiling exists for the 3-5 book that shipped fully second person."""
    story = _story(["You walk on."] * 3, metadata={"narrative_person": "third"})
    report = person_report(story)
    assert report.rate > MAX_THIRD_SECOND_PERSON
    assert judge_person(story, report).breached is True


def test_a_declared_second_person_prose_book_is_held_to_the_gamebook_floor() -> None:
    """A declaration is a promise, whatever the style field says."""
    story = _story(["The corridor was cold."], metadata={"narrative_person": "second"})
    judgment = judge_person(story, person_report(story))
    assert judgment.breached is True
    assert f"{MIN_GAMEBOOK_SECOND_PERSON:.0%}" in judgment.framing


def test_the_offline_script_holds_no_second_copy_of_the_detectors() -> None:
    """Drift here silently invalidates the offline calibration figures.

    The 0.898 top-3 share, the 23 redundant nodes and the 0.715-to-1.0
    gamebook range were all measured with this code. Identity is checked
    rather than equality, because a copy can be edited and an equality test
    updated in the same commit; the only way to change a detector is to
    change the one definition both callers read.
    """
    from scripts import check_prose_craft

    assert check_prose_craft.sameness_report is sameness_report
    assert check_prose_craft.person_report is person_report
    assert check_prose_craft.strip_quoted is prose_craft.strip_quoted
    assert check_prose_craft.strip_dialogue is prose_craft.narration_of


def test_the_script_defaults_are_the_shared_thresholds() -> None:
    """A default that drifts from the constant is the same defect, one level up.

    The CLI could otherwise ship a looser bar than the request path enforces
    while both cite the same calibration.
    """
    from scripts.check_prose_craft import _build_parser

    defaults = _build_parser().parse_args(["x.json"])
    assert defaults.max_top3_label_share == MAX_TOP3_LABEL_SHARE
    assert defaults.max_third_second_person == MAX_THIRD_SECOND_PERSON
    assert defaults.min_gamebook_second_person == MIN_GAMEBOOK_SECOND_PERSON
