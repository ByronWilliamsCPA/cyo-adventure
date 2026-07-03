"""Tests for the Layer-1 graph validator.

The validator is driven against the Phase-0 fixture corpus: every valid story
must pass (no error-severity findings), and every invalid story must be rejected
with its expected rule id. ``stateful_dead_end`` is a Tier-2 (Layer-2) case and
must pass Layer 1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.validator import Severity, layer1, validate_layer1
from cyo_adventure.validator.band_profile import production_cell_budget
from cyo_adventure.validator.layer1 import band_budget

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cyo_adventure.validator.report import ValidationReport

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "storybook"
_VALID = _FIXTURES / "valid"
_INVALID = _FIXTURES / "invalid"


def _load(path: Path) -> Mapping[str, object]:
    """Load a story fixture as a mapping."""
    return json.loads(path.read_text(encoding="utf-8"))


# --- Valid corpus --------------------------------------------------------------

_VALID_FILES = sorted(_VALID.glob("*.json"))


@pytest.mark.unit
@pytest.mark.parametrize("path", _VALID_FILES, ids=lambda p: p.name)
def test_valid_fixtures_pass_layer1(path: Path) -> None:
    """Every valid fixture passes Layer 1 (no error-severity findings)."""
    report = validate_layer1(_load(path))
    assert report.ok, [f.message for f in report.errors]


# --- Invalid corpus ------------------------------------------------------------

# Each invalid fixture maps to the Layer-1 rule it is expected to trip.
_EXPECTED_RULE: dict[str, str] = {
    "invalid/schema/duplicate_node_id.json": "L1-2",
    "invalid/schema/undeclared_variable.json": "L1-6",
    "invalid/schema/non_whitelisted_operator.json": "L1-6",
    "invalid/schema/int_initial_above_max.json": "L1-6",
    "invalid/schema/missing_ending_block.json": "L1-4",
    "invalid/schema/tier1_with_variables.json": "L1-6",
    "invalid/graph/dangling_target.json": "L1-2",
    "invalid/graph/orphan_node.json": "L1-3",
    "invalid/graph/unreachable_ending.json": "L1-3",
    "invalid/graph/trap_loop.json": "L1-5",
}


@pytest.mark.unit
@pytest.mark.parametrize(("rel", "rule_id"), list(_EXPECTED_RULE.items()))
def test_invalid_fixture_rejected_with_rule(rel: str, rule_id: str) -> None:
    """Each invalid fixture is rejected and carries its expected rule id."""
    report = validate_layer1(_load(_INVALID / Path(rel).relative_to("invalid")))
    assert not report.ok, f"{rel} should have failed Layer 1"
    assert rule_id in report.rule_ids(), (
        f"{rel}: expected {rule_id}, got {sorted(report.rule_ids())}"
    )


@pytest.mark.unit
def test_stateful_dead_end_passes_layer1() -> None:
    """The silver-door story is a Tier-2 (Layer-2) case and passes Layer 1."""
    report = validate_layer1(_load(_INVALID / "graph" / "stateful_dead_end.json"))
    assert report.ok, [f.message for f in report.errors]


# --- Targeted rule behaviour ---------------------------------------------------


@pytest.mark.unit
def test_below_lower_node_bound_is_warning_not_error() -> None:
    """A tiny valid story warns on node count but does not fail (L1-7)."""
    report = validate_layer1(_load(_VALID / "01_hello_world.json"))
    assert report.ok
    budget_warnings = [f for f in report.warnings if f.rule_id == "L1-7"]
    assert budget_warnings, "expected an L1-7 below-lower-bound warning"


@pytest.mark.unit
def test_dangling_target_attributes_node_and_choice() -> None:
    """An L1-2 dangling-target finding names the offending node and choice."""
    report = validate_layer1(_load(_INVALID / "graph" / "dangling_target.json"))
    l1_2 = [f for f in report.errors if f.rule_id == "L1-2"]
    assert l1_2
    assert any(f.node_id is not None for f in l1_2)


@pytest.mark.unit
def test_report_is_serializable() -> None:
    """A report round-trips to a JSON-serializable dict."""
    report = validate_layer1(_load(_INVALID / "graph" / "trap_loop.json"))
    payload = report.to_dict()
    assert payload["ok"] is False
    text = json.dumps(payload)
    assert "L1-5" in text


@pytest.mark.unit
def test_severity_enum_values() -> None:
    """Severity serializes to the documented wire strings."""
    assert str(Severity.ERROR) == "error"
    assert str(Severity.WARNING) == "warning"


@pytest.mark.unit
def test_band_budget_delegates_to_profile() -> None:
    """band_budget reads the band profile and returns the budget triple."""
    assert band_budget("13-16") == (30, 60, 10)
    assert band_budget("99-100") is None


@pytest.mark.unit
def test_legacy_budgets_table_is_gone() -> None:
    """The legacy module-level _BUDGETS table has been removed."""
    assert not hasattr(layer1, "_BUDGETS")


# --- Synthetic stories for branch coverage -------------------------------------


def _meta(
    age_band: str = "10-13", tier: int = 2, ending_count: int = 1
) -> dict[str, object]:
    """Build a minimal valid metadata block."""
    return {
        "age_band": age_band,
        "reading_level": {"scheme": "flesch_kincaid", "target": 4.0, "tolerance": 1.0},
        "tier": tier,
        "themes": [],
        "estimated_minutes": 5,
        "ending_count": ending_count,
        "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
        "topology": "branch_and_bottleneck",
    }


def _ending(nid: str = "n_end", eid: str = "e1") -> dict[str, object]:
    """Build an ending node."""
    return {
        "id": nid,
        "body": "The end.",
        "on_enter": [],
        "choices": [],
        "is_ending": True,
        "ending": {
            "id": eid,
            "valence": "positive",
            "kind": "success",
            "title": "Done",
        },
        "tags": [],
    }


def _link(nid: str, target: str, **over: object) -> dict[str, object]:
    """Build a non-ending node with a single choice to ``target``."""
    node: dict[str, object] = {
        "id": nid,
        "body": "x",
        "on_enter": [],
        "choices": [{"id": f"c_{nid}", "label": "go", "target": target, "effects": []}],
        "is_ending": False,
        "tags": [],
    }
    node.update(over)
    return node


def _story(
    nodes: list[dict[str, object]],
    *,
    variables: list[dict[str, object]] | None = None,
    meta: dict[str, object] | None = None,
    start: str = "n_start",
) -> dict[str, object]:
    """Assemble a story mapping around the given nodes."""
    return {
        "schema_version": "2.0",
        "id": "s_test",
        "version": 1,
        "title": "T",
        "metadata": meta or _meta(),
        "variables": variables or [],
        "start_node": start,
        "nodes": nodes,
    }


@pytest.mark.unit
def test_effect_on_undeclared_variable_is_l1_6() -> None:
    """An effect targeting an undeclared variable trips L1-6."""
    node = _link(
        "n_start", "n_end", on_enter=[{"op": "set", "var": "ghost", "value": True}]
    )
    report = validate_layer1(_story([node, _ending()]))
    assert "L1-6" in report.rule_ids()


@pytest.mark.unit
def test_inc_on_bool_variable_is_l1_6() -> None:
    """Applying ``inc`` to a bool variable trips L1-6."""
    node = _link(
        "n_start", "n_end", on_enter=[{"op": "inc", "var": "flag", "value": 1}]
    )
    variables = [{"name": "flag", "type": "bool", "initial": False}]
    report = validate_layer1(
        _story([node, _ending()], variables=variables, meta=_meta(tier=2))
    )
    assert "L1-6" in report.rule_ids()


@pytest.mark.unit
def test_set_bool_with_int_value_is_l1_6() -> None:
    """A ``set`` of an int onto a bool variable trips L1-6."""
    node = _link(
        "n_start", "n_end", on_enter=[{"op": "set", "var": "flag", "value": 3}]
    )
    variables = [{"name": "flag", "type": "bool", "initial": False}]
    report = validate_layer1(_story([node, _ending()], variables=variables))
    assert "L1-6" in report.rule_ids()


@pytest.mark.unit
def test_ordering_operator_on_bool_variable_is_l1_6() -> None:
    """Using an ordering operator on a bool variable trips L1-6."""
    cond = {"<": [{"var": "flag"}, 1]}
    node = _link("n_start", "n_end")
    choices = node["choices"]
    assert isinstance(choices, list)
    choices[0]["condition"] = cond
    variables = [{"name": "flag", "type": "bool", "initial": False}]
    report = validate_layer1(_story([node, _ending()], variables=variables))
    assert "L1-6" in report.rule_ids()


@pytest.mark.unit
def test_nested_ordering_on_bool_in_compound_is_l1_6() -> None:
    """An ordering-on-bool nested inside an ``and`` is still caught (L1-6)."""
    cond = {"and": [{"<": [{"var": "flag"}, 1]}, {"var": "flag"}]}
    node = _link("n_start", "n_end")
    choices = node["choices"]
    assert isinstance(choices, list)
    choices[0]["condition"] = cond
    variables = [{"name": "flag", "type": "bool", "initial": False}]
    report = validate_layer1(_story([node, _ending()], variables=variables))
    assert "L1-6" in report.rule_ids()


@pytest.mark.unit
def test_variable_min_greater_than_max_is_l1_6() -> None:
    """A variable whose min exceeds its max trips L1-6."""
    variables = [{"name": "x", "type": "int", "initial": 0, "min": 5, "max": 2}]
    report = validate_layer1(
        _story([_link("n_start", "n_end"), _ending()], variables=variables)
    )
    assert "L1-6" in report.rule_ids()


@pytest.mark.unit
def test_node_count_above_upper_bound_is_error() -> None:
    """Exceeding the tier's upper node-count bound is an L1-7 error."""
    chain = [_link(f"n{i}", f"n{i + 1}") for i in range(30)]
    nodes = [*chain, _ending("n30")]
    report = validate_layer1(
        _story(nodes, meta=_meta(age_band="8-11", tier=1), start="n0")
    )
    assert any(
        f.rule_id == "L1-7"
        and f.severity is Severity.ERROR
        and "node_count" in f.message
        for f in report.errors
    )


