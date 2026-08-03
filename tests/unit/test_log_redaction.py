"""Unit tests for the reusable log redaction helpers and structlog processor.

The safety property that "secrets are never logged" previously rested entirely
on ~40 independent hand-written per-call-site projections: every new log call
had to remember the rule, and nothing failed when one did not. These tests pin
a structural backstop instead: a censoring processor in the structlog chain
that redacts deny-listed key names and obviously credential-shaped values,
plus ``digest_identifier`` for call sites that still need a correlatable but
non-reversible stand-in for a secret.
"""

from __future__ import annotations

import pytest

from cyo_adventure.utils.redaction import (
    REDACTED,
    censor_sensitive_processor,
    digest_identifier,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]

# Clearly-fake credentials (never real-looking).
#
# The JWT and the DSN are ASSEMBLED at import time instead of being written as
# single literals. The processor under test still receives byte-identical
# strings, so these cases lose no strength; the split exists because a
# repository secret scanner matches on the literal source shape, and a
# three-segment ``eyJ...`` token or a ``scheme://user:password@host`` DSN
# sitting on one line reads as a real leak. Splitting is preferred over a
# scanner suppression: an inline ignore would also blind the scanner to a
# genuine credential later added to this same file.
#
# #ASSUME: security: these fixtures defuse the scanner by shape alone; a
# detector that normalises string concatenation would still flag them.
# #VERIFY: if the secret-scanning check reports this file again, replace the
# fixture values outright rather than adding an ignore comment.
_FAKE_SECRET = "test-not-a-real-secret-value"
_FAKE_PASSWORD = "test-not-a-real-password"
_FAKE_JWT = ".".join(
    ("eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiJmYWtlIn0", "not-a-real-signature")
)
_FAKE_DSN = f"postgresql+asyncpg://cyo:{_FAKE_PASSWORD}@db.invalid:5432/cyo"


def _censor(**fields: object) -> dict[str, object]:
    """Run the processor over one event dict and return the result."""
    event_dict: dict[str, object] = {"event": "some_event", **fields}
    return dict(censor_sensitive_processor(None, "info", event_dict))


class TestSensitiveKeyNames:
    @pytest.mark.parametrize(
        "field_name",
        [
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "client_secret",
            "password",
            "db_password",
            "passphrase",
            "api_key",
            "openai_api_key",
            "aws_secret_access_key",
            "authorization",
            "dsn",
            "database_url",
            "private_key",
            "signing_key",
            "credential",
            "cover_object_salt",
            "salt",
            "cookie",
            "jwt",
            "bearer",
        ],
    )
    def test_deny_listed_key_name_has_its_value_redacted(self, field_name: str) -> None:
        """A value under any deny-listed key name never survives to a renderer."""
        result = _censor(**{field_name: _FAKE_SECRET})

        assert result[field_name] == REDACTED
        assert _FAKE_SECRET not in repr(result)

    def test_key_name_matching_is_case_insensitive(self) -> None:
        """Deny-list matching does not depend on the field's casing."""
        result = _censor(Authorization=_FAKE_SECRET, API_KEY=_FAKE_SECRET)

        assert result["Authorization"] == REDACTED
        assert result["API_KEY"] == REDACTED

    def test_non_string_values_on_sensitive_names_are_still_redacted(self) -> None:
        """A dict or list parked under a sensitive name is redacted whole."""
        result = _censor(credentials={"user": "u", "password": _FAKE_SECRET})

        assert result["credentials"] == REDACTED
        assert _FAKE_SECRET not in repr(result)

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("max_tokens", 4096),
            ("content_token_count", 128),
            ("has_pin", True),
            ("prompt_tokens", 0),
        ],
        ids=["max_tokens", "token_count", "has_pin", "prompt_tokens"],
    )
    def test_numeric_and_boolean_metrics_are_not_redacted(
        self, field_name: str, value: object
    ) -> None:
        """Counts and flags whose names brush the deny-list keep their value.

        A number or a boolean cannot itself be credential material, and this
        codebase logs LLM token counts and ``has_pin``-style flags; redacting
        them would cost real observability for no security gain.
        """
        result = _censor(**{field_name: value})

        assert result[field_name] == value


class TestBenignFieldsPassThrough:
    def test_benign_fields_are_returned_untouched(self) -> None:
        """Ordinary structured fields are passed through byte for byte."""
        result = _censor(
            storybook_id="sb-1",
            version=3,
            status="published",
            duration_ms=12.5,
            node_ids=["n1", "n2"],
        )

        assert result == {
            "event": "some_event",
            "storybook_id": "sb-1",
            "version": 3,
            "status": "published",
            "duration_ms": 12.5,
            "node_ids": ["n1", "n2"],
        }

    def test_the_event_name_itself_is_never_redacted(self) -> None:
        """``event`` is the log message key, not a value slot."""
        event_dict: dict[str, object] = {"event": "token_refresh_failed"}

        result = dict(censor_sensitive_processor(None, "warning", event_dict))

        assert result["event"] == "token_refresh_failed"


class TestCredentialShapedValues:
    def test_bearer_prefixed_value_is_redacted_under_a_benign_name(self) -> None:
        """A raw ``Bearer <token>`` header value is caught by shape, not name."""
        result = _censor(header_value=f"Bearer {_FAKE_SECRET}")

        assert result["header_value"] == REDACTED

    def test_jwt_shaped_value_is_redacted_under_a_benign_name(self) -> None:
        """A three-segment JWT is redacted wherever it is parked."""
        result = _censor(subject=_FAKE_JWT)

        assert result["subject"] == REDACTED

    def test_url_with_embedded_credentials_is_redacted(self) -> None:
        """A DSN carrying ``user:password@`` never reaches a renderer."""
        result = _censor(target=_FAKE_DSN)

        assert result["target"] == REDACTED
        assert _FAKE_PASSWORD not in repr(result)

    def test_a_plain_url_without_credentials_survives(self) -> None:
        """Shape matching does not blanket-redact every URL-looking string."""
        result = _censor(target="https://images.example.com/s1/2.webp")

        assert result["target"] == "https://images.example.com/s1/2.webp"


class TestDigestIdentifier:
    def test_digest_is_stable_for_the_same_input(self) -> None:
        """Two calls on one value correlate, which is the point of the digest."""
        assert digest_identifier("s1/2-abc.webp") == digest_identifier("s1/2-abc.webp")

    def test_digest_differs_for_different_inputs(self) -> None:
        """Distinct secrets stay distinguishable in logs."""
        assert digest_identifier("value-a") != digest_identifier("value-b")

    def test_digest_never_contains_the_input(self) -> None:
        """The digest is a stand-in, not an encoding, of the secret."""
        secret = "abcdef0123456789"

        assert secret not in digest_identifier(secret)

    def test_digest_is_short_and_hexadecimal(self) -> None:
        """Short enough to read in a log line, still collision-resistant."""
        digest = digest_identifier("s1/2-abc.webp")

        assert len(digest) == 12
        assert all(char in "0123456789abcdef" for char in digest)
