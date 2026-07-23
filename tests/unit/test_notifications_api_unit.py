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

from cyo_adventure.api import notifications
from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.notifications.models import NotificationItem


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