@pytest.mark.unit
def test_branch_depth_above_max_is_error() -> None:
    """A chain deeper than the tier's max branch depth is an L1-7 error."""
    chain = [_link(f"n{i}", f"n{i + 1}") for i in range(8)]
    nodes = [*chain, _ending("n8")]
    report = validate_layer1(
        _story(nodes, meta=_meta(age_band="8-11", tier=1), start="n0")
    )
    assert any(
        f.rule_id == "L1-7"
        and f.severity is Severity.ERROR
        and "branch_depth" in f.message
        for f in report.errors
    )


@pytest.mark.unit
def test_band_budget_scale_profiles() -> None:
    """band_budget defaults to standard; "compact" returns the smaller numbers."""
    # Default and explicit "standard" are identical (full-size ladder).
    assert band_budget("8-11") == (15, 30, 6)
    assert band_budget("8-11", "standard") == (15, 30, 6)
    # Compact profile is smaller across all bands.
    assert band_budget("8-11", "compact") == (6, 12, 4)
    assert band_budget("10-13", "compact") == (10, 18, 5)
    assert band_budget("13-16", "compact") == (12, 24, 6)


@pytest.mark.unit
def test_compact_scale_enforces_smaller_branch_depth() -> None:
    """A depth-5 chain passes standard (max 6) but trips L1-7 under compact (max 4)."""
    chain = [_link(f"n{i}", f"n{i + 1}") for i in range(5)]
    nodes = [*chain, _ending("n5")]
    story = _story(nodes, meta=_meta(age_band="8-11", tier=1), start="n0")

    standard = validate_layer1(story)
    compact = validate_layer1(story, "compact")

    # Standard 8-11 allows depth up to 6: no branch-depth error.
    assert not any(
        f.rule_id == "L1-7" and "branch_depth" in f.message for f in standard.errors
    )
    # Compact 8-11 caps depth at 4: depth 5 is an error.
    assert any(
        f.rule_id == "L1-7" and "branch_depth" in f.message for f in compact.errors
    )


