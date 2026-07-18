"""FastAPI application factory.

Wires correlation (first) and security middleware, maps the core exception
hierarchy to HTTP status codes, and mounts the health, library, and reading
routers. The OpenAPI schema this app exposes is the source of truth for the
generated frontend client.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse

from cyo_adventure import __version__
from cyo_adventure.api import (
    admin_profiles,
    admin_users,
    approval,
    assignments,
    audit,
    child_sessions,
    covers,
    device_grants,
    families,
    family_connections,
    flags,
    generation,
    health,
    library,
    me,
    moderation_dashboard,
    moderation_thresholds,
    node_edit,
    notifications,
    onboarding,
    profiles,
    provider_allowlist,
    ratings,
    reading,
    reading_history,
    recommendations,
    rescreen,
    story_requests,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ProjectBaseError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.core.observability import init_sentry
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


def _handle_response_validation_error(
    _request: Request, exc: Exception
) -> JSONResponse:
    """Render a ResponseValidationError as the standard JSON error envelope.

    Raised when a route's return value violates its `response_model` (for
    example, a status field narrowed to a `Literal` no longer matching
    runtime data, issue #48). This is a server-side bug, not caller input, so
    it must never surface as an unhandled traceback to the client. The full
    Pydantic error detail is logged server-side only; the client gets the
    same generic `InternalError` envelope as any other unmapped exception.

    Args:
        _request: The incoming request (unused).
        exc: The `ResponseValidationError` raised during response
            serialization.

    Returns:
        JSONResponse: The standard `InternalError` envelope with a 500
        status code.
    """
    # #CRITICAL: data integrity: a response_model violation means the route
    # returned data its own contract disallows (e.g. a stale Literal). This
    # is a bug to fix in the route, not a client error, so log full detail
    # (with correlation id, via correlation_context_processor) at error level
    # for debugging while keeping the client body generic.
    # #VERIFY: alerting/monitoring on this log event so silent contract drift
    # is caught before it reaches production traffic.
    logger.error("response_validation_error", error=str(exc))
    return JSONResponse(status_code=500, content=_INTERNAL_ERROR)


def _handle_request_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render a RequestValidationError without echoing the submitted input.

    FastAPI's default handler returns each Pydantic error verbatim, including
    the ``input`` field that repeats the caller's raw submitted value (and a
    ``ctx`` field that can embed it too). That bypasses this app's CWE-209
    sanitization posture (`_client_safe_error` strips ``value``/``context``
    from the core-exception path): a malformed profile PIN, for example, would
    be echoed back in the 422 body. Only ``type``/``loc``/``msg`` survive to
    the client; the full detail is available server-side via the log below.

    Args:
        _request: The incoming request (unused).
        exc: The ``RequestValidationError`` raised by request parsing.

    Returns:
        JSONResponse: A 422 body whose ``detail`` entries carry only
        ``type``, ``loc``, and ``msg``.
    """
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        return JSONResponse(status_code=500, content=_INTERNAL_ERROR)
    # exc.errors() is typed as returning Any-valued dicts; pin the shape so
    # the sanitizing projection below stays type-checked.
    errors = cast("list[dict[str, object]]", exc.errors())
    # #CRITICAL: security: log only the sanitized shape as well. Request
    # bodies on this app can carry credential material (the profile PIN),
    # which must never be written to logs either (same posture as the
    # token-never-logged rule in the frontend's logApiError).
    # #VERIFY: tests/integration/test_profiles.py asserts a malformed PIN
    # never appears in the 422 body.
    safe = [
        {"type": e.get("type"), "loc": e.get("loc"), "msg": e.get("msg")}
        for e in errors
    ]
    logger.warning("request_validation_error", errors=safe)
    return JSONResponse(status_code=422, content={"detail": safe})


