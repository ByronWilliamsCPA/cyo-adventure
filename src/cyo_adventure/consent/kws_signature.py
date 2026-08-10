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
and future timestamps, millisecond and second units including the observed
production-shaped value, and every malformed-header shape.
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

# Plausible ranges for the `t=` value under each unit, used to decide which unit
# a delivery is speaking. Both bands cover 2001 to 2286 in their own unit, and
# they are separated by a factor of 1000, so no clock error, replay, or hostile
# choice puts a value in the wrong one: reading a seconds-value as milliseconds
# lands in 1970, and a milliseconds-value as seconds lands in the year 58600.
#
# Epic's documentation does not state the unit. A Test delivery on 2026-08-10
# settled it by observation: `t=1786390879601`, received 0.52 seconds later.
# That is milliseconds. Seconds is still accepted rather than rejected, because
# the cost of being wrong is asymmetric. A verifier hard-coded to milliseconds
# that meets a seconds-emitting sender rejects EVERY delivery, and the visible
# symptom is silence: parents verify successfully at KWS, no consent is ever
# recorded, and nothing in any log we can read says so. Accepting both costs one
# comparison and is not attacker-controllable, since `t=` is inside the signed
# string and cannot be moved between bands without breaking the MAC.
_EPOCH_SECONDS_MIN = 1_000_000_000
_EPOCH_SECONDS_MAX = 10_000_000_000
_EPOCH_MILLIS_MIN = _EPOCH_SECONDS_MIN * 1000
_EPOCH_MILLIS_MAX = _EPOCH_SECONDS_MAX * 1000


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
    """The fields carried by an ``x-kws-signature`` header.

    Attributes:
        timestamp: The ``t=`` component as an int, in WHATEVER unit the sender
            used. Deliberately not normalised: see ``epoch_seconds`` for the
            comparable value and ``raw_timestamp`` for the signable one.
        raw_timestamp: The ``t=`` component as the exact characters received.
            This, not ``timestamp``, is what goes into the signed string. The
            two round-trip identically for a canonical integer, but the moment
            this module started reinterpreting the value's unit, reconstructing
            the signed material from the parsed int became a way for a future
            normalisation to silently change what we hash and break every
            signature at once.
        signatures: Every ``v1=`` component, lowercased, in header order. More
            than one is normal: it is how KWS keeps a secret rotation from
            breaking in-flight deliveries.
        unit: Which unit ``timestamp`` was found to be in, ``"s"`` or ``"ms"``.
            Carried so the caller can log it: a sender that changes units is a
            wire-format change we want to see in telemetry the day it happens,
            not the day consent stops being recorded.
    """

    timestamp: int
    raw_timestamp: str
    signatures: tuple[str, ...]
    unit: str

    @property
    def epoch_seconds(self) -> int:
        """The timestamp in epoch seconds, whichever unit arrived.

        Returns:
            int: Epoch seconds, truncated. Sub-second precision is discarded on
                purpose: the freshness window is measured in minutes, so
                rounding cannot change a verdict, and an int keeps the
                diagnostics channel integer-typed end to end.
        """
        return self.timestamp // 1000 if self.unit == "ms" else self.timestamp


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

    raw_timestamp = timestamps[0]
    try:
        timestamp = int(raw_timestamp)
    except ValueError as exc:
        reason = "non_integer_timestamp"
        raise _fail(reason) from exc

    unit = _timestamp_unit(timestamp)
    if unit is None:
        # Neither band. This is not a stale delivery and not a clock problem;
        # it is a value that cannot be a date at all, so it is rejected here as
        # malformed rather than being handed to the freshness check, which
        # would report it as skew and send the reader looking at NTP.
        reason = "implausible_timestamp"
        raise _fail(reason, signature_timestamp=timestamp)

    return ParsedSignatureHeader(
        timestamp=timestamp,
        raw_timestamp=raw_timestamp,
        signatures=tuple(s.lower() for s in signatures),
        unit=unit,
    )


def _timestamp_unit(timestamp: int) -> str | None:
    """Classify a ``t=`` value as seconds or milliseconds by magnitude.

    Args:
        timestamp: The parsed ``t=`` value.

    Returns:
        str | None: ``"s"``, ``"ms"``, or None when the value falls in neither
            plausible band and cannot be a date in either unit.
    """
    if _EPOCH_SECONDS_MIN <= timestamp < _EPOCH_SECONDS_MAX:
        return "s"
    if _EPOCH_MILLIS_MIN <= timestamp < _EPOCH_MILLIS_MAX:
        return "ms"
    return None


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
    3. That freshness check is done in a UNIT, not in raw integers. KWS sends
       ``t=`` in milliseconds, which Epic's documentation does not say
       anywhere; comparing it to a seconds clock rejects every genuine
       delivery, and the symptom is a verification that succeeds at the vendor
       and silently records nothing here. Both units are accepted; see
       ``_timestamp_unit``.

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
    # Compared in seconds against `epoch_seconds`, never against the raw value:
    # KWS sends milliseconds, and comparing those to a seconds clock rejected
    # every genuine delivery on 2026-08-10 while reporting a 56,000-year skew.
    #
    # The measurements still travel with the reason, because the label alone
    # cannot separate the faults that remain. A skew of a few seconds is our
    # clock drifting and needs NTP; minutes to hours is a real replay or a
    # queued redelivery and needs investigating. Signed, not absolute: the
    # direction distinguishes a delivery from the past from one from the
    # future. The raw value rides along so a unit change is still visible here
    # even though it can no longer reach this branch.
    skew = window.now - parsed.epoch_seconds
    if abs(skew) > window.max_skew_seconds:
        reason = "timestamp_outside_window"
        raise _fail(
            reason,
            signature_timestamp=parsed.timestamp,
            skew_seconds=skew,
        )

    # The verbatim token, never `parsed.timestamp`. KWS signed the characters it
    # sent; anything we reconstruct is a guess that happens to agree.
    signed = f"{parsed.raw_timestamp}.".encode() + body
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
