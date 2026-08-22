"""Tests for cyo_adventure.api.health module.

Covers liveness, readiness, startup, and health alias endpoints, plus the
check_database (happy path and failure path), check_cache, and
readiness helper functions.

No live database is used; get_session is patched with an async context manager.
"""

from __future__ import annotations

import time as _time_stdlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

# Safe at module scope: core.rls_posture holds a query constant and a frozen
# dataclass, with no app or engine construction (unlike api.health, which the
# helpers below import lazily on purpose).
from cyo_adventure.core.rls_posture import CONNECTED_ROLE_QUERY

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable


def _time_raiser_on_nth_call(n: int, exc: Exception) -> Callable[[], float]:
    """Return a side-effect callable that raises ``exc`` on the Nth call to time.time().

    All other calls delegate to the real ``time.time()`` so structlog timestamps
    and other incidental callers are not disturbed.
    """
    _real = _time_stdlib.time
    _state: dict[str, int] = {"count": 0}

    def _fake() -> float:
        _state["count"] += 1
        if _state["count"] == n:
            raise exc
        return _real()

    return _fake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with the health router mounted at its
    canonical ``/api/v1`` prefix, matching how ``app.py`` mounts it in
    production (UW-L04). The un-prefixed loopback alias app.py also mounts
    is exercised separately by ``TestLegacyHealthPathAlias`` against the
    real app, not this minimal one.
    """
    from cyo_adventure.api.health import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


# ---------------------------------------------------------------------------
# Liveness probe
# ---------------------------------------------------------------------------


class TestLiveness:
    """Tests for the /api/v1/health/live endpoint."""

    @pytest.mark.unit
    def test_liveness_returns_200(self) -> None:
        """GET /api/v1/health/live returns HTTP 200."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        response = client.get("/api/v1/health/live")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_liveness_status_is_ok(self) -> None:
        """GET /api/v1/health/live body has status 'ok'."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        data = client.get("/api/v1/health/live").json()

        assert data["status"] == "ok"

    @pytest.mark.unit
    def test_liveness_includes_uptime(self) -> None:
        """GET /api/v1/health/live body includes a non-negative uptime_seconds field."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        data = client.get("/api/v1/health/live").json()

        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0


# ---------------------------------------------------------------------------
# Startup probe
# ---------------------------------------------------------------------------


class TestStartup:
    """Tests for the /api/v1/health/startup endpoint."""

    @pytest.mark.unit
    def test_startup_returns_200(self) -> None:
        """GET /api/v1/health/startup returns HTTP 200."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        response = client.get("/api/v1/health/startup")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_startup_status_is_started(self) -> None:
        """GET /api/v1/health/startup body has status 'started'."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        data = client.get("/api/v1/health/startup").json()

        assert data["status"] == "started"


# ---------------------------------------------------------------------------
# Health alias
# ---------------------------------------------------------------------------


