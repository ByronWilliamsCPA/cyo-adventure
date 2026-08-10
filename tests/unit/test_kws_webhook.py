"""Tests for the KWS ``parent-verified`` webhook receiver.

Four properties matter more than the happy path and are pinned individually:
an unauthenticated caller cannot get past the signature check, an
authenticated delivery that is not ours is answered terminally rather than
retried forever, a delivery that IS ours resolves its verification row, and the
parent's email address never reaches a log line.

The session is the shared ``mock_async_session`` double, not a database: what
this module tests is the route's routing and its acknowledgement, and what
happens to the row is pinned against the service seam in
``test_kws_verification_service.py``.
"""

from __future__ import annotations

import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from cyo_adventure.api.deps import get_db_session
from cyo_adventure.app import create_app
from cyo_adventure.consent import VerificationCorrelation, serialize_correlation
from cyo_adventure.core.config import settings
from cyo_adventure.db.models import KwsVerification

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import AsyncSession

_SECRET = "test-webhook-secret-not-a-real-credential"
_ORG = "00000000-0000-4000-8000-000000000001"
_PRODUCT = "00000000-0000-4000-8000-000000000009"
_PARENT_EMAIL = "parent.under.test@example.com"
_URL = "/api/v1/webhooks/kws/parent-verified"
_USER_ID = uuid.UUID("00000000-0000-4000-8000-00000000000a")
# The attempt the default body quotes back, and the id the default seeded row
# is written under. A delivery is only ours because these two agree.
_ATTEMPT_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c0")
_EXTERNAL_PAYLOAD = serialize_correlation(VerificationCorrelation(_ATTEMPT_ID))


def _body(
    *,
    name: str = "parent-verified",
    org_id: str = _ORG,
    product_id: str = _PRODUCT,
    external_payload: str | None = _EXTERNAL_PAYLOAD,
) -> bytes:
    """A delivery body shaped exactly like Epic's documented example."""
    payload: dict[str, Any] = {
        "parentEmail": _PARENT_EMAIL,
        "status": {"verified": True, "transactionId": "tx-1"},
    }
    if external_payload is not None:
        payload["externalPayload"] = external_payload
    return json.dumps(
        {
            "name": name,
            "time": "2026-08-09T12:00:00Z",
            "orgId": org_id,
            "productId": product_id,
            "payload": payload,
        }
    ).encode()


def _sent_row(**overrides: Any) -> KwsVerification:
    """An unresolved verification row, as the send leg would have written it."""
    values: dict[str, Any] = {
        "id": _ATTEMPT_ID,
        "user_id": _USER_ID,
        "kws_environment": "test",
        "status": "sent",
        "requested_at": datetime.now(UTC),
        "resolved_at": None,
        "transaction_id": None,
        "enabled_methods": ["credit_card"],
    }
    values.update(overrides)
    return KwsVerification(**values)


def _headers(
    body: bytes, *, secret: str = _SECRET, at: int | None = None
) -> dict[str, str]:
    """Sign a body the way KWS would."""
    timestamp = int(time.time()) if at is None else at
    signature = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, sha256
    ).hexdigest()
    return {
        "x-kws-signature": f"t={timestamp},v1={signature}",
        "content-type": "application/json",
    }


