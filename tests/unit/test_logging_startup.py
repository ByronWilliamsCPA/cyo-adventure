"""Regression tests: the running application must configure structlog itself.

``setup_logging`` used to have exactly three callers: a backfill script, this
module's own ``__main__`` demo block, and the autouse fixture in
``tests/conftest.py``. Neither ``app.py`` nor ``generation/worker_main.py``
called it, and ``Dockerfile`` runs bare uvicorn, so a deployed process ran on
structlog's defaults: no level filtering, no JSON renderer, and (the part that
matters most) no ``correlation_context_processor``. ``settings.log_level`` and
``settings.json_logs`` were dead config and correlation ids were absent from
every production log line, contradicting CLAUDE.md architectural fact #3.

Test-isolation note: ``tests/conftest.py``'s autouse ``setup_logging`` fixture
mutates process-global structlog state before every test, so a naive assertion
here would pass vacuously against the unfixed code. Every test below calls
``structlog.reset_defaults()`` first and asserts the unconfigured precondition,
so it genuinely exercises application startup. That same conftest fixture also
snapshots and restores structlog and root-handler state around every test, so
the teardown of the deliberate reset below leaks nothing into later tests; the
snapshot/restore used to be a module-local fixture here and was moved to
conftest once ``TestClient`` began running the lifespan (and therefore
``setup_logging``) for every module that builds one.
"""

from __future__ import annotations

import contextvars
import logging

import pytest
import structlog
from fastapi.testclient import TestClient

from cyo_adventure import app as app_module
from cyo_adventure.middleware.correlation import (
    correlation_context_processor,
    set_correlation_id,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]


def _capture_one_log(logger_name: str, event: str) -> list[str]:
    """Emit one event through the CONFIGURED chain and return rendered records.

    Attaches a handler to the stdlib logger the structlog stdlib
    ``LoggerFactory`` writes to, so what is captured is the real rendered
    output of whatever processor chain is currently installed, not a test
    double's.

    Args:
        logger_name: The logger name to bind and capture (use a fresh one per
            test; ``cache_logger_on_first_use`` caches bound loggers).
        event: The event name to log at INFO.

    Returns:
        list[str]: The rendered message of every record the handler saw.
    """
    records: list[str] = []
    stdlib_logger = logging.getLogger(logger_name)
    handler = logging.StreamHandler()
    handler.emit = lambda record: records.append(record.getMessage())  # type: ignore[method-assign]
    stdlib_logger.addHandler(handler)
    stdlib_logger.setLevel(logging.INFO)
    try:
        structlog.get_logger(logger_name).info(event)
    finally:
        stdlib_logger.removeHandler(handler)
    return records


class TestAppStartupConfiguresLogging:
    def test_app_startup_configures_structlog(self) -> None:
        """Entering the app's lifespan leaves structlog configured."""
        structlog.reset_defaults()
        assert not structlog.is_configured(), (
            "precondition: this test must start from an unconfigured structlog, "
            "or it passes vacuously on conftest's autouse fixture"
        )

        with TestClient(app_module.create_app()):
            assert structlog.is_configured()

    def test_app_startup_installs_the_correlation_processor(self) -> None:
        """The configured chain includes correlation, per architectural fact #3."""
        structlog.reset_defaults()
        assert not structlog.is_configured()

        with TestClient(app_module.create_app()):
            assert correlation_context_processor in structlog.get_config()["processors"]

    def test_a_log_emitted_after_startup_carries_the_correlation_id(self) -> None:
        """A real record rendered by the configured chain carries the id.

        Presence of the processor in the chain is necessary but not
        sufficient; this drives an actual log call so an ordering or renderer
        regression that drops the field is caught too.
        """
        structlog.reset_defaults()
        assert not structlog.is_configured()
        correlation_id = "startup-correlation-regression-id"

        def _emit() -> list[str]:
            set_correlation_id(correlation_id)
            return _capture_one_log("startup_correlation_probe", "startup_probe")

        with TestClient(app_module.create_app()):
            records = contextvars.copy_context().run(_emit)

        assert records, "expected the configured chain to emit a record"
        assert correlation_id in records[0]

    def test_startup_drives_setup_logging_from_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """log_level / json_logs stop being dead config: startup reads them."""
        calls: list[dict[str, object]] = []

        def _record(**kwargs: object) -> None:
            calls.append(kwargs)

        monkeypatch.setattr(app_module, "setup_logging", _record)
        monkeypatch.setattr(app_module.settings, "log_level", "WARNING")
        monkeypatch.setattr(app_module.settings, "json_logs", True)

        with TestClient(app_module.create_app()):
            pass

        assert calls == [
            {"level": "WARNING", "json_logs": True, "include_timestamp": True}
        ]


class TestAppLifespanIsNotAnImportSideEffect:
    def test_importing_the_app_module_does_not_configure_logging(self) -> None:
        """Configuration belongs to startup, not to import.

        ``create_app()`` runs at import time (``app = create_app()`` at module
        scope), so wiring ``setup_logging`` into the factory body rather than
        the lifespan would reintroduce an import-time side effect.
        """
        structlog.reset_defaults()

        app_module.create_app()

        assert not structlog.is_configured()
