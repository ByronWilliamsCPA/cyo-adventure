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
from cyo_adventure.storyplan.models import book_sha256, shape_hash
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
    parsed = Storybook.model_validate(book)
    plan["provenance"]["shape"] = {"id": parsed.id, "hash": shape_hash(parsed)}


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
    plan["provenance"]["shape"] = None
    [finding] = _findings(_check(book, plan), "SP-0")
    assert shape_hash(Storybook.model_validate(book)) in finding.message


@pytest.mark.unit
def test_sp0_book_sha256_binding_is_verified_when_bytes_are_given() -> None:
    book, plan = _pair()
    plan["provenance"]["shape"] = None
    plan["provenance"]["book_sha256"] = "a" * 64
    parsed_plan = StoryPlan.model_validate(plan)
    parsed_book = Storybook.model_validate(book)
    assert check_plan(parsed_plan, parsed_book, book_digest="a" * 64).findings == []
    stale = check_plan(parsed_plan, parsed_book, book_digest="b" * 64)
    [finding] = _findings(stale, "SP-0")
    assert "the book changed after the plan was written" in finding.message
    unverified = check_plan(parsed_plan, parsed_book)
    assert unverified.ok
    [warning] = unverified.warnings
    assert "not verified" in warning.message


@pytest.mark.unit
def test_sp0_book_block_must_name_this_book() -> None:
    book, plan = _pair()
    plan["book"] = {
        "slug": "x",
        "storybook_id": "s_other",
        "storybook_version": 2,
        "title": "X",
    }
    messages = {f.message for f in _findings(_check(book, plan), "SP-0")}
    assert (
        "book.storybook_id 's_other' is not the book's id 's_plan_witness'" in messages
    )
    assert "book.storybook_version 2 is not the book's version 1" in messages


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
def test_sp1_planting_choices_must_equal_the_choices_that_set_the_variable() -> None:
    book, plan = _pair()
    _node(book, "n_start")["choices"][1]["effects"] = [
        {"op": "set", "var": "has_map", "value": True}
    ]
    _rebind(book, plan)
    [finding] = _findings(_check(book, plan), "SP-1")
    assert finding.choice_id == "c_skip_map"
    assert "planting_choices omit it" in finding.message

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
def test_sp1_declared_ending_valence_and_kind_must_match_the_book() -> None:
    book, plan = _pair()
    plan["endings"]["n_fall"].update(valence="negative", kind="setback")
    plan["endings"]["n_home"] = {"gift": "g", "valence": "positive", "kind": "success"}
    assert _check(book, plan).ok
    plan["endings"]["n_fall"].update(valence="neutral", kind="capture")
    messages = {f.message for f in _findings(_check(book, plan), "SP-1")}
    assert (
        "endings.n_fall.valence 'neutral' differs from the book's 'negative'"
        in messages
    )
    assert "endings.n_fall.kind 'capture' differs from the book's 'setback'" in messages


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
def test_sp2_choice_requires_is_checked_only_where_the_choice_is_visible() -> None:
    book, plan = _pair()
    plan["choices"]["c_cave"]["requires"] = ["map_marks_cave"]  # gated: fine
    plan["choices"]["c_skip_lamp"]["requires"] = ["well_seen"]  # known on entry
    plan["choices"]["c_take_map"]["requires"] = ["well_seen"]  # its node adds it
    assert not _findings(_check(book, plan), "SP-2")
    plan["choices"]["c_road"]["requires"] = ["map_marks_cave"]
    [finding] = _findings(_check(book, plan), "SP-2")
    assert finding.choice_id == "c_road"
    assert finding.node_id == "n_fork"
    assert finding.state is not None
    assert "has_map=false" in finding.state
    assert "2 of 4 states offering it" in finding.message


@pytest.mark.unit
def test_sp2_a_choice_establishes_on_entry_to_its_target() -> None:
    book, plan = _pair()
    plan["facts"]["cliff_edge"] = {"text": "The cliff path crumbles at the edge."}
    plan["choices"]["c_cliff"]["establishes"] = ["cliff_edge"]
    plan["nodes"]["n_fall"]["requires"] = ["cliff_edge"]
    assert not _findings(_check(book, plan), "SP-2")
    plan["nodes"]["n_home"]["requires"] = ["well_seen", "cliff_edge"]
    [finding] = _findings(_check(book, plan), "SP-2")
    assert finding.node_id == "n_home"


@pytest.mark.unit
def test_sp2_a_node_may_require_and_establish_so_defects_do_not_cascade() -> None:
    book, plan = _pair()
    plan["nodes"]["n_fork"]["requires"] = ["cave_drawing"]
    plan["nodes"]["n_fork"]["establishes"] = ["cave_drawing"]
    plan["nodes"]["n_home"]["requires"] = ["well_seen", "cave_drawing"]
    findings = _findings(_check(book, plan), "SP-2")
    assert [f.node_id for f in findings] == ["n_fork"]


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
def test_sp3_one_reading_meeting_both_sides_via_a_plant_is_an_error() -> None:
    # The Lighthouse B2 shape: a passage says "no lamp" to a reader whose
    # choice planted the lamp.
    book, plan = _pair()
    plan["facts"]["cave_drawing"]["contradicts"] = ["lamp_lit"]
    [finding] = _findings(_check(book, plan), "SP-3")
    assert finding.severity is Severity.ERROR
    assert "one reading meets both" in finding.message
    assert "c_take_lamp" in finding.message  # the plant is a choice site
    assert finding.node_id == "n_cave"
    assert finding.state == "has_lamp=true, has_map=true"
    assert finding.route is not None
    assert "c_take_lamp" in finding.route.split(" > ")


