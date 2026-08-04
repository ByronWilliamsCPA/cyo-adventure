"""Unit tests for security_audit.py (OPS-005 follow-up: durable audit trail).

Covers record_security_event's field mapping into SecurityEvent rows, its
own-session lifecycle (add/commit/close), and the fail-open contract: a
database failure (properly wrapped SQLAlchemyError, or a raw OSError from a
refused/unreachable connection at pool checkout -- see security_audit.py's
own #CRITICAL note) is logged and swallowed, never propagated to the caller.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from cyo_adventure.db.models import SecurityEvent
from cyo_adventure.security_audit import _MAX_REASON_LEN, record_security_event

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _mock_session() -> MagicMock:
    """A MagicMock session with the async methods this writer calls as AsyncMock.

    ``add`` stays a plain (sync) MagicMock method, matching SQLAlchemy's real
    ``AsyncSession.add`` signature.
    """
    session = MagicMock()
    session.commit = AsyncMock()
    session.close = AsyncMock()
    return session


async def test_writes_a_security_event_row_with_all_fields() -> None:
    session = _mock_session()
    with patch("cyo_adventure.security_audit.get_session", return_value=session):
        await record_security_event(
            event_type="security_auth_failed",
            reason="unknown subject",
            client_ip="203.0.113.5",
            path="/v1/profiles",
            method="GET",
            status_code=401,
        )

    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert isinstance(row, SecurityEvent)
    assert row.event_type == "security_auth_failed"
    assert row.reason == "unknown subject"
    assert row.client_ip == "203.0.113.5"
    assert row.path == "/v1/profiles"
    assert row.method == "GET"
    assert row.status_code == 401
    assert row.resource is None
    session.commit.assert_awaited_once()
    session.close.assert_awaited_once()


async def test_writes_a_resource_for_authz_denial() -> None:
    session = _mock_session()
    with patch("cyo_adventure.security_audit.get_session", return_value=session):
        await record_security_event(
            event_type="security_authz_denied",
            reason="forbidden",
            client_ip="203.0.113.5",
            path="/v1/profiles/abc",
            method="GET",
            status_code=403,
            resource="profile-123",
        )

    row = session.add.call_args.args[0]
    assert row.resource == "profile-123"


async def test_rate_limit_event_has_no_path_or_method() -> None:
    """A rate-limit trip has no route-level request context (middleware/security.py's
    call site never passes path/method), so those columns stay unset.
    """
    session = _mock_session()
    with patch("cyo_adventure.security_audit.get_session", return_value=session):
        await record_security_event(
            event_type="security_rate_limit_exceeded",
            reason="rpm",
            client_ip="203.0.113.5",
            status_code=429,
        )

    row = session.add.call_args.args[0]
    assert row.path is None
    assert row.method is None
    assert row.resource is None


async def test_reason_is_truncated_to_max_length() -> None:
    """A backstop, not an expected path: reason is always a short, fixed
    developer-authored string in practice (see the call sites' own RAD
    notes), but the column is bounded regardless of what a future caller
    passes.
    """
    session = _mock_session()
    with patch("cyo_adventure.security_audit.get_session", return_value=session):
        await record_security_event(
            event_type="security_auth_failed",
            reason="x" * (_MAX_REASON_LEN + 100),
            client_ip=None,
        )

    row = session.add.call_args.args[0]
    assert len(row.reason) == _MAX_REASON_LEN


async def test_missing_client_yields_none_client_ip_column() -> None:
    session = _mock_session()
    with patch("cyo_adventure.security_audit.get_session", return_value=session):
        await record_security_event(
            event_type="security_auth_failed",
            reason="missing or malformed bearer token",
            client_ip=None,
        )

    row = session.add.call_args.args[0]
    assert row.client_ip is None


async def test_database_error_is_logged_and_swallowed_not_raised() -> None:
    """A properly-wrapped SQLAlchemy failure (e.g. a constraint violation, or
    a connection error surfaced through SQLAlchemy's own error-translation
    layer) never propagates: the caller's real response (401/403/429) must
    not become a 500 because the audit write failed.
    """
    session = _mock_session()
    session.commit = AsyncMock(
        side_effect=OperationalError("INSERT ...", {}, Exception("connection lost"))
    )
    with (
        patch("cyo_adventure.security_audit.get_session", return_value=session),
        patch("cyo_adventure.security_audit.logger") as mock_logger,
    ):
        await record_security_event(
            event_type="security_auth_failed",
            reason="unknown subject",
            client_ip="203.0.113.5",
        )

    mock_logger.exception.assert_called_once()
    assert mock_logger.exception.call_args.args[0] == "security_event_write_failed"
    # The `finally` still closes the session even though commit raised.
    session.close.assert_awaited_once()


async def test_connection_refused_is_logged_and_swallowed_not_raised() -> None:
    """A raw OSError (e.g. asyncpg's ConnectionRefusedError at pool checkout)
    is caught too, not just SQLAlchemyError: SQLAlchemy does NOT wrap a
    connect-time driver failure at pool checkout into SQLAlchemyError, the
    exact failure mode this test pins (see security_audit.py's #CRITICAL
    note and middleware/security.py's identical `except (RedisError,
    OSError)` split for its own Redis fail-open).
    """
    session = _mock_session()
    session.commit = AsyncMock(side_effect=ConnectionRefusedError("connection refused"))
    with (
        patch("cyo_adventure.security_audit.get_session", return_value=session),
        patch("cyo_adventure.security_audit.logger") as mock_logger,
    ):
        await record_security_event(
            event_type="security_rate_limit_exceeded",
            reason="rpm",
            client_ip="203.0.113.5",
        )

    mock_logger.exception.assert_called_once()
    session.close.assert_awaited_once()
