"""The persistence seam between the KWS legs and ``kws_verification``.

``consent/kws_client.py`` is pure HTTP and stays that way: it knows how to talk
to KWS and nothing about our database. ``api/kws_webhook.py`` is a receiver and
stays that way too. This module is where the two meet a row, so neither of them
has to grow a second responsibility.

Ordering, which is the whole point
----------------------------------
The record is INSERTed before the outbound send, never after. The two orderings
fail differently and only one of the failures is survivable: insert-then-send
can leave a ``sent`` row for an email that never went, which is a row nobody
will ever resolve and nothing worse; send-then-insert can put a real email in
front of a real parent with no record of it at all, which is permanently
unattributable when the webhook arrives quoting an id we never stored.

Why the send leg commits its own transaction and the webhook leg does not
------------------------------------------------------------------------
``start_parent_verification`` writes on a short-lived session of its own, the
same way ``security_audit.py`` does, rather than on the caller's request unit
of work. Ordering alone does not buy the property above: a row that is merely
flushed into the caller's transaction is rolled back if the caller lets the
send's ``ExternalServiceError`` propagate, and a 5xx or a transport failure
AFTER KWS accepted the request is exactly the case where the email goes out
anyway. Flushing would therefore delete the record of the one send most likely
to need it. Committing first makes the row survive any outcome of the caller's
request, which is what "insert before send" was always for.

``record_parent_verified`` is the opposite and shares the caller's session on
purpose: resolving an attempt SHOULD be atomic with the webhook request that
resolved it, so a receiver that fails after this call leaves the attempt
unresolved and lets KWS retry into it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cyo_adventure.consent.external_payload import (
    VerificationCorrelation,
    mint_correlation,
)
from cyo_adventure.consent.kws_client import KwsClient, VerificationEmailRequest
from cyo_adventure.core.config import settings
from cyo_adventure.core.database import get_session
from cyo_adventure.db.models import (
    KWS_VERIFICATION_STATUS_FAILED,
    KWS_VERIFICATION_STATUS_SENT,
    KWS_VERIFICATION_STATUS_VERIFIED,
    KwsVerification,
)
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class VerificationStartRequest:
    """Everything one verification attempt needs, bundled.

    A dataclass rather than four parameters: the guardian and the child's
    location are read from different places by any caller, and passing them
    positionally is how a location ends up in a language slot.

    Attributes:
        user_id: The guardian the attempt attributes to. Not the child.
        email: The parent or guardian's email address. Never persisted here
            and never logged; it goes to KWS and nowhere else.
        location: The CHILD's location as an ISO 3166-1 alpha-2 country code
            or an ISO 3166-2 subdivision code. It selects which verification
            methods the parent is offered, so it is a compliance input.
        language: The parent's language, for KWS's emails and web screens.
    """

    user_id: uuid.UUID
    email: str
    location: str
    language: str = "en"


@dataclass(frozen=True, slots=True)
class ParentVerifiedOutcome:
    """What an authenticated ``parent-verified`` delivery reports about us.

    Attributes:
        attempt_id: The attempt id parsed out of the delivery's
            ``externalPayload``. Untrusted until a row is found for it.
        verified: The delivery's ``status.verified`` flag.
        transaction_id: KWS's opaque id for the verification, when reported.
    """

    attempt_id: uuid.UUID
    verified: bool
    transaction_id: str | None


async def start_parent_verification(
    request: VerificationStartRequest,
    *,
    client: KwsClient | None = None,
) -> VerificationCorrelation:
    """Record a verification attempt, then ask KWS to email the parent.

    #CRITICAL: data integrity: the INSERT is COMMITTED, on its own session,
    BEFORE the outbound HTTP call, and neither the ordering nor the separate
    transaction may be collapsed for tidiness. Sending first can put a real
    email in front of a real parent with no row for the webhook to match, and
    KWS will not replay a delivery on request, so that attempt is
    unattributable forever. Merely flushing into the caller's unit of work
    reintroduces the same hole by a longer route: an ``ExternalServiceError``
    that propagates rolls the row back, and a 5xx or transport failure after
    KWS accepted the request is precisely when the email goes out regardless.
    The reverse failure, a ``sent`` row for an email that never went, costs one
    unresolved row. Note that this function takes no session for that reason,
    unlike its sibling below.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_the_row_is_committed_before_the_outbound_call and
    ::test_a_failed_send_leaves_the_row_committed.

    #EDGE: external resources: a failed send deliberately leaves the row
    ``sent`` rather than marking it ``failed``. ``sent`` means "unresolved",
    which is the truth: if KWS did deliver the email before failing us, the
    parent can still complete verification and the webhook still finds a row to
    resolve. Marking it ``failed`` here would record a false negative about a
    parent who went on to verify, and the resolution guard would then refuse
    the real answer.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_a_failed_send_leaves_the_attempt_unresolved.

    Args:
        request: The guardian, the email, the child's location, the language.
        client: An optional long-lived ``KwsClient``. Omitted, a fresh one is
            built per call, which re-authenticates once per verification: fine
            at one verification per guardian, worth injecting a shared instance
            if that ever stops being true (the token endpoint is behind a
            rate-limiting WAF).

    Returns:
        VerificationCorrelation: The attempt token handed to KWS, which is also
            the row's primary key. A plain value rather than the ORM instance,
            because that instance belongs to a session this function closes.

    Raises:
        ConfigurationError: When the KWS integration is not configured.
        ValidationError: When the request would be rejected by KWS.
        ExternalServiceError: When KWS rejects or fails the call.
    """
    correlation = mint_correlation()
    async with get_session() as session:
        session.add(
            KwsVerification(
                id=correlation.attempt_id,
                user_id=request.user_id,
                kws_environment=settings.kws_environment,
                status=KWS_VERIFICATION_STATUS_SENT,
                requested_at=datetime.now(UTC),
                # list(...) rather than the settings list itself: a shared
                # reference would make this row's evidence mutate with the
                # setting, which is the exact retroactivity the snapshot exists
                # to prevent.
                enabled_methods=list(settings.kws_enabled_methods),
            )
        )
        await session.commit()

    logger.info(
        "kws_verification_recorded",
        attempt_id=str(correlation.attempt_id),
        kws_environment=settings.kws_environment,
        kws_environment_label=settings.kws_environment_label,
        enabled_methods=list(settings.kws_enabled_methods),
    )

    sender = client if client is not None else KwsClient()
    await sender.send_verification_email(
        VerificationEmailRequest(
            email=request.email,
            location=request.location,
            language=request.language,
        ),
        correlation=correlation,
    )
    return correlation


async def record_parent_verified(
    session: AsyncSession, outcome: ParentVerifiedOutcome
) -> bool:
    """Resolve the attempt a ``parent-verified`` delivery refers to.

    #CRITICAL: data integrity: KWS retries deliveries, so this must be
    idempotent. Two guards make it so. The attempt id is the PRIMARY KEY, so a
    replay can never fan out into a second row; and the row is loaded
    ``FOR UPDATE`` and only written while it is still ``sent``, so a second
    delivery (or a simultaneous one on another worker) leaves the first
    resolution's ``resolved_at`` and ``transaction_id`` exactly as they were
    rather than overwriting them with a later clock reading.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_a_replayed_delivery_does_not_rewrite_the_resolution and
    ::test_the_row_is_locked_for_update_before_it_is_resolved.

    #CRITICAL: security: the attempt id arrives from a third party and is only
    ever a lookup key. Finding no row, or finding one from the other KWS
    environment, is answered as "not ours" rather than as an error: a non-2xx
    would only buy a retry loop against a decision that cannot change, and a
    Test-environment row must never be resolved by a production delivery or
    vice versa, since that column is the only thing separating sandbox noise
    from evidence about a real parent.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_an_unknown_attempt_id_is_not_handled and
    ::test_a_delivery_from_the_other_environment_is_not_handled.

    Args:
        session: The caller's session. This function never commits it.
        outcome: The attempt id, the verified flag, and the transaction id.

    Returns:
        bool: True when the delivery was ours, including the replay case where
            it changed nothing. False when no row matched, which is what the
            receiver reports as ``handled=False``.
    """
    record = await session.get(
        KwsVerification, outcome.attempt_id, with_for_update=True
    )
    if record is None:
        logger.warning(
            "kws_verification_unknown_attempt",
            attempt_id=str(outcome.attempt_id),
            kws_environment=settings.kws_environment,
        )
        return False

    if record.kws_environment != settings.kws_environment:
        logger.warning(
            "kws_verification_environment_mismatch",
            attempt_id=str(outcome.attempt_id),
            record_environment=record.kws_environment,
            kws_environment=settings.kws_environment,
        )
        return False

    if record.status != KWS_VERIFICATION_STATUS_SENT:
        logger.info(
            "kws_verification_already_resolved",
            attempt_id=str(outcome.attempt_id),
            status=record.status,
            kws_environment=record.kws_environment,
        )
        return True

    record.status = (
        KWS_VERIFICATION_STATUS_VERIFIED
        if outcome.verified
        else KWS_VERIFICATION_STATUS_FAILED
    )
    record.resolved_at = datetime.now(UTC)
    record.transaction_id = outcome.transaction_id
    logger.info(
        "kws_verification_resolved",
        attempt_id=str(outcome.attempt_id),
        status=record.status,
        transaction_id=outcome.transaction_id,
        kws_environment=record.kws_environment,
    )
    return True