class TestHealthAlias:
    """Tests for the hidden /api/v1/health/ alias endpoint."""

    @pytest.mark.unit
    def test_health_alias_returns_200(self) -> None:
        """GET /api/v1/health/ returns HTTP 200 (alias for liveness)."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        response = client.get("/api/v1/health/")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_health_alias_status_is_ok(self) -> None:
        """GET /api/v1/health/ has the same status as /api/v1/health/live."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        data = client.get("/api/v1/health/").json()

        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Legacy (un-prefixed) health path alias (UW-L04, app.py's second mount)
# ---------------------------------------------------------------------------


class TestLegacyHealthPathAlias:
    """The un-prefixed ``/health/*`` mount exists solely for an out-of-repo probe.

    ``app.py`` mounts the health router twice: once at the canonical
    ``/api/v1/health`` prefix (in the OpenAPI schema, reachable through
    ``frontend/nginx.conf``'s ``location /api/`` proxy), and once with no
    prefix and ``include_in_schema=False``. The second mount is not dead
    duplication: the production container healthcheck is defined out of
    repo, in homelab-infra's ``services/cyo-adventure/docker-compose.yml``,
    and probes ``/health/live`` directly on port 8000, bypassing the proxy
    entirely. Deleting this alias to "tidy up" app.py would make the
    container fail its healthcheck on the next deploy, since that
    out-of-repo probe path cannot be updated in the same change. This class
    is the regression guard both `#VERIFY` markers on that mount (app.py and
    middleware/security.py) point at.
    """

    @pytest.mark.unit
    def test_legacy_alias_path_returns_200(self) -> None:
        """GET /health/live (the un-prefixed alias) still returns HTTP 200."""
        from cyo_adventure.app import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/health/live")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_legacy_alias_is_absent_from_openapi_schema(self) -> None:
        """The alias never appears in the OpenAPI schema; the canonical path does.

        This is what would catch someone deleting the canonical
        ``/api/v1/health`` mount and keeping only the alias: a naive "health
        responds" smoke test would still pass, but the documented,
        schema-visible path every external monitor relies on would be gone.
        """
        from cyo_adventure.app import create_app

        app = create_app()
        paths = app.openapi()["paths"]

        assert "/api/v1/health/live" in paths
        assert "/health/live" not in paths


# ---------------------------------------------------------------------------
# check_database helper
# ---------------------------------------------------------------------------


class TestCheckDatabase:
    """Tests for the check_database() async helper."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_database_happy_path_returns_true_status(self) -> None:
        """check_database returns status=True when the session executes successfully."""
        from cyo_adventure.api.health import check_database

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock()

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=_fake_get_session,
        ):
            result = await check_database()

        assert result.status is True
        assert result.name == "database"
        assert result.error is None
        assert result.latency_ms is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_database_failure_returns_false_status(self) -> None:
        """check_database returns status=False and generic error when execute raises."""
        from cyo_adventure.api.health import check_database

        @asynccontextmanager
        async def _failing_get_session() -> AsyncGenerator[None, None]:
            raise RuntimeError("connection refused")
            yield  # pragma: no cover

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=_failing_get_session,
        ):
            result = await check_database()

        assert result.status is False
        assert result.name == "database"
        # Must NOT leak the raw exception text (OWASP A09)
        assert result.error == "dependency unavailable"
        assert "connection refused" not in (result.error or "")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_database_failure_latency_is_recorded(self) -> None:
        """check_database records latency even on failure."""
        from cyo_adventure.api.health import check_database

        @asynccontextmanager
        async def _failing_get_session() -> AsyncGenerator[None, None]:
            raise OSError("timeout")
            yield  # pragma: no cover

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=_failing_get_session,
        ):
            result = await check_database()

        assert result.latency_ms is not None
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# check_database_privilege helper
# ---------------------------------------------------------------------------


def _fake_session_with_connected_role(
    role_name: str,
    *,
    role_bypasses_rls: bool | None,
    owns_rls_table: bool = False,
) -> Callable[[], AsyncGenerator[AsyncMock, None]]:
    """Build a mock AsyncSession whose execute() resolves the connected-role row.

    Mirrors ``_fake_session_with_queue_counts``: one round trip returning the
    identity ``check_database_privilege`` reads. The query reports the two
    bypass signals separately, so each can be exercised on its own:

    - ``role_bypasses_rls``: the ``rolbypassrls OR rolsuper`` attribute pair,
      already COALESCEd to ``true`` in SQL when the role has no ``pg_roles``
      row. ``None`` models that COALESCE failing to apply.
    - ``owns_rls_table``: the role owns at least one RLS-enabled ``public``
      table that does not FORCE RLS, which bypasses every policy on it.
    """
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = Mock()
    mock_result.one = Mock(
        return_value=SimpleNamespace(
            role_name=role_name,
            role_bypasses_rls=role_bypasses_rls,
            owns_rls_table=owns_rls_table,
        )
    )
    mock_session.execute = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    return _fake_get_session


class TestCheckDatabasePrivilege:
    """Tests for the check_database_privilege() helper (ADR-021 cutover guard).

    RLS never applies to a table's owner, so every RLS policy in this schema
    is inert while the app connects as the ``postgres`` owner role. This check
    makes the connected identity observable per environment, turning "no
    application traffic connects as postgres" from a one-off manual query into
    a standing, alertable signal.

    The check is deliberately NOT in ``_CRITICAL_READINESS_CHECKS``: a
    pre-cutover environment is a security finding, not an outage, and must not
    pull pods out of the load-balancer rotation.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_least_privilege_role_reports_ok(self) -> None:
        """status=True, state='ok' when the connected role cannot bypass RLS."""
        from cyo_adventure.api.health import check_database_privilege

        fake_get_session = _fake_session_with_connected_role(
            "cyo_api", role_bypasses_rls=False, owns_rls_table=False
        )

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=fake_get_session,
        ):
            result = await check_database_privilege()

        assert result.name == "database_privilege"
        assert result.status is True
        assert result.state == "ok"
        assert result.error is None
        assert result.latency_ms is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bypassrls_role_reports_degraded(self) -> None:
        """status=False, state='degraded' via the rolbypassrls/rolsuper path.

        The first of the three bypass paths: the role attribute itself. The
        ownership path is exercised separately below, because an environment
        can be caught by either one alone.
        """
        from cyo_adventure.api.health import check_database_privilege

        fake_get_session = _fake_session_with_connected_role(
            "postgres", role_bypasses_rls=True, owns_rls_table=False
        )

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=fake_get_session,
        ):
            result = await check_database_privilege()

        assert result.status is False
        assert result.state == "degraded"
        assert result.error is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ownership_bypass_alone_reports_degraded(self) -> None:
        """Table ownership alone is a bypass, even with rolbypassrls false.

        The path an un-cut-over environment actually uses: the baseline
        migration assigns the Tier 1 tables to ``postgres``, RLS never applies
        to a table's owner, and this schema does not FORCE RLS. A check that
        read only the role attribute would report "ok" for a connection that
        still sees every family's rows.
        """
        from cyo_adventure.api.health import check_database_privilege

        fake_get_session = _fake_session_with_connected_role(
            "cyo_api", role_bypasses_rls=False, owns_rls_table=True
        )

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=fake_get_session,
        ):
            result = await check_database_privilege()

        assert result.status is False
        assert result.state == "degraded"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_role_missing_from_pg_roles_fails_closed(self) -> None:
        """An unanalyzable role reports degraded, never ok.

        The query COALESCEs a missing ``pg_roles`` row to ``true``; ``None``
        here models that default failing to apply. "Can this connection bypass
        RLS?" answered with "cannot tell" must not render as a reassuring
        state="ok" on an alertable check.
        """
        from cyo_adventure.api.health import check_database_privilege

        fake_get_session = _fake_session_with_connected_role(
            "ghost_role", role_bypasses_rls=None, owns_rls_table=False
        )

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=fake_get_session,
        ):
            result = await check_database_privilege()

        assert result.status is False
        assert result.state == "degraded"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_role_name_is_logged_but_never_in_the_response(self) -> None:
        """The role name reaches the logs and nothing else.

        /api/v1/health/ready is unauthenticated, so the response carries only the
        posture bit. The role name is operator-facing detail and belongs in
        the (access-controlled, redaction-aware) logs instead. Both halves are
        asserted here: a check that stopped logging the role would still pass
        a leak-only assertion while silently making the finding untriageable.
        """
        from cyo_adventure.api.health import check_database_privilege

        fake_get_session = _fake_session_with_connected_role(
            "postgres", role_bypasses_rls=True, owns_rls_table=True
        )

        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=fake_get_session,
            ),
            patch("cyo_adventure.api.health.logger") as mock_logger,
        ):
            result = await check_database_privilege()

        # Every serialized field, not just the concatenated repr: a role name
        # landing in `error` would be caught by both, but one landing in a
        # field added later is only caught by checking them individually.
        dumped = result.model_dump()
        for field, value in dumped.items():
            assert "postgres" not in str(value), f"role name leaked via {field}"
        assert "postgres" not in str(dumped)

        # ...and the operator-facing half: the role name, plus which of the
        # two bypass paths fired, must actually be logged.
        warning_kwargs = [call.kwargs for call in mock_logger.warning.call_args_list]
        assert any(
            kwargs.get("role") == "postgres"
            and kwargs.get("via_role_attribute") is True
            and kwargs.get("via_table_ownership") is True
            for kwargs in warning_kwargs
        ), f"role name and bypass paths not logged; saw {warning_kwargs}"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_failure_returns_generic_error(self) -> None:
        """A database error yields status=False, state='unknown', no raw text.

        state distinguishes the two failure modes on purpose: "degraded" is a
        measured, real un-cut-over role an operator can fix, "unknown" is a
        probe that never returned. Collapsing them makes the alert
        unactionable.
        """
        from cyo_adventure.api.health import check_database_privilege

        @asynccontextmanager
        async def _failing_get_session() -> AsyncGenerator[None, None]:
            raise RuntimeError("connection refused")
            yield  # pragma: no cover

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=_failing_get_session,
        ):
            result = await check_database_privilege()

        assert result.status is False
        assert result.state == "unknown"
        # Must NOT leak the raw exception text (OWASP A09)
        assert result.error == "dependency unavailable"
        assert "connection refused" not in (result.error or "")
        assert result.latency_ms is not None


