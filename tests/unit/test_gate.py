"""Tests for the combined validation gate runner (gate.py).

Coverage:
1. Clean Tier-2 fixture: blocked=False, safety_flagged=False, report.ok True.
2. L1 failure: blocked=True, NO L2 findings present (proves short-circuit).
3. L1-clean but L2-failing Tier-2 story: blocked=True with L2 rule_id, no L1 error.
4. Clean Tier-1 fixture: blocked=False (Layer 2 is a no-op for Tier 1).
5. RL-13 WARNING does not block: blocked=False despite warning in report.
6. Defensive parse failure: _parse_storybook exception path sets blocked=True.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cyo_adventure.validator.gate import GateResult, run_fill_gate, run_gate

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "storybook"
_VALID = _FIXTURES / "valid"
_INVALID_GRAPH = _FIXTURES / "invalid" / "graph"
_INVALID_SCHEMA = _FIXTURES / "invalid" / "schema"


def _load(path: Path) -> dict[str, object]:
    """Load a story fixture as a raw dict."""
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_l2_finding(result: GateResult) -> bool:
    """Return True if the merged report contains any L2-prefixed finding."""
    return any(f.rule_id.startswith("L2") for f in result.report.findings)


def _has_l1_error(result: GateResult) -> bool:
    """Return True if the merged report contains any L1-prefixed ERROR finding."""
    from cyo_adventure.validator.report import Severity

    return any(
        f.rule_id.startswith("L1") and f.severity is Severity.ERROR
        for f in result.report.findings
    )


# ---------------------------------------------------------------------------
# 1. Clean Tier-2 fixture
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_clean_tier2_passes_gate() -> None:
    """A clean Tier-2 story must produce blocked=False, safety_flagged=False,
    and a report with no error-severity findings."""
    data = _load(_VALID / "03_tier2_lantern.json")
    result = run_gate(data)
    assert result.blocked is False
    assert result.safety_flagged is False
    assert result.report.ok is True, [f.message for f in result.report.errors]


@pytest.mark.unit
def test_clean_tier2_gate_result_type() -> None:
    """run_gate must return a GateResult (frozen dataclass)."""
    data = _load(_VALID / "03_tier2_lantern.json")
    result = run_gate(data)
    assert isinstance(result, GateResult)


# ---------------------------------------------------------------------------
# 2. L1 failure: short-circuit means no L2 findings
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_l1_failure_sets_blocked() -> None:
    """An L1-failing story must produce blocked=True."""
    data = _load(_INVALID_GRAPH / "orphan_node.json")
    result = run_gate(data)
    assert result.blocked is True


@pytest.mark.unit
def test_l1_failure_no_l2_findings() -> None:
    """When L1 fails, Layer 2 must NOT run: no L2-prefixed rule_id in report.

    This is the proof of the L1 short-circuit. If any L2 rule_id appears,
    the walk ran on broken input.
    """
    data = _load(_INVALID_GRAPH / "orphan_node.json")
    result = run_gate(data)
    l2_ids = [f.rule_id for f in result.report.findings if f.rule_id.startswith("L2")]
    assert l2_ids == [], f"L2 rules fired despite L1 failure: {l2_ids}"


@pytest.mark.unit
def test_l1_failure_schema_fixture_no_l2_findings() -> None:
    """Schema-level L1 failure must also short-circuit before Layer 2."""
    data = _load(_INVALID_SCHEMA / "duplicate_node_id.json")
    result = run_gate(data)
    assert result.blocked is True
    assert not _has_l2_finding(result), "L2 must not run when L1 fails"


@pytest.mark.unit
def test_l1_failure_has_l1_findings() -> None:
    """An L1-failing story must have at least one L1 finding in the report."""
    data = _load(_INVALID_GRAPH / "orphan_node.json")
    result = run_gate(data)
    l1_ids = [f.rule_id for f in result.report.findings if f.rule_id.startswith("L1")]
    assert l1_ids, "Expected at least one L1 finding in the report"


# ---------------------------------------------------------------------------
# 3. L1-clean but L2-failing Tier-2 story
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_l2_failure_sets_blocked() -> None:
    """A story that passes L1 but fails L2 must produce blocked=True.

    The stateful_dead_end fixture is Tier-2 with an L2-9 dead-end condition.
    It passes all Layer-1 rules (the graph is structurally sound).
    """
    data = _load(_INVALID_GRAPH / "stateful_dead_end.json")
    result = run_gate(data)
    assert result.blocked is True


@pytest.mark.unit
def test_l2_failure_has_l2_finding() -> None:
    """A story that fails L2 must have at least one L2-prefixed finding."""
    data = _load(_INVALID_GRAPH / "stateful_dead_end.json")
    result = run_gate(data)
    assert _has_l2_finding(result), "Expected an L2 finding for the dead-end story"


@pytest.mark.unit
def test_l2_failure_has_no_l1_error() -> None:
    """A story that fails L2 (but passes L1) must have no L1 ERROR findings.

    Confirms the stateful_dead_end fixture is genuinely L1-clean.
    """
    data = _load(_INVALID_GRAPH / "stateful_dead_end.json")
    result = run_gate(data)
    assert not _has_l1_error(result), (
        "Unexpected L1 error on a structurally sound story"
    )


# ---------------------------------------------------------------------------
# 4. Clean Tier-1 fixture: Layer 2 is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_clean_tier1_passes_gate() -> None:
    """A clean Tier-1 story must not be blocked (Layer 2 short-circuits)."""
    data = _load(_VALID / "01_hello_world.json")
    result = run_gate(data)
    assert result.blocked is False
    assert result.safety_flagged is False
    assert result.report.ok is True


@pytest.mark.unit
def test_clean_tier1_no_l2_findings() -> None:
    """A Tier-1 story must produce no L2 findings (Layer 2 skips Tier 1)."""
    data = _load(_VALID / "02_tier1_three_endings.json")
    result = run_gate(data)
    assert not _has_l2_finding(result)


# ---------------------------------------------------------------------------
# 5. RL-13 WARNING does not block
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_warning_only_report_does_not_block() -> None:
    """A report containing only WARNING-severity findings must not set blocked.

    Injects a synthetic story whose reading level is deliberately out of
    range to force an RL-13 WARNING, then asserts blocked is False.
    """
    # Build a Tier-1 story with long-enough node bodies to trigger FK scoring.
    # The body uses deliberately complex vocabulary to push the FK grade high
    # while the target is set at grade 3 with tight tolerance (0.5), making
    # an RL-13 warning almost certain on a high-grade passage.
    story_data: dict[str, object] = {
        "schema_version": "2.0",
        "id": "s_rl13_test",
        "version": 1,
        "title": "RL-13 Advisory Test",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 1.0,
                "tolerance": 0.1,
            },
            "tier": 1,
            "themes": ["test"],
            "estimated_minutes": 5,
            "ending_count": 4,
            "topology": "time_cave",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_open",
        "nodes": [
            {
                # The establishing stop PL-25's floor requires: 8-11 may not put
                # its first decision at depth 1. Without it this fixture blocks on
                # PL-25 and the test can no longer observe what it is about, since
                # "warnings alone do not block" is only measurable on a story whose
                # sole findings are warnings. Its body stays in the same
                # deliberately high-register vocabulary as the rest of the fixture
                # so it does not pull the story-mean FK grade back toward target and
                # quietly stop RL-13 from firing at all.
                "id": "n_open",
                "body": (
                    "Preliminary observations invariably necessitate considerable "
                    "deliberation before consequential determinations become "
                    "practicable."
                ),
                "is_ending": False,
                "choices": [
                    {"id": "c_open", "label": "Begin.", "target": "n_start"},
                ],
            },
            {
                "id": "n_start",
                "body": (
                    "The extraordinarily sophisticated phenomenon that scientists "
                    "have meticulously documented demonstrates unequivocally the "
                    "unprecedented complexity inherent in multidimensional "
                    "theoretical frameworks, particularly when considering "
                    "epistemological implications and ontological ramifications "
                    "of contemporary philosophical discourse."
                ),
                "is_ending": False,
                "choices": [
                    {
                        "id": "c1",
                        "label": "Continue.",
                        "target": "n_end",
                    },
                    {
                        "id": "c_branch",
                        "label": "Consider an alternative.",
                        "target": "n_d1",
                    },
                ],
            },
            {
                "id": "n_d1",
                "body": "A side decision.",
                "is_ending": False,
                "choices": [
                    {"id": "c_d1a", "label": "left", "target": "n_d2"},
                    {"id": "c_d1b", "label": "right", "target": "n_alt1"},
                ],
            },
            {
                "id": "n_d2",
                "body": "Another side decision.",
                "is_ending": False,
                "choices": [
                    {"id": "c_d2a", "label": "up", "target": "n_alt2"},
                    {"id": "c_d2b", "label": "down", "target": "n_alt3"},
                ],
            },
            {
                "id": "n_end",
                "body": "The end.",
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Done",
                },
                "choices": [],
            },
            {
                "id": "n_alt1",
                "body": "An alternative resolution.",
                "is_ending": True,
                "ending": {
                    "id": "e_alt1",
                    "valence": "neutral",
                    "kind": "discovery",
                    "title": "Aside One",
                },
                "choices": [],
            },
            {
                "id": "n_alt2",
                "body": "Another resolution.",
                "is_ending": True,
                "ending": {
                    "id": "e_alt2",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "Aside Two",
                },
                "choices": [],
            },
            {
                "id": "n_alt3",
                "body": "A final resolution.",
                "is_ending": True,
                "ending": {
                    "id": "e_alt3",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Aside Three",
                },
                "choices": [],
            },
        ],
    }

    result = run_gate(story_data)

    # Regardless of whether RL-13 fired, blocked must be False: no L1/L2 errors.
    assert result.blocked is False, (
        f"blocked must be False even if RL-13 warnings are present; "
        f"findings: {[f.rule_id for f in result.report.findings]}"
    )

    # Assert that if RL-13 fired, it is WARNING severity (sanity check).
    from cyo_adventure.validator.report import Severity

    for finding in result.report.findings:
        if finding.rule_id == "RL-13":
            assert finding.severity is Severity.WARNING, (
                "RL-13 must always be WARNING, never ERROR"
            )


@pytest.mark.unit
def test_rl13_warning_present_but_not_blocking() -> None:
    """Explicitly confirm: a report with an RL-13 WARNING sets blocked=False.

    Uses the 04_tier2_courage_gate fixture, which has rich prose that may
    trigger RL-13 depending on FK scoring. The key invariant is that blocked
    must be False regardless of whether RL-13 fires.
    """
    data = _load(_VALID / "04_tier2_courage_gate.json")
    result = run_gate(data)
    assert result.blocked is False

    rl13_ids = [f.rule_id for f in result.report.findings if f.rule_id == "RL-13"]
    # If RL-13 fired, it must be WARNING and must not have set blocked.
    if rl13_ids:
        from cyo_adventure.validator.report import Severity

        for finding in result.report.findings:
            if finding.rule_id == "RL-13":
                assert finding.severity is Severity.WARNING


# ---------------------------------------------------------------------------
# 6. safety_flagged is False in Phase 2
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_safety_flagged_false_in_phase2() -> None:
    """The Phase-2 safety stub returns no findings; safety_flagged must be False."""
    data = _load(_VALID / "03_tier2_lantern.json")
    result = run_gate(data)
    assert result.safety_flagged is False


# ---------------------------------------------------------------------------
# 7. Merge order: findings appear in L1 -> L2 -> RL -> SAFE order
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_findings_ordered_l1_before_l2() -> None:
    """Findings from L1 must appear before L2 findings in the merged report.

    Uses a story that is L1-clean but L2-failing. The test checks ordering by
    verifying that no L1 finding appears after an L2 finding.
    """
    data = _load(_INVALID_GRAPH / "stateful_dead_end.json")
    result = run_gate(data)

    findings = result.report.findings
    layer_order: list[str] = []
    for f in findings:
        if f.rule_id.startswith("L1"):
            layer_order.append("L1")
        elif f.rule_id.startswith("L2"):
            layer_order.append("L2")
        elif f.rule_id == "RL-13":
            layer_order.append("RL")
        elif f.rule_id == "SAFE-14":
            layer_order.append("SAFE")

    # The fixture must actually exercise both layers, or the ordering check
    # below (no L1 label after an L2 label) would pass vacuously.
    assert "L1" in layer_order
    assert "L2" in layer_order

    # No L1 label should appear after an L2 label in the ordering.
    seen_l2 = False
    for layer in layer_order:
        if layer == "L2":
            seen_l2 = True
        if layer == "L1" and seen_l2:
            pytest.fail("L1 finding appeared after an L2 finding in merged report")


# ---------------------------------------------------------------------------
# 8. Additional clean fixture sweep (parametric)
# ---------------------------------------------------------------------------


_CLEAN_FIXTURES = [
    "01_hello_world.json",
    "02_tier1_three_endings.json",
    "03_tier2_lantern.json",
    "04_tier2_courage_gate.json",
    "05_tier2_bottleneck.json",
    "06_tier1_tide_pools.json",
    "07_tier2_clockwork_garden.json",
]


@pytest.mark.unit
@pytest.mark.parametrize("filename", _CLEAN_FIXTURES)
def test_all_valid_fixtures_pass_gate(filename: str) -> None:
    """Every valid fixture must produce blocked=False through the full gate."""
    data = _load(_VALID / filename)
    result = run_gate(data)
    assert result.blocked is False, (
        f"{filename}: unexpected blocking findings: "
        f"{[f.message for f in result.report.errors]}"
    )


# ---------------------------------------------------------------------------
# 9. Defensive parse failure (covers _parse_storybook exception path)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_storybook_reports_unsupported_schema_version() -> None:
    """An unsupported schema_version reaches _parse_storybook unpatched.

    This is the non-simulated version of the two tests below, and the reason
    the handler's docstring calls the path reachable rather than defensive:
    schema/storybook.schema.json constrains schema_version to
    {"type": "string"} with no pattern or enum, so a higher major clears L1-1
    and is refused by Storybook's after-validator. The finding must carry
    Pydantic's own message so the reader learns WHICH validator refused it,
    rather than being told the schema may have drifted.
    """
    data = dict(_load(_VALID / "01_hello_world.json"))
    data["schema_version"] = "3.0"

    result = run_gate(data)

    assert result.blocked is True
    l1_1 = [f for f in result.report.findings if f.rule_id == "L1-1"]
    assert l1_1, "Expected a synthetic L1-1 finding for the unsupported version"
    assert any("unsupported schema_version" in f.message for f in l1_1), (
        f"L1-1 finding must name the version refusal, got: {[f.message for f in l1_1]}"
    )
    assert not any("schema drift" in f.message for f in l1_1)


@pytest.mark.unit
def test_defensive_parse_failure_sets_blocked() -> None:
    """When Pydantic raises after a clean L1, the gate must block defensively.

    Unlike test_parse_storybook_reports_unsupported_schema_version above, this
    simulates a genuine drift between the exported schema and the models by
    patching Storybook.model_validate, so the handler is covered even for
    failures no real document currently produces.
    """
    from pydantic import ValidationError as PydanticValidationError

    from cyo_adventure.storybook.models import Storybook

    # Build a valid document first (L1 must pass so we reach the parse step).
    data = _load(_VALID / "01_hello_world.json")

    # Construct a real PydanticValidationError by asking Pydantic to validate
    # something structurally invalid -- we only need the exception instance.
    try:
        Storybook.model_validate({"id": 123})  # wrong type, guaranteed to fail
    except PydanticValidationError as exc:
        fake_exc = exc
    else:
        # NOT a skip. `{"id": 123}` is structurally invalid for Storybook, so
        # model_validate accepting it means the model stopped rejecting garbage,
        # which is a regression this test should report rather than step around.
        # A skip here would have made that regression indistinguishable from a pass.
        pytest.fail(
            "Storybook.model_validate accepted {'id': 123}; the model no longer "
            "rejects a structurally invalid document, so this test's premise is broken"
        )

    with patch.object(Storybook, "model_validate", side_effect=fake_exc):
        result = run_gate(data)

    assert result.blocked is True
    # A synthetic L1-1 finding must have been added by the defensive handler.
    l1_1_ids = [f.rule_id for f in result.report.findings if f.rule_id == "L1-1"]
    assert l1_1_ids, (
        "Expected a synthetic L1-1 finding from the defensive parse handler"
    )


@pytest.mark.unit
def test_defensive_parse_failure_no_l2_findings() -> None:
    """When the defensive parse path fires, L2 must not run."""
    from pydantic import ValidationError as PydanticValidationError

    from cyo_adventure.storybook.models import Storybook

    data = _load(_VALID / "01_hello_world.json")

    try:
        Storybook.model_validate({"id": 123})
    except PydanticValidationError as exc:
        fake_exc = exc
    else:
        # NOT a skip. `{"id": 123}` is structurally invalid for Storybook, so
        # model_validate accepting it means the model stopped rejecting garbage,
        # which is a regression this test should report rather than step around.
        # A skip here would have made that regression indistinguishable from a pass.
        pytest.fail(
            "Storybook.model_validate accepted {'id': 123}; the model no longer "
            "rejects a structurally invalid document, so this test's premise is broken"
        )

    with patch.object(Storybook, "model_validate", side_effect=fake_exc):
        result = run_gate(data)

    l2_ids = [f.rule_id for f in result.report.findings if f.rule_id.startswith("L2")]
    assert l2_ids == [], f"L2 must not run on a parse failure: {l2_ids}"


# ---------------------------------------------------------------------------
# 10. Policy layer (PL-15..PL-18) blocks through the gate
# ---------------------------------------------------------------------------


def _policy_story_with_death_ending() -> dict[str, object]:
    """A structurally valid 5-8 story whose only paths reach a death ending.

    Passes Layer 1 (reachable, terminating, ending_count matches) so the policy
    layer runs, but the death ending is forbidden for the 5-8 band (PL-15).
    """
    return {
        "schema_version": "2.0",
        "id": "s_policy_death",
        "version": 1,
        "title": "Policy Death",
        "metadata": {
            "age_band": "5-8",
            "reading_level": {"target": 2.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 2,
            "topology": "time_cave",
        },
        "start_node": "n0",
        "nodes": [
            {
                "id": "n0",
                "body": "A fork in the path.",
                "is_ending": False,
                "choices": [
                    {"id": "c1", "label": "left", "target": "n_dead"},
                    {"id": "c2", "label": "right", "target": "n_safe"},
                ],
            },
            {
                "id": "n_dead",
                "body": "It ends badly.",
                "is_ending": True,
                "ending": {
                    "id": "e_dead",
                    "valence": "negative",
                    "kind": "death",
                    "title": "The End",
                },
            },
            {
                "id": "n_safe",
                "body": "Home safe.",
                "is_ending": True,
                "ending": {
                    "id": "e_safe",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Safe",
                },
            },
        ],
    }


@pytest.mark.unit
def test_gate_blocks_on_policy_violation() -> None:
    """A 5-8 story with a death ending is blocked with a PL-15 finding."""
    result = run_gate(_policy_story_with_death_ending())
    assert result.blocked
    assert any(f.rule_id == "PL-15" for f in result.report.errors)


# ---------------------------------------------------------------------------
# 11. PL-22: an unconfigured band profile fails the gate closed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gate_blocks_on_unconfigured_band_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A story whose band has no configured BandProfile blocks with PL-22.

    Owner ruling 2026-07-16: the policy layer must fail CLOSED, not silently
    skip PL-15/16/17, when band_profile.profile_for cannot resolve a profile
    for the story's band. Every real AgeBand is configured (guarded by
    test_band_profile.py::test_profiles_match_age_band_enum_exactly), so this
    is exercised by monkeypatching profile_for at its policy.py import site,
    same as test_policy.py::test_validate_policy_fails_closed_when_profile_is_none,
    but through the full run_gate entry point used by the generation
    orchestrator and the validate API endpoint.
    """
    monkeypatch.setattr(
        "cyo_adventure.validator.policy.profile_for", lambda _band: None
    )
    result = run_gate(_policy_story_with_death_ending())
    assert result.blocked
    assert any(f.rule_id == "PL-22" for f in result.report.errors)
    # PL-15 must not have run: profile_for was forced to None, so the gate
    # cannot check the forbidden-ending-kind rule without a profile.
    assert not any(f.rule_id == "PL-15" for f in result.report.findings)


