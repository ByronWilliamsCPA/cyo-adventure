"""Tests for the KWS verification redirect return page.

Three properties carry the weight here. A return we cannot authenticate never
renders as success; the four ways a return can fail authentication are
indistinguishable from one another; and a value that has to travel through
URL encoding still verifies against the literal string KWS signed.
"""

from __future__ import annotations

import ast
import hmac
import inspect
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from cyo_adventure.api import kws_redirect
from cyo_adventure.app import create_app
from cyo_adventure.core.config import settings

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType


def _names_used(module: ModuleType) -> set[str]:
    """Every identifier a module actually evaluates.

    Substring matching over raw source cannot tell code from the prose that
    explains it, and cannot tell an identifier from a longer one containing
    it: ``settings.kws_verification_secret`` contains the table name
    ``kws_verification``, and a docstring stating an invariant contains every
    symbol the invariant forbids. Both produce a guard that fails on
    well-documented correct code, which trains the next reader to weaken it.

    Args:
        module: The module to read.

    Returns:
        set[str]: The module's identifiers and attribute names.
    """
    tree = ast.parse(inspect.getsource(module))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    return names | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}


def _modules_imported(module: ModuleType) -> set[str]:
    """Every module a module imports, by dotted path.

    Args:
        module: The module to read.

    Returns:
        set[str]: Dotted module paths named in ``import`` and ``from`` forms.
    """
    tree = ast.parse(inspect.getsource(module))
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    return {path for path in imported if path is not None}


_SECRET = "test-verification-secret-not-a-real-credential"
_URL = "/api/v1/consent/kws/return"

# The literal the page renders, asserted as bytes rather than read back off
# the route module: what matters is what reaches the parent's browser.
_LANDING_PATH = "/guardian"

_VERIFIED_STATUS = '{"verified": true, "transactionId": "tx-1"}'
_UNVERIFIED_STATUS = '{"verified": false}'
_EXTERNAL = "corr-1"


def _sign(status: str, external_payload: str, *, secret: str = _SECRET) -> str:
    """Sign a return the way KWS would: HMAC over the literal, undecorated pair.

    Args:
        status: The literal ``status`` value, before any URL encoding.
        external_payload: The literal ``externalPayload`` value.
        secret: The verification secret to sign under.

    Returns:
        str: The lowercase hex signature.
    """
    signed = f"{status}:{external_payload}".encode()
    return hmac.new(secret.encode(), signed, sha256).hexdigest()


def _params(
    status: str = _VERIFIED_STATUS,
    external_payload: str = _EXTERNAL,
    *,
    secret: str = _SECRET,
) -> dict[str, str]:
    """Build a correctly signed query parameter mapping.

    Args:
        status: The literal ``status`` value.
        external_payload: The literal ``externalPayload`` value.
        secret: The secret to sign under.

    Returns:
        dict[str, str]: Parameters ready to hand to the test client, which
            percent-encodes them on the way out.
    """
    return {
        "status": status,
        "externalPayload": external_payload,
        "signature": _sign(status, external_payload, secret=secret),
    }


@pytest.fixture
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured Test-environment redirect leg.

    The settings object is a module-level singleton the route reads directly
    and it has no ``validate_assignment``, so patching an attribute on it is a
    plain set rather than a revalidation of the whole model.
    """
    monkeypatch.setattr(settings, "kws_verification_secret", SecretStr(_SECRET))
    monkeypatch.setattr(settings, "kws_environment", "test")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A test client over the real app, so the exception handlers are wired."""
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def audit() -> Iterator[AsyncMock]:
    """Stub the durable security-audit write for every test in this module.

    ``record_security_event`` opens a database session of its own. It swallows
    its own failures, so leaving it live would not fail anything here; it would
    just make each rejection test attempt a real connection, which
    ``tests/CLAUDE.md`` forbids and which costs a connect timeout apiece.

    Autouse plus assertions against the same mock is deliberate: a stub that no
    test inspects would silently absorb a dropped call, so
    ``test_a_refused_return_is_recorded_as_a_security_event`` reads this very
    object.

    Yields:
        AsyncMock: The stubbed recorder.
    """
    with patch(
        "cyo_adventure.api.kws_redirect.record_security_event",
        new_callable=AsyncMock,
    ) as recorder:
        yield recorder


