"""Shared fixtures for tests/unit/.

Provides spec-constrained test doubles per the org testing standard §4.2
(Mock Safety): unspec'd mocks silently accept typos and wrong arguments, so
every shared double here is built with ``spec=`` against the real interface
it stands in for. Keep this file minimal; register only fixtures genuinely
shared across multiple unit test modules, not per-module helpers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_async_session() -> AsyncMock:
    """Return an ``AsyncMock(spec=AsyncSession)`` drop-in for a request session.

    A spec-constrained replacement for the hand-rolled ``session = AsyncMock()``
    doubles that were scattered across individual test files: attribute access
    for a name that is not a real ``AsyncSession`` member (a typo, or a method
    renamed in production code) raises ``AttributeError`` immediately instead
    of silently returning a fresh, always-passing child mock. Callers still
    configure the specific methods they need, e.g.::

        mock_async_session.execute = AsyncMock(return_value=...)
        mock_async_session.get = AsyncMock(return_value=...)
    """
    return AsyncMock(spec=AsyncSession)
