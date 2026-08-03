"""Reusable log redaction helpers and the structlog censoring processor.

Two complements to the per-call-site discipline of never passing a secret to a
logger:

* :func:`censor_sensitive_processor` is a structlog processor installed by
  :func:`cyo_adventure.utils.logging.setup_logging` immediately before the
  renderer. It is the structural backstop: a call site that forgets the rule
  gets its value replaced with :data:`REDACTED` instead of publishing it.
* :func:`digest_identifier` gives a call site that legitimately needs to
  correlate occurrences of a secret-bearing value (an R2 object key, an auth
  subject) a stable, non-reversible stand-in it can log safely.

The processor is a backstop, not a licence: call sites must still project
non-secret identifiers themselves. A deny list can only catch what it has been
told to look for.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import MutableMapping

__all__ = [
    "REDACTED",
    "censor_sensitive_processor",
    "digest_identifier",
    "is_sensitive_key",
]

REDACTED = "[redacted]"

_DIGEST_LENGTH = 12

# Substring matches against the lowercased field name. Chosen to be specific
# enough that ordinary domain fields do not collide: the bare words "key" and
# "auth" are deliberately absent (this codebase logs `key=`, `authored_by=`,
# `authorization_status=`-style fields), and the short ambiguous names live in
# _SENSITIVE_EXACT_NAMES below where only a whole-name match counts.
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
# would swallow unrelated fields ("pin" in "spinner", "dsn" in a slug).
_SENSITIVE_EXACT_NAMES: frozenset[str] = frozenset(
    {
        "auth",
        "bearer",
        "cookie",
        "dsn",
        "jwt",
        "pin",
        "pwd",
        "set_cookie",
    }
)

# The log message key, not a value slot: redacting it would erase the event
# name of anything called "token_refresh_failed".
_EVENT_KEY = "event"

# Credential-shaped VALUES under otherwise benign field names. Each pattern is
# guarded by a cheap literal pre-check in _is_credential_shaped so the regex
# only runs on the small fraction of strings that could possibly match.
_BEARER_PREFIX = "bearer "
_JWT_RE = re.compile(r"^ey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*$")
_URL_CREDENTIALS_RE = re.compile(r"://[^/\s:@]+:[^/\s@]+@")


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
    # tests/unit/test_log_redaction.py::TestDigestIdentifier pins stability
    # and that the input never appears in the output.

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
        JWT, or a URL with an embedded ``user:password@`` pair.
    """
    if value[:7].lower() == _BEARER_PREFIX:
        return True
    if value.startswith("ey") and _JWT_RE.match(value) is not None:
        return True
    return "@" in value and _URL_CREDENTIALS_RE.search(value) is not None


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

    # #CRITICAL: security: this is a DENY list, so it protects only against
    # the field names and value shapes enumerated in this module. It reduces
    # the blast radius of a forgotten projection; it does not make logging a
    # secret safe. Call sites remain responsible for logging non-secret
    # identifiers (see covers/storage.py and api/notifications.py, which
    # project a digest_identifier rather than the raw value).
    # #VERIFY: tests/unit/test_log_redaction.py covers both matching modes and
    # the benign pass-through; extend the lists there when a new secret-
    # bearing field name appears.

    # #EDGE: data integrity: only the TOP LEVEL of the event dict is scanned.
    # A secret nested inside a logged dict or dataclass is not reached, and
    # scanning recursively would put unbounded work on every log call.
    # #VERIFY: a sensitive TOP-LEVEL name whose value is a container is
    # redacted whole, which covers the common `credentials={...}` shape.

    Args:
        _logger: The wrapped logger (unused; part of the processor contract).
        _method_name: The log method name (unused).
        event_dict: The event dictionary to censor.

    Returns:
        MutableMapping[str, object]: The same dictionary, mutated in place.
    """
    for name, value in event_dict.items():
        if name == _EVENT_KEY:
            continue
        # A number or a boolean cannot itself be credential material, and this
        # codebase logs LLM token counts (`max_tokens`, `content_token_count`)
        # and `has_pin`-style flags whose names brush the deny list. Exempting
        # them keeps real observability without weakening the guarantee.
        if value is None or isinstance(value, bool | int | float):
            continue
        if is_sensitive_key(name) or (
            isinstance(value, str) and value and _is_credential_shaped(value)
        ):
            event_dict[name] = REDACTED
    return event_dict
