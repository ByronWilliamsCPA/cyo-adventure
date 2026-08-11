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

Paths: this router declares `/health/...` relative to wherever it is mounted,
and `app.py` mounts it twice. `/api/v1/health/...` is canonical and is the only
form reachable through the reverse proxy; `/health/...` is a schema-hidden alias
kept for in-container loopback probes. See `app.py`'s `include_router` calls for
why both exist, and never document or monitor the un-prefixed form.
"""

from __future__ import annotations

import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import text

from cyo_adventure import __version__
from cyo_adventure.core.config import settings
from cyo_adventure.core.rls_posture import measure_role_posture
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

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

# #ASSUME: timing dependencies: how long an unresolved KWS attempt may sit
# before check_kws_verification counts it as stuck, and how far back that
# check looks for sends and resolutions. 24 hours for both, and the value is
# doing less work than it looks: the alarm is a CONJUNCTION (see
# consent/service.py::VerificationDeliveryHealth.deliveries_have_stopped), so
# this threshold only decides how quickly a genuine outage surfaces, not
# whether abandonment is mistaken for one. A full day also puts the two terms
# on disjoint sets of rows, which is what stops one slow-but-eventually-
# verifying parent from being both the stuck row and the recent send.
# #VERIFY: tests/unit/test_health.py::TestCheckKwsVerification.
_KWS_STUCK_AFTER = timedelta(hours=24)
_KWS_DELIVERY_WINDOW = timedelta(hours=24)


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
    # unreachable. "unknown" reports status=False for a check that could not
    # run at all, which is a different operator response than a check that
    # ran and returned a bad answer: "degraded" on database_privilege means
    # the role really can bypass RLS, "unknown" means the query failed and
    # the posture is unmeasured. None for checks (database) that have no
    # unconfigured concept. See check_cache's docstring for the cache check.
    state: Literal["ok", "degraded", "unconfigured", "unknown"] | None = Field(
        default=None,
        description="Fine-grained state: ok, degraded, unconfigured, or unknown",
    )


class ReadinessStatus(HealthStatus):
    """Readiness check response with dependency details."""

    checks: dict[str, ReadinessCheck] = Field(
        default_factory=dict, description="Individual dependency checks"
    )


@router.get(
    "/live",
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


@asynccontextmanager
async def _readiness_session(
    session: AsyncSession | None,
) -> AsyncGenerator[AsyncSession]:
    """Yield a session for a readiness check, reusing a caller's if given.

    ``readiness()`` opens one session and hands it to both database-backed
    checks so a single probe takes one connection out of the pool instead of
    one per check. A check called directly (the unit tests, or any future
    standalone caller) passes ``None`` and gets its own session.

    Args:
        session: An open session to reuse, or ``None`` to open a new one.

    Yields:
        AsyncSession: The session the caller should execute against.
    """
    if session is not None:
        yield session
        return
    # Import here to avoid circular dependencies.
    from cyo_adventure.core.database import get_session

    async with get_session() as owned:
        yield owned


async def check_database(session: AsyncSession | None = None) -> ReadinessCheck:
    """Check database connectivity.

    Args:
        session: An already-open session to reuse. ``readiness()`` passes one
            so the two database-backed checks share a single pool checkout;
            when omitted the check opens (and closes) its own.

    Returns:
        ReadinessCheck: database status and latency.
    """
    start = time.time()
    try:
        async with _readiness_session(session) as db:
            # Simple query to check connectivity
            await db.execute(text("SELECT 1"))

        latency_ms = (time.time() - start) * 1000
        return ReadinessCheck(
            name="database",
            status=True,
            latency_ms=round(latency_ms, 2),
        )
    except Exception as exc:
        # #EDGE: data-integrity: the parens below are required, not
        # redundant (Sonar S1110 false positive): "-" binds looser than
        # "*" in Python, so removing them would silently compute
        # time.time() - start * 1000 instead of the intended latency.
        # #VERIFY: tests/unit/test_health.py latency-value assertions.
        latency_ms = (time.time() - start) * 1000  # NOSONAR
        logger.warning(_CHECK_FAILED_LOG, check="database", error=str(exc))
        return ReadinessCheck(
            name="database",
            status=False,
            latency_ms=round(latency_ms, 2),
            error=_CHECK_FAILED_MESSAGE,
        )


async def check_database_privilege(
    session: AsyncSession | None = None,
) -> ReadinessCheck:
    """Report whether the API's database role is least-privileged (ADR-021).

    RLS never applies to a table's owner, and this schema deliberately does
    not set ``FORCE ROW LEVEL SECURITY`` (see
    ``20260711200745_enable_rls_all_tables.sql``). Every RLS policy shipped
    since then, including ADR-022's Tier 1 per-family predicates, is therefore
    inert in any environment still connecting as the ``postgres`` owner role.
    The migrations alone never make that visible; this check does.

    Covers all three bypass paths (see
    ``core/rls_posture.py::CONNECTED_ROLE_QUERY``): the ``rolbypassrls``
    attribute, superuser, and table ownership. Ownership is the one that
    matters in practice, since the baseline migration assigns the Tier 1
    tables to ``postgres``.

    This check covers the **API** process only, and probing the worker engine
    from here would report a false verdict: the sanctioned deployment leaves
    ``WORKER_DATABASE_URL`` unset on the API container, so in this process the
    worker engine resolves to the API's own DSN. The worker runs the same probe
    against its own engine at startup (``generation/worker_main.py``) and logs
    the result, because it serves no HTTP and cannot be probed from outside.

    Deliberately non-gating (absent from ``_CRITICAL_READINESS_CHECKS``): a
    pre-cutover environment is an open security finding, not an outage, and
    must not pull pods out of the load-balancer rotation. ``readiness()``
    computes its HTTP status from critical checks only, so ``status=False``
    here is visible and alertable without being disruptive.

    #CRITICAL: security: the connected role name is logged but never returned.
    /health/ready is unauthenticated, so the response carries only the posture
    bit; naming the role would hand an unauthenticated caller the database
    identity the application connects as.
    #VERIFY: tests/unit/test_health.py::TestCheckDatabasePrivilege asserts the
    role name is absent from the serialized response on the degraded path.

    Args:
        session: An already-open session to reuse; see ``_readiness_session``.

    Returns:
        ReadinessCheck: ``status=True``/``state="ok"`` when the connected role
        cannot bypass RLS by any path, ``status=False``/``state="degraded"``
        when it can, and ``status=False``/``state="unknown"`` when the query
        itself failed and the posture could not be measured at all.
    """
    start = time.time()
    try:
        async with _readiness_session(session) as db:
            posture = await measure_role_posture(db)

        latency_ms = (time.time() - start) * 1000
        if posture.bypasses_rls:
            logger.warning(
                "database role bypasses row-level security",
                check="database_privilege",
                role=posture.role_name,
                # Which path fired: an operator fixes ownership and role
                # attributes differently, so "it bypasses" alone is not
                # actionable. Both are booleans, never row data.
                via_role_attribute=posture.via_role_attribute,
                via_table_ownership=posture.via_table_ownership,
            )
            return ReadinessCheck(
                name="database_privilege",
                status=False,
                latency_ms=round(latency_ms, 2),
                error="database role bypasses row-level security",
                state="degraded",
            )
        return ReadinessCheck(
            name="database_privilege",
            status=True,
            latency_ms=round(latency_ms, 2),
            state="ok",
        )
    except Exception as exc:
        # #EDGE: data-integrity: parens required, not redundant (Sonar
        # S1110 false positive); see check_database's identical comment.
        latency_ms = (time.time() - start) * 1000  # NOSONAR
        logger.warning(_CHECK_FAILED_LOG, check="database_privilege", error=str(exc))
        # state="unknown", not "degraded": the query never returned, so the
        # posture is unmeasured rather than known-bad. An operator paging on
        # "degraded" is responding to a real un-cut-over role; "unknown" is a
        # broken probe. Conflating them makes the alert unactionable.
        return ReadinessCheck(
            name="database_privilege",
            status=False,
            latency_ms=round(latency_ms, 2),
            error=_CHECK_FAILED_MESSAGE,
            state="unknown",
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
        # #EDGE: data-integrity: parens required, not redundant (Sonar
        # S1110 false positive); see check_database's identical comment.
        latency_ms = (time.time() - start) * 1000  # NOSONAR
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
        # #EDGE: data-integrity: parens required, not redundant (Sonar
        # S1110 false positive); see check_database's identical comment.
        latency_ms = (time.time() - start) * 1000  # NOSONAR
        logger.warning(_CHECK_FAILED_LOG, check="generation_queue", error=str(exc))
        return ReadinessCheck(
            name="generation_queue",
            status=False,
            latency_ms=round(latency_ms, 2),
            error=_CHECK_FAILED_MESSAGE,
            state="degraded",
        )


async def check_kws_verification() -> ReadinessCheck:
    """Check that KWS parent-verification deliveries are still arriving.

    #CRITICAL: external resources: this check exists because its failure mode
    is invisible everywhere else. On 2026-08-09 a Cloudflare custom rule
    blocked four KWS webhook retries at the edge, so the origin logged zero
    POSTs and every log-based view of the system was byte-identical to "KWS
    happened not to send anything". Meanwhile the parents behind those
    deliveries were permanently stuck: verification precedes admin approval
    (ADR-018 D1), so an unresolved attempt is a guardian who cannot finish
    signing up and cannot be told why. The only evidence such an outage
    leaves is rows that never leave ``sent``, which is what this reads.
    #VERIFY: tests/unit/test_health.py::TestCheckKwsVerification covers ok,
    degraded, unconfigured, and the DB-error path;
    ::TestReadinessKwsDoesNotGate proves it never flips readiness.

    Reports ``state="unconfigured"`` (``status=True``, no query) when the tier
    does not run verification (``kws_verification_required`` off). On such a
    tier no attempt is ever started, so any rows present are historical and
    reporting them as degraded would be a permanent false alarm on a feature
    that is switched off.

    The degraded condition is a conjunction of three terms rather than a
    stuck count, for the reason
    ``consent/service.py::VerificationDeliveryHealth.deliveries_have_stopped``
    documents: ordinary abandonment (a parent who never opens the email)
    leaves a stuck row behind forever and is not an incident. All four counts
    are reported either way, so an operator reading the payload sees the same
    numbers the condition was computed from.

    Deliberately non-gating (absent from ``_CRITICAL_READINESS_CHECKS``),
    matching check_cache and check_generation_queue: a broken inbound KWS leg
    blocks new sign-ups, but it has no bearing on serving stories to children
    who are already reading, and 503-ing the pod out of rotation would turn a
    sign-up outage into a whole-app one.

    The response exposes four integers and no PII, on an already
    unauthenticated endpoint. That is deliberate rather than incidental: the
    table it counts has no email column at all (see
    ``db/models.py::KwsVerification``), so there is no address here to leak
    even by accident.

    Returns:
        ReadinessCheck: KWS delivery status, latency, and fine-grained state
        ("ok", "degraded", or "unconfigured").
    """
    start = time.time()
    if not settings.kws_verification_required:
        return ReadinessCheck(
            name="kws_verification",
            status=True,
            latency_ms=round((time.time() - start) * 1000, 2),
            state="unconfigured",
        )
    try:
        # Import here to avoid circular dependencies, matching check_database.
        from cyo_adventure.consent.service import verification_delivery_health
        from cyo_adventure.core.database import get_session

        async with get_session() as session:
            health = await verification_delivery_health(
                session,
                stuck_after=_KWS_STUCK_AFTER,
                window=_KWS_DELIVERY_WINDOW,
            )

        latency_ms = round((time.time() - start) * 1000, 2)
        if health.deliveries_have_stopped:
            oldest = health.oldest_stuck_requested_at
            # `oldest` is non-None whenever stuck > 0, which the conjunction
            # already required; the guard is for the type checker, not for a
            # case that can occur.
            oldest_note = (
                "" if oldest is None else f" (oldest sent {oldest.isoformat()})"
            )
            window_hours = int(_KWS_DELIVERY_WINDOW.total_seconds() // 3600)
            return ReadinessCheck(
                name="kws_verification",
                status=False,
                latency_ms=latency_ms,
                error=(
                    f"{health.stuck} KWS verification(s) stuck unresolved"
                    f"{oldest_note}; {health.sent_in_window} sent and "
                    f"{health.resolved_in_window} resolved in the last "
                    f"{window_hours}h"
                ),
                state="degraded",
            )
        return ReadinessCheck(
            name="kws_verification",
            status=True,
            latency_ms=latency_ms,
            state="ok",
        )
    except Exception as exc:
        # #EDGE: data-integrity: parens required, not redundant (Sonar
        # S1110 false positive); see check_database's identical comment.
        latency_ms = (time.time() - start) * 1000  # NOSONAR
        logger.warning(_CHECK_FAILED_LOG, check="kws_verification", error=str(exc))
        return ReadinessCheck(
            name="kws_verification",
            status=False,
            latency_ms=round(latency_ms, 2),
            error=_CHECK_FAILED_MESSAGE,
            state="degraded",
        )


async def check_external_service() -> ReadinessCheck:  # NOSONAR
    """Check external API/service connectivity.

    #ASSUME: external resources: kept ``async``, and awaits nothing yet, on
    purpose (Sonar S7503): this is a placeholder sibling of check_database /
    check_cache / check_generation_queue, all real ``async def check_x() ->
    ReadinessCheck`` callables awaited uniformly by readiness(). Enabling the
    commented-out httpx call below only requires uncommenting code, not
    touching this signature or any caller/test; dropping ``async`` now would
    require re-adding it later and would break the existing
    ``await check_external_service()`` call sites in tests/unit/test_health.py.

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
        # #EDGE: data-integrity: parens required, not redundant (Sonar
        # S1110 false positive); see check_database's identical comment.
        latency_ms = (time.time() - start) * 1000  # NOSONAR
        logger.warning(_CHECK_FAILED_LOG, check="external_api", error=str(exc))
        return ReadinessCheck(
            name="external_api",
            status=False,
            latency_ms=round(latency_ms, 2),
            error=_CHECK_FAILED_MESSAGE,
        )


