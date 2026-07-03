"""Unit tests for the library API handlers (no DB, no ASGI stack).

Calls route functions directly with a fake session and a constructed principal,
following the pattern established in test_ratings_api_unit.py. Covers:
list_library (happy path, empty library, invalid UUID, profile IDOR, family
IDOR, N+1 prevention, blob metadata edge cases) and get_storybook_version
(happy path, storybook not found, version not found, family IDOR). Also covers
the _parse_profile_id and _library_item helpers directly.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.api.library import (
    _library_item,
    _parse_profile_id,
    get_storybook_version,
    list_library,
)
from cyo_adventure.api.schemas import LibraryItem, LibraryProgress
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import Rating, ReadingState, Storybook, StorybookVersion

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy import Select

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeScalars:
    """Returned by session.scalars() -- wraps a list of ORM rows."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        """Return seeded rows."""
        return self._rows

    def __iter__(self) -> object:
        """Support direct iteration (e.g. `for row in scalars_result`)."""
        return iter(self._rows)


class _FakeSession:
    """Minimal async session double for library API handlers."""

    def __init__(
        self,
        *,
        storybooks: list[Storybook] | None = None,
        versions: list[StorybookVersion] | None = None,
        states: list[ReadingState] | None = None,
        ratings: list[Rating] | None = None,
        get_map: dict[tuple[type[object], object], object] | None = None,
        scalar_result: object | None = None,
    ) -> None:
        # scalars() cycles in order: storybooks, versions, reading states, ratings.
        self._scalars_queue: list[list[object]] = [
            list(storybooks or []),
            list(versions or []),
            list(states or []),
            list(ratings or []),
        ]
        self._get_map: dict[tuple[type[object], object], object] = get_map or {}
        self._scalar_result = scalar_result
        self.scalars_calls: list[object] = []
        self.get_calls: list[tuple[type[object], object]] = []

    async def get(self, model: type[object], key: object) -> object | None:
        """Look up by (model, key) in the seeded map."""
        self.get_calls.append((model, key))
        return self._get_map.get((model, key))

    async def scalar(self, stmt: object) -> object | None:
        """Return the seeded scalar (the assignment lookup in get_storybook_version)."""
        self.scalars_calls.append(stmt)
        return self._scalar_result

    async def scalars(self, stmt: object) -> _FakeScalars:
        """Return rows from the queue in order (storybooks then versions)."""
        self.scalars_calls.append(stmt)
        rows = self._scalars_queue[0] if self._scalars_queue else []
        if self._scalars_queue:
            self._scalars_queue = self._scalars_queue[1:]
        return _FakeScalars(rows)


def _flatten_params(values: Iterable[object]) -> set[object]:
    """Flatten compiled bind params, unpacking IN-clause list values.

    ``Select.compile().params`` binds an ``IN`` filter's values as a list, so
    a bare ``set()`` over the raw values raises TypeError on the unhashable
    list. This flattens one level deep so scalar and list-bound params can be
    membership-tested uniformly.
    """
    flat: set[object] = set()
    for value in values:
        if isinstance(value, list):
            flat.update(value)
        else:
            flat.add(value)
    return flat


def _child_principal(family_id: uuid.UUID, profile_id: uuid.UUID) -> Principal:
    """Build a child principal allowed to act on exactly one profile."""
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="child",
        family_id=family_id,
        profile_ids=frozenset({profile_id}),
    )


def _guardian_principal(family_id: uuid.UUID) -> Principal:
    """Build a guardian principal with no specific profile restriction."""
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=family_id,
        profile_ids=frozenset(),
    )


def _admin_principal(family_id: uuid.UUID) -> Principal:
    """Build a global admin principal (cross-family read authority)."""
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="admin",
        family_id=family_id,
        profile_ids=frozenset(),
    )


def _published_book(
    storybook_id: str, family_id: uuid.UUID, version: int = 1
) -> Storybook:
    """Return a Storybook row in 'published' status with a current version."""
    book = Storybook(id=storybook_id, family_id=family_id)
    book.status = "published"
    book.current_published_version = version
    return book


def _version_row(
    storybook_id: str,
    version: int,
    blob: dict[str, object] | None = None,
) -> StorybookVersion:
    """Return a StorybookVersion with a minimal content blob."""
    if blob is None:
        blob = {
            "title": "The Dragon's Den",
            "metadata": {
                "age_band": "8-10",
                "tier": 2,
                "reading_level": {"target": 4.5},
            },
        }
    return StorybookVersion(storybook_id=storybook_id, version=version, blob=blob)


def _state_row(
    profile_id: uuid.UUID,
    storybook_id: str,
    *,
    visit_set: list[str],
    current_node: str = "n1",
    version: int = 1,
) -> ReadingState:
    """Return an in-memory ReadingState row with a deterministic updated_at."""
    row = ReadingState(
        child_profile_id=profile_id,
        storybook_id=storybook_id,
        version=version,
        current_node=current_node,
        visit_set=visit_set,
    )
    row.updated_at = datetime(2026, 7, 1, tzinfo=UTC)
    return row


# ---------------------------------------------------------------------------
# _parse_profile_id
# ---------------------------------------------------------------------------


class TestParseProfileId:
    @pytest.mark.unit
    def test_valid_uuid_string_returns_uuid(self) -> None:
        """A valid UUID string is parsed without error."""
        raw = str(uuid.uuid4())
        result = _parse_profile_id(raw)
        assert isinstance(result, uuid.UUID)
        assert str(result) == raw

    @pytest.mark.unit
    def test_invalid_string_raises_validation_error(self) -> None:
        """A non-UUID string raises ValidationError with the field name."""
        with pytest.raises(ValidationError) as exc_info:
            _parse_profile_id("not-a-uuid")
        assert "profile_id" in str(exc_info.value)

    @pytest.mark.unit
    def test_empty_string_raises_validation_error(self) -> None:
        """An empty string raises ValidationError."""
        with pytest.raises(ValidationError):
            _parse_profile_id("")


# ---------------------------------------------------------------------------
# _library_item
# ---------------------------------------------------------------------------


class TestLibraryItem:
    @pytest.mark.unit
    def test_full_metadata_extracted_correctly(self) -> None:
        """All metadata fields map to the LibraryItem correctly."""
        blob: dict[str, object] = {
            "title": "Space Race",
            "metadata": {
                "age_band": "6-8",
                "tier": 1,
                "reading_level": {"target": 2.5},
            },
        }
        item = _library_item("story-1", blob, 3)
        assert item.id == "story-1"
        assert item.title == "Space Race"
        assert item.version == 3
        assert item.age_band == "6-8"
        assert item.tier == 1
        assert item.reading_level_target == 2.5

    @pytest.mark.unit
    def test_missing_title_falls_back_to_storybook_id(self) -> None:
        """When the blob has no title field the storybook id is used."""
        blob: dict[str, object] = {"metadata": {"age_band": "8-10"}}
        item = _library_item("fallback-id", blob, 1)
        assert item.title == "fallback-id"

    @pytest.mark.unit
    def test_non_string_title_falls_back_to_storybook_id(self) -> None:
        """A non-string title value falls back to the storybook id."""
        blob: dict[str, object] = {"title": 42, "metadata": {}}
        item = _library_item("my-story", blob, 1)
        assert item.title == "my-story"

    @pytest.mark.unit
    def test_missing_metadata_uses_defaults(self) -> None:
        """A blob without 'metadata' produces zero/empty defaults."""
        blob: dict[str, object] = {"title": "Plain Story"}
        item = _library_item("plain", blob, 1)
        assert item.age_band == ""
        assert item.tier == 0
        assert item.reading_level_target == 0.0

    @pytest.mark.unit
    def test_non_dict_metadata_uses_defaults(self) -> None:
        """A metadata field that is not a dict is treated as absent."""
        blob: dict[str, object] = {"title": "Story", "metadata": "not-a-dict"}
        item = _library_item("plain", blob, 1)
        assert item.age_band == ""
        assert item.tier == 0

    @pytest.mark.unit
    def test_reading_level_integer_target_accepted(self) -> None:
        """An integer reading_level target is coerced to float."""
        blob: dict[str, object] = {
            "title": "X",
            "metadata": {"reading_level": {"target": 3}},
        }
        item = _library_item("s", blob, 1)
        assert item.reading_level_target == 3.0

    @pytest.mark.unit
    def test_reading_level_non_numeric_target_defaults_to_zero(self) -> None:
        """A non-numeric target value defaults to 0.0."""
        blob: dict[str, object] = {
            "title": "X",
            "metadata": {"reading_level": {"target": "high"}},
        }
        item = _library_item("s", blob, 1)
        assert item.reading_level_target == 0.0

    @pytest.mark.unit
    def test_reading_level_not_a_dict_defaults_to_zero(self) -> None:
        """A non-dict reading_level field defaults to 0.0."""
        blob: dict[str, object] = {
            "title": "X",
            "metadata": {"reading_level": "advanced"},
        }
        item = _library_item("s", blob, 1)
        assert item.reading_level_target == 0.0

    @pytest.mark.unit
    def test_non_int_tier_defaults_to_zero(self) -> None:
        """A non-integer tier value defaults to 0."""
        blob: dict[str, object] = {"title": "X", "metadata": {"tier": "gold"}}
        item = _library_item("s", blob, 1)
        assert item.tier == 0

    @pytest.mark.unit
    def test_non_string_age_band_defaults_to_empty(self) -> None:
        """A non-string age_band value defaults to empty string."""
        blob: dict[str, object] = {"title": "X", "metadata": {"age_band": 8}}
        item = _library_item("s", blob, 1)
        assert item.age_band == ""

    @pytest.mark.unit
    def test_bool_tier_rejected_as_non_int(self) -> None:
        """A bool tier (True) must not read as 1; it falls back to 0."""
        blob: dict[str, object] = {"title": "X", "metadata": {"tier": True}}
        item = _library_item("s", blob, 1)
        assert item.tier == 0

    @pytest.mark.unit
    def test_bool_reading_level_target_rejected(self) -> None:
        """A bool reading_level target (True) must not read as 1.0; defaults to 0.0."""
        blob: dict[str, object] = {
            "title": "X",
            "metadata": {"reading_level": {"target": True}},
        }
        item = _library_item("s", blob, 1)
        assert item.reading_level_target == 0.0

    @pytest.mark.unit
    def test_nan_reading_level_target_defaults_to_zero(self) -> None:
        """A NaN target must be rejected (Starlette allow_nan=False would 500)."""
        blob: dict[str, object] = {
            "title": "X",
            "metadata": {"reading_level": {"target": float("nan")}},
        }
        item = _library_item("s", blob, 1)
        assert item.reading_level_target == 0.0
        assert math.isfinite(item.reading_level_target)

    @pytest.mark.unit
    def test_infinite_reading_level_target_defaults_to_zero(self) -> None:
        """An infinite target must be rejected so the response stays serializable."""
        blob: dict[str, object] = {
            "title": "X",
            "metadata": {"reading_level": {"target": float("inf")}},
        }
        item = _library_item("s", blob, 1)
        assert item.reading_level_target == 0.0

    @pytest.mark.unit
    def test_malformed_metadata_emits_structured_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A malformed metadata blob surfaces one structured warning, not silence."""
        blob: dict[str, object] = {
            "title": 42,
            "metadata": {"tier": True, "reading_level": {"target": float("nan")}},
        }
        with caplog.at_level("WARNING"):
            item = _library_item("noisy-story", blob, 7)

        assert item.title == "noisy-story"
        assert item.tier == 0
        assert item.reading_level_target == 0.0
        assert "library_item_malformed_metadata" in caplog.text
        assert "title" in caplog.text
        assert "tier" in caplog.text
        assert "reading_level.target" in caplog.text


