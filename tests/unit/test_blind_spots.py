"""Unit tests for the gate blind-spot manifest (W6).

W6's decision rule is unusually demanding, and these tests are it: keep the
manifest only while its declarations cannot drift from behaviour. A manifest
maintained beside the code rather than tied to it converts an unknown blind spot
into a false assurance, which is worse than having none, so the decisive test
here is not that the manifest lists the right things today. It is that breaking a
checker makes the manifest say so.
"""

from __future__ import annotations

import dataclasses
from unittest import mock

from cyo_adventure.validator.blind_spots import (
    OBSERVED,
    UNOBSERVED,
    _base,  # pyright: ignore[reportPrivateUsage]
    annotate,
    blind_spots,
    verify_declarations,
)
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.report import ValidationReport


def test_every_declaration_still_describes_the_gate() -> None:
    """The battery must be green against the real gate, unpatched.

    A stale entry here is not a test failure about this module; it means the
    manifest is currently lying about what the gate observes.
    """
    assert verify_declarations() == []


def test_the_manifest_names_the_qualitative_age_dimensions_as_unobserved() -> None:
    """The AL-337 case, which is the reason this module exists.

    "Safe and age-appropriate, verifiably" was claimed at the highest confidence
    in the programme while the age-appropriateness half rested on a
    Flesch-Kincaid grade. Flesch-Kincaid is the quantitative leg of a three-leg
    construct; nothing in the pipeline observes the other three, and a clean
    verdict said nothing about that.
    """
    for context in ("skeleton", "fill_result"):
        spots = blind_spots(context)  # pyright: ignore[reportArgumentType]
        assert "levels_of_meaning" in spots
        assert "text_structure" in spots
        assert "language_conventionality" in spots
        assert "knowledge_demands" in spots


def test_filled_prose_is_unobserved_on_a_skeleton_and_observed_on_a_fill() -> None:
    """The AL-325 case, expressed as the difference between two contexts.

    Every deterministic checker correctly skips a ``<<FILL>>`` body at catalogue
    time, and four correct skips composed into a pass on a book that was never
    written. PL-27 closed that for fill results. It does not run on a skeleton,
    correctly, and a skeleton-context verdict has to say so rather than let the
    silence read as coverage.
    """
    assert "filled_prose" in blind_spots("skeleton")
    assert "filled_prose" not in blind_spots("fill_result")


def test_a_checker_that_stops_checking_makes_its_declaration_stale() -> None:
    """The decisive test: the manifest must notice a checker going quiet.

    This is what separates a declaration tied to behaviour from a constant
    maintained beside it. If this test can be made to pass with the checker
    disabled, the manifest is a hand-kept list and W6's rule says to delete it
    and write prose instead.
    """
    # Before: the declaration is sound.
    assert verify_declarations() == []

    with mock.patch(
        "cyo_adventure.validator.gate.check_reading_level",
        return_value=ValidationReport(),
    ):
        stale = verify_declarations()

    assert len(stale) == 1
    assert stale[0].startswith("reading_level_quantitative")
    assert "RL-13" in stale[0]

    # After: the patch is gone and so is the finding, so the check is measuring
    # the checker rather than something incidental about the run.
    assert verify_declarations() == []


def test_a_declaration_naming_a_rule_that_never_fires_is_reported() -> None:
    """A declaration that was never true must fail the same way a stale one does.

    The drift check cannot only catch regressions: an entry added with an
    optimistic rule id and no witness that trips it would otherwise sit in the
    manifest asserting coverage that never existed.
    """
    invented = dataclasses.replace(OBSERVED[0], rules=frozenset({"XX-999"}))

    stale = verify_declarations([invented])

    assert len(stale) == 1
    assert "XX-999" in stale[0]


def test_annotate_carries_the_scope_of_a_verdict_alongside_the_verdict() -> None:
    """A consumer reading ``ok`` must see what ``ok`` did not cover.

    Putting the two in one object is the whole intervention: the failure was
    never that a checker was wrong, it was that a claim was stated over a
    dimension nothing in the composition observed.
    """
    clean = run_gate(_clean_document(), context="fill_result")

    annotated = annotate(clean.report, "fill_result")

    assert annotated["ok"] is clean.report.ok
    assert annotated["context"] == "fill_result"
    unobserved = annotated["unobserved_dimensions"]
    assert isinstance(unobserved, list)
    assert set(UNOBSERVED) <= set(unobserved)


def _clean_document() -> dict[str, object]:
    """Return a document the gate passes, for the annotation test.

    Returns:
        The base witness document with nothing broken.
    """
    return _base()
