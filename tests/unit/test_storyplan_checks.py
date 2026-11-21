"""Unit tests for the Story Plan structural checks and CLI (ADR-033, WP-1.2).

Every rule has a clean case (the shared example passes it) and a firing case
(its witness, plus focused fixtures that pin node, state, fact and route).
The witness battery is also run through ``verify_witnesses`` so a rule that
stops firing, or starts firing on a clean plan, fails here.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any, cast

import pytest

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storyplan import StoryPlan
from cyo_adventure.storyplan.checks import (
    ASSERT_RULE,
    RULE_IDS,
    WITNESSES,
    PlanFinding,
    RuleWitness,
    base_example,
    build_config_graph,
    check_assertions,
    check_plan,
    guaranteed_on_entry,
    meet_of,
    must_not_assert,
    verify_witnesses,
)
from cyo_adventure.storyplan.models import shape_hash
from cyo_adventure.validator.report import Severity, ValidationReport
from scripts.check_story_plan import default_plan_path, main


def _pair() -> tuple[dict[str, Any], dict[str, Any]]:
    """Return mutable copies of the clean example book and plan.

    Returns:
        tuple[dict[str, Any], dict[str, Any]]: ``(book, plan)``.
    """
    book, plan = base_example()
    return (
        cast("dict[str, Any]", copy.deepcopy(book)),
        cast("dict[str, Any]", copy.deepcopy(plan)),
    )


def _rebind(book: dict[str, Any], plan: dict[str, Any]) -> None:
    """Re-bind a plan after a graph edit to its book.

    Args:
        book: The edited book.
        plan: The plan, updated in place.
    """
    plan["provenance"]["shape_hash"] = shape_hash(Storybook.model_validate(book))


def _check(book: dict[str, Any], plan: dict[str, Any]) -> ValidationReport:
    """Parse and check a pair.

    Args:
        book: The book document.
        plan: The plan document.

    Returns:
        ValidationReport: The report.
    """
    return check_plan(StoryPlan.model_validate(plan), Storybook.model_validate(book))


def _findings(report: ValidationReport, rule: str) -> list[PlanFinding]:
    """Return a report's findings for one rule, typed as plan findings.

    Args:
        report: The report.
        rule: The rule id.

    Returns:
        list[PlanFinding]: The findings.
    """
    return [cast("PlanFinding", f) for f in report.findings if f.rule_id == rule]


def _node(book: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return a book node by id.

    Args:
        book: The book document.
        node_id: The node id.

    Returns:
        dict[str, Any]: The node.
    """
    return next(n for n in book["nodes"] if n["id"] == node_id)


# ---------------------------------------------------------------------------
# The battery
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_clean_example_passes_every_rule() -> None:
    report = _check(*_pair())
    assert report.ok
    assert report.findings == []


@pytest.mark.unit
def test_there_is_one_witness_per_rule() -> None:
    assert tuple(w.rule_id for w in WITNESSES) == RULE_IDS


@pytest.mark.unit
@pytest.mark.parametrize("witness", WITNESSES, ids=lambda w: w.rule_id)
def test_each_witness_trips_exactly_its_rule(witness: RuleWitness) -> None:
    book, plan = witness.build()
    report = check_plan(StoryPlan.model_validate(plan), Storybook.model_validate(book))
    assert {f.rule_id for f in report.errors} == {witness.rule_id}


@pytest.mark.unit
def test_verify_witnesses_is_green_and_reports_a_broken_witness() -> None:
    assert verify_witnesses() == []
    lying = RuleWitness("SP-7", WITNESSES[2].build)  # an SP-2 witness
    assert verify_witnesses([lying]) == [
        "SP-7: witness should trip exactly that rule, tripped ['SP-2']"
    ]


@pytest.mark.unit
def test_verify_witnesses_reports_a_dirty_base(monkeypatch: pytest.MonkeyPatch) -> None:
    from cyo_adventure.storyplan import checks

    dirty = WITNESSES[7].build()  # the SP-7 witness standing in as the base
    monkeypatch.setattr(checks, "base_example", lambda: dirty)
    assert verify_witnesses([]) == ["base: expected no errors, got ['SP-7']"]


@pytest.mark.unit
def test_the_checker_is_deterministic() -> None:
    for witness in WITNESSES:
        book, plan = witness.build()
        first = [f.to_dict() for f in _check(book, plan).findings]
        second = [f.to_dict() for f in _check(book, plan).findings]
        assert first == second