@pytest.mark.usefixtures("_configured")
class TestSignature:
    """What the page will and will not render a result for."""

    @pytest.mark.unit
    def test_valid_signature_renders_the_success_page(self, client: TestClient) -> None:
        """The ordinary case: signed by KWS, and the status says verified."""
        response = client.get(_URL, params=_params())

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Verification complete" in response.text

    @pytest.mark.unit
    def test_valid_signature_with_a_failure_status_renders_the_failure_page(
        self, client: TestClient
    ) -> None:
        """An authentic return reporting no verification is still a 200.

        The parent finished the flow and deserves a real answer; only the
        wording changes. Reserving the non-200 for returns we cannot
        authenticate is what keeps the two situations distinguishable in logs.
        """
        response = client.get(_URL, params=_params(_UNVERIFIED_STATUS))

        assert response.status_code == 200
        assert "Verification was not completed" in response.text

    @pytest.mark.unit
    def test_url_encoded_values_still_verify(self, client: TestClient) -> None:
        """A status full of characters URL encoding mangles still verifies.

        This is the whole raw-versus-decoded question in one test. The
        signature covers the literal JSON-ish string, which contains braces,
        quotes, colons, spaces and a plus; the wire carries a percent-encoded
        form of it. The route must feed the verifier Starlette's decoded view,
        because handing it the encoded query string would never match.

        The assertion on the outgoing URL is what keeps this test honest: if
        the client stopped encoding, the test would pass for the wrong reason.
        """
        status = '{"verified": true, "note": "a+b c/d"}'
        params = _params(status, "corr/1+2 3")

        response = client.get(_URL, params=params)

        raw_query = str(response.request.url.query)
        assert "%7B" in raw_query, "expected the client to percent-encode the value"
        assert "%2B" in raw_query, "expected the client to percent-encode the plus"
        assert response.status_code == 200
        assert "Verification complete" in response.text

    @pytest.mark.unit
    def test_tampered_status_is_rejected(self, client: TestClient) -> None:
        """Flipping the verified flag after signing does not verify."""
        params = _params()
        params["status"] = _UNVERIFIED_STATUS

        response = client.get(_URL, params=params)

        assert response.status_code == 400
        assert "We could not confirm this link" in response.text

    @pytest.mark.unit
    def test_tampered_external_payload_is_rejected(self, client: TestClient) -> None:
        """The correlation token is inside the signed string, so it is bound too.

        Without this, a valid return for one attempt could be replayed against
        another guardian's attempt by swapping one query parameter.
        """
        params = _params()
        params["externalPayload"] = "corr-someone-else"

        response = client.get(_URL, params=params)

        assert response.status_code == 400

    @pytest.mark.unit
    def test_wrong_secret_is_rejected(self, client: TestClient) -> None:
        """A signature under another key does not verify."""
        response = client.get(_URL, params=_params(secret="another-secret-entirely"))

        assert response.status_code == 400

    @pytest.mark.unit
    def test_missing_signature_is_rejected(self, client: TestClient) -> None:
        """No signature at all is a rejection, not a 422 about a missing field.

        The parameters are read off the query mapping rather than declared, so
        an incomplete return lands on the failure page a browser can read.
        """
        response = client.get(
            _URL, params={"status": _VERIFIED_STATUS, "externalPayload": _EXTERNAL}
        )

        assert response.status_code == 400
        assert "We could not confirm this link" in response.text

    @pytest.mark.unit
    def test_no_query_parameters_at_all_is_rejected(self, client: TestClient) -> None:
        """A bare visit to the URL renders the failure page, never success."""
        response = client.get(_URL)

        assert response.status_code == 400
        assert "Verification complete" not in response.text


