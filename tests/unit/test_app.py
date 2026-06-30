"""Unit tests for the app factory module (app.py).

Covers: _status_for() for every mapped exception type and the default fallback,
_handle_project_error() for ProjectBaseError and non-ProjectBaseError input, and
create_app() returning a configured FastAPI instance.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cyo_adventure.app import _handle_project_error, _status_for, create_app
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
        from unittest.mock import MagicMock

        request = MagicMock()
        exc = ResourceNotFoundError("no such item")
        response = _handle_project_error(request, exc)
        assert response.status_code == 404

    @pytest.mark.unit
    def test_project_base_error_body_uses_to_dict(self) -> None:
        """The response body is the exc.to_dict() JSON."""
        import json
        from unittest.mock import MagicMock

        request = MagicMock()
        exc = ValidationError("bad value", field="email", value="x")
        response = _handle_project_error(request, exc)
        body = json.loads(response.body)
        assert "error" in body

    @pytest.mark.unit
    def test_non_project_error_returns_500_internal(self) -> None:
        """A plain Exception that is not a ProjectBaseError returns 500."""
        from unittest.mock import MagicMock

        request = MagicMock()
        exc = RuntimeError("unexpected")
        response = _handle_project_error(request, exc)
        assert response.status_code == 500

    @pytest.mark.unit
    def test_non_project_error_body_is_internal_error(self) -> None:
        """The 500 body contains the generic InternalError key."""
        import json
        from unittest.mock import MagicMock

        request = MagicMock()
        response = _handle_project_error(request, RuntimeError("boom"))
        body = json.loads(response.body)
        assert body["error"] == "InternalError"

    @pytest.mark.unit
    def test_authentication_error_returns_401(self) -> None:
        from unittest.mock import MagicMock

        request = MagicMock()
        response = _handle_project_error(request, AuthenticationError("unauth"))
        assert response.status_code == 401

    @pytest.mark.unit
    def test_authorization_error_returns_403(self) -> None:
        from unittest.mock import MagicMock

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
