"""Guardian-set profile PIN hashing (P6-07).

A guardian may put an optional 4-8 digit PIN on a child profile; the kid
picker must present it before a child session is minted for that profile
(see ``api/child_sessions.py``). This module owns the at-rest encoding of
that PIN and nothing else: hashing on set, constant-time verification on
mint. The stored value is write-only credential material; no API response
ever includes it (profile views expose a derived ``has_pin`` bool only).

Encoding
--------
``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``

- stdlib ``hashlib.pbkdf2_hmac("sha256", ...)``: deliberately FIPS-safe
  (this repo forbids bcrypt/md5; see the FIPS section in CLAUDE.md).
- A fresh random salt per PIN (``secrets.token_bytes``), so equal PINs on
  two profiles never share a hash.
- The iteration count is stored in the encoding, so it can be raised later
  without invalidating existing rows (old hashes verify with their stored
  count; new sets pick up the new default).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_SCHEME = "pbkdf2_sha256"
# OWASP's 2023+ PBKDF2-HMAC-SHA256 recommendation; stored per hash so it can
# be raised without a migration.
_ITERATIONS = 600_000
_SALT_BYTES = 16
_HASH_BYTES = 32


def hash_pin(pin: str, *, iterations: int = _ITERATIONS) -> str:
    """Hash a profile PIN for at-rest storage.

    Args:
        pin: The PIN to hash. Format (4-8 digits) is enforced at the API
            boundary (``schemas.PinCode``); this function only refuses the
            empty string so a blank can never become a valid credential.
        iterations: PBKDF2 iteration count; the default is the module
            standard and tests may lower it for speed.

    Returns:
        str: The encoded hash, ``pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>``.

    Raises:
        ValueError: If ``pin`` is empty or ``iterations`` is not positive.
    """
    if not pin:
        msg = "pin must not be empty"
        raise ValueError(msg)
    if iterations < 1:
        msg = "iterations must be positive"
        raise ValueError(msg)
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt, iterations, dklen=_HASH_BYTES
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(digest).decode("ascii")
    return f"{_SCHEME}${iterations}${salt_b64}${hash_b64}"


def verify_pin(pin: str, encoded: str) -> bool:
    """Check a candidate PIN against a stored encoded hash.

    Any malformed or tampered encoding (wrong scheme, wrong field count,
    non-integer iterations, invalid base64) verifies as ``False`` rather than
    raising: a corrupt stored value must fail closed, never crash the mint
    endpoint or fall open.

    Args:
        pin: The candidate PIN presented by the caller.
        encoded: The stored ``pbkdf2_sha256$...`` encoding.

    Returns:
        bool: True only when the candidate matches the stored hash.
    """
    # #CRITICAL: security: the comparison must be constant-time
    # (hmac.compare_digest), never ==, so a byte-by-byte early exit cannot
    # leak hash prefixes; and every parse failure returns False (fail closed).
    # #VERIFY: tests/unit/test_pin.py::test_verify_rejects_tampered_encodings
    # covers scheme/field/iteration/base64 tampering, all -> False.
    if not pin or not encoded:
        return False
    parts = encoded.split("$")
    expected_parts = 4
    if len(parts) != expected_parts or parts[0] != _SCHEME:
        return False
    try:
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2], validate=True)
        stored = base64.b64decode(parts[3], validate=True)
    except (ValueError, TypeError):
        return False
    if iterations < 1 or not salt or not stored:
        return False
    # Always derive the full module-standard length, NEVER dklen=len(stored):
    # a PBKDF2 output at a shorter dklen is a prefix of the longer one, so
    # matching the stored length would let a truncated stored hash verify.
    candidate = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt, iterations, dklen=_HASH_BYTES
    )
    return hmac.compare_digest(candidate, stored)
