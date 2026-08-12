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
    serialize_correlation,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    ConfigurationError,
    ExternalServiceError,
    ProjectBaseError,
    ValidationError,
)
from cyo_adventure.utils.logging import get_logger

logger = get_logger(__name__)

_SERVICE = "kws"
# The two suppressions below are the same false positive reported twice: ruff
# raises S105 and bandit raises its B105 equivalent, and each needs its own
# marker because neither reads the other's. This is the OIDC token ENDPOINT's
# URL path, a public constant published in Epic's docs, not a credential. The
# credential is settings.kws_api_key, which is a SecretStr and is never a
# literal. (This comment must not open with the bare word that ruff reads as a
# directive, or the prose itself becomes a blanket suppression.)
_TOKEN_PATH = "/auth/realms/kws/protocol/openid-connect/token"  # noqa: S105  # nosec B105
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
_HTTP_FORBIDDEN: Final = 403
_HTTP_TOO_MANY_REQUESTS: Final = 429
_HTTP_SERVER_ERROR: Final = 500

# The statuses that mean "the operator has to fix something", not "the vendor
# is having a bad minute". A 401 that survives one forced re-authentication is
# a rejected client id or API key, or a grant this client has lost; a 403 is
# either the same answer by another name or the "Request blocked" KWS returns
# for a missing User-Agent (vendor constraint 1 in the module docstring). None
# of them clears by waiting.
_CREDENTIAL_REJECTION_STATUSES: Final = frozenset({_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN})

# Deliberately says nothing about which vendor answered or how. The caller of
# this module is a browser holding a guardian's session, and "an operator must
# fix this" is the whole of what it can act on; the diagnostic goes to the log
# line beside every raise instead.
_MISCONFIGURED_MESSAGE: Final = (
    "parent verification is misconfigured on this deployment; an operator must "
    "correct it before a verification email can be sent"
)

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
        correlation: The token this attempt was sent under, echoed back so a
            caller that discarded its own copy still has it. The token is
            MINTED BY THE CALLER, not here: it is the primary key of the
            ``kws_verification`` row, and that row must exist before this call
            goes out (see ``consent/service.py``).
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


def _credential_rejection(status: int, *, leg: str) -> ConfigurationError:
    """Build the operator-facing error for a credential or config rejection.

    #CRITICAL: external resources: a rejected credential must NOT leave this
    module as the ``ExternalServiceError`` a timeout or a 5xx produces. Since
    UW-A55 that class is HTTP 502, which
    ``GuardianVerificationPage.tsx::messageForStartError`` renders as "this
    may clear, try again"; a wrong client id or API key never clears on a
    retry, so that advice would loop a parent against a condition only an
    operator can fix, which is the exact failure UW-A55 set out to remove, one
    status code further along. ``ConfigurationError`` puts it on the existing
    400 path beside "KWS is not configured", where the copy already reads
    "trying again will not help, so please contact support".
    #VERIFY: tests/unit/test_kws_client.py::TestCredentialRejection.

    #CRITICAL: security: the returned message names neither the vendor nor its
    status. Both travel on the log line below instead, which is where an
    operator reads them and a guardian's browser does not.
    #VERIFY: tests/unit/test_kws_client.py::
    test_a_credential_rejection_tells_the_client_nothing_about_the_vendor.

    Args:
        status: The rejecting HTTP status (401 or 403).
        leg: Which call was rejected, ``"auth"`` or ``"send"``, for the log.

    Returns:
        ConfigurationError: The operator-fixable error to raise.
    """
    logger.error(
        "kws_credentials_rejected",
        status_code=status,
        leg=leg,
        kws_environment=settings.kws_environment,
    )
    return ConfigurationError(_MISCONFIGURED_MESSAGE)


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
        self,
        request: VerificationEmailRequest,
        *,
        correlation: VerificationCorrelation,
    ) -> VerificationEmailResult:
        """Ask KWS to email a parent and begin verifying they are an adult.

        Sending is not consenting. A successful call here means an email is on
        its way, nothing more: the parent may never open it, and even a
        completed verification establishes adulthood rather than consent under
        16 CFR 312.5. The consent record remains ours.

        Args:
            request: The parent's email, the child's location, the language.
            correlation: The attempt token to send as ``externalPayload``.
                Required rather than minted here, because it is the primary key
                of the ``kws_verification`` row and that row must be written
                before this call goes out; a client that minted its own would
                make an unrecorded send the default and the recorded one an
                option (see ``consent/service.py``).

        Returns:
            VerificationEmailResult: The correlation this attempt was sent
                under, echoed back for callers that discarded their copy.

        Raises:
            ConfigurationError: When the integration is unconfigured, or when
                KWS rejects our credentials or blocks the request (401/403 on
                either leg). Both are operator-fixable and reach the browser
                as a 400 that says so, never as the retryable 502 below.
            ValidationError: When the request would be rejected by KWS.
            ExternalServiceError: When KWS fails the call for a reason that
                may clear on its own (5xx, timeout, transport failure, the
                per-address rate limit).
        """
        api_origin, credentials = _require_configured()
        _validate(request)

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
            ConfigurationError: On a 401 that survived a forced re-auth, or a
                403; both are operator-fixable rather than transient.
            ExternalServiceError: On any other non-2xx that is not worth
                retrying, or once the retry budget is exhausted.
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
            ConfigurationError: On a 401 that survived the one forced re-auth,
                or on a 403; see ``_credential_rejection``.
            ExternalServiceError: On any other terminal status, a transport
                failure after the last attempt, or an exhausted retry budget.
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

    def _terminal_error(self, status: int) -> ProjectBaseError:
        """Build the error for a status we will not retry.

        The return type is the shared base rather than
        ``ExternalServiceError``, because the two terminal outcomes are not
        the same kind of failure and must not carry the same HTTP status: a
        401/403 is the operator's to fix (400 via ``ConfigurationError``) and
        everything else here is the vendor's (502 via
        ``ExternalServiceError``). Collapsing them was UW-A55's defect
        re-created one status code along.

        Args:
            status: The HTTP status returned by KWS.

        Returns:
            ProjectBaseError: ``ConfigurationError`` for a credential or
                configuration rejection; otherwise ``ExternalServiceError``
                carrying the status, with a distinct ``error_code`` for the
                rate limit so a caller can tell a guardian "too many attempts
                for that address in the last hour" instead of a generic
                upstream failure.
        """
        if status in _CREDENTIAL_REJECTION_STATUSES:
            return _credential_rejection(status, leg="send")
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
            ConfigurationError: When the token endpoint rejects our client
                credentials (401/403).
            ExternalServiceError: When authentication fails for any other
                reason.
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
            ConfigurationError: When the token endpoint answers 401 or 403.
                A client-credentials grant is machine-to-machine and carries
                no user input, so a rejection here can only mean our own
                client id, API key, or grant is wrong: an operator's problem,
                and one no retry resolves.
            ExternalServiceError: On any other non-2xx, a transport failure,
                or a body without an ``access_token``.
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
            if response.status_code in _CREDENTIAL_REJECTION_STATUSES:
                raise _credential_rejection(response.status_code, leg="auth")
            msg = "KWS authentication failed"
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
