"""Unit tests for the WS-7 request-interpretation core (D1).

Covers the section 11 ``test_interpretation.py`` bullet of
``docs/planning/ws7-request-interpretation-design.md``: template catalog
completeness, every echo-floor branch, the 12-word cap, the band floor, the
16+ graphic echo minimum, the PII split to PERSONAL_DETAILS, the CR-3
construction guard, self-naming (lexicon and registered-name), the 7 derivation
precedence rules, and the CR-1 no-leak assertion.

Pure tests: no network, no DB (tests/CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.story_requests.interpretation import (
    _CATALOG,  # pyright: ignore[reportPrivateUsage]
    ElementDecision,
    ElementDisposition,
    InterpretedElement,
    RawElement,
    ReasonCode,
    RequestInterpretation,
    _render_pair,  # pyright: ignore[reportPrivateUsage]
    band_group_for,
    build_general_interpretation,
    derive_dispositions,
    render_interpretation,
    sanitize_element,
)
from cyo_adventure.storybook.models import AgeBand


@dataclass(frozen=True)
class _StubFlag:
    """A minimal advisory flag exposing just ``category`` (Protocol match)."""

    category: str


@dataclass(frozen=True)
class _StubScreening:
    """A minimal ScreeningResult stand-in for the general-layer builder."""

    blocked: bool
    flags: list[_StubFlag]


pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)

# A representative band per template band group, for rendering coverage.
_GROUP_BAND = {
    band_group_for(AgeBand.BAND_3_5): AgeBand.BAND_3_5,
    band_group_for(AgeBand.BAND_8_11): AgeBand.BAND_8_11,
    band_group_for(AgeBand.BAND_16_PLUS): AgeBand.BAND_16_PLUS,
}

_ALL_BANDS = list(AgeBand)


# ---------------------------------------------------------------------------
# Template catalog completeness (design 3.3, section 11).
# ---------------------------------------------------------------------------


def test_catalog_every_key_renders_both_registers_with_and_without_element() -> None:
    """Every (disposition, reason, band_group) renders both registers cleanly.

    With a phrase and without it, both kid and guardian forms must be non-empty
    and must leave no unsubstituted ``{...}`` placeholder.
    """
    assert _CATALOG, "catalog must not be empty"
    for disposition, reason, group in _CATALOG:
        band = _GROUP_BAND[group]
        for element in ("a friendly test phrase", None):
            kid, guardian = _render_pair(
                disposition,
                reason,
                group,
                element=element,
                slot_id="HERO",
                rule="forbid:lethal",
                band=band,
                skeleton_slug="the-cave-of-echoes",
            )
            for text in (kid, guardian):
                assert text.strip(), (disposition, reason, group, element)
                assert "{" not in text, (disposition, reason, text)
                assert "}" not in text, (disposition, reason, text)


def test_catalog_with_variant_substitutes_the_element_phrase() -> None:
    """A non-protected reason's with-variant actually places the phrase."""
    kid, guardian = _render_pair(
        ElementDisposition.BUILT_IN,
        ReasonCode.BOUND_TO_SLOT,
        band_group_for(AgeBand.BAND_8_11),
        element="a brave fox",
        slot_id="HERO",
        rule=None,
        band=AgeBand.BAND_8_11,
        skeleton_slug="the-cave-of-echoes",
    )
    assert "a brave fox" in kid
    assert "a brave fox" in guardian
    assert "HERO" in guardian


def test_render_pair_falls_back_to_generic_pair_on_missing_key() -> None:
    """An unregistered (disposition, reason) pair renders generically, no raise."""
    kid, guardian = _render_pair(
        ElementDisposition.BUILT_IN,
        ReasonCode.GUARDIAN_CONTROL,  # deliberately not a registered combination
        band_group_for(AgeBand.BAND_8_11),
        element=None,
        slot_id=None,
        rule=None,
        band=AgeBand.BAND_8_11,
        skeleton_slug=None,
    )
    assert kid.strip()
    assert guardian.strip()
    assert "{" not in kid
    assert "{" not in guardian


