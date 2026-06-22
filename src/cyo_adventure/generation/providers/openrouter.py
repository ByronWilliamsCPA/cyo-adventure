"""OpenRouter generation provider adapter (Phase 2b primary leg).

Calls the OpenRouter chat-completions API and returns the raw model text. This
adapter owns **Layer 1** of the three-layer failure model: it retries TRANSIENT
failures (connection error, timeout, HTTP 429, HTTP 5xx) against the *same*
model with exponential backoff, and maps leg-fatal failures (invalid/unavailable
model, authentication) to :class:`~cyo_adventure.core.exceptions.ProviderError`
immediately. It never inspects gate results or content quality; a schema-valid
but gate-blocked response is a successful completion here (Layer 3 handles it).

The adapter returns the model output verbatim (no markdown-fence stripping): the
Phase 2b probe confirmed the pinned first-party models return raw JSON, so the
orchestrator's ``json.loads`` parses it directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import httpx

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.generation.providers._base import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_MAX_RETRIES,
    as_str_map,
    run_with_retries,
)

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
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: int,
        effort: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key: Final[str] = api_key
        self._model: Final[str] = model
        self._base_url: Final[str] = base_url.rstrip("/")
        self._timeout_seconds: Final[int] = timeout_seconds
        self._effort: Final[str] = effort
        self._max_retries: Final[int] = max_retries
        self._backoff_base_seconds: Final[float] = backoff_base_seconds
        self._client: Final[httpx.AsyncClient | None] = client

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

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Return the model completion for a system+user prompt pair.

        Args:
            system: System-role instructions (the cacheable static block).
            prompt: User-role prompt content (the volatile per-job block).
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The raw text completion from the model (no fence stripping).

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
    ) -> str:
        """Perform one HTTP attempt and map the outcome to text or ProviderError.

        Args:
            url: The chat-completions endpoint url.
            body: The JSON request body.
            headers: The request headers (including the Bearer credential).

        Returns:
            The model completion text on success.

        Raises:
            ProviderError: Transient (``leg_fatal=False``) on network/timeout/5xx
                or rate limiting; leg-fatal (``leg_fatal=True``) on
                invalid-model/auth/credit failures.
        """
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
        return self._extract_content(response)

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

    def _extract_content(self, response: httpx.Response) -> str:
        """Extract the completion text from a successful response.

        Args:
            response: A 2xx HTTP response.

        Returns:
            The first choice's message content.

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

        content = _dig_content(payload)
        if not content:
            msg = "openrouter response had no message content"
            raise ProviderError(
                msg, provider="openrouter", model=self._model, leg_fatal=False
            )
        return content


def _dig_content(payload: object) -> str | None:
    """Safely extract ``choices[0].message.content`` from a response payload.

    Narrows the untrusted decoded JSON with ``isinstance`` at each level (the
    same defensive pattern the validator uses for raw JSON) so an unexpected
    shape returns ``None`` rather than raising.

    Args:
        payload: The decoded JSON response (untrusted shape).

    Returns:
        The content string, or ``None`` when any expected key is missing or has
        an unexpected type.
    """
    top = as_str_map(payload)
    if top is None:
        return None
    choices = top.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = as_str_map(choices[0])
    if first is None:
        return None
    message = as_str_map(first.get("message"))
    if message is None:
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None
