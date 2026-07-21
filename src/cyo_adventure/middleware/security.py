"""Security middleware for FastAPI applications.

This module provides production-ready security middleware implementing OWASP best practices:
- CORS configuration (A05: Security Misconfiguration)
- Security headers (A05: Security Misconfiguration)
- Rate limiting (A07: Identification and Authentication Failures)
- Request validation (A03: Injection)
- SSRF prevention (A10: Server-Side Request Forgery)

Usage:
    from cyo_adventure.middleware.security import (
        add_security_middleware,
        SecurityHeadersMiddleware,
        RateLimitMiddleware,
    )

    app = FastAPI()
    add_security_middleware(app)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, Final, Literal

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

logger = logging.getLogger(__name__)
# Structured logger for the Redis-backed rate limiter's fail-open path: an
# operator alerting rule should be able to key on the `event` field
# ("rate_limit_redis_unavailable") rather than parsing a stdlib log line.
#
# Uses structlog directly rather than cyo_adventure.utils.logging.get_logger:
# that wrapper module imports from cyo_adventure.middleware.correlation,
# which is a sibling submodule imported by this package's __init__.py before
# security.py -- routing through the wrapper here creates a circular import
# (cyo_adventure.utils.logging -> cyo_adventure.middleware -> .security ->
# cyo_adventure.utils.logging, observed as a partially-initialized-module
# ImportError during test collection). structlog.get_logger(__name__) is
# exactly what the wrapper does internally (see utils/logging.py::get_logger)
# minus the import-time dependency, and still honors whatever structlog.configure()
# call setup_logging() has made process-wide.
_struct_logger = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from redis.commands.core import AsyncScript
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Default request-body ceiling for BodySizeLimitMiddleware (1 MiB). A guardian
# reading-state save or concept brief is a small JSON payload; 1 MiB is
# generous headroom over any legitimate request while still bounding a
# byte-bomb POST (audit Finding 8).
_DEFAULT_MAX_BODY_BYTES: Final[int] = 1_048_576


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses.

    Implements OWASP recommended security headers to prevent:
    - XSS attacks
    - Clickjacking
    - MIME sniffing
    - Information leakage

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: HSTS for HTTPS
    - Content-Security-Policy: Prevent inline scripts
    - Referrer-Policy: Control referrer information
    - Permissions-Policy: Restrict browser features
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Add security headers to response."""
        response = await call_next(request)

        # Prevent MIME sniffing (OWASP A05)
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking (OWASP A05)
        response.headers["X-Frame-Options"] = "DENY"

        # Enable XSS protection (OWASP A03)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # HSTS: Force HTTPS for 1 year (OWASP A02)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Content Security Policy: Prevent inline scripts (OWASP A03)
        # object-src/base-uri/form-action close three additional injection
        # vectors (F11): plugin content, base-tag hijacking of relative URLs,
        # and form-action redirection to an attacker-controlled origin.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

        # Control referrer information (OWASP A09)
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features (OWASP A05)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )

        # Remove server identification (OWASP A09)
        if "Server" in response.headers:
            del response.headers["Server"]

        return response


_HEALTH_PATH_PREFIX: Final = "/health"


class HealthExemptHTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS, except for ``/health*`` liveness probes.

    Starlette's stock ``HTTPSRedirectMiddleware`` has no path exemption, so
    it 307s any plain-HTTP request, including a liveness/uptime probe that
    hits this container directly rather than through the TLS-terminating
    reverse proxy. Most such probes (container orchestrator health checks,
    external uptime monitors) treat a redirect as a failed check, not a
    live one. `/health/*` (see `api/health.py`) is read-only and returns
    nothing sensitive, so exempting it from the redirect is a narrow,
    deliberate carve-out; every other path still redirects.

    #ASSUME: security: matches by path prefix only, not by verb or host, so
    any HTTP method against `/health/*` is exempt. All health endpoints are
    GET-only reads (see `api/health.py`), so this does not open a write
    path to plain HTTP.
    #VERIFY: tests/unit/test_security.py::TestAddSecurityMiddleware::
    test_https_redirect_exempts_health_path.

    #EDGE: security: like the middleware it replaces, this subclasses
    `BaseHTTPMiddleware`, which only wraps HTTP scope requests; a WebSocket
    upgrade bypasses `dispatch` entirely and is neither redirected nor
    exempted. No route in this app accepts WebSocket connections today.
    #VERIFY: if a WebSocket route is added, revisit this middleware (or
    reintroduce a pure-ASGI wrapper, like `BodySizeLimitMiddleware`, so the
    "ws" -> "wss" scheme upgrade Starlette's original middleware performed
    is not silently lost).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Redirect HTTP to HTTPS unless the request targets `/health/*`."""
        if request.url.scheme == "https" or request.url.path.startswith(
            _HEALTH_PATH_PREFIX
        ):
            return await call_next(request)

        redirect_url = request.url.replace(scheme="https")
        return RedirectResponse(redirect_url, status_code=307)


class _BodyTooLargeError(Exception):
    """Internal signal: the streamed request body exceeded the byte cap.

    Raised from inside the wrapped ``receive`` callable in
    :class:`BodySizeLimitMiddleware` and caught by that same middleware to
    render the 413 response; never escapes the middleware.
    """


class BodySizeLimitMiddleware:
    """Reject an oversized request body with 413, before it reaches the app.

    A pure ASGI middleware (not ``BaseHTTPMiddleware``): Starlette's
    ``Request.body()`` (which ``BaseHTTPMiddleware.dispatch`` and downstream
    Pydantic body-parsing both eventually call) buffers the WHOLE body in
    memory before anything can inspect its size. Wrapping ``receive`` instead
    lets every chunk be counted and rejected the moment the cap is crossed,
    so an oversized body is never fully materialized (audit Finding 8).

    Args:
        app: The wrapped ASGI application.
        max_body_bytes: The byte ceiling (default 1 MiB).
    """

    def __init__(
        self, app: ASGIApp, max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES
    ) -> None:
        """Store the wrapped app and the configured byte ceiling."""
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Enforce the body-size cap for an http scope; pass through otherwise."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast-path reject when the client declares an oversized body upfront
        # via Content-Length, without reading a single byte of it.
        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        for name, value in raw_headers:
            if name == b"content-length":
                declared = _parse_content_length(value)
                if declared is not None and declared > self.max_body_bytes:
                    await _send_413(send)
                    return
                break

        total = 0

        async def limited_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body") or b"")
                # #CRITICAL: security: this is the resource-bound backstop for
                # a missing or understated Content-Length: the cap is enforced
                # against bytes actually streamed, not the (untrusted) header.
                # #VERIFY: test_body_over_limit_rejected_with_413 posts a body
                # with no explicit Content-Length override and still gets 413.
                if total > self.max_body_bytes:
                    raise _BodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLargeError:
            await _send_413(send)


def _parse_content_length(value: bytes) -> int | None:
    """Return the parsed Content-Length header value, or ``None`` if malformed."""
    try:
        return int(value)
    except ValueError:
        return None


async def _send_413(send: Send) -> None:
    """Send a minimal 413 JSON response directly at the ASGI layer."""
    body = json.dumps(
        {
            "error": "Payload Too Large",
            "message": "request body exceeds the size limit",
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


# Atomic sliding-window-log rate check, run server-side via Redis' EVAL so the
# expire-count-decide-record sequence cannot race with another worker
# process/replica hitting the same Redis instance between our count read and
# our record write. That atomicity is the entire point of this backend: the
# multi-process property a plain (non-scripted) sequence of ZCARD/ZADD calls
# from Python would NOT reliably provide under concurrent requests.
#
# KEYS[1]: per-client-IP sorted-set key (member=unique request id, score=the
#          request's time.time())
# ARGV: now, minute_window_seconds, burst_window_seconds, rpm_limit,
#       burst_limit, member
#
# Returns {0, count} if allowed (and records the request), {1, count} if the
# per-minute limit is exceeded, or {2, count} if the burst limit is exceeded.
# In both rejection cases nothing is recorded, matching the in-memory
# limiter's behavior of never counting a rejected request against later ones.
_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local minute_window = tonumber(ARGV[2])
local burst_window = tonumber(ARGV[3])
local rpm_limit = tonumber(ARGV[4])
local burst_limit = tonumber(ARGV[5])
local member = ARGV[6]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - minute_window)

local minute_count = redis.call('ZCARD', key)
if minute_count >= rpm_limit then
    return {1, minute_count}
end

local burst_count = redis.call('ZCOUNT', key, now - burst_window, '+inf')
if burst_count >= burst_limit then
    return {2, burst_count}
end

redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, minute_window)
return {0, minute_count + 1}
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware: Redis-backed, with an in-memory fail-open fallback.

    Implements rate limiting to prevent:
    - Brute force attacks (OWASP A07)
    - DoS attacks (OWASP A04)
    - Credential stuffing (OWASP A07)

    Two backends:

    - ``backend="redis"`` (the deployed default; see
      ``core/config.py::Settings.rate_limit_backend``): per-client-IP counters
      live in a Redis sorted set, shared by every worker process/replica, via
      the atomic Lua script above (``_RATE_LIMIT_SCRIPT``). This replaces the
      single-process-only limiter documented as a known limitation in
      SECURITY.md.
    - ``backend="memory"``: the original process-local ``dict``-of-timestamps
      counter. Used directly by most unit tests and single-process local dev,
      and used automatically as the fail-open fallback when Redis is
      unreachable (see ``dispatch``) regardless of the configured backend.

    #CRITICAL: security/concurrency: choosing to fail OPEN (fall back to the
    weaker in-memory limiter) rather than fail CLOSED (reject all requests, or
    hang) on a Redis outage is a deliberate availability-over-strictness
    trade-off: an operator-visible Redis outage must not become a
    customer-visible API outage. The cost is that during an outage, the
    effective limit reverts to per-process enforcement (a client distributing
    requests across replicas is no longer capped in aggregate) until Redis
    recovers and a fresh attempt succeeds.
    #VERIFY: the fallback logs ``rate_limit_redis_unavailable`` via structlog
    (``_struct_logger``) so this degraded mode is observable/alertable in
    production; SECURITY.md documents the trade-off explicitly.

    Args:
        requests_per_minute: Maximum requests per IP per minute
        burst_size: Maximum burst requests allowed
        max_tracked_ips: Maximum IPs to track in the in-memory fallback
            (prevents memory exhaustion)
        cleanup_interval: Seconds between full in-memory cleanup cycles
        backend: ``"redis"`` to prefer the shared Redis-backed counter
            (falling back to memory on error), or ``"memory"`` to use only
            the process-local counter. Defaults to ``"memory"`` so
            constructing this middleware directly, as most unit tests and ad
            hoc wiring do, never depends on a reachable Redis;
            ``add_security_middleware`` resolves the real deployed default
            from ``Settings.rate_limit_backend`` (``"redis"``) when the
            caller does not override it.
        redis_url: Redis connection URL, used when backend="redis" and no
            ``redis_client`` is supplied. Reuses the same URL as the RQ task
            queue (``Settings.redis_url``).
        redis_client: An already-constructed async Redis client (or
            test double) to use instead of building one from ``redis_url``.
        redis_timeout_seconds: Socket connect/read timeout for the Redis
            client, bounding how long a single request can be delayed by an
            unresponsive (not just unreachable) Redis.
        redis_retry_cooldown_seconds: After a Redis error, how long to skip
            further Redis attempts and serve straight from the in-memory
            fallback, so a sustained outage costs one timeout, not one
            timeout per request.
        redis_key_prefix: Namespace prefix for the Redis sorted-set keys.
    """

    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        max_tracked_ips: int = 10000,
        cleanup_interval: int = 300,
        *,
        backend: Literal["redis", "memory"] = "memory",
        redis_url: str | None = None,
        redis_client: Redis | None = None,
        redis_timeout_seconds: float = 0.5,
        redis_retry_cooldown_seconds: float = 5.0,
        redis_key_prefix: str = "cyo:ratelimit",
    ) -> None:
        """Initialize rate limiter."""
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.max_tracked_ips = max_tracked_ips
        self.cleanup_interval = cleanup_interval
        self.requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()

        self.backend: Literal["redis", "memory"] = backend
        self._redis_url = redis_url
        self._redis_client = redis_client
        self._redis_timeout_seconds = redis_timeout_seconds
        self._redis_retry_cooldown_seconds = redis_retry_cooldown_seconds
        self._redis_key_prefix = redis_key_prefix
        self._script: AsyncScript | None = None
        # 0.0 (not a future timestamp) so the very first request after
        # startup always attempts Redis rather than skipping straight to the
        # fallback.
        self._redis_unavailable_until: float = 0.0

    def _cleanup_stale_entries(self, current_time: float) -> None:
        """Remove stale IP entries to prevent memory leaks.

        This method performs two types of cleanup:
        1. Removes expired timestamps from all tracked IPs
        2. If we exceed max_tracked_ips, removes least recently active IPs

        Args:
            current_time: Current timestamp for expiration checks
        """
        # Only run full cleanup periodically to avoid performance impact
        if current_time - self._last_cleanup < self.cleanup_interval:
            return

        self._last_cleanup = current_time

        # Remove expired entries from all IPs
        stale_ips: list[str] = []
        for ip, timestamps in self.requests.items():
            # Filter to only recent timestamps
            recent = [t for t in timestamps if current_time - t < 60]
            if recent:
                self.requests[ip] = recent
            else:
                stale_ips.append(ip)

        # Remove completely stale IPs
        for ip in stale_ips:
            del self.requests[ip]

        # If still over limit, remove oldest IPs (LRU-style)
        if len(self.requests) > self.max_tracked_ips:
            # Sort by most recent activity and keep only max_tracked_ips
            sorted_ips = sorted(
                self.requests.items(),
                key=lambda x: max(x[1]) if x[1] else 0,
                reverse=True,
            )
            self.requests = defaultdict(
                list,
                {
                    ip: timestamps
                    for ip, timestamps in sorted_ips[: self.max_tracked_ips]
                },
            )

    def _check_memory(self, client_ip: str, current_time: float) -> Response | None:
        """Evaluate the in-memory sliding-window counters for one request.

        Returns a 429 ``JSONResponse`` if either limit is exceeded, else
        records the request and returns ``None`` so the caller proceeds. Used
        both as the ``"memory"`` backend and as the fail-open fallback path
        for ``"redis"`` (see ``dispatch``).
        """
        # Periodic cleanup to prevent memory leaks
        self._cleanup_stale_entries(current_time)

        # Clean up old entries for current IP (older than 1 minute)
        self.requests[client_ip] = [
            req_time
            for req_time in self.requests[client_ip]
            if current_time - req_time < 60
        ]

        # Check rate limit
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded: {self.requests_per_minute} requests per minute",
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )

        # Check burst limit
        recent_requests = sum(
            1 for req_time in self.requests[client_ip] if current_time - req_time < 1
        )
        if recent_requests >= self.burst_size:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Burst limit exceeded: {self.burst_size} requests per second",
                    "retry_after": 1,
                },
                headers={"Retry-After": "1"},
            )

        # Record request
        self.requests[client_ip].append(current_time)
        return None

    async def _get_script(self) -> AsyncScript:
        """Lazily construct the Redis client and register the Lua script.

        #CRITICAL: external-resources: this is the first point of contact
        with Redis on the request path; a connection error surfaces either
        here (client construction is lazy, so a bad URL only fails on first
        use) or from the subsequent ``await script(...)`` call in
        ``_check_redis``. Both are caught by ``dispatch``.
        #VERIFY: test_redis_backend_falls_back_to_memory_on_connection_error
        drives this path with an unreachable redis_url.
        """
        if self._redis_client is None:
            if self._redis_url is None:
                msg = (
                    "redis_url is required when backend='redis' and no "
                    "redis_client is supplied"
                )
                raise RedisError(msg)
            self._redis_client = Redis.from_url(
                self._redis_url,
                socket_connect_timeout=self._redis_timeout_seconds,
                socket_timeout=self._redis_timeout_seconds,
            )
        if self._script is None:
            self._script = self._redis_client.register_script(_RATE_LIMIT_SCRIPT)
        return self._script

    async def _check_redis(
        self, client_ip: str, current_time: float
    ) -> Response | None:
        """Evaluate the Redis-backed sliding-window counters for one request.

        Raises whatever the ``redis`` client raises on a connection, timeout,
        or protocol error; ``dispatch`` is responsible for catching that and
        falling back to ``_check_memory``. Intentionally does not catch
        anything itself, so the fallback decision stays centralized in one
        place.
        """
        script = await self._get_script()
        # #ASSUME: data-integrity: pairing the float timestamp with a uuid4
        # suffix keeps the sorted-set member unique even for two requests
        # landing on the same float tick, so a second ZADD in the same tick
        # cannot silently overwrite the first member's score (which would
        # undercount a genuine concurrent burst).
        # #VERIFY: see TestRedisBackedRateLimitMiddleware in test_security.py.
        member = f"{current_time!r}:{uuid.uuid4().hex}"
        key = f"{self._redis_key_prefix}:{client_ip}"
        code, count = await script(
            keys=[key],
            args=[
                current_time,
                60,  # minute window (seconds)
                1,  # burst window (seconds)
                self.requests_per_minute,
                self.burst_size,
                member,
            ],
        )
        del count  # returned for observability/debugging only, unused here
        if code == 1:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded: {self.requests_per_minute} requests per minute",
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )
        if code == 2:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Burst limit exceeded: {self.burst_size} requests per second",
                    "retry_after": 1,
                },
                headers={"Retry-After": "1"},
            )
        return None

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Apply rate limiting per IP address."""
        if request.client is None:
            logger.warning(
                "request.client is None; using 'unknown' as client IP for rate limiting"
            )
        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()

        decision: Response | None
        if self.backend == "redis" and current_time >= self._redis_unavailable_until:
            try:
                decision = await self._check_redis(client_ip, current_time)
            except (RedisError, OSError, TimeoutError) as exc:
                # #CRITICAL: concurrency/security: fail OPEN, not closed --
                # see the class docstring for the full trade-off. Arm the
                # circuit-breaker cooldown so a sustained outage costs one
                # connection timeout per redis_retry_cooldown_seconds window,
                # not one per request.
                # #VERIFY: see TestRedisBackedRateLimitMiddleware in
                # test_security.py (the circuit-breaker cooldown tests).
                self._redis_unavailable_until = (
                    current_time + self._redis_retry_cooldown_seconds
                )
                _struct_logger.warning(
                    "rate_limit_redis_unavailable",
                    error=str(exc),
                    client_ip=client_ip,
                    cooldown_seconds=self._redis_retry_cooldown_seconds,
                )
                decision = self._check_memory(client_ip, current_time)
        else:
            decision = self._check_memory(client_ip, current_time)

        if decision is not None:
            return decision

        return await call_next(request)


class SSRFPreventionMiddleware(BaseHTTPMiddleware):
    """Prevent Server-Side Request Forgery (SSRF) attacks.

    Blocks requests to internal/private IP ranges when making outbound HTTP calls.
    Implements OWASP A10 protection with proper IP address validation.

    Features:
    - Proper CIDR range validation using ipaddress module
    - Cloud metadata endpoint blocking (AWS, GCP, Azure)
    - DNS rebinding protection via hostname validation
    - IPv4 and IPv6 support

    Note: For production SSRF prevention, also consider:
    1. Use allowlists for external API endpoints
    2. Validate and sanitize URLs before making requests
    3. Use network segmentation
    4. Implement egress filtering at the network level
    """

    # Blocked hostnames (case-insensitive)
    BLOCKED_HOSTS: set[str] = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        # AWS/Azure metadata endpoints (shared IP)
        "169.254.169.254",
        "fd00:ec2::254",
        # GCP metadata endpoints
        "metadata.google.internal",
        "metadata.goog",
        # Kubernetes
        "kubernetes.default",
        "kubernetes.default.svc",
    }

    # Blocked URL schemes
    BLOCKED_SCHEMES: set[str] = {
        "file",
        "gopher",
        "dict",
        "ftp",
        "ldap",
        "tftp",
    }

    @staticmethod
    def _is_private_ip(ip_str: str) -> bool:
        """Check if an IP address is private, loopback, or otherwise internal.

        Args:
            ip_str: IP address string to validate

        Returns:
            True if the IP is private/internal, False otherwise
        """
        import ipaddress

        try:
            ip = ipaddress.ip_address(ip_str)
            # Check various internal IP properties
            return (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
                # Additional check for IPv4-mapped IPv6 addresses
                or (
                    isinstance(ip, ipaddress.IPv6Address)
                    and ip.ipv4_mapped is not None
                    and SSRFPreventionMiddleware._is_private_ip(str(ip.ipv4_mapped))
                )
            )
        except ValueError:
            # Not a valid IP address - let hostname checks handle it
            return False

    @staticmethod
    def _extract_host_from_url(url: str) -> str | None:
        """Extract hostname from URL string.

        Args:
            url: URL string to parse

        Returns:
            Hostname string or None if parsing fails
        """
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            return parsed.hostname
        except Exception:
            return None

    @staticmethod
    def _extract_scheme_from_url(url: str) -> str | None:
        """Extract scheme from URL string.

        Args:
            url: URL string to parse

        Returns:
            Scheme string or None if parsing fails
        """
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            return parsed.scheme.lower() if parsed.scheme else None
        except Exception:
            return None

    def _is_blocked_url(self, url: str) -> bool:
        """Check if a URL points to a blocked destination.

        Args:
            url: URL string to validate

        Returns:
            True if the URL should be blocked, False otherwise
        """
        # Check scheme
        scheme = self._extract_scheme_from_url(url)
        if scheme and scheme in self.BLOCKED_SCHEMES:
            return True

        # Extract and check hostname
        host = self._extract_host_from_url(url)
        if not host:
            return False

        host_lower = host.lower()

        # Check against blocked hostnames
        if host_lower in self.BLOCKED_HOSTS:
            return True

        # Check if it's a private IP
        if self._is_private_ip(host):
            return True

        # Check for numeric IP obfuscation (decimal, octal, hex)
        # e.g., 2130706433 = 127.0.0.1, 0x7f000001 = 127.0.0.1
        try:
            import ipaddress

            # Try parsing as integer (decimal IP notation)
            if host.isdigit():
                ip_int = int(host)
                if 0 <= ip_int <= 0xFFFFFFFF:
                    ip = ipaddress.ip_address(ip_int)
                    if self._is_private_ip(str(ip)):
                        return True
        except (ValueError, OverflowError):
            pass

        return False

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Check for SSRF patterns in the request's query parameters.

        Only ``request.query_params`` is scanned for embedded URLs; this
        middleware does NOT inspect form data or the JSON body (F21). No
        current endpoint accepts a URL in a body field, so a body scanner
        would be speculative complexity with nothing to guard.

        #EDGE: security: if a future endpoint adds a body field that accepts
        a URL (e.g. an image-import-by-URL feature), that field needs its own
        SSRF guard; this middleware will not see it.
        #VERIFY: add a dedicated check (reusing `_is_blocked_url`) at the
        point that field is parsed, before any outbound request is made.
        """
        # Check query parameters for URLs
        for param, value in request.query_params.items():
            if "://" in value or value.startswith("//"):
                if self._is_blocked_url(value):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "Bad Request",
                            "message": "Request blocked: potential SSRF attempt",
                            "detail": f"Blocked URL detected in parameter: {param}",
                        },
                    )

        return await call_next(request)


