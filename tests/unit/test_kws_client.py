"""Tests for the KWS Parent Verification send leg.

Driven through ``httpx.MockTransport`` rather than by patching the client's own
methods, so the request that would go on the wire is the thing under test: the
URL, the Basic auth on the token leg, the bearer and User-Agent on the send
leg, and the exact JSON body. Patching ``_post_json`` would assert only that we
call ourselves the way we expect to.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr

from cyo_adventure.consent import (
    KwsClient,
    VerificationEmailRequest,
    mint_correlation,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    ConfigurationError,
    ExternalServiceError,
    ValidationError,
)

_API_ORIGIN = "https://api.kidswebservices.example"
_AUTH_ORIGIN = "https://auth.kidswebservices.example"
_CLIENT_ID = "00000000-0000-4000-8000-000000000002"
_API_KEY = "test-kws-api-key-not-a-real-secret"
_PARENT_EMAIL = "parent.under.test@example.com"
_TOKEN = "test-access-token"
_SEND_URL = f"{_API_ORIGIN}/v1/verifications/send-email"
_TOKEN_URL = f"{_AUTH_ORIGIN}/auth/realms/kws/protocol/openid-connect/token"

_REQUEST = VerificationEmailRequest(email=_PARENT_EMAIL, location="US", language="en")
# One attempt token, reused across these tests the way _REQUEST is. The client
# no longer mints its own: the token is the primary key of the kws_verification
# row and must exist before the send goes out, so the caller supplies it. Hoisted
# to module scope rather than called inline because a mint_correlation() inside a
# pytest.raises body would be a second call in the block
# (scripts/check_pytest_raises_scope.py).
_CORRELATION = mint_correlation()


@pytest.fixture
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fully configured Test-environment integration."""
    monkeypatch.setattr(settings, "kws_environment", "test")
    monkeypatch.setattr(settings, "kws_api_origin", _API_ORIGIN)
    monkeypatch.setattr(settings, "kws_auth_origin", _AUTH_ORIGIN)
    monkeypatch.setattr(settings, "kws_client_id", _CLIENT_ID)
    monkeypatch.setattr(settings, "kws_api_key", SecretStr(_API_KEY))
    monkeypatch.setattr(
        settings, "kws_organization_id", "00000000-0000-4000-8000-000000000001"
    )
    monkeypatch.setattr(settings, "kws_user_agent", "cyo-adventure-test")


class _Recorder:
    """Answers requests from a script of status codes, keeping what it saw.

    Statuses rather than pre-built ``httpx.Response`` objects, because a single
    Response instance handed back for two attempts would be a shared, already
    consumed object; building a fresh one per call keeps each attempt
    independent the way the real transport does.
    """

    def __init__(self, send_statuses: list[int]) -> None:
        """Store the scripted send-leg statuses.

        Args:
            send_statuses: Returned in order for successive send calls; the
                last one repeats if the client asks more times than scripted.
        """
        self.requests: list[httpx.Request] = []
        self.token_calls = 0
        self._send_statuses = send_statuses

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Answer one request.

        Args:
            request: The outbound request.

        Returns:
            httpx.Response: The scripted response.
        """
        self.requests.append(request)
        if request.url.path.endswith("/token"):
            self.token_calls += 1
            return httpx.Response(
                200, json={"access_token": _TOKEN, "expires_in": 3600}
            )
        index = min(len(self.send_requests) - 1, len(self._send_statuses) - 1)
        return httpx.Response(self._send_statuses[index], json={})

    @property
    def send_requests(self) -> list[httpx.Request]:
        """Every request made to the send-email endpoint.

        Returns:
            list[httpx.Request]: The send-leg requests, in order.
        """
        return [r for r in self.requests if not r.url.path.endswith("/token")]


class _SuspendingTransport(httpx.AsyncBaseTransport):
    """A recorder-backed transport that yields to the event loop mid-call.

    Needed for the concurrency test only. Real network I/O suspends; a
    ``MockTransport`` does not, and a coroutine that never suspends cannot
    interleave with another, so a burst of "concurrent" sends over a mock
    transport is really a sequence. Yielding on the token call restores the
    interleaving the lock exists to handle.
    """

    def __init__(self, recorder: _Recorder) -> None:
        """Wrap a recorder.

        Args:
            recorder: The recorder that decides the response.
        """
        self._recorder = recorder

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Answer one request, suspending first on the token path.

        Args:
            request: The outbound request.

        Returns:
            httpx.Response: The recorder's scripted response.
        """
        if request.url.path.endswith("/token"):
            # A real token round-trip suspends here; without this the first
            # caller would finish and warm the cache before the second starts.
            await asyncio.sleep(0)
        return self._recorder.handle(request)


