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

    with pytest.raises(SystemExit) as exc:
        await seed_staging.seed()
    message = str(exc.value)
    assert "staging" in message
    assert "production" in message


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
