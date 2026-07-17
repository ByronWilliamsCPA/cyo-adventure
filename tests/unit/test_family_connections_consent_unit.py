"""Unit tests for the guardian consent endpoints (ADR-016, register G17).

Calls the route functions directly with a fake session and a constructed
principal, mirroring ``test_reading_history_api_unit.py`` and
``test_ratings_api_unit.py``. Covers: the guardian-only gate (admin rejected
too, register A15), the viewer/sharer side resolution and its 403 for an
unrelated family, the consent-granted and consent-revoked mutations, and the
active-only-with-both-sides rule (``_is_active``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.family_connections import (
    _is_active,
    _resolve_side,
    consent_family_connection,
    list_my_family_connections,
    revoke_family_connection_consent,
)
from cyo_adventure.core.exceptions import AuthorizationError, ResourceNotFoundError
from cyo_adventure.db.models import Family, FamilyConnection

_T1 = datetime(2026, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fake session
# ---------------------------------------------------------------------------


class _FakeScalars:
    """Returned by session.scalars() -- supports direct iteration."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def __iter__(self) -> object:
        return iter(self._rows)


class _FakeSession:
    """Minimal async session double for the consent route handlers."""

    def __init__(
        self,
        *,
        connections: dict[uuid.UUID, FamilyConnection] | None = None,
        families: dict[uuid.UUID, Family] | None = None,
        list_rows: list[FamilyConnection] | None = None,
    ) -> None:
        self._connections = connections or {}
        self._families = families or {}
        self._list_rows = list_rows or []
        self.flush_count = 0
        self.added: list[object] = []

    async def get(self, model: type[object], key: object) -> object | None:
        if model is FamilyConnection:
            return self._connections.get(key)
        if model is Family:
            return self._families.get(key)
        return None

    async def scalars(self, _stmt: object) -> _FakeScalars:
        return _FakeScalars(self._list_rows)

    async def flush(self) -> None:
        self.flush_count += 1

    def add(self, obj: object) -> None:
        """Record the appended PipelineEvent row (record_event's write)."""
        self.added.append(obj)


def _principal(
    family_id: uuid.UUID, *, role: str = "guardian", is_admin: bool = False
) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role=role,
        family_id=family_id,
        profile_ids=frozenset(),
        is_admin=is_admin,
    )


def _connection(
    viewer_family_id: uuid.UUID,
    sharer_family_id: uuid.UUID,
    *,
    connection_id: uuid.UUID | None = None,
    viewer_consented: bool = False,
    sharer_consented: bool = False,
    viewer_user_id: uuid.UUID | None = None,
    sharer_user_id: uuid.UUID | None = None,
) -> FamilyConnection:
    row = FamilyConnection(
        id=connection_id or uuid.uuid4(),
        family_id=viewer_family_id,
        connected_family_id=sharer_family_id,
    )
    row.created_at = _T1
    if viewer_consented:
        row.consented_by_viewer_user_id = viewer_user_id or uuid.uuid4()
        row.consented_by_viewer_at = _T1
    if sharer_consented:
        row.consented_by_sharer_user_id = sharer_user_id or uuid.uuid4()
        row.consented_by_sharer_at = _T1
    return row


# ---------------------------------------------------------------------------
# _is_active
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_is_active_requires_both_sides() -> None:
    """Neither, one, or both consent columns set: only both is active."""
    viewer_fam, sharer_fam = uuid.uuid4(), uuid.uuid4()
    neither = _connection(viewer_fam, sharer_fam)
    viewer_only = _connection(viewer_fam, sharer_fam, viewer_consented=True)
    sharer_only = _connection(viewer_fam, sharer_fam, sharer_consented=True)
    both = _connection(
        viewer_fam, sharer_fam, viewer_consented=True, sharer_consented=True
    )

    assert _is_active(neither) is False
    assert _is_active(viewer_only) is False
    assert _is_active(sharer_only) is False
    assert _is_active(both) is True


@pytest.mark.unit
def test_is_active_false_after_one_side_clears() -> None:
    """Revoking either side (setting its consent back to None) deactivates."""
    viewer_fam, sharer_fam = uuid.uuid4(), uuid.uuid4()
    row = _connection(
        viewer_fam, sharer_fam, viewer_consented=True, sharer_consented=True
    )
    assert _is_active(row) is True

    row.consented_by_viewer_user_id = None
    row.consented_by_viewer_at = None
    assert _is_active(row) is False


# ---------------------------------------------------------------------------
# _resolve_side
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_side_viewer_and_sharer() -> None:
    """The caller's family on either side resolves to the matching side."""
    viewer_fam, sharer_fam = uuid.uuid4(), uuid.uuid4()
    row = _connection(viewer_fam, sharer_fam)
    assert _resolve_side(row, viewer_fam) == "viewer"
    assert _resolve_side(row, sharer_fam) == "sharer"


@pytest.mark.unit
def test_resolve_side_unrelated_family_raises_403() -> None:
    """A family on neither side of the connection is rejected."""
    viewer_fam, sharer_fam, stranger_fam = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    row = _connection(viewer_fam, sharer_fam)
    with pytest.raises(AuthorizationError):
        _resolve_side(row, stranger_fam)