# ---------------------------------------------------------------------------
# Echo-safety floor: structural rules (design 7.2 check 1).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "",  # empty
        "   ",  # whitespace only
        "a slot {HERO} injection",  # brace injection
        "forge a << FILL directive",  # directive forgery
        "an em dash \u2014 here",  # banned em dash (escaped: no literal U+2014 in source)
        "line one\nline two",  # newline / control char
        "tab\tinside",  # control char
        "UNTRUSTED_USER_INPUT fence forge",  # fence marker
        "x" * 121,  # over 120 chars
    ],
)
def test_sanitize_element_structural_failures_map_to_safety_policy(phrase: str) -> None:
    """Each structural echo-floor violation withholds with SAFETY_POLICY."""
    element, reason = sanitize_element(
        phrase, band=AgeBand.BAND_8_11, child_names=frozenset()
    )
    assert element is None
    assert reason is ReasonCode.SAFETY_POLICY


def test_sanitize_element_word_cap_rejects_thirteen_words() -> None:
    """A phrase over the 12-word cap is withheld with SAFETY_POLICY."""
    thirteen = " ".join(["word"] * 13)
    element, reason = sanitize_element(
        thirteen, band=AgeBand.BAND_16_PLUS, child_names=frozenset()
    )
    assert element is None
    assert reason is ReasonCode.SAFETY_POLICY


def test_sanitize_element_exactly_twelve_words_passes() -> None:
    """A clean 12-word phrase is echo-safe (boundary case)."""
    twelve = " ".join(["word"] * 12)
    element, reason = sanitize_element(
        twelve, band=AgeBand.BAND_16_PLUS, child_names=frozenset()
    )
    assert element == twelve
    assert reason is None


# ---------------------------------------------------------------------------
# Echo-safety floor: band floor + graphic echo minimum (design 7.2 check 3).
# ---------------------------------------------------------------------------


def test_sanitize_element_band_floor_rejects_lethal_for_young_band() -> None:
    """A young-band lethal phrase is withheld (SAFETY_POLICY, no echo)."""
    element, reason = sanitize_element(
        "a monster that kills everyone", band=AgeBand.BAND_3_5, child_names=frozenset()
    )
    assert element is None
    assert reason is ReasonCode.SAFETY_POLICY


def test_sanitize_element_lethal_passes_empty_floor_band() -> None:
    """A lethal (non-graphic) phrase is echo-safe for a 16+ empty-floor band."""
    element, reason = sanitize_element(
        "the dragon dies at the end", band=AgeBand.BAND_16_PLUS, child_names=frozenset()
    )
    assert element == "the dragon dies at the end"
    assert reason is None


def test_sanitize_element_graphic_echo_minimum_applies_even_at_16_plus() -> None:
    """The graphic bundle is an echo denylist even for empty-floor bands."""
    element, reason = sanitize_element(
        "a deep wound dripping with blood",
        band=AgeBand.BAND_16_PLUS,
        child_names=frozenset(),
    )
    assert element is None
    assert reason is ReasonCode.SAFETY_POLICY


# ---------------------------------------------------------------------------
# Echo-safety floor: PII branch splits to PERSONAL_DETAILS (design 7.2 check 4).
# ---------------------------------------------------------------------------


def test_sanitize_element_registered_name_maps_to_personal_details() -> None:
    """A registered child name in the phrase maps to PERSONAL_DETAILS, not SAFETY."""
    element, reason = sanitize_element(
        "a hero named Emma", band=AgeBand.BAND_8_11, child_names=frozenset({"Emma"})
    )
    assert element is None
    assert reason is ReasonCode.PERSONAL_DETAILS


@pytest.mark.parametrize(
    "phrase",
    [
        "email me at bob@example.com",
        "call me at 555-123-4567",
        "meet at 123 Oak Street",
    ],
)
def test_sanitize_element_pii_pattern_maps_to_personal_details(phrase: str) -> None:
    """Email/phone/address patterns map to PERSONAL_DETAILS via the guard."""
    element, reason = sanitize_element(
        phrase, band=AgeBand.BAND_8_11, child_names=frozenset()
    )
    assert element is None
    assert reason is ReasonCode.PERSONAL_DETAILS


