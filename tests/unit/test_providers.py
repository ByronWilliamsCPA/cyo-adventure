"""Unit tests for the live generation provider adapters and fallback cascade.

All HTTP is faked with ``httpx.MockTransport`` (no network, no live LLM). Retry
backoff is set to ``0`` so transient-retry paths run instantly. The tests assert
the three-layer failure model:

- Layer 1 (adapter): transient failures retry the same model; leg-fatal failures
  raise immediately.
- Layer 2 (FallbackProvider): cross-leg failover, leg-fatal circuit breaker,
  exhaustion, and that a non-ProviderError (e.g. a PII ValidationError) is never
  caught.
"""

from __future__ import annotations

import base64
import json
import os
from typing import TYPE_CHECKING, Literal

import anthropic as anthropic_sdk
import httpx
import pytest
from anthropic.resources.messages.messages import AsyncMessages

from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import (
    ConfigurationError,
    ProviderError,
    ValidationError,
)
from cyo_adventure.generation.provider import build_anthropic_leg
from cyo_adventure.generation.providers import (
    AnthropicProvider,
    FallbackProvider,
    ModalProvider,
    OllamaProvider,
    OpenRouterProvider,
)
from cyo_adventure.generation.providers._base import strip_code_fences

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """Return an AsyncClient backed by a MockTransport running ``handler``."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _openrouter_ok_body(content: str) -> dict[str, object]:
    """Return a minimal OpenRouter chat-completions success payload."""
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _anthropic_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> anthropic_sdk.AsyncAnthropic:
    """Return an AsyncAnthropic backed by a MockTransport, with SDK retries off.

    max_retries=0 disables the SDK's own built-in retry so AnthropicProvider's
    Layer-1 run_with_retries loop is the only retry loop exercised in tests.
    """
    return anthropic_sdk.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _anthropic_ok_body(text: str) -> dict[str, object]:
    """Return a minimal Anthropic Messages API success payload."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-6",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _anthropic_error_body(error_type: str, message: str) -> dict[str, object]:
    """Return an Anthropic API error payload shape."""
    return {"type": "error", "error": {"type": error_type, "message": message}}


def _ollama_stream(*pieces: str, done: bool = True) -> str:
    """Build a newline-delimited JSON Ollama chat stream body.

    Each piece becomes one chunk's ``message.content``; a terminal ``done`` marker
    (with empty content) is appended unless ``done=False``. Mirrors the real
    ``/api/chat`` streaming response the adapter accumulates.
    """
    lines = [
        json.dumps({"message": {"role": "assistant", "content": piece}, "done": False})
        for piece in pieces
    ]
    if done:
        lines.append(
            json.dumps({"message": {"role": "assistant", "content": ""}, "done": True})
        )
    return "\n".join(lines) + "\n"


def _openrouter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    model: str = "anthropic/claude-sonnet-4.6",
    max_retries: int = 3,
    effort: Literal["off", "low", "medium", "high"] = "off",
) -> OpenRouterProvider:
    """Build an OpenRouterProvider wired to a mock client with no backoff sleep."""
    return OpenRouterProvider(
        api_key="test-key",
        model=model,
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=30,
        effort=effort,
        max_retries=max_retries,
        backoff_base_seconds=0,
        client=_client(handler),
    )


def _ollama(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    model: str = "qwen3",
    max_retries: int = 3,
    username: str | None = None,
    password: str | None = None,
    stream_byte_multiplier: int | None = None,
) -> OllamaProvider:
    """Build an OllamaProvider wired to a mock client with no backoff sleep."""
    kwargs: dict[str, object] = {}
    if stream_byte_multiplier is not None:
        kwargs["stream_byte_multiplier"] = stream_byte_multiplier
    return OllamaProvider(
        model=model,
        base_url="http://localhost:11434",
        timeout_seconds=30,
        username=username,
        password=password,
        max_retries=max_retries,
        backoff_base_seconds=0,
        client=_client(handler),
        **kwargs,
    )


def _modal(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    model: str = "google/gemma-4-26b-a4b-it",
    proxy_key: str | None = "test-key-id",
    proxy_secret: str | None = "test-key-secret",
    max_retries: int = 3,
) -> ModalProvider:
    """Build a ModalProvider wired to a mock client with no backoff sleep."""
    return ModalProvider(
        base_url="https://example--cyo-standard.modal.run/v1",
        model=model,
        proxy_key=proxy_key,
        proxy_secret=proxy_secret,
        timeout_seconds=30,
        max_retries=max_retries,
        backoff_base_seconds=0,
        client=_client(handler),
    )


# ---------------------------------------------------------------------------
# OpenRouterProvider
# ---------------------------------------------------------------------------