# ---------------------------------------------------------------------------
# list_library
# ---------------------------------------------------------------------------


class TestListLibrary:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_happy_path_returns_library_view(self) -> None:
        """A profile with one published story gets a LibraryView with one item."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id, version=1)
        version = _version_row("story-1", 1)
        session = _FakeSession(storybooks=[book], versions=[version])
        principal = _child_principal(family_id, profile_id)

        result = await list_library(str(profile_id), principal, session)

        assert len(result.stories) == 1
        assert result.stories[0].id == "story-1"
        assert result.stories[0].title == "The Dragon's Den"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_query_is_family_scoped_and_version_fetch_is_bulk(self) -> None:
        """Enforce the IDOR/published filters and the single bulk version fetch.

        Inspects the SQL captured by the fake session so a regression that drops
        the family_id scope (cross-family IDOR), the published-only predicate, or
        collapses the single bulk version fetch into per-story queries (N+1)
        fails here rather than passing on seeded rows alone.
        """
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        books = [
            _published_book("story-a", family_id, version=1),
            _published_book("story-b", family_id, version=2),
        ]
        versions = [_version_row("story-a", 1), _version_row("story-b", 2)]
        session = _FakeSession(storybooks=books, versions=versions)
        principal = _child_principal(family_id, profile_id)

        await list_library(str(profile_id), principal, session)

        # Exactly four queries: storybooks, bulk version fetch, bulk reading
        # state fetch, bulk rating fetch (no N+1 for any of the four).
        assert len(session.scalars_calls) == 4

        # Inspect whereclause specifically: the SELECT column list names every
        # column, so checking the full statement string would still pass if a
        # predicate were dropped. The access scope lives in the WHERE clause.
        storybook_stmt = cast("Select[Any]", session.scalars_calls[0])
        storybook_where = str(storybook_stmt.whereclause)
        assert "family_id" in storybook_where  # cross-family IDOR scope
        assert "status" in storybook_where  # published-only predicate
        assert "current_published_version IS NOT NULL" in storybook_where

        # Column presence does not pin the value compared against it; bind the
        # family scope to THIS principal and the status to "published" so an
        # inverted predicate or a constant binding still fails here.
        storybook_params = set(storybook_stmt.compile().params.values())
        assert family_id in storybook_params  # bound to the caller's family
        assert "published" in storybook_params  # not "draft" / inverted

        # Assignment gate: the storybook query must correlate to an assignment
        # for the authorized profile, so an unassigned book cannot leak.
        assert "storybook_assignment" in storybook_where
        assert profile_id in storybook_params  # gate bound to the authorized profile

        # Composite (storybook_id, version) IN (...) bulk fetch, not per-story.
        # Qualify the version column: the bare substring "version" also matches
        # the table name "storybook_version", so it would pass even if the
        # composite key collapsed to storybook_id alone.
        version_where = str(cast("Select[Any]", session.scalars_calls[1]).whereclause)
        assert "IN" in version_where
        assert "storybook_version.storybook_id" in version_where
        assert "storybook_version.version" in version_where

        # Bulk reading-state fetch (index 2): scoped to the authorized profile,
        # not the whole family, plus an IN filter on the published book ids so
        # a regression that widens the scope to every profile, or that drops
        # the published-book-id filter, fails here.
        state_stmt = cast("Select[Any]", session.scalars_calls[2])
        state_where = str(state_stmt.whereclause)
        assert "reading_state.child_profile_id" in state_where
        assert "reading_state.storybook_id" in state_where
        assert "IN" in state_where
        # The IN filter binds its values as a list, not a scalar, so flatten
        # before membership-testing (a bare set() would choke on the list).
        state_params = _flatten_params(state_stmt.compile().params.values())
        assert profile_id in state_params  # bound to the authorized profile
        assert "story-a" in state_params  # bound to the published book ids
        assert "story-b" in state_params

        # Bulk rating fetch (index 3): same profile scope and book-id IN filter.
        rating_stmt = cast("Select[Any]", session.scalars_calls[3])
        rating_where = str(rating_stmt.whereclause)
        assert "rating.child_profile_id" in rating_where
        assert "rating.storybook_id" in rating_where
        assert "IN" in rating_where
        rating_params = _flatten_params(rating_stmt.compile().params.values())
        assert profile_id in rating_params  # bound to the authorized profile
        assert "story-a" in rating_params  # bound to the published book ids
        assert "story-b" in rating_params

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_library_returns_empty_view(self) -> None:
        """When no published stories exist the result has an empty stories list."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        session = _FakeSession(storybooks=[], versions=[])
        principal = _child_principal(family_id, profile_id)

        result = await list_library(str(profile_id), principal, session)

        assert result.stories == []
        # Only one scalars() call should be made (for storybooks; version query is skipped).
        assert len(session.scalars_calls) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_uuid_profile_raises_validation_error(self) -> None:
        """A non-UUID profile_id string raises ValidationError."""
        family_id = uuid.uuid4()
        session = _FakeSession()
        principal = _guardian_principal(family_id)

        with pytest.raises(ValidationError):
            await list_library("not-a-uuid", principal, session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_cannot_list_another_profile(self) -> None:
        """A child principal that does not own the requested profile gets 403."""
        family_id = uuid.uuid4()
        my_profile = uuid.uuid4()
        other_profile = uuid.uuid4()
        session = _FakeSession()
        principal = _child_principal(family_id, my_profile)

        with pytest.raises(AuthorizationError):
            await list_library(str(other_profile), principal, session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_stories_all_returned(self) -> None:
        """Multiple published stories in the family all appear in the listing."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        books = [
            _published_book("story-a", family_id, version=1),
            _published_book("story-b", family_id, version=2),
        ]
        versions = [
            _version_row("story-a", 1),
            _version_row("story-b", 2),
        ]
        session = _FakeSession(storybooks=books, versions=versions)
        principal = _child_principal(family_id, profile_id)

        result = await list_library(str(profile_id), principal, session)

        assert len(result.stories) == 2
        ids = {s.id for s in result.stories}
        assert "story-a" in ids
        assert "story-b" in ids

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_version_missing_from_blob_map_is_silently_skipped(self) -> None:
        """A storybook whose version is absent from the version query is omitted."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id, version=1)
        # Return no StorybookVersion rows so the blob map is empty.
        session = _FakeSession(storybooks=[book], versions=[])
        principal = _child_principal(family_id, profile_id)

        result = await list_library(str(profile_id), principal, session)

        assert result.stories == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_guardian_with_child_profile_can_list_library(self) -> None:
        """A guardian whose profile_ids includes the child profile can list the library.

        In production _resolve_profiles() loads all family profiles for guardians,
        so the guardian principal's profile_ids is non-empty at request time.
        """
        family_id = uuid.uuid4()
        child_profile = uuid.uuid4()
        book = _published_book("story-g", family_id, version=1)
        version = _version_row("story-g", 1)
        session = _FakeSession(storybooks=[book], versions=[version])
        # Simulate a guardian whose profile_ids contains the child profile
        # (as _resolve_profiles() would populate it in production).
        guardian = Principal(
            subject="sub",
            user_id=uuid.uuid4(),
            role="guardian",
            family_id=family_id,
            profile_ids=frozenset({child_profile}),
        )

        result = await list_library(str(child_profile), guardian, session)

        assert len(result.stories) == 1


# ---------------------------------------------------------------------------
# get_storybook_version
# ---------------------------------------------------------------------------


class TestGetStorybookVersion:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_happy_path_returns_blob(self) -> None:
        """A valid storybook+version owned by the principal returns the blob."""
        family_id = uuid.uuid4()
        book = _published_book("story-1", family_id, version=1)
        blob: dict[str, object] = {"title": "Test", "nodes": []}
        version = _version_row("story-1", 1, blob=blob)
        # approved_by must be set: the library guard rejects non-admin reads of
        # unapproved versions even when the story status is published (Task 6).
        version.approved_by = uuid.uuid4()
        get_map: dict[tuple[type[object], object], object] = {
            (Storybook, "story-1"): book,
            (StorybookVersion, ("story-1", 1)): version,
        }
        session = _FakeSession(get_map=get_map)
        principal = _guardian_principal(family_id)

        result = await get_storybook_version("story-1", 1, principal, session)

        assert result == blob

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_storybook_not_found_raises_resource_not_found(self) -> None:
        """A missing storybook raises ResourceNotFoundError."""
        family_id = uuid.uuid4()
        session = _FakeSession(get_map={})
        principal = _guardian_principal(family_id)

        with pytest.raises(ResourceNotFoundError):
            await get_storybook_version("no-such-book", 1, principal, session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_version_not_found_raises_resource_not_found(self) -> None:
        """A valid storybook with a missing version raises ResourceNotFoundError."""
        family_id = uuid.uuid4()
        book = _published_book("story-1", family_id, version=1)
        get_map: dict[tuple[type[object], object], object] = {
            (Storybook, "story-1"): book,
            # No entry for (StorybookVersion, ("story-1", 99))
        }
        session = _FakeSession(get_map=get_map)
        principal = _guardian_principal(family_id)

        with pytest.raises(ResourceNotFoundError):
            await get_storybook_version("story-1", 99, principal, session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_non_admin_non_current_version_raises_404(self) -> None:
        """Published at v2, a non-admin requesting v1 gets 404 (non-current)."""
        family_id = uuid.uuid4()
        book = _published_book("story-1", family_id, version=2)
        v1 = _version_row("story-1", 1, blob={"title": "old"})
        v1.approved_by = uuid.uuid4()
        get_map: dict[tuple[type[object], object], object] = {
            (Storybook, "story-1"): book,
            (StorybookVersion, ("story-1", 1)): v1,
        }
        session = _FakeSession(get_map=get_map)
        principal = _guardian_principal(family_id)

        with pytest.raises(ResourceNotFoundError):
            await get_storybook_version("story-1", 1, principal, session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_admin_reads_non_current_version_returns_blob(self) -> None:
        """An admin may read a non-current version (v1) of a story published at v2."""
        family_id = uuid.uuid4()
        other_family = uuid.uuid4()
        book = _published_book("story-1", family_id, version=2)
        blob: dict[str, object] = {"title": "old", "nodes": []}
        v1 = _version_row("story-1", 1, blob=blob)
        get_map: dict[tuple[type[object], object], object] = {
            (Storybook, "story-1"): book,
            (StorybookVersion, ("story-1", 1)): v1,
        }
        session = _FakeSession(get_map=get_map)
        # Admin from a different family: cross-family read is permitted.
        principal = _admin_principal(other_family)

        result = await get_storybook_version("story-1", 1, principal, session)

        assert result == blob

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cross_family_access_raises_authorization(self) -> None:
        """A storybook owned by another family raises AuthorizationError."""
        my_family = uuid.uuid4()
        other_family = uuid.uuid4()
        book = _published_book("story-1", other_family, version=1)
        get_map: dict[tuple[type[object], object], object] = {
            (Storybook, "story-1"): book,
        }
        session = _FakeSession(get_map=get_map)
        principal = _guardian_principal(my_family)

        with pytest.raises(AuthorizationError):
            await get_storybook_version("story-1", 1, principal, session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_unassigned_published_version_raises_404(self) -> None:
        """A child fetching a published+approved but UNASSIGNED book gets 404."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id, version=1)
        version = _version_row("story-1", 1)
        version.approved_by = uuid.uuid4()
        get_map: dict[tuple[type[object], object], object] = {
            (Storybook, "story-1"): book,
            (StorybookVersion, ("story-1", 1)): version,
        }
        session = _FakeSession(get_map=get_map, scalar_result=None)  # not assigned
        principal = _child_principal(family_id, profile_id)
        with pytest.raises(ResourceNotFoundError):
            await get_storybook_version("story-1", 1, principal, session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_assigned_version_returns_blob(self) -> None:
        """A child fetching a book assigned to their profile receives the blob."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id, version=1)
        blob: dict[str, object] = {"title": "Test", "nodes": []}
        version = _version_row("story-1", 1, blob=blob)
        version.approved_by = uuid.uuid4()
        get_map: dict[tuple[type[object], object], object] = {
            (Storybook, "story-1"): book,
            (StorybookVersion, ("story-1", 1)): version,
        }
        session = _FakeSession(get_map=get_map, scalar_result="story-1")  # assigned
        principal = _child_principal(family_id, profile_id)
        result = await get_storybook_version("story-1", 1, principal, session)
        assert result == blob


class TestLibraryItemEnrichmentFields:
    """New per-profile fields default to safe empties for callers that omit them."""

    @pytest.mark.unit
    def test_new_fields_default(self) -> None:
        item = LibraryItem(
            id="s1",
            title="T",
            version=1,
            age_band="6-8",
            tier=1,
            reading_level_target=2.0,
        )
        assert item.node_count == 0
        assert item.rating is None
        assert item.progress is None

    @pytest.mark.unit
    def test_progress_round_trip(self) -> None:
        progress = LibraryProgress(
            current_node="n3",
            nodes_visited=4,
            updated_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
        item = LibraryItem(
            id="s1",
            title="T",
            version=2,
            age_band="6-8",
            tier=1,
            reading_level_target=2.0,
            node_count=12,
            rating=5,
            progress=progress,
        )
        assert item.progress is not None
        assert item.progress.nodes_visited == 4
        assert item.node_count == 12
        assert item.rating == 5


class TestListLibraryEnrichment:
    """list_library joins per-profile reading state and ratings into items."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_progress_and_rating_attached(self) -> None:
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        blob: dict[str, object] = {
            "title": "The Lantern",
            "metadata": {
                "age_band": "6-8",
                "tier": 1,
                "reading_level": {"target": 2.0},
            },
            "nodes": [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}, {"id": "n4"}],
        }
        session = _FakeSession(
            storybooks=[_published_book("s1", family_id, version=2)],
            versions=[_version_row("s1", 2, blob=blob)],
            states=[
                _state_row(profile_id, "s1", visit_set=["n1", "n2"], current_node="n2")
            ],
            ratings=[Rating(child_profile_id=profile_id, storybook_id="s1", value=4)],
        )
        view = await list_library(
            str(profile_id), _child_principal(family_id, profile_id), session
        )
        item = view.stories[0]
        assert item.node_count == 4
        assert item.rating == 4
        assert item.progress is not None
        assert item.progress.current_node == "n2"
        assert item.progress.nodes_visited == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_state_no_rating_yields_none(self) -> None:
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        blob: dict[str, object] = {
            "title": "T",
            "metadata": {},
            "nodes": [{"id": "n1"}],
        }
        session = _FakeSession(
            storybooks=[_published_book("s1", family_id)],
            versions=[_version_row("s1", 1, blob=blob)],
        )
        view = await list_library(
            str(profile_id), _child_principal(family_id, profile_id), session
        )
        item = view.stories[0]
        assert item.node_count == 1
        assert item.rating is None
        assert item.progress is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_malformed_nodes_gives_zero_count(self) -> None:
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        blob: dict[str, object] = {"title": "T", "metadata": {}, "nodes": "not-a-list"}
        session = _FakeSession(
            storybooks=[_published_book("s1", family_id)],
            versions=[_version_row("s1", 1, blob=blob)],
        )
        view = await list_library(
            str(profile_id), _child_principal(family_id, profile_id), session
        )
        assert view.stories[0].node_count == 0
