"""Unit tests for review-provider construction and independence enforcement."""

from __future__ import annotations

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.moderation.review_provider import build_review_provider

pytestmark = pytest.mark.unit


def test_mock_review_provider_is_always_independent() -> None:
    settings = Settings(review_provider="mock")
    provider, independent = build_review_provider(
        settings, generator_provider="openrouter", generator_model="x"
    )
    assert independent is True
    assert provider is not None


def test_modal_review_provider_is_deferred() -> None:
    settings = Settings(review_provider="modal", openai_api_key="k")
    with pytest.raises(ConfigurationError):
        build_review_provider(
            settings, generator_provider="ollama", generator_model="y"
        )


def test_same_backend_same_model_is_not_independent() -> None:
    settings = Settings(
        review_provider="openrouter",
        review_openrouter_model="anthropic/claude-sonnet-4.6",
        openrouter_api_key="k",
        openai_api_key="k",
    )
    _provider, independent = build_review_provider(
        settings,
        generator_provider="openrouter",
        generator_model="anthropic/claude-sonnet-4.6",
    )
    assert independent is False


def test_different_backend_is_independent() -> None:
    settings = Settings(
        review_provider="ollama",
        openai_api_key="k",
    )
    _provider, independent = build_review_provider(
        settings, generator_provider="openrouter", generator_model="anything"
    )
    assert independent is True
