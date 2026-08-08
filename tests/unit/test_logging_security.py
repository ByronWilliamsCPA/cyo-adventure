"""Auth-event and secrets logging tests (org standard §14.8b/c, §14.9).

What IS logged on an auth failure (verified by reading the source; OPS-005):

* ``src/cyo_adventure/api/deps.py`` emits **no auth events**, and that is
  deliberate: ``AuthenticationError``/``AuthorizationError`` is raised from
  89 call sites across 35 files (``api/deps.py``, most of ``api/*``,
  ``core/child_session.py``, ``core/device_grant.py``, ``publishing/``,
  ``covers/``), and every one of them passes through the single global
  handler below on its way to a response. Rather than instrument each raise
  site (and risk a future one forgetting to), the auth-event logging is
  centralized there. ``test_deps_module_logs_no_auth_events`` below pins the
  module's complete set of log call sites, so any addition has to be declared
  there rather than appearing quietly next to an auth raise.
* ``src/cyo_adventure/app.py::_handle_project_error`` emits the generic
  ``project_error`` warning for every ``ProjectBaseError``
  (``error``/``message``/``status_code``/``details``), same as before, AND
  now additionally emits a distinctly-named security event for auth
  failures specifically: ``security_auth_failed`` for an
  ``AuthenticationError`` (401), ``security_authz_denied`` for an
  ``AuthorizationError`` (403). Each carries ``reason`` (the exception
  message; always a fixed, developer-authored string, never caller input),
  ``client_ip``, ``path``, and ``method`` -- the actor/source context the
  generic line lacked, and the distinct name a log-based alert rule can key
  on without parsing ``status_code`` out of ``project_error``. Correlation
  ids reach every one of these events via ``correlation_context_processor``
  (``middleware/correlation.py``), fed by the request-scoped contextvars
  ``CorrelationMiddleware`` sets.

Capture strategy: the app's module-level ``logger`` is a structlog proxy
whose processor chain depends on process-global configuration (mutated by
the autouse ``setup_logging`` fixture and other tests). To make capture
deterministic and order-independent, each test monkeypatches the module
logger with an explicitly wrapped logger whose chain is exactly
``[correlation_context_processor, LogCapture()]``; ``LogCapture`` raises
``DropEvent`` so nothing propagates to real handlers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import mock

import pytest
import pytest_asyncio
import structlog
from httpx import ASGITransport, AsyncClient
from structlog.testing import LogCapture

from cyo_adventure import app as app_module
from cyo_adventure.api import health as health_module
from cyo_adventure.app import app
from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ProjectBaseError,
)
from cyo_adventure.middleware.correlation import (
    correlation_context_processor,
    set_correlation_id,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from structlog.stdlib import BoundLogger

pytestmark = [pytest.mark.unit, pytest.mark.security]

# Clearly-fake credentials (never real-looking; see the batch instructions).
_FAKE_BEARER_TOKEN = "test-secret-token-not-real"
_FAKE_DB_PASSWORD = "test-db-password-not-real"
_FAKE_DSN = f"postgresql+asyncpg://cyo:{_FAKE_DB_PASSWORD}@db.invalid.example:5432/cyo"


def _capturing_logger(cap: LogCapture) -> BoundLogger:
    """Build a logger whose only processors are correlation context + capture.

    ``LogCapture`` raises ``DropEvent`` after recording, so nothing reaches a
    real handler; ``correlation_context_processor`` runs first so each
    captured entry carries whatever correlation contextvars are set, exactly
    as the production chain built by ``setup_logging(include_correlation=
    True)`` would.
    """
    return structlog.wrap_logger(
        structlog.testing.ReturnLogger(),
        processors=[correlation_context_processor, cap],
    )


def _all_captured_text(cap: LogCapture) -> str:
    """Flatten every captured event dict into one searchable string."""
    return "\n".join(repr(entry) for entry in cap.entries)


@pytest.fixture
def log_capture(monkeypatch: pytest.MonkeyPatch) -> LogCapture:
    """Capture the app's and health module's structured logs deterministically."""
    cap = LogCapture()
    monkeypatch.setattr(app_module, "logger", _capturing_logger(cap))
    monkeypatch.setattr(health_module, "logger", _capturing_logger(cap))
    return cap


@pytest_asyncio.fixture
async def unit_client() -> AsyncIterator[AsyncClient]:
    """An httpx client against the real app, for DB-free auth-failure paths.

    Only exercises requests that fail authentication before any database
    access (``_extract_subject`` raises before ``require_principal`` runs its
    first query), so no session override or container is needed here.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# §14.8b: auth failures produce a structured event with outcome + correlation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_security_event"),
    [
        (
            AuthenticationError("missing or malformed bearer token"),
            401,
            "security_auth_failed",
        ),
        (
            AuthorizationError("admin role required"),
            403,
            "security_authz_denied",
        ),
    ],
    ids=["authentication_error_401", "authorization_error_403"],
)
@pytest.mark.asyncio
async def test_handle_project_error_auth_failure_logs_outcome_and_correlation_id(
    log_capture: LogCapture,
    exc: ProjectBaseError,
    expected_status: int,
    expected_security_event: str,
) -> None:
    """The app's error handler logs both the generic and the security event.

    Every auth failure now produces TWO structured log entries: the generic
    ``project_error`` (unchanged) and a distinctly-named security event
    (OPS-005) carrying the client address, path, and method alongside the
    outcome and the request's correlation id.
    """
    # Arrange: a request object exposing exactly what the handler reads
    # (headers/url/method for the generic path, client for the security
    # event's client_ip). No contextvars.copy_context().run() indirection
    # needed here: each async test function already runs in its own asyncio
    # Task, and a Task's context is a COPY taken at creation, so
    # set_correlation_id below can never leak into a sibling test.
    request = mock.Mock(spec=["headers", "url", "method", "client"])
    request.url.path = "/api/v1/me"
    request.method = "GET"
    request.client.host = "203.0.113.7"
    correlation_id = "authz-log-test-correlation-id"
    set_correlation_id(correlation_id)

    # Act
    # record_security_event opens a real DB session when unmocked
    # (tests/CLAUDE.md: unit tests must not hit a live database).
    with mock.patch("cyo_adventure.app.record_security_event"):
        response = await app_module._handle_project_error(request, exc)

    # Assert: mapped status code, the generic project_error event, and the
    # new security event, both carrying the correlation id.
    assert getattr(response, "status_code", None) == expected_status
    assert len(log_capture.entries) == 2
    generic_entry = log_capture.entries[0]
    assert generic_entry["event"] == "project_error"
    assert generic_entry["status_code"] == expected_status
    assert generic_entry["error"] == type(exc).__name__
    assert generic_entry["correlation_id"] == correlation_id

    security_entry = log_capture.entries[1]
    assert security_entry["event"] == expected_security_event
    assert security_entry["reason"] == exc.message
    assert security_entry["client_ip"] == "203.0.113.7"
    assert security_entry["path"] == "/api/v1/me"
    assert security_entry["method"] == "GET"
    assert security_entry["correlation_id"] == correlation_id


