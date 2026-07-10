"""run_cover_job_sync and _run: the RQ entrypoint's sync/async boundary.

``run_cover_job_sync`` is a plain sync function (the RQ entrypoint), so its
own test drives the real ``asyncio.run`` call with ``_run`` patched out; a
running event loop (as pytest-asyncio provides) would make a nested
``asyncio.run`` call raise. ``_run`` is exercised directly as an async test
with its lazily-imported collaborators (``get_session``, ``settings``,
``generate_cover``) patched at their source modules, since those names are
imported fresh inside the function body on every call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.core.config import Settings
from cyo_adventure.core.database import get_session as real_get_session
from cyo_adventure.covers import service as service_module
from cyo_adventure.covers import worker as worker_module
from cyo_adventure.covers.worker import _run, run_cover_job_sync

pytestmark = pytest.mark.unit


def test_run_cover_job_sync_with_correlation_id_binds_context() -> None:
    """A correlation id is bound into the worker's log context before _run."""
    # Arrange
    run_mock = AsyncMock(spec=_run)
    bind_mock = MagicMock(spec=worker_module.bind_contextvars)

    # Act
    with (
        patch.object(worker_module, "_run", run_mock),
        patch.object(worker_module, "bind_contextvars", bind_mock),
    ):
        run_cover_job_sync("story-1", 3, "corr-abc")

    # Assert
    bind_mock.assert_called_once_with(correlation_id="corr-abc")
    run_mock.assert_awaited_once_with("story-1", 3)


def test_run_cover_job_sync_without_correlation_id_skips_binding() -> None:
    """No correlation id means bind_contextvars is never called."""
    # Arrange
    run_mock = AsyncMock(spec=_run)
    bind_mock = MagicMock(spec=worker_module.bind_contextvars)

    # Act
    with (
        patch.object(worker_module, "_run", run_mock),
        patch.object(worker_module, "bind_contextvars", bind_mock),
    ):
        run_cover_job_sync("story-1", 3, None)

    # Assert
    bind_mock.assert_not_called()
    run_mock.assert_awaited_once_with("story-1", 3)


@pytest.mark.asyncio
async def test_run_opens_own_session_and_delegates_to_generate_cover() -> None:
    """_run opens its own DB session and forwards to generate_cover."""
    # Arrange: get_session() returns an async-context-manager whose __aenter__
    # yields a session sentinel; spec against AsyncSession since that is the
    # real return type of get_session().
    session_sentinel = object()
    session_ctx = MagicMock(spec=AsyncSession)
    session_ctx.__aenter__ = AsyncMock(return_value=session_sentinel)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    real_settings = Settings()
    generate_cover_mock = AsyncMock(spec=service_module.generate_cover)

    # Act
    with (
        patch(
            "cyo_adventure.core.database.get_session",
            MagicMock(spec=real_get_session, return_value=session_ctx),
        ),
        patch("cyo_adventure.core.config.settings", real_settings),
        patch("cyo_adventure.covers.service.generate_cover", generate_cover_mock),
    ):
        await _run("story-1", 3)

    # Assert
    session_ctx.__aenter__.assert_awaited_once()
    session_ctx.__aexit__.assert_awaited_once()
    generate_cover_mock.assert_awaited_once_with(
        "story-1", 3, session=session_sentinel, settings=real_settings
    )
