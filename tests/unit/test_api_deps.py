"""Unit tests for the auth seam and the session unit-of-work in api.deps."""

from __future__ import annotations

import importlib
import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import jwt
import pytest

from cyo_adventure.api import deps
from cyo_adventure.api.deps import Principal
from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import AuthenticationError

if TYPE_CHECKING:
    from collections.abc import Iterator


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

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_admin_only_returns_empty_frozenset(self) -> None:
        """An admin-only user (not a guardian) gets an empty frozenset.

        Mirrors the docstring's "empty for an admin-only adult" case: the
        admin base role skips the guardian branch entirely, and an admin row
        carries no ``child_profile_id``, so the child branch also falls
        through to the empty-set default.
        """
        from cyo_adventure.api.deps import _resolve_profiles
        from cyo_adventure.db.models import User

        user = User(
            id=uuid.uuid4(),
            family_id=uuid.uuid4(),
            role="admin",
            is_admin=True,
            authn_subject="sub",
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

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dual_role_user_resolves_guardian_principal_with_admin(
        self,
    ) -> None:
        """A (role=guardian, is_admin=True) row yields a dual-capability principal.

        The guardian base role still resolves the family profile set, and the
        stored flag carries the admin capability onto the same principal.
        """
        from cyo_adventure.db.models import User

        p1 = uuid.uuid4()
        user = User(
            id=uuid.uuid4(),
            family_id=uuid.uuid4(),
            role="guardian",
            is_admin=True,
            authn_subject="dual-token",
        )
        session = _FakeDepSession(scalar_return=user, scalars_items=[p1])
        result = await deps.require_principal(
            session,  # pyright: ignore[arg-type]
            authorization="Bearer dual-token",
        )
        assert result.is_guardian is True
        assert result.is_admin is True
        assert result.profile_ids == frozenset({p1})


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


# ---------------------------------------------------------------------------
# Auth-stub environment guard
# ---------------------------------------------------------------------------


class TestAuthStubGuard:
    """Tests for the module-level environment guard in api.deps."""

    @pytest.fixture(autouse=True)
    def _restore_deps_namespace(self) -> Iterator[None]:
        """Snapshot and restore ``deps``'s module namespace around each test.

        These guard tests exercise import-time behavior via
        ``importlib.reload(deps)``, which rebinds every callable in the module
        (``get_db_session``, ``require_principal``, ...) to a brand-new object.
        The singleton ``app`` and the integration DB-session override
        (``app.dependency_overrides[get_db_session]``) captured the ORIGINAL
        callables at import, so a plain reload leaves the shared module graph
        desynced. A later DB-backed integration test (``tests/integration/
        test_me.py``) then bypasses the session override and connects to the
        real dev database, failing with an auth error. Because pytest-randomly
        shuffles execution order, that failure is an order-dependent flake
        rather than a deterministic one. Restoring the exact original namespace
        keeps ``deps`` byte-identical after each test so the override always
        matches.
        """
        original = deps.__dict__.copy()
        try:
            yield
        finally:
            importlib.reload(deps)
            deps.__dict__.update(original)

    @pytest.mark.unit
    def test_guard_raises_when_non_local_and_no_oidc_config(self) -> None:
        """deps raises ConfigurationError when environment != 'local' and no
        OIDC issuer/JWKS is configured to take over from the dev stub.

        The guard is the sole enforcement point preventing the no-validation dev
        auth stub from reaching staging or production unconfigured. Tested via
        importlib.reload which re-executes module-level code.
        """
        from cyo_adventure.core.exceptions import ConfigurationError

        # spec=list(Settings.model_fields) (field names, not an instance):
        # passing a Settings() instance as spec makes mock walk dir(spec)
        # with real getattr on Python <= 3.12, which touches pydantic's
        # deprecated `__fields__` instance property and raises
        # PydanticDeprecatedSince20 under this project's
        # filterwarnings = ["error"] (3.13+ mock uses inspect.getattr_static
        # and skips properties). A name-list spec gives the same protection
        # mock specs actually provide, reads of unknown attributes fail
        # loudly while attribute sets are never spec-checked in any form,
        # without ever touching the instance. A cleaner
        # monkeypatch.setenv(...) + single reload was evaluated instead of
        # this double-reload/patched-singleton pattern; it does not work
        # cleanly here because deps.py binds `settings` by value at import
        # time (`from cyo_adventure.core.config import settings`), so
        # reloading only `deps` would keep the OLD Settings instance. Getting
        # a genuinely new instance requires reloading `core.config` too,
        # which reruns Settings' own model_validator (the non-local +
        # dev-database-url guard in config.py) and would need an unrelated
        # DATABASE_URL override just to avoid tripping that guard: out of
        # scope for this auth-stub guard test. Keeping the patched-singleton
        # pattern, now spec'd, per the documented deferral for this case.
        with patch(
            "cyo_adventure.core.config.settings", spec=list(Settings.model_fields)
        ) as mock_settings:
            mock_settings.environment = "production"
            mock_settings.oidc_issuer = None
            mock_settings.oidc_jwks_url = None
            with pytest.raises(ConfigurationError, match="dev auth stub"):
                importlib.reload(deps)

        # Restore the module to a working local state so subsequent tests pass.
        importlib.reload(deps)

    @pytest.mark.unit
    def test_guard_does_not_raise_in_local_env(self) -> None:
        """deps imports cleanly when environment == 'local' (the default)."""
        from cyo_adventure.core.exceptions import ConfigurationError

        # See test_guard_raises_when_non_local_and_no_oidc_config above for why
        # this stays a patched-singleton (now spec'd) instead of an env-var reload.
        with patch(
            "cyo_adventure.core.config.settings", spec=list(Settings.model_fields)
        ) as mock_settings:
            mock_settings.environment = "local"
            try:
                importlib.reload(deps)
            except ConfigurationError:
                pytest.fail(
                    "ConfigurationError raised unexpectedly for environment='local'"
                )

        importlib.reload(deps)

    @pytest.mark.unit
    def test_guard_does_not_raise_when_non_local_with_oidc_config(self) -> None:
        """deps imports cleanly outside 'local' once real OIDC config is set.

        This is the case the dev-stub guard exists to allow: a non-local
        deployment is legitimate once _verify_oidc_jwt has something to verify
        against, so the guard must not block it. A ConfigurationError here would
        fail the test naturally.
        """
        # See test_guard_raises_when_non_local_and_no_oidc_config above for why
        # this stays a patched-singleton (now spec'd) instead of an env-var reload.
        with patch(
            "cyo_adventure.core.config.settings", spec=list(Settings.model_fields)
        ) as mock_settings:
            mock_settings.environment = "staging"
            mock_settings.oidc_issuer = "https://example.supabase.co/auth/v1"
            mock_settings.oidc_jwks_url = (
                "https://example.supabase.co/auth/v1/.well-known/jwks.json"
            )
            importlib.reload(deps)

        importlib.reload(deps)


@pytest.mark.unit
def test_principal_is_admin_role() -> None:
    """The admin base role derives the capability; a plain guardian has neither."""
    admin = Principal(
        subject="s",
        user_id=uuid.uuid4(),
        role="admin",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )
    # __post_init__ derives the capability from the admin base role even when
    # the flag is not passed, so a legacy admin-only row keeps its power.
    assert admin.is_admin is True
    assert admin.is_guardian is False
    guardian = Principal(
        subject="s",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )
    assert guardian.is_admin is False


@pytest.mark.unit
def test_principal_dual_role_holds_both_capabilities() -> None:
    """A guardian with the admin flag is both guardian and admin."""
    dual = Principal(
        subject="s",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
        is_admin=True,
    )
    assert dual.is_guardian is True
    assert dual.is_admin is True


@pytest.mark.unit
def test_principal_child_cannot_hold_admin_capability() -> None:
    """A CHILD principal force-clears is_admin (defense in depth).

    The ck_user_child_not_admin CHECK blocks this at rest, but a mistakenly
    constructed Principal(role=CHILD, is_admin=True) must never escalate
    in-memory: __post_init__ clears the flag for a child base role.
    """
    child = Principal(
        subject="s",
        user_id=uuid.uuid4(),
        role="child",
        family_id=uuid.uuid4(),
        profile_ids=frozenset({uuid.uuid4()}),
        is_admin=True,
    )
    assert child.is_admin is False
    assert child.is_guardian is False


class TestJwksClient:
    """Direct tests for the lazily-constructed JWKS client and its guards.

    The OIDC negative-token suite (test_oidc_verification.py) monkeypatches
    `_jwks_client`, so the function body, including the https guard, is
    exercised only here.
    """

    @pytest.fixture(autouse=True)
    def _reset_jwks_cache(self) -> Iterator[None]:
        """Isolate the process-wide `_jwks_client_cache` singleton per test."""
        deps._jwks_client_cache = None
        try:
            yield
        finally:
            deps._jwks_client_cache = None

    @pytest.mark.unit
    def test_missing_jwks_url_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A None `oidc_jwks_url` cannot verify tokens and must fail fast."""
        from cyo_adventure.core.exceptions import ConfigurationError

        monkeypatch.setattr(deps.settings, "oidc_jwks_url", None)
        with pytest.raises(ConfigurationError, match="OIDC_JWKS_URL is not configured"):
            deps._jwks_client()

    @pytest.mark.unit
    def test_non_https_jwks_url_rejected_outside_local(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An http JWKS URL outside local is refused (on-path key substitution)."""
        from cyo_adventure.core.exceptions import ConfigurationError

        monkeypatch.setattr(deps.settings, "environment", "production")
        monkeypatch.setattr(
            deps.settings, "oidc_jwks_url", "http://example.supabase.co/jwks.json"
        )
        with pytest.raises(ConfigurationError, match="must use https"):
            deps._jwks_client()

    @pytest.mark.unit
    def test_https_jwks_url_outside_local_builds_and_caches_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A https JWKS URL outside local constructs and caches the client.

        PyJWKClient opens no network connection at construction, so this stays
        offline; a second call returns the same cached instance.
        """
        monkeypatch.setattr(deps.settings, "environment", "production")
        monkeypatch.setattr(
            deps.settings,
            "oidc_jwks_url",
            "https://example.supabase.co/auth/v1/.well-known/jwks.json",
        )
        client = deps._jwks_client()
        assert isinstance(client, jwt.PyJWKClient)
        assert deps._jwks_client() is client

    @pytest.mark.unit
    def test_local_env_allows_http_jwks_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """In local the https requirement is not enforced (dev convenience)."""
        monkeypatch.setattr(deps.settings, "environment", "local")
        monkeypatch.setattr(
            deps.settings, "oidc_jwks_url", "http://localhost:9999/jwks.json"
        )
        assert isinstance(deps._jwks_client(), jwt.PyJWKClient)