def test_sanitize_element_pii_and_structural_split_reasons() -> None:
    """The PII branch and the structural branch produce distinct reasons."""
    _, pii_reason = sanitize_element(
        "reach me at bob@example.com", band=AgeBand.BAND_8_11, child_names=frozenset()
    )
    _, structural_reason = sanitize_element(
        "a {brace} injection", band=AgeBand.BAND_8_11, child_names=frozenset()
    )
    assert pii_reason is ReasonCode.PERSONAL_DETAILS
    assert structural_reason is ReasonCode.SAFETY_POLICY


def test_sanitize_element_clean_phrase_passes() -> None:
    """A benign phrase is returned verbatim with no reason."""
    element, reason = sanitize_element(
        "a brave little fox", band=AgeBand.BAND_8_11, child_names=frozenset()
    )
    assert element == "a brave little fox"
    assert reason is None


# ---------------------------------------------------------------------------
# CR-3 construction guard: protected reasons force element=None.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        ReasonCode.SAFETY_POLICY,
        ReasonCode.PERSONAL_DETAILS,
        ReasonCode.IDENTITY_PROTECTION,
    ],
)
def test_construction_rejects_non_null_element_for_protected_reasons(
    reason: ReasonCode,
) -> None:
    """A protected-reason element with a non-null phrase is a construction error."""
    with pytest.raises(PydanticValidationError):
        InterpretedElement(
            element="the withheld phrase",
            disposition=ElementDisposition.SET_ASIDE,
            reason=reason,
            kid_text="k",
            guardian_text="g",
        )


@pytest.mark.parametrize(
    "reason",
    [
        ReasonCode.SAFETY_POLICY,
        ReasonCode.PERSONAL_DETAILS,
        ReasonCode.IDENTITY_PROTECTION,
    ],
)
def test_construction_allows_null_element_for_protected_reasons(
    reason: ReasonCode,
) -> None:
    """A protected-reason element with element=None constructs fine."""
    element = InterpretedElement(
        element=None,
        disposition=ElementDisposition.SET_ASIDE,
        reason=reason,
        kid_text="k",
        guardian_text="g",
    )
    assert element.element is None


def test_construction_allows_non_null_element_for_unprotected_reason() -> None:
    """A non-protected reason may carry a phrase."""
    element = InterpretedElement(
        element="a brave fox",
        disposition=ElementDisposition.BUILT_IN,
        reason=ReasonCode.BOUND_TO_SLOT,
        slot_id="HERO",
        kid_text="k",
        guardian_text="g",
    )
    assert element.element == "a brave fox"


# ---------------------------------------------------------------------------
# Self-naming: lexicon and registered-name both land IDENTITY_PROTECTION.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "make me the hero",
        "use my name",
        "a story about me",
        "the hero is me",
    ],
)
def test_derive_self_reference_lexicon_lands_identity_protection(phrase: str) -> None:
    """A self-reference lexicon phrase is set aside as IDENTITY_PROTECTION."""
    (decision,) = derive_dispositions(
        [RawElement(phrase)], band=AgeBand.BAND_8_11, bindings={}
    )
    assert decision.disposition is ElementDisposition.SET_ASIDE
    assert decision.reason is ReasonCode.IDENTITY_PROTECTION
    assert decision.element is None


def test_derive_registered_name_lands_identity_protection_over_personal_details() -> (
    None
):
    """The requesting child's own name self-names (IDENTITY_PROTECTION).

    Even when that name is ALSO in the PII floor set, the self-naming rule
    (rule 2) wins over the generic PERSONAL_DETAILS (rule 1 PII limb).
    """
    (decision,) = derive_dispositions(
        [RawElement("a story starring Emma")],
        band=AgeBand.BAND_8_11,
        bindings={},
        child_names=frozenset({"Emma"}),
        self_names=frozenset({"Emma"}),
    )
    assert decision.reason is ReasonCode.IDENTITY_PROTECTION
    assert decision.element is None


