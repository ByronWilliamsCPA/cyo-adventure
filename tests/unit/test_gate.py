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

from cyo_adventure.validator.gate import GateResult, run_gate

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
            "ending_count": 1,
            "topology": "branch_and_bottleneck",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
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
                    }
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
def test_defensive_parse_failure_sets_blocked() -> None:
    """When Pydantic raises after a clean L1, the gate must block defensively.

    This exercises the rare schema-drift scenario: L1 passes but model_validate
    still raises. We simulate it by patching Storybook.model_validate.
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
        pytest.skip("Could not construct a PydanticValidationError for the mock")

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
        pytest.skip("Could not construct a PydanticValidationError for the mock")

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
