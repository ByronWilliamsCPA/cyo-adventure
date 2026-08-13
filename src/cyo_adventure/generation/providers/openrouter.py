"""OpenRouter generation provider adapter (Phase 2b primary leg).

Calls the OpenRouter chat-completions API and returns the model text. This
adapter owns **Layer 1** of the three-layer failure model: it retries TRANSIENT
failures (connection error, timeout, HTTP 429, HTTP 5xx) against the *same*
model with exponential backoff, and maps leg-fatal failures (invalid/unavailable
model, authentication) to :class:`~cyo_adventure.core.exceptions.ProviderError`
immediately. It never inspects gate results or content quality; a schema-valid
but gate-blocked response is a successful completion here (Layer 3 handles it).

The adapter normalizes the output through ``strip_code_fences`` before returning:
the Phase 2b probe found the pinned first-party models usually emit raw JSON, but
some models wrap output in a markdown fence despite instructions, so the
normalization is applied unconditionally and the orchestrator's ``json.loads``
always receives plain JSON.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final, Literal

import httpx

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.generation.providers._base import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_MAX_RETRIES,
    dig_content,
    dig_finish_reason,
    dig_reasoning_tokens,
    dig_usage,
    elapsed_ms,
    run_with_retries,
    strip_code_fences,
)
from cyo_adventure.generation.usage import Completion, TokenUsage

if TYPE_CHECKING:
    from collections.abc import Mapping

# HTTP statuses worth retrying against the same model: rate limiting and
# transient server faults. Anything 5xx is treated as transient even if not
# enumerated here.
_TRANSIENT_STATUS: Final[frozenset[int]] = frozenset({408, 409, 425, 429})

# HTTP statuses that mean this leg cannot serve the request at all this run:
# bad request / unavailable model (400, 404), out of credits (402), and auth
# failures (401, 403). These mark the leg dead in the cascade's circuit breaker.
_LEG_FATAL_STATUS: Final[frozenset[int]] = frozenset({400, 401, 402, 403, 404})

# Reasoning-effort levels accepted by the adapter. Mirrors ``Settings.llm_effort``
# so an out-of-range value is a type error at the call site, not a silent
# forward of an invalid ``reasoning.effort`` to the API.
_Effort = Literal["off", "low", "medium", "high"]


class OpenRouterProvider:
    """A ``GenerationProvider`` that calls the OpenRouter chat-completions API.

    Satisfies the ``GenerationProvider`` protocol structurally. Construct one per
    model id; the composite cascade holds several (primary, fallback model) plus
    a local Ollama leg.

    Args:
        api_key: OpenRouter API key (Bearer credential). Never logged.
        model: OpenRouter model id (e.g. ``"anthropic/claude-sonnet-4.6"``).
        base_url: OpenRouter API base url (no trailing slash needed).
        timeout_seconds: Per-attempt wall-clock timeout for one HTTP call.
        effort: Reasoning effort. ``"off"`` omits the ``reasoning`` param entirely
            (correct for structured-JSON generation); any other value is
            forwarded as OpenRouter's ``reasoning.effort`` to opt the model into
            extended thinking.
        max_retries: Number of attempts for transient failures (default 3).
        backoff_base_seconds: Base for exponential backoff between transient
            retries; attempt *n* waits ``backoff_base_seconds * 2**n`` seconds.
            Set to ``0`` in tests to avoid real sleeping.
        client: Optional injected ``httpx.AsyncClient`` (for tests). When
            provided the adapter uses it and does not close it; when ``None`` a
            fresh client is created and closed per ``complete`` call.
        provider_order: Optional OpenRouter *backend* preference, most preferred
            first (e.g. ``("Anthropic",)``). Empty (the default) sends no
            ``provider`` field at all, leaving OpenRouter's own routing intact,
            so production behaviour is unchanged. A non-empty order additionally
            sets ``allow_fallbacks: false``, which is what makes a measurement
            attributable to one backend rather than to whichever backend
            happened to win the routing auction that minute.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: int,
        effort: _Effort,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        client: httpx.AsyncClient | None = None,
        provider_order: tuple[str, ...] = (),
    ) -> None:
        self._api_key: Final[str] = api_key
        self._model: Final[str] = model
        self._base_url: Final[str] = base_url.rstrip("/")
        self._timeout_seconds: Final[int] = timeout_seconds
        self._effort: Final[_Effort] = effort
        self._max_retries: Final[int] = max_retries
        self._backoff_base_seconds: Final[float] = backoff_base_seconds
        self._client: Final[httpx.AsyncClient | None] = client
        self._provider_order: Final[tuple[str, ...]] = provider_order

    @property
    def name(self) -> str:
        """Return the leg label used in logs and the worker provider record."""
        return f"openrouter:{self._model}"

    def _build_messages(self, system: str, user: str) -> list[dict[str, object]]:
        """Build the chat messages, marking the system block cacheable for Anthropic.

        Anthropic models support explicit prompt caching via ``cache_control`` on
        a content block; the static system block (schema + drafting guide) is the
        cache target. Non-Anthropic models on OpenRouter either auto-cache or
        ignore the field, so for them the system content is a plain string.

        Args:
            system: The static system block (cacheable prefix).
            user: The volatile per-job user block.

        Returns:
            The OpenRouter ``messages`` array.
        """
        if self._model.startswith("anthropic/"):
            system_content: object = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_content = system
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user},
        ]

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Return the model completion for a system+user prompt pair.

        Args:
            system: System-role instructions (the cacheable static block).
            prompt: User-role prompt content (the volatile per-job block).
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The completion text with any wrapping markdown code fence stripped,
            plus the token usage the response reported for the successful
            attempt.

        Raises:
            ProviderError: On a leg-fatal failure (mapped immediately) or after
                exhausting transient retries.
        """
        # #CRITICAL: external-resources: this performs network I/O to a third-party
        # LLM endpoint. Every attempt is bounded by ``timeout_seconds``; transient
        # failures are retried with exponential backoff up to ``max_retries``;
        # leg-fatal failures raise immediately so the cascade can fail over.
        # #VERIFY: tests assert transient->retry, 404/401->leg_fatal ProviderError,
        # and exhausted transient->ProviderError(leg_fatal=False).
        body: dict[str, object] = {
            "model": self._model,
            "messages": self._build_messages(system, prompt),
            "max_tokens": max_tokens,
        }
        # Only request reasoning when explicitly opted in. Story generation is
        # structured-JSON output; enabling reasoning on Claude spends the whole
        # max_tokens budget on thinking tokens and returns empty content
        # (finish_reason=length). "off" therefore omits the param entirely.
        if self._effort != "off":
            body["reasoning"] = {"effort": self._effort}
        # #ASSUME: external-resources: an unpinned slug can be served by several
        # backends at different quantizations, so two runs of "the same model"
        # are not the same measurement. When a pin is supplied we also forbid
        # fallbacks, turning a silent substitution into a visible 404.
        # #VERIFY: test_openrouter_provider_pin_forbids_fallbacks asserts the
        # body, and test_openrouter_unpinned_body_has_no_provider_field asserts
        # the default path stays byte-identical to the pre-pin request.
        if self._provider_order:
            body["provider"] = {
                "order": list(self._provider_order),
                "allow_fallbacks": False,
            }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": "cyo-adventure",
        }
        url = f"{self._base_url}/chat/completions"

        return await run_with_retries(
            lambda: self._attempt(url, body, headers),
            provider="openrouter",
            model=self._model,
            max_retries=self._max_retries,
            backoff_base_seconds=self._backoff_base_seconds,
        )

    async def _attempt(
        self,
        url: str,
        body: Mapping[str, object],
        headers: Mapping[str, str],
    ) -> Completion:
        """Perform one HTTP attempt and map the outcome to text or ProviderError.

        Args:
            url: The chat-completions endpoint url.
            body: The JSON request body.
            headers: The request headers (including the Bearer credential).

        Returns:
            The model completion text and its reported token usage on success.

        Raises:
            ProviderError: Transient (``leg_fatal=False``) on network/timeout/5xx
                or rate limiting; leg-fatal (``leg_fatal=True``) on
                invalid-model/auth/credit failures.
        """
        started = time.monotonic()
        try:
            if self._client is not None:
                response = await self._client.post(url, json=body, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            # Connection refused, DNS failure, read timeout: transient.
            msg = f"openrouter request failed: {type(exc).__name__}"
            raise ProviderError(
                msg, provider="openrouter", model=self._model, leg_fatal=False
            ) from exc

        self._raise_for_status(response)
        return self._extract_completion(response, started)

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map a non-2xx HTTP status to a ProviderError with the right fatality.

        Args:
            response: The HTTP response to inspect.

        Raises:
            ProviderError: Transient for 429/5xx/enumerated codes; leg-fatal for
                invalid-model/auth/credit codes and other non-retryable 4xx.
        """
        status = response.status_code
        if status < 400:
            return
        # Do not include the response body in the message: it can echo request
        # content. The status code is enough to classify the failure.
        if status in _TRANSIENT_STATUS or status >= 500:
            msg = f"openrouter returned transient HTTP {status}"
            raise ProviderError(
                msg,
                provider="openrouter",
                model=self._model,
                status_code=status,
                leg_fatal=False,
            )
        # Any other 4xx is not worth retrying against the same model: mark the
        # leg dead. _LEG_FATAL_STATUS enumerates the codes we expect here; the
        # `else` keeps an unexpected 4xx (e.g. 422) leg-fatal too, since retrying
        # a client error cannot help.
        if status in {400, 404}:
            reason = "invalid or unavailable model"
        elif status in _LEG_FATAL_STATUS:
            reason = "authentication or credit failure"
        else:
            reason = "non-retryable client error"
        msg = f"openrouter returned leg-fatal HTTP {status} ({reason})"
        raise ProviderError(
            msg,
            provider="openrouter",
            model=self._model,
            status_code=status,
            leg_fatal=True,
        )

    @staticmethod
    def _empty_content_message(
        finish_reason: str | None, reasoning_tokens: int | None
    ) -> str:
        """Say why an empty completion was empty, so the log names the cause.

        Args:
            finish_reason: The reason the backend reported, or ``None``.
            reasoning_tokens: Hidden reasoning tokens reported, or ``None``.

        Returns:
            The error text. Both figures are carried into it because
            ``run_with_retries`` logs the exception string on every transient
            retry, so this is what makes a budget failure legible in a run's
            stderr rather than only in a later billing probe.
        """
        if finish_reason == "length":
            spent = (
                f", {reasoning_tokens} of them on reasoning" if reasoning_tokens else ""
            )
            return (
                "openrouter completion hit the token budget and returned no "
                f"usable content (finish_reason=length{spent}); retrying at the "
                "same cap would buy the same wall, so this leg is not retried"
            )
        return (
            "openrouter response had no message content "
            f"(finish_reason={finish_reason!r}, reasoning_tokens={reasoning_tokens!r})"
        )

    def _extract_completion(
        self, response: httpx.Response, started: float
    ) -> Completion:
        """Extract the completion text and token usage from a successful response.

        Args:
            response: A 2xx HTTP response.
            started: The ``time.monotonic()`` reading taken before the request.

        Returns:
            The first choice's message content plus the reported token usage.

        Raises:
            ProviderError: Transient if the response shape is unexpected or the
                content is empty (a malformed success is treated as retryable).
        """
        try:
            payload: object = response.json()
        except ValueError as exc:
            msg = "openrouter returned a non-JSON response body"
            raise ProviderError(
                msg, provider="openrouter", model=self._model, leg_fatal=False
            ) from exc

        finish_reason = dig_finish_reason(payload)
        reasoning_tokens = dig_reasoning_tokens(payload)
        content = dig_content(payload)
        if not content:
            # #CRITICAL: external-resources: an empty body from a truncated
            # completion and an empty body from a dead endpoint are the same
            # bytes and want opposite responses. Retrying a truncation re-buys
            # the identical wall at the identical cap: the comparison harness
            # spent three attempts at roughly eleven minutes and fifty cents
            # each doing exactly that (AL-329), and one leg burned its entire
            # 32,000-token budget on reasoning and returned 1,128 tokens of
            # prose. `finish_reason` is the only thing that separates them, so
            # a budget failure is leg-fatal here rather than transient.
            # #VERIFY: test_openrouter_provider_pin.py drives both bodies and
            # asserts leg_fatal True for length and False for everything else.
            raise ProviderError(
                self._empty_content_message(finish_reason, reasoning_tokens),
                provider="openrouter",
                model=self._model,
                leg_fatal=finish_reason == "length",
            )
        input_tokens, output_tokens = dig_usage(payload)
        # Normalize away any markdown code fence so the orchestrator's json.loads
        # parses models (e.g. Gemini Flash) that wrap output despite instructions.
        return Completion(
            text=strip_code_fences(content),
            usage=TokenUsage(
                provider="openrouter",
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=elapsed_ms(started),
                reasoning_tokens=reasoning_tokens,
            ),
            finish_reason=finish_reason,
        )
