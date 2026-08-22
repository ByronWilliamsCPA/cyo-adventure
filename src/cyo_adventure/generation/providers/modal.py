"""Modal generation provider adapter (cascade leg 3).

Calls a Modal Auto Endpoint's OpenAI-compatible chat-completions API and returns
the model text. Structurally mirrors ``OpenRouterProvider``: the same Layer-1
retry/backoff via ``run_with_retries``, the same transient-vs-leg-fatal HTTP
status split, the same ``finish_reason`` handling on an empty body, and the same
``strip_code_fences`` normalization.

This leg is no longer offline-only. Since the 2026-08-18 Ollama retirement
``build_provider`` appends it to the production ``FallbackProvider`` cascade as
leg 3 whenever ``MODAL_BASE_URL`` and ``MODAL_MODEL`` are both set, so it is the
backstop that keeps the cascade spanning two vendors (ADR-003 as amended
2026-08-18, amending ADR-010 Decision 2). Being last matters for error
classification: a leg-fatal failure here ends the job rather than falling
through to another leg.

Two vendor-shape differences from OpenRouter, both recorded in the 2026-08-20
smoke test: reasoning tokens arrive flat on ``usage`` rather than under
``completion_tokens_details``, and no ``cost`` field is returned at all, so
spend accounting for this leg comes from Modal billing rather than the response
(there is also no ``core/pricing.py`` row, so ``CostEstimate.complete`` is
``False`` for Modal-served completions).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

import httpx

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.generation.providers._base import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_MAX_RETRIES,
    dig_content,
    dig_finish_reason,
    dig_flat_reasoning_tokens,
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
        proxy_key: Optional Modal proxy-token id, sent as the ``Modal-Key``
            header. Modal Auto Endpoints use a ``Modal-Key``/``Modal-Secret``
            header pair for proxy auth, not a Bearer token; both headers are
            omitted entirely unless both ``proxy_key`` and ``proxy_secret``
            are set (a half-set pair sends neither, never a partial
            credential).
        proxy_secret: Optional Modal proxy-token secret, sent as the
            ``Modal-Secret`` header. Required together with ``proxy_key``;
            see above.
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
        proxy_key: str | None,
        proxy_secret: str | None,
        timeout_seconds: int,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url: Final[str] = base_url.rstrip("/")
        self._model: Final[str] = model
        self._proxy_key: Final[str | None] = proxy_key
        self._proxy_secret: Final[str | None] = proxy_secret
        self._timeout_seconds: Final[int] = timeout_seconds
        self._max_retries: Final[int] = max_retries
        self._backoff_base_seconds: Final[float] = backoff_base_seconds
        self._client: Final[httpx.AsyncClient | None] = client

    @property
    def name(self) -> str:
        """Return the leg label used in logs and the worker provider record."""
        return f"modal:{self._model}"

    @property
    def model(self) -> str:
        """The model id this leg targets, exposed for cap resolution.

        Every adapter exposes this so ``resolve_output_cap`` sees the leg's
        real model through the provider wrappers rather than falling back to
        the configured default (`AL-518`/`UW-C323`; the contract is asserted
        by test_provider_contract.py).
        """
        return self._model

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Return the model completion for a system+user prompt pair.

        Args:
            system: System-role instructions.
            prompt: User-role prompt content.
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The completion text with any wrapping markdown code fence removed,
            plus the token usage the response reported for the successful
            attempt.

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
        if self._proxy_key and self._proxy_secret:
            headers["Modal-Key"] = self._proxy_key
            headers["Modal-Secret"] = self._proxy_secret
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
    ) -> Completion:
        """Perform one HTTP attempt and map the outcome to text or ProviderError.

        Args:
            url: The chat-completions endpoint url.
            body: The JSON request body.
            headers: The request headers.

        Returns:
            The model completion text and its reported token usage on success.

        Raises:
            ProviderError: Transient (``leg_fatal=False``) on network/timeout/5xx
                or rate limiting; leg-fatal (``leg_fatal=True``) on
                invalid-model/auth failures.
        """
        started = time.monotonic()
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
        return self._extract_completion(response, started)

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
            reason = "authentication or credit failure"
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

    @staticmethod
    def _empty_content_message(
        finish_reason: str | None, reasoning_tokens: int | None
    ) -> str:
        """Say why an empty completion was empty, so the log names the cause.

        Args:
            finish_reason: The reason the backend reported, or ``None``.
            reasoning_tokens: Hidden reasoning tokens reported, or ``None``.

        Returns:
            The error text. Mirrors ``OpenRouterProvider``'s wording so a
            cascade failure reads the same whichever leg produced it, and
            carries both figures because ``run_with_retries`` logs the
            exception string on every transient retry.
        """
        if finish_reason == "length":
            spent = (
                f", {reasoning_tokens} of them on reasoning" if reasoning_tokens else ""
            )
            return (
                "modal completion hit the token budget and returned no "
                f"usable content (finish_reason=length{spent}); retrying at the "
                "same cap would buy the same wall, so this leg is not retried"
            )
        return (
            "modal response had no message content "
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
            msg = "modal returned a non-JSON response body"
            raise ProviderError(
                msg, provider="modal", model=self._model, leg_fatal=False
            ) from exc

        finish_reason = dig_finish_reason(payload)
        reasoning_tokens = dig_flat_reasoning_tokens(payload)
        content = dig_content(payload)
        if not content:
            # #CRITICAL: external-resources: a truncated completion and a dead
            # endpoint return the same empty bytes and want opposite responses.
            # Without this split the adapter retried a deterministic budget
            # exhaustion at the identical cap until the retry budget was gone,
            # which the 2026-08-20 smoke test named as the blocking adapter gap
            # before this leg could take real traffic. As leg 3 there is no
            # further leg to fall through to, so burning the budget here is the
            # job's whole failure path, not a delay before the next attempt.
            # #VERIFY: test_modal_provider.py asserts leg_fatal True for
            # finish_reason=length and False for every other empty body.
            raise ProviderError(
                self._empty_content_message(finish_reason, reasoning_tokens),
                provider="modal",
                model=self._model,
                leg_fatal=finish_reason == "length",
            )
        input_tokens, output_tokens = dig_usage(payload)
        return Completion(
            text=strip_code_fences(content),
            usage=TokenUsage(
                provider="modal",
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=elapsed_ms(started),
                reasoning_tokens=reasoning_tokens,
            ),
            finish_reason=finish_reason,
        )