@pytest.mark.asyncio
async def test_request_without_token_returns_401_and_logs_correlated_event(
    unit_client: AsyncClient, log_capture: LogCapture
) -> None:
    """End-to-end through the middleware: 401 logs project_error + the security event.

    Drives a real request (no DB touched by the ROUTE: ``_extract_subject``
    raises before the first query) so the correlation id in the log lines is
    the one ``CorrelationMiddleware`` echoes in the response headers, proving
    the contextvar plumbing rather than a manually seeded value.
    record_security_event IS patched, though: unlike the route itself, the
    security-event audit write always opens its own session regardless of
    which raise site failed, and unit tests must not hit a live database
    (tests/CLAUDE.md).
    """
    # Act
    with mock.patch("cyo_adventure.app.record_security_event") as mock_record:
        response = await unit_client.get("/api/v1/me")

    # Assert
    assert response.status_code == 401
    events = [e for e in log_capture.entries if e["event"] == "project_error"]
    assert len(events) == 1
    entry = events[0]
    assert entry["status_code"] == 401
    assert entry["error"] == "AuthenticationError"
    assert entry["correlation_id"] == response.headers["X-Correlation-ID"]

    # OPS-005: the same real request also produces the distinct security
    # event, through the real ASGI request (not a hand-built mock), carrying
    # the path/method and the same correlation id as the generic log line.
    security_events = [
        e for e in log_capture.entries if e["event"] == "security_auth_failed"
    ]
    assert len(security_events) == 1
    security_entry = security_events[0]
    assert security_entry["path"] == "/api/v1/me"
    assert security_entry["method"] == "GET"
    assert security_entry["correlation_id"] == response.headers["X-Correlation-ID"]

    # And the durable audit write was attempted with the same path/method.
    mock_record.assert_awaited_once()
    assert mock_record.await_args.kwargs["path"] == "/api/v1/me"
    assert mock_record.await_args.kwargs["method"] == "GET"


