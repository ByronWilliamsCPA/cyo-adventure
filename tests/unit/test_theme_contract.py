"""Unit tests for the theme contract schema (storybook/theme_contract.py)."""

from typing import cast

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.generation.binding import render_bound_skeleton
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.sentinels import wrap
from cyo_adventure.storybook.theme_contract import (
    PERSONALIZATION_FIELDS,
    REAL_PERSON_PERSONALIZATION_FIELDS,
    SLOT_TOKEN_RE,
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
    first_name_pin_error,
    slot_ids,
)

# Mark every test in this module as a unit test, consistent with the sibling
# unit-test modules, so it is selected by a `-m unit` run (this file is all
# synchronous, so no asyncio marker interaction applies).
pytestmark = pytest.mark.unit


def _slot(
    slot_id: str,
    *,
    scope: SlotScope = SlotScope.GLOBAL,
    meaning: str = "a placeholder meaning",
    constraints: SlotConstraints | None = None,
) -> SlotSpec:
    return SlotSpec(
        id=slot_id,
        scope=scope,
        meaning=meaning,
        constraints=constraints or SlotConstraints(),
    )


def _contract(
    slots: list[SlotSpec],
    default_binding: dict[str, str],
    *,
    legacy_lexicon: list[str] | None = None,
    age_band: AgeBand = AgeBand.BAND_8_11,
) -> ThemeContract:
    return ThemeContract(
        contract_version=1,
        skeleton_slug="the-cave-of-echoes",
        age_band=age_band,
        legacy_lexicon=legacy_lexicon or [],
        default_binding=default_binding,
        slots=slots,
    )


def test_schema_round_trip():
    contract = _contract(
        [
            _slot("HERO"),
            _slot(
                "A1_GATE",
                scope=SlotScope.TRACK,
                constraints=SlotConstraints(max_words=8, forbid=["lethal"]),
            ),
        ],
        {"HERO": "Priya", "A1_GATE": "the jammed pressure hatch"},
    )
    dumped = contract.model_dump(mode="json")
    reloaded = ThemeContract.model_validate(dumped)
    assert reloaded == contract


def test_rejects_duplicate_slot_ids():
    slots = [_slot("HERO"), _slot("HERO")]
    with pytest.raises(PydanticValidationError, match="duplicate slot id"):
        _contract(slots, {"HERO": "Priya"})


def test_rejects_undeclared_distinct_from_reference():
    slots = [
        _slot(
            "HERO",
            constraints=SlotConstraints(distinct_from=["COMPANION"]),
        )
    ]
    with pytest.raises(PydanticValidationError, match="undeclared slot id"):
        _contract(slots, {"HERO": "Priya"})


def test_rejects_default_binding_missing_a_declared_key():
    slots = [_slot("HERO"), _slot("COMPANION")]
    with pytest.raises(PydanticValidationError, match="missing"):
        _contract(slots, {"HERO": "Priya"})


def test_rejects_default_binding_with_an_extra_key():
    slots = [_slot("HERO")]
    with pytest.raises(PydanticValidationError, match="extra"):
        _contract(slots, {"HERO": "Priya", "COMPANION": "Sam"})


def test_rejects_blank_forbid_bundle_id():
    slots = [_slot("HERO", constraints=SlotConstraints(forbid=["  "]))]
    with pytest.raises(PydanticValidationError, match="empty/blank forbid bundle id"):
        _contract(slots, {"HERO": "Priya"})


def test_slot_id_grammar_rejects_non_screaming_snake_case():
    with pytest.raises(PydanticValidationError):
        SlotSpec(id="a1_gate", scope=SlotScope.TRACK, meaning="lowercase id")


def test_slot_id_grammar_rejects_leading_digit():
    with pytest.raises(PydanticValidationError):
        SlotSpec(id="1BAD", scope=SlotScope.TRACK, meaning="leading digit")


@pytest.mark.parametrize(
    "model_factory",
    [
        lambda: SlotConstraints(unknown_field=1),  # type: ignore[call-arg]
        lambda: SlotSpec(
            id="HERO", scope=SlotScope.GLOBAL, meaning="m", unknown_field=1
        ),  # type: ignore[call-arg]
    ],
)
def test_extra_forbid_rejects_unknown_keys(model_factory):
    with pytest.raises(PydanticValidationError):
        model_factory()


def test_theme_contract_extra_forbid_rejects_unknown_keys():
    slots = [_slot("HERO")]
    with pytest.raises(PydanticValidationError):
        ThemeContract(
            contract_version=1,
            skeleton_slug="slug",
            age_band=AgeBand.BAND_8_11,
            default_binding={"HERO": "Priya"},
            slots=slots,
            unknown_field=1,  # type: ignore[call-arg]
        )


