"""Pure seed derivation for persistent characters (ADR-028).

No I/O and no ORM imports: the read-start path and the progression
writeback path both need one authoritative answer to "what numbers does
this character carry", and a pure module is the only version of that both
can share and both can test without a database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.storybook.character_vocabulary import (
    ARCHETYPE_CODES,
    ARCHETYPE_VARIABLE_NAME,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cyo_adventure.storybook.evaluator import VarState

_STAT_NAMES = ("might", "wits", "nerve")


def character_seed(attributes: Mapping[str, int]) -> VarState:
    """Return the carried variable state for a character's attributes.

    Args:
        attributes: Stored attribute name to value, as persisted in
            ``character_attribute``.

    Returns:
        VarState: A plain name-to-value map suitable for
        ``StoryEngine.start_continuation``. No filtering happens here: G3
        carry is name-match, so a book that does not declare a name simply
        ignores it, and pre-filtering by the receiving book would put the
        same decision in two places.
    """
    return dict(attributes)


def initial_attributes(archetype: str) -> dict[str, int]:
    """Return the attribute rows a newly created character starts with.

    Args:
        archetype: A canonical archetype name from ``ARCHETYPE_ROSTER``.

    Returns:
        dict[str, int]: The four canonical attributes, stats at zero.

    Raises:
        ValueError: If ``archetype`` is not in the canonical roster.
    """
    # #ASSUME: data integrity: this is the ONE place a new character's
    # Character.archetype string and its "archetype"-named CharacterAttribute
    # int code are derived from the same input and written together (by
    # api/characters.py::create_character, in one transaction). That is also
    # the ONLY thing that keeps the two representations agreeing; see
    # db/models.py Character.archetype's docstring for the full account of
    # why no CHECK/FK/trigger backs it. Do not add a second call site that
    # derives one representation without going through this function for the
    # other, or the two can drift.
    # #VERIFY: no test proves the invariant from outside this function's own
    # correctness; tests/unit/test_character_seeding.py exercises this
    # mapping directly, and the write-path restrictions that keep it the
    # only writer are covered by the tests cited on Character.archetype's
    # docstring.
    code = ARCHETYPE_CODES.get(archetype)
    if code is None:
        msg = f"'{archetype}' is not a canonical archetype"
        raise ValueError(msg)
    return {ARCHETYPE_VARIABLE_NAME: code} | dict.fromkeys(_STAT_NAMES, 0)
