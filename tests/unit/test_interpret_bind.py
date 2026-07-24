"""Unit tests for the WS-7 interpret-and-bind step (generation/binding.py, D4).

All tests run against the deterministic MockProvider -- no real network or LLM
calls are made. Mirrors ``tests/unit/test_bind_step.py``'s fixtures and
parse/PII-abort conventions; the extra surface here is the asymmetric parse
(load-bearing ``bindings`` vs advisory ``elements``) and the element
sanitization posture of design section 5.2.
"""

from __future__ import annotations

import inspect
import json
from typing import cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation import binding as binding_module
from cyo_adventure.generation.binding import interpret_and_bind
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.prompts import (
    build_bind_prompt,
    build_interpret_bind_prompt,
)
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.story_requests.interpretation import RawElement
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import (
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
)
from cyo_adventure.validator.slots import validate_slot_bindings


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
        guidance="keep it short, safe, and concrete",
        constraints=constraints or SlotConstraints(),
    )


def _contract() -> ThemeContract:
    """A small fixture contract: two slots, one with a declared forbid bundle."""
    return ThemeContract(
        contract_version=1,
        skeleton_slug="s_test_interpret_bind",
        age_band=AgeBand.BAND_8_11,
        legacy_lexicon=["Maya"],
        default_binding={
            "HERO": "Priya",
            "A1_GATE": "the jammed hatch",
        },
        slots=[
            _slot("HERO", constraints=SlotConstraints(max_words=4, forbid=["weapon"])),
            _slot(
                "A1_GATE",
                scope=SlotScope.TRACK,
                constraints=SlotConstraints(max_words=8, forbid=["lethal"]),
            ),
        ],
    )


def _empty_pii() -> PiiContext:
    return PiiContext(child_names=frozenset())


def _brief() -> dict[str, object]:
    return {"premise": "A curious fox explores a glowing cave."}


_VALID_BINDING = {"HERO": "Priya", "A1_GATE": "the jammed hatch"}
_WEAPON_VIOLATING_BINDING = {"HERO": "a knife wielder", "A1_GATE": "the jammed hatch"}


def _resp(bindings: object, elements: object) -> str:
    """Serialize an interpret-and-bind response envelope."""
    return json.dumps({"bindings": bindings, "elements": elements})


_VALID_ELEMENTS = [
    {"phrase": "a curious fox", "slot_id": "HERO"},
    {"phrase": "a glowing cave", "slot_id": None},
]
_VALID_RESPONSE = _resp(_VALID_BINDING, _VALID_ELEMENTS)


# ---------------------------------------------------------------------------
# Combined parse happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_happy_path_returns_bindings_and_elements() -> None:
    """A single valid response yields validated bindings AND sanitized elements."""
    provider = MockProvider(responses=[_VALID_RESPONSE])

    bindings, elements = await interpret_and_bind(
        _contract(), _brief(), provider, _empty_pii()
    )

    assert bindings == _VALID_BINDING
    assert elements == [
        RawElement(phrase="a curious fox", slot_id="HERO"),
        RawElement(phrase="a glowing cave", slot_id=None),
    ]
    assert len(provider.calls) == 1
    assert "Previous Attempt Violations" not in provider.calls[0]


