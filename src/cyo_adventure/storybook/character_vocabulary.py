"""Canonical character vocabulary (ADR-028 decision 2).

G3 carry is name-match, so an undeclared canonical name is silently ignored
rather than an error. That makes this vocabulary a menu each book draws from
rather than a mandate every book satisfies: a 16+ long gamebook and an 8-11
prose book can share a character while declaring disjoint variable sets.

``archetype`` and the stats never coexist in one book. In a mechanics book the
stat spread is the archetype (a Scout is ``wits 2 / nerve 1 / might 0``), so
``archetype`` carries identity only in prose cells, where there are no stats to
infer it from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from cyo_adventure.storybook.models import VariableType

# The six archetypes, in roster order. Codes are assigned by position starting
# at 1; see ARCHETYPE_CODES.
#
# #CRITICAL: data integrity: this order is the wire format for every stored
# character. Inserting a name anywhere but the end renumbers every archetype
# above it, silently changing what existing readers' characters are.
# #VERIFY: test_archetype_codes_are_pinned_to_their_names asserts the codes
# literally rather than deriving them from this tuple, so an insertion fails
# the suite instead of passing it.
ARCHETYPE_ROSTER: Final[tuple[str, ...]] = (
    "scout",
    "guardian",
    "trickster",
    "scholar",
    "healer",
    "wildheart",
)

# The Storybook variable value meaning "not yet chosen". A participating prose
# book declares ``archetype: 0`` as its initial so that every archetype-gated
# branch stays reachable from declared initials and L2-11 keeps passing; an
# in-story build node then sets 1-6. See ADR-028 decision 3.
ARCHETYPE_UNCHOSEN: Final[int] = 0

ARCHETYPE_CODES: Final[dict[str, int]] = {
    name: index for index, name in enumerate(ARCHETYPE_ROSTER, start=1)
}


@dataclass(frozen=True, slots=True)
class CanonicalVariable:
    """A canonical character variable's declared shape.

    Attributes:
        name: The variable name, which is also the G3 carry match key.
        type: The Storybook variable type. Always ``INT``: Tier-2 conditions
            are a JSONLogic subset with no string comparison, so a text trait
            cannot be read by a condition.
        min: Inclusive lower bound.
        max: Inclusive upper bound.
    """

    name: str
    type: VariableType
    min: int
    max: int


def _canonical(name: str, low: int, high: int) -> CanonicalVariable:
    return CanonicalVariable(name=name, type=VariableType.INT, min=low, max=high)


# Range 0-2 rather than 0-3 for the stats is an envelope-size decision: three
# stats at 0-3 is 64 states, which is exactly the _MAX_ENTRY_STATES ceiling, and
# at 0-2 it is 27. A four-band degrees-of-success ladder still fits: >= 2 crit,
# == 1 pass, == 0 with a local resource = scrape, == 0 without = fail.
CANONICAL_CHARACTER_VARIABLES: Final[dict[str, CanonicalVariable]] = {
    "archetype": _canonical("archetype", ARCHETYPE_UNCHOSEN, len(ARCHETYPE_ROSTER)),
    "might": _canonical("might", 0, 2),
    "wits": _canonical("wits", 0, 2),
    "nerve": _canonical("nerve", 0, 2),
}
