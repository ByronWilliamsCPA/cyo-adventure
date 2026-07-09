"""Admin CRUD for age-band moderation surfacing thresholds (WS-A)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import (
    MinVerdict,
    NoiseFloorUpdateBody,
    NoiseFloorView,
    ThresholdListView,
    ThresholdUpsertBody,
    ThresholdView,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import (
    ModerationSetting,
    ModerationThreshold,
    ModerationThresholdAudit,
)
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.moderation.thresholds import (
    ADMIN_NOISE_FLOOR_KEY,
    DEFAULT_THRESHOLD,
    KNOWN_CATEGORIES,
    load_admin_noise_floor,
)
from cyo_adventure.storybook.models import AgeBand

# Re-exported locally so call sites below read naturally; the string itself
# lives in exactly one place: cyo_adventure.moderation.thresholds.
_NOISE_FLOOR_KEY = ADMIN_NOISE_FLOOR_KEY

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
    # #ASSUME: external-resources: a whole-table read per request is deliberate;
    # the table is admin-curated and small, mirroring load_threshold_policy's
    # no-cache stance. Revisit only if it grows past a few hundred rows.
    # #VERIFY: tests/integration/test_moderation_thresholds_api.py.
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
    # #ASSUME: data-integrity: scalar() is unambiguous only because
    # uq_moderation_threshold_band_category guarantees at most one row per
    # (age_band, category) natural key.
    # #VERIFY: tests/integration/test_threshold_policy_loader.py::
    # test_duplicate_band_category_rejected_by_unique_constraint.
    return await ctx.session.scalar(
        select(ModerationThreshold).where(
            ModerationThreshold.age_band == age_band,
            ModerationThreshold.category == category,
        )
    )


@router.put("/admin/moderation-thresholds/{age_band}")
async def upsert_threshold(
    age_band: str, category: str, body: ThresholdUpsertBody, ctx: Context
) -> ThresholdView:
    """Create or update one override; write an audit row (admin only).

    ``category`` is a QUERY parameter (FastAPI treats a str param absent
    from the path template as query), never a path segment: five known
    categories contain ``/`` (e.g. ``self-harm/instructions``), and a
    decoded slash in a path segment breaks route matching and 404s.

    Args:
        age_band: The age band half of the natural key (path).
        category: The category half of the natural key (query).
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
    # #ASSUME: concurrency: check-then-act on (age_band, category) is unlocked;
    # two concurrent admin PUTs to the same cell can both miss the row and race
    # to INSERT. Admin-only and rare; the uq_moderation_threshold_band_category
    # UniqueConstraint is the backstop (the loser gets a 500, not corruption).
    # #VERIFY: switch to INSERT ... ON CONFLICT DO UPDATE if this ever recurs.
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
    # #CRITICAL: data-integrity: the pipeline event log is the durable record of
    # who changed surfacing policy and when; it must land in the same
    # transaction as the threshold write and its audit row.
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_threshold_upsert_emits_threshold_changed_event.
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="moderation_threshold",
        entity_id=age_band,
        event_type=EventType.THRESHOLD_CHANGED,
        payload={
            "age_band": age_band,
            "category": category,
            "action": "upsert",
            "min_verdict": body.min_verdict,
            "min_score": body.min_score,
        },
    )
    return ThresholdView(
        age_band=age_band,
        category=category,
        min_verdict=body.min_verdict,
        min_score=body.min_score,
    )


@router.delete("/admin/moderation-thresholds/{age_band}")
async def delete_threshold(
    age_band: str, category: str, ctx: Context
) -> ThresholdListView:
    """Remove one override (reverting to the default); audit it (admin only).

    ``category`` is a QUERY parameter for the same slash-in-category reason
    as the upsert route.

    Args:
        age_band: The age band half of the natural key (path).
        category: The category half of the natural key (query).
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
    # #ASSUME: concurrency: check-then-act on the natural key is unlocked,
    # accepting the same benign race as upsert_threshold (two admins deleting
    # the same row concurrently; one gets a 404-after-check failure at flush).
    # #VERIFY: acceptable for an admin-curated table; revisit if the console
    # ever automates edits.
    row = await _get_row(ctx, age_band, category)
    if row is None:
        msg = f"no threshold override for ({age_band}, {category})"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: data-integrity: the audit row and the delete share one
    # transaction, so the trail can never record a delete that did not happen
    # (or miss one that did).
    # #VERIFY: tests/integration/test_moderation_thresholds_api.py::
    # test_audit_rows_capture_changed_by_and_old_new_values.
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
    # #CRITICAL: data-integrity: same durability requirement as the upsert
    # path; only the keys known at delete time go into the payload, no
    # min_verdict/min_score (those describe a value that no longer exists).
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_threshold_delete_emits_threshold_changed_event.
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="moderation_threshold",
        entity_id=age_band,
        event_type=EventType.THRESHOLD_CHANGED,
        payload={"age_band": age_band, "category": category, "action": "delete"},
    )
    return await list_thresholds(ctx)


# ---------------------------------------------------------------------------
# Admin noise-floor endpoints (WS-A admin noise-floor addendum, Task A3)
# ---------------------------------------------------------------------------


@router.get("/admin/moderation/noise-floor")
async def get_noise_floor(ctx: Context) -> NoiseFloorView:
    """Return the global admin noise floor (admin only).

    Args:
        ctx: The request context (principal + session).

    Returns:
        NoiseFloorView: The stored floor, or the code default when no row
        has been persisted yet.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    _require_admin(ctx)
    # #ASSUME: external-resources: one primary-key lookup with a code-default
    # fallback when the seed row is absent; see load_admin_noise_floor for the
    # missing-row-versus-missing-table boundary.
    # #VERIFY: tests/integration/test_moderation_noise_floor_api.py.
    value = await load_admin_noise_floor(ctx.session)
    return NoiseFloorView(value=value)


@router.put("/admin/moderation/noise-floor")
async def update_noise_floor(
    body: NoiseFloorUpdateBody, ctx: Context
) -> NoiseFloorView:
    """Create or update the global admin noise floor (admin only).

    Args:
        body: The desired floor value, already bounded to [0, 1] by the
            schema (out-of-range values 422 before this runs).
        ctx: The request context (principal + session).

    Returns:
        NoiseFloorView: The stored floor after the write.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #ASSUME: security: the floor governs what admins see on the review
    # surface; the role gate runs before any query.
    _require_admin(ctx)
    # #ASSUME: concurrency: check-then-act on the single 'admin_noise_floor'
    # key is unlocked; two concurrent admin PUTs can both miss the row and
    # race to INSERT, the loser gets a PK-conflict 500. Admin-only and rare.
    # #VERIFY: switch to INSERT ... ON CONFLICT DO UPDATE if it recurs.
    row = await ctx.session.get(ModerationSetting, _NOISE_FLOOR_KEY)
    if row is None:
        row = ModerationSetting(
            key=_NOISE_FLOOR_KEY,
            value=body.value,
            updated_by=ctx.principal.user_id,
        )
        ctx.session.add(row)
    else:
        row.value = body.value
        row.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    # #CRITICAL: data-integrity: the noise floor governs what surfaces on the
    # admin review queue for every family; the event must land in the same
    # transaction as the setting write.
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_noise_floor_update_emits_noise_floor_changed_event.
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="moderation_setting",
        entity_id="admin_noise_floor",
        event_type=EventType.NOISE_FLOOR_CHANGED,
        payload={"value": row.value},
    )
    return NoiseFloorView(value=row.value)
