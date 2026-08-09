"""Edge-hardening tests for the ADR-023 personalization request schemas.

Covers only what the schema layer itself decides: value normalization, the
length bound it shares with the structural gate, and the consent scope's
bound and de-duplication. The semantic checks (closed vocabulary, denylist,
sibling-in-family) live in `storybook/personalization_values.py` and are
tested by `test_personalization_values.py`; nothing here duplicates them.
"""

from __future__ import annotations

import unicodedata
from typing import get_args

import pytest
from pydantic import ValidationError

from cyo_adventure.api.schemas import (
    _PERSONALIZATION_RING2_SLOT_TYPE_COUNT,
    CharacterCreateBody,
    PersonalizationSlotBody,
    PersonalizationValuesView,
    Ring2ConsentGrantBody,
    _PersonalizationSlotType,
)
from cyo_adventure.validator.slots import structural_value_violations

pytestmark = [pytest.mark.unit]


def _consent(covered: list[str]) -> Ring2ConsentGrantBody:
    """Build a valid grant body with a given covered_slot_types list."""
    return Ring2ConsentGrantBody(
        family_connection_id="fc-1",
        covered_slot_types=covered,
        policy_version="v1",
        signer_name="A Guardian",
        accepted=True,
    )


def test_decomposed_and_precomposed_text_values_normalize_identically() -> None:
    """The same name in NFD and NFC is stored as one canonical form.

    Without this the row stores whatever byte sequence the client sent, so
    the replace route's `!=` change detection sees an edit where a human sees
    none, and the 120-character structural limit is measured on a form whose
    length depends on the client's normalization.
    """
    precomposed = "José"
    decomposed = unicodedata.normalize("NFD", precomposed)
    assert precomposed != decomposed

    a = PersonalizationSlotBody(
        slot_type="protagonist_first_name", value_text=decomposed
    )
    b = PersonalizationSlotBody(
        slot_type="protagonist_first_name", value_text=precomposed
    )

    assert a.value_text == b.value_text == precomposed


def test_value_text_bound_matches_the_structural_gate() -> None:
    """The schema's max_length is the same 120 the structural gate enforces.

    A disagreement is not a hole (the gate rejects either way) but it routes
    the same input to two different error shapes depending on its length.
    """
    at_limit = "a" * 120
    over_limit = "a" * 121

    assert structural_value_violations(at_limit) == []
    assert any(v.rule == "charset" for v in structural_value_violations(over_limit))

    PersonalizationSlotBody(slot_type="protagonist_first_name", value_text=at_limit)
    with pytest.raises(ValidationError):
        PersonalizationSlotBody(
            slot_type="protagonist_first_name", value_text=over_limit
        )


def test_empty_value_text_is_rejected_by_the_structural_gate() -> None:
    """An empty or whitespace-only value is already rejected, one layer in.

    Pinned deliberately: the schema does NOT carry a `min_length`, and this
    records why that is not a gap. `structural_value_violations` reports
    `non_empty` for both, at write time and at payload-build time alike, so
    adding a second bound at the edge would only change which error shape the
    caller sees.
    """
    for candidate in ("", "   "):
        rules = {v.rule for v in structural_value_violations(candidate)}
        assert "non_empty" in rules


def test_covered_slot_types_are_deduplicated_in_first_seen_order() -> None:
    """Repeats collapse and the guardian's chosen order survives."""
    body = _consent(
        ["dedication", "pet_name", "dedication", "favorite_color", "pet_name"]
    )

    assert body.covered_slot_types == ["dedication", "pet_name", "favorite_color"]


def test_covered_slot_types_reject_a_flood_of_repeats() -> None:
    """A list longer than the number of slot types cannot be submitted.

    Every element here is an eligible slot type, so the route's own
    eligibility check would have passed it through and written 100,000
    entries into the consent row's JSONB column.
    """
    with pytest.raises(ValidationError):
        _consent(["dedication"] * 100_000)


