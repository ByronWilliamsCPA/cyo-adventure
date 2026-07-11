"""Guardian-minted child session tokens (G1 / P6-04).

A guardian (or admin) exchanges a child profile id for a short-lived,
backend-signed session token the kid surface uses as its own bearer. The token
is scoped to that single profile (role=child); see ``core/child_session.py``
for the trust model and ``api/deps.py::require_principal`` for the verifying
branch. Children never mint their own sessions.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context, authorize_profile, parse_uuid
from cyo_adventure.api.schemas import ChildSessionCreateBody, ChildSessionView
from cyo_adventure.core.child_session import mint_child_session_token
from cyo_adventure.core.exceptions import AuthorizationError, ResourceNotFoundError
from cyo_adventure.db.models import ChildProfile, User

router = APIRouter(prefix="/api/v1", tags=["child-sessions"])


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
        ResourceNotFoundError: If the profile does not exist, or has no child
            account to attribute the session to (-> 404).
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
    # pipeline_event log (its actor_id is a FK to user.id); a profile with no
    # child account cannot start a session yet. Provisioning a child account
    # alongside a profile is out of scope here (deferred; see the handoff).
    # #VERIFY: test_child_sessions.py::test_mint_requires_child_account.
    child_user = await ctx.session.scalar(
        select(User).where(
            User.child_profile_id == profile_uuid,
            User.role == "child",
        )
    )
    if child_user is None:
        msg = "profile has no child account"
        raise ResourceNotFoundError(msg)

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
