"""Integration tests for ``POST /me/reading-time`` against a real Postgres.

Every other test of this endpoint uses a ``_FakeSession``
(``tests/unit/test_reading_time_api_unit.py``) or asserts only who may call it
(``test_authz_matrix.py``). That leaves the parts of the contract that are
*properties of the database*, not of the handler, entirely unexercised:

* ``accumulate_stmt``'s ``ON CONFLICT DO UPDATE`` is the sole reason two
  concurrent flushes for one (profile, date) cannot collide on the composite
  primary key or lose an increment. Its ``#CRITICAL: concurrency`` block points
  at ``TestAccumulateStmt``, which asserts the *compiled SQL text*: that pins
  the statement's shape, not its behaviour under a real race.
* ``last_flush_id`` idempotency is only meaningful if the slot survives a real
  UPDATE and is read back by the next request's own transaction.
* The clamp's ``last_updated_at`` reference comes from the stored row, so a
  rapid second flush is bounded by a timestamp the database wrote, not one the
  handler held in memory.
* The ``ck_reading_activity_day_active_seconds`` CHECK constraint exists only
  in the schema; no Python code path can demonstrate it.

These tests cover exactly that gap. The clamp arithmetic, date-window
rejection, and paused-profile branch selection stay in the unit suite where
they belong.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from cyo_adventure.db.models import ChildProfile, ReadingActivityDay
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration]

_URL = "/api/v1/me/reading-time"

# A day that has already fully elapsed, so a FIRST flush for it gets the
# generous whole-day ceiling (_elapsed_ceiling_seconds' `activity_date <
# now.date()` branch) and is never clamped. Using "today" instead would make
# every assertion below depend on what time the suite happens to run.
_YESTERDAY = (datetime.now(UTC) - timedelta(days=1)).date()

# Every SECOND flush to an existing bucket is bounded by wall time since that
# bucket's own last write plus the 120s grace margin, so a test that flushes
# twice in quick succession must keep the follow-up at or below the grace
# margin or the clamp (correctly) trims it. See
# test_a_rapid_second_flush_is_clamped_by_the_stored_updated_at, which asserts
# that behaviour deliberately rather than working around it.
_WITHIN_GRACE_SECONDS = 90


def _body(
    *, flush_id: str, seconds: int, activity_date: date = _YESTERDAY
) -> dict[str, object]:
    """Build a reading-time flush body.

    Args:
        flush_id: The client-minted idempotency key for this attempt.
        seconds: The client-reported active-reading delta.
        activity_date: The day the seconds belong to; defaults to a fully
            elapsed day so a first flush is never clamped.

    Returns:
        dict[str, object]: The JSON body for ``POST /me/reading-time``.
    """
    return {
        "date": activity_date.isoformat(),
        "seconds_delta": seconds,
        "flush_id": flush_id,
    }


async def _bucket(
    sessions: async_sessionmaker[AsyncSession], profile_id: uuid.UUID
) -> ReadingActivityDay | None:
    """Read one profile's bucket for ``_YESTERDAY`` straight from the database.

    Args:
        sessions: The test session factory.
        profile_id: The child profile whose bucket to read.

    Returns:
        ReadingActivityDay | None: The stored row, or None if none exists.
    """
    async with sessions() as session:
        return await session.get(ReadingActivityDay, (profile_id, _YESTERDAY))


async def _row_count(sessions: async_sessionmaker[AsyncSession]) -> int:
    """Count every reading-activity row in the database.

    Args:
        sessions: The test session factory.

    Returns:
        int: The total row count across all profiles and dates.
    """
    async with sessions() as session:
        return (
            await session.execute(select(func.count()).select_from(ReadingActivityDay))
        ).scalar_one()


@pytest.mark.asyncio
async def test_first_flush_persists_a_bucket_row(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A first flush creates exactly one row carrying the seconds and flush id.

    The unit suite can only assert what the handler returned; this asserts what
    the database actually holds afterwards, including ``last_flush_id``, which
    every later idempotency guarantee reads back from.
    """
    resp = await client.post(
        _URL, json=_body(flush_id="f1", seconds=1800), headers=auth(seed.child_token)
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["active_seconds"] == 1800
    assert resp.json()["settled_seconds"] == 1800

    row = await _bucket(sessions, seed.child_profile_id)
    assert row is not None
    assert row.active_seconds == 1800
    assert row.last_flush_id == "f1"
    assert await _row_count(sessions) == 1


@pytest.mark.asyncio
async def test_sequential_flushes_accumulate_into_one_row(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Two distinct flushes for one day sum into a single bucket.

    This is the ON CONFLICT DO UPDATE path taken sequentially: the second
    request must UPDATE the first request's row (adding to the *stored* value)
    rather than insert a second one or overwrite the total.
    """
    first = await client.post(
        _URL, json=_body(flush_id="f1", seconds=1800), headers=auth(seed.child_token)
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        _URL,
        json=_body(flush_id="f2", seconds=_WITHIN_GRACE_SECONDS),
        headers=auth(seed.child_token),
    )

    assert second.status_code == 200, second.text
    assert second.json()["active_seconds"] == 1800 + _WITHIN_GRACE_SECONDS
    assert second.json()["settled_seconds"] == _WITHIN_GRACE_SECONDS

    row = await _bucket(sessions, seed.child_profile_id)
    assert row is not None
    assert row.active_seconds == 1800 + _WITHIN_GRACE_SECONDS
    assert row.last_flush_id == "f2"
    assert await _row_count(sessions) == 1


@pytest.mark.asyncio
async def test_concurrent_first_flushes_both_land_and_sum(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Two overlapping first flushes for one day: no 500, no lost increment.

    This is the race ``accumulate_stmt``'s ``#CRITICAL: concurrency`` block
    exists to prevent, and the only test that can actually run it. Both
    requests read no row, so both attempt an INSERT against the same composite
    primary key: a read-modify-write would either raise a unique violation
    (one 500) or silently drop one increment. The upsert performs the addition
    inside the row lock Postgres already takes for the conflicting insert, so
    whichever ordering wins, the total is exact.

    Both deltas sit at or below the 120s grace margin so the assertion holds
    regardless of interleaving: if the requests happen not to overlap, the
    loser's clamp reference becomes the winner's ``updated_at`` and its ceiling
    collapses to the grace margin alone.
    """
    left, right = await asyncio.gather(
        client.post(
            _URL,
            json=_body(flush_id="race-a", seconds=90),
            headers=auth(seed.child_token),
        ),
        client.post(
            _URL,
            json=_body(flush_id="race-b", seconds=45),
            headers=auth(seed.child_token),
        ),
    )

    assert left.status_code == 200, left.text
    assert right.status_code == 200, right.text

    row = await _bucket(sessions, seed.child_profile_id)
    assert row is not None
    assert row.active_seconds == 135
    assert await _row_count(sessions) == 1


@pytest.mark.asyncio
async def test_replayed_flush_id_is_a_noop_across_a_real_update(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Replaying the last-applied flush after a real UPDATE adds nothing.

    The unit suite proves the handler's early-return branch against a fake
    session that was handed the row. This proves the slot genuinely persists
    through an ON CONFLICT DO UPDATE and is read back by a later request's own
    transaction, which is the only reason an offline queue can retry safely.
    """
    await client.post(
        _URL, json=_body(flush_id="f1", seconds=1800), headers=auth(seed.child_token)
    )
    await client.post(
        _URL,
        json=_body(flush_id="f2", seconds=_WITHIN_GRACE_SECONDS),
        headers=auth(seed.child_token),
    )
    total = 1800 + _WITHIN_GRACE_SECONDS

    replay = await client.post(
        _URL,
        json=_body(flush_id="f2", seconds=_WITHIN_GRACE_SECONDS),
        headers=auth(seed.child_token),
    )

    assert replay.status_code == 200, replay.text
    assert replay.json()["active_seconds"] == total
    # The client must still advance its baseline past a deduped replay, or it
    # retries the same flush forever.
    assert replay.json()["settled_seconds"] == _WITHIN_GRACE_SECONDS

    row = await _bucket(sessions, seed.child_profile_id)
    assert row is not None
    assert row.active_seconds == total


@pytest.mark.asyncio
async def test_concurrent_replay_of_one_flush_id_applies_exactly_once(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A retry racing its own original banks the seconds once, not twice.

    When both requests read no row, the handler's read-then-check dedup is
    useless and the atomic ``WHERE last_flush_id IS DISTINCT FROM`` guard
    inside the upsert is what saves the count: the loser's DO UPDATE matches
    nothing, RETURNING yields no row, and the handler falls back to reading the
    bucket as it now stands. That fallback branch is unreachable from the unit
    suite, which cannot produce a genuine write-write race.
    """
    body = _body(flush_id="retry-me", seconds=90)
    first, second = await asyncio.gather(
        client.post(_URL, json=body, headers=auth(seed.child_token)),
        client.post(_URL, json=body, headers=auth(seed.child_token)),
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["active_seconds"] == 90
    assert second.json()["active_seconds"] == 90

    row = await _bucket(sessions, seed.child_profile_id)
    assert row is not None
    assert row.active_seconds == 90


@pytest.mark.asyncio
async def test_a_rapid_second_flush_is_clamped_by_the_stored_updated_at(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The clamp's reference instant comes from the database, not the request.

    A bucket written moments ago cannot plausibly have accrued another hour, so
    the follow-up is trimmed to roughly the grace margin. Worth an integration
    test rather than a unit one because the reference is the row's own
    ``updated_at``, set by ``func.now()`` on the server: a handler that passed
    its in-memory copy, or a schema that stopped refreshing the column on
    UPDATE, would silently widen this ceiling.
    """
    await client.post(
        _URL, json=_body(flush_id="f1", seconds=1800), headers=auth(seed.child_token)
    )

    second = await client.post(
        _URL, json=_body(flush_id="f2", seconds=3600), headers=auth(seed.child_token)
    )

    assert second.status_code == 200, second.text
    settled = second.json()["settled_seconds"]
    assert settled < 3600, "an hour cannot have elapsed since the previous flush"
    # The exact figure is the 120s grace margin plus however long the two
    # requests took, which is milliseconds in-process. The slack below is for a
    # slow runner, not for the assertion's meaning: anything under 180 proves
    # the ceiling came from the stored timestamp rather than the request.
    assert settled <= 180, settled

    row = await _bucket(sessions, seed.child_profile_id)
    assert row is not None
    assert row.active_seconds == 1800 + settled
    # The unsettled remainder is the client's to retry later, not the server's
    # to silently bank.
    assert row.active_seconds < 1800 + 3600


@pytest.mark.asyncio
async def test_two_children_writing_the_same_day_get_separate_buckets(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """One child's flush can never land in another child's bucket.

    The body carries no profile id at all: the target is derived solely from
    the child principal, so isolation here is structural. This pins it at the
    storage layer, where the composite primary key is what keeps two children
    flushing the same calendar day apart.
    """
    await client.post(
        _URL, json=_body(flush_id="a1", seconds=600), headers=auth(seed.child_token)
    )
    await client.post(
        _URL,
        json=_body(flush_id="b1", seconds=1200),
        headers=auth(seed.other_child_token),
    )

    mine = await _bucket(sessions, seed.child_profile_id)
    theirs = await _bucket(sessions, seed.other_child_profile_id)
    assert mine is not None
    assert theirs is not None
    assert mine.active_seconds == 600
    assert theirs.active_seconds == 1200
    assert await _row_count(sessions) == 2


@pytest.mark.asyncio
async def test_paused_profile_flush_writes_no_row_at_all(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A guardian's pause toggle leaves no behavioural trace in the database.

    The unit suite asserts the discard *response*. The privacy claim the toggle
    actually makes ("families who want none of it recorded") is about storage,
    so it needs a test that looks at storage: no row, not a zeroed row.
    """
    async with sessions() as session:
        profile = await session.get(ChildProfile, seed.child_profile_id)
        assert profile is not None
        profile.time_capture_paused = True
        await session.commit()

    resp = await client.post(
        _URL, json=_body(flush_id="f1", seconds=1800), headers=auth(seed.child_token)
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["active_seconds"] == 0
    # Settled in full: the seconds are dropped by policy, so the client must
    # advance past them rather than retrying against a toggle that keeps
    # discarding them.
    assert resp.json()["settled_seconds"] == 1800
    assert await _row_count(sessions) == 0


@pytest.mark.asyncio
async def test_check_constraint_rejects_a_negative_total(
    seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """``ck_reading_activity_day_active_seconds`` is present in the schema.

    No HTTP path can reach this: ``seconds_delta`` is Pydantic-bound to
    ``ge=0``, so the constraint is a floor under future writers (a retention
    rollup, a correction script, a migration) rather than under this endpoint.
    A constraint nothing ever tests is a constraint that can quietly go missing
    from a migration, so this asserts it directly.
    """
    async with sessions() as session:
        session.add(
            ReadingActivityDay(
                child_profile_id=seed.child_profile_id,
                activity_date=_YESTERDAY,
                active_seconds=-1,
            )
        )
        constraint = "ck_reading_activity_day_active_seconds"
        with pytest.raises(IntegrityError, match=constraint):
            await session.commit()
        # Leave the session clean for the context manager's exit: a failed
        # commit leaves the transaction in an aborted state, and this module
        # runs under `filterwarnings = ["error"]`.
        await session.rollback()