def _client(recorder: _Recorder) -> KwsClient:
    """Build a KwsClient wired to a recorder.

    Args:
        recorder: The recorder answering the requests.

    Returns:
        KwsClient: A client whose transport is the recorder.
    """
    return KwsClient(httpx.AsyncClient(transport=httpx.MockTransport(recorder.handle)))


_OK = 200


def _body_of(request: httpx.Request) -> dict[str, Any]:
    """Decode a request's JSON body.

    Args:
        request: The request to read.

    Returns:
        dict[str, Any]: The decoded body.
    """
    decoded: dict[str, Any] = json.loads(request.content)
    return decoded


@pytest.mark.usefixtures("_configured")
class TestRequestShape:
    """What actually goes on the wire."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sends_the_documented_body(self) -> None:
        """Every field KWS documents as required is present and correct."""
        recorder = _Recorder([_OK])

        result = await _client(recorder).send_verification_email(
            _REQUEST, correlation=_CORRELATION
        )

        body = _body_of(recorder.send_requests[0])
        assert body["email"] == _PARENT_EMAIL
        assert body["location"] == "US"
        assert body["language"] == "en"
        assert body["externalPayload"] == json.dumps(
            {"v": 1, "attemptId": str(result.correlation.attempt_id)},
            separators=(",", ":"),
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_user_context_is_parent(self) -> None:
        """Only the parent flow raises the event our receiver waits for.

        The other documented values, "adult" and "age", are age-assurance
        flows. Sending one would still return a success, and the verification
        result would simply never arrive at our parent-verified receiver, so
        nothing downstream would report the mistake.
        """
        recorder = _Recorder([_OK])

        await _client(recorder).send_verification_email(
            _REQUEST, correlation=_CORRELATION
        )

        assert _body_of(recorder.send_requests[0])["userContext"] == "parent"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sends_a_non_empty_user_agent(self) -> None:
        """KWS answers 403 "Request blocked" without one.

        That reads like an authorization failure and is not one, which is
        exactly the kind of misdiagnosis a test is cheaper than.
        """
        recorder = _Recorder([_OK])

        await _client(recorder).send_verification_email(
            _REQUEST, correlation=_CORRELATION
        )

        assert recorder.send_requests[0].headers["user-agent"] == "cyo-adventure-test"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_authenticates_against_the_separate_auth_host(self) -> None:
        """The token host is not the API host.

        An earlier reading that one published URL served both was falsified
        against the docs; this pins the corrected behaviour.
        """
        recorder = _Recorder([_OK])

        await _client(recorder).send_verification_email(
            _REQUEST, correlation=_CORRELATION
        )

        assert str(recorder.requests[0].url) == _TOKEN_URL
        assert str(recorder.send_requests[0].url) == _SEND_URL

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_token_leg_uses_basic_auth_and_client_credentials(self) -> None:
        """The documented grant, with the API key as the Basic password."""
        recorder = _Recorder([_OK])

        await _client(recorder).send_verification_email(
            _REQUEST, correlation=_CORRELATION
        )

        token_request = recorder.requests[0]
        assert token_request.headers["authorization"].startswith("Basic ")
        assert b"grant_type=client_credentials" in token_request.content
        assert b"scope=verification" in token_request.content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_leg_carries_the_bearer_token(self) -> None:
        """The token minted on the auth host is what authorizes the API call."""
        recorder = _Recorder([_OK])

        await _client(recorder).send_verification_email(
            _REQUEST, correlation=_CORRELATION
        )

        assert recorder.send_requests[0].headers["authorization"] == f"Bearer {_TOKEN}"


@pytest.mark.usefixtures("_configured")
class TestTokenHandling:
    """Minting, caching, and re-minting the access token."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_token_is_reused_across_calls(self) -> None:
        """The token endpoint sits behind a WAF that rate-limits.

        A client that re-authenticated per verification would spend that budget
        on nothing, so the cache is a correctness property, not an optimisation.
        """
        recorder = _Recorder([_OK])
        client = _client(recorder)

        await client.send_verification_email(_REQUEST, correlation=_CORRELATION)
        await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        assert recorder.token_calls == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_sends_authenticate_once(self) -> None:
        """Concurrent callers on a cold cache share one token fetch.

        Without the lock, a burst would each mint a token and race to overwrite
        the others, multiplying load on the one endpoint that punishes it.

        The suspending transport is what makes this a real test rather than a
        tautology. ``httpx.MockTransport`` answers without ever yielding, so
        five gathered sends run strictly one after another and the second finds
        a warm cache no matter what the lock does: with the lock deleted, this
        assertion still held. ``_SuspendingTransport`` yields inside the token
        call, which is what interleaves the five and lets an unguarded cache
        actually be raced.
        """
        recorder = _Recorder([_OK])
        client = KwsClient(httpx.AsyncClient(transport=_SuspendingTransport(recorder)))

        await asyncio.gather(
            *(
                client.send_verification_email(_REQUEST, correlation=_CORRELATION)
                for _ in range(5)
            )
        )

        assert recorder.token_calls == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_401_mints_a_fresh_token_and_retries(self) -> None:
        """KWS token lifetimes vary, so a 401 means expiry, not bad credentials."""
        recorder = _Recorder([401, _OK])

        await _client(recorder).send_verification_email(
            _REQUEST, correlation=_CORRELATION
        )

        assert recorder.token_calls == 2
        assert len(recorder.send_requests) == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_second_401_is_terminal(self) -> None:
        """A brand new token rejected again is a real authorization failure.

        Retrying past this point would loop against a credential problem no
        amount of waiting fixes, which is why the error is the
        operator-facing ConfigurationError and not the retryable
        ExternalServiceError (see TestCredentialRejection).
        """
        recorder = _Recorder([401])

        client = _client(recorder)

        with pytest.raises(ConfigurationError):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        assert recorder.token_calls == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_auth_failure_is_reported_not_swallowed(self) -> None:
        """Bad client credentials surface as an operator-fixable error."""

        def handle(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(403, text="nope")

        client = KwsClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))

        with pytest.raises(ConfigurationError):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_auth_response_without_a_token_is_rejected(self) -> None:
        """A 200 with no access_token must not be read as success."""

        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token"):
                return httpx.Response(200, json={"expires_in": 3600})
            return httpx.Response(200, json={})

        client = KwsClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))

        with pytest.raises(ExternalServiceError):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_token_without_expires_in_is_still_cached(self) -> None:
        """Epic says the lifetime varies, so its absence must not be fatal.

        Caching it forever and leaning on re-auth-on-401 is the documented
        fallback. Treating a missing expiry as "already expired" would
        re-authenticate on every single call, which is the failure this avoids.
        """
        calls = {"token": 0}

        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token"):
                calls["token"] += 1
                return httpx.Response(200, json={"access_token": _TOKEN})
            return httpx.Response(200, json={})

        client = KwsClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        await client.send_verification_email(_REQUEST, correlation=_CORRELATION)
        await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        assert calls["token"] == 1


