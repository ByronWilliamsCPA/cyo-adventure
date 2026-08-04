"""Durable audit trail for security events (OPS-005 follow-up).

Complements the ``security_auth_failed``/``security_authz_denied``/
``security_rate_limit_exceeded`` structured log events
``app.py::_handle_project_error`` and
``middleware/security.py::RateLimitMiddleware`` already emit: those are the
real-time, alerting-facing surface, and this module is the durable,
query-facing counterpart that ``docs/compliance/breach-notification-runbook.md``
needs to reconstruct an incident after log retention has rolled the log lines
off.

Unlike ``events/writer.py``'s ``PipelineEvent`` (an append-only log keyed to
an authenticated ``Actor``), a row here often has no authenticated principal
at all: an anonymous, pre-``Principal`` auth failure has nothing to attribute
it to but a client IP. See ``db.models.SecurityEvent``'s docstring and the
creating migration for why this is a separate table rather than a
``PipelineEvent`` extension.
"""

from __future__ import annotations

import asyncio

import asyncpg
import structlog
from sqlalchemy.exc import SQLAlchemyError

from cyo_adventure.core.database import get_session
from cyo_adventure.db.models import SecurityEvent

# Uses structlog directly rather than cyo_adventure.utils.logging.get_logger,
# mirroring middleware/security.py's identical workaround and for the same
# reason: this module is imported at module scope from middleware/security.py
# (RateLimitMiddleware's trip logging), which is itself imported by
# cyo_adventure/middleware/__init__.py. The wrapper module imports from
# cyo_adventure.middleware.correlation; routing through it here would risk
# the same partially-initialized-module ImportError the sibling file already
# documents, depending on which module happens to trigger the import chain
# first. structlog.get_logger(__name__) is exactly what the wrapper does
# internally minus the import-time dependency, and still honors whatever
# structlog.configure() call setup_logging() has made process-wide.
logger = structlog.get_logger(__name__)

# Backstop truncation lengths, one per SecurityEvent string column (matching
# the migration's VARCHAR widths exactly). `reason`/`code` are developer-
# controlled in practice (see the call sites' own RAD notes) so these bounds
# are pure defense in depth for them; `path`/`client_ip`/`method`/`resource`
# are reachable from caller input (a request path, a header-derived IP), so
# without this bound an oversized value would raise StringDataRightTruncation
# at INSERT time -- caught by the except clause below like any other DB
# failure, which means an attacker could make their own audit row silently
# fail to write just by sending an oversized path. Truncating BEFORE the
# INSERT keeps the row-write itself unconditional on input size.
_MAX_REASON_LEN = 200
_MAX_PATH_LEN = 255
_MAX_CLIENT_IP_LEN = 45
_MAX_METHOD_LEN = 10
_MAX_RESOURCE_LEN = 255
_MAX_CODE_LEN = 64

# How long a single write may wait on a pool checkout / round-trip before
# giving up. SQLAlchemy's own pool_timeout default (30s) is sized for normal
# request-serving connections, not a best-effort audit write competing for
# the SAME pool on the rejection path; under sustained abuse (many rate-limit
# trips or auth failures at once) this bounds how much that competition can
# add to each rejected request's latency before failing open instead.
_WRITE_TIMEOUT_SECONDS = 2.0


def _truncate(value: str | None, max_len: int) -> str | None:
    """Return ``value`` clipped to ``max_len``, or ``None`` unchanged."""
    return value[:max_len] if value is not None else None