@pytest.mark.unit
def test_compact_scale_accepts_small_node_count() -> None:
    """A 6-node story warns under standard (min 15) but is in-band under compact."""
    chain = [_link(f"n{i}", f"n{i + 1}") for i in range(5)]
    nodes = [*chain, _ending("n5")]
    story = _story(nodes, meta=_meta(age_band="8-11", tier=1), start="n0")

    standard = validate_layer1(story)
    compact = validate_layer1(story, "compact")

    # Standard min is 15, so 6 nodes is flagged (a node_count finding).
    assert any(
        f.rule_id == "L1-7" and "node_count" in f.message for f in standard.findings
    )
    # Compact band is 6..12, so 6 nodes is in range: no node_count finding.
    assert not any(
        f.rule_id == "L1-7" and "node_count" in f.message for f in compact.findings
    )


@pytest.mark.unit
def test_ending_count_mismatch_is_l1_7_error() -> None:
    """A metadata ending_count that disagrees with reality is an L1-7 error."""
    nodes = [_link("n_start", "n_end"), _ending()]
    report = validate_layer1(_story(nodes, meta=_meta(ending_count=2)))
    assert any(
        f.rule_id == "L1-7" and "ending_count" in f.message for f in report.errors
    )


@pytest.mark.unit
def test_ending_node_with_choices_is_l1_4() -> None:
    """An ending node that also carries choices trips L1-4."""
    bad_ending = _ending()
    bad_ending["choices"] = [
        {"id": "c_x", "label": "go", "target": "n_start", "effects": []}
    ]
    report = validate_layer1(_story([_link("n_start", "n_end"), bad_ending]))
    assert "L1-4" in report.rule_ids()