def test_slot_token_re_extracts_screaming_snake_tokens():
    text = "The {HERO} approaches {A1_GATE} near {lower} and {1BAD}."
    matches = SLOT_TOKEN_RE.findall(text)
    assert matches == ["HERO", "A1_GATE"]


def test_slot_ids_helper_returns_every_declared_id():
    contract = _contract(
        [_slot("HERO"), _slot("COMPANION")],
        {"HERO": "Priya", "COMPANION": "Sam"},
    )
    assert slot_ids(contract) == frozenset({"HERO", "COMPANION"})


def test_default_constraints_have_expected_values():
    constraints = SlotConstraints()
    assert constraints.max_words == 8
    assert constraints.forbid == []
    assert constraints.distinct_from == []
    assert constraints.pattern is None


def test_max_words_bounds_are_enforced():
    with pytest.raises(PydanticValidationError):
        SlotConstraints(max_words=0)
    with pytest.raises(PydanticValidationError):
        SlotConstraints(max_words=17)
    assert SlotConstraints(max_words=16).max_words == 16


# ---------------------------------------------------------------------------
# SlotSpec.kind (P1b, ADR-023)
# ---------------------------------------------------------------------------


def test_slot_kind_defaults_to_theme():
    slot = _slot("HERO")
    assert slot.kind == "theme"
    assert slot.personalization_field is None
    assert slot.role_safety is None


def test_personalization_fields_vocabulary_is_closed():
    assert (
        frozenset(
            {
                "protagonist_first_name",
                "pronoun_set",
                "sibling_name",
                "pet_species",
                "pet_name",
                "kinship_label",
                "favorite_color",
                "favorite_food",
                "favorite_hobby",
                "home_type",
                "dedication",
                # ADR-028: the persistent-character's name, the twelfth slot.
                # See storybook.theme_contract.PERSONALIZATION_FIELDS's own
                # comment for the full rationale; this test is a second,
                # hand-maintained mirror of that set, drift-guarded the same
                # way tests/unit/test_personalization_vocab_drift.py mirrors
                # the DB-side copies.
                "character_name",
            }
        )
        == PERSONALIZATION_FIELDS
    )
    assert (
        frozenset({"protagonist_first_name", "sibling_name", "character_name"})
        == REAL_PERSON_PERSONALIZATION_FIELDS
    )
    # Every real-person field must itself be a member of the full vocabulary.
    assert REAL_PERSON_PERSONALIZATION_FIELDS <= PERSONALIZATION_FIELDS


def test_personalizable_slot_with_valid_field_and_no_role_safety_needed():
    slot = SlotSpec(
        id="PET_NAME",
        scope=SlotScope.GLOBAL,
        meaning="the pet's name",
        kind="personalizable",
        personalization_field="pet_name",
    )
    assert slot.kind == "personalizable"
    assert slot.personalization_field == "pet_name"


def test_personalizable_slot_requires_a_personalization_field():
    slots = [_slot("HERO", constraints=SlotConstraints())]
    slots[0] = slots[0].model_copy(update={"kind": "personalizable"})
    with pytest.raises(PydanticValidationError, match="personalization_field"):
        _contract(slots, {"HERO": "Priya"})


def test_personalizable_slot_rejects_an_unknown_personalization_field():
    slot = SlotSpec(
        id="HERO",
        scope=SlotScope.GLOBAL,
        meaning="m",
        kind="personalizable",
        personalization_field="not_a_real_field",
    )
    with pytest.raises(PydanticValidationError, match="personalization_field"):
        _contract([slot], {"HERO": "Priya"})


def test_real_person_field_requires_role_safety():
    slot = SlotSpec(
        id="HERO",
        scope=SlotScope.GLOBAL,
        meaning="m",
        kind="personalizable",
        personalization_field="protagonist_first_name",
    )
    with pytest.raises(PydanticValidationError, match="role_safety"):
        _contract([slot], {"HERO": "Priya"})


def test_real_person_field_with_role_safety_set_passes():
    slot = SlotSpec(
        id="HERO",
        scope=SlotScope.GLOBAL,
        meaning="m",
        kind="personalizable",
        personalization_field="protagonist_first_name",
        role_safety="protagonist",
    )
    contract = _contract([slot], {"HERO": "Priya"})
    assert contract.slots[0].role_safety == "protagonist"


def test_non_real_person_field_does_not_require_role_safety():
    slot = SlotSpec(
        id="PET_NAME",
        scope=SlotScope.GLOBAL,
        meaning="m",
        kind="personalizable",
        personalization_field="pet_name",
    )
    contract = _contract([slot], {"PET_NAME": "Buddy"})
    assert contract.slots[0].role_safety is None