async def record_security_event(
    *,
    event_type: str,
    reason: str,
    client_ip: str | None,
    code: str | None = None,
    path: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    resource: str | None = None,
) -> None:
    """Persist one append-only ``security_event`` row on its own short-lived session.

    Called from ``app.py::_handle_project_error`` (auth failures, authz
    denials) and ``middleware/security.py::RateLimitMiddleware`` (rate-limit
    trips) immediately after the matching structured log call, with the same
    field values.

    Args:
        event_type: One of ``SecurityEvent``'s CHECK-constrained values --
            the exact structlog event name (``security_auth_failed``,
            ``security_authz_denied``, or ``security_rate_limit_exceeded``).
        reason: The fixed, developer-authored message/limit-type token; never
            caller input (see the call sites' own RAD notes). Truncated to
            ``_MAX_REASON_LEN`` as a backstop.
        client_ip: The request's observed client address, or ``None`` when
            unavailable (no transport-level peer). Truncated to
            ``_MAX_CLIENT_IP_LEN``.
        code: The exception's machine-readable ``error_code`` (e.g.
            ``PIN_MISMATCH``), when the caller has one. Truncated to
            ``_MAX_CODE_LEN``.
        path: The request path, when the caller has one (unset for a
            rate-limit trip, which has no route-level request context).
            Caller-controlled; truncated to ``_MAX_PATH_LEN``.
        method: The request method, same availability as ``path``.
            Truncated to ``_MAX_METHOD_LEN``.
        status_code: The mapped HTTP status: 401/403 for an auth/authz row,
            429 for a rate-limit row (RateLimitMiddleware passes this too;
            unset only if a future call site has no fixed status to report).
        resource: The denied resource identifier, for authz-denial rows only
            (already pruned of ``value``/``context`` by the caller).
            Truncated to ``_MAX_RESOURCE_LEN``.
    """
    # #CRITICAL: external resources: this write must never turn a real
    # response (401/403/429) into a 500, and must never add unbounded latency
    # to one either. It runs on its OWN short-lived session via
    # core.database.get_session() -- never the request's own unit-of-work --
    # because neither call site reliably has one: a 401 raised by
    # api/deps.py::_extract_subject fires before require_principal ever opens
    # a session, and RateLimitMiddleware runs at the ASGI middleware layer,
    # before routing resolves any request-scoped dependency at all. The whole
    # write is bounded by _WRITE_TIMEOUT_SECONDS (asyncio.timeout raises the
    # builtin TimeoutError, an OSError subclass since Python 3.11, so it is
    # caught by the same except clause as a refused connection) so a
    # contended pool degrades to fail-open quickly rather than blocking the
    # rejection response for the engine's much longer default pool_timeout.
    #
    # The except clause covers three distinct failure layers: a
    # properly-wrapped SQLAlchemyError (constraint violation, an error
    # SQLAlchemy's own translation layer caught); OSError (a refused/
    # unreachable connection surfaces as the driver's raw OSError subclass at
    # pool checkout, never wrapped into SQLAlchemyError -- the same class
    # RateLimitMiddleware's own Redis fail-open catches via
    # except (RedisError, OSError)); and asyncpg's own exception hierarchy
    # (asyncpg.PostgresError / asyncpg.InterfaceError derive from bare
    # Exception, not OSError or SQLAlchemyError, and SQLAlchemy does not
    # translate an error raised at connect time, before a DBAPI connection
    # exists for its translation layer to attach to -- verified against this
    # repo's pinned asyncpg: InvalidPasswordError, CannotConnectNowError,
    # TooManyConnectionsError, and InsufficientPrivilegeError all reach this
    # far uncaught without this third branch). Anything outside these three
    # (a genuine bug in this function) is deliberately allowed to propagate
    # rather than hidden behind a blind except.
    # #VERIFY: tests/unit/test_security_audit.py::
    # test_database_error_is_logged_and_swallowed_not_raised,
    # ::test_connection_refused_is_logged_and_swallowed_not_raised,
    # ::test_asyncpg_connect_time_error_is_logged_and_swallowed_not_raised,
    # ::test_write_timeout_is_logged_and_swallowed_not_raised.
    try:
        async with (
            asyncio.timeout(_WRITE_TIMEOUT_SECONDS),
            get_session() as session,
        ):
            session.add(
                SecurityEvent(
                    event_type=event_type,
                    reason=_truncate(reason, _MAX_REASON_LEN) or "",
                    client_ip=_truncate(client_ip, _MAX_CLIENT_IP_LEN),
                    code=_truncate(code, _MAX_CODE_LEN),
                    path=_truncate(path, _MAX_PATH_LEN),
                    method=_truncate(method, _MAX_METHOD_LEN),
                    status_code=status_code,
                    resource=_truncate(resource, _MAX_RESOURCE_LEN),
                )
            )
            await session.commit()
    except (
        SQLAlchemyError,
        OSError,
        asyncpg.PostgresError,
        asyncpg.InterfaceError,
    ) as exc:
        # #CRITICAL: security: log the exception TYPE only, never str(exc) or
        # exc_info (which structlog's format_exc_info processor would render
        # into the log as a full traceback). A DBAPI-level SQLAlchemy error's
        # __str__ includes "[parameters: {...}]" by default (hide_parameters
        # is not set on the shared engine, and setting it there would blunt
        # every OTHER caller's error messages too, not just this module's) --
        # that would put client_ip and other row fields straight into the log
        # store this module exists to reduce reliance on. logger.error (not
        # .exception) additionally means no exc_info is attached at all.
        # #VERIFY: tests/unit/test_security_audit.py::
        # test_database_error_never_logs_exception_string_or_traceback.
        logger.error(  # noqa: TRY400 -- deliberate: see the comment above
            "security_event_write_failed",
            event_type=event_type,
            error_type=type(exc).__name__,
        )
