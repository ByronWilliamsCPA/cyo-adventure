"""Tests for the CH-* character envelope rules (ADR-028 decision 5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator import character as character_module
from cyo_adventure.validator.character import build_node_headroom, validate_character
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.layer2 import validate_layer2
from cyo_adventure.validator.report import Severity, ValidationFinding, ValidationReport
from cyo_adventure.validator.walk import WalkResult

_VALID_TIER2_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "03_tier2_lantern.json"
)

_SKELETONS = Path(__file__).resolve().parents[2] / "skeletons"


def _load_skeleton(relative: str) -> Storybook:
    """Load a catalog skeleton by its band-relative path, without an envelope."""
    path = _SKELETONS / f"{relative}.json"
    return Storybook.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _skeleton_with_archetype_dict(relative: str) -> dict[str, Any]:
    """Load a catalog skeleton's raw dict and opt it in to a six-way archetype envelope.

    Returns the raw dict rather than a parsed :class:`Storybook`, because
    ``run_gate`` validates raw JSON (Layer 1 must run before anything is
    trusted to parse) while ``validate_character`` needs the parsed model;
    keeping this as a dict lets both call paths share one fixture.
    """
    path = _SKELETONS / f"{relative}.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = "2.1"
    data["variables"] = [
        *data.get("variables", []),
        {"name": "archetype", "type": "int", "initial": 0, "min": 0, "max": 6},
    ]
    data["accepts_character"] = {"archetype": {"min": 0, "max": 6}}
    return data


def _load_skeleton_with_archetype(relative: str) -> Storybook:
    """Load a catalog skeleton and opt it in to a six-way archetype envelope."""
    return Storybook.model_validate(_skeleton_with_archetype_dict(relative))


def _flooded_quarter_with_narrow_archetype_dict() -> dict[str, Any]:
    """C1 regression fixture: a declared ``1..6`` archetype span still means six.

    Reproduces the exact bypass from the task-7 review. CH-2 only checks that
    the envelope range equals the *declared variable's own* range, not that
    either equals the canonical ``0..6``, so a book may declare both its
    ``archetype`` variable and its envelope span as ``1..6``: schema-valid,
    passes CH-1 and CH-2 cleanly, and an in-story build node can still set any
    of the same six real archetype values (1-6) that a full ``0..6``
    declaration would allow. It simply omits the ``0`` ("not yet chosen")
    sentinel state; the build node never sets that state anyway, so nothing
    about the real branching factor changed.

    the-flooded-quarter measures 19,236 baseline configs: below the buggy
    5-way threshold of 20,000 (a formula reading ``span.max - span.min``
    would let this through silently) but above the true 6-way threshold of
    16,666 (what a vocabulary-derived arity correctly rejects on).
    """
    path = _SKELETONS / "10-13/the-flooded-quarter.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = "2.1"
    data["variables"] = [
        *data.get("variables", []),
        {"name": "archetype", "type": "int", "initial": 1, "min": 1, "max": 6},
    ]
    data["accepts_character"] = {"archetype": {"min": 1, "max": 6}}
    return data


def _linear_chain_story_dict(length: int) -> dict[str, Any]:
    """Build a Tier-2 story whose baseline walk visits exactly ``length`` configs.

    A straight, unbranching chain of ``length`` nodes with a declared-but-
    never-set variable: the variable's state component of the walk's dedup
    key never changes, so each node contributes exactly one distinct
    ``(node_id, var_state, once_visit)`` triple, giving
    ``len(walk_configurations(story).configs) == length`` exactly (see
    ``validator/walk.py``'s ``ConfigKey``). This gives the I1 boundary tests
    an exact, known baseline count to divide the walk cap against, without a
    real (large, slow) catalog skeleton.
    """
    if length < 1:
        msg = f"length must be at least 1, got {length}"
        raise ValueError(msg)
    nodes: list[dict[str, Any]] = []
    for i in range(1, length + 1):
        node_id = f"n{i}"
        if i == length:
            nodes.append(
                {
                    "id": node_id,
                    "body": "The end.",
                    "is_ending": True,
                    "ending": {
                        "id": "e1",
                        "kind": "success",
                        "valence": "positive",
                        "title": "The End",
                    },
                }
            )
        else:
            nodes.append(
                {
                    "id": node_id,
                    "body": f"Passage {i}.",
                    "choices": [
                        {"id": f"c{i}", "label": "Continue", "target": f"n{i + 1}"}
                    ],
                }
            )
    return {
        "schema_version": "2.1",
        "id": "ch-test-linear-chain",
        "version": 1,
        "title": "CH Test Linear Chain",
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
        "nodes": nodes,
    }


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


def test_ch2_rejects_a_range_wider_than_the_canonical_vocabulary() -> None:
    """Equality alone cannot bound the document: both its operands are the document's.

    A book that declares ``might: 0-3`` on the variable *and* in the envelope
    satisfies the equality check above with zero findings, so without a
    containment check the vocabulary is whatever the document says it is. The
    canonical bounds are the only code-owned operand available.
    """
    data = _story_dict()
    data["variables"] = [
        {"name": "might", "type": "int", "initial": 0, "min": 0, "max": 3}
    ]
    data["accepts_character"] = {"might": {"min": 0, "max": 3}}
    story = Storybook.model_validate(data)
    assert _ids(story, "CH-2") == ["CH-2"]
    message = next(
        f.message for f in validate_character(story).findings if f.rule_id == "CH-2"
    )
    # The canonical range must appear in the message, so the check is provably
    # reading CANONICAL_CHARACTER_VARIABLES rather than any document value.
    assert "canonical vocabulary range 0-2" in message


def test_ch2_rejects_a_lower_bound_below_the_canonical_vocabulary() -> None:
    """Containment is two-sided; widening downward is the same defect."""
    data = _story_dict()
    data["variables"] = [
        {"name": "might", "type": "int", "initial": 0, "min": -1, "max": 2}
    ]
    data["accepts_character"] = {"might": {"min": -1, "max": 2}}
    assert _ids(Storybook.model_validate(data), "CH-2") == ["CH-2"]


def test_ch2_allows_a_range_narrower_than_the_canonical_vocabulary() -> None:
    """Narrowing stays legal, and that asymmetry is the whole point of the rule.

    A book declaring ``might: 0-1`` walks exactly 0-1, and G3 clamps a reader
    carrying 2 down to 1, so the reader lands in a state the validator proved.
    Only widening puts a reader somewhere nothing was walked.
    """
    data = _story_dict()
    data["variables"] = [
        {"name": "might", "type": "int", "initial": 0, "min": 0, "max": 1}
    ]
    data["accepts_character"] = {"might": {"min": 0, "max": 1}}
    assert _ids(Storybook.model_validate(data), "CH") == []


def test_ch2_reports_one_finding_when_the_range_is_both_unequal_and_wide() -> None:
    """A single defect earns a single finding.

    ``0-3`` in the envelope against ``0-2`` on the variable violates equality;
    reporting containment as well would make an author fix one range twice.
    """
    data = _story_dict(accepts_character={"might": {"min": 0, "max": 3}})
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


def test_ch_walk_rules_skip_an_oversized_envelope_instead_of_enumerating_it() -> None:
    """CH-5 blocking an oversized envelope must stop the walk rules from running.

    ``envelope_states`` materializes the full Cartesian product and its own
    docstring says it is unsafe to call on an envelope CH-5 has already
    flagged. A schema-valid Tier-2 story can declare a range this wide,
    nothing upstream bounds a variable's width beyond ``MAX_ABS_STORY_INT``,
    so before the fix ``run_gate`` would build a 50,000,001-entry state list
    for a single book, which is exactly the ``MemoryError`` reproduction that
    drove this fix. CH-5 blocks the book either way, so nothing is lost by
    skipping the walk; this test's own fast completion is the proof the walk
    rules did not run.
    """
    data = _gate_clean_story_dict(
        accepts_character={"might": {"min": 0, "max": 50_000_000}}
    )
    data["variables"][-1]["max"] = 50_000_000
    result = run_gate(data)
    assert result.blocked is True
    ch_ids = {f.rule_id for f in result.report.findings if f.rule_id.startswith("CH-")}
    assert "CH-5" in ch_ids
    assert ch_ids.isdisjoint({"CH-3a", "CH-3b", "CH-4"})


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
    story = Storybook.model_validate(data)
    findings = [
        f
        for f in validate_character(story).findings
        if f.rule_id == "CH-3a" and f.severity is Severity.ERROR
    ]
    assert len(findings) == 1
    assert findings[0].choice_id == "to_secret"


def test_ch3a_stays_silent_when_a_walk_caps() -> None:
    """A capped walk must not be trusted as ground truth for a dead-branch claim.

    Forces every ``walk_configurations`` call CH-3a makes to return an
    empty, capped result, starving ``ever_visible`` of every choice,
    including the six legitimate ones the six-way fixture proves are
    visible once a walk actually completes (see
    ``test_ch3a_accepts_what_a_per_state_check_would_reject``). Without the
    capped check, that starved union would make all six conditional choices
    in this fixture look dead and CH-3a would raise six spurious errors on a
    book that is not actually broken; the fix must stay silent instead.
    """
    data = _six_way_archetype_story()
    story = Storybook.model_validate(data)
    empty_capped = WalkResult(configs={}, edges={}, capped=True)
    with patch(
        "cyo_adventure.validator.character.walk_configurations",
        return_value=empty_capped,
    ):
        findings = [
            f for f in validate_character(story).findings if f.rule_id == "CH-3a"
        ]
    assert findings == []


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

    The exact count is load bearing, not incidental: ``might == 2`` raises
    both an L2-9 dead end at "hold" and an L2-10 unreachable-ending finding
    at "start" (the config one hop upstream, which also can no longer reach
    an ending), so a clean run reports 2. Deleting the baseline diff
    entirely (an ``if False:`` mutation on its suppression guard) would also
    let ``might == 0``'s matching pair through unsuppressed, for 4; a
    ``>= 1`` assertion cannot distinguish those two worlds.
    """
    data = _masked_second_dead_end_story()
    assert len(_ids(Storybook.model_validate(data), "CH-3b")) == 2


def test_ch3b_is_silent_for_the_state_that_matches_the_declared_initial() -> None:
    """CH-3b's baseline diff must suppress the declared-initial state exactly.

    ``might == 0`` is this book's declared initial, so it reproduces the
    baseline's own known L2-9/L2-10 defects rather than introducing a new
    one; the suppression must silence it. ``might == 2`` is a genuinely
    different entry state and must NOT be suppressed. Asserting both
    directions proves the suppression is targeted at the matching state, not
    merely present somewhere: this is the test the review found missing,
    the one that directly exercises the suppression's purpose rather than
    only its absence-detectable side effect.
    """
    data = _masked_second_dead_end_story()
    story = Storybook.model_validate(data)
    findings = [f for f in validate_character(story).findings if f.rule_id == "CH-3b"]
    assert not any("{might=0}" in f.message for f in findings)
    assert any("{might=2}" in f.message for f in findings)


def test_ch3b_reports_a_capped_per_state_walk_instead_of_passing_it_clean() -> None:
    """A per-state walk that hits L2-12's cap must not read as clean.

    ``validate_layer2`` returns only an L2-12 finding when its own walk
    caps, and L2-12 is not in ``_PER_STATE_RULES``, so before the fix this
    state silently contributed nothing: a state whose safety was never
    actually proven read exactly like a state with no defect. Forces the
    walk for ``might == 1`` (the one state the real fixture is clean at) to
    look capped; the fix must report that state explicitly rather than
    staying silent about it.
    """
    data = _masked_second_dead_end_story()
    story = Storybook.model_validate(data)

    def _fake_validate_layer2(
        book: Storybook, *, cap: int = 100_000, carried: dict[str, int] | None = None
    ) -> ValidationReport:
        if carried == {"might": 1}:
            capped_report = ValidationReport()
            capped_report.add(
                ValidationFinding(
                    rule_id="L2-12",
                    severity=Severity.ERROR,
                    story_id=book.id,
                    message="L2-12 forced cap for test",
                )
            )
            return capped_report
        return validate_layer2(book, cap=cap, carried=carried)

    with patch(
        "cyo_adventure.validator.character.validate_layer2",
        side_effect=_fake_validate_layer2,
    ):
        findings = [
            f for f in validate_character(story).findings if f.rule_id == "CH-3b"
        ]
    assert any("{might=1}" in f.message for f in findings)


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


# ---------------------------------------------------------------------------
# CH-8: build-node cost pre-flight
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("skeleton", "fits"),
    [
        ("10-13/the-glass-comet", True),
        ("10-13/the-flooded-quarter", False),
        ("10-13/the-winter-of-the-wolf-queen", False),
    ],
)
def test_ch8_matches_the_measured_catalog_outcomes(skeleton: str, fits: bool) -> None:
    """CH-8 must reject the two books that cap out, before they reach L2-12.

    Measured 2026-08-05: glass-comet 638 configs goes to 3,829 under the
    six-way build-node idiom; flooded-quarter (19,236) and
    winter-of-the-wolf-queen (28,512) both cap.
    """
    story = _load_skeleton(skeleton)
    assert build_node_headroom(story, arity=6) is fits