# ---------------------------------------------------------------------------
# PL-27: fill-result residue (AL-325)
# ---------------------------------------------------------------------------


def _unfilled_story() -> dict[str, object]:
    """A structurally valid story whose every node body is still a directive.

    This is what a failed fill returns: the orchestrator seeds the repair loop
    with the authoring skeleton when a fill produces no parseable document
    (AL-327), so a book that was never written is byte-identical to its
    skeleton and clears every other checker by abstention (AL-325).
    """
    story = _load(_VALID / "01_hello_world.json")
    nodes = story["nodes"]
    assert isinstance(nodes, list)
    for node in nodes:
        assert isinstance(node, dict)
        node["body"] = "<<FILL role=rising words=95 beats='the reader arrives'>>"
    return story


@pytest.mark.unit
def test_fill_result_context_blocks_on_retained_directive() -> None:
    """A document validated as a fill result fails on any retained ``<<FILL``.

    AL-325: every checker that meets a directive skips it rather than failing,
    so a gate assembled entirely from abstainers has no floor and an unwritten
    book validates clean. PL-27 is that floor.
    """
    result = run_gate(_unfilled_story(), context="fill_result")

    assert result.blocked
    assert any(f.rule_id == "PL-27" for f in result.report.errors)


@pytest.mark.unit
def test_skeleton_context_tolerates_retained_directive() -> None:
    """The catalog-time posture keeps every checker's directive tolerance.

    The 61-skeleton catalog, the mutation acceptance path and the promotion
    scripts all validate documents whose bodies are directives by construction.
    PL-27 must not fire for them, or the fix for AL-325 would break the path it
    was required not to regress.
    """
    result = run_gate(_unfilled_story())

    assert not any(f.rule_id == "PL-27" for f in result.report.findings)


