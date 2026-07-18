"""Unit tests for the app factory module (app.py).

Covers: _status_for() for every mapped exception type and the default fallback,
_handle_project_error() for ProjectBaseError and non-ProjectBaseError input, and
create_app() returning a configured FastAPI instance.
"""

from __future__ import annotations

import json
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from cyo_adventure.app import (
    _INTERNAL_ERROR,
    _handle_project_error,
    _status_for,
    create_app,
)
from cyo_adventure.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusinessLogicError,
    ConfigurationError,
    DatabaseError,
    ExternalServiceError,
    ProjectBaseError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# _status_for
# ---------------------------------------------------------------------------


class TestStatusFor:
    @pytest.mark.unit
    def test_authentication_error_maps_to_401(self) -> None:
        assert _status_for(AuthenticationError("bad token")) == 401

    @pytest.mark.unit
    def test_authorization_error_maps_to_403(self) -> None:
        assert _status_for(AuthorizationError("forbidden")) == 403

    @pytest.mark.unit
    def test_resource_not_found_error_maps_to_404(self) -> None:
        assert _status_for(ResourceNotFoundError("missing")) == 404

    @pytest.mark.unit
    def test_validation_error_maps_to_422(self) -> None:
        assert _status_for(ValidationError("invalid")) == 422

    @pytest.mark.unit
    def test_business_logic_error_falls_back_to_400(self) -> None:
        assert _status_for(BusinessLogicError("conflict")) == 400

    @pytest.mark.unit
    def test_configuration_error_falls_back_to_400(self) -> None:
        assert _status_for(ConfigurationError("bad config")) == 400

    @pytest.mark.unit
    def test_database_error_falls_back_to_400(self) -> None:
        assert _status_for(DatabaseError("db fail")) == 400

    @pytest.mark.unit
    def test_external_service_error_falls_back_to_400(self) -> None:
        assert _status_for(ExternalServiceError("upstream down")) == 400

    @pytest.mark.unit
    def test_status_for_state_transition_is_409(self) -> None:
        """A StateTransitionError maps to 409; bare BusinessLogicError stays 400."""
        assert _status_for(StateTransitionError("illegal hop")) == 409
        assert _status_for(BusinessLogicError("conflict")) == 400


# ---------------------------------------------------------------------------
# _handle_project_error
# ---------------------------------------------------------------------------


class TestHandleProjectError:
    @pytest.mark.unit
    def test_project_base_error_returns_mapped_status(self) -> None:
        """A ProjectBaseError subclass gets the correct status from _status_for."""
        request = MagicMock()
        exc = ResourceNotFoundError("no such item")
        response = _handle_project_error(request, exc)
        assert response.status_code == 404

    @pytest.mark.unit
    def test_project_base_error_body_contains_error_key(self) -> None:
        """The response body contains the error type key."""
        request = MagicMock(spec=Request)
        exc = ValidationError("bad value", field="email", value="x")
        response = _handle_project_error(request, exc)
        body = json.loads(response.body)
        assert "error" in body

    @pytest.mark.unit
    def test_handle_project_error_omits_validation_value(self) -> None:
        """Raw caller input in `value` must not appear in the client response body."""
        request = MagicMock(spec=Request)
        exc = ValidationError("bad email", field="email", value="secret@example.com")
        resp = _handle_project_error(request, exc)
        assert resp.status_code == 422
        body = json.loads(bytes(resp.body))
        details = body.get("details", {})
        assert "value" not in details
        assert details.get("field") == "email"

    @pytest.mark.unit
    def test_handle_project_error_omits_business_context(self) -> None:
        """Internal lifecycle `context` must not appear in the client response body."""
        request = MagicMock(spec=Request)
        exc = StateTransitionError(
            "cannot approve",
            rule="invalid_state_transition",
            context={"from": "draft", "action": "approve"},
        )
        resp = _handle_project_error(request, exc)
        assert resp.status_code == 409
        body = json.loads(bytes(resp.body))
        details = body.get("details", {})
        assert "context" not in details
        assert details.get("rule") == "invalid_state_transition"
        assert body["message"] == "cannot approve"

    @pytest.mark.unit
    def test_non_project_error_returns_500_internal(self) -> None:
        """A plain Exception that is not a ProjectBaseError returns 500."""
        request = MagicMock()
        exc = RuntimeError("unexpected")
        response = _handle_project_error(request, exc)
        assert response.status_code == 500

    @pytest.mark.unit
    def test_non_project_error_body_is_internal_error(self) -> None:
        """The 500 body contains the generic InternalError key."""
        request = MagicMock()
        response = _handle_project_error(request, RuntimeError("boom"))
        body = json.loads(response.body)
        assert body["error"] == "InternalError"

    @pytest.mark.unit
    def test_authentication_error_returns_401(self) -> None:
        request = MagicMock()
        response = _handle_project_error(request, AuthenticationError("unauth"))
        assert response.status_code == 401

    @pytest.mark.unit
    def test_authorization_error_returns_403(self) -> None:
        request = MagicMock()
        response = _handle_project_error(request, AuthorizationError("denied"))
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# create_app
# ---------------------------------------------------------------------------