@pytest.mark.usefixtures("_configured")
class TestStatusReading:
    """How an authenticated status value is read into one of two screens."""

    @pytest.mark.unit
    def test_json_object_status_reports_verified(self, client: TestClient) -> None:
        """The better-evidenced shape, matching the webhook's own status object."""
        response = client.get(_URL, params=_params('{"verified": true}'))

        assert "Verification complete" in response.text

    @pytest.mark.unit
    def test_bare_json_literal_status_reports_verified(
        self, client: TestClient
    ) -> None:
        """A bare ``true`` is not a JSON object and is still affirmative."""
        response = client.get(_URL, params=_params("true"))

        assert "Verification complete" in response.text

    @pytest.mark.unit
    def test_bare_token_status_reports_verified(self, client: TestClient) -> None:
        """A plain word, which is not JSON at all, is read by the fallback."""
        response = client.get(_URL, params=_params("verified"))

        assert "Verification complete" in response.text

    @pytest.mark.unit
    def test_quoted_token_status_reports_verified(self, client: TestClient) -> None:
        """A JSON string arrives with its quotes, which the fallback strips."""
        response = client.get(_URL, params=_params('"verified"'))

        assert "Verification complete" in response.text

    @pytest.mark.unit
    def test_unrecognised_status_reports_not_verified(self, client: TestClient) -> None:
        """An authentic status we cannot read falls to the safe side.

        The page writes nothing, so under-reporting costs the parent a retry;
        over-reporting would tell them a verification happened that we have no
        evidence for.
        """
        response = client.get(_URL, params=_params("something-new-from-epic"))

        assert response.status_code == 200
        assert "Verification was not completed" in response.text

    @pytest.mark.unit
    def test_empty_status_reports_not_verified(self, client: TestClient) -> None:
        """An empty but correctly signed status is not an affirmation."""
        response = client.get(_URL, params=_params(""))

        assert response.status_code == 200
        assert "Verification was not completed" in response.text


