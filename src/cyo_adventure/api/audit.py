"""Admin-only audit view over the append-only pipeline event log (register A13).

Phase 5 (M5) deliverable: a filterable read surface answering "who did what
to child-linked data." This is a pure projection over ``pipeline_event``
(``events/writer.py`` is the only writer; see ``events/models.py`` for the
``EventType`` vocabulary and the actor/system-actor invariant). No new table,
no write path here: this module only ever reads.

Response models are defined in this module rather than ``api/schemas.py`` so
the audit surface stays self-contained (matches the ownership boundary this
feature was built under).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from cyo_adventure.api.deps import Context, parse_uuid
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.db.models import PipelineEvent
from cyo_adventure.events import EventType

if TYPE_CHECKING:
    import uuid

    from sqlalchemy import ColumnElement

router = APIRouter(prefix="/api/v1", tags=["audit"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200
_KNOWN_KINDS = frozenset(kind.value for kind in EventType)


class AuditEventView(BaseModel):
    """One append-only pipeline_event row, projected for the admin console."""

    id: str
    occurred_at: datetime
    actor_id: str | None
    actor_role: str
    entity_type: str
    entity_id: str
    event_type: str
    from_state: str | None
    to_state: str | None
    payload: dict[str, object]


class AuditListView(BaseModel):
    """A page of the audit log, newest first."""

    events: list[AuditEventView]
    limit: int
    offset: int
    has_more: bool


class AuditFilters(BaseModel):
    """Query parameters for ``GET /admin/audit`` (see ``list_audit_events``).

    Bundled into one Pydantic query-parameter model (FastAPI's "Query
    Parameter Models" support) rather than eight individual handler
    arguments, to stay within this repo's function argument-count budget
    (PLR0913, ``max-args = 4``) -- the same reason ``reading_history.py``
    bundles per-book activity into ``_BookActivity`` instead of passing
    each field separately. ``extra="forbid"`` rejects an unknown query key
    with a 422 rather than silently ignoring it (mirrors
    ``KidFlagCreateBody``'s no-smuggled-field stance).

    Every field is a raw string (or int): ids and timestamps are validated
    and parsed by the route handler, not by Pydantic's own coercion, so a
    malformed value raises this codebase's ``ValidationError`` (-> 422 via
    the shared exception handler) with the same shape as every other
    hand-parsed id/timestamp query param in this API (see
    ``notifications.py::_parse_since``, ``api/deps.py::parse_uuid``).
    """

    model_config = ConfigDict(extra="forbid")

    kind: str | None = None
    actor_id: str | None = None
    storybook_id: str | None = None
    profile_id: str | None = None
    since: str | None = None
    until: str | None = None
    limit: int = _DEFAULT_LIMIT
    offset: int = 0


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before any query runs.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #CRITICAL: security: pipeline_event rows describe cross-family actions
    # on child-linked data (WS-J user management, moderation, ratings, kid
    # flags, ...); the role gate runs before any query so a non-admin learns
    # nothing about who did what, mirroring
    # moderation_thresholds.py::_require_admin and
    # moderation_dashboard.py::_require_admin.
    # #VERIFY: tests/unit/test_audit_api_unit.py::TestListAuditEventsRoleGate;
    # tests/integration/test_authz_matrix.py pins GET /api/v1/admin/audit
    # admin-only.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


def _validate_kind(kind: str | None) -> None:
    """Reject an out-of-vocabulary ``kind`` filter with a 422-mapped error.

    Args:
        kind: The raw ``kind`` query parameter, or ``None`` for no filter.

    Raises:
        ValidationError: If ``kind`` is present but not a known ``EventType``.
    """
    if kind is not None and kind not in _KNOWN_KINDS:
        msg = "kind must be a known pipeline event type"
        raise ValidationError(msg, field="kind", value=kind)


def _parse_timestamp(raw: str | None, field: str) -> datetime | None:
    """Parse an optional ISO-8601 query param as an aware UTC datetime.

    Args:
        raw: The raw ISO-8601 query value, or ``None``.
        field: The query parameter name, for the error message.

    Returns:
        datetime | None: The parsed, timezone-aware timestamp, or ``None``.

    Raises:
        ValidationError: If ``raw`` is present but not valid ISO-8601 (422).
    """
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        msg = f"{field} must be an ISO-8601 timestamp"
        raise ValidationError(msg, field=field, value=raw) from exc
    # #ASSUME: data-integrity: a naive timestamp (no UTC offset) is treated as
    # UTC rather than rejected, mirroring
    # notifications.py::_parse_since. occurred_at is stored TIMESTAMPTZ; a
    # caller's admin-console date-range input is more likely to be
    # accidentally-naive than malicious, and this only narrows or widens the
    # result WINDOW, never any authorization boundary.
    # #VERIFY: tests/unit/test_audit_api_unit.py::
    # test_naive_since_and_until_are_treated_as_utc.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _bound_limit(limit: int) -> int:
    """Clamp the caller's requested page size to a positive, sane range.

    Args:
        limit: The caller-supplied limit.

    Returns:
        int: ``limit`` clamped to ``[1, _MAX_LIMIT]``.
    """
    return max(1, min(limit, _MAX_LIMIT))


def _bound_offset(offset: int) -> int:
    """Clamp the caller's requested offset to a non-negative value.

    Args:
        offset: The caller-supplied offset.

    Returns:
        int: ``offset`` clamped to ``>= 0``.
    """
    return max(0, offset)


def _storybook_match(storybook_id: str) -> ColumnElement[bool]:
    """Build the entity_id predicate for a ``storybook_id`` filter.

    ``entity_id`` is a free-form string whose shape depends on
    ``entity_type`` (see ``events/writer.py`` call sites): a bare storybook
    id (``entity_type="storybook"``), a ``"{storybook_id}:{version}"`` pair
    (``storybook_version``), or a ``"{profile_id}:{storybook_id}"`` pair
    (``storybook_assignment``, ``rating``). There is no dedicated
    ``storybook_id`` column, so this matches all three known shapes.

    # #EDGE: data-integrity: ``kid_flagged`` events carry ``storybook_id``
    # only in ``payload`` (entity_id is the flag's own id), so they are not
    # matched by this filter. An admin can still find them via
    # ``kind=kid_flagged`` and reading the payload.
    # #VERIFY: tests/unit/test_audit_api_unit.py::
    # test_storybook_id_filter_matches_known_entity_id_shapes.

    Args:
        storybook_id: The storybook id to match.

    Returns:
        ColumnElement[bool]: A predicate true for any of the three shapes.
    """
    return (
        (PipelineEvent.entity_id == storybook_id)
        | PipelineEvent.entity_id.startswith(f"{storybook_id}:")
        | PipelineEvent.entity_id.endswith(f":{storybook_id}")
    )


def _profile_match(profile_id: uuid.UUID) -> ColumnElement[bool]:
    """Build the entity_id predicate for a ``profile_id`` filter.

    Every event type that names a child profile in ``entity_id`` writes it
    as the leading ``"{profile_id}:..."`` segment (``storybook_assignment``,
    ``rating``; see ``events/writer.py`` call sites).

    # #EDGE: data-integrity: ``book_assigned`` also carries
    # ``child_profile_id`` in ``payload``, redundant with the entity_id
    # prefix this matches; no other event type currently names a profile
    # only in payload.
    # #VERIFY: tests/unit/test_audit_api_unit.py::
    # test_profile_id_filter_matches_prefix_shape.

    Args:
        profile_id: The child profile id to match.

    Returns:
        ColumnElement[bool]: A predicate true when entity_id is prefixed by
        the profile id.
    """
    return PipelineEvent.entity_id.startswith(f"{profile_id}:")


@router.get("/admin/audit")
async def list_audit_events(
    ctx: Context, filters: Annotated[AuditFilters, Query()]
) -> AuditListView:
    """List pipeline_event rows, newest first, with optional filters (admin only).

    Register A13, the view half: a filterable projection over the append-only
    pipeline event log answering "who did what to child-linked data" (M5 /
    Phase 5). Every filter is optional and they compose with AND.

    Args:
        ctx: The request context (principal + session).
        filters: The query parameters, bundled into ``AuditFilters`` to stay
            within the argument-count budget (see that class's docstring):
            ``kind`` (one of ``EventType``'s values), ``actor_id`` (a UUID
            string), ``storybook_id`` (see ``_storybook_match`` for the
            entity_id shapes this matches), ``profile_id`` (a UUID string;
            see ``_profile_match``), ``since``/``until`` (ISO-8601 bounds,
            inclusive, on ``occurred_at``), ``limit`` (default 50, clamped
            to [1, 200]), and ``offset`` (clamped to >= 0).

    Returns:
        AuditListView: Up to ``limit`` matching rows, newest first
        (``occurred_at`` descending, ``id`` descending as a stable
        tie-break), plus ``has_more`` for the next page.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ValidationError: If ``kind`` is not a known event type, ``actor_id``
            or ``profile_id`` is not a UUID, or ``since``/``until`` is not
            ISO-8601 (422).
    """
    _require_admin(ctx)
    _validate_kind(filters.kind)
    actor_uuid = (
        parse_uuid(filters.actor_id, "actor_id")
        if filters.actor_id is not None
        else None
    )
    profile_uuid = (
        parse_uuid(filters.profile_id, "profile_id")
        if filters.profile_id is not None
        else None
    )
    since_dt = _parse_timestamp(filters.since, "since")
    until_dt = _parse_timestamp(filters.until, "until")
    bounded_limit = _bound_limit(filters.limit)
    bounded_offset = _bound_offset(filters.offset)

    stmt = select(PipelineEvent)
    if filters.kind is not None:
        stmt = stmt.where(PipelineEvent.event_type == filters.kind)
    if actor_uuid is not None:
        stmt = stmt.where(PipelineEvent.actor_id == actor_uuid)
    if filters.storybook_id is not None:
        stmt = stmt.where(_storybook_match(filters.storybook_id))
    if profile_uuid is not None:
        stmt = stmt.where(_profile_match(profile_uuid))
    if since_dt is not None:
        stmt = stmt.where(PipelineEvent.occurred_at >= since_dt)
    if until_dt is not None:
        stmt = stmt.where(PipelineEvent.occurred_at <= until_dt)
    stmt = (
        stmt.order_by(PipelineEvent.occurred_at.desc(), PipelineEvent.id.desc())
        .offset(bounded_offset)
        # #ASSUME: external-resources: fetch one extra row to derive
        # has_more without a second COUNT(*) query; the admin console never
        # needs a total, only "is there a next page" (mirrors keyset-style
        # over-fetch, not a true keyset cursor -- offset is still the paging
        # token here, consistent with this codebase's other list endpoints,
        # none of which use a cursor).
        # #VERIFY: tests/unit/test_audit_api_unit.py::
        # test_has_more_true_when_extra_row_exists,
        # test_has_more_false_when_exactly_limit_rows_exist.
        .limit(bounded_limit + 1)
    )
    rows = list((await ctx.session.scalars(stmt)).all())
    has_more = len(rows) > bounded_limit
    page = rows[:bounded_limit]
    return AuditListView(
        events=[
            AuditEventView(
                id=str(row.id),
                occurred_at=row.occurred_at,
                actor_id=str(row.actor_id) if row.actor_id is not None else None,
                actor_role=row.actor_role,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                event_type=row.event_type,
                from_state=row.from_state,
                to_state=row.to_state,
                payload=row.payload,
            )
            for row in page
        ],
        limit=bounded_limit,
        offset=bounded_offset,
        has_more=has_more,
    )
