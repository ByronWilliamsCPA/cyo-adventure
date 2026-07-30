"""Edge-hardening tests for the ADR-023 personalization request schemas.

Covers only what the schema layer itself decides: value normalization, the
length bound it shares with the structural gate, and the consent scope's
bound and de-duplication. The semantic checks (closed vocabulary, denylist,
sibling-in-family) live in `storybook/personalization_values.py` and are
tested by `test_personalization_values.py`; nothing here duplicates them.
"""

from __future__ import annotations

import unicodedata

import pytest
from pydantic import ValidationError

from cyo_adventure.api.schemas import (
    PersonalizationSlotBody,
    PersonalizationValuesView,
    Ring2ConsentGrantBody,
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
    body = _consent(["dedication", "pet_name", "dedication", "favorite", "pet_name"])

    assert body.covered_slot_types == ["dedication", "pet_name", "favorite"]


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


def test_values_view_declares_the_two_client_contract_fields() -> None:
    """Both C0 fields are required, non-nullable, and defaulted for the empty view."""
    fields = PersonalizationValuesView.model_fields

    assert fields["sentinel_pattern"].annotation is str
    assert fields["slot_bindings"].annotation == dict[str, str]
