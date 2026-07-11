"""Unit tests for scripts/seed_staging.py helpers (no network, no DB).

scripts/ is not an importable package (no __init__.py, by design; see
per-file-ignores INP for scripts/**/*.py in pyproject.toml), so the module is
loaded directly from its file path via importlib.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "seed_staging",
    Path(__file__).resolve().parents[2] / "scripts" / "seed_staging.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
seed_staging = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seed_staging)

pytestmark = pytest.mark.unit

_ALL_ENV = {
    "SUPABASE_URL": "https://staging-ref.supabase.co",
    "SUPABASE_SERVICE_KEY": "sb_secret_test",
    "SEED_GUARDIAN_EMAIL": "guardian@example.com",
    "SEED_ADMIN_EMAIL": "admin@example.com",
    "SEED_GUARDIAN_PASSWORD": "pw-guardian-12345!",
    "SEED_ADMIN_PASSWORD": "pw-admin-12345!",
    "CYO_ADVENTURE_DATABASE_URL": "postgresql+asyncpg://u:p@host:5432/postgres",
    "ENVIRONMENT": "staging",
}


def _set_all_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    values = {**_ALL_ENV, **overrides}
    for name, value in values.items():
        monkeypatch.setenv(name, value)


class _FakeResponse:
    """A minimal httpx.Response stand-in: status_code, json(), raise_for_status()."""

    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://staging-ref.supabase.co")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=request, response=response
            )


# ---------------------------------------------------------------------------
# build_auth_user_payload / require_env (given in the task brief)
# ---------------------------------------------------------------------------


def test_admin_user_payload_confirms_email() -> None:
    payload = seed_staging.build_auth_user_payload("a@example.com", "pw12345678!")
    assert payload == {
        "email": "a@example.com",
        "password": "pw12345678!",
        "email_confirm": True,
    }


def test_required_env_lists_all_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in seed_staging.REQUIRED_ENV:
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(SystemExit) as exc:
        seed_staging.require_env()
    assert "SUPABASE_URL" in str(exc.value)


def test_required_env_lists_only_the_missing_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in seed_staging.REQUIRED_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://staging-ref.supabase.co")

    with pytest.raises(SystemExit) as exc:
        seed_staging.require_env()
    message = str(exc.value)
    assert "SUPABASE_URL" not in message
    assert "SEED_GUARDIAN_PASSWORD" in message
    assert "ENVIRONMENT" in message


def test_require_env_passes_when_all_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all_env(monkeypatch)
    assert seed_staging.require_env() is None


# ---------------------------------------------------------------------------
# Hard guard: refuse to run unless ENVIRONMENT=staging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_exits_when_environment_not_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_all_env(monkeypatch, ENVIRONMENT="production")

    # The guard must block BEFORE any Auth network call: a refactor moving the
    # ENVIRONMENT check after ensure_auth_user would still raise SystemExit but
    # would have already created Auth users against a non-staging target. Patch
    # the client constructor and assert it is never even instantiated.
    auth_client = MagicMock()
    with (
        patch.object(seed_staging.httpx, "AsyncClient", auth_client),
        pytest.raises(SystemExit) as exc,
    ):
        await seed_staging.seed()
    message = str(exc.value)
    assert "staging" in message
    assert "production" in message
    auth_client.assert_not_called()


@pytest.mark.asyncio
async def test_seed_exits_when_supabase_url_not_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_all_env(monkeypatch, SUPABASE_URL="http://staging-ref.supabase.co")

    # A non-https URL must be rejected before the service key is attached to a
    # client, so the full-privilege admin key cannot be sent in cleartext or to
    # an unexpected transport.
    auth_client = MagicMock()
    with (
        patch.object(seed_staging.httpx, "AsyncClient", auth_client),
        pytest.raises(SystemExit) as exc,
    ):
        await seed_staging.seed()
    assert "https" in str(exc.value)
    auth_client.assert_not_called()


@pytest.mark.asyncio
async def test_seed_exits_when_required_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in seed_staging.REQUIRED_ENV:
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(SystemExit) as exc:
        await seed_staging.seed()
    assert "SUPABASE_URL" in str(exc.value)


# ---------------------------------------------------------------------------
# _find_auth_user_by_email
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_auth_user_by_email_found() -> None:
    body = {"users": [{"id": "abc-1", "email": "a@example.com"}]}
    client = SimpleNamespace(get=AsyncMock(return_value=_FakeResponse(200, body)))
    result = await seed_staging._find_auth_user_by_email(client, "a@example.com")
    assert result == "abc-1"


@pytest.mark.asyncio
async def test_find_auth_user_by_email_not_found() -> None:
    body = {"users": [{"id": "abc-1", "email": "other@example.com"}]}
    client = SimpleNamespace(get=AsyncMock(return_value=_FakeResponse(200, body)))
    result = await seed_staging._find_auth_user_by_email(client, "a@example.com")
    assert result is None


@pytest.mark.asyncio
async def test_find_auth_user_by_email_handles_malformed_body() -> None:
    client = SimpleNamespace(get=AsyncMock(return_value=_FakeResponse(200, ["oops"])))
    result = await seed_staging._find_auth_user_by_email(client, "a@example.com")
    assert result is None


@pytest.mark.asyncio
async def test_find_auth_user_by_email_handles_non_list_users_key() -> None:
    client = SimpleNamespace(
        get=AsyncMock(return_value=_FakeResponse(200, {"users": "not-a-list"}))
    )
    result = await seed_staging._find_auth_user_by_email(client, "a@example.com")
    assert result is None


@pytest.mark.asyncio
async def test_find_auth_user_by_email_returns_none_when_matched_id_is_null() -> None:
    # A record matching the email but carrying a null id must yield None (so
    # ensure_auth_user proceeds to create) rather than returning the string
    # "None" from the id-stringify branch.
    body = {"users": [{"id": None, "email": "a@example.com"}]}
    client = SimpleNamespace(get=AsyncMock(return_value=_FakeResponse(200, body)))
    result = await seed_staging._find_auth_user_by_email(client, "a@example.com")
    assert result is None


# ---------------------------------------------------------------------------
# ensure_auth_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_auth_user_returns_existing_without_posting() -> None:
    body = {"users": [{"id": "existing-id", "email": "a@example.com"}]}
    get = AsyncMock(return_value=_FakeResponse(200, body))
    post = AsyncMock()
    client = SimpleNamespace(get=get, post=post)

    result = await seed_staging.ensure_auth_user(client, "a@example.com", "pw!")

    assert result == "existing-id"
    post.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_auth_user_creates_when_absent() -> None:
    get = AsyncMock(return_value=_FakeResponse(200, {"users": []}))
    post = AsyncMock(
        return_value=_FakeResponse(200, {"id": "new-id", "email": "b@example.com"})
    )
    client = SimpleNamespace(get=get, post=post)

    result = await seed_staging.ensure_auth_user(client, "b@example.com", "pw12345678!")

    assert result == "new-id"
    post.assert_awaited_once()
    _, kwargs = post.call_args
    assert kwargs["json"] == {
        "email": "b@example.com",
        "password": "pw12345678!",
        "email_confirm": True,
    }


@pytest.mark.asyncio
async def test_ensure_auth_user_recovers_from_conflicting_create() -> None:
    get = AsyncMock(
        side_effect=[
            _FakeResponse(200, {"users": []}),
            _FakeResponse(
                200, {"users": [{"id": "race-id", "email": "c@example.com"}]}
            ),
        ]
    )
    post = AsyncMock(return_value=_FakeResponse(422, {"msg": "already registered"}))
    client = SimpleNamespace(get=get, post=post)

    result = await seed_staging.ensure_auth_user(client, "c@example.com", "pw!")

    assert result == "race-id"
    assert get.await_count == 2


@pytest.mark.asyncio
async def test_ensure_auth_user_raises_when_create_fails_and_recheck_finds_nothing() -> (
    None
):
    get = AsyncMock(return_value=_FakeResponse(200, {"users": []}))
    post = AsyncMock(return_value=_FakeResponse(422, {"msg": "nope"}))
    client = SimpleNamespace(get=get, post=post)

    with pytest.raises(httpx.HTTPStatusError):
        await seed_staging.ensure_auth_user(client, "d@example.com", "pw!")


@pytest.mark.asyncio
async def test_ensure_auth_user_raises_runtime_error_on_missing_id() -> None:
    get = AsyncMock(return_value=_FakeResponse(200, {"users": []}))
    post = AsyncMock(return_value=_FakeResponse(200, {"email": "e@example.com"}))
    client = SimpleNamespace(get=get, post=post)

    with pytest.raises(RuntimeError, match="unexpected body"):
        await seed_staging.ensure_auth_user(client, "e@example.com", "pw!")


@pytest.mark.asyncio
async def test_ensure_auth_user_recovers_from_conflicting_create_400() -> None:
    # The recovery branch keys on status_code in (400, 422); the 422 arm is
    # covered above. This pins the 400 arm so a narrowing to `== 422` (which
    # would break race recovery when GoTrue returns 400 for "already
    # registered") is caught.
    get = AsyncMock(
        side_effect=[
            _FakeResponse(200, {"users": []}),
            _FakeResponse(
                200, {"users": [{"id": "race-id-400", "email": "c@example.com"}]}
            ),
        ]
    )
    post = AsyncMock(return_value=_FakeResponse(400, {"msg": "already registered"}))
    client = SimpleNamespace(get=get, post=post)

    result = await seed_staging.ensure_auth_user(client, "c@example.com", "pw!")

    assert result == "race-id-400"
    assert get.await_count == 2


# ---------------------------------------------------------------------------
# seed() idempotency (DB and network fully mocked)
# ---------------------------------------------------------------------------


def _auth_ctx() -> MagicMock:
    """A MagicMock async-context-manager standing in for httpx.AsyncClient()."""
    body = {
        "users": [
            {"id": "guardian-auth-id", "email": _ALL_ENV["SEED_GUARDIAN_EMAIL"]},
            {"id": "admin-auth-id", "email": _ALL_ENV["SEED_ADMIN_EMAIL"]},
        ]
    }
    fake_client = SimpleNamespace(
        get=AsyncMock(return_value=_FakeResponse(200, body)),
        post=AsyncMock(),
    )
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=fake_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _mock_engine() -> MagicMock:
    conn = AsyncMock()
    conn.run_sync = AsyncMock(return_value=None)
    engine_ctx = MagicMock()
    engine_ctx.__aenter__ = AsyncMock(return_value=conn)
    engine_ctx.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.begin = MagicMock(return_value=engine_ctx)
    return engine


def _mock_session_factory(
    existing_guardian: object | None,
) -> tuple[MagicMock, MagicMock]:
    session = AsyncMock()
    # session.add is synchronous in real SQLAlchemy; AsyncMock() would default
    # every attribute (including .add) to an async mock, leaving its returned
    # coroutine un-awaited and raising a RuntimeWarning under this project's
    # filterwarnings = ["error"].
    session.add = MagicMock()
    session.scalar = AsyncMock(return_value=existing_guardian)

    def _populate_ids() -> None:
        # Real SQLAlchemy applies each row's uuid PK default during flush; this
        # mock never touches a DB, so emulate it by giving every pending row a
        # distinct id. Without this, guardian.id and admin.id both stay None and
        # the downstream FK-wiring assertions (approved_by/assigned_by ==
        # guardian.id, not admin.id) would pass tautologically (None == None).
        for index, add_call in enumerate(session.add.call_args_list):
            row = add_call.args[0]
            if getattr(row, "id", None) is None:
                row.id = f"pk-{index}"

    session.flush = AsyncMock(side_effect=_populate_ids)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session_ctx)
    return session_factory, session


def _assert_scalar_filters_on_authn_subject(
    session: MagicMock, expected_subject: str
) -> None:
    """Assert the statement passed to session.scalar() is a WHERE on
    User.authn_subject with the expected bound value.

    A fixed session.scalar() return value alone would let a regression that
    filters on the wrong column (e.g. User.id or User.email) pass silently;
    this inspects the actual Select statement's WHERE clause structure.
    """
    session.scalar.assert_awaited_once()
    (stmt,), _ = session.scalar.call_args
    where_clause = stmt.whereclause
    assert where_clause is not None
    assert where_clause.left.name == "authn_subject"
    assert where_clause.left.table.name == seed_staging.User.__tablename__
    assert where_clause.right.value == expected_subject


@pytest.mark.asyncio
async def test_seed_skips_when_guardian_already_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_all_env(monkeypatch)
    session_factory, session = _mock_session_factory(existing_guardian=object())
    engine = _mock_engine()

    with patch.object(seed_staging.httpx, "AsyncClient", return_value=_auth_ctx()):
        await seed_staging.seed(engine=engine, session_factory=session_factory)

    _assert_scalar_filters_on_authn_subject(session, "guardian-auth-id")
    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_seed_inserts_fixtures_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_all_env(monkeypatch)
    session_factory, session = _mock_session_factory(existing_guardian=None)
    engine = _mock_engine()

    with patch.object(seed_staging.httpx, "AsyncClient", return_value=_auth_ctx()):
        await seed_staging.seed(engine=engine, session_factory=session_factory)

    _assert_scalar_filters_on_authn_subject(session, "guardian-auth-id")
    session.commit.assert_awaited_once()
    # family, profile, guardian, admin, then (storybook, version, assignment)
    # per fixture story (2 stories) = 4 + 2 * 3 = 10 inserts.
    assert session.add.call_count == 10

    added = [call.args[0] for call in session.add.call_args_list]
    roles = {getattr(row, "role", None) for row in added}
    assert roles == {None, "guardian", "admin"}
    guardian_row = next(
        row for row in added if getattr(row, "role", None) == "guardian"
    )
    admin_row = next(row for row in added if getattr(row, "role", None) == "admin")
    assert guardian_row.authn_subject == "guardian-auth-id"
    assert admin_row.authn_subject == "admin-auth-id"

    storybook_ids = {row.id for row in added if type(row).__name__ == "Storybook"}
    assert storybook_ids == {"s_tide_pools", "s_clockwork_garden"}

    # The child profile's age band gates which content it may be assigned.
    profiles = [row for row in added if type(row).__name__ == "ChildProfile"]
    assert len(profiles) == 1
    assert profiles[0].age_band == "5-8"

    # Publish/assignment wiring is the actual deliverable: a regression that
    # dropped published_at, mis-set status, or wired approved_by/assigned_by to
    # the admin (or None) would still add 10 rows and pass the count assertion
    # while producing staging stories the child profile cannot open (the read
    # gate needs an approved version plus an assignment).
    storybooks = [row for row in added if type(row).__name__ == "Storybook"]
    assert all(sb.status == "published" for sb in storybooks)
    assert all(sb.current_published_version is not None for sb in storybooks)

    versions = [row for row in added if type(row).__name__ == "StorybookVersion"]
    assert len(versions) == 2
    assert all(v.published_at is not None for v in versions)
    assert all(v.approved_by == guardian_row.id for v in versions)
    assert all(v.approved_by != admin_row.id for v in versions)

    assignments = [row for row in added if type(row).__name__ == "StorybookAssignment"]
    assert len(assignments) == 2
    assert all(a.assigned_by == guardian_row.id for a in assignments)
    assert all(a.assigned_by != admin_row.id for a in assignments)
    assert {a.child_profile_id for a in assignments} == {profiles[0].id}
