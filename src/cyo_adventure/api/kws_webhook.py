"""Receiver for the KWS ``parent-verified`` webhook (ADR-018).

``POST /api/v1/webhooks/kws/parent-verified`` is the server-to-server leg of
the Parent Verification Service. It is the only leg allowed to write: the
redirect leg's signature covers immutable content with no timestamp, so a
redirect URL is a permanently replayable bearer token (see
``consent/kws_signature.py``).

Deliberately excluded from the OpenAPI schema
---------------------------------------------
``include_in_schema=False``. The frontend has no business calling this route,
and the generated axios client is committed with a CI drift check, so putting
a machine-to-machine webhook in the schema would churn ``frontend/src/client/``
for an endpoint no browser will ever hit.

What a delivery is worth, and what it is not
--------------------------------------------
A delivery resolves the ``kws_verification`` row whose id the send leg minted
and handed out as ``externalPayload`` (``consent/service.py``). That row is
adult-verification evidence, corroborating the 16 CFR 312.5 consent record on
``User.consent_*``, never a replacement for it: KWS establishes that an adult
is an adult, and Epic's own documentation disclaims the consent and direct
notice legs entirely.

Everything this route declines to treat as an error
---------------------------------------------------
An unrecognised event name, another organization's delivery, a missing or
malformed ``externalPayload``, and an attempt id we hold no row for are all
answered ``200`` with ``handled=False``. None of them can become ours on a
later attempt, so a non-2xx would only buy a retry loop against a decision that
cannot change. A signature failure is the opposite and is answered ``401``,
because that one IS about whether to believe the delivery at all.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from cyo_adventure.api.deps import DbSession
from cyo_adventure.consent import (
    FreshnessWindow,
    ParentVerifiedOutcome,
    parse_correlation,
    record_parent_verified,
    verify_webhook_signature,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ValidationError,
)
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["kws"])

# The only event name this route acts on. KWS may add others; an unrecognised
# name is acknowledged and ignored rather than rejected, so a new event type
# does not turn into a retry storm against an endpoint that will never want it.
_PARENT_VERIFIED = "parent-verified"

# Hard cap on the body we will authenticate. The HMAC runs over the whole body,
# so an uncapped reader lets an unauthenticated caller choose how much work we
# do per request. Real deliveries are a few hundred bytes; 64 KiB is four
# orders of magnitude of headroom and still bounded.
# #EDGE: security: this bounds unauthenticated CPU per request, it is not a
# schema constraint; a legitimate delivery has never come close.
# #VERIFY: tests/unit/test_kws_webhook.py::test_oversized_body_rejected.
_MAX_BODY_BYTES = 64 * 1024


class ParentVerifiedAck(BaseModel):
    """The acknowledgement returned for an authenticated delivery.

    Attributes:
        handled: Whether the delivery was acted on. False means it verified but
            was not for us (another organization, another product, or an event
            name this route does not consume), which is a terminal outcome
            rather than something KWS should retry.
    """

    handled: bool


class _VerificationStatus(BaseModel):
    """The ``payload.status`` object of a ``parent-verified`` delivery.

    Note what is absent: there is no verification-method field. KWS reports
    only that verification succeeded and an opaque transaction id, so the
    method that actually ran is unknowable from the event, and
    ``settings.kws_enabled_methods`` is the only bound on it.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    verified: bool = False
    transaction_id: str | None = Field(default=None, alias="transactionId")


class _VerificationPayload(BaseModel):
    """The ``payload`` object of a ``parent-verified`` delivery."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    # #CRITICAL: security: parentEmail arrives in cleartext and is the most
    # sensitive field in the delivery. It is parsed so the shape is validated,
    # and it is never logged, never echoed, and never used as a join key.
    # #VERIFY: tests/unit/test_kws_webhook.py::test_parent_email_is_never_logged.
    parent_email: str | None = Field(default=None, alias="parentEmail")
    external_payload: str | None = Field(default=None, alias="externalPayload")
    status: _VerificationStatus = Field(default_factory=_VerificationStatus)


class _VerificationEvent(BaseModel):
    """A whole ``parent-verified`` delivery envelope."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = ""
    time: str | None = None
    org_id: str | None = Field(default=None, alias="orgId")
    product_id: str | None = Field(default=None, alias="productId")
    payload: _VerificationPayload = Field(default_factory=_VerificationPayload)


