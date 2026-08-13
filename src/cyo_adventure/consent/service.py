"""The persistence seam between the KWS legs and ``kws_verification``.

``consent/kws_client.py`` is pure HTTP and stays that way: it knows how to talk
to KWS and nothing about our database. ``api/kws_webhook.py`` is a receiver and
stays that way too. This module is where the two meet a row, so neither of them
has to grow a second responsibility.

Ordering, which is the whole point
----------------------------------
The record is INSERTed before the outbound send, never after. The two orderings
fail differently and only one of the failures is survivable: insert-then-send
can leave a row for an email that never went, which the send's own error
handler closes out as ``send_failed``; send-then-insert can put a real email in
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
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from cyo_adventure.consent.external_payload import (
    VerificationCorrelation,
    mint_correlation,
)
from cyo_adventure.consent.kws_client import KwsClient, VerificationEmailRequest
from cyo_adventure.core.config import settings
from cyo_adventure.core.database import get_session
from cyo_adventure.core.exceptions import ProjectBaseError
from cyo_adventure.db.models import (
    KWS_ENVIRONMENT_TEST,
    KWS_VERIFICATION_DELIVERED_STATUSES,
    KWS_VERIFICATION_STATUS_FAILED,
    KWS_VERIFICATION_STATUS_SEND_FAILED,
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
        location: The GUARDIAN's own location as an ISO 3166-1 alpha-2 country code
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

    #CRITICAL: external resources: a failed send resolves the row to
    ``send_failed``, and the status is a THIRD value rather than ``failed`` on
    purpose. ``failed`` is KWS's answer about a parent; ``send_failed`` is our
    own outbound leg giving up and says nothing about the parent at all.
    Writing ``failed`` here would record a refusal nobody ever gave, and would
    make the delivery-health alarm read our own timeout handler as proof the
    inbound leg works. Leaving it ``sent``, which is what this used to do, is
    the opposite error: ``sent`` is what the resend guard treats as an email in
    flight, so a guardian whose send failed outright was locked out of retrying
    for the full cooldown on account of an email that never left.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_a_failed_send_resolves_the_attempt_as_send_failed, and
    tests/integration/test_consent_api.py::
    test_a_send_failure_does_not_block_an_immediate_retry for the guardian-
    visible half (the retry is accepted rather than 409'd).

    #EDGE: external resources: ``send_failed`` is not final against a later
    delivery. A 5xx or a timeout can arrive after KWS already accepted the
    request and mailed the parent, so :func:`record_parent_verified` still
    resolves a ``send_failed`` row when a real delivery quotes it. Refusing
    that would discard a genuine verification of a real adult on the strength
    of our own transport error.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_a_delivery_still_resolves_an_attempt_whose_send_failed.

    Args:
        request: The guardian, the email, the guardian's own location, the language.
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
        ConfigurationError: When the KWS integration is not configured, or
            when KWS rejects our credentials or blocks the request. Both are
            operator-fixable; either way the attempt is still closed out as
            ``send_failed`` first, because the ``except ProjectBaseError``
            below is deliberately wider than the send's own error class.
        ValidationError: When the request would be rejected by KWS.
        ExternalServiceError: When the call fails in a way that may clear on
            its own (5xx, timeout, transport failure, rate limit).
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
    try:
        await sender.send_verification_email(
            VerificationEmailRequest(
                email=request.email,
                location=request.location,
                language=request.language,
            ),
            correlation=correlation,
        )
    except ProjectBaseError:
        await _resolve_as_send_failed(correlation.attempt_id)
        raise
    return correlation


async def _resolve_as_send_failed(attempt_id: uuid.UUID) -> None:
    """Close out an attempt whose outbound send raised.

    On its own session for the same reason the INSERT was: the caller is about
    to let the send's error propagate, and a write flushed into the caller's
    unit of work would be rolled back by exactly the failure it exists to
    record.

    #CRITICAL: external resources: this must never replace the caller's
    exception. The send error is what the endpoint turns into the status code
    a guardian sees; a database failure while tidying up would otherwise
    surface in its place and describe the wrong outage entirely. A failure here
    is therefore logged and swallowed, and the cost of swallowing it is one row
    left ``sent``, which is exactly the state this function is an improvement
    on rather than a prerequisite for.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_a_bookkeeping_failure_does_not_mask_the_send_error.

    Args:
        attempt_id: The attempt whose send failed.
    """
    try:
        async with get_session() as session:
            record = await session.get(
                KwsVerification, attempt_id, with_for_update=True
            )
            # Only a still-open row is ours to close. A delivery that beat us
            # here has said something true about the parent, and this function
            # knows nothing that outranks it.
            if record is None or record.status != KWS_VERIFICATION_STATUS_SENT:
                return
            record.status = KWS_VERIFICATION_STATUS_SEND_FAILED
            record.resolved_at = datetime.now(UTC)
            await session.commit()
            logger.info(
                "kws_verification_send_failed",
                attempt_id=str(attempt_id),
                kws_environment=settings.kws_environment,
            )
    except SQLAlchemyError as exc:
        logger.warning(
            "kws_verification_send_failure_not_recorded",
            attempt_id=str(attempt_id),
            error=str(exc),
        )


async def record_parent_verified(
    session: AsyncSession, outcome: ParentVerifiedOutcome
) -> bool:
    """Resolve the attempt a ``parent-verified`` delivery refers to.

    #CRITICAL: data integrity: KWS retries deliveries, so this must be
    idempotent. Two guards make it so. The attempt id is the PRIMARY KEY, so a
    replay can never fan out into a second row; and the row is loaded
    ``FOR UPDATE`` and only written while no delivery has resolved it yet, so a
    second delivery (or a simultaneous one on another worker) leaves the first
    resolution's ``resolved_at`` and ``transaction_id`` exactly as they were
    rather than overwriting them with a later clock reading.

    The guard is an ALLOWLIST of statuses a delivery has already answered
    (``KWS_VERIFICATION_DELIVERED_STATUSES``), not ``status != 'sent'``.
    ``send_failed`` is the difference: our outbound call can fail after KWS
    already accepted the request and mailed the parent, so a delivery quoting
    such an attempt is a real answer about a real adult, and a ``!= 'sent'``
    guard would discard it on the strength of our own transport error.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_a_replayed_delivery_does_not_rewrite_the_resolution,
    ::test_the_row_is_locked_for_update_before_it_is_resolved and
    ::test_a_delivery_still_resolves_an_attempt_whose_send_failed.

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

    if record.status in KWS_VERIFICATION_DELIVERED_STATUSES:
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

    #CRITICAL: security: this is what ``api/profiles.py::_require_consent`` and
    ``api/admin_profiles.py::_require_family_consent`` ask before letting an
    adult create a child profile, so a wrong True is the failure that matters.
    It delegates the whole decision rather than re-deriving any part of it,
    which is the point: the ``test``-evidence refusal and the
    ``kws_environment`` scoping cannot end up applied on the id-shaped face and
    missing from the gate-shaped one. Do not inline the query here.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_a_test_environment_verification_is_not_usable_by_default and
    ::test_the_query_is_scoped_to_the_configured_environment both drive the
    refusal and the scoping THROUGH this function, not through
    ``usable_verification_id``, so inlining would break them.

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


