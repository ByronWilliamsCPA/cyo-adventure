"""ADR-028: the PURGE_TARGETS map, which decides where each slot is purged from.

These two assertions read only two module-level constants: no database, no
event loop, no HTTP client. They lived in
``tests/integration/test_personalization_purge.py`` alongside the tests that
do need Postgres, which meant they sat behind the integration marker and
skipped on any machine without Docker, silently taking a pure drift guard
offline. The database halves of the same claim stay in that module.
"""

from __future__ import annotations

import pytest

from cyo_adventure.api.personalization import PURGE_TARGETS
from cyo_adventure.storybook.theme_contract import PERSONALIZATION_FIELDS

pytestmark = [pytest.mark.unit]


def test_purge_targets_is_exhaustive_over_personalization_fields() -> None:
    """PURGE_TARGETS names every PERSONALIZATION_FIELDS member, and nothing else.

    Both directions matter. A field missing from PURGE_TARGETS is a slot the
    purge path has no story for at all; a stray extra key is a purge target
    for a slot type that no longer exists, which is exactly the kind of
    drift AL-068/UW-C20 found in the neighboring CLOSED_VOCABULARIES map (see
    tests/unit/test_personalization_vocab_drift.py). Asserting set equality
    covers both without hardcoding either list a second time here.
    """
    assert set(PURGE_TARGETS) == set(PERSONALIZATION_FIELDS), (
        "PURGE_TARGETS and PERSONALIZATION_FIELDS have drifted apart; a slot "
        "type must appear in both or neither, or the next slot added to "
        "PERSONALIZATION_FIELDS silently has no decided purge target"
    )


def test_purge_targets_names_character_for_character_name_only() -> None:
    """character_name is the one PURGE_TARGETS entry naming `character`.

    Every other entry names `personalization_row`: pinning that split
    directly (rather than only via the exhaustiveness test above) makes a
    future edit that widened `character`'s purge target to a second slot,
    or narrowed character_name's away from it, fail here with a message
    naming the exact slot, instead of only failing the vaguer set-equality
    assertion.
    """
    character_targets = {
        slot_type
        for slot_type, target in PURGE_TARGETS.items()
        if target == "character"
    }
    assert character_targets == {"character_name"}