# One entry per router tag, in the order the docs UI should group them:
# probes, then kid/guardian reader surfaces, then intake/pipeline, then the
# admin console. Keep in sync with the routers wired in create_app below.
_OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "health",
        "description": "Liveness, readiness, and startup probes (unauthenticated).",
    },
    {
        "name": "me",
        "description": "The authenticated caller's own identity, role, and capabilities.",
    },
    {
        "name": "onboarding",
        "description": "First-login guardian provisioning (idempotent family/user creation).",
    },
    {
        "name": "library",
        "description": "A profile's published-book library and story version fetches.",
    },
    {
        "name": "reading",
        "description": "Reading-state saves with optimistic concurrency, completions, and series continuation.",
    },
    {"name": "ratings", "description": "A child profile's star ratings of storybooks."},
    {
        "name": "reading-history",
        "description": "Reading-history reads for the kid and guardian surfaces.",
    },
    {
        "name": "recommendations",
        "description": "A profile's recommendation feed across the family and connected-family rings (ADR-016).",
    },
    {
        "name": "flags",
        "description": "Kid-raised, structured content flags feeding the admin moderation queue.",
    },
    {
        "name": "notifications",
        "description": "The guardian notification feed projected from the pipeline event log.",
    },
    {
        "name": "profiles",
        "description": "Guardian-managed child profiles within the caller's own family.",
    },
    {
        "name": "child-sessions",
        "description": "Guardian-minted, short-lived child session tokens for the kid surface.",
    },
    {
        "name": "device-grants",
        "description": "Durable device authorizations for shared family devices (ADR-014).",
    },
    {
        "name": "story-requests",
        "description": "Story-request intake, screening, and the approve/decline lifecycle.",
    },
    {
        "name": "generation",
        "description": "Concept intake and the gated story-generation job pipeline.",
    },
    {
        "name": "assignments",
        "description": "Guardian assignment of published books to child profiles.",
    },
    {
        "name": "approval",
        "description": "The storybook review/publish state machine: submit, approve, send back, archive.",
    },
    {
        "name": "node-edit",
        "description": "The lightweight passage editor with mandatory re-review (G6).",
    },
    {
        "name": "rescreen",
        "description": "Admin policy re-screen of published storybook versions.",
    },
    {
        "name": "audit",
        "description": "Admin-only audit reads over the append-only pipeline event log.",
    },
    {
        "name": "covers",
        "description": "AI cover-art generation triggers and status reads.",
    },
    {
        "name": "families",
        "description": "Admin listing and lifecycle management of families.",
    },
    {
        "name": "admin-users",
        "description": "Admin console management of guardian and admin accounts.",
    },
    {
        "name": "admin-profiles",
        "description": "Admin console management of child profiles across families.",
    },
    {
        "name": "family-connections",
        "description": "Admin-managed directional cross-family recommendation opt-ins.",
    },
    {
        "name": "moderation-thresholds",
        "description": "Admin surfacing-threshold overrides and the global noise floor.",
    },
    {
        "name": "moderation-dashboard",
        "description": "Admin moderation evidence, override insights, and threshold suggestions.",
    },
    {
        "name": "provider-allowlist",
        "description": "Admin CRUD for the generation provider/model allowlist.",
    },
]

_BEARER_SCHEME_NAME = "HTTPBearer"


def _document_bearer_security(schema: dict[str, Any]) -> dict[str, Any]:
    """Rewrite the OpenAPI schema to document bearer auth as a security scheme.

    The auth seam is a plain ``Authorization`` header dependency
    (``api/deps.py::require_principal``), which FastAPI documents as an
    optional per-operation header parameter rather than a security
    requirement. This rewrite declares one HTTP bearer security scheme,
    replaces each operation's ``authorization`` header parameter with a
    ``security`` requirement, and leaves unauthenticated operations (the
    health probes) untouched. Documentation only: request handling and the
    401 semantics for a missing token are unchanged, and the frontend client
    keeps injecting the header through its axios interceptor
    (``frontend/src/hooks/useApi.ts``), never through a per-call parameter.

    Args:
        schema: The schema produced by FastAPI's default builder.

    Returns:
        dict[str, Any]: The same schema object, rewritten in place.
    """
    components: dict[str, Any] = schema.setdefault("components", {})
    schemes: dict[str, Any] = components.setdefault("securitySchemes", {})
    schemes[_BEARER_SCHEME_NAME] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Supabase-issued guardian/admin JWT, a backend-signed child "
            "session token, or a backend-signed device grant token "
            "(api/deps.py routes on the token's audience). The local dev "
            "environment accepts seeded opaque subjects (docs/api/README.md)."
        ),
    }
    paths = cast("dict[str, dict[str, Any]]", schema.get("paths", {}))
    for path_item in paths.values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            op = cast("dict[str, Any]", operation)
            parameters = cast("list[dict[str, Any]]", op.get("parameters", []))
            kept = [
                param
                for param in parameters
                if not (
                    param.get("in") == "header"
                    and str(param.get("name", "")).lower() == "authorization"
                )
            ]
            if len(kept) == len(parameters):
                continue
            if kept:
                op["parameters"] = kept
            else:
                op.pop("parameters", None)
            op["security"] = [{_BEARER_SCHEME_NAME: []}]
    return schema


