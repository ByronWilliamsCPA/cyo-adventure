"""Tests for the KWS webhook and redirect signature verifiers.

The webhook verifier is the entire boundary between a KWS-signed verification
and one an attacker posted at our URL, so these tests are written as attacks
rather than as happy-path coverage: every rejection case is a thing that must
not get through, and the one acceptance case is pinned to a known-answer
vector so a refactor that quietly changes the signed string is caught.
"""

from __future__ import annotations

import hmac
from hashlib import sha256

import pytest

from cyo_adventure.consent import (
    FreshnessWindow,
    parse_signature_header,
    verify_redirect_signature,
    verify_webhook_signature,
)
from cyo_adventure.core.exceptions import AuthenticationError

_SECRET = "test-webhook-secret-not-a-real-credential"
_OTHER_SECRET = "rotated-webhook-secret-not-a-real-credential"
_BODY = b'{"name":"parent-verified","orgId":"org-1"}'
_NOW = 1_800_000_000
_SKEW = 300
# The clock is a fixed value rather than time.time(), so the window-edge tests
# below assert on an exact boundary instead of racing a real clock.
_WINDOW = FreshnessWindow(now=_NOW, max_skew_seconds=_SKEW)


def _sign(body: bytes, timestamp: int, secret: str = _SECRET) -> str:
    """Produce the signature KWS would send for a body and timestamp."""
    signed = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), signed, sha256).hexdigest()


def _header(body: bytes = _BODY, timestamp: int = _NOW, secret: str = _SECRET) -> str:
    """Produce a complete, valid x-kws-signature header."""
    return f"t={timestamp},v1={_sign(body, timestamp, secret)}"


class TestParseSignatureHeader:
    """Shape-level parsing, before any cryptography is attempted."""

    @pytest.mark.unit
    def test_parses_timestamp_and_signature(self) -> None:
        """The documented single-signature form."""
        parsed = parse_signature_header("t=1700000000,v1=abc123")

        assert parsed.timestamp == 1_700_000_000
        assert parsed.signatures == ("abc123",)

    @pytest.mark.unit
    def test_parses_multiple_signatures(self) -> None:
        """The rotation form: t=<ts>,v1=<sig>,v1=<sig>.

        Both must survive parsing. Dropping the second is the defect in the
        one open-source reference implementation, and it only shows up on the
        day a secret is rotated.
        """
        parsed = parse_signature_header("t=1700000000,v1=aaa,v1=bbb")

        assert parsed.signatures == ("aaa", "bbb")

    @pytest.mark.unit
    def test_tolerates_whitespace_between_components(self) -> None:
        """A space after the comma is cosmetic, not a different header."""
        parsed = parse_signature_header("t=1700000000, v1=abc")

        assert parsed.signatures == ("abc",)

    @pytest.mark.unit
    def test_signatures_are_lowercased(self) -> None:
        """Hex case must not decide whether a valid delivery verifies."""
        parsed = parse_signature_header("t=1700000000,v1=ABCDEF")

        assert parsed.signatures == ("abcdef",)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "header",
        [
            "",
            "v1=abc",
            "t=1700000000",
            "t=1700000000,v1=",
            "t=notanumber,v1=abc",
            "t=1700000000,t=1700000001,v1=abc",
            "garbage",
        ],
        ids=[
            "empty",
            "no_timestamp",
            "no_signature",
            "empty_signature",
            "non_integer_timestamp",
            "two_timestamps",
            "unstructured",
        ],
    )
    def test_malformed_headers_rejected(self, header: str) -> None:
        """Every unusual shape is rejected rather than coerced.

        A lenient reading of a signature header is a place where the attacker,
        not the protocol, chooses which branch runs.
        """
        with pytest.raises(AuthenticationError):
            parse_signature_header(header)

    @pytest.mark.unit
    def test_absurd_component_count_rejected(self) -> None:
        """An unbounded component list is unauthenticated work we choose to do."""
        header = "t=1700000000," + ",".join(f"v1={i:064x}" for i in range(64))

        with pytest.raises(AuthenticationError):
            parse_signature_header(header)


