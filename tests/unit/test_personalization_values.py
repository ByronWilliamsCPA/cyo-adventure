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


def test_value_profile_id_on_non_sibling_slot_rejected() -> None:
    """A profile reference on a non-sibling slot is a shape violation.

    The hole this closes: `ck_cpp_exactly_one_value` counts NOT NULLs but
    never binds which column a slot_type may use, and every other check in
    the module reads only text/enum or is gated on the sibling slot type.
    A row with only `value_profile_id` set on `pet_name` therefore ran zero
    checks and validated clean, while the render path stringified the raw
    UUID into child-facing prose. The FK only requires the id to name SOME
    child_profile, including another family's.
    """
    violations = validate_personalization_value(
        "pet_name",
        AgeBand.BAND_8_11,
        value_profile_id=uuid.uuid4(),
    )

    assert [v.rule for v in violations] == ["value_shape"]


def test_value_profile_id_on_non_sibling_slot_rejected_even_with_family_ids() -> None:
    """Passing the family roster does not rescue a mis-shaped non-sibling value.

    The sibling-in-family check is gated on `slot_type == SIBLING_SLOT_TYPE`,
    so supplying `family_profile_ids` never applied it to another slot. The
    shape rule must reject regardless of whether the id happens to belong to
    the family.
    """
    own_profile = uuid.uuid4()
    violations = validate_personalization_value(
        "kinship_label",
        AgeBand.BAND_8_11,
        value_profile_id=own_profile,
        family_profile_ids=[own_profile],
    )

    assert [v.rule for v in violations] == ["value_shape"]


def test_sibling_slot_with_free_text_rejected() -> None:
    """The same cross-family hole entered from the other side.

    A sibling slot carrying free text skips the sibling-in-family check
    entirely, because that check only inspects `value_profile_id`.
    """
    violations = validate_personalization_value(
        SIBLING_SLOT_TYPE,
        AgeBand.BAND_8_11,
        value_text="Mira",
    )

    assert any(v.rule == "value_shape" for v in violations)


def test_closed_vocabulary_slot_with_free_text_rejected() -> None:
    """Free text on a closed-vocabulary slot cannot bypass the vocabulary gate.

    `CLOSED_VOCABULARIES` ships every entry empty on purpose (fail-closed),
    but the membership check only ran when `value_enum` was set, so the
    fail-closed vocabulary was one JSON field name away from unbounded free
    text.
    """
    for slot_type in CLOSED_VOCABULARIES:
        violations = validate_personalization_value(
            slot_type,
            AgeBand.BAND_8_11,
            value_text="fire-breathing wyvern",
        )

        assert any(v.rule == "value_shape" for v in violations), slot_type


def test_enum_membership_message_never_contains_the_candidate() -> None:
    """The rejection message names the slot, never the guardian-typed value.

    `SlotViolation.message`'s contract is that it never contains candidate
    text. This message reaches `logger.warning("project_error", ...)` and the
    422 body, and every vocabulary ships empty, so EVERY enum submission for
    these slots takes this branch. `kinship_label` is designed to hold values
    like "Grandma Rosita"; application logs have no erasure path.
    """
    candidate = "Grandma Rosita"
    violations = validate_personalization_value(
        "kinship_label",
        AgeBand.BAND_8_11,
        value_enum=candidate,
    )

    membership = [v for v in violations if v.rule == "enum_membership"]
    assert membership, "expected the fail-closed vocabulary to reject"
    assert all(candidate not in v.message for v in membership)
    assert all("kinship_label" in v.message for v in membership)


def test_pronoun_set_shape_is_deliberately_unconstrained() -> None:
    """`pronoun_set` keeps accepting free text; no design doc states its shape.

    Pinned so the omission reads as a decision rather than an oversight. The
    existing fixtures (`measurement/fixtures.py`) use free text.
    """
    violations = validate_personalization_value(
        "pronoun_set",
        AgeBand.BAND_8_11,
        value_text="they/them",
    )

    assert violations == []


def test_payload_rejection_reports_rules_through_on_reject() -> None:
    """A value dropped at render time hands its rules to the `on_reject` hook.

    Dropping is correct (ADR-023's render-time fallback contract), but a
    value reaching this point invalid was accepted at write time and has
    since gone bad; without the hook the same row fails on every render and
    nothing ever surfaces it.
    """
    seen: list[list[str]] = []

    result = personalization_value_for_payload(
        "pet_species",
        AgeBand.BAND_5_8,
        value_enum="not-in-the-vocabulary",
        on_reject=lambda violations: seen.append([v.rule for v in violations]),
    )

    assert result is None
    assert seen == [["enum_membership"]]


def test_on_reject_is_not_called_for_a_valid_value() -> None:
    """The hook fires only on rejection, never as a per-slot heartbeat."""
    calls: list[object] = []

    result = personalization_value_for_payload(
        "protagonist_first_name",
        AgeBand.BAND_5_8,
        value_text="Rosa",
        on_reject=calls.append,
    )

    assert result == "Rosa"
    assert calls == []


def test_dedication_rejects_free_text() -> None:
    """A dedication is a closed kinship enum, never guardian-authored prose.

    Design plan section 9: "a free-text dedication would be a new unmoderated-prose
    surface on a kid-facing screen, which is the one thing this whole architecture
    exists to avoid". Before this test, `dedication` was absent from
    CLOSED_VOCABULARIES, so `_shape_violations` permitted value_text and the
    membership check never ran.
    """
    violations = validate_personalization_value(
        "dedication",
        AgeBand.BAND_8_11,
        value_text="anything at all",
    )

    assert [v.rule for v in violations] == ["value_shape"]


def test_dedication_enum_is_rejected_until_a_vocabulary_ships() -> None:
    """Fail-closed, exactly like the other four enum slots."""
    violations = validate_personalization_value(
        "dedication",
        AgeBand.BAND_8_11,
        value_enum="Grandma",
    )

    assert violations != []
