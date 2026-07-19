"""Unit tests for the deterministic pre-fill slot validator (validator/slots.py)."""

from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import (
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
)
from cyo_adventure.validator.slots import (
    DENYLIST_VERSION,
    band_mandatory_bundles,
    validate_slot_bindings,
)


def _slot(
    slot_id: str,
    *,
    scope: SlotScope = SlotScope.GLOBAL,
    constraints: SlotConstraints | None = None,
) -> SlotSpec:
    return SlotSpec(
        id=slot_id,
        scope=scope,
        meaning=f"placeholder meaning for {slot_id}",
        constraints=constraints or SlotConstraints(),
    )


def _make_contract(age_band: AgeBand = AgeBand.BAND_8_11) -> ThemeContract:
    """A small hand-authored fixture contract covering every slot role used below."""
    return ThemeContract(
        contract_version=1,
        skeleton_slug="the-cave-of-echoes",
        age_band=age_band,
        legacy_lexicon=["Maya"],
        default_binding={
            "HERO": "Priya",
            "COMPANION": "Sam",
            "A1_GATE": "the jammed pressure hatch",
            "ROUTE_A_LURE": "a glinting tide pool",
            "ROUTE_B_LURE": "an echoing stone archway",
            "CODE_SLOT": "ValidCode",
        },
        slots=[
            _slot(
                "HERO",
                constraints=SlotConstraints(
                    max_words=6, forbid=["weapon"], distinct_from=["COMPANION"]
                ),
            ),
            _slot(
                "COMPANION",
                constraints=SlotConstraints(
                    max_words=6, forbid=["weapon"], distinct_from=["HERO"]
                ),
            ),
            _slot(
                "A1_GATE",
                scope=SlotScope.TRACK,
                constraints=SlotConstraints(max_words=8),
            ),
            _slot(
                "ROUTE_A_LURE",
                scope=SlotScope.ROUTE,
                constraints=SlotConstraints(
                    max_words=6, distinct_from=["ROUTE_B_LURE"]
                ),
            ),
            _slot(
                "ROUTE_B_LURE",
                scope=SlotScope.ROUTE,
                constraints=SlotConstraints(
                    max_words=6, distinct_from=["ROUTE_A_LURE"]
                ),
            ),
            _slot(
                "CODE_SLOT",
                constraints=SlotConstraints(pattern=r"[A-Za-z]+"),
            ),
        ],
    )


def test_fully_valid_default_binding_passes():
    contract = _make_contract()
    assert validate_slot_bindings(contract, contract.default_binding) == []


def test_completeness_flags_a_missing_slot():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    del bindings["HERO"]
    violations = validate_slot_bindings(contract, bindings)
    assert any(
        v.rule == "completeness" and v.slot_id == "" and "HERO" in v.message
        for v in violations
    )


def test_completeness_flags_an_undeclared_key():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["BOGUS"] = "extra value"
    violations = validate_slot_bindings(contract, bindings)
    assert any(
        v.rule == "completeness" and v.slot_id == "" and "BOGUS" in v.message
        for v in violations
    )


def test_non_empty_rejects_blank_value():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["HERO"] = "   "
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "non_empty" and v.slot_id == "HERO" for v in violations)


def test_single_line_rejects_newline():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "the jammed hatch\nsecond line"
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "single_line" and v.slot_id == "A1_GATE" for v in violations)


def test_charset_rejects_brace_token():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "a gate guarded by {X}"
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "charset" and v.slot_id == "A1_GATE" for v in violations)


def test_charset_rejects_fill_directive_marker():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "<<FILL role=setup words=10 beats='x'>>"
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "charset" and v.slot_id == "A1_GATE" for v in violations)


def test_charset_rejects_em_dash():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "the jammed hatch \u2014 sealed shut"
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "charset" and v.slot_id == "A1_GATE" for v in violations)


def test_charset_rejects_overlong_value():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "a " * 65  # far over the 120-character limit
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "charset" and v.slot_id == "A1_GATE" for v in violations)


def test_fence_guard_rejects_untrusted_input_marker():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "UNTRUSTED_USER_INPUT leaked into a slot value"
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "fence_guard" and v.slot_id == "A1_GATE" for v in violations)


def test_max_words_rejects_value_over_the_cap():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = " ".join(["word"] * 9)  # cap is 8
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "max_words" and v.slot_id == "A1_GATE" for v in violations)


def test_forbid_lethal_blocks_a_lethal_gate_binding():
    """The owner-named case: a chasm that kills anyone who falls."""
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "a chasm that Kills anyone who falls"
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "forbid:lethal" and v.slot_id == "A1_GATE" for v in violations)


def test_forbid_does_not_false_positive_on_a_word_boundary_near_miss():
    """'skillful' contains the substring 'kill' but must not match \\bkill\\b."""
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "a skillful navigator crosses the bridge"
    violations = validate_slot_bindings(contract, bindings)
    assert not any(v.rule.startswith("forbid:") for v in violations)


