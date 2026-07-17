"""Unit tests for the K17 recommendation feed (ADR-016 rings 1-2).

Calls the route function and its helpers directly with a fake session and a
constructed principal, mirroring ``test_reading_history_api_unit.py``. Covers:
authorization (child own profile, guardian family, admin bypass, cross-family
403), the ring-1 family recommendation, the ring-2 connection recommendation
ONLY when both guardians have consented, the #CRITICAL dual-consent guard
(a connection missing either consent contributes zero recommendations, never
a partial result), immediate loss of visibility on revocation, and that a
profile's own ratings never appear as a recommendation of themselves.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.api.recommendations import (
    _dual_consented_connected_family_ids,
    _is_dual_consented,
    get_recommendations,
)
from cyo_adventure.core.exceptions import AuthorizationError, ResourceNotFoundError
from cyo_adventure.db.models import (
    ChildProfile,
    FamilyConnection,
    Rating,
    StorybookVersion,
)

_T1 = datetime(2026, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fake session
# ---------------------------------------------------------------------------


class _FakeExecuteResult:
    """Stand-in for the object ``session.execute()`` returns."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        """Return the seeded row tuples."""
        return self._rows


class _FakeScalars:
    """Stand-in for the object ``session.scalars()`` returns; iterable."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def __iter__(self) -> object:
        return iter(self._rows)


class _FakeSession:
    """Minimal async session double for ``get_recommendations``.

    ``session.scalars`` is called in a FIXED order by the handler (matching
    its own read sequence): visible-book StorybookVersion rows, ring-1
    ChildProfile ids, all-outgoing FamilyConnection rows, [ring-2 ChildProfile
    ids, only if any connection is dual-consented], Rating rows, then rater
    ChildProfile rows. Each test supplies exactly the queue that sequence
    needs; a test that expects an early return (no visible books, no raters)
    supplies a shorter queue.
    """

    def __init__(
        self,
        *,
        profile: ChildProfile | None = None,
        execute_rows: list[tuple[object, ...]] | None = None,
        scalars_queue: list[list[object]] | None = None,
    ) -> None:
        self._profile = profile
        self._execute_rows = execute_rows or []
        self._scalars_queue = [list(rows) for rows in (scalars_queue or [])]
        self.scalars_calls: list[object] = []

    async def get(self, model: type[object], _key: object) -> object | None:
        if model is ChildProfile:
            return self._profile
        return None

    async def execute(self, _stmt: object) -> _FakeExecuteResult:
        return _FakeExecuteResult(self._execute_rows)

    async def scalars(self, stmt: object) -> _FakeScalars:
        self.scalars_calls.append(stmt)
        rows = self._scalars_queue.pop(0) if self._scalars_queue else []
        return _FakeScalars(rows)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _child_principal(family_id: uuid.UUID, profile_id: uuid.UUID) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="child",
        family_id=family_id,
        profile_ids=frozenset({profile_id}),
    )


def _guardian_principal(
    family_id: uuid.UUID, profile_ids: frozenset[uuid.UUID]
) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=family_id,
        profile_ids=profile_ids,
    )


def _admin_principal() -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="admin",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _profile(
    profile_id: uuid.UUID, family_id: uuid.UUID, display_name: str = "Kid"
) -> ChildProfile:
    return ChildProfile(
        id=profile_id,
        family_id=family_id,
        display_name=display_name,
        age_band="8-11",
    )


def _version(storybook_id: str, version: int, title: str = "A Story") -> StorybookVersion:
    row = StorybookVersion(
        storybook_id=storybook_id, version=version, blob={"title": title}
    )
    row.cover_image_url = None
    return row


def _rating(profile_id: uuid.UUID, storybook_id: str, value: int) -> Rating:
    return Rating(child_profile_id=profile_id, storybook_id=storybook_id, value=value)


def _connection(
    viewer_family_id: uuid.UUID,
    sharer_family_id: uuid.UUID,
    *,
    viewer_consented: bool = False,
    sharer_consented: bool = False,
) -> FamilyConnection:
    row = FamilyConnection(
        id=uuid.uuid4(), family_id=viewer_family_id, connected_family_id=sharer_family_id
    )
    if viewer_consented:
        row.consented_by_viewer_user_id = uuid.uuid4()
        row.consented_by_viewer_at = _T1
    if sharer_consented:
        row.consented_by_sharer_user_id = uuid.uuid4()
        row.consented_by_sharer_at = _T1
    return row