# ---------------------------------------------------------------------------
# The fixpoint (NC-1 moved into the package)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_meet_of_is_intersection_and_empty_for_no_sets() -> None:
    assert meet_of([]) == frozenset()
    assert meet_of([frozenset("ab"), frozenset("bc")]) == frozenset("b")


@pytest.mark.unit
def test_guaranteed_on_entry_handles_merges_edges_and_cycles() -> None:
    # s -> a -> m, s -> b -> m, m -> a (a cycle back through a).
    vertices = ["s", "a", "b", "m"]
    incoming = {
        "a": [("s", frozenset()), ("m", frozenset())],
        "b": [("s", frozenset({"edge"}))],
        "m": [("a", frozenset()), ("b", frozenset())],
    }
    gen = {"s": frozenset({"f0"}), "a": frozenset({"fa"}), "b": frozenset({"fa"})}
    entry = guaranteed_on_entry(
        vertices, incoming, "s", gen, frozenset({"f0", "fa", "edge"})
    )
    assert entry["s"] == frozenset()
    assert entry["a"] == frozenset({"f0"})
    assert entry["b"] == frozenset({"f0", "edge"})
    assert entry["m"] == frozenset({"f0", "fa"})


@pytest.mark.unit
def test_an_unreached_vertex_without_predecessors_enters_with_nothing() -> None:
    entry = guaranteed_on_entry(["s", "x"], {}, "s", {}, frozenset({"f"}))
    assert entry == {"s": frozenset(), "x": frozenset()}


# ---------------------------------------------------------------------------
# Configuration graph
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_config_graph_labels_edges_with_choice_ids() -> None:
    graph = build_config_graph(Storybook.model_validate(_pair()[0]))
    assert graph.node_of[0] == "n_start"
    assert not graph.capped
    for config, edges in enumerate(graph.succ):
        state = dict(graph.state_of[config])
        labels = {choice_id for choice_id, _ in edges}
        if graph.node_of[config] == "n_fork":
            assert ("c_cave" in labels) is state["has_map"]
            assert ("c_tunnel" in labels) is state["has_lamp"]


@pytest.mark.unit
def test_a_capped_walk_is_an_sp0_error() -> None:
    book, plan = _pair()
    report = check_plan(
        StoryPlan.model_validate(plan), Storybook.model_validate(book), cap=3
    )
    messages = [f.message for f in _findings(report, "SP-0")]
    assert any("stopped at its cap of 3" in m for m in messages)


@pytest.mark.unit
def test_a_walk_and_engine_disagreement_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from cyo_adventure.player.engine import StoryEngine
    from cyo_adventure.storyplan import checks

    class _Drifted(StoryEngine):
        def visible_choices(self, state: Any) -> Any:
            return super().visible_choices(state)[:-1]

    monkeypatch.setattr(checks, "StoryEngine", _Drifted)
    book = Storybook.model_validate(_pair()[0])
    with pytest.raises(RuntimeError, match="disagree"):
        build_config_graph(book)


# ---------------------------------------------------------------------------
# SP-0 binding
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sp0_unbound_plan_names_the_hash_to_set() -> None:
    book, plan = _pair()
    plan["provenance"]["shape_hash"] = None
    [finding] = _findings(_check(book, plan), "SP-0")
    assert shape_hash(Storybook.model_validate(book)) in finding.message


@pytest.mark.unit
def test_sp0_band_mismatch() -> None:
    book, plan = _pair()
    plan["request"]["band"] = "10-13"
    [finding] = _findings(_check(book, plan), "SP-0")
    assert "'10-13' differs" in finding.message


@pytest.mark.unit
def test_sp0_a_prose_edit_keeps_the_plan_bound() -> None:
    book, plan = _pair()
    _node(book, "n_fork")["body"] = "A rewritten passage."
    assert _check(book, plan).ok


# ---------------------------------------------------------------------------
# SP-1 coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sp1_reports_both_directions_for_nodes_and_choices() -> None:
    book, plan = _pair()
    del plan["nodes"]["n_cave"]["establishes"]
    plan["nodes"]["n_extra"] = {"function": "f", "event": "e"}
    plan["choices"]["c_extra"] = {"intent": "i", "cost": "c"}
    del plan["nodes"]["n_path"]
    messages = {f.message for f in _findings(_check(book, plan), "SP-1")}
    assert "book node 'n_path' has no plan entry" in messages
    assert "plan node 'n_extra' is not in the book" in messages
    assert "plan choice 'c_extra' is not in the book" in messages