class TestCreateApp:
    @pytest.mark.unit
    def test_create_app_returns_fastapi_instance(self) -> None:
        """create_app() returns a FastAPI instance."""
        app = create_app()
        assert isinstance(app, FastAPI)

    @pytest.mark.unit
    def test_app_title_is_set(self) -> None:
        """The returned app has the expected title."""
        app = create_app()
        assert app.title == "CYO Adventure"

    @pytest.mark.unit
    def test_health_endpoint_responds(self) -> None:
        """The /health/live liveness probe is reachable on the created app."""
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health/live")
        assert response.status_code == 200

    @pytest.mark.unit
    def test_project_error_handler_returns_json(self) -> None:
        """A ProjectBaseError raised in a route is rendered to JSON by the handler."""
        import json

        app = create_app()

        @app.get("/test-error")
        async def _raise() -> None:
            raise ResourceNotFoundError("test item not found")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-error")
        assert response.status_code == 404
        body = json.loads(response.content)
        assert "error" in body

    @pytest.mark.unit
    def test_project_base_error_subclass_is_valid(self) -> None:
        """ProjectBaseError instances all satisfy isinstance(exc, ProjectBaseError)."""
        for cls in (
            AuthenticationError,
            AuthorizationError,
            ResourceNotFoundError,
            ValidationError,
            BusinessLogicError,
            ConfigurationError,
        ):
            assert isinstance(cls("msg"), ProjectBaseError)


# ---------------------------------------------------------------------------
# ResponseValidationError handler (#48)
# ---------------------------------------------------------------------------


class TestResponseValidationErrorHandler:
    """A route whose return value violates its response_model must surface the
    standard error envelope (500 + correlation id), not an unhandled traceback."""

    @pytest.mark.unit
    def test_response_model_violation_returns_standard_envelope(self) -> None:
        from pydantic import BaseModel

        class _StrictModel(BaseModel):
            status: str

        app = create_app()

        @app.get("/test-response-validation", response_model=_StrictModel)
        async def _bad_response() -> dict[str, str]:
            return {}  # missing required `status` field triggers ResponseValidationError

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-response-validation")

        assert response.status_code == 500
        body = json.loads(response.content)
        assert body == _INTERNAL_ERROR
        assert "X-Correlation-ID" in response.headers


# ---------------------------------------------------------------------------
# CORS allowlist regression guard
# ---------------------------------------------------------------------------


class TestCorsAllowlist:
    """Tests that the CORS middleware is configured with an explicit header allowlist.

    A regression to allow_headers=['*'] with allow_credentials=True would violate
    the CORS spec and silently pass the existing test suite without this guard.
    """

    @pytest.mark.unit
    def test_cors_allow_headers_is_not_wildcard(self) -> None:
        """add_security_middleware must not use allow_headers=['*']."""
        from starlette.middleware.cors import CORSMiddleware

        from cyo_adventure.middleware.security import add_security_middleware

        app = FastAPI()
        add_security_middleware(app, allowed_origins=["http://localhost:3000"])

        cors_mw = next(
            (m for m in app.user_middleware if m.cls is CORSMiddleware),
            None,
        )
        assert cors_mw is not None, "CORSMiddleware not found in middleware stack"
        allow_headers = cors_mw.kwargs.get("allow_headers", [])
        assert "*" not in allow_headers, (
            "allow_headers=['*'] with allow_credentials=True is a CORS misconfiguration"
        )

    @pytest.mark.unit
    def test_cors_allow_headers_includes_authorization(self) -> None:
        """The CORS allowlist must include Authorization for bearer-token flows."""
        from starlette.middleware.cors import CORSMiddleware

        from cyo_adventure.middleware.security import add_security_middleware

        app = FastAPI()
        add_security_middleware(app, allowed_origins=["http://localhost:3000"])

        cors_mw = next(
            (m for m in app.user_middleware if m.cls is CORSMiddleware),
            None,
        )
        assert cors_mw is not None
        allow_headers = cors_mw.kwargs.get("allow_headers", [])
        assert "Authorization" in allow_headers


