"""Tests for cyo_adventure.middleware.security module.

Covers SecurityHeadersMiddleware, RateLimitMiddleware, SSRFPreventionMiddleware,
the add_security_middleware configuration function, and the proxy-header trust
boundary (Task E1) that lets both RateLimitMiddleware and SecurityHeadersMiddleware
see the real client behind the nginx/Traefik reverse proxy.

All tests use a minimal FastAPI app with TestClient; no real network calls.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI, Request
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
    def test_content_security_policy_includes_hardening_directives(self) -> None:
        """CSP additionally locks down object/base/form vectors (F11).

        ``object-src 'none'`` blocks plugin-based content (Flash/Java applets),
        ``base-uri 'self'`` stops a base-tag injection from rewriting relative
        URLs, and ``form-action 'self'`` stops a form-action hijack from
        exfiltrating form submissions to an attacker-controlled origin.
        """
        client = TestClient(_app_with_security_headers(), raise_server_exceptions=True)
        response = client.get("/")

        csp = response.headers.get("Content-Security-Policy", "")
        assert "object-src 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp

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

    @pytest.mark.unit
    def test_rate_limiter_cleanup_retains_ips_with_recent_activity(self) -> None:
        """_cleanup_stale_entries keeps the recent-timestamp slice for an IP.

        The prior cleanup test only exercises the "all timestamps expired"
        (stale) branch; this covers the sibling branch where filtering still
        leaves at least one recent timestamp, so the IP's entry is trimmed
        in place rather than dropped.
        """
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import RateLimitMiddleware

        middleware = RateLimitMiddleware(
            app=MagicMock(),
            requests_per_minute=60,
            burst_size=10,
            cleanup_interval=0,
        )

        now = time.time()
        middleware.requests["1.2.3.4"] = [now - 120, now - 5]
        middleware._last_cleanup = 0

        middleware._cleanup_stale_entries(now)

        assert middleware.requests["1.2.3.4"] == [now - 5]

    @pytest.mark.unit
    def test_rate_limiter_cleanup_evicts_oldest_ips_over_max_tracked(self) -> None:
        """_cleanup_stale_entries trims to max_tracked_ips, keeping the newest.

        All three IPs here have recent activity, so none are dropped by the
        stale-timestamp check; only the LRU-style max_tracked_ips eviction
        should remove the least-recently-active one.
        """
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import RateLimitMiddleware

        middleware = RateLimitMiddleware(
            app=MagicMock(),
            requests_per_minute=60,
            burst_size=10,
            max_tracked_ips=2,
            cleanup_interval=0,
        )

        now = time.time()
        middleware.requests["1.1.1.1"] = [now - 50]
        middleware.requests["2.2.2.2"] = [now - 30]
        middleware.requests["3.3.3.3"] = [now - 10]
        middleware._last_cleanup = 0

        middleware._cleanup_stale_entries(now)

        assert len(middleware.requests) == 2
        assert "3.3.3.3" in middleware.requests
        assert "2.2.2.2" in middleware.requests
        assert "1.1.1.1" not in middleware.requests


# ---------------------------------------------------------------------------
# BodySizeLimitMiddleware (audit Finding 8: unbounded request body)
# ---------------------------------------------------------------------------


class TestBodySizeLimitMiddleware:
    """Tests for the ASGI-layer request-body size guard (413 over the cap)."""

    def _body_limited_app(self, max_body_bytes: int) -> FastAPI:
        from cyo_adventure.middleware.security import BodySizeLimitMiddleware

        app = FastAPI()

        @app.post("/echo")
        async def echo(request: Request) -> dict[str, int]:
            body = await request.body()
            return {"received": len(body)}

        app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=max_body_bytes)
        return app

    @pytest.mark.unit
    def test_body_at_limit_passes_through(self) -> None:
        """A body exactly at the byte cap is accepted."""
        client = TestClient(self._body_limited_app(max_body_bytes=10))
        response = client.post("/echo", content=b"0123456789")

        assert response.status_code == 200
        assert response.json() == {"received": 10}

    @pytest.mark.unit
    def test_body_over_limit_rejected_with_413(self) -> None:
        """A body one byte over the cap receives HTTP 413, not the handler."""
        client = TestClient(self._body_limited_app(max_body_bytes=10))
        response = client.post("/echo", content=b"0123456789X")

        assert response.status_code == 413

    @pytest.mark.unit
    def test_declared_content_length_over_limit_rejected_without_reading_body(
        self,
    ) -> None:
        """An oversized declared Content-Length is rejected on the fast path."""
        client = TestClient(self._body_limited_app(max_body_bytes=10))
        response = client.post(
            "/echo",
            content=b"0123456789012345",
            headers={"content-length": "16"},
        )

        assert response.status_code == 413

    @pytest.mark.unit
    def test_non_http_scope_passes_through_unmodified(self) -> None:
        """A non-http ASGI scope (e.g. lifespan) is forwarded untouched."""
        from cyo_adventure.middleware.security import BodySizeLimitMiddleware

        calls: list[str] = []

        async def inner_app(
            scope: dict[str, object], receive: object, send: object
        ) -> None:
            calls.append(str(scope["type"]))

        middleware = BodySizeLimitMiddleware(inner_app, max_body_bytes=10)

        import asyncio

        asyncio.run(middleware({"type": "lifespan"}, None, None))  # type: ignore[arg-type]

        assert calls == ["lifespan"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_streamed_body_over_limit_raises_413_without_content_length(
        self,
    ) -> None:
        """A body that only exceeds the cap once streamed (no Content-Length
        header at all) still gets rejected with 413.

        This drives the byte-counting backstop in ``limited_receive`` directly
        at the ASGI layer: the fast-path Content-Length check in ``__call__``
        never fires (no such header is present), so the only way to reject
        this body is the streamed-total check on line 181.
        """
        from cyo_adventure.middleware.security import BodySizeLimitMiddleware

        messages = [
            {"type": "http.request", "body": b"0" * 6, "more_body": True},
            {"type": "http.request", "body": b"0" * 6, "more_body": False},
        ]
        message_iter = iter(messages)

        async def receive() -> dict[str, object]:
            return next(message_iter)

        async def inner_app(
            scope: dict[str, object], receive: object, send: object
        ) -> None:
            while True:
                message = await receive()  # type: ignore[operator]
                if not message.get("more_body", False):
                    break

        sent: list[dict[str, object]] = []

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        middleware = BodySizeLimitMiddleware(inner_app, max_body_bytes=10)
        await middleware({"type": "http", "headers": []}, receive, send)  # type: ignore[arg-type]

        assert sent[0]["status"] == 413

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_non_request_message_skips_size_check(self) -> None:
        """A non-``http.request`` message (e.g. ``http.disconnect``) passes
        through ``limited_receive`` without being counted toward the cap."""
        from cyo_adventure.middleware.security import BodySizeLimitMiddleware

        messages = [{"type": "http.disconnect"}]
        message_iter = iter(messages)

        async def receive() -> dict[str, object]:
            return next(message_iter)

        async def inner_app(
            scope: dict[str, object], receive: object, send: object
        ) -> None:
            await receive()  # type: ignore[operator]

        sent: list[dict[str, object]] = []

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        middleware = BodySizeLimitMiddleware(inner_app, max_body_bytes=10)
        await middleware({"type": "http", "headers": []}, receive, send)  # type: ignore[arg-type]

        assert sent == []


class TestParseContentLength:
    """Tests for the standalone ``_parse_content_length`` helper."""

    @pytest.mark.unit
    def test_parse_content_length_valid_bytes_returns_int(self) -> None:
        """A well-formed numeric Content-Length header parses to an int."""
        from cyo_adventure.middleware.security import _parse_content_length

        assert _parse_content_length(b"1024") == 1024

    @pytest.mark.unit
    def test_parse_content_length_malformed_bytes_returns_none(self) -> None:
        """A non-numeric Content-Length header returns None instead of raising."""
        from cyo_adventure.middleware.security import _parse_content_length

        assert _parse_content_length(b"not-a-number") is None


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

    @pytest.mark.unit
    def test_is_blocked_url_decimal_ip_out_of_range_is_not_blocked(self) -> None:
        """A digit-only host outside the 0-0xFFFFFFFF IPv4 int range is not
        treated as an obfuscated IP (falls through to the "not blocked" path)."""
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        middleware = SSRFPreventionMiddleware(app=MagicMock())

        # 99999999999 exceeds 0xFFFFFFFF (4294967295), so the range guard
        # short-circuits before ipaddress.ip_address is ever called.
        assert middleware._is_blocked_url("http://99999999999/path") is False

    @pytest.mark.unit
    def test_is_blocked_url_decimal_ip_public_is_not_blocked(self) -> None:
        """A digit-only host that decodes to a public IP is not blocked."""
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        middleware = SSRFPreventionMiddleware(app=MagicMock())

        # 134744072 == 8.8.8.8 (public) in decimal notation.
        assert middleware._is_blocked_url("http://134744072/path") is False

    @pytest.mark.unit
    def test_is_blocked_url_unicode_digit_host_swallows_int_conversion_error(
        self,
    ) -> None:
        """A host that is Unicode-digit-like but not ``int()``-convertible is
        handled by the except clause instead of propagating.

        ``str.isdigit()`` returns True for characters like U+00B2
        (superscript two) that ``int()`` still rejects; this is the real
        (not mocked) trigger for the ValueError/OverflowError guard around
        the decimal-IP-obfuscation check.
        """
        from unittest.mock import MagicMock

        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        middleware = SSRFPreventionMiddleware(app=MagicMock())

        assert "²".isdigit()
        assert middleware._is_blocked_url("http://²/path") is False

    @pytest.mark.unit
    def test_extract_host_from_url_malformed_ipv6_returns_none(self) -> None:
        """_extract_host_from_url returns None instead of raising on a
        malformed IPv6-bracketed URL that makes urlparse raise ValueError."""
        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        assert SSRFPreventionMiddleware._extract_host_from_url("http://[::1") is None

    @pytest.mark.unit
    def test_extract_scheme_from_url_malformed_ipv6_returns_none(self) -> None:
        """_extract_scheme_from_url returns None instead of raising on a
        malformed IPv6-bracketed URL that makes urlparse raise ValueError."""
        from cyo_adventure.middleware.security import SSRFPreventionMiddleware

        assert SSRFPreventionMiddleware._extract_scheme_from_url("http://[::1") is None


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
        """add_security_middleware registers TrustedHostMiddleware when allowed_hosts is set."""
        from starlette.middleware.trustedhost import TrustedHostMiddleware

        from cyo_adventure.middleware.security import add_security_middleware

        app = _minimal_app()
        add_security_middleware(app, allowed_hosts=["testserver", "localhost"])

        middleware_classes = [m.cls for m in app.user_middleware]
        assert TrustedHostMiddleware in middleware_classes

    @pytest.mark.unit
    def test_add_security_middleware_with_https_redirect(self) -> None:
        """add_security_middleware registers HTTPSRedirectMiddleware when requested."""
        from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

        from cyo_adventure.middleware.security import add_security_middleware

        app = _minimal_app()
        add_security_middleware(app, enable_https_redirect=True)

        middleware_classes = [m.cls for m in app.user_middleware]
        assert HTTPSRedirectMiddleware in middleware_classes

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

    @pytest.mark.unit
    def test_add_security_middleware_enforces_body_size_limit_by_default(self) -> None:
        """add_security_middleware wires the body-size guard on by default."""
        from cyo_adventure.middleware.security import add_security_middleware

        app = FastAPI()

        @app.post("/echo")
        async def echo(request: Request) -> dict[str, int]:
            body = await request.body()
            return {"received": len(body)}

        add_security_middleware(app, max_body_bytes=10)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/echo", content=b"0123456789X")

        assert response.status_code == 413

    @pytest.mark.unit
    def test_add_security_middleware_disable_body_size_limit(self) -> None:
        """add_security_middleware skips the body-size guard when disabled."""
        from cyo_adventure.middleware.security import add_security_middleware

        app = FastAPI()

        @app.post("/echo")
        async def echo(request: Request) -> dict[str, int]:
            body = await request.body()
            return {"received": len(body)}

        add_security_middleware(app, enable_body_size_limit=False, max_body_bytes=10)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/echo", content=b"0123456789X")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Proxy header trust boundary (Task E1, audit Group A: A1 rate-limit keying,
# A2 HSTS gating)
# ---------------------------------------------------------------------------
#
# Neither RateLimitMiddleware nor SecurityHeadersMiddleware reads
# X-Forwarded-For/X-Forwarded-Proto directly: they read request.client.host
# and request.url.scheme, which Starlette populates from the ASGI scope's
# "client" and "scheme" keys. Behind the nginx/Traefik TLS-terminating
# reverse proxy, the raw scope always carries the proxy's own IP and plain
# "http" scheme unless something rewrites the scope first. uvicorn's
# ProxyHeadersMiddleware is that rewriter: run with --proxy-headers
# --forwarded-allow-ips=<CIDR>, it rewrites scope["client"]/scope["scheme"]
# from X-Forwarded-For/-Proto, but ONLY when the immediate TCP peer is inside
# the trusted CIDR. These tests exercise the real uvicorn middleware (not a
# mock) at the ASGI layer via TestClient(app, client=(...)), which sets the
# scope's "client" tuple to simulate the immediate TCP peer -- no live server
# needed to prove the trust boundary.


class TestProxyHeaderTrust:
    """ASGI-layer tests proving the proxy-header trust boundary works."""

    @staticmethod
    def _proxy_wrapped_app(trusted_hosts: str) -> object:
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        app = _minimal_app()

        @app.get("/whoami")
        async def whoami(request: Request) -> dict[str, str | None]:
            return {
                "scheme": request.url.scheme,
                "client_host": request.client.host if request.client else None,
            }

        return ProxyHeadersMiddleware(app, trusted_hosts=trusted_hosts)

    @pytest.mark.unit
    def test_trusted_proxy_forwarded_headers_rewrite_scheme_and_client(self) -> None:
        """A request whose immediate peer is inside the trusted CIDR has its
        scheme and client rewritten from X-Forwarded-Proto/-For.
        """
        app = self._proxy_wrapped_app(trusted_hosts="172.16.0.0/12")
        # 172.20.0.5 simulates the immediate TCP peer (e.g. the nginx sidecar
        # on the compose bridge network), which sits inside the trusted CIDR.
        client = TestClient(app, client=("172.20.0.5", 12345))  # type: ignore[arg-type]

        response = client.get(
            "/whoami",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-For": "203.0.113.9",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["scheme"] == "https"
        assert body["client_host"] == "203.0.113.9"

    @pytest.mark.unit
    def test_untrusted_source_forwarded_headers_are_ignored(self) -> None:
        """A request from OUTSIDE the trusted CIDR keeps its original scheme
        and client: forwarded headers from an untrusted peer must be ignored,
        not trusted, or any client could spoof its own IP/scheme.
        """
        app = self._proxy_wrapped_app(trusted_hosts="172.16.0.0/12")
        # 8.8.8.8 is outside 172.16.0.0/12: an attacker (or misrouted
        # request) reaching the backend directly rather than via the proxy.
        client = TestClient(app, client=("8.8.8.8", 12345))  # type: ignore[arg-type]

        response = client.get(
            "/whoami",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-For": "203.0.113.9",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["scheme"] == "http"  # unchanged: TestClient's own scheme
        assert body["client_host"] == "8.8.8.8"  # unchanged: untrusted source

    @pytest.mark.unit
    def test_trusted_proxy_https_scheme_fires_hsts_header(self) -> None:
        """End-to-end: a trusted-proxy https-forwarded request makes
        SecurityHeadersMiddleware's HSTS branch (security.py) fire.
        """
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        from cyo_adventure.middleware.security import SecurityHeadersMiddleware

        app = _minimal_app()
        app.add_middleware(SecurityHeadersMiddleware)
        wrapped = ProxyHeadersMiddleware(app, trusted_hosts="172.16.0.0/12")
        client = TestClient(wrapped, client=("172.20.0.5", 12345))  # type: ignore[arg-type]

        response = client.get("/", headers={"X-Forwarded-Proto": "https"})

        assert "Strict-Transport-Security" in response.headers

    @pytest.mark.unit
    def test_untrusted_source_https_header_does_not_fire_hsts(self) -> None:
        """An untrusted source cannot forge HSTS by sending X-Forwarded-Proto
        on its own: the scheme stays "http" so the HSTS branch stays closed.
        """
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        from cyo_adventure.middleware.security import SecurityHeadersMiddleware

        app = _minimal_app()
        app.add_middleware(SecurityHeadersMiddleware)
        wrapped = ProxyHeadersMiddleware(app, trusted_hosts="172.16.0.0/12")
        client = TestClient(wrapped, client=("8.8.8.8", 12345))  # type: ignore[arg-type]

        response = client.get("/", headers={"X-Forwarded-Proto": "https"})

        assert "Strict-Transport-Security" not in response.headers

    @pytest.mark.unit
    def test_trusted_proxy_rate_limiter_keys_by_forwarded_client(self) -> None:
        """End-to-end: the REAL RateLimitMiddleware, wired behind the REAL
        uvicorn ProxyHeadersMiddleware, buckets by the trusted-proxy-rewritten
        client IP, not the shared nginx peer IP.

        Mirrors test_trusted_proxy_https_scheme_fires_hsts_header's
        construction, but for the rate-limiter side of the same trust
        boundary: before Task E1, RateLimitMiddleware read request.client.host
        directly off the raw ASGI scope, so every request arriving via the
        nginx/Traefik reverse proxy collapsed into ONE bucket keyed on the
        proxy's own IP, regardless of which real client sent it. Exhausting
        client A's burst limit must not throttle client B, even though both
        requests share the same immediate TCP peer (the proxy) and differ
        only in their X-Forwarded-For value.
        """
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        from cyo_adventure.middleware.security import RateLimitMiddleware

        app = _minimal_app()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=1000, burst_size=2)
        wrapped = ProxyHeadersMiddleware(app, trusted_hosts="172.16.0.0/12")
        # 172.20.0.5 simulates the nginx sidecar's IP on the compose bridge
        # network: the immediate TCP peer for BOTH clients below.
        client = TestClient(wrapped, client=("172.20.0.5", 12345))  # type: ignore[arg-type]

        # Client A exhausts its burst limit (2 requests/second).
        for _ in range(2):
            response = client.get("/", headers={"X-Forwarded-For": "203.0.113.9"})
            assert response.status_code == 200
        throttled = client.get("/", headers={"X-Forwarded-For": "203.0.113.9"})
        assert throttled.status_code == 429

        # Client B, forwarded from the SAME nginx peer but a different
        # X-Forwarded-For, gets its own bucket: it is not throttled by
        # client A's exhausted limit.
        response = client.get("/", headers={"X-Forwarded-For": "203.0.113.10"})
        assert response.status_code == 200

    @pytest.mark.unit
    def test_untrusted_source_rate_limiter_collapses_to_peer_ip(self) -> None:
        """Without the proxy trust boundary, two claimed clients sharing an
        untrusted immediate peer collapse into the SAME rate-limit bucket.

        Complements the previous test: it shows what Task E1 fixed. When the
        immediate TCP peer is OUTSIDE the trusted CIDR, ProxyHeadersMiddleware
        leaves scope["client"] unchanged, so RateLimitMiddleware keys on that
        one peer IP no matter what X-Forwarded-For claims; one claimed
        client's exhausted burst limit throttles a completely different
        claimed client sharing the same peer.
        """
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        from cyo_adventure.middleware.security import RateLimitMiddleware

        app = _minimal_app()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=1000, burst_size=2)
        wrapped = ProxyHeadersMiddleware(app, trusted_hosts="172.16.0.0/12")
        # 8.8.8.8 is outside the trusted CIDR: X-Forwarded-For is ignored and
        # scope["client"] stays 8.8.8.8 for every request below.
        client = TestClient(wrapped, client=("8.8.8.8", 12345))  # type: ignore[arg-type]

        for _ in range(2):
            response = client.get("/", headers={"X-Forwarded-For": "203.0.113.9"})
            assert response.status_code == 200

        # A different claimed X-Forwarded-For does NOT get its own bucket:
        # the untrusted peer IP is the real key, so this collides with the
        # bucket client A already exhausted above.
        collided = client.get("/", headers={"X-Forwarded-For": "203.0.113.10"})
        assert collided.status_code == 429

    @pytest.mark.unit
    def test_forwarded_allow_ips_setting_defaults_to_private_cidr(self) -> None:
        """Settings.forwarded_allow_ips defaults to a private CIDR, never '*'.

        A wildcard default would let ANY upstream peer forge its client IP
        (bypassing per-client rate-limit keying) or scheme (forging HSTS).
        """
        from cyo_adventure.core.config import Settings

        default_value = Settings().forwarded_allow_ips

        assert default_value == "172.16.0.0/12"
        assert default_value != "*"

    @pytest.mark.unit
    def test_forwarded_allow_ips_setting_overridable_via_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FORWARDED_ALLOW_IPS env var overrides the Settings default."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("FORWARDED_ALLOW_IPS", "203.0.113.0/24")

        assert Settings().forwarded_allow_ips == "203.0.113.0/24"