def _reject(
    reason: str, diagnostics: Mapping[str, int] | None = None
) -> AuthenticationError:
    """Log why a delivery was refused and return the error the caller sees.

    The split matters. ``consent/kws_signature.py`` raises with the
    discriminator in ``details`` so a caller can tell a stale replay from a
    wrong key, but the app's error handler serialises ``details`` into the
    response body: correct for a ``ValidationError`` naming the offending
    field, wrong here, where it would hand an unauthenticated poster a precise
    account of which check they failed. So the reason is logged here and the
    error that propagates carries none.

    #CRITICAL: security: information disclosure (CWE-209). Every rejection path
    out of this route must go through this function; raising the verifier's own
    exception directly would publish the discriminator to the caller.
    #VERIFY: tests/unit/test_kws_webhook.py::
    test_rejection_body_does_not_name_the_failed_check.

    Args:
        reason: The log-safe discriminator, never sent to the caller.
        diagnostics: Extra integer measurements from the verifier, logged
            beside ``reason``. Same destination and same secrecy as ``reason``:
            telemetry only. ``consent/kws_signature.py`` constrains these to
            ``int`` at the raising end, so nothing string-shaped can be routed
            here by a later edit.

    Returns:
        AuthenticationError: The opaque error to raise, with no ``details``.
    """
    logger.warning(
        "kws_webhook_rejected",
        reason=reason,
        kws_environment=settings.kws_environment,
        **dict(diagnostics or {}),
    )
    return AuthenticationError("KWS signature verification failed")


def _require_receiver_configured() -> str:
    """Return the webhook secret, refusing to run without one.

    An unset secret is not permission to trust unsigned deliveries. Every
    delivery would be unverifiable, and an unverifiable consent event is worse
    than a missed one the moment it becomes our evidence of a consent that may
    never have happened.

    Returns:
        str: The configured webhook secret.

    Raises:
        ConfigurationError: When no webhook secret is configured. Renders as a
            400, which is non-2xx and therefore visible to KWS's retry
            behaviour rather than silently absorbed.
    """
    secret = settings.kws_webhook_secret
    if secret is None or not secret.get_secret_value():
        msg = (
            "KWS_WEBHOOK_SECRET is not configured; refusing to accept an "
            "unverifiable parent-verified delivery."
        )
        raise ConfigurationError(msg)
    return secret.get_secret_value()


