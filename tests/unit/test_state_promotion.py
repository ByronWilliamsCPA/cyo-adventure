"""Tests for the consequence tool (``mutation/state_promotion.py``).

The tool gives a stateless skeleton plants (``set`` effects on early choices)
and payoffs (same-label choice pairs with opposite conditions) so that an early
choice comes back later. These tests pin the four behaviours the brief asked
for (a cosmetic fork becomes a plant, a payoff gate keeps an unconditional
option, refusals carry a reason, running twice adds nothing), the exact inverse
that keeps the WS-5 flywheel's donor pool intact, and the reproducibility of
the committed pilot.
"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from cyo_adventure.mutation.operators import _load_catalog_donor
from cyo_adventure.mutation.state_promotion import (
    _WORDS_PER_STOP_CEILING,
    promote_skeleton,
    stateless_view,
)
from cyo_adventure.player.engine import StoryEngine
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator import choice_grammar
from cyo_adventure.validator.gate import run_gate
from scripts import add_consequence

_REPO = Path(__file__).resolve().parent.parent.parent

# The 2026-11-20 pilot: committed promoted, so each must be reproducible from
# its own stateless reading.
_PILOT = (
    "skeletons/8-11/the-lantern-keepers-list.json",
    "skeletons/8-11/the-hundred-door-hotel.json",
    "skeletons/10-13/the-orchard-signal.json",
    "skeletons/10-13/the-cartographers-apprentice.json",
    "skeletons/13-16/the-migration-year.json",
    "skeletons/13-16/the-hollow-crown-gambit.json",
)
_FILL_RE = re.compile(r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$", re.DOTALL)


def _directive(role: str, beats: str) -> str:
    return f"<<FILL role={role} words=60 beats='{beats}'>>"


def _node(node_id: str, role: str, choices: list[tuple[str, str]]) -> dict[str, object]:
    return {
        "id": node_id,
        "body": _directive(role, f"{node_id} happens"),
        "is_ending": False,
        "choices": [
            {"id": f"c_{node_id}_{k}", "label": label, "target": target}
            for k, (label, target) in enumerate(choices)
        ],
    }


def _ending(node_id: str, valence: str, kind: str) -> dict[str, object]:
    return {
        "id": node_id,
        "body": _directive("ending", f"{node_id} ending"),
        "is_ending": True,
        "choices": [],
        "ending": {
            "id": f"end_{node_id}",
            "valence": valence,
            "kind": kind,
            "title": f"Title {node_id}",
        },
    }


def _skeleton(band: str = "10-13") -> dict[str, object]:
    """A small MVP shell: a cosmetic fork early, a setback door, a climax.

    ``n_fork``'s two options rejoin at ``n_hall`` with nothing changed (a false
    choice by the consequence measure). ``n_door`` offers a choice that runs
    straight into a negative ending beside a continuation, and ``n_inside``
    offers a neutral ending beside a positive one: both are rescue sites.
    """
    nodes = [
        _node("n_start", "setup", [("Look around.", "n_fork")]),
        _node(
            "n_fork",
            "choice",
            [("Pick up the brass key.", "a_key"), ("Read the old sign.", "b_sign")],
        ),
        _node("a_key", "rising", [("Go on to the hall.", "n_hall")]),
        _node("b_sign", "rising", [("Go on to the hall.", "n_hall")]),
        _node(
            "n_hall",
            "rising",
            [("Climb the stairs.", "n_door"), ("Take the lift.", "n_door")],
        ),
        _node(
            "n_door",
            "choice",
            [("Force the stuck door.", "x_force"), ("Knock and wait.", "n_wait")],
        ),
        _node("x_force", "setback", [("Give up for the night.", "e_bad")]),
        _ending("e_bad", "negative", "setback"),
        _node("n_wait", "rising", [("Step inside.", "n_inside")]),
        _node(
            "n_inside",
            "climax",
            [("Open the chest.", "e_good"), ("Leave it shut.", "e_ok")],
        ),
        _ending("e_good", "positive", "success"),
        _ending("e_ok", "neutral", "completion"),
    ]
    return {
        "schema_version": "2.0",
        "id": "sk_fixture",
        "version": 1,
        "title": "Fixture",
        "metadata": {
            "narrative_person": "third",
            "age_band": band,
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 5.5,
                "tolerance": 1.5,
            },
            "tier": 1,
            "themes": ["test"],
            "estimated_minutes": 3,
            "ending_count": 3,
            "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
            "topology": "branch_and_bottleneck",
            "production_eligible": False,
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": nodes,
    }


def _choices(doc: dict[str, object], node_id: str) -> list[dict[str, object]]:
    nodes = doc["nodes"]
    assert isinstance(nodes, list)
    for node in nodes:
        assert isinstance(node, dict)
        if node["id"] == node_id:
            choices = node["choices"]
            assert isinstance(choices, list)
            return choices
    msg = f"no node {node_id}"
    raise AssertionError(msg)


def _promoted() -> dict[str, object]:
    report = promote_skeleton(_skeleton(), allow_mvp=True)
    assert report.status == "promoted", report.reason
    assert report.candidate is not None
    return report.candidate


@pytest.mark.unit
def test_cosmetic_fork_becomes_a_plant() -> None:
    """Both options of the false fork now set a different variable."""
    doc = _promoted()
    fork = _choices(doc, "n_fork")
    set_vars = [c["effects"][0]["var"] for c in fork]
    assert len(set(set_vars)) == 2
    declared = {v["name"] for v in doc["variables"]}
    assert set(set_vars) == declared
    assert doc["metadata"]["tier"] == 2
    assert all(v["type"] == "bool" for v in doc["variables"])
    assert not run_gate(doc).blocked


@pytest.mark.unit
def test_payoff_gate_keeps_an_unconditional_option() -> None:
    """Every node with a conditional choice keeps one a reader always sees."""
    story = Storybook.model_validate(_promoted())
    gated = [n for n in story.nodes if any(c.condition is not None for c in n.choices)]
    assert gated
    for node in gated:
        assert any(c.condition is None for c in node.choices), node.id
        labels = [c.label for c in node.choices if c.condition is not None]
        # A same-label pair: the two gated twins share one label.
        assert len(labels) == 2
        assert labels[0] == labels[1]


@pytest.mark.unit
def test_rescue_changes_which_ending_is_reachable() -> None:
    """Playing both states: the planter sees the door move go well."""
    doc = _promoted()
    story = Storybook.model_validate(doc)
    engine = StoryEngine(story)
    fork = _choices(doc, "n_fork")
    for planted, expected_target in ((0, "cq_payoff_"), (1, "x_force")):
        state = engine.start()
        state = engine.choose(state, engine.visible_choices(state)[0].id)
        assert state.current_node == "n_fork"
        state = engine.choose(state, str(fork[planted]["id"]))
        while state.current_node != "n_door":
            state = engine.choose(state, engine.visible_choices(state)[0].id)
        door = [c.target for c in engine.visible_choices(state)]
        assert len(door) == 2  # visible count unchanged by the pair
        assert any(t.startswith(expected_target) for t in door), door


@pytest.mark.unit
def test_young_band_is_refused() -> None:
    """3-5 and 5-8 are Tier-1 by ADR-011; the tool refuses with the reason."""
    for band in ("3-5", "5-8"):
        report = promote_skeleton(_skeleton(band), allow_mvp=True)
        assert report.status == "refused"
        assert "Tier-1 by ADR-011" in report.reason
        assert report.candidate is None


@pytest.mark.unit
def test_pure_tree_is_refused_with_a_reason() -> None:
    """With no merge anywhere, no plant can be paid off on a shared route."""
    doc = _skeleton("8-11")  # time_cave is an 8-11 topology, not a 10-13 one
    tree = [
        _node("n_start", "setup", [("Look around.", "n_fork")]),
        _node("n_fork", "choice", [("Go left.", "n_left"), ("Go right.", "n_right")]),
        _node("n_left", "rising", [("Push on.", "n_l2")]),
        _node("n_l2", "choice", [("Climb.", "e_good"), ("Rest.", "e_bad")]),
        _node("n_right", "rising", [("Push on.", "n_r2")]),
        _node("n_r2", "choice", [("Swim.", "e_ok"), ("Wait.", "e_bad2")]),
        _ending("e_good", "positive", "success"),
        _ending("e_bad", "negative", "setback"),
        _ending("e_ok", "neutral", "completion"),
        _ending("e_bad2", "negative", "setback"),
    ]
    doc["nodes"] = tree
    doc["metadata"]["ending_count"] = 4
    doc["metadata"]["topology"] = "time_cave"
    assert not run_gate(doc).blocked
    report = promote_skeleton(doc, allow_mvp=True)
    assert report.status == "refused"
    assert "pure tree" in report.reason


@pytest.mark.unit
def test_narrative_sidecar_is_refused() -> None:
    """A .narrative.json's per-node entry states would go stale."""
    report = promote_skeleton(_skeleton(), allow_mvp=True, has_narrative_sidecar=True)
    assert report.status == "refused"
    assert "narrative" in report.reason


