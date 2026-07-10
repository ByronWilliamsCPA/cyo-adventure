"""Pytest configuration and shared fixtures for CYO Adventure tests.

This module provides:
- Shared fixtures for common test resources
- Temporary directory management

Custom pytest markers are registered in ``pyproject.toml``
(``[tool.pytest.ini_options].markers``), not here.
"""

from pathlib import Path

import pytest

# ============================================================================
# Temporary Directory Fixtures
# ============================================================================


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Return temporary directory for test outputs.

    Creates and returns a clean temporary directory for each test to write
    output files.

    Args:
        tmp_path: Pytest's built-in tmp_path fixture.

    Returns:
        Path object pointing to the temporary output directory.
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """Return temporary directory for caching.

    Creates and returns a clean temporary cache directory for each test.

    Args:
        tmp_path: Pytest's built-in tmp_path fixture.

    Returns:
        Path object pointing to the temporary cache directory.
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


# ============================================================================
# Moderation Test Data
# ============================================================================


def make_clean_moderation_report() -> dict[str, object]:
    """Return a fresh screened-clean moderation report body.

    For tests that need publishing.service.approve to succeed: approve()
    refuses to publish a version whose moderation_report is None (C3-SAFETY
    Findings 1-2). Tests exercising the illegal-transition, authorization, or
    not-found paths never reach that check, so they do not need this. Returns
    a new dict per call so callers cannot mutate a shared instance across
    tests.

    Returns:
        A moderation report dict with no findings and a clean summary.
    """
    return {
        "findings": [],
        "summary": {
            "count": 0,
            "hard_block": False,
            "soft_flag": False,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


# ============================================================================
# Logging Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def setup_logging() -> None:
    """Setup test logging configuration.

    Automatically applied to all tests to ensure consistent logging setup.
    """
    from cyo_adventure.utils.logging import setup_logging

    setup_logging(level="DEBUG", json_logs=False, include_timestamp=False)
