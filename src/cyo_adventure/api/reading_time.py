"""Active-reading-time flush endpoint (W3.3, gamification recommendation 2.4).

``POST /me/reading-time`` accumulates a client-measured, idle-gated,
visibility-gated active-reading delta into a per-(profile, day) bucket
(``reading_activity_day``). Two integrity guards, both named in the
recommendation's section 2.4 and the kid-appeal-implementation-plan.md W3.3
task:

* **Idempotency**: a client-minted ``flush_id`` dedupes an offline-queue
  replay, mirroring ``ReadingState.last_event_id``.
* **Sanity clamp**: client clocks are reader-reported and unverified
  (#ASSUME below), so a delta is clamped to what could plausibly have
  elapsed, never trusted verbatim. This is a literacy signal, not a billing
  ledger: an over-large delta is clamped and logged, never rejected outright
  (rejecting would just make the client retry with the same bad number).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter

from cyo_adventure.api.deps import CurrentPrincipal, DbSession, Role
from cyo_adventure.api.schemas import (
    ReadingActivityDayView,
    ReadingTimeFlushBody,
    error_responses,
)
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.db.models import ChildProfile, ReadingActivityDay
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import uuid

    from cyo_adventure.api.deps import Principal

_logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1", tags=["reading-time"], responses=error_responses(401)
)

# A single flush can never plausibly represent more than this much active
# reading (the recommendation's own "e.g. 6 hours" sanity example); a delta
# above this is clamped down to it regardless of how much wall-clock time has
# elapsed.
_MAX_SINGLE_FLUSH_SECONDS = 6 * 60 * 60

# Grace margin added to the elapsed-wall-time ceiling, absorbing client clock
# skew and normal request/queue latency so an honest flush sent moments after
# its window closes is not clamped for a few seconds of jitter.
_CLAMP_GRACE_SECONDS = 120

# How many days into the future a client-reported activity_date may sit
# before it is rejected outright (not merely clamped): a generous allowance
# for a device whose local clock/timezone reads ahead of the server's UTC
# "today", while still catching a clearly bogus far-future date.
_MAX_FUTURE_DAYS = 1

_ONE_DAY_SECONDS = 24 * 60 * 60


def _require_child_profile(principal: Principal) -> uuid.UUID:
    """Return the caller's own profile id, rejecting a non-child principal.

    Args:
        principal: The authenticated principal.

    Returns:
        uuid.UUID: The child's own profile id.

    Raises:
        AuthorizationError: If the principal is not a child.
    """
    # #CRITICAL: security: mirrors api/progress.py::_require_child_profile;
    # a CHILD Principal is structurally scoped to exactly one profile, so
    # this can never write another profile's reading-time bucket.
    # #VERIFY: tests/unit/test_reading_time_api_unit.py::
    # test_guardian_and_admin_rejected.
    if principal.role != Role.CHILD:
        msg = "this endpoint is child-scoped"
        raise AuthorizationError(msg)
    return next(iter(principal.profile_ids))


def _validate_activity_date(activity_date: date, now: datetime) -> None:
    """Reject an activity date implausibly far in the future.

    Args:
        activity_date: The client-reported day this flush's seconds belong
            to.
        now: The server's current UTC time.

    Raises:
        ValidationError: If ``activity_date`` is more than
            ``_MAX_FUTURE_DAYS`` ahead of the server's current UTC date.
    """
    if activity_date > now.date() + timedelta(days=_MAX_FUTURE_DAYS):
        msg = "activity date is too far in the future"
        raise ValidationError(msg, field="date", value=activity_date.isoformat())


def _elapsed_ceiling_seconds(
    activity_date: date, now: datetime, last_updated_at: datetime | None
) -> float:
    """Return the most active-seconds that could plausibly have elapsed.

    # #ASSUME: timing-dependencies: client clocks are reader-reported and
    # unverified (recommendation section 2.4); this clamp is a plausibility
    # bound derived from the SERVER's own clock, never the client's claimed
    # timestamp, so a forged or skewed client clock cannot widen it.
    # #VERIFY: tests/unit/test_reading_time_api_unit.py::TestClamp.

    Args:
        activity_date: The day this flush's seconds belong to.
        now: The server's current UTC time.
        last_updated_at: This (profile, date) bucket's own last write time,
            or ``None`` if the bucket does not exist yet.

    Returns:
        float: The elapsed-seconds ceiling, before the grace margin and the
        absolute per-flush cap are applied.
    """
    if last_updated_at is not None:
        # A bucket already exists: bound by wall time since ITS last write,
        # the same reference ReadingState.last_synced_at style reasoning
        # uses, so a rapid double-flush cannot each claim a full day.
        reference = last_updated_at
    elif activity_date < now.date():
        # First flush ever for a past day: the whole day has already fully
        # elapsed, so it is the natural (generous) ceiling.
        return float(_ONE_DAY_SECONDS)
    else:
        # First flush ever for today (or the allowed one-day-future slack):
        # bound by wall time since that day's UTC midnight.
        reference = datetime.combine(activity_date, time.min, tzinfo=UTC)
    return max(0.0, (now - reference).total_seconds())


def _clamp_seconds_delta(
    requested: int,
    *,
    activity_date: date,
    now: datetime,
    last_updated_at: datetime | None,
) -> int:
    """Bound a requested delta to what could plausibly have elapsed.

    Args:
        requested: The client-reported seconds_delta (already Pydantic-bound
            to ``[0, 86400]``; see ``ReadingTimeFlushBody``).
        activity_date: The day this flush's seconds belong to.
        now: The server's current UTC time.
        last_updated_at: This bucket's own last write time, or ``None``.

    Returns:
        int: The delta actually applied: the smallest of the request, the
        elapsed-time-plus-grace ceiling, and the absolute per-flush cap.
    """
    ceiling = _elapsed_ceiling_seconds(activity_date, now, last_updated_at)
    return int(
        min(requested, ceiling + _CLAMP_GRACE_SECONDS, _MAX_SINGLE_FLUSH_SECONDS)
    )


def _to_view(row: ReadingActivityDay) -> ReadingActivityDayView:
    """Build the wire view of a reading-activity-day row."""
    return ReadingActivityDayView(
        activity_date=row.activity_date,
        active_seconds=row.active_seconds,
        updated_at=row.updated_at,
    )


@router.post("/me/reading-time")
async def flush_reading_time(
    body: ReadingTimeFlushBody, principal: CurrentPrincipal, session: DbSession
) -> ReadingActivityDayView:
    """Idempotently add a clamped active-reading-time delta to a day bucket.

    Args:
        body: The flush payload.
        principal: The authenticated principal (must be a child token).
        session: The request session.

    Returns:
        ReadingActivityDayView: The bucket's state after this flush (or its
        unchanged current state, on a deduped replay).

    Raises:
        AuthorizationError: If the caller is not a child.
        ValidationError: If ``date`` is implausibly far in the future.
    """
    profile_id = _require_child_profile(principal)
    now = datetime.now(UTC)
    _validate_activity_date(body.date, now)

    # #CRITICAL: security: time_capture_paused is a guardian privacy toggle
    # ("families who want none of it recorded"), so it must hold server-side,
    # not only in the client accumulator: a stale or offline client that
    # missed the settings change still gets its flush discarded here. The
    # discard returns the bucket's current (or zero) state rather than an
    # error so queued offline flushes drain without retry loops.
    # #VERIFY: tests/unit/test_reading_time_api_unit.py::
    # test_paused_profile_flush_is_discarded.
    profile = await session.get(ChildProfile, profile_id)
    row = await session.get(ReadingActivityDay, (profile_id, body.date))
    if profile is not None and profile.time_capture_paused:
        _logger.info("reading_time_flush_discarded_paused", profile_id=str(profile_id))
        if row is not None:
            return _to_view(row)
        return ReadingActivityDayView(
            activity_date=body.date, active_seconds=0, updated_at=now
        )
    # #ASSUME: concurrency: single-slot idempotency, matching
    # db/models.py::ReadingActivityDay's own #ASSUME -- a replay of the LAST
    # applied flush_id is a no-op; a client that single-flights retries
    # before starting its next flush never double-counts.
    # #VERIFY: tests/unit/test_reading_time_api_unit.py::
    # test_replayed_flush_id_is_a_noop.
    if row is not None and row.last_flush_id == body.flush_id:
        return _to_view(row)

    applied = _clamp_seconds_delta(
        body.seconds_delta,
        activity_date=body.date,
        now=now,
        last_updated_at=row.updated_at if row is not None else None,
    )
    if applied < body.seconds_delta:
        _logger.warning(
            "reading_time_flush_clamped",
            profile_id=str(profile_id),
            requested_seconds=body.seconds_delta,
            applied_seconds=applied,
        )

    if row is None:
        row = ReadingActivityDay(
            child_profile_id=profile_id,
            activity_date=body.date,
            active_seconds=applied,
            last_flush_id=body.flush_id,
        )
        session.add(row)
    else:
        row.active_seconds += applied
        row.last_flush_id = body.flush_id
    await session.flush()
    await session.refresh(row, ["updated_at", "active_seconds"])
    return _to_view(row)