def test_covered_slot_types_still_reject_an_empty_list() -> None:
    """The pre-existing min_length=1 floor is unchanged by the new bound."""
    with pytest.raises(ValidationError):
        _consent([])


def test_covered_slot_types_bound_is_the_ring2_ceiling_not_the_whole_vocabulary() -> (
    None
):
    """The consent-scope bound counts only slots that may legally appear in it.

    ``covered_slot_types`` is a ring-2 consent scope, and three slot types
    (``pronoun_set``, ``dedication``, and ADR-028's ``character_name``) are
    permanently ring-1-only, so they can never be admissible members. Bounding
    the list by the whole slot vocabulary counted members that cannot legally
    appear in it, and each new ring-1-only slot loosened the bound further.
    """
    all_slot_types = set(get_args(_PersonalizationSlotType))
    ring1_only = {"pronoun_set", "dedication", "character_name"}

    assert ring1_only < all_slot_types
    assert len(all_slot_types - ring1_only) == _PERSONALIZATION_RING2_SLOT_TYPE_COUNT
    assert len(all_slot_types) > _PERSONALIZATION_RING2_SLOT_TYPE_COUNT

    # The bound is wired to the field, not merely computed: a list one longer
    # than the ceiling is rejected before de-duplication can collapse it.
    with pytest.raises(ValidationError):
        _consent(["pet_name"] * (_PERSONALIZATION_RING2_SLOT_TYPE_COUNT + 1))


def test_character_name_slot_body_validates_with_no_value_field() -> None:
    """`character_name` is the one slot whose body carries no value at all.

    Its value is synthesized at resolve time from the profile's active
    character, so the consent row holds only the ring flags. Under the old
    unconditional `!= 1` check this body 422'd, making the slot unusable
    through its own API.
    """
    body = PersonalizationSlotBody(slot_type="character_name", ring1_enabled=True)

    assert body.value_text is None
    assert body.value_enum is None
    assert body.value_profile_id is None


def test_character_name_slot_body_with_a_value_text_is_rejected() -> None:
    """The other direction: a value smuggled onto `character_name` is a 422.

    Relaxing the count check to `<= 1` would have left the database's
    `ck_cpp_value_cardinality` CHECK as the only thing rejecting this, as a
    raw IntegrityError rather than a clean validation error.
    """
    for kwargs in (
        {"value_text": "Zephyr"},
        {"value_enum": "Zephyr"},
        {"value_profile_id": "11111111-1111-4111-8111-111111111111"},
    ):
        with pytest.raises(ValidationError):
            PersonalizationSlotBody(slot_type="character_name", **kwargs)  # pyright: ignore[reportArgumentType]


def test_ordinary_slot_body_with_no_value_field_is_rejected() -> None:
    """The `else 1` side of the branch still requires exactly one value.

    Only `character_name` may carry nothing; the special case must not have
    relaxed the rule for the other eleven slots.
    """
    with pytest.raises(ValidationError):
        PersonalizationSlotBody(slot_type="protagonist_first_name")


def test_character_name_is_nfc_normalized_like_a_personalization_value() -> None:
    """A child-authored character name gets the same canonical stored form.

    The name resolves into the `character_name` personalization slot and is
    substituted into story prose, so it needs the same NFC normalization the
    guardian-authored free-text slots get; without it the stored form depends
    on the client's normalization.
    """
    precomposed = "José"
    decomposed = unicodedata.normalize("NFD", precomposed)
    assert precomposed != decomposed

    body = CharacterCreateBody(
        profile_id="p-1", name=decomposed, archetype="scout", look="avatar_01"
    )

    assert body.name == precomposed


def test_values_view_declares_the_two_client_contract_fields() -> None:
    """Both C0 fields are required, non-nullable, and defaulted for the empty view."""
    fields = PersonalizationValuesView.model_fields

    assert fields["sentinel_pattern"].annotation is str
    assert fields["slot_bindings"].annotation == dict[str, str]