# ---------------------------------------------------------------------------
# check_cache helper
# ---------------------------------------------------------------------------


class TestCheckCache:
    """Tests for the check_cache() Redis-backed helper.

    settings.rate_limit_backend gates the real ping: "redis" performs one
    (mocked here, never a live connection), "memory" short-circuits to
    state="unconfigured" without touching the network at all.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_cache_redis_ok_returns_true_status(self) -> None:
        """check_cache returns status=True, state='ok' when ping succeeds."""
        from cyo_adventure.api.health import check_cache

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with (
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "redis",
            ),
            patch(
                "cyo_adventure.api.health.Redis.from_url",
                return_value=mock_client,
            ),
        ):
            result = await check_cache()

        assert result.status is True
        assert result.name == "cache"
        assert result.state == "ok"
        assert result.error is None
        mock_client.ping.assert_awaited_once()
        mock_client.aclose.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_cache_redis_ok_includes_latency(self) -> None:
        """check_cache includes a non-negative latency_ms on the happy path."""
        from cyo_adventure.api.health import check_cache

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with (
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "redis",
            ),
            patch(
                "cyo_adventure.api.health.Redis.from_url",
                return_value=mock_client,
            ),
        ):
            result = await check_cache()

        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_cache_redis_down_returns_false_status(self) -> None:
        """check_cache returns status=False, state='degraded' when ping fails."""
        from cyo_adventure.api.health import check_cache

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=OSError("connection refused"))
        mock_client.aclose = AsyncMock()

        with (
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "redis",
            ),
            patch(
                "cyo_adventure.api.health.Redis.from_url",
                return_value=mock_client,
            ),
        ):
            result = await check_cache()

        assert result.status is False
        assert result.name == "cache"
        assert result.state == "degraded"
        # Must NOT leak the raw exception text (OWASP A09)
        assert result.error == "dependency unavailable"
        assert "connection refused" not in (result.error or "")
        mock_client.aclose.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_cache_unconfigured_when_memory_backend(self) -> None:
        """check_cache reports state='unconfigured' when rate_limit_backend='memory'.

        No Redis client is constructed in this branch: patching Redis.from_url
        to raise proves the memory-backend short-circuit never reaches it.
        """
        from cyo_adventure.api.health import check_cache

        with (
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "memory",
            ),
            patch(
                "cyo_adventure.api.health.Redis.from_url",
                side_effect=AssertionError("Redis.from_url should not be called"),
            ),
        ):
            result = await check_cache()

        assert result.status is True
        assert result.name == "cache"
        assert result.state == "unconfigured"
        assert result.error is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_cache_unconfigured_includes_latency(self) -> None:
        """check_cache includes a non-negative latency_ms in the unconfigured branch."""
        from cyo_adventure.api.health import check_cache

        with patch(
            "cyo_adventure.api.health.settings.rate_limit_backend",
            "memory",
        ):
            result = await check_cache()

        assert result.latency_ms is not None
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# check_generation_queue helper (ADR-021 Phase 1: worker observability)
# ---------------------------------------------------------------------------


def _make_queue_result(
    stale_queued: int, stale_running: int, recent_failed: int
) -> Mock:
    """Build a fake SQLAlchemy Result whose ``.one()`` returns a queue-count row.

    check_generation_queue (ADR-021 review fix) collapsed its three
    sequential ``SELECT COUNT(*)`` round trips into a single
    ``COUNT(*) FILTER (WHERE ...)`` query, so tests now mock
    ``session.execute()`` returning a single Result rather than three
    ``session.scalar()`` calls.
    """
    row = SimpleNamespace(
        stale_queued=stale_queued,
        stale_running=stale_running,
        recent_failed=recent_failed,
    )
    result = Mock()
    result.one = Mock(return_value=row)
    return result


def _posture_dispatch(
    *,
    role_name: str = "cyo_api",
    role_bypasses_rls: bool | None = False,
    owns_rls_table: bool = False,
    error: Exception | None = None,
) -> tuple[Any, list[str]]:
    """Build a ``session.execute`` side effect that answers the posture query.

    ``readiness()`` shares one session between ``check_database`` and
    ``check_database_privilege``, so a test that mocks the session has to route
    two different statements to two different results.

    Dispatch is by identity against ``CONNECTED_ROLE_QUERY`` rather than by
    searching the rendered SQL for ``"rolbypassrls"``. A substring guess is a
    silent gate: rewriting the query so that literal no longer appears (using
    ``pg_authid``, or aliasing the column) would send the privilege check the
    queue-count row instead, and the test would go on "passing" while measuring
    nothing. The returned list records which statements were dispatched to the
    posture branch, so a caller can assert the branch actually fired.

    Args:
        role_name: ``current_user`` to report.
        role_bypasses_rls: The ``rolbypassrls OR rolsuper`` column; ``None``
            exercises the fail-closed path.
        owns_rls_table: The table-ownership bypass column.
        error: When given, the posture query raises this instead of returning a
            row, exercising the ``state="unknown"`` path.

    Returns:
        tuple: the ``side_effect`` callable, and a list appended to once per
        posture-query dispatch.
    """
    dispatched: list[str] = []

    async def _execute(statement: Any) -> Any:
        if str(statement).strip() == CONNECTED_ROLE_QUERY.strip():
            dispatched.append("posture")
            if error is not None:
                raise error
            result = Mock()
            result.one = Mock(
                return_value=SimpleNamespace(
                    role_name=role_name,
                    role_bypasses_rls=role_bypasses_rls,
                    owns_rls_table=owns_rls_table,
                )
            )
            return result
        return _make_queue_result(0, 0, 0)

    return _execute, dispatched


def _extract_updated_at_cutoff(stmt: Any, label: str) -> datetime:
    """Pull the bound ``updated_at`` cutoff literal out of one FILTER clause.

    Walks the actual SQLAlchemy expression tree check_generation_queue built
    for the aggregate column labeled ``label`` (e.g. "stale_queued") and
    returns the bound datetime value compared against ``updated_at``. Used
    to prove the health check computes its cutoff live from the queue
    module's constant rather than a hardcoded duplicate that happens to
    produce the same ok/degraded verdict when every count is zero.

    Typed ``Any`` deliberately: this walks SQLAlchemy's internal expression
    tree (``Select.selected_columns``, ``FunctionFilter.criterion``), which
    has no stable, precisely-typed public surface to assert against.
    """
    for col in stmt.selected_columns:
        if col.name != label:
            continue
        for clause in col.element.criterion.get_children():
            left, right = clause.get_children()
            if getattr(left, "name", None) == "updated_at":
                return right.value
    reason = f"no updated_at cutoff found for label {label!r}"
    raise AssertionError(reason)


def _fake_session_with_queue_counts(
    stale_queued: int, stale_running: int, recent_failed: int
) -> tuple[AsyncMock, Callable[[], AsyncGenerator[AsyncMock, None]]]:
    """Build a mock AsyncSession whose execute() resolves the queue-count row.

    Mirrors the check_database mocking pattern (an async-context-managed
    session), with ``execute()`` returning the single Result row
    check_generation_queue's one aggregate query now produces (stale-queued,
    stale-running, recent-failed, in one round trip).
    """
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(
        return_value=_make_queue_result(stale_queued, stale_running, recent_failed)
    )

    @asynccontextmanager
    async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    return mock_session, _fake_get_session


class TestCheckGenerationQueue:
    """Tests for the check_generation_queue() async helper (ADR-021).

    Real production failure mode (a schema-drift incident): jobs FAILING,
    not merely piling up queued. The check surfaces three signals: rows
    stranded at "queued" past DEFAULT_STALE_AFTER, rows stranded at
    "running" past the job-timeout-derived threshold (mirroring
    requeue_stranded_jobs exactly so the alarm and the actual sweep never
    disagree), and rows that recently failed (the schema-drift catcher,
    gated by RECENT_FAILED_DEGRADED_THRESHOLD so one force-failed job does
    not cause 24h of alarm fatigue). All three counts come from a single
    ``COUNT(*) FILTER (WHERE ...)`` query (one round trip); see
    ``_fake_session_with_queue_counts``.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_generation_queue_ok_when_all_counts_zero(self) -> None:
        """status=True, state='ok' when no stale/failed rows exist."""
        from cyo_adventure.api.health import check_generation_queue

        _, fake_get_session = _fake_session_with_queue_counts(0, 0, 0)

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=fake_get_session,
        ):
            result = await check_generation_queue()

        assert result.name == "generation_queue"
        assert result.status is True
        assert result.state == "ok"
        assert result.error is None
        assert result.latency_ms is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_generation_queue_degraded_on_stale_queued(self) -> None:
        """status=False, state='degraded' when stale-queued rows exist.

        stale_queued is not threshold-gated: even a single stranded row is
        reported immediately, since requeue_stranded_jobs would already
        have swept it if it weren't genuinely stuck.
        """
        from cyo_adventure.api.health import check_generation_queue

        _, fake_get_session = _fake_session_with_queue_counts(3, 0, 0)

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=fake_get_session,
        ):
            result = await check_generation_queue()

        assert result.status is False
        assert result.state == "degraded"
        assert result.error is not None
        assert "3" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_generation_queue_degraded_on_stale_running(self) -> None:
        """status=False, state='degraded' when stale-running rows exist."""
        from cyo_adventure.api.health import check_generation_queue

        _, fake_get_session = _fake_session_with_queue_counts(0, 2, 0)

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=fake_get_session,
        ):
            result = await check_generation_queue()

        assert result.status is False
        assert result.state == "degraded"
        assert result.error is not None
        assert "2" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_generation_queue_degraded_on_recent_failed(self) -> None:
        """status=False, state='degraded' when recent failures exceed the threshold.

        This is the signal that would have caught the real schema-drift
        incident: jobs failing outright, not merely piling up queued. 5
        exceeds RECENT_FAILED_DEGRADED_THRESHOLD (3).
        """
        from cyo_adventure.api.health import (
            RECENT_FAILED_DEGRADED_THRESHOLD,
            check_generation_queue,
        )

        assert RECENT_FAILED_DEGRADED_THRESHOLD < 5

        _, fake_get_session = _fake_session_with_queue_counts(0, 0, 5)

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=fake_get_session,
        ):
            result = await check_generation_queue()

        assert result.status is False
        assert result.state == "degraded"
        assert result.error is not None
        assert "5" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_generation_queue_recent_failed_at_threshold_stays_ok(
        self,
    ) -> None:
        """A recent_failed count AT the threshold does not flip to degraded.

        Fix for the alarm-fatigue gap: a handful of jobs force-failed by
        requeue_stranded_jobs (e.g. a single worker OOM) must not read as
        'degraded' for 24h. Only a count that *exceeds*
        RECENT_FAILED_DEGRADED_THRESHOLD should. This is the boundary case
        one below the "above threshold" test.
        """
        from cyo_adventure.api.health import (
            RECENT_FAILED_DEGRADED_THRESHOLD,
            check_generation_queue,
        )

        _, fake_get_session = _fake_session_with_queue_counts(
            0, 0, RECENT_FAILED_DEGRADED_THRESHOLD
        )

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=fake_get_session,
        ):
            result = await check_generation_queue()

        assert result.status is True
        assert result.state == "ok"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_generation_queue_recent_failed_above_threshold_is_degraded(
        self,
    ) -> None:
        """A recent_failed count one ABOVE the threshold flips to degraded.

        Paired boundary case with the "at threshold" test above: the raw
        count is always reported, but classification only flips once the
        threshold is exceeded, not merely reached.
        """
        from cyo_adventure.api.health import (
            RECENT_FAILED_DEGRADED_THRESHOLD,
            check_generation_queue,
        )

        _, fake_get_session = _fake_session_with_queue_counts(
            0, 0, RECENT_FAILED_DEGRADED_THRESHOLD + 1
        )

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=fake_get_session,
        ):
            result = await check_generation_queue()

        assert result.status is False
        assert result.state == "degraded"
        assert result.error is not None
        assert str(RECENT_FAILED_DEGRADED_THRESHOLD + 1) in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_generation_queue_db_error_returns_false_status(self) -> None:
        """status=False, generic error, when the database is unreachable."""
        from cyo_adventure.api.health import check_generation_queue

        @asynccontextmanager
        async def _failing_get_session() -> AsyncGenerator[None, None]:
            raise RuntimeError("connection refused")
            yield  # pragma: no cover

        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=_failing_get_session,
        ):
            result = await check_generation_queue()

        assert result.status is False
        assert result.name == "generation_queue"
        # Must NOT leak the raw exception text (OWASP A09)
        assert result.error == "dependency unavailable"
        assert "connection refused" not in (result.error or "")
        assert result.latency_ms is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_generation_queue_uses_queue_module_stale_after(self) -> None:
        """The stale-queued cutoff is derived live from queue.DEFAULT_STALE_AFTER.

        Regression guard for the ADR-021 invariant: the health check must
        import the same constant requeue_stranded_jobs defaults to, not a
        hardcoded duplicate, so the alarm and the actual sweep never drift
        apart.

        The predecessor of this test patched the constant but fed all-zero
        counts through a fully mocked ``scalar()``, so the cutoff never
        affected the outcome and a hardcoded ``timedelta(minutes=30)``
        duplicate in health.py would have passed it just as well. This
        version captures the actual statement passed to ``session.execute``
        and reads the bound ``updated_at`` cutoff literal off the
        stale_queued FILTER clause: the assertion window is derived from
        the *patched* 5-minute constant, so a hardcoded 30-minute duplicate
        would miss it by ~25 minutes and fail.
        """
        from cyo_adventure.api.health import check_generation_queue

        captured_stmt: dict[str, Any] = {}

        async def _capture_execute(stmt: Any) -> Mock:
            captured_stmt["stmt"] = stmt
            return _make_queue_result(0, 0, 0)

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(side_effect=_capture_execute)

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        patched_stale_after = timedelta(minutes=5)
        before = datetime.now(UTC)
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_fake_get_session,
            ),
            patch(
                "cyo_adventure.generation.queue.DEFAULT_STALE_AFTER",
                patched_stale_after,
            ),
        ):
            result = await check_generation_queue()
        after = datetime.now(UTC)

        assert result.state == "ok"
        cutoff = _extract_updated_at_cutoff(captured_stmt["stmt"], "stale_queued")
        # `now` inside check_generation_queue was sampled between `before`
        # and `after`, so the cutoff it derived (`now - patched_stale_after`)
        # must fall in this exact window. A hardcoded 30-minute duplicate
        # would land ~25 minutes below `expected_low` and fail here.
        expected_low = before - patched_stale_after
        expected_high = after - patched_stale_after
        assert expected_low <= cutoff <= expected_high


