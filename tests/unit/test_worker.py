"""Unit tests for the generation worker and provider factory (no DB, no Redis).

Tests cover:
1. build_provider("mock") returns a MockProvider seeded with a valid canned story.
2. build_provider with deferred providers raises ConfigurationError.
3. The canned mock story is schema-valid (Storybook.model_validate succeeds).
"""

from __future__ import annotations

import json

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.generation.provider import (
    _CANNED_STORY,
    _CANNED_STORY_JSON,
    MockProvider,
    build_provider,
)
from cyo_adventure.storybook.models import Storybook


@pytest.fixture
def mock_settings() -> Settings:
    """Return a Settings instance with generation_provider='mock'."""
    return Settings(generation_provider="mock")  # type: ignore[call-arg]


class TestBuildProviderMock:
    """build_provider with generation_provider='mock'."""

    def test_returns_mock_provider_instance(self, mock_settings: Settings) -> None:
        """build_provider('mock') returns a MockProvider."""
        provider = build_provider(mock_settings)
        assert isinstance(provider, MockProvider)

    def test_mock_provider_has_enough_responses(self, mock_settings: Settings) -> None:
        """The mock provider queue has at least Stage A + Stage B + 3 repairs."""
        provider = build_provider(mock_settings)
        assert isinstance(provider, MockProvider)
        assert len(provider.responses) >= 5

    def test_mock_provider_responses_are_canned_json(
        self, mock_settings: Settings
    ) -> None:
        """Each queued response is the canned story JSON string."""
        provider = build_provider(mock_settings)
        assert isinstance(provider, MockProvider)
        for response in provider.responses:
            assert isinstance(response, str)
            parsed = json.loads(response)
            assert parsed["id"] == "s_mock_generated"


class TestBuildProviderDeferred:
    """Deferred providers raise ConfigurationError mentioning Phase 2b."""

    @pytest.mark.parametrize("provider_name", ["claude", "ollama", "openrouter"])
    def test_deferred_provider_raises_configuration_error(
        self, provider_name: str
    ) -> None:
        """Non-mock providers raise ConfigurationError."""
        deferred_settings = Settings(generation_provider=provider_name)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(deferred_settings)
        assert "Phase 2b" in str(exc_info.value)
        assert provider_name in str(exc_info.value)

    @pytest.mark.parametrize("provider_name", ["claude", "ollama", "openrouter"])
    def test_deferred_provider_error_suggests_mock(self, provider_name: str) -> None:
        """Error message tells the user to set generation_provider=mock."""
        deferred_settings = Settings(generation_provider=provider_name)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(deferred_settings)
        assert "mock" in str(exc_info.value)


class TestCannedStorySchemaValid:
    """The canned mock story satisfies the Storybook schema."""

    def test_canned_story_dict_validates(self) -> None:
        """_CANNED_STORY is a valid Storybook (Pydantic model_validate succeeds)."""
        book = Storybook.model_validate(_CANNED_STORY)
        assert book.id == "s_mock_generated"
        assert book.metadata.tier == 1
        assert len(book.nodes) == 2

    def test_canned_story_json_round_trips(self) -> None:
        """JSON-serialised canned story round-trips through Storybook validation."""
        parsed = json.loads(_CANNED_STORY_JSON)
        book = Storybook.model_validate(parsed)
        assert book.id == "s_mock_generated"

    def test_canned_story_has_one_ending(self) -> None:
        """The canned story has exactly one ending node."""
        book = Storybook.model_validate(_CANNED_STORY)
        ending_nodes = [node for node in book.nodes if node.is_ending]
        assert len(ending_nodes) == 1
        assert book.metadata.ending_count == 1

    def test_canned_story_start_node_exists(self) -> None:
        """start_node references an existing node id."""
        book = Storybook.model_validate(_CANNED_STORY)
        node_ids = {node.id for node in book.nodes}
        assert book.start_node in node_ids
