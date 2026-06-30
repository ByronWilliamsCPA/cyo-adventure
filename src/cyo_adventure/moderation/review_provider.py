"""The review-provider abstraction for the LLM moderation stages.

``ReviewProvider`` mirrors ``GenerationProvider`` exactly so the same backend
adapters (OpenRouter, Ollama) and the same ``PiiGuardedProvider`` wrapper apply.
``build_review_provider`` enforces reviewer independence: a model must not review
its own output without that being recorded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.generation.provider import (
    MockProvider,
    build_ollama_leg,
    build_openrouter_leg,
)

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings


class ReviewProvider(Protocol):
    """Structural protocol identical to ``GenerationProvider``."""

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Return the model's completion for a system+user prompt."""
        ...


def build_review_provider(
    settings: Settings,
    *,
    generator_provider: str | None,
    generator_model: str | None,
) -> tuple[ReviewProvider, bool]:
    """Build the review provider and report whether it is independent.

    Independence tiers (prefer-different, degrade-with-warning):

      1. Different backend from the generator -> independent.
      2. Same backend, different model -> independent.
      3. Same backend and same model -> NOT independent (caller records a
         ``reviewer_not_independent`` finding).

    Args:
        settings: Application settings (``review_provider`` and model fields).
        generator_provider: The provider that generated the story; ``None``
            when unknown.
        generator_model: The model that generated the story; ``None`` when
            unknown.

    Returns:
        ``(provider, independent)``.

    Raises:
        ConfigurationError: when ``review_provider`` is the deferred ``"modal"``,
            or when the required API credential is missing.
    """
    # #CRITICAL: security: a model reviewing its own output is not an independent
    # check; tier 3 must surface as not-independent, never silently pass.
    # #VERIFY: test_same_backend_same_model_is_not_independent.
    backend = settings.review_provider

    if backend == "mock":
        return MockProvider(responses=["{}"] * 64), True

    if backend == "modal":
        msg = (
            "review_provider 'modal' is deferred to slice 2b; use openrouter or ollama"
        )
        raise ConfigurationError(msg)

    if backend == "openrouter":
        provider = build_openrouter_leg(settings, settings.review_openrouter_model)
        review_model: str | None = settings.review_openrouter_model
    else:  # "ollama"
        provider = build_ollama_leg(settings, settings.review_ollama_model)
        review_model = settings.review_ollama_model

    independent = backend != generator_provider or review_model != generator_model
    return provider, independent
