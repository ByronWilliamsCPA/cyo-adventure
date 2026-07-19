"""Tests for the staged generation orchestrator (WP8).

All tests run against the deterministic MockProvider -- no real network or LLM
calls are made. Async tests use @pytest.mark.asyncio.

Test inventory:
    1. Happy path: Stage A + B both pass -> status="passed", attempts==0
    2. Repair success: Stage B blocked once, repair fixes it -> status="passed",
       attempts==1, repair prompt contained failing node id
    3. Repair exhaustion: provider always returns blocked story ->
       status="needs_review", attempts==max_repairs
    4. No-progress abort: same blocked story repeated -> abort before max_repairs
    5. Malformed output: Stage B returns invalid JSON -> no exception escapes,
       routed to repair; if repairs also malformed -> needs_review
    6. PII abort: brief with seeded real-child name -> ValidationError raised,
       provider.calls == [] (provider never called)
    7. Stage A blocked, skip Stage B: repair loop runs on Stage A document
    8. Safety flagged: gate clean but safety_flagged -> needs_review
    9. Parse error produces failed status when all stages malform
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.concept import ConceptBrief, StructurePattern
from cyo_adventure.generation.orchestrator import (
    GenerationOutcome,
    fill_skeleton,
    generate_story,
)
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.storybook.models import AgeBand

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "storybook"


def _load_fixture(name: str) -> dict[str, object]:
    """Load a fixture JSON file as a dict."""
    with (FIXTURE_DIR / name).open(encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


# A minimal valid Storybook dict (Tier-1, single ending).
VALID_STORY: dict[str, object] = _load_fixture("valid/01_hello_world.json")

# A second valid story for stage B (so A and B can return different docs).
VALID_STORY_2: dict[str, object] = _load_fixture("valid/02_tier1_three_endings.json")

# An invalid story with a dangling choice target -- triggers L1 errors.
BLOCKED_STORY: dict[str, object] = _load_fixture("invalid/graph/dangling_target.json")


def _valid_json() -> str:
    """Return JSON string of the valid hello_world story."""
    return json.dumps(VALID_STORY)


def _valid_json_2() -> str:
    """Return JSON string of the second valid story."""
    return json.dumps(VALID_STORY_2)


def _blocked_json() -> str:
    """Return JSON string of a story that fails the gate (dangling target)."""
    return json.dumps(BLOCKED_STORY)


def _make_brief(
    *, premise: str = "A young sailor discovers a mysterious island."
) -> ConceptBrief:
    """Build a valid ConceptBrief with the given premise."""
    return ConceptBrief(
        title="Test Adventure",
        premise=premise,
        protagonist={"name": "Captain Rosa", "age": 10, "role": "explorer"},  # type: ignore[arg-type]
        point_of_view="second",
        age_band=AgeBand.BAND_8_11,
        reading_level_target=4.5,
        tier=1,
        tone="adventurous",
        themes_allowed=["friendship"],
        content_nogo=[],
        target_node_count=5,
        ending_count=1,
        structure_pattern=StructurePattern.QUEST,
        desired_variables=[],
        special_constraints=[],
    )


def _empty_pii() -> PiiContext:
    """Return a PiiContext with no forbidden tokens."""
    return PiiContext(child_names=frozenset())


# ---------------------------------------------------------------------------
# Test 1: Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_passed_status() -> None:
    """Stage A and Stage B both produce valid stories -> status='passed', attempts==0.

    Both stages return a valid Storybook JSON. The gate clears after Stage B;
    no repairs are needed.
    """
    provider = MockProvider(responses=[_valid_json(), _valid_json_2()])
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii)

    assert outcome.status == "passed"
    assert outcome.attempts == 0
    assert outcome.storybook is not None
    assert isinstance(outcome.storybook, dict)
    assert outcome.report["ok"] is True
    # Two calls: one for stage A, one for stage B
    assert len(provider.calls) == 2
    # Stage log should record gate_ok for both stages
    assert "stage_a:gate_ok" in outcome.stage_log
    assert "stage_b:gate_ok" in outcome.stage_log


# ---------------------------------------------------------------------------
# Test 2: Repair success (one repair fixes Stage B blocked story)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_success_one_attempt() -> None:
    """Stage A valid; Stage B returns blocked story; repair 1 returns valid story.

    Expected: status='passed', attempts==1. The repair prompt must contain the
    failing node id from the blocked story's findings.
    """
    provider = MockProvider(
        responses=[
            _valid_json(),  # Stage A: valid skeleton
            _blocked_json(),  # Stage B: blocked (dangling target)
            _valid_json_2(),  # Repair 1: fixed valid story
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii)

    assert outcome.status == "passed"
    assert outcome.attempts == 1
    assert outcome.storybook is not None
    assert outcome.report["ok"] is True
    # The third provider call was the repair prompt; it must contain the failing
    # node id from the blocked story's findings. dangling_target.json has node
    # 'n_start' with a dangling choice target; the gate emits findings with
    # node_id='n_start' (L1-2 and L1-4). The repair prompt must name this node.
    repair_prompt = provider.calls[2]
    assert "n_start" in repair_prompt, (
        f"Repair prompt must reference the failing node 'n_start', got:\n{repair_prompt[:300]}"
    )
    assert "repair:1" in outcome.stage_log


# ---------------------------------------------------------------------------
# Test 3: Repair exhaustion (max_repairs attempts, still blocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_exhaustion_needs_review() -> None:
    """Provider keeps returning a blocked story (different each attempt).

    The story is mutated slightly at each repair to prevent no-progress abort.
    Expected: status='needs_review', attempts==max_repairs (3).
    """

    # Produce 5 distinct blocked stories (A + B + 3 repairs).
    # Each has a slightly different title so the hash differs.
    def _make_distinct_blocked(idx: int) -> str:
        story = copy.deepcopy(BLOCKED_STORY)
        story["title"] = f"Blocked Story Variant {idx}"  # type: ignore[index]
        return json.dumps(story)

    provider = MockProvider(
        responses=[
            _valid_json(),  # Stage A: valid
            _make_distinct_blocked(1),  # Stage B: blocked
            _make_distinct_blocked(2),  # Repair 1: still blocked
            _make_distinct_blocked(3),  # Repair 2: still blocked
            _make_distinct_blocked(4),  # Repair 3: still blocked
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii, max_repairs=3)

    assert outcome.status == "needs_review"
    assert outcome.attempts == 3
    # Provider must have been called exactly 5 times (A + B + 3 repairs)
    assert len(provider.calls) == 5
    assert outcome.storybook is not None


# ---------------------------------------------------------------------------
# Test 4: No-progress abort (same blocked story repeated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_progress_abort_stops_early() -> None:
    """Provider returns the SAME blocked story on Stage B and first repair.

    The no-progress check (same findings AND same doc hash) should stop the
    loop before exhausting all max_repairs attempts.
    """
    provider = MockProvider(
        responses=[
            _valid_json(),  # Stage A: valid
            _blocked_json(),  # Stage B: blocked
            _blocked_json(),  # Repair 1: identical blocked story (no progress)
            _valid_json_2(),  # Repair 2: would be reached if no-progress check fails
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii, max_repairs=3)

    # Must have stopped before exhausting all 3 repairs
    assert outcome.attempts < 3, (
        f"Expected early abort but attempts == {outcome.attempts}"
    )
    # Exactly 1 repair attempt (Stage B + 1 repair = 3 provider calls total)
    assert outcome.attempts == 1
    # Status is needs_review (blocked, but a document was produced)
    assert outcome.status == "needs_review"
    # Stage log records the no-progress abort
    assert "repair:no_progress_abort" in outcome.stage_log
    # The 4th response must NOT have been consumed
    assert len(provider.calls) == 3  # A + B + repair_1


# ---------------------------------------------------------------------------
# Test 5: Malformed output (Stage B returns invalid JSON)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_stage_b_no_exception_escapes() -> None:
    """Stage B returns invalid JSON -> handled as blocked, repair attempted.

    The orchestrator must never raise a JSONDecodeError; it should route to
    the repair loop. If all repairs also malform -> needs_review.
    """
    provider = MockProvider(
        responses=[
            _valid_json(),  # Stage A: valid
            "not json {{{",  # Stage B: malformed
            "also not json <<<",  # Repair 1: still malformed
            "still broken !!!",  # Repair 2: still malformed
            "broken ~~~",  # Repair 3: still malformed
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    # Must not raise
    outcome = await generate_story(brief, provider, pii, max_repairs=3)

    assert outcome.status in ("needs_review", "failed")
    # No exception escaping is the key assertion -- if we're here, it worked.


@pytest.mark.asyncio
async def test_malformed_stage_b_stage_log_records_parse_error() -> None:
    """Stage B parse error appears as 'stage_b:parse_error' in the stage log."""
    provider = MockProvider(
        responses=[
            _valid_json(),  # Stage A: valid
            "not json {{{",  # Stage B: malformed
            _valid_json_2(),  # Repair 1: valid -> passes
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii, max_repairs=3)

    assert "stage_b:parse_error" in outcome.stage_log
    # Repair 1 returned a valid story -> should be passed
    assert outcome.status == "passed"
    assert outcome.attempts == 1


# ---------------------------------------------------------------------------
# Test 6: PII abort -- provider never called when prompt contains real name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pii_abort_raises_and_provider_not_called() -> None:
    """A brief whose premise contains a seeded real-child name raises ValidationError.

    The PII guard fires on the Stage A prompt before any provider call.
    provider.calls must be empty.
    """
    # #CRITICAL: security: assert_prompt_pii_safe runs before every
    # provider.complete call; a PII violation aborts generation before
    # any external egress.
    # #VERIFY: this test asserts provider.calls is empty when a brief would
    # leak a seeded real-child name.
    real_child_name = "SecretChildActualName"
    # The real child's name is in the brief premise -- it flows into the
    # Stage A prompt via build_structure_prompt(brief).
    brief = _make_brief(premise=f"A story created for {real_child_name} the brave.")
    pii = PiiContext(child_names=frozenset({real_child_name}))
    provider = MockProvider(responses=[_valid_json(), _valid_json_2()])

    with pytest.raises(ValidationError):
        await generate_story(brief, provider, pii)

    # Provider must have received zero calls.
    assert provider.calls == [], (
        f"Expected 0 provider calls but got: {provider.calls!r}"
    )


# ---------------------------------------------------------------------------
# Test 7: Stage A blocked -- Stage B skipped, repair runs on Stage A doc
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_a_blocked_skips_stage_b() -> None:
    """Stage A returns a blocked story -> Stage B is skipped, repair loop runs.

    If the repair succeeds, status is 'passed' and total calls = 1 (A) + 1 (repair).
    There must be NO Stage B call.
    """
    provider = MockProvider(
        responses=[
            _blocked_json(),  # Stage A: blocked
            _valid_json(),  # Repair 1: valid
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii, max_repairs=3)

    # Stage A was blocked, so Stage B was skipped.
    assert "stage_b:gate_ok" not in outcome.stage_log
    assert "stage_b:blocked" not in outcome.stage_log
    assert "stage_b:parse_error" not in outcome.stage_log
    # Repair 1 returned valid -> passed
    assert outcome.status == "passed"
    assert outcome.attempts == 1
    # Only 2 provider calls: A + repair_1 (no Stage B)
    assert len(provider.calls) == 2


# ---------------------------------------------------------------------------
# Test 8: Safety flagged -> needs_review even when gate is clean
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safety_flagged_gives_needs_review() -> None:
    """When gate_result.safety_flagged is True (but not blocked), status is needs_review.

    In Phase 2, SAFE-14 is a stub so this is encoded defensively. We test the
    outcome mapping logic directly here by patching run_gate to return a
    safety-flagged result.
    """
    from unittest.mock import patch

    from cyo_adventure.validator.gate import GateResult
    from cyo_adventure.validator.report import ValidationReport

    # Produce a gate result that is clean (not blocked) but safety_flagged.
    safe_flagged_result = GateResult(
        report=ValidationReport(),
        blocked=False,
        safety_flagged=True,
    )

    provider = MockProvider(responses=[_valid_json(), _valid_json_2()])
    brief = _make_brief()
    pii = _empty_pii()

    # Patch run_gate so it always returns the safety-flagged result.
    with patch(
        "cyo_adventure.generation.orchestrator.run_gate",
        return_value=safe_flagged_result,
    ):
        outcome = await generate_story(brief, provider, pii)

    assert outcome.status == "needs_review"
    assert outcome.storybook is not None
    assert outcome.attempts == 0


# ---------------------------------------------------------------------------
# Test 9: All stages produce malformed output -> status="failed" (no doc)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_malformed_produces_failed_when_no_doc() -> None:
    """All stage outputs are malformed JSON -> status='failed' (no doc produced).

    Stage A is malformed (no doc at all from the start). If all repairs
    are also malformed and there is never a parseable dict, we expect
    status='failed'.
    """
    provider = MockProvider(
        responses=[
            "not json at all",  # Stage A: malformed
            "also not json",  # Repair 1: malformed
            "still broken",  # Repair 2: malformed
            "broken again",  # Repair 3: malformed
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii, max_repairs=3)

    # All outputs were malformed: no doc was ever produced. The no-progress
    # check fires after Repair 1 (same hash "{}" for every malformed output),
    # so the loop stops after exactly 1 repair attempt.
    # Deterministic outcome: status='failed', storybook is None.
    assert outcome.status == "failed"
    assert outcome.storybook is None


# ---------------------------------------------------------------------------
# Test 10: GenerationOutcome is a frozen dataclass with correct fields
# ---------------------------------------------------------------------------


def test_generation_outcome_fields() -> None:
    """GenerationOutcome has all required fields and is immutable."""
    outcome = GenerationOutcome(
        status="passed",
        storybook={"id": "test"},
        report={"ok": True, "findings": []},
        attempts=0,
        stage_log=["stage_a:gate_ok"],
    )
    assert outcome.status == "passed"
    assert outcome.storybook == {"id": "test"}
    assert outcome.report == {"ok": True, "findings": []}
    assert outcome.attempts == 0
    assert outcome.stage_log == ["stage_a:gate_ok"]

    # Frozen: must not be mutable
    with pytest.raises((AttributeError, TypeError)):
        outcome.status = "failed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test 11: max_repairs=0 skips repair loop entirely
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_repairs_zero_no_repair_attempts() -> None:
    """With max_repairs=0, a blocked Stage B immediately returns needs_review."""
    provider = MockProvider(
        responses=[
            _valid_json(),  # Stage A: valid
            _blocked_json(),  # Stage B: blocked
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii, max_repairs=0)

    assert outcome.attempts == 0
    assert outcome.status == "needs_review"
    assert len(provider.calls) == 2


# ---------------------------------------------------------------------------
# Test 12: Outcome never "passed" when gate is blocked
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Test 13: Non-dict JSON (e.g. a JSON array) is treated as blocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_dict_json_treated_as_blocked() -> None:
    """A provider that returns valid JSON but not a dict (e.g. an array) is treated
    as a blocked parse error, not a crash.

    Covers the ``not isinstance(parsed, dict)`` branch in ``_run_one_stage``.
    """
    provider = MockProvider(
        responses=[
            '["not", "a", "dict"]',  # Stage A: valid JSON, but a list
            _valid_json(),  # Repair 1: fixed
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii, max_repairs=3)

    # Must not raise; Stage A produced a non-dict so it routes to repair.
    # Stage A: parse_error -> repair loop runs; Repair 1 returns valid story.
    # Deterministic outcome: status='passed', attempts==1.
    assert outcome.status == "passed"
    assert outcome.attempts == 1
    assert "stage_a:parse_error" in outcome.stage_log


@pytest.mark.asyncio
async def test_status_never_passed_when_gate_blocked() -> None:
    """Under no circumstances does a blocked gate result in status='passed'."""
    # Use max_repairs=1 and only provide 3 responses to guarantee we don't
    # over-call the provider.
    provider = MockProvider(
        responses=[
            _valid_json(),  # Stage A: valid
            _blocked_json(),  # Stage B: blocked
            _blocked_json(),  # Repair 1: still blocked
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii, max_repairs=1)

    assert outcome.status != "passed", (
        "status must never be 'passed' when the final gate is blocked"
    )
    assert outcome.status in ("needs_review", "failed")


def test_gate_signature_handles_mixed_nullability_findings() -> None:
    """_gate_signature must not raise when findings share a rule_id but differ
    in node_id nullability.

    Regression test: two L1-2 findings (a start-node finding with node_id=None
    and a dangling-choice finding with a concrete node_id) made the previous
    ``sorted`` call compare ``None`` against ``str`` and raise TypeError,
    crashing the repair loop instead of routing the malformed output to repair.
    """
    from cyo_adventure.generation.orchestrator import _gate_signature
    from cyo_adventure.validator.gate import GateResult
    from cyo_adventure.validator.report import (
        Severity,
        ValidationFinding,
        ValidationReport,
    )

    report = ValidationReport()
    report.add(
        ValidationFinding(
            rule_id="L1-2",
            severity=Severity.ERROR,
            story_id="s",
            node_id=None,
            message="L1-2 ref: start_node not found",
        )
    )
    report.add(
        ValidationFinding(
            rule_id="L1-2",
            severity=Severity.ERROR,
            story_id="s",
            node_id="n_start",
            choice_id="c1",
            message="L1-2 ref: dangling choice target",
        )
    )
    gate = GateResult(report=report, blocked=True, safety_flagged=False)

    findings_tuple, doc_hash = _gate_signature(gate, None)

    assert len(findings_tuple) == 2
    assert len(doc_hash) == 64
    # Signature must be deterministic and order-independent of insertion.
    assert _gate_signature(gate, None) == (findings_tuple, doc_hash)


@pytest.mark.asyncio
async def test_stage_b_parse_failure_preserves_stage_a_skeleton() -> None:
    """A Stage B parse failure must not discard Stage A's validated skeleton.

    Regression: Stage A produces a valid (passing) skeleton, then Stage B and
    every repair return malformed JSON. The outcome must surface the Stage A
    skeleton as needs_review rather than collapsing to failed/storybook=None.
    """
    provider = MockProvider(
        responses=[
            _valid_json(),  # Stage A: valid skeleton, passes the gate
            "not valid json",  # Stage B: parse error
            "still not json",  # Repair 1: parse error
        ]
    )
    brief = _make_brief()
    pii = _empty_pii()

    outcome = await generate_story(brief, provider, pii, max_repairs=1)

    assert outcome.status == "needs_review", (
        "Stage A skeleton should be surfaced as needs_review, not failed"
    )
    assert outcome.storybook is not None, "Stage A skeleton must be preserved"


# ---------------------------------------------------------------------------
# Test: fill_skeleton (Stage B' -- reuses the same repair-loop machinery)
# ---------------------------------------------------------------------------
#
# #ASSUME: data-integrity: unlike generate_story's Stage A, fill_skeleton is
# always handed a schema-shaped skeleton by its caller (never None), so its
# "last known good" fallback (`skeleton`) is never absent. That means a
# fill_skeleton run can never terminate with status="failed": even if the
# fill call and every repair attempt return unparseable output, the raw
# skeleton (FILL directives still in place) is surfaced as needs_review
# rather than being discarded. This differs from the brief's illustrative
# expectation (status="failed"); verified directly against the implementation
# below (test_fill_skeleton_repair_exhaustion_is_needs_review_not_failed).
# #VERIFY: covered by both tests in this section.


def _skeleton_with_fill_placeholder() -> dict[str, object]:
    """A schema-valid skeleton (hello_world fixture) with one FILL placeholder.

    Mirrors what a matched skeleton library file looks like before Stage B'
    fills it in: structurally valid and gate-clean except for the one node
    body still carrying an unfilled ``<<FILL ...>>`` directive.
    """
    skeleton = copy.deepcopy(VALID_STORY)
    nodes = cast("list[dict[str, object]]", skeleton["nodes"])
    nodes[0]["body"] = "<<FILL role=setup words=10 beats='greet the fox'>>"
    return skeleton


@pytest.mark.asyncio
async def test_fill_skeleton_returns_passed_on_clean_fill() -> None:
    """A clean first-attempt fill (gate passes) returns status='passed', attempts==0."""
    skeleton = _skeleton_with_fill_placeholder()
    filled = copy.deepcopy(VALID_STORY)  # provider "fills" the placeholder cleanly
    provider = MockProvider(responses=[json.dumps(filled)])
    pii = PiiContext(child_names=frozenset())

    outcome = await fill_skeleton(skeleton, {"premise": "a fox"}, provider, pii)

    assert outcome.status == "passed"
    assert outcome.storybook is not None
    assert outcome.attempts == 0
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_fill_skeleton_repair_exhaustion_is_needs_review_not_failed() -> None:
    """A malformed first response routes into the same repair loop as generate_story.

    Every provider response is malformed (fill call + max_repairs repairs), so
    the repair loop runs to exhaustion. Because fill_skeleton always has the
    caller-supplied skeleton as a non-None fallback document (unlike
    generate_story's Stage A, which can genuinely produce no document), the
    outcome is "needs_review" with the original skeleton surfaced, not
    "failed". attempts==max_repairs since no-progress detection does not
    short-circuit before the cap here (each repair sees the same skeleton
    payload as the previous one, but this is the first differing signature
    from the seed, so no early abort occurs before the cap is hit).
    """
    skeleton = _skeleton_with_fill_placeholder()
    provider = MockProvider(responses=["not json", "still not json", "nope"])
    pii = PiiContext(child_names=frozenset())

    outcome = await fill_skeleton(
        skeleton, {"premise": "a fox"}, provider, pii, max_repairs=2
    )

    assert outcome.status == "needs_review"
    assert outcome.storybook is not None
    assert outcome.attempts == 2
    assert len(provider.calls) == 3
    assert outcome.storybook["id"] == VALID_STORY["id"]


# ---------------------------------------------------------------------------
# Test: fill_skeleton Stage 1 fidelity fold (#133)
# ---------------------------------------------------------------------------
#
# These tests exercise the folded design: when fill_skeleton is given the
# Stage 1 parameters (settings not None), a structurally-clean-but-Stage-1-
# failing fill re-enters the SAME bounded max_repairs repair loop that
# structural blocks use, with a fidelity-aware repair prompt, sharing one
# budget. run_stage1_gate is monkeypatched at the orchestrator seam so the
# gate outcome is deterministic without a real review backend.


def _valid_variant(index: int) -> str:
    """A gate-clean VALID_STORY variant with a distinct start-node body.

    Distinct bodies give each repair a distinct no-progress signature so the
    bounded loop runs to its budget instead of aborting on an identical redo.
    """
    doc = copy.deepcopy(VALID_STORY)
    nodes = cast("list[dict[str, object]]", doc["nodes"])
    nodes[0]["body"] = f"A gate-clean variant number {index} of the same story."
    return json.dumps(doc)


@pytest.mark.asyncio
async def test_fill_skeleton_stage1_fail_once_then_pass_returns_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Stage 1 miss then a clean recheck yields passed within the shared budget.

    The fill is structurally clean; Stage 1 fails on attempt 1 and passes on
    attempt 2, so exactly one fidelity-aware repair runs (attempts == 1) and no
    downgrade key is added.
    """
    import cyo_adventure.generation.orchestrator as orch

    skeleton = _skeleton_with_fill_placeholder()
    provider = MockProvider(responses=[_valid_variant(0), _valid_variant(1)])
    pii = PiiContext(child_names=frozenset())

    stage1_calls = 0

    async def _fake_gate(*_args: object, **_kwargs: object) -> list[str]:
        nonlocal stage1_calls
        stage1_calls += 1
        return ["node 'n1' word count mismatch"] if stage1_calls == 1 else []

    monkeypatch.setattr(orch, "run_stage1_gate", _fake_gate)

    outcome = await fill_skeleton(
        skeleton,
        {"premise": "a fox"},
        provider,
        pii,
        settings=Settings(generation_provider="mock"),  # type: ignore[call-arg]
    )

    assert outcome.status == "passed"
    assert "stage1_fidelity_violations" not in outcome.report
    assert outcome.attempts == 1
    assert stage1_calls == 2
    assert len(provider.calls) == 2  # fill + one fidelity repair


@pytest.mark.asyncio
async def test_fill_skeleton_stage1_exhaustion_downgrades_with_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persistent Stage 1 miss downgrades to needs_review with the violations key.

    The retries share the SAME max_repairs budget as structural repairs: with
    max_repairs=2 the fill makes exactly 1 fill + 2 repair provider calls (3
    total), NOT a separate 3x3 budget, before downgrading.
    """
    import cyo_adventure.generation.orchestrator as orch

    skeleton = _skeleton_with_fill_placeholder()
    provider = MockProvider(
        responses=[_valid_variant(0), _valid_variant(1), _valid_variant(2)]
    )
    pii = PiiContext(child_names=frozenset())

    stage1_calls = 0

    async def _fake_gate(*_args: object, **_kwargs: object) -> list[str]:
        nonlocal stage1_calls
        stage1_calls += 1
        return ["node 'n1' still short"]

    monkeypatch.setattr(orch, "run_stage1_gate", _fake_gate)

    outcome = await fill_skeleton(
        skeleton,
        {"premise": "a fox"},
        provider,
        pii,
        max_repairs=2,
        settings=Settings(generation_provider="mock"),  # type: ignore[call-arg]
    )

    assert outcome.status == "needs_review"
    assert outcome.report.get("stage1_fidelity_violations") == ["node 'n1' still short"]
    assert outcome.attempts == 2
    assert len(provider.calls) == 3  # fill + max_repairs repairs, one shared budget
    assert stage1_calls == 3


@pytest.mark.asyncio
async def test_fill_skeleton_stage1_repair_is_fidelity_aware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry prompt carries the violation text, proving it is not a blind redo."""
    import cyo_adventure.generation.orchestrator as orch

    skeleton = _skeleton_with_fill_placeholder()
    provider = MockProvider(responses=[_valid_variant(0), _valid_variant(1)])
    pii = PiiContext(child_names=frozenset())
    violation = "node 'greeting' word count 3 outside [6, 14] for target 10"

    calls = 0

    async def _fake_gate(*_args: object, **_kwargs: object) -> list[str]:
        nonlocal calls
        calls += 1
        return [violation] if calls == 1 else []

    monkeypatch.setattr(orch, "run_stage1_gate", _fake_gate)

    await fill_skeleton(
        skeleton,
        {"premise": "a fox"},
        provider,
        pii,
        settings=Settings(generation_provider="mock"),  # type: ignore[call-arg]
    )

    # provider.calls[0] is the fill; provider.calls[1] is the fidelity repair.
    assert len(provider.calls) == 2
    assert violation in provider.calls[1]


@pytest.mark.asyncio
async def test_fill_skeleton_without_settings_never_runs_stage1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Stage 1 params means the gate is never called and behavior is unchanged.

    This is the guard that keeps generate_story and every non-authoring caller
    of the shared repair machinery byte-identical: Stage 1 is opt-in via the
    settings parameter.
    """
    import cyo_adventure.generation.orchestrator as orch

    skeleton = _skeleton_with_fill_placeholder()
    filled = copy.deepcopy(VALID_STORY)
    provider = MockProvider(responses=[json.dumps(filled)])
    pii = PiiContext(child_names=frozenset())

    async def _boom(*_args: object, **_kwargs: object) -> list[str]:
        msg = "run_stage1_gate must not be called when settings is None"
        raise AssertionError(msg)

    monkeypatch.setattr(orch, "run_stage1_gate", _boom)

    outcome = await fill_skeleton(skeleton, {"premise": "a fox"}, provider, pii)

    assert outcome.status == "passed"
    assert outcome.attempts == 0
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# Test: fill_skeleton WS-2 bound-fill prompt selection (slot_bindings)
# ---------------------------------------------------------------------------
#
# `slot_bindings` selects the initial-fill prompt variant only; every other
# fill_skeleton behavior (repair loop, Stage 1 fold) is untouched by this
# parameter, so these tests only assert on the prompt the mock provider
# actually received.


@pytest.mark.asyncio
async def test_fill_skeleton_with_slot_bindings_builds_bound_fill_prompt() -> None:
    """slot_bindings supplied -> the initial fill prompt is the bound-fill variant.

    build_bound_fill_prompt's user block carries a labeled
    '## Bound Theme Values' data section (fill_bound.md) that the plain
    build_fill_prompt variant never contains; its presence in the actual
    prompt the mock provider received is the signal this test pins.
    """
    skeleton = _skeleton_with_fill_placeholder()
    filled = copy.deepcopy(VALID_STORY)
    provider = MockProvider(responses=[json.dumps(filled)])
    pii = PiiContext(child_names=frozenset())
    slot_bindings = {"HERO": "Priya", "A1_GATE": "the jammed hatch"}

    outcome = await fill_skeleton(
        skeleton, {"premise": "a fox"}, provider, pii, slot_bindings=slot_bindings
    )

    assert outcome.status == "passed"
    assert len(provider.calls) == 1
    prompt = provider.calls[0]
    assert "Bound Theme Values" in prompt
    assert "Priya" in prompt
    assert "the jammed hatch" in prompt


@pytest.mark.asyncio
async def test_fill_skeleton_without_slot_bindings_builds_plain_fill_prompt() -> None:
    """slot_bindings=None (the default) builds the ordinary build_fill_prompt
    variant, with no bound-theme-values data block -- the regression pin every
    existing (WS-1) caller of fill_skeleton relies on.
    """
    skeleton = _skeleton_with_fill_placeholder()
    filled = copy.deepcopy(VALID_STORY)
    provider = MockProvider(responses=[json.dumps(filled)])
    pii = PiiContext(child_names=frozenset())

    outcome = await fill_skeleton(skeleton, {"premise": "a fox"}, provider, pii)

    assert outcome.status == "passed"
    assert len(provider.calls) == 1
    assert "Bound Theme Values" not in provider.calls[0]


@pytest.mark.asyncio
async def test_fill_skeleton_slot_bindings_default_is_byte_identical_prompt() -> None:
    """The default (no slot_bindings) call produces the EXACT same prompt as
    an explicit slot_bindings=None call, and matches build_fill_prompt
    directly -- pinning that adding the parameter changed nothing for callers
    that do not pass it.
    """
    from cyo_adventure.generation.prompts import build_fill_prompt

    skeleton = _skeleton_with_fill_placeholder()
    theme_brief: dict[str, object] = {"premise": "a fox"}
    expected = build_fill_prompt(json.dumps(skeleton), json.dumps(theme_brief))

    filled = copy.deepcopy(VALID_STORY)
    provider = MockProvider(responses=[json.dumps(filled)])
    pii = PiiContext(child_names=frozenset())

    await fill_skeleton(skeleton, theme_brief, provider, pii)

    assert provider.calls[0] == expected.user
