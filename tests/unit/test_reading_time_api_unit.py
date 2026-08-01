"""Unit tests for the reading-time flush endpoint (W3.3, no DB, no ASGI).

Covers the pure clamp/idempotency helpers directly, plus the route handler
end to end against a fake session, following the ``_FakeSession`` convention
established in ``test_reading_api_unit.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.api.reading_time import (
    _MAX_SINGLE_FLUSH_SECONDS,
    _clamp_seconds_delta,
    _elapsed_ceiling_seconds,
    _require_child_profile,
    _validate_activity_date,
    flush_reading_time,
)
from cyo_adventure.api.schemas import ReadingTimeFlushBody
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.db.models import ReadingActivityDay

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
_TODAY = _NOW.date()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSession:
    """Minimal async session double: one row keyed by (model, key), like
    test_reading_api_unit.py's own fake.
    """

    def __init__(self, *, existing: ReadingActivityDay | None = None) -> None:
        self._existing = existing
        self.added: list[object] = []
        self.flush_count = 0
        self.refresh_calls: list[object] = []

    async def get(self, _model: type[object], _key: object) -> object | None:
        return self._existing

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, obj: object, _attrs: list[str] | None = None) -> None:
        self.refresh_calls.append(obj)
        if isinstance(obj, ReadingActivityDay) and obj.updated_at is None:
            obj.updated_at = _NOW


def _child_principal(profile_id: uuid.UUID | None = None) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="child",
        family_id=uuid.uuid4(),
        profile_ids=frozenset({profile_id or uuid.uuid4()}),
    )


def _guardian_principal() -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _body(
    *,
    activity_date: date = _TODAY,
    seconds_delta: int = 60,
    flush_id: str = "flush-1",
) -> ReadingTimeFlushBody:
    return ReadingTimeFlushBody(
        date=activity_date, seconds_delta=seconds_delta, flush_id=flush_id
    )


# ---------------------------------------------------------------------------
# _require_child_profile
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_require_child_profile_returns_singleton_for_child() -> None:
    profile_id = uuid.uuid4()
    principal = _child_principal(profile_id)
    assert _require_child_profile(principal) == profile_id


@pytest.mark.unit
def test_require_child_profile_rejects_guardian() -> None:
    with pytest.raises(AuthorizationError):
        _require_child_profile(_guardian_principal())


# ---------------------------------------------------------------------------
# _validate_activity_date
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateActivityDate:
    def test_today_is_valid(self) -> None:
        _validate_activity_date(_TODAY, _NOW)  # does not raise

    def test_past_date_is_valid(self) -> None:
        _validate_activity_date(_TODAY - timedelta(days=30), _NOW)  # does not raise

    def test_one_day_future_is_valid(self) -> None:
        _validate_activity_date(_TODAY + timedelta(days=1), _NOW)  # does not raise

    def test_far_future_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _validate_activity_date(_TODAY + timedelta(days=2), _NOW)


# ---------------------------------------------------------------------------
# _elapsed_ceiling_seconds / _clamp_seconds_delta
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClamp:
    def test_existing_bucket_bounds_by_time_since_last_write(self) -> None:
        last_updated = _NOW - timedelta(seconds=30)
        ceiling = _elapsed_ceiling_seconds(_TODAY, _NOW, last_updated)
        assert ceiling == pytest.approx(30.0)

    def test_new_bucket_today_bounds_by_time_since_midnight(self) -> None:
        ceiling = _elapsed_ceiling_seconds(_TODAY, _NOW, None)
        expected = _NOW - datetime.combine(_TODAY, datetime.min.time(), tzinfo=UTC)
        assert ceiling == pytest.approx(expected.total_seconds())

    def test_new_bucket_past_day_bounds_by_a_full_day(self) -> None:
        ceiling = _elapsed_ceiling_seconds(_TODAY - timedelta(days=5), _NOW, None)
        assert ceiling == 86_400.0

    def test_clamp_passes_through_a_small_honest_delta(self) -> None:
        applied = _clamp_seconds_delta(
            60,
            activity_date=_TODAY,
            now=_NOW,
            last_updated_at=_NOW - timedelta(seconds=90),
        )
        assert applied == 60

    def test_clamp_bounds_an_implausibly_large_delta_to_elapsed_time(self) -> None:
        # Only 10 seconds elapsed since the last write; requesting an hour is
        # implausible and must be clamped near the elapsed-plus-grace ceiling.
        applied = _clamp_seconds_delta(
            3600,
            activity_date=_TODAY,
            now=_NOW,
            last_updated_at=_NOW - timedelta(seconds=10),
        )
        assert applied < 3600
        assert applied <= 10 + 120  # elapsed + grace margin

    def test_clamp_never_exceeds_the_absolute_per_flush_cap(self) -> None:
        # A brand-new bucket for a long-past day has an 86400s elapsed
        # ceiling, but the absolute per-flush cap (6h) still governs.
        applied = _clamp_seconds_delta(
            999_999,
            activity_date=_TODAY - timedelta(days=10),
            now=_NOW,
            last_updated_at=None,
        )
        assert applied == _MAX_SINGLE_FLUSH_SECONDS


# ---------------------------------------------------------------------------
# flush_reading_time (route handler)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestFlushReadingTime:
    async def test_guardian_and_admin_rejected(self) -> None:
        session = _FakeSession()
        with pytest.raises(AuthorizationError):
            await flush_reading_time(_body(), _guardian_principal(), session)

    async def test_creates_a_new_bucket(self) -> None:
        session = _FakeSession(existing=None)
        result = await flush_reading_time(
            _body(seconds_delta=45), _child_principal(), session
        )
        assert result.active_seconds == 45
        assert len(session.added) == 1

    async def test_accumulates_into_an_existing_bucket(self) -> None:
        profile_id = uuid.uuid4()
        existing = ReadingActivityDay(
            child_profile_id=profile_id,
            activity_date=_TODAY,
            active_seconds=100,
            last_flush_id="prior-flush",
        )
        existing.updated_at = _NOW - timedelta(seconds=200)
        session = _FakeSession(existing=existing)

        result = await flush_reading_time(
            _body(seconds_delta=30, flush_id="new-flush"),
            _child_principal(profile_id),
            session,
        )
        assert result.active_seconds == 130
        assert existing.last_flush_id == "new-flush"

    async def test_replayed_flush_id_is_a_noop(self) -> None:
        profile_id = uuid.uuid4()
        existing = ReadingActivityDay(
            child_profile_id=profile_id,
            activity_date=_TODAY,
            active_seconds=100,
            last_flush_id="already-applied",
        )
        existing.updated_at = _NOW
        session = _FakeSession(existing=existing)

        result = await flush_reading_time(
            _body(seconds_delta=999, flush_id="already-applied"),
            _child_principal(profile_id),
            session,
        )
        assert result.active_seconds == 100  # unchanged: no-op replay
        assert session.flush_count == 0
        assert session.added == []