def test_band_mandatory_union_blocks_lethal_even_when_contract_omits_it():
    """Proves the floor lives in the validator, not the contract data.

    A1_GATE's own constraints declare no `forbid` bundles at all (see
    _make_contract), yet an 8-11 band contract must still reject a lethal
    value because validator/slots.py unions the band-mandatory floor in
    unconditionally.
    """
    contract = _make_contract(age_band=AgeBand.BAND_8_11)
    slot = next(s for s in contract.slots if s.id == "A1_GATE")
    assert slot.constraints.forbid == []
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "a pit that kills anyone who falls"
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "forbid:lethal" and v.slot_id == "A1_GATE" for v in violations)


def test_band_mandatory_union_has_no_floor_for_the_oldest_bands():
    """13-16/16+ contracts are not forced to forbid lethal content on every slot."""
    contract = _make_contract(age_band=AgeBand.BAND_13_16)
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "a pit that kills anyone who falls"
    violations = validate_slot_bindings(contract, bindings)
    assert not any(v.rule.startswith("forbid:") for v in violations)


def test_band_mandatory_bundles_matches_the_design_table():
    assert band_mandatory_bundles(AgeBand.BAND_3_5) == frozenset(
        {"lethal", "capture", "weapon", "toxic", "graphic", "despair"}
    )
    assert band_mandatory_bundles(AgeBand.BAND_5_8) == frozenset(
        {"lethal", "capture", "weapon", "toxic", "graphic", "despair"}
    )
    assert band_mandatory_bundles(AgeBand.BAND_8_11) == frozenset(
        {"lethal", "toxic", "graphic"}
    )
    assert band_mandatory_bundles(AgeBand.BAND_10_13) == frozenset({"graphic"})
    assert band_mandatory_bundles(AgeBand.BAND_13_16) == frozenset()
    assert band_mandatory_bundles(AgeBand.BAND_16_PLUS) == frozenset()


def test_band_mandatory_bundles_covers_every_age_band():
    for band in AgeBand:
        assert isinstance(band_mandatory_bundles(band), frozenset)


def test_distinct_from_rejects_equal_values():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["ROUTE_A_LURE"] = "a hidden cove"
    bindings["ROUTE_B_LURE"] = "a hidden cove"
    violations = validate_slot_bindings(contract, bindings)
    assert any(
        v.rule == "distinct_from" and v.slot_id == "ROUTE_A_LURE" for v in violations
    )


def test_distinct_from_rejects_high_token_overlap():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["ROUTE_A_LURE"] = "a hidden shining cove"
    bindings["ROUTE_B_LURE"] = "a hidden shining bay"
    violations = validate_slot_bindings(contract, bindings)
    assert any(
        v.rule == "distinct_from" and v.slot_id == "ROUTE_A_LURE" for v in violations
    )


def test_legacy_lexicon_leak_is_rejected():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["HERO"] = "Maya"
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "legacy_lexicon" and v.slot_id == "HERO" for v in violations)


def test_pattern_rejects_non_matching_value():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["CODE_SLOT"] = "Bad Code!"
    violations = validate_slot_bindings(contract, bindings)
    assert any(v.rule == "pattern" and v.slot_id == "CODE_SLOT" for v in violations)


def test_pattern_accepts_matching_value():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["CODE_SLOT"] = "AnotherValidCode"
    violations = validate_slot_bindings(contract, bindings)
    assert not any(v.rule == "pattern" for v in violations)


def test_is_a_pure_function_same_input_same_output():
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["A1_GATE"] = "a pit that kills anyone who falls"
    first = validate_slot_bindings(contract, bindings)
    second = validate_slot_bindings(contract, dict(bindings))
    assert first == second
    assert first == validate_slot_bindings(contract, bindings)


def test_denylist_version_is_stamped():
    assert isinstance(DENYLIST_VERSION, int)
    assert DENYLIST_VERSION >= 1


def test_legacy_lexicon_tolerates_a_blank_entry_without_matching_everything():
    """An empty legacy_lexicon stem must never match (defensive: not a wildcard)."""
    contract = _make_contract()
    contract = contract.model_copy(update={"legacy_lexicon": ["Maya", ""]})
    bindings = dict(contract.default_binding)
    violations = validate_slot_bindings(contract, bindings)
    assert not any(v.rule == "legacy_lexicon" for v in violations)


def test_distinct_from_handles_both_sibling_values_blank():
    """Both siblings blank exercises the empty-token-set Jaccard branch."""
    contract = _make_contract()
    bindings = dict(contract.default_binding)
    bindings["ROUTE_A_LURE"] = ""
    bindings["ROUTE_B_LURE"] = ""
    violations = validate_slot_bindings(contract, bindings)
    assert any(
        v.rule == "distinct_from" and v.slot_id == "ROUTE_A_LURE" for v in violations
    )