# ---------------------------------------------------------------------------
# Readiness endpoint (integrates check_database)
# ---------------------------------------------------------------------------


class TestReadiness:
    """Tests for the /api/v1/health/ready endpoint via TestClient.

    settings.rate_limit_backend is patched to "memory" in every test here
    (unrelated to what's under test) so check_cache short-circuits to
    state="unconfigured" without a real Redis connection attempt, per this
    package's "no real network calls in unit tests" rule
    (tests/CLAUDE.md). TestReadinessCacheDoesNotGate below is what actually
    exercises the cache-down-does-not-gate-readiness behavior.
    """

    @pytest.mark.unit
    def test_readiness_returns_200_when_database_healthy(self) -> None:
        """GET /api/v1/health/ready returns 200 when database check passes."""
        mock_session = AsyncMock(spec=AsyncSession)
        # check_generation_queue shares get_session; explicit zero counts
        # keep this test's intent (a fully healthy readiness probe) clear
        # rather than relying on MagicMock's implicit int() coercion.
        # check_database's own execute(text("SELECT 1")) ignores this
        # return value, so a single row satisfies both callers.
        mock_session.execute = AsyncMock(return_value=_make_queue_result(0, 0, 0))

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_fake_get_session,
            ),
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "memory",
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        # A status code alone cannot distinguish FastAPI's real readiness
        # response from a proxy stub that returns a hardcoded 200 (exactly
        # how UW-L04 went unnoticed for a month: nginx's `location /health {
        # return 200 'OK'; }` shadowed this endpoint and a documented
        # "verified 200" pass was actually hitting the stub). The JSON
        # content type is the discriminator a status-only check misses.
        assert response.headers["content-type"].startswith("application/json")

    @pytest.mark.unit
    def test_readiness_returns_503_when_database_fails(self) -> None:
        """GET /api/v1/health/ready returns 503 when database check fails."""

        @asynccontextmanager
        async def _failing_get_session() -> AsyncGenerator[None, None]:
            raise RuntimeError("db down")
            yield  # pragma: no cover

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_failing_get_session,
            ),
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "memory",
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/health/ready")

        assert response.status_code == 503
        # Same discriminator as the 200 case above: a status code alone
        # cannot tell FastAPI's real response apart from a static proxy
        # stub, which is exactly how UW-L04's anti-oracle "verified 200"
        # survived undetected. The JSON content type is what a stub lacks.
        assert response.headers["content-type"].startswith("application/json")

    @pytest.mark.unit
    def test_readiness_503_detail_does_not_leak_exception_text(self) -> None:
        """GET /api/v1/health/ready 503 body must not contain raw exception text."""

        @asynccontextmanager
        async def _failing_get_session() -> AsyncGenerator[None, None]:
            raise RuntimeError("db-conn-error: connection timeout")
            yield  # pragma: no cover

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_failing_get_session,
            ),
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "memory",
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            body = client.get("/api/v1/health/ready").text

        assert "db-conn-error: connection timeout" not in body
        assert "dependency unavailable" in body


