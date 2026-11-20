"""Unit tests for the readiness ``schema`` check (api/health.py, UW-C363).

Separate from test_health.py so the schema-drift contract reads in one place:
behind is degraded but never 503, ahead never fires, the body carries counts
and never names, and the measurement is cached rather than per poll. No
database: the monitor's measure function and the other checks are patched.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cyo_adventure.core.schema_parity import SchemaComparison, SchemaParityMonitor

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterator

pytestmark = pytest.mark.unit

_BEHIND = SchemaComparison(
    orm_tables=31,
    orm_columns=307,
    missing_columns=(
        ("storybook_version", "cover_review_verdict"),
        ("storybook_version", "cover_review_notes"),
    ),
)
_AHEAD = SchemaComparison(
    orm_tables=31, orm_columns=307, extra_columns=(("family", "future_col"),)
)
_PARITY = SchemaComparison(orm_tables=31, orm_columns=307)


def _make_app() -> FastAPI:
    from cyo_adventure.api.health import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@asynccontextmanager
async def _fake_session() -> AsyncGenerator[Mock]:
    yield Mock()


def _ok(name: str) -> object:
    from cyo_adventure.api.health import ReadinessCheck

    return ReadinessCheck(name=name, status=True, state="ok")


@pytest.fixture
def other_checks_ok() -> Iterator[None]:
    """Make every non-schema readiness check pass without I/O."""
    with (
        patch("cyo_adventure.core.database.get_session", side_effect=_fake_session),
        patch(
            "cyo_adventure.api.health.check_database",
            AsyncMock(return_value=_ok("database")),
        ),
        patch(
            "cyo_adventure.api.health.check_database_privilege",
            AsyncMock(return_value=_ok("database_privilege")),
        ),
        patch(
            "cyo_adventure.api.health.check_cache",
            AsyncMock(return_value=_ok("cache")),
        ),
        patch(
            "cyo_adventure.api.health.check_generation_queue",
            AsyncMock(return_value=_ok("generation_queue")),
        ),
        patch(
            "cyo_adventure.api.health.check_kws_verification",
            AsyncMock(return_value=_ok("kws_verification")),
        ),
        patch(
            "cyo_adventure.api.health.check_generation_cascade",
            AsyncMock(return_value=_ok("generation_cascade")),
        ),
    ):
        yield


def _monitor_returning(
    comparison: SchemaComparison,
) -> tuple[SchemaParityMonitor, AsyncMock]:
    measure = AsyncMock(return_value=comparison)
    return SchemaParityMonitor(measure=measure), measure


def _monitor_raising() -> SchemaParityMonitor:
    return SchemaParityMonitor(
        measure=AsyncMock(side_effect=OSError("postgresql://u:hunter2@db failed"))
    )


@pytest.fixture(autouse=True)
def _reset_log_state() -> Iterator[None]:
    with patch.dict("cyo_adventure.api.health._schema_log_state", {"last": None}):
        yield


@pytest.mark.usefixtures("other_checks_ok")
class TestCheckSchemaParity:
    def test_readiness_behind_schema_returns_200_with_degraded_status(self) -> None:
        monitor, _ = _monitor_returning(_BEHIND)
        with patch("cyo_adventure.api.health._schema_monitor", monitor):
            response = TestClient(_make_app()).get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "degraded"
        schema = body["checks"]["schema"]
        assert schema["status"] is False
        assert schema["state"] == "degraded"
        assert "2 column(s)" in schema["error"]

    def test_readiness_body_never_names_missing_tables_or_columns(self) -> None:
        monitor, _ = _monitor_returning(_BEHIND)
        with patch("cyo_adventure.api.health._schema_monitor", monitor):
            text = TestClient(_make_app()).get("/api/v1/health/ready").text

        assert "cover_review" not in text
        assert "storybook_version" not in text

    def test_behind_schema_logs_names_at_error(self) -> None:
        from cyo_adventure.api import health

        monitor, _ = _monitor_returning(_BEHIND)
        with (
            patch.object(health, "_schema_monitor", monitor),
            patch.object(health, "logger") as logger,
        ):
            _ = TestClient(_make_app()).get("/api/v1/health/ready")

        logger.error.assert_called_once()
        event = logger.error.call_args.args[0]
        kwargs = logger.error.call_args.kwargs
        assert event == "schema_parity.database_behind"
        assert kwargs["missing_column_count"] == 2
        assert "storybook_version.cover_review_verdict" in kwargs["missing_columns"]

    def test_readiness_ahead_schema_reports_ok(self) -> None:
        monitor, _ = _monitor_returning(_AHEAD)
        with patch("cyo_adventure.api.health._schema_monitor", monitor):
            body = TestClient(_make_app()).get("/api/v1/health/ready").json()

        assert body["status"] == "ok"
        assert body["checks"]["schema"]["status"] is True
        assert body["checks"]["schema"]["state"] == "ok"

    def test_readiness_unmeasurable_schema_is_unknown_and_non_gating(self) -> None:
        monitor = _monitor_raising()
        with patch("cyo_adventure.api.health._schema_monitor", monitor):
            response = TestClient(_make_app()).get("/api/v1/health/ready")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"]["schema"]["state"] == "unknown"
        assert body["checks"]["schema"]["error"] == "dependency unavailable"
        assert "hunter2" not in response.text

    def test_repeated_polls_measure_once(self) -> None:
        monitor, measure = _monitor_returning(_PARITY)
        with patch("cyo_adventure.api.health._schema_monitor", monitor):
            client = TestClient(_make_app())
            for _ in range(5):
                assert client.get("/api/v1/health/ready").status_code == 200

        assert measure.await_count == 1

    def test_healthy_verdict_is_logged_once_but_behind_every_measurement(
        self,
    ) -> None:
        from cyo_adventure.api import health
        from cyo_adventure.core.schema_parity import SchemaParityResult

        ok = SchemaParityResult(state="ok", measured_at=0.0, comparison=_PARITY)
        behind = SchemaParityResult(state="behind", measured_at=0.0, comparison=_BEHIND)
        with patch.object(health, "logger") as logger:
            health._log_schema_result(ok)
            health._log_schema_result(ok)
            health._log_schema_result(behind)
            health._log_schema_result(behind)

        assert logger.warning.call_count == 1
        assert logger.warning.call_args.args[0] == "schema_parity.in_parity"
        assert logger.error.call_count == 2


class TestMeasureSchemaParity:
    @pytest.mark.asyncio
    async def test_measure_compares_catalog_rows_with_the_real_orm(self) -> None:
        """Rows describing exactly Base.metadata compare as in parity."""
        import cyo_adventure.db.models  # noqa: F401
        from cyo_adventure.api import health
        from cyo_adventure.core.database import Base
        from cyo_adventure.core.schema_parity import expected_catalog

        rows = [
            (table, column, spec.nullable, spec.data_type)
            for table, columns in expected_catalog(Base.metadata).items()
            for column, spec in columns.items()
        ]
        result = Mock()
        result.tuples.return_value.all.return_value = rows
        session = Mock()
        session.execute = AsyncMock(return_value=result)

        @asynccontextmanager
        async def fake_get_session() -> AsyncGenerator[Mock]:
            yield session

        with patch(
            "cyo_adventure.core.database.get_session", side_effect=fake_get_session
        ):
            comparison = await health._measure_schema_parity()

        assert comparison.orm_tables > 0
        assert not comparison.behind
        assert not comparison.ahead


class TestPrimeSchemaParityLifespan:
    def test_lifespan_starts_the_startup_measurement(self) -> None:
        from cyo_adventure.app import create_app

        prime = AsyncMock()
        with (
            patch("cyo_adventure.api.health.prime_schema_parity", prime),
            TestClient(create_app()),
        ):
            pass

        prime.assert_awaited_once()

    def test_a_hanging_measurement_never_blocks_shutdown(self) -> None:
        import asyncio

        from cyo_adventure.app import create_app

        async def hang() -> None:
            await asyncio.sleep(3600)

        with (
            patch("cyo_adventure.api.health.prime_schema_parity", hang),
            TestClient(create_app()),
        ):
            pass
