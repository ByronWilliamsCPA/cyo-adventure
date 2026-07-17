"""Tests for cyo_adventure.api.health module.

Covers liveness, readiness, startup, and health alias endpoints, plus the
check_database (happy path and failure path), check_cache, and
check_external_service helper functions.

No live database is used; get_session is patched with an async context manager.
"""

from __future__ import annotations

import time as _time_stdlib
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

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
    """Build a minimal FastAPI app with the health router mounted."""
    from cyo_adventure.api.health import router

    app = FastAPI()
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# Liveness probe
# ---------------------------------------------------------------------------


class TestLiveness:
    """Tests for the /health/live endpoint."""

    @pytest.mark.unit
    def test_liveness_returns_200(self) -> None:
        """GET /health/live returns HTTP 200."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        response = client.get("/health/live")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_liveness_status_is_ok(self) -> None:
        """GET /health/live body has status 'ok'."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        data = client.get("/health/live").json()

        assert data["status"] == "ok"

    @pytest.mark.unit
    def test_liveness_includes_uptime(self) -> None:
        """GET /health/live body includes a non-negative uptime_seconds field."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        data = client.get("/health/live").json()

        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0


# ---------------------------------------------------------------------------
# Startup probe
# ---------------------------------------------------------------------------


class TestStartup:
    """Tests for the /health/startup endpoint."""

    @pytest.mark.unit
    def test_startup_returns_200(self) -> None:
        """GET /health/startup returns HTTP 200."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        response = client.get("/health/startup")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_startup_status_is_started(self) -> None:
        """GET /health/startup body has status 'started'."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        data = client.get("/health/startup").json()

        assert data["status"] == "started"


# ---------------------------------------------------------------------------
# Health alias
# ---------------------------------------------------------------------------


class TestHealthAlias:
    """Tests for the hidden /health/ alias endpoint."""

    @pytest.mark.unit
    def test_health_alias_returns_200(self) -> None:
        """GET /health/ returns HTTP 200 (alias for liveness)."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        response = client.get("/health/")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_health_alias_status_is_ok(self) -> None:
        """GET /health/ has the same status as /health/live."""
        client = TestClient(_make_app(), raise_server_exceptions=True)
        data = client.get("/health/").json()

        assert data["status"] == "ok"


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
# check_external_service helper
# ---------------------------------------------------------------------------


class TestCheckExternalService:
    """Tests for the check_external_service() placeholder helper."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_external_service_returns_true_status(self) -> None:
        """check_external_service placeholder always returns status=True."""
        from cyo_adventure.api.health import check_external_service

        result = await check_external_service()

        assert result.status is True
        assert result.name == "external_api"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_external_service_includes_latency(self) -> None:
        """check_external_service includes a non-negative latency_ms."""
        from cyo_adventure.api.health import check_external_service

        result = await check_external_service()

        assert result.latency_ms is not None
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# Readiness endpoint (integrates check_database)
# ---------------------------------------------------------------------------


class TestReadiness:
    """Tests for the /health/ready endpoint via TestClient.

    settings.rate_limit_backend is patched to "memory" in every test here
    (unrelated to what's under test) so check_cache short-circuits to
    state="unconfigured" without a real Redis connection attempt, per this
    package's "no real network calls in unit tests" rule
    (tests/CLAUDE.md). TestReadinessCacheDoesNotGate below is what actually
    exercises the cache-down-does-not-gate-readiness behavior.
    """

    @pytest.mark.unit
    def test_readiness_returns_200_when_database_healthy(self) -> None:
        """GET /health/ready returns 200 when database check passes."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock()

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
            response = client.get("/health/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @pytest.mark.unit
    def test_readiness_returns_503_when_database_fails(self) -> None:
        """GET /health/ready returns 503 when database check fails."""

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
            response = client.get("/health/ready")

        assert response.status_code == 503

    @pytest.mark.unit
    def test_readiness_503_detail_does_not_leak_exception_text(self) -> None:
        """GET /health/ready 503 body must not contain raw exception text."""

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
            body = client.get("/health/ready").text

        assert "db-conn-error: connection timeout" not in body
        assert "dependency unavailable" in body


# ---------------------------------------------------------------------------
# Readiness endpoint: cache does not gate readiness (#ASSUME in readiness())
# ---------------------------------------------------------------------------


class TestReadinessCacheDoesNotGate:
    """A down or unconfigured cache is reported but never flips /health/ready.

    Only ``database`` is in ``_CRITICAL_READINESS_CHECKS``; see readiness()'s
    #ASSUME docstring note for why cache is deliberately excluded.
    """

    @pytest.mark.unit
    def test_readiness_returns_200_when_cache_down_and_database_healthy(
        self,
    ) -> None:
        """A down Redis is reported in checks but still returns HTTP 200."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock()

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
            response = client.get("/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"]["cache"]["status"] is False
        assert body["checks"]["cache"]["state"] == "degraded"

    @pytest.mark.unit
    def test_readiness_returns_200_when_cache_unconfigured(self) -> None:
        """An unconfigured (memory-backend) cache is reported but returns HTTP 200."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock()

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
            response = client.get("/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["checks"]["cache"]["status"] is True
        assert body["checks"]["cache"]["state"] == "unconfigured"


# ---------------------------------------------------------------------------
# HealthStatus and ReadinessCheck models
# ---------------------------------------------------------------------------


class TestHealthStatusModel:
    """Tests for the HealthStatus pydantic model."""

    @pytest.mark.unit
    def test_health_status_defaults(self) -> None:
        """HealthStatus sets timestamp and python_version automatically."""
        import sys

        from cyo_adventure.api.health import HealthStatus

        hs = HealthStatus(status="ok", uptime_seconds=5.0)

        assert hs.version == "0.1.0"
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
# check_external_service except branch
# ---------------------------------------------------------------------------


class TestCheckExternalServiceExceptBranch:
    """Tests for the check_external_service() except branch (lines 183-186)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_external_service_except_branch_returns_false_status(
        self,
    ) -> None:
        """check_external_service returns status=False when time.time raises inside try."""
        from cyo_adventure.api.health import check_external_service

        raiser = _time_raiser_on_nth_call(
            2, OSError("simulated external service failure")
        )
        with patch("cyo_adventure.api.health.time.time", side_effect=raiser):
            result = await check_external_service()

        assert result.status is False
        assert result.name == "external_api"
        assert result.error == "dependency unavailable"
        assert result.latency_ms is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_external_service_except_branch_does_not_leak_exception_text(
        self,
    ) -> None:
        """check_external_service except branch must not expose the raw error (OWASP A09)."""
        from cyo_adventure.api.health import check_external_service

        internal_message = "api.example.com:443 ETIMEDOUT"
        raiser = _time_raiser_on_nth_call(2, OSError(internal_message))
        with patch("cyo_adventure.api.health.time.time", side_effect=raiser):
            result = await check_external_service()

        assert internal_message not in (result.error or "")
        assert result.error == "dependency unavailable"
