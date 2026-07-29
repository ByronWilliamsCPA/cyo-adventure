"""Unit tests for the notifications route handler (no DB, no ASGI stack).

Mirrors tests/unit/test_ratings_api_unit.py: calls the route function
directly with a constructed ``Principal`` and a stand-in session, patching
``list_guardian_notifications`` so the role gate and query-parsing helpers
are exercised in isolation from the projection itself (which has its own
dedicated tests in test_notifications_service.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi.responses import StreamingResponse

from cyo_adventure.api import notifications
from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ValidationError,
)
from cyo_adventure.notifications.models import NotificationItem
from cyo_adventure.storybook.sentinels import wrap


def _principal(role: str) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role=role,
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _ctx(role: str) -> RequestContext:
    return RequestContext(principal=_principal(role), session=cast("object", object()))


class TestParseSince:
    @pytest.mark.unit
    def test_none_returns_none(self) -> None:
        assert notifications._parse_since(None) is None

    @pytest.mark.unit
    def test_offset_aware_timestamp_round_trips(self) -> None:
        parsed = notifications._parse_since("2026-07-01T12:00:00+00:00")
        assert parsed == datetime(2026, 7, 1, 12, 0, tzinfo=UTC)

    @pytest.mark.unit
    def test_naive_timestamp_is_treated_as_utc(self) -> None:
        parsed = notifications._parse_since("2026-07-01T12:00:00")
        assert parsed is not None
        assert parsed.tzinfo == UTC

    @pytest.mark.unit
    def test_malformed_timestamp_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="since"):
            notifications._parse_since("not-a-timestamp")


class TestBoundLimit:
    @pytest.mark.unit
    def test_within_range_is_unchanged(self) -> None:
        assert notifications._bound_limit(10) == 10

    @pytest.mark.unit
    def test_zero_or_negative_clamps_to_one(self) -> None:
        assert notifications._bound_limit(0) == 1
        assert notifications._bound_limit(-5) == 1

    @pytest.mark.unit
    def test_above_ceiling_clamps_to_max(self) -> None:
        assert notifications._bound_limit(10_000) == notifications._MAX_LIMIT


class TestListNotificationsRoleGate:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_guardian_token_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: dict[str, object] = {}

        async def fake_list_guardian_notifications(
            session: object, principal: Principal, *, since: object, limit: int
        ) -> list[NotificationItem]:
            called["principal"] = principal
            called["since"] = since
            called["limit"] = limit
            return []

        monkeypatch.setattr(
            notifications,
            "list_guardian_notifications",
            fake_list_guardian_notifications,
        )

        view = await notifications.list_notifications(_ctx("guardian"))

        assert view.notifications == []
        assert called["limit"] == notifications._DEFAULT_LIMIT

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_token_is_rejected_before_any_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fail_if_called(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("the projection must not run for a rejected role")

        monkeypatch.setattr(
            notifications, "list_guardian_notifications", fail_if_called
        )

        ctx = _ctx("child")
        with pytest.raises(AuthorizationError):
            await notifications.list_notifications(ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_device_token_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fail_if_called(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("the projection must not run for a rejected role")

        monkeypatch.setattr(
            notifications, "list_guardian_notifications", fail_if_called
        )

        ctx = _ctx("device")
        with pytest.raises(AuthorizationError):
            await notifications.list_notifications(ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_admin_only_token_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An admin-only adult (no guardianship of their own) has no family
        # for this feed to be scoped to; the guardian-only gate rejects it
        # the same as it rejects a child or device token.
        async def fail_if_called(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("the projection must not run for a rejected role")

        monkeypatch.setattr(
            notifications, "list_guardian_notifications", fail_if_called
        )

        ctx = _ctx("admin")
        with pytest.raises(AuthorizationError):
            await notifications.list_notifications(ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_since_and_limit_are_parsed_and_forwarded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        async def fake_list_guardian_notifications(
            session: object, principal: Principal, *, since: object, limit: int
        ) -> list[NotificationItem]:
            captured["since"] = since
            captured["limit"] = limit
            return []

        monkeypatch.setattr(
            notifications,
            "list_guardian_notifications",
            fake_list_guardian_notifications,
        )

        await notifications.list_notifications(
            _ctx("guardian"), since="2026-07-01T00:00:00Z", limit=500
        )

        assert captured["since"] == datetime(2026, 7, 1, tzinfo=UTC)
        assert captured["limit"] == notifications._MAX_LIMIT

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_malformed_since_raises_before_calling_the_projection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fail_if_called(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("the projection must not run for bad input")

        monkeypatch.setattr(
            notifications, "list_guardian_notifications", fail_if_called
        )

        ctx = _ctx("guardian")
        with pytest.raises(ValidationError):
            await notifications.list_notifications(ctx, since="garbage")


class TestListNotificationsResponseShape:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_items_round_trip_into_the_view(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        item = NotificationItem(
            id="evt-1",
            occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
            kind="story_ready",
            severity="info",
            title="The Lighthouse Mystery is ready on the shelf",
            body="It has been approved and published to your family library.",
            storybook_id="the-lighthouse-mystery",
            request_id=None,
            profile_id=None,
        )

        async def fake_list_guardian_notifications(
            *_args: object, **_kwargs: object
        ) -> list[NotificationItem]:
            return [item]

        monkeypatch.setattr(
            notifications,
            "list_guardian_notifications",
            fake_list_guardian_notifications,
        )

        view = await notifications.list_notifications(_ctx("guardian"))

        assert len(view.notifications) == 1
        out = view.notifications[0]
        assert out.id == item.id
        assert out.kind == item.kind
        assert out.severity == item.severity
        assert out.title == item.title
        assert out.storybook_id == item.storybook_id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sentinels_are_stripped_from_title_and_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token = wrap("HERO", "Explorer")
        item = NotificationItem(
            id="evt-2",
            occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
            kind="story_ready",
            severity="info",
            title=f"{token}'s story is ready on the shelf",
            body=f"{token} has a new adventure waiting.",
            storybook_id="the-hero-chronicles",
            request_id=None,
            profile_id=None,
        )

        async def fake_list_guardian_notifications(
            *_args: object, **_kwargs: object
        ) -> list[NotificationItem]:
            return [item]

        monkeypatch.setattr(
            notifications,
            "list_guardian_notifications",
            fake_list_guardian_notifications,
        )

        view = await notifications.list_notifications(_ctx("guardian"))

        out = view.notifications[0]
        assert "{~" not in out.title
        assert "~}" not in out.title
        assert "Explorer" in out.title
        assert "{~" not in out.body
        assert "~}" not in out.body
        assert "Explorer" in out.body


def _item(
    item_id: str = "evt-1", *, title: str = "Ready", body: str = "Ready"
) -> NotificationItem:
    return NotificationItem(
        id=item_id,
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
        kind="story_ready",
        severity="info",
        title=title,
        body=body,
        storybook_id="the-lighthouse-mystery",
        request_id=None,
        profile_id=None,
    )


class _FakeSession:
    """Stand-in for AsyncSession: only tracks how many times close() runs."""

    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


class _ScriptedDisconnect:
    """A test double for ``is_disconnected``: replays a fixed answer sequence.

    The generator under test calls this once per loop iteration; the last
    scripted answer repeats forever so a test does not need to predict the
    exact call count.
    """

    def __init__(self, answers: list[bool]) -> None:
        self._answers = answers
        self.call_count = 0

    async def __call__(self) -> bool:
        index = min(self.call_count, len(self._answers) - 1)
        self.call_count += 1
        return self._answers[index]


class TestNotificationEventSource:
    """Tests for ``_notification_event_source``, the SSE push generator.

    Patches ``notifications.get_session``, ``apply_family_rls_context``, and
    ``list_guardian_notifications`` the same way TestListNotificationsRoleGate
    patches the poll path, so no real database or ASGI stack is needed.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_yields_a_frame_for_each_new_item_then_stops_on_disconnect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sessions: list[_FakeSession] = []

        def fake_get_session() -> _FakeSession:
            session = _FakeSession()
            sessions.append(session)
            return session

        async def fake_apply_family_rls_context(
            *_args: object, **_kwargs: object
        ) -> None:
            return None

        item = _item()

        async def fake_list_guardian_notifications(
            *_args: object, **_kwargs: object
        ) -> list[NotificationItem]:
            return [item]

        monkeypatch.setattr(notifications, "get_session", fake_get_session)
        monkeypatch.setattr(
            notifications, "apply_family_rls_context", fake_apply_family_rls_context
        )
        monkeypatch.setattr(
            notifications,
            "list_guardian_notifications",
            fake_list_guardian_notifications,
        )

        principal = _principal("guardian")
        config = notifications._StreamConfig(
            is_disconnected=_ScriptedDisconnect([False, True]),
            poll_interval=0.0,
            max_seconds=60.0,
        )

        frames = [
            frame
            async for frame in notifications._notification_event_source(
                principal, since=None, config=config
            )
        ]

        assert frames == [notifications._format_sse_frame(item)]
        assert len(sessions) == 1
        assert sessions[0].closed == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_yields_keepalive_when_nothing_new(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_apply_family_rls_context(
            *_args: object, **_kwargs: object
        ) -> None:
            return None

        async def fake_list_guardian_notifications(
            *_args: object, **_kwargs: object
        ) -> list[NotificationItem]:
            return []

        monkeypatch.setattr(notifications, "get_session", _FakeSession)
        monkeypatch.setattr(
            notifications, "apply_family_rls_context", fake_apply_family_rls_context
        )
        monkeypatch.setattr(
            notifications,
            "list_guardian_notifications",
            fake_list_guardian_notifications,
        )

        principal = _principal("guardian")
        config = notifications._StreamConfig(
            is_disconnected=_ScriptedDisconnect([False, True]),
            poll_interval=0.0,
            max_seconds=60.0,
        )

        frames = [
            frame
            async for frame in notifications._notification_event_source(
                principal, since=None, config=config
            )
        ]

        assert frames == [notifications._KEEPALIVE_FRAME]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_closes_the_session_after_each_poll_tick(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sessions: list[_FakeSession] = []

        def fake_get_session() -> _FakeSession:
            session = _FakeSession()
            sessions.append(session)
            return session

        async def fake_apply_family_rls_context(
            *_args: object, **_kwargs: object
        ) -> None:
            return None

        async def fake_list_guardian_notifications(
            *_args: object, **_kwargs: object
        ) -> list[NotificationItem]:
            return []

        monkeypatch.setattr(notifications, "get_session", fake_get_session)
        monkeypatch.setattr(
            notifications, "apply_family_rls_context", fake_apply_family_rls_context
        )
        monkeypatch.setattr(
            notifications,
            "list_guardian_notifications",
            fake_list_guardian_notifications,
        )

        principal = _principal("guardian")
        # Two ticks (False, False) then stop (True) on the third check.
        config = notifications._StreamConfig(
            is_disconnected=_ScriptedDisconnect([False, False, True]),
            poll_interval=0.0,
            max_seconds=60.0,
        )

        _ = [
            frame
            async for frame in notifications._notification_event_source(
                principal, since=None, config=config
            )
        ]

        # A fresh session per tick (never one held open across ticks), and
        # every one of them closed.
        assert len(sessions) == 2
        assert all(session.closed == 1 for session in sessions)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stops_immediately_when_already_disconnected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        get_session_calls = 0

        def fake_get_session() -> _FakeSession:
            nonlocal get_session_calls
            get_session_calls += 1
            return _FakeSession()

        async def fail_if_called(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("no query should run once the client is disconnected")

        monkeypatch.setattr(notifications, "get_session", fake_get_session)
        monkeypatch.setattr(notifications, "apply_family_rls_context", fail_if_called)
        monkeypatch.setattr(
            notifications, "list_guardian_notifications", fail_if_called
        )

        principal = _principal("guardian")
        config = notifications._StreamConfig(
            is_disconnected=_ScriptedDisconnect([True]),
            poll_interval=0.0,
            max_seconds=60.0,
        )

        frames = [
            frame
            async for frame in notifications._notification_event_source(
                principal, since=None, config=config
            )
        ]

        assert frames == []
        assert get_session_calls == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stops_after_max_seconds_elapses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        get_session_calls = 0

        def fake_get_session() -> _FakeSession:
            nonlocal get_session_calls
            get_session_calls += 1
            return _FakeSession()

        async def fail_if_called(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("no query should run once max_seconds has elapsed")

        monkeypatch.setattr(notifications, "get_session", fake_get_session)
        monkeypatch.setattr(notifications, "apply_family_rls_context", fail_if_called)
        monkeypatch.setattr(
            notifications, "list_guardian_notifications", fail_if_called
        )

        # #ASSUME: timing-dependencies: max_seconds=0.0 rather than a mocked
        # clock. Patching notifications.time.monotonic globally corrupts
        # pytest's own internal timing (pytest-asyncio's event loop and
        # pytest's own instant-based teardown both call time.monotonic()
        # through the SAME module object notifications.py imports, since
        # `import time` binds the module, not a name-local copy), which
        # manifested as a `RuntimeError: generator raised StopIteration`
        # in an unrelated fixture teardown when this test first tried that
        # approach. A max_seconds of 0.0 makes the elapsed-time check true
        # on the very first tick using the real clock (any elapsed span is
        # >= 0.0), which exercises the exact same self-close branch without
        # touching a module every other test and pytest itself depend on.
        # #VERIFY: get_session_calls == 0 below proves the branch that
        # matters (no query runs once the bound is hit) actually fired.
        principal = _principal("guardian")
        config = notifications._StreamConfig(
            is_disconnected=_ScriptedDisconnect([False]),
            poll_interval=0.0,
            max_seconds=0.0,
        )

        frames = [
            frame
            async for frame in notifications._notification_event_source(
                principal, since=None, config=config
            )
        ]

        assert frames == []
        assert get_session_calls == 0


class TestFormatSseFrame:
    @pytest.mark.unit
    def test_frame_carries_the_event_and_data_fields(self) -> None:
        item = _item()

        frame = notifications._format_sse_frame(item)

        assert frame.startswith("event: notification\ndata: ")
        assert frame.endswith("\n\n")
        assert item.id in frame

    @pytest.mark.unit
    def test_sentinels_are_stripped_from_pushed_items(self) -> None:
        token = wrap("HERO", "Explorer")
        item = _item(
            title=f"{token}'s story is ready", body=f"{token} has a new adventure."
        )

        frame = notifications._format_sse_frame(item)

        assert "{~" not in frame
        assert "~}" not in frame
        assert "Explorer" in frame


class _FakeRequest:
    """Stand-in for ``fastapi.Request``: only ``is_disconnected`` is used."""

    async def is_disconnected(self) -> bool:
        return False


class TestStreamNotifications:
    """Tests for the ``GET /notifications/stream`` route handler."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stream_requires_authentication(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(notifications, "get_session", _FakeSession)

        async def fake_require_principal(
            *_args: object, **_kwargs: object
        ) -> Principal:
            raise AuthenticationError("missing or invalid token")

        monkeypatch.setattr(notifications, "require_principal", fake_require_principal)

        with pytest.raises(AuthenticationError):
            await notifications.stream_notifications(
                cast("object", object()), authorization=None
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stream_rejects_non_guardian_roles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(notifications, "get_session", _FakeSession)

        async def fake_require_principal(
            *_args: object, **_kwargs: object
        ) -> Principal:
            return _principal("child")

        monkeypatch.setattr(notifications, "require_principal", fake_require_principal)

        with pytest.raises(AuthorizationError):
            await notifications.stream_notifications(
                cast("object", object()), authorization="Bearer token"
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stream_accepts_guardian_and_returns_an_event_stream(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sessions: list[_FakeSession] = []

        def fake_get_session() -> _FakeSession:
            session = _FakeSession()
            sessions.append(session)
            return session

        async def fake_require_principal(
            *_args: object, **_kwargs: object
        ) -> Principal:
            return _principal("guardian")

        monkeypatch.setattr(notifications, "get_session", fake_get_session)
        monkeypatch.setattr(notifications, "require_principal", fake_require_principal)

        response = await notifications.stream_notifications(
            cast("object", _FakeRequest()), authorization="Bearer token"
        )

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["X-Accel-Buffering"] == "no"
        # The auth-check session is short-lived: closed before the streaming
        # response is even constructed, never held open for the connection.
        assert len(sessions) == 1
        assert sessions[0].closed == 1