@pytest.mark.usefixtures("_configured")
class TestDisclosure:
    """What the page is allowed to say about why a return was refused."""

    @pytest.mark.unit
    def test_every_rejection_cause_is_indistinguishable(
        self, client: TestClient
    ) -> None:
        """Four different failures, one byte-identical answer.

        Otherwise the page is an oracle: probe once to learn the signature
        format is right, again to learn the key is wrong.
        """
        tampered_status = _params()
        tampered_status["status"] = _UNVERIFIED_STATUS
        tampered_payload = _params()
        tampered_payload["externalPayload"] = "corr-someone-else"
        no_signature = {"status": _VERIFIED_STATUS, "externalPayload": _EXTERNAL}

        responses = [
            client.get(_URL, params=tampered_status),
            client.get(_URL, params=tampered_payload),
            client.get(_URL, params=_params(secret="another-secret-entirely")),
            client.get(_URL, params=no_signature),
        ]

        assert {r.status_code for r in responses} == {400}
        assert len({r.text for r in responses}) == 1

    @pytest.mark.unit
    def test_a_refused_return_is_recorded_as_a_security_event(
        self, client: TestClient, audit: AsyncMock
    ) -> None:
        """OPS-005: a forged return is an auth failure and must leave a row.

        This route cannot reach ``record_security_event`` the way the other 89
        auth-failure sites do, because raising ``AuthenticationError`` renders
        JSON at a parent instead of a page. That makes the call an explicit
        one, and an explicit call is exactly what a later edit can drop without
        any other test in this file noticing.
        """
        client.get(_URL, params=_params(secret="another-secret-entirely"))

        audit.assert_awaited_once()
        recorded = audit.await_args.kwargs
        assert recorded["event_type"] == "security_auth_failed"
        assert recorded["reason"] == "redirect_signature_mismatch"
        assert recorded["path"] == _URL
        assert recorded["status_code"] == 400

    @pytest.mark.unit
    def test_a_verified_return_records_no_security_event(
        self, client: TestClient, audit: AsyncMock
    ) -> None:
        """The audit write lives on the refusal path and nowhere else.

        This is what makes the write safe on a replayable URL: replaying a
        forged link a thousand times writes a thousand rows all saying the same
        forgery was refused, and a SUCCESSFUL return writes nothing at all, so
        no amount of replay can produce a record asserting anyone was verified.
        """
        response = client.get(_URL, params=_params())

        assert response.status_code == 200
        audit.assert_not_awaited()

    @pytest.mark.unit
    def test_rejection_page_names_no_discriminator(self, client: TestClient) -> None:
        """The verifier's own reason codes must not reach the rendered page."""
        params = _params()
        params["status"] = _UNVERIFIED_STATUS

        response = client.get(_URL, params=params)

        assert "redirect_signature_mismatch" not in response.text
        assert "missing_redirect_signature" not in response.text
        assert "signature" not in response.text.lower()

    @pytest.mark.unit
    def test_rejection_reason_still_reaches_telemetry(self, client: TestClient) -> None:
        """The other half of the contract above.

        Withholding the reason from the caller is only correct if we keep it
        ourselves; otherwise the fix for the disclosure is indistinguishable
        from deleting the signal.
        """
        params = _params()
        params["status"] = _UNVERIFIED_STATUS

        with patch("cyo_adventure.api.kws_redirect.logger") as mock_logger:
            client.get(_URL, params=params)

        rendered = _rendered_log_calls(mock_logger)
        assert "kws_redirect_rejected" in rendered
        assert "redirect_signature_mismatch" in rendered

    @pytest.mark.unit
    def test_accepted_return_logs_no_correlation_token(
        self, client: TestClient
    ) -> None:
        """The per-attempt token's presence is worth logging; its value is not."""
        with patch("cyo_adventure.api.kws_redirect.logger") as mock_logger:
            client.get(_URL, params=_params(external_payload="corr-secret-token"))

        rendered = _rendered_log_calls(mock_logger)
        assert "kws_redirect_return" in rendered
        assert "corr-secret-token" not in rendered

    @pytest.mark.unit
    def test_page_is_not_cached(self, client: TestClient) -> None:
        """A permanently replayable URL should not also be a cached page."""
        response = client.get(_URL, params=_params())

        assert response.headers["cache-control"] == "no-store"


