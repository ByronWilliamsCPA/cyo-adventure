"""Admin CRUD for the provider/model generation allowlist (WS-C PR1)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import (
    AllowlistCreateBody,
    AllowlistListView,
    AllowlistUpdateBody,
    AllowlistView,
    error_responses,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import ProviderModelAllowlist, ProviderModelAllowlistAudit
from cyo_adventure.generation.provider import FAMILY_LANE_PROVIDERS

router = APIRouter(
    prefix="/api/v1",
    tags=["provider-allowlist"],
    responses=error_responses(401, 403),
)


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


def _reject_enabling_outside_the_family_lane(
    provider: str, *, enabled: bool, field: str
) -> None:
    """Refuse any write that would leave a forbidden provider's row enabled.

    D1 (ruled 2026-08-23, ``UW-C346``) restricts kid- and guardian-triggered
    generation to ``provider.py::FAMILY_LANE_PROVIDERS``. Every authoring plan
    is created against a family story request, so the worker builds every one
    of them with ``lane="family"``.

    The rule enforced here is "a row whose provider is outside that set may
    exist but may not be ENABLED", not "may not exist": D1 still permits the
    direct leg for out-of-band admin content generation, the seed migration's
    ``ON CONFLICT DO NOTHING`` makes a deleted row come back ENABLED on any
    replay, and the admin surface has to be able to show what was withdrawn.

    Args:
        provider: The row's provider. On create this is untrusted request
            input; on update it is the stored row's value, since the update
            body cannot change it.
        enabled: The enabled state the request is asking the row to end in.
        field: The request field the rejection is attributed to.

    Raises:
        ValidationError: If an enabled row would name a provider the family
            lane forbids (422).
    """
    # #CRITICAL: security: this is the runtime half of the D1 guard. Its
    # code-side twin (tests/unit/test_allowlist.py::
    # test_no_enabled_seed_row_names_a_provider_the_family_lane_forbids) covers
    # only the static DEFAULT_ALLOWLIST literal, while the rows THIS router
    # writes are what `is_enabled_allowlist_pair` actually reads and what the
    # authoring-plan endpoint trusts. Without this check an admin can create or
    # re-enable a forbidden pair, and `build_provider(lane="family")` then
    # raises at job time, so a configuration error arrives as a generation
    # failure attributed to the job.
    # #VERIFY: tests/integration/test_provider_allowlist_api.py::
    # test_add_a_provider_the_family_lane_forbids_is_422 and
    # test_reenabling_a_provider_the_family_lane_forbids_is_422; the
    # may-exist-while-disabled half is pinned by
    # test_a_withdrawn_row_stays_editable_while_it_stays_disabled.
    if not enabled or provider in FAMILY_LANE_PROVIDERS:
        return
    msg = (
        f"provider '{provider}' may not be enabled on the allowlist: a kid- or "
        "guardian-triggered generation job is not permitted to use it, so an "
        "enabled row would be a pair the authoring-plan endpoint accepts and "
        "the worker then refuses. The row may exist while disabled."
    )
    raise ValidationError(msg, field=field)


def _view(row: ProviderModelAllowlist) -> AllowlistView:
    """Map an ORM row to its response schema.

    ``row.provider`` is passed through unnarrowed. It used to be
    ``cast("ProviderName", ...)``, which is a no-op at runtime and so told the
    type checker a story Pydantic did not believe: ``AllowlistView`` validated
    the same field for real, and a row naming a retired backend raised instead.
    See ``AllowlistView`` for why responses stay wider than requests.
    """
    return AllowlistView(
        id=str(row.id),
        provider=row.provider,
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


@router.post(
    "/admin/provider-allowlist", status_code=201, responses=error_responses(409)
)
async def add_allowlist_entry(body: AllowlistCreateBody, ctx: Context) -> AllowlistView:
    """Add a new (provider, model_id) pair to the allowlist (admin only).

    Args:
        body: The provider/model_id/display_name to add.
        ctx: The request context (principal + session).

    Returns:
        AllowlistView: The created row.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ValidationError: If the provider is one the family generation lane
            forbids (422); this endpoint only ever creates enabled rows.
        StateTransitionError: If the pair already exists (409).
    """
    _require_admin(ctx)
    # Checked before the duplicate pre-check so a rejected write does no DB
    # work at all, and stated as enabled=True because that is what the INSERT
    # below hardcodes: there is no way to ask this endpoint for a disabled row.
    _reject_enabling_outside_the_family_lane(
        body.provider, enabled=True, field="provider"
    )
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


@router.put("/admin/provider-allowlist/{entry_id}", responses=error_responses(404))
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
        ValidationError: If the request would enable a row whose provider the
            family generation lane forbids (422).
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
    # The 404 comes first (a missing row is not a lane question), then the lane
    # guard, before any field is assigned or any audit row is staged. `enabled`
    # is the field named because provider is not settable through this body.
    _reject_enabling_outside_the_family_lane(
        row.provider, enabled=body.enabled, field="enabled"
    )
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


@router.delete("/admin/provider-allowlist/{entry_id}", responses=error_responses(404))
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