@pytest.mark.unit
def test_sp3_exclusive_routes_without_truth_is_a_warning() -> None:
    # The Museum cipher shape: two versions of one detail on routes no single
    # reading crosses.
    book, plan = _pair()
    plan["facts"]["tunnel_drawing"] = {
        "text": "The tunnel wall shows a drawing of an owl.",
        "contradicts": ["cave_drawing"],
    }
    plan["nodes"]["n_tunnel"]["establishes"] = ["tunnel_drawing"]
    report = _check(book, plan)
    assert report.ok
    [finding] = _findings(report, "SP-3")
    assert finding.severity is Severity.WARNING
    assert "replay inconsistency" in finding.message


@pytest.mark.unit
def test_sp3_exclusive_routes_splitting_the_truth_is_an_error() -> None:
    book, plan = WITNESSES[3].build()
    [finding] = _findings(_check(cast("Any", book), cast("Any", plan)), "SP-3")
    assert finding.severity is Severity.ERROR
    assert "answers its question two ways" in finding.message


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
def test_sp4_a_non_planting_choice_establishing_the_plant_leaks_it() -> None:
    book, plan = _pair()
    plan["choices"]["c_skip_map"]["establishes"] = ["map_marks_cave"]
    [finding] = _findings(_check(book, plan), "SP-4")
    assert finding.node_id == "n_path"
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
def test_sp5_site_never_reached_with_the_plant() -> None:
    book, plan = _pair()
    plan["threads"]["t_map"]["payoff_sites"] = [
        {"node": "n_start", "choice": "c_take_map", "shows": "nothing yet"}
    ]
    [finding] = _findings(_check(book, plan), "SP-5")
    assert "site 'n_start'" in finding.message
    assert "reached with the plant" in finding.message


@pytest.mark.unit
def test_sp5_payoff_choice_never_offered() -> None:
    book, plan = _pair()
    _node(book, "n_fork")["choices"][0]["condition"] = {
        "and": [
            {"==": [{"var": "has_map"}, True]},
            {"==": [{"var": "has_map"}, False]},
        ]
    }
    _rebind(book, plan)
    [finding] = _findings(_check(book, plan), "SP-5")
    assert finding.choice_id == "c_cave"
    assert "never offered" in finding.message


@pytest.mark.unit
def test_sp1_payoff_choice_must_belong_to_its_site() -> None:
    book, plan = _pair()
    plan["threads"]["t_map"]["payoff_sites"][0]["choice"] = "c_road_x"
    plan["choices"]["c_road_x"] = {"intent": "i", "cost": "c"}
    rules = {f.message for f in _findings(_check(book, plan), "SP-1")}
    assert (
        "threads.t_map.payoff_sites[0].choice 'c_road_x' is not a choice of 'n_fork'"
        in rules
    )


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
def test_sp6_checks_the_payoff_choice_requires_too() -> None:
    book, plan = WITNESSES[6].build()
    plan = cast("dict[str, Any]", plan)
    plan["nodes"]["n_tunnel"]["requires"] = ["lamp_lit"]
    plan["choices"]["c_tunnel"]["requires"] = ["map_marks_cave"]
    report = _check(cast("Any", book), plan)
    assert not _findings(report, "SP-2")
    [finding] = _findings(report, "SP-6")
    assert finding.choice_id == "c_tunnel"
    assert finding.node_id == "n_fork"


