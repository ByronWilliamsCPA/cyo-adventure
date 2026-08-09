"""Outbound client for the KWS Parent Verification Service (ADR-018).

This is the SEND leg. It triggers the flow by handing KWS a parent's email
address; KWS then emails them, walks them through a verification method, and
reports the outcome back on the two return legs handled in
``consent/kws_signature.py``.

Two hosts, not one
------------------
Tokens come from ``auth.kidswebservices.com`` (a Keycloak realm) and API calls
go to the Service API host published in the Control Panel. An earlier reading
that the single published URL served both was falsified against the docs, which
is why ``KWS_AUTH_ORIGIN`` and ``KWS_API_ORIGIN`` are separate settings.

Three vendor constraints that shape code rather than config
-----------------------------------------------------------
1. The ``User-Agent`` header is REQUIRED. Missing or empty is a 403 "Request
   blocked", which reads like an authorization failure and is not one.
2. Rate limiting is ten requests per hour per unique parent email, in test and
   production alike. That is the reason a 429 is not retried here (see
   ``_is_retryable``).
3. ``externalPayload`` caps at 250 characters; enforced in
   ``consent/external_payload.py`` before the request is built.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Final, NamedTuple

import httpx

from cyo_adventure.consent.external_payload import (
    VerificationCorrelation,
    mint_correlation,
    serialize_correlation,
)
from cyo_adventure.consent.guards import require_non_production_kws_environment
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    ConfigurationError,
    ExternalServiceError,
    ValidationError,
)
from cyo_adventure.utils.logging import get_logger

logger = get_logger(__name__)

_SERVICE = "kws"
# The S105 suppression below is a false positive: this is the OIDC token
# ENDPOINT's URL path, a public constant published in Epic's docs, not a
# credential. The credential is settings.kws_api_key, which is a SecretStr and
# is never a literal. (This comment must not open with the bare word that ruff
# reads as a directive, or the prose itself becomes a blanket suppression.)
_TOKEN_PATH = "/auth/realms/kws/protocol/openid-connect/token"  # noqa: S105
_SEND_EMAIL_PATH = "/v1/verifications/send-email"

# Per-attempt ceiling on a single HTTP call. Deliberately a constant rather than
# a setting: this is one low-volume call to one vendor, an operator has no basis
# on which to tune it, and every additional env var is one more way for a
# partially-configured deployment to fail (which is what the credential guards
# in core/config.py already exist to catch).
_TIMEOUT_SECONDS: Final = 10.0

# Epic requires exponential backoff on failure. Three attempts across ~1.5s of
# sleeping covers a restart or a blip without holding a request open long enough
# to matter to the guardian waiting on the response.
_MAX_ATTEMPTS: Final = 3
_BACKOFF_BASE_SECONDS: Final = 0.5

# Re-authenticate once a token has burned this fraction of its advertised life,
# so a token on the edge of expiry is never the one we send. KWS says the
# lifetime varies with usage, so this is a hint, not a guarantee, and the
# reactive re-auth-on-401 path below is what actually makes it safe.
_TOKEN_REFRESH_RATIO: Final = 0.9

_HTTP_UNAUTHORIZED: Final = 401
_HTTP_TOO_MANY_REQUESTS: Final = 429
_HTTP_SERVER_ERROR: Final = 500

# ISO 3166-1 alpha-2 ("US") or an ISO 3166-2 subdivision ("US-NY", "GB-ENG").
# Shape only: this rejects obvious mistakes such as a full country name or a
# lowercase locale, and does not claim the code names a real place.
_LOCATION_PATTERN: Final = re.compile(r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$")


class _Credentials(NamedTuple):
    """The three values an authenticated call needs, resolved once per call.

    Bundled because they are always used together and are always read from the
    same settings snapshot: passing them separately would let a caller mix a
    client id from one environment with an API key from another.

    Attributes:
        auth_origin: The Keycloak token host, distinct from the API host.
        client_id: The environment's client id.
        api_key: The environment's API key, in cleartext for HTTP Basic.
    """

    auth_origin: str
    client_id: str
    api_key: str


@dataclass(frozen=True, slots=True)
class VerificationEmailRequest:
    """The user details KWS needs to start a verification.

    Attributes:
        email: The parent or guardian's email address. Never logged.
        location: The CHILD's location, not the parent's, as an ISO 3166-1
            alpha-2 country code or an ISO 3166-2 subdivision code. It selects
            which verification methods the parent is offered, so it is a
            compliance input rather than a display preference.
        language: The parent's language, used for KWS's emails and web screens.
    """

    email: str
    location: str
    language: str = "en"


@dataclass(frozen=True, slots=True)
class VerificationEmailResult:
    """What the caller needs in order to recognise the result later.

    Attributes:
        correlation: The token minted for this attempt. The caller persists it
            against the guardian; the return legs quote it back.
    """

    correlation: VerificationCorrelation


def _require_configured() -> tuple[str, _Credentials]:
    """Return the resolved credentials, refusing to run without all of them.

    Returns:
        tuple[str, _Credentials]: The API origin and the auth credentials.

    Raises:
        ConfigurationError: When the integration is not fully configured. The
            partial-credential case is already rejected at settings-load time;
            this covers the wholly-unconfigured deployment, where the correct
            behaviour is to be inert rather than to fail at the vendor.
    """
    if not settings.kws_configured:
        msg = (
            "The KWS integration is not configured; refusing to start a "
            "parent verification."
        )
        raise ConfigurationError(msg)
    # Narrowing for the type checker: kws_configured is exactly the assertion
    # that these four are present and non-empty.
    return settings.kws_api_origin or "", _Credentials(
        auth_origin=settings.kws_auth_origin,
        client_id=settings.kws_client_id or "",
        api_key=(
            settings.kws_api_key.get_secret_value() if settings.kws_api_key else ""
        ),
    )


def _validate(request: VerificationEmailRequest) -> None:
    """Reject a request KWS would reject, before it costs a rate-limit slot.

    Ten requests per hour per email is a small budget, and a 4xx spends one.

    #CRITICAL: security: no validation error may carry the email address. The
    app's error handler logs the full error payload including ``value``, so
    passing the address as ``value=`` would write a parent's email into every
    log sink. Only ``field`` is set.
    #VERIFY: tests/unit/test_kws_client.py::test_validation_errors_omit_the_email.

    Args:
        request: The request to check.

    Raises:
        ValidationError: When the email is not minimally well formed or the
            location is not a country or subdivision code.
    """
    email = request.email.strip()
    if not email or email.count("@") != 1 or any(c.isspace() for c in email):
        msg = "A parent verification needs a well-formed email address."
        raise ValidationError(msg, field="email")
    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        msg = "A parent verification needs a well-formed email address."
        raise ValidationError(msg, field="email")
    if not _LOCATION_PATTERN.match(request.location):
        msg = (
            "location must be an ISO 3166-1 alpha-2 country code (US) or an "
            "ISO 3166-2 subdivision code (US-NY)."
        )
        raise ValidationError(msg, field="location")
    if not request.language:
        msg = "language must be a non-empty language code."
        raise ValidationError(msg, field="language")


def _usable_lifetime(expires_in: object) -> float | None:
    """Read a token lifetime out of an untrusted auth-response field.

    Returning the narrowed value rather than a separate boolean is deliberate:
    a ``bool`` flag beside the raw field leaves the conversion unguarded, which
    is exactly what the type checker objected to.

    ``bool`` is excluded explicitly because it is a subclass of ``int``, so
    ``"expires_in": true`` would otherwise be read as a one-second lifetime.

    Args:
        expires_in: The raw ``expires_in`` value, of any type or absent.

    Returns:
        float | None: The lifetime in seconds, or None when the field is
            missing, the wrong type, or not positive.
    """
    if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)):
        return None
    return float(expires_in) if expires_in > 0 else None


def _is_retryable(status: int) -> bool:
    """Whether a failing status is worth another attempt.

    Epic's guidance is to back off and retry on any status outside 200-299.
    This narrows that deliberately:

    * 429 is NOT retried. The limit is ten per hour per email, so a retry
      seconds later cannot succeed and only burns the guardian's remaining
      budget for the address. It is surfaced instead, because the honest
      response to the caller is "not now", not a longer wait.
    * Other 4xx are NOT retried. A malformed request is malformed on the second
      attempt too, and each attempt spends a slot from that same budget.

    Args:
        status: The HTTP status returned.

    Returns:
        bool: True for 5xx only.
    """
    return status >= _HTTP_SERVER_ERROR


class KwsClient:
    """A client for the KWS Parent Verification Service send leg.

    Holds the access token across calls, so it is worth keeping one instance
    alive rather than constructing one per request: the token endpoint sits
    behind a WAF that rate-limits, and a fresh instance per verification would
    re-authenticate every time.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Initialise the client.

        Args:
            client: Optional injected ``httpx.AsyncClient`` (for tests). When
                omitted, each call opens its own client with a bounded timeout.
        """
        self._injected: Final = client
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        # Coalesces concurrent authentication onto one request. Without it, a
        # burst of verifications on a cold cache would each mint a token and
        # race to overwrite the others.
        # #CRITICAL: concurrency: this lock guards _token and _token_expires_at,
        # which are read outside it on the fast path. That read is safe because
        # a stale-but-unexpired token is still valid, and an expired one falls
        # through to the locked path.
        # #VERIFY: tests/unit/test_kws_client.py::
        # test_concurrent_sends_authenticate_once.
        self._auth_lock: Final = asyncio.Lock()

    async def send_verification_email(
        self, request: VerificationEmailRequest
    ) -> VerificationEmailResult:
        """Ask KWS to email a parent and begin verifying they are an adult.

        Sending is not consenting. A successful call here means an email is on
        its way, nothing more: the parent may never open it, and even a
        completed verification establishes adulthood rather than consent under
        16 CFR 312.5. The consent record remains ours.

        Args:
            request: The parent's email, the child's location, the language.

        Returns:
            VerificationEmailResult: The correlation token minted for this
                attempt, which the caller must persist to recognise the result.

        Raises:
            ConfigurationError: When the integration is unconfigured, or when
                pointed at the production environment before persistence exists.
            ValidationError: When the request would be rejected by KWS.
            ExternalServiceError: When KWS rejects or fails the call.
        """
        require_non_production_kws_environment(action="start a parent verification")
        api_origin, credentials = _require_configured()
        _validate(request)

        correlation = mint_correlation()
        body = {
            "email": request.email.strip(),
            "location": request.location,
            "language": request.language,
            "externalPayload": serialize_correlation(correlation),
            # Required, and must be exactly this. "adult" and "age" are the
            # other KWS flows; they raise different events and would leave our
            # parent-verified receiver waiting for a delivery that never comes.
            "userContext": "parent",
        }

        # The attempt id is ours and identifies no person, so it is the right
        # correlation handle for logs. The email address is not logged here or
        # anywhere else in this module.
        logger.info(
            "kws_verification_email_requested",
            attempt_id=str(correlation.attempt_id),
            location=request.location,
            language=request.language,
            kws_environment=settings.kws_environment,
        )
        await self._post_json(
            url=f"{api_origin.rstrip('/')}{_SEND_EMAIL_PATH}",
            body=body,
            credentials=credentials,
        )
        return VerificationEmailResult(correlation=correlation)

    async def _post_json(
        self, *, url: str, body: dict[str, str], credentials: _Credentials
    ) -> None:
        """POST an authenticated JSON body, retrying what is worth retrying.

        #CRITICAL: external resources: this is the live outbound call. A
        self-created client must carry a bounded timeout, or a hung vendor host
        stalls the request that is waiting on it.
        #VERIFY: timeout=_TIMEOUT_SECONDS is passed to httpx.AsyncClient below.

        Args:
            url: The fully-qualified endpoint.
            body: The JSON request body.
            credentials: The resolved auth credentials.

        Raises:
            ExternalServiceError: On a non-2xx that is not worth retrying, or
                once the retry budget is exhausted.
        """
        if self._injected is not None:
            await self._attempt_loop(self._injected, url, body, credentials)
            return
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            await self._attempt_loop(client, url, body, credentials)

    async def _attempt_loop(
        self,
        client: httpx.AsyncClient,
        url: str,
        body: dict[str, str],
        credentials: _Credentials,
    ) -> None:
        """Run the send with backoff, re-authenticating once on a 401.

        Args:
            client: The client to send on.
            url: The fully-qualified endpoint.
            body: The JSON request body.
            credentials: The resolved auth credentials.

        Raises:
            ExternalServiceError: On a terminal status, a transport failure
                after the last attempt, or an exhausted retry budget.
        """
        reauthenticated = False
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            token = await self._access_token(client, credentials)
            try:
                response = await client.post(
                    url,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        # Required by KWS; an empty one is a 403 "Request
                        # blocked" that reads like an auth failure.
                        "User-Agent": settings.kws_user_agent,
                    },
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == _MAX_ATTEMPTS:
                    msg = f"KWS send-email failed: {type(exc).__name__}"
                    raise ExternalServiceError(msg, service_name=_SERVICE) from exc
                await self._back_off(attempt, reason=type(exc).__name__)
                continue

            if response.is_success:
                return

            # A 401 means the token was rejected, and KWS token lifetimes vary,
            # so mint a fresh one and try again rather than treating an expiry
            # as a credential problem. Only once: a second 401 with a brand new
            # token is a real authorization failure.
            if response.status_code == _HTTP_UNAUTHORIZED and not reauthenticated:
                reauthenticated = True
                # Dropping the cache is what forces the next _access_token call
                # to mint; there is no separate "force" flag to keep in sync.
                self._invalidate_token()
                continue

            if not _is_retryable(response.status_code) or attempt == _MAX_ATTEMPTS:
                raise self._terminal_error(response.status_code)
            await self._back_off(attempt, reason=str(response.status_code))

    def _terminal_error(self, status: int) -> ExternalServiceError:
        """Build the error for a status we will not retry.

        Args:
            status: The HTTP status returned by KWS.

        Returns:
            ExternalServiceError: Carrying the status, and a distinct
                ``error_code`` for the rate limit so a caller can tell a
                guardian "too many attempts for that address in the last hour"
                instead of a generic upstream failure.
        """
        rate_limited = status == _HTTP_TOO_MANY_REQUESTS
        msg = (
            "KWS is rate limiting verification emails for this address"
            if rate_limited
            else "KWS rejected the parent verification request"
        )
        logger.warning(
            "kws_send_email_failed",
            status_code=status,
            rate_limited=rate_limited,
            kws_environment=settings.kws_environment,
        )
        return ExternalServiceError(
            msg,
            service_name=_SERVICE,
            status_code=status,
            error_code="KWS_RATE_LIMITED" if rate_limited else None,
        )

    async def _back_off(self, attempt: int, *, reason: str) -> None:
        """Sleep before the next attempt, doubling each time.

        Args:
            attempt: The 1-based attempt that just failed.
            reason: A log-safe discriminator (status code or exception type).
        """
        # Shift rather than 2 ** n: the exponent form is typed as returning
        # Any (a negative exponent would make it a float), which propagates an
        # untyped value into asyncio.sleep for no benefit. attempt is 1-based,
        # so the shift distance is never negative.
        delay = _BACKOFF_BASE_SECONDS * (1 << (attempt - 1))
        logger.warning(
            "kws_send_email_retrying",
            attempt=attempt,
            delay_seconds=delay,
            reason=reason,
        )
        await asyncio.sleep(delay)

    def _invalidate_token(self) -> None:
        """Drop the cached token so the next call mints a fresh one."""
        self._token = None
        self._token_expires_at = 0.0

    def _cached_token(self) -> str | None:
        """Return the cached token if it is still worth sending.

        Returns:
            str | None: The token, or None when absent or past its refresh
                point.
        """
        cached = self._token
        if cached is None or time.monotonic() >= self._token_expires_at:
            return None
        return cached

    async def _access_token(
        self, client: httpx.AsyncClient, credentials: _Credentials
    ) -> str:
        """Return a usable access token, minting one only when needed.

        Args:
            client: The client to authenticate on.
            credentials: The resolved auth credentials.

        Returns:
            str: A bearer token.

        Raises:
            ExternalServiceError: When authentication fails.
        """
        cached = self._cached_token()
        if cached is not None:
            return cached
        async with self._auth_lock:
            # Re-check under the lock: whoever held it before us may already
            # have minted the token this call was about to duplicate.
            cached = self._cached_token()
            if cached is not None:
                return cached
            return await self._fetch_token(client, credentials)

    async def _fetch_token(
        self, client: httpx.AsyncClient, credentials: _Credentials
    ) -> str:
        """Mint a new access token via client-credentials.

        Args:
            client: The client to authenticate on.
            credentials: auth_origin, client_id, api_key.

        Returns:
            str: The new bearer token.

        Raises:
            ExternalServiceError: On a non-2xx, a transport failure, or a body
                without an ``access_token``.
        """
        try:
            response = await client.post(
                f"{credentials.auth_origin.rstrip('/')}{_TOKEN_PATH}",
                data={"grant_type": "client_credentials", "scope": "verification"},
                # #CRITICAL: security: the API key is the credential for this
                # environment. It travels as HTTP Basic here and must never be
                # logged or interpolated into an error message; every raise
                # below carries a status code and static text only.
                # #VERIFY: tests/unit/test_kws_client.py::
                # test_api_key_never_appears_in_logs_or_errors.
                auth=httpx.BasicAuth(credentials.client_id, credentials.api_key),
                headers={"Accept": "application/json"},
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            self._invalidate_token()
            msg = f"KWS authentication failed: {type(exc).__name__}"
            raise ExternalServiceError(msg, service_name=_SERVICE) from exc

        if not response.is_success:
            self._invalidate_token()
            msg = "KWS rejected the client credentials"
            raise ExternalServiceError(
                msg, service_name=_SERVICE, status_code=response.status_code
            )

        return self._store_token(response)

    def _store_token(self, response: httpx.Response) -> str:
        """Cache the token from an auth response and return it.

        Args:
            response: The successful token response.

        Returns:
            str: The access token.

        Raises:
            ExternalServiceError: When the body is not a JSON object carrying a
                non-empty ``access_token``.
        """
        try:
            payload: Any = response.json()
        except ValueError as exc:
            self._invalidate_token()
            msg = "KWS authentication returned a body that was not JSON"
            raise ExternalServiceError(msg, service_name=_SERVICE) from exc
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            self._invalidate_token()
            msg = "KWS authentication returned no access token"
            raise ExternalServiceError(msg, service_name=_SERVICE)

        # expires_in is documented but Epic says the lifetime varies with usage,
        # so its absence is survivable rather than fatal: cache the token with
        # no proactive refresh and let the re-auth-on-401 path handle expiry.
        # math.inf, not 0.0: a zero here would mean "already expired", so every
        # call would re-authenticate against a WAF-rate-limited token endpoint,
        # which is the failure this branch exists to avoid.
        lifetime = _usable_lifetime(payload.get("expires_in"))
        if lifetime is None:
            logger.warning(
                "kws_auth_response_without_expiry",
                kws_environment=settings.kws_environment,
            )
        self._token = token
        self._token_expires_at = (
            math.inf
            if lifetime is None
            else time.monotonic() + lifetime * _TOKEN_REFRESH_RATIO
        )
        return token