def test_ch8_reports_a_book_that_cannot_host_its_build_node() -> None:
    data = _skeleton_with_archetype_dict("10-13/the-flooded-quarter")
    story = Storybook.model_validate(data)
    findings = [f for f in validate_character(story).findings if f.rule_id == "CH-8"]
    assert len(findings) == 1
    assert "16,666" in findings[0].message
    # M1: a CH-8 ERROR must actually stop the gate, not just be reported.
    result = run_gate(data)
    assert result.blocked is True
    assert any(f.rule_id == "CH-8" for f in result.report.findings)


def test_ch8_is_silent_for_a_book_with_headroom() -> None:
    story = _load_skeleton_with_archetype("10-13/the-glass-comet")
    assert [f for f in validate_character(story).findings if f.rule_id == "CH-8"] == []


def test_ch8_is_silent_when_the_envelope_has_no_archetype_span() -> None:
    """CH-8 returns early without a walk when accepts_character omits archetype.

    Distinct from ``test_ch8_is_silent_for_a_book_with_headroom`` above: this
    proves the *early-return* path (no ``archetype`` key at all), not the
    walk-and-compare path. Reuses ``might``, which every catalog book's own
    CH-1/CH-2 tests already exercise, so a mutation that deleted the ``span
    is None`` guard would surface here as a spurious walk over an unrelated
    variable rather than as a wrong finding.
    """
    data = _story_dict(accepts_character={"might": {"min": 0, "max": 2}})
    findings = [
        f
        for f in validate_character(Storybook.model_validate(data)).findings
        if f.rule_id == "CH-8"
    ]
    assert findings == []