@pytest.mark.unit
def test_sp1_skips_graph_rules_but_still_floors_text() -> None:
    book, plan = _pair()
    del plan["choices"]["c_road"]
    plan["nodes"]["n_home"]["requires"].append("map_marks_cave")  # an SP-2 defect
    plan["facts"]["cave_drawing"]["text"] = "a {HERO} token"  # an SP-9 defect
    rules = {f.rule_id for f in _check(book, plan).errors}
    assert rules == {"SP-1", "SP-9"}


@pytest.mark.unit
def test_sp1_ending_entry_on_a_non_ending_node() -> None:
    book, plan = _pair()
    plan["endings"]["n_path"] = {"gift": "a laugh"}
    [finding] = _findings(_check(book, plan), "SP-1")
    assert finding.node_id == "n_path"
    assert "not an ending node" in finding.message


@pytest.mark.unit
def test_sp1_thread_variable_must_be_declared_and_every_variable_threaded() -> None:
    book, plan = _pair()
    plan["threads"]["t_lamp"]["variable"] = "has_torch"
    messages = {f.message for f in _findings(_check(book, plan), "SP-1")}
    assert "book variable 'has_lamp' has no thread" in messages
    assert any("names variable 'has_torch'" in m for m in messages)


@pytest.mark.unit
def test_sp1_planted_by_must_equal_the_choices_that_set_the_variable() -> None:
    book, plan = _pair()
    _node(book, "n_start")["choices"][1]["effects"] = [
        {"op": "set", "var": "has_map", "value": True}
    ]
    _rebind(book, plan)
    [finding] = _findings(_check(book, plan), "SP-1")
    assert finding.choice_id == "c_skip_map"
    assert "planted_by omits it" in finding.message

    book, plan = _pair()
    _node(book, "n_start")["choices"][0]["effects"] = []
    _rebind(book, plan)
    messages = [f.message for f in _findings(_check(book, plan), "SP-1")]
    assert any("does not set 'has_map'" in m for m in messages)


@pytest.mark.unit
def test_sp1_resetting_to_initial_is_not_a_plant() -> None:
    book, plan = _pair()
    _node(book, "n_start")["choices"][1]["effects"] = [
        {"op": "set", "var": "has_map", "value": False}
    ]
    _rebind(book, plan)
    assert _check(book, plan).ok


@pytest.mark.unit
def test_sp1_an_on_enter_plant_is_a_warning() -> None:
    book, plan = _pair()
    _node(book, "n_cave")["on_enter"] = [
        {"op": "set", "var": "has_lamp", "value": True}
    ]
    _rebind(book, plan)
    report = _check(book, plan)
    [warning] = report.warnings
    assert warning.rule_id == "SP-1"
    assert warning.node_id == "n_cave"
    assert "SP-1" not in {f.rule_id for f in report.errors}


# ---------------------------------------------------------------------------
# SP-2 merge closure
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sp2_names_node_state_fact_and_a_real_route() -> None:
    book, plan = WITNESSES[2].build()
    [finding] = _findings(_check(cast("Any", book), cast("Any", plan)), "SP-2")
    assert finding.node_id == "n_home"
    assert finding.fact_id == "map_marks_cave"
    assert finding.state is not None
    assert "has_map=false" in finding.state
    assert finding.route is not None
    route = finding.route.split(" > ")
    assert route[0] == "n_start"
    assert route[-1] == "n_home"
    assert "c_take_map" not in route
    assert "2 of 4 reachable states" in finding.message


@pytest.mark.unit
def test_sp2_is_state_aware_a_gated_node_has_its_plant() -> None:
    # The clean example already relies on this: n_cave requires the map's plant
    # and is reached only with has_map true. A node-level analysis would flag it.
    book, plan = _pair()
    assert plan["nodes"]["n_cave"]["requires"] == ["map_marks_cave"]
    assert not _findings(_check(book, plan), "SP-2")


