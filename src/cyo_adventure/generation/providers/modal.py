"""Modal generation provider adapter (ADR-010 experimental leg).

Calls a Modal Auto Endpoint's OpenAI-compatible chat-completions API and returns
the model text. Structurally mirrors ``OpenRouterProvider``: the same Layer-1
retry/backoff via ``run_with_retries``, the same transient-vs-leg-fatal HTTP
status split, and the same ``strip_code_fences`` normalization. This leg is
experimental only (ADR-010 item 2): ``build_provider`` never wraps it in the
production ``FallbackProvider`` cascade; selecting ``generation_provider=modal``
is an explicit, offline-only choice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import httpx

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.generation.providers._base import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_MAX_RETRIES,
    _dig_content,
    run_with_retries,
    strip_code_fences,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

# HTTP statuses worth retrying against the same model: rate limiting and
# transient server faults. Anything 5xx is treated as transient even if not
# enumerated here. Mirrors OpenRouterProvider's classification.
_TRANSIENT_STATUS: Final[frozenset[int]] = frozenset({408, 409, 425, 429})

# HTTP statuses that mean this leg cannot serve the request at all this run:
# bad request / unavailable model (400, 404), out of credits (402), and auth
# failures (401, 403).
_LEG_FATAL_STATUS: Final[frozenset[int]] = frozenset({400, 401, 402, 403, 404})


class ModalProvider:
    """A ``GenerationProvider`` that calls a Modal Auto Endpoint.

    Satisfies the ``GenerationProvider`` protocol structurally. Experimental
    leg only (ADR-010 item 2): construct via ``build_modal_leg``, never
    wrapped in the production fallback cascade.

    Args:
        base_url: The deployed Modal Auto Endpoint base url (from
            ``modal endpoint list``; no trailing slash needed).
        model: The served model id, used for the ``name`` property, logs, and
            the request body (the endpoint itself is already bound to one
            model, but the OpenAI-compatible API still requires the field).
        api_key: Optional Bearer credential. Omitted entirely from the request
            when ``None`` (whether a Modal Auto Endpoint enforces auth by
            default is unconfirmed as of this adapter; #VERIFY at deploy time).
        timeout_seconds: Per-attempt wall-clock timeout. Cold starts need
            materially more headroom than a warm OpenRouter call.
        max_retries: Number of attempts for transient failures (default 3).
        backoff_base_seconds: Base for exponential backoff between transient
            retries; attempt *n* waits ``backoff_base_seconds * 2**n`` seconds.
            Set to ``0`` in tests to avoid real sleeping.
        client: Optional injected ``httpx.AsyncClient`` (for tests). When
            provided the adapter uses it and does not close it; when ``None``
            a fresh client is created and closed per ``complete`` call.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: int,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url: Final[str] = base_url.rstrip("/")
        self._model: Final[str] = model
        self._api_key: Final[str | None] = api_key
        self._timeout_seconds: Final[int] = timeout_seconds
        self._max_retries: Final[int] = max_retries
        self._backoff_base_seconds: Final[float] = backoff_base_seconds
        self._client: Final[httpx.AsyncClient | None] = client

    @property
    def name(self) -> str:
        """Return the leg label used in logs and the worker provider record."""
        return f"modal:{self._model}"

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Return the model completion for a system+user prompt pair.

        Args:
            system: System-role instructions.
            prompt: User-role prompt content.
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The completion text with any wrapping markdown code fence removed.

        Raises:
            ProviderError: On a leg-fatal failure (mapped immediately) or after
                exhausting transient retries.
        """
        # #CRITICAL: external-resources: this performs network I/O to a
        # self-hosted Modal endpoint. Every attempt is bounded by
        # timeout_seconds; transient failures retry with exponential backoff
        # up to max_retries; leg-fatal failures raise immediately so the
        # orchestrator's retry loop does not waste attempts on a dead leg.
        # #VERIFY: tests assert transient->retry, 404/401->leg_fatal
        # ProviderError, and exhausted transient->ProviderError(leg_fatal=False).
        body: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        url = f"{self._base_url}/chat/completions"

        return await run_with_retries(
            lambda: self._attempt(url, body, headers),
            provider="modal",
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
            headers: The request headers.

        Returns:
            The model completion text on success.

        Raises:
            ProviderError: Transient (``leg_fatal=False``) on network/timeout/5xx
                or rate limiting; leg-fatal (``leg_fatal=True``) on
                invalid-model/auth failures.
        """
        try:
            if self._client is not None:
                response = await self._client.post(url, json=body, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            msg = f"modal request failed: {type(exc).__name__}"
            raise ProviderError(
                msg, provider="modal", model=self._model, leg_fatal=False
            ) from exc

        self._raise_for_status(response)
        return self._extract_content(response)

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map a non-2xx HTTP status to a ProviderError with the right fatality.

        Args:
            response: The HTTP response to inspect.

        Raises:
            ProviderError: Transient for 429/5xx/enumerated codes; leg-fatal for
                invalid-model/auth codes and other non-retryable 4xx.
        """
        status = response.status_code
        if status < 400:
            return
        if status in _TRANSIENT_STATUS or status >= 500:
            msg = f"modal returned transient HTTP {status}"
            raise ProviderError(
                msg,
                provider="modal",
                model=self._model,
                status_code=status,
                leg_fatal=False,
            )
        if status in {400, 404}:
            reason = "invalid or unavailable model"
        elif status in _LEG_FATAL_STATUS:
            reason = "authentication failure"
        else:
            reason = "non-retryable client error"
        msg = f"modal returned leg-fatal HTTP {status} ({reason})"
        raise ProviderError(
            msg,
            provider="modal",
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
            msg = "modal returned a non-JSON response body"
            raise ProviderError(
                msg, provider="modal", model=self._model, leg_fatal=False
            ) from exc

        content = _dig_content(payload)
        if not content:
            msg = "modal response had no message content"
            raise ProviderError(
                msg, provider="modal", model=self._model, leg_fatal=False
            )
        return strip_code_fences(content)
