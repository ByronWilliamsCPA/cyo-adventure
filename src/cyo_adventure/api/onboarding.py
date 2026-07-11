"""JIT guardian provisioning: first-login Family + guardian User (P6-03).

A guardian's first authenticated call to ``POST /api/v1/onboarding`` creates
their ``Family`` and guardian ``User`` row, keyed on the verified Supabase
subject. Every subsequent call is idempotent: it returns the existing row
without creating anything. This is the ONLY endpoint that accepts a verified
token whose subject has no ``User`` row yet (see
``deps.require_onboarding_identity``); every other endpoint keeps rejecting an
unknown subject as before.

Admins are provisioned out of band and always already have a ``User`` row, so
onboarding returns that row unchanged and never creates a family for an admin
(the "admin is not a family member" invariant is preserved by never taking the
create path for a subject that already resolves).
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.api.deps import DbSession, OnboardingIdentityDep
from cyo_adventure.api.schemas import OnboardingBody, OnboardingConsent, OnboardingView
from cyo_adventure.db.models import Family, User
from cyo_adventure.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["onboarding"])

# Placeholder family name at provisioning; the guardian renames it later via the
# families surface. NOT NULL on the column, so a non-empty default is required.
_DEFAULT_FAMILY_NAME = "My Family"
_GUARDIAN_ROLE = "guardian"
# asyncpg surfaces the first-login unique conflict on user.authn_subject under
# this unique-index name (baseline migration: CREATE UNIQUE INDEX
# ix_user_authn_subject); the race recovery below matches on it so an FK or
# other integrity error is never mistaken for a lost provisioning race.
_AUTHN_SUBJECT_UNIQUE = "ix_user_authn_subject"


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
    # #VERIFY: test_onboarding asserts a consent payload is accepted with no
    # provisioning side effect; P7-02 will add the record + tests.
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


@router.post("/onboarding")
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
        # Idempotent retry, or an already-provisioned guardian/admin. An admin
        # always has a row, so this returns it unchanged: onboarding never
        # creates a family for an admin.
        response.status_code = 200
        return _view(existing, created=False)

    # #CRITICAL: concurrency: two first-login requests for the same subject can
    # both miss the read above and race to INSERT. Postgres blocks the second
    # on the winner's unique-index entry; once the winner commits, the loser's
    # flush raises IntegrityError, the SAVEPOINT unwinds (undoing both the
    # Family and User inserts), and the loser returns the winner's row rather
    # than a 500. The inserts MUST stay inside begin_nested(): the savepoint
    # bounds exactly the rollback, keeping the outer unit-of-work usable for
    # the recovery re-read.
    # #VERIFY: test_onboarding_race_returns_winner drives a real IntegrityError
    # from the unique index and asserts a 200 with the winner's ids.
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
        # Only the authn_subject unique conflict is a recoverable race; an FK or
        # other integrity error is a real fault and must propagate unchanged.
        if _AUTHN_SUBJECT_UNIQUE not in str(exc.orig):
            raise
        winner = await session.scalar(
            select(User).where(User.authn_subject == identity.subject)
        )
        if winner is None:  # pragma: no cover - a conflict implies a visible row
            raise
        logger.info("onboarding.race_resolved", user_id=str(winner.id))
        response.status_code = 200
        return _view(winner, created=False)

    logger.info(
        "onboarding.provisioned",
        family_id=str(family.id),
        user_id=str(user.id),
    )
    response.status_code = 201
    return _view(user, created=True)
