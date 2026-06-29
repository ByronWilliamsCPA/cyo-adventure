"""Unit tests for the auth seam and the session unit-of-work in api.deps."""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.api import deps
from cyo_adventure.api.deps import Principal
from cyo_adventure.core.exceptions import AuthenticationError


class _FakeSession:
    """A minimal async session double recording lifecycle calls."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


class _FakeScalarsResult:
    """Minimal scalars() result double with .all() support."""

    def __init__(self, items: list[object]) -> None:
        self._items = items

    def all(self) -> list[object]:
        return self._items


class _FakeDepSession:
    """Session double for require_principal and _resolve_profiles tests.

    scalar() returns a pre-seeded value (None or a User-like object).
    scalars() returns a _FakeScalarsResult whose .all() yields the seeded items.
    """

    def __init__(
        self,
        *,
        scalar_return: object | None = None,
        scalars_items: list[object] | None = None,
    ) -> None:
        self._scalar_return = scalar_return
        self._scalars_items: list[object] = scalars_items or []

    async def scalar(self, stmt: object) -> object | None:
        return self._scalar_return

    async def scalars(self, stmt: object) -> _FakeScalarsResult:
        return _FakeScalarsResult(self._scalars_items)


def _principal(role: str, profiles: frozenset[uuid.UUID]) -> Principal:
    """Build a Principal for tests."""
    return Principal(
        subject="s",
        user_id=uuid.uuid4(),
        role=role,
        family_id=uuid.uuid4(),
        profile_ids=profiles,
    )


@pytest.mark.unit
def test_is_guardian_true_and_false() -> None:
    """The is_guardian property reflects the role."""
    assert _principal("guardian", frozenset()).is_guardian is True
    assert _principal("child", frozenset()).is_guardian is False


@pytest.mark.unit
def test_can_access_profile() -> None:
    """A principal can access only profiles in its set."""
    pid = uuid.uuid4()
    principal = _principal("child", frozenset({pid}))
    assert principal.can_access_profile(pid) is True
    assert principal.can_access_profile(uuid.uuid4()) is False


@pytest.mark.unit
def test_extract_subject_valid() -> None:
    """A well-formed bearer header yields the token."""
    assert deps._extract_subject("Bearer abc123") == "abc123"


@pytest.mark.unit
@pytest.mark.parametrize("header", [None, "Token abc", "Bearer ", "Bearer    "])
def test_extract_subject_rejects_bad_headers(header: str | None) -> None:
    """Missing, non-bearer, or empty tokens raise an authentication error."""
    with pytest.raises(AuthenticationError):
        deps._extract_subject(header)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_db_session_commits_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unit-of-work commits and closes when the request body succeeds."""
    fake = _FakeSession()
    monkeypatch.setattr(deps, "get_session", lambda: fake)
    agen = deps.get_db_session()
    session = await agen.__anext__()
    assert session is fake
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
    assert fake.committed
    assert fake.closed
    assert not fake.rolled_back


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_db_session_rolls_back_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unit-of-work rolls back and closes when the request body raises."""
    fake = _FakeSession()
    monkeypatch.setattr(deps, "get_session", lambda: fake)
    agen = deps.get_db_session()
    await agen.__anext__()
    with pytest.raises(ValueError, match="boom"):
        await agen.athrow(ValueError("boom"))
    assert fake.rolled_back
    assert fake.closed
    assert not fake.committed


# ---------------------------------------------------------------------------
# _resolve_profiles
# ---------------------------------------------------------------------------


class TestResolveProfiles:
    """Direct tests for the _resolve_profiles private helper."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_guardian_returns_all_family_profiles(self) -> None:
        """A guardian user gets a frozenset of every child profile in the family."""
        from cyo_adventure.api.deps import _resolve_profiles
        from cyo_adventure.db.models import User

        family_id = uuid.uuid4()
        p1 = uuid.uuid4()
        p2 = uuid.uuid4()
        user = User(
            id=uuid.uuid4(),
            family_id=family_id,
            role="guardian",
            authn_subject="sub",
        )
        session = _FakeDepSession(scalars_items=[p1, p2])
        result = await _resolve_profiles(session, user)  # pyright: ignore[arg-type]
        assert result == frozenset({p1, p2})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_with_assigned_profile_returns_singleton(self) -> None:
        """A child user with child_profile_id set returns that single profile."""
        from cyo_adventure.api.deps import _resolve_profiles
        from cyo_adventure.db.models import User

        profile_id = uuid.uuid4()
        user = User(
            id=uuid.uuid4(),
            family_id=uuid.uuid4(),
            role="child",
            authn_subject="sub",
            child_profile_id=profile_id,
        )
        session = _FakeDepSession()
        result = await _resolve_profiles(session, user)  # pyright: ignore[arg-type]
        assert result == frozenset({profile_id})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_without_profile_returns_empty_frozenset(self) -> None:
        """A child user with no assigned profile gets an empty frozenset."""
        from cyo_adventure.api.deps import _resolve_profiles
        from cyo_adventure.db.models import User

        user = User(
            id=uuid.uuid4(),
            family_id=uuid.uuid4(),
            role="child",
            authn_subject="sub",
            child_profile_id=None,
        )
        session = _FakeDepSession()
        result = await _resolve_profiles(session, user)  # pyright: ignore[arg-type]
        assert result == frozenset()


