"""Tests for cyo_adventure.api.health module.

Covers liveness, readiness, startup, and health alias endpoints, plus the
check_database (happy path and failure path), check_cache, and
check_external_service helper functions.

No live database is used; get_session is patched with an async context manager.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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

        mock_session = AsyncMock()
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
    """Tests for the check_cache() placeholder helper."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_cache_returns_true_status(self) -> None:
        """check_cache placeholder always returns status=True."""
        from cyo_adventure.api.health import check_cache

        result = await check_cache()

        assert result.status is True
        assert result.name == "cache"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_cache_includes_latency(self) -> None:
        """check_cache includes a non-negative latency_ms."""
        from cyo_adventure.api.health import check_cache

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
    """Tests for the /health/ready endpoint via TestClient."""

    @pytest.mark.unit
    def test_readiness_returns_200_when_database_healthy(self) -> None:
        """GET /health/ready returns 200 when database check passes."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app = _make_app()
        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=_fake_get_session,
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
        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=_failing_get_session,
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
        with patch(
            "cyo_adventure.core.database.get_session",
            side_effect=_failing_get_session,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            body = client.get("/health/ready").text

        assert "db-conn-error: connection timeout" not in body
        assert "dependency unavailable" in body


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
