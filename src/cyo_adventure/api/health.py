"""Health check endpoints for Kubernetes and production monitoring.

This module provides standardized health check endpoints following best practices:
- Liveness probe: Is the application running?
- Readiness probe: Can the application serve traffic?
- Startup probe: Has the application fully started?

Implements:
- Kubernetes probe patterns
- Graceful degradation
- Detailed diagnostic information
- OWASP A09 (Security Logging) compliance
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import text

from cyo_adventure import __version__
from cyo_adventure.core.config import settings
from cyo_adventure.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

# Generic, non-leaking message returned to clients when a readiness probe fails.
# The full exception is logged server-side (OWASP A09); raw exception text is
# never serialized into the response body to avoid leaking DSN/host/driver detail.
_CHECK_FAILED_MESSAGE = "dependency unavailable"
_CHECK_FAILED_LOG = "readiness check failed"

# Track application start time for uptime calculation
_START_TIME = time.time()

# Dependency names whose failure actually flips /health/ready to 503. See
# check_cache's docstring and readiness()'s #ASSUME note: cache is
# deliberately excluded, since the app fails open without Redis.
# check_generation_queue (ADR-021) is deliberately excluded too: see its
# docstring and TestReadinessQueueDoesNotGate.
_CRITICAL_READINESS_CHECKS = frozenset({"database"})

# #ASSUME: timing dependencies: 24 hours is the lookback window for the
# recent-failed-jobs signal in check_generation_queue. This is calibrated to
# catch a sustained failure mode (e.g. a schema-drift incident where every
# job fails outright) within one operator work day, without keeping an old,
# already-investigated failure flagging "degraded" indefinitely.
# #VERIFY: tests/unit/test_health.py::TestCheckGenerationQueue.
_RECENT_FAILED_WINDOW = timedelta(hours=24)

# #ASSUME: external resources: a single job force-failed by
# requeue_stranded_jobs (e.g. one worker OOM) must not flip this signal to
# "degraded" for a full 24h and cause alarm fatigue on the exact check meant
# to catch a sustained incident (schema drift failing every job). Requiring
# more than one recent failure before flipping state keeps the check quiet
# for an isolated, already-recovered job while still catching a real
# failure streak well within the operator's work day. 3 is a starting
# calibration, not a measured value; revisit if it proves too noisy or too
# quiet in production.
# #VERIFY: tests/unit/test_health.py::TestCheckGenerationQueue covers the
# threshold boundary (at the threshold vs. one above it).
RECENT_FAILED_DEGRADED_THRESHOLD = 3


class HealthStatus(BaseModel):
    """Health check response model."""

    status: str = Field(..., description="Overall status: ok, degraded, or error")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp")
    uptime_seconds: float = Field(..., description="Application uptime in seconds")
    version: str = Field(default=__version__, description="Application version")
    python_version: str = Field(default_factory=lambda: sys.version.split()[0])


class ReadinessCheck(BaseModel):
    """Individual dependency check result."""

    name: str = Field(..., description="Dependency name")
    status: bool = Field(..., description="Check passed")
    latency_ms: float | None = Field(
        default=None, description="Check latency in milliseconds"
    )
    error: str | None = Field(default=None, description="Error message if failed")
    # Fine-grained state beyond the pass/fail `status` bool. "ok" and
    # "unconfigured" both report status=True (neither fails readiness);
    # "degraded" reports status=False for a check that is configured but
    # unreachable. None for checks (database) that have no unconfigured
    # concept. See check_cache's docstring for the cache check's use of this.
    state: Literal["ok", "degraded", "unconfigured"] | None = Field(
        default=None, description="Fine-grained state: ok, degraded, or unconfigured"
    )


class ReadinessStatus(HealthStatus):
    """Readiness check response with dependency details."""

    checks: dict[str, ReadinessCheck] = Field(
        default_factory=dict, description="Individual dependency checks"
    )


@router.get(
    "/live",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Indicates if the application is running. Used by Kubernetes liveness probe.",
)
async def liveness() -> HealthStatus:
    """Kubernetes liveness probe.

    Returns HTTP 200 if the application is alive.
    If this fails, Kubernetes will restart the pod.

    This should be a simple, fast check that doesn't depend on external services.
    """
    return HealthStatus(
        status="ok",
        uptime_seconds=time.time() - _START_TIME,
    )


async def check_database() -> ReadinessCheck:
    """Check database connectivity.

    Returns:
        ReadinessCheck: database status and latency.
    """
    start = time.time()
    try:
        # Import here to avoid circular dependencies
        from cyo_adventure.core.database import get_session

        async with get_session() as session:
            # Simple query to check connectivity
            await session.execute(text("SELECT 1"))

        latency_ms = (time.time() - start) * 1000
        return ReadinessCheck(
            name="database",
            status=True,
            latency_ms=round(latency_ms, 2),
        )
    except Exception as exc:
        latency_ms = (time.time() - start) * 1000
        logger.warning(_CHECK_FAILED_LOG, check="database", error=str(exc))
        return ReadinessCheck(
            name="database",
            status=False,
            latency_ms=round(latency_ms, 2),
            error=_CHECK_FAILED_MESSAGE,
        )


async def check_cache() -> ReadinessCheck:
    """Check Redis/cache connectivity.

    Reuses the same Redis URL as the rate limiter and the RQ generation
    queue (``Settings.redis_url``; see ``middleware/security.py``'s
    ``RateLimitMiddleware._get_script`` for the identical
    ``Redis.from_url(..., socket_connect_timeout=..., socket_timeout=...)``
    client-construction pattern this mirrors) and the same
    ``rate_limit_redis_timeout_seconds`` bound, so a slow/black-holed Redis
    cannot add unbounded latency to a readiness probe either.

    Reports a distinct ``state="unconfigured"`` (``status=True``, no ping
    attempted), rather than a failure, when the operator has deliberately
    chosen the in-memory rate-limit backend (``Settings.rate_limit_backend
    == "memory"``): in that mode nothing in the request path depends on
    Redis being reachable (``RateLimitMiddleware`` itself always falls back
    to an in-memory counter on a Redis error regardless of this setting), so
    an unreachable Redis in that configuration is not a real problem and
    must not read as one.

    #ASSUME: external resources: ``rate_limit_backend == "memory"`` is
    treated as the deliberate "Redis intentionally absent" signal. A
    deployment that sets ``rate_limit_backend="redis"`` but has genuinely
    never provisioned Redis (rather than hitting a transient outage) reports
    ``state="degraded"`` here, the same as a transient outage; this check
    cannot distinguish "never configured" from "temporarily down" once the
    backend is set to "redis". It intentionally does NOT check
    ``settings.generation_provider`` or any RQ-specific state: Redis backs
    both the rate limiter and the RQ queue, and ``rate_limit_backend`` is
    the one explicit, boolean-ish opt-out already in ``Settings``.
    #VERIFY: tests/unit/test_health.py::TestCheckCache covers ok, degraded,
    and unconfigured.

    Returns:
        ReadinessCheck: cache status, latency, and fine-grained state.
    """
    start = time.time()
    if settings.rate_limit_backend != "redis":
        return ReadinessCheck(
            name="cache",
            status=True,
            latency_ms=round((time.time() - start) * 1000, 2),
            state="unconfigured",
        )

    try:
        client: Redis = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.rate_limit_redis_timeout_seconds,
            socket_timeout=settings.rate_limit_redis_timeout_seconds,
        )
        try:
            await client.ping()
        finally:
            await client.aclose()

        latency_ms = (time.time() - start) * 1000
        return ReadinessCheck(
            name="cache",
            status=True,
            latency_ms=round(latency_ms, 2),
            state="ok",
        )
    except Exception as exc:
        latency_ms = (time.time() - start) * 1000
        logger.warning(_CHECK_FAILED_LOG, check="cache", error=str(exc))
        return ReadinessCheck(
            name="cache",
            status=False,
            latency_ms=round(latency_ms, 2),
            error=_CHECK_FAILED_MESSAGE,
            state="degraded",
        )


async def check_generation_queue() -> ReadinessCheck:
    """Check the RQ generation-job pipeline for a stopped or failing worker.

    ADR-021 Phase 1: the real production failure mode already diagnosed was
    jobs FAILING outright (a schema-drift incident), not merely jobs piling
    up queued. This check surfaces three independent signals from the
    ``generation_job`` table:

    1. **stale_queued**: rows at ``status="queued"`` older than
       :data:`~cyo_adventure.generation.queue.DEFAULT_STALE_AFTER`. Mirrors
       the exact threshold :func:`~cyo_adventure.generation.queue.requeue_stranded_jobs`
       uses to decide a queued row is lost, so the alarm and the actual
       sweep can never disagree.
    2. **stale_running**: rows at ``status="running"`` older than
       ``generation_job_timeout_seconds`` plus
       :data:`~cyo_adventure.generation.queue.RUNNING_STALE_MARGIN`. Also
       mirrors ``requeue_stranded_jobs``'s own running-row threshold, rather
       than a flat constant, so a legitimately long-running job is never
       flagged early.
    3. **recent_failed**: rows at ``status="failed"`` whose ``updated_at``
       falls within :data:`_RECENT_FAILED_WINDOW` (24h). This is the signal
       that would have caught the real incident: a stopped worker shows up
       as stale_queued/stale_running, but a *running* worker whose jobs are
       failing outright (e.g. a schema-drift error on every write) shows up
       here instead. The raw count is always reported, but it only flips
       the check to "degraded" once it exceeds
       :data:`RECENT_FAILED_DEGRADED_THRESHOLD`: a single job force-failed
       by ``requeue_stranded_jobs`` (e.g. one worker OOM) must not produce
       24h of false-degraded alarm fatigue on the exact signal meant to
       catch a sustained incident. ``stale_queued`` and ``stale_running``
       are not thresholded: any stranded row is worth reporting immediately
       since ``requeue_stranded_jobs`` would already have swept it if it
       weren't genuinely stuck.

    All three counts are fetched in a single query using
    ``COUNT(*) FILTER (WHERE ...)`` aggregates (one database round trip)
    rather than three sequential ``SELECT COUNT(*)`` statements.

    Deliberately non-gating (see readiness()'s docstring and
    ``_CRITICAL_READINESS_CHECKS``): a stuck or failing generation pipeline
    must not pull API pods out of the load-balancer rotation for endpoints
    that never touch generation at all. The response exposes only three
    counts, no PII, on an already-unauthenticated endpoint (OWASP A09: no
    raw exception text on failure, matching check_database/check_cache).

    #ASSUME: external resources: this reads through the API's own
    ``get_session`` (the ``cyo_api`` role once ADR-021's Phase 2 role split
    lands), not a separate worker connection; a database outage here is
    already covered by the gating ``database`` check.
    #VERIFY: tests/unit/test_health.py::TestCheckGenerationQueue covers ok,
    each of the three degraded signals, the recent_failed threshold
    boundary, and the DB-error path; TestReadinessQueueDoesNotGate proves
    this check never flips readiness.

    Returns:
        ReadinessCheck: generation-queue status, latency, and fine-grained
        state ("ok" or "degraded"; this check has no "unconfigured" concept).
    """
    start = time.time()
    try:
        # Import here to avoid circular dependencies, matching check_database.
        from sqlalchemy import func, select

        from cyo_adventure.core.database import get_session
        from cyo_adventure.db.models import GenerationJob
        from cyo_adventure.generation.queue import (
            DEFAULT_STALE_AFTER,
            RUNNING_STALE_MARGIN,
        )

        now = datetime.now(UTC)
        queued_cutoff = now - DEFAULT_STALE_AFTER
        running_cutoff = now - (
            timedelta(seconds=settings.generation_job_timeout_seconds)
            + RUNNING_STALE_MARGIN
        )
        failed_cutoff = now - _RECENT_FAILED_WINDOW

        async with get_session() as session:
            result = await session.execute(
                select(
                    func.count()
                    .filter(
                        GenerationJob.status == "queued",
                        GenerationJob.updated_at < queued_cutoff,
                    )
                    .label("stale_queued"),
                    func.count()
                    .filter(
                        GenerationJob.status == "running",
                        GenerationJob.updated_at < running_cutoff,
                    )
                    .label("stale_running"),
                    func.count()
                    .filter(
                        GenerationJob.status == "failed",
                        GenerationJob.updated_at >= failed_cutoff,
                    )
                    .label("recent_failed"),
                ).select_from(GenerationJob)
            )
            row = result.one()

        stale_queued_count = int(row.stale_queued or 0)
        stale_running_count = int(row.stale_running or 0)
        recent_failed_count = int(row.recent_failed or 0)
        latency_ms = round((time.time() - start) * 1000, 2)

        recent_failed_degraded = recent_failed_count > RECENT_FAILED_DEGRADED_THRESHOLD
        if stale_queued_count or stale_running_count or recent_failed_degraded:
            return ReadinessCheck(
                name="generation_queue",
                status=False,
                latency_ms=latency_ms,
                error=(
                    f"{stale_queued_count} stale queued, "
                    f"{stale_running_count} stale running, "
                    f"{recent_failed_count} recently failed generation job(s)"
                ),
                state="degraded",
            )
        return ReadinessCheck(
            name="generation_queue",
            status=True,
            latency_ms=latency_ms,
            state="ok",
        )
    except Exception as exc:
        latency_ms = (time.time() - start) * 1000
        logger.warning(_CHECK_FAILED_LOG, check="generation_queue", error=str(exc))
        return ReadinessCheck(
            name="generation_queue",
            status=False,
            latency_ms=round(latency_ms, 2),
            error=_CHECK_FAILED_MESSAGE,
            state="degraded",
        )


async def check_external_service() -> ReadinessCheck:
    """Check external API/service connectivity.

    Returns:
        ReadinessCheck: external service status.
    """
    start = time.time()
    try:
        # Example external service check
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     response = await client.get("https://api.example.com/health", timeout=2.0)
        #     response.raise_for_status()

        # #ASSUME: external resources: this placeholder returns status=True without
        # calling the external service. Enabling it in readiness() before the real
        # request is implemented reports a false-healthy dependency.
        # #VERIFY: implement the httpx call above before uncommenting the external
        # service check in readiness().
        # Placeholder - replace with actual external service check
        latency_ms = (time.time() - start) * 1000
        return ReadinessCheck(
            name="external_api",
            status=True,
            latency_ms=round(latency_ms, 2),
        )
    except Exception as exc:
        latency_ms = (time.time() - start) * 1000
        logger.warning(_CHECK_FAILED_LOG, check="external_api", error=str(exc))
        return ReadinessCheck(
            name="external_api",
            status=False,
            latency_ms=round(latency_ms, 2),
            error=_CHECK_FAILED_MESSAGE,
        )


@router.get(
    "/ready",
    response_model=ReadinessStatus,
    responses={
        200: {"description": "Application is ready to serve traffic"},
        503: {"description": "Application is not ready (dependencies unavailable)"},
    },
    summary="Readiness probe",
    description="Checks if the application can serve traffic. Used by Kubernetes readiness probe.",
)
async def readiness() -> ReadinessStatus:
    """Kubernetes readiness probe.

    Checks dependencies and reports all of them in the payload, but only
    ``database`` gates the HTTP status (``_CRITICAL_READINESS_CHECKS``):

    - Database connectivity (gates readiness; 503 on failure).
    - Cache/Redis availability (reported, does not gate readiness; see
      check_cache's docstring and the #ASSUME note below).
    - Generation-queue health (reported, does not gate readiness; see
      check_generation_queue's docstring, ADR-021 Phase 1).
    - External service health: not wired in (check_external_service exists
      but is unused; see api/health.py module history / docs/operations/runbook.md).

    #ASSUME: external resources: cache (Redis) is deliberately excluded from
    the gate below. The app fails open without Redis: RateLimitMiddleware
    falls back to an in-memory counter on any Redis error regardless of
    ``rate_limit_backend``, and RQ generation-queue enqueue/consume is a
    separate, already-degraded-on-its-own-terms path (a stuck "queued" job,
    not a request-path failure). Flipping /health/ready to 503 on a Redis
    outage would pull the pod out of the load-balancer rotation for every
    endpoint, including ones with no Redis dependency at all, which is a
    worse outcome than the fail-open behavior it already has. A Redis outage
    is still visible in this payload (cache.status=False, state="degraded")
    for anyone polling /health/ready directly or checking dashboards/alerts
    built on it.
    #VERIFY: tests/unit/test_health.py::TestReadinessCacheDoesNotGate.

    Returns HTTP 503 if the database is unavailable. If this fails,
    Kubernetes will stop sending traffic to this pod.
    """
    checks: dict[str, ReadinessCheck] = {}

    # Run all checks in parallel for better performance
    # For now, run sequentially - can be optimized with asyncio.gather()
    checks["database"] = await check_database()
    checks["cache"] = await check_cache()
    checks["generation_queue"] = await check_generation_queue()

    # check_external_service remains unwired here: LLM/story-generation
    # providers are optional and provider-specific (generation_provider is
    # "mock" by default; live legs are validated lazily at call time in
    # build_provider, not at startup or health-check time), so there is no
    # single external dependency to ping generically. Uncomment once a
    # specific, always-critical external dependency needs readiness coverage:
    # checks["external_api"] = await check_external_service()

    # Determine overall status: only checks named in
    # _CRITICAL_READINESS_CHECKS can flip readiness to unavailable.
    all_healthy = all(
        check.status
        for name, check in checks.items()
        if name in _CRITICAL_READINESS_CHECKS
    )

    if not all_healthy:
        # Return 503 if any critical check fails
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unavailable",
                "timestamp": time.time(),
                "uptime_seconds": time.time() - _START_TIME,
                "checks": {name: check.model_dump() for name, check in checks.items()},
            },
        )

    return ReadinessStatus(
        status="ok",
        uptime_seconds=time.time() - _START_TIME,
        checks=checks,
    )


@router.get(
    "/startup",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Startup probe",
    description="Indicates if the application has completed startup. Used by Kubernetes startup probe.",
)
async def startup() -> HealthStatus:
    """Kubernetes startup probe.

    Used during application startup to delay liveness and readiness checks.
    This prevents the application from being killed during slow initialization.

    Returns HTTP 200 once the application has fully started.
    """
    # Add any startup checks here (e.g., database migrations completed)
    # For most applications, being alive means startup is complete

    return HealthStatus(
        status="started",
        uptime_seconds=time.time() - _START_TIME,
    )


@router.get(
    "/",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Basic health check",
    description="Simple health check endpoint for load balancers and monitoring.",
    include_in_schema=False,  # Hide from OpenAPI docs (use /live instead)
)
async def health() -> HealthStatus:
    """Basic health check endpoint.

    Alias for /health/live for compatibility with load balancers
    that expect a /health endpoint.
    """
    return await liveness()


# =============================================================================
# Kubernetes Probe Configuration Examples
# =============================================================================
"""
Add to your Kubernetes Deployment YAML:

apiVersion: apps/v1
kind: Deployment
metadata:
  name: cyo_adventure
spec:
  template:
    spec:
      containers:
      - name: app
        image: cyo_adventure:latest
        ports:
        - containerPort: 8000

        # Liveness probe - restart if fails
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3

        # Readiness probe - stop traffic if fails
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3

        # Startup probe - delay other probes during startup
        startupProbe:
          httpGet:
            path: /health/startup
            port: 8000
          initialDelaySeconds: 0
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 30  # 30 * 5s = 150s max startup time
"""
