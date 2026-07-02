"""Principal introspection: who does this bearer token belong to.

The frontend app shell (C4a-1) needs this to decide which layout (kid vs
guardian) and nav to render; it must not attempt to parse a bearer token
itself, since that token is opaque locally and a signed JWT elsewhere.
"""

from __future__ import annotations

from fastapi import APIRouter

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import MeResponse

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get("/me")
async def whoami(ctx: Context) -> MeResponse:
    """Return the authenticated caller's own identity and role.

    Args:
        ctx: The request context (principal + unit-of-work session).

    Returns:
        MeResponse: The principal's subject, role, family, and profile ids.
    """
    # #ASSUME: security: /me returns identity only for an already-verified
    # principal (require_principal ran and resolved a Principal); no token
    # parsing happens here.
    # #VERIFY: tests/integration/test_me.py::test_me_requires_authentication
    # asserts 401 without a bearer.
    principal = ctx.principal
    return MeResponse(
        subject=principal.subject,
        role=principal.role.value,
        family_id=str(principal.family_id),
        profile_ids=[str(pid) for pid in principal.profile_ids],
    )