@router.get(
    "/ready",
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
    - KWS parent-verification delivery health (reported, does not gate
      readiness; see check_kws_verification's docstring, ADR-018 D1).
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
    #
    # The two database-backed checks share one pool checkout. A readiness
    # probe that took a connection per check would multiply pool pressure by
    # the number of checks precisely when the pool is already stressed, which
    # is when readiness matters most.
    try:
        # Import here to avoid circular dependencies, matching the checks.
        from cyo_adventure.core.database import get_session

        async with get_session() as db:
            checks["database"] = await check_database(session=db)
            checks["database_privilege"] = await check_database_privilege(session=db)
    except Exception:
        logger.warning(_CHECK_FAILED_LOG, check="database_session_checkout")

    # #CRITICAL: external-resources: only genuinely-missing entries are re-run,
    # never entries the shared checkout already produced. `database` is the one
    # gating check, and the context manager's EXIT can raise (a close/rollback
    # on a dropped connection) after both checks have already succeeded.
    # Re-running unconditionally in the handler would overwrite those passes
    # with failures and 503 a healthy process out of the load-balancer
    # rotation, an outage manufactured by the probe itself.
    # #VERIFY: tests/unit/test_health.py::TestReadinessSharedSession covers a
    # failure on entry (both re-run) and on exit (results preserved).
    if "database" not in checks:
        checks["database"] = await check_database()
    if "database_privilege" not in checks:
        checks["database_privilege"] = await check_database_privilege()

    checks["cache"] = await check_cache()
    checks["generation_queue"] = await check_generation_queue()
    checks["kws_verification"] = await check_kws_verification()

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
Add to your Kubernetes Deployment YAML.

Use the canonical `/api/v1/health/*` paths below, not the un-prefixed
`/health/*` alias. Both answer on port 8000, so a probe against either would
pass today, but the alias exists only to keep already-deployed out-of-repo
probes working until they migrate (see `app.py`'s `include_router` calls) and
is scheduled to be retired. A new probe written against it would be the reason
it can never go away.

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
            path: /api/v1/health/live
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3

        # Readiness probe - stop traffic if fails
        readinessProbe:
          httpGet:
            path: /api/v1/health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3

        # Startup probe - delay other probes during startup
        startupProbe:
          httpGet:
            path: /api/v1/health/startup
            port: 8000
          initialDelaySeconds: 0
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 30  # 30 * 5s = 150s max startup time
"""
