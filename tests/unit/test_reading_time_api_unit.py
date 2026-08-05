"""Unit tests for the reading-time flush endpoint (W3.3, no DB, no ASGI).

Covers the pure clamp/idempotency helpers directly, plus the route handler
end to end against a fake session, following the ``_FakeSession`` convention
established in ``test_reading_api_unit.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.dialects import postgresql

from cyo_adventure.api.deps import Principal
from cyo_adventure.api.reading_time import (
    _MAX_PAST_DAYS,
    _MAX_SINGLE_FLUSH_SECONDS,
    _MAX_UTC_OFFSET_SECONDS,
    _ONE_DAY_SECONDS,
    _clamp_seconds_delta,
    _elapsed_ceiling_seconds,
    _require_child_profile,
    _validate_activity_date,
    accumulate_stmt,
    flush_reading_time,
)
from cyo_adventure.api.reading_time import router as reading_time_router
from cyo_adventure.api.schemas import ReadingTimeFlushBody
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.db.models import ChildProfile, ReadingActivityDay

if TYPE_CHECKING:
    from sqlalchemy.sql.expression import Executable

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
_TODAY = _NOW.date()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeResult:
    """The narrow slice of ``Result`` this handler uses."""

    def __init__(self, row: tuple[int, datetime] | None) -> None:
        self._row = row

    def one_or_none(self) -> tuple[int, datetime] | None:
        return self._row

    def one(self) -> tuple[int, datetime]:
        if self._row is None:
            msg = "no row"
            raise AssertionError(msg)
        return self._row


class _FakeSession:
    """Minimal async session double: one row keyed by (model, key), like
    test_reading_api_unit.py's own fake.

    ``execute`` stands in for the ON CONFLICT DO UPDATE accumulate. It records
    every statement so a test can assert WHICH statement was emitted, and
    simulates the increment arithmetic so the handler's own control flow stays
    exercised. It deliberately does NOT model the concurrency semantics: what
    makes the upsert atomic is asserted against the compiled SQL in
    ``TestAccumulateStmt``, and end to end against a real database is I24's
    integration-test gap, not something a fake can speak to.
    """

    def __init__(
        self,
        *,
        existing: ReadingActivityDay | None = None,
        profile: ChildProfile | None = None,
        applied_override: int | None = None,
    ) -> None:
        self._existing = existing
        self._profile = profile
        self._applied_override = applied_override
        self.added: list[object] = []
        self.flush_count = 0
        self.refresh_calls: list[object] = []
        self.statements: list[Executable] = []

    async def get(self, model: type[object], _key: object) -> object | None:
        if model is ChildProfile:
            return self._profile
        return self._existing

    async def execute(self, statement: Executable) -> _FakeResult:
        self.statements.append(statement)
        # Recover the delta the handler chose from the statement's own bound
        # values, so the fake never invents a number of its own.
        applied = self._applied_override
        if applied is None:
            applied = int(statement.compile().params["active_seconds"])
        base = self._existing.active_seconds if self._existing is not None else 0
        return _FakeResult((base + applied, _NOW))

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


def _unpaused() -> ChildProfile:
    """A profile whose guardian has NOT paused time capture.

    Passed explicitly everywhere rather than defaulted, because a missing
    profile row is now itself meaningful (it fails closed, like a paused one).
    """
    return ChildProfile(time_capture_paused=False)


def _bucket(
    profile_id: uuid.UUID,
    *,
    active_seconds: int,
    last_flush_id: str,
    written_seconds_ago: int = 0,
) -> ReadingActivityDay:
    """An existing day bucket, dated against the REAL clock.

    ``flush_reading_time`` calls ``datetime.now(UTC)`` itself with no
    injection point, so anything the handler compares against a date (the
    past/future window, the elapsed-time clamp) has to be expressed relative
    to the real now, not the frozen ``_NOW`` the pure helpers above use.
    """
    now = datetime.now(UTC)
    row = ReadingActivityDay(
        child_profile_id=profile_id,
        activity_date=now.date(),
        active_seconds=active_seconds,
        last_flush_id=last_flush_id,
    )
    row.updated_at = now - timedelta(seconds=written_seconds_ago)
    return row


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
    activity_date: date | None = None,
    seconds_delta: int = 60,
    flush_id: str = "flush-1",
) -> ReadingTimeFlushBody:
    """A flush body defaulting to the REAL today; see ``_bucket``."""
    return ReadingTimeFlushBody(
        date=activity_date or datetime.now(UTC).date(),
        seconds_delta=seconds_delta,
        flush_id=flush_id,
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
    principal = _guardian_principal()
    with pytest.raises(AuthorizationError):
        _require_child_profile(principal)


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
        too_far_ahead = _TODAY + timedelta(days=2)
        with pytest.raises(ValidationError):
            _validate_activity_date(too_far_ahead, _NOW)

    def test_recent_past_within_the_window_is_valid(self) -> None:
        # A device offline for a long stretch drains real accrued buckets, so
        # the past window has to stay generous.
        _validate_activity_date(_TODAY - timedelta(days=_MAX_PAST_DAYS), _NOW)

    def test_far_past_is_rejected(self) -> None:
        # Unbounded on the past side, a tampered client can mint an arbitrary
        # number of historical rows, each with a fresh flush_id and a full-day
        # elapsed ceiling.
        too_far_back = _TODAY - timedelta(days=_MAX_PAST_DAYS + 1)
        with pytest.raises(ValidationError):
            _validate_activity_date(too_far_back, _NOW)


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
# accumulate_stmt
# ---------------------------------------------------------------------------


def _compiled_accumulate(flush_id: str = "flush-1", applied: int = 45) -> str:
    stmt = accumulate_stmt(
        profile_id=uuid.uuid4(),
        activity_date=_TODAY,
        applied=applied,
        flush_id=flush_id,
    )
    return str(stmt.compile(dialect=postgresql.dialect()))


@pytest.mark.unit
class TestAccumulateStmt:
    """The accumulate must be ONE statement, not a read-modify-write.

    These assert against the compiled SQL rather than against a fake, because
    the property at stake is a concurrency property of the statement itself:
    a fake session cannot distinguish an atomic increment from a lost one.
    """

    def test_is_an_upsert_rather_than_a_plain_insert(self) -> None:
        sql = _compiled_accumulate()
        assert "ON CONFLICT" in sql
        assert "DO UPDATE" in sql

    def test_conflict_target_is_the_composite_primary_key(self) -> None:
        sql = _compiled_accumulate()
        assert "child_profile_id" in sql
        assert "activity_date" in sql

    def test_increment_reads_the_stored_column_not_a_client_value(self) -> None:
        # ``reading_activity_day.active_seconds + :param`` is what makes two
        # concurrent flushes sum instead of one overwriting the other.
        sql = _compiled_accumulate()
        assert "reading_activity_day.active_seconds +" in sql

    def test_do_update_carries_the_idempotency_guard(self) -> None:
        # The replay check has to live INSIDE the write, not only in the
        # read above it, or a retry racing its own original applies twice.
        sql = _compiled_accumulate()
        assert "WHERE" in sql.split("DO UPDATE")[1]
        assert "IS DISTINCT FROM" in sql

    def test_returns_the_post_write_state(self) -> None:
        sql = _compiled_accumulate()
        assert "RETURNING" in sql


# ---------------------------------------------------------------------------
# flush_reading_time (route handler)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestFlushReadingTime:
    async def test_guardian_and_admin_rejected(self) -> None:
        session = _FakeSession(profile=_unpaused())
        body = _body()
        principal = _guardian_principal()
        with pytest.raises(AuthorizationError):
            await flush_reading_time(body, principal, session)

    async def test_creates_a_new_bucket(self) -> None:
        session = _FakeSession(existing=None, profile=_unpaused())
        result = await flush_reading_time(
            _body(seconds_delta=45), _child_principal(), session
        )
        assert result.active_seconds == 45
        assert result.settled_seconds == 45
        # One statement, not a SELECT-then-INSERT: see TestAccumulateStmt.
        assert len(session.statements) == 1
        assert session.added == []

    async def test_clamped_flush_settles_only_what_it_applied(self) -> None:
        """The response must report the APPLIED seconds, not the requested
        ones: the client advances its synced baseline by settled_seconds, so
        over-reporting here is what silently deletes the clamped remainder.
        """
        profile_id = uuid.uuid4()
        existing = _bucket(
            profile_id,
            active_seconds=100,
            last_flush_id="prior-flush",
            written_seconds_ago=10,
        )
        session = _FakeSession(existing=existing, profile=_unpaused())

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
        assert session.statements == []
        assert session.added == []
        assert session.flush_count == 0

    async def test_missing_profile_row_is_treated_as_paused(self) -> None:
        """A privacy toggle that cannot be read must fail CLOSED.

        The prior ``profile is not None and profile.time_capture_paused``
        recorded behavioural data for a profile whose settings were
        unavailable, which is the wrong direction for a privacy control.
        """
        session = _FakeSession(existing=None, profile=None)
        result = await flush_reading_time(
            _body(seconds_delta=45), _child_principal(), session
        )
        assert result.active_seconds == 0
        assert session.statements == []

    async def test_paused_profile_returns_existing_bucket_unchanged(self) -> None:
        profile_id = uuid.uuid4()
        existing = _bucket(profile_id, active_seconds=300, last_flush_id="flush-0")
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
        assert session.statements == []
        assert session.flush_count == 0

    async def test_accumulates_into_an_existing_bucket(self) -> None:
        profile_id = uuid.uuid4()
        existing = _bucket(
            profile_id,
            active_seconds=100,
            last_flush_id="prior-flush",
            written_seconds_ago=200,
        )
        session = _FakeSession(existing=existing, profile=_unpaused())

        result = await flush_reading_time(
            _body(seconds_delta=30, flush_id="new-flush"),
            _child_principal(profile_id),
            session,
        )
        assert result.active_seconds == 130
        # The new id rides on the statement rather than on a mutated ORM
        # object, because the write is now a single upsert.
        params = session.statements[0].compile().params
        assert params["last_flush_id"] == "new-flush"

    async def test_replayed_flush_id_is_a_noop(self) -> None:
        profile_id = uuid.uuid4()
        existing = _bucket(
            profile_id, active_seconds=100, last_flush_id="already-applied"
        )
        session = _FakeSession(existing=existing, profile=_unpaused())

        result = await flush_reading_time(
            _body(seconds_delta=999, flush_id="already-applied"),
            _child_principal(profile_id),
            session,
        )
        assert result.active_seconds == 100  # unchanged: no-op replay
        assert session.statements == []
        assert session.flush_count == 0
        assert session.added == []

    async def test_aba_cross_device_replay_is_a_known_residual(self) -> None:
        """Pin the A-B-A window the single-slot guard cannot close.

        Device 1 loses the ack for flush A, device 2 lands flush B, then
        device 1 retries A. The slot holds B, so A no longer looks like a
        replay and its seconds are banked a second time. This asserts the
        CURRENT behaviour deliberately: closing it needs a per-device slot or
        a bounded set of recent ids, i.e. a schema change. If a future change
        makes this a no-op, that is an improvement and this test should be
        updated to demand it, not deleted.
        """
        profile_id = uuid.uuid4()
        # last_flush_id is B; device 1 now retries A.
        existing = _bucket(
            profile_id,
            active_seconds=100,
            last_flush_id="flush-B",
            written_seconds_ago=600,
        )
        session = _FakeSession(existing=existing, profile=_unpaused())

        result = await flush_reading_time(
            _body(seconds_delta=60, flush_id="flush-A"),
            _child_principal(profile_id),
            session,
        )
        assert result.active_seconds == 160  # A applied a second time
        assert len(session.statements) == 1
        # Damage stays bounded by the per-flush clamp, which is what makes
        # this residual acceptable for a literacy signal.
        assert result.settled_seconds <= _MAX_SINGLE_FLUSH_SECONDS


@pytest.mark.unit
def test_router_declares_the_403_it_can_raise() -> None:
    """See api/progress.py's twin test: _require_child_profile raises 403."""
    assert set(reading_time_router.responses) >= {401, 403}