@router.post(
    "/webhooks/kws/parent-verified",
    include_in_schema=False,
    status_code=200,
)
async def receive_parent_verified(
    request: Request,
    session: DbSession,
    x_kws_signature: Annotated[str, Header()] = "",
) -> ParentVerifiedAck:
    """Authenticate and record a KWS ``parent-verified`` delivery.

    The order of operations is the security-relevant part: the raw body is read
    and authenticated BEFORE it is parsed. Epic's documentation is explicit
    that the signature covers the raw bytes and warns against parsing and
    re-stringifying, and parsing first would additionally mean running a JSON
    decoder over unauthenticated input.

    #ASSUME: external resources: the signature travels in the
    ``x-kws-signature`` HEADER. The API reference documents the header form and
    the one open-source production integration reads the header, but the
    Control Panel's own webhook copy says the signature is in the "webhook call
    query string". The two disagree; the header is the better-evidenced of the
    two, and a query-string signature would land here as a missing header,
    which is rejected loudly rather than silently accepted.
    #VERIFY: the first real Test-environment delivery settles it; if these
    rejections appear with a populated query string, add the query-string form.

    Args:
        request: The inbound request, read for its raw body.
        session: The request unit of work the verification row is resolved on.
            This handler never commits it; ``UnitOfWorkMiddleware`` does, before
            the acknowledgement reaches KWS, so a 200 is never sent for a
            resolution that has not landed.
        x_kws_signature: The signature header, defaulted to empty so a missing
            header is a signature failure rather than a 422 shape error.

    Returns:
        ParentVerifiedAck: Whether the delivery was acted on.

    Raises:
        AuthenticationError: When the signature is missing, malformed, stale,
            or does not match. Rendered as 401 and recorded to the security
            audit trail by the app's exception handler.
        ValidationError: When an authenticated body is not JSON, or is not a
            JSON object.
    """
    secret = _require_receiver_configured()

    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        reason = "body_too_large"
        raise _reject(reason)

    received_at = int(time.time())
    try:
        verified_header = verify_webhook_signature(
            header=x_kws_signature,
            body=body,
            secret=secret,
            window=FreshnessWindow(
                now=received_at,
                max_skew_seconds=settings.kws_webhook_max_skew_seconds,
            ),
        )
    except AuthenticationError as exc:
        # Re-raised, not propagated: the verifier's exception carries the
        # discriminator in `details`, and the app handler puts `details` in the
        # response body. `_reject` keeps it in telemetry and off the wire.
        # Typed `object`, not the mapping's own `Any`: the whole point of the
        # block below is to interrogate these values' types, which a value the
        # checker already believes could be anything cannot support.
        details: Mapping[str, object] = exc.details or {}
        reason = details.get("reason") or "unspecified"
        # Everything else the verifier measured, filtered to ints so a future
        # detail of any other shape cannot ride this path into the log, and
        # with the two keys `_reject` sets itself excluded so a collision
        # raises no TypeError at the logging call.
        diagnostics = {
            key: value
            for key, value in details.items()
            if key not in {"reason", "kws_environment"} and isinstance(value, int)
        }
        raise _reject(str(reason), diagnostics) from exc

    # Logged on the ACCEPTED path, which is the only place a unit change is
    # cheap to notice. Once the verifier tolerates both units, a sender that
    # switches stops producing any rejection at all, so the rejection log can
    # no longer be the alarm; this line is what makes the switch visible while
    # deliveries are still succeeding, rather than after something else breaks.
    logger.info(
        "kws_webhook_verified",
        timestamp_unit=verified_header.unit,
        delivery_age_seconds=received_at - verified_header.epoch_seconds,
        signature_count=len(verified_header.signatures),
        kws_environment=settings.kws_environment,
    )

    try:
        decoded: object = json.loads(body)
    except json.JSONDecodeError as exc:
        msg = "Authenticated KWS delivery was not valid JSON."
        raise ValidationError(msg, field="body") from exc
    if not isinstance(decoded, dict):
        msg = "Authenticated KWS delivery was not a JSON object."
        raise ValidationError(msg, field="body")

    event = _VerificationEvent.model_validate(decoded)

    # Envelope checks are answered with 200 + handled=False, not an error. A
    # delivery for another organization or a future event type will never
    # become ours, so a non-2xx would only buy a retry loop against a decision
    # that cannot change. The warning is what makes a misrouted webhook
    # visible; silence is what would hide it.
    if event.name != _PARENT_VERIFIED or not _is_for_us(event):
        logger.warning(
            "kws_webhook_ignored",
            event_name=event.name,
            org_matches=event.org_id == settings.kws_organization_id,
            product_matches=_product_matches(event),
            # The received ids, not just the verdicts. `product_matches=False`
            # names a mismatch without naming either side of it, which on
            # 2026-08-10 meant a delivery could report the comparison failing
            # while the value we needed in order to pin the setting, and the
            # value that revealed the setting was `""` rather than unset, both
            # went unlogged. Neither id is personal data: they identify our own
            # KWS tenant and product, and the delivery is authenticated by the
            # time this line runs.
            received_org_id=event.org_id,
            received_product_id=event.product_id,
            kws_environment=settings.kws_environment,
        )
        return ParentVerifiedAck(handled=False)

    # No parent email: it is the most sensitive field in the delivery, it is
    # never a join key here, and the attempt id below identifies the attempt
    # without identifying a person.
    logger.info(
        "kws_parent_verified",
        verified=event.payload.status.verified,
        transaction_id=event.payload.status.transaction_id,
        has_external_payload=event.payload.external_payload is not None,
        kws_environment=settings.kws_environment,
        kws_environment_label=settings.kws_environment_label,
        enabled_methods=settings.kws_enabled_methods,
        event_time=event.time,
    )

    attempt_id = _attempt_id(event)
    if attempt_id is None:
        return ParentVerifiedAck(handled=False)

    handled = await record_parent_verified(
        session,
        ParentVerifiedOutcome(
            attempt_id=attempt_id,
            verified=event.payload.status.verified,
            transaction_id=event.payload.status.transaction_id,
        ),
    )
    return ParentVerifiedAck(handled=handled)