# ---------------------------------------------------------------------------
# Derivation precedence rules 1-7 (design 5.3), hand-built inputs.
# ---------------------------------------------------------------------------


def test_precedence_rule1_structural_beats_bound_to_slot() -> None:
    """Rule 1: an unsafe phrase is never described as built in (SAFETY_POLICY)."""
    (decision,) = derive_dispositions(
        [RawElement("a {brace} injection", slot_id="HERO")],
        band=AgeBand.BAND_8_11,
        bindings={"HERO": "Rue"},
    )
    assert decision.disposition is ElementDisposition.SET_ASIDE
    assert decision.reason is ReasonCode.SAFETY_POLICY
    assert decision.element is None


def test_precedence_rule1_pii_limb_personal_details() -> None:
    """Rule 1 (PII limb): free-typed contact detail -> PERSONAL_DETAILS."""
    (decision,) = derive_dispositions(
        [RawElement("reach me at bob@example.com", slot_id="HERO")],
        band=AgeBand.BAND_8_11,
        bindings={"HERO": "Rue"},
    )
    assert decision.reason is ReasonCode.PERSONAL_DETAILS
    assert decision.element is None


def test_precedence_rule2_self_naming_identity_protection() -> None:
    """Rule 2: self-naming lexicon -> IDENTITY_PROTECTION."""
    (decision,) = derive_dispositions(
        [RawElement("make me the hero", slot_id=None)],
        band=AgeBand.BAND_8_11,
        bindings={},
    )
    assert decision.reason is ReasonCode.IDENTITY_PROTECTION


def test_precedence_rule3_bound_to_slot_built_in() -> None:
    """Rule 3: a placed, echo-safe element -> BUILT_IN / BOUND_TO_SLOT."""
    (decision,) = derive_dispositions(
        [RawElement("a brave fox", slot_id="HERO")],
        band=AgeBand.BAND_8_11,
        bindings={"HERO": "Rue"},
    )
    assert decision.disposition is ElementDisposition.BUILT_IN
    assert decision.reason is ReasonCode.BOUND_TO_SLOT
    assert decision.element == "a brave fox"
    assert decision.slot_id == "HERO"


def test_precedence_rule3_adapted_when_slot_corrected_on_retry() -> None:
    """Rule 3: a slot corrected on retry -> ADAPTED (the narrow OQ-7 trigger)."""
    (decision,) = derive_dispositions(
        [RawElement("a brave fox", slot_id="HERO")],
        band=AgeBand.BAND_8_11,
        bindings={"HERO": "Rue"},
        adapted_slot_ids=frozenset({"HERO"}),
    )
    assert decision.disposition is ElementDisposition.ADAPTED
    assert decision.reason is ReasonCode.BOUND_TO_SLOT


def test_precedence_rule3_beats_guardian_control() -> None:
    """Rule 3 outranks rule 4: a bound element is built in even if banned-listed."""
    (decision,) = derive_dispositions(
        [RawElement("a spider hero", slot_id="HERO")],
        band=AgeBand.BAND_8_11,
        bindings={"HERO": "Rue"},
        content_nogo=["spider"],
    )
    assert decision.reason is ReasonCode.BOUND_TO_SLOT


def test_precedence_rule4_guardian_control() -> None:
    """Rule 4: an unplaced element matching a banned theme -> GUARDIAN_CONTROL."""
    (decision,) = derive_dispositions(
        [RawElement("a big spider", slot_id=None)],
        band=AgeBand.BAND_16_PLUS,
        bindings={},
        content_nogo=["spider"],
    )
    assert decision.reason is ReasonCode.GUARDIAN_CONTROL


def test_precedence_rule5_band_policy_with_forbid_rule() -> None:
    """Rule 5: an unplaced band-floor hit -> BAND_POLICY with a forbid:<bundle>."""
    (decision,) = derive_dispositions(
        [RawElement("a poisonous cloud", slot_id=None)],
        band=AgeBand.BAND_3_5,
        bindings={},
    )
    assert decision.reason is ReasonCode.BAND_POLICY
    assert decision.rule == "forbid:toxic"
    assert decision.element is None