# ---------------------------------------------------------------------------
# Asymmetry: advisory `elements` never fail the parse
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_malformed_elements_degrade_to_empty_list() -> None:
    """A malformed `elements` value degrades to [] while bindings still succeed."""
    provider = MockProvider(responses=[_resp(_VALID_BINDING, "not a list at all")])

    bindings, elements = await interpret_and_bind(
        _contract(), _brief(), provider, _empty_pii()
    )

    assert bindings == _VALID_BINDING
    assert elements == []
    assert len(provider.calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_missing_elements_key_degrades_to_empty_list() -> None:
    """An entirely missing `elements` key still succeeds with an empty list."""
    provider = MockProvider(responses=[json.dumps({"bindings": _VALID_BINDING})])

    bindings, elements = await interpret_and_bind(
        _contract(), _brief(), provider, _empty_pii()
    )

    assert bindings == _VALID_BINDING
    assert elements == []
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# Asymmetry: load-bearing `bindings` still consume an attempt and can fail
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_malformed_bindings_consumes_attempt_then_valid() -> None:
    """A non-dict `bindings` is a failed attempt (not a crash); the retry succeeds."""
    provider = MockProvider(
        responses=[_resp([1, 2, 3], _VALID_ELEMENTS), _VALID_RESPONSE]
    )

    bindings, elements = await interpret_and_bind(
        _contract(), _brief(), provider, _empty_pii(), max_attempts=2
    )

    assert bindings == _VALID_BINDING
    assert elements == [
        RawElement(phrase="a curious fox", slot_id="HERO"),
        RawElement(phrase="a glowing cave", slot_id=None),
    ]
    assert len(provider.calls) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_malformed_bindings_exhaustion_raises() -> None:
    """Persistently malformed `bindings` consumes every attempt then raises."""
    provider = MockProvider(
        responses=[
            _resp("not a dict", _VALID_ELEMENTS),
            _resp({"HERO": 123, "A1_GATE": "the jammed hatch"}, _VALID_ELEMENTS),
        ]
    )

    contract = _contract()
    brief = _brief()
    pii = _empty_pii()
    with pytest.raises(ValidationError):
        await interpret_and_bind(contract, brief, provider, pii, max_attempts=2)

    assert len(provider.calls) == 2


# ---------------------------------------------------------------------------
# Element sanitization: unknown slot ids, cap, and long phrases
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_unknown_slot_id_dropped_to_null() -> None:
    """An `elements[].slot_id` not in the contract is mapped to None."""
    elements = [
        {"phrase": "a curious fox", "slot_id": "HERO"},
        {"phrase": "a mystery box", "slot_id": "NOT_A_REAL_SLOT"},
        {"phrase": "a numeric slot", "slot_id": 7},
    ]
    provider = MockProvider(responses=[_resp(_VALID_BINDING, elements)])

    _bindings, result = await interpret_and_bind(
        _contract(), _brief(), provider, _empty_pii()
    )

    assert result == [
        RawElement(phrase="a curious fox", slot_id="HERO"),
        RawElement(phrase="a mystery box", slot_id=None),
        RawElement(phrase="a numeric slot", slot_id=None),
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_element_list_capped_and_long_phrase_dropped() -> None:
    """The element list caps at 12 entries and a >120-char phrase is dropped."""
    long_phrase = "a" * 121  # 121 chars, one word: dropped by the char check only.
    raw_elements: list[dict[str, object]] = [{"phrase": long_phrase, "slot_id": None}]
    raw_elements.extend(
        {"phrase": f"element number {n}", "slot_id": None} for n in range(15)
    )
    provider = MockProvider(responses=[_resp(_VALID_BINDING, raw_elements)])

    _bindings, result = await interpret_and_bind(
        _contract(), _brief(), provider, _empty_pii()
    )

    assert len(result) == 12
    assert all(len(e.phrase) <= 120 for e in result)
    assert long_phrase not in {e.phrase for e in result}
    # The kept 12 are the first 12 valid (short) phrases in order.
    assert result[0].phrase == "element number 0"
    assert result[-1].phrase == "element number 11"


# ---------------------------------------------------------------------------
# CR-2: a failed attempt's elements are discarded; only the passing attempt's
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_failed_attempt_elements_discarded() -> None:
    """Elements from a failed (violating) attempt never leak into the result."""
    failed_elements = [{"phrase": "a knife wielder", "slot_id": "HERO"}]
    passing_elements = [{"phrase": "a curious fox", "slot_id": "HERO"}]
    provider = MockProvider(
        responses=[
            _resp(_WEAPON_VIOLATING_BINDING, failed_elements),
            _resp(_VALID_BINDING, passing_elements),
        ]
    )

    bindings, result = await interpret_and_bind(
        _contract(), _brief(), provider, _empty_pii(), max_attempts=2
    )

    assert bindings == _VALID_BINDING
    assert result == [RawElement(phrase="a curious fox", slot_id="HERO")]
    assert "a knife wielder" not in {e.phrase for e in result}
    assert len(provider.calls) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_exhaustion_on_persistent_violation_raises() -> None:
    """A binding that never conforms raises ValidationError with the violations."""
    provider = MockProvider(
        responses=[
            _resp(_WEAPON_VIOLATING_BINDING, _VALID_ELEMENTS),
            _resp(_WEAPON_VIOLATING_BINDING, _VALID_ELEMENTS),
        ]
    )

    contract = _contract()
    brief = _brief()
    pii = _empty_pii()
    with pytest.raises(ValidationError) as exc_info:
        await interpret_and_bind(contract, brief, provider, pii, max_attempts=2)

    assert len(provider.calls) == 2
    violations = cast("list[dict[str, str]]", exc_info.value.details["violations"])
    assert any(v["rule"] == "forbid:weapon" for v in violations)


# ---------------------------------------------------------------------------
# Violations retry byte-parity with bind_theme_to_contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_interpret_bind_prompt_user_block_byte_identical_to_bind_prompt() -> None:
    """The fenced-brief user block is byte-identical to build_bind_prompt's.

    Same fence, same violations retry block: only the system Output section
    differs between bind.md and interpret_bind.md (CR-2 / design section 5.2).
    """
    contract, brief = _contract(), _brief()
    violations = validate_slot_bindings(contract, _WEAPON_VIOLATING_BINDING)
    assert violations  # sanity: the fixture actually violates

    # First attempt (no violations) and retry (with violations) both match.
    assert (
        build_interpret_bind_prompt(contract, brief).user
        == build_bind_prompt(contract, brief).user
    )
    assert (
        build_interpret_bind_prompt(contract, brief, violations=violations).user
        == build_bind_prompt(contract, brief, violations=violations).user
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_violations_fed_back_verbatim_into_retry_prompt() -> None:
    """The exact slot id and rule from the failed attempt reach the retry prompt.

    Mirrors ``test_bind_step.py``'s equivalent, proving the retry posture is the
    same as ``bind_theme_to_contract``.
    """
    provider = MockProvider(
        responses=[
            _resp(_WEAPON_VIOLATING_BINDING, _VALID_ELEMENTS),
            _VALID_RESPONSE,
        ]
    )

    bindings, _elements = await interpret_and_bind(
        _contract(), _brief(), provider, _empty_pii(), max_attempts=2
    )

    assert bindings == _VALID_BINDING
    assert len(provider.calls) == 2
    retry_prompt = provider.calls[1]
    assert "Previous Attempt Violations" in retry_prompt
    assert "HERO" in retry_prompt
    assert "forbid:weapon" in retry_prompt


# ---------------------------------------------------------------------------
# PII guard fires before any provider call (name AND pattern hits)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_pii_guard_fires_on_child_name_before_any_call() -> None:
    """A seeded real-child name in the brief aborts before any provider call."""
    real_child_name = "SecretChildActualName"
    brief = {"premise": f"A story created for {real_child_name} the brave."}
    pii = PiiContext(child_names=frozenset({real_child_name}))
    provider = MockProvider(responses=[_VALID_RESPONSE])
    contract = _contract()

    with pytest.raises(ValidationError):
        await interpret_and_bind(contract, brief, provider, pii)

    assert provider.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_pii_guard_fires_on_pattern_hit_before_any_call() -> None:
    """An email/phone/address pattern in the brief aborts before any call.

    The post-#304 guard screens for email/phone/address unconditionally, even
    with an empty child-name set; the abort must precede provider dispatch.
    """
    brief = {"premise": "Please email me at kid@example.com about my dragon story."}
    provider = MockProvider(responses=[_VALID_RESPONSE])
    contract = _contract()
    pii = _empty_pii()

    with pytest.raises(ValidationError):
        await interpret_and_bind(contract, brief, provider, pii)

    assert provider.calls == []


# ---------------------------------------------------------------------------
# Structural: no provider.complete call outside PiiGuardedProvider (CR-4)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_interpret_and_bind_only_calls_complete_through_guarded_provider() -> None:
    """No code path in interpret_and_bind dispatches outside PiiGuardedProvider.

    Grep-style structural assertion (mirrors the WS-1 exit criterion): the raw
    provider is only ever handed to ``PiiGuardedProvider(...)``, and every
    ``.complete(`` call in the function targets ``guarded_provider``, never the
    bare ``provider`` argument (CR-4 / design sections 7.1, 8.2).
    """
    source = inspect.getsource(binding_module.interpret_and_bind)

    assert "PiiGuardedProvider(provider, forbidden=pii)" in source
    assert "guarded_provider.complete(" in source
    # The bare provider parameter is never awaited directly.
    assert "provider.complete(" not in source.replace("guarded_provider.complete(", "")
    assert "await provider.complete" not in source


# ---------------------------------------------------------------------------
# _sanitize_elements: malformed entries (design section 5.2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sanitize_elements_skips_non_dict_entries_and_bad_phrases() -> None:
    """A non-dict entry, a non-string phrase, and an empty phrase are all dropped."""
    raw_elements: list[object] = [
        "not an element",
        {"phrase": 123},
        {"phrase": ""},
        {"no_phrase_key": "x"},
        {"phrase": "a curious fox", "slot_id": "HERO"},
    ]

    result = binding_module._sanitize_elements(raw_elements, _contract())

    assert result == [RawElement(phrase="a curious fox", slot_id="HERO")]


# ---------------------------------------------------------------------------
# _parse_interpret_bind_response: malformed top-level JSON (bindings half)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_invalid_json_then_valid_succeeds() -> None:
    """A non-JSON first attempt is a failed attempt, not an exception; retry succeeds."""
    provider = MockProvider(responses=["not json at all", _VALID_RESPONSE])

    bindings, elements = await interpret_and_bind(
        _contract(), _brief(), provider, _empty_pii(), max_attempts=2
    )

    assert bindings == _VALID_BINDING
    assert elements == [
        RawElement(phrase="a curious fox", slot_id="HERO"),
        RawElement(phrase="a glowing cave", slot_id=None),
    ]
    assert len(provider.calls) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interpret_bind_non_dict_top_level_json_then_valid_succeeds() -> None:
    """A JSON array (valid JSON, wrong shape) is also a failed attempt, not a crash."""
    provider = MockProvider(responses=[json.dumps([1, 2, 3]), _VALID_RESPONSE])

    bindings, _elements = await interpret_and_bind(
        _contract(), _brief(), provider, _empty_pii(), max_attempts=2
    )

    assert bindings == _VALID_BINDING
    assert len(provider.calls) == 2