@pytest.mark.usefixtures("_configured")
class TestRetryPolicy:
    """What is retried, and what deliberately is not."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_5xx_is_retried(self) -> None:
        """A server fault may not recur, so backoff is worth the wait."""
        recorder = _Recorder([503, _OK])

        with patch("cyo_adventure.consent.kws_client._BACKOFF_BASE_SECONDS", 0):
            await _client(recorder).send_verification_email(
                _REQUEST, correlation=_CORRELATION
            )

        assert len(recorder.send_requests) == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retries_are_bounded(self) -> None:
        """A permanently failing upstream must not hold the caller forever."""
        recorder = _Recorder([500])
        client = _client(recorder)

        with (
            patch("cyo_adventure.consent.kws_client._BACKOFF_BASE_SECONDS", 0),
            pytest.raises(ExternalServiceError),
        ):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        assert len(recorder.send_requests) == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_429_is_not_retried(self) -> None:
        """The limit is ten per hour per email address.

        A retry seconds later cannot succeed and spends another slot from the
        guardian's hourly budget for that address, so the honest answer is to
        surface it. This is a deliberate narrowing of Epic's "back off on any
        non-2xx" guidance.
        """
        recorder = _Recorder([429])

        client = _client(recorder)

        with pytest.raises(ExternalServiceError) as caught:
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        assert len(recorder.send_requests) == 1
        assert caught.value.error_code == "KWS_RATE_LIMITED"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_400_is_not_retried(self) -> None:
        """A malformed request is malformed on the second attempt too."""
        recorder = _Recorder([400])

        client = _client(recorder)

        with pytest.raises(ExternalServiceError):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        assert len(recorder.send_requests) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_transport_failure_is_retried_then_reported(self) -> None:
        """A dropped connection is transient until it has happened three times."""
        attempts = {"count": 0}

        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token"):
                return httpx.Response(
                    200, json={"access_token": _TOKEN, "expires_in": 3600}
                )
            attempts["count"] += 1
            msg = "connection reset"
            raise httpx.ConnectError(msg)

        client = KwsClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))

        with (
            patch("cyo_adventure.consent.kws_client._BACKOFF_BASE_SECONDS", 0),
            pytest.raises(ExternalServiceError),
        ):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        assert attempts["count"] == 3


@pytest.mark.usefixtures("_configured")
class TestValidation:
    """Rejecting locally what KWS would reject at the cost of a slot."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("email", "location"),
        [
            ("", "US"),
            ("no-at-sign", "US"),
            ("two@@at.example", "US"),
            ("has space@example.com", "US"),
            ("@example.com", "US"),
            ("parent@localhost", "US"),
            (_PARENT_EMAIL, "usa"),
            (_PARENT_EMAIL, "United States"),
            (_PARENT_EMAIL, "us"),
            (_PARENT_EMAIL, ""),
        ],
        ids=[
            "empty_email",
            "no_at",
            "double_at",
            "whitespace_in_email",
            "no_local_part",
            "no_dot_in_domain",
            "lowercase_country",
            "country_name",
            "lowercase_two_letter",
            "empty_location",
        ],
    )
    async def test_bad_input_never_reaches_the_vendor(
        self, email: str, location: str
    ) -> None:
        """Ten requests per hour per email is a budget a 4xx would spend."""
        recorder = _Recorder([_OK])
        request = VerificationEmailRequest(email=email, location=location)

        client = _client(recorder)

        with pytest.raises(ValidationError):
            await client.send_verification_email(request, correlation=_CORRELATION)

        assert recorder.send_requests == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.parametrize("location", ["US", "GB", "US-NY", "GB-ENG", "CA-BC"])
    async def test_documented_location_formats_accepted(self, location: str) -> None:
        """Both ISO 3166-1 alpha-2 and ISO 3166-2 subdivisions are valid."""
        recorder = _Recorder([_OK])
        request = VerificationEmailRequest(email=_PARENT_EMAIL, location=location)

        await _client(recorder).send_verification_email(
            request, correlation=_CORRELATION
        )

        assert _body_of(recorder.send_requests[0])["location"] == location

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_validation_errors_omit_the_email(self) -> None:
        """The app's error handler logs a ValidationError's ``value``.

        Passing the address as value= would write a parent's email into every
        log sink on every typo, so only ``field`` is ever set.
        """
        request = VerificationEmailRequest(email="not-an-email", location="US")

        client = _client(_Recorder([_OK]))

        with pytest.raises(ValidationError) as caught:
            await client.send_verification_email(request, correlation=_CORRELATION)

        assert "not-an-email" not in json.dumps(caught.value.to_dict())


