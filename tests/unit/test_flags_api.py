"""Unit tests for the kid flag API handlers (K15; no DB, no ASGI stack).

Mirrors ``test_ratings_api_unit.py``: these call the route functions
directly with a fake session and a constructed principal, so the handler
bodies in ``api/flags.py`` stay covered even where the Docker-less
compatibility/unit matrix skips the testcontainers integration suite. They
lock in: ownership scoping (own profile, assigned book only), the
open-flag cap, the admin-only gates on the two admin routes, resolve's
idempotency guard, and that both KID_FLAGGED and FLAG_RESOLVED pipeline
events are recorded with their allowlisted (no-free-text) payloads.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.flags import (
    MAX_OPEN_FLAGS_PER_PROFILE,
    create_flag,
    list_open_flags,
    resolve_flag,
)
from cyo_adventure.api.schemas import KidFlagCreateBody, KidFlagResolveBody
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import ChildProfile, KidFlag, PipelineEvent
from cyo_adventure.events import EventType

_FIXED_TS = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeScalars:
    """Stand-in for the iterable returned by ``session.scalars``."""

    def __init__(self, values: list[KidFlag]) -> None:
        self._values = values

    def all(self) -> list[KidFlag]:
        """Return the seeded KidFlag rows."""
        return self._values


class _FakeSession:
    """Minimal async session double for the flags API handlers.

    ``scalar`` is called at most twice per ``create_flag`` invocation, always
    in the same order: the storybook-assignment check first, then the
    open-flag count. Each fake session backs exactly one handler call in
    these tests, so a call-index dispatch is unambiguous and mirrors the
    established fake-session pattern in this test suite (see
    ``test_ratings_api_unit.py``).
    """

    def __init__(
        self,
        *,
        profile: ChildProfile | None = None,
        flag: KidFlag | None = None,
        assigned: bool = True,
        open_count: int = 0,
        list_rows: list[KidFlag] | None = None,
    ) -> None:
        self._profile = profile
        self._flag = flag
        self._assigned = assigned
        self._open_count = open_count
        self._list_rows = list_rows or []
        self.added: list[object] = []
        self.flush_count = 0
        self.get_calls: list[tuple[type[object], object]] = []
        self.scalar_calls: list[object] = []

    async def get(self, model: type[object], key: object) -> object | None:
        """Return the seeded ChildProfile or KidFlag by model type."""
        self.get_calls.append((model, key))
        if model is ChildProfile:
            return self._profile
        if model is KidFlag:
            return self._flag
        return None

    async def scalar(self, statement: object) -> object | None:
        """Return the assignment check result, then the open-flag count."""
        self.scalar_calls.append(statement)
        if len(self.scalar_calls) == 1:
            return "book-1" if self._assigned else None
        return self._open_count

    async def scalars(self, statement: object) -> _FakeScalars:
        """Return the seeded flag rows for the admin list endpoint."""
        return _FakeScalars(self._list_rows)

    def add(self, obj: object) -> None:
        """Record an added ORM instance."""
        self.added.append(obj)

    async def flush(self) -> None:
        """Count flushes (no-op persistence)."""
        self.flush_count += 1


def _child(family_id: uuid.UUID, profile_id: uuid.UUID) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="child",
        family_id=family_id,
        profile_ids=frozenset({profile_id}),
    )


def _guardian(family_id: uuid.UUID, profile_ids: set[uuid.UUID]) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=family_id,
        profile_ids=frozenset(profile_ids),
    )


def _admin(family_id: uuid.UUID) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="admin",
        family_id=family_id,
        profile_ids=frozenset(),
    )


def _device(family_id: uuid.UUID) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="device",
        family_id=family_id,
        profile_ids=frozenset(),
    )


# ---------------------------------------------------------------------------
# POST /flags
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_flag_inserts_new_and_records_event() -> None:
    """A child flags their own profile's assigned book; a KID_FLAGGED event fires."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    profile = ChildProfile(
        id=profile_id, family_id=family_id, display_name="Kid", age_band="8-11"
    )
    session = _FakeSession(profile=profile, assigned=True, open_count=0)
    ctx = RequestContext(principal=_child(family_id, profile_id), session=session)

    view = await create_flag(
        KidFlagCreateBody(
            profile_id=str(profile_id),
            storybook_id="book-1",
            version=1,
            reason="scared_me",
            node_id="node-3",
        ),
        ctx,
    )

    assert view.reason == "scared_me"
    added_flags = [obj for obj in session.added if isinstance(obj, KidFlag)]
    assert len(added_flags) == 1
    assert added_flags[0].profile_id == profile_id
    assert added_flags[0].storybook_id == "book-1"
    assert added_flags[0].node_id == "node-3"
    assert added_flags[0].family_id == family_id
    # No free text anywhere on the stored row (ADR-016 / K15).
    assert added_flags[0].reason == "scared_me"

    added_events = [obj for obj in session.added if isinstance(obj, PipelineEvent)]
    assert len(added_events) == 1
    assert added_events[0].event_type == str(EventType.KID_FLAGGED)
    assert added_events[0].payload == {"reason": "scared_me", "storybook_id": "book-1"}
    assert session.flush_count >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_flag_wrong_profile_raises_authorization() -> None:
    """A profile the principal cannot access raises AuthorizationError (-> 403)."""
    family_id = uuid.uuid4()
    session = _FakeSession()
    # The principal may act on a different profile than the one in the body.
    ctx = RequestContext(principal=_child(family_id, uuid.uuid4()), session=session)

    with pytest.raises(AuthorizationError):
        await create_flag(
            KidFlagCreateBody(
                profile_id=str(uuid.uuid4()),
                storybook_id="book-1",
                version=1,
                reason="confusing",
            ),
            ctx,
        )
    assert session.added == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_flag_unassigned_book_raises_authorization() -> None:
    """A storybook not assigned to the profile raises AuthorizationError (-> 403)."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    profile = ChildProfile(
        id=profile_id, family_id=family_id, display_name="Kid", age_band="8-11"
    )
    session = _FakeSession(profile=profile, assigned=False)
    ctx = RequestContext(principal=_child(family_id, profile_id), session=session)

    with pytest.raises(AuthorizationError):
        await create_flag(
            KidFlagCreateBody(
                profile_id=str(profile_id),
                storybook_id="unassigned-book",
                version=1,
                reason="did_not_like",
            ),
            ctx,
        )
    assert session.added == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_flag_missing_profile_raises_not_found() -> None:
    """A profile that no longer exists raises ResourceNotFoundError (-> 404)."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    session = _FakeSession(profile=None)
    ctx = RequestContext(principal=_child(family_id, profile_id), session=session)

    with pytest.raises(ResourceNotFoundError):
        await create_flag(
            KidFlagCreateBody(
                profile_id=str(profile_id),
                storybook_id="book-1",
                version=1,
                reason="did_not_like",
            ),
            ctx,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_flag_cap_returns_state_transition_error() -> None:
    """A profile already at the open-flag cap raises StateTransitionError (-> 409)."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    profile = ChildProfile(
        id=profile_id, family_id=family_id, display_name="Kid", age_band="8-11"
    )
    session = _FakeSession(
        profile=profile, assigned=True, open_count=MAX_OPEN_FLAGS_PER_PROFILE
    )
    ctx = RequestContext(principal=_child(family_id, profile_id), session=session)

    with pytest.raises(StateTransitionError):
        await create_flag(
            KidFlagCreateBody(
                profile_id=str(profile_id),
                storybook_id="book-1",
                version=1,
                reason="did_not_like",
            ),
            ctx,
        )
    assert session.added == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_flag_guardian_may_flag_owned_profile() -> None:
    """A guardian may also submit a flag on behalf of an owned profile."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    profile = ChildProfile(
        id=profile_id, family_id=family_id, display_name="Kid", age_band="8-11"
    )
    session = _FakeSession(profile=profile, assigned=True, open_count=0)
    ctx = RequestContext(principal=_guardian(family_id, {profile_id}), session=session)

    view = await create_flag(
        KidFlagCreateBody(
            profile_id=str(profile_id),
            storybook_id="book-1",
            version=1,
            reason="confusing",
        ),
        ctx,
    )
    assert view.reason == "confusing"


