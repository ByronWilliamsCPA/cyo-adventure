"""FastAPI application factory.

Wires correlation (first) and security middleware, maps the core exception
hierarchy to HTTP status codes, and mounts the health, library, and reading
routers. The OpenAPI schema this app exposes is the source of truth for the
generated frontend client.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cyo_adventure.api import health, library, reading
from cyo_adventure.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ProjectBaseError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.middleware import CorrelationMiddleware, add_security_middleware

_INTERNAL_ERROR = {"error": "InternalError", "message": "internal error"}


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
    return 400


def _handle_project_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render a core exception as a JSON error response.

    Args:
        _request: The incoming request (unused).
        exc: The exception raised during handling.

    Returns:
        JSONResponse: The error body with the mapped status code.
    """
    if not isinstance(exc, ProjectBaseError):
        return JSONResponse(status_code=500, content=_INTERNAL_ERROR)
    return JSONResponse(status_code=_status_for(exc), content=exc.to_dict())


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
    return app


app = create_app()
