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

What this does NOT do yet
-------------------------
It does not persist a verification record. Attribution requires the send leg
(``send-email``), which is what mints the ``externalPayload`` correlation blob
that ties a delivery back to a specific guardian; designing the record before
that exists would mean designing it around ``parentEmail``, the one field we
least want as a join key. Until then this receiver is an INSTRUMENT: it proves
the signature scheme against the real service and answers the open question
that no documentation settles, namely whether ``parent-verified`` fires at all
on the pre-verified (AgeGraph) path.

Because an instrument that silently discards real consent evidence would be
worse than no instrument, the production guard below is a mechanism rather
than a promise: this route refuses to process a delivery while
``kws_environment`` is ``"production"``, and that refusal is removed by the
commit that adds persistence, not before.
"""

from __future__ import annotations

import json
import time
from typing import Annotated

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from cyo_adventure.consent import FreshnessWindow, verify_webhook_signature
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ValidationError,
)
from cyo_adventure.utils.logging import get_logger

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


def _reject(reason: str) -> AuthenticationError:
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

    Returns:
        AuthenticationError: The opaque error to raise, with no ``details``.
    """
    logger.warning(
        "kws_webhook_rejected",
        reason=reason,
        kws_environment=settings.kws_environment,
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


def _reject_production_until_persistence_exists() -> None:
    """Refuse production deliveries while this receiver only logs.

    #CRITICAL: data integrity: a production delivery reaching a receiver with
    no persistence is a real parent's verification discarded, and KWS will not
    replay it on request. Enforcing the restriction in code rather than in a
    comment is what keeps "we will add persistence before pointing it at
    production" from being a promise nobody re-reads.
    #VERIFY: tests/unit/test_kws_webhook.py::
    test_production_environment_refuses_to_process.

    Raises:
        ConfigurationError: When ``kws_environment`` is ``"production"``.
    """
    if settings.kws_environment == "production":
        msg = (
            "This receiver records no verification yet, so it must not be "
            "pointed at the production KWS environment: a real delivery would "
            "be acknowledged and lost. Remove this guard in the change that "
            "adds the verification record."
        )
        raise ConfigurationError(msg)


@router.post(
    "/webhooks/kws/parent-verified",
    include_in_schema=False,
    status_code=200,
)
async def receive_parent_verified(
    request: Request,
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
    _reject_production_until_persistence_exists()

    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        reason = "body_too_large"
        raise _reject(reason)

    try:
        verify_webhook_signature(
            header=x_kws_signature,
            body=body,
            secret=secret,
            window=FreshnessWindow(
                now=int(time.time()),
                max_skew_seconds=settings.kws_webhook_max_skew_seconds,
            ),
        )
    except AuthenticationError as exc:
        # Re-raised, not propagated: the verifier's exception carries the
        # discriminator in `details`, and the app handler puts `details` in the
        # response body. `_reject` keeps it in telemetry and off the wire.
        reason = (exc.details or {}).get("reason") or "unspecified"
        raise _reject(str(reason)) from exc

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
            kws_environment=settings.kws_environment,
        )
        return ParentVerifiedAck(handled=False)

    # No parent email, and no externalPayload contents: the first is the most
    # sensitive field in the delivery and the second is our own correlation
    # blob, which is only meaningful once the send leg mints it. Its presence
    # is worth knowing; its value is not.
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
    return ParentVerifiedAck(handled=True)


def _product_matches(event: _VerificationEvent) -> bool:
    """Whether the delivery's product id matches our configured one.

    Vacuously true while ``kws_product_id`` is unset, which is the expected
    state until a first delivery reveals the id: the organization check still
    bounds the delivery to our tenant, and refusing everything until the id is
    known would prevent the very delivery that reveals it.

    Args:
        event: The parsed delivery envelope.

    Returns:
        bool: True when the product id matches or is not yet pinned.
    """
    return (
        settings.kws_product_id is None or event.product_id == settings.kws_product_id
    )


def _is_for_us(event: _VerificationEvent) -> bool:
    """Whether the delivery belongs to our organization and product.

    Args:
        event: The parsed delivery envelope.

    Returns:
        bool: True when both the organization and product ids match.
    """
    return event.org_id == settings.kws_organization_id and _product_matches(event)
