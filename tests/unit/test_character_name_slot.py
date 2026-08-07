"""The character_name slot: a personalization value with no personalization row.

Every assertion here exists because character_name breaks an assumption
the other eleven slots share. Where a normal slot's value, consent flag,
and purge target all live in one child_profile_personalization row,
character_name's value lives in `character`, its consent flag lives in
that row, and purging it means deleting from a table the purge path has
never touched.

`ring2_eligible_fields()` does not exist anywhere in this tree (confirmed by
grep); the ring-2 ceiling is expressed only as the hand-maintained
`db.models._PERSONALIZATION_RING2_SLOT_TYPE_VALUES` string, the literal body
of the `ck_cpp_ring2_ceiling` CHECK. This module derives the ring-2-eligible
set from that single source (parsed the same way
`tests/unit/test_personalization_vocab_drift.py` parses its sibling
constants) rather than inventing a second copy of the ceiling here or a
function that does not exist in the source module.
"""

from __future__ import annotations

import re

import pytest

from cyo_adventure.db.models import _PERSONALIZATION_RING2_SLOT_TYPE_VALUES
from cyo_adventure.storybook.theme_contract import (
    PERSONALIZATION_FIELDS,
    REAL_PERSON_PERSONALIZATION_FIELDS,
)


def _ring2_eligible_fields() -> frozenset[str]:
    """Parse the ring-2 ceiling's slot-type names from its own literal SQL body.

    Returns:
        frozenset[str]: Every slot_type the `ck_cpp_ring2_ceiling` CHECK
        permits, i.e. the same set `api.personalization._RING2_EXCLUDED_SLOT_TYPES`
        is built to complement.
    """
    return frozenset(re.findall(r"'([^']*)'", _PERSONALIZATION_RING2_SLOT_TYPE_VALUES))


@pytest.mark.unit
def test_character_name_is_a_personalization_field() -> None:
    assert "character_name" in PERSONALIZATION_FIELDS


@pytest.mark.unit
def test_character_name_is_treated_as_a_real_person_field() -> None:
    """Kids name characters after themselves and their friends.

    Nothing stops a child typing their own first name, so the slot
    inherits the same handling as protagonist_first_name rather than the
    handling of favorite_color.
    """
    assert "character_name" in REAL_PERSON_PERSONALIZATION_FIELDS


@pytest.mark.unit
def test_character_name_is_ring_1_only_permanently() -> None:
    """Not a default that can be widened later: a ceiling.

    Ring 2 shares a story with a connected family. A character name is
    free text a child chose, and the three-ring boundary (ADR-018) puts
    unreviewed child free text inside ring 1 only.
    """
    assert "character_name" not in _ring2_eligible_fields()


@pytest.mark.unit
def test_character_name_never_enters_the_ring2_ceiling_alongside_every_other_field() -> (
    None
):
    """The ring-2 ceiling is PERSONALIZATION_FIELDS minus the ring-1-only set.

    Cross-checks the parsed ceiling against the closed vocabulary directly,
    so a future edit that added character_name to
    `_PERSONALIZATION_RING2_SLOT_TYPE_VALUES` without removing it from
    `PERSONALIZATION_FIELDS`'s complement would fail here, not just in the
    single-field assertion above.
    """
    ceiling = _ring2_eligible_fields()
    assert ceiling <= set(PERSONALIZATION_FIELDS)
    assert "character_name" not in ceiling