# ---------------------------------------------------------------------------
# GET /admin/flags
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_open_flags_admin_returns_views() -> None:
    """An admin sees the open flags, mapped to KidFlagView rows."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    row = KidFlag(
        id=uuid.uuid4(),
        family_id=family_id,
        profile_id=profile_id,
        storybook_id="book-1",
        version=1,
        reason="scared_me",
        node_id=None,
        created_at=_FIXED_TS,
        resolved_by=None,
        resolved_at=None,
        resolution=None,
    )
    session = _FakeSession(list_rows=[row])
    ctx = RequestContext(principal=_admin(family_id), session=session)

    result = await list_open_flags(ctx)

    assert len(result.flags) == 1
    assert result.flags[0].reason == "scared_me"
    assert result.flags[0].resolved_at is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_open_flags_guardian_raises_authorization() -> None:
    """A guardian (no admin capability) is rejected on the admin queue (-> 403)."""
    family_id = uuid.uuid4()
    session = _FakeSession()
    ctx = RequestContext(principal=_guardian(family_id, set()), session=session)

    with pytest.raises(AuthorizationError):
        await list_open_flags(ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_open_flags_device_raises_authorization() -> None:
    """A device grant token is rejected on the admin queue (-> 403)."""
    family_id = uuid.uuid4()
    session = _FakeSession()
    ctx = RequestContext(principal=_device(family_id), session=session)

    with pytest.raises(AuthorizationError):
        await list_open_flags(ctx)


# ---------------------------------------------------------------------------
# POST /admin/flags/{id}/resolve
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_flag_admin_success_records_event() -> None:
    """An admin resolves an open flag; a FLAG_RESOLVED event fires."""
    family_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    flag_id = uuid.uuid4()
    flag = KidFlag(
        id=flag_id,
        family_id=family_id,
        profile_id=profile_id,
        storybook_id="book-1",
        version=1,
        reason="scared_me",
        node_id=None,
        created_at=_FIXED_TS,
        resolved_by=None,
        resolved_at=None,
        resolution=None,
    )
    session = _FakeSession(flag=flag)
    admin = _admin(family_id)
    ctx = RequestContext(principal=admin, session=session)

    view = await resolve_flag(
        str(flag_id), KidFlagResolveBody(resolution="archived_book"), ctx
    )

    assert view.resolution == "archived_book"
    assert view.resolved_by == str(admin.user_id)
    assert view.resolved_at is not None
    assert flag.resolved_by == admin.user_id
    assert flag.resolution == "archived_book"

    added_events = [obj for obj in session.added if isinstance(obj, PipelineEvent)]
    assert len(added_events) == 1
    assert added_events[0].event_type == str(EventType.FLAG_RESOLVED)
    assert added_events[0].payload == {"resolution": "archived_book"}
    assert added_events[0].actor_role == "admin"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_flag_guardian_raises_authorization() -> None:
    """A guardian (no admin capability) may not resolve a flag (-> 403)."""
    family_id = uuid.uuid4()
    session = _FakeSession()
    ctx = RequestContext(principal=_guardian(family_id, set()), session=session)

    with pytest.raises(AuthorizationError):
        await resolve_flag(
            str(uuid.uuid4()), KidFlagResolveBody(resolution="dismissed"), ctx
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_flag_device_raises_authorization() -> None:
    """A device grant token may not resolve a flag (-> 403)."""
    family_id = uuid.uuid4()
    session = _FakeSession()
    ctx = RequestContext(principal=_device(family_id), session=session)

    with pytest.raises(AuthorizationError):
        await resolve_flag(
            str(uuid.uuid4()), KidFlagResolveBody(resolution="dismissed"), ctx
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_flag_not_found_raises() -> None:
    """A missing flag id raises ResourceNotFoundError (-> 404)."""
    family_id = uuid.uuid4()
    session = _FakeSession(flag=None)
    ctx = RequestContext(principal=_admin(family_id), session=session)

    with pytest.raises(ResourceNotFoundError):
        await resolve_flag(
            str(uuid.uuid4()), KidFlagResolveBody(resolution="dismissed"), ctx
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_flag_already_resolved_raises_state_transition() -> None:
    """Resolving an already-resolved flag raises StateTransitionError (-> 409)."""
    family_id = uuid.uuid4()
    flag = KidFlag(
        id=uuid.uuid4(),
        family_id=family_id,
        profile_id=uuid.uuid4(),
        storybook_id="book-1",
        version=1,
        reason="scared_me",
        node_id=None,
        created_at=_FIXED_TS,
        resolved_by=uuid.uuid4(),
        resolved_at=_FIXED_TS,
        resolution="noted",
    )
    session = _FakeSession(flag=flag)
    ctx = RequestContext(principal=_admin(family_id), session=session)

    with pytest.raises(StateTransitionError):
        await resolve_flag(
            str(flag.id), KidFlagResolveBody(resolution="dismissed"), ctx
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_flag_invalid_uuid_raises_validation() -> None:
    """A non-UUID flag_id raises ValidationError (-> 422)."""
    family_id = uuid.uuid4()
    session = _FakeSession()
    ctx = RequestContext(principal=_admin(family_id), session=session)

    with pytest.raises(ValidationError):
        await resolve_flag(
            "not-a-uuid", KidFlagResolveBody(resolution="dismissed"), ctx
        )
