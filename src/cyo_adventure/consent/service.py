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
from typing import TYPE_CHECKING, Literal

from sqlalchemy import func, select

from cyo_adventure.consent.external_payload import (
    VerificationCorrelation,
    mint_correlation,
)
from cyo_adventure.consent.kws_client import KwsClient, VerificationEmailRequest
from cyo_adventure.core.config import settings
from cyo_adventure.core.database import get_session
from cyo_adventure.db.models import (
    KWS_ENVIRONMENT_TEST,
    KWS_VERIFICATION_STATUS_FAILED,
    KWS_VERIFICATION_STATUS_SENT,
    KWS_VERIFICATION_STATUS_VERIFIED,
    KwsVerification,
)
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection

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
                # Recorded for the same reason the method list is: it is what
                # decided which methods KWS offered this parent, and no later
                # read of the vendor's API can recover it.
                location=request.location,
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


async def usable_verification_id(
    session: AsyncSession, user_ids: Collection[uuid.UUID]
) -> uuid.UUID | None:
    """Return the id of a verification worth relying on, for any of these adults.

    "Usable" is a narrower question than "verified", and the gap is the whole
    reason this function exists rather than a ``status == 'verified'`` filter
    written inline at each call site. Three things have to hold: the attempt
    resolved as verified, it ran against the KWS environment this process is
    configured for, and that environment is one whose verifications this
    deployment is willing to treat as evidence.

    Plural ``user_ids`` because the callers ask about different sets. The
    guardian-facing gate asks about one adult, the caller themselves; the admin
    gate asks about the target family's adults, since 16 CFR 312.5(a)(1) poses
    the question of the child's parent, not of whoever is typing.

    The id, rather than a bool, because ``api/onboarding.py::_record_consent``
    stamps it onto the consent record it writes. Both shapes come from this one
    function so that the refusal below cannot apply to the gates and not to the
    evidence link, which would be the worst combination: a record naming a
    sandbox verification as the thing that corroborated it.

    #CRITICAL: security: a ``test`` verification is a sandbox event about
    whoever happened to click the link, not evidence about a real parent, and
    the KWS API reports nothing that would let the two be told apart after the
    fact. The refusal is therefore evaluated FIRST and returns before the query
    runs, so there is no ordering of the remaining conditions in which a Test
    row can be read as evidence. It is also keyed on ``kws_environment``, never
    on ``settings.environment``: staging declares ``ENVIRONMENT=production``,
    so an ``environment == "local"``-shaped guard is inert on every deployed
    tier and would be a control in name only.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_a_test_environment_verification_is_not_usable_by_default and
    ::test_the_test_refusal_never_reaches_the_database.

    Args:
        session: The caller's session. This function only reads.
        user_ids: The adults to consider. Empty means none, without a query.

    Returns:
        uuid.UUID | None: The most recently resolved usable attempt, or None
            when there is none.
    """
    if (
        settings.kws_environment == KWS_ENVIRONMENT_TEST
        and not settings.kws_accept_test_evidence
    ):
        logger.info(
            "kws_test_evidence_refused",
            kws_environment=settings.kws_environment,
            kws_environment_label=settings.kws_environment_label,
        )
        return None
    if not user_ids:
        return None

    # kws_environment is filtered here as well as being gated above, so the
    # other direction is closed too: a production-configured process must not
    # count a leftover Test row from before the cutover.
    return await session.scalar(
        select(KwsVerification.id)
        .where(
            KwsVerification.user_id.in_(user_ids),
            KwsVerification.status == KWS_VERIFICATION_STATUS_VERIFIED,
            KwsVerification.kws_environment == settings.kws_environment,
        )
        # Most recent first, so a guardian who verified again after an earlier
        # attempt is corroborated by the attempt they actually just completed.
        .order_by(KwsVerification.resolved_at.desc())
        .limit(1)
    )


async def has_usable_verification(
    session: AsyncSession, user_ids: Collection[uuid.UUID]
) -> bool:
    """Report whether any of these adults holds a verification worth relying on.

    The gate-shaped face of ``usable_verification_id``; see that function for
    what "usable" means and why the test-environment refusal runs first.

    Args:
        session: The caller's session. This function only reads.
        user_ids: The adults to consider.

    Returns:
        bool: True when at least one of ``user_ids`` has a usable verification.
    """
    return await usable_verification_id(session, user_ids) is not None