@pytest.mark.unit
def test_sp2_a_fact_from_one_branch_only_fails_at_the_merge() -> None:
    book, plan = _pair()
    plan["nodes"]["n_cave"]["establishes"] = ["cave_drawing"]
    plan["nodes"]["n_home"]["requires"] = ["well_seen", "cave_drawing"]
    [finding] = _findings(_check(book, plan), "SP-2")
    assert finding.node_id == "n_home"
    assert finding.fact_id == "cave_drawing"


@pytest.mark.unit
def test_sp2_the_start_node_enters_with_nothing() -> None:
    book, plan = _pair()
    plan["nodes"]["n_start"]["requires"] = ["well_seen"]
    [finding] = _findings(_check(book, plan), "SP-2")
    assert finding.node_id == "n_start"
    assert finding.route == "n_start"


# ---------------------------------------------------------------------------
# SP-3 single truth
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sp3_blames_the_non_truth_side_of_a_contradiction() -> None:
    book, plan = WITNESSES[3].build()
    [finding] = _findings(_check(cast("Any", book), cast("Any", plan)), "SP-3")
    assert finding.fact_id == "stranger_left_map"
    assert finding.node_id == "n_fall"
    assert "grandpa_left_map' (at n_home)" in finding.message


@pytest.mark.unit
def test_sp3_contradicting_non_truth_facts_on_separate_routes() -> None:
    book, plan = _pair()
    plan["facts"]["cave_drawing"]["contradicts"] = ["lamp_lit"]
    plan["nodes"]["n_cave"]["establishes"] = ["cave_drawing"]
    findings = _findings(_check(book, plan), "SP-3")
    assert len(findings) == 1
    assert "c_take_lamp" in findings[0].message  # the plant is a choice site


@pytest.mark.unit
def test_sp3_a_truth_fact_nobody_establishes() -> None:
    book, plan = _pair()
    plan["nodes"]["n_home"]["establishes"] = []
    [finding] = _findings(_check(book, plan), "SP-3")
    assert finding.fact_id == "grandpa_left_map"
    assert "no reachable route" in finding.message


@pytest.mark.unit
def test_sp3_an_unreachable_node_is_not_a_site() -> None:
    book, plan = _pair()
    _node(book, "n_fork")["choices"][3]["condition"] = {
        "and": [
            {"==": [{"var": "has_map"}, True]},
            {"==": [{"var": "has_map"}, False]},
        ]
    }
    _rebind(book, plan)
    plan["nodes"]["n_fall"]["establishes"] = ["stranger_left_map"]
    assert not _findings(_check(book, plan), "SP-3")


# ---------------------------------------------------------------------------
# SP-4 plant exclusivity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sp4_public_plant_has_route_skipping_the_planting_choice() -> None:
    book, plan = WITNESSES[4].build()
    [finding] = _findings(_check(cast("Any", book), cast("Any", plan)), "SP-4")
    assert finding.node_id == "n_path"
    assert finding.fact_id == "map_marks_cave"
    assert finding.route == "n_start > c_skip_map > n_path"


@pytest.mark.unit
def test_sp4_a_node_only_reached_through_the_plant_may_restate_it() -> None:
    book, plan = _pair()
    plan["nodes"]["n_cave"]["establishes"] = ["cave_drawing", "map_marks_cave"]
    assert not _findings(_check(book, plan), "SP-4")


# ---------------------------------------------------------------------------
# SP-5 payoff reach
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sp5_site_never_reached_without_the_plant() -> None:
    book, plan = WITNESSES[5].build()
    [finding] = _findings(_check(cast("Any", book), cast("Any", plan)), "SP-5")
    assert finding.node_id == "n_cave"
    assert "without the plant" in finding.message


@pytest.mark.unit
def test_sp5_site_never_reached_with_the_plant_and_node_never_planted() -> None:
    book, plan = _pair()
    plan["threads"]["t_map"]["payoffs"] = [
        {"site": "n_start", "node": "n_start", "shows": "nothing yet"}
    ]
    messages = [f.message for f in _findings(_check(book, plan), "SP-5")]
    assert any("site 'n_start'" in m and "with the plant" in m for m in messages)
    assert any("node 'n_start'" in m for m in messages)


# ---------------------------------------------------------------------------
# SP-6 payoff independence
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sp6_leaning_on_another_plant_fails_even_when_gated() -> None:
    book, plan = WITNESSES[6].build()
    report = _check(cast("Any", book), cast("Any", plan))
    assert not _findings(report, "SP-2")  # state-wise it is guaranteed
    [finding] = _findings(report, "SP-6")
    assert finding.node_id == "n_tunnel"
    assert finding.fact_id == "map_marks_cave"


