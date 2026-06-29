"""Unit tests for cyo_adventure.utils.logging.

Covers the uncovered branches: setup_logging with json_logs=True,
setup_logging with include_correlation=False, and log_performance().
"""

from __future__ import annotations

import pytest


class TestSetupLogging:
    @pytest.mark.unit
    def test_setup_logging_json_logs_true_does_not_raise(self) -> None:
        """setup_logging(json_logs=True) configures JSON output without error."""
        from cyo_adventure.utils.logging import setup_logging

        # Must not raise; structlog is reconfigured.
        setup_logging(level="INFO", json_logs=True, include_correlation=True)

    @pytest.mark.unit
    def test_setup_logging_no_correlation_does_not_raise(self) -> None:
        """setup_logging(include_correlation=False) skips the correlation processor."""
        from cyo_adventure.utils.logging import setup_logging

        setup_logging(level="DEBUG", json_logs=False, include_correlation=False)

    @pytest.mark.unit
    def test_setup_logging_json_no_correlation_does_not_raise(self) -> None:
        """setup_logging(json_logs=True, include_correlation=False) is valid."""
        from cyo_adventure.utils.logging import setup_logging

        setup_logging(level="WARNING", json_logs=True, include_correlation=False)

    @pytest.mark.unit
    def test_setup_logging_no_timestamp_does_not_raise(self) -> None:
        """setup_logging(include_timestamp=False) uses the noop_processor."""
        from cyo_adventure.utils.logging import setup_logging

        setup_logging(level="INFO", json_logs=False, include_timestamp=False)


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
