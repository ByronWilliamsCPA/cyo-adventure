"""Unit tests for the WS-2 LLM bind step (generation/binding.py).

All tests run against the deterministic MockProvider -- no real network or
LLM calls are made. Mirrors the orchestrator's parse-posture and PII-abort
test conventions (``tests/unit/test_orchestrator.py``).
"""

from __future__ import annotations

import json

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.binding import bind_theme_to_contract
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.storybook.theme_contract import (
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
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
        guidance="keep it short, safe, and concrete",
        constraints=constraints or SlotConstraints(),
    )


def _contract() -> ThemeContract:
    """A small fixture contract: two slots, one with a declared forbid bundle."""
    return ThemeContract(
        contract_version=1,
        skeleton_slug="s_test_bind",
        age_band="8-11",
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
_VALID_RESPONSE = json.dumps(_VALID_BINDING)
# HERO's declared forbid=["weapon"] plus the 8-11 band-mandatory union both
# apply to every slot; "knife" is a denylisted weapon term.
_WEAPON_VIOLATING_RESPONSE = json.dumps(
    {"HERO": "a knife wielder", "A1_GATE": "the jammed hatch"}
)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bind_happy_path_returns_validated_binding() -> None:
    """A single valid, conforming response is returned as-is."""
    provider = MockProvider(responses=[_VALID_RESPONSE])

    result = await bind_theme_to_contract(_contract(), _brief(), provider, _empty_pii())

    assert result == _VALID_BINDING
    assert len(provider.calls) == 1
    assert "Previous Attempt Violations" not in provider.calls[0]


# ---------------------------------------------------------------------------
# Invalid JSON then valid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bind_invalid_json_then_valid_succeeds() -> None:
    """A non-JSON first attempt is a failed attempt, not an exception; retry succeeds."""
    provider = MockProvider(responses=["not json at all", _VALID_RESPONSE])

    result = await bind_theme_to_contract(
        _contract(), _brief(), provider, _empty_pii(), max_attempts=2
    )

    assert result == _VALID_BINDING
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_bind_non_dict_json_then_valid_succeeds() -> None:
    """A JSON array (valid JSON, wrong shape) is also a failed attempt, not a crash."""
    provider = MockProvider(responses=[json.dumps([1, 2, 3]), _VALID_RESPONSE])

    result = await bind_theme_to_contract(
        _contract(), _brief(), provider, _empty_pii(), max_attempts=2
    )

    assert result == _VALID_BINDING
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_bind_non_string_values_then_valid_succeeds() -> None:
    """A dict with a non-string value is also a failed attempt, not a crash."""
    non_string_response = json.dumps({"HERO": 123, "A1_GATE": "the jammed hatch"})
    provider = MockProvider(responses=[non_string_response, _VALID_RESPONSE])

    result = await bind_theme_to_contract(
        _contract(), _brief(), provider, _empty_pii(), max_attempts=2
    )

    assert result == _VALID_BINDING
    assert len(provider.calls) == 2


# ---------------------------------------------------------------------------
# Violations fed back verbatim into the retry prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bind_violations_fed_back_verbatim_into_retry_prompt() -> None:
    """The exact slot id and rule from the failed attempt reach the retry prompt."""
    provider = MockProvider(responses=[_WEAPON_VIOLATING_RESPONSE, _VALID_RESPONSE])

    result = await bind_theme_to_contract(
        _contract(), _brief(), provider, _empty_pii(), max_attempts=2
    )

    assert result == _VALID_BINDING
    assert len(provider.calls) == 2
    retry_prompt = provider.calls[1]
    assert "HERO" in retry_prompt
    assert "forbid:weapon" in retry_prompt


# ---------------------------------------------------------------------------
# Exhaustion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bind_exhaustion_on_persistent_violation_raises() -> None:
    """A binding that never conforms raises ValidationError with the violations."""
    provider = MockProvider(
        responses=[_WEAPON_VIOLATING_RESPONSE, _WEAPON_VIOLATING_RESPONSE]
    )

    contract = _contract()
    brief = _brief()
    pii = _empty_pii()
    with pytest.raises(ValidationError) as exc_info:
        await bind_theme_to_contract(contract, brief, provider, pii, max_attempts=2)

    assert len(provider.calls) == 2
    violations = exc_info.value.details["violations"]
    assert any(v["rule"] == "forbid:weapon" for v in violations)


@pytest.mark.asyncio
async def test_bind_exhaustion_on_persistent_parse_failure_raises() -> None:
    """Persistently unparseable output raises ValidationError, not a crash."""
    provider = MockProvider(responses=["nope", "still nope"])

    contract = _contract()
    brief = _brief()
    pii = _empty_pii()
    with pytest.raises(ValidationError):
        await bind_theme_to_contract(contract, brief, provider, pii, max_attempts=2)

    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_bind_max_attempts_one_fails_fast() -> None:
    """max_attempts=1 makes exactly one call before raising."""
    provider = MockProvider(responses=[_WEAPON_VIOLATING_RESPONSE])

    contract = _contract()
    brief = _brief()
    pii = _empty_pii()
    with pytest.raises(ValidationError):
        await bind_theme_to_contract(contract, brief, provider, pii, max_attempts=1)

    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# PII guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bind_pii_guard_fires_and_provider_never_called() -> None:
    """A seeded real-child name in the brief aborts before any provider call.

    Mirrors ``test_orchestrator.py::test_pii_abort_raises_and_provider_not_called``.
    """
    real_child_name = "SecretChildActualName"
    brief = {"premise": f"A story created for {real_child_name} the brave."}
    pii = PiiContext(child_names=frozenset({real_child_name}))
    provider = MockProvider(responses=[_VALID_RESPONSE])
    contract = _contract()

    with pytest.raises(ValidationError):
        await bind_theme_to_contract(contract, brief, provider, pii)

    assert provider.calls == []