# ---------------------------------------------------------------------------
# Environment-aware rate limiting
# ---------------------------------------------------------------------------


class TestRateLimitingByEnvironment:
    """create_app() must disable the in-memory rate limiter in ENVIRONMENT=local.

    The single-user local stack (dev work, the e2e-real serial suite that now
    drives full kid journeys) legitimately exceeds the 60 rpm public ceiling
    from one localhost IP. Gating the limiter on environment mirrors the
    codebase's existing local-relaxation pattern for the OIDC and signing-secret
    guards, while keeping it active for every deployed tier.
    """

    @pytest.mark.unit
    def test_rate_limiting_absent_in_local_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No RateLimitMiddleware is wired when environment is local."""
        from cyo_adventure.core.config import settings
        from cyo_adventure.middleware import RateLimitMiddleware

        monkeypatch.setattr(settings, "environment", "local")
        app = create_app()

        assert not any(m.cls is RateLimitMiddleware for m in app.user_middleware), (
            "RateLimitMiddleware must be disabled in ENVIRONMENT=local"
        )

    @pytest.mark.unit
    def test_rate_limiting_present_outside_local_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RateLimitMiddleware is wired for deployed (non-local) environments."""
        from cyo_adventure.core.config import settings
        from cyo_adventure.middleware import RateLimitMiddleware

        monkeypatch.setattr(settings, "environment", "production")
        app = create_app()

        assert any(m.cls is RateLimitMiddleware for m in app.user_middleware), (
            "RateLimitMiddleware must stay enabled outside ENVIRONMENT=local"
        )


# ---------------------------------------------------------------------------
# Trusted host allowlist (SEC-B3)
# ---------------------------------------------------------------------------


class TestTrustedHost:
    """create_app() wires TrustedHostMiddleware only when allowed_hosts is set."""

    @pytest.mark.unit
    def test_trusted_host_absent_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no allowed_hosts configured the middleware is not added."""
        from starlette.middleware.trustedhost import TrustedHostMiddleware

        from cyo_adventure.core.config import settings

        monkeypatch.setattr(settings, "allowed_hosts", "")
        app = create_app()

        assert not any(m.cls is TrustedHostMiddleware for m in app.user_middleware)

    @pytest.mark.unit
    def test_trusted_host_present_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A comma-separated allowlist wires TrustedHostMiddleware."""
        from starlette.middleware.trustedhost import TrustedHostMiddleware

        from cyo_adventure.core.config import settings

        monkeypatch.setattr(
            settings, "allowed_hosts", "cyoadventure.app, api.cyoadventure.app"
        )
        app = create_app()

        assert any(m.cls is TrustedHostMiddleware for m in app.user_middleware)