class TestOpenRouterProvider:
    """OpenRouter adapter: success, error mapping, retry, caching, reasoning."""

    @pytest.mark.asyncio
    async def test_success_returns_content_verbatim(self) -> None:
        """A 200 response returns the model content with no fence stripping."""
        raw = '{"id": "s_x", "title": "T"}'

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openrouter_ok_body(raw))

        provider = _openrouter(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == raw

    @pytest.mark.asyncio
    async def test_request_sends_model_and_max_tokens(self) -> None:
        """The request body carries model and max_tokens."""
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=_openrouter_ok_body("{}"))

        provider = _openrouter(handler)
        await provider.complete(system="s", prompt="u", max_tokens=4096)
        assert captured["model"] == "anthropic/claude-sonnet-4.6"
        assert captured["max_tokens"] == 4096

    @pytest.mark.asyncio
    async def test_effort_off_omits_reasoning_param(self) -> None:
        """With effort='off' (the default) no reasoning param is sent.

        Story generation is structured-JSON; enabling reasoning on Claude burns
        the max_tokens budget on thinking and returns empty content.
        """
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=_openrouter_ok_body("{}"))

        provider = _openrouter(handler, effort="off")
        await provider.complete(system="s", prompt="u", max_tokens=4096)
        assert "reasoning" not in captured

    @pytest.mark.asyncio
    async def test_explicit_effort_sends_reasoning_param(self) -> None:
        """A non-off effort is forwarded as reasoning.effort (opt-in)."""
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=_openrouter_ok_body("{}"))

        provider = _openrouter(handler, effort="high")
        await provider.complete(system="s", prompt="u", max_tokens=4096)
        assert captured["reasoning"] == {"effort": "high"}

    @pytest.mark.asyncio
    async def test_anthropic_model_marks_system_block_cacheable(self) -> None:
        """For anthropic/* models the system block carries cache_control."""
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=_openrouter_ok_body("{}"))

        provider = _openrouter(handler, model="anthropic/claude-sonnet-4.6")
        await provider.complete(system="SCHEMA", prompt="u", max_tokens=100)
        messages = captured["messages"]
        assert isinstance(messages, list)
        system_msg = messages[0]
        assert isinstance(system_msg["content"], list)
        block = system_msg["content"][0]
        assert block["text"] == "SCHEMA"
        assert block["cache_control"] == {"type": "ephemeral"}

    @pytest.mark.asyncio
    async def test_non_anthropic_model_uses_plain_system_string(self) -> None:
        """For non-anthropic models the system content is a plain string."""
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=_openrouter_ok_body("{}"))

        provider = _openrouter(handler, model="google/gemma-4-31b-it:free")
        await provider.complete(system="SCHEMA", prompt="u", max_tokens=100)
        messages = captured["messages"]
        assert isinstance(messages, list)
        assert messages[0]["content"] == "SCHEMA"

    @pytest.mark.asyncio
    async def test_404_is_leg_fatal_without_retry(self) -> None:
        """An invalid/unavailable model (404) raises leg-fatal and does not retry."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(404, json={"error": "no such model"})

        provider = _openrouter(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is True
        assert calls == 1

    @pytest.mark.asyncio
    async def test_401_is_leg_fatal(self) -> None:
        """An auth failure (401) raises leg-fatal."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "bad key"})

        provider = _openrouter(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 402, 403])
    async def test_other_4xx_are_leg_fatal_without_retry(self, status: int) -> None:
        """400 (bad request), 402 (out of credits), and 403 (forbidden) are
        leg-fatal and must not retry against the same model."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(status, json={"error": "fatal"})

        provider = _openrouter(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is True
        assert exc_info.value.status_code == status
        assert calls == 1

    @pytest.mark.asyncio
    async def test_429_retries_then_succeeds(self) -> None:
        """A rate-limit (429) is transient: retry then succeed."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(429, json={"error": "slow down"})
            return httpx.Response(200, json=_openrouter_ok_body("ok"))

        provider = _openrouter(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == "ok"
        assert calls == 2

    @pytest.mark.asyncio
    async def test_persistent_5xx_exhausts_to_transient_error(self) -> None:
        """A persistent 500 exhausts retries and raises a non-leg-fatal error."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500, json={"error": "boom"})

        provider = _openrouter(handler, max_retries=3)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False
        assert calls == 3

    @pytest.mark.asyncio
    async def test_connect_error_is_transient_and_retried(self) -> None:
        """A transport error (connect/timeout) is transient and retried."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 2:
                raise httpx.ConnectError("refused")
            return httpx.Response(200, json=_openrouter_ok_body("ok"))

        provider = _openrouter(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == "ok"
        assert calls == 2

    @pytest.mark.asyncio
    async def test_empty_content_raises_transient(self) -> None:
        """A 200 with empty content raises a non-leg-fatal ProviderError."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openrouter_ok_body(""))

        provider = _openrouter(handler, max_retries=1)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_malformed_payload_raises_transient(self) -> None:
        """A 200 missing the choices array raises a non-leg-fatal ProviderError."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        provider = _openrouter(handler, max_retries=1)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False

    def test_name_includes_model(self) -> None:
        """The leg name combines provider and model id."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openrouter_ok_body("ok"))

        provider = _openrouter(handler, model="anthropic/claude-sonnet-4.6")
        assert provider.name == "openrouter:anthropic/claude-sonnet-4.6"

    @pytest.mark.asyncio
    async def test_strips_markdown_code_fence(self) -> None:
        """A model that wraps JSON in a ```json fence is normalized to raw JSON.

        Gemini Flash and Haiku wrap output despite instructions; the orchestrator
        parses with json.loads, so the adapter must return de-fenced content.
        """
        fenced = '```json\n{"schema_version": "1.0"}\n```'

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openrouter_ok_body(fenced))

        provider = _openrouter(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == '{"schema_version": "1.0"}'
        assert json.loads(result) == {"schema_version": "1.0"}


class TestStripCodeFences:
    """Unit tests for the shared fence-stripping helper."""

    def test_plain_json_unchanged(self) -> None:
        """Raw JSON without a fence is returned unchanged (original models)."""
        assert strip_code_fences('{"a": 1}') == '{"a": 1}'

    def test_json_language_fence(self) -> None:
        """A ```json fence is removed."""
        assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_bare_fence(self) -> None:
        """A bare ``` fence (no language tag) is removed."""
        assert strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_surrounding_whitespace(self) -> None:
        """Leading/trailing whitespace around the fence is trimmed."""
        assert strip_code_fences('  \n```json\n{"a": 1}\n```\n  ') == '{"a": 1}'


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


class TestOllamaProvider:
    """Ollama adapter: success, error mapping, retry, request shape."""

    @pytest.mark.asyncio
    async def test_success_accumulates_streamed_chunks(self) -> None:
        """A streamed 200 response concatenates each chunk's message content."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_ollama_stream("st", "or", "y"))

        provider = _ollama(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == "story"

    @pytest.mark.asyncio
    async def test_request_maps_max_tokens_to_num_predict(self) -> None:
        """max_tokens is forwarded as options.num_predict, stream is True."""
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, text=_ollama_stream("x"))

        provider = _ollama(handler)
        await provider.complete(system="s", prompt="u", max_tokens=2048)
        assert captured["options"] == {"num_predict": 2048}
        assert captured["stream"] is True
        assert captured["model"] == "qwen3"

    @pytest.mark.asyncio
    async def test_request_disables_response_compression(self) -> None:
        """The stream request sends Accept-Encoding: identity (Traefik compress no-op)."""
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["accept_encoding"] = request.headers.get("accept-encoding", "")
            return httpx.Response(200, text=_ollama_stream("ok"))

        provider = _ollama(handler)
        await provider.complete(system="s", prompt="u", max_tokens=100)
        assert captured["accept_encoding"] == "identity"

    @pytest.mark.asyncio
    async def test_404_missing_model_is_leg_fatal(self) -> None:
        """A missing/unpulled model (404) raises leg-fatal without retry."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(404, json={"error": "model not found"})

        provider = _ollama(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is True
        assert calls == 1

    @pytest.mark.asyncio
    async def test_503_retries_then_succeeds(self) -> None:
        """A transient 503 is retried then succeeds."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, json={"error": "loading"})
            return httpx.Response(200, text=_ollama_stream("ok"))

        provider = _ollama(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == "ok"
        assert calls == 2

    @pytest.mark.asyncio
    async def test_empty_content_raises_transient(self) -> None:
        """A stream that yields no content raises a non-leg-fatal ProviderError."""

        def handler(_request: httpx.Request) -> httpx.Response:
            # Only the terminal done marker, no content chunks.
            return httpx.Response(200, text=_ollama_stream(done=True))

        provider = _ollama(handler, max_retries=1)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_error_chunk_raises_transient(self) -> None:
        """An {\"error\": ...} chunk mid-stream raises a non-leg-fatal error."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text='{"error": "model is loading"}\n')

        provider = _ollama(handler, max_retries=1)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_non_json_line_raises_transient(self) -> None:
        """A malformed (non-JSON) stream line raises a non-leg-fatal error."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not json at all\n")

        provider = _ollama(handler, max_retries=1)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_error_chunk_after_partial_content_raises_transient(self) -> None:
        """An error chunk arriving after valid content chunks raises transient."""

        def handler(_request: httpx.Request) -> httpx.Response:
            body = (
                json.dumps(
                    {"message": {"role": "assistant", "content": "par"}, "done": False}
                )
                + "\n"
                + json.dumps({"error": "model unloaded mid-stream"})
                + "\n"
            )
            return httpx.Response(200, text=body)

        provider = _ollama(handler, max_retries=1)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_retry_after_mid_stream_error_discards_partial_content(self) -> None:
        """After a mid-stream error, the retry returns only the second attempt's text."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    200,
                    text=(
                        json.dumps(
                            {
                                "message": {"role": "assistant", "content": "PARTIAL"},
                                "done": False,
                            }
                        )
                        + "\n"
                        + json.dumps({"error": "boom"})
                        + "\n"
                    ),
                )
            return httpx.Response(200, text=_ollama_stream("clean"))

        provider = _ollama(handler, max_retries=2)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == "clean"
        assert "PARTIAL" not in result
        assert calls == 2

    @pytest.mark.asyncio
    async def test_basic_auth_header_sent_when_credentials_present(self) -> None:
        """Both username and password produce an HTTP Basic Authorization header."""
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["authorization"] = request.headers.get("authorization", "")
            return httpx.Response(200, text=_ollama_stream("ok"))

        # Prefer env vars so real homelab creds can be injected in live integration
        # runs. The synthetic defaults (testservice / testservice-pass) are used in
        # unit and CI runs; the adapter only base64-encodes user:pass, so the value
        # does not matter for correctness.
        test_user = os.environ.get("OLLAMA_TEST_USER", "testservice")
        test_pw = os.environ.get("OLLAMA_TEST_PW", f"{test_user}-pass")
        provider = _ollama(handler, username=test_user, password=test_pw)
        await provider.complete(system="s", prompt="u", max_tokens=100)

        expected = base64.b64encode(f"{test_user}:{test_pw}".encode()).decode()
        assert captured["authorization"] == f"Basic {expected}"

    @pytest.mark.asyncio
    async def test_no_auth_header_when_credentials_absent(self) -> None:
        """With no credentials the request carries no Authorization header."""
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["authorization"] = request.headers.get("authorization", "")
            return httpx.Response(200, text=_ollama_stream("ok"))

        provider = _ollama(handler)
        await provider.complete(system="s", prompt="u", max_tokens=100)
        assert captured["authorization"] == ""

    @pytest.mark.asyncio
    async def test_302_auth_redirect_is_leg_fatal(self) -> None:
        """An auth-proxy 302 (Authentik login) is leg-fatal without retry."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                302, headers={"location": "https://auth.example/login"}
            )

        provider = _ollama(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is True
        assert "302" in str(exc_info.value)
        assert calls == 1

    @pytest.mark.asyncio
    async def test_stream_at_byte_ceiling_succeeds(self) -> None:
        """A stream totaling exactly the max_tokens-derived byte ceiling succeeds."""
        # OllamaProvider.STREAM_BYTE_MULTIPLIER (default 16) x max_tokens is the
        # ceiling; max_tokens=1 gives a tiny, exactly-controllable 16-byte cap.
        content = "x" * 16

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_ollama_stream(content))

        provider = _ollama(handler, max_retries=1)
        result = await provider.complete(system="s", prompt="u", max_tokens=1)
        assert result == content

    @pytest.mark.asyncio
    async def test_stream_over_byte_ceiling_raises_transient(self) -> None:
        """A stream one byte over the max_tokens-derived ceiling is rejected."""
        content = "x" * 17

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_ollama_stream(content))

        provider = _ollama(handler, max_retries=1)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=1)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_stream_byte_ceiling_scales_with_max_tokens(self) -> None:
        """A larger max_tokens raises the byte ceiling proportionally."""
        content = "y" * 32  # fits under max_tokens=2 -> 32-byte ceiling

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_ollama_stream(content))

        provider = _ollama(handler, max_retries=1)
        result = await provider.complete(system="s", prompt="u", max_tokens=2)
        assert result == content

    @pytest.mark.asyncio
    async def test_stream_byte_ceiling_configurable_multiplier(self) -> None:
        """A custom stream_byte_multiplier raises the effective ceiling.

        The content is sized to sit strictly between the default ceiling and
        the custom one, so this only passes when the custom multiplier is
        genuinely honored; a silent fallback to DEFAULT_STREAM_BYTE_MULTIPLIER
        (16) would reject the same stream. The paired default-multiplier leg
        proves 24 bytes really does exceed the default ceiling, so the
        custom-multiplier success is not a false pass.
        """
        # 24 bytes: over the default ceiling (max_tokens=1 * 16 = 16) but under
        # the custom ceiling (max_tokens=1 * 32 = 32).
        content = "z" * 24

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_ollama_stream(content))

        # Default multiplier (16): 24 bytes exceeds the 16-byte ceiling, reject.
        default_provider = _ollama(handler, max_retries=1)
        with pytest.raises(ProviderError) as exc_info:
            await default_provider.complete(system="s", prompt="u", max_tokens=1)
        assert exc_info.value.leg_fatal is False

        # Custom multiplier (32): the ceiling rises to 32 bytes, accept.
        provider = _ollama(handler, max_retries=1, stream_byte_multiplier=32)
        result = await provider.complete(system="s", prompt="u", max_tokens=1)
        assert result == content


# ---------------------------------------------------------------------------
# FallbackProvider
# ---------------------------------------------------------------------------


class _StubLeg:
    """A scripted GenerationProvider leg for cascade tests."""

    def __init__(self, name: str, outcomes: list[object]) -> None:
        """Build a stub leg.

        Args:
            name: The leg name (used in cascade labels/logs).
            outcomes: Per-call outcomes; each is a ``str`` to return or an
                ``Exception`` to raise, consumed in order.
        """
        self.name = name
        self._outcomes = outcomes
        self.calls = 0

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Return or raise the next scripted outcome."""
        _ = (system, prompt, max_tokens)
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)


class TestFallbackProvider:
    """Composite cascade: failover, circuit breaker, exhaustion, propagation."""

    @pytest.mark.asyncio
    async def test_first_leg_success_skips_others(self) -> None:
        """When the first leg succeeds, later legs are not called."""
        leg_a = _StubLeg("a", ["ok"])
        leg_b = _StubLeg("b", ["never"])
        cascade = FallbackProvider(legs=[leg_a, leg_b])
        result = await cascade.complete(system="s", prompt="u", max_tokens=10)
        assert result == "ok"
        assert leg_b.calls == 0

    @pytest.mark.asyncio
    async def test_transient_failover_to_next_leg(self) -> None:
        """A leg's ProviderError fails over to the next live leg."""
        leg_a = _StubLeg("a", [ProviderError("down", leg_fatal=False)])
        leg_b = _StubLeg("b", ["ok"])
        cascade = FallbackProvider(legs=[leg_a, leg_b])
        result = await cascade.complete(system="s", prompt="u", max_tokens=10)
        assert result == "ok"
        assert leg_a.calls == 1
        assert leg_b.calls == 1

    @pytest.mark.asyncio
    async def test_leg_fatal_marks_leg_dead_for_subsequent_calls(self) -> None:
        """A leg-fatal failure marks the leg dead so it is skipped next call."""
        leg_a = _StubLeg("a", [ProviderError("gone", leg_fatal=True), "should-not-run"])
        leg_b = _StubLeg("b", ["first", "second"])
        cascade = FallbackProvider(legs=[leg_a, leg_b])

        first = await cascade.complete(system="s", prompt="u", max_tokens=10)
        second = await cascade.complete(system="s", prompt="u", max_tokens=10)

        assert first == "first"
        assert second == "second"
        # leg_a was tried exactly once (the leg-fatal call) and never again.
        assert leg_a.calls == 1
        assert leg_b.calls == 2

    @pytest.mark.asyncio
    async def test_all_legs_exhausted_raises_provider_error(self) -> None:
        """When every leg fails, the cascade raises ProviderError."""
        leg_a = _StubLeg("a", [ProviderError("a down", leg_fatal=False)])
        leg_b = _StubLeg("b", [ProviderError("b down", leg_fatal=False)])
        cascade = FallbackProvider(legs=[leg_a, leg_b])
        with pytest.raises(ProviderError) as exc_info:
            await cascade.complete(system="s", prompt="u", max_tokens=10)
        assert "exhausted" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_non_provider_error_propagates_uncaught(self) -> None:
        """A non-ProviderError (e.g. a PII ValidationError) is never caught."""
        leg_a = _StubLeg("a", [ValidationError("PII", field="prompt")])
        leg_b = _StubLeg("b", ["should-not-run"])
        cascade = FallbackProvider(legs=[leg_a, leg_b])
        with pytest.raises(ValidationError):
            await cascade.complete(system="s", prompt="u", max_tokens=10)
        # The cascade did not fail over past the raising leg.
        assert leg_b.calls == 0

    @pytest.mark.asyncio
    async def test_attempt_cap_raises(self) -> None:
        """The per-run attempt cap bounds total leg invocations."""
        leg_a = _StubLeg("a", [ProviderError("x", leg_fatal=False)] * 5)
        leg_b = _StubLeg("b", [ProviderError("y", leg_fatal=False)] * 5)
        cascade = FallbackProvider(legs=[leg_a, leg_b], max_total_attempts=1)
        with pytest.raises(ProviderError) as exc_info:
            await cascade.complete(system="s", prompt="u", max_tokens=10)
        # Cap is 1: the first leg consumes the only allowed attempt, then the cap
        # trips before the second leg runs.
        assert "attempt cap" in str(exc_info.value)
        assert leg_a.calls == 1
        assert leg_b.calls == 0

    def test_name_lists_legs_in_order(self) -> None:
        """The cascade name lists its legs in order."""
        cascade = FallbackProvider(legs=[_StubLeg("a", []), _StubLeg("b", [])])
        assert cascade.name == "fallback[a,b]"


# ---------------------------------------------------------------------------
# ProviderError construction invariant
# ---------------------------------------------------------------------------


class TestProviderErrorInvariant:
    """The leg_fatal/status_code pairing guard that protects the circuit breaker."""

    def test_provider_error_rejects_fatal_success_status(self) -> None:
        """leg_fatal=True with a successful (< 400) status_code is rejected: a
        2xx/3xx response cannot represent a fatal leg failure."""
        with pytest.raises(ValueError, match="contradictory"):
            ProviderError(
                "impossible", provider="openrouter", status_code=200, leg_fatal=True
            )

    def test_provider_error_allows_fatal_4xx(self) -> None:
        """leg_fatal=True with a 4xx status_code is the normal leg-fatal case."""
        err = ProviderError(
            "bad model", provider="openrouter", status_code=404, leg_fatal=True
        )
        assert err.leg_fatal is True
        assert err.status_code == 404

    def test_provider_error_allows_transient_without_status(self) -> None:
        """A transient error (leg_fatal=False) needs no status_code."""
        err = ProviderError("timeout", provider="ollama", leg_fatal=False)
        assert err.leg_fatal is False
        assert err.status_code is None


# ---------------------------------------------------------------------------
# OllamaProvider: additional branch coverage
# ---------------------------------------------------------------------------


class TestOllamaProviderBranches:
    """Cover the remaining uncovered branches in the Ollama adapter."""

    @pytest.mark.asyncio
    async def test_http_400_bad_request_is_leg_fatal(self) -> None:
        """An HTTP 400 raises a leg-fatal ProviderError with 'bad request' in message."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "bad request"})

        provider = _ollama(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is True
        assert "bad request" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unexpected_4xx_is_leg_fatal(self) -> None:
        """A 4xx not explicitly mapped (e.g. 401) is still leg-fatal."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "auth required"})

        provider = _ollama(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is True
        assert "401" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_raises_transient_provider_error(self) -> None:
        """An httpx.TimeoutException maps to a non-leg-fatal ProviderError."""

        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout", request=_request)

        provider = _ollama(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_empty_stream_lines_are_skipped(self) -> None:
        """Blank lines in the stream body are silently ignored."""

        def handler(_request: httpx.Request) -> httpx.Response:
            # Include a blank line between chunks -- the adapter should skip it.
            body = (
                json.dumps(
                    {
                        "message": {"role": "assistant", "content": "hello"},
                        "done": False,
                    }
                )
                + "\n\n"
                + json.dumps(
                    {"message": {"role": "assistant", "content": ""}, "done": True}
                )
                + "\n"
            )
            return httpx.Response(200, text=body)

        provider = _ollama(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_non_dict_json_chunk_returns_empty_string(self) -> None:
        """A JSON-parseable non-dict chunk (e.g. a number) is treated as empty content."""

        def handler(_request: httpx.Request) -> httpx.Response:
            # First chunk is a JSON number (non-dict), second is the real content.
            body = (
                "42\n"
                + json.dumps(
                    {"message": {"role": "assistant", "content": "ok"}, "done": False}
                )
                + "\n"
                + json.dumps(
                    {"message": {"role": "assistant", "content": ""}, "done": True}
                )
                + "\n"
            )
            return httpx.Response(200, text=body)

        provider = _ollama(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == "ok"


# ---------------------------------------------------------------------------
# OpenRouterProvider: additional branch coverage
# ---------------------------------------------------------------------------


class TestOpenRouterProviderBranches:
    """Cover the remaining uncovered branches in the OpenRouter adapter."""

    @pytest.mark.asyncio
    async def test_non_json_response_body_raises_transient(self) -> None:
        """A response body that is not valid JSON raises a non-leg-fatal ProviderError."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not-json-at-all")

        provider = _openrouter(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_unexpected_4xx_is_leg_fatal(self) -> None:
        """A 4xx not in the explicit maps (e.g. 405) is still leg-fatal."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(405, json={"error": "method not allowed"})

        provider = _openrouter(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is True
        assert "405" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_dig_content_non_dict_payload_raises_via_empty_content(self) -> None:
        """A JSON list response body triggers the 'no content' ProviderError path."""

        def handler(_request: httpx.Request) -> httpx.Response:
            # A JSON array is valid JSON but fails as_str_map(payload) -> None.
            return httpx.Response(200, json=[1, 2, 3])

        provider = _openrouter(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_dig_content_non_dict_choice_raises_via_empty_content(self) -> None:
        """When choices[0] is not a dict the content path falls through to empty."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": ["not-a-dict"]})

        provider = _openrouter(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_dig_content_non_dict_message_raises_via_empty_content(self) -> None:
        """When message is not a dict the content path returns None -> empty content."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": "not-a-dict"}]})

        provider = _openrouter(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False


# ---------------------------------------------------------------------------
# ModalProvider
# ---------------------------------------------------------------------------


class TestModalProvider:
    """Modal adapter: success, error mapping, retry, optional proxy-key auth."""

    @pytest.mark.asyncio
    async def test_success_returns_content_verbatim(self) -> None:
        """A 200 response returns the model content verbatim (no fences to strip)."""
        raw = '{"id": "s_x", "title": "T"}'

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openrouter_ok_body(raw))

        provider = _modal(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == raw

    @pytest.mark.asyncio
    async def test_request_sends_model_and_max_tokens(self) -> None:
        """The request body carries model and max_tokens, plain system/user messages."""
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=_openrouter_ok_body("{}"))

        provider = _modal(handler)
        await provider.complete(system="SYS", prompt="USR", max_tokens=4096)
        assert captured["model"] == "google/gemma-4-26b-a4b-it"
        assert captured["max_tokens"] == 4096
        assert captured["messages"] == [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "USR"},
        ]

    @pytest.mark.asyncio
    async def test_proxy_credentials_send_modal_key_and_secret_headers(self) -> None:
        """A configured proxy_key/proxy_secret pair sends the Modal-Key/Modal-Secret headers."""
        captured_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(request.headers)
            return httpx.Response(200, json=_openrouter_ok_body("ok"))

        provider = _modal(
            handler, proxy_key="secret-token-id", proxy_secret="secret-token-value"
        )
        await provider.complete(system="s", prompt="u", max_tokens=100)
        assert captured_headers["modal-key"] == "secret-token-id"
        assert captured_headers["modal-secret"] == "secret-token-value"

    @pytest.mark.asyncio
    async def test_no_proxy_credentials_omits_auth_headers(self) -> None:
        """A None proxy_key/proxy_secret pair sends neither header at all."""
        captured_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(request.headers)
            return httpx.Response(200, json=_openrouter_ok_body("ok"))

        provider = _modal(handler, proxy_key=None, proxy_secret=None)
        await provider.complete(system="s", prompt="u", max_tokens=100)
        assert "modal-key" not in captured_headers
        assert "modal-secret" not in captured_headers

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("proxy_key", "proxy_secret"),
        [
            pytest.param("only-the-key", None, id="key-only"),
            pytest.param(None, "only-the-secret", id="secret-only"),
        ],
    )
    async def test_partial_proxy_credentials_omits_auth_headers(
        self, proxy_key: str | None, proxy_secret: str | None
    ) -> None:
        """A half-set proxy credential pair sends neither header (ModalProvider's own
        fail-safe; the fail-loud ConfigurationError for this case belongs to
        build_modal_leg and is tested in test_worker.py, not here).
        """
        captured_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(request.headers)
            return httpx.Response(200, json=_openrouter_ok_body("ok"))

        provider = _modal(handler, proxy_key=proxy_key, proxy_secret=proxy_secret)
        await provider.complete(system="s", prompt="u", max_tokens=100)
        assert "modal-key" not in captured_headers
        assert "modal-secret" not in captured_headers

    @pytest.mark.asyncio
    async def test_404_is_leg_fatal_without_retry(self) -> None:
        """An invalid/unavailable model (404) raises leg-fatal and does not retry."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(404, json={"error": "no such model"})

        provider = _modal(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is True
        assert calls == 1

    @pytest.mark.asyncio
    async def test_401_is_leg_fatal(self) -> None:
        """An auth failure (401) raises leg-fatal."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "bad key"})

        provider = _modal(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is True

    @pytest.mark.asyncio
    async def test_429_retries_then_succeeds(self) -> None:
        """A rate-limit (429) is transient: retry then succeed."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(429, json={"error": "slow down"})
            return httpx.Response(200, json=_openrouter_ok_body("ok"))

        provider = _modal(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == "ok"
        assert calls == 2

    @pytest.mark.asyncio
    async def test_persistent_5xx_exhausts_to_transient_error(self) -> None:
        """A persistent 500 exhausts retries and raises a non-leg-fatal error."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500, json={"error": "boom"})

        provider = _modal(handler, max_retries=3)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="u", max_tokens=100)
        assert exc_info.value.leg_fatal is False
        assert calls == 3

    @pytest.mark.asyncio
    async def test_connect_error_is_transient_and_retried(self) -> None:
        """A transport error (connect/timeout) is transient and retried."""
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 2:
                raise httpx.ConnectError("refused")
            return httpx.Response(200, json=_openrouter_ok_body("ok"))

        provider = _modal(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == "ok"
        assert calls == 2

    @pytest.mark.asyncio
    async def test_strips_markdown_code_fence(self) -> None:
        """A model that wraps JSON in a fence is normalized to raw JSON."""
        fenced = '```json\n{"schema_version": "1.0"}\n```'

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openrouter_ok_body(fenced))

        provider = _modal(handler)
        result = await provider.complete(system="s", prompt="u", max_tokens=100)
        assert result == '{"schema_version": "1.0"}'
        assert json.loads(result) == {"schema_version": "1.0"}

    def test_name_includes_model(self) -> None:
        """The leg name combines provider and model id."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openrouter_ok_body("ok"))

        provider = _modal(handler, model="openai/gpt-oss-120b")
        assert provider.name == "modal:openai/gpt-oss-120b"


# ---------------------------------------------------------------------------
# AnthropicProvider (direct Anthropic Messages API, WS-C PR1)
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    """Unit tests for the direct-Anthropic adapter (WS-C PR1)."""

    def _provider(
        self, handler: Callable[[httpx.Request], httpx.Response]
    ) -> AnthropicProvider:
        return AnthropicProvider(
            api_key="test-key",
            model="claude-sonnet-4-6",
            base_url="https://api.anthropic.com",
            timeout_seconds=5,
            backoff_base_seconds=0,
            client=_anthropic_client(handler),
        )

    @pytest.mark.asyncio
    async def test_success_returns_content(self) -> None:
        """A 200 response returns the text content, stripped of any code fence."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_anthropic_ok_body("```json\n{}\n```"))

        provider = self._provider(handler)
        result = await provider.complete(system="s", prompt="p", max_tokens=100)
        assert result == "{}"

    @pytest.mark.asyncio
    async def test_name_and_model_properties(self) -> None:
        """name and model both reflect the configured model id."""
        provider = self._provider(
            lambda _r: httpx.Response(200, json=_anthropic_ok_body("x"))
        )
        assert provider.name == "anthropic:claude-sonnet-4-6"
        assert provider.model == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_transient_429_retries_then_succeeds(self) -> None:
        """A 429 retries against the same model and succeeds on the next attempt."""
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    429, json=_anthropic_error_body("rate_limit_error", "slow down")
                )
            return httpx.Response(200, json=_anthropic_ok_body("ok"))

        provider = self._provider(handler)
        result = await provider.complete(system="s", prompt="p", max_tokens=10)
        assert result == "ok"
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_leg_fatal_401_raises_immediately(self) -> None:
        """A 401 (authentication_error) raises ProviderError(leg_fatal=True) with no retry."""
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(
                401, json=_anthropic_error_body("authentication_error", "bad key")
            )

        provider = self._provider(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="p", max_tokens=10)
        assert exc_info.value.leg_fatal is True
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_leg_fatal_404_raises_immediately(self) -> None:
        """A 404 (not_found_error, e.g. unknown model) is leg-fatal."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                404, json=_anthropic_error_body("not_found_error", "unknown model")
            )

        provider = self._provider(handler)
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="p", max_tokens=10)
        assert exc_info.value.leg_fatal is True

    @pytest.mark.asyncio
    async def test_connection_error_is_transient(self) -> None:
        """A transport-level connection failure is transient, not leg-fatal."""

        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = AnthropicProvider(
            api_key="test-key",
            model="claude-sonnet-4-6",
            base_url="https://api.anthropic.com",
            timeout_seconds=5,
            max_retries=1,
            backoff_base_seconds=0,
            client=_anthropic_client(handler),
        )
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="p", max_tokens=10)
        assert exc_info.value.leg_fatal is False

    @pytest.mark.asyncio
    async def test_empty_content_is_transient(self) -> None:
        """A 200 with no text content block is treated as a retryable malformed success."""

        def handler(_request: httpx.Request) -> httpx.Response:
            body = _anthropic_ok_body("")
            body["content"] = []
            return httpx.Response(200, json=body)

        provider = AnthropicProvider(
            api_key="test-key",
            model="claude-sonnet-4-6",
            base_url="https://api.anthropic.com",
            timeout_seconds=5,
            max_retries=1,
            backoff_base_seconds=0,
            client=_anthropic_client(handler),
        )
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="p", max_tokens=10)
        assert exc_info.value.leg_fatal is False


# ---------------------------------------------------------------------------
# build_anthropic_leg (fail-fast credential check, WS-C PR1)
# ---------------------------------------------------------------------------


class TestBuildAnthropicLeg:
    """build_anthropic_leg's fail-fast-by-name credential check.

    This builder is standalone in Task 7: it is not yet wired into
    build_provider's dispatch (that is Task 8), so it is exercised directly.
    """

    def test_missing_key_raises_configuration_error_by_name(self) -> None:
        """A missing ANTHROPIC_API_KEY raises ConfigurationError naming the key."""
        settings = Settings(generation_provider="anthropic", anthropic_api_key=None)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_anthropic_leg(settings, settings.anthropic_model)
        assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_missing_key_error_never_contains_a_key_value(self) -> None:
        """The fail-fast error names the key only, never a credential value."""
        settings = Settings(generation_provider="anthropic", anthropic_api_key=None)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError) as exc_info:
            build_anthropic_leg(settings, settings.anthropic_model)
        assert "Bearer" not in str(exc_info.value)

    def test_with_key_builds_anthropic_provider(self) -> None:
        """A configured key builds a live AnthropicProvider for the given model."""
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="anthropic", anthropic_api_key="test-key"
        )
        provider = build_anthropic_leg(settings, "claude-sonnet-4-6")
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_anthropic_key_value_not_leaked_in_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even with the API key set to a real (sentinel) value, a ProviderError
        raised on a failing request never echoes the key's value in its message
        or repr. Carried forward from Task 6's config #VERIFY marker: presence
        is checked by name in the fail-fast tests above, this test guards the
        VALUE never leaking once a key is actually configured and used to build
        a live client.
        """
        sentinel_key = "sk-ant-sentinel-do-not-leak-9f3c2b7a"
        settings = Settings(  # type: ignore[call-arg]
            generation_provider="anthropic", anthropic_api_key=sentinel_key
        )
        provider = build_anthropic_leg(settings, settings.anthropic_model)
        assert isinstance(provider, AnthropicProvider)

        async def _raise_401(*_args: object, **_kwargs: object) -> None:
            response = httpx.Response(
                401,
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
            )
            raise anthropic_sdk.APIStatusError("bad key", response=response, body=None)

        # Patch the SDK's own AsyncMessages.create (a public SDK class), not a
        # private attribute of AnthropicProvider, so this stays basedpyright
        # reportPrivateUsage-clean while still exercising the real client the
        # sentinel key was used to construct.
        monkeypatch.setattr(AsyncMessages, "create", _raise_401)

        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(system="s", prompt="p", max_tokens=10)

        assert sentinel_key not in str(exc_info.value)
        assert sentinel_key not in repr(exc_info.value)
