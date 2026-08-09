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
    CHARACTER_NAME_SLOT_TYPE,
    CLOSED_VOCABULARIES,
    SIBLING_SLOT_TYPE,
    character_name_violations,
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
        "favorite_hobby",
        AgeBand.BAND_5_8,
        value_enum="a sharpened steel sword",
    )

    assert any(v.rule == "forbid:weapon" for v in violations)


def test_validate_personalization_value_enum_non_membership_rejected() -> None:
    """A candidate not in the slot's closed vocabulary is rejected.

    Task D6 seeded the real, owner-accepted lists (ADR-023 rows 4a/5/6/7/8,
    `personalization-closed-vocabularies-proposal.md`), so `CLOSED_VOCABULARIES`
    entries are finite closed lists rather than the empty, fail-closed
    placeholders they shipped as before acceptance; a candidate that is not
    itself a member is still rejected as "not a member".
    """
    assert "dragon" not in CLOSED_VOCABULARIES["pet_species"]

    violations = validate_personalization_value(
        "pet_species",
        AgeBand.BAND_8_11,
        value_enum="dragon",
    )

    assert any(v.rule == "enum_membership" for v in violations)


def test_validate_personalization_value_enum_membership_accepted() -> None:
    """A candidate that IS a member of the seeded vocabulary raises no violation."""
    assert "dog" in CLOSED_VOCABULARIES["pet_species"]

    violations = validate_personalization_value(
        "pet_species",
        AgeBand.BAND_8_11,
        value_enum="dog",
    )

    assert violations == []


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

    The hole this closes: `ck_cpp_value_cardinality` counts NOT NULLs but
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

    A closed-vocabulary slot must use `value_enum`, never `value_text`,
    regardless of whether the slot's vocabulary is seeded or (as every entry
    shipped before Task D6) still empty: the membership check only runs when
    `value_enum` is set, so without this shape rule a closed vocabulary would
    be one JSON field name away from unbounded free text.
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
    422 body. `kinship_label`'s seeded vocabulary holds the bare address term
    ("Grandma") but not a name-qualified variant ("Grandma Rosita"), so this
    candidate is rejected as a non-member; application logs have no erasure
    path, so the message must never echo it.
    """
    candidate = "Grandma Rosita"
    assert candidate not in CLOSED_VOCABULARIES["kinship_label"]
    violations = validate_personalization_value(
        "kinship_label",
        AgeBand.BAND_8_11,
        value_enum=candidate,
    )

    membership = [v for v in violations if v.rule == "enum_membership"]
    assert membership, "expected the seeded vocabulary to reject a non-member"
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


def test_dedication_enum_accepts_a_member_of_its_seeded_vocabulary() -> None:
    """A dedication enum value that IS in the (kinship_label-shared) list passes.

    Task D6 seeded `dedication` with the same 21-value kinship list as
    `kinship_label` (ADR-023 row 8: the "from" kinship on a dedication can
    legitimately differ from the in-story trusted-adult kinship, so it is a
    separate key sharing the same closed vocabulary).
    """
    assert "Grandma" in CLOSED_VOCABULARIES["dedication"]
    violations = validate_personalization_value(
        "dedication",
        AgeBand.BAND_8_11,
        value_enum="Grandma",
    )

    assert violations == []


def test_character_name_slot_with_any_value_column_rejected() -> None:
    """`character_name` carries no value in any of the three value columns.

    Its value is synthesized at resolve time from the child's active
    character, so a row that carries one anyway is mis-shaped: no other check
    in this module reads it (the slot has no vocabulary and no profile
    reference), and the resolver never looks at it, so it would sit in the
    row looking authoritative while influencing nothing.
    """
    for kwargs in (
        {"value_text": "Zephyr"},
        {"value_enum": "Zephyr"},
        {"value_profile_id": uuid.uuid4()},
    ):
        violations = validate_personalization_value(
            CHARACTER_NAME_SLOT_TYPE,
            AgeBand.BAND_8_11,
            **kwargs,  # pyright: ignore[reportArgumentType]
        )

        assert any(v.rule == "value_shape" for v in violations), kwargs


def test_character_name_violations_rejects_a_sentinel_shaped_name() -> None:
    """A child-authored name shaped like a sentinel token must never render.

    The resolved payload ships the character name beside `SENTINEL_RE.pattern`
    for substitution into story prose, so a name carrying the sentinel's own
    braces is a template-forgery vector.
    """
    violations = character_name_violations("{~HERO:friend~}", AgeBand.BAND_5_8)

    assert any(v.rule == "charset" for v in violations)
    assert all(v.slot_id == CHARACTER_NAME_SLOT_TYPE for v in violations)


def test_character_name_violations_rejects_a_control_character() -> None:
    """A name carrying a control character is rejected by the structural guard."""
    violations = character_name_violations("Ro\x07sa", AgeBand.BAND_5_8)

    assert any(v.rule == "single_line" for v in violations)
    assert all(v.slot_id == CHARACTER_NAME_SLOT_TYPE for v in violations)


def test_character_name_violations_rejects_a_band_denylisted_name() -> None:
    """A name matching the band-mandatory denylist floor is rejected.

    The denylist is band-scoped, so the check needs the subject profile's age
    band rather than a global list.
    """
    violations = character_name_violations("Captain Sword", AgeBand.BAND_5_8)

    assert any(v.rule == "forbid:weapon" for v in violations)
    assert all(v.slot_id == CHARACTER_NAME_SLOT_TYPE for v in violations)


def test_character_name_violations_message_never_contains_the_name() -> None:
    """A rejection message names the rule, never the child-authored name.

    `SlotViolation.message` reaches structured logs, which have no erasure
    path; a child's own free text must not land there.
    """
    name = "Captain Sword"
    violations = character_name_violations(name, AgeBand.BAND_5_8)

    assert violations
    assert all(name not in v.message for v in violations)


def test_character_name_violations_accepts_an_ordinary_name() -> None:
    """An ordinary child-authored name raises no violation and renders."""
    assert character_name_violations("Biscuit", AgeBand.BAND_5_8) == []


def test_dedication_enum_non_member_is_rejected() -> None:
    """A dedication enum value NOT in the seeded vocabulary is rejected.

    Before Task D6 seeded the list, this slot rejected every candidate
    fail-closed (the vocabulary was empty); it now rejects only non-members.
    """
    assert "Grandma Rosita" not in CLOSED_VOCABULARIES["dedication"]
    violations = validate_personalization_value(
        "dedication",
        AgeBand.BAND_8_11,
        value_enum="Grandma Rosita",
    )

    assert any(v.rule == "enum_membership" for v in violations)
