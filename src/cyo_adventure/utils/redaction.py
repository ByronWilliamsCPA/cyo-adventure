"""Reusable log redaction helpers and the structlog censoring processor.

Three complements to the per-call-site discipline of never passing a secret to
a logger:

* :func:`censor_sensitive_processor` is a structlog processor installed by
  :func:`cyo_adventure.utils.logging.setup_logging` immediately before the
  renderer. It is the structural backstop: a call site that forgets the rule
  gets its value replaced with :data:`REDACTED` instead of publishing it.
* :class:`RedactingLogFilter` carries the same value-shape rules onto the root
  stdlib-logging handler, because the processor above only ever sees records
  that originate in structlog (see "Scope" below).
* :func:`digest_identifier` gives a call site that legitimately needs to
  correlate occurrences of a secret-bearing value (an R2 object key, an auth
  subject) a stable, non-reversible stand-in it can log safely.

Scope
-----
``censor_sensitive_processor`` runs inside structlog's processor chain, so it
covers structlog-originated records only. Records emitted through plain stdlib
``logging`` (``uvicorn.access``, which renders the full request line including
its query string; ``botocore``/``boto3``; SQLAlchemy; ``rq``) never enter that
chain. :class:`RedactingLogFilter` closes that gap for the value shapes it can
recognise by attaching to the root handler ``setup_logging`` installs; it
cannot apply the field-name deny list, because a stdlib record has no
structured fields to match names against.

Coverage limits worth stating outright, because a backstop that is believed to
cover more than it does is worse than no backstop:

* The deny list is a deny list. It protects only the field names and value
  shapes enumerated below.
* A bare ``key=`` field name is INTENTIONALLY not on the deny list: this
  codebase logs ordinary ``*_key`` domain fields (a dict key, a cache key, a
  skeleton key) far more often than secret-bearing ones, and a substring rule
  on ``key`` would redact them all. The two secret-bearing spellings that do
  exist (``object_key``, ``cover_key``) are named exactly, and the R2
  object-key VALUE shape is matched independently of its field name, so a
  newly-invented ``*_key`` spelling still gets caught by shape.
* The message channel (structlog's ``event``, a stdlib record's formatted
  message) is matched by value SHAPE only, never by name; a credential with no
  recognisable shape (an opaque, non-JWT token interpolated into an f-string)
  is not reachable by any rule here. Supabase access tokens are JWTs, so the
  realistic case in this codebase is covered.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import MutableMapping

__all__ = [
    "REDACTED",
    "RedactingLogFilter",
    "censor_sensitive_processor",
    "digest_identifier",
    "is_sensitive_key",
    "redact_credential_substrings",
]

REDACTED = "[redacted]"

_DIGEST_LENGTH = 12

# Substring matches against the lowercased field name. Chosen to be specific
# enough that ordinary domain fields do not collide: the bare words "key" and
# "auth" are deliberately absent from THIS tuple (the codebase logs `key=` and
# `authored_by=`-style fields), and the short ambiguous names live in
# _SENSITIVE_EXACT_NAMES below where only a whole-name match counts. Note that
# "authorization" IS a substring rule here, so an `authorization_status=` field
# would be redacted, not preserved; that field does not exist in this codebase
# today, and if one is ever wanted it should be named so it does not read as a
# header.
_SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "access_key",
    "api_key",
    "apikey",
    "authorization",
    "connection_string",
    "credential",
    "database_url",
    "encryption_key",
    "passphrase",
    "passwd",
    "password",
    "private_key",
    "publishable_key",
    "salt",
    "secret",
    "service_role_key",
    "session_key",
    "signing_key",
    "token",
)

# Whole-name matches only: each of these is short enough that a substring rule
# would swallow unrelated fields ("pin" in "spinner", "dsn" in a slug), or is
# a `*_key` spelling that the deliberately-absent bare "key" rule cannot reach
# (`object_key`/`cover_key` both name an R2 object key, which embeds the
# per-cover salt; see covers/storage.py::_key_log_fields).
_SENSITIVE_EXACT_NAMES: frozenset[str] = frozenset(
    {
        "auth",
        "bearer",
        "cookie",
        "cover_key",
        "dsn",
        "jwt",
        "object_key",
        "pin",
        "pwd",
        "set_cookie",
    }
)

# The log message key. It is matched by value shape but never by field name:
# name matching would erase the event name of anything called
# "token_refresh_failed", while shape matching leaves that name alone and
# still catches a secret interpolated into the message text.
_EVENT_KEY = "event"

# A `{"field": <name>, "value": <the caller's input>}` descriptor pair, as
# produced by core/exceptions.py::ValidationError and logged nested under
# `details=` by app.py::_handle_project_error. The value is only as sensitive
# as the field it describes, so it is judged by the field's NAME.
_DESCRIPTOR_NAME_KEY = "field"
_DESCRIPTOR_VALUE_KEY = "value"

# Credential-shaped VALUES under otherwise benign field names. Each pattern is
# guarded by a cheap literal pre-check in _is_credential_shaped so the regex
# only runs on the small fraction of strings that could possibly match.
_BEARER_PREFIX = "bearer "
_JWT_RE = re.compile(r"^ey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*$")
_URL_CREDENTIALS_RE = re.compile(r"://[^/\s:@]+:[^/\s@]+@")
# AWS SigV4 query-string credentials. covers/storage.py::
# generate_presigned_cover_url mints exactly this shape, so a debug log of one
# would publish a working time-limited GET credential for a child's cover.
_AWS_SIGV4_RE = re.compile(r"X-Amz-(?:Signature|Credential)=", re.IGNORECASE)
_AWS_SIGV4_MARKER = "x-amz-"
# An R2 cover object key: `<storybook_id>/<version>-<token_hex(16)>.webp`.
# The 32-hex segment is `cover_object_salt`, the unguessability control.
_COVER_KEY_RE = re.compile(r"[A-Za-z0-9_-]+/\d+-[0-9a-f]{32}\.webp")

# Substring rules for the MESSAGE channel and for any string value the
# whole-value rules above did not already replace outright. Applied in order;
# each is anchored on a literal or a fixed-width lookbehind, and none nests a
# quantifier inside another, so matching stays linear in the input length.
_SUBSTRING_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # `Bearer <token>`. The 8-character floor keeps prose such as "missing
    # bearer token" from being swallowed.
    (re.compile(r"[Bb]earer\s+[A-Za-z0-9._~+/=-]{8,}"), REDACTED),
    (re.compile(r"ey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"), REDACTED),
    # Only the `user:password` userinfo, so the surrounding URL still tells an
    # operator which host failed.
    (re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"), REDACTED),
    (
        re.compile(r"(X-Amz-(?:Signature|Credential))=[^&\s]+", re.IGNORECASE),
        r"\1=" + REDACTED,
    ),
    (_COVER_KEY_RE, REDACTED),
)

# Bytes values are decoded before shape matching, but only up to this many
# bytes: an image or model payload logged by accident must not cost a
# full-length decode on every log call.
_MAX_BYTES_SCANNED = 4096


def digest_identifier(value: str, *, length: int = _DIGEST_LENGTH) -> str:
    """Return a short, stable, non-reversible digest of ``value``.

    For call sites that must correlate occurrences of a secret-bearing value
    across log lines (the same R2 object key failing to delete twice, the same
    auth subject opening two streams) without publishing the value itself.

    # #CRITICAL: security: this is an UNSALTED digest, so it is only
    # non-reversible for high-entropy inputs (a ``secrets.token_hex(16)``
    # salt, an opaque bearer token, a UUID subject). Do NOT pass a
    # low-cardinality value such as an email address, a PIN, or a
    # child's name: those are brute-forceable from the digest alone.
    # #VERIFY: every call site passes an opaque high-entropy identifier;
    # tests/unit/test_log_redaction.py::TestDigestIdentifier::
    # test_digest_matches_a_pinned_sha256_prefix pins the ALGORITHM against a
    # precomputed SHA-256 value, so a refactor to any reversible encoding
    # (a truncation, a base64) fails. Stability and non-containment alone do
    # not pin it: a `value[:length]` prefix satisfies both.

    Args:
        value: The value to digest. Encoded as UTF-8 before hashing.
        length: Number of leading hex characters to keep. Defaults to 12,
            which is 48 bits: enough to make an accidental collision between
            two live object keys implausible while staying readable in a log
            line.

    Returns:
        str: The leading ``length`` hex characters of the SHA-256 digest.

    Example:
        >>> digest_identifier("s1/2-abc.webp") == digest_identifier("s1/2-abc.webp")
        True
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def is_sensitive_key(name: str) -> bool:
    """Whether a structured-log field name is on the sensitive deny list.

    Args:
        name: The field name as passed to the logger (any casing).

    Returns:
        bool: True when the field's value must be redacted.
    """
    lowered = name.lower()
    if lowered in _SENSITIVE_EXACT_NAMES:
        return True
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_SUBSTRINGS)