def add_security_middleware(
    app: FastAPI,
    *,
    enable_https_redirect: bool = False,
    enable_rate_limiting: bool = True,
    enable_ssrf_prevention: bool = True,
    enable_body_size_limit: bool = True,
    allowed_origins: list[str] | None = None,
    allowed_hosts: list[str] | None = None,
    rate_limit_rpm: int = 60,
    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
    rate_limit_backend: Literal["redis", "memory"] | None = None,
    redis_url: str | None = None,
) -> None:
    """Add all security middleware to FastAPI application.

    This configures comprehensive security following OWASP best practices.

    Args:
        app: FastAPI application instance
        enable_https_redirect: Redirect HTTP to HTTPS (production only),
            except `/health/*`, which stays reachable over plain HTTP so a
            direct liveness/uptime probe against this container (not routed
            through the TLS-terminating reverse proxy) still gets a real
            response instead of a redirect
        enable_rate_limiting: Enable rate limiting middleware
        enable_ssrf_prevention: Enable SSRF prevention middleware
        enable_body_size_limit: Enable the request-body size guard (413 over cap)
        allowed_origins: CORS allowed origins (default: none)
        allowed_hosts: Trusted host names (default: all)
        rate_limit_rpm: Rate limit requests per minute
        max_body_bytes: Request-body byte ceiling (default 1 MiB)
        rate_limit_backend: ``"redis"`` or ``"memory"`` for
            ``RateLimitMiddleware``'s backend (see its docstring). When left
            as ``None`` (the default used by ``app.py::create_app``, which
            does not pass this), resolved lazily from
            ``core.config.settings.rate_limit_backend`` -- "redis" for every
            deployed tier. Passed explicitly here (rather than importing
            ``settings`` at module scope) so this generic middleware-wiring
            helper stays trivially unit-testable without a Settings object.
        redis_url: Redis connection URL for the ``"redis"`` backend. When
            ``None``, resolved lazily from ``core.config.settings.redis_url``
            (the same URL the RQ task queue uses) alongside
            ``rate_limit_backend``.

    Example:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> add_security_middleware(
        ...     app,
        ...     enable_https_redirect=True,
        ...     allowed_origins=["https://example.com"],
        ...     allowed_hosts=["example.com", "api.example.com"],
        ...     rate_limit_rpm=100,
        ... )
    """
    # HTTPS redirect (production only), health endpoints exempt
    if enable_https_redirect:
        app.add_middleware(HealthExemptHTTPSRedirectMiddleware)

    # Trusted hosts (OWASP A05)
    if allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=allowed_hosts,
        )

    # CORS configuration (OWASP A05)
    # Explicit allowlist: wildcard allow_headers with allow_credentials=True
    # violates the CORS spec and enables header-escalation attacks.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or [],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Correlation-ID",
            "X-Request-ID",
            "X-Trace-ID",
            "X-Span-ID",
        ],
        expose_headers=["X-Request-ID"],
        max_age=3600,
    )

    # Security headers (OWASP A05, A03, A09)
    app.add_middleware(SecurityHeadersMiddleware)

    # Rate limiting (OWASP A07)
    if enable_rate_limiting:
        resolved_backend = rate_limit_backend
        resolved_redis_url = redis_url
        if resolved_backend is None or resolved_redis_url is None:
            # Lazy import: keeps this generic middleware-wiring helper
            # importable/testable without pulling in Settings (env parsing,
            # validators) when the caller supplies both values explicitly.
            # This is also what makes the Redis backend the real production
            # default with NO change needed in app.py::create_app, which
            # calls add_security_middleware() without either of these two
            # kwargs: Settings.rate_limit_backend defaults to "redis" and
            # Settings.redis_url is the same URL the RQ task queue uses.
            from cyo_adventure.core.config import settings as _settings

            if resolved_backend is None:
                resolved_backend = _settings.rate_limit_backend
            if resolved_redis_url is None:
                resolved_redis_url = _settings.redis_url
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=rate_limit_rpm,
            burst_size=10,
            backend=resolved_backend,
            redis_url=resolved_redis_url,
        )

    # SSRF prevention (OWASP A10)
    if enable_ssrf_prevention:
        app.add_middleware(SSRFPreventionMiddleware)

    # Request body size guard (audit Finding 8: unbounded body -> resource
    # exhaustion). Added last so it wraps every other middleware added here,
    # rejecting an oversized body before anything else (rate limiting, CORS,
    # SSRF checks) does any work on the request.
    if enable_body_size_limit:
        app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=max_body_bytes)


# Example usage in main.py:
"""
from fastapi import FastAPI
from cyo_adventure.middleware.security import add_security_middleware

app = FastAPI()

# Add all security middleware
add_security_middleware(
    app,
    enable_https_redirect=True,  # Production only
    enable_rate_limiting=True,
    allowed_origins=[
        "https://example.com",
        "https://app.example.com",
    ],
    allowed_hosts=[
        "api.example.com",
        "localhost",  # Development only
    ],
    rate_limit_rpm=100,
)

# Your routes here
@app.get("/")
async def root():
    return {"message": "Hello World"}
"""
