"""Unit tests for scripts/generate_drafting_brief.py (AL-149)."""

from __future__ import annotations

import pytest

from cyo_adventure.validator.band_profile import (
    _NODES_PER_DECISION_CEILING,
    production_cell_budget,
)
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
    assert main(["3-5", "short", "prose", "--json"]) == 0
    out = capsys.readouterr().out
    assert '"age_band": "3-5"' in out
    assert '"random_walk_satisfying_floor": 0.6' in out
