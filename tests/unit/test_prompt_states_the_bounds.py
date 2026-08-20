"""Every numeric bound the gate enforces must be stated in the prompt.

The largest single effect measured in this workstream. Five story-first drafts
were written; the four given no numeric targets produced median scene lengths of
246, 439, 400 and 279 words with no trend, each failing PL-19 across most of its
nodes and the 13-16 draft carrying 17 blocking errors. The one draft told its
numbers produced median 198, max exactly at the stated 230, with zero PL-19 and
zero CG-3 findings, and 2 blocking errors.

The confound runs the right way: 16+ has the largest words-per-node budget in the
catalog and produced the SMALLEST median, so if band drove scene length that run
should have been the longest.

So this is not a style preference. A bound the gate enforces and the prompt omits
is a defect by construction, and this asserts the property per cell rather than
per rule, because the defect that motivated it (`UW-C279`) was a whole table
being consulted on one side and not the other.
"""

from __future__ import annotations

import uuid
from typing import cast

import pytest

from cyo_adventure.db.models import StoryRequest
from cyo_adventure.generation.prompts import (
    _scale_cell_block,  # pyright: ignore[reportPrivateUsage]
)
from cyo_adventure.story_requests.brief import brief_from_request
from cyo_adventure.validator.band_profile import (
    _PRODUCTION_CELLS,  # pyright: ignore[reportPrivateUsage]
    breadth_scaled_floors,
    cell_ending_bounds,
    min_complete_floor,
    nodes_per_decision_ceiling,
    offered_cells,
    words_per_node_profile,
)
from cyo_adventure.validator.choice_grammar import words_per_stop_ceiling


def _brief_for(band: str, length: str, style: str):
    """Build the concept brief a real request for this cell would produce."""
    return brief_from_request(
        StoryRequest(
            family_id=uuid.uuid4(),
            request_text="a story",
            status="pending",
            age_band=band,
            length=length,
            narrative_style=style,
        ),
        None,
    )


@pytest.mark.parametrize("cell", sorted(_PRODUCTION_CELLS))
def test_the_prompt_states_every_bound_the_gate_will_apply(
    cell: tuple[str, str, str],
) -> None:
    """The rendered cell block names the per-node max, stop ceiling and arc floor.

    Checks the NUMBER appears, not that some prose mentions the rule, because a
    prompt that names a rule without its threshold tells the generator nothing it
    can act on.
    """
    band, length, style = cell
    rendered = _scale_cell_block(_brief_for(band, length, style))

    profile = words_per_node_profile(band, style)
    assert profile is not None
    assert str(profile[3]) in rendered, f"{cell}: PL-19 per-node max absent"

    floor = min_complete_floor(band, length, style)
    assert floor is not None
    assert str(floor) in rendered, f"{cell}: PL-20 arc floor absent"

    stop = words_per_stop_ceiling(band)
    if stop is not None:
        assert str(stop) in rendered, f"{cell}: CG-3 words-per-stop ceiling absent"


@pytest.mark.parametrize("cell", sorted(_PRODUCTION_CELLS))
def test_the_brief_asks_for_an_ending_count_the_gate_accepts(
    cell: tuple[str, str, str],
) -> None:
    """The brief's ending count satisfies PL-17 at the cell's least favourable size.

    `UW-C279`: the brief read the BAND envelope while PL-17 floors from the CELL
    envelope, so the prompt demanded "EXACTLY 4 ending node(s) ... Not more, not
    fewer" where the gate required 24. Swept over every cell, because the defect
    was which table was consulted rather than one cell's arithmetic.
    """
    band, length, style = cell
    min_nodes, _max_nodes, _depth = _PRODUCTION_CELLS[cell]
    brief = _brief_for(band, length, style)

    floor, _decisions = breadth_scaled_floors(min_nodes, style)

    assert brief.ending_count >= floor, (
        f"{cell}: prompt asks for exactly {brief.ending_count} endings, "
        f"PL-17 floors at {floor}"
    )


# ---------------------------------------------------------------------------
# The drafting brief must agree with the rules it publishes (UW-C300)
# ---------------------------------------------------------------------------


def test_brief_publishes_the_pl26_ceiling_the_rule_grades() -> None:
    """The brief's pacing ceiling must be the one PL-26 applies, per band.

    This drifted twice. `generate_drafting_brief.py` exists because a
    hand-copied brief mis-stated PL-26's gamebook ceiling as 6.0 against the
    enforced 4.0 (`AL-149`), and the script then reproduced the same defect by
    reading the flat by-style table directly while PL-26 graded the per-band
    one. Three of seven authoring agents hit it independently on 2026-08-18. The
    error flipped direction across the band range, so a single spot check would
    not have caught it.
    """
    from scripts.generate_drafting_brief import build_brief

    for band, length, style in sorted(offered_cells()):
        brief = build_brief(band, length, style)
        pacing = cast("dict[str, object]", brief["pacing"])
        assert pacing["nodes_per_decision_ceiling_fastest_finish"] == (
            nodes_per_decision_ceiling(style, band)
        ), f"brief disagrees with PL-26 at {band}/{length}/{style}"


def test_brief_publishes_the_cell_endings_ceiling() -> None:
    """The ADR section 5 per-cell maximum must appear in the brief.

    PL-17's ceiling is advisory so it does not block, but under the authoring
    bar of zero findings at any severity it binds, and `the-last-blue-cup` is
    the proof that a book authored to the strict bar can cross it.
    """
    from scripts.generate_drafting_brief import build_brief

    for band, length, style in sorted(offered_cells()):
        brief = build_brief(band, length, style)
        assert "endings_ceiling_for_cell" in brief
        assert brief["endings_ceiling_for_cell"] == (
            None
            if cell_ending_bounds(band, length, style) is None
            else cell_ending_bounds(band, length, style)[1]
        )


def test_no_brief_floor_ever_exceeds_the_brief_own_ceiling() -> None:
    """A floor above the ceiling is unsatisfiable, and the brief printed one.

    At 3-5/medium with 45 nodes the uncapped floor asked for 7 endings against a
    cell ceiling of 4, so the top of the declared node envelope could not be
    authored. `UW-C283` fixed this inversion in PL-17 and two other call sites
    kept the uncapped reading.
    """
    from scripts.generate_drafting_brief import build_brief

    for band, length, style in sorted(offered_cells()):
        brief = build_brief(band, length, style)
        ceiling = brief["endings_ceiling_for_cell"]
        if ceiling is None:
            continue
        floors = cast("dict[str, int]", brief["endings_floor_by_node_count"])
        for node_count, floor in floors.items():
            assert floor <= cast("int", ceiling), (
                f"{band}/{length}/{style} at {node_count} nodes: floor {floor} "
                f"exceeds the cell ceiling {ceiling}"
            )
