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


# ---------------------------------------------------------------------------
# CH-3a / CH-3b / CH-4: the walk-based envelope rules
# ---------------------------------------------------------------------------


def _six_way_archetype_story(**overrides: Any) -> dict[str, Any]:
    """A Tier-2 story whose own graph, not any carried envelope, sets ``archetype``.

    "gate" offers two choices: "build" (visible only at ``archetype == 0``,
    the declared initial) and "to_hall" (visible only at ``archetype != 0``).
    "build" leads to a node offering six unconditional picks, one per
    archetype code, each of which sets ``archetype`` and loops back to
    "gate" rather than going straight to "hall". That loop-back is load
    bearing: it is what makes "to_hall" visible from the single
    declared-initial walk (once "gate" is revisited with
    ``archetype != 0``), with no envelope state required at all. Sending
    ``pick_i`` straight to "hall" instead would leave "to_hall" invisible in
    every configuration of that single walk (nothing else ever revisits
    "gate" at a nonzero archetype), which is a genuine L2-11 dead branch at
    baseline, not the envelope-only scenario this fixture exists to isolate.

    This is exactly the fixture CH-3a's union quantification needs: a naive
    per-state check, walking each of the seven envelope states
    (``archetype`` 0-6) in isolation, would flag "build" as dead in every
    ``archetype != 0`` state (nothing in that single-state walk ever sets
    archetype back to 0) and flag "to_hall" as dead in the ``archetype == 0``
    state. Taking the union across the baseline walk and all seven envelope
    walks together correctly recognises both choices are visible somewhere,
    so CH-3a stays silent; a per-state check would reject what the union
    check accepts.
    """
    data: dict[str, Any] = {
        "schema_version": "2.1",
        "id": "ch-six-way",
        "version": 1,
        "title": "Six Way",
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
            "topology": "loop_and_grow",
        },
        "variables": [
            {"name": "archetype", "type": "int", "initial": 0, "min": 0, "max": 6},
        ],
        "accepts_character": {"archetype": {"min": 0, "max": 6}},
        "start_node": "gate",
        "nodes": [
            {
                "id": "gate",
                "body": "A gate stands before you.",
                "choices": [
                    {
                        "id": "build",
                        "label": "Choose who you are.",
                        "target": "build",
                        "condition": {"==": [{"var": "archetype"}, 0]},
                    },
                    {
                        "id": "to_hall",
                        "label": "Enter the hall.",
                        "target": "hall",
                        "condition": {"!=": [{"var": "archetype"}, 0]},
                    },
                ],
            },
            {
                "id": "build",
                "body": "Pick who you will be.",
                "choices": [
                    {
                        "id": f"pick_{i}",
                        "label": f"Become archetype {i}.",
                        "target": "gate",
                        "effects": [{"op": "set", "var": "archetype", "value": i}],
                    }
                    for i in range(1, 7)
                ],
            },
            {
                "id": "hall",
                "body": "You arrive in the hall.",
                "is_ending": True,
                "ending": {
                    "id": "e_hall",
                    "kind": "success",
                    "valence": "positive",
                    "title": "You Arrive",
                },
            },
        ],
    }
    data.update(overrides)
    return data


def test_ch3a_accepts_what_a_per_state_check_would_reject() -> None:
    data = _six_way_archetype_story()
    assert _ids(Storybook.model_validate(data), "CH-3a") == []


def test_the_six_way_book_passes_the_existing_gate_from_declared_initials() -> None:
    """L2-11 (the existing, non-envelope-aware dead-branch check) stays clean.

    Pins that the six-way fixture's own graph, walked only from its declared
    initial (no carried state at all), already makes every choice visible.
    If this regresses, the fixture itself is broken and the CH-3a tests above
    would not be testing what they claim to.
    """
    data = _six_way_archetype_story()
    result = run_gate(data)
    assert [f.rule_id for f in result.report.findings if f.rule_id == "L2-11"] == []


def test_ch3a_reports_a_branch_invisible_in_every_state() -> None:
    """A choice gated on an impossible value is dead in the union too.

    ``archetype`` never carries 7: the canonical vocabulary and this story's
    own declared bounds both cap it at 6. A choice visible only at
    ``archetype == 7`` is therefore invisible in the baseline walk and in
    every one of the seven envelope states, so it is dead under the union
    quantification too, unlike the six legitimate branches above.
    """
    data = _six_way_archetype_story()
    data["nodes"][0]["choices"].append(
        {
            "id": "to_secret",
            "label": "Slip through a secret door.",
            "target": "hall",
            "condition": {"==": [{"var": "archetype"}, 7]},
        }
    )
    assert len(_ids(Storybook.model_validate(data), "CH-3a")) >= 1


