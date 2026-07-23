"""Unit tests for the theme contract schema (storybook/theme_contract.py)."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import (
    SLOT_TOKEN_RE,
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
    slot_ids,
)


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
