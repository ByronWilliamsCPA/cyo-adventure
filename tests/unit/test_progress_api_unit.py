"""Unit tests for the GET /me/progress route handler (no DB, no ASGI).

Authorization plus the query-glue layer (``_build_progress_facts``); the
badge math itself is covered by ``tests/unit/test_progress_badges.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.api.progress import (
    _build_found_endings,
    _reading_day_totals,
    _require_child_profile,
    _resolve_ring_settings,
    _week_start,
    get_my_progress,
)
from cyo_adventure.api.progress import router as progress_router
from cyo_adventure.api.reading_history import _week_start as _history_week_start
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import (
    ChildProfile,
    Completion,
    ReadingActivityDay,
    Storybook,
    StorybookVersion,
)
from cyo_adventure.storybook.sentinels import wrap

_T1 = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeScalars:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows

    def __iter__(self) -> object:
        return iter(self._rows)


class _FakeSession:
    """Queue-based fake: session.scalars() drains an ordered list of results."""

    def __init__(self, queue: list[list[object]]) -> None:
        self._queue: list[list[object]] = [list(rows) for rows in queue]
        self.scalars_calls: list[object] = []

    async def scalars(self, stmt: object) -> _FakeScalars:
        self.scalars_calls.append(stmt)
        rows = self._queue.pop(0) if self._queue else []
        return _FakeScalars(rows)


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


def _admin_principal() -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="admin",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


@pytest.mark.unit
def test_require_child_profile_returns_singleton() -> None:
    profile_id = uuid.uuid4()
    assert _require_child_profile(_child_principal(profile_id)) == profile_id


@pytest.mark.unit
@pytest.mark.parametrize("build", [_guardian_principal, _admin_principal])
def test_require_child_profile_rejects_non_child(build: object) -> None:
    with pytest.raises(AuthorizationError):
        _require_child_profile(build())


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetMyProgress:
    async def test_guardian_rejected(self) -> None:
        session = _FakeSession([])
        with pytest.raises(AuthorizationError):
            await get_my_progress(_guardian_principal(), session)

    async def test_empty_profile_returns_empty_projection(self) -> None:
        # completions, ratings, story_requests all empty -> no book/version
        # queries fire (book_ids/version_keys stay empty); the trailing two
        # entries are the W3.4 ChildProfile and ReadingActivityDay queries,
        # both empty here (no profile row -> the inert fallback resolves).
        session = _FakeSession([[], [], [], [], []])
        result = await get_my_progress(_child_principal(), session)
        assert result.badges == []
        assert result.books == []
        assert result.totals.books_finished == 0
        assert result.totals.endings_found == 0
        assert result.days_read_this_week == 0
        assert result.lifetime_days_read == 0
        # A missing profile row is an age the server cannot establish, so it
        # resolves through the same conservative fallback as an unrecognized
        # band (the youngest band's row), not the mid-range "8-11" it used to
        # invent. See _UNKNOWN_BAND.
        assert result.settings.ring_enabled is False
        assert result.settings.ring_goal_days == 2
        # Decoration, so this one keeps its column default: an absent row says
        # nothing about whether badges should show, and showing them costs a
        # profile that no longer exists nothing.
        assert result.settings.badges_enabled is True
        # See test_missing_profile_row_resolves_time_capture_to_paused: the one
        # privacy toggle in this block does NOT follow its column default.
        assert result.settings.time_capture_paused is True

    async def test_missing_profile_row_resolves_time_capture_to_paused(self) -> None:
        """A profile whose row vanished must not be told to keep recording.

        This resolved value is what the client accumulator obeys, so returning
        "not paused" here started measurement and transmission on the child's
        device for a profile whose settings the server cannot read.
        ``api/reading_time.py::flush_reading_time`` already fails CLOSED on the
        identical condition and would discard whatever arrived, so the two
        endpoints disagreed and the recording was pure waste on the wrong side
        of a privacy boundary. The only way to reach this state is a
        delete/erasure racing the request, where "keep recording" is the worst
        available default.
        """
        session = _FakeSession([[], [], [], [], []])

        result = await get_my_progress(_child_principal(), session)

        assert result.settings.time_capture_paused is True

    async def test_first_completion_earns_first_ending_badge(self) -> None:
        profile_id = uuid.uuid4()
        completion = Completion(
            child_profile_id=profile_id,
            storybook_id="story-a",
            version=1,
            ending_id="e1",
        )
        completion.found_at = _T1
        book = Storybook(id="story-a", family_id=uuid.uuid4())
        book.current_published_version = 1
        version = StorybookVersion(
            storybook_id="story-a",
            version=1,
            blob={
                "title": "Story A",
                "metadata": {"ending_count": 2},
                "nodes": [
                    {
                        "id": "n1",
                        "is_ending": True,
                        "ending": {
                            "id": "e1",
                            "valence": "positive",
                            "kind": "success",
                            "title": "Yay",
                        },
                    }
                ],
            },
        )
        profile = ChildProfile(
            family_id=uuid.uuid4(),
            display_name="Kid",
            age_band="5-8",
            badges_enabled=True,
            time_capture_paused=False,
        )
        profile.id = profile_id
        activity = ReadingActivityDay(
            child_profile_id=profile_id,
            activity_date=date(2026, 1, 1),
            active_seconds=600,
        )

        # queue order: completions, ratings, story_requests, storybooks,
        # storybook_versions, (no series query: series_id is None),
        # child_profile, reading_activity_day.
        session = _FakeSession(
            [[completion], [], [], [book], [version], [profile], [activity]]
        )

        result = await get_my_progress(_child_principal(profile_id), session)

        badge_ids = {b.id for b in result.badges}
        assert "first_ending" in badge_ids
        assert result.books[0].storybook_id == "story-a"
        assert result.books[0].title == "Story A"
        assert result.books[0].total_endings == 2
        assert result.totals.books_finished == 1
        # 5-8 band default: ring on, goal 2 (P-A table).
        assert result.settings.ring_enabled is True
        assert result.settings.ring_goal_days == 2
        assert result.lifetime_days_read == 1
        assert len(result.books[0].found_endings) == 1
        assert result.books[0].found_endings[0].ending_id == "e1"
        assert result.books[0].found_endings[0].title == "Yay"
        assert result.books[0].found_endings[0].valence == "positive"


@pytest.mark.unit
class TestResolveRingSettings:
    """Pins the P-A band-default table (D17) and the max-6 goal clamp."""

    @pytest.mark.parametrize(
        ("age_band", "expected_enabled", "expected_goal"),
        [
            ("3-5", False, 2),
            ("5-8", True, 2),
            ("8-11", True, 3),
            ("10-13", True, 3),
            ("13-16", True, 4),
            ("16+", True, 4),
        ],
    )
    def test_band_default_when_both_columns_null(
        self, age_band: str, expected_enabled: bool, expected_goal: int
    ) -> None:
        enabled, goal = _resolve_ring_settings(age_band, None, None)
        assert enabled is expected_enabled
        assert goal == expected_goal

    def test_explicit_override_wins_over_band_default(self) -> None:
        # 3-5 defaults off; an explicit True overrides it (a guardian who
        # opts a pre-reader in).
        enabled, goal = _resolve_ring_settings(
            "3-5", ring_enabled=True, ring_goal_days=5
        )
        assert enabled is True
        assert goal == 5

    def test_explicit_false_overrides_an_on_by_default_band(self) -> None:
        enabled, _goal = _resolve_ring_settings(
            "8-11", ring_enabled=False, ring_goal_days=None
        )
        assert enabled is False

    def test_goal_above_six_is_clamped(self) -> None:
        # Backstop: the Pydantic Field bound and the DB CHECK should already
        # prevent this from ever reaching here, but the resolver clamps
        # anyway (see its #CRITICAL note).
        _enabled, goal = _resolve_ring_settings(
            "16+", ring_enabled=True, ring_goal_days=99
        )
        assert goal == 6

    def test_unknown_age_band_falls_back_to_the_youngest_bands_defaults(self) -> None:
        """An unrecognized band must resolve DOWN, not up.

        This replaces an assertion that the fallback was ``(True, 3)``. That
        was the 8-11 row, not a conservative default: the band table exists
        precisely because 3-5 is the one band D17 excludes, so falling back to
        "on" turns the streak ring on for readers whose age the server could
        not establish, which may well be the youngest. The safe fallback is
        the youngest band's own row.
        """
        enabled, goal = _resolve_ring_settings("unknown-band", None, None)
        assert enabled is False
        assert goal == 2
        assert (enabled, goal) == _resolve_ring_settings("3-5", None, None)

    def test_an_explicit_setting_still_wins_for_an_unknown_band(self) -> None:
        # The conservative fallback governs the DEFAULT only; a guardian who
        # has explicitly chosen is still obeyed.
        enabled, goal = _resolve_ring_settings(
            "unknown-band", ring_enabled=True, ring_goal_days=4
        )
        assert enabled is True
        assert goal == 4


@pytest.mark.unit
class TestReadingDayTotals:
    """Pins the ISO-week-Monday-start and lifetime-days-read computation."""

    def test_week_start_is_monday(self) -> None:
        # 2026-01-01 is a Thursday.
        assert _week_start(date(2026, 1, 1)) == date(2025, 12, 29)
        assert _week_start(date(2025, 12, 29)) == date(2025, 12, 29)

    def test_week_start_agrees_with_the_guardian_summarys_own_copy(self) -> None:
        """The two ``_week_start`` copies must never disagree.

        ``api/reading_history.py`` defines the same helper for the guardian
        summary; ``api/progress.py`` duplicates it rather than importing,
        because that one is module-private and W3's touch scope did not include
        editing the guardian module to export it. That is a defensible scope
        call, but until now only this copy was tested, so a change to either
        could silently make the kid's ring and the guardian's "days read this
        week" disagree about which days count. Same story, two numbers, no
        failing test.

        Sweeping a full year plus both year boundaries covers every weekday
        alignment and the ISO-week/calendar-year seam where a naive
        implementation diverges.
        """
        for offset in range(370):
            day = date(2025, 12, 25) + timedelta(days=offset)
            assert _week_start(day) == _history_week_start(day), day

    def test_zero_second_days_do_not_count(self) -> None:
        profile_id = uuid.uuid4()
        rows = [
            ReadingActivityDay(
                child_profile_id=profile_id,
                activity_date=date(2025, 12, 30),
                active_seconds=0,
            ),
            ReadingActivityDay(
                child_profile_id=profile_id,
                activity_date=date(2025, 12, 31),
                active_seconds=120,
            ),
        ]
        days_this_week, lifetime_days = _reading_day_totals(rows, date(2026, 1, 1))
        assert days_this_week == 1
        assert lifetime_days == 1

    def test_days_outside_the_current_week_still_count_lifetime(self) -> None:
        profile_id = uuid.uuid4()
        rows = [
            ReadingActivityDay(
                child_profile_id=profile_id,
                activity_date=date(2025, 11, 1),
                active_seconds=300,
            ),
        ]
        days_this_week, lifetime_days = _reading_day_totals(rows, date(2026, 1, 1))
        assert days_this_week == 0
        assert lifetime_days == 1


@pytest.mark.unit
def test_found_ending_title_strips_sentinels() -> None:
    """Referenced by name from tests/unit/test_title_strip_registry.py's
    ENFORCED mapping (``FoundEndingView.title``); kept as a bare top-level
    function so that registry's plain-text ``def <name>(`` scan finds it.
    """
    token = wrap("HERO", "Explorer")
    profile_id = uuid.uuid4()
    completion = Completion(
        child_profile_id=profile_id,
        storybook_id="story-a",
        version=1,
        ending_id="e1",
    )
    completion.found_at = _T1
    version = StorybookVersion(
        storybook_id="story-a",
        version=1,
        blob={
            "nodes": [
                {
                    "id": "n1",
                    "is_ending": True,
                    "ending": {
                        "id": "e1",
                        "valence": "positive",
                        "kind": "success",
                        "title": f"{token} Wins!",
                    },
                }
            ],
        },
    )
    found_endings_by_book = _build_found_endings(
        [completion], {("story-a", 1): version}
    )
    title = found_endings_by_book["story-a"][0].title
    assert "{~" not in title
    assert "Explorer" in title


@pytest.mark.unit
def test_router_declares_the_403_it_can_raise() -> None:
    """A denial the client cannot model is a denial the UI mishandles.

    Every route here runs ``_require_child_profile``, which raises
    ``AuthorizationError`` (403) for a non-child principal. With only 401
    declared, the generated client's error union omitted 403 entirely, so a
    guardian previewing as a child got an unmodelled failure that read as an
    empty success rather than a denial.
    """
    assert set(progress_router.responses) >= {401, 403}
