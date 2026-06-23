"""Ollama generation provider adapter (Phase 2b final fallback leg).

Calls a local Ollama server's chat API and returns the raw model text. Serves as
the offline fallback leg of the cascade and as a separately-measurable
comparison target against the OpenRouter legs.

Like the OpenRouter adapter it owns **Layer 1**: transient failures (connection
refused when Ollama is down, timeout, HTTP 5xx) are retried with backoff; a
missing model (HTTP 404) is leg-fatal. A direct local Ollama needs no credential
and does its own KV caching via ``keep_alive``, so there is no prompt-cache
control here. When the server is fronted by an auth proxy (the homelab host runs
Traefik + Authentik), optional HTTP Basic credentials are attached; an
unauthenticated request to that path answers ``302`` (redirect to the login
flow), which this adapter maps to a leg-fatal error rather than parsing the
redirect body as a completion.
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
    strip_code_fences,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

# HTTP statuses worth retrying against the same local model. 5xx is also treated
# as transient even when not enumerated.
_TRANSIENT_STATUS: Final[frozenset[int]] = frozenset({408, 425, 429, 503})

# A missing/unpulled model (404) or a malformed request (400) cannot be fixed by
# retrying: mark the leg dead.
_LEG_FATAL_STATUS: Final[frozenset[int]] = frozenset({400, 404})


class OllamaProvider:
    """A ``GenerationProvider`` that calls a local Ollama server's chat API.

    Satisfies the ``GenerationProvider`` protocol structurally.

    Args:
        model: Ollama model name (e.g. ``"qwen3:30b"``).
        base_url: Ollama server base url. Either a direct host
            (``"http://localhost:11434"``) or an auth-proxied HTTPS vhost
            (``"https://ollama.svc.williamshome.family"``, no explicit port).
        timeout_seconds: Per-attempt wall-clock timeout for one HTTP call.
        username: Optional HTTP Basic-auth user. Basic auth is attached only when
            both ``username`` and ``password`` are provided.
        password: Optional HTTP Basic-auth password (a secret; never logged).
        max_retries: Number of attempts for transient failures (default 3).
        backoff_base_seconds: Base for exponential backoff between transient
            retries. Set to ``0`` in tests to avoid real sleeping.
        client: Optional injected ``httpx.AsyncClient`` (for tests). When
            provided the adapter uses it and does not close it; when ``None`` a
            fresh client is created and closed per ``complete`` call.
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        timeout_seconds: int,
        username: str | None = None,
        password: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model: Final[str] = model
        self._base_url: Final[str] = base_url.rstrip("/")
        self._timeout_seconds: Final[int] = timeout_seconds
        # Attach Basic auth only when both halves are present; a partial
        # credential is treated as no credential (the 302 path then surfaces a
        # clear leg-fatal error rather than a confusing half-authenticated call).
        self._auth: Final[httpx.BasicAuth | None] = (
            httpx.BasicAuth(username, password)
            if username is not None and password is not None
            else None
        )
        self._max_retries: Final[int] = max_retries
        self._backoff_base_seconds: Final[float] = backoff_base_seconds
        self._client: Final[httpx.AsyncClient | None] = client

    @property
    def name(self) -> str:
        """Return the leg label used in logs and the worker provider record."""
        return f"ollama:{self._model}"

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        """Return the model completion for a system+user prompt pair.

        Args:
            system: System-role instructions (the static block).
            prompt: User-role prompt content (the volatile per-job block).
            max_tokens: Upper bound on response length, mapped to Ollama's
                ``options.num_predict``.

        Returns:
            The completion text with any wrapping markdown code fence stripped.

        Raises:
            ProviderError: On a leg-fatal failure (mapped immediately) or after
                exhausting transient retries.
        """
        # #CRITICAL: external-resources: this performs network I/O to the local
        # Ollama server. Every attempt is bounded by ``timeout_seconds``;
        # transient failures retry with backoff; a missing model is leg-fatal.
        # #VERIFY: tests assert transient->retry and 404->leg_fatal ProviderError.
        body: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        url = f"{self._base_url}/api/chat"

        return await run_with_retries(
            lambda: self._attempt(url, body),
            provider="ollama",
            model=self._model,
            max_retries=self._max_retries,
            backoff_base_seconds=self._backoff_base_seconds,
        )

    async def _attempt(self, url: str, body: Mapping[str, object]) -> str:
        """Perform one HTTP attempt and map the outcome to text or ProviderError.

        Args:
            url: The Ollama chat endpoint url.
            body: The JSON request body.

        Returns:
            The model completion text on success.

        Raises:
            ProviderError: Transient on network/timeout/5xx; leg-fatal on
                missing-model/bad-request.
        """
        try:
            if self._client is not None:
                response = await self._post(self._client, url, body)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await self._post(client, url, body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            msg = f"ollama request failed: {type(exc).__name__}"
            raise ProviderError(
                msg, provider="ollama", model=self._model, leg_fatal=False
            ) from exc

        self._raise_for_status(response)
        return self._extract_content(response)

    async def _post(
        self, client: httpx.AsyncClient, url: str, body: Mapping[str, object]
    ) -> httpx.Response:
        """POST ``body`` to ``url`` on ``client``, attaching Basic auth if set.

        ``auth`` is passed only when a credential is configured: httpx's ``auth``
        parameter type does not admit ``None`` (its "no override" sentinel is
        ``UseClientDefault``), so omitting the keyword is the type-clean way to
        send no credential.

        Args:
            client: The AsyncClient to use (injected for tests, or per-call).
            url: The Ollama chat endpoint url.
            body: The JSON request body.

        Returns:
            The HTTP response (status not yet inspected).
        """
        auth = self._auth
        if auth is None:
            return await client.post(url, json=body)
        return await client.post(url, json=body, auth=auth)

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map a non-2xx HTTP status to a ProviderError with the right fatality.

        Args:
            response: The HTTP response to inspect.

        Raises:
            ProviderError: Transient for 5xx/enumerated codes; leg-fatal for an
                auth-proxy redirect (3xx), missing-model/bad-request, and other
                non-retryable 4xx.
        """
        status = response.status_code
        if status < 300:
            return
        if status < 400:
            # The auth proxy (Authentik) answers an unauthenticated request with a
            # 302 to its login flow. httpx does not follow redirects, so we see the
            # 3xx directly. Retrying cannot help (the credential is missing or
            # wrong), so mark the leg dead with a credential-pointing message.
            # status_code is intentionally omitted: a 3xx is < 400, and the
            # ProviderError invariant forbids pairing leg_fatal with a
            # successful/redirect status; the code is already in the message.
            msg = (
                f"ollama returned leg-fatal HTTP {status} (unexpected redirect; "
                "authentication required or credentials rejected)"
            )
            raise ProviderError(
                msg,
                provider="ollama",
                model=self._model,
                leg_fatal=True,
            )
        if status in _TRANSIENT_STATUS or status >= 500:
            msg = f"ollama returned transient HTTP {status}"
            raise ProviderError(
                msg,
                provider="ollama",
                model=self._model,
                status_code=status,
                leg_fatal=False,
            )
        # Distinguish the leg-fatal 4xx causes: 404 is a missing/unpulled model,
        # 400 is a malformed request. Both mark the leg dead, but the operator
        # message should not mislabel a bad request as a missing model. Any other
        # 4xx outside the expected set (_LEG_FATAL_STATUS) is still leg-fatal,
        # since retrying a client error against the same model cannot help.
        if status == 404:
            reason = "missing or unpulled model"
        elif status == 400:
            reason = "bad request"
        elif status in _LEG_FATAL_STATUS:
            reason = "non-retryable client error"
        else:
            reason = "unexpected non-retryable client error"
        msg = f"ollama returned leg-fatal HTTP {status} ({reason})"
        raise ProviderError(
            msg,
            provider="ollama",
            model=self._model,
            status_code=status,
            leg_fatal=True,
        )

    def _extract_content(self, response: httpx.Response) -> str:
        """Extract the completion text from a successful response.

        Args:
            response: A 2xx HTTP response.

        Returns:
            The ``message.content`` string.

        Raises:
            ProviderError: Transient if the response shape is unexpected or the
                content is empty.
        """
        try:
            payload: object = response.json()
        except ValueError as exc:
            msg = "ollama returned a non-JSON response body"
            raise ProviderError(
                msg, provider="ollama", model=self._model, leg_fatal=False
            ) from exc

        top = as_str_map(payload)
        message = as_str_map(top.get("message")) if top is not None else None
        content = message.get("content") if message is not None else None
        if not isinstance(content, str) or not content:
            msg = "ollama response had no message content"
            raise ProviderError(
                msg, provider="ollama", model=self._model, leg_fatal=False
            )
        # Normalize away any markdown code fence so the orchestrator's json.loads
        # parses local models that wrap output despite instructions.
        return strip_code_fences(content)
