"""Tests for the naive-ux-check scenario data file.

`scenarios.json` (`.claude/skills/naive-ux-check/scenarios.json`) is the
single source of truth for the 17 naive-user comprehension scenarios
(K0-K4, G0-G7, A0-A3; task D2a). Two properties matter enough to be
enforced by structure rather than by a human reading SKILL.md's
instructions:

1. Every scenario round-trips: all required fields are present and
   non-empty, and the id set is exactly the expected 17 with no
   duplicates.
2. Operator-only content (`operator_notes`: operator setup lines,
   operator notes, and expected-observations paragraphs) can never reach
   the block that gets pasted into the model. SKILL.md says twice,
   emphatically, that a prompt leaking its own expected observations
   tests transcription, not comprehension, so every verdict downstream of
   a leak would be worthless.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

SCENARIOS_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "skills"
    / "naive-ux-check"
    / "scenarios.json"
)

EXPECTED_IDS = (
    [f"K{i}" for i in range(5)]
    + [f"G{i}" for i in range(8)]
    + [f"A{i}" for i in range(4)]
)

REQUIRED_FIELDS = (
    "id",
    "persona",
    "name",
    "persona_text",
    "task_text",
    "report_back_questions",
    "requires_credentials",
    "production_safe",
    "operator_notes",
)

MUTATING_SCENARIO_IDS = frozenset({"G4", "G5", "G6", "A2", "A3"})

PREFIX_TO_PERSONA = {"K": "kid", "G": "guardian", "A": "admin"}


def _load_scenarios() -> list[dict[str, Any]]:
    return json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))


def compose_paste_block(scenario: dict[str, Any]) -> str:
    """Render the block a human pastes into the Claude-for-Chrome extension.

    Mirrors SKILL.md step 4: an ALLOWLIST of exactly the three model-facing
    fields (`persona_text`, `task_text`, `report_back_questions`). Nothing
    else on the scenario, including `operator_notes` and any field added to
    the schema later, is ever read here. The allowlist shape (not a
    blacklist of `operator_notes`) is what makes the separation structural:
    a new field lands outside the paste block by default, not inside it.
    """
    questions = "\n".join(
        f"{i}. {q}" for i, q in enumerate(scenario["report_back_questions"], start=1)
    )
    return (
        f"Persona: {scenario['persona_text']}\n\n"
        f"Task: {scenario['task_text']}\n\n"
        f"Report back:\n\n{questions}"
    )


def _compose_paste_block_leaky(scenario: dict[str, Any]) -> str:
    """A deliberately wrong composer, used only to prove the leak test bites.

    This is the exact defect class the leak test exists to catch: operator
    notes reaching the model-facing block. It must never be wired into
    `compose_paste_block`; it exists so `test_leaky_composer_is_caught_...`
    below can show the detection logic is not vacuous without requiring a
    hand mutation on every test run.
    """
    return (
        compose_paste_block(scenario)
        + "\n\n"
        + json.dumps(scenario.get("operator_notes", {}))
    )


def _iter_operator_strings(node: Any):
    """Yield every non-blank string leaf found anywhere under `node`.

    Deliberately generic over shape: walks dicts and lists recursively
    instead of hardcoding today's three `operator_notes` sub-keys
    (`operator_setup`, `operator_note`, `expected_observations`). A future
    field added anywhere under `operator_notes` is covered automatically,
    without editing this test.
    """
    if isinstance(node, str):
        if node.strip():
            yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_operator_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_operator_strings(item)


# ---------------------------------------------------------------------------
# Round-trip: every one of the 17 scenarios has every required field,
# non-empty, and the id set is exactly right with no duplicates.
# ---------------------------------------------------------------------------


def test_scenario_ids_are_exactly_the_expected_17_with_no_duplicates():
    scenarios = _load_scenarios()
    ids = [s["id"] for s in scenarios]
    assert len(ids) == 17, f"expected 17 scenarios, found {len(ids)}: {ids}"
    assert len(ids) == len(set(ids)), "duplicate scenario ids in scenarios.json"
    assert set(ids) == set(EXPECTED_IDS), (
        f"id set mismatch: missing={set(EXPECTED_IDS) - set(ids)}, "
        f"unexpected={set(ids) - set(EXPECTED_IDS)}"
    )
    # Array order is the selection order SKILL.md relies on: K0-K4, G0-G7,
    # A0-A3, with each persona's auth-gate scenario first in its group.
    assert ids == EXPECTED_IDS


@pytest.mark.parametrize("scenario", _load_scenarios(), ids=lambda s: s["id"])
def test_scenario_has_all_required_fields_non_empty(scenario: dict[str, Any]):
    for field in REQUIRED_FIELDS:
        assert field in scenario, f"{scenario.get('id', '?')} missing field {field!r}"

    assert scenario["id"].strip()
    assert scenario["name"].strip()
    assert scenario["persona_text"].strip()
    assert scenario["task_text"].strip()
    assert scenario["persona"] in ("kid", "guardian", "admin")
    assert isinstance(scenario["requires_credentials"], bool)
    assert isinstance(scenario["production_safe"], bool)

    questions = scenario["report_back_questions"]
    assert isinstance(questions, list)
    assert len(questions) > 0
    assert all(isinstance(q, str) and q.strip() for q in questions)

    assert isinstance(scenario["operator_notes"], dict)


@pytest.mark.parametrize("scenario", _load_scenarios(), ids=lambda s: s["id"])
def test_persona_field_matches_id_prefix(scenario: dict[str, Any]):
    expected_persona = PREFIX_TO_PERSONA[scenario["id"][0]]
    assert scenario["persona"] == expected_persona


def test_credential_and_production_safety_posture_is_unchanged():
    """D2a records these facts; it must not loosen them.

    Per SKILL.md: only K0 (the fresh-device auth-gate scenario) is
    non-credentialed and production-safe. Every other scenario either
    signs in with staging-only seeded credentials or mutates content.
    """
    scenarios = {s["id"]: s for s in _load_scenarios()}
    assert scenarios["K0"]["production_safe"] is True
    assert scenarios["K0"]["requires_credentials"] is False
    for sid, scenario in scenarios.items():
        if sid == "K0":
            continue
        assert scenario["production_safe"] is False, (
            f"{sid} must not be production_safe"
        )
        assert scenario["requires_credentials"] is True, (
            f"{sid} must require credentials"
        )

    for sid in MUTATING_SCENARIO_IDS:
        assert scenarios[sid]["production_safe"] is False


# ---------------------------------------------------------------------------
# The leak test: operator-only content must never reach the paste block.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", _load_scenarios(), ids=lambda s: s["id"])
def test_paste_block_never_leaks_operator_only_content(scenario: dict[str, Any]):
    block = compose_paste_block(scenario)
    for operator_string in _iter_operator_strings(scenario.get("operator_notes", {})):
        assert operator_string not in block, (
            f"{scenario['id']}: operator-only text leaked into the paste block: "
            f"{operator_string!r}"
        )


def test_leaky_composer_is_caught_by_the_operator_content_check():
    """Proves the leak check above is not vacuous.

    Picks a scenario with non-empty `operator_notes`, runs it through the
    deliberately-wrong `_compose_paste_block_leaky`, and confirms the
    operator text the real check looks for is actually present in the
    output. This is the permanent record that the detection logic fires;
    the D2a task additionally required observing the real
    `compose_paste_block` mutated the same way and watching
    `test_paste_block_never_leaks_operator_only_content` go red, which was
    done by hand (see the D2a report) and reverted immediately after.
    """
    scenarios = _load_scenarios()
    leaky_scenario = next(
        s for s in scenarios if any(_iter_operator_strings(s.get("operator_notes", {})))
    )
    operator_strings = list(
        _iter_operator_strings(leaky_scenario.get("operator_notes", {}))
    )
    assert operator_strings, "fixture scenario unexpectedly has no operator_notes text"

    leaky_block = _compose_paste_block_leaky(leaky_scenario)
    assert any(op in leaky_block for op in operator_strings), (
        "the leaky composer should reproduce the exact defect class the leak "
        "test exists to catch; if this fails, the leak test would not have "
        "caught it either"
    )
