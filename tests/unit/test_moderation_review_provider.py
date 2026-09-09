"""Unit tests for review-provider construction and independence enforcement."""

from __future__ import annotations

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.moderation.review_provider import (
    build_cover_review_provider,
    build_review_provider,
)

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
            settings, generator_provider="anthropic", generator_model="y"
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
    # Reviewing on openrouter while the story was generated on the direct
    # anthropic leg is the surviving cross-backend pairing now that the ollama
    # review backend is retired.
    settings = Settings(
        review_provider="openrouter",
        openrouter_api_key="k",
        openai_api_key="k",
    )
    _provider, independent = build_review_provider(
        settings, generator_provider="anthropic", generator_model="anything"
    )
    assert independent is True


def test_mock_cover_review_provider_is_always_independent() -> None:
    settings = Settings(review_provider="mock")
    provider, independent = build_cover_review_provider(settings)
    assert independent is True
    assert provider is not None


def test_modal_cover_review_provider_is_deferred() -> None:
    settings = Settings(review_provider="modal", openai_api_key="k")
    with pytest.raises(ConfigurationError):
        build_cover_review_provider(settings)


def test_openrouter_cover_review_same_vendor_as_generator_is_not_independent() -> None:
    """A reviewer on a different model id but the SAME vendor as the cover
    generator (Google, always called via the direct SDK in covers/provider.py)
    is not independent, even though the OpenRouter-namespaced id string
    ("google/gemini-2.5-flash") differs from the bare generator id
    ("gemini-3-pro-image")."""
    settings = Settings(
        review_provider="openrouter",
        cover_review_model="google/gemini-2.5-flash",
        openrouter_api_key="k",
        openai_api_key="k",
    )
    _provider, independent = build_cover_review_provider(settings)
    assert independent is False


def test_openrouter_cover_review_different_vendor_is_independent() -> None:
    settings = Settings(
        review_provider="openrouter",
        cover_review_model="openai/gpt-4.1-mini",
        openrouter_api_key="k",
        openai_api_key="k",
    )
    _provider, independent = build_cover_review_provider(settings)
    assert independent is True


def test_openrouter_cover_review_same_model_as_generator_is_not_independent() -> None:
    """A misconfiguration (reviewer pinned to the generator's own model id)
    is caught, not silently assumed independent."""
    settings = Settings(
        review_provider="openrouter",
        cover_review_model="gemini-3-pro-image",
        openrouter_api_key="k",
        openai_api_key="k",
    )
    _provider, independent = build_cover_review_provider(settings)
    assert independent is False