def _attempt_id(event: _VerificationEvent) -> uuid.UUID | None:
    """Read our own attempt id out of the delivery's ``externalPayload``.

    #CRITICAL: security: ``externalPayload`` is third-party-echoed, untrusted
    input, and it is parsed in full rather than trusted because we minted its
    ancestor. A missing or malformed one is a routing outcome (``handled=
    False``), not a 4xx: both are terminal, and answering non-2xx would put KWS
    into a retry loop over a body that cannot improve. The parsed id is still
    only a lookup key; the row it finds is what decides whether an attempt is
    real.
    #VERIFY: tests/unit/test_kws_webhook.py::
    test_missing_external_payload_not_handled and
    ::test_malformed_external_payload_not_handled.

    Args:
        event: The parsed delivery envelope.

    Returns:
        uuid.UUID | None: The attempt id, or None when the delivery carries no
            payload we can read.
    """
    raw = event.payload.external_payload
    if raw is None:
        logger.warning(
            "kws_webhook_without_external_payload",
            kws_environment=settings.kws_environment,
        )
        return None
    try:
        return parse_correlation(raw).attempt_id
    except ValidationError:
        # The value itself is never logged: it is ours, it is opaque, and an
        # unparsable one is as likely to be an attacker's guess as a bug.
        logger.warning(
            "kws_webhook_unreadable_external_payload",
            kws_environment=settings.kws_environment,
        )
        return None


def _product_matches(event: _VerificationEvent) -> bool:
    """Whether the delivery's product id matches our configured one.

    Vacuously true while ``kws_product_id`` is unset, which is the expected
    state until a first delivery reveals the id: the organization check still
    bounds the delivery to our tenant, and refusing everything until the id is
    known would prevent the very delivery that reveals it.

    "Unset" is tested by emptiness rather than by ``is None``, which is the
    narrower check this used to make. ``core/config.py`` now normalises an
    empty override to None, so a settings object built from the environment
    can no longer carry ``""`` here; this stays because a settings object is
    not always built that way. Direct assignment bypasses field validators
    entirely, which is exactly how every test of this function sets the value,
    and it is how the guard came to be tested only in states it could not
    actually be in. The cost of the two checks disagreeing is a signed, fresh
    delivery silently dropped, so they are made to agree here as well.

    Args:
        event: The parsed delivery envelope.

    Returns:
        bool: True when the product id matches or is not yet pinned.
    """
    return not settings.kws_product_id or event.product_id == settings.kws_product_id


def _is_for_us(event: _VerificationEvent) -> bool:
    """Whether the delivery belongs to our organization and product.

    Args:
        event: The parsed delivery envelope.

    Returns:
        bool: True when both the organization and product ids match.
    """
    return event.org_id == settings.kws_organization_id and _product_matches(event)
