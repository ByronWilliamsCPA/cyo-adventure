"""FastAPI application factory.

Wires correlation (first) and security middleware, maps the core exception
hierarchy to HTTP status codes, and mounts the health, library, and reading
routers. The OpenAPI schema this app exposes is the source of truth for the
generated frontend client.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cyo_adventure.api import (
    approval,
    assignments,
    generation,
    health,
    library,
    me,
    profiles,
    ratings,
    reading,
)
from cyo_adventure.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ProjectBaseError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.middleware import CorrelationMiddleware, add_security_middleware
from cyo_adventure.utils.logging import get_logger

logger = get_logger(__name__)

_INTERNAL_ERROR = {"error": "InternalError", "message": "internal error"}

# Detail keys that carry caller-supplied input (`value`) or internal state
# (`context`, e.g. a resource's lifecycle status) and must not be disclosed in
# the client-facing error body. They are retained in the server log only.
_SENSITIVE_DETAIL_KEYS = frozenset({"value", "context"})


def _client_safe_error(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of an error payload with sensitive detail keys removed."""
    safe = dict(payload)
    details = safe.get("details")
    if isinstance(details, dict):
        pruned = {k: v for k, v in details.items() if k not in _SENSITIVE_DETAIL_KEYS}
        if pruned:
            safe["details"] = pruned
        else:
            safe.pop("details", None)
    return safe


def _status_for(exc: ProjectBaseError) -> int:
    """Map a core exception to its HTTP status code.

    Args:
        exc: The raised project exception.

    Returns:
        int: The HTTP status code for the response.
    """
    if isinstance(exc, AuthenticationError):
        return 401
    if isinstance(exc, AuthorizationError):
        return 403
    if isinstance(exc, ResourceNotFoundError):
        return 404
    if isinstance(exc, ValidationError):
        return 422
    if isinstance(exc, StateTransitionError):
        return 409
    return 400


def _handle_project_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render a core exception as a JSON error response.

    The full error payload (including caller `value` and internal `context`)
    is logged server-side; the client body is sanitized so it never discloses
    raw input or internal lifecycle state.

    Args:
        _request: The incoming request (unused).
        exc: The exception raised during handling.

    Returns:
        JSONResponse: The sanitized error body with the mapped status code.
    """
    if not isinstance(exc, ProjectBaseError):
        return JSONResponse(status_code=500, content=_INTERNAL_ERROR)
    status = _status_for(exc)
    payload = exc.to_dict()
    # #CRITICAL: security: the full payload (value/context) goes to the server
    # log only; the client body is pruned of caller input and internal state to
    # avoid information disclosure (CWE-209).
    # #VERIFY: _client_safe_error drops `value` and `context`; structured log
    # retains them for debugging.
    logger.warning(
        "project_error",
        error=payload.get("error"),
        message=payload.get("message"),
        status_code=status,
        details=payload.get("details"),
    )
    return JSONResponse(status_code=status, content=_client_safe_error(payload))


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        FastAPI: The configured application.
    """
    app = FastAPI(
        title="CYO Adventure",
        version="0.1.0",
        description="Choose-your-own-adventure reader API for the family library.",
    )
    # Correlation must wrap everything else so every log line carries the id.
    app.add_middleware(CorrelationMiddleware)
    add_security_middleware(app)
    app.add_exception_handler(ProjectBaseError, _handle_project_error)
    app.include_router(health.router)
    app.include_router(library.router)
    app.include_router(reading.router)
    app.include_router(generation.router)
    app.include_router(profiles.router)
    app.include_router(ratings.router)
    app.include_router(assignments.router)
    app.include_router(approval.router)
    app.include_router(me.router)
    return app


app = create_app()