def test_ch8_still_evaluates_a_single_value_declared_archetype_span() -> None:
    """A declared 0-0 span no longer short-circuits CH-8; arity is a vocabulary constant.

    Before the fix, ``arity = span.max - span.min`` read a single-value
    declared span as arity 0 and returned before any walk. That early return
    is gone: ``arity`` now always comes from ``len(ARCHETYPE_ROSTER)``
    regardless of the declared span's width, because the declared width is
    exactly the value C1 showed cannot be trusted. This tiny, single-node
    fixture still clears CH-8 (ample headroom at arity 6), proving the walk
    ran and stayed silent, not that it was skipped.
    """
    data = _story_dict()
    data["variables"] = [
        {"name": "archetype", "type": "int", "initial": 0, "min": 0, "max": 0},
    ]
    data["accepts_character"] = {"archetype": {"min": 0, "max": 0}}
    findings = [
        f
        for f in validate_character(Storybook.model_validate(data)).findings
        if f.rule_id == "CH-8"
    ]
    assert findings == []


def test_ch8_rejects_a_narrow_declared_span_that_still_means_six_archetypes() -> None:
    """C1 regression: arity must come from the vocabulary, never the declared span.

    Before the fix, ``arity = span.max - span.min`` read this book's declared
    ``1..6`` span as arity 5, moving CH-8's threshold from 16,666 to 20,000
    configurations and letting this exact 19,236-config book through with
    zero findings from any rule, with ``run_gate`` returning
    ``blocked=False``. Confirmed by running this exact assertion against the
    pre-fix formula: it failed there (no CH-8 finding, ``blocked=False``) and
    passes here.
    """
    data = _flooded_quarter_with_narrow_archetype_dict()
    story = Storybook.model_validate(data)
    findings = [f for f in validate_character(story).findings if f.rule_id == "CH-8"]
    assert len(findings) == 1
    assert "16,666" in findings[0].message

    result = run_gate(data)
    assert result.blocked is True
    assert any(f.rule_id == "CH-8" for f in result.report.findings)