# ---------------------------------------------------------------------------
# Readiness endpoint: cache does not gate readiness (#ASSUME in readiness())
# ---------------------------------------------------------------------------


class TestReadinessCacheDoesNotGate:
    """A down or unconfigured cache is reported but never flips /api/v1/health/ready.

    Only ``database`` is in ``_CRITICAL_READINESS_CHECKS``; see readiness()'s
    #ASSUME docstring note for why cache is deliberately excluded.
    """

    @pytest.mark.unit
    def test_readiness_returns_200_when_cache_down_and_database_healthy(
        self,
    ) -> None:
        """A down Redis is reported in checks but still returns HTTP 200."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(return_value=_make_queue_result(0, 0, 0))

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock(side_effect=OSError("connection refused"))
        mock_redis_client.aclose = AsyncMock()

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_fake_get_session,
            ),
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "redis",
            ),
            patch(
                "cyo_adventure.api.health.Redis.from_url",
                return_value=mock_redis_client,
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"]["cache"]["status"] is False
        assert body["checks"]["cache"]["state"] == "degraded"

    @pytest.mark.unit
    def test_readiness_returns_200_when_cache_unconfigured(self) -> None:
        """An unconfigured (memory-backend) cache is reported but returns HTTP 200."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(return_value=_make_queue_result(0, 0, 0))

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_fake_get_session,
            ),
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "memory",
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["checks"]["cache"]["status"] is True
        assert body["checks"]["cache"]["state"] == "unconfigured"


# ---------------------------------------------------------------------------
# Readiness endpoint: database privilege does not gate readiness (ADR-021)
# ---------------------------------------------------------------------------


