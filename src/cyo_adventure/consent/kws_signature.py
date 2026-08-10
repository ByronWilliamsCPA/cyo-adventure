"""Signature verification for the two KWS return legs.

KWS answers a verification on two channels and signs them DIFFERENTLY. Nothing
here is shared between them beyond the hash function, which is why they are two
functions rather than one with a flag:

======================  ====================================  ===============
Leg                     Signed material                       Carrier
======================  ====================================  ===============
``parent-verified``     ``f"{timestamp}.{raw request body}"``  request header
webhook                                                       ``x-kws-signature``
Verification response   ``f"{status}:{external_payload}"``     query parameter
(redirect)                                                     ``signature``
======================  ====================================  ===============

The redirect construction has **no timestamp and no nonce**, which makes a
signed redirect URL a permanently replayable "I am verified" token: whoever
observes it once, including the child, can revisit it forever and the signature
still verifies, because it covers immutable content. It is therefore fit for
deciding which screen to render and unfit for creating a consent record. The
webhook, which is server-to-server and carries a timestamp inside the signed
string, is the only leg that may write.

#CRITICAL: security: these functions are the entire boundary between a
KWS-signed verification and one an attacker posted at our webhook URL. There is
no second check downstream, and a verification that gets past here becomes
evidence of parental consent.
#VERIFY: tests/unit/test_kws_signature.py covers a known-answer vector, both
tamper directions (body and timestamp), rotation via multiple ``v1=``, stale
and future timestamps, and every malformed-header shape.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from hashlib import sha256
from typing import NamedTuple

from cyo_adventure.core.exceptions import AuthenticationError

# Header component prefixes, per Epic's "Configure the Parent Verification
# Service Webhook" page: `t=<timestamp>,v1=<signature>[,v1=<signature>]`.
_TIMESTAMP_PREFIX = "t="
_SIGNATURE_PREFIX = "v1="

# A ceiling on how many components a header may carry before it is treated as
# malformed rather than parsed. Rotation needs two signatures, not hundreds; an
# unbounded list would let a caller push arbitrary HMAC work onto us with one
# request. 16 is far above any legitimate rotation and far below anything that
# costs measurable CPU.
_MAX_HEADER_COMPONENTS = 16


class FreshnessWindow(NamedTuple):
    """How far a delivery's ``t=`` may sit from now, and what now is.

    The two travel together because neither means anything alone: a tolerance
    with no reference point cannot be evaluated, and a clock reading with no
    tolerance cannot decide anything. Passing the clock in rather than reading
    it inside the verifier is what makes the window testable at its exact
    edges without patching time.

    Attributes:
        now: Current time in epoch seconds.
        max_skew_seconds: Tolerance in EITHER direction. A far-future timestamp
            is as much a sign of a forged or misconfigured sender as a far-past
            one, so the check is on the absolute difference.
    """

    now: int
    max_skew_seconds: int


@dataclass(frozen=True, slots=True)
class ParsedSignatureHeader:
    """The two fields carried by an ``x-kws-signature`` header.

    Attributes:
        timestamp: The ``t=`` component, epoch seconds, as an int.
        signatures: Every ``v1=`` component, lowercased, in header order. More
            than one is normal: it is how KWS keeps a secret rotation from
            breaking in-flight deliveries.
    """

    timestamp: int
    signatures: tuple[str, ...]


def _fail(reason: str, **diagnostics: int) -> AuthenticationError:
    """Build the single, deliberately uninformative rejection error.

    Every rejection path raises the same message. The caller logs ``reason``
    server-side, but an unauthenticated poster learns only that the request was
    rejected, never whether they got the format right and the key wrong, the
    key right and the timestamp stale, or neither.

    Args:
        reason: A short, log-safe discriminator for our own telemetry.
        diagnostics: Extra measurements for the same telemetry, typed ``int``
            deliberately. The type is the safeguard, not a convenience: it
            makes it impossible for a future call site to route a header, a
            digest, or a secret through this channel, since none of those are
            integers. Values reach the server log only; ``api/kws_webhook.py``
            drops the whole ``details`` mapping before the error is serialised.

    Returns:
        AuthenticationError: The error to raise, carrying ``reason`` and any
            diagnostics in ``details`` for structured logging rather than in
            the message.
    """
    return AuthenticationError(
        "KWS signature verification failed", details={"reason": reason, **diagnostics}
    )


def parse_signature_header(header: str) -> ParsedSignatureHeader:
    """Parse an ``x-kws-signature`` header into its timestamp and signatures.

    Strict about shape on purpose. A header that is merely unusual (two ``t=``
    components, a non-numeric timestamp, a ``v1=`` with no hex after it) is
    rejected rather than coerced, because every lenient reading of a signature
    header is a place where an attacker chooses which branch we take.

    Args:
        header: The raw header value.

    Returns:
        ParsedSignatureHeader: The parsed timestamp and one or more signatures.

    Raises:
        AuthenticationError: When the header is absent, empty, over-long, is
            missing either component, carries more than one timestamp, or has a
            non-integer timestamp.
    """
    if not header:
        reason = "missing_header"
        raise _fail(reason)

    parts = [part.strip() for part in header.split(",")]
    if len(parts) > _MAX_HEADER_COMPONENTS:
        reason = "too_many_components"
        raise _fail(reason)

    timestamps = [
        p.removeprefix(_TIMESTAMP_PREFIX)
        for p in parts
        if p.startswith(_TIMESTAMP_PREFIX)
    ]
    signatures = [
        p.removeprefix(_SIGNATURE_PREFIX)
        for p in parts
        if p.startswith(_SIGNATURE_PREFIX)
    ]

    if len(timestamps) != 1:
        reason = "timestamp_component_count"
        raise _fail(reason)
    if not signatures or not all(signatures):
        reason = "missing_signature_component"
        raise _fail(reason)

    try:
        timestamp = int(timestamps[0])
    except ValueError as exc:
        reason = "non_integer_timestamp"
        raise _fail(reason) from exc

    return ParsedSignatureHeader(
        timestamp=timestamp, signatures=tuple(s.lower() for s in signatures)
    )


def _matches_any(*, expected: str, candidates: tuple[str, ...]) -> bool:
    """Whether the computed digest matches any offered signature.

    Args:
        expected: The digest we computed, lowercase hex.
        candidates: The ``v1=`` components offered by the caller.

    Returns:
        bool: True when at least one candidate matches.
    """
    # Every comparison is constant-time. The loop short-circuits on a match,
    # which reveals only WHICH rotation key matched (not secret), never
    # anything about the digest itself.
    return any(hmac.compare_digest(expected, candidate) for candidate in candidates)


def verify_webhook_signature(
    *,
    header: str,
    body: bytes,
    secret: str,
    window: FreshnessWindow,
) -> ParsedSignatureHeader:
    """Verify a ``parent-verified`` webhook delivery.

    Two properties are worth stating because the one open-source reference
    implementation (``bluesky-social/atproto``) gets both wrong:

    1. **All** ``v1=`` components are tried, not just the first. Taking only
       the first is correct until the day a secret is rotated, at which point
       deliveries signed with the new key are silently rejected while the
       header plainly contains a matching signature.
    2. The ``t=`` component is checked for freshness. KWS puts the timestamp
       inside the signed string precisely so a window can be enforced;
       verifying the MAC alone leaves any captured delivery replayable
       forever, and a replayed consent event is indistinguishable from a real
       one once written.

    Args:
        header: The raw ``x-kws-signature`` header value.
        body: The RAW request body bytes. Never a parsed-and-re-serialised
            copy: Epic's documentation is explicit that JSON libraries differ
            in key order and whitespace, so a round-tripped body produces a
            valid delivery that fails verification.
        secret: The webhook secret from the Control Panel.
        window: The freshness window to judge ``t=`` against.

    Returns:
        ParsedSignatureHeader: The verified header, so a caller that wants to
            record the delivery timestamp does not re-parse it.

    Raises:
        AuthenticationError: When the header is malformed, the timestamp is
            outside the window, or no signature matches. The message is
            identical in every case.
    """
    parsed = parse_signature_header(header)

    # Freshness first, so a replay of an otherwise-valid capture is rejected
    # without spending an HMAC on it.
    #
    # The measurements travel with the reason because the label alone cannot
    # separate three very different faults, and a KWS Test run on 2026-08-10
    # cost real time to exactly this ambiguity. A skew of a few seconds is our
    # clock drifting; minutes to hours is a genuine replay or a queued
    # redelivery; a value near 1.8e12 is a sender emitting MILLISECONDS where
    # this compares seconds, which is a wire-format change, not a stale
    # delivery, and needs a code fix rather than an NTP fix. Signed, not
    # absolute: the direction distinguishes a delivery from the past from one
    # from the future.
    if abs(window.now - parsed.timestamp) > window.max_skew_seconds:
        reason = "timestamp_outside_window"
        raise _fail(
            reason,
            signature_timestamp=parsed.timestamp,
            skew_seconds=window.now - parsed.timestamp,
        )

    signed = f"{parsed.timestamp}.".encode() + body
    expected = hmac.new(secret.encode(), signed, sha256).hexdigest()
    if not _matches_any(expected=expected, candidates=parsed.signatures):
        reason = "no_matching_signature"
        raise _fail(reason)
    return parsed


def verify_redirect_signature(
    *, signature: str, status: str, external_payload: str, secret: str
) -> None:
    """Verify the redirect leg's ``signature`` query parameter.

    Different secret and a different construction from the webhook:
    ``HMAC-SHA256(secret, f"{status}:{external_payload}")``, with no timestamp.

    #CRITICAL: security: a valid result here means only that KWS produced this
    URL at some point, never that it was produced just now or for this session.
    The signed material is immutable, so the URL is a bearer token with no
    expiry. Use it to choose a screen; never to write a consent record. The
    webhook is the write path.

    Args:
        signature: The ``signature`` query parameter.
        status: The ``status`` query parameter, exactly as received (still
            URL-decoded but not JSON-parsed, since the signature covers the
            literal string).
        external_payload: The ``externalPayload`` query parameter, likewise
            verbatim.
        secret: The verification secret from the Control Panel.

    Raises:
        AuthenticationError: When the signature is absent or does not match.
    """
    if not signature:
        reason = "missing_redirect_signature"
        raise _fail(reason)

    signed = f"{status}:{external_payload}".encode()
    expected = hmac.new(secret.encode(), signed, sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        reason = "redirect_signature_mismatch"
        raise _fail(reason)