# ---------------------------------------------------------------------------
# _is_dual_consented / _dual_consented_connected_family_ids
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_is_dual_consented_requires_both_columns() -> None:
    """Only a connection with both consent columns set is dual-consented."""
    viewer_fam, sharer_fam = uuid.uuid4(), uuid.uuid4()
    assert _is_dual_consented(_connection(viewer_fam, sharer_fam)) is False
    assert (
        _is_dual_consented(_connection(viewer_fam, sharer_fam, viewer_consented=True))
        is False
    )
    assert (
        _is_dual_consented(_connection(viewer_fam, sharer_fam, sharer_consented=True))
        is False
    )
    assert (
        _is_dual_consented(
            _connection(
                viewer_fam, sharer_fam, viewer_consented=True, sharer_consented=True
            )
        )
        is True
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_missing_sharer_consent_contributes_nothing() -> None:
    """#CRITICAL: viewer-only consent yields an EMPTY connected-family set."""
    my_family, other_family = uuid.uuid4(), uuid.uuid4()
    row = _connection(my_family, other_family, viewer_consented=True)
    session = _FakeSession(scalars_queue=[[row]])

    result = await _dual_consented_connected_family_ids(session, my_family)

    assert result == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_missing_viewer_consent_contributes_nothing() -> None:
    """#CRITICAL: sharer-only consent yields an EMPTY connected-family set."""
    my_family, other_family = uuid.uuid4(), uuid.uuid4()
    row = _connection(my_family, other_family, sharer_consented=True)
    session = _FakeSession(scalars_queue=[[row]])

    result = await _dual_consented_connected_family_ids(session, my_family)

    assert result == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dual_consented_connection_contributes_its_family() -> None:
    """A connection with both sides consented is returned."""
    my_family, other_family = uuid.uuid4(), uuid.uuid4()
    row = _connection(
        my_family, other_family, viewer_consented=True, sharer_consented=True
    )
    session = _FakeSession(scalars_queue=[[row]])

    result = await _dual_consented_connected_family_ids(session, my_family)

    assert result == {other_family}


# ---------------------------------------------------------------------------
# get_recommendations: authorization
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_malformed_profile_id_raises_validation_error() -> None:
    """A non-UUID profile_id is rejected before any query runs."""
    from cyo_adventure.core.exceptions import ValidationError

    principal = _child_principal(uuid.uuid4(), uuid.uuid4())
    session = _FakeSession()
    with pytest.raises(ValidationError):
        await get_recommendations("not-a-uuid", principal, session)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_child_cannot_read_another_profiles_recommendations() -> None:
    """A child token scoped to a different profile is rejected (403)."""
    family_id = uuid.uuid4()
    own_profile = uuid.uuid4()
    other_profile = uuid.uuid4()
    principal = _child_principal(family_id, own_profile)
    session = _FakeSession()
    with pytest.raises(AuthorizationError):
        await get_recommendations(str(other_profile), principal, session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_profile_raises_404() -> None:
    """A profile id that authorizes but does not exist in the DB is 404."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    principal = _child_principal(family_id, profile_id)
    session = _FakeSession(profile=None)
    with pytest.raises(ResourceNotFoundError):
        await get_recommendations(str(profile_id), principal, session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_bypasses_ownership_and_gets_empty_feed_for_isolated_profile() -> (
    None
):
    """An admin may read any profile; here it has no visible books, so []."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    principal = _admin_principal()
    session = _FakeSession(
        profile=_profile(profile_id, family_id), execute_rows=[]
    )
    result = await get_recommendations(str(profile_id), principal, session)
    assert result.items == []


# ---------------------------------------------------------------------------
# get_recommendations: ring logic
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_family_ring_recommendation_from_sibling_profile() -> None:
    """Ring 1: another profile's 4+ rating in the same family is recommended."""
    family_id = uuid.uuid4()
    me = uuid.uuid4()
    sibling = uuid.uuid4()
    storybook_id = "lantern"
    session = _FakeSession(
        profile=_profile(me, family_id),
        execute_rows=[(storybook_id, 3)],
        scalars_queue=[
            [_version(storybook_id, 3, title="The Lantern")],  # version_rows
            [sibling],  # ring-1 rater ids (other profiles in family)
            [],  # all outgoing connections (none)
            [_rating(sibling, storybook_id, 5)],  # rating_rows
            [_profile(sibling, family_id, display_name="Sibling")],  # rater_rows
        ],
    )
    principal = _guardian_principal(family_id, frozenset({me, sibling}))

    result = await get_recommendations(str(me), principal, session)

    assert len(result.items) == 1
    item = result.items[0]
    assert item.storybook_id == storybook_id
    assert item.title == "The Lantern"
    assert item.recommender_name == "Sibling"
    assert item.rating == 5
    assert item.ring == "family"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_ring_recommendation_only_when_dual_consented() -> None:
    """Ring 2: a cousin's rating surfaces once BOTH guardians have consented."""
    my_family = uuid.uuid4()
    cousin_family = uuid.uuid4()
    me = uuid.uuid4()
    cousin = uuid.uuid4()
    storybook_id = "catalog-book"
    connection = _connection(
        my_family, cousin_family, viewer_consented=True, sharer_consented=True
    )
    session = _FakeSession(
        profile=_profile(me, my_family),
        execute_rows=[(storybook_id, 1)],
        scalars_queue=[
            [_version(storybook_id, 1, title="Catalog Book")],  # version_rows
            [],  # ring-1 rater ids (no siblings)
            [connection],  # all outgoing connections
            [cousin],  # ring-2 rater ids (dual-consented family's profiles)
            [_rating(cousin, storybook_id, 4)],  # rating_rows
            [_profile(cousin, cousin_family, display_name="Cousin")],  # rater_rows
        ],
    )
    principal = _guardian_principal(my_family, frozenset({me}))

    result = await get_recommendations(str(me), principal, session)

    assert len(result.items) == 1
    item = result.items[0]
    assert item.recommender_name == "Cousin"
    assert item.ring == "connection"
    assert item.rating == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_missing_either_consent_yields_empty_feed() -> None:
    """#CRITICAL: a one-sided connection contributes ZERO recommendations."""
    my_family = uuid.uuid4()
    cousin_family = uuid.uuid4()
    me = uuid.uuid4()
    storybook_id = "catalog-book"
    connection = _connection(my_family, cousin_family, viewer_consented=True)
    session = _FakeSession(
        profile=_profile(me, my_family),
        execute_rows=[(storybook_id, 1)],
        scalars_queue=[
            [_version(storybook_id, 1, title="Catalog Book")],  # version_rows
            [],  # ring-1 rater ids
            [connection],  # all outgoing connections (one-sided)
            # No further queue entries: connected_family_ids resolves empty,
            # so ring-2 rater lookup is never issued, and rater_ids as a
            # whole is empty -> the handler returns before another query.
        ],
    )
    principal = _guardian_principal(my_family, frozenset({me}))

    result = await get_recommendations(str(me), principal, session)

    assert result.items == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_revoked_connection_removes_ring2_visibility_immediately() -> None:
    """Revocation (clearing one consent column) drops ring 2 on the next read."""
    my_family = uuid.uuid4()
    cousin_family = uuid.uuid4()
    me = uuid.uuid4()
    storybook_id = "catalog-book"
    # Simulates a connection the sharer just revoked: viewer side is still
    # set, sharer side has been cleared back to None.
    connection = _connection(my_family, cousin_family, viewer_consented=True)
    connection.consented_by_sharer_user_id = None
    connection.consented_by_sharer_at = None
    session = _FakeSession(
        profile=_profile(me, my_family),
        execute_rows=[(storybook_id, 1)],
        scalars_queue=[
            [_version(storybook_id, 1, title="Catalog Book")],
            [],
            [connection],
        ],
    )
    principal = _guardian_principal(my_family, frozenset({me}))

    result = await get_recommendations(str(me), principal, session)

    assert result.items == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_own_rating_excluded() -> None:
    """A profile's own 5-star rating never appears as its own recommendation."""
    family_id = uuid.uuid4()
    me = uuid.uuid4()
    storybook_id = "lantern"
    session = _FakeSession(
        profile=_profile(me, family_id),
        execute_rows=[(storybook_id, 1)],
        scalars_queue=[
            [_version(storybook_id, 1, title="The Lantern")],  # version_rows
            [],  # ring-1 rater ids: no other profiles in the family
            [],  # all outgoing connections
            # rater_ids ends up empty -> handler returns before further reads.
        ],
    )
    principal = _guardian_principal(family_id, frozenset({me}))

    result = await get_recommendations(str(me), principal, session)

    assert result.items == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_visible_books_yields_empty_feed_without_further_queries() -> None:
    """A profile with no visible (assigned+published) books gets []."""
    family_id = uuid.uuid4()
    me = uuid.uuid4()
    session = _FakeSession(profile=_profile(me, family_id), execute_rows=[])
    principal = _guardian_principal(family_id, frozenset({me}))

    result = await get_recommendations(str(me), principal, session)

    assert result.items == []
    assert session.scalars_calls == []