class TestReadinessPrivilegeDoesNotGate:
    """A degraded database_privilege check is reported but never flips readiness.

    Pre-cutover (the app connected as the ``postgres`` owner) is an open
    security finding, not an outage. It must be visible in the payload without
    pulling pods out of the load-balancer rotation.
    """

    @pytest.mark.unit
    def test_readiness_reports_degraded_privilege_and_still_returns_200(self) -> None:
        """A BYPASSRLS role is surfaced in checks but readiness stays HTTP 200."""
        mock_session = AsyncMock(spec=AsyncSession)
        execute, dispatched = _posture_dispatch(
            role_name="postgres", role_bypasses_rls=True, owns_rls_table=True
        )
        mock_session.execute = AsyncMock(side_effect=execute)

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_fake_get_session,
            ),
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "memory",
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"]["database_privilege"]["status"] is False
        assert body["checks"]["database_privilege"]["state"] == "degraded"
        # The unauthenticated payload must not name the role (OWASP A01).
        assert "postgres" not in str(body)
        # Proves the degraded verdict came from the posture query and not from a
        # mis-dispatched queue row that happened to look falsy.
        assert dispatched == ["posture"]

    @pytest.mark.unit
    def test_privilege_query_failure_is_unknown_and_does_not_gate(self) -> None:
        """A failing privilege query reports state='unknown' and stays HTTP 200.

        readiness() opens one session and hands it to both database checks, so
        this also pins the isolation that sharing implies: a failure inside the
        second check must not take out the first, and the probe must not
        conflate "could not measure" with "measured and bad".
        """
        mock_session = AsyncMock(spec=AsyncSession)
        execute, dispatched = _posture_dispatch(
            error=RuntimeError("permission denied for table pg_class")
        )
        mock_session.execute = AsyncMock(side_effect=execute)

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_fake_get_session,
            ),
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "memory",
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"]["database"]["status"] is True
        assert body["checks"]["database_privilege"]["status"] is False
        assert body["checks"]["database_privilege"]["state"] == "unknown"
        assert "permission denied" not in str(body)
        # Without this, a dispatch that never reached the posture branch would
        # also produce state="unknown" for the wrong reason.
        assert dispatched == ["posture"]


