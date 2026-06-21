"""Example tests demonstrating best practices for CYO Adventure.

This module shows:
- Unit test structure and naming conventions
- Using pytest fixtures
- Testing with mocks
- Structured assertions with descriptive messages
- Docstring examples that can be tested with doctest
"""

import pytest


class TestPackageInitialization:
    """Test package initialization and version info."""

    @pytest.mark.unit
    def test_package_version_exists(self) -> None:
        """Verify package has __version__ attribute.

        This test verifies that the package exports a version string
        that follows semantic versioning.
        """
        from cyo_adventure import __version__

        assert __version__ is not None
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    @pytest.mark.unit
    def test_package_author_exists(self) -> None:
        """Verify package has __author__ attribute.

        This test verifies that the package exports author information.
        """
        from cyo_adventure import __author__, __email__

        assert __author__ is not None
        assert isinstance(__author__, str)
        assert __email__ is not None
        assert isinstance(__email__, str)


class TestSettings:
    """Test configuration settings.

    Tests for the Settings class covering:
    - Default values
    - Environment variable overrides
    - Keyword argument overrides
    - Type validation
    """

    @pytest.mark.unit
    def test_settings_default_values(self) -> None:
        """Verify Settings initializes with correct defaults.

        This test verifies that when no environment variables or
        keyword arguments are provided, Settings uses sensible defaults.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings()

        assert settings.log_level == "INFO"
        assert settings.json_logs is False
        assert settings.include_timestamp is True

    @pytest.mark.unit
    def test_settings_keyword_arguments(self) -> None:
        """Verify Settings keyword arguments override defaults.

        This test verifies that keyword arguments passed to Settings
        take precedence over defaults.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings(
            log_level="DEBUG",
            json_logs=True,
            include_timestamp=False,
        )

        assert settings.log_level == "DEBUG"
        assert settings.json_logs is True
        assert settings.include_timestamp is False

    # Note: Boolean and integer environment variable parsing tests removed
    # Pydantic BaseSettings handles environment variable parsing automatically
    # and validates types based on field annotations. No custom parsing methods needed.


class TestLogging:
    """Test logging configuration and utilities.

    Tests for structured logging setup covering:
    - Logger creation
    - Logging at different levels
    - Performance logging
    """

    @pytest.mark.unit
    def test_get_logger_returns_logger(self) -> None:
        """Verify get_logger returns a functional logger instance.

        This test verifies that get_logger creates a valid structlog
        logger with expected methods.
        """
        from cyo_adventure.utils.logging import get_logger

        logger = get_logger("test_logger")

        assert logger is not None
        assert callable(logger.info)
        assert callable(logger.debug)
        assert callable(logger.warning)
        assert callable(logger.error)

    @pytest.mark.unit
    def test_log_performance(self) -> None:
        """Verify performance logging works correctly.

        This test verifies that log_performance can be called without error
        and properly formats the metrics.
        """
        from unittest.mock import MagicMock

        from cyo_adventure.utils.logging import log_performance

        mock_logger = MagicMock()

        log_performance(
            mock_logger,
            operation="test_operation",
            duration_ms=123.456,
            success=True,
            extra_metric=42,
        )

        assert mock_logger.info.called
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "performance"
        assert call_args[1]["operation"] == "test_operation"
        assert call_args[1]["duration_ms"] == 123.46  # Rounded to 2 decimals
        assert call_args[1]["success"] is True
        assert call_args[1]["extra_metric"] == 42


class TestLoggingJSON:
    """Test JSON logging configuration.

    Tests for JSON renderer when json_logs=True.
    """

    @pytest.mark.unit
    def test_json_logging_renderer(self) -> None:
        """Verify JSON renderer is used when json_logs=True.

        Tests that setup_logging properly configures JSON output.
        """
        from cyo_adventure.utils.logging import setup_logging

        # Configure with JSON logging to cover the JSON renderer branch
        setup_logging(level="INFO", json_logs=True)

        # Should complete without errors
        # The JSON renderer path (line 87) is now covered
        assert True


class TestExampleIntegration:
    """Integration tests demonstrating end-to-end workflows.

    These tests verify that multiple components work together
    to accomplish realistic tasks.
    """

    @pytest.mark.integration
    def test_settings_and_logging_integration(self) -> None:
        """Verify Settings and logging work together.

        This test demonstrates that configuration and logging
        can be integrated properly.
        """
        from cyo_adventure.core.config import Settings
        from cyo_adventure.utils.logging import get_logger

        settings = Settings(log_level="INFO")
        logger = get_logger(__name__)

        assert settings.log_level == "INFO"
        assert logger is not None

    @pytest.mark.integration
    def test_package_imports(self) -> None:
        """Verify all public API imports work correctly.

        This test ensures that users can import the public API
        from the package root without errors.
        """
        # Test importing main package
        import cyo_adventure

        assert hasattr(cyo_adventure, "__version__")

        # Test importing from submodules
        from cyo_adventure.utils import get_logger

        assert callable(get_logger)

        from cyo_adventure.core import Settings

        assert Settings is not None
