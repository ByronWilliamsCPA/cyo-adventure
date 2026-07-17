"""Unit tests for the app factory module (app.py).

Covers: _status_for() for every mapped exception type and the default fallback,
_handle_project_error() for ProjectBaseError and non-ProjectBaseError input, and
create_app() returning a configured FastAPI instance.
"""

from __future__ import annotations

import json
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
