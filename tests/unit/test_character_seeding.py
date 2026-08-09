"""Seed derivation: turning stored character attributes into a VarState.

Kept free of I/O so both the read-start path and the writeback path can
share one definition of what a character's numbers mean.
"""

from __future__ import annotations

import pytest

from cyo_adventure.characters.seeding import character_seed, initial_attributes
from cyo_adventure.storybook.character_vocabulary import (
    ARCHETYPE_CODES,
    ARCHETYPE_ROSTER,
)


@pytest.mark.unit
def test_seed_maps_attribute_rows_straight_through() -> None:
    """No transformation: the stored int IS the variable value."""
    assert character_seed({"might": 1, "wits": 2}) == {"might": 1, "wits": 2}


@pytest.mark.unit
def test_seed_of_no_attributes_is_empty_not_none() -> None:
    """An empty seed is a legal seed; G3 carry ignores names it lacks."""
    assert character_seed({}) == {}


@pytest.mark.unit
@pytest.mark.parametrize("archetype", ARCHETYPE_ROSTER)
def test_a_new_character_starts_every_stat_at_zero(archetype: str) -> None:
    """Progression is earned. A fresh character has nothing but its identity."""
    attributes = initial_attributes(archetype)
    assert attributes == {
        "archetype": ARCHETYPE_CODES[archetype],
        "might": 0,
        "wits": 0,
        "nerve": 0,
    }


@pytest.mark.unit
def test_initial_attributes_rejects_an_unknown_archetype() -> None:
    """The roster is the wire format; an unknown name must not silently become 0.

    Code 0 means "not yet chosen", so coercing an unknown name to it would
    create a character that every archetype-gated branch treats as
    unchosen while the row claims an archetype.
    """
    with pytest.raises(ValueError, match="not a canonical archetype"):
        initial_attributes("paladin")
