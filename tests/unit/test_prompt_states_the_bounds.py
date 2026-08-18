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

import pytest

from cyo_adventure.db.models import StoryRequest
from cyo_adventure.generation.prompts import (
    _scale_cell_block,  # pyright: ignore[reportPrivateUsage]
)
from cyo_adventure.story_requests.brief import brief_from_request
from cyo_adventure.validator.band_profile import (
    _PRODUCTION_CELLS,  # pyright: ignore[reportPrivateUsage]
    breadth_scaled_floors,
    min_complete_floor,
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
