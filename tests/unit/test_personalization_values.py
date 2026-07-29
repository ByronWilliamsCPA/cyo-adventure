"""Unit tests for the write-time/payload-build-time personalization validator.

Covers ADR-023 P4's four write-time checks (structural injection guard,
band-mandatory denylist, closed-enum membership, sibling-in-family) plus the
render-time fallback contract: an invalid value at payload-build time is
omitted, never raised.
"""

from __future__ import annotations

import uuid

from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.personalization_values import (
    CLOSED_VOCABULARIES,
    SIBLING_SLOT_TYPE,
    personalization_value_for_payload,
    validate_personalization_value,
)


def test_validate_personalization_value_structural_violation_rejected() -> None:
    """A slot-token-injection candidate fails the structural guard."""
    violations = validate_personalization_value(
        "protagonist_first_name",
        AgeBand.BAND_8_11,
        value_text="{HERO}",
    )

    assert any(v.rule == "charset" for v in violations)
    assert all(v.slot_id == "protagonist_first_name" for v in violations)


def test_validate_personalization_value_denylisted_bundle_rejected() -> None:
    """A value matching a band-mandatory denylist bundle is rejected."""
    violations = validate_personalization_value(
        "favorite",
        AgeBand.BAND_5_8,
        value_enum="a sharpened steel sword",
    )

    assert any(v.rule == "forbid:weapon" for v in violations)


def test_validate_personalization_value_enum_non_membership_rejected() -> None:
    """A candidate not in the slot's closed vocabulary is rejected.

    ADR-023 rows 4a/5/6/7 describe these enum slots conceptually but do not
    enumerate a shippable closed vocabulary for any of them (see the module
    docstring's STOP note), so every ``CLOSED_VOCABULARIES`` entry is
    currently empty and every candidate value is, by construction, rejected
    as "not a member" until product supplies the real lists.
    """
    assert CLOSED_VOCABULARIES["pet_species"] == frozenset()

    violations = validate_personalization_value(
        "pet_species",
        AgeBand.BAND_8_11,
        value_enum="dog",
    )

    assert any(v.rule == "enum_membership" for v in violations)


def test_validate_personalization_value_sibling_outside_family_rejected() -> None:
    """A sibling slot's value_profile_id must be one of the family's own profiles."""
    family_profile_ids = {uuid.uuid4(), uuid.uuid4()}
    outside_profile_id = uuid.uuid4()

    violations = validate_personalization_value(
        SIBLING_SLOT_TYPE,
        AgeBand.BAND_8_11,
        value_profile_id=outside_profile_id,
        family_profile_ids=family_profile_ids,
    )

    assert any(v.rule == "sibling_outside_family" for v in violations)


def test_validate_personalization_value_sibling_inside_family_passes() -> None:
    """A sibling slot's value_profile_id inside the family raises no violation."""
    sibling_id = uuid.uuid4()
    family_profile_ids = {sibling_id, uuid.uuid4()}

    violations = validate_personalization_value(
        SIBLING_SLOT_TYPE,
        AgeBand.BAND_8_11,
        value_profile_id=sibling_id,
        family_profile_ids=family_profile_ids,
    )

    assert violations == []


def test_validate_personalization_value_clean_text_passes() -> None:
    """A clean, non-denylisted, non-injecting text value raises no violation."""
    violations = validate_personalization_value(
        "pet_name",
        AgeBand.BAND_8_11,
        value_text="Biscuit",
    )

    assert violations == []


def test_personalization_value_for_payload_invalid_value_omitted_not_raised() -> None:
    """An invalid value at payload-build time resolves to None, never an exception."""
    result = personalization_value_for_payload(
        "protagonist_first_name",
        AgeBand.BAND_8_11,
        value_text="{HERO}",
    )

    assert result is None


def test_personalization_value_for_payload_valid_value_returned() -> None:
    """A valid value at payload-build time is returned unchanged."""
    result = personalization_value_for_payload(
        "pet_name",
        AgeBand.BAND_8_11,
        value_text="Biscuit",
    )

    assert result == "Biscuit"
