"""Tests for GenerationProvider protocol and MockProvider test double."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.generation.provider import (
    GenerationProvider,
    MockProvider,
    make_canned_story_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_via_protocol(provider: GenerationProvider, prompt: str) -> str:
    """Call complete() through a GenerationProvider-typed reference.

    This function exists to prove structural protocol conformance: if
    MockProvider did not satisfy GenerationProvider, BasedPyright strict
    mode would flag the assignment below.
    """
    return await provider.complete(system="sys", prompt=prompt, max_tokens=50)


# ---------------------------------------------------------------------------
# 1. Ordered string responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_returns_queued_strings_in_order() -> None:
    """complete() returns queued string responses in call order."""
    provider = MockProvider(responses=["first", "second", "third"])

    r1 = await provider.complete(system="s", prompt="p1", max_tokens=10)
    r2 = await provider.complete(system="s", prompt="p2", max_tokens=10)
    r3 = await provider.complete(system="s", prompt="p3", max_tokens=10)

    assert r1 == "first"
    assert r2 == "second"
    assert r3 == "third"


# ---------------------------------------------------------------------------
# 2. Callable responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_callable_response_receives_prompt() -> None:
    """A callable response is called with the user prompt and its result returned."""

    def branch_on_prompt(prompt: str) -> str:
        if "stage_a" in prompt:
            return '{"skeleton": true}'
        return '{"full_story": true}'

    provider = MockProvider(responses=[branch_on_prompt, branch_on_prompt])

    r_a = await provider.complete(system="s", prompt="stage_a skeleton", max_tokens=100)
    r_b = await provider.complete(system="s", prompt="stage_b full", max_tokens=100)

    assert r_a == '{"skeleton": true}'
    assert r_b == '{"full_story": true}'


# ---------------------------------------------------------------------------
# 3. Prompt recording
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_records_prompts_in_calls() -> None:
    """Every prompt is appended to provider.calls in call order."""
    provider = MockProvider(responses=["a", "b", "c"])

    await provider.complete(system="s", prompt="first prompt", max_tokens=10)
    await provider.complete(system="s", prompt="second prompt", max_tokens=10)
    await provider.complete(system="s", prompt="third prompt", max_tokens=10)

    assert provider.calls == ["first prompt", "second prompt", "third prompt"]


# ---------------------------------------------------------------------------
# 4. Exhausted queue raises BusinessLogicError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_raises_business_logic_error_when_exhausted() -> None:
    """complete() raises BusinessLogicError when more calls than queued responses."""
    provider = MockProvider(responses=["only one"])

    await provider.complete(system="s", prompt="ok", max_tokens=10)

    with pytest.raises(BusinessLogicError) as exc_info:
        await provider.complete(system="s", prompt="over-call", max_tokens=10)

    msg = str(exc_info.value)
    assert "MockProvider exhausted" in msg
    assert "1 responses queued" in msg
    assert "call 2 received" in msg


@pytest.mark.asyncio
async def test_exhausted_error_message_includes_correct_counts() -> None:
    """Error message contains the exact queued-count and call-count."""
    provider = MockProvider(responses=["r1", "r2"])

    await provider.complete(system="s", prompt="p1", max_tokens=5)
    await provider.complete(system="s", prompt="p2", max_tokens=5)

    with pytest.raises(BusinessLogicError) as exc_info:
        await provider.complete(system="s", prompt="p3", max_tokens=5)

    msg = str(exc_info.value)
    assert "2 responses queued" in msg
    assert "call 3 received" in msg


# ---------------------------------------------------------------------------
# 5. Structural typing / protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_provider_satisfies_generation_provider_protocol() -> None:
    """MockProvider is assignable to and usable via GenerationProvider reference."""
    provider = MockProvider(responses=["protocol-response"])

    # Pass MockProvider where GenerationProvider is expected: structural check.
    result = await _run_via_protocol(provider, "my prompt")

    assert result == "protocol-response"


# ---------------------------------------------------------------------------
# 6. system and max_tokens accepted and ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_accepts_system_and_max_tokens_without_error() -> None:
    """system and max_tokens are accepted (and ignored) by MockProvider."""
    provider = MockProvider(responses=["ok"])

    result = await provider.complete(
        system="You are a story generator.",
        prompt="generate a story",
        max_tokens=2048,
    )

    assert result == "ok"
    # system/max_tokens not surfaced in calls; only prompt is recorded
    assert provider.calls == ["generate a story"]


# ---------------------------------------------------------------------------
# 7. Mixed string + callable responses in one queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_string_and_callable_responses() -> None:
    """A queue may mix plain strings and callables freely."""
    provider = MockProvider(
        responses=[
            "static response",
            lambda p: f"dynamic:{p}",
            "another static",
        ]
    )

    r1 = await provider.complete(system="s", prompt="ignored", max_tokens=10)
    r2 = await provider.complete(system="s", prompt="my-prompt", max_tokens=10)
    r3 = await provider.complete(system="s", prompt="ignored2", max_tokens=10)

    assert r1 == "static response"
    assert r2 == "dynamic:my-prompt"
    assert r3 == "another static"


# ---------------------------------------------------------------------------
# 8. Canned story response helper
# ---------------------------------------------------------------------------


def test_make_canned_story_response_produces_valid_json() -> None:
    """make_canned_story_response serializes a dict to valid JSON."""
    story = {"id": "s_test", "title": "Test Story", "tier": 1}
    result = make_canned_story_response(story)

    parsed = json.loads(result)
    assert parsed["id"] == "s_test"
    assert parsed["title"] == "Test Story"


@pytest.mark.asyncio
async def test_make_canned_story_response_usable_as_queued_response() -> None:
    """A canned story JSON can be queued in MockProvider and returned correctly."""
    fixture_path = (
        Path(__file__).parent.parent
        / "fixtures"
        / "storybook"
        / "valid"
        / "03_tier2_lantern.json"
    )
    with fixture_path.open() as fh:
        story_dict = json.load(fh)

    canned = make_canned_story_response(story_dict)  # type: ignore[arg-type]
    provider = MockProvider(responses=[canned])

    response = await provider.complete(
        system="s", prompt="generate lantern", max_tokens=4096
    )

    parsed = json.loads(response)
    assert parsed["id"] == "s_lantern_cave"
    assert parsed["title"] == "The Lantern Cave"


# ---------------------------------------------------------------------------
# 9. Empty responses list raises immediately on first call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_responses_raises_on_first_call() -> None:
    """A MockProvider with no responses raises BusinessLogicError on first call."""
    provider = MockProvider(responses=[])

    with pytest.raises(BusinessLogicError) as exc_info:
        await provider.complete(system="s", prompt="p", max_tokens=10)

    assert "0 responses queued" in str(exc_info.value)
    assert "call 1 received" in str(exc_info.value)