@pytest.fixture
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured Test-environment receiver.

    The settings object is a module-level singleton the route reads directly,
    and it has no ``validate_assignment``, so patching attributes on it is a
    plain set rather than a revalidation of the whole model.
    """
    monkeypatch.setattr(settings, "kws_webhook_secret", SecretStr(_SECRET))
    monkeypatch.setattr(settings, "kws_environment", "test")
    monkeypatch.setattr(settings, "kws_organization_id", _ORG)
    monkeypatch.setattr(settings, "kws_product_id", None)
    monkeypatch.setattr(settings, "kws_webhook_max_skew_seconds", 300)


def _seeded_row(mock_async_session: AsyncMock) -> KwsVerification:
    """Return the row the ``client`` fixture seeded the session double with.

    Args:
        mock_async_session: The session double.

    Returns:
        KwsVerification: The seeded row, so a test can assert what the route
            did to it rather than only what it answered.
    """
    row = mock_async_session.get.return_value
    assert isinstance(row, KwsVerification)
    return row


@pytest.fixture
def client(mock_async_session: AsyncMock) -> Iterator[TestClient]:
    """A test client over the real app, so the exception handlers are wired.

    Only the session dependency is overridden, and it is seeded with the
    attempt the default body quotes back. The route now resolves a verification
    row, and a unit test must not reach a database (tests/CLAUDE.md), so the
    double stands in for the request unit of work.
    """

    async def _override() -> AsyncIterator[AsyncSession]:
        yield mock_async_session

    mock_async_session.get.return_value = _sent_row()
    app = create_app()
    app.dependency_overrides[get_db_session] = _override
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.mark.usefixtures("_configured")
class TestAuthentication:
    """Nothing unsigned, stale, or tampered may reach the parsing stage."""

    @pytest.mark.unit
    def test_valid_delivery_is_acknowledged(self, client: TestClient) -> None:
        """The ordinary case: signed, fresh, ours."""
        body = _body()

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 200
        assert response.json() == {"handled": True}

    @pytest.mark.unit
    def test_missing_signature_rejected(self, client: TestClient) -> None:
        """No header at all is a 401, not a 422 about a missing field."""
        response = client.post(_URL, content=_body())

        assert response.status_code == 401

    @pytest.mark.unit
    def test_tampered_body_rejected(self, client: TestClient) -> None:
        """A body edited after signing does not verify.

        The header is computed over the original body and sent with a modified
        one, which is precisely the attack the signature exists to stop.
        """
        original = _body()
        modified = original.replace(b'"verified": true', b'"verified": false')

        response = client.post(_URL, content=modified, headers=_headers(original))

        assert response.status_code == 401

    @pytest.mark.unit
    def test_stale_delivery_rejected(self, client: TestClient) -> None:
        """A correctly signed capture from an hour ago is still refused.

        Without the freshness window this delivery would verify forever, which
        is the defect in the one open-source reference implementation.
        """
        body = _body()
        headers = _headers(body, at=int(time.time()) - 3600)

        response = client.post(_URL, content=body, headers=headers)

        assert response.status_code == 401

    @pytest.mark.unit
    def test_wrong_secret_rejected(self, client: TestClient) -> None:
        """A signature under another key does not verify."""
        body = _body()
        headers = _headers(body, secret="some-other-secret-entirely")

        response = client.post(_URL, content=body, headers=headers)

        assert response.status_code == 401

    @pytest.mark.unit
    def test_oversized_body_rejected(self, client: TestClient) -> None:
        """The HMAC input is bounded, so unauthenticated CPU per request is too."""
        body = b"x" * (64 * 1024 + 1)

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 401

    @pytest.mark.unit
    def test_authenticated_non_json_rejected(self, client: TestClient) -> None:
        """Holding the secret does not buy the right to send garbage."""
        body = b"not json at all"

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 422

    @pytest.mark.unit
    def test_authenticated_non_object_rejected(self, client: TestClient) -> None:
        """A bare JSON array is valid JSON and still not a delivery envelope."""
        body = b"[1, 2, 3]"

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 422


@pytest.mark.usefixtures("_configured")
class TestEnvelopeRouting:
    """A delivery that verifies but is not ours gets a terminal answer."""

    @pytest.mark.unit
    def test_foreign_organization_acknowledged_but_not_handled(
        self, client: TestClient
    ) -> None:
        """200 with handled=False, deliberately, rather than an error.

        A delivery for another organization will never become ours, so a
        non-2xx would only buy a retry loop against a decision that cannot
        change.
        """
        body = _body(org_id="00000000-0000-4000-8000-0000000000ff")

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 200
        assert response.json() == {"handled": False}

    @pytest.mark.unit
    def test_unknown_event_name_not_handled(self, client: TestClient) -> None:
        """A future KWS event type is ignored, not rejected."""
        body = _body(name="parent-consent-revoked")

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 200
        assert response.json() == {"handled": False}

    @pytest.mark.unit
    def test_unpinned_product_id_still_handled(self, client: TestClient) -> None:
        """Before the product id is known, the organization check is the bound.

        Refusing everything until the id is pinned would prevent the very
        delivery that reveals it, so an unset product id is vacuously matched.
        """
        body = _body()

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.json() == {"handled": True}

    @pytest.mark.unit
    def test_pinned_product_id_mismatch_not_handled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Once pinned, an event for another product is not attributed to us."""
        monkeypatch.setattr(settings, "kws_product_id", _PRODUCT)
        body = _body(product_id="00000000-0000-4000-8000-0000000000ee")

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.json() == {"handled": False}

    @pytest.mark.unit
    def test_pinned_product_id_match_handled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pinned-and-matching case still works."""
        monkeypatch.setattr(settings, "kws_product_id", _PRODUCT)
        body = _body()

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.json() == {"handled": True}


class TestRefusalToRun:
    """Two configurations the receiver declines to serve at all."""

    @pytest.mark.unit
    def test_unconfigured_receiver_refuses(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No secret means every delivery is unverifiable, so none is accepted.

        Answering 2xx here would mean recording consent evidence we cannot
        attribute to KWS at all.
        """
        monkeypatch.setattr(settings, "kws_webhook_secret", None)
        body = _body()

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 400

    @pytest.mark.unit
    def test_empty_secret_refuses(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty SecretStr is an unset secret, not a configured empty key."""
        monkeypatch.setattr(settings, "kws_webhook_secret", SecretStr(""))
        body = _body()

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 400


@pytest.mark.usefixtures("_configured")
class TestAttribution:
    """Turning an authenticated delivery into a resolved verification row."""

    @pytest.mark.unit
    def test_our_attempt_is_resolved(
        self, client: TestClient, mock_async_session: AsyncMock
    ) -> None:
        """The delivery this receiver exists for: a row moves to verified."""
        body = _body()

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.json() == {"handled": True}
        row = _seeded_row(mock_async_session)
        assert row.status == "verified"
        assert row.transaction_id == "tx-1"

    @pytest.mark.unit
    def test_unknown_attempt_id_not_handled(
        self, client: TestClient, mock_async_session: AsyncMock
    ) -> None:
        """No row for the id: a replay after erasure, or a foreign delivery.

        200 rather than an error, deliberately. A non-2xx would buy a retry
        loop against a decision that cannot change, and there is nothing here
        for a later attempt to find.
        """
        mock_async_session.get.return_value = None
        body = _body()

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 200
        assert response.json() == {"handled": False}

    @pytest.mark.unit
    def test_missing_external_payload_not_handled(
        self, client: TestClient, mock_async_session: AsyncMock
    ) -> None:
        """With no correlation there is nothing to attribute the delivery to."""
        body = _body(external_payload=None)

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 200
        assert response.json() == {"handled": False}
        assert mock_async_session.get.await_count == 0

    @pytest.mark.unit
    def test_malformed_external_payload_not_handled(
        self, client: TestClient, mock_async_session: AsyncMock
    ) -> None:
        """An echoed payload is untrusted input, parsed in full, not guessed at.

        It never reaches a lookup: a body that is not our correlation cannot
        become one on a retry either.
        """
        body = _body(external_payload="corr-1")

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 200
        assert response.json() == {"handled": False}
        assert mock_async_session.get.await_count == 0

    @pytest.mark.unit
    def test_a_row_from_the_other_environment_is_not_handled(
        self, client: TestClient, mock_async_session: AsyncMock
    ) -> None:
        """A Test delivery must never resolve a production row, or vice versa."""
        mock_async_session.get.return_value = _sent_row(kws_environment="production")
        body = _body()

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.json() == {"handled": False}
        assert _seeded_row(mock_async_session).status == "sent"

    @pytest.mark.unit
    def test_a_replayed_delivery_is_handled_without_rewriting(
        self, client: TestClient, mock_async_session: AsyncMock
    ) -> None:
        """KWS retries deliveries; the second one must change nothing.

        Answered handled=True because the delivery IS ours and is already
        recorded; handled=False would invite a retry of work already done.
        """
        resolved_at = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        mock_async_session.get.return_value = _sent_row(
            status="verified", resolved_at=resolved_at, transaction_id="tx-first"
        )
        body = _body()

        response = client.post(_URL, content=body, headers=_headers(body))

        assert response.json() == {"handled": True}
        row = _seeded_row(mock_async_session)
        assert row.transaction_id == "tx-first"
        assert row.resolved_at == resolved_at

    @pytest.mark.unit
    def test_the_handler_never_commits_the_unit_of_work(
        self, client: TestClient, mock_async_session: AsyncMock
    ) -> None:
        """``UnitOfWorkMiddleware`` owns the commit, not the route."""
        body = _body()

        client.post(_URL, content=body, headers=_headers(body))

        assert mock_async_session.commit.await_count == 0


@pytest.mark.usefixtures("_configured")
class TestDisclosure:
    """What the receiver is allowed to say about a delivery."""

    @pytest.mark.unit
    def test_parent_email_is_never_logged(self, client: TestClient) -> None:
        """The most sensitive field in the delivery must not reach telemetry.

        Asserted against every argument of every log call rather than against
        one expected call, so a future log line added anywhere in the handler
        is covered by this test without anyone remembering to extend it.
        """
        body = _body()

        with patch("cyo_adventure.api.kws_webhook.logger") as mock_logger:
            response = client.post(_URL, content=body, headers=_headers(body))

        assert response.status_code == 200
        rendered = _rendered_log_calls(mock_logger)
        assert rendered, "expected the handler to log the accepted delivery"
        assert _PARENT_EMAIL not in rendered
        assert "example.com" not in rendered

    @pytest.mark.unit
    def test_accepted_delivery_records_the_environment(
        self, client: TestClient
    ) -> None:
        """Which environment answered is the one fact no later reader can re-derive."""
        body = _body()

        with patch("cyo_adventure.api.kws_webhook.logger") as mock_logger:
            client.post(_URL, content=body, headers=_headers(body))

        rendered = _rendered_log_calls(mock_logger)
        assert "kws_parent_verified" in rendered
        assert "tx-1" in rendered

    @pytest.mark.unit
    def test_rejection_body_does_not_name_the_failed_check(
        self, client: TestClient
    ) -> None:
        """The 401 body must not tell a poster which check they failed.

        Otherwise the endpoint is an oracle: probe once to learn the header
        format is right, again to learn the key is wrong.
        """
        body = _body()
        stale = client.post(
            _URL, content=body, headers=_headers(body, at=int(time.time()) - 3600)
        )
        wrong_key = client.post(
            _URL, content=body, headers=_headers(body, secret="another-secret")
        )

        assert stale.status_code == wrong_key.status_code == 401
        assert stale.json() == wrong_key.json()

    @pytest.mark.unit
    def test_rejection_reason_still_reaches_telemetry(self, client: TestClient) -> None:
        """The other half of the contract above.

        Withholding the reason from the caller is only correct if we keep it
        ourselves; otherwise the fix for the disclosure would be indistinguish-
        able from deleting the signal.
        """
        body = _body()

        with patch("cyo_adventure.api.kws_webhook.logger") as mock_logger:
            client.post(
                _URL, content=body, headers=_headers(body, secret="another-secret")
            )

        rendered = _rendered_log_calls(mock_logger)
        assert "kws_webhook_rejected" in rendered
        assert "no_matching_signature" in rendered

    @pytest.mark.unit
    def test_stale_rejection_carries_the_measured_skew_to_telemetry(
        self, client: TestClient
    ) -> None:
        """A stale rejection is only actionable if the numbers survive the hop.

        The verifier measures the skew, but the handler deliberately drops the
        verifier's ``details`` before the error is serialised, so the
        measurement is one careless filter away from being discarded on our
        side of the boundary rather than the caller's. That is what this pins.
        """
        body = _body()
        sent_at = int(time.time()) - 3600

        with patch("cyo_adventure.api.kws_webhook.logger") as mock_logger:
            client.post(_URL, content=body, headers=_headers(body, at=sent_at))

        logged = mock_logger.warning.call_args.kwargs
        assert logged["reason"] == "timestamp_outside_window"
        # Echoed verbatim from the header, so this is exact rather than
        # approximate: it is the number that distinguishes a stale delivery
        # from a sender emitting milliseconds.
        assert logged["signature_timestamp"] == sent_at
        # The wall clock advances between the send above and the check inside
        # the handler, so only the magnitude is stable. The sign is the part
        # that carries meaning, and it is exact.
        assert logged["skew_seconds"] >= 3600

    @pytest.mark.unit
    def test_skew_diagnostics_do_not_change_the_rejection_body(
        self, client: TestClient
    ) -> None:
        """Adding telemetry must not reopen the oracle the 401 body closes.

        ``test_rejection_body_does_not_name_the_failed_check`` above compares a
        stale delivery against a wrong-key one. This compares two STALE
        deliveries whose diagnostics differ, since those now flow through a
        code path the older test never exercises: identical bodies here mean
        the new fields stayed server-side.
        """
        body = _body()
        recent = client.post(
            _URL, content=body, headers=_headers(body, at=int(time.time()) - 400)
        )
        ancient = client.post(
            _URL, content=body, headers=_headers(body, at=int(time.time()) - 999_999)
        )

        assert recent.status_code == ancient.status_code == 401
        assert recent.json() == ancient.json()


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


class TestSchemaExposure:
    """The webhook stays out of the generated client's contract."""

    @pytest.mark.unit
    def test_route_absent_from_the_openapi_schema(self) -> None:
        """include_in_schema=False, so the committed frontend client never churns.

        A browser has no reason to call this route, and the contract-drift CI
        job compares generated files: putting a machine-to-machine webhook in
        the schema would mean regenerating the client for an endpoint no user
        agent will ever hit.
        """
        schema = create_app().openapi()

        assert _URL not in schema["paths"]
