"""The parent-facing start of KWS verification (ADR-018 D1).

``POST /api/v1/consent/kws/start`` is the one leg of the Parent Verification
Service a browser calls. The other two are inbound: ``api/kws_webhook.py``
receives the server-to-server result, and ``api/kws_redirect.py`` shows the
parent a page when they return. Only the webhook resolves an attempt.

Why this endpoint does not use ``Context``
------------------------------------------
It authenticates with ``OnboardingIdentityDep``, the same dependency
``api/onboarding.py`` uses, rather than the ``Context`` every other guardian
route uses. That is forced by the ratified order of the sign-in sequence:
verification sits BEFORE admin approval, and ``api/deps.py::require_principal``
refuses any user whose status is not ``active``. A guardian awaiting approval
is precisely the caller this endpoint exists for, so a dependency that
requires an active principal would make the endpoint unreachable by everyone
who needs it. The identity is still a fully verified token; what is relaxed is
the account-status requirement, not the authentication.

What bounds the abuse
---------------------
The endpoint causes an outbound email to a real person, so it carries three
independent bounds rather than relying on the app-wide per-IP limiter, which
is far too loose to protect a mailbox and cannot see who is calling:

1. The recipient is never caller-supplied. It comes from the verified token's
   email claim, falling back to the address already recorded on the caller's
   own ``User`` row. There is no body field for it, so the endpoint cannot be
   pointed at a third party at all.
2. An unresolved attempt blocks a fresh send for ``kws_open_attempt_minutes``,
   so a double-click or a retry loop cannot mail one parent repeatedly.
3. A rolling-hour cap per account, counted from the ``kws_verification`` table
   itself. Rows are inserted before the send and never deleted, so the count
   is exact, shared across replicas, and survives a restart.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import DbSession, OnboardingIdentityDep
from cyo_adventure.api.schemas import (
    KwsVerificationStartBody,
    KwsVerificationStartView,
    error_responses,
)
from cyo_adventure.consent import (
    VerificationStartRequest,
    attempts_since,
    open_attempt_started_at,
    start_parent_verification,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ConfigurationError,
    RateLimitedError,
    StateTransitionError,
)
from cyo_adventure.db.models import KWS_VERIFICATION_STATUS_SENT, User
from cyo_adventure.utils.logging import get_logger

logger = get_logger(__name__)

# The account states that may cause a verification email.
#
# `require_principal` answers this question with `!= "active"`, but this
# endpoint cannot use it (see the module docstring): verification sits BEFORE
# admin approval, so refusing a non-active caller would make the endpoint
# unreachable by the very guardians it exists for. Relaxing that requirement
# has to be a narrowing, not a removal, and the two states below are the only
# ones with a legitimate reason to send: 'active' for a re-verification, and
# 'awaiting_approval' for the first-time self-signup case the endpoint was
# built around.
#
# #CRITICAL: security: written as an allowlist rather than a
# `!= "deactivated"` denylist so a state added to db/models.py's
# _USER_STATUS_VALUES is refused here until somebody deliberately admits it.
# The reachable exclusion is 'deactivated': app-level deactivation does not
# revoke the Supabase JWT, so a revoked guardian holding a live token would
# otherwise still be able to mail a real person in our organization's name,
# spend the hourly cap, and hold the open-attempt window. The two invite
# states carry a synthetic placeholder authn_subject that no verified subject
# matches, so excluding them is defense in depth rather than a live hole.
# #VERIFY: tests/integration/test_consent_api.py::
# test_a_deactivated_guardian_cannot_start_a_verification and
# ::test_a_guardian_awaiting_approval_can_start_a_verification.
_VERIFICATION_ELIGIBLE_STATUSES = ("active", "awaiting_approval")

router = APIRouter(
    prefix="/api/v1/consent", tags=["consent"], responses=error_responses(401)
)


@router.post(
    "/kws/start",
    status_code=202,
    responses=error_responses(400, 403, 409, 429, 502),
)
async def start_kws_verification(
    body: KwsVerificationStartBody,
    identity: OnboardingIdentityDep,
    session: DbSession,
) -> KwsVerificationStartView:
    """Ask KWS to email this adult a parent-verification link.

    202 rather than 201: what the request achieves is an attempt in flight,
    not a verified parent. The attempt is resolved later, and only ever by the
    webhook.

    Args:
        body: The parent's location and language. Deliberately carries no
            email address; see the module docstring.
        identity: The verified token identity. Does not require an active
            account, because verification precedes admin approval.
        session: The request unit of work. Used for the caller lookup and the
            two limit reads only; the attempt row itself is written on a
            separate committed session inside ``start_parent_verification``.

    Returns:
        KwsVerificationStartView: The attempt id and when it was started.

    Raises:
        ConfigurationError: If KWS is not configured on this tier (400).
        BusinessLogicError: If the caller has no ``User`` row yet, or no email
            address to send to (400).
        AuthorizationError: If the caller is a child account, or the account
            is in a state that may not send (403).
        StateTransitionError: If an unresolved attempt is still recent (409).
        RateLimitedError: If the caller's hourly attempt cap is spent (429).
        ExternalServiceError: If KWS rejects or fails the outbound send, or
            the call times out (502). Unlike the four refusals above, this
            one clears on its own, and the closed-out `send_failed` row lets
            an immediate retry through (UW-A55).
    """
    # Checked before anything is written, so an unconfigured tier cannot leave
    # a `sent` row behind for an email that was never sendable. kws_client.py
    # raises the same error, but only after start_parent_verification has
    # already committed the row.
    if not settings.kws_configured:
        msg = (
            "parent verification is not configured on this deployment; "
            "no verification email can be sent"
        )
        raise ConfigurationError(msg)

    # #CRITICAL: security: credential presence is NOT the control. This
    # endpoint discloses an adult's email address to Epic (ADR-018 D1, O-125),
    # and the flag that decides whether this tier runs verification at all is
    # kws_verification_required, so that is what has to gate it. Gating on
    # kws_configured alone left the endpoint live on any tier that merely held
    # credentials, including one where nothing depends on the answer.
    #
    # kws_allow_start_while_not_required is the single, separately-named,
    # separately-auditable escape that lets staging exercise this endpoint and
    # the screens in front of it while the gate is still off. The Gate 1
    # procedure itself does not need it: scripts/kws_send_test_verification.py
    # calls start_parent_verification directly and never reaches here.
    # config.py refuses that variable outright against Production KWS, so the
    # override cannot widen the production endpoint even if it is set there.
    # #VERIFY: tests/integration/test_consent_api.py::
    # test_start_is_refused_while_verification_is_not_required and
    # ::test_the_test_plan_override_re_opens_start_while_not_required.
    if not (
        settings.kws_verification_required
        or settings.kws_allow_start_while_not_required
    ):
        msg = (
            "parent verification is not in use on this deployment; "
            "no verification email can be sent"
        )
        raise ConfigurationError(msg)

    # #CRITICAL: concurrency: the caller's own row is locked, which is what
    # makes the two limit checks below mean anything. Without it, two requests
    # arriving together both read a count of zero and both send, so the cap
    # bounds nothing at its most useful moment. The lock is held until the
    # request unit of work commits, and it is taken on `user`, a table the
    # webhook leg never writes, so it cannot delay resolving an attempt.
    #
    # key_share=True emits FOR NO KEY UPDATE, NOT FOR UPDATE, and the
    # difference is the whole endpoint. start_parent_verification writes the
    # attempt row on a SEPARATE transaction, and that INSERT's foreign key to
    # `user` makes PostgreSQL take FOR KEY SHARE on this very row. FOR UPDATE
    # conflicts with FOR KEY SHARE, so the request would block forever on a
    # lock its own outer transaction holds; FOR NO KEY UPDATE does not, while
    # still conflicting with itself, which is the mutual exclusion we need.
    # #VERIFY: tests/integration/test_consent_api.py::
    # test_two_concurrent_starts_do_not_both_send (mutual exclusion) and
    # ::test_a_start_sends_once_and_records_one_attempt (no self-deadlock;
    # it hangs outright under a plain FOR UPDATE).
    user = (
        await session.scalars(
            select(User)
            .where(User.authn_subject == identity.subject)
            .with_for_update(key_share=True)
        )
    ).one_or_none()
    if user is None:
        msg = (
            "complete account setup (POST /onboarding) before starting "
            "parent verification"
        )
        raise BusinessLogicError(msg, rule="vpc_no_account")
    # #CRITICAL: security: a child account must never start a parent
    # verification for itself. require_onboarding_identity already refuses a
    # child session token by audience, so this is the second, role-based
    # gate behind it, covering any adult-audience token that nonetheless
    # resolves to a child row.
    # #VERIFY: tests/integration/test_consent_api.py::
    # test_a_child_row_cannot_start_a_verification.
    if user.role == "child":
        msg = "a child account cannot start a parent verification"
        raise AuthorizationError(msg)
    # See _VERIFICATION_ELIGIBLE_STATUSES: the endpoint relaxes
    # require_principal's active-only rule to admit a guardian awaiting
    # approval, and this keeps that relaxation from also admitting a
    # deactivated one. Refusing here rather than at the dependency keeps the
    # message specific to the caller's own account, which they already know
    # exists, so no status oracle is created for a third party.
    if user.status not in _VERIFICATION_ELIGIBLE_STATUSES:
        msg = "this account cannot start a parent verification"
        raise AuthorizationError(msg)

    # #CRITICAL: security: the recipient is never caller-supplied. The live
    # verified token claim is preferred over the stored copy because a parent
    # who changed their sign-in address controls the new one and may no longer
    # read the old; both are issued by the identity provider, so neither is
    # attacker-chosen. KwsVerificationStartBody has no email field at all, so
    # there is no path by which a request body reaches this variable.
    # #VERIFY: tests/integration/test_consent_api.py::
    # test_the_body_cannot_choose_the_recipient.
    email = identity.email or user.email
    if not email:
        msg = (
            "no email address is on file for this account, so no "
            "verification email can be sent"
        )
        raise BusinessLogicError(msg, rule="vpc_no_email")

    now = datetime.now(UTC)
    started_at = await open_attempt_started_at(session, user.id)
    open_window = timedelta(minutes=settings.kws_open_attempt_minutes)
    if started_at is not None and started_at >= now - open_window:
        msg = (
            "a verification email was already sent and is still awaiting a "
            "response; check the inbox, or try again shortly"
        )
        raise StateTransitionError(msg, rule="kws_attempt_already_open")

    attempts = await attempts_since(session, user.id, now - timedelta(hours=1))
    if attempts >= settings.kws_start_max_attempts_per_hour:
        msg = "too many verification emails have been sent for this account recently"
        raise RateLimitedError(msg, rule="kws_start_hourly_cap")

    # #ASSUME: concurrency: the `user` row lock taken above is still held here
    # and stays held across this outbound call, because it is released only
    # when the request unit of work commits. That is deliberate, not an
    # oversight: the lock is what makes the two limit checks above mean
    # anything, so dropping it before the send would reopen the exact race they
    # exist to close, and the send is what the second request must not
    # duplicate. The cost is the hold duration. kws_client.py budgets
    # _MAX_ATTEMPTS=3 attempts, each with _TIMEOUT_SECONDS=10.0 on both the
    # token leg and the POST, plus 0.5s + 1.0s of backoff, so a fully
    # unresponsive vendor host can hold this row for roughly a minute before
    # the error propagates.
    #
    # Bounded blast radius is what makes that acceptable. The lock is on ONE
    # row, the caller's own `user`, so the only request that can queue behind
    # it is another start for the same adult, which is precisely the request
    # that must not proceed. No other endpoint takes a conflicting mode on
    # `user` (the webhook leg writes `kws_verification`, never this table), so
    # a stalled send cannot delay resolving an attempt or block an unrelated
    # guardian. Connection-pool pressure is the residual risk, and it scales
    # with concurrent starts per adult, which the hourly cap already bounds.
    # #VERIFY: revisit if `user` ever acquires a hot writer, or if the endpoint
    # gains a caller that is not one adult acting for themselves; either would
    # turn a one-row hold into contention. tests/integration/test_consent_api.py
    # ::test_two_concurrent_starts_do_not_both_send pins the behaviour the hold
    # buys.
    correlation = await start_parent_verification(
        VerificationStartRequest(
            user_id=user.id,
            email=email,
            location=body.location,
            language=body.language,
        )
    )
    # The email itself is never logged, here or in consent/service.py; the
    # attempt id is the correlation handle for everything that follows.
    logger.info(
        "kws_verification_started",
        attempt_id=str(correlation.attempt_id),
        kws_environment=settings.kws_environment,
        attempts_in_last_hour=attempts + 1,
    )
    # #ASSUME: data integrity: read the row's OWN requested_at back rather than
    # reporting the `now` taken above. The client counts the resend window from
    # this value, and the server refuses a resend by comparing against the
    # column; reporting a slightly earlier clock would let the client offer a
    # resend that the endpoint then rejects with 409. The row was committed on
    # its own session before the outbound call, so this statement sees it; the
    # fallback only covers a row resolved by the webhook between the send and
    # this read, which is an unreachably fast round trip rather than an error.
    # #VERIFY: tests/integration/test_consent_api.py::
    # test_the_reported_start_time_is_the_row_the_limiter_reads.
    return KwsVerificationStartView(
        attempt_id=str(correlation.attempt_id),
        status=KWS_VERIFICATION_STATUS_SENT,
        requested_at=await open_attempt_started_at(session, user.id) or now,
    )