def _masked_second_dead_end_story(**overrides: Any) -> dict[str, Any]:
    """A book with one baseline L2-9 defect that a naive signature would hide again.

    "hold" is a stateful dead end at the declared initial (``might == 0``):
    its only choice, "leave", needs ``might == 1``. That is a real, pre-existing
    defect in this book's own baseline walk (accepted here, not fixed, so the
    fixture can prove CH-3b distinguishes it from a *new* one). At
    ``might == 2`` "leave" is still invisible (``2 != 1``), so "hold" is a
    dead end there too, for the reader's own accepts_character-carried
    reason, not the book's.

    Neither L2-9 finding ever sets ``choice_id`` (only L2-11 does), so the
    ``rule_id|node_id|choice_id`` signature is identical for both:
    ``L2-9|hold|``. A signature built from only those three fields cannot
    tell "the book's own known defect" apart from "a new defect this reader's
    carried state introduces" when both land on the same node, which is
    exactly the masking this fixture is built to exercise.
    """
    data: dict[str, Any] = {
        "schema_version": "2.1",
        "id": "ch-masked-dead-end",
        "version": 1,
        "title": "Masked Dead End",
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
        "accepts_character": {"might": {"min": 0, "max": 2}},
        "start_node": "start",
        "nodes": [
            {
                "id": "start",
                "body": "You approach a locked door.",
                "choices": [
                    {
                        "id": "wait_here",
                        "label": "Wait by the door.",
                        "target": "hold",
                    }
                ],
            },
            {
                "id": "hold",
                "body": "You wait, hoping for a way through.",
                "choices": [
                    {
                        "id": "leave",
                        "label": "Force the door open.",
                        "target": "win",
                        "condition": {"==": [{"var": "might"}, 1]},
                    }
                ],
            },
            {
                "id": "win",
                "body": "The door gives way.",
                "is_ending": True,
                "ending": {
                    "id": "e_win",
                    "kind": "success",
                    "valence": "positive",
                    "title": "Through",
                },
            },
        ],
    }
    data.update(overrides)
    return data


def test_ch3b_distinguishes_two_dead_branches_on_one_node() -> None:
    """The might == 2 dead end at "hold" must survive baseline diffing.

    ``might == 0`` (the declared initial) reproduces the book's own baseline
    defect and must stay suppressed; ``might == 1`` is clean ("leave" becomes
    visible); ``might == 2`` is a second, genuinely different dead end on the
    same node that a ``rule_id|node_id|choice_id``-only signature would wrongly
    collapse into the baseline one, because L2-9 never sets ``choice_id``.
    """
    data = _masked_second_dead_end_story()
    assert len(_ids(Storybook.model_validate(data), "CH-3b")) >= 1


def _unreachable_win_for_one_state_story(**overrides: Any) -> dict[str, Any]:
    """A book where only ``might == 2`` can still reach its satisfying ending.

    "branch" offers exactly one visible choice per state: "advance"
    (``might >= 2``) reaches the success ending "win"; "retreat"
    (``might < 2``) reaches the setback ending "lose". A reader carried in at
    ``might`` 0 or 1 can therefore never reach "win"; only ``might == 2`` can.
    """
    data: dict[str, Any] = {
        "schema_version": "2.1",
        "id": "ch-narrow-win",
        "version": 1,
        "title": "Narrow Win",
        "metadata": {
            "age_band": "13-16",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 6.0,
                "tolerance": 1.0,
            },
            "tier": 2,
            "estimated_minutes": 5,
            "ending_count": 2,
            "topology": "branch_and_bottleneck",
        },
        "variables": [
            {"name": "might", "type": "int", "initial": 0, "min": 0, "max": 2},
        ],
        "accepts_character": {"might": {"min": 0, "max": 2}},
        "start_node": "branch",
        "nodes": [
            {
                "id": "branch",
                "body": "You size up the wall.",
                "choices": [
                    {
                        "id": "advance",
                        "label": "Climb over.",
                        "target": "win",
                        "condition": {">=": [{"var": "might"}, 2]},
                    },
                    {
                        "id": "retreat",
                        "label": "Turn back.",
                        "target": "lose",
                        "condition": {"<": [{"var": "might"}, 2]},
                    },
                ],
            },
            {
                "id": "win",
                "body": "You clear the wall.",
                "is_ending": True,
                "ending": {
                    "id": "e_win",
                    "kind": "success",
                    "valence": "positive",
                    "title": "Over",
                },
            },
            {
                "id": "lose",
                "body": "You turn back, wall unclimbed.",
                "is_ending": True,
                "ending": {
                    "id": "e_lose",
                    "kind": "setback",
                    "valence": "negative",
                    "title": "Turned Back",
                },
            },
        ],
    }
    data.update(overrides)
    return data


def test_ch4_reports_the_states_that_cannot_win() -> None:
    data = _unreachable_win_for_one_state_story()
    assert len(_ids(Storybook.model_validate(data), "CH-4")) == 2


def test_ch4_is_silent_when_every_state_can_win() -> None:
    """Reuses the six-way fixture: "hall" is reachable from all seven states.

    The six-way graph loops every archetype value back through "gate" and on
    to "hall", so a satisfying ending is reachable from the baseline and
    every one of the seven envelope states; CH-4 must not flag any of them.
    """
    data = _six_way_archetype_story()
    assert _ids(Storybook.model_validate(data), "CH-4") == []
