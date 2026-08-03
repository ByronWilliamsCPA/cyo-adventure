"""Pytest configuration and shared fixtures for CYO Adventure tests.

This module provides:
- Hypothesis settings profiles (ci / dev)
- Shared fixtures for common test resources
- Temporary directory management

Custom pytest markers are registered in ``pyproject.toml``
(``[tool.pytest.ini_options].markers``), not here.
"""

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog
from hypothesis import HealthCheck, settings

# ============================================================================
# Hypothesis Profiles
# ============================================================================
#
# ci: more examples, derandomized so a red CI run reproduces exactly, and no
#     per-example deadline (shared runners have noisy timings; the suite-level
#     timeout is the real guard).
# dev: the library default (100 randomized examples) for fast local feedback
#     with fresh exploration on every run.
settings.register_profile(
    "ci",
    max_examples=200,
    derandomize=True,
    deadline=None,
    print_blob=True,
    suppress_health_check=(HealthCheck.too_slow,),
)
settings.register_profile("dev", settings.default)
settings.load_profile(
    "ci"
    if os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"}
    else "dev"
)

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
def setup_logging() -> Iterator[None]:
    """Configure logging per test, then restore the process-global state.

    Automatically applied to all tests to ensure consistent logging setup.

    The restore half used to live in ``tests/unit/test_logging_startup.py``,
    which was the only module that knowingly tore structlog down. It belongs
    here instead: any test that constructs a ``TestClient`` now runs the app
    lifespan, and the lifespan calls ``setup_logging``, so ANY such test
    mutates process-wide structlog and root-handler state. With
    ``cache_logger_on_first_use=True`` a leaked configuration is an
    order-dependent hazard that only shows up under ``pytest-randomly``.

    Yields:
        None: after logging is configured for the test.
    """
    from cyo_adventure.utils.logging import setup_logging as configure_logging

    was_configured = structlog.is_configured()
    saved_structlog = structlog.get_config()
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    configure_logging(level="DEBUG", json_logs=False, include_timestamp=False)
    try:
        yield
    finally:
        if was_configured:
            structlog.configure(**saved_structlog)
        else:
            structlog.reset_defaults()
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