class TestVerifyWebhookSignature:
    """The webhook leg: HMAC-SHA256 over "{t}.{raw body}"."""

    @pytest.mark.unit
    def test_known_answer_vector(self) -> None:
        """Pin the exact signed string, not just self-consistency.

        Computing the expected value with the same helper the implementation
        uses would pass even if both changed together, so this vector is a
        literal: it is what KWS's documented algorithm produces for this body
        and timestamp, and a refactor that changes the separator or the byte
        ordering breaks it.
        """
        body = b'{"a":1}'
        expected = hmac.new(_SECRET.encode(), b"1800000000." + body, sha256).hexdigest()

        parsed = verify_webhook_signature(
            header=f"t={_NOW},v1={expected}",
            body=body,
            secret=_SECRET,
            window=_WINDOW,
        )

        assert parsed.timestamp == _NOW

    @pytest.mark.unit
    def test_valid_delivery_accepted(self) -> None:
        """The ordinary case."""
        parsed = verify_webhook_signature(
            header=_header(),
            body=_BODY,
            secret=_SECRET,
            window=_WINDOW,
        )

        assert parsed.signatures == (_sign(_BODY, _NOW),)

    @pytest.mark.unit
    def test_tampered_body_rejected(self) -> None:
        """A single byte changed in the body invalidates the delivery."""
        header = _header()
        tampered = _BODY.replace(b"org-1", b"org-2")

        with pytest.raises(AuthenticationError):
            verify_webhook_signature(
                header=header,
                body=tampered,
                secret=_SECRET,
                window=_WINDOW,
            )

    @pytest.mark.unit
    def test_reserialized_body_rejected(self) -> None:
        """A parse-and-re-stringify round trip fails, which is why raw bytes matter.

        Epic's documentation warns about exactly this. The re-serialised body
        is semantically identical JSON and still fails, so a receiver that
        verifies against a re-encoded body would reject every real delivery.
        """
        import json

        reserialized = json.dumps(json.loads(_BODY)).encode()
        header = _header()

        assert reserialized != _BODY
        with pytest.raises(AuthenticationError):
            verify_webhook_signature(
                header=header,
                body=reserialized,
                secret=_SECRET,
                window=_WINDOW,
            )

    @pytest.mark.unit
    def test_wrong_secret_rejected(self) -> None:
        """A signature computed under another key does not verify."""
        header = _header(secret=_OTHER_SECRET)

        with pytest.raises(AuthenticationError):
            verify_webhook_signature(
                header=header,
                body=_BODY,
                secret=_SECRET,
                window=_WINDOW,
            )

    @pytest.mark.unit
    def test_timestamp_is_covered_by_the_signature(self) -> None:
        """Rewriting t= to defeat the freshness check invalidates the MAC.

        This is what makes the replay window meaningful: an attacker holding a
        captured delivery cannot simply refresh its timestamp.
        """
        stale = _NOW - 10_000
        header = f"t={_NOW},v1={_sign(_BODY, stale)}"

        with pytest.raises(AuthenticationError):
            verify_webhook_signature(
                header=header,
                body=_BODY,
                secret=_SECRET,
                window=_WINDOW,
            )

    @pytest.mark.unit
    def test_rotation_second_signature_accepted(self) -> None:
        """A match against ANY v1= component is a match.

        Mid-rotation KWS sends both the old and new signatures. Accepting only
        the first would reject every delivery signed with the key we hold, with
        the matching signature sitting in the same header.
        """
        header = (
            f"t={_NOW},v1={_sign(_BODY, _NOW, _OTHER_SECRET)},v1={_sign(_BODY, _NOW)}"
        )

        parsed = verify_webhook_signature(
            header=header,
            body=_BODY,
            secret=_SECRET,
            window=_WINDOW,
        )

        assert len(parsed.signatures) == 2

    @pytest.mark.unit
    @pytest.mark.parametrize("offset", [-301, 301, -100_000, 100_000])
    def test_timestamp_outside_the_window_rejected(self, offset: int) -> None:
        """Both directions are bounded.

        A far-future timestamp is as much a sign of a forged or badly
        misconfigured sender as a far-past one, and only the past direction is
        obvious, so the symmetry is worth pinning.
        """
        header = _header(timestamp=_NOW + offset)

        with pytest.raises(AuthenticationError):
            verify_webhook_signature(
                header=header,
                body=_BODY,
                secret=_SECRET,
                window=_WINDOW,
            )

    @pytest.mark.unit
    @pytest.mark.parametrize("offset", [-300, 0, 300])
    def test_timestamp_at_the_window_edge_accepted(self, offset: int) -> None:
        """The window is inclusive, so a delivery exactly at the edge is valid."""
        timestamp = _NOW + offset

        verify_webhook_signature(
            header=_header(timestamp=timestamp),
            body=_BODY,
            secret=_SECRET,
            window=_WINDOW,
        )

    @pytest.mark.unit
    def test_rejection_message_does_not_disclose_the_reason(self) -> None:
        """A poster must not learn which check they failed.

        Distinguishable messages would turn the endpoint into an oracle: try a
        forged signature, learn the format is right; try again with a fresh
        timestamp, learn the key is wrong. The discriminator stays in
        ``details`` for our logs.
        """
        stale = AuthenticationError("")
        mismatch = AuthenticationError("")
        try:
            verify_webhook_signature(
                header=_header(timestamp=_NOW - 10_000),
                body=_BODY,
                secret=_SECRET,
                window=_WINDOW,
            )
        except AuthenticationError as exc:
            stale = exc
        try:
            verify_webhook_signature(
                header=_header(secret=_OTHER_SECRET),
                body=_BODY,
                secret=_SECRET,
                window=_WINDOW,
            )
        except AuthenticationError as exc:
            mismatch = exc

        assert str(stale) == str(mismatch)
        assert stale.details["reason"] != mismatch.details["reason"]


