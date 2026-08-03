"""Unit tests for cyo_adventure.utils.logging.

Covers setup_logging's flag-driven processor chain (JSON vs console renderer,
correlation toggle, timestamp toggle) and log_performance(). The setup_logging
tests inspect the processor chain structlog is actually configured with, so a
regression that ignores a flag fails here rather than passing on no-crash alone.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
import structlog

from cyo_adventure.utils.logging import (
    correlation_context_processor,
    setup_logging,
)
from cyo_adventure.utils.redaction import (
    REDACTED,
    RedactingLogFilter,
    censor_sensitive_processor,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

# Clearly-fake credential (never real-looking).
_FAKE_SECRET = "test-not-a-real-api-key"


@pytest.fixture(autouse=True)
def _restore_logging_config() -> Iterator[None]:
    """Snapshot and restore process-wide structlog and stdlib-logging config.

    setup_logging mutates global structlog configuration and the root logger.
    Without this, configuration leaks between tests (and across modules) and the
    flag-toggle assertions below become order-dependent.
    """
    saved_structlog = structlog.get_config()
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        yield
    finally:
        structlog.configure(**saved_structlog)
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


def _configured_processors() -> list[object]:
    """Return the processor chain structlog is currently configured with."""
    return structlog.get_config()["processors"]


def _has_instance(processors: list[object], cls: type) -> bool:
    """Whether any configured processor is an instance of ``cls``."""
    return any(isinstance(p, cls) for p in processors)


class TestSetupLogging:
    @pytest.mark.unit
    def test_json_logs_true_uses_json_renderer(self) -> None:
        """json_logs=True ends the chain with a JSONRenderer, not the console one."""
        setup_logging(level="INFO", json_logs=True, include_correlation=True)

        procs = _configured_processors()
        assert _has_instance(procs, structlog.processors.JSONRenderer)
        assert not _has_instance(procs, structlog.dev.ConsoleRenderer)

    @pytest.mark.unit
    def test_json_logs_false_uses_console_renderer(self) -> None:
        """json_logs=False ends the chain with a ConsoleRenderer, not JSON."""
        setup_logging(level="DEBUG", json_logs=False, include_correlation=True)

        procs = _configured_processors()
        assert _has_instance(procs, structlog.dev.ConsoleRenderer)
        assert not _has_instance(procs, structlog.processors.JSONRenderer)

    @pytest.mark.unit
    def test_include_correlation_toggles_correlation_processor(self) -> None:
        """The correlation processor is present only when include_correlation=True."""
        setup_logging(level="INFO", json_logs=True, include_correlation=True)
        assert correlation_context_processor in _configured_processors()

        setup_logging(level="INFO", json_logs=True, include_correlation=False)
        assert correlation_context_processor not in _configured_processors()

    @pytest.mark.unit
    def test_include_timestamp_toggles_timestamper(self) -> None:
        """include_timestamp adds a TimeStamper only when True."""
        setup_logging(level="INFO", json_logs=False, include_timestamp=True)
        assert _has_instance(_configured_processors(), structlog.processors.TimeStamper)

        setup_logging(level="INFO", json_logs=False, include_timestamp=False)
        assert not _has_instance(
            _configured_processors(), structlog.processors.TimeStamper
        )

    @pytest.mark.unit
    @pytest.mark.security
    @pytest.mark.parametrize("json_logs", [True, False], ids=["json", "console"])
    def test_censor_processor_is_installed_before_the_renderer(
        self, json_logs: bool
    ) -> None:
        """The censoring backstop runs ahead of whichever renderer is active.

        A processor placed after the renderer would see a rendered string, not
        the event dict, and could not redact anything; pin the ordering rather
        than mere presence.
        """
        setup_logging(level="INFO", json_logs=json_logs)

        procs = _configured_processors()
        assert censor_sensitive_processor in procs
        renderer = (
            structlog.processors.JSONRenderer
            if json_logs
            else structlog.dev.ConsoleRenderer
        )
        renderer_index = next(i for i, p in enumerate(procs) if isinstance(p, renderer))
        assert procs.index(censor_sensitive_processor) < renderer_index

    @pytest.mark.unit
    @pytest.mark.security
    def test_configured_chain_redacts_a_secret_field_end_to_end(self) -> None:
        """A secret passed to a real logger is redacted in the rendered output.

        Drives the whole configured chain (not just the processor in
        isolation) so a regression that installs the censor in the wrong place
        fails here.
        """
        setup_logging(level="INFO", json_logs=True, include_timestamp=False)
        captured: list[str] = []
        logger = structlog.get_logger("censor_e2e_test")
        logger.bind()  # force the lazy proxy to materialize the configured chain
        stdlib_logger = logging.getLogger("censor_e2e_test")
        handler = logging.StreamHandler()
        handler.emit = lambda record: captured.append(record.getMessage())  # type: ignore[method-assign]
        stdlib_logger.addHandler(handler)
        stdlib_logger.setLevel(logging.INFO)
        try:
            logger.info("provider_call", api_key=_FAKE_SECRET, provider="anthropic")
        finally:
            stdlib_logger.removeHandler(handler)

        assert captured, "expected the configured chain to emit a record"
        rendered = "\n".join(captured)
        assert _FAKE_SECRET not in rendered
        assert REDACTED in rendered
        assert "anthropic" in rendered

    @pytest.mark.unit
    def test_setup_logging_replaces_a_preexisting_root_handler(self) -> None:
        """``force=True`` is load-bearing, not decoration.

        ``basicConfig`` is a documented no-op when the root logger already has
        a handler, which under uvicorn, gunicorn, or pytest it usually does.
        Without ``force`` the root level would stay wherever it was and
        structlog's ``filter_by_level`` (chain index 0) would silently drop
        every INFO record this app emits.
        """
        root = logging.getLogger()
        preexisting = logging.NullHandler()
        root.handlers[:] = [preexisting]
        root.setLevel(logging.WARNING)

        setup_logging(level="DEBUG", json_logs=True)

        assert preexisting not in root.handlers
        assert root.level == logging.DEBUG

    @pytest.mark.unit
    def test_the_installed_root_handler_carries_the_redacting_filter(self) -> None:
        """Structlog's processor never sees a stdlib-origin record."""
        setup_logging(level="INFO", json_logs=True)

        handlers = logging.getLogger().handlers
        assert handlers, "setup_logging must install a root handler"
        assert any(
            isinstance(f, RedactingLogFilter)
            for handler in handlers
            for f in handler.filters
        )

    @pytest.mark.unit
    @pytest.mark.security
    def test_a_stdlib_log_record_is_redacted_by_the_root_handler_filter(self) -> None:
        """uvicorn.access, botocore, SQLAlchemy and rq bypass structlog entirely.

        Their records reach the root handler without passing through any
        structlog processor, so the censoring processor cannot see them. The
        message below is shaped like a uvicorn.access request line whose query
        string carries a presigned-URL signature.
        """
        setup_logging(level="INFO", json_logs=True)
        captured: list[str] = []
        for handler in logging.getLogger().handlers:
            handler.emit = lambda record: captured.append(record.getMessage())  # type: ignore[method-assign]

        logging.getLogger("stdlib_bypass_probe").info(
            "GET /v1/covers?X-Amz-Signature=%s HTTP/1.1", _FAKE_SECRET
        )

        rendered = "\n".join(captured)
        assert rendered, "expected the root handler to see the record"
        assert _FAKE_SECRET not in rendered
        assert REDACTED in rendered

    @pytest.mark.unit
    def test_a_known_level_name_is_applied_case_insensitively(self) -> None:
        """The happy path keeps working, including lowercase env values."""
        setup_logging(level="warning", json_logs=True)

        assert logging.getLogger().level == logging.WARNING

    @pytest.mark.unit
    def test_an_unknown_level_falls_back_to_info_and_warns(self) -> None:
        """A typo'd LOG_LEVEL must be visible, not silently downgraded.

        ``getattr(logging, level.upper(), logging.INFO)`` used to swallow this
        outright: ``LOG_LEVEL=DEBGU`` simply became INFO with nothing said.
        """
        captured: list[str] = []
        # Attached to the emitting logger, not to root: setup_logging's
        # basicConfig(force=True) tears every ROOT handler down, so a probe
        # parked there would be removed before the warning is emitted.
        probe_logger = logging.getLogger("cyo_adventure.utils.logging")
        probe = logging.StreamHandler()
        probe.emit = lambda record: captured.append(record.getMessage())  # type: ignore[method-assign]
        probe_logger.addHandler(probe)
        try:
            setup_logging(level="DEBGU", json_logs=True, include_timestamp=False)
        finally:
            probe_logger.removeHandler(probe)

        assert logging.getLogger().level == logging.INFO
        assert any("log_level_unknown" in message for message in captured), captured