def _is_credential_shaped(value: str) -> bool:
    """Whether a string looks like a credential regardless of its field name.

    Args:
        value: The candidate string value.

    Returns:
        bool: True for a ``Bearer <token>`` header value, a three-segment
        JWT, a URL with an embedded ``user:password@`` pair, an AWS SigV4
        presigned URL, or an R2 cover object key carrying its salt.
    """
    if value[:7].lower() == _BEARER_PREFIX:
        return True
    if value.startswith("ey") and _JWT_RE.match(value) is not None:
        return True
    if "@" in value and _URL_CREDENTIALS_RE.search(value) is not None:
        return True
    if _AWS_SIGV4_MARKER in value.lower() and _AWS_SIGV4_RE.search(value) is not None:
        return True
    return value.endswith(".webp") and _COVER_KEY_RE.fullmatch(value) is not None


def redact_credential_substrings(text: str) -> tuple[str, bool]:
    """Replace credential-shaped SUBSTRINGS of ``text`` with :data:`REDACTED`.

    Used for the channels that carry prose rather than a single value (a
    structlog ``event`` message, a stdlib record's formatted message), where
    replacing the whole string would destroy the diagnostic text wrapped
    around the secret.

    Args:
        text: The message or value to scan.

    Returns:
        tuple[str, bool]: The (possibly rewritten) text, and whether any
        substitution was made.
    """
    changed = False
    for pattern, replacement in _SUBSTRING_REDACTIONS:
        text, count = pattern.subn(replacement, text)
        changed = changed or count > 0
    return text, changed


