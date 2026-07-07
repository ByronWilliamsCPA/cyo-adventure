"""Admin CRUD for age-band moderation surfacing thresholds (WS-A)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import (
    MinVerdict,
    ThresholdListView,
    ThresholdUpsertBody,
    ThresholdView,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import ModerationThreshold, ModerationThresholdAudit
from cyo_adventure.moderation.thresholds import DEFAULT_THRESHOLD, KNOWN_CATEGORIES
from cyo_adventure.storybook.models import AgeBand

router = APIRouter(prefix="/api/v1", tags=["moderation-thresholds"])

_VALID_BANDS = frozenset(band.value for band in AgeBand)


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before any read or write.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #CRITICAL: security: threshold edits change what EVERY family's guardians
    # see; the role gate runs before any query so non-admins learn nothing.
    # #VERIFY: test_guardian_gets_403.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


def _validate_band(age_band: str) -> None:
    """Validate an age-band path segment against the closed enum.

    Args:
        age_band: The age band from the URL path.

    Raises:
        ValidationError: If the value is not a known age band (422).
    """
    if age_band not in _VALID_BANDS:
        msg = f"unknown age band '{age_band}'"
        raise ValidationError(msg, field="age_band", value=age_band)


@router.get("/admin/moderation-thresholds")
async def list_thresholds(ctx: Context) -> ThresholdListView:
    """List all overrides plus the code default (admin only).

    Args:
        ctx: The request context (principal + session).

    Returns:
        ThresholdListView: The code default, known categories, and all
        stored override rows.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    _require_admin(ctx)
    rows = (
        await ctx.session.scalars(
            select(ModerationThreshold).order_by(
                ModerationThreshold.age_band, ModerationThreshold.category
            )
        )
    ).all()
    return ThresholdListView(
        default_min_verdict=cast("MinVerdict", DEFAULT_THRESHOLD.min_verdict.value),
        default_min_score=DEFAULT_THRESHOLD.min_score,
        known_categories=list(KNOWN_CATEGORIES),
        rows=[
            ThresholdView(
                age_band=row.age_band,
                category=row.category,
                # DB CHECK constraint guarantees the enum domain; cast, don't
                # suppress (repo rule: no type-ignore without a ticket).
                min_verdict=cast("MinVerdict", row.min_verdict),
                min_score=row.min_score,
            )
            for row in rows
        ],
    )


async def _get_row(
    ctx: Context, age_band: str, category: str
) -> ModerationThreshold | None:
    """Load one override row by its natural key, or ``None`` if absent.

    Args:
        ctx: The request context (principal + session).
        age_band: The age band half of the natural key.
        category: The category half of the natural key.

    Returns:
        ModerationThreshold | None: The row, or ``None`` if no override exists.
    """
    return await ctx.session.scalar(
        select(ModerationThreshold).where(
            ModerationThreshold.age_band == age_band,
            ModerationThreshold.category == category,
        )
    )


@router.put("/admin/moderation-thresholds/{age_band}/{category}")
async def upsert_threshold(
    age_band: str, category: str, body: ThresholdUpsertBody, ctx: Context
) -> ThresholdView:
    """Create or update one override; write an audit row (admin only).

    Args:
        age_band: The age band half of the natural key.
        category: The category half of the natural key.
        body: The desired min_verdict/min_score.
        ctx: The request context (principal + session).

    Returns:
        ThresholdView: The stored override after the write.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ValidationError: If ``age_band`` is not a known band (422).
    """
    _require_admin(ctx)
    _validate_band(age_band)
    row = await _get_row(ctx, age_band, category)
    old_verdict = row.min_verdict if row else None
    old_score = row.min_score if row else None
    if row is None:
        row = ModerationThreshold(
            age_band=age_band,
            category=category,
            min_verdict=body.min_verdict,
            min_score=body.min_score,
            updated_by=ctx.principal.user_id,
        )
        ctx.session.add(row)
    else:
        row.min_verdict = body.min_verdict
        row.min_score = body.min_score
        row.updated_by = ctx.principal.user_id
    # #CRITICAL: data-integrity: every threshold edit must leave an audit trail
    # (changed_by is a NOT NULL FK), so the audit row is written in the same
    # unit-of-work as the upsert; both commit or both roll back together.
    # #VERIFY: test_upsert_creates_then_updates_with_audit asserts one audit
    # row per PUT with the correct old/new score pairing.
    ctx.session.add(
        ModerationThresholdAudit(
            age_band=age_band,
            category=category,
            action="upsert",
            old_min_verdict=old_verdict,
            new_min_verdict=body.min_verdict,
            old_min_score=old_score,
            new_min_score=body.min_score,
            changed_by=ctx.principal.user_id,
        )
    )
    await ctx.session.flush()
    return ThresholdView(
        age_band=age_band,
        category=category,
        min_verdict=body.min_verdict,
        min_score=body.min_score,
    )


@router.delete("/admin/moderation-thresholds/{age_band}/{category}")
async def delete_threshold(
    age_band: str, category: str, ctx: Context
) -> ThresholdListView:
    """Remove one override (reverting to the default); audit it (admin only).

    Args:
        age_band: The age band half of the natural key.
        category: The category half of the natural key.
        ctx: The request context (principal + session).

    Returns:
        ThresholdListView: The full list view after the delete.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ValidationError: If ``age_band`` is not a known band (422).
        ResourceNotFoundError: If no override exists for the key (404).
    """
    _require_admin(ctx)
    _validate_band(age_band)
    row = await _get_row(ctx, age_band, category)
    if row is None:
        msg = f"no threshold override for ({age_band}, {category})"
        raise ResourceNotFoundError(msg)
    ctx.session.add(
        ModerationThresholdAudit(
            age_band=age_band,
            category=category,
            action="delete",
            old_min_verdict=row.min_verdict,
            new_min_verdict=None,
            old_min_score=row.min_score,
            new_min_score=None,
            changed_by=ctx.principal.user_id,
        )
    )
    await ctx.session.delete(row)
    await ctx.session.flush()
    return await list_thresholds(ctx)
