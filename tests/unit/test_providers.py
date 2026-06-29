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

import httpx
import pytest

from cyo_adventure.core.exceptions import ProviderError, ValidationError
from cyo_adventure.generation.providers import (
    FallbackProvider,
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
) -> OllamaProvider:
    """Build an OllamaProvider wired to a mock client with no backoff sleep."""
    return OllamaProvider(
        model=model,
        base_url="http://localhost:11434",
        timeout_seconds=30,
        username=username,
        password=password,
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
