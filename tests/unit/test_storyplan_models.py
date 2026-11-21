"""Unit tests for the Story Plan schema v0 (ADR-033 Decision 1, WP-1.1).

The schema rejects at load what would otherwise surface as a KeyError or a
silently skipped obligation inside the checks: undeclared facts, unknown nodes
and choices, a one-sided plant, duplicates, and contradictions inside the
truth. Book-relative coverage (node ids, declared variables) is SP-1's job and
is tested in ``test_storyplan_checks.py``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storyplan import PLAN_VERSION, StoryPlan, is_supported_plan_version
from cyo_adventure.storyplan.checks import base_example
from cyo_adventure.storyplan.models import book_sha256, shape_hash, shape_projection
from cyo_adventure.storyplan.schema_export import build_schema, export_schema


def _plan() -> dict[str, Any]:
    """Return the clean example plan as a mutable dict.

    Returns:
        dict[str, Any]: A deep copy, safe to mutate.
    """
    return cast("dict[str, Any]", copy.deepcopy(base_example()[1]))


def _book() -> dict[str, Any]:
    """Return the clean example book as a mutable dict.

    Returns:
        dict[str, Any]: A deep copy, safe to mutate.
    """
    return cast("dict[str, Any]", copy.deepcopy(base_example()[0]))


def _rejection(plan: dict[str, Any]) -> str:
    """Validate ``plan`` expecting failure and return the error text.

    Args:
        plan: The plan document.

    Returns:
        str: The validation error message.
    """
    with pytest.raises(ValidationError) as caught:
        StoryPlan.model_validate(plan)
    return str(caught.value)


@pytest.mark.unit
def test_the_example_plan_validates_and_round_trips() -> None:
    plan = StoryPlan.model_validate(_plan())
    assert plan.plan_version == PLAN_VERSION
    again = StoryPlan.model_validate(plan.model_dump(mode="json"))
    assert again == plan


@pytest.mark.unit
def test_unknown_keys_are_rejected_at_every_level() -> None:
    plan = _plan()
    plan["nodes"]["n_start"]["must_not_assert"] = ["well_seen"]
    assert "must_not_assert" in _rejection(plan)
    plan = _plan()
    plan["surprise"] = 1
    assert "surprise" in _rejection(plan)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("section", "mutate"),
    [
        ("requires", lambda p: p["nodes"]["n_path"]["requires"].append("ghost")),
        ("establishes", lambda p: p["nodes"]["n_path"]["establishes"].append("ghost")),
        ("knows", lambda p: p["cast"]["wren"]["knows"].append("ghost")),
        ("truth", lambda p: p["truth"]["facts"].append("ghost")),
        (
            "contradicts",
            lambda p: p["facts"]["well_seen"].update(contradicts=["ghost"]),
        ),
        ("plant", lambda p: p["threads"]["t_map"].update(plant="ghost")),
        (
            "choice requires",
            lambda p: p["choices"]["c_road"].update(requires=["ghost"]),
        ),
    ],
)
def test_an_undeclared_fact_id_is_rejected(
    section: str,
    mutate: Any,
) -> None:
    plan = _plan()
    mutate(plan)
    message = _rejection(plan)
    assert "undeclared fact 'ghost'" in message, section


@pytest.mark.unit
def test_a_payoff_site_naming_an_unknown_node_or_choice_is_rejected() -> None:
    plan = _plan()
    plan["threads"]["t_map"]["payoff_sites"][0]["node"] = "n_nowhere"
    plan["threads"]["t_map"]["payoff_sites"][0]["choice"] = "c_nowhere"
    message = _rejection(plan)
    assert "node names unknown node 'n_nowhere'" in message
    assert "choice names unknown choice 'c_nowhere'" in message


@pytest.mark.unit
def test_an_ending_entry_for_an_unknown_node_is_rejected() -> None:
    plan = _plan()
    plan["endings"]["n_nowhere"] = {"gift": "a laugh"}
    assert "endings.n_nowhere is not a key of nodes" in _rejection(plan)


@pytest.mark.unit
def test_a_planting_choice_the_plan_lacks_is_rejected() -> None:
    plan = _plan()
    plan["threads"]["t_map"]["planting_choices"].append("c_nowhere")
    assert "unknown choice 'c_nowhere'" in _rejection(plan)


@pytest.mark.unit
def test_a_choice_planting_an_unknown_thread_is_rejected() -> None:
    plan = _plan()
    plan["choices"]["c_road"]["plants"] = ["t_ghost"]
    assert "unknown thread 't_ghost'" in _rejection(plan)


@pytest.mark.unit
def test_plants_and_planting_choices_must_agree_in_both_directions() -> None:
    plan = _plan()
    del plan["choices"]["c_take_map"]["plants"]
    assert "planting_choices lists 'c_take_map', whose plants omit" in _rejection(plan)
    plan = _plan()
    plan["choices"]["c_road"]["plants"] = ["t_map"]
    assert "choices.c_road.plants names 't_map', whose planting_choices" in _rejection(
        plan
    )


@pytest.mark.unit
def test_two_threads_may_not_share_a_variable_or_a_plant() -> None:
    plan = _plan()
    plan["threads"]["t_lamp"]["variable"] = "has_map"
    plan["threads"]["t_lamp"]["plant"] = "map_marks_cave"
    message = _rejection(plan)
    assert "more than one thread has variable 'has_map'" in message
    assert "more than one thread has plant 'map_marks_cave'" in message


@pytest.mark.unit
def test_duplicates_in_an_id_list_are_rejected() -> None:
    plan = _plan()
    plan["nodes"]["n_path"]["requires"] = ["well_seen", "well_seen"]
    assert "nodes.n_path.requires repeats 'well_seen'" in _rejection(plan)


@pytest.mark.unit
def test_contradiction_marks_are_symmetric_and_bounded() -> None:
    plan = _plan()
    plan["facts"]["well_seen"]["contradicts"] = ["well_seen"]
    assert "facts.well_seen contradicts itself" in _rejection(plan)
    plan = _plan()
    plan["truth"]["facts"] = ["grandpa_left_map", "stranger_left_map"]
    assert "are marked as contradicting" in _rejection(plan)
    parsed = StoryPlan.model_validate(_plan())
    assert parsed.contradiction_pairs() == {
        frozenset({"grandpa_left_map", "stranger_left_map"})
    }


@pytest.mark.unit
def test_every_problem_is_reported_in_one_pass() -> None:
    plan = _plan()
    plan["nodes"]["n_path"]["requires"].append("ghost")
    plan["endings"]["n_nowhere"] = {"gift": "a laugh"}
    message = _rejection(plan)
    assert "ghost" in message
    assert "n_nowhere" in message


@pytest.mark.unit
@pytest.mark.parametrize(
    ("version", "ok"),
    [("0.1", True), ("0.0", True), ("0.2", False), ("1.0", False), ("v0", False)],
)
def test_plan_version_gate(version: str, *, ok: bool) -> None:
    assert is_supported_plan_version(version) is ok
    plan = _plan()
    plan["plan_version"] = version
    if ok:
        StoryPlan.model_validate(plan)
    else:
        assert "unsupported plan_version" in _rejection(plan)


@pytest.mark.unit
def test_non_string_plan_version_is_unsupported() -> None:
    assert is_supported_plan_version(1) is False


@pytest.mark.unit
def test_ids_follow_the_variable_pattern_but_book_ids_do_not() -> None:
    plan = _plan()
    plan["facts"]["Bad-Id"] = {"text": "x"}
    assert "Bad-Id" in _rejection(plan)
    # Node ids are the book's, verbatim; any non-empty string is accepted.
    plan = _plan()
    plan["nodes"]["N-Odd.1"] = {"function": "f", "event": "e"}
    StoryPlan.model_validate(plan)


@pytest.mark.unit
def test_request_band_is_required_and_text_optional() -> None:
    plan = _plan()
    del plan["request"]["band"]
    assert "band" in _rejection(plan)
    plan = _plan()
    plan["request"]["text"] = "a dragon who is afraid of the dark"
    assert StoryPlan.model_validate(plan).request.text is not None


@pytest.mark.unit
def test_binding_hashes_must_be_well_formed() -> None:
    plan = _plan()
    plan["provenance"]["shape"]["hash"] = "md5:abc"
    plan["provenance"]["book_sha256"] = "sha256:abc"
    message = _rejection(plan)
    assert "shape.hash" in message
    assert "book_sha256" in message


@pytest.mark.unit
def test_plants_accepts_a_bare_thread_id() -> None:
    plan = _plan()
    plan["choices"]["c_take_map"]["plants"] = "t_map"
    parsed = StoryPlan.model_validate(plan)
    assert parsed.choices["c_take_map"].plants == ["t_map"]


@pytest.mark.unit
def test_the_wp03_plan_shape_is_accepted() -> None:
    """The fields the WP-0.3 plan writer chose where ADR-033 was silent."""
    plan = _plan()
    plan["book"] = {
        "slug": "plan-witness",
        "storybook_id": "s_plan_witness",
        "storybook_version": 1,
        "title": "Plan Witness",
    }
    plan["request"].update(text=None, note="hand-written catalog book")
    plan["provenance"].update(
        method="written by reading the book",
        book_file="out/plan-witness.filled.json",
        book_sha256="0" * 64,
        authored="2026-11-21",
        authoring_minutes=11,
        checks=None,
        approver=None,
    )
    plan["choices"]["c_road"]["requires"] = ["well_seen"]
    parsed = StoryPlan.model_validate(plan)
    assert parsed.book is not None
    assert parsed.provenance.authoring_minutes == 11


@pytest.mark.unit
def test_plants_by_choice_maps_planting_choices_to_their_facts() -> None:
    parsed = StoryPlan.model_validate(_plan())
    assert parsed.plants_by_choice() == {
        "c_take_map": frozenset({"map_marks_cave"}),
        "c_take_lamp": frozenset({"lamp_lit"}),
    }


@pytest.mark.unit
def test_shape_hash_ignores_prose_and_tracks_the_graph() -> None:
    book = _book()
    baseline = shape_hash(Storybook.model_validate(book))
    reworded = _book()
    reworded["nodes"][0]["body"] = "Completely different prose."
    reworded["nodes"][0]["choices"][0]["label"] = "Another label."
    reworded["title"] = "Another title"
    reworded["variables"][0]["description"] = "described"
    assert shape_hash(Storybook.model_validate(reworded)) == baseline
    retargeted = _book()
    retargeted["nodes"][0]["choices"][1]["target"] = "n_fork"
    assert shape_hash(Storybook.model_validate(retargeted)) != baseline
    assert baseline.startswith("sha256:")
    assert len(baseline) == len("sha256:") + 64


@pytest.mark.unit
def test_shape_projection_drops_every_prose_field() -> None:
    projection = json.dumps(shape_projection(Storybook.model_validate(_book())))
    assert "Body of" not in projection
    assert "Go (" not in projection
    assert "Plan Witness" not in projection


@pytest.mark.unit
def test_the_committed_json_schema_is_current() -> None:
    committed = Path(__file__).resolve().parents[2] / "schema" / "storyplan.schema.json"
    assert json.loads(committed.read_text(encoding="utf-8")) == build_schema(), (
        "schema/storyplan.schema.json is stale; regenerate via "
        "`uv run python -m cyo_adventure.storyplan.schema_export`"
    )


@pytest.mark.unit
def test_schema_export_writes_and_main_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from cyo_adventure.storyplan import schema_export

    target = export_schema(tmp_path / "out" / "storyplan.schema.json")
    assert json.loads(target.read_text(encoding="utf-8"))["title"] == "StoryPlan"
    with patch.object(schema_export, "export_schema", return_value=target):
        schema_export.main()
    assert "wrote" in capsys.readouterr().out


@pytest.mark.unit
def test_book_sha256_is_the_hex_digest_of_the_bytes() -> None:
    assert book_sha256(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


@pytest.mark.unit
def test_the_control_book_plan_extras_are_accepted() -> None:
    """Additive fields the second WP-0.3 plan writer chose, kept in the canonical shape."""
    plan = _plan()
    plan["facts"]["well_seen"]["implicit_plant"] = "paid off at the fork"
    plan["choices"]["c_road"]["establishes"] = ["well_seen"]
    plan["endings"]["n_fall"].update(valence="negative", kind="setback")
    plan["provenance"]["notes"] = ["no threads: the book declares no variables"]
    parsed = StoryPlan.model_validate(plan)
    assert parsed.plants_by_choice()["c_road"] == frozenset({"well_seen"})
    plan["choices"]["c_road"]["establishes"] = ["ghost"]
    assert "choices.c_road.establishes names undeclared fact 'ghost'" in _rejection(
        plan
    )


@pytest.mark.unit
def test_the_second_dialect_is_rejected_where_it_differs() -> None:
    plan = _plan()
    plan["truth"]["answer"] = plan["truth"].pop("statement")
    plan["request"]["source"] = "catalog book"
    message = _rejection(plan)
    assert "truth.statement" in message
    assert "truth.answer" in message
    assert "request.source" in message