@pytest.mark.unit
def test_sp6_leaning_on_another_payoff_scene_fails() -> None:
    book, plan = _pair()
    # Gate the tunnel behind the cave so cave_drawing is guaranteed state-wise.
    _node(book, "n_cave")["choices"] = [
        {"id": "c_cave_on", "label": "On.", "target": "n_tunnel"}
    ]
    _node(book, "n_fork")["choices"][1]["condition"] = {"==": [{"var": "has_map"}, 2]}
    _rebind(book, plan)
    plan["nodes"]["n_tunnel"]["requires"] = ["cave_drawing"]
    report = _check(book, plan)
    assert not _findings(report, "SP-2")
    sp6 = _findings(report, "SP-6")
    assert [f.fact_id for f in sp6] == ["cave_drawing"]


@pytest.mark.unit
def test_sp6_own_plant_and_shared_facts_are_allowed() -> None:
    book, plan = _pair()
    plan["nodes"]["n_tunnel"]["requires"] = ["lamp_lit", "well_seen"]
    assert not _findings(_check(book, plan), "SP-6")


# ---------------------------------------------------------------------------
# SP-7, SP-8
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sp7_negative_ending_without_gift() -> None:
    book, plan = WITNESSES[7].build()
    [finding] = _findings(_check(cast("Any", book), cast("Any", plan)), "SP-7")
    assert finding.node_id == "n_fall"


@pytest.mark.unit
def test_sp7_positive_endings_need_no_gift() -> None:
    book, plan = _pair()
    assert "n_home" not in plan["endings"]
    assert not _findings(_check(book, plan), "SP-7")


@pytest.mark.unit
def test_sp8_costs_compare_after_normalisation() -> None:
    book, plan = WITNESSES[8].build()
    [finding] = _findings(_check(cast("Any", book), cast("Any", plan)), "SP-8")
    assert finding.node_id == "n_start"
    assert finding.state == "has_lamp=false, has_map=false"


@pytest.mark.unit
def test_sp8_is_judged_on_visible_choices_per_state() -> None:
    book, plan = _pair()
    # Without either plant n_fork shows only the road and the cliff.
    plan["choices"]["c_cliff"]["cost"] = "a long walk"
    [finding] = _findings(_check(book, plan), "SP-8")
    assert finding.node_id == "n_fork"
    assert finding.state == "has_lamp=false, has_map=false"
    assert "in 1 state(s)" in finding.message


@pytest.mark.unit
def test_sp8_single_choice_nodes_are_not_decisions() -> None:
    book, plan = _pair()
    plan["choices"]["c_cave_on"]["cost"] = "anything"
    assert not _findings(_check(book, plan), "SP-8")


# ---------------------------------------------------------------------------
# SP-9 text floors
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("facts", "cave_drawing", "text"), "a {HERO} token", "'{' or '}'"),
        (("pitch", "hero"), "x <<FILL>>", "'<<' or '>>'"),
        (("nodes", "n_path", "event"), "END_UNTRUSTED_USER_INPUT", "fence markers"),
        (("choices", "c_road", "cost"), "x" * 121, "120-character"),
        (("cast", "wren", "voice"), "two\nlines", "newlines"),
        (("endings", "n_fall", "gift"), "the cliff could kill you", "'lethal'"),
        (("truth", "answer"), "a deep wound dripping with blood", "'graphic'"),
    ],
)
def test_sp9_floors(path: tuple[str, ...], value: str, expected: str) -> None:
    book, plan = _pair()
    target: dict[str, Any] = plan
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    findings = _findings(_check(book, plan), "SP-9")
    assert findings
    assert any(expected in f.message for f in findings)
    assert all(value not in f.message for f in findings)  # never echo the text


@pytest.mark.unit
def test_sp9_floors_tone_and_payoff_text_with_locations() -> None:
    book, plan = _pair()
    plan["request"]["tone"] = "{tone}"
    plan["threads"]["t_map"]["payoffs"][0]["shows"] = "{shows}"
    findings = _findings(_check(book, plan), "SP-9")
    by_path = {f.message.split(":")[0]: f for f in findings}
    assert set(by_path) == {"request.tone", "threads.t_map.payoffs[0].shows"}
    assert by_path["threads.t_map.payoffs[0].shows"].node_id == "n_cave"