def _mvp_seed_story() -> dict[str, object]:
    """A fully written story that declares itself an ADR-011 MVP/Test seed.

    Deliberately built from a story whose bodies are real prose, so the only
    thing separating it from a publishable book is the flag: if PL-28 were
    absent this document would validate clean and import.
    """
    story = _load(_VALID / "01_hello_world.json")
    metadata = story["metadata"]
    assert isinstance(metadata, dict)
    metadata["production_eligible"] = False
    return story


@pytest.mark.unit
def test_fill_result_context_blocks_an_mvp_seed() -> None:
    """A prototyping shell must not become a child-facing book.

    ADR-011 requires the MVP tier be firewalled from production and says the
    selection layer has to enforce it. It does, for generation. The manual
    `cyo-author` plus `import_cli` path had no guard at all, so all three seeds
    the ADR names by slug already had filled books in the corpus.
    """
    result = run_gate(_mvp_seed_story(), context="fill_result")

    assert result.blocked
    assert any(f.rule_id == "PL-28" for f in result.report.errors)


@pytest.mark.unit
def test_skeleton_context_tolerates_an_mvp_seed() -> None:
    """At catalog time a seed is a legitimate object, not a defect.

    `check_skeleton.py --allow-mvp` exists to inspect these, and the mutation
    core reads them. PL-28 firing under the skeleton posture would break the
    prototyping tier the ADR deliberately created.
    """
    result = run_gate(_mvp_seed_story())

    assert not any(f.rule_id == "PL-28" for f in result.report.findings)