def _decoded_for_scanning(value: bytes | bytearray) -> str | None:
    """Decode a bytes value for shape matching, or None if it is too large.

    Args:
        value: The raw bytes logged under some field name.

    Returns:
        str | None: A lossy UTF-8 decode, or None when the payload exceeds
        :data:`_MAX_BYTES_SCANNED`.
    """
    if len(value) > _MAX_BYTES_SCANNED:
        return None
    return bytes(value).decode("utf-8", errors="replace")


def _censored_value(name: str, value: object) -> object:
    """Return ``value`` censored according to its field ``name`` and shape.

    Applies the name deny list first (which redacts a value of any type,
    including a container), then whole-value shape matching, then substring
    matching for anything the first two left intact.

    Args:
        name: The structured-log field name the value was logged under.
        value: The value as passed to the logger.

    Returns:
        object: :data:`REDACTED`, a rewritten string, or ``value`` unchanged.
    """
    if is_sensitive_key(name):
        return REDACTED
    text: str | None = None
    if isinstance(value, str):
        text = value
    elif isinstance(value, bytes | bytearray):
        text = _decoded_for_scanning(value)
    if not text:
        return value
    if _is_credential_shaped(text):
        return REDACTED
    if isinstance(value, str):
        rewritten, changed = redact_credential_substrings(text)
        return rewritten if changed else value
    # A bytes payload is not rewritten piecemeal: a partial replacement would
    # hand a caller back a string where it logged bytes. Redact it whole.
    _, changed = redact_credential_substrings(text)
    return REDACTED if changed else value


def _censored_nested(value: object) -> object:
    """Censor one level inside a logged mapping, without recursing further.

    Args:
        value: A candidate nested value from the event dict.

    Returns:
        object: A censored shallow copy when ``value`` is a mapping, else
        ``value`` unchanged.
    """
    if not isinstance(value, dict):
        return value
    nested = cast("dict[object, object]", value)
    censored: dict[object, object] = {
        key: (_censored_value(key, inner) if isinstance(key, str) else inner)
        for key, inner in nested.items()
    }
    _redact_descriptor_pair(censored)
    return censored


def _redact_descriptor_pair(mapping: MutableMapping[object, object]) -> None:
    """Redact a ``value`` entry whose sibling ``field`` entry names a secret.

    ``ValidationError(field="pin", value=<the PIN>)`` puts the caller's raw
    input under the generic name ``value``, which no name rule can judge on
    its own; the sibling ``field`` entry is what says whether it is secret.

    Args:
        mapping: A censored shallow copy of a logged mapping, mutated in
            place.
    """
    described = mapping.get(_DESCRIPTOR_NAME_KEY)
    if (
        isinstance(described, str)
        and _DESCRIPTOR_VALUE_KEY in mapping
        and is_sensitive_key(described)
    ):
        mapping[_DESCRIPTOR_VALUE_KEY] = REDACTED


