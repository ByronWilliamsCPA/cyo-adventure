"""Direct-Anthropic generation provider adapter (WS-C PR1).

Calls the Anthropic Messages API directly via the official ``anthropic`` SDK
and returns the model text. Mirrors OpenRouterProvider's Layer-1 contract:
retries TRANSIENT failures (connection error, timeout, HTTP 408, HTTP 409,
HTTP 425, HTTP 429, HTTP 529 overloaded, HTTP 5xx) against the same model
with exponential backoff, and maps leg-fatal failures (invalid request,
authentication, permission, not found, and any other non-retryable 4xx) to
:class:`~cyo_adventure.core.exceptions.ProviderError` immediately.

This adapter owns Layer-1 retries exclusively: the internal ``AsyncAnthropic``
client is always constructed with ``max_retries=0`` so the SDK's own built-in
retry loop never runs underneath ``run_with_retries``, which would otherwise
double the backoff with different semantics.
"""

from __future__ import annotations

from typing import Final, NoReturn

import anthropic

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.generation.providers._base import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_MAX_RETRIES,
    run_with_retries,
    strip_code_fences,
)

# Anthropic status codes worth retrying against the same model. Matches the
# sibling OpenRouterProvider's transient set exactly (openrouter.py) and the
# Anthropic SDK's own _should_retry, which retries request-timeout (408),
# conflict/lock-timeout (409), too-early (425), and rate-limit (429). The
# overloaded signal (529) is a 5xx and stays transient via the >= 500 check in
# _raise_for_status, so it does not need enumerating here.
_TRANSIENT_STATUS: Final[frozenset[int]] = frozenset({408, 409, 425, 429})


class AnthropicProvider:
    """A ``GenerationProvider`` that calls the Anthropic Messages API directly.

    Satisfies the ``GenerationProvider`` protocol structurally.

    Args:
        api_key: Anthropic API key (Bearer credential). Never logged.
        model: Anthropic model id (e.g. ``"claude-sonnet-4-6"``).
        base_url: Anthropic API base url.
        timeout_seconds: Per-attempt wall-clock timeout for one API call.
        max_retries: Number of attempts for transient failures (default 3).
        backoff_base_seconds: Base for exponential backoff between transient
            retries. Set to ``0`` in tests to avoid real sleeping.
        client: Optional injected ``AsyncAnthropic`` (for tests, via its own
            ``http_client=`` parameter). When ``None`` a client is constructed
            from ``api_key``/``base_url``/``timeout_seconds`` with the SDK's
            own retries disabled.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: int,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._model: Final[str] = model
        self._max_retries: Final[int] = max_retries
        self._backoff_base_seconds: Final[float] = backoff_base_seconds
        self._client: Final[anthropic.AsyncAnthropic] = (
            client
            or anthropic.AsyncAnthropic(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout_seconds,
                max_retries=0,
            )
        )

    @property
    def name(self) -> str:
        """Return the leg label used in logs and the worker provider record."""
        return f"anthropic:{self._model}"

    @property
    def model(self) -> str:
        """Return the model id this leg targets."""
        return self._model

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Return the model completion for a system+user prompt pair.

        Args:
            system: System-role instructions.
            prompt: User-role prompt content.
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The completion text with any wrapping markdown code fence stripped.

        Raises:
            ProviderError: On a leg-fatal failure (mapped immediately) or after
                exhausting transient retries.
        """
        # #CRITICAL: external-resources: this performs network I/O to a
        # third-party LLM endpoint. Every attempt is bounded by
        # timeout_seconds; transient failures are retried with exponential
        # backoff up to max_retries; leg-fatal failures raise immediately.
        # #VERIFY: tests assert transient (429/connection-error) -> retry,
        # 401/404 -> leg_fatal ProviderError, and exhausted transient ->
        # ProviderError(leg_fatal=False).
        return await run_with_retries(
            lambda: self._attempt(system, prompt, max_tokens),
            provider="anthropic",
            model=self._model,
            max_retries=self._max_retries,
            backoff_base_seconds=self._backoff_base_seconds,
        )

    async def _attempt(self, system: str, prompt: str, max_tokens: int) -> str:
        """Perform one Messages API call and map the outcome to text or ProviderError.

        Args:
            system: System-role instructions.
            prompt: User-role prompt content.
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The model completion text on success.

        Raises:
            ProviderError: Transient (``leg_fatal=False``) on connection
                error/timeout/HTTP 408/409/425/429/529/5xx; leg-fatal
                (``leg_fatal=True``) on any other 4xx.
        """
        try:
            message = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIConnectionError as exc:
            # Covers a bare connection failure and its APITimeoutError
            # subclass (a request that never got a response at all).
            msg = f"anthropic request failed: {type(exc).__name__}"
            raise ProviderError(
                msg, provider="anthropic", model=self._model, leg_fatal=False
            ) from exc
        except anthropic.APIStatusError as exc:
            self._raise_for_status(exc)

        return self._extract_content(message)

    def _raise_for_status(self, exc: anthropic.APIStatusError) -> NoReturn:
        """Map an Anthropic API status error to a ProviderError with the right fatality.

        Args:
            exc: The status error raised by the SDK.

        Raises:
            ProviderError: Transient for 408/409/425/429/529/5xx; leg-fatal
                for every other 4xx.
        """
        status = exc.status_code
        if status in _TRANSIENT_STATUS or status >= 500:
            msg = f"anthropic returned transient HTTP {status}"
            raise ProviderError(
                msg,
                provider="anthropic",
                model=self._model,
                status_code=status,
                leg_fatal=False,
            ) from exc
        msg = f"anthropic returned leg-fatal HTTP {status}"
        raise ProviderError(
            msg,
            provider="anthropic",
            model=self._model,
            status_code=status,
            leg_fatal=True,
        ) from exc

    def _extract_content(self, message: anthropic.types.Message) -> str:
        """Extract the completion text from a successful Messages API response.

        Args:
            message: The parsed ``Message`` response.

        Returns:
            The concatenated text of every text content block, with any
            wrapping markdown code fence stripped.

        Raises:
            ProviderError: Transient if the message carries no usable text
                content (a null, empty, or text-less success is retryable).
        """
        # #CRITICAL: data-integrity: the SDK's Message model is permissive (all
        # fields optional), so a malformed 200 does NOT raise
        # APIResponseValidationError; it yields a Message whose `content` is
        # None or empty. `message.content or []` guards the None case so a
        # malformed success becomes a retryable ProviderError rather than a raw
        # TypeError escaping run_with_retries' ProviderError-only contract.
        # #VERIFY: test_null_content_is_transient, test_empty_content_is_transient.
        content = message.content or []
        text = "".join(block.text for block in content if block.type == "text")
        if not text:
            msg = "anthropic response had no text content"
            raise ProviderError(
                msg, provider="anthropic", model=self._model, leg_fatal=False
            )
        return strip_code_fences(text)
