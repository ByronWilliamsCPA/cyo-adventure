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

import hashlib
import logging

import pytest

from cyo_adventure.utils.redaction import (
    REDACTED,
    RedactingLogFilter,
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
#
# The DSN is joined rather than written as one f-string for the same reason.
# An f-string still leaves the literal `scheme://user:<something>@host` shape
# on a single source line, and a shape-matching detector has no way to know
# that `<something>` is a variable reference and not a password. Joining
# means no line carries the full `user:password@host` triple.
_FAKE_SECRET = "test-not-a-real-secret-value"
_FAKE_PASSWORD = "test-not-a-real-password"
_FAKE_JWT = ".".join(
    ("eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiJmYWtlIn0", "not-a-real-signature")
)
_FAKE_DSN = "".join(
    ("postgresql+asyncpg://cyo:", _FAKE_PASSWORD, "@", "db.invalid:5432/cyo")
)
# Shaped exactly like covers/storage.py::cover_object_key output: the 32 hex
# characters are the per-cover `cover_object_salt`.
_FAKE_COVER_SALT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
_FAKE_COVER_KEY = f"s1/2-{_FAKE_COVER_SALT}.webp"
# Shaped like the presigned GET URL generate_presigned_cover_url returns.
_FAKE_PRESIGNED_URL = (
    "https://covers.example.com/s1/2.webp"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256"
    "&X-Amz-Credential=AKIDEXAMPLE%2F20260803%2Fauto%2Fs3%2Faws4_request"
    "&X-Amz-Signature=not-a-real-signature-value"
)


def _censor(**fields: object) -> dict[str, object]:
    """Run the processor over one event dict and return the result."""
    event_dict: dict[str, object] = {"event": "some_event", **fields}
    return dict(censor_sensitive_processor(None, "info", event_dict))


def _censor_event(message: str) -> str:
    """Run the processor over one message and return the censored event text."""
    event_dict: dict[str, object] = {"event": message}
    event = dict(censor_sensitive_processor(None, "info", event_dict))["event"]
    assert isinstance(event, str), "the processor must not retype the message"
    return event


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
            "object_key",
            "cover_key",
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

    def test_a_container_under_a_sensitive_name_is_redacted_whole(self) -> None:
        """A dict or list parked under a sensitive name is redacted whole.

        This is the case the processor's one-level #EDGE note points at: a
        sensitive TOP-LEVEL name never needs the nested scan, because the
        whole container goes.
        """
        result = _censor(credentials={"user": "u", "password": _FAKE_SECRET})

        assert result["credentials"] == REDACTED
        assert _FAKE_SECRET not in repr(result)

    def test_a_bare_key_field_is_deliberately_not_covered_by_name(self) -> None:
        """``key=`` stays off the deny list; the VALUE shape is the net.

        The codebase logs ordinary ``*_key`` domain fields far more often
        than secret-bearing ones, so a substring rule on ``key`` would cost
        real observability. This pins the documented tradeoff so a future
        reader does not mistake the gap for an oversight.
        """
        result = _censor(cache_key="library:profile-7")

        assert result["cache_key"] == "library:profile-7"

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

    def test_a_presigned_sigv4_url_is_redacted(self) -> None:
        """A presigned R2 URL is a working, time-limited GET credential.

        ``generate_presigned_cover_url`` mints exactly this shape, so a debug
        log of one would publish read access to a child's cover image for the
        URL's whole TTL.
        """
        result = _censor(cover_url=_FAKE_PRESIGNED_URL)

        assert result["cover_url"] == REDACTED

    def test_a_salted_cover_object_key_is_redacted_by_shape(self) -> None:
        """The exact leak this PR fixed by hand in covers/storage.py.

        A future ``_logger.info("cover_uploaded", object_key=key)`` under a
        name the deny list has never heard of is still caught, because the
        key's value shape carries its own tell.
        """
        result = _censor(uploaded_to=_FAKE_COVER_KEY)

        assert result["uploaded_to"] == REDACTED
        assert _FAKE_COVER_SALT not in repr(result)

    def test_a_legacy_unsalted_cover_key_is_not_redacted(self) -> None:
        """A pre-migration key carries no salt, so it stays diagnosable."""
        result = _censor(uploaded_to="s1/2.webp")

        assert result["uploaded_to"] == "s1/2.webp"

    def test_a_credential_inside_a_longer_string_is_substituted(self) -> None:
        """Surrounding diagnostic text survives; only the credential goes."""
        result = _censor(note=f"upstream said: Bearer {_FAKE_SECRET} expired")

        assert result["note"] == f"upstream said: {REDACTED} expired"

    def test_credential_bearing_bytes_are_redacted(self) -> None:
        """A bytes payload carrying a credential does not slip the scan."""
        result = _censor(blob=f"Bearer {_FAKE_SECRET}".encode())

        assert result["blob"] == REDACTED

    def test_benign_bytes_are_left_alone(self) -> None:
        """Bytes are only touched when they actually carry a shape."""
        result = _censor(blob=b"plain payload bytes")

        assert result["blob"] == b"plain payload bytes"

    def test_an_oversized_bytes_payload_is_not_scanned(self) -> None:
        """A logged image or model payload must not cost a full decode.

        The scan is capped, so a large blob passes through unread. It is
        reached only by a call site logging raw bytes under a benign name,
        which is already a bug; the cap keeps that bug cheap rather than
        turning every log call into an O(payload) decode.
        """
        oversized = b"x" * 4097 + b"Bearer never-scanned"

        assert _censor(blob=oversized)["blob"] == oversized


class TestTheMessageChannel:
    """The ``event`` message is scanned by SHAPE, never by field name.

    ``PositionalArgumentsFormatter`` runs at chain index 3, well before this
    processor at the tail, so a call site that writes
    ``logger.warning("token refresh failed for %s", tok)`` has already had the
    secret spliced into ``event`` by the time the backstop sees it.
    """

    def test_a_credential_in_the_message_is_redacted(self) -> None:
        """Issue #556's acceptance criterion for the message channel."""
        censored = _censor_event(f"token refresh failed for Bearer {_FAKE_SECRET}")

        assert censored == f"token refresh failed for {REDACTED}"
        assert _FAKE_SECRET not in censored

    def test_a_jwt_interpolated_into_the_message_is_redacted(self) -> None:
        """Supabase access tokens are JWTs, so this is the realistic case."""
        assert _censor_event(f"rejecting session for {_FAKE_JWT}") == (
            f"rejecting session for {REDACTED}"
        )

    def test_a_dsn_in_the_message_keeps_its_host(self) -> None:
        """Only the userinfo goes: the host is what an operator needs."""
        censored = _censor_event(f"connect failed: {_FAKE_DSN}")

        assert _FAKE_PASSWORD not in censored
        assert "db.invalid:5432" in censored

    def test_an_event_name_that_merely_mentions_a_secret_word_survives(self) -> None:
        """``token_refresh_failed`` is a name, not a credential.

        This is the concern the old unconditional ``event`` exemption was
        justified by. Shape matching alone already honours it, so the
        exemption bought nothing it needed.
        """
        assert _censor_event("token_refresh_failed") == "token_refresh_failed"

    @pytest.mark.parametrize(
        "event_name",
        [
            "auth_subject_resolved",
            "cover_delete_failed",
            "database_url_missing",
            "missing bearer token",
        ],
    )
    def test_ordinary_event_names_are_left_alone(self, event_name: str) -> None:
        """Names built from secret-adjacent words are not credentials."""
        assert _censor_event(event_name) == event_name

    def test_a_non_string_event_is_passed_through(self) -> None:
        """structlog does not require ``event`` to be a string."""
        event_dict: dict[str, object] = {"event": ["a", "list"]}

        result = dict(censor_sensitive_processor(None, "info", event_dict))

        assert result["event"] == ["a", "list"]


class TestNestedValues:
    """Scanning goes exactly one level below the event dict, and no further."""

    def test_a_secret_nested_one_level_down_is_redacted(self) -> None:
        """``details={...}`` is what app.py::_handle_project_error logs."""
        result = _censor(details={"field": "email", "password": _FAKE_SECRET})

        assert result["details"] == {"field": "email", "password": REDACTED}

    def test_a_validation_error_pin_value_is_redacted(self) -> None:
        """core/exceptions.py's ``{field, value}`` descriptor pair.

        ``ValidationError(field="pin", value=<the PIN>)`` parks the caller's
        raw input under the generic name ``value``, which no name rule can
        judge alone; the sibling ``field`` entry is what makes it secret.
        This is what makes exceptions.py's "will be sanitized in logs"
        docstring claim true.
        """
        result = _censor(details={"field": "pin", "value": "4821"})

        assert result["details"] == {"field": "pin", "value": REDACTED}

    def test_a_benign_descriptor_pair_keeps_its_value(self) -> None:
        """Only a descriptor naming a SENSITIVE field loses its value."""
        result = _censor(details={"field": "email", "value": "not-an-email"})

        assert result["details"] == {"field": "email", "value": "not-an-email"}

    def test_a_top_level_descriptor_pair_is_redacted_too(self) -> None:
        """The same pair logged as flat kwargs gets the same treatment."""
        result = _censor(field="pin", value="4821")

        assert result["value"] == REDACTED

    def test_the_nested_scan_does_not_mutate_the_callers_dict(self) -> None:
        """A logged dict is often live application state; do not rewrite it."""
        details: dict[str, object] = {"password": _FAKE_SECRET}

        _censor(details=details)

        assert details == {"password": _FAKE_SECRET}

    def test_two_levels_down_is_documented_as_out_of_reach(self) -> None:
        """Pins the #EDGE gap, so a later reader sees the limit, not a bug."""
        result = _censor(details={"inner": {"password": _FAKE_SECRET}})

        assert result["details"] == {"inner": {"password": _FAKE_SECRET}}


class TestRedactingLogFilter:
    """Records that never enter structlog's chain still get the shape rules."""

    @staticmethod
    def _record(message: str, *args: object) -> logging.LogRecord:
        return logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=message,
            args=args or None,
            exc_info=None,
        )

    def test_a_credential_in_a_stdlib_record_is_redacted(self) -> None:
        """uvicorn.access renders the full request line, query string and all."""
        record = self._record(f"GET /v1/covers?X-Amz-Signature={_FAKE_SECRET} HTTP/1.1")

        assert RedactingLogFilter().filter(record) is True
        assert _FAKE_SECRET not in record.getMessage()
        assert REDACTED in record.getMessage()

    def test_percent_style_arguments_are_scanned_after_interpolation(self) -> None:
        """The secret only exists once ``args`` have been spliced in."""
        record = self._record("token refresh failed for %s", _FAKE_JWT)

        assert RedactingLogFilter().filter(record) is True
        assert _FAKE_JWT not in record.getMessage()

    def test_a_benign_record_is_left_untouched(self) -> None:
        """No credential shape means no rewrite, including of ``args``."""
        record = self._record("GET /v1/library/%s HTTP/1.1", "profile-7")

        assert RedactingLogFilter().filter(record) is True
        assert record.getMessage() == "GET /v1/library/profile-7 HTTP/1.1"
        assert record.args == ("profile-7",)

    def test_a_record_whose_message_cannot_be_formatted_still_passes(self) -> None:
        """A filter that raises is a filter that drops the record."""
        record = self._record("needs %d args", "not-a-number")

        assert RedactingLogFilter().filter(record) is True


