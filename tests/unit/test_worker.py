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
    _split_basic_auth,
    build_provider,
)
from cyo_adventure.generation.providers import (
    FallbackProvider,
    ModalProvider,
    OllamaProvider,
    OpenRouterProvider,
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


class TestBuildProviderLive:
    """build_provider assembles the live cascade and isolated legs from settings."""

    def test_claude_is_deferred(self) -> None:
        """The direct-Anthropic ('claude') adapter is deferred and raises."""
        settings = Settings(generation_provider="claude")  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings)
        # Points the operator at the supported OpenRouter path.
        assert "openrouter" in str(exc_info.value)

    def test_openrouter_without_key_raises(self) -> None:
        """openrouter without a credential raises ConfigurationError by key name."""
        settings = Settings(generation_provider="openrouter", openrouter_api_key=None)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings)
        message = str(exc_info.value)
        assert "OPENROUTER_API_KEY" in message

    def test_openrouter_key_value_not_leaked_in_error(self) -> None:
        """A missing-key error never echoes any key value."""
        settings = Settings(generation_provider="openrouter", openrouter_api_key=None)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_provider(settings)
        # The message references the variable by name only.
        assert "Bearer" not in str(exc_info.value)

    def test_openrouter_with_key_builds_three_leg_cascade(self) -> None:
        """openrouter + key + fallback enabled assembles the ordered cascade."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
        )
        provider = build_provider(settings)
        assert isinstance(provider, FallbackProvider)
        assert len(provider.legs) == 3
        assert isinstance(provider.legs[0], OpenRouterProvider)
        assert isinstance(provider.legs[1], OpenRouterProvider)
        assert isinstance(provider.legs[2], OllamaProvider)

    def test_openrouter_cascade_leg_order_matches_settings(self) -> None:
        """The cascade legs target the primary, fallback, and ollama models in order."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            openrouter_model="anthropic/claude-sonnet-4.6",
            openrouter_fallback_model="google/gemma-4-31b-it:free",
            ollama_model="qwen3",
        )
        provider = build_provider(settings)
        assert isinstance(provider, FallbackProvider)
        names = [leg.name for leg in provider.legs]  # type: ignore[attr-defined]
        assert names == [
            "openrouter:anthropic/claude-sonnet-4.6",
            "openrouter:google/gemma-4-31b-it:free",
            "ollama:qwen3",
        ]

    def test_openrouter_fallback_disabled_returns_bare_primary(self) -> None:
        """With fallback disabled the bare primary leg is returned (isolation runs)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="openrouter",
            openrouter_api_key="test-key",
            provider_fallback_enabled=False,
        )
        provider = build_provider(settings)
        assert isinstance(provider, OpenRouterProvider)
        assert provider.name == "openrouter:anthropic/claude-haiku-4.5"

    def test_ollama_returns_bare_ollama_leg(self) -> None:
        """generation_provider='ollama' returns the local Ollama leg alone."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama", ollama_model="qwen3:30b"
        )
        provider = build_provider(settings)
        assert isinstance(provider, OllamaProvider)
        assert provider.name == "ollama:qwen3:30b"

    def test_ollama_ca_bundle_valid_path_builds_leg(self) -> None:
        """A valid CA bundle path builds the leg with an SSLContext verifier."""
        import ssl

        import certifi

        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama", ollama_ca_bundle=certifi.where()
        )
        provider = build_provider(settings)
        assert isinstance(provider, OllamaProvider)
        # The CA bundle must be threaded through as an SSLContext (verify=),
        # not silently dropped; this is the leg's whole TLS-to-homelab purpose.
        assert isinstance(provider._verify, ssl.SSLContext)

    def test_ollama_no_ca_bundle_uses_default_verification(self) -> None:
        """Without a CA bundle the leg verifies against the public store (verify=True)."""
        settings = Settings(generation_provider="ollama")  # type: ignore[call-arg]
        provider = build_provider(settings)
        assert isinstance(provider, OllamaProvider)
        assert provider._verify is True

    def test_ollama_ca_bundle_bad_path_raises_configuration_error(self) -> None:
        """A nonexistent CA bundle path maps to ConfigurationError, not a raw OSError."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama",
            ollama_ca_bundle="/nonexistent/homelab-ca.pem",
        )
        with pytest.raises(ConfigurationError, match="OLLAMA_CA_BUNDLE"):
            build_provider(settings)

    def test_ollama_auth_over_http_remote_raises(self) -> None:
        """Basic auth over plaintext http to a remote host is rejected (cleartext leak)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama",
            ollama_base_url="http://ollama.example.com",
            ollama_auth="testservice:testcred",
        )
        with pytest.raises(ConfigurationError, match="cleartext"):
            build_provider(settings)

    def test_ollama_auth_over_https_is_allowed(self) -> None:
        """Basic auth over https builds the leg (credential is encrypted in transit)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama",
            ollama_base_url="https://ollama.example.com",
            ollama_auth="testservice:testcred",
        )
        assert isinstance(build_provider(settings), OllamaProvider)

    def test_ollama_auth_over_http_loopback_is_allowed(self) -> None:
        """Basic auth over http to loopback is allowed (never crosses the network)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="ollama",
            ollama_base_url="http://localhost:11434",
            ollama_auth="testservice:testcred",
        )
        assert isinstance(build_provider(settings), OllamaProvider)

    def test_modal_without_base_url_raises(self) -> None:
        """modal without MODAL_BASE_URL raises ConfigurationError by name."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="modal", modal_model="google/gemma-4-26b-a4b-it"
        )
        with pytest.raises(ConfigurationError, match="MODAL_BASE_URL"):
            build_provider(settings)

    def test_modal_without_model_raises(self) -> None:
        """modal without MODAL_MODEL raises ConfigurationError by name."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="modal",
            modal_base_url="https://example--cyo-standard.modal.run/v1",
        )
        with pytest.raises(ConfigurationError, match="MODAL_MODEL"):
            build_provider(settings)

    def test_modal_with_config_returns_bare_leg(self) -> None:
        """modal with both required settings returns a bare ModalProvider (no cascade)."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="modal",
            modal_base_url="https://example--cyo-standard.modal.run/v1",
            modal_model="google/gemma-4-26b-a4b-it",
        )
        provider = build_provider(settings)
        assert isinstance(provider, ModalProvider)
        assert provider.name == "modal:google/gemma-4-26b-a4b-it"

    def test_modal_partial_proxy_credentials_raises(self) -> None:
        """Setting only one of MODAL_PROXY_KEY/MODAL_PROXY_SECRET raises by name."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="modal",
            modal_base_url="https://example--cyo-standard.modal.run/v1",
            modal_model="google/gemma-4-26b-a4b-it",
            modal_proxy_key="only-the-key",
        )
        with pytest.raises(ConfigurationError, match="MODAL_PROXY_KEY"):
            build_provider(settings)


