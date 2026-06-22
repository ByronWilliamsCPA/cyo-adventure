"""Layer-2 known-bad corpus and Tier-2 state corpus curating tests (WP5).

This module proves that each ``invalid/state/`` fixture triggers EXACTLY its
intended rule with the correct node/choice attribution, and that every
``valid/*tier2*.json`` fixture passes the combined gate cleanly.

Fixture intent summary
----------------------
silver_door_dead_end.json
    L2-9 (stateful dead-end): node ``n_silver_door`` is reachable with
    ``has_key=False``, and its only choice requires ``has_key==True``. Arriving
    without the key leaves the player with zero visible choices and no ending.
    The story provides a path that picks up the key first (so ``c_use_key`` IS
    visible in one config, avoiding L2-11), and a direct path to the door
    without the key (the dead-end path). A separate unconditional side-exit
    ensures all other configs can reach an ending (avoiding spurious L2-10 on
    other nodes).

trap_cycle.json
    L2-10 (no escape): a cycle ``n_loop_a <-> n_loop_b`` has a conditional exit
    (``c_exit_hatch`` requires ``escaped=True``) that is never satisfiable
    because nothing in the story sets ``escaped`` to True. The cycle configs
    cannot reach the ending in any reachable configuration. As a coupled
    side-effect, ``c_exit_hatch`` is never visible in any config, which also
    triggers L2-11. The primary target is L2-10; L2-11 is documented here as an
    expected co-occurrence.

unsatisfiable_condition.json
    L2-11 (dead branch): node ``n_training`` has choice ``c_champion_gate`` that
    requires ``courage >= 5``. The ``courage`` variable is bounded ``max=2`` and
    all ``inc`` effects are clamped to 2 by the engine. The condition is
    therefore unsatisfiable in every reachable configuration.

config_cap_blowup.json
    L2-12 (cap exceeded): four bool variables with dense effects produce many
    distinct configurations across ``n_start`` -> ``n_mid``. A cap of 5 is enough
    to trigger L2-12 via ``validate_layer2(story, cap=5)`` without needing to
    enumerate the full reachable space. The full gate runs cleanly on this fixture
    (default cap=100_000 is not exceeded), so ``run_gate`` is not used for the
    cap assertion.

bound_overflow.json
    L1-6 (set value above max): a ``set`` effect assigns ``courage = 5`` when
    the variable declares ``max=2``. Layer 1 catches this as a static bound
    violation before the story is parsed. Layer 2 does NOT run when L1 fails, so
    this fixture proves the L1 short-circuit. NOTE: the engine clamps ``inc``/
    ``dec`` at runtime, so reachable-overflow via ``inc`` past max is not an L1
    error (it is silently clamped). This fixture uses a ``set`` operation, which
    IS checked statically by L1-6 (``_set_bounds_error``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.layer2 import validate_layer2

if TYPE_CHECKING:
    from cyo_adventure.validator.report import ValidationReport

# ---------------------------------------------------------------------------
# Fixture path constants
# ---------------------------------------------------------------------------

_STATE = Path(__file__).parent.parent / "fixtures" / "storybook" / "invalid" / "state"
_VALID = Path(__file__).parent.parent / "fixtures" / "storybook" / "valid"


def _load_raw(path: Path) -> dict[str, object]:
    """Load a story fixture as a raw dict for ``run_gate``.

    Args:
        path: Absolute path to the JSON fixture file.

    Returns:
        dict[str, object]: The decoded JSON mapping.
    """
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[return-value]


def _load_story(path: Path) -> Storybook:
    """Load and parse a Storybook from a JSON fixture file.

    Args:
        path: Absolute path to the JSON fixture file.

    Returns:
        Storybook: The parsed and validated story model.
    """
    return Storybook.model_validate(_load_raw(path))


# ---------------------------------------------------------------------------
# Section 1: Rejection tests for invalid/state fixtures
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_silver_door_dead_end_triggers_l2_9() -> None:
    """silver_door_dead_end.json must trigger L2-9 attributed to n_silver_door.

    The fixture is L1-clean (structurally sound graph). L2-9 fires because
    the configuration (n_silver_door, has_key=False) has zero visible choices
    and is not an ending node. The key choice IS visible in the (n_silver_door,
    has_key=True) configuration, so L2-11 does not fire.
    """
    data = _load_raw(_STATE / "silver_door_dead_end.json")
    result = run_gate(data)

    # L1 must have passed (the failure is purely a Layer-2 concern).
    l1_errors = [
        f
        for f in result.report.findings
        if f.rule_id.startswith("L1") and f.severity.value == "error"
    ]
    assert l1_errors == [], f"expected no L1 errors; got {l1_errors}"

    # Gate must block.
    assert result.blocked is True

    # L2-9 must be present.
    assert "L2-9" in result.report.rule_ids(), (
        f"expected L2-9; got rule_ids={result.report.rule_ids()}"
    )

    # L2-9 must be attributed to n_silver_door.
    dead_end_nodes = {f.node_id for f in result.report.findings if f.rule_id == "L2-9"}
    assert "n_silver_door" in dead_end_nodes, (
        f"expected L2-9 on n_silver_door; attributed to {dead_end_nodes}"
    )

    # No L2-11 (the key choice is visible in the has_key=True config).
    assert "L2-11" not in result.report.rule_ids(), (
        "unexpected L2-11: the key choice should be visible when has_key=True"
    )


@pytest.mark.unit
def test_trap_cycle_triggers_l2_10() -> None:
    """trap_cycle.json must trigger L2-10 for the unreachable-ending loop nodes.

    The cycle n_loop_a <-> n_loop_b has only a conditional exit (escaped==True)
    that is never satisfiable. L2-10 fires for every config in the cycle. As a
    coupled side-effect L2-11 also fires for c_exit_hatch (expected co-occurrence,
    documented above).
    """
    data = _load_raw(_STATE / "trap_cycle.json")
    result = run_gate(data)

    # L1 must have passed.
    l1_errors = [
        f
        for f in result.report.findings
        if f.rule_id.startswith("L1") and f.severity.value == "error"
    ]
    assert l1_errors == [], f"expected no L1 errors; got {l1_errors}"

    # Gate must block.
    assert result.blocked is True

    # L2-10 must be present.
    assert "L2-10" in result.report.rule_ids(), (
        f"expected L2-10; got rule_ids={result.report.rule_ids()}"
    )

    # L2-10 must attribute to the cycle nodes.
    escape_nodes = {f.node_id for f in result.report.findings if f.rule_id == "L2-10"}
    assert escape_nodes & {"n_loop_a", "n_loop_b"}, (
        f"expected L2-10 on n_loop_a or n_loop_b; got {escape_nodes}"
    )


@pytest.mark.unit
def test_unsatisfiable_condition_triggers_l2_11() -> None:
    """unsatisfiable_condition.json must trigger L2-11 on c_champion_gate.

    courage is bounded max=2 but the condition requires courage >= 5. The engine
    clamps all inc effects at max=2, so the condition is never true. L2-11
    attributes to choice c_champion_gate on node n_training.
    """
    data = _load_raw(_STATE / "unsatisfiable_condition.json")
    result = run_gate(data)

    # L1 must have passed.
    l1_errors = [
        f
        for f in result.report.findings
        if f.rule_id.startswith("L1") and f.severity.value == "error"
    ]
    assert l1_errors == [], f"expected no L1 errors; got {l1_errors}"

    # Gate must block.
    assert result.blocked is True

    # L2-11 must be present.
    assert "L2-11" in result.report.rule_ids(), (
        f"expected L2-11; got rule_ids={result.report.rule_ids()}"
    )

    # L2-11 must be attributed to c_champion_gate on n_training.
    dead_branch_findings = [f for f in result.report.findings if f.rule_id == "L2-11"]
    choice_ids = {f.choice_id for f in dead_branch_findings}
    node_ids = {f.node_id for f in dead_branch_findings}
    assert "c_champion_gate" in choice_ids, (
        f"expected c_champion_gate in L2-11 choices; got {choice_ids}"
    )
    assert "n_training" in node_ids, (
        f"expected n_training in L2-11 nodes; got {node_ids}"
    )


@pytest.mark.unit
def test_config_cap_blowup_triggers_l2_12() -> None:
    """config_cap_blowup.json must trigger L2-12 when validated with cap=5.

    The fixture has four bool variables with dense effects across two branch
    nodes, producing at least 10 distinct configurations. With cap=5 the walk
    aborts and returns exactly one L2-12 finding and no other L2 findings.

    This test uses validate_layer2 directly with a small cap rather than
    run_gate, because run_gate uses the default cap=100_000 (which this small
    fixture does not exceed).
    """
    story = _load_story(_STATE / "config_cap_blowup.json")

    # First confirm the full gate passes (the fixture is L1-clean and does not
    # exceed the default cap).
    data = _load_raw(_STATE / "config_cap_blowup.json")
    gate_result = run_gate(data)
    assert gate_result.blocked is False, (
        f"config_cap_blowup should pass the full gate; got {gate_result.report.errors}"
    )

    # Now assert that a small cap triggers L2-12.
    report: ValidationReport = validate_layer2(story, cap=5)
    assert not report.ok, "expected report.ok=False when L2-12 fires"
    assert "L2-12" in report.rule_ids(), (
        f"expected L2-12 with cap=5; got {report.rule_ids()}"
    )

    # Exactly one L2-12 finding; no other findings when capped.
    l2_12_findings = [f for f in report.findings if f.rule_id == "L2-12"]
    assert len(l2_12_findings) == 1, (
        f"expected exactly one L2-12 finding; got {report.findings}"
    )
    other = [f for f in report.findings if f.rule_id != "L2-12"]
    assert other == [], (
        f"expected no findings other than L2-12 when capped; got {other}"
    )


@pytest.mark.unit
def test_bound_overflow_triggers_l1_6() -> None:
    """bound_overflow.json must trigger L1-6 and NOT run Layer 2.

    A ``set`` effect assigns ``courage=5`` when the variable declares ``max=2``.
    L1-6 catches this as a static bound violation. The gate short-circuits before
    Layer 2, so no L2 rule ids appear in the report.

    NOTE: the engine clamps ``inc``/``dec`` at runtime (values never escape
    declared bounds via increment). This fixture uses a ``set`` operation, which
    IS validated statically by L1-6 (``_set_bounds_error``). Reachable-overflow
    via ``inc`` past max is silently clamped and therefore not an L1-6 case.
    """
    data = _load_raw(_STATE / "bound_overflow.json")
    result = run_gate(data)

    # Gate must block.
    assert result.blocked is True

    # L1-6 must be present.
    l1_6_findings = [f for f in result.report.findings if f.rule_id == "L1-6"]
    assert l1_6_findings, (
        f"expected L1-6 finding; got rule_ids={result.report.rule_ids()}"
    )

    # No L2 findings (Layer 2 must not run when L1 fails).
    l2_findings = [f for f in result.report.findings if f.rule_id.startswith("L2")]
    assert l2_findings == [], (
        f"L2 must not run when L1 fails; got {[f.rule_id for f in l2_findings]}"
    )


# ---------------------------------------------------------------------------
# Section 2: 100% rejection guarantee (parametrized)
# ---------------------------------------------------------------------------

_INVALID_STATE_FIXTURES = [
    ("silver_door_dead_end.json", "L2-9"),
    ("trap_cycle.json", "L2-10"),
    ("unsatisfiable_condition.json", "L2-11"),
    ("bound_overflow.json", "L1-6"),
]


@pytest.mark.unit
@pytest.mark.parametrize(("filename", "expected_rule_id"), _INVALID_STATE_FIXTURES)
def test_invalid_state_fixture_is_blocked(filename: str, expected_rule_id: str) -> None:
    """Every invalid/state fixture must be rejected (blocked=True via run_gate).

    For config_cap_blowup.json the assertion is handled separately via
    validate_layer2 with a small cap; this parametrized sweep covers the four
    fixtures that are blocked by run_gate directly.

    Args:
        filename: The fixture file name.
        expected_rule_id: The rule id that must appear in the report.
    """
    data = _load_raw(_STATE / filename)
    result = run_gate(data)
    assert result.blocked is True, (
        f"{filename}: expected blocked=True; rule_ids={result.report.rule_ids()}"
    )
    assert expected_rule_id in result.report.rule_ids(), (
        f"{filename}: expected {expected_rule_id} in report; "
        f"got rule_ids={result.report.rule_ids()}"
    )


# ---------------------------------------------------------------------------
# Section 3: Valid Tier-2 corpus passes the full gate
# ---------------------------------------------------------------------------


def _tier2_valid_fixtures() -> list[str]:
    """Return the filenames of every valid Tier-2 fixture in the valid directory.

    Returns:
        list[str]: Sorted list of filename strings.
    """
    return sorted(p.name for p in _VALID.glob("*tier2*.json"))


@pytest.mark.unit
@pytest.mark.parametrize("filename", _tier2_valid_fixtures())
def test_valid_tier2_fixture_passes_gate(filename: str) -> None:
    """Every valid Tier-2 fixture (including newly added ones) must pass run_gate.

    A fixture passes when blocked=False. RL-13 warnings and L1-7 node-count
    warnings are allowed and do not constitute failures.

    Args:
        filename: The fixture file name.
    """
    data = _load_raw(_VALID / filename)
    result = run_gate(data)
    assert result.blocked is False, (
        f"{filename}: unexpected blocking; "
        f"errors={[f.message for f in result.report.errors]}"
    )