def _narrow_win_with_archetype_dict() -> dict[str, Any]:
    """The CH-4 fixture, opted in to an ``archetype`` span as well as ``might``.

    ``might`` 0-2 crossed with ``archetype`` 0-6 is 21 entry states, well
    under ``MAX_ENTRY_STATES``, so the walk block is size-eligible and CH-4
    fires on the 14 states that cannot reach "win". Adding ``archetype`` is
    what makes CH-8 applicable to the same fixture: CH-8 returns early when
    the envelope declares no ``archetype`` span at all.
    """
    data = _unreachable_win_for_one_state_story()
    data["variables"] = [
        *data["variables"],
        {"name": "archetype", "type": "int", "initial": 0, "min": 0, "max": 6},
    ]
    data["accepts_character"] = {
        "might": {"min": 0, "max": 2},
        "archetype": {"min": 0, "max": 6},
    }
    return data


def test_ch_walk_rules_do_not_run_on_a_book_ch8_has_already_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CH ERROR other than CH-5 must also stop the walk rules from running.

    The walk block used to be entered on envelope size alone, so a book CH-8
    had already rejected still paid for a full walk per entry state: measured
    on longwinter-station with a seven-state archetype envelope, CH-8 decided
    the rejection in about 0.7s and the walk then ran for roughly 11.5s more
    on a book that was already blocked.

    Elapsed time is not the assertion, because a timing assertion passes in
    both worlds on a fast machine. Instead the same fixture is run twice. The
    control run proves the walk rules genuinely produce findings here (14
    CH-4 findings, one per entry state that cannot reach the satisfying
    ending) and that CH-8 is silent. Shrinking ``_WALK_CAP`` then makes CH-8
    fire on that identical fixture, and the CH-4 findings must disappear:
    they can only disappear because the walk block was skipped.
    """
    data = _narrow_win_with_archetype_dict()
    story = Storybook.model_validate(data)

    control = validate_character(story)
    assert "CH-8" not in control.rule_ids()
    assert len([f for f in control.findings if f.rule_id == "CH-4"]) == 14

    # A cap of 6 puts CH-8's threshold at 1 configuration, which this book
    # exceeds, so CH-8 rejects it without any envelope-size rule firing.
    monkeypatch.setattr(character_module, "_WALK_CAP", 6)
    blocked = validate_character(story)
    assert "CH-8" in blocked.rule_ids()
    assert "CH-5" not in blocked.rule_ids()
    assert blocked.rule_ids().isdisjoint({"CH-3a", "CH-3b", "CH-4"})


def test_build_node_headroom_rejects_arity_below_one() -> None:
    data = _story_dict()
    story = Storybook.model_validate(data)
    with pytest.raises(ValueError, match="arity must be at least 1"):
        build_node_headroom(story, arity=0)


def test_build_node_headroom_boundary_pins_the_inclusive_comparison() -> None:
    """I1: pin the ``<=`` boundary in :func:`build_node_headroom` exactly.

    An eight-node linear chain has exactly 8 baseline configs. At arity
    12_500 the threshold is ``100_000 // 12_500 == 8``, exactly at the
    boundary (must fit); at arity 14_285 the threshold is 7, one below (must
    not fit); at arity 11_111 the threshold is 9, one above (must fit).
    Mutating ``<=`` to ``<`` flips only the boundary case, so this pins it
    without touching ``_WALK_CAP`` or needing a real catalog skeleton.
    """
    story = Storybook.model_validate(_linear_chain_story_dict(8))
    assert build_node_headroom(story, arity=12_500) is True
    assert build_node_headroom(story, arity=14_285) is False
    assert build_node_headroom(story, arity=11_111) is True


def test_build_node_headroom_is_fail_closed_on_a_capped_walk() -> None:
    """I2: a capped baseline walk must reject, not silently pass.

    :func:`build_node_headroom` returns ``False`` when the baseline walk hits
    the cap, because a capped walk's ``len(configs)`` is a partial, truncated
    count that could understate the real total. Mutating that branch to
    ``return True`` would survive every other test in this module (none of
    them caps the walk), so this test patches ``walk_configurations`` to
    return a capped result directly and asserts the fail-closed outcome.
    """
    story = Storybook.model_validate(_story_dict())
    capped = WalkResult(configs={}, edges={}, capped=True)
    with patch(
        "cyo_adventure.validator.character.walk_configurations",
        return_value=capped,
    ):
        assert build_node_headroom(story, arity=6) is False
