"""Unit tests for scripts/generate_drafting_brief.py (AL-149)."""

from __future__ import annotations

import json

import pytest

from cyo_adventure.validator.band_profile import (
    _NODES_PER_DECISION_CEILING,
    production_cell_budget,
)
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