class TestSplitBasicAuth:
    """_split_basic_auth turns an OLLAMA_AUTH string into (username, password)."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            # A basic user:pass pair splits cleanly.
            ("testservice:testcred", ("testservice", "testcred")),
            # A username containing hyphens still splits on the first colon.
            ("test-svc-laptop:abc123", ("test-svc-laptop", "abc123")),
            # First-colon split keeps a password that itself contains colons.
            ("user:p:a:ss", ("user", "p:a:ss")),
            # Missing/blank/half values yield no credential.
            (None, (None, None)),
            ("", (None, None)),
            ("   ", (None, None)),
            ("no-colon", (None, None)),
            (":only-password", (None, None)),
            ("only-user:", (None, None)),
            # Surrounding whitespace on either half is trimmed (stray-space typo).
            (" testservice : testcred ", ("testservice", "testcred")),
            (" : ", (None, None)),
        ],
    )
    def test_split(
        self, value: str | None, expected: tuple[str | None, str | None]
    ) -> None:
        """A well-formed user:password splits on the first colon; else (None, None)."""
        assert _split_basic_auth(value) == expected


class TestCannedStorySchemaValid:
    """The canned mock story satisfies the Storybook schema."""

    def test_canned_story_dict_validates(self) -> None:
        """_CANNED_STORY is a valid Storybook (Pydantic model_validate succeeds)."""
        book = Storybook.model_validate(_CANNED_STORY)
        assert book.id == "s_mock_generated"
        assert book.metadata.tier == 1
        assert len(book.nodes) == 7

    def test_canned_story_json_round_trips(self) -> None:
        """JSON-serialised canned story round-trips through Storybook validation."""
        parsed = json.loads(_CANNED_STORY_JSON)
        book = Storybook.model_validate(parsed)
        assert book.id == "s_mock_generated"

    def test_canned_story_ending_count_matches_nodes(self) -> None:
        """The canned story's ending nodes agree with metadata.ending_count."""
        book = Storybook.model_validate(_CANNED_STORY)
        ending_nodes = [node for node in book.nodes if node.is_ending]
        assert len(ending_nodes) == book.metadata.ending_count
        assert book.metadata.ending_count >= 3

    def test_canned_story_start_node_exists(self) -> None:
        """start_node references an existing node id."""
        book = Storybook.model_validate(_CANNED_STORY)
        node_ids = {node.id for node in book.nodes}
        assert book.start_node in node_ids