def test_precedence_rule6_structure_fixed_ending() -> None:
    """Rule 6: an ending/fate request (empty-floor band) -> STRUCTURE_FIXED."""
    (decision,) = derive_dispositions(
        [RawElement("the hero wins at the end", slot_id=None)],
        band=AgeBand.BAND_16_PLUS,
        bindings={},
    )
    assert decision.reason is ReasonCode.STRUCTURE_FIXED
    assert decision.element == "the hero wins at the end"


def test_precedence_rule7_not_this_story_kind() -> None:
    """Rule 7: a benign, unplaced, non-matching element -> NOT_THIS_STORY_KIND."""
    (decision,) = derive_dispositions(
        [RawElement("a purple teapot", slot_id=None)],
        band=AgeBand.BAND_16_PLUS,
        bindings={},
    )
    assert decision.reason is ReasonCode.NOT_THIS_STORY_KIND
    assert decision.element == "a purple teapot"


def test_derive_dispositions_preserves_order_and_length() -> None:
    """Derivation is one decision per input element, in order."""
    raws = [
        RawElement("a brave fox", slot_id="HERO"),
        RawElement("a purple teapot", slot_id=None),
    ]
    decisions = derive_dispositions(
        raws, band=AgeBand.BAND_16_PLUS, bindings={"HERO": "Rue"}
    )
    assert len(decisions) == 2
    assert decisions[0].reason is ReasonCode.BOUND_TO_SLOT
    assert decisions[1].reason is ReasonCode.NOT_THIS_STORY_KIND


# ---------------------------------------------------------------------------
# render_interpretation: object shape, summaries, purity.
# ---------------------------------------------------------------------------


def test_render_interpretation_builds_full_object() -> None:
    """render_interpretation yields a RequestInterpretation with rendered text."""
    decisions = [
        ElementDecision(
            "a brave fox",
            ElementDisposition.BUILT_IN,
            ReasonCode.BOUND_TO_SLOT,
            slot_id="HERO",
        ),
        ElementDecision(
            None,
            ElementDisposition.SET_ASIDE,
            ReasonCode.BAND_POLICY,
            rule="forbid:lethal",
        ),
    ]
    result = render_interpretation(
        decisions,
        band=AgeBand.BAND_8_11,
        layer="refined",
        created_at=_NOW,
        skeleton_slug="the-cave-of-echoes",
        contract_version=1,
    )
    assert isinstance(result, RequestInterpretation)
    assert result.layer == "refined"
    assert result.created_at == _NOW
    assert result.skeleton_slug == "the-cave-of-echoes"
    assert result.contract_version == 1
    assert len(result.elements) == 2
    assert all(e.kid_text and e.guardian_text for e in result.elements)
    assert "1 built in" in result.guardian_summary
    assert "forbid:lethal" in result.guardian_summary


def test_render_interpretation_kid_summary_counts_dispositions() -> None:
    """The kid summary counts built-in vs set-aside dispositions."""
    decisions = derive_dispositions(
        [
            RawElement("a brave fox", slot_id="HERO"),
            RawElement("a poisonous cloud", slot_id=None),
        ],
        band=AgeBand.BAND_3_5,
        bindings={"HERO": "Rue"},
    )
    result = render_interpretation(
        decisions, band=AgeBand.BAND_3_5, layer="refined", created_at=_NOW
    )
    assert "built in 1" in result.kid_summary
    assert "saved 1 for later" in result.kid_summary


def test_render_interpretation_is_pure_and_repeatable() -> None:
    """Same inputs render an equal serialized object (no wall-clock read)."""
    decisions = derive_dispositions(
        [RawElement("a brave fox", slot_id="HERO")],
        band=AgeBand.BAND_8_11,
        bindings={"HERO": "Rue"},
    )
    first = render_interpretation(
        decisions, band=AgeBand.BAND_8_11, layer="refined", created_at=_NOW
    )
    second = render_interpretation(
        decisions, band=AgeBand.BAND_8_11, layer="refined", created_at=_NOW
    )
    assert first.model_dump() == second.model_dump()