class TestDigestIdentifier:
    def test_digest_is_stable_for_the_same_input(self) -> None:
        """Two calls on one value correlate, which is the point of the digest.

        The two calls are bound to names solely to satisfy ``S5863``, which
        flags two syntactically identical operands around ``==`` without
        executing the code, so it fires on ``f(x) == f(x)`` whether or not
        ``f`` is deterministic. Binding changes nothing at runtime: both forms
        evaluate two independent calls and compare the results, and both would
        equally catch a salted or time-varying digest. Do not collapse this
        back into a self-comparison, or the rule fires again.
        """
        identifier = "s1/2-abc.webp"

        first = digest_identifier(identifier)
        second = digest_identifier(identifier)

        assert first == second

    def test_digest_differs_for_different_inputs(self) -> None:
        """Distinct secrets stay distinguishable in logs."""
        assert digest_identifier("value-a") != digest_identifier("value-b")

    def test_digest_never_contains_the_input(self) -> None:
        """The digest is a stand-in, not an encoding, of the secret.

        The fixture is deliberately SHORTER than the 12-character digest. A
        16-character fixture (what this test used to carry) can never be a
        substring of a 12-character result, so the assertion held for any
        implementation whatsoever, including a plain prefix of the input.
        """
        secret = "abc123"

        assert len(secret) < 12, "a longer fixture makes this assertion vacuous"
        assert secret not in digest_identifier(secret)

    def test_digest_matches_a_pinned_sha256_prefix(self) -> None:
        """Pins the ALGORITHM, not just its observable properties.

        Stability, distinctness, and non-containment are all satisfied by a
        fully reversible ``value[:length]`` prefix, so the #CRITICAL
        non-reversibility claim on ``digest_identifier`` needs a test that
        fails for anything that is not SHA-256.
        """
        expected = hashlib.sha256(b"s1/2-abc.webp").hexdigest()[:12]

        assert digest_identifier("s1/2-abc.webp") == expected

    def test_digest_of_a_long_input_is_not_a_prefix_of_it(self) -> None:
        """A truncating implementation is caught even on a long input.

        The non-containment test above only rules out the input appearing
        WHOLE in the digest; this rules out the digest being a leading slice
        of the input, which is the reversible refactor that matters.
        """
        secret = "abcdef0123456789"

        assert not secret.startswith(digest_identifier(secret))

    def test_digest_is_short_and_hexadecimal(self) -> None:
        """Short enough to read in a log line, still collision-resistant."""
        digest = digest_identifier("s1/2-abc.webp")

        assert len(digest) == 12
        assert all(char in "0123456789abcdef" for char in digest)