async def open_attempt_started_at(
    session: AsyncSession, user_id: uuid.UUID
) -> datetime | None:
    """Return when this adult's most recent unresolved attempt was sent.

    An unresolved attempt is one still in ``sent``: KWS was asked to email the
    parent and has told us nothing since. The function reports the fact and
    applies no policy to it, because its two callers want different policies
    from the same fact. ``api/consent.py`` refuses a fresh send while the
    attempt is recent, so a double-click cannot mail a parent twice;
    ``api/me.py`` reports a pending state for an attempt of any age, because
    an attempt that was never resolved genuinely is still outstanding and the
    screen that says so is what offers the parent a resend.

    #ASSUME: security: the ``test``-evidence refusal that guards
    ``usable_verification_id`` deliberately does NOT apply here, and its
    absence is a decision rather than an oversight. That refusal is about what
    counts as EVIDENCE about a real parent; an open attempt is not evidence,
    it is an email in flight, and a Test-environment email reaches a real
    mailbox exactly as a production one does. Suppressing it here would make
    the send guard inert on the one tier that runs against Test.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_an_open_attempt_is_reported_even_when_test_evidence_is_refused.

    Args:
        session: The caller's session. This function only reads.
        user_id: The adult whose attempts to consider.

    Returns:
        datetime | None: The ``requested_at`` of the most recent unresolved
            attempt in the current KWS environment, or None when there is
            none.
    """
    return await session.scalar(
        select(KwsVerification.requested_at)
        .where(
            KwsVerification.user_id == user_id,
            KwsVerification.status == KWS_VERIFICATION_STATUS_SENT,
            KwsVerification.kws_environment == settings.kws_environment,
        )
        .order_by(KwsVerification.requested_at.desc())
        .limit(1)
    )


async def attempts_since(
    session: AsyncSession, user_id: uuid.UUID, since: datetime
) -> int:
    """Count this adult's verification attempts started at or after ``since``.

    #CRITICAL: security: this is the counter behind the per-account send cap,
    and it counts attempts of EVERY status and every KWS environment on
    purpose. A failed attempt still sent an email, so excluding it would let a
    caller loop on failures without limit; and an environment filter would
    reset the cap for anyone who could influence which environment a row was
    written under. The table is the counter precisely because rows are
    inserted before the send and never deleted, so nothing a caller does
    lowers this number.
    #VERIFY: tests/integration/test_consent_api.py::
    test_a_failed_attempt_still_counts_against_the_hourly_cap.

    Args:
        session: The caller's session. This function only reads.
        user_id: The adult whose attempts to count.
        since: The inclusive lower bound on ``requested_at``.

    Returns:
        int: The number of attempts started in the window.
    """
    counted = await session.scalar(
        select(func.count())
        .select_from(KwsVerification)
        .where(
            KwsVerification.user_id == user_id,
            KwsVerification.requested_at >= since,
        )
    )
    return counted or 0


# Three values rather than a bool: "no attempt" and "an attempt nobody has
# resolved" need different screens, the first offering a start button and the
# second a wait-and-resend state. Declared here rather than in api/schemas.py
# so the wire contract and the function that computes it cannot drift apart.
VerificationStatus = Literal["verified", "pending", "none"]


async def verification_status(
    session: AsyncSession, user_id: uuid.UUID
) -> VerificationStatus:
    """Report where one adult stands in the verification flow.

    ``"verified"`` outranks ``"pending"``: an adult who verified and then
    started another attempt is verified, and reporting them as pending would
    send a client that trusts this field to a wait screen they can never
    leave.

    This is a display fact, never an enforcement one. The gates in
    ``api/profiles.py`` and ``api/admin_profiles.py`` re-derive what they need
    from the database at the point of use, so a client that ignores this value
    loses a screen, not a control.

    Args:
        session: The caller's session. This function only reads.
        user_id: The adult to report on.

    Returns:
        VerificationStatus: ``"verified"``, ``"pending"``, or ``"none"``.
    """
    if await has_usable_verification(session, (user_id,)):
        return "verified"
    if await open_attempt_started_at(session, user_id) is not None:
        return "pending"
    return "none"


async def reportable_verification_status(
    session: AsyncSession, user_id: uuid.UUID
) -> VerificationStatus:
    """Report verification state the way a client-facing surface should read it.

    Wraps :func:`verification_status` with the deployment-level question the
    pure fact deliberately ignores: does this tier run verification at all.
    With ``kws_verification_required`` off there is no verification screen to
    route anyone to, so every adult reads ``"none"`` regardless of what rows
    exist. A tier that ran verification and later switched it off therefore
    stops advertising the state instead of pointing clients at a flow that no
    longer gates anything.

    Two surfaces need this same answer and they see different callers:
    ``GET /v1/me`` serves an approved adult, and ``POST /v1/onboarding``
    serves the one who is not approved yet and whom ``require_principal``
    refuses. Sharing one function is what stops those two answers drifting
    apart while a guardian moves between them.

    Args:
        session: The caller's session. This function only reads.
        user_id: The adult to report on.

    Returns:
        VerificationStatus: ``"none"`` whenever the flag is off; otherwise
        whatever :func:`verification_status` derives.
    """
    if not settings.kws_verification_required:
        return "none"
    return await verification_status(session, user_id)