# ---------------------------------------------------------------------------
# CR-1 style: a withheld phrase never appears in any output string.
# ---------------------------------------------------------------------------


def test_withheld_phrases_never_appear_in_any_output_string() -> None:
    """A blocked/withheld phrase never leaks into any rendered field (CR-1)."""
    toxic_phrases = [
        "a monster that kills everyone with poison",  # band floor (young)
        "reach me at bob@example.com",  # PII pattern
        "a story about Emma being herself",  # registered self-name
        "make me the hero of my own name",  # self-naming lexicon
        "a slot {HERO} injection attempt",  # structural
    ]
    raws = [RawElement(p) for p in toxic_phrases]
    decisions = derive_dispositions(
        raws,
        band=AgeBand.BAND_3_5,
        bindings={},
        child_names=frozenset({"Emma"}),
        self_names=frozenset({"Emma"}),
    )
    # Every one must be withheld (element=None).
    assert all(d.element is None for d in decisions)

    result = render_interpretation(
        decisions,
        band=AgeBand.BAND_3_5,
        layer="refined",
        created_at=_NOW,
        skeleton_slug="the-cave-of-echoes",
    )
    serialized = str(result.model_dump())
    haystacks = [serialized, result.kid_summary, result.guardian_summary]
    for element in result.elements:
        haystacks.extend([element.kid_text, element.guardian_text])
    combined = "\n".join(haystacks)
    for phrase in toxic_phrases:
        assert phrase not in combined, phrase
    # Spot-check the most sensitive tokens specifically.
    for token in ("bob@example.com", "Emma", "{HERO}"):
        assert token not in combined, token


def test_all_bands_map_to_a_band_group() -> None:
    """Every declared age band resolves to a template band group."""
    for band in _ALL_BANDS:
        assert band_group_for(band) in _GROUP_BAND


# ---------------------------------------------------------------------------
# The general layer (design section 4, D3): build_general_interpretation.
# ---------------------------------------------------------------------------


def test_build_general_blocked_is_single_generic_safety_element() -> None:
    """A blocked screening yields one CANNOT_CARRY/SAFETY_POLICY element (CR-1).

    The blocked path must not read the premise at all: even a banned theme that
    literally appears in the premise is neither matched nor echoed, and the
    unique premise string appears in no field of the output.
    """
    premise = "a dragon that breathes zephyrqux fire everywhere"
    result = build_general_interpretation(
        screening=_StubScreening(blocked=True, flags=[_StubFlag("violence")]),
        band=AgeBand.BAND_8_11,
        banned_themes=["dragon"],
        premise=premise,
        created_at=_NOW,
    )
    assert result.layer == "general"
    assert len(result.elements) == 1
    (element,) = result.elements
    assert element.disposition is ElementDisposition.CANNOT_CARRY
    assert element.reason is ReasonCode.SAFETY_POLICY
    assert element.element is None

    # CR-1: no premise-derived content anywhere, including the banned theme
    # "dragon" that is present in the premise (the blocked path never reads it).
    serialized = str(result.model_dump())
    haystacks = [
        serialized,
        result.kid_summary,
        result.guardian_summary,
        element.kid_text,
        element.guardian_text,
    ]
    combined = "\n".join(haystacks)
    assert premise not in combined
    assert "zephyrqux" not in combined
    assert "dragon" not in combined