@pytest.mark.usefixtures("_configured")
class TestLanding:
    """Where the page leaves a parent who has finished at Epic."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("params", "expected_status"),
        [
            (_params(), 200),
            (_params(_UNVERIFIED_STATUS), 200),
            ({"status": _VERIFIED_STATUS, "externalPayload": _EXTERNAL}, 400),
        ],
        ids=["verified", "not-verified", "unconfirmed"],
    )
    def test_every_page_offers_a_way_back_into_the_app(
        self,
        client: TestClient,
        params: dict[str, str],
        expected_status: int,
    ) -> None:
        """All three outcomes, one way out.

        The parent reaches this page from a link in Epic's email, so there is
        no history to go back through and, in a mail app's browser, no session
        either. Without a link the page is a dead end whichever way the
        verification went, and the two non-success pages are the ones that ask
        the parent to start again.

        Covering the rejection page here also keeps the three structurally
        alike: an offer present on success and absent on refusal would hand
        back exactly the discriminator ``TestDisclosure`` exists to deny.
        """
        response = client.get(_URL, params=params)

        assert response.status_code == expected_status
        assert f'href="{_LANDING_PATH}"' in response.text
        assert "Return to CYO Adventure" in response.text

    @pytest.mark.unit
    def test_the_landing_path_matches_the_app_route(self) -> None:
        """The one thing that silently breaks this link is a frontend rename.

        The path is a literal on both sides of a stack boundary with nothing
        connecting them, so a route rename in the SPA would leave this page
        pointing at the app's own 404 and every test above would still pass.
        Reading the constant the router actually uses is what makes that a
        failing test rather than a report from a parent.
        """
        routes = Path(__file__).resolve().parents[2] / "frontend" / "src" / "routes.ts"

        assert routes.is_file(), f"expected the SPA route table at {routes}"
        assert f"GUARDIAN_CONSOLE_PATH = '{_LANDING_PATH}'" in routes.read_text(
            encoding="utf-8"
        ), f"the SPA no longer routes {_LANDING_PATH} to the guardian console"


class TestRefusalToRun:
    """The configuration the page declines to serve at all."""

    @pytest.mark.unit
    def test_unconfigured_secret_refuses(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no secret, every return is unverifiable, so none is believed.

        Rendering "verified" here would mean believing a URL anyone could type,
        which is strictly worse than showing nothing.
        """
        monkeypatch.setattr(settings, "kws_verification_secret", None)

        response = client.get(_URL, params=_params())

        assert response.status_code == 400
        assert "Verification complete" not in response.text

    @pytest.mark.unit
    def test_empty_secret_refuses(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty SecretStr is an unset secret, not a configured empty key."""
        monkeypatch.setattr(settings, "kws_verification_secret", SecretStr(""))

        response = client.get(_URL, params=_params())

        assert response.status_code == 400
        assert "Verification complete" not in response.text

    @pytest.mark.unit
    def test_the_webhook_secret_does_not_configure_this_leg(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The two legs use different keys, and confusing them must not work."""
        monkeypatch.setattr(settings, "kws_verification_secret", None)
        monkeypatch.setattr(settings, "kws_webhook_secret", SecretStr(_SECRET))

        response = client.get(_URL, params=_params())

        assert response.status_code == 400
        assert "Verification complete" not in response.text


class TestNoPersistence:
    """The route is display-only, and that is checked rather than promised."""

    @pytest.mark.unit
    def test_route_module_never_touches_verification_state(self) -> None:
        """No session, ORM, commit, or verification record anywhere in the module.

        A signed return URL is a permanently replayable bearer token, so this
        route may choose a screen and nothing else. The check is on the module
        source rather than on behaviour because the defect being guarded
        against is a future edit, not a current bug: an added write would be
        invisible to every other test in this file.

        The property is "no CONSENT state", not "no bytes": ``_reject`` writes
        a security-audit row, which asserts that a return was refused and can
        never assert that anybody was verified. So the verification table and
        its service seam are named here explicitly, rather than relying on the
        generic session and ORM tokens to catch them by side effect.
        """
        used = _names_used(kws_redirect)
        forbidden_names = {"get_session", "AsyncSession", "KwsVerification", "commit"}
        assert not (used & forbidden_names), (
            f"redirect route must not use {sorted(used & forbidden_names)}"
        )

        imported = _modules_imported(kws_redirect)
        forbidden_modules = {"cyo_adventure.db", "cyo_adventure.consent.service"}
        offending = {
            path
            for path in imported
            for banned in forbidden_modules
            if path == banned or path.startswith(f"{banned}.")
        }
        assert not offending, f"redirect route must not import {sorted(offending)}"

    @pytest.mark.unit
    def test_success_page_is_self_contained(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No scripts and no external assets, so the page needs no network."""
        monkeypatch.setattr(settings, "kws_verification_secret", SecretStr(_SECRET))
        with TestClient(create_app(), raise_server_exceptions=False) as client:
            response = client.get(_URL, params=_params())

        assert "<script" not in response.text
        assert "http://" not in response.text
        assert "https://" not in response.text


class TestSchemaExposure:
    """The return page stays out of the generated client's contract."""

    @pytest.mark.unit
    def test_route_absent_from_the_openapi_schema(self) -> None:
        """include_in_schema=False, so the committed frontend client never churns.

        The contract-drift CI job compares generated files, so adding a
        browser-only landing page to the schema would regenerate the axios
        client for a route no SPA will ever call.
        """
        schema = create_app().openapi()

        assert _URL not in schema["paths"]


def _rendered_log_calls(mock_logger: Any) -> str:
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