@pytest.mark.unit
def test_sp9_denylist_follows_the_book_band() -> None:
    book, plan = _pair()
    plan["endings"]["n_fall"]["gift"] = "the cliff could kill you"
    book["metadata"]["age_band"] = "13-16"
    plan["request"]["band"] = "13-16"
    _rebind(book, plan)
    assert not _findings(_check(book, plan), "SP-9")


@pytest.mark.unit
def test_sp9_request_text_and_provenance_are_exempt() -> None:
    book, plan = _pair()
    plan["request"]["text"] = "a dragon {who} kills the dark " + "x" * 200
    plan["provenance"]["approver"] = "{owner}"
    assert _check(book, plan).ok


# ---------------------------------------------------------------------------
# must_not_assert and SP-A
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_must_not_assert_is_the_union_over_states() -> None:
    book, plan = _pair()
    mna = must_not_assert(
        StoryPlan.model_validate(plan), Storybook.model_validate(book)
    )
    assert "well_seen" not in mna["n_fork"]
    assert {"map_marks_cave", "lamp_lit", "grandpa_left_map"} <= mna["n_fork"]
    assert "map_marks_cave" not in mna["n_cave"]
    assert "cave_drawing" not in mna["n_cave"]  # it establishes it
    assert "grandpa_left_map" not in mna["n_home"]
    assert list(mna) == [n["id"] for n in book["nodes"]]


@pytest.mark.unit
def test_check_assertions_flags_a_leak_with_route() -> None:
    book, plan = _pair()
    report = check_assertions(
        StoryPlan.model_validate(plan),
        Storybook.model_validate(book),
        {"n_home": ["well_seen", "lamp_lit"], "n_tunnel": ["lamp_lit"]},
    )
    [finding] = cast("list[PlanFinding]", report.findings)
    assert finding.rule_id == ASSERT_RULE
    assert finding.node_id == "n_home"
    assert finding.fact_id == "lamp_lit"
    assert finding.route is not None
    assert "c_take_lamp" not in finding.route


@pytest.mark.unit
def test_check_assertions_rejects_unknown_ids() -> None:
    book, plan = _pair()
    report = check_assertions(
        StoryPlan.model_validate(plan),
        Storybook.model_validate(book),
        {"n_ghost": ["well_seen"], "n_home": ["ghost"]},
    )
    messages = [f.message for f in report.findings]
    assert "assertions name unknown node 'n_ghost'" in messages
    assert "assertions for 'n_home' name undeclared fact 'ghost'" in messages


@pytest.mark.unit
def test_plan_finding_wire_format_adds_plan_keys() -> None:
    finding = PlanFinding(
        rule_id="SP-2",
        severity=Severity.ERROR,
        story_id="s",
        message="m",
        node_id="n",
        state="x=true",
        fact_id="f",
        route="a > c > n",
    )
    assert finding.to_dict() == {
        "rule_id": "SP-2",
        "severity": "error",
        "story_id": "s",
        "node_id": "n",
        "choice_id": None,
        "message": "m",
        "state": "x=true",
        "fact_id": "f",
        "route": "a > c > n",
    }


# ---------------------------------------------------------------------------
# Performance on a book the size of the family-test books
# ---------------------------------------------------------------------------


# Payoff sites in the committed Hollow Lighthouse, per variable: a node reached
# with and without the plant, and the passage only planted readers reach.
_LIGHTHOUSE_PAYOFFS = {
    "knows_tunnel": ("n_tunnel", "tn_cut"),
    "knows_code": ("cm_cottage", "cm_cottage_light"),
    "has_key": ("cm_light_relight", "cm_light_true"),
    "knows_ledger": ("cm_smug_follow", "e_win_ledger"),
}


@pytest.mark.unit
def test_runs_well_under_ten_seconds_on_a_family_test_book() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "out"
        / "the-hollow-lighthouse.filled.json"
    )
    book = Storybook.model_validate(json.loads(path.read_text(encoding="utf-8")))
    plan = _covering_plan(book)
    started = time.perf_counter()
    report = check_plan(plan, book)
    must_not_assert(plan, book)
    assert time.perf_counter() - started < 10
    assert report.ok, [f.to_dict() for f in report.errors]


