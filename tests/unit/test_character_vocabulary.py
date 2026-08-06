"""Tests for the canonical character vocabulary (ADR-028 decision 2)."""

from __future__ import annotations

from cyo_adventure.storybook.character_vocabulary import (
    ARCHETYPE_CODES,
    ARCHETYPE_ROSTER,
    ARCHETYPE_UNCHOSEN,
    CANONICAL_CHARACTER_VARIABLES,
)
from cyo_adventure.storybook.models import VariableType


def test_archetype_codes_are_pinned_to_their_names() -> None:
    """Pin every roster name to its int code.

    The database stores archetype as a text enum and the Storybook variable is
    an int; this mapping is the single place the roster order is load-bearing.
    A roster insertion that renumbered existing codes would silently change
    every live character's archetype, so the codes are asserted literally
    rather than derived from the roster tuple.
    """
    assert ARCHETYPE_CODES == {
        "scout": 1,
        "guardian": 2,
        "trickster": 3,
        "scholar": 4,
        "healer": 5,
        "wildheart": 6,
    }


def test_zero_is_reserved_for_not_yet_chosen() -> None:
    assert ARCHETYPE_UNCHOSEN == 0
    assert 0 not in ARCHETYPE_CODES.values()


def test_roster_order_matches_the_codes() -> None:
    assert ARCHETYPE_ROSTER == (
        "scout",
        "guardian",
        "trickster",
        "scholar",
        "healer",
        "wildheart",
    )
    assert [ARCHETYPE_CODES[name] for name in ARCHETYPE_ROSTER] == [1, 2, 3, 4, 5, 6]


def test_canonical_variables_carry_type_and_range() -> None:
    """All four canonical variables are ints with the spec's ranges."""
    assert set(CANONICAL_CHARACTER_VARIABLES) == {
        "archetype",
        "might",
        "wits",
        "nerve",
    }
    for canonical in CANONICAL_CHARACTER_VARIABLES.values():
        assert canonical.type is VariableType.INT

    archetype = CANONICAL_CHARACTER_VARIABLES["archetype"]
    assert (archetype.min, archetype.max) == (0, len(ARCHETYPE_ROSTER))

    for stat in ("might", "wits", "nerve"):
        assert (
            CANONICAL_CHARACTER_VARIABLES[stat].min,
            CANONICAL_CHARACTER_VARIABLES[stat].max,
        ) == (0, 2)


def test_stat_envelope_is_twenty_seven_states() -> None:
    """Range 0-2 rather than 0-3 is the choice that keeps the envelope at 27.

    Three stats at 0-3 would be 64 states, which is exactly the
    ``_MAX_ENTRY_STATES`` ceiling CH-5 enforces, leaving no headroom.
    """
    span = 1
    for stat in ("might", "wits", "nerve"):
        canonical = CANONICAL_CHARACTER_VARIABLES[stat]
        span *= canonical.max - canonical.min + 1
    assert span == 27
