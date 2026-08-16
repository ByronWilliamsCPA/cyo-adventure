"""The fill output cap: raised default, per-model clamp, feasibility screen.

The cap was 32,000 from initial testing until 2026-08-16, which made 36 of the
59 production skeletons unfillable and the 13-16 and 16+ bands unfillable
entirely. Raising it is only safe alongside the clamp: AL-328's finding was
that ONE fixed cap across models silently converts a verbose model into a
failing one, and a raised default repeats that defect in the other direction
unless a small-output backend is clamped back down.
"""

from __future__ import annotations

import pytest

from cyo_adventure.generation.skeleton import (
    MAX_FILL_OUTPUT_TOKENS,
    MODEL_OUTPUT_CAPS,
    active_fill_model,
    expected_output_tokens,
    is_fill_feasible,
    resolve_output_cap,
)


class _Settings:
    """Minimal stand-in carrying only the fields the resolver reads."""

    def __init__(self, provider: str, **models: str) -> None:
        self.generation_provider = provider
        for name, value in models.items():
            setattr(self, name, value)


@pytest.mark.unit
def test_the_default_cap_clears_the_whole_production_catalog() -> None:
    """131,072 is chosen against the catalog, not picked round.

    The largest skeleton needs 87,200 output tokens; the next step down
    (65,536) still leaves 12 skeletons short.
    """
    assert int(87_200 / 0.8) <= MAX_FILL_OUTPUT_TOKENS


@pytest.mark.unit
def test_a_small_output_model_clamps_the_cap_down() -> None:
    """A backend that cannot emit the default must not be asked to.

    Asking for more than a model will emit truncates the completion, and a
    truncated document parses as nothing at all rather than as a partial book.
    """
    small = "deepseek/deepseek-chat-v3.1"

    assert MODEL_OUTPUT_CAPS[small] < MAX_FILL_OUTPUT_TOKENS
    assert resolve_output_cap(small) == MODEL_OUTPUT_CAPS[small]


@pytest.mark.unit
def test_a_large_output_model_does_not_raise_the_cap() -> None:
    """The clamp only ever lowers. deepseek-v4-pro emits far more than we ask."""
    assert MODEL_OUTPUT_CAPS["deepseek/deepseek-v4-pro"] > MAX_FILL_OUTPUT_TOKENS
    assert resolve_output_cap("deepseek/deepseek-v4-pro") == MAX_FILL_OUTPUT_TOKENS


@pytest.mark.unit
def test_an_unknown_model_gets_the_default() -> None:
    """Absent evidence the cap is not lowered; `length` is leg-fatal anyway."""
    assert resolve_output_cap("some/unlisted-model") == MAX_FILL_OUTPUT_TOKENS
    assert resolve_output_cap(None) == MAX_FILL_OUTPUT_TOKENS


@pytest.mark.unit
@pytest.mark.parametrize(
    ("provider", "field", "model"),
    [
        ("openrouter", "openrouter_model", "deepseek/deepseek-v4-pro"),
        ("ollama", "ollama_model", "qwen2.5:14b"),
        ("anthropic", "anthropic_model", "claude-sonnet-4-6"),
    ],
)
def test_the_active_model_follows_the_configured_backend(
    provider: str, field: str, model: str
) -> None:
    """The cap must resolve against the model the call will actually use."""
    assert active_fill_model(_Settings(provider, **{field: model})) == model


@pytest.mark.unit
def test_a_backend_with_no_model_concept_resolves_to_none() -> None:
    """mock has no model, and None must mean 'use the default', not crash."""
    assert active_fill_model(_Settings("mock")) is None


@pytest.mark.unit
def test_feasibility_is_measured_against_the_declared_fill_targets() -> None:
    """Expected size is computable before anything has been paid for."""
    story = {
        "nodes": [
            {"body": "<<FILL role=rising words=100 beats='a'>>"},
            {"body": "<<FILL role=rising words=150 beats='b'>>"},
        ]
    }

    assert expected_output_tokens(story) == 500
    assert is_fill_feasible(story, max_tokens=1000)
    assert not is_fill_feasible(story, max_tokens=100)
