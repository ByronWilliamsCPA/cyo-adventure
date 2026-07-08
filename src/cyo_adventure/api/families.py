"""Admin-only family listing (WS-B PR 2).

Powers the required family selector on the admin authored-request form
(decision B3: admin-initiated requests must name a family).
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import FamilyListView, FamilyView
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import Family

router = APIRouter(prefix="/api/v1", tags=["families"])

# Defensive ceiling mirroring generation.py's _JOB_LIST_LIMIT convention: the
# admin form renders every row into one <select>, so an unbounded roster would
# degrade both the query and the DOM as tenants grow.
_FAMILY_LIST_LIMIT = 50


@router.get("/admin/families")
async def list_families(ctx: Context) -> FamilyListView:
    """List families (name order, capped) for the admin authored-request form.

    Args:
        ctx: The request context (principal and session).

    Returns:
        FamilyListView: Up to ``_FAMILY_LIST_LIMIT`` families ordered by name.

    Raises:
        AuthorizationError: If the caller is not an admin (-> 403).
    """
    # #CRITICAL: security: the full family roster is cross-tenant data; only
    # the admin role (the global operator) may enumerate it.
    # #VERIFY: test_admin_lists_families_guardian_forbidden asserts 403 for a
    # guardian token.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg)
    # #EDGE: data-integrity: past _FAMILY_LIST_LIMIT families the selector
    # silently omits the tail; revisit with pagination or search before the
    # deployment outgrows a single dropdown.
    # #VERIFY: test_admin_families_list_is_name_ordered_and_capped.
    rows = await ctx.session.scalars(
        select(Family)
        .order_by(Family.name.asc(), Family.id.asc())
        .limit(_FAMILY_LIST_LIMIT)
    )
    return FamilyListView(
        families=[FamilyView(id=str(f.id), name=f.name) for f in rows.all()]
    )