class TestLogPerformance:
    @pytest.mark.unit
    def test_log_performance_calls_logger_info(self) -> None:
        """log_performance() calls logger.info with performance fields."""
        from unittest.mock import MagicMock

        from cyo_adventure.utils.logging import log_performance

        logger = MagicMock()
        log_performance(logger, operation="test_op", duration_ms=42.5, success=True)

        logger.info.assert_called_once()
        call_kwargs = logger.info.call_args
        assert call_kwargs[0][0] == "performance"
        assert call_kwargs[1]["operation"] == "test_op"
        assert call_kwargs[1]["duration_ms"] == pytest.approx(42.5)
        assert call_kwargs[1]["success"] is True

    @pytest.mark.unit
    def test_log_performance_failure_case(self) -> None:
        """log_performance() with success=False logs correctly."""
        from unittest.mock import MagicMock

        from cyo_adventure.utils.logging import log_performance

        logger = MagicMock()
        log_performance(logger, operation="bad_op", duration_ms=1000.0, success=False)

        logger.info.assert_called_once()
        call_kwargs = logger.info.call_args
        assert call_kwargs[1]["success"] is False

    @pytest.mark.unit
    def test_log_performance_extra_context_forwarded(self) -> None:
        """log_performance() passes **context kwargs through to logger.info."""
        from unittest.mock import MagicMock

        from cyo_adventure.utils.logging import log_performance

        logger = MagicMock()
        log_performance(
            logger, operation="parse", duration_ms=5.0, success=True, doc_id="d123"
        )

        logger.info.assert_called_once()
        call_kwargs = logger.info.call_args
        assert call_kwargs[1]["doc_id"] == "d123"

    @pytest.mark.unit
    def test_log_performance_rounds_duration(self) -> None:
        """log_performance() rounds duration_ms to 2 decimal places."""
        from unittest.mock import MagicMock

        from cyo_adventure.utils.logging import log_performance

        logger = MagicMock()
        log_performance(logger, operation="x", duration_ms=1.23456789, success=True)

        call_kwargs = logger.info.call_args
        assert call_kwargs[1]["duration_ms"] == pytest.approx(1.23)