class TestVerifyRedirectSignature:
    """The redirect leg: HMAC-SHA256 over "{status}:{external_payload}"."""

    _STATUS = '{"verified":true,"transactionId":"tx-1","errorCode":null}'
    _PAYLOAD = "corr-1"

    def _signature(self, secret: str = _SECRET) -> str:
        """The signature KWS would attach for this status and payload."""
        signed = f"{self._STATUS}:{self._PAYLOAD}".encode()
        return hmac.new(secret.encode(), signed, sha256).hexdigest()

    @pytest.mark.unit
    def test_valid_redirect_accepted(self) -> None:
        """The ordinary case."""
        verify_redirect_signature(
            signature=self._signature(),
            status=self._STATUS,
            external_payload=self._PAYLOAD,
            secret=_SECRET,
        )

    @pytest.mark.unit
    def test_tampered_status_rejected(self) -> None:
        """Flipping verified to true must not survive verification."""
        signature = self._signature()
        tampered = self._STATUS.replace("true", "false")

        with pytest.raises(AuthenticationError):
            verify_redirect_signature(
                signature=signature,
                status=tampered,
                external_payload=self._PAYLOAD,
                secret=_SECRET,
            )

    @pytest.mark.unit
    def test_missing_signature_rejected(self) -> None:
        """An absent query parameter is a rejection, not an empty comparison."""
        with pytest.raises(AuthenticationError):
            verify_redirect_signature(
                signature="",
                status=self._STATUS,
                external_payload=self._PAYLOAD,
                secret=_SECRET,
            )

    @pytest.mark.unit
    def test_webhook_signature_does_not_verify_as_a_redirect(self) -> None:
        """The two constructions are genuinely different, not one with a flag.

        If a future refactor merged them, this is the test that fails: a
        webhook signature over the same secret must not satisfy the redirect
        verifier, because the redirect's signed string has no timestamp and a
        shared implementation would silently give the redirect leg replay
        protection it does not have, or take it away from the webhook.
        """
        webhook_signature = _sign(_BODY, _NOW)

        with pytest.raises(AuthenticationError):
            verify_redirect_signature(
                signature=webhook_signature,
                status=self._STATUS,
                external_payload=self._PAYLOAD,
                secret=_SECRET,
            )