# ---------------------------------------------------------------------------
# require_principal
# ---------------------------------------------------------------------------


class TestRequirePrincipal:
    """Tests for the require_principal dependency function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unknown_subject_raises_authentication_error(self) -> None:
        """When no User row matches the subject, AuthenticationError is raised."""
        session = _FakeDepSession(scalar_return=None)
        with pytest.raises(AuthenticationError, match="unknown subject"):
            await deps.require_principal(
                session,  # pyright: ignore[arg-type]
                authorization="Bearer unknown-subject",
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_happy_path_returns_correct_principal(self) -> None:
        """A valid bearer token resolves to a Principal with the user's attributes."""
        from cyo_adventure.db.models import User

        family_id = uuid.uuid4()
        user_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        user = User(
            id=user_id,
            family_id=family_id,
            role="child",
            authn_subject="my-token",
            child_profile_id=profile_id,
        )
        session = _FakeDepSession(scalar_return=user)
        result = await deps.require_principal(
            session,  # pyright: ignore[arg-type]
            authorization="Bearer my-token",
        )
        assert result.subject == "my-token"
        assert result.user_id == user_id
        assert result.role == "child"
        assert result.family_id == family_id
        assert result.profile_ids == frozenset({profile_id})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_guardian_principal_has_all_family_profiles(self) -> None:
        """A guardian's principal includes all child profiles returned by _resolve_profiles."""
        from cyo_adventure.db.models import User

        family_id = uuid.uuid4()
        p1 = uuid.uuid4()
        p2 = uuid.uuid4()
        user = User(
            id=uuid.uuid4(),
            family_id=family_id,
            role="guardian",
            authn_subject="g-token",
        )
        session = _FakeDepSession(scalar_return=user, scalars_items=[p1, p2])
        result = await deps.require_principal(
            session,  # pyright: ignore[arg-type]
            authorization="Bearer g-token",
        )
        assert result.role == "guardian"
        assert result.profile_ids == frozenset({p1, p2})


# ---------------------------------------------------------------------------
# get_context
# ---------------------------------------------------------------------------


class TestGetContext:
    """Tests for the get_context dependency factory."""

    @pytest.mark.unit
    def test_get_context_bundles_principal_and_session(self) -> None:
        """get_context returns a RequestContext containing both arguments."""
        from cyo_adventure.api.deps import RequestContext, get_context

        principal = _principal("guardian", frozenset())
        fake_session = _FakeDepSession()
        ctx = get_context(principal, fake_session)  # pyright: ignore[arg-type]
        assert isinstance(ctx, RequestContext)
        assert ctx.principal is principal
        assert ctx.session is fake_session
