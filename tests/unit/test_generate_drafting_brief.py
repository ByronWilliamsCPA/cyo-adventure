"""Unit tests for scripts/generate_drafting_brief.py (AL-149)."""

from __future__ import annotations

import json

import pytest

from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle
from cyo_adventure.validator.band_profile import (
    _NODES_PER_DECISION_CEILING,
    is_offered_cell,
    production_cell_budget,
)
from cyo_adventure.validator.topology import BAND_TOPOLOGIES
from scripts.check_skeleton import walk_floor
from scripts.generate_drafting_brief import build_brief, main


@pytest.mark.unit
def test_brief_values_come_from_the_enforced_sources() -> None:
    """The brief must mirror band_profile exactly; hand-copied briefs drifted
    twice during the strict pilot (AL-149)."""
    brief = build_brief("13-16", "medium", "gamebook")
    nodes = brief["nodes"]
    assert isinstance(nodes, dict)
    budget = production_cell_budget("13-16", "medium", "gamebook")
    assert budget is not None
    assert (nodes["min"], nodes["max"], nodes["depth_cap"]) == budget
    pacing = brief["pacing"]
    assert isinstance(pacing, dict)
    # The exact drift the pilot hit: the gamebook density ceiling is 4.0,
    # not prose's 6.0, and the brief must carry the style-correct value.
    assert (
        pacing["nodes_per_decision_ceiling_fastest_finish"]
        == _NODES_PER_DECISION_CEILING["gamebook"]
    )


@pytest.mark.unit
def test_brief_rejects_an_off_matrix_cell() -> None:
    with pytest.raises(ValueError, match="not an offered production cell"):
        build_brief("3-5", "long", "gamebook")
    assert main(["3-5", "long", "gamebook"]) == 2


@pytest.mark.unit
def test_cli_emits_json_when_asked(capsys: pytest.CaptureFixture[str]) -> None:
    """The emitted JSON must mirror the enforced source, not a copied value.

    A hand-copied literal here would drift the moment ``walk_floor`` changes,
    the same failure mode AL-149 already hit twice; assert against the live
    computation instead (AL-149).
    """
    assert main(["3-5", "short", "prose", "--json"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["cell"]["age_band"] == "3-5"
    assert payload["outcome_economy"]["random_walk_satisfying_floor"] == walk_floor(
        "3-5", "prose"
    )


def _offered_cells() -> list[tuple[str, str, str]]:
    """Every offered production cell, derived rather than frozen.

    Derived so a cell added to the matrix is swept automatically. Freezing this
    list is the failure `AL-477` records: an expectation that must be edited by
    hand every time the artifact set grows taxes the project's central activity.
    """
    return [
        (band.value, length.value, style.value)
        for band in AgeBand
        for length in Length
        for style in NarrativeStyle
        if is_offered_cell(band.value, length.value, style.value)
    ]


@pytest.mark.unit
@pytest.mark.parametrize(("band", "length", "style"), _offered_cells())
def test_the_brief_publishes_only_topologies_the_band_may_declare(
    band: str, length: str, style: str
) -> None:
    """A brief that names a forbidden topology steers an author into a blocking rule.

    `reconvergence.capped_topologies` is a band-INDEPENDENT list and reads as a
    menu of options. It is not one: at 10-13 it names `gauntlet` and `time_cave`
    and the band admits neither, and at 13-16 it names `time_cave`, which that
    band cannot declare either. On 2026-08-19 two independent Sonnet authoring
    agents each picked a forbidden topology off it and only found out by reading
    `validator/topology.py`; one had already built a whole draft around it
    (`UW-C306`).

    Asserted per cell rather than per rule, because the defect was not a wrong
    value: every value in that list is a genuine capped topology. It was a wrong
    SCOPE, and only a per-cell sweep catches that.
    """
    brief = build_brief(band, length, style)
    topology = brief["topology"]
    assert isinstance(topology, dict)
    allowed = topology["allowed_for_this_band"]
    assert allowed == sorted(item.value for item in BAND_TOPOLOGIES[band])
    assert allowed, f"{band} must admit at least one topology"


@pytest.mark.unit
@pytest.mark.parametrize(("band", "length", "style"), _offered_cells())
def test_the_brief_states_the_depth_cap_is_a_longest_path(
    band: str, length: str, style: str
) -> None:
    """The depth cap is the one depth in the system that is not reader-experienced.

    L1-7 grades `nx.dag_longest_path_length` over the reachable subgraph, while
    every other depth-flavoured rule an author meets (the ending-depth floor,
    PL-20, PL-25) is a shortest-path quantity. A single-choice detour that
    rejoins the spine therefore adds a hop to this cap while adding nothing any
    one reader walks. Nothing said so, and an agent lost a whole draft to it.
    """
    brief = build_brief(band, length, style)
    depth = brief["depth"]
    nodes = brief["nodes"]
    assert isinstance(depth, dict)
    assert isinstance(nodes, dict)
    # The two must not drift apart: they are the same budget, reported twice.
    assert depth["cap"] == nodes["depth_cap"]
    assert "dag_longest_path_length" in str(depth["metric"])


@pytest.mark.unit
@pytest.mark.parametrize(("band", "length", "style"), _offered_cells())
def test_the_brief_states_that_any_variable_requires_tier_2(
    band: str, length: str, style: str
) -> None:
    """Declaring a variable requires tier 2, and the brief omitted it entirely.

    A tier-1 story that declares one is a blocking L1-6. This is the first thing
    to set on a stateful book, and it cost a gamebook agent a full gate iteration
    in the one cell where every book is stateful. Asserted in every cell, not
    only the gamebook ones: a prose book may declare state too, and the brief
    should not be the reason an author believes otherwise.
    """
    brief = build_brief(band, length, style)
    state = brief["state_budget"]
    assert isinstance(state, dict)
    assert "L1-6" in str(state["requires_tier_2"])
    assert "tier = 2" in str(state["requires_tier_2"])
