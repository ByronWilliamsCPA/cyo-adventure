"""Unit tests for the rating API handlers (no DB, no ASGI stack).

These call the route functions directly with a fake session and a constructed
principal, mirroring ``test_generation_api_unit.py``. They exist because the
Docker-less compatibility/unit matrix skips the testcontainers integration
suite, so the handler bodies in ``api/ratings.py`` are otherwise absent from the
coverage report CI uploads. They lock in: the upsert insert and overwrite
branches, the 404-before-family-auth ordering, the malformed-UUID 422 path on
both endpoints, and the family/profile authorization gates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.ratings import list_ratings, record_rating
from cyo_adventure.api.schemas import RatingBody
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import Rating, Storybook

_FIXED_TS = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeScalars:
    """Stand-in for the iterable returned by ``session.scalars``."""

    def __init__(self, values: list[Rating]) -> None:
        self._values = values

    def all(self) -> list[Rating]:
        """Return the seeded Rating rows."""
        return self._values


class _FakeSession:
    """Minimal async session double for the rating API handlers."""

    def __init__(
        self,
        *,
        storybook: Storybook | None = None,
        existing_rating: Rating | None = None,
        list_rows: list[Rating] | None = None,
    ) -> None:
        self._storybook = storybook
        self._existing_rating = existing_rating
        self._list_rows = list_rows or []
        self.added: list[object] = []
        self.flush_count = 0

    async def get(self, model: type[object], key: object) -> object | None:
        """Return the seeded Storybook or existing Rating by model type."""
        _ = key
        if model is Storybook:
            return self._storybook
        if model is Rating:
            return self._existing_rating
        return None

    def add(self, obj: object) -> None:
        """Record an added ORM instance."""
        self.added.append(obj)

    async def flush(self) -> None:
        """Count flushes (no-op persistence)."""
        self.flush_count += 1

    async def refresh(self, obj: object, attrs: list[str] | None = None) -> None:
        """Populate server-side timestamps the handler reads back after flush."""
        for attr in attrs or ["rated_at", "updated_at"]:
            setattr(obj, attr, _FIXED_TS)

    async def scalars(self, statement: object) -> _FakeScalars:
        """Return the seeded rating rows for the list endpoint."""
        _ = statement
        return _FakeScalars(self._list_rows)


def _principal(family_id: uuid.UUID, profile_id: uuid.UUID) -> Principal:
    """Build a child principal that may act on ``profile_id``."""
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="child",
        family_id=family_id,
        profile_ids=frozenset({profile_id}),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_rating_inserts_new() -> None:
    """A first rating is inserted and echoed back with timestamps."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    book = Storybook(id="book-1", family_id=family_id)
    session = _FakeSession(storybook=book, existing_rating=None)
    ctx = RequestContext(principal=_principal(family_id, profile_id), session=session)

    view = await record_rating(
        RatingBody(profile_id=str(profile_id), storybook_id="book-1", value=4), ctx
    )

    assert view.value == 4
    assert view.storybook_id == "book-1"
    assert view.rated_at == _FIXED_TS
    added = [obj for obj in session.added if isinstance(obj, Rating)]
    assert len(added) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_rating_overwrites_existing() -> None:
    """Re-rating an existing row updates value without adding a new row."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    book = Storybook(id="book-1", family_id=family_id)
    existing = Rating(child_profile_id=profile_id, storybook_id="book-1", value=2)
    session = _FakeSession(storybook=book, existing_rating=existing)
    ctx = RequestContext(principal=_principal(family_id, profile_id), session=session)

    view = await record_rating(
        RatingBody(profile_id=str(profile_id), storybook_id="book-1", value=5), ctx
    )

    assert view.value == 5
    assert session.added == []
    assert existing.value == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_rating_unknown_storybook_raises_not_found() -> None:
    """A missing storybook raises ResourceNotFoundError (-> 404)."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    session = _FakeSession(storybook=None)
    ctx = RequestContext(principal=_principal(family_id, profile_id), session=session)

    with pytest.raises(ResourceNotFoundError):
        await record_rating(
            RatingBody(profile_id=str(profile_id), storybook_id="missing", value=3),
            ctx,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_rating_invalid_uuid_raises_validation() -> None:
    """A non-UUID profile_id raises ValidationError (-> 422)."""
    session = _FakeSession()
    ctx = RequestContext(
        principal=_principal(uuid.uuid4(), uuid.uuid4()), session=session
    )

    with pytest.raises(ValidationError):
        await record_rating(
            RatingBody(profile_id="not-a-uuid", storybook_id="book-1", value=3), ctx
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_rating_wrong_profile_raises_authorization() -> None:
    """A profile the principal cannot access raises AuthorizationError (-> 403)."""
    family_id = uuid.uuid4()
    session = _FakeSession()
    # principal may act on a different profile than the one in the body.
    ctx = RequestContext(principal=_principal(family_id, uuid.uuid4()), session=session)

    with pytest.raises(AuthorizationError):
        await record_rating(
            RatingBody(profile_id=str(uuid.uuid4()), storybook_id="book-1", value=3),
            ctx,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_rating_foreign_family_raises_authorization() -> None:
    """A storybook owned by another family raises AuthorizationError (-> 403)."""
    profile_id = uuid.uuid4()
    book = Storybook(id="book-1", family_id=uuid.uuid4())  # different family
    session = _FakeSession(storybook=book)
    ctx = RequestContext(
        principal=_principal(uuid.uuid4(), profile_id), session=session
    )

    with pytest.raises(AuthorizationError):
        await record_rating(
            RatingBody(profile_id=str(profile_id), storybook_id="book-1", value=3),
            ctx,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_ratings_returns_views() -> None:
    """The list handler maps each Rating row to a RatingView."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    row = Rating(child_profile_id=profile_id, storybook_id="book-1", value=5)
    row.rated_at = _FIXED_TS
    row.updated_at = _FIXED_TS
    session = _FakeSession(list_rows=[row])
    ctx = RequestContext(principal=_principal(family_id, profile_id), session=session)

    result = await list_ratings(str(profile_id), ctx)

    assert len(result.ratings) == 1
    assert result.ratings[0].storybook_id == "book-1"
    assert result.ratings[0].value == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_ratings_invalid_uuid_raises_validation() -> None:
    """A non-UUID profile_id on the list endpoint raises ValidationError (-> 422)."""
    session = _FakeSession()
    ctx = RequestContext(
        principal=_principal(uuid.uuid4(), uuid.uuid4()), session=session
    )

    with pytest.raises(ValidationError):
        await list_ratings("not-a-uuid", ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_ratings_wrong_profile_raises_authorization() -> None:
    """Listing a profile the principal cannot access raises AuthorizationError."""
    session = _FakeSession()
    ctx = RequestContext(
        principal=_principal(uuid.uuid4(), uuid.uuid4()), session=session
    )

    with pytest.raises(AuthorizationError):
        await list_ratings(str(uuid.uuid4()), ctx)
