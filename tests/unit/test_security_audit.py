"""Unit tests for security_audit.py (OPS-005 follow-up: durable audit trail).

Covers record_security_event's field mapping into SecurityEvent rows
(including truncation of every string column, not just `reason`), its
own-session lifecycle (`async with get_session() as session`, add/commit,
auto-close on exit), and the fail-open contract: a database failure --
a properly-wrapped SQLAlchemyError, a raw OSError from a refused/unreachable
connection at pool checkout, an asyncpg connect-time PostgresError/
InterfaceError SQLAlchemy never gets a chance to translate, or the write
exceeding its own timeout budget -- is logged (by TYPE only, never
`str(exc)` or a traceback) and swallowed, never propagated to the caller.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
from sqlalchemy.exc import OperationalError

from cyo_adventure.db.models import SecurityEvent
from cyo_adventure.security_audit import (
    _MAX_CLIENT_IP_LEN,
    _MAX_CODE_LEN,
    _MAX_METHOD_LEN,
    _MAX_PATH_LEN,
    _MAX_REASON_LEN,
    _MAX_RESOURCE_LEN,
    record_security_event,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class _FakeSessionCM:
    """An async-context-manager double for ``core.database.get_session()``'s
    return value.

    Production code does ``async with get_session() as session:``;
    ``get_session()`` itself is a plain (sync) call whose return value (a
    real ``AsyncSession``) implements ``__aenter__``/``__aexit__``. This
    double reproduces exactly that shape so ``patch(..., return_value=...)``
    can stand in for it without touching a real engine.
    """

    def __init__(self, session: MagicMock) -> None:
        self.session = session
        self.exited = False

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.exited = True
        return False


def _mock_session() -> tuple[MagicMock, _FakeSessionCM]:
    """A MagicMock session plus the async-context-manager double wrapping it.

    ``add`` stays a plain (sync) MagicMock method, matching SQLAlchemy's real
    ``AsyncSession.add`` signature; ``commit`` is the only method under test
    that's awaited.
    """
    session = MagicMock()
    session.commit = AsyncMock()
    return session, _FakeSessionCM(session)


async def test_writes_a_security_event_row_with_all_fields() -> None:
    session, cm = _mock_session()
    with patch("cyo_adventure.security_audit.get_session", return_value=cm):
        await record_security_event(
            event_type="security_auth_failed",
            reason="unknown subject",
            client_ip="203.0.113.5",
            code="AUTH_FAILED",
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
    assert row.code == "AUTH_FAILED"
    assert row.path == "/v1/profiles"
    assert row.method == "GET"
    assert row.status_code == 401
    assert row.resource is None
    session.commit.assert_awaited_once()
    # The session is closed via `async with`'s __aexit__, not an explicit
    # session.close() call -- see the module's #CRITICAL note on why this
    # moved off manual try/finally.
    assert cm.exited


async def test_writes_a_resource_for_authz_denial() -> None:
    session, cm = _mock_session()
    with patch("cyo_adventure.security_audit.get_session", return_value=cm):
        await record_security_event(
            event_type="security_authz_denied",
            reason="forbidden",
            client_ip="203.0.113.5",
            code="FORBIDDEN",
            path="/v1/profiles/abc",
            method="GET",
            status_code=403,
            resource="profile-123",
        )

    row = session.add.call_args.args[0]
    assert row.resource == "profile-123"


async def test_rate_limit_event_has_no_path_method_or_code() -> None:
    """A rate-limit trip has no route-level request context and no exception
    to draw `code` from (middleware/security.py's call site never passes
    them), so those columns stay unset.
    """
    session, cm = _mock_session()
    with patch("cyo_adventure.security_audit.get_session", return_value=cm):
        await record_security_event(
            event_type="security_rate_limit_exceeded",
            reason="rpm",
            client_ip="203.0.113.5",
            status_code=429,
        )

    row = session.add.call_args.args[0]
    assert row.path is None
    assert row.method is None
    assert row.code is None
    assert row.resource is None


@pytest.mark.parametrize(
    ("field", "max_len"),
    [
        ("reason", _MAX_REASON_LEN),
        ("client_ip", _MAX_CLIENT_IP_LEN),
        ("code", _MAX_CODE_LEN),
        ("path", _MAX_PATH_LEN),
        ("method", _MAX_METHOD_LEN),
        ("resource", _MAX_RESOURCE_LEN),
    ],
)
async def test_every_string_column_is_truncated_to_its_bound(
    field: str, max_len: int
) -> None:
    """Every attacker-reachable string column (path, client_ip, method,
    resource) is truncated at the writer, not just `reason`: an oversized
    value that hit Postgres untruncated would raise
    StringDataRightTruncation, caught and swallowed by the same except
    clause as any other DB failure -- silently dropping the audit row for
    exactly the request an attacker most wants unlogged (a long `path`).
    Truncating first keeps the write unconditional on input size.
    """
    oversized = "x" * (max_len + 100)
    kwargs: dict[str, object] = {
        "event_type": "security_authz_denied",
        "reason": "forbidden",
        "client_ip": "203.0.113.5",
        "code": "FORBIDDEN",
        "path": "/v1/profiles",
        "method": "GET",
        "resource": "profile-123",
    }
    kwargs[field] = oversized

    session, cm = _mock_session()
    with patch("cyo_adventure.security_audit.get_session", return_value=cm):
        await record_security_event(**kwargs)  # type: ignore[arg-type]

    row = session.add.call_args.args[0]
    assert len(getattr(row, field)) == max_len


async def test_missing_client_yields_none_client_ip_column() -> None:
    session, cm = _mock_session()
    with patch("cyo_adventure.security_audit.get_session", return_value=cm):
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
    session, cm = _mock_session()
    session.commit = AsyncMock(
        side_effect=OperationalError("INSERT ...", {}, Exception("connection lost"))
    )
    with (
        patch("cyo_adventure.security_audit.get_session", return_value=cm),
        patch("cyo_adventure.security_audit.logger") as mock_logger,
    ):
        await record_security_event(
            event_type="security_auth_failed",
            reason="unknown subject",
            client_ip="203.0.113.5",
        )

    mock_logger.error.assert_called_once()
    assert mock_logger.error.call_args.args[0] == "security_event_write_failed"


async def test_connection_refused_is_logged_and_swallowed_not_raised() -> None:
    """A raw OSError (e.g. asyncpg's ConnectionRefusedError at pool checkout)
    is caught too, not just SQLAlchemyError: SQLAlchemy does NOT wrap a
    connect-time driver failure at pool checkout into SQLAlchemyError, the
    exact failure mode this test pins (see security_audit.py's #CRITICAL
    note and middleware/security.py's identical `except (RedisError,
    OSError)` split for its own Redis fail-open).
    """
    session, cm = _mock_session()
    session.commit = AsyncMock(side_effect=ConnectionRefusedError("connection refused"))
    with (
        patch("cyo_adventure.security_audit.get_session", return_value=cm),
        patch("cyo_adventure.security_audit.logger") as mock_logger,
    ):
        await record_security_event(
            event_type="security_rate_limit_exceeded",
            reason="rpm",
            client_ip="203.0.113.5",
        )

    mock_logger.error.assert_called_once()


@pytest.mark.parametrize(
    "exc",
    [
        asyncpg.InvalidPasswordError("wrong password"),
        asyncpg.TooManyConnectionsError("too many connections"),
        asyncpg.InsufficientPrivilegeError(
            "permission denied for table security_event"
        ),
        asyncpg.InterfaceError("connection is closed"),
    ],
)
async def test_asyncpg_connect_time_error_is_logged_and_swallowed_not_raised(
    exc: Exception,
) -> None:
    """asyncpg's own exception hierarchy (PostgresError/InterfaceError, both
    deriving from bare Exception, not OSError or SQLAlchemyError) is caught
    too. SQLAlchemy translates DBAPI errors raised DURING a query on an
    established connection, but not one raised while a connection is still
    being established -- exactly the case a wrong password, a pg_hba
    rejection, connection-pool saturation, or a missing GRANT produces.
    Without this third except-clause branch, any of these would escape as an
    unhandled exception and turn a real 401/403/429 into a 500.
    """
    session, cm = _mock_session()
    session.commit = AsyncMock(side_effect=exc)
    with (
        patch("cyo_adventure.security_audit.get_session", return_value=cm),
        patch("cyo_adventure.security_audit.logger") as mock_logger,
    ):
        await record_security_event(
            event_type="security_auth_failed",
            reason="unknown subject",
            client_ip="203.0.113.5",
        )

    mock_logger.error.assert_called_once()
    assert mock_logger.error.call_args.kwargs["error_type"] == type(exc).__name__


async def test_write_timeout_is_logged_and_swallowed_not_raised() -> None:
    """A write that exceeds `_WRITE_TIMEOUT_SECONDS` (e.g. blocked on pool
    checkout under contention) fails open rather than blocking the caller's
    401/403/429 response for the engine's much longer default pool_timeout.
    `asyncio.timeout` raises the builtin `TimeoutError` (an `OSError`
    subclass since Python 3.11), so this is caught by the same except clause
    as a refused connection -- verified end to end here rather than assumed.
    """

    async def _slow_commit() -> None:
        await asyncio.sleep(10)

    session, cm = _mock_session()
    session.commit = _slow_commit
    with (
        patch("cyo_adventure.security_audit.get_session", return_value=cm),
        patch("cyo_adventure.security_audit._WRITE_TIMEOUT_SECONDS", 0.05),
        patch("cyo_adventure.security_audit.logger") as mock_logger,
    ):
        await record_security_event(
            event_type="security_auth_failed",
            reason="unknown subject",
            client_ip="203.0.113.5",
        )

    mock_logger.error.assert_called_once()
    assert mock_logger.error.call_args.kwargs["error_type"] == "TimeoutError"


async def test_database_error_never_logs_exception_string_or_traceback() -> None:
    """The failure log carries the exception TYPE only, never `str(exc)` or a
    traceback: a DBAPI-level SQLAlchemy error's `__str__` includes
    `[parameters: {...}]` by default (the shared engine does not set
    `hide_parameters`, and setting it there would blunt every OTHER caller's
    error messages too), which would put `client_ip` and the row's other
    fields straight into the log store this module exists to reduce
    reliance on.
    """
    secret_marker = "203.0.113.99-should-never-appear-in-the-log"
    session, cm = _mock_session()
    session.commit = AsyncMock(
        side_effect=OperationalError(
            "INSERT INTO security_event ...",
            {"client_ip": secret_marker},
            Exception("connection lost"),
        )
    )
    with (
        patch("cyo_adventure.security_audit.get_session", return_value=cm),
        patch("cyo_adventure.security_audit.logger") as mock_logger,
    ):
        await record_security_event(
            event_type="security_auth_failed",
            reason="unknown subject",
            client_ip=secret_marker,
        )

    # logger.error (not .exception) means no exc_info is attached, so
    # structlog's format_exc_info processor never renders a traceback for
    # this call; and no kwarg anywhere in the call carries the marker.
    call = mock_logger.error.call_args
    assert secret_marker not in str(call)
    assert set(call.kwargs) == {"event_type", "error_type"}