def test_build_general_advisory_flags_put_category_in_guardian_text_only() -> None:
    """Each distinct advisory category yields a SAFETY_POLICY element.

    The classifier category is echoed to the guardian register only, never to
    kid_text, and is deduplicated (two 'violence' flags collapse to one).
    """
    result = build_general_interpretation(
        screening=_StubScreening(
            blocked=False,
            flags=[
                _StubFlag("violence"),
                _StubFlag("violence"),
                _StubFlag("scariness"),
            ],
        ),
        band=AgeBand.BAND_8_11,
        banned_themes=(),
        premise="a mostly gentle woodland walk",
        created_at=_NOW,
    )
    safety = [e for e in result.elements if e.reason is ReasonCode.SAFETY_POLICY]
    assert len(safety) == 2  # deduped by category
    assert all(e.disposition is ElementDisposition.SET_ASIDE for e in safety)
    assert all(e.element is None for e in safety)

    guardian_blob = " ".join(e.guardian_text for e in safety)
    kid_blob = " ".join(e.kid_text for e in safety)
    assert "violence" in guardian_blob
    assert "scariness" in guardian_blob
    assert "violence" not in kid_blob
    assert "scariness" not in kid_blob


def test_build_general_banned_theme_hit_is_guardian_control_echoing_guardian_word() -> (
    None
):
    """A premise that trips a guardian banned theme yields GUARDIAN_CONTROL.

    Only the tripped theme produces an element, and the echoed phrase is the
    guardian's own banned-theme string (which passes the echo floor trivially).
    """
    result = build_general_interpretation(
        screening=_StubScreening(blocked=False, flags=[]),
        band=AgeBand.BAND_8_11,
        banned_themes=["spider", "unrelatedtheme"],
        premise="a story about a big spider in the garden",
        created_at=_NOW,
    )
    guardian_control = [
        e for e in result.elements if e.reason is ReasonCode.GUARDIAN_CONTROL
    ]
    assert len(guardian_control) == 1
    assert guardian_control[0].disposition is ElementDisposition.SET_ASIDE
    assert guardian_control[0].element == "spider"


def test_build_general_always_exactly_one_band_expectation_element() -> None:
    """A clean request yields exactly the single BUILT_IN/STORY_FIT band element."""
    result = build_general_interpretation(
        screening=_StubScreening(blocked=False, flags=[]),
        band=AgeBand.BAND_3_5,
        banned_themes=(),
        premise="a friendly bunny hops home",
        created_at=_NOW,
    )
    band_elements = [
        e
        for e in result.elements
        if e.disposition is ElementDisposition.BUILT_IN
        and e.reason is ReasonCode.STORY_FIT
    ]
    assert len(band_elements) == 1
    assert band_elements[0].element is None
    # With no advisory flags and no banned-theme hit, it is the only element.
    assert len(result.elements) == 1


def test_general_layer_template_pairs_are_bespoke_in_all_band_groups() -> None:
    """The four general-layer pairs have bespoke catalog entries per band group.

    Membership in ``_CATALOG`` means ``_render_pair`` uses the bespoke pair, not
    the generic fallback, for young / middle / teen.
    """
    pairs = [
        (ElementDisposition.CANNOT_CARRY, ReasonCode.SAFETY_POLICY),
        (ElementDisposition.SET_ASIDE, ReasonCode.SAFETY_POLICY),
        (ElementDisposition.SET_ASIDE, ReasonCode.GUARDIAN_CONTROL),
        (ElementDisposition.BUILT_IN, ReasonCode.STORY_FIT),
    ]
    groups = [
        band_group_for(AgeBand.BAND_3_5),
        band_group_for(AgeBand.BAND_8_11),
        band_group_for(AgeBand.BAND_16_PLUS),
    ]
    for disposition, reason in pairs:
        for group in groups:
            assert (disposition, reason, group) in _CATALOG, (
                disposition,
                reason,
                group,
            )


def test_build_general_is_pure_and_repeatable() -> None:
    """Same inputs render an equal serialized object (no wall-clock read)."""
    screening = _StubScreening(blocked=False, flags=[_StubFlag("violence")])
    first = build_general_interpretation(
        screening=screening,
        band=AgeBand.BAND_8_11,
        banned_themes=["spider"],
        premise="a spider adventure",
        created_at=_NOW,
    )
    second = build_general_interpretation(
        screening=screening,
        band=AgeBand.BAND_8_11,
        banned_themes=["spider"],
        premise="a spider adventure",
        created_at=_NOW,
    )
    assert first.model_dump() == second.model_dump()
