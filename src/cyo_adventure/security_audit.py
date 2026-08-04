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

# Mirrors events/writer.py's _MAX_PAYLOAD_STR_LEN: the longest legitimate
# `reason` is a developer-authored error message, well under this bound: a
# backstop against a future call site accidentally passing free text, not an
# expected truncation path.
_MAX_REASON_LEN = 200


async def record_security_event(
    *,
    event_type: str,
    reason: str,
    client_ip: str | None,
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
            unavailable (no transport-level peer).
        path: The request path, when the caller has one (unset for a
            rate-limit trip, which has no route-level request context).
        method: The request method, same availability as ``path``.
        status_code: The mapped HTTP status: 401/403 for an auth/authz row,
            429 for a rate-limit row (RateLimitMiddleware passes this too;
            unset only if a future call site has no fixed status to report).
        resource: The denied resource identifier, for authz-denial rows only
            (already pruned of ``value``/``context`` by the caller).
    """
    # #CRITICAL: external resources: this write must never turn a real
    # response (401/403/429) into a 500. It runs on its OWN short-lived
    # session via core.database.get_session() -- never the request's own
    # unit-of-work -- because neither call site reliably has one: a 401
    # raised by api/deps.py::_extract_subject fires before require_principal
    # ever opens a session, and RateLimitMiddleware runs at the ASGI
    # middleware layer, before routing resolves any request-scoped
    # dependency at all. Both a properly-wrapped SQLAlchemy failure
    # (constraint violation, already-connected session error) and a raw
    # connection-time failure are caught: a DB connection refused/unreachable
    # at pool checkout surfaces as the driver's own OSError subclass (e.g.
    # asyncpg's ConnectionRefusedError), never wrapped into SQLAlchemyError,
    # exactly the same two-exception-type split
    # middleware/security.py::RateLimitMiddleware's own Redis fail-open uses
    # (except (RedisError, OSError)). Anything outside that pair (a genuine
    # bug in this function) is deliberately allowed to propagate rather than
    # hidden behind a blind except.
    # #VERIFY: tests/unit/test_security_audit.py::
    # test_database_error_is_logged_and_swallowed_not_raised,
    # ::test_connection_refused_is_logged_and_swallowed_not_raised.
    try:
        session = get_session()
        try:
            session.add(
                SecurityEvent(
                    event_type=event_type,
                    reason=reason[:_MAX_REASON_LEN],
                    client_ip=client_ip,
                    path=path,
                    method=method,
                    status_code=status_code,
                    resource=resource,
                )
            )
            await session.commit()
        finally:
            await session.close()
    except (SQLAlchemyError, OSError) as exc:
        logger.exception(
            "security_event_write_failed",
            event_type=event_type,
            error=str(exc),
        )