def censor_sensitive_processor(
    _logger: object,
    _method_name: str,
    event_dict: MutableMapping[str, object],
) -> MutableMapping[str, object]:
    """Redact deny-listed field names and credential-shaped values in place.

    structlog's own ``EventDict``/``WrappedLogger`` aliases resolve to ``Any``,
    which this project's BasedPyright profile flags. The structurally
    equivalent ``object``-valued signature below stays assignable to
    ``structlog.types.Processor`` (``Any`` is bidirectionally compatible)
    without importing ``Any`` into a strict module.

    Installed immediately before the renderer by
    :func:`cyo_adventure.utils.logging.setup_logging`, so it covers every
    downstream renderer (JSON and console alike) and every field any earlier
    processor added.

    The ``event`` message is scanned by value SHAPE only, never by field name.
    Name matching there would erase the event name of anything called
    ``token_refresh_failed``; shape matching leaves that name alone while
    catching a secret that a call site interpolated into the message, which
    ``PositionalArgumentsFormatter`` (chain index 3) has already spliced in by
    the time this processor runs.

    # #CRITICAL: security: this is a DENY list, so it protects only against
    # the field names and value shapes enumerated in this module. It reduces
    # the blast radius of a forgotten projection; it does not make logging a
    # secret safe. Call sites remain responsible for logging non-secret
    # identifiers (see covers/storage.py and api/notifications.py, which
    # project a digest_identifier rather than the raw value).
    # #VERIFY: tests/unit/test_log_redaction.py covers name matching, whole-
    # value and substring shape matching, the message channel, the nested
    # level, and the benign pass-through; extend the lists there when a new
    # secret-bearing field name appears.

    # #EDGE: data integrity: scanning stops ONE level below the event dict.
    # A mapping logged as a field value is censored entry by entry (this is
    # what reaches `details=` in app.py::_handle_project_error, which logs
    # core/exceptions.py's `{"field": ..., "value": <caller input>}`
    # descriptor for a ValidationError), but a mapping nested inside THAT is
    # not, and no non-mapping container (list, dataclass, model) is entered
    # at any depth. Unbounded recursion would put unbounded work on every
    # log call.
    # #VERIFY: tests/unit/test_log_redaction.py::TestNestedValues pins the
    # one-level guarantee AND the two-levels-down gap, and
    # ::test_a_container_under_a_sensitive_name_is_redacted_whole pins that a
    # sensitive TOP-LEVEL name redacts its container outright.

    Args:
        _logger: The wrapped logger (unused; part of the processor contract).
        _method_name: The log method name (unused).
        event_dict: The event dictionary to censor.

    Returns:
        MutableMapping[str, object]: The same dictionary, mutated in place.
    """
    for name, value in event_dict.items():
        # A number or a boolean cannot itself be credential material, and this
        # codebase logs LLM token counts (`max_tokens`, `content_token_count`)
        # and `has_pin`-style flags whose names brush the deny list. Exempting
        # them keeps real observability without weakening the guarantee.
        if value is None or isinstance(value, bool | int | float):
            continue
        if name == _EVENT_KEY:
            if isinstance(value, str):
                rewritten, changed = redact_credential_substrings(value)
                if changed:
                    event_dict[name] = rewritten
            continue
        censored = _censored_value(name, value)
        event_dict[name] = _censored_nested(censored) if censored is value else censored
    _redact_descriptor_pair(cast("MutableMapping[object, object]", event_dict))
    return event_dict


class RedactingLogFilter(logging.Filter):
    """Apply the value-shape rules to records that bypass structlog.

    ``censor_sensitive_processor`` only sees records that originate in
    structlog. Everything logged through plain stdlib ``logging`` reaches the
    root handler without passing through any processor: ``uvicorn.access``
    (whose message is the full request line, query string included),
    ``botocore``/``boto3``, SQLAlchemy, and ``rq``. This filter is attached to
    the handler ``setup_logging`` installs so those records get the same
    shape-based treatment.

    Only shape rules apply here. A stdlib record has no structured fields, so
    the field-name deny list has nothing to match against.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Rewrite the record's message in place when it carries a credential.

        # #CRITICAL: security: a filter that raises is a filter that drops the
        # record, so a malformed %-format pair must not become log loss. Both
        # failure modes of ``getMessage`` (a mismatched format string, a
        # non-formattable argument) are caught and the record passes through
        # untouched, exactly as it would have without this filter. The
        # ``else`` branch, rather than an early return from the handler, is
        # what keeps that pass-through on the same single exit as the success
        # path: ``logging.Filter.filter`` has one honest answer here, and two
        # ``return True`` statements only invited a reader (and SonarCloud's
        # S3516) to hunt for the falsy path that does not exist.
        # #VERIFY: tests/unit/test_log_redaction.py::TestRedactingLogFilter::
        # test_a_record_whose_message_cannot_be_formatted_still_passes.

        Args:
            record: The record about to be emitted by the handler.

        Returns:
            bool: Always True; this filter censors, it never suppresses.
        """
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            pass
        else:
            rewritten, changed = redact_credential_substrings(message)
            if changed:
                record.msg = rewritten
                record.args = None
        return True