class TestReadinessSharedSession:
    """readiness() hands one pool checkout to both database-backed checks.

    A probe that took a connection per check would multiply pool pressure by
    the number of checks exactly when the pool is stressed, which is when
    readiness matters most. Sharing introduces one failure mode worth pinning:
    the context manager's exit can raise after both checks have already
    succeeded.
    """

    @pytest.mark.unit
    def test_both_checks_share_a_single_session_checkout(self) -> None:
        """One /api/v1/health/ready call opens one session for the two db checks."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(return_value=_make_queue_result(0, 0, 0))
        checkouts = {"count": 0}

        @asynccontextmanager
        async def _counting_get_session() -> AsyncGenerator[AsyncMock, None]:
            checkouts["count"] += 1
            yield mock_session

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_counting_get_session,
            ),
            patch("cyo_adventure.api.health.settings.rate_limit_backend", "memory"),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        assert response.status_code == 200
        # One for the shared database pair, one for check_generation_queue,
        # which is not part of the pair. Three would mean the pair split.
        assert checkouts["count"] == 2

    @pytest.mark.unit
    def test_teardown_failure_does_not_discard_completed_checks(self) -> None:
        """A raising session exit must not turn two passes into a 503.

        ``database`` is the only gating check. Re-running both checks
        unconditionally after any exception would overwrite results the shared
        checkout already produced, manufacturing an outage out of a failed
        close on an otherwise healthy process.
        """
        mock_session = AsyncMock(spec=AsyncSession)
        execute, _dispatched = _posture_dispatch()
        mock_session.execute = AsyncMock(side_effect=execute)
        entries = {"count": 0}

        @asynccontextmanager
        async def _exit_failing_get_session() -> AsyncGenerator[AsyncMock, None]:
            entries["count"] += 1
            msg = "connection reset on close"
            # The shared pair's checkout serves both checks, then fails on the
            # way out. Every later checkout fails outright: the connection is
            # genuinely gone, so a standalone re-run cannot succeed. That is
            # what makes this test non-vacuous -- re-running unconditionally
            # turns two passing checks into a 503.
            if entries["count"] == 1:
                yield mock_session
                raise RuntimeError(msg)
            raise RuntimeError(msg)
            yield mock_session  # pragma: no cover

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_exit_failing_get_session,
            ),
            patch("cyo_adventure.api.health.settings.rate_limit_backend", "memory"),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["checks"]["database"]["status"] is True
        assert body["checks"]["database_privilege"]["status"] is True
        assert body["checks"]["database_privilege"]["state"] == "ok"
        assert "connection reset on close" not in str(body)


# ---------------------------------------------------------------------------
# Readiness endpoint: generation queue does not gate readiness (ADR-021)
# ---------------------------------------------------------------------------


class TestReadinessQueueDoesNotGate:
    """A degraded generation_queue check is reported but never flips /api/v1/health/ready.

    Only ``database`` is in ``_CRITICAL_READINESS_CHECKS``; a stuck or failing
    worker must not pull API pods out of the load-balancer rotation for
    endpoints that touch nothing worker-related.
    """

    @pytest.mark.unit
    def test_readiness_returns_200_when_queue_degraded_and_database_healthy(
        self,
    ) -> None:
        """A degraded generation_queue is reported but still returns HTTP 200."""
        mock_session = AsyncMock(spec=AsyncSession)
        # stale_queued=4, stale_running=0, recent_failed=0
        mock_session.execute = AsyncMock(return_value=_make_queue_result(4, 0, 0))

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_fake_get_session,
            ),
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "memory",
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"]["generation_queue"]["status"] is False
        assert body["checks"]["generation_queue"]["state"] == "degraded"

    @pytest.mark.unit
    def test_readiness_returns_503_on_database_failure_regardless_of_queue(
        self,
    ) -> None:
        """A database failure still 503s even though generation_queue is unrelated.

        get_session fails for every caller (check_database AND
        check_generation_queue both use it), proving the 503 gate is driven
        by the database check, not incidentally by the queue check sharing
        the same failure.
        """

        @asynccontextmanager
        async def _failing_get_session() -> AsyncGenerator[None, None]:
            raise RuntimeError("db down")
            yield  # pragma: no cover

        app = _make_app()
        with (
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_failing_get_session,
            ),
            patch(
                "cyo_adventure.api.health.settings.rate_limit_backend",
                "memory",
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/health/ready")

        assert response.status_code == 503


# ---------------------------------------------------------------------------
# HealthStatus and ReadinessCheck models
# ---------------------------------------------------------------------------


class TestHealthStatusModel:
    """Tests for the HealthStatus pydantic model."""

    @pytest.mark.unit
    def test_health_status_defaults(self) -> None:
        """HealthStatus sets timestamp and python_version automatically."""
        import sys

        import cyo_adventure
        from cyo_adventure.api.health import HealthStatus

        hs = HealthStatus(status="ok", uptime_seconds=5.0)

        assert hs.version == cyo_adventure.__version__
        assert hs.python_version.startswith(sys.version.split()[0][:3])
        assert hs.timestamp > 0


class TestReadinessCheckModel:
    """Tests for the ReadinessCheck pydantic model."""

    @pytest.mark.unit
    def test_readiness_check_error_defaults_none(self) -> None:
        """ReadinessCheck.error defaults to None when not provided."""
        from cyo_adventure.api.health import ReadinessCheck

        rc = ReadinessCheck(name="db", status=True)

        assert rc.error is None
        assert rc.latency_ms is None

    @pytest.mark.unit
    def test_readiness_check_failed_state(self) -> None:
        """ReadinessCheck stores status=False and error message."""
        from cyo_adventure.api.health import ReadinessCheck

        rc = ReadinessCheck(
            name="db",
            status=False,
            latency_ms=12.5,
            error="dependency unavailable",
        )

        assert rc.status is False
        assert rc.error == "dependency unavailable"
        assert rc.latency_ms == 12.5


# ---------------------------------------------------------------------------
# check_cache except branch
# ---------------------------------------------------------------------------
#
# NOTE: check_cache no longer has a placeholder try/except around bare
# time.time() calls; TestCheckCache above (redis_down, unconfigured cases)
# now covers the except branch and the OWASP A09 non-leak requirement
# directly against the real Redis-backed implementation, with the client
# mocked rather than relying on time.time() as an indirect failure trigger.


# ---------------------------------------------------------------------------
# KWS parent-verification delivery health
# ---------------------------------------------------------------------------


def _fake_health(
    *,
    stuck: int,
    oldest: datetime | None,
    newest: datetime | None,
    last_resolved: datetime | None,
) -> Any:
    """Build a real VerificationDeliveryHealth, not a mock of one.

    The check branches on ``deliveries_have_stopped``, which is the timestamp
    comparison itself; substituting a mocked boolean would leave the branch
    under test reading a value this suite invented rather than the one the
    service computes.
    """
    from cyo_adventure.consent.service import VerificationDeliveryHealth

    return VerificationDeliveryHealth(
        stuck=stuck,
        oldest_stuck_requested_at=oldest,
        newest_stuck_requested_at=newest,
        last_resolved_at=last_resolved,
    )


class TestCheckKwsVerification:
    """Tests for the check_kws_verification() readiness helper (ADR-018 D1).

    The failure this watches for leaves no log line: on 2026-08-09 a Cloudflare
    custom rule blocked four KWS webhook retries at the edge, so the origin saw
    zero POSTs and every log-based view was identical to "the vendor sent
    nothing". Publishing the table-derived signal here is what turns that
    invisible outage into something a probe can see.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reports_unconfigured_without_touching_the_database(self) -> None:
        """A tier with the flag off pays nothing for a feature it does not run.

        Asserted on the session factory as well as the state: a check that
        queried first and classified afterwards would put a per-probe round
        trip on every deployment that has never enabled KWS.
        """
        from cyo_adventure.api.health import check_kws_verification

        get_session = Mock()
        with (
            patch(
                "cyo_adventure.api.health.settings.kws_verification_required", new=False
            ),
            patch("cyo_adventure.core.database.get_session", get_session),
        ):
            result = await check_kws_verification()

        assert result.name == "kws_verification"
        assert result.status is True
        assert result.state == "unconfigured"
        assert result.error is None
        assert get_session.called is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reports_ok_while_resolutions_are_still_arriving(self) -> None:
        """Open attempts alongside fresh resolutions are the steady state."""
        from cyo_adventure.api.health import check_kws_verification

        mock_session = AsyncMock(spec=AsyncSession)

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        with (
            patch(
                "cyo_adventure.api.health.settings.kws_verification_required", new=True
            ),
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_fake_get_session,
            ),
            patch(
                "cyo_adventure.consent.service.verification_delivery_health",
                AsyncMock(
                    return_value=_fake_health(
                        stuck=3,
                        oldest=datetime.now(UTC) - timedelta(days=9),
                        newest=datetime.now(UTC) - timedelta(days=2),
                        last_resolved=datetime.now(UTC) - timedelta(hours=3),
                    )
                ),
            ),
        ):
            result = await check_kws_verification()

        assert result.status is True
        assert result.state == "ok"
        assert result.error is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reports_degraded_with_the_facts_an_operator_needs(self) -> None:
        """The degraded message must name what stopped, not just that something did.

        Whoever reads this alarm has to decide between "the vendor is down",
        "our edge is blocking them", and "this was never wired up", and the
        two timestamps are what separates those: when the longest-waiting
        parent was mailed, and when the leg last delivered anything. A bare
        "degraded" would send them back to the logs, which is exactly where
        this failure mode leaves no trace.
        """
        from cyo_adventure.api.health import check_kws_verification

        mock_session = AsyncMock(spec=AsyncSession)
        oldest = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        last_resolved = datetime(2026, 8, 1, 9, 30, tzinfo=UTC)

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        with (
            patch(
                "cyo_adventure.api.health.settings.kws_verification_required", new=True
            ),
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_fake_get_session,
            ),
            patch(
                "cyo_adventure.consent.service.verification_delivery_health",
                AsyncMock(
                    return_value=_fake_health(
                        stuck=4,
                        oldest=oldest,
                        newest=datetime(2026, 8, 10, 6, 0, tzinfo=UTC),
                        last_resolved=last_resolved,
                    )
                ),
            ),
        ):
            result = await check_kws_verification()

        assert result.status is False
        assert result.state == "degraded"
        assert result.error is not None
        assert "4" in result.error
        assert oldest.isoformat() in result.error
        assert last_resolved.isoformat() in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_query_failure_is_unknown_not_degraded_and_leaks_nothing(
        self,
    ) -> None:
        """A broken check reports unknown, and says nothing about why.

        The state matters as much as the redaction. "degraded" on this check
        asserts that attempts were sent and stopped resolving, which is a page
        for a broken inbound webhook leg. A query failure asserts nothing of
        the kind: the delivery signal is simply unmeasured, which is
        "unknown". Conflating the two sends an operator after a KWS outage
        that may not exist, and spends the alert that a real stoppage needs.

        The redaction half matches check_database and check_generation_queue:
        /health/ready is unauthenticated, so a driver message naming a host,
        role, or schema would be published to anyone who asks.
        """
        from cyo_adventure.api.health import check_kws_verification

        internal_message = "connection to server at 10.0.0.5 failed: role cyo_app"

        @asynccontextmanager
        async def _failing_get_session() -> AsyncGenerator[None, None]:
            raise RuntimeError(internal_message)
            yield  # pragma: no cover

        with (
            patch(
                "cyo_adventure.api.health.settings.kws_verification_required", new=True
            ),
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=_failing_get_session,
            ),
        ):
            result = await check_kws_verification()

        assert result.status is False
        assert result.state == "unknown"
        assert internal_message not in (result.error or "")
        assert "10.0.0.5" not in (result.error or "")


