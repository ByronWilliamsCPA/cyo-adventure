"""Unit tests for the pure kid-progress badge computation (W3.1).

Pure, DB-free tests: every fixture is a real ``Completion``/``Rating``/
``StoryRequest`` ORM instance constructed directly (no session, no flush --
SQLAlchemy mapped classes are plain Python objects until added to a session),
mirroring ``tests/unit/test_notifications_registry.py``'s convention.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cyo_adventure.db.models import Completion, Rating, StoryRequest
from cyo_adventure.progress.badges import BADGE_CATALOG, compute_progress
from cyo_adventure.progress.models import ProgressFacts

_T1 = datetime(2026, 1, 1, tzinfo=UTC)
_T2 = datetime(2026, 1, 2, tzinfo=UTC)
_T3 = datetime(2026, 1, 3, tzinfo=UTC)
_T4 = datetime(2026, 1, 4, tzinfo=UTC)


def _completion(
    storybook_id: str,
    ending_id: str,
    *,
    version: int = 1,
    found_at: datetime = _T1,
    profile_id: uuid.UUID | None = None,
) -> Completion:
    row = Completion(
        child_profile_id=profile_id or uuid.uuid4(),
        storybook_id=storybook_id,
        version=version,
        ending_id=ending_id,
    )
    row.found_at = found_at
    return row


def _rating(
    storybook_id: str, *, value: int = 5, rated_at: datetime = _T1
) -> Rating:
    row = Rating(child_profile_id=uuid.uuid4(), storybook_id=storybook_id, value=value)
    row.rated_at = rated_at
    return row


def _child_request(created_at: datetime = _T1) -> StoryRequest:
    row = StoryRequest(
        family_id=uuid.uuid4(),
        request_text="a story",
        status="pending",
        age_band="8-11",
        initiator_role="child",
    )
    row.created_at = created_at
    return row


def _guardian_request(created_at: datetime = _T1) -> StoryRequest:
    row = StoryRequest(
        family_id=uuid.uuid4(),
        request_text="a story",
        status="pending",
        age_band="8-11",
        initiator_role="guardian",
    )
    row.created_at = created_at
    return row


def _compute(
    *,
    completions: list[Completion] | None = None,
    ratings: list[Rating] | None = None,
    story_requests: list[StoryRequest] | None = None,
    ending_valence: dict[tuple[str, int, str], str] | None = None,
    ending_total_by_book: dict[str, int] | None = None,
    series_by_book: dict[str, str | None] | None = None,
    series_membership: dict[str, frozenset[str]] | None = None,
) -> ProgressFacts:
    return compute_progress(
        completions=completions or [],
        ratings=ratings or [],
        child_story_requests=story_requests or [],
        ending_valence=ending_valence or {},
        ending_total_by_book=ending_total_by_book or {},
        book_titles={},
        series_by_book=series_by_book or {},
        series_membership=series_membership or {},
    )


def _badge_ids(facts: ProgressFacts) -> set[str]:
    return {badge.id for badge in facts.badges}


@pytest.mark.unit
class TestCatalog:
    def test_catalog_excludes_badges_9_and_12(self) -> None:
        """Badges 9 (Wish Come True) and 12 (Forty Days) are extension points."""
        assert "wish_come_true" not in BADGE_CATALOG
        assert "forty_days_of_stories" not in BADGE_CATALOG
        assert len(BADGE_CATALOG) == 10  # noqa: PLR2004


@pytest.mark.unit
class TestEmptyState:
    def test_no_data_earns_nothing(self) -> None:
        facts = _compute()
        assert facts.badges == []
        assert facts.books == []
        assert facts.totals.books_finished == 0
        assert facts.totals.endings_found == 0


@pytest.mark.unit
class TestFirstEnding:
    def test_earns_on_first_completion(self) -> None:
        facts = _compute(completions=[_completion("s1", "e1", found_at=_T2)])
        assert "first_ending" in _badge_ids(facts)
        badge = next(b for b in facts.badges if b.id == "first_ending")
        assert badge.earned_at == _T2

    def test_uses_earliest_completion(self) -> None:
        facts = _compute(
            completions=[
                _completion("s1", "e1", found_at=_T2),
                _completion("s1", "e2", found_at=_T1),
            ]
        )
        badge = next(b for b in facts.badges if b.id == "first_ending")
        assert badge.earned_at == _T1


@pytest.mark.unit
class TestPathNotTaken:
    def test_not_earned_with_one_ending(self) -> None:
        facts = _compute(completions=[_completion("s1", "e1")])
        assert "path_not_taken" not in _badge_ids(facts)

    def test_earned_with_two_distinct_endings_same_book(self) -> None:
        facts = _compute(
            completions=[
                _completion("s1", "e1", found_at=_T1),
                _completion("s1", "e2", found_at=_T2),
            ]
        )
        assert "path_not_taken" in _badge_ids(facts)
        badge = next(b for b in facts.badges if b.id == "path_not_taken")
        assert badge.earned_at == _T2  # the SECOND distinct ending's time

    def test_not_earned_by_two_endings_in_different_books(self) -> None:
        facts = _compute(
            completions=[
                _completion("s1", "e1", found_at=_T1),
                _completion("s2", "e1", found_at=_T2),
            ]
        )
        assert "path_not_taken" not in _badge_ids(facts)

    def test_replay_dedupe_a_revisited_ending_does_not_count_twice(self) -> None:
        """Reaching the SAME ending again (a replay) is not a second distinct
        ending; version is ignored per the dedup contract.
        """
        facts = _compute(
            completions=[
                _completion("s1", "e1", found_at=_T1),
                _completion("s1", "e1", version=2, found_at=_T2),
            ]
        )
        assert "path_not_taken" not in _badge_ids(facts)


@pytest.mark.unit
class TestEveryPathWalked:
    def test_earned_when_all_declared_endings_found(self) -> None:
        facts = _compute(
            completions=[
                _completion("s1", "e1", found_at=_T1),
                _completion("s1", "e2", found_at=_T2),
            ],
            ending_total_by_book={"s1": 2},
        )
        assert "every_path_walked" in _badge_ids(facts)
        book = facts.books[0]
        assert book.every_path_walked is True

    def test_not_earned_when_endings_remain(self) -> None:
        facts = _compute(
            completions=[_completion("s1", "e1", found_at=_T1)],
            ending_total_by_book={"s1": 2},
        )
        assert "every_path_walked" not in _badge_ids(facts)
        assert facts.books[0].every_path_walked is False

    def test_zero_total_never_earns(self) -> None:
        """A book with no known total (unpublished/degraded) never claims completion."""
        facts = _compute(
            completions=[_completion("s1", "e1", found_at=_T1)],
            ending_total_by_book={},
        )
        assert "every_path_walked" not in _badge_ids(facts)


@pytest.mark.unit
class TestBookwormAndShelfHero:
    def _five_books(self, offset: int = 0) -> list[Completion]:
        return [
            _completion(f"s{i}", "e1", found_at=datetime(2026, 1, i + 1, tzinfo=UTC))
            for i in range(1 + offset, 6 + offset)
        ]

    def test_bookworm_earns_at_five_distinct_books(self) -> None:
        facts = _compute(completions=self._five_books())
        assert "bookworm" in _badge_ids(facts)
        assert "shelf_hero" not in _badge_ids(facts)

    def test_bookworm_not_earned_with_four_books(self) -> None:
        facts = _compute(completions=self._five_books()[:4])
        assert "bookworm" not in _badge_ids(facts)

    def test_shelf_hero_earns_at_ten_distinct_books(self) -> None:
        completions = [
            _completion(f"s{i}", "e1", found_at=datetime(2026, 1, (i % 28) + 1, tzinfo=UTC))
            for i in range(10)
        ]
        facts = _compute(completions=completions)
        assert "bookworm" in _badge_ids(facts)
        assert "shelf_hero" in _badge_ids(facts)

    def test_totals_books_finished_counts_distinct_storybook_ids(self) -> None:
        facts = _compute(
            completions=[
                _completion("s1", "e1", found_at=_T1),
                _completion("s1", "e2", found_at=_T2),
                _completion("s2", "e1", found_at=_T3),
            ]
        )
        assert facts.totals.books_finished == 2  # noqa: PLR2004


@pytest.mark.unit
class TestEndingCollector:
    def test_earns_at_twenty_five_distinct_endings(self) -> None:
        completions = [
            _completion(
                f"s{i // 5}", f"e{i}", found_at=datetime(2026, 1, (i % 28) + 1, tzinfo=UTC)
            )
            for i in range(25)
        ]
        facts = _compute(completions=completions)
        assert "ending_collector" in _badge_ids(facts)
        assert facts.totals.endings_found == 25  # noqa: PLR2004

    def test_not_earned_at_twenty_four(self) -> None:
        completions = [
            _completion(
                f"s{i // 5}", f"e{i}", found_at=datetime(2026, 1, (i % 28) + 1, tzinfo=UTC)
            )
            for i in range(24)
        ]
        facts = _compute(completions=completions)
        assert "ending_collector" not in _badge_ids(facts)


@pytest.mark.unit
class TestBraveReader:
    def test_earns_after_negative_then_different_ending(self) -> None:
        completions = [
            _completion("s1", "e-sad", found_at=_T1),
            _completion("s1", "e-happy", found_at=_T2),
        ]
        valence = {("s1", 1, "e-sad"): "negative", ("s1", 1, "e-happy"): "positive"}
        facts = _compute(completions=completions, ending_valence=valence)
        assert "brave_reader" in _badge_ids(facts)
        badge = next(b for b in facts.badges if b.id == "brave_reader")
        assert badge.earned_at == _T2

    def test_not_earned_without_a_negative_ending_first(self) -> None:
        completions = [
            _completion("s1", "e-happy1", found_at=_T1),
            _completion("s1", "e-happy2", found_at=_T2),
        ]
        valence = {
            ("s1", 1, "e-happy1"): "positive",
            ("s1", 1, "e-happy2"): "positive",
        }
        facts = _compute(completions=completions, ending_valence=valence)
        assert "brave_reader" not in _badge_ids(facts)

    def test_repeating_the_same_negative_ending_does_not_earn(self) -> None:
        """Revisiting the SAME negative ending again is not 'found another'."""
        completions = [
            _completion("s1", "e-sad", found_at=_T1),
            _completion("s1", "e-sad", version=2, found_at=_T2),
        ]
        valence = {("s1", 1, "e-sad"): "negative", ("s1", 2, "e-sad"): "negative"}
        facts = _compute(completions=completions, ending_valence=valence)
        assert "brave_reader" not in _badge_ids(facts)

    def test_earns_only_after_the_negative_ending_not_before(self) -> None:
        """A different ending found BEFORE the negative one does not count."""
        completions = [
            _completion("s1", "e-happy", found_at=_T1),
            _completion("s1", "e-sad", found_at=_T2),
        ]
        valence = {("s1", 1, "e-happy"): "positive", ("s1", 1, "e-sad"): "negative"}
        facts = _compute(completions=completions, ending_valence=valence)
        assert "brave_reader" not in _badge_ids(facts)

    def test_brave_reader_missing_valence_data_never_earns(self) -> None:
        """A completion absent from ending_valence defaults to non-negative."""
        completions = [
            _completion("s1", "e1", found_at=_T1),
            _completion("s1", "e2", found_at=_T2),
        ]
        facts = _compute(completions=completions, ending_valence={})
        assert "brave_reader" not in _badge_ids(facts)


@pytest.mark.unit
class TestStoryWisher:
    def test_earns_on_child_initiated_request(self) -> None:
        facts = _compute(story_requests=[_child_request(created_at=_T1)])
        assert "story_wisher" in _badge_ids(facts)

    def test_guardian_initiated_request_does_not_earn(self) -> None:
        facts = _compute(story_requests=[_guardian_request(created_at=_T1)])
        assert "story_wisher" not in _badge_ids(facts)

    def test_uses_earliest_child_request(self) -> None:
        facts = _compute(
            story_requests=[
                _child_request(created_at=_T2),
                _child_request(created_at=_T1),
            ]
        )
        badge = next(b for b in facts.badges if b.id == "story_wisher")
        assert badge.earned_at == _T1


@pytest.mark.unit
class TestStarGiver:
    def test_earns_at_three_distinct_books_rated(self) -> None:
        facts = _compute(
            ratings=[
                _rating("s1", rated_at=_T1),
                _rating("s2", rated_at=_T2),
                _rating("s3", rated_at=_T3),
            ]
        )
        assert "star_giver" in _badge_ids(facts)
        badge = next(b for b in facts.badges if b.id == "star_giver")
        assert badge.earned_at == _T3

    def test_not_earned_at_two_books(self) -> None:
        facts = _compute(
            ratings=[_rating("s1", rated_at=_T1), _rating("s2", rated_at=_T2)]
        )
        assert "star_giver" not in _badge_ids(facts)


@pytest.mark.unit
class TestSeriesFinisher:
    def test_earns_when_every_series_book_finished(self) -> None:
        facts = _compute(
            completions=[
                _completion("s1", "e1", found_at=_T1),
                _completion("s2", "e1", found_at=_T2),
            ],
            series_by_book={"s1": "series-a", "s2": "series-a"},
            series_membership={"series-a": frozenset({"s1", "s2"})},
        )
        assert "series_finisher" in _badge_ids(facts)
        badge = next(b for b in facts.badges if b.id == "series_finisher")
        assert badge.earned_at == _T2  # the LAST book to be finished

    def test_not_earned_with_a_book_missing(self) -> None:
        facts = _compute(
            completions=[_completion("s1", "e1", found_at=_T1)],
            series_by_book={"s1": "series-a", "s2": "series-a"},
            series_membership={"series-a": frozenset({"s1", "s2"})},
        )
        assert "series_finisher" not in _badge_ids(facts)

    def test_standalone_book_never_earns(self) -> None:
        facts = _compute(
            completions=[_completion("s1", "e1", found_at=_T1)],
            series_by_book={"s1": None},
            series_membership={},
        )
        assert "series_finisher" not in _badge_ids(facts)


@pytest.mark.unit
class TestBookStates:
    def test_book_progress_reports_finished_and_totals(self) -> None:
        facts = _compute(
            completions=[
                _completion("s1", "e1", found_at=_T1),
                _completion("s1", "e2", found_at=_T2),
            ],
            ending_total_by_book={"s1": 3},
        )
        book = facts.books[0]
        assert book.storybook_id == "s1"
        assert book.endings_found == 2  # noqa: PLR2004
        assert book.total_endings == 3  # noqa: PLR2004
        assert book.finished is True
        assert book.every_path_walked is False

    def test_books_sorted_by_storybook_id(self) -> None:
        facts = _compute(
            completions=[
                _completion("zeta", "e1", found_at=_T1),
                _completion("alpha", "e1", found_at=_T2),
            ]
        )
        assert [b.storybook_id for b in facts.books] == ["alpha", "zeta"]


@pytest.mark.unit
class TestBadgeOrdering:
    def test_badges_sorted_oldest_earned_first(self) -> None:
        facts = _compute(
            completions=[
                _completion("s1", "e1", found_at=_T3),
                _completion("s1", "e2", found_at=_T4),
            ],
            story_requests=[_child_request(created_at=_T1)],
        )
        earned_order = [b.id for b in facts.badges]
        assert earned_order.index("story_wisher") < earned_order.index("first_ending")
