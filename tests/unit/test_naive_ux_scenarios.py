"""Tests for the naive-ux-check scenario data file and its paste-block renderer.

`scenarios.json` (`.claude/skills/naive-ux-check/scenarios.json`) is the
single source of truth for the 17 naive-user comprehension scenarios
(K0-K4, G0-G7, A0-A3; task D2a). `render.py`
(`.claude/skills/naive-ux-check/render.py`) is the single composer of the
block a human pastes into the Claude-for-Chrome extension: SKILL.md step 4
runs it rather than composing the block itself, so this test imports and
exercises the actual module the skill executes, not a test-local stand-in.

Two properties matter enough to be enforced by structure rather than by a
human reading SKILL.md's instructions:

1. Every scenario round-trips: all required fields are present and
   non-empty, and the id set is exactly the expected 17 with no
   duplicates.
2. Operator-only content (`operator_notes`: operator setup lines, operator
   notes, persona context, and expected-observations paragraphs) can never
   reach the block that gets pasted into the model. SKILL.md says twice,
   emphatically, that a prompt leaking its own expected observations tests
   transcription, not comprehension, so every verdict downstream of a leak
   would be worthless.

Property 2 is checked by an exact-equality assertion against an
independently-built reference string (`_expected_paste_block`, defined only
in this test module), rather than by asserting that specific operator
strings are absent. Equality discriminates on all 17 scenarios, including
the nine (G2-G7, A1-A3) whose `operator_notes` are entirely empty, where a
"forbidden substring is absent" check would pass vacuously. Equality also
catches a leak through a field that isn't under `operator_notes` at all
(a new top-level scenario field, for instance), because anything not named
in `_expected_paste_block`'s three fields changes the comparison.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCENARIOS_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "skills"
    / "naive-ux-check"
    / "scenarios.json"
)

RENDER_MODULE_PATH = SCENARIOS_PATH.parent / "render.py"

# Not a real target; only used to exercise the <URL> substitution the
# renderer performs. Never resolved to a live host.
_TEST_URL = "https://example.invalid/"

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


def _load_render_module() -> ModuleType:
    """Import the real `render.py` the skill executes, by file path.

    `.claude/skills/naive-ux-check/` is not a Python package (it is a
    Claude Code skill directory, not part of `src/cyo_adventure`), so this
    loads the module directly from its path rather than via a package
    import. This is the module under test for the leak property: there is
    exactly one paste-block composer in the repository, and this is it.
    """
    spec = importlib.util.spec_from_file_location(
        "naive_ux_check_render", RENDER_MODULE_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load render module from {RENDER_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render_module = _load_render_module()


def _expected_paste_block(scenario: dict[str, Any], url: str) -> str:
    """Build the paste block independently, from named model-facing fields only.

    This is NOT the composer under test; it exists only so the equality
    assertion below has a reference value that was not produced by
    `render.py`. It names exactly the three fields SKILL.md documents as
    model-facing (`persona_text`, `task_text`, `report_back_questions`) and
    nothing else on `scenario`, so any field `render_paste_block` reads
    beyond those three (an `operator_notes` leak, or a leak through some
    other field entirely) changes the render without changing this
    reference, and the equality assertion catches the divergence.
    """
    persona_text = scenario["persona_text"].replace("<URL>", url)
    task_text = scenario["task_text"].replace("<URL>", url)
    questions = "\n".join(
        f"{i}. {q}" for i, q in enumerate(scenario["report_back_questions"], start=1)
    )
    return (
        f"Persona: {persona_text}\n\nTask: {task_text}\n\nReport back:\n\n{questions}"
    )


def _iter_operator_strings(node: Any):
    """Yield every non-blank string leaf found anywhere under `node`.

    Deliberately generic over shape: walks dicts and lists recursively
    instead of hardcoding today's `operator_notes` sub-keys
    (`operator_setup`, `operator_note`, `persona_context`,
    `expected_observations`). A future field added anywhere under
    `operator_notes` is covered automatically, without editing this test.
    Used only by `test_leaky_render_is_caught_by_the_equality_check` below,
    to prove the fixture scenario it mutates actually carries operator text.
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


def test_a1_persona_context_gives_the_dropped_admin_premise_a_home():
    """Minor 5: admin.md's premise paragraph must live somewhere, not nowhere.

    D2a's migration dropped admin.md's substantive preamble (admins reuse
    every /guardian/* route; the distinguishing signals are the muted
    "Admin" hint, the absent "Books" link, the cross-family picker, and the
    moderation nav) with no replacement home. It is the stated premise of
    A1 ("indistinguishable surface"), so it now lives in
    `A1.operator_notes.persona_context`, an operator-only field alongside
    `operator_setup`/`operator_note`/`expected_observations`. This pins
    that it stays populated, not merely present.
    """
    scenarios = {s["id"]: s for s in _load_scenarios()}
    persona_context = scenarios["A1"]["operator_notes"]["persona_context"]
    assert isinstance(persona_context, list)
    assert persona_context, "A1 persona_context must not be empty"
    assert all(isinstance(text, str) and text.strip() for text in persona_context)


# ---------------------------------------------------------------------------
# The leak test: operator-only content must never reach the paste block.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", _load_scenarios(), ids=lambda s: s["id"])
def test_render_paste_block_matches_the_exact_allowlist_render(
    scenario: dict[str, Any],
):
    """The real renderer's output must equal the independent reference, exactly.

    Exact equality, not substring absence: this fails on ANY divergence
    from the three-field reference, whether that is an operator-notes leak
    (any sub-key, including one added after this test was written), a leak
    through a field outside `operator_notes` entirely, or an unrelated
    change to the three allowed fields. It runs unconditionally on all 17
    scenarios, including the nine whose `operator_notes` are entirely
    empty (G2-G7, A1-A3), where a "forbidden substring is absent" check
    would have passed vacuously.
    """
    rendered = render_module.render_paste_block(scenario["id"], _TEST_URL)
    expected = _expected_paste_block(scenario, _TEST_URL)
    assert rendered == expected


def test_leaky_render_is_caught_by_the_equality_check():
    """Proves the equality check above is not vacuous.

    Picks a scenario with non-empty `operator_notes`, builds a
    deliberately-leaky block by appending its operator content to the real
    renderer's output, and confirms that leaky block no longer equals the
    reference `_expected_paste_block` produces. This is the permanent
    record that the equality check fires on a leak; the D2a report records
    the additional live confirmation that mutating `render.py` itself
    (rather than simulating the leak here) makes
    `test_render_paste_block_matches_the_exact_allowlist_render` fail, and
    that editing SKILL.md's prose alone (with `render.py` unchanged) does
    not resurrect the leak, since SKILL.md's prose is never executed by
    this test or by the renderer.
    """
    scenarios = _load_scenarios()
    leaky_scenario = next(
        s for s in scenarios if any(_iter_operator_strings(s.get("operator_notes", {})))
    )
    operator_strings = list(
        _iter_operator_strings(leaky_scenario.get("operator_notes", {}))
    )
    assert operator_strings, "fixture scenario unexpectedly has no operator_notes text"

    real_block = render_module.render_paste_block(leaky_scenario["id"], _TEST_URL)
    leaky_block = real_block + "\n\n" + json.dumps(leaky_scenario["operator_notes"])
    reference = _expected_paste_block(leaky_scenario, _TEST_URL)

    assert leaky_block != reference, (
        "the leaky block should diverge from the reference; if this fails, "
        "the equality check above would not have caught it either"
    )