@dataclass(frozen=True, slots=True)
class VerificationDeliveryHealth:
    """When the stuck attempts were sent, and when the leg last proved itself.

    The two timestamps are the alarm; the count is for the operator reading
    it. They come back in one object and one query because comparing them is
    the whole measurement. See :func:`verification_delivery_health`.

    Attributes:
        stuck: Attempts still in ``sent`` whose ``requested_at`` is older than
            the caller's staleness threshold. Reported, not tested against:
            one stuck attempt and fifty are the same verdict.
        oldest_stuck_requested_at: When the oldest of those was sent, or None
            when ``stuck`` is 0. Reported so an alert can say how long the
            longest-waiting parent has been waiting.
        newest_stuck_requested_at: When the most recent of those was sent, or
            None when ``stuck`` is 0. This is the discriminating one: see
            :attr:`deliveries_have_stopped`.
        last_resolved_at: The most recent ``resolved_at`` in this environment,
            verified or failed alike, or None when nothing has ever resolved.
            A ``failed`` resolution is still a delivery that reached us, which
            is exactly what this is evidence of.
    """

    stuck: int
    oldest_stuck_requested_at: datetime | None
    newest_stuck_requested_at: datetime | None
    last_resolved_at: datetime | None

    @property
    def deliveries_have_stopped(self) -> bool:
        """Whether the inbound leg looks broken rather than merely quiet.

        The question is answered by ordering two timestamps: did anything
        come back AFTER the most recent attempt that is still waiting.

        - Nothing stuck: no attempt has been outstanding long enough to be
          evidence of anything, so there is no alarm to raise.
        - Something stuck, and a delivery landed after it was sent: the leg
          demonstrably works, and what is outstanding is a parent who has not
          acted yet. Ordinary abandonment lives here.
        - Something stuck, and nothing has come back since it was sent: the
          leg has had a chance to prove itself and has not. That is the
          alarm.

        #CRITICAL: external resources: the anchor is the NEWEST stuck attempt,
        not the oldest, and the difference is a masked outage rather than a
        style choice. One abandoned attempt from months ago stays the oldest
        stuck row forever; anchoring on it would mean every resolution since
        then reads as "the leg works", so a fresh outage arriving today would
        be answered by evidence from months ago and never alarm. Anchoring on
        the newest makes the freshest waiting attempt the thing the leg has to
        answer for.
        #VERIFY: tests/unit/test_kws_verification_service.py::
        TestVerificationDeliveryHealth::
        test_an_old_abandoned_row_does_not_mask_a_fresh_outage.

        Note what this deliberately does NOT exclude: a single abandoned
        attempt on a tier with no other traffic keeps alarming, because on
        the evidence available that state is indistinguishable from a broken
        leg. The predecessor of this rule excluded it by also requiring fresh
        sends, and the price was silence during exactly the outage this
        exists to catch: a blocked inbound leg suppresses the sends that
        would have satisfied that term, so the quieter the tier, the less
        the alarm worked. The remedy for the noise is to resolve the row,
        not to widen the rule until it stops speaking.
        """
        newest_stuck = self.newest_stuck_requested_at
        if newest_stuck is None:
            return False
        return self.last_resolved_at is None or self.last_resolved_at < newest_stuck