@pytest.mark.unit
def test_self_loop_with_no_escape_is_l1_5() -> None:
    """A self-looping node that cannot reach an ending is a trap loop (L1-5)."""
    loop = _link("n_loop", "n_loop")
    nodes = [_link("n_start", "n_loop"), loop, _ending()]
    report = validate_layer1(_story(nodes))
    assert "L1-5" in report.rule_ids()


@pytest.mark.unit
def test_missing_nodes_is_schema_error() -> None:
    """A document with no nodes array fails L1-1 and skips graph rules."""
    report = validate_layer1({"id": "s_test", "start_node": "x"})
    assert not report.ok
    assert "L1-1" in report.rule_ids()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("band", "expected"),
    [("3-5", (8, 20, 4)), ("5-8", (12, 30, 6)), ("16+", (30, 60, 12))],
)
def test_new_bands_have_budgets(band: str, expected: tuple[int, int, int]) -> None:
    """band_budget returns the configured tuple for each new band."""
    budget = band_budget(band)
    assert budget is not None, f"No budget entry found for band {band!r}"
    assert budget == expected


def _node_count_errors(report: ValidationReport) -> list[str]:
    """Return L1-7 node_count ERROR messages from a validation report."""
    return [
        f.message
        for f in report.errors
        if f.rule_id == "L1-7"
        and f.severity is Severity.ERROR
        and "node_count" in f.message
    ]


@pytest.mark.unit
def test_mvp_tier_budget_overrides_band_ceiling() -> None:
    """A non-production (MVP) story is capped at the MVP envelope, not the band's.

    47 nodes sit within the 16+ production ceiling (60) but exceed the
    band-independent MVP ceiling (45), so the same graph passes the node-count
    budget as production and trips L1-7 node_count as MVP.
    """
    chain = [_link(f"n{i}", f"n{i + 1}") for i in range(46)]
    nodes = [*chain, _ending("n46")]
    production_meta = _meta(age_band="16+", tier=1)
    mvp_meta = {**_meta(age_band="16+", tier=1), "production_eligible": False}

    production = validate_layer1(_story(nodes, meta=production_meta, start="n0"))
    mvp = validate_layer1(_story(nodes, meta=mvp_meta, start="n0"))

    assert _node_count_errors(production) == []
    assert _node_count_errors(mvp), "MVP story above the 45-node envelope must error"