# OpenAPI contract customization (_DocumentedApp / _document_bearer_security)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    """Build the customized OpenAPI schema once for this module.

    Module-scoped (not a class-scoped instance method, which pytest deprecates
    under this project's ``filterwarnings = ["error"]``) so the schema builds
    a single time for the whole contract-test class below.
    """
    return create_app().openapi()


class TestOpenApiContract:
    """Pins the documentation-only OpenAPI rewrite in ``_DocumentedApp``.

    The rewrite must declare one HTTP bearer scheme, mark every authenticated
    operation with it (replacing the raw ``authorization`` header parameter
    FastAPI derives from the auth dependency), leave the health probes
    untouched, and report the installed distribution version. These tests are
    the contract the generated frontend client and docs/api/README.md rely on.
    """

    @staticmethod
    def _operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
        """Return (path, method, operation) for every operation in the schema."""
        methods = ("get", "post", "put", "patch", "delete")
        paths = cast("dict[str, dict[str, dict[str, Any]]]", schema["paths"])
        return [
            (path, method, operation)
            for path, item in paths.items()
            for method, operation in item.items()
            if method in methods
        ]

    @pytest.mark.unit
    def test_bearer_scheme_is_declared(self, schema: dict[str, Any]) -> None:
        """components.securitySchemes carries one HTTP bearer scheme."""
        scheme = schema["components"]["securitySchemes"]["HTTPBearer"]

        assert scheme["type"] == "http"
        assert scheme["scheme"] == "bearer"

    @pytest.mark.unit
    def test_every_api_operation_requires_bearer_auth(
        self, schema: dict[str, Any]
    ) -> None:
        """Every non-health operation carries the security requirement."""
        api_ops = [
            (path, method, op)
            for path, method, op in self._operations(schema)
            if not path.startswith("/health")
        ]

        assert api_ops, "expected /api/v1 operations in the schema"
        for path, method, op in api_ops:
            assert op.get("security") == [{"HTTPBearer": []}], (
                f"{method.upper()} {path} must document bearer auth"
            )

    @pytest.mark.unit
    def test_no_raw_authorization_header_parameter_survives(
        self, schema: dict[str, Any]
    ) -> None:
        """The redundant authorization header parameter is stripped everywhere."""
        for path, method, op in self._operations(schema):
            params = cast("list[dict[str, Any]]", op.get("parameters", []))
            leaked = [
                p
                for p in params
                if p.get("in") == "header"
                and str(p.get("name", "")).lower() == "authorization"
            ]

            assert not leaked, (
                f"{method.upper()} {path} still documents a raw authorization header"
            )

    @pytest.mark.unit
    def test_health_probes_stay_unauthenticated(self, schema: dict[str, Any]) -> None:
        """The health probes carry no security requirement."""
        health_ops = [
            (path, method, op)
            for path, method, op in self._operations(schema)
            if path.startswith("/health")
        ]

        assert health_ops, "expected /health operations in the schema"
        for path, method, op in health_ops:
            assert "security" not in op, (
                f"{method.upper()} {path} must stay unauthenticated"
            )

    @pytest.mark.unit
    def test_info_version_tracks_installed_distribution(
        self, schema: dict[str, Any]
    ) -> None:
        """info.version reports the package version, not a hardcoded literal."""
        import cyo_adventure

        assert schema["info"]["version"] == cyo_adventure.__version__

    @pytest.mark.unit
    def test_tag_metadata_covers_every_operation_tag(
        self, schema: dict[str, Any]
    ) -> None:
        """Every tag used by an operation has a described top-level entry."""
        declared = {
            cast("dict[str, str]", tag)["name"]: cast("dict[str, str]", tag).get(
                "description", ""
            )
            for tag in cast("list[dict[str, Any]]", schema["tags"])
        }
        used = {
            tag
            for _, _, op in self._operations(schema)
            for tag in cast("list[str]", op.get("tags", []))
        }

        assert used <= set(declared), f"tags without metadata: {used - set(declared)}"
        assert all(declared.values()), "every declared tag needs a description"

    @pytest.mark.unit
    def test_error_envelope_schema_is_documented(self, schema: dict[str, Any]) -> None:
        """components.schemas carries the exception handlers' envelope."""
        envelope = schema["components"]["schemas"]["ErrorResponse"]

        assert set(envelope["required"]) == {"error", "message"}
        assert set(envelope["properties"]) == {"error", "message", "code", "details"}

    @pytest.mark.unit
    def test_admin_users_patch_documents_error_statuses(
        self, schema: dict[str, Any]
    ) -> None:
        """A representative admin op documents 401/403/404 with the envelope."""
        responses = schema["paths"]["/api/v1/admin/users/{user_id}"]["patch"][
            "responses"
        ]

        for status_code in ("401", "403", "404"):
            ref = responses[status_code]["content"]["application/json"]["schema"]
            assert ref == {"$ref": "#/components/schemas/ErrorResponse"}, (
                f"PATCH /admin/users must document {status_code} with ErrorResponse"
            )

    @pytest.mark.unit
    def test_reading_put_keeps_conflict_view_on_409(
        self, schema: dict[str, Any]
    ) -> None:
        """The reading-state PUT keeps its richer 409 ConflictView body."""
        responses = schema["paths"][
            "/api/v1/reading-state/{profile_id}/{storybook_id}"
        ]["put"]["responses"]
        ref = responses["409"]["content"]["application/json"]["schema"]

        assert ref == {"$ref": "#/components/schemas/ConflictView"}

    @pytest.mark.unit
    def test_openapi_schema_is_built_once_and_cached(self) -> None:
        """Repeated openapi() calls return the same customized object."""
        app = create_app()

        assert app.openapi() is app.openapi()


class TestErrorResponsesHelper:
    """Pins the shape of the shared ``error_responses`` declaration helper."""

    @pytest.mark.unit
    def test_builds_one_envelope_entry_per_status(self) -> None:
        """Each requested status maps to the envelope model and a description."""
        from cyo_adventure.api.schemas import ErrorResponse, error_responses

        built = error_responses(401, 403, 404, 409, 400)

        assert set(built) == {400, 401, 403, 404, 409}
        for entry in built.values():
            assert entry["model"] is ErrorResponse
            assert isinstance(entry["description"], str)
            assert entry["description"]

    @pytest.mark.unit
    def test_rejects_an_undescribed_status(self) -> None:
        """A status without a curated description is a programming error."""
        from cyo_adventure.api.schemas import error_responses

        with pytest.raises(KeyError):
            error_responses(418)