@pytest.mark.unit
def test_a_production_story_is_untouched_by_the_mvp_firewall() -> None:
    """The firewall must key off the flag alone and nothing else.

    Every real book in the corpus is production-eligible; a rule that fired on
    any of them would block the whole beta rather than the three seeds.
    """
    result = run_gate(_load(_VALID / "01_hello_world.json"), context="fill_result")

    assert not any(f.rule_id == "PL-28" for f in result.report.findings)


@pytest.mark.unit
def test_gate_result_records_the_context_it_ran_under() -> None:
    """A verdict names the posture that produced it (AL-324).

    Without this, a ``blocked=False`` that cleared PL-27 is spelled identically
    to one that never ran it, which is exactly the defect that let three
    unwritten books be recorded as delivered.
    """
    assert run_gate(_unfilled_story()).context == "skeleton"
    assert run_gate(_unfilled_story(), context="fill_result").context == "fill_result"


@pytest.mark.unit
def test_fill_result_context_blocks_a_directive_in_a_choice_label() -> None:
    """PL-27's floor covers labels, not just bodies.

    A choice label is fillable prose and reader-visible button text, but it was
    the one piece of it no deterministic rule checked, so a document with written
    bodies and an unwritten label cleared this gate unblocked (`AL-430`). Guarded
    at the merge as well; this is the check that holds regardless of which fill
    path wrote the document.
    """
    story = _load(_VALID / "01_hello_world.json")
    nodes = story["nodes"]
    assert isinstance(nodes, list)
    node = next(n for n in nodes if isinstance(n, dict) and n.get("choices"))
    choices = node["choices"]
    assert isinstance(choices, list)
    first = choices[0]
    assert isinstance(first, dict)
    first["label"] = "<<FILL role=choice words=8>>"

    result = run_gate(story, context="fill_result")

    assert result.blocked
    assert any(
        f.rule_id == "PL-27" and "label still holds" in f.message
        for f in result.report.errors
    )


@pytest.mark.unit
def test_run_fill_gate_reproduces_the_fill_result_posture() -> None:
    """The shared helper is exactly ``run_gate(..., context="fill_result")``.

    ``run_fill_gate`` exists so that every writer of
    ``storybook_version.validation_report`` produces its report under one
    posture: generation/import_story.py, api/node_edit.py and
    api/remoderate.py all route through it. Two copies of the same call can
    drift silently, and the review surface would then rank reports built under
    different postures against each other. This pins the helper to the
    expression it replaced.
    """
    story = _unfilled_story()

    assert (
        run_fill_gate(story).report.to_dict()
        == run_gate(story, context="fill_result").report.to_dict()
    )
    assert run_fill_gate(story).context == "fill_result"
    assert run_fill_gate(story).blocked