@pytest.mark.unit
def test_running_twice_adds_no_second_set() -> None:
    """Idempotence: a promoted skeleton is skipped, never re-planted."""
    doc = _promoted()
    before = copy.deepcopy(doc)
    again = promote_skeleton(doc, allow_mvp=True)
    assert again.status == "skipped"
    assert again.candidate is None
    assert doc == before


@pytest.mark.unit
def test_promotion_is_deterministic() -> None:
    """Same input, byte-identical output: a reviewer can re-derive any result."""
    first = json.dumps(_promoted(), sort_keys=True)
    second = json.dumps(_promoted(), sort_keys=True)
    assert first == second


@pytest.mark.unit
def test_directives_still_parse_and_carry_no_em_dash() -> None:
    """Every body stays a FILL directive, and nothing inserted an em-dash."""
    doc = _promoted()
    text = json.dumps(doc, ensure_ascii=False)
    assert chr(0x2014) not in text  # em-dash-ok: asserting its absence
    story = Storybook.model_validate(doc)
    for node in story.nodes:
        assert _FILL_RE.match(node.body), node.id
    merge = next(n for n in story.nodes if n.id == "n_hall")
    assert "MERGE:" in merge.body


@pytest.mark.unit
def test_stateless_view_round_trips_the_fixture() -> None:
    """The inverse removes exactly what was added."""
    original = _skeleton()
    assert stateless_view(_promoted()) == original
    # A document the tool did not produce comes back unchanged.
    assert stateless_view(original) == original


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "skeletons/8-11/the-half-hour-call.json",
        "skeletons/10-13/the-blackout-week.json",
        "skeletons/13-16/the-glasswright-debt.json",
        "skeletons/16+/the-salt-archive.json",
    ],
)
def test_stateless_view_round_trips_committed_skeletons(path: str) -> None:
    """On real Tier-1 shells too, ``stateless_view(promote(x)) == x``."""
    original = json.loads((_REPO / path).read_text(encoding="utf-8"))
    report = promote_skeleton(original)
    assert report.candidate is not None, report.reason
    assert stateless_view(report.candidate) == original


