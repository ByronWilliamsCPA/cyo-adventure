"""Admin CRUD for the provider/model generation allowlist (WS-C PR1)."""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import (
    AllowlistCreateBody,
    AllowlistListView,
    AllowlistUpdateBody,
    AllowlistView,
    ProviderName,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
)
from cyo_adventure.db.models import ProviderModelAllowlist, ProviderModelAllowlistAudit

router = APIRouter(prefix="/api/v1", tags=["provider-allowlist"])


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before any read or write.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #CRITICAL: security: this allowlist is the control that keeps
    # free-string model ids out of billing; the role gate runs before any
    # query so a non-admin cannot even enumerate what is allowlisted.
    # #VERIFY: test_guardian_gets_403_on_every_verb.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


def _view(row: ProviderModelAllowlist) -> AllowlistView:
    """Map an ORM row to its response schema."""
    return AllowlistView(
        id=str(row.id),
        provider=cast("ProviderName", row.provider),
        model_id=row.model_id,
        enabled=row.enabled,
        display_name=row.display_name,
    )


@router.get("/admin/provider-allowlist")
async def list_allowlist(ctx: Context) -> AllowlistListView:
    """List every allowlist row, ordered by (provider, model_id) (admin only).

    Args:
        ctx: The request context (principal + session).

    Returns:
        AllowlistListView: Every row, ordered by (provider, model_id).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    _require_admin(ctx)
    # #ASSUME: external-resources: a whole-table read per request is
    # deliberate; the table is admin-curated and small, mirroring
    # list_thresholds's no-cache stance.
    # #VERIFY: tests/integration/test_provider_allowlist_api.py.
    rows = (
        await ctx.session.scalars(
            select(ProviderModelAllowlist).order_by(
                ProviderModelAllowlist.provider, ProviderModelAllowlist.model_id
            )
        )
    ).all()
    return AllowlistListView(rows=[_view(row) for row in rows])


@router.post("/admin/provider-allowlist", status_code=201)
async def add_allowlist_entry(body: AllowlistCreateBody, ctx: Context) -> AllowlistView:
    """Add a new (provider, model_id) pair to the allowlist (admin only).

    Args:
        body: The provider/model_id/display_name to add.
        ctx: The request context (principal + session).

    Returns:
        AllowlistView: The created row.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        StateTransitionError: If the pair already exists (409).
    """
    _require_admin(ctx)
    # #ASSUME: concurrency: check-then-act on (provider, model_id) is unlocked;
    # two concurrent admin POSTs for the same pair can both miss the row and race
    # to INSERT. Admin-only and rare; the
    # uq_provider_model_allowlist_provider_model UniqueConstraint is the backstop,
    # and the flush below maps its IntegrityError to the same 409 the pre-check
    # returns, so the race loser gets a conflict status, not a 500.
    # #VERIFY: test_add_duplicate_pair_is_409 covers the 409 contract; the
    # IntegrityError guard on flush below extends it to the concurrent race.
    existing = await ctx.session.scalar(
        select(ProviderModelAllowlist).where(
            ProviderModelAllowlist.provider == body.provider,
            ProviderModelAllowlist.model_id == body.model_id,
        )
    )
    if existing is not None:
        msg = f"allowlist entry already exists for ({body.provider}, {body.model_id})"
        raise StateTransitionError(msg)
    row = ProviderModelAllowlist(
        provider=body.provider,
        model_id=body.model_id,
        enabled=True,
        display_name=body.display_name,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    ctx.session.add(row)
    # #CRITICAL: data-integrity: every allowlist edit must leave an audit
    # trail (changed_by is a NOT NULL FK), so the audit row is written in the
    # same unit-of-work as the insert; both commit or both roll back.
    # #VERIFY: test_add_then_list_with_audit.
    ctx.session.add(
        ProviderModelAllowlistAudit(
            provider=body.provider,
            model_id=body.model_id,
            action="create",
            old_enabled=None,
            new_enabled=True,
            changed_by=ctx.principal.user_id,
        )
    )
    # #CRITICAL: concurrency: the pre-check above can be raced; the unique
    # constraint is the real guard. Map its IntegrityError to a 409 so the loser
    # of a concurrent insert gets the same conflict status as the pre-check path
    # rather than a 500. The failed flush aborts the transaction; the request
    # unit-of-work rolls it back (no further session use here).
    # #VERIFY: test_add_duplicate_pair_conflicts.
    try:
        await ctx.session.flush()
    except IntegrityError as exc:
        msg = f"allowlist entry already exists for ({body.provider}, {body.model_id})"
        raise StateTransitionError(msg) from exc
    return _view(row)


@router.put("/admin/provider-allowlist/{entry_id}")
async def update_allowlist_entry(
    entry_id: uuid.UUID, body: AllowlistUpdateBody, ctx: Context
) -> AllowlistView:
    """Toggle enabled and/or update display_name for one row (admin only).

    Args:
        entry_id: The row's id (path).
        body: The desired enabled/display_name state (full replace).
        ctx: The request context (principal + session).

    Returns:
        AllowlistView: The row after the update.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ResourceNotFoundError: If no row exists for ``entry_id`` (404).
    """
    _require_admin(ctx)
    # #CRITICAL: security: admin-only mutation of the billing-control allowlist;
    # the role gate runs first (above) so a non-admin cannot toggle a backend on.
    # #CRITICAL: data-integrity: the enabled/display_name change and its audit
    # row are written in one unit-of-work (below), so a toggle and its audit
    # trail commit or roll back together (changed_by is a NOT NULL FK).
    # #VERIFY: test_toggle_enabled_with_audit.
    row = await ctx.session.get(ProviderModelAllowlist, entry_id)
    if row is None:
        msg = f"no allowlist entry '{entry_id}'"
        raise ResourceNotFoundError(msg)
    old_enabled = row.enabled
    row.enabled = body.enabled
    row.display_name = body.display_name
    row.updated_by = ctx.principal.user_id
    ctx.session.add(
        ProviderModelAllowlistAudit(
            provider=row.provider,
            model_id=row.model_id,
            action="update",
            old_enabled=old_enabled,
            new_enabled=body.enabled,
            changed_by=ctx.principal.user_id,
        )
    )
    await ctx.session.flush()
    return _view(row)


@router.delete("/admin/provider-allowlist/{entry_id}")
async def delete_allowlist_entry(
    entry_id: uuid.UUID, ctx: Context
) -> AllowlistListView:
    """Remove one row and audit it before deletion (admin only).

    Args:
        entry_id: The row's id (path).
        ctx: The request context (principal + session).

    Returns:
        AllowlistListView: The full list view after the delete.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ResourceNotFoundError: If no row exists for ``entry_id`` (404).
    """
    _require_admin(ctx)
    # #CRITICAL: security: admin-only removal from the billing-control allowlist;
    # the role gate runs first (above).
    # #CRITICAL: data-integrity: the audit row is written BEFORE the delete so it
    # captures the row's provider/model_id/enabled while they still exist; the
    # audit insert and the delete share one unit-of-work and commit or roll back
    # together (changed_by is a NOT NULL FK). Reordering them would lose the
    # deleted row's state from the audit trail.
    # #VERIFY: test_delete_removes_row_with_audit.
    row = await ctx.session.get(ProviderModelAllowlist, entry_id)
    if row is None:
        msg = f"no allowlist entry '{entry_id}'"
        raise ResourceNotFoundError(msg)
    ctx.session.add(
        ProviderModelAllowlistAudit(
            provider=row.provider,
            model_id=row.model_id,
            action="delete",
            old_enabled=row.enabled,
            new_enabled=None,
            changed_by=ctx.principal.user_id,
        )
    )
    await ctx.session.delete(row)
    await ctx.session.flush()
    return await list_allowlist(ctx)