def test_theme_slot_rejects_personalization_field():
    slot = SlotSpec(
        id="HERO",
        scope=SlotScope.GLOBAL,
        meaning="m",
        personalization_field="pet_name",
    )
    with pytest.raises(PydanticValidationError, match="kind='theme'"):
        _contract([slot], {"HERO": "Priya"})


def test_theme_slot_rejects_role_safety():
    slot = SlotSpec(
        id="HERO",
        scope=SlotScope.GLOBAL,
        meaning="m",
        role_safety="companion",
    )
    with pytest.raises(PydanticValidationError, match="kind='theme'"):
        _contract([slot], {"HERO": "Priya"})


# ---------------------------------------------------------------------------
# Personalizable slot default_binding validation (Task 2 review fix, ADR-023)
# ---------------------------------------------------------------------------


def _personalizable_slot(
    slot_id: str = "PET_NAME",
    *,
    personalization_field: str = "pet_name",
    constraints: SlotConstraints | None = None,
) -> SlotSpec:
    return SlotSpec(
        id=slot_id,
        scope=SlotScope.GLOBAL,
        meaning="the pet's name",
        kind="personalizable",
        personalization_field=personalization_field,
        constraints=constraints or SlotConstraints(),
    )


def test_personalizable_default_rejects_empty_value():
    slot = _personalizable_slot()
    with pytest.raises(PydanticValidationError, match="default_binding value"):
        _contract([slot], {"PET_NAME": ""})


def test_personalizable_default_rejects_whitespace_only_value():
    slot = _personalizable_slot()
    with pytest.raises(PydanticValidationError, match="default_binding value"):
        _contract([slot], {"PET_NAME": "   "})


def test_personalizable_default_rejects_value_exceeding_max_words():
    slot = _personalizable_slot(constraints=SlotConstraints(max_words=2))
    with pytest.raises(PydanticValidationError, match="max_words"):
        _contract([slot], {"PET_NAME": "a very long pet name indeed"})


def test_personalizable_default_rejects_forbidden_bundle_term():
    slot = _personalizable_slot(constraints=SlotConstraints(forbid=["lethal"]))
    with pytest.raises(PydanticValidationError, match="forbid:lethal"):
        _contract([slot], {"PET_NAME": "a deadly pet"})


def test_personalizable_default_rejects_wrap_forbidden_char():
    """A value ``validate_slot_bindings`` accepts (no doubled `<<`/`>>`) but
    `wrap` rejects (a lone apostrophe) must still be rejected at contract
    construction, since it would otherwise crash `render_bound_skeleton`.
    """
    slot = _personalizable_slot()
    with pytest.raises(PydanticValidationError, match="sentinel-safe"):
        _contract([slot], {"PET_NAME": "Buddy's"})


def test_personalizable_default_valid_value_constructs_binds_and_renders():
    """A regression/positive-path check: a valid personalizable contract still
    constructs, and its default renders cleanly through the real bind/render
    pipeline (`generation/binding.py`).
    """
    slot = _personalizable_slot()
    contract = _contract([slot], {"PET_NAME": "Buddy"})
    assert contract.slots[0].kind == "personalizable"

    skeleton: dict[str, object] = {
        "schema_version": "2.0",
        "id": "s_test_personalizable_default",
        "version": 1,
        "title": "Test Story",
        "metadata": {
            "age_band": "3-5",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 1.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": ["adventure"],
            "estimated_minutes": 5,
            "ending_count": 2,
            "topology": "time_cave",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    "<<FILL role=setup words=40 "
                    "beats='Meet {PET_NAME} at the door and choose a path.'>>"
                ),
                "is_ending": False,
                "choices": [
                    {"id": "c_a", "label": "Go inside.", "target": "n_end_a"},
                    {"id": "c_b", "label": "Stay outside.", "target": "n_end_b"},
                ],
            },
            {
                "id": "n_end_a",
                "body": (
                    "<<FILL role=ending words=30 beats='They go home together.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Home Again",
                },
                "choices": [],
            },
            {
                "id": "n_end_b",
                "body": (
                    "<<FILL role=ending words=30 beats='They wait a while longer.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "neutral",
                    "kind": "completion",
                    "title": "A Quiet Evening",
                },
                "choices": [],
            },
        ],
    }
    bound = render_bound_skeleton(
        skeleton,
        {"PET_NAME": "Buddy"},
        personalizable_slots=frozenset({"PET_NAME"}),
    )
    nodes = cast("list[dict[str, object]]", bound["nodes"])
    assert wrap("PET_NAME", "Buddy") in cast("str", nodes[0]["body"])


