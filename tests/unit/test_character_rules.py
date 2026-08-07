"""Tests for the CH-* character envelope rules (ADR-028 decision 5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.character import validate_character
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.report import Severity

_VALID_TIER2_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "03_tier2_lantern.json"
)


def _story_dict(**overrides: Any) -> dict[str, Any]:
    """Build a minimal, schema-2.1, Tier-2 story dict for CH-only checks.

    ``validate_character`` is called directly against the parsed model in
    most tests here, so this fixture only needs to satisfy Storybook's own
    pydantic invariants (start_node exists, ending_count matches, Tier-2
    permits variables); it does not need to pass Layer 1/2. Tests that need
    a fully gate-clean story use ``_gate_clean_story_dict`` instead.
    """
    data: dict[str, Any] = {
        "schema_version": "2.1",
        "id": "ch-test",
        "version": 1,
        "title": "CH Test",
        "metadata": {
            "age_band": "13-16",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 6.0,
                "tolerance": 1.0,
            },
            "tier": 2,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "gauntlet",
        },
        "variables": [
            {"name": "might", "type": "int", "initial": 0, "min": 0, "max": 2},
        ],
        "start_node": "n1",
        "nodes": [
            {
                "id": "n1",
                "body": "The end.",
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "kind": "success",
                    "valence": "positive",
                    "title": "The End",
                },
            }
        ],
    }
    data.update(overrides)
    return data


def _gate_clean_story_dict(**overrides: Any) -> dict[str, Any]:
    """Load the known-clean Tier-2 fixture used by ``test_gate.py``.

    ``test_clean_tier2_passes_gate`` pins this fixture as ``blocked is
    False`` and ``report.ok is True`` before any character rule exists.
    Building the gate-blocking test on top of it, rather than on the minimal
    ``_story_dict`` above, is what lets the mutation experiment mean
    anything: if the base story carried some other ERROR, removing "CH" from
    the blocked-prefix tuple would still leave ``blocked is True`` and the
    test would pass in both worlds.
    """
    data: dict[str, Any] = json.loads(_VALID_TIER2_FIXTURE.read_text(encoding="utf-8"))
    data["schema_version"] = "2.1"
    data["variables"].append(
        {"name": "might", "type": "int", "initial": 0, "min": 0, "max": 2}
    )
    data.update(overrides)
    return data


def _ids(story: Storybook, prefix: str) -> list[str]:
    report = validate_character(story)
    return [
        f.rule_id
        for f in report.findings
        if f.rule_id.startswith(prefix) and f.severity is Severity.ERROR
    ]


def test_ch1_accepts_a_canonical_name_declared_with_a_matching_type() -> None:
    data = _story_dict(accepts_character={"might": {"min": 0, "max": 2}})
    assert _ids(Storybook.model_validate(data), "CH-1") == []


def test_ch1_rejects_a_name_outside_the_vocabulary() -> None:
    data = _story_dict()
    data["variables"].append(
        {"name": "swagger", "type": "int", "initial": 0, "min": 0, "max": 2}
    )
    data["accepts_character"] = {"swagger": {"min": 0, "max": 2}}
    assert _ids(Storybook.model_validate(data), "CH-1") == ["CH-1"]


def test_ch1_rejects_an_envelope_name_not_declared_as_a_variable() -> None:
    data = _story_dict(accepts_character={"wits": {"min": 0, "max": 2}})
    assert _ids(Storybook.model_validate(data), "CH-1") == ["CH-1"]


def test_ch1_rejects_a_type_mismatch() -> None:
    data = _story_dict()
    data["variables"] = [{"name": "might", "type": "bool", "initial": False}]
    data["accepts_character"] = {"might": {"min": 0, "max": 2}}
    assert _ids(Storybook.model_validate(data), "CH-1") == ["CH-1"]


def test_ch2_rejects_an_envelope_narrower_than_the_declared_bounds() -> None:
    """The narrower case is the one the runtime clamp hides.

    G3 clamps to *declared* bounds, so an envelope of 0-1 against a variable
    declared 0-2 lets a reader arrive at 2 in a state the validator never
    walked, with nothing at runtime reporting it.
    """
    data = _story_dict(accepts_character={"might": {"min": 0, "max": 1}})
    assert _ids(Storybook.model_validate(data), "CH-2") == ["CH-2"]


def test_ch2_rejects_an_envelope_wider_than_the_declared_bounds() -> None:
    data = _story_dict()
    data["variables"] = [
        {"name": "might", "type": "int", "initial": 0, "min": 0, "max": 1}
    ]
    data["accepts_character"] = {"might": {"min": 0, "max": 2}}
    assert _ids(Storybook.model_validate(data), "CH-2") == ["CH-2"]


def test_ch2_rejects_a_variable_with_absent_bounds() -> None:
    """Variable.min and Variable.max default to None.

    You cannot equal an absent bound, so an opted-in book must declare both.
    """
    data = _story_dict()
    data["variables"] = [{"name": "might", "type": "int", "initial": 0}]
    data["accepts_character"] = {"might": {"min": 0, "max": 2}}
    assert _ids(Storybook.model_validate(data), "CH-2") == ["CH-2"]


def test_ch5_rejects_an_envelope_above_the_entry_state_cap() -> None:
    """Four 0-6 variables is 2,401 states against a 64 cap.

    CH-5 errors rather than truncating: an envelope is declared, so exceeding
    the cap is an authoring mistake with an obvious fix, and validating a
    truncated sample of a declared envelope would report a book clean over
    states nobody walked.
    """
    data = _story_dict()
    data["variables"] = [
        {"name": name, "type": "int", "initial": 0, "min": 0, "max": 6}
        for name in ("archetype", "might", "wits", "nerve")
    ]
    data["accepts_character"] = {
        name: {"min": 0, "max": 6} for name in ("archetype", "might", "wits", "nerve")
    }
    assert _ids(Storybook.model_validate(data), "CH-5") == ["CH-5"]


def test_ch6_rejects_a_canonical_name_without_opting_in() -> None:
    """Without CH-6, "omitting accepts_character changes nothing" is false.

    G3 name-match seeds any book declaring a canonical name, opted in or not.
    If this rule ever becomes a no-op this is the test that catches it.
    """
    data = _story_dict()
    assert "accepts_character" not in data
    assert _ids(Storybook.model_validate(data), "CH-6") == ["CH-6"]


def test_ch6_is_silent_for_a_book_using_no_canonical_name() -> None:
    data = _story_dict()
    data["variables"] = [{"name": "lantern_lit", "type": "bool", "initial": False}]
    assert _ids(Storybook.model_validate(data), "CH-6") == []


def test_ch6_rejects_an_uncovered_canonical_name_in_an_opted_in_book() -> None:
    """CH-6's other half: the converse of CH-1's envelope -> variable direction.

    CH-1 only ever walks accepts_character -> variables, so an opted-in book
    that declares a second canonical-named variable outside its envelope
    passes CH-1 cleanly. Without this half, that variable would still be
    seeded by G3 name-match over states this book's Layer 2 walk never
    proved. If only CH-1 existed, this scenario would produce no CH-6
    finding at all.
    """
    data = _story_dict(accepts_character={"might": {"min": 0, "max": 2}})
    data["variables"].append(
        {"name": "wits", "type": "int", "initial": 0, "min": 0, "max": 2}
    )
    assert _ids(Storybook.model_validate(data), "CH-6") == ["CH-6"]


def test_ch7_still_runs_for_an_opted_in_book_with_an_empty_envelope() -> None:
    """Pins the ``None``-vs-``{}`` branch: ``accepts_character={}`` opts in.

    ``None`` means "did not opt in"; ``{}`` means "opted in with an empty
    envelope declared". A slip to ``if not story.accepts_character:`` would
    route this empty-but-opted-in book through the opt-out branch, which
    only ever runs CH-6, so CH-7 would never be evaluated and this later,
    state-carrying book would wrongly pass despite also declaring
    ``accepts_character``.
    """
    data = _story_dict(accepts_character={})
    data["metadata"]["series"] = {
        "series_id": "s1",
        "book_index": 2,
        "carries_state": True,
    }
    assert _ids(Storybook.model_validate(data), "CH-7") == ["CH-7"]


def test_ch7_rejects_a_later_book_of_a_state_carrying_series() -> None:
    data = _story_dict(accepts_character={"might": {"min": 0, "max": 2}})
    data["metadata"]["series"] = {
        "series_id": "s1",
        "book_index": 2,
        "carries_state": True,
    }
    assert _ids(Storybook.model_validate(data), "CH-7") == ["CH-7"]


def test_ch7_allows_the_first_book_of_a_series() -> None:
    data = _story_dict(accepts_character={"might": {"min": 0, "max": 2}})
    data["metadata"]["series"] = {
        "series_id": "s1",
        "book_index": 1,
        "carries_state": True,
    }
    assert _ids(Storybook.model_validate(data), "CH-7") == []


def test_ch7_allows_a_later_book_of_an_episodic_series() -> None:
    """The ``carries_state`` conjunct: both other CH-7 tests set it ``True``.

    Without this case, deleting ``series.carries_state and`` from CH-7's
    condition would leave the suite green: an episodic (``carries_state:
    False``) later book would wrongly light up CH-7 and nothing would catch
    it.
    """
    data = _story_dict(accepts_character={"might": {"min": 0, "max": 2}})
    data["metadata"]["series"] = {
        "series_id": "s1",
        "book_index": 2,
        "carries_state": False,
    }
    assert _ids(Storybook.model_validate(data), "CH-7") == []


def test_a_ch_error_blocks_the_gate() -> None:
    """The assertion this whole task exists for.

    gate.py computes ``blocked`` from a hard-coded rule-id prefix tuple. A CH-*
    ERROR added without extending that tuple lands in the report and blocks
    nothing, and every "did CH-N fire" assertion passes in both worlds. Only
    ``blocked`` distinguishes them.
    """
    data = _gate_clean_story_dict(accepts_character={"might": {"min": 0, "max": 1}})
    result = run_gate(data)
    assert any(f.rule_id == "CH-2" for f in result.report.findings)
    assert result.blocked is True
