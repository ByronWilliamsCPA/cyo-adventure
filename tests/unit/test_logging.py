"""Unit tests for cyo_adventure.utils.logging.

Covers setup_logging's flag-driven processor chain (JSON vs console renderer,
correlation toggle, timestamp toggle) and log_performance(). The setup_logging
tests inspect the processor chain structlog is actually configured with, so a
regression that ignores a flag fails here rather than passing on no-crash alone.
"""

from __future__ import annotations

import pytest
import structlog

from cyo_adventure.utils.logging import (
    correlation_context_processor,
    setup_logging,
)


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
        assert call_kwargs[1]["duration_ms"] == 42.5
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
        assert call_kwargs[1]["duration_ms"] == 1.23