async def verification_delivery_health(
    session: AsyncSession,
    *,
    stuck_after: timedelta,
) -> VerificationDeliveryHealth:
    """Measure whether KWS deliveries are still reaching us at all.

    #CRITICAL: external resources: this exists because the failure it watches
    for produces NO log line to alert on. On 2026-08-09 a Cloudflare custom
    rule blocked four KWS webhook retries at the edge; the origin recorded
    zero POSTs, so every log-based check read exactly like a period in which
    KWS had simply not sent anything. The only trace such an outage leaves in
    this system is rows that stay ``sent``, which is why the alarm has to be a
    query over the table rather than a rule over the logs.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    TestVerificationDeliveryHealth covers the healthy, stopped, masking and
    quiet cases; api/health.py::check_kws_verification publishes it.

    There is no lookback window, on purpose. A window bounds how far back the
    evidence may come from, and the evidence that matters here is the single
    most recent resolution however old it is: if the last thing KWS delivered
    was six weeks ago and an attempt has been waiting since yesterday, the
    leg has not answered, and a 24-hour window would have reported that as
    "quiet" rather than as the outage it is.

    Scoped to ``settings.kws_environment``, matching
    :func:`open_attempt_started_at`: each deployment watches the environment
    it is itself configured for, so staging's Test rows never mask or inflate
    production's, and the two tiers alarm independently.

    #CRITICAL: data-integrity: the resolution term is an ALLOWLIST of the two
    statuses a delivery produces, not "``resolved_at`` is not null".
    ``send_failed`` also carries a ``resolved_at`` (the pairing CHECK gives it
    no choice), and that timestamp records our own outbound call giving up.
    Counting it would let a broken inbound leg be vouched for by the very
    timeout handler that ran because nothing was working, which is the exact
    blindness this alarm exists to remove.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_a_send_failure_is_not_counted_as_a_delivery;
    tests/unit/test_kws_verification_model.py::
    test_resolution_pairing_is_constrained_at_rest pins the CHECK that forces
    the overload.

    Args:
        session: The caller's session. This function only reads.
        stuck_after: How old an unresolved attempt must be to count as stuck.

    Returns:
        VerificationDeliveryHealth: The count and the three timestamps, in one
        round trip.
    """
    stuck_cutoff = datetime.now(UTC) - stuck_after
    is_stuck = (
        KwsVerification.status == KWS_VERIFICATION_STATUS_SENT,
        KwsVerification.requested_at < stuck_cutoff,
    )
    result = await session.execute(
        select(
            func.count().filter(*is_stuck).label("stuck"),
            func.min(KwsVerification.requested_at).filter(*is_stuck).label("oldest"),
            func.max(KwsVerification.requested_at).filter(*is_stuck).label("newest"),
            func.max(KwsVerification.resolved_at)
            .filter(KwsVerification.status.in_(KWS_VERIFICATION_DELIVERED_STATUSES))
            .label("last_resolved"),
        )
        .select_from(KwsVerification)
        .where(KwsVerification.kws_environment == settings.kws_environment)
    )
    row = result.one()
    return VerificationDeliveryHealth(
        stuck=int(row.stuck or 0),
        oldest_stuck_requested_at=row.oldest,
        newest_stuck_requested_at=row.newest,
        last_resolved_at=row.last_resolved,
    )


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

    #ASSUME: concurrency: the two reads below are separate statements, so the
    pair is not a snapshot. A webhook that resolves the attempt between them
    makes the first read miss the resolution and the second miss the open
    attempt, and this function briefly answers ``"none"`` for an adult who is
    in fact verified. That interleaving is tolerable ONLY because this is a
    display fact: the caller re-polls, and the gates named above never consult
    it. Widening this to an enforcement value would make that window a hole.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_verified_outranks_an_open_attempt pins the ordering; the window itself
    is accepted, not defended against.

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

    #CRITICAL: security: this function answers ``"none"`` for EVERY adult while
    ``kws_verification_required`` is off, including adults who really did
    verify. It is therefore unusable as a control by construction, and nothing
    may gate on it: an authorization check written against this value would
    read "not verified" and "this tier does not ask" as the same answer, which
    is exactly the collapse the flag exists to avoid. Enforcement asks
    ``has_usable_verification``; ``verification_required`` ships beside this
    value on both responses so a client can tell the two cases apart.
    #VERIFY: tests/unit/test_kws_verification_service.py::
    test_the_flag_being_off_suppresses_the_state_entirely.

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
