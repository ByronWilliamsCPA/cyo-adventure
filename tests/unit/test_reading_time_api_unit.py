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
    _MAX_UTC_OFFSET_SECONDS,
    _ONE_DAY_SECONDS,
    _clamp_seconds_delta,
    _elapsed_ceiling_seconds,
    _require_child_profile,
    _validate_activity_date,
    flush_reading_time,
)
from cyo_adventure.api.schemas import ReadingTimeFlushBody
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.db.models import ChildProfile, ReadingActivityDay

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
_TODAY = _NOW.date()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSession:
    """Minimal async session double: one row keyed by (model, key), like
    test_reading_api_unit.py's own fake.
    """

    def __init__(
        self,
        *,
        existing: ReadingActivityDay | None = None,
        profile: ChildProfile | None = None,
    ) -> None:
        self._existing = existing
        self._profile = profile
        self.added: list[object] = []
        self.flush_count = 0
        self.refresh_calls: list[object] = []

    async def get(self, model: type[object], _key: object) -> object | None:
        if model is ChildProfile:
            return self._profile
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

    def test_new_bucket_today_bounds_by_time_since_earliest_local_midnight(
        self,
    ) -> None:
        # body.date is a READER-LOCAL date, so the day's earliest possible
        # start is its UTC midnight offset by the largest positive UTC offset.
        ceiling = _elapsed_ceiling_seconds(_TODAY, _NOW, None)
        midnight = datetime.combine(_TODAY, datetime.min.time(), tzinfo=UTC)
        expected = _NOW - (midnight - timedelta(seconds=_MAX_UTC_OFFSET_SECONDS))
        assert ceiling == pytest.approx(expected.total_seconds())

    def test_first_flush_for_a_reader_ahead_of_utc_is_not_clamped_to_zero(
        self,
    ) -> None:
        # 22:00 UTC: a reader in UTC+9 is already on the NEXT local date, so
        # body.date's bare UTC midnight is two hours in the FUTURE. That used
        # to zero the ceiling and clamp a real 30-minute session down to the
        # 120s grace margin, while the client marked all 1800s as synced.
        now = datetime(2026, 1, 15, 22, 0, 0, tzinfo=UTC)
        reader_local_date = date(2026, 1, 16)
        applied = _clamp_seconds_delta(
            1800,
            activity_date=reader_local_date,
            now=now,
            last_updated_at=None,
        )
        assert applied == 1800

    def test_ceiling_is_still_bounded_for_a_future_local_date(self) -> None:
        # The widened reference must not become a blank cheque: a first flush
        # for the allowed one-day-future date is still bounded well below a
        # full day of claimed reading.
        ceiling = _elapsed_ceiling_seconds(_TODAY + timedelta(days=1), _NOW, None)
        assert 0.0 < ceiling < float(_ONE_DAY_SECONDS)

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
        assert result.settled_seconds == 45
        assert len(session.added) == 1

    async def test_clamped_flush_settles_only_what_it_applied(self) -> None:
        """The response must report the APPLIED seconds, not the requested
        ones: the client advances its synced baseline by settled_seconds, so
        over-reporting here is what silently deletes the clamped remainder.
        """
        profile_id = uuid.uuid4()
        existing = ReadingActivityDay(
            child_profile_id=profile_id,
            activity_date=_TODAY,
            active_seconds=100,
            last_flush_id="prior-flush",
        )
        existing.updated_at = _NOW - timedelta(seconds=10)
        session = _FakeSession(existing=existing)

        result = await flush_reading_time(
            _body(seconds_delta=3600, flush_id="new-flush"),
            _child_principal(profile_id),
            session,
        )
        assert result.settled_seconds < 3600
        assert result.settled_seconds == result.active_seconds - 100

    async def test_paused_profile_flush_is_discarded(self) -> None:
        """The guardian privacy toggle holds server-side, not just in the
        client accumulator: a flush against a paused profile writes nothing
        and reports a zero bucket so queued offline flushes drain quietly.
        """
        session = _FakeSession(
            existing=None, profile=ChildProfile(time_capture_paused=True)
        )
        result = await flush_reading_time(
            _body(seconds_delta=45), _child_principal(), session
        )
        assert result.active_seconds == 0
        # Settled in full so the client stops retrying: the seconds are
        # intentionally dropped by policy, not lost to a transient failure.
        assert result.settled_seconds == 45
        assert session.added == []
        assert session.flush_count == 0

    async def test_paused_profile_returns_existing_bucket_unchanged(self) -> None:
        profile_id = uuid.uuid4()
        existing = ReadingActivityDay(
            child_profile_id=profile_id,
            activity_date=_TODAY,
            active_seconds=300,
            last_flush_id="flush-0",
            updated_at=_NOW,
        )
        session = _FakeSession(
            existing=existing, profile=ChildProfile(time_capture_paused=True)
        )
        result = await flush_reading_time(
            _body(seconds_delta=45, flush_id="flush-2"),
            _child_principal(profile_id),
            session,
        )
        assert result.active_seconds == 300
        assert existing.last_flush_id == "flush-0"
        assert session.flush_count == 0

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
