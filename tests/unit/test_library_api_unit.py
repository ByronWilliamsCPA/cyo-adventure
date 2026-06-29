"""Unit tests for the library API handlers (no DB, no ASGI stack).

Calls route functions directly with a fake session and a constructed principal,
following the pattern established in test_ratings_api_unit.py. Covers:
list_library (happy path, empty library, invalid UUID, profile IDOR, family
IDOR, N+1 prevention, blob metadata edge cases) and get_storybook_version
(happy path, storybook not found, version not found, family IDOR). Also covers
the _parse_profile_id and _library_item helpers directly.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.api.library import (
    _library_item,
    _parse_profile_id,
    get_storybook_version,
    list_library,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import Storybook, StorybookVersion

if TYPE_CHECKING:
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
        get_map: dict[tuple[type[object], object], object] | None = None,
    ) -> None:
        # scalars() cycles: first call returns storybooks, second returns versions.
        self._scalars_queue: list[list[object]] = [
            list(storybooks or []),
            list(versions or []),
        ]
        self._get_map: dict[tuple[type[object], object], object] = get_map or {}
        self.scalars_calls: list[object] = []
        self.get_calls: list[tuple[type[object], object]] = []

    async def get(self, model: type[object], key: object) -> object | None:
        """Look up by (model, key) in the seeded map."""
        self.get_calls.append((model, key))
        return self._get_map.get((model, key))

    async def scalars(self, stmt: object) -> _FakeScalars:
        """Return rows from the queue in order (storybooks then versions)."""
        self.scalars_calls.append(stmt)
        rows = self._scalars_queue[0] if self._scalars_queue else []
        if self._scalars_queue:
            self._scalars_queue = self._scalars_queue[1:]
        return _FakeScalars(rows)


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

        # Exactly two queries: one for storybooks, one bulk version fetch (no N+1).
        assert len(session.scalars_calls) == 2

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

        # Composite (storybook_id, version) IN (...) bulk fetch, not per-story.
        # Qualify the version column: the bare substring "version" also matches
        # the table name "storybook_version", so it would pass even if the
        # composite key collapsed to storybook_id alone.
        version_where = str(cast("Select[Any]", session.scalars_calls[1]).whereclause)
        assert "IN" in version_where
        assert "storybook_version.storybook_id" in version_where
        assert "storybook_version.version" in version_where

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