@pytest.mark.unit
def test_mvp_tier_below_envelope_warns_not_errors() -> None:
    """An MVP story below the MVP floor warns (not errors), matching the band path."""
    chain = [_link(f"n{i}", f"n{i + 1}") for i in range(3)]
    nodes = [*chain, _ending("n3")]
    mvp_meta = {**_meta(age_band="16+", tier=1), "production_eligible": False}

    report = validate_layer1(_story(nodes, meta=mvp_meta, start="n0"))

    assert _node_count_errors(report) == []
    assert any(
        f.rule_id == "L1-7"
        and f.severity is Severity.WARNING
        and "node_count" in f.message
        for f in report.findings
    )


@pytest.mark.unit
def test_production_length_cell_lifts_the_band_ceiling() -> None:
    """The same 80-node 8-11 story errors as band-scale but passes as 'short'.

    Band-level 8-11 caps at 30 nodes; the ADR-011 'short' production cell allows
    60-100, so declaring a length raises the node ceiling. (The linear fixture
    also trips branch_depth, which ``_node_count_errors`` deliberately excludes.)
    """
    chain = [_link(f"n{i}", f"n{i + 1}") for i in range(79)]
    nodes = [*chain, _ending("n79")]  # 80 nodes
    band_meta = _meta(age_band="8-11", tier=1)
    cell_meta = {**band_meta, "length": "short", "narrative_style": "prose"}

    band_scale = validate_layer1(_story(nodes, meta=band_meta, start="n0"))
    cell_scale = validate_layer1(_story(nodes, meta=cell_meta, start="n0"))

    assert _node_count_errors(band_scale)  # 80 > band 8-11 max 30
    assert _node_count_errors(cell_scale) == []  # 80 within the 60-100 cell


@pytest.mark.unit
def test_production_cell_ceiling_still_blocks_above_max() -> None:
    """A production story above its cell's max node count trips L1-7."""
    chain = [_link(f"n{i}", f"n{i + 1}") for i in range(100)]
    nodes = [*chain, _ending("n100")]  # 101 nodes
    cell_meta = {
        **_meta(age_band="8-11", tier=1),
        "length": "short",
        "narrative_style": "prose",
    }
    report = validate_layer1(_story(nodes, meta=cell_meta, start="n0"))
    assert _node_count_errors(report)  # 101 > 100 cell max


@pytest.mark.unit
def test_off_matrix_length_falls_back_to_band_budget() -> None:
    """A length with no matching cell (3-5 'long') uses the band budget."""
    chain = [_link(f"n{i}", f"n{i + 1}") for i in range(30)]
    nodes = [*chain, _ending("n30")]  # 31 nodes, above 3-5 band max 20
    meta = {
        **_meta(age_band="3-5", tier=1, ending_count=1),
        "length": "long",
        "narrative_style": "prose",
    }
    report = validate_layer1(_story(nodes, meta=meta, start="n0"))
    assert _node_count_errors(report)  # no 3-5 'long' cell -> band max 20 applies


@pytest.mark.unit
def test_resolve_node_budget_precedence() -> None:
    """The shared resolver applies MVP -> production-cell -> band precedence.

    This is the single budget path both the gate and the Stage A prompt call, so
    the precedence is asserted once here rather than through each caller.
    """
    from cyo_adventure.validator.band_profile import mvp_node_budget
    from cyo_adventure.validator.layer1 import ScalePlacement, resolve_node_budget

    # 1. MVP overrides everything, ignoring an otherwise-valid length cell.
    assert resolve_node_budget(
        "8-11",
        ScalePlacement(length="short", production_eligible=False),
        scale="standard",
    ) == mvp_node_budget("8-11")
    # 2. A declared, offered cell wins over the band budget.
    assert resolve_node_budget(
        "8-11",
        ScalePlacement(length="short", narrative_style="prose"),
        scale="standard",
    ) == production_cell_budget("8-11", "short", "prose")
    # 3. No length falls back to the band budget.
    assert resolve_node_budget(
        "8-11", ScalePlacement(), scale="standard"
    ) == band_budget("8-11")
    # 4. An off-matrix length also falls back to the band budget.
    assert resolve_node_budget(
        "3-5", ScalePlacement(length="long"), scale="standard"
    ) == band_budget("3-5")