# ---------------------------------------------------------------------------
# §14.8c / §14.9: secrets (bearer tokens, DSN passwords) never logged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization_header",
    [
        f"Token {_FAKE_BEARER_TOKEN}",
        f"Bearer{_FAKE_BEARER_TOKEN}",
        "Bearer ",
    ],
    ids=["wrong_scheme", "missing_space", "empty_token"],
)
async def test_auth_failure_with_token_in_header_never_logs_token(
    unit_client: AsyncClient,
    log_capture: LogCapture,
    authorization_header: str,
) -> None:
    """A rejected Authorization header's token value appears in no log line.

    All three malformed-header shapes fail in ``_extract_subject`` (before
    any DB access) and flow through the generic error handler; the token
    substring must appear neither in any captured structured log entry nor
    in the client-facing response body.
    """
    # Act
    with mock.patch("cyo_adventure.app.record_security_event"):
        response = await unit_client.get(
            "/api/v1/me", headers={"Authorization": authorization_header}
        )

    # Assert
    assert response.status_code == 401
    assert _FAKE_BEARER_TOKEN not in response.text
    assert log_capture.entries, "expected the auth failure to be logged at all"
    assert _FAKE_BEARER_TOKEN not in _all_captured_text(log_capture)


@pytest.mark.asyncio
async def test_readiness_check_db_failure_logs_generic_error_without_dsn(
    log_capture: LogCapture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing DB readiness check never puts the DSN password in log or body.

    ``check_database`` deliberately logs ``str(exc)`` server-side and returns
    the generic ``"dependency unavailable"`` message to the client (OWASP
    A09; see api/health.py). With a Settings object whose DSN carries a fake
    password in scope (built from monkeypatched env), the password substring
    must appear in neither the structured log entries nor the returned check.
    """
    # Arrange: a Settings object holding a password-bearing DSN (env-sourced),
    # and a get_session that fails the way an unreachable DB would, WITHOUT
    # the driver ever being handed real credentials.
    monkeypatch.setenv("CYO_ADVENTURE_DATABASE_URL", _FAKE_DSN)
    settings = Settings()
    assert _FAKE_DB_PASSWORD in settings.database_url  # the secret is in scope

    from cyo_adventure.core import database as database_module

    failing_get_session = mock.create_autospec(
        database_module.get_session, side_effect=RuntimeError("connection refused")
    )
    monkeypatch.setattr(database_module, "get_session", failing_get_session)

    # Act
    check = await health_module.check_database()

    # Assert: generic client-facing message, one warning log, no password.
    assert check.status is False
    assert check.error == "dependency unavailable"
    assert _FAKE_DB_PASSWORD not in (check.error or "")
    assert len(log_capture.entries) == 1
    entry = log_capture.entries[0]
    assert entry["event"] == "readiness check failed"
    assert entry["check"] == "database"
    captured = _all_captured_text(log_capture)
    assert _FAKE_DB_PASSWORD not in captured
    assert _FAKE_DSN not in captured


def test_deps_module_logs_no_auth_events() -> None:
    """Pin every log call in the auth seam by name (OPS-005).

    ``api/deps.py`` emits no auth event of its own, and that is deliberate
    rather than an oversight: every ``AuthenticationError``/
    ``AuthorizationError`` it raises (12 of the 89 sites, the other 77 being
    spread across 34 further files) already passes through the single global
    handler (``app.py::_handle_project_error``), which is where
    ``security_auth_failed``/``security_authz_denied`` are emitted with the
    request's client address, path, and method. Logging directly in
    ``deps.py`` as well would duplicate that event (and risk a
    differently-shaped one) for no benefit.

    This asserts the module's complete, ordered list of log event names
    rather than the absence of a logger object, because the module does now
    hold one: ``request_unit_of_work`` logs when it takes the fallback commit
    path, which is the only trace a silently bypassed ``UnitOfWorkMiddleware``
    would leave. Reading the call sites out of the AST rather than the
    namespace keeps the guard pointed at what is actually emitted, and an
    event name that is not a plain string literal lands in the list as
    ``None`` so it cannot slip past the comparison. Any new log line in this
    module fails here until it is declared; an auth event added here fails
    here and should be moved to the central handler instead.
    """
    # Arrange: parse the module rather than importing its namespace, so the
    # assertion sees call sites instead of module attributes.
    import ast
    import inspect

    import cyo_adventure.api.deps as deps_module

    tree = ast.parse(inspect.getsource(deps_module))

    # Act: collect one entry per `logger.<level>(...)` call, in source order.
    event_names: list[str | None] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        target = func.value
        if not isinstance(target, ast.Name) or target.id != "logger":
            continue
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            event_names.append(first.value)
        else:
            event_names.append(None)

    # Assert: the one declared event, and nothing auth-shaped alongside it.
    assert event_names == ["unit_of_work_committed_in_dependency_fallback"], (
        "api/deps.py's log call sites changed. If an auth event was added, "
        "move it to the central app.py::_handle_project_error handler "
        "instead; otherwise declare the new event name here. "
        f"Found: {event_names}"
    )