class _DocumentedApp(FastAPI):
    """FastAPI app whose OpenAPI schema documents the bearer auth scheme."""

    def openapi(self) -> dict[str, Any]:
        """Build (once) and return the schema with bearer security documented.

        Returns:
            dict[str, Any]: The customized OpenAPI schema.
        """
        if self.openapi_schema is None:
            self.openapi_schema = _document_bearer_security(super().openapi())
        return self.openapi_schema


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        FastAPI: The configured application.
    """
    init_sentry(settings)
    app = _DocumentedApp(
        title="CYO Adventure",
        # The installed distribution version tracks pyproject.toml (bumped by
        # the release workflow), so the served schema and /health report the
        # real release instead of a hardcoded string (see __init__.py).
        version=__version__,
        description="Choose-your-own-adventure reader API for the family library.",
        openapi_tags=_OPENAPI_TAGS,
    )
    # #CRITICAL: security: the in-memory rate limiter (60 rpm/IP) is a public
    # deployment defense. It is disabled ONLY in ENVIRONMENT=local, where the
    # single-user dev stack and the e2e-real serial suite legitimately exceed
    # that ceiling from one localhost IP; every deployed tier (dev, staging,
    # production) keeps it on. Mirrors the local-relaxation pattern used for the
    # OIDC and signing-secret guards in core/config.py.
    # #VERIFY: tests/unit/test_app.py::TestRateLimitingByEnvironment asserts the
    # limiter is absent in local and present otherwise.
    #
    # #ASSUME: security: allowed_hosts is a comma-separated Host allowlist;
    # empty leaves TrustedHostMiddleware off (prior behavior). A deployed tier
    # sets its fronting domain(s) so a spoofed Host/X-Forwarded-Host is rejected.
    # #VERIFY: tests/unit/test_app.py::TestTrustedHost.
    _allowed_hosts = [h.strip() for h in settings.allowed_hosts.split(",") if h.strip()]
    add_security_middleware(
        app,
        enable_rate_limiting=settings.environment != "local",
        allowed_hosts=_allowed_hosts or None,
    )
    # #CRITICAL: observability: CorrelationMiddleware is added LAST so it is the
    # OUTERMOST layer (Starlette applies the most-recently-added middleware
    # first). This way a rate-limit / body-size / SSRF rejection emitted by the
    # security middleware still runs inside an active correlation context and
    # carries the id, instead of the correlation layer sitting inside them.
    app.add_middleware(CorrelationMiddleware)
    app.add_exception_handler(ProjectBaseError, _handle_project_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation_error)
    app.add_exception_handler(
        ResponseValidationError, _handle_response_validation_error
    )
    app.include_router(health.router)
    app.include_router(library.router)
    app.include_router(reading.router)
    app.include_router(reading_history.router)
    app.include_router(generation.router)
    app.include_router(profiles.router)
    app.include_router(families.router)
    app.include_router(ratings.router)
    app.include_router(assignments.router)
    app.include_router(approval.router)
    app.include_router(node_edit.router)
    app.include_router(covers.router)
    app.include_router(moderation_thresholds.router)
    app.include_router(moderation_dashboard.router)
    app.include_router(audit.router)
    app.include_router(rescreen.router)
    app.include_router(provider_allowlist.router)
    app.include_router(me.router)
    app.include_router(story_requests.router)
    app.include_router(child_sessions.router)
    app.include_router(device_grants.router)
    app.include_router(onboarding.router)
    app.include_router(flags.router)
    app.include_router(notifications.router)
    app.include_router(admin_users.router)
    app.include_router(admin_profiles.router)
    app.include_router(family_connections.router)
    app.include_router(recommendations.router)
    return app


app = create_app()
