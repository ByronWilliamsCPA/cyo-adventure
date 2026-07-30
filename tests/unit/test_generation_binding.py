"""Unit tests for cyo_adventure.generation.binding's slot-field mapping.

Covers `personalizable_slot_fields` (ADR-023 Stage C, Task C0b): the pure
slot-id-to-personalization-field map a theme contract's `personalizable`
slots declare. This is the join the values-payload resolver needs and
cannot derive on its own: prose sentinels carry the slot id, the values
payload is keyed by slot type, and only `SlotSpec.personalization_field`
connects the two.
"""

from __future__ import annotations

from cyo_adventure.generation.binding import personalizable_slot_fields
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import (
    SlotScope,
    SlotSpec,
    ThemeContract,
)


def test_personalizable_slot_fields_maps_slot_id_to_field() -> None:
    """Every personalizable slot contributes one slot_id -> field entry."""
    contract = ThemeContract(
        contract_version=1,
        skeleton_slug="fixture-slug",
        age_band=AgeBand.BAND_8_11,
        default_binding={"HERO": "Explorer", "PLACE": "the harbor"},
        slots=[
            SlotSpec(
                id="HERO",
                scope=SlotScope.GLOBAL,
                meaning="the protagonist",
                kind="personalizable",
                personalization_field="protagonist_first_name",
                role_safety="protagonist",
            ),
            SlotSpec(id="PLACE", scope=SlotScope.GLOBAL, meaning="the setting"),
        ],
    )

    assert personalizable_slot_fields(contract) == {"HERO": "protagonist_first_name"}


def test_personalizable_slot_fields_is_empty_without_personalizable_slots() -> None:
    """A contract with only theme slots yields an empty map, never None."""
    contract = ThemeContract(
        contract_version=1,
        skeleton_slug="fixture-slug",
        age_band=AgeBand.BAND_8_11,
        default_binding={"PLACE": "the harbor"},
        slots=[SlotSpec(id="PLACE", scope=SlotScope.GLOBAL, meaning="the setting")],
    )

    assert personalizable_slot_fields(contract) == {}
