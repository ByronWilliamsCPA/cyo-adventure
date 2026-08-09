"""The correlation blob we hand KWS and get back on both return legs.

``externalPayload`` is the only field that travels out with a verification
request and comes back attached to the result, so it is the sole means of
tying a ``parent-verified`` delivery to the guardian who started the flow.
``parentEmail`` comes back too, but joining on an email address would make the
most sensitive field in the delivery into a primary key, and it does not
survive a guardian changing their address.

What goes in it, and what must not
----------------------------------
An opaque per-attempt token, and nothing else. The value round-trips through a
third party and comes back in a redirect URL, which lands in browser history,
in any referrer, and in front of whoever is holding the device. So it must
carry no personal data, and it must not be a stable internal identifier: a
guardian's user id in a URL is a durable cross-request handle we would be
publishing for no gain. A fresh random token per attempt is unguessable, means
nothing to anyone who intercepts it, and is revocable by deleting one row.

The version field earns its four characters: the one open-source KWS
integration already carries a v1/v2 compatibility path for exactly this blob,
because in-flight verifications outlive a deploy. A payload minted before a
shape change comes back after it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from cyo_adventure.core.exceptions import ValidationError

# KWS caps externalPayload at 250 characters (a JSON or UTF-8 string). Note the
# 200 in bluesky-social/atproto is that product's own lower limit, not this one.
MAX_EXTERNAL_PAYLOAD_CHARS = 250

# Bumped only when the blob's shape changes. A reader must reject a version it
# does not understand rather than guess at the fields.
_SCHEMA_VERSION = 1

_VERSION_KEY = "v"
_ATTEMPT_KEY = "attemptId"


@dataclass(frozen=True, slots=True)
class VerificationCorrelation:
    """A single verification attempt's correlation token.

    Attributes:
        attempt_id: An opaque, randomly generated identifier for one attempt.
            Not derived from the guardian, the child, or the email address.
    """

    attempt_id: UUID


def mint_correlation() -> VerificationCorrelation:
    """Create a correlation token for a new verification attempt.

    Returns:
        VerificationCorrelation: A token with a fresh random attempt id.
    """
    return VerificationCorrelation(attempt_id=uuid4())


def serialize_correlation(correlation: VerificationCorrelation) -> str:
    """Render a correlation token as the ``externalPayload`` string.

    Args:
        correlation: The token to serialise.

    Returns:
        str: Compact JSON, comfortably inside the 250-character cap.

    Raises:
        ValidationError: If the rendered payload would exceed the cap. It
            cannot today at roughly 50 characters, so this firing means the
            blob's shape grew; failing here beats a 4xx from KWS that a caller
            would read as a transient upstream fault.
    """
    rendered = json.dumps(
        {_VERSION_KEY: _SCHEMA_VERSION, _ATTEMPT_KEY: str(correlation.attempt_id)},
        separators=(",", ":"),
    )
    if len(rendered) > MAX_EXTERNAL_PAYLOAD_CHARS:
        msg = (
            f"externalPayload is {len(rendered)} characters, over the KWS "
            f"limit of {MAX_EXTERNAL_PAYLOAD_CHARS}."
        )
        raise ValidationError(msg, field="externalPayload")
    return rendered


def parse_correlation(raw: str) -> VerificationCorrelation:
    """Read back a correlation token that KWS returned to us.

    #CRITICAL: security: this parses UNTRUSTED input. The value is echoed by a
    third party and arrives on the redirect leg as a query parameter anyone can
    edit, so it is validated in full (shape, version, id format) rather than
    trusted because we minted its ancestor. A parsed token is still only a
    lookup key: it proves nothing on its own, and the row it finds is what
    decides whether an attempt is real.
    #VERIFY: tests/unit/test_kws_external_payload.py covers non-JSON, non-object,
    unknown version, missing and malformed attempt ids.

    Args:
        raw: The ``externalPayload`` string as received.

    Returns:
        VerificationCorrelation: The parsed token.

    Raises:
        ValidationError: When the payload is not JSON, is not an object, is not
            a version this build understands, or carries no valid attempt id.
    """
    try:
        decoded: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = "externalPayload was not valid JSON."
        raise ValidationError(msg, field="externalPayload") from exc
    if not isinstance(decoded, dict):
        msg = "externalPayload was not a JSON object."
        raise ValidationError(msg, field="externalPayload")

    if decoded.get(_VERSION_KEY) != _SCHEMA_VERSION:
        msg = "externalPayload carries an unsupported schema version."
        raise ValidationError(msg, field="externalPayload")

    attempt = decoded.get(_ATTEMPT_KEY)
    if not isinstance(attempt, str):
        msg = "externalPayload carries no attempt id."
        raise ValidationError(msg, field="externalPayload")
    try:
        attempt_id = UUID(attempt)
    except ValueError as exc:
        msg = "externalPayload carries a malformed attempt id."
        raise ValidationError(msg, field="externalPayload") from exc

    return VerificationCorrelation(attempt_id=attempt_id)
