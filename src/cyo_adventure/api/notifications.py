"""Guardian notification feed: a read-only projection over pipeline_event.

Delivery infrastructure (S9) first slice: guardian digest/alerts (G10) for
a story awaiting consent, a story ready on the shelf, kid-flagged content,
and a failed generation. ``GET /notifications`` is poll-only (client-side
unread state; the caller re-polls with ``since`` set to the newest
``occurred_at`` it has already shown). ``GET /notifications/stream`` (added
alongside it, never replacing it) is a push transport: an authenticated
Server-Sent Events endpoint that re-runs the SAME family-scoped projection
(``notifications/service.py::list_guardian_notifications``) on a short
server-side interval and pushes new items to an open connection, so a
guardian with a tab open sees a safety-relevant alert in near-real-time
instead of waiting for the next 30s badge poll. It is deliberately NOT a
WebSocket: ``middleware/security.py``'s ``HealthExemptHTTPSRedirectMiddleware``
docstring notes no route in this app accepts a WebSocket upgrade, and SSE
needs no new dependency (FastAPI's native ``StreamingResponse``) where a
WebSocket route would need new middleware-layer support this app does not
have. The frontend (``NotificationBell.tsx``) prefers the stream and falls
back to the existing poll on any connection failure -- the poll path is
never removed, this is additive.

Still genuinely missing (S9's remaining half, tracked separately): a
server-scheduled digest job. This module has no cron/RQ job that batches a
day's ``info``-severity events into one digest; both endpoints here are
pull/push projections a client must be connected (or polling) to receive.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from cyo_adventure.api.deps import (
    Context,
    Principal,
    SessionFactory,
    require_principal,
)
from cyo_adventure.api.schemas import NotificationListView, NotificationView
from cyo_adventure.api.sentinel_log import strip_and_log
from cyo_adventure.core.config import settings
from cyo_adventure.core.database import apply_family_rls_context
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.notifications.models import NotificationItem
from cyo_adventure.notifications.service import list_guardian_notifications
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.utils.redaction import digest_identifier

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

_logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["notifications"])

_DEFAULT_LIMIT = 30
_MAX_LIMIT = 100
_STREAM_LIMIT = 30


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


def _to_view(item: NotificationItem) -> NotificationView:
    """Build the wire-ready view for one projected item.

    Shared by both the poll (``GET /notifications``) and push
    (``GET /notifications/stream``) transports so the sentinel-stripping
    boundary below has exactly one implementation.

    Args:
        item: One item from ``list_guardian_notifications``.

    Returns:
        NotificationView: The wire-ready view.
    """
    # #CRITICAL: security: title/body are composed in
    # notifications/registry.py (e.g. f"{_story_label(ctx)} is ready on the
    # shelf"), from a story title that may itself carry personalization
    # sentinels (notifications/service.py projects blob["title"] into
    # EntityContext.storybook_title, unstripped). Strip them here, at the
    # wire-serialization boundary shared by both transports, so a raw
    # {~SLOTID:value~} token never reaches a guardian's feed or stream.
    # #VERIFY: tests/unit/test_notifications_api_unit.py::
    # TestListNotificationsResponseShape::
    # test_sentinels_are_stripped_from_title_and_body;
    # TestStreamNotifications::test_stream_strips_sentinels_from_pushed_items.
    return NotificationView(
        id=item.id,
        occurred_at=item.occurred_at,
        kind=item.kind,
        severity=item.severity,
        title=strip_and_log(
            item.title,
            at="notification.title",
            storybook_id=item.storybook_id,
        ),
        body=strip_and_log(
            item.body,
            at="notification.body",
            storybook_id=item.storybook_id,
        ),
        storybook_id=item.storybook_id,
        request_id=item.request_id,
        profile_id=item.profile_id,
    )


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
    return NotificationListView(notifications=[_to_view(item) for item in items])


def _format_sse_frame(item: NotificationItem) -> str:
    """Render one notification as a ``text/event-stream`` frame.

    Args:
        item: One item from ``list_guardian_notifications``.

    Returns:
        str: An ``event: notification`` frame carrying the item's
        sentinel-stripped JSON view as ``data``, terminated by the blank
        line the SSE wire format requires between frames.
    """
    payload = _to_view(item).model_dump_json()
    return f"event: notification\ndata: {payload}\n\n"


# A comment line (":" prefix) per the SSE wire format: valid framing that
# carries no ``data:``/``event:`` field, so EventSource and a manual
# text/event-stream parser both ignore it as a payload but still see bytes
# arrive, which is what keeps an idle connection from reading as stalled to
# the client, to any intermediary proxy's idle-timeout, and to
# ``request.is_disconnected()``'s own liveness check on the next loop tick.
_KEEPALIVE_FRAME = ": keep-alive\n\n"


@dataclass(frozen=True, slots=True)
class _StreamConfig:
    """The streaming knobs for one SSE connection's poll loop.

    Bundled into one parameter (rather than three positional/keyword
    arguments on ``_notification_event_source``) purely to keep that
    function's signature within this package's Ruff PLR0913 limit; it
    carries no behavior of its own.
    """

    is_disconnected: Callable[[], Awaitable[bool]]
    poll_interval: float
    max_seconds: float


async def _notification_event_source(
    principal: Principal,
    *,
    since: datetime | None,
    config: _StreamConfig,
    session_factory: Callable[[], AsyncSession],
) -> AsyncIterator[str]:
    """Poll the guardian projection and yield new items as SSE frames.

    Reuses ``list_guardian_notifications`` (the same family-scoped, sentinel-
    unaware projection ``GET /notifications`` calls) on a
    ``config.poll_interval``-second cadence; never duplicates its query or
    family-scoping logic. Self-closes after ``config.max_seconds`` (see
    ``Settings.notification_stream_max_seconds`` for why that bound exists)
    so the caller's own generator (and, in production, the frontend's
    reconnect loop) owns re-establishing the connection.

    Args:
        principal: The already-authenticated, already guardian-role-checked
            principal (the caller confirms both before this generator is
            ever constructed).
        since: The initial lower bound on ``occurred_at`` (the caller's
            last-known timestamp, so a freshly (re)opened connection still
            catches anything that arrived while it was closed), or None for
            no lower bound.
        config: The poll cadence, self-close bound, and disconnect predicate
            for this connection (see ``_StreamConfig``). ``is_disconnected``
            is checked at the top of every loop iteration;
            ``request.is_disconnected`` in production, a test double in unit
            tests (see the #CRITICAL note below on why this is passed as a
            callable rather than a closed-over ``Request``).
        session_factory: Opens one fresh database session per poll tick. The
            caller injects it via ``deps.get_session_factory``, so this
            generator never reaches for the module-level factory and stays
            reachable by ``app.dependency_overrides`` like every other route.

    Yields:
        str: One SSE frame per new notification (newest last, so a client
        appending in arrival order sees chronological order), or a
        keep-alive comment frame on a tick with nothing new.
    """
    # #CRITICAL: external-resources: this opens and closes a FRESH,
    # short-lived database session on every poll tick rather than holding one
    # session (and its pooled connection) open for the whole SSE connection's
    # lifetime. An open guardian tab can live for max_seconds; holding a
    # pooled connection for that entire span, per concurrently open tab,
    # would compete with request-path connections for the same
    # database_pool_size/database_max_overflow ceiling (core/database.py) far
    # more aggressively than the brief per-tick checkout this does instead.
    # The sessions come from the INJECTED factory (deps.get_session_factory),
    # never from the module-level one: a direct core/database.py::get_session
    # call is bound to the real engine at import and silently bypasses
    # app.dependency_overrides, so tests would talk to the wrong database.
    # #VERIFY: tests/unit/test_notifications_api_unit.py::
    # TestNotificationEventSource::test_closes_the_session_after_each_poll_tick.
    #
    # #CRITICAL: security: apply_family_rls_context is re-applied on EVERY
    # fresh session (not just the caller's initial auth session), from the
    # same verified principal.family_id/is_admin the route already checked --
    # never from request input -- so the Tier 1 RLS guarantee (ADR-022) holds
    # for every poll tick, not just the connection's first query.
    # #VERIFY: tests/integration/test_rls_tier1_enforcement.py's existing
    # coverage of apply_family_rls_context applies identically here, since
    # this calls the exact same function with the exact same argument shape.
    loop_start = time.monotonic()
    last_seen = since
    try:
        while True:
            if await config.is_disconnected():
                break
            if time.monotonic() - loop_start >= config.max_seconds:
                break
            session = session_factory()
            try:
                await apply_family_rls_context(
                    session, family_id=principal.family_id, is_admin=principal.is_admin
                )
                items = await list_guardian_notifications(
                    session, principal, since=last_seen, limit=_STREAM_LIMIT
                )
            finally:
                await session.close()
            if items:
                # Newest first (list_guardian_notifications's contract);
                # advance the watermark from the newest before reversing for
                # chronological emission order.
                last_seen = items[0].occurred_at
                for item in reversed(items):
                    yield _format_sse_frame(item)
            else:
                yield _KEEPALIVE_FRAME
            await asyncio.sleep(config.poll_interval)
    finally:
        # Reached on a client disconnect, the max_seconds self-close, or an
        # unhandled exception propagating out of the loop body; in every
        # case the generator is done and holds no further resources (the
        # per-tick session above is already closed by its own try/finally).
        # #CRITICAL: security: principal.subject can BE the caller's raw
        # credential. In ENVIRONMENT=local, deps._resolve_subject returns the
        # bearer token verbatim (the documented dev auth seam), so logging it
        # wrote the raw Authorization value on every stream close. Outside
        # local it is the OIDC `sub`, a stable user identifier that still does
        # not belong in a log line unhashed. The digest keeps the field's only
        # real use, correlating a reconnect loop from one caller, without
        # publishing either form.
        # #VERIFY: tests/unit/test_notifications_api_unit.py::
        # TestStreamCloseNeverLogsTheRawSubject asserts the raw subject never
        # appears in the emitted event.
        _logger.info(
            "notification stream closed",
            subject_digest=digest_identifier(principal.subject),
        )


@router.get("/notifications/stream")
async def stream_notifications(
    request: Request,
    session_factory: SessionFactory,
    authorization: Annotated[str | None, Header()] = None,
    since: str | None = None,
) -> StreamingResponse:
    """Authenticated SSE push transport for the guardian notification feed.

    Additive alongside ``GET /notifications``: reuses the same family-scoped
    projection and never replaces the poll path (see the module docstring).
    The caller resolves and role-checks the principal itself, with its own
    short-lived database session closed before the stream begins, rather
    than depending on ``Context``/``CurrentPrincipal`` -- a FastAPI ``yield``
    dependency's session stays open for the entire response, which for a
    ``StreamingResponse`` means the whole connection's lifetime; resolving
    auth on a session that closes immediately, then having the generator
    open its own short-lived sessions per poll tick, is what keeps this
    endpoint from holding one connection per open guardian tab. Both of
    those session sets come from the INJECTED ``SessionFactory``, so
    declining ``DbSession`` costs this route no test seam: an override
    installed on ``get_session_factory`` reaches the auth check and every
    poll tick alike.

    Args:
        request: The ASGI request; only ``is_disconnected()`` is used, to
            let the streaming generator notice a client-side close.
        session_factory: Injected opener for the short-lived sessions this
            route and its generator use (see ``deps.get_session_factory``).
        authorization: The ``Authorization`` header (same bearer contract as
            every other authenticated route; see ``api/deps.py``).
        since: Optional ISO-8601 lower bound (exclusive) on ``occurred_at``,
            same contract as ``GET /notifications``'s query param, so a
            client can pass its last-known timestamp and the newly (re)opened
            stream still pushes anything that arrived while it was closed.

    Returns:
        StreamingResponse: A ``text/event-stream`` response.

    Raises:
        AuthenticationError: If the token is missing or fails verification
            (-> 401), raised by ``require_principal``.
        AuthorizationError: If the caller does not hold the guardian base
            role (-> 403); same guardian-only rationale as
            ``GET /notifications`` (see its docstring).
        ValidationError: If ``since`` is present but not ISO-8601 (-> 422).
    """
    # #CRITICAL: security: auth is resolved BEFORE the StreamingResponse (and
    # therefore before any byte is sent), on a session opened and closed
    # solely for this check -- identical bearer-token contract to every other
    # route (require_principal), just called directly instead of through
    # Context/CurrentPrincipal for the connection-lifetime reason in the
    # docstring above.
    # #VERIFY: tests/unit/test_notifications_api_unit.py::
    # TestStreamNotifications::test_stream_requires_authentication;
    # test_stream_rejects_non_guardian_roles.
    session = session_factory()
    try:
        principal = await require_principal(session, authorization)
    finally:
        await session.close()
    # #CRITICAL: security: guardian-only, checked before the stream opens, for
    # the exact reason GET /notifications is guardian-only (see its
    # docstring): this pushes the same safety-sensitive, child-naming text a
    # child or device token must never see, and an admin-only adult has no
    # guardian family-scoping meaning either.
    if not principal.is_guardian:
        msg = "guardian role required"
        raise AuthorizationError(msg)
    since_dt = _parse_since(since)
    return StreamingResponse(
        _notification_event_source(
            principal,
            since=since_dt,
            session_factory=session_factory,
            config=_StreamConfig(
                is_disconnected=request.is_disconnected,
                poll_interval=settings.notification_stream_poll_seconds,
                max_seconds=settings.notification_stream_max_seconds,
            ),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # #EDGE: external-resources: disables response buffering on an
            # nginx reverse proxy specifically (a de facto standard header
            # for this, ignored harmlessly by anything else); without it a
            # proxy sitting in front of this app could buffer the whole
            # response before forwarding, defeating the push behavior
            # entirely while still working (degrading silently to
            # poll-at-proxy-flush rather than erroring). GZipMiddleware
            # (app.py) may similarly delay a keep-alive frame's flush by a
            # compression-buffer window; accepted because the frontend's
            # polling fallback (NotificationBell.tsx) covers a stream that
            # is alive but slow to flush exactly the same way it covers one
            # that fails outright.
            # #VERIFY: none automated (a real reverse-proxy/gzip interaction
            # is not exercised by the ASGI-in-process test client); this is
            # a deployment-configuration concern, not a code-correctness one.
            "X-Accel-Buffering": "no",
        },
    )