# ---------------------------------------------------------------------------
# list_my_family_connections
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_only_principal_is_rejected_from_consent() -> None:
    """An admin-only (non-guardian) principal cannot list, consent, or revoke."""
    principal = _principal(uuid.uuid4(), role="admin", is_admin=True)
    ctx = RequestContext(principal=principal, session=_FakeSession())
    with pytest.raises(AuthorizationError):
        await list_my_family_connections(ctx)
    with pytest.raises(AuthorizationError):
        await consent_family_connection(str(uuid.uuid4()), ctx)
    with pytest.raises(AuthorizationError):
        await revoke_family_connection_consent(str(uuid.uuid4()), ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mine_lists_both_directions_with_counterpart_and_consent_state() -> None:
    """A guardian sees rows where their family is either the viewer or sharer."""
    my_family = uuid.uuid4()
    other_family = uuid.uuid4()
    as_viewer = _connection(my_family, other_family, viewer_consented=True)
    as_sharer = _connection(other_family, my_family, sharer_consented=True)
    families = {
        other_family: Family(id=other_family, name="Smith Family"),
        my_family: Family(id=my_family, name="My Family"),
    }
    session = _FakeSession(families=families, list_rows=[as_viewer, as_sharer])
    principal = _principal(my_family)
    ctx = RequestContext(principal=principal, session=session)

    result = await list_my_family_connections(ctx)

    assert {item.id for item in result.connections} == {
        str(as_viewer.id),
        str(as_sharer.id),
    }
    viewer_item = next(i for i in result.connections if i.id == str(as_viewer.id))
    assert viewer_item.direction == "viewer"
    assert viewer_item.counterpart_family_name == "Smith Family"
    assert viewer_item.my_consent is True
    assert viewer_item.active is False  # only the viewer side has consented

    sharer_item = next(i for i in result.connections if i.id == str(as_sharer.id))
    assert sharer_item.direction == "sharer"
    assert sharer_item.counterpart_family_name == "Smith Family"
    assert sharer_item.my_consent is True
    assert sharer_item.active is False


# ---------------------------------------------------------------------------
# consent_family_connection / revoke_family_connection_consent
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_consent_as_viewer_sets_viewer_columns_and_stamps_user() -> None:
    """A viewer-side guardian's consent sets only the viewer consent pair."""
    my_family, other_family = uuid.uuid4(), uuid.uuid4()
    row = _connection(my_family, other_family)
    other = Family(id=other_family, name="Smith Family")
    session = _FakeSession(connections={row.id: row}, families={other_family: other})
    principal = _principal(my_family)
    ctx = RequestContext(principal=principal, session=session)

    result = await consent_family_connection(str(row.id), ctx)

    assert row.consented_by_viewer_user_id == principal.user_id
    assert row.consented_by_viewer_at is not None
    assert row.consented_by_sharer_user_id is None
    assert result.my_consent is True
    assert result.active is False
    # One explicit flush after the mutation, one more inside record_event.
    assert session.flush_count == 2
    assert len(session.added) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_consent_from_both_sides_makes_connection_active() -> None:
    """Once both sides have consented, the connection reports active=True."""
    viewer_family, sharer_family = uuid.uuid4(), uuid.uuid4()
    row = _connection(viewer_family, sharer_family, viewer_consented=True)
    families = {
        sharer_family: Family(id=sharer_family, name="Sharer Family"),
        viewer_family: Family(id=viewer_family, name="Viewer Family"),
    }
    session = _FakeSession(connections={row.id: row}, families=families)
    sharer_principal = _principal(sharer_family)
    ctx = RequestContext(principal=sharer_principal, session=session)

    result = await consent_family_connection(str(row.id), ctx)

    assert row.consented_by_sharer_user_id == sharer_principal.user_id
    assert result.active is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_revoke_clears_the_callers_side_and_deactivates_immediately() -> None:
    """Revoking one side clears only that side and flips active to False."""
    viewer_family, sharer_family = uuid.uuid4(), uuid.uuid4()
    row = _connection(
        viewer_family, sharer_family, viewer_consented=True, sharer_consented=True
    )
    assert _is_active(row) is True
    families = {sharer_family: Family(id=sharer_family, name="Sharer Family")}
    session = _FakeSession(connections={row.id: row}, families=families)
    viewer_principal = _principal(viewer_family)
    ctx = RequestContext(principal=viewer_principal, session=session)

    result = await revoke_family_connection_consent(str(row.id), ctx)

    assert row.consented_by_viewer_user_id is None
    assert row.consented_by_viewer_at is None
    assert row.consented_by_sharer_user_id is not None  # untouched
    assert result.my_consent is False
    assert result.active is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unrelated_family_gets_403_on_consent() -> None:
    """A guardian whose family is on neither side gets 403, not a mutation."""
    viewer_family, sharer_family, stranger_family = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    row = _connection(viewer_family, sharer_family)
    session = _FakeSession(connections={row.id: row})
    stranger_principal = _principal(stranger_family)
    ctx = RequestContext(principal=stranger_principal, session=session)

    with pytest.raises(AuthorizationError):
        await consent_family_connection(str(row.id), ctx)
    with pytest.raises(AuthorizationError):
        await revoke_family_connection_consent(str(row.id), ctx)
    # No mutation happened on either failed attempt.
    assert row.consented_by_viewer_user_id is None
    assert row.consented_by_sharer_user_id is None
    assert session.flush_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_consent_on_missing_connection_raises_404() -> None:
    """An unknown connection id is a 404, not a 403 or silent no-op."""
    principal = _principal(uuid.uuid4())
    session = _FakeSession()
    ctx = RequestContext(principal=principal, session=session)

    with pytest.raises(ResourceNotFoundError):
        await consent_family_connection(str(uuid.uuid4()), ctx)
    with pytest.raises(ResourceNotFoundError):
        await revoke_family_connection_consent(str(uuid.uuid4()), ctx)
