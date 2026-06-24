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

Requests are made with ``stream: true``: the homelab host runs one generation at
a time (``OLLAMA_NUM_PARALLEL=1``) with a multi-second cold start, so a full
story can take minutes. Streaming the newline-delimited JSON chunks and
accumulating their ``message.content`` means the per-call timeout bounds the gap
between chunks (time-to-first-byte), not the whole generation, which avoids both
a single wall-clock wall and intermediary idle timeouts. The accumulated text is
returned as one string, so the orchestrator contract is unchanged.
"""

from __future__ import annotations

import json
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
    import ssl
    from collections.abc import Mapping

# HTTP statuses worth retrying against the same local model. 5xx is also treated
# as transient even when not enumerated.
_TRANSIENT_STATUS: Final[frozenset[int]] = frozenset({408, 425, 429, 503})

# A missing/unpulled model (404) or a malformed request (400) cannot be fixed by
# retrying: mark the leg dead.
_LEG_FATAL_STATUS: Final[frozenset[int]] = frozenset({400, 404})

# Opt out of response compression. The homelab proxy (Traefik) has a compress
# middleware that buffers a gzipped streaming response, which stalls and then
# drops long generations mid-stream. Requesting ``identity`` makes compress a
# no-op so the NDJSON stream flows to completion; NDJSON gzips poorly and the
# per-chunk payloads are tiny, so this costs effectively nothing.
_STREAM_HEADERS: Final[dict[str, str]] = {"Accept-Encoding": "identity"}


class OllamaProvider:
    """A ``GenerationProvider`` that calls a local Ollama server's chat API.

    Satisfies the ``GenerationProvider`` protocol structurally.

    Args:
        model: Ollama model name (e.g. ``"qwen3:30b"``).
        base_url: Ollama server base url. Either a direct host
            (``"http://localhost:11434"``) or an auth-proxied HTTPS vhost
            (``"https://ollama.williamshome.family"``, no explicit port).
        timeout_seconds: Per-attempt wall-clock timeout for one HTTP call.
        username: Optional HTTP Basic-auth user. Basic auth is attached only when
            both ``username`` and ``password`` are provided.
        password: Optional HTTP Basic-auth password (a secret; never logged).
        verify: TLS verification for self-created clients. ``True`` uses the
            public CA store; pass an ``ssl.SSLContext`` (e.g. system CAs plus the
            Homelab CA bundle) to verify a privately-signed homelab cert. Not a
            bypass. Ignored when ``client`` is injected.
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
        verify: ssl.SSLContext | bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model: Final[str] = model
        self._base_url: Final[str] = base_url.rstrip("/")
        self._timeout_seconds: Final[int] = timeout_seconds
        # TLS verification for self-created clients: True uses the public CA store;
        # an SSLContext (system CAs + Homelab bundle) verifies the privately-signed
        # homelab cert. Ignored when a client is injected (tests own their context).
        self._verify: Final[ssl.SSLContext | bool] = verify
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
            "stream": True,
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
        # #CRITICAL: external-resources: this opens the live Ollama HTTP call. A
        # self-created client must carry TLS verification (self._verify) and a
        # bounded per-attempt timeout, or a hung or MITM homelab host stalls the
        # leg or weakens transport security.
        # #VERIFY: verify=self._verify and timeout=self._timeout_seconds are
        # passed to httpx.AsyncClient below; tests/unit/test_worker.py asserts the
        # _verify wiring (SSLContext when a CA bundle is set, else True).
        try:
            if self._client is not None:
                return await self._stream(self._client, url, body)
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, verify=self._verify
            ) as client:
                return await self._stream(client, url, body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            msg = f"ollama request failed: {type(exc).__name__}"
            raise ProviderError(
                msg, provider="ollama", model=self._model, leg_fatal=False
            ) from exc

    async def _stream(
        self, client: httpx.AsyncClient, url: str, body: Mapping[str, object]
    ) -> str:
        """Stream ``/api/chat`` and accumulate the chunked completion text.

        Opens a streaming POST (attaching Basic auth only when configured, since
        httpx's ``auth`` parameter type does not admit ``None``), maps a non-2xx
        status to a :class:`ProviderError`, then concatenates the ``message.content``
        of each newline-delimited JSON chunk until the stream ends.

        Args:
            client: The AsyncClient to use (injected for tests, or per-call).
            url: The Ollama chat endpoint url.
            body: The JSON request body (with ``stream: true``).

        Returns:
            The fence-stripped completion text accumulated across all chunks.

        Raises:
            ProviderError: Leg-fatal/transient per status (via _raise_for_status);
                transient on a malformed chunk, an error chunk, or empty content.
        """
        # #CRITICAL: security: HTTP Basic credentials are attached to this
        # streaming request; the password must never be logged or echoed into a
        # ProviderError, and is sent only over the verified client built in
        # _attempt (the cleartext-http guard runs earlier, at build time).
        # #VERIFY: auth is passed only when self._auth is set, and no raise below
        # interpolates the credential (only HTTP status and static text).
        auth = self._auth
        if auth is None:
            request = client.stream("POST", url, json=body, headers=_STREAM_HEADERS)
        else:
            request = client.stream(
                "POST", url, json=body, auth=auth, headers=_STREAM_HEADERS
            )
        parts: list[str] = []
        async with request as response:
            if response.status_code >= 300:
                # Drain the (non-streamed) error body so the connection closes
                # cleanly, then map the status. _raise_for_status always raises here.
                await response.aread()
                self._raise_for_status(response)
            async for line in response.aiter_lines():
                stripped = line.strip()
                if stripped:
                    parts.append(self._chunk_content(stripped))
        content = "".join(parts)
        if not content:
            # An empty accumulation usually means the budget was spent on a
            # reasoning model's thinking tokens; treat as a retryable failure.
            msg = "ollama stream returned no message content"
            raise ProviderError(
                msg, provider="ollama", model=self._model, leg_fatal=False
            )
        # Normalize away any markdown code fence so the orchestrator's json.loads
        # parses local models that wrap output despite instructions.
        return strip_code_fences(content)

    def _chunk_content(self, line: str) -> str:
        """Return the ``message.content`` of one NDJSON stream chunk.

        Args:
            line: One non-empty line of the streamed response body.

        Returns:
            The chunk's content fragment, or ``""`` when the chunk carries none
            (e.g. the terminal ``done`` marker).

        Raises:
            ProviderError: Transient on a non-JSON line or an ``{"error": ...}``
                chunk (Ollama signals mid-stream failures this way).
        """
        try:
            chunk: object = json.loads(line)
        except ValueError as exc:
            msg = "ollama stream returned a non-JSON line"
            raise ProviderError(
                msg, provider="ollama", model=self._model, leg_fatal=False
            ) from exc
        top = as_str_map(chunk)
        if top is None:
            return ""
        error = top.get("error")
        if isinstance(error, str) and error:
            msg = "ollama stream returned an error chunk"
            raise ProviderError(
                msg, provider="ollama", model=self._model, leg_fatal=False
            )
        message = as_str_map(top.get("message"))
        content = message.get("content") if message is not None else None
        return content if isinstance(content, str) else ""

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
