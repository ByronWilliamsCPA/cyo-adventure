"""Guardian-minted child session tokens (G1 / P6-04).

A guardian (or admin) exchanges a child profile id for a short-lived,
backend-signed session token the kid surface uses as its own bearer. The token
is scoped to that single profile (role=child); see ``core/child_session.py``
for the trust model and ``api/deps.py::require_principal`` for the verifying
branch. Children never mint their own sessions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.api.deps import Context, authorize_profile, parse_uuid
from cyo_adventure.api.schemas import ChildSessionCreateBody, ChildSessionView
from cyo_adventure.core.child_session import mint_child_session_token
from cyo_adventure.core.exceptions import AuthorizationError, ResourceNotFoundError
from cyo_adventure.db.integrity import is_authn_subject_conflict
from cyo_adventure.db.models import ChildProfile, User
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["child-sessions"])

# Deterministic synthetic subject for JIT-provisioned child accounts. Supabase
# guardian subs are bare UUIDs and the seed scripts use short opaque tokens
# ("dev-child", "child-a"), so this prefixed form can never collide with either
# family of subject on the unique authn_subject index. The seed scripts' child
# subjects are NOT deterministic per profile; new API-provisioned accounts
# deliberately diverge to this deterministic shape so a concurrent double-mint
# converges on one row.
_SUBJECT_PREFIX = "child-profile:"


@router.post("/child-sessions", status_code=201)
async def create_child_session(
    body: ChildSessionCreateBody, ctx: Context
) -> ChildSessionView:
    """Mint a child session token for one profile (guardian or admin only).

    Args:
        body: The target child profile id.
        ctx: The request context (principal and session).

    Returns:
        ChildSessionView: The signed token, its expiry, and the profile id.

    Raises:
        AuthorizationError: If a child token reaches this endpoint, or a
            guardian names a profile outside its own family (-> 403).
        ResourceNotFoundError: If the profile does not exist (-> 404).
        ValidationError: If ``profile_id`` is not a valid UUID (-> 422).
    """
    # #CRITICAL: security: only a guardian (own family) or an admin may mint a
    # child session; a child principal must never mint one for itself or anyone
    # else. This role gate runs before any lookup, so a child token is rejected
    # with an exact 403.
    # #VERIFY: test_child_sessions.py::test_child_cannot_mint asserts 403.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = "guardian or admin role required"
        raise AuthorizationError(msg)

    profile_uuid = parse_uuid(body.profile_id, "profile_id")
    # #CRITICAL: security: a guardian may mint only for a profile in its own
    # family (authorize_profile checks the family-resolved profile set); an
    # admin is global and skips the ownership check by design (mirrors the
    # admin-global branch in story_requests.py). A cross-family guardian id is
    # rejected with 403 before the profile row is read.
    # #VERIFY: test_child_sessions.py::test_guardian_cannot_mint_other_family.
    if not ctx.principal.is_admin:
        authorize_profile(ctx.principal, profile_uuid)

    profile = await ctx.session.get(ChildProfile, profile_uuid)
    if profile is None:
        msg = "profile not found"
        raise ResourceNotFoundError(msg)

    # #CRITICAL: data integrity: the minted token embeds a real child User.id so
    # the resulting child principal is attributable on the append-only
    # pipeline_event log (its actor_id is a FK to user.id). Profiles created
    # through the API get no User row (api/profiles.py creates only the
    # ChildProfile; only the seed scripts ever create child users), so the
    # child account is JIT-provisioned here, inside the same unit of work,
    # under the family authorization that already ran above.
    # #VERIFY: test_child_sessions.py::test_mint_provisions_child_account and
    # test_second_mint_reuses_provisioned_account.
    child_user = await _child_user_for_profile(ctx.session, profile)

    token, expires_at = mint_child_session_token(
        profile_id=profile_uuid,
        family_id=profile.family_id,
        user_id=child_user.id,
    )
    return ChildSessionView(
        token=token,
        expires_at=expires_at,
        profile_id=str(profile_uuid),
    )


async def _child_user_for_profile(session: AsyncSession, profile: ChildProfile) -> User:
    """Return the profile's child account, JIT-provisioning one if absent.

    Args:
        session: The request's unit-of-work session.
        profile: The already-authorized child profile row.

    Returns:
        User: The existing or newly-provisioned child user.
    """
    existing = await session.scalar(
        select(User).where(
            User.child_profile_id == profile.id,
            User.role == "child",
        )
    )
    if existing is not None:
        return existing
    return await _provision_child_user(session, profile)


async def _provision_child_user(session: AsyncSession, profile: ChildProfile) -> User:
    """Create the profile's child ``User`` row, surviving a double-mint race.

    The synthetic ``authn_subject`` (``child-profile:{profile_id}``) is
    deterministic, so two guardian devices minting simultaneously both compute
    the same subject and collide on the unique ``authn_subject`` index instead
    of creating two accounts. The loser fetches the winner's row.

    Args:
        session: The request's unit-of-work session.
        profile: The already-authorized child profile row.

    Returns:
        User: The provisioned (or concurrently-won) child user.

    Raises:
        IntegrityError: On a non-``authn_subject`` constraint violation (a
            logic or data error a retry cannot resolve).
    """
    subject = f"{_SUBJECT_PREFIX}{profile.id}"
    user = User(
        family_id=profile.family_id,
        role="child",
        authn_subject=subject,
        child_profile_id=profile.id,
    )
    try:
        # #CRITICAL: concurrency: two devices can both see "no child account"
        # and both insert; Postgres serializes them on the unique authn_subject
        # index and the loser gets IntegrityError. The write goes INSIDE
        # begin_nested (the savepoint pattern from generation/series_link.py:
        # begin_nested autoflushes already-dirty state before the SAVEPOINT, so
        # an add before the block would run the conflicting INSERT against the
        # outer transaction and corrupt it instead of just the savepoint). The
        # unwound savepoint leaves the request transaction usable, and the
        # loser recovers by reading the winner's now-visible committed row.
        # #VERIFY: test_child_sessions.py::test_provision_race_recovers_winner
        # exercises a real IntegrityError from the unique index.
        async with session.begin_nested():
            session.add(user)
            await session.flush()
    except IntegrityError as exc:
        # Only the authn_subject unique conflict is the benign double-mint
        # race; an FK or CHECK violation is a real error and must propagate.
        if not is_authn_subject_conflict(exc):
            raise
        logger.warning(
            "child_session.provision_conflict",
            profile_id=str(profile.id),
        )
        # #ASSUME: concurrency: recovery relies on READ COMMITTED isolation
        # (Postgres' default). The loser's INSERT blocks on the winner's
        # uncommitted row, then raises 23505 only once the winner COMMITS, so a
        # fresh per-statement snapshot makes the winner's row visible to this
        # SELECT. Under REPEATABLE READ / SERIALIZABLE the loser's snapshot
        # predates the winner's commit, this SELECT returns None, and the guard
        # below re-raises instead of silently minting against a missing row.
        # #VERIFY: keep the request transaction at READ COMMITTED; if isolation
        # is ever raised, replace this read with a retry that opens a new
        # snapshot (see test_provision_race_recovers_winner).
        winner = await session.scalar(select(User).where(User.authn_subject == subject))
        if winner is None:  # pragma: no cover - conflict implies a winner row
            raise
        return winner
    logger.info(
        "child_session.account_provisioned",
        profile_id=str(profile.id),
        user_id=str(user.id),
    )
    return user
