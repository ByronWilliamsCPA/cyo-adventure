"""Tests for cyo_adventure.middleware.security module.

Covers SecurityHeadersMiddleware, RateLimitMiddleware, SSRFPreventionMiddleware,
and the add_security_middleware configuration function.

All tests use a minimal FastAPI app with TestClient; no real network calls.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.security]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_app() -> FastAPI:
    """Return a bare FastAPI app with a simple GET / endpoint."""
    app = FastAPI()

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"hello": "world"}

    return app


def _app_with_security_headers() -> FastAPI:
    from cyo_adventure.middleware.security import SecurityHeadersMiddleware

    app = _minimal_app()
    app.add_middleware(SecurityHeadersMiddleware)
    return app


# ---------------------------------------------------------------------------
# SecurityHeadersMiddleware
# ---------------------------------------------------------------------------


class TestSecurityHeadersMiddleware:
    """Tests for OWASP security-header injection."""

    @pytest.mark.unit
    def test_x_content_type_options_header_present(self) -> None:
        """SecurityHeadersMiddleware adds X-Content-Type-Options: nosniff."""
        client = TestClient(_app_with_security_headers(), raise_server_exceptions=True)
        response = client.get("/")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    @pytest.mark.unit
    def test_x_frame_options_header_present(self) -> None:
        """SecurityHeadersMiddleware adds X-Frame-Options: DENY."""
        client = TestClient(_app_with_security_headers(), raise_server_exceptions=True)
        response = client.get("/")

        assert response.headers.get("X-Frame-Options") == "DENY"

    @pytest.mark.unit
    def test_x_xss_protection_header_present(self) -> None:
        """SecurityHeadersMiddleware adds X-XSS-Protection."""
        client = TestClient(_app_with_security_headers(), raise_server_exceptions=True)
        response = client.get("/")

        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    @pytest.mark.unit
    def test_content_security_policy_header_present(self) -> None:
        """SecurityHeadersMiddleware adds Content-Security-Policy header."""
        client = TestClient(_app_with_security_headers(), raise_server_exceptions=True)
        response = client.get("/")

        assert "default-src 'self'" in response.headers.get(
            "Content-Security-Policy", ""
        )

    @pytest.mark.unit
    def test_referrer_policy_header_present(self) -> None:
        """SecurityHeadersMiddleware adds Referrer-Policy header."""
        client = TestClient(_app_with_security_headers(), raise_server_exceptions=True)
        response = client.get("/")

        assert (
            response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        )

    @pytest.mark.unit
    def test_permissions_policy_header_present(self) -> None:
        """SecurityHeadersMiddleware adds Permissions-Policy header."""
        client = TestClient(_app_with_security_headers(), raise_server_exceptions=True)
        response = client.get("/")

        assert "geolocation=()" in response.headers.get("Permissions-Policy", "")

    @pytest.mark.unit
    def test_no_hsts_header_on_http_scheme(self) -> None:
        """SecurityHeadersMiddleware does NOT add HSTS on plain HTTP requests."""
        client = TestClient(_app_with_security_headers(), raise_server_exceptions=True)
        response = client.get("/")

        # TestClient uses http:// scheme, so HSTS must NOT be present.
        assert "Strict-Transport-Security" not in response.headers

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_hsts_header_added_for_https_scheme(self) -> None:
        """SecurityHeadersMiddleware adds HSTS when request scheme is https."""
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import SecurityHeadersMiddleware

        middleware = SecurityHeadersMiddleware(app=MagicMock())

        mock_request = MagicMock()
        mock_request.url.scheme = "https"

        mock_response = MagicMock()
        mock_response.headers = {}

        async def call_next(_req: object) -> object:
            return mock_response

        response = await middleware.dispatch(mock_request, call_next)  # type: ignore[arg-type]

        assert "Strict-Transport-Security" in response.headers  # type: ignore[operator]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_server_header_removed_when_present(self) -> None:
        """SecurityHeadersMiddleware removes Server header from responses."""
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import SecurityHeadersMiddleware

        middleware = SecurityHeadersMiddleware(app=MagicMock())

        mock_request = MagicMock()
        mock_request.url.scheme = "http"

        # Simulate a response that leaks a Server header
        headers: dict[str, str] = {"Server": "uvicorn/0.21.0"}

        mock_response = MagicMock()
        mock_response.headers = headers

        async def call_next(_req: object) -> object:
            return mock_response

        response = await middleware.dispatch(mock_request, call_next)  # type: ignore[arg-type]

        assert "Server" not in response.headers  # type: ignore[operator]


# ---------------------------------------------------------------------------
# RateLimitMiddleware
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    """Tests for the in-memory rate limiter."""

    def _rate_limited_app(
        self, requests_per_minute: int = 3, burst_size: int = 100
    ) -> FastAPI:
        from cyo_adventure.middleware.security import RateLimitMiddleware

        app = _minimal_app()
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=requests_per_minute,
            burst_size=burst_size,
        )
        return app

    @pytest.mark.unit
    def test_requests_below_limit_pass_through(self) -> None:
        """Requests under the rate limit receive a 200 response."""
        client = TestClient(self._rate_limited_app(requests_per_minute=10))
        response = client.get("/")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_requests_exceeding_rate_limit_receive_429(self) -> None:
        """Requests exceeding the per-minute limit receive HTTP 429."""
        app = self._rate_limited_app(requests_per_minute=2, burst_size=100)
        client = TestClient(app, raise_server_exceptions=False)

        # Exhaust the limit
        client.get("/")
        client.get("/")
        response = client.get("/")

        assert response.status_code == 429

    @pytest.mark.unit
    def test_429_response_includes_retry_after_header(self) -> None:
        """HTTP 429 response includes a Retry-After header."""
        app = self._rate_limited_app(requests_per_minute=1, burst_size=100)
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/")
        response = client.get("/")

        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @pytest.mark.unit
    def test_burst_limit_returns_429(self) -> None:
        """Rapid burst of requests exceeding burst_size receives HTTP 429."""
        from cyo_adventure.middleware.security import RateLimitMiddleware

        app = _minimal_app()
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=1000,
            burst_size=2,
        )
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/")
        client.get("/")
        response = client.get("/")

        assert response.status_code == 429

    @pytest.mark.unit
    def test_rate_limiter_cleanup_stale_entries(self) -> None:
        """_cleanup_stale_entries removes expired IP timestamps."""
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import RateLimitMiddleware

        middleware = RateLimitMiddleware(
            app=MagicMock(),
            requests_per_minute=60,
            burst_size=10,
            cleanup_interval=0,  # Trigger cleanup on every call
        )

        old_time = time.time() - 120  # 2 minutes ago
        middleware.requests["1.2.3.4"] = [old_time]
        middleware._last_cleanup = 0  # Force cleanup

        middleware._cleanup_stale_entries(time.time())

        assert "1.2.3.4" not in middleware.requests

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rate_limiter_no_client_uses_unknown_ip(self) -> None:
        """RateLimitMiddleware handles request.client=None without crashing."""
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=MagicMock(), requests_per_minute=60)

        mock_request = MagicMock()
        mock_request.client = None  # Simulate missing client

        mock_response = MagicMock()

        async def call_next(_req: object) -> object:
            return mock_response

        result = await middleware.dispatch(mock_request, call_next)  # type: ignore[arg-type]

        assert result is mock_response
        assert "unknown" in middleware.requests


# ---------------------------------------------------------------------------
# SSRFPreventionMiddleware
# ---------------------------------------------------------------------------


class TestSSRFPreventionMiddleware:
    """Tests for SSRF URL blocking logic."""

    def _ssrf_app(self) -> FastAPI:
        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        app = _minimal_app()
        app.add_middleware(SSRFPreventionMiddleware)
        return app

    @pytest.mark.unit
    def test_normal_request_passes_through(self) -> None:
        """Requests without URL-like params are allowed through."""
        client = TestClient(self._ssrf_app(), raise_server_exceptions=True)
        response = client.get("/")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_ssrf_blocked_url_in_query_param_returns_400(self) -> None:
        """A query parameter containing a localhost URL triggers SSRF block (400)."""
        client = TestClient(self._ssrf_app(), raise_server_exceptions=False)
        response = client.get("/?target=http://localhost/secret")

        assert response.status_code == 400

    @pytest.mark.unit
    def test_ssrf_blocked_private_ip_in_query_param_returns_400(self) -> None:
        """A query parameter with a private IP URL is blocked."""
        client = TestClient(self._ssrf_app(), raise_server_exceptions=False)
        response = client.get("/?url=http://192.168.1.1/internal")

        assert response.status_code == 400

    @pytest.mark.unit
    def test_ssrf_blocked_scheme_in_query_param_returns_400(self) -> None:
        """A query parameter with a blocked scheme (file://) is rejected."""
        client = TestClient(self._ssrf_app(), raise_server_exceptions=False)
        response = client.get("/?path=file:///etc/passwd")

        assert response.status_code == 400

    @pytest.mark.unit
    def test_ssrf_external_url_is_allowed(self) -> None:
        """A query parameter with an external HTTPS URL is allowed through."""
        client = TestClient(self._ssrf_app(), raise_server_exceptions=True)
        response = client.get("/?callback=https://api.example.com/webhook")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_is_private_ip_loopback(self) -> None:
        """_is_private_ip returns True for loopback address 127.0.0.1."""
        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        assert SSRFPreventionMiddleware._is_private_ip("127.0.0.1") is True

    @pytest.mark.unit
    def test_is_private_ip_private_range(self) -> None:
        """_is_private_ip returns True for RFC-1918 private addresses."""
        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        assert SSRFPreventionMiddleware._is_private_ip("10.0.0.1") is True
        assert SSRFPreventionMiddleware._is_private_ip("192.168.0.1") is True

    @pytest.mark.unit
    def test_is_private_ip_public_address(self) -> None:
        """_is_private_ip returns False for a public IP address."""
        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        assert SSRFPreventionMiddleware._is_private_ip("8.8.8.8") is False

    @pytest.mark.unit
    def test_is_private_ip_invalid_string(self) -> None:
        """_is_private_ip returns False for a non-IP string (handled gracefully)."""
        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        assert SSRFPreventionMiddleware._is_private_ip("not-an-ip") is False

    @pytest.mark.unit
    def test_is_private_ip_ipv4_mapped_ipv6(self) -> None:
        """_is_private_ip returns True for an IPv4-mapped IPv6 loopback address."""
        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        # ::ffff:127.0.0.1 is the IPv4-mapped IPv6 form of 127.0.0.1
        assert SSRFPreventionMiddleware._is_private_ip("::ffff:127.0.0.1") is True

    @pytest.mark.unit
    def test_is_blocked_url_blocked_scheme(self) -> None:
        """_is_blocked_url returns True for a gopher:// URL."""
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        middleware = SSRFPreventionMiddleware(app=MagicMock())

        assert middleware._is_blocked_url("gopher://internal.host/") is True

    @pytest.mark.unit
    def test_is_blocked_url_blocked_host(self) -> None:
        """_is_blocked_url returns True for a known blocked hostname."""
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        middleware = SSRFPreventionMiddleware(app=MagicMock())

        assert middleware._is_blocked_url("http://metadata.google.internal/") is True

    @pytest.mark.unit
    def test_is_blocked_url_decimal_ip_obfuscation(self) -> None:
        """_is_blocked_url detects integer decimal notation for 127.0.0.1 (2130706433)."""
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        middleware = SSRFPreventionMiddleware(app=MagicMock())

        # 2130706433 == 127.0.0.1 in decimal
        assert middleware._is_blocked_url("http://2130706433/secret") is True

    @pytest.mark.unit
    def test_is_blocked_url_no_host_returns_false(self) -> None:
        """_is_blocked_url returns False when URL has no parseable host."""
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        middleware = SSRFPreventionMiddleware(app=MagicMock())

        # A plain relative path has no scheme or host
        assert middleware._is_blocked_url("/relative/path") is False


# ---------------------------------------------------------------------------
# add_security_middleware
# ---------------------------------------------------------------------------


class TestAddSecurityMiddleware:
    """Tests for the add_security_middleware configuration helper."""

    @pytest.mark.unit
    def test_add_security_middleware_returns_none(self) -> None:
        """add_security_middleware does not return a value."""
        from cyo_adventure.middleware.security import add_security_middleware

        app = _minimal_app()
        result = add_security_middleware(app)

        assert result is None

    @pytest.mark.unit
    def test_add_security_middleware_default_config_allows_requests(self) -> None:
        """App with default security middleware still serves requests successfully."""
        from cyo_adventure.middleware.security import add_security_middleware

        app = _minimal_app()
        add_security_middleware(app)
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_add_security_middleware_with_allowed_hosts(self) -> None:
        """add_security_middleware accepts allowed_hosts without error."""
        from cyo_adventure.middleware.security import add_security_middleware

        app = _minimal_app()
        # Should not raise
        add_security_middleware(app, allowed_hosts=["testserver", "localhost"])

    @pytest.mark.unit
    def test_add_security_middleware_with_https_redirect(self) -> None:
        """add_security_middleware registers HTTPSRedirectMiddleware when requested."""
        from cyo_adventure.middleware.security import add_security_middleware

        app = _minimal_app()
        # Should not raise during setup
        add_security_middleware(app, enable_https_redirect=True)

    @pytest.mark.unit
    def test_add_security_middleware_disable_rate_limiting(self) -> None:
        """add_security_middleware skips RateLimitMiddleware when disabled."""
        from cyo_adventure.middleware.security import add_security_middleware

        app = _minimal_app()
        add_security_middleware(app, enable_rate_limiting=False)
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_add_security_middleware_disable_ssrf_prevention(self) -> None:
        """add_security_middleware skips SSRFPreventionMiddleware when disabled."""
        from cyo_adventure.middleware.security import add_security_middleware

        app = _minimal_app()
        add_security_middleware(app, enable_ssrf_prevention=False)
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_add_security_middleware_with_allowed_origins(self) -> None:
        """add_security_middleware accepts a list of CORS allowed_origins."""
        from cyo_adventure.middleware.security import add_security_middleware

        app = _minimal_app()
        add_security_middleware(
            app,
            allowed_origins=["https://example.com", "https://app.example.com"],
        )
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/")

        assert response.status_code == 200

    @pytest.mark.unit
    def test_add_security_middleware_custom_rate_limit(self) -> None:
        """add_security_middleware applies a custom rate_limit_rpm."""
        from cyo_adventure.middleware.security import add_security_middleware

        app = _minimal_app()
        add_security_middleware(app, rate_limit_rpm=120, enable_ssrf_prevention=False)
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/")

        assert response.status_code == 200