class TestReadinessKwsDoesNotGate:
    """A degraded kws_verification check is reported but never flips readiness.

    Only ``database`` is in ``_CRITICAL_READINESS_CHECKS``. A blocked webhook
    leg stops new parents completing verification; it does not stop a child
    reading a published book, so pulling API pods out of the load-balancer
    rotation would convert a consent-intake outage into a whole-app outage.
    """

    @pytest.mark.unit
    def test_readiness_returns_200_when_kws_degraded_and_database_healthy(
        self,
    ) -> None:
        """A degraded kws_verification is published in the body but still 200."""
        _, fake_get_session = _fake_session_with_queue_counts(0, 0, 0)

        app = _make_app()
        with (
            patch(
                "cyo_adventure.api.health.settings.kws_verification_required", new=True
            ),
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=fake_get_session,
            ),
            patch("cyo_adventure.api.health.settings.rate_limit_backend", "memory"),
            patch(
                "cyo_adventure.consent.service.verification_delivery_health",
                AsyncMock(
                    return_value=_fake_health(
                        stuck=4,
                        oldest=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
                        newest=datetime(2026, 8, 10, 6, 0, tzinfo=UTC),
                        last_resolved=datetime(2026, 8, 1, 9, 30, tzinfo=UTC),
                    )
                ),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"]["kws_verification"]["status"] is False
        assert body["checks"]["kws_verification"]["state"] == "degraded"

    @pytest.mark.unit
    def test_the_check_is_published_even_when_the_flag_is_off(self) -> None:
        """The key is always present, so a probe can tell "off" from "missing".

        A probe that keys on the check's absence cannot distinguish a tier
        that has KWS switched off from a build where the check was dropped,
        and the second of those is how a monitoring gap ships unnoticed.
        """
        _, fake_get_session = _fake_session_with_queue_counts(0, 0, 0)

        app = _make_app()
        with (
            patch(
                "cyo_adventure.api.health.settings.kws_verification_required", new=False
            ),
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=fake_get_session,
            ),
            patch("cyo_adventure.api.health.settings.rate_limit_backend", "memory"),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["checks"]["kws_verification"]["state"] == "unconfigured"
        assert body["checks"]["kws_verification"]["status"] is True


class TestCheckGenerationCascade:
    """Tests for the check_generation_cascade() readiness helper.

    Since the 2026-08-18 Ollama retirement the default cascade is OpenRouter
    primary, OpenRouter fallback, Modal backstop, so the first two legs sit
    behind one vendor's account and Modal is the only thing making the chain
    span two vendors. Before this check the sole signal that a deploy had
    silently degraded to single-vendor was a per-job log line, which meant
    noticing it required grepping worker logs for one string.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reports_ok_when_the_modal_backstop_is_configured(self) -> None:
        """Two vendors is the intended posture and reports no error text."""
        from cyo_adventure.api.health import check_generation_cascade

        with (
            patch(
                "cyo_adventure.api.health.settings.generation_provider",
                new="openrouter",
            ),
            patch(
                "cyo_adventure.core.config.Settings.modal_leg_configured",
                new=property(lambda _self: True),
            ),
        ):
            result = await check_generation_cascade()

        assert result.name == "generation_cascade"
        assert result.status is True
        assert result.state == "ok"
        assert result.error is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reports_degraded_when_the_modal_backstop_is_absent(self) -> None:
        """The single-vendor state is the whole reason this check exists.

        Asserted on the error text as well as the state: an operator reading
        a bare "degraded" cannot tell which of the cascade's three legs is
        missing, and the actionable part is the env var pair to set.
        """
        from cyo_adventure.api.health import check_generation_cascade

        with (
            patch(
                "cyo_adventure.api.health.settings.generation_provider",
                new="openrouter",
            ),
            patch(
                "cyo_adventure.core.config.Settings.modal_leg_configured",
                new=property(lambda _self: False),
            ),
        ):
            result = await check_generation_cascade()

        assert result.status is False
        assert result.state == "degraded"
        assert result.error is not None
        assert "MODAL_BASE_URL" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reports_unconfigured_when_this_process_runs_no_cascade(
        self,
    ) -> None:
        """A tier on the mock or anthropic provider has no cascade to degrade.

        Reporting "degraded" there would train operators to ignore the state,
        which is how a real single-vendor deploy gets missed.
        """
        from cyo_adventure.api.health import check_generation_cascade

        with patch("cyo_adventure.api.health.settings.generation_provider", new="mock"):
            result = await check_generation_cascade()

        assert result.status is True
        assert result.state == "unconfigured"
        assert result.error is None

    @pytest.mark.unit
    def test_a_degraded_cascade_does_not_take_the_pod_out_of_rotation(self) -> None:
        """Degraded generation capacity must not stop serving reads to children.

        This also pins the readiness route's response SHAPE. The check is
        defined immediately above readiness() in the module, so a helper
        inserted between the @router.get("/ready") decorator and readiness()
        would silently rebind the route to the helper: the endpoint would
        answer 200 with a single ReadinessCheck body and stop running the
        database check entirely, while every function-level test above still
        passed. Asserting that "checks" is present and holds the other checks
        is what distinguishes those two worlds.
        """
        _, fake_get_session = _fake_session_with_queue_counts(0, 0, 0)

        app = _make_app()
        with (
            patch(
                "cyo_adventure.api.health.settings.generation_provider",
                new="openrouter",
            ),
            patch(
                "cyo_adventure.core.config.Settings.modal_leg_configured",
                new=property(lambda _self: False),
            ),
            patch(
                "cyo_adventure.api.health.settings.kws_verification_required",
                new=False,
            ),
            patch(
                "cyo_adventure.core.database.get_session",
                side_effect=fake_get_session,
            ),
            patch("cyo_adventure.api.health.settings.rate_limit_backend", "memory"),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["checks"]["generation_cascade"]["state"] == "degraded"
        assert body["checks"]["generation_cascade"]["status"] is False
        assert "database" in body["checks"]
        assert body["status"] == "ok"
