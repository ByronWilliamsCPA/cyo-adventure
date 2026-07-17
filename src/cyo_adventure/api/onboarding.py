"""JIT guardian provisioning: first-login Family + guardian User (P6-03).

A guardian's first authenticated call to ``POST /api/v1/onboarding`` creates
their ``Family`` and guardian ``User`` row, keyed on the verified Supabase
subject. Every subsequent call is idempotent: it returns the existing row
without creating anything. This is the ONLY endpoint that accepts a verified
token whose subject has no ``User`` row yet (see
``deps.require_onboarding_identity``); every other endpoint keeps rejecting an
unknown subject as before.

ANY unknown verified subject with no matching pending invite is provisioned
as ``role="guardian"`` with a fresh family; the endpoint cannot tell an
intended admin apart from a guardian. Admin accounts MUST therefore either be
seeded before their first sign-in, or admin-invited via ``POST
/api/v1/admin/users`` (WS-J admin user management): a seeded admin resolves
to its existing row and is returned unchanged (no family is created); an
admin-invited (``status="pending"``) row is bound to the verified subject by
exact email match (see ``_bind_pending_invite``) instead of falling through
to guardian provisioning; an unseeded, uninvited admin's first call would
still silently create a guardian row plus a family that account should never
hold.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.api.deps import DbSession, OnboardingIdentity, OnboardingIdentityDep
from cyo_adventure.api.schemas import (
    OnboardingBody,
    OnboardingConsent,
    OnboardingView,
    error_responses,
)
from cyo_adventure.db.integrity import is_authn_subject_conflict
from cyo_adventure.db.models import Family, User
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1", tags=["onboarding"], responses=error_responses(401, 403)
)

# Placeholder family name at provisioning. It persists until a rename surface
# exists (none does today: the families API has no rename endpoint). NOT NULL
# on the column, so a non-empty default is required.
_DEFAULT_FAMILY_NAME = "My Family"
_GUARDIAN_ROLE = "guardian"


def _record_consent(consent: OnboardingConsent | None) -> None:
    """Consent-capture seam for P7-02; intentionally a no-op today.

    P6-03 provides only the seam: the request may carry a consent payload, and
    this hook is where P7-02 will persist a durable consent record. It records
    nothing now so onboarding stays idempotent and no half-built consent path
    ships.

    Args:
        consent: The optional consent payload from the request body.
    """
    # #ASSUME: security: P6-03 does NOT persist or enforce consent; this is the
    # extension point P7-02 fills. Nothing here gates provisioning until then.
    # A presence-only debug line (no payload content, so no PII) marks the seam
    # without building consent logic; P7-02 replaces this body with a durable
    # consent record and its tests.
    # #VERIFY: test_onboarding_api.py::test_consent_seam_is_accepted_without_side_effect
    # asserts a consent payload is accepted with no provisioning side effect;
    # P7-02 will add the record + tests.
    if consent is not None:
        logger.debug("onboarding.consent_seam_received")


def _view(user: User, *, created: bool) -> OnboardingView:
    """Project a resolved/created user row to the onboarding response.

    Args:
        user: The resolved or freshly-created guardian/admin user.
        created: Whether this request provisioned the row.

    Returns:
        OnboardingView: The family/user identity and the created flag.
    """
    return OnboardingView(
        family_id=str(user.family_id),
        user_id=str(user.id),
        role=user.role,
        created=created,
    )


async def _provision_guardian(
    session: AsyncSession, identity: OnboardingIdentity
) -> tuple[User, bool]:
    """Create the subject's Family + guardian User, surviving a first-login race.

    Args:
        session: The request unit-of-work session.
        identity: The verified onboarding identity (subject + optional email).

    Returns:
        tuple[User, bool]: The created (or concurrently-won) user row, and
        whether THIS call created it (``False`` when a racing request won).

    Raises:
        IntegrityError: On a non-``authn_subject`` constraint violation (a
            logic or data error a retry cannot resolve).
    """
    # #CRITICAL: concurrency: two first-login requests for the same subject can
    # both miss the caller's pre-read and race to INSERT. Postgres blocks the
    # second on the winner's unique-index entry; once the winner commits, the
    # loser's flush raises IntegrityError, the SAVEPOINT unwinds (undoing both
    # the Family and User inserts), and the loser returns the winner's row
    # rather than a 500. The inserts MUST stay inside begin_nested(): the
    # savepoint bounds exactly the rollback, keeping the outer unit-of-work
    # usable for the recovery re-read.
    # #VERIFY: test_onboarding_handler.py::test_onboarding_race_returns_winner_not_500
    # drives the recovery branch against a mocked session, and
    # test_onboarding_api.py::test_onboarding_race_recovers_winner drives a
    # real IntegrityError from the unique index against Postgres.
    try:
        async with session.begin_nested():
            family = Family(name=_DEFAULT_FAMILY_NAME)
            session.add(family)
            await session.flush()
            user = User(
                family_id=family.id,
                role=_GUARDIAN_ROLE,
                authn_subject=identity.subject,
                email=identity.email,
            )
            session.add(user)
            await session.flush()
    except IntegrityError as exc:
        # Only the authn_subject unique conflict is a recoverable race; an FK
        # or other integrity error is a real fault and must propagate.
        if not is_authn_subject_conflict(exc):
            raise
        winner = await session.scalar(
            select(User).where(User.authn_subject == identity.subject)
        )
        if winner is None:  # pragma: no cover - a conflict implies a visible row
            raise
        logger.info("onboarding.race_resolved", user_id=str(winner.id))
        return winner, False
    # #ASSUME: security: any unknown verified subject reaching this point is
    # provisioned as role="guardian" with a fresh family, including an admin
    # whose row was never seeded (that admin would become a plain guardian
    # holding a family it should not have). Admin accounts MUST be seeded
    # before their first sign-in; there is deliberately no allowlist here.
    # #VERIFY: every environment's seed path creates admin rows before sign-in
    # is enabled; the warning below is the operational tripwire for auditing
    # each JIT provisioning after the fact.
    logger.warning(
        "onboarding.provisioned",
        family_id=str(family.id),
        user_id=str(user.id),
    )
    return user, True


async def _bind_pending_invite(
    session: AsyncSession, identity: OnboardingIdentity
) -> User | None:
    """Bind a verified subject to a matching admin-created pending invite.

    Args:
        session: The request unit-of-work session.
        identity: The verified onboarding identity (subject + optional email).

    Returns:
        User | None: The now-``active`` user row, or ``None`` when no
        ``status="pending"`` row matches this identity's email (the caller
        falls back to ``_provision_guardian``).
    """
    # #ASSUME: security: the match is an exact string comparison against the
    # verified Supabase email claim (no case-folding); an invite typed with
    # different casing than the identity provider reports falls through to
    # _provision_guardian instead of binding, which surfaces as an
    # unexpected extra family rather than a silent takeover of another
    # pending row, so the failure mode is safe.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_pending_invite_binds_on_first_login_by_email.
    if identity.email is None:
        return None
    pending = await session.scalar(
        select(User).where(User.status == "pending", User.email == identity.email)
    )
    if pending is None:
        return None
    # #CRITICAL: concurrency: two concurrent first-logins for the SAME
    # invited identity race to set the same authn_subject on the same row.
    # Unlike _provision_guardian's race (two DIFFERENT rows competing to
    # insert one unique value), both writers here converge on the identical
    # subject, so there is no conflicting insert to recover from; the second
    # writer's UPDATE just repeats the first's.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_pending_invite_bind_race_is_idempotent.
    pending.authn_subject = identity.subject
    pending.status = "active"
    await session.flush()
    logger.info("onboarding.pending_invite_bound", user_id=str(pending.id))
    return pending


@router.post(
    "/onboarding",
    status_code=201,
    responses={
        200: {
            "model": OnboardingView,
            "description": (
                "The subject already has a User row (an idempotent retry, an "
                "already-provisioned guardian or admin, or a lost first-login "
                "race); the existing identity is returned with created=false "
                "and nothing is created."
            ),
        },
    },
)
async def onboard(
    identity: OnboardingIdentityDep,
    session: DbSession,
    response: Response,
    body: OnboardingBody | None = None,
) -> OnboardingView:
    """Provision, or return, the caller's family and guardian user (P6-03).

    On first login (no ``User`` for the verified subject) this creates a
    ``Family`` and a guardian ``User`` atomically and returns 201. On any
    later call, or for an already-provisioned guardian/admin, it returns the
    existing row with 200 and creates nothing.

    Args:
        identity: The verified onboarding identity (subject + optional email).
        session: The request unit-of-work session.
        response: The response, whose status code is set to 201 (created) or
            200 (idempotent) here.
        body: The optional request body carrying only the P7-02 consent seam.

    Returns:
        OnboardingView: The resolved or created family/guardian identity.
    """
    _record_consent(body.consent if body is not None else None)

    existing = await session.scalar(
        select(User).where(User.authn_subject == identity.subject)
    )
    if existing is not None:
        # Idempotent retry, or an already-provisioned guardian/admin. A SEEDED
        # admin resolves here and is returned unchanged; an unseeded,
        # uninvited admin falls through and is provisioned as a guardian (see
        # the module docstring: seed or invite admin rows before first
        # sign-in).
        response.status_code = 200
        return _view(existing, created=False)

    bound = await _bind_pending_invite(session, identity)
    if bound is not None:
        # Binding an existing (admin-created) row, not creating one: 200,
        # same as any other already-provisioned identity.
        response.status_code = 200
        return _view(bound, created=False)

    user, created = await _provision_guardian(session, identity)
    response.status_code = 201 if created else 200
    return _view(user, created=created)