def test_personalizable_default_check_does_not_affect_theme_slot_defaults():
    """A `theme` slot's default is not subject to this invariant.

    The same value that would fail the personalizable check (too many words
    for a tight `max_words`) is left alone for a `theme` slot, proving the
    new invariant is scoped to `kind='personalizable'` only and cannot reject
    any existing (all-theme-slot) contract.
    """
    slot = _slot("HERO", constraints=SlotConstraints(max_words=1))
    contract = _contract([slot], {"HERO": "a name with several words in it"})
    assert contract.slots[0].kind == "theme"


# ---------------------------------------------------------------------------
# protagonist_first_name pin shape, and personalizable/theme value collisions
# (PR #759 review fix, ADR-023)
# ---------------------------------------------------------------------------

# Every value the catalog actually pinned that is not a first name, with the
# clause of the rule each one breaks. Stated as literals rather than read back
# from `skeletons/`, so fixing the catalog cannot also silence the test.
_BAD_FIRST_NAME_PINS = [
    ("a child of the opera house crew", "determiner"),
    ("a pilgrim", "determiner"),
    ("the pilot", "determiner"),
    ("auditor", "lowercase"),
    ("Captain Mira Voss", "whitespace"),
    ("Nell Marlow", "whitespace"),
    ("Noor Haddad", "whitespace"),
    ("Wren Ashby", "whitespace"),
]


def _first_name_slot(slot_id: str = "HERO") -> SlotSpec:
    return SlotSpec(
        id=slot_id,
        scope=SlotScope.GLOBAL,
        meaning="the protagonist",
        kind="personalizable",
        personalization_field="protagonist_first_name",
        role_safety="protagonist",
    )


@pytest.mark.parametrize(("value", "clause"), _BAD_FIRST_NAME_PINS)
def test_first_name_pin_rejects_every_shape_the_catalog_got_wrong(value, clause):
    """Each of the eight real bad pins is rejected, by the expected clause."""
    message = first_name_pin_error("HERO", value)
    assert message is not None
    assert clause in message

    # The slot is built OUTSIDE the raises block (S5778): if construction
    # itself raised, the block would pass without ever exercising the pin rule.
    slot = _first_name_slot()
    with pytest.raises(PydanticValidationError, match="protagonist_first_name"):
        _contract([slot], {"HERO": value})


@pytest.mark.parametrize(
    "value", ["Mira", "Nell", "Noor", "Wren", "Mary-Kate", "O'Brien"]
)
def test_first_name_pin_accepts_a_plain_given_name(value):
    """A single given-name token passes, hyphens and apostrophes included."""
    assert first_name_pin_error("HERO", value) is None


def test_first_name_pin_theme_slot_with_a_role_phrase_is_untouched():
    """The rule is scoped to personalizable slots, so no theme pin can fail it.

    This is what makes the four excluded role-phrase skeletons legal: their
    ``HERO`` pin is unchanged, only its ``kind`` is.
    """
    contract = _contract([_slot("HERO")], {"HERO": "a child of the opera house crew"})
    assert contract.slots[0].kind == "theme"


def test_personalizable_value_inside_a_theme_slot_value_is_rejected():
    """The vanishing-orchard shape: HERO 'Rowan' beside HERO_FULL 'Rowan Ashby'.

    Only ``HERO`` is rewritten at read time, so a personalized book would open
    with the authored full name and then use the family's chosen name for the
    rest of the story.
    """
    slots = [_first_name_slot(), _slot("HERO_FULL", meaning="the full name")]
    with pytest.raises(PydanticValidationError, match="HERO_FULL"):
        _contract(slots, {"HERO": "Rowan", "HERO_FULL": "Rowan Ashby"})


def test_personalizable_value_echoed_in_lowercase_is_accepted():
    """A common-word echo is not a second naming surface.

    The 3-5 band pins ``HERO`` to "Twinkle" beside a ``LULLABY_SONG`` of "a
    twinkle song", which names the nursery rhyme rather than the child. A
    case-insensitive rule would reject that real, correct contract.
    """
    slots = [_first_name_slot(), _slot("LULLABY_SONG", meaning="the lullaby")]
    contract = _contract(slots, {"HERO": "Twinkle", "LULLABY_SONG": "a twinkle song"})
    assert contract.default_binding["LULLABY_SONG"] == "a twinkle song"


def test_personalizable_value_inside_a_possessive_theme_value_is_rejected():
    """A possessive names the same character, so it must not survive the check."""
    slots = [_first_name_slot(), _slot("KEEPSAKE", meaning="the keepsake")]
    with pytest.raises(PydanticValidationError, match="KEEPSAKE"):
        _contract(slots, {"HERO": "Rowan", "KEEPSAKE": "Rowan's viola"})