@pytest.mark.unit
@pytest.mark.parametrize("path", _PILOT)
def test_committed_pilot_is_reproducible(path: str) -> None:
    """Each committed pilot skeleton is exactly what the tool produces today."""
    committed = json.loads((_REPO / path).read_text(encoding="utf-8"))
    assert committed["metadata"]["tier"] == 2
    report = promote_skeleton(stateless_view(committed))
    assert report.status == "promoted", report.reason
    assert report.candidate == committed
    assert report.ending_changing, "no payoff changes ending reachability"


@pytest.mark.unit
def test_words_per_stop_table_matches_choice_grammar() -> None:
    """The local copy of the CG-3 ceilings tracks the validator's table."""
    source = choice_grammar._WORDS_PER_STOP_CEILING
    for band, ceiling in _WORDS_PER_STOP_CEILING.items():
        assert source[band] == ceiling


@pytest.mark.unit
def test_m3_donor_resolver_grafts_from_the_stateless_view() -> None:
    """A promoted donor reaches M3 as its exact Tier-1 reading."""
    donor = _load_catalog_donor("the-lantern-keepers-list")
    assert donor["variables"] == []
    assert donor["metadata"]["tier"] == 1
    assert "cq_payoff_" not in json.dumps(donor)


@pytest.mark.unit
def test_cli_dry_run_writes_nothing_and_write_keeps_formatting(
    tmp_path: Path,
) -> None:
    """Dry run leaves the file alone; --write keeps the file's own indent."""
    path = tmp_path / "fixture.json"
    raw = json.dumps(_skeleton(), indent=1, ensure_ascii=True) + "\n"
    path.write_text(raw, encoding="utf-8")
    assert add_consequence.main([str(path), "--allow-mvp"]) == 0
    assert path.read_text(encoding="utf-8") == raw
    assert add_consequence.main([str(path), "--allow-mvp", "--write"]) == 0
    written = path.read_text(encoding="utf-8")
    assert written == json.dumps(_promoted(), indent=1, ensure_ascii=True) + "\n"
    # Second run: skipped, exit 0, file unchanged.
    assert add_consequence.main([str(path), "--allow-mvp", "--write"]) == 0
    assert path.read_text(encoding="utf-8") == written


@pytest.mark.unit
def test_cli_exits_one_when_anything_is_refused(tmp_path: Path) -> None:
    """A dry run over a corpus doubles as a coverage report."""
    path = tmp_path / "young.json"
    path.write_text(json.dumps(_skeleton("5-8")), encoding="utf-8")
    assert add_consequence.main([str(path), "--allow-mvp"]) == 1


@pytest.mark.unit
def test_output_does_not_depend_on_the_hash_seed() -> None:
    """Two interpreters with different PYTHONHASHSEED plan identically.

    Regression: the first version took its payoff search root from the
    consequence measure's ``reconverged_at``, which breaks ties by set order,
    so the lantern list's second payoff moved between three nodes run to run.
    """
    script = (
        "import json,sys;"
        "from cyo_adventure.mutation.state_promotion import promote_skeleton;"
        "from cyo_adventure.mutation.state_promotion import stateless_view;"
        "d=json.load(open(sys.argv[1]));"
        "r=promote_skeleton(stateless_view(d));"
        "print(json.dumps([p.node_id for p in r.payoffs]))"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", script, str(_REPO / _PILOT[0])],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("1", "2", "4")
    }
    assert len(outputs) == 1