class TestRefusalToRun:
    """Configurations the send leg declines to serve."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unconfigured_integration_refuses_to_send(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unconfigured deployment is inert, not broken at the vendor."""
        monkeypatch.setattr(settings, "kws_environment", "test")
        monkeypatch.setattr(settings, "kws_api_origin", None)
        monkeypatch.setattr(settings, "kws_client_id", None)
        monkeypatch.setattr(settings, "kws_api_key", None)
        monkeypatch.setattr(settings, "kws_organization_id", None)
        recorder = _Recorder([_OK])

        client = _client(recorder)

        with pytest.raises(ConfigurationError):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        assert recorder.requests == []


@pytest.mark.usefixtures("_configured")
class TestCredentialRejection:
    """A rejected credential is the operator's problem, not the parent's.

    UW-A55 gave ExternalServiceError its own 502 so a transient vendor
    failure would stop reading as a permanent refusal. That leaves the mirror
    defect live unless the credential case is split back out: a wrong client
    id or API key would otherwise arrive as the same 502, and the page's
    502 copy invites the retry that cannot possibly work. These tests pin the
    split at both legs and in both directions.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [401, 403])
    async def test_the_token_leg_rejecting_us_is_a_configuration_error(
        self, status: int
    ) -> None:
        """A client-credentials grant carries no user input.

        Nothing a guardian did can make the token endpoint answer 401 or 403,
        so the only remaining explanation is our own client id, API key, or
        grant, and no retry changes any of them.
        """

        def handle(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(status, json={})

        client = KwsClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))

        with pytest.raises(ConfigurationError):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_send_leg_403_is_a_configuration_error(self) -> None:
        """A 403 on the send leg is the "Request blocked" User-Agent answer.

        Vendor constraint 1: a missing or empty User-Agent is a 403 that
        reads like an authorization failure. Either reading is an operator
        setting, never a transient outage.
        """
        recorder = _Recorder([403])

        client = _client(recorder)

        with pytest.raises(ConfigurationError):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        # One attempt, not three: a blocked request is blocked on every retry
        # and each one spends a slot from the address's hourly budget.
        assert len(recorder.send_requests) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_credential_rejection_tells_the_client_nothing_about_the_vendor(
        self,
    ) -> None:
        """The diagnostic goes to the log; the error body does not carry it.

        The counterpart to app.py's `_SENSITIVE_DETAIL_KEYS`: that prunes the
        vendor's identity and status out of a response body, and this keeps
        them from being written into the message string, where no pruning
        would reach them.
        """
        recorder = _Recorder([403])
        client = _client(recorder)

        with (
            patch("cyo_adventure.consent.kws_client.logger") as mock_logger,
            pytest.raises(ConfigurationError) as caught,
        ):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        rendered = json.dumps(caught.value.to_dict())
        assert "KWS" not in rendered
        assert "kws" not in rendered
        assert "403" not in rendered
        # The operator keeps both, on a distinctly-named event an alert can
        # key on without parsing a generic failure line.
        logged = _rendered(mock_logger)
        assert "kws_credentials_rejected" in logged
        assert "403" in logged

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_5xx_is_still_the_retryable_error(self) -> None:
        """The split must not swallow the case UW-A55 was actually about.

        Without this, narrowing 401/403 to ConfigurationError could be
        satisfied by narrowing everything, which would put a genuine outage
        back on the "contact support" copy it was moved off.
        """
        recorder = _Recorder([503])
        client = _client(recorder)

        with (
            patch("cyo_adventure.consent.kws_client._BACKOFF_BASE_SECONDS", 0),
            pytest.raises(ExternalServiceError),
        ):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)


@pytest.mark.usefixtures("_configured")
class TestDisclosure:
    """What the send leg is allowed to say about a verification."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_email_address_is_never_logged(self) -> None:
        """The attempt id identifies no person and is the right log handle."""
        recorder = _Recorder([_OK])

        with patch("cyo_adventure.consent.kws_client.logger") as mock_logger:
            result = await _client(recorder).send_verification_email(
                _REQUEST, correlation=_CORRELATION
            )

        rendered = _rendered(mock_logger)
        assert _PARENT_EMAIL not in rendered
        assert "example.com" not in rendered
        assert str(result.correlation.attempt_id) in rendered

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_api_key_never_appears_in_logs_or_errors(self) -> None:
        """The API key is the credential for the whole environment."""
        recorder = _Recorder([400])
        client = _client(recorder)

        with (
            patch("cyo_adventure.consent.kws_client.logger") as mock_logger,
            pytest.raises(ExternalServiceError) as caught,
        ):
            await client.send_verification_email(_REQUEST, correlation=_CORRELATION)

        assert _API_KEY not in _rendered(mock_logger)
        assert _API_KEY not in json.dumps(caught.value.to_dict())


def _rendered(mock_logger: Any) -> str:
    """Flatten every argument of every call made to a mocked logger.

    Args:
        mock_logger: The patched module-level logger.

    Returns:
        str: All positional and keyword arguments of all calls, stringified.
    """
    return " ".join(
        f"{call.args} {call.kwargs}"
        for call in mock_logger.mock_calls
        if call.args or call.kwargs
    )