@pytest.mark.unit
def test_sp6_leaning_on_another_payoff_scene_fails() -> None:
    book, plan = _pair()
    # Move the lamp's payoff into the map's payoff passage, so every reader
    # who reaches the tunnel has seen the cave drawing: SP-2 is satisfied,
    # but the lamp payoff now leans on what the map payoff showed.
    fork = _node(book, "n_fork")
    fork["choices"] = [c for c in fork["choices"] if c["id"] != "c_tunnel"]
    _node(book, "n_cave")["choices"].append(
        {
            "id": "c_tunnel2",
            "label": "Light the tunnel.",
            "target": "n_tunnel",
            "condition": {"==": [{"var": "has_lamp"}, True]},
        }
    )
    _rebind(book, plan)
    plan["choices"]["c_tunnel2"] = plan["choices"].pop("c_tunnel")
    plan["choices"]["c_cave_on"]["cost"] = "an early night"
    plan["threads"]["t_lamp"]["payoff_sites"] = [
        {"node": "n_cave", "choice": "c_tunnel2", "shows": "The lamp opens a tunnel."}
    ]
    plan["nodes"]["n_cave"]["establishes"] = ["cave_drawing"]
    plan["nodes"]["n_tunnel"]["requires"] = ["lamp_lit", "cave_drawing"]
    report = _check(book, plan)
    assert not report.findings or {f.rule_id for f in report.errors} == {"SP-6"}
    [finding] = _findings(report, "SP-6")
    assert finding.fact_id == "cave_drawing"
    assert finding.node_id == "n_tunnel"


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
        (("truth", "statement"), "x" * 601, "600-character"),
        (("cast", "wren", "voice"), "two\nlines", "newlines"),
        (("endings", "n_fall", "gift"), "the cliff could kill you", "'lethal'"),
        (("truth", "statement"), "a deep wound dripping with blood", "'graphic'"),
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
@pytest.mark.parametrize(
    ("path", "length", "fails"),
    [
        (("facts", "cave_drawing", "text"), 200, False),
        (("facts", "cave_drawing", "text"), 250, True),
        (("nodes", "n_path", "event"), 240, False),
        (("nodes", "n_path", "event"), 241, True),
        (("pitch", "hero"), 120, False),
        (("pitch", "hero"), 130, True),
        (("truth", "statement"), 600, False),
        (("truth", "statement"), 601, True),
    ],
)
def test_sp9_length_caps_are_per_field(
    path: tuple[str, ...], length: int, fails: bool
) -> None:
    book, plan = _pair()
    target: dict[str, Any] = plan
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = "a" * length
    findings = [
        f
        for f in _findings(_check(book, plan), "SP-9")
        if "character limit" in f.message
    ]
    assert bool(findings) is fails


@pytest.mark.unit
def test_sp9_floors_tone_and_payoff_text_with_locations() -> None:
    book, plan = _pair()
    plan["request"]["tone"] = "{tone}"
    plan["threads"]["t_map"]["payoff_sites"][0]["shows"] = "{shows}"
    plan["truth"]["question"] = "{question}"
    findings = _findings(_check(book, plan), "SP-9")
    by_path = {f.message.split(":")[0]: f for f in findings}
    shows = "threads.t_map.payoff_sites[0].shows"
    assert set(by_path) == {"request.tone", shows, "truth.question"}
    assert by_path[shows].node_id == "n_fork"
    assert by_path[shows].choice_id == "c_cave"


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
    plan["request"]["note"] = "{note}"
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
# with and without the plant, and the choice only planted readers see.
_LIGHTHOUSE_PAYOFFS = {
    "knows_tunnel": ("n_tunnel", "c_n_tunnel_4"),
    "knows_code": ("cm_cottage", "c_cm_cottage_2"),
    "has_key": ("cm_light_relight", "c_cm_light_relight_1"),
    "knows_ledger": ("cm_smug_follow", "c_cm_smug_follow_3"),
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
        "truth": {"statement": "a", "facts": ["truth"]},
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
                "plant": f"f_{v.name}",
                "planting_choices": setters[v.name],
                "payoff_sites": [
                    {
                        "node": _LIGHTHOUSE_PAYOFFS[v.name][0],
                        "choice": _LIGHTHOUSE_PAYOFFS[v.name][1],
                        "shows": "s",
                    }
                ],
            }
            for v in book.variables
        },
        "endings": {n.id: {"gift": "g"} for n in book.nodes if n.ending is not None},
        "provenance": {
            "producer": "test",
            "shape": {"id": book.id, "hash": shape_hash(book)},
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
    assert "plan bound to shape s_plan_witness by witness (not approved)" in out
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
        "bound_to": "shape s_plan_witness",
        "producer": "witness",
        "approver": None,
        "book_file": None,
        "authored": None,
        "authoring_minutes": None,
        "implicit_plants": {},
    }
    assert "lamp_lit" in payload["must_not_assert"]["n_home"]


@pytest.mark.unit
def test_cli_json_reports_authoring_provenance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    book, plan = _pair()
    plan["provenance"].update(
        book_file="out/x.filled.json", authored="2026-11-21", authoring_minutes=11
    )
    plan["facts"]["well_seen"]["implicit_plant"] = "paid off at the fork"
    book_path, _ = _write_pair(tmp_path, book, plan)
    assert main([str(book_path), "--json"]) == 0
    block = json.loads(capsys.readouterr().out)["plan"]
    assert block["authored"] == "2026-11-21"
    assert block["authoring_minutes"] == 11
    assert block["implicit_plants"] == {"well_seen": "paid off at the fork"}


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
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"shape s_plan_witness {expected}"
    assert out[1] == f"book_sha256 {book_sha256(book_path.read_bytes())}"


@pytest.mark.unit
def test_cli_verifies_book_sha256_from_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    book, plan = _pair()
    book_path, plan_path = _write_pair(tmp_path, book, plan)
    plan["provenance"]["shape"] = None
    plan["provenance"]["book_sha256"] = book_sha256(book_path.read_bytes())
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    assert main([str(book_path)]) == 0
    assert "bound to book file" in capsys.readouterr().out
    book_path.write_text(
        json.dumps(book, indent=1), encoding="utf-8"
    )  # same graph, new bytes
    assert main([str(book_path)]) == 1
    assert "the book changed after the plan was written" in capsys.readouterr().out


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
