"""Guardian notification feed: a read-only projection over pipeline_event.

Delivery infrastructure (S9) first slice: guardian digest/alerts (G10) for
a story awaiting consent, a story ready on the shelf, kid-flagged content,
and a failed generation. No new tables, no push channel; unread state is
client-side for this slice (the caller re-polls with ``since`` set to the
newest ``occurred_at`` it has already shown -- see
``notifications/service.py`` for the projection and family-scoping logic).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import NotificationListView, NotificationView
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.notifications.service import list_guardian_notifications

router = APIRouter(prefix="/api/v1", tags=["notifications"])

_DEFAULT_LIMIT = 30
_MAX_LIMIT = 100


def _parse_since(raw: str | None) -> datetime | None:
    """Parse the optional ``since`` query param as an aware UTC datetime.

    Args:
        raw: The raw ISO-8601 query value, or None.

    Returns:
        datetime | None: The parsed, timezone-aware timestamp, or None.

    Raises:
        ValidationError: If ``raw`` is present but not valid ISO-8601 (-> 422).
    """
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        msg = "since must be an ISO-8601 timestamp"
        raise ValidationError(msg, field="since", value=raw) from exc
    # #ASSUME: data-integrity: a naive timestamp (no UTC offset) is treated as
    # UTC rather than rejected. occurred_at is stored TIMESTAMPTZ, and a
    # client's "last seen" clock is more likely to be an accidentally-naive
    # local timestamp than a malicious one; this only ever narrows or widens
    # the result WINDOW, it never crosses a family boundary (that scoping is
    # enforced independently in notifications/service.py).
    # #VERIFY: tests/unit/test_notifications_api_unit.py::
    # test_parse_since_treats_naive_timestamp_as_utc.
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


@router.get("/notifications")
async def list_notifications(
    ctx: Context,
    since: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> NotificationListView:
    """List the calling guardian's family-scoped notification feed.

    A read-only projection over ``pipeline_event`` (S9 delivery
    infrastructure; see ``notifications/service.py`` for the family-scoping
    mechanism). Unread state is client-side for this first slice: a caller
    tracks the newest ``occurred_at`` it has already shown and passes it back
    as ``since`` on the next poll.

    Args:
        ctx: The request context (principal and session).
        since: Optional ISO-8601 lower bound (exclusive) on ``occurred_at``.
        limit: Maximum items to return (default 30, clamped to [1, 100]).

    Returns:
        NotificationListView: Up to ``limit`` items, newest first.

    Raises:
        AuthorizationError: If the caller does not hold the guardian base
            role (-> 403). This is a guardian-only surface: it composes
            safety-sensitive text (a blocked or flagged story, naming the
            child involved) that a child must never see, and it is scoped to
            ``Principal.family_id``, which has no guardian meaning for an
            admin-only adult (mirrors the guardian-only gate in
            api/assignments.py and api/profiles.py).
        ValidationError: If ``since`` is present but not ISO-8601 (-> 422).
    """
    # #CRITICAL: security: guardian-only, checked before any query runs. A
    # child or device token must never see this feed (it can name the child
    # and describe safety-sensitive events involving them); an admin-only
    # adult is rejected too, matching the guardian-only pattern elsewhere
    # (api/assignments.py::_require_guardian_visible_book,
    # api/profiles.py::_require_guardian).
    # #VERIFY: tests/unit/test_notifications_api_unit.py::
    # test_non_guardian_tokens_are_rejected_before_any_query; the route is
    # additionally pinned guardian-only in
    # tests/integration/test_authz_matrix.py's ROUTE_TABLE.
    if not ctx.principal.is_guardian:
        msg = "guardian role required"
        raise AuthorizationError(msg)
    since_dt = _parse_since(since)
    items = await list_guardian_notifications(
        ctx.session, ctx.principal, since=since_dt, limit=_bound_limit(limit)
    )
    return NotificationListView(
        notifications=[
            NotificationView(
                id=item.id,
                occurred_at=item.occurred_at,
                kind=item.kind,
                severity=item.severity,
                title=item.title,
                body=item.body,
                storybook_id=item.storybook_id,
                request_id=item.request_id,
                profile_id=item.profile_id,
            )
            for item in items
        ]
    )
