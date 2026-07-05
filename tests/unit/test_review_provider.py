"""Unit tests for review-model override resolution."""

from __future__ import annotations

from cyo_adventure.core.config import Settings
from cyo_adventure.moderation.review_provider import resolve_review_settings


def test_none_override_returns_settings_unchanged() -> None:
    """No override means the original settings object is returned as-is."""
    # #ASSUME: data-integrity: Settings requires a classifier key whenever
    # review_provider != "mock" (see config.py::_require_classifier_when_reviewing);
    # supply one so this test exercises resolve_review_settings, not that gate.
    # #VERIFY: test_non_mock_review_without_any_classifier_key_raises in test_config.py.
    settings = Settings(review_provider="openrouter", openai_api_key="k")
    assert resolve_review_settings(settings, None) is settings


def test_override_replaces_openrouter_model() -> None:
    """An override replaces review_openrouter_model when that backend is active."""
    settings = Settings(review_provider="openrouter", openai_api_key="k")
    result = resolve_review_settings(settings, "anthropic/claude-opus-4.8")
    assert result.review_openrouter_model == "anthropic/claude-opus-4.8"
    assert result.review_provider == "openrouter"


def test_override_replaces_ollama_model() -> None:
    """An override replaces review_ollama_model when that backend is active."""
    settings = Settings(review_provider="ollama", openai_api_key="k")
    result = resolve_review_settings(settings, "llama3.1:70b")
    assert result.review_ollama_model == "llama3.1:70b"


def test_override_is_a_noop_for_mock_backend() -> None:
    """The mock backend has no configurable model; the override is ignored."""
    settings = Settings(review_provider="mock")
    result = resolve_review_settings(settings, "some-model")
    assert result.review_provider == "mock"