def _covering_plan(book: Storybook) -> StoryPlan:
    """Build a structurally clean plan for the Hollow Lighthouse.

    Args:
        book: The book.

    Returns:
        StoryPlan: A plan with one thread per variable and distinct costs.
    """
    setters: dict[str, list[str]] = {}
    for node in book.nodes:
        for choice in node.choices:
            for effect in choice.effects:
                setters.setdefault(effect.var, []).append(choice.id)
    plants: dict[str, list[str]] = {}
    for var, choice_ids in setters.items():
        for choice_id in choice_ids:
            plants.setdefault(choice_id, []).append(f"t_{var}")
    first = book.start_node
    facts: dict[str, Any] = {"truth": {"text": "The keeper set the lamp."}}
    facts |= {f"f_{v.name}": {"text": "A plant."} for v in book.variables}
    doc: dict[str, Any] = {
        "request": {"band": book.metadata.age_band.value},
        "pitch": dict.fromkeys(
            ("hero", "want", "obstacle", "stake", "ending_kind"), "x"
        ),
        "cast": {"hero": {"name": "Hero", "role": "r", "want": "w", "voice": "v"}},
        "truth": {"question": "q", "answer": "a", "facts": ["truth"]},
        "facts": facts,
        "nodes": {n.id: {"function": "f", "event": "e"} for n in book.nodes},
        "choices": {
            c.id: {"intent": "i", "cost": f"cost {i}", "plants": plants.get(c.id, [])}
            for n in book.nodes
            for i, c in enumerate(n.choices)
        },
        "threads": {
            f"t_{v.name}": {
                "variable": v.name,
                "planted_fact": f"f_{v.name}",
                "planted_by": setters[v.name],
                "payoffs": [
                    {
                        "site": _LIGHTHOUSE_PAYOFFS[v.name][0],
                        "node": _LIGHTHOUSE_PAYOFFS[v.name][1],
                        "shows": "s",
                    }
                ],
            }
            for v in book.variables
        },
        "endings": {n.id: {"gift": "g"} for n in book.nodes if n.ending is not None},
        "provenance": {
            "producer": "test",
            "shape_id": book.id,
            "shape_hash": shape_hash(book),
        },
    }
    doc["nodes"][first]["establishes"] = ["truth"]
    return StoryPlan.model_validate(doc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write_pair(
    tmp_path: Path, book: dict[str, Any], plan: dict[str, Any]
) -> tuple[Path, Path]:
    """Write a pair under the conventional names.

    Args:
        tmp_path: The directory.
        book: The book document.
        plan: The plan document.

    Returns:
        tuple[Path, Path]: The book and plan paths.
    """
    book_path = tmp_path / "demo.filled.json"
    plan_path = tmp_path / "demo.plan.json"
    book_path.write_text(json.dumps(book), encoding="utf-8")
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return book_path, plan_path


@pytest.mark.unit
def test_default_plan_path() -> None:
    assert default_plan_path(Path("out/x.filled.json")) == Path("out/x.plan.json")
    assert default_plan_path(Path("out/x.json")) == Path("out/x.plan.json")
    assert default_plan_path(Path("out/x")) == Path("out/x.plan.json")


@pytest.mark.unit
def test_cli_clean_pair_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    book_path, _ = _write_pair(tmp_path, *_pair())
    assert main([str(book_path)]) == 0
    out = capsys.readouterr().out
    assert "plan for s_plan_witness by witness (not approved)" in out
    assert "ok: 0 error(s), 0 warning(s)" in out


@pytest.mark.unit
def test_cli_reports_node_state_fact_and_route(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    book, plan = WITNESSES[2].build()
    book_path, plan_path = _write_pair(tmp_path, cast("Any", book), cast("Any", plan))
    assert main([str(book_path), str(plan_path)]) == 1
    out = capsys.readouterr().out
    assert "ERROR SP-2 node_id=n_home fact_id=map_marks_cave state=[" in out
    assert "route: n_start > c_skip_map" in out


@pytest.mark.unit
def test_cli_json_with_must_not_assert_and_assertions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    book_path, plan_path = _write_pair(tmp_path, *_pair())
    assertions = tmp_path / "assertions.json"
    assertions.write_text(json.dumps({"n_home": ["lamp_lit"]}), encoding="utf-8")
    code = main(
        [
            str(book_path),
            str(plan_path),
            "--json",
            "--must-not-assert",
            "--assertions",
            str(assertions),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["ok"] is False
    assert payload["findings"][0]["rule_id"] == ASSERT_RULE
    assert payload["shape_hash"].startswith("sha256:")
    assert payload["plan"] == {
        "shape_id": "s_plan_witness",
        "producer": "witness",
        "approver": None,
    }
    assert "lamp_lit" in payload["must_not_assert"]["n_home"]


@pytest.mark.unit
def test_cli_text_must_not_assert(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    book_path, _ = _write_pair(tmp_path, *_pair())
    assert main([str(book_path), "--must-not-assert"]) == 0
    assert "MUST_NOT_ASSERT n_cave: " in capsys.readouterr().out


@pytest.mark.unit
def test_cli_shape_hash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    book, _ = _pair()
    book_path, _ = _write_pair(tmp_path, *_pair())
    assert main([str(book_path), "--shape-hash"]) == 0
    expected = shape_hash(Storybook.model_validate(book))
    assert capsys.readouterr().out.strip() == f"s_plan_witness {expected}"


@pytest.mark.unit
def test_cli_verify_witnesses(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--verify-witnesses"]) == 0
    assert "every SP rule fires" in capsys.readouterr().out


@pytest.mark.unit
def test_cli_verify_witnesses_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import scripts.check_story_plan as cli

    monkeypatch.setattr(cli, "verify_witnesses", lambda: ["SP-9: broken"])
    assert main(["--verify-witnesses"]) == 1
    assert "FAIL SP-9: broken" in capsys.readouterr().err


@pytest.mark.unit
def test_cli_schema_failure_lists_locations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    book, plan = _pair()
    plan["nodes"]["n_path"]["requires"].append("ghost")
    book_path, _ = _write_pair(tmp_path, book, plan)
    assert main([str(book_path)]) == 1
    assert "SCHEMA $: Value error" in capsys.readouterr().err


@pytest.mark.unit
def test_cli_unreadable_inputs_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.filled.json"
    assert main([str(missing)]) == 2
    bad_book = tmp_path / "bad.filled.json"
    bad_book.write_text(json.dumps({"id": "x"}), encoding="utf-8")
    assert main([str(bad_book)]) == 2
    book_path = tmp_path / "solo.filled.json"
    book_path.write_text(json.dumps(_pair()[0]), encoding="utf-8")
    assert main([str(book_path)]) == 2  # no plan beside it
    book_path, _ = _write_pair(tmp_path, *_pair())
    bad_assertions = tmp_path / "a.json"
    bad_assertions.write_text("[]", encoding="utf-8")
    assert main([str(book_path), "--assertions", str(bad_assertions)]) == 2
    bad_assertions.write_text(json.dumps({"n_home": "lamp_lit"}), encoding="utf-8")
    assert main([str(book_path), "--assertions", str(bad_assertions)]) == 2
    err = capsys.readouterr().err
    assert "cannot load" in err
    assert "not a valid Storybook" in err
    assert "must map to a list of ids" in err


@pytest.mark.unit
def test_cli_requires_a_book(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main([])
    assert caught.value.code == 2
    assert "a book path is required" in capsys.readouterr().err


@pytest.mark.unit
def test_a_stateless_book_reports_no_variables_state() -> None:
    book, plan = _pair()
    book["variables"] = []
    book["metadata"]["tier"] = 1
    for node in book["nodes"]:
        for choice in node.get("choices", []):
            choice.pop("effects", None)
            choice.pop("condition", None)
    _rebind(book, plan)
    plan["threads"] = {}
    for choice in plan["choices"].values():
        choice.pop("plants", None)
    plan["nodes"]["n_cave"]["requires"] = []
    plan["nodes"]["n_tunnel"]["requires"] = ["well_seen", "cave_drawing"]
    [finding] = _findings(_check(book, plan), "SP-2")
    assert finding.state == "(no variables)"


@pytest.mark.unit
def test_an_int_counter_increment_is_a_plant() -> None:
    book, plan = _pair()
    book["variables"][0] = {"name": "has_map", "type": "int", "initial": 0}
    _node(book, "n_start")["choices"][0]["effects"] = [
        {"op": "inc", "var": "has_map", "value": 1}
    ]
    _node(book, "n_fork")["choices"][0]["condition"] = {">=": [{"var": "has_map"}, 1]}
    _rebind(book, plan)
    report = _check(book, plan)
    assert report.ok, [f.to_dict() for f in report.errors]
