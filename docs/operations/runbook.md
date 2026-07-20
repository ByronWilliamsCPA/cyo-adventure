---
title: "Operator Runbook"
schema_type: common
status: published
owner: core-maintainer
purpose: >-
  Day-to-day operations for CYO Adventure: start/stop, health checks, incident diagnosis,
  secrets inventory, and the content kill switch.
tags:
  - deployment
  - infrastructure
  - monitoring
  - guide
---

This is the operator's reference for running CYO Adventure day to day: what runs where, how to
start and stop it, how to read its health signals, how to diagnose the incidents that actually
recur, and what to do when a book has to come off a child's shelf immediately.

It documents the system as it exists in this repository today, not an aspirational target. Where
a capability the pipeline needs does not exist yet (a backup script, a restore drill, a console
screen), that gap is called out explicitly rather than described as if it were built. See
[ADR-004](../planning/adr/adr-004-homelab-first-deployment.md) (homelab-first deployment),
[ADR-009](../planning/adr/adr-009-supabase-platform.md) (Supabase as the auth/database platform),
[ADR-012](../planning/adr/adr-012-supabase-cli-migrations.md) (Supabase CLI SQL migrations), and
[Deployment](../architecture/deployment.md) for the design decisions behind what follows.

## 1. Service topology

**FastAPI backend**: `cyo_adventure.app:app`, served by uvicorn on port 8000. Runs as the `app`
container in this repo's `docker-compose.yml`, or as a bare `uvicorn` process. The live R1
deployment runs it as `cyo-backend` behind nginx/Pangolin ingress (see the caveat below).

**React frontend**: a static PWA build (Vite), or the Vite dev server in development. Runs as the
`frontend` container in `docker-compose.yml` (dev target) or `docker-compose.prod.yml` (nginx
serving the production build).

**PostgreSQL**: the operational database is **Supabase Postgres** (managed, external), reached
over the internet through Supabase's session pooler. This repo's `docker-compose.yml` `db` service
(a local Postgres container) is a development convenience and, per
[Deployment](../architecture/deployment.md#container-stack), a one-redeploy rollback fallback in
the live stack; it does not carry live production traffic.

**Redis**: the broker for the RQ job queue and, in every deployed tier, the rate-limiter backend.
As of ADR-021 Phase 1, `redis` is a real service in this repo's `docker-compose.yml`
(`ghcr.io/byronwilliamscpa/dhi-redis:7-debian13`); `docker compose up -d` starts it alongside `app`
and `worker`. `core/config.py`'s `redis_url` accepts either `CYO_ADVENTURE_REDIS_URL` or the
unprefixed `REDIS_URL` (the name the compose file's `${REDIS_URL:-...}` interpolation reads).

**RQ generation worker**: `python -m cyo_adventure.generation.worker_main`, a long-running process
pulling from the single `"generation"` RQ queue. As of ADR-021 Phase 1, `worker` is a real service
in this repo's `docker-compose.yml`, built from the same image as `app`; `docker compose up -d`
starts it too. The live R1 deployment still runs its own copy as `cyo-worker` in the separate
`ByronWilliamsCPA/homelab-infra` repo's compose stack; that stack is not derived from this file and
is not updated by this change.

**Cover-art worker**: `covers.worker.run_cover_job_sync`, entered via the **same** `"generation"`
RQ queue as story-generation jobs (`generation/queue.py::get_queue` always names the queue
`"generation"`, regardless of caller). Runs inside the same RQ worker process above; there is no
separate cover-worker container or process, and one worker handles both story and cover jobs.

**Object storage (MinIO / R2)**: planned for `storybook_version.blob_ref`; today story blobs are
inline `JSONB` in Postgres. Cover art already uses Cloudflare R2 (`covers/storage.py`,
S3-compatible API, configured via the `R2_*` env vars). Story-content object storage (MinIO, per
[ADR-004](../planning/adr/adr-004-homelab-first-deployment.md)) is Phase 5 and not yet built; see
[Deployment: Phase 1 vs Phase 5 Storage](../architecture/deployment.md#phase-1-vs-phase-5-storage).

**Ollama**: the local/homelab LLM fallback leg (third leg of the default provider cascade). A
separate service the worker calls over HTTP (`OLLAMA_BASE_URL`); not started by this repo's
compose files.

**Live-deployment caveat**: the actual R1 internal-web deployment's container definitions
(`cyo-backend`, `cyo-worker`, `cyo-redis`, `cyo-ollama`, the rollback-only `cyo-postgres`, and
nginx ingress) live in `services/cyo-adventure/` in the separate `ByronWilliamsCPA/homelab-infra`
repository, not in this repository. As of ADR-021 Phase 1, this repo's `docker-compose.yml` and
`docker-compose.prod.yml` do stand up a working generation pipeline locally (`app`, `worker`,
`redis`, `db`), but the live R1 stack still runs its own separately-defined `cyo-worker`/`cyo-redis`
in homelab-infra rather than pulling this repo's service definitions directly. Treat the tables and
commands below as what this repo actually provides; cross-check the homelab-infra repo for the live
stack's exact compose file when operating production.

The default LLM provider cascade for story generation (`generation/providers/fallback.py`, per
[ADR-003](../planning/adr/adr-003-frontier-llm-generation.md) as amended) is: OpenRouter Haiku
(primary) → OpenRouter Sonnet (fallback) → Ollama (local fallback). Anthropic and Modal are
additional per-job-selectable legs gated by the admin provider allowlist (Section 5.2, Section
8).

## 2. Start, stop, restart

### 2.1 Full local stack (docker-compose)

```bash
# Start the full pipeline: API, frontend, local Postgres, Redis, and the
# generation worker (all five services are defined in docker-compose.yml as
# of ADR-021 Phase 1; see Section 2.2 for details on the worker/Redis pair).
docker-compose up -d

# Rebuild after a dependency change
docker-compose up -d --build

# Tail logs
docker-compose logs -f app
docker-compose logs -f worker

# Open a shell in the backend container
docker-compose exec app bash

# Stop everything, keep volumes
docker-compose down

# Stop and delete volumes (destroys the local Postgres data)
docker-compose down -v

# Production overrides (immutable image tag required; pins resource limits,
# replica counts, and postgres tuning flags)
VERSION=v1.2.0 docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Restarting a single container after a config change:

```bash
docker-compose restart app
```

### 2.2 Redis and the generation worker (in the compose file)

As of ADR-021 Phase 1, `redis` and `worker` are real services in `docker-compose.yml`; `docker
compose up -d` (Section 2.1) starts both, and no manual `docker run` step is needed for local
development. To operate them individually:

```bash
# Redis alone (e.g. to restart it without touching app/worker):
docker-compose up -d redis
docker-compose restart redis

# The worker alone (runs the stranded-job reclaim sweep once at startup, then
# blocks pulling from the "generation" queue -- see generation/worker_main.py):
docker-compose up -d worker
docker-compose restart worker

# Bare-process worker against the compose Redis (useful when iterating on
# worker code without a rebuild; the app container still needs its own
# CYO_ADVENTURE_REDIS_URL export pointed at the same instance):
export CYO_ADVENTURE_REDIS_URL=redis://localhost:6379/0
uv run python -m cyo_adventure.generation.worker_main
```

The `worker` service in `docker-compose.yml` gets the same `ENVIRONMENT`, `DATABASE_URL`,
`CHILD_SESSION_SECRET`, `DEVICE_GRANT_SECRET`, and `CYO_ADVENTURE_REDIS_URL` env block as `app`
(the local-dev defaults are the same repository-known values); it does not carry provider
credentials (Section 8) by default, so add those to its `environment:` block or an `.env` file
before testing a live provider leg. A bare, non-compose worker process needs the same variables set
in its own shell environment; it does not inherit the API container's environment automatically.

### 2.3 Bare-process variants (no Docker)

```bash
# Backend API
uv sync --all-extras
uv run uvicorn cyo_adventure.app:app --host 0.0.0.0 --port 8000 --reload

# Generation + cover worker (same process, same queue; see Section 1)
uv run python -m cyo_adventure.generation.worker_main

# Frontend dev server
cd frontend && npm install && npm run dev
```

`ENVIRONMENT` gates two fail-fast startup guards in `core/config.py`: any value other than
`local` requires a real `DATABASE_URL` (rejects the local dev default) and requires
`OIDC_ISSUER`/`OIDC_JWKS_URL` plus `CHILD_SESSION_SECRET`/`DEVICE_GRANT_SECRET` to be set. A
process that starts in `dev`/`staging`/`production` with any of those missing refuses to boot
rather than silently running the local auth stub against real traffic.

### 2.4 Schema migrations

Per [ADR-012](../planning/adr/adr-012-supabase-cli-migrations.md), schema changes ship as plain
SQL in `supabase/migrations/*.sql`, applied by the pinned Supabase CLI, not Alembic:

```bash
# Local/staging (CLI handles TLS negotiation quirks against a plain target
# via PGSSLMODE=disable; see ADR-012's "TLS gotcha" note)
PGSSLMODE=disable supabase db push --db-url "$DATABASE_URL"
```

Migrations are forward-only: there are no downgrade scripts. Recovery from a bad migration is a
corrective roll-forward migration, rehearsed on staging first (ADR-012, Consequences).

## 3. Health checks

`api/health.py` exposes three Kubernetes-style probes plus a load-balancer alias:

**`GET /health/live`** (liveness: is the process up): checks nothing external; always returns
`200 {"status": "ok", ...}` if the process is running. This is what the Dockerfile's own
`HEALTHCHECK` and `docker-compose.yml`'s `healthcheck:` block poll.

**`GET /health/ready`** (readiness: can it serve traffic): runs `SELECT 1` against the database
(`check_database`). Returns `503` with per-check detail if the database is unreachable.

**`GET /health/startup`** (startup probe): identical to `/health/live` today; no
migration-completion check is wired in.

**`GET /health`** (undocumented alias, load-balancer compatibility): aliases `/health/live`.

**`check_cache()` (Redis)** is wired into `/health/ready` and performs a real `PING` against
`CYO_ADVENTURE_REDIS_URL` (the same Redis instance and timeout the rate limiter uses;
`middleware/security.py`). It reports one of three states in the response's `checks.cache`: `"ok"`
(ping succeeded), `"degraded"` (configured for Redis but the ping failed), or `"unconfigured"`
(`CYO_ADVENTURE_RATE_LIMIT_BACKEND=memory`, so nothing in the request path depends on Redis).
**Deliberately, cache status never flips `/health/ready`'s HTTP code**: the app fails open without
Redis (the rate limiter falls back to an in-memory counter on any Redis error), so a `200` can
still be paired with `checks.cache.status: false` when Redis is down; watch that field, or the
queue-depth and worker-log checks in Section 5.1, rather than relying on the top-level status
alone. `check_external_service()` remains an unwired placeholder: LLM/story-generation providers
are optional and provider-specific, so there is no single external dependency to ping generically.

**`check_generation_queue()` (ADR-021 Phase 1)** is wired into `/health/ready` as
`checks.generation_queue` and is the worker-down/worker-failing alarm: a stopped or crash-looping
worker, or a worker whose jobs are failing outright (e.g. the schema-drift incident that motivated
this check), is visible here well before anyone notices a specific story stuck. It reports
`"degraded"` (`status: false`) when any of three counts against `generation_job` is nonzero:

- **stale queued**: rows at `status="queued"` older than `DEFAULT_STALE_AFTER` (30 minutes,
  `generation/queue.py`), the same threshold `requeue_stranded_jobs` uses, so this check and the
  actual reclaim sweep can never disagree about what counts as stuck.
- **stale running**: rows at `status="running"` older than `generation_job_timeout_seconds` plus a
  margin (`RUNNING_STALE_MARGIN`), not a flat constant, so a legitimately long-running job is never
  flagged early.
- **recently failed**: rows at `status="failed"` updated within the last 24 hours. This is the
  signal that catches a *running* worker whose jobs are all failing (the schema-drift case); the
  first two counts alone only catch a *stopped* worker.

Like cache, **`generation_queue` never flips `/health/ready`'s HTTP code**: a stuck or failing
generation pipeline must not pull API pods out of the load-balancer rotation for endpoints that
never touch generation at all. Treat a nonzero `checks.generation_queue` count as a page-worthy
signal on its own dashboard/alert, not as a 503; see Section 5.1 for the diagnosis and remediation
steps this check is meant to trigger.

## 4. Logs and correlation IDs

All application logging goes through `structlog` (`utils/logging.py`); set `JSON_LOGS=true` in
any deployed environment (the `docker-compose.prod.yml` override does this) to get structured
JSON lines suitable for a log aggregator, or leave it `false` for human-readable console output
locally.

`CorrelationMiddleware` (`middleware/correlation.py`) is added before every other middleware and
propagates a request-scoped correlation ID into every log line for that request's lifecycle. It
accepts any of these inbound headers and echoes the resolved ID back on the response:

| Header | Purpose |
| --- | --- |
| `X-Correlation-ID` | Primary correlation header |
| `X-Request-ID` | Unique request identifier |
| `X-Trace-ID` | Distributed tracing ID |
| `X-Span-ID` | Span ID for tracing |

To trace one request end to end: grab the `X-Correlation-ID` (or `X-Request-ID`) from the browser
network tab or the frontend error toast, then filter backend logs on that value. Background jobs
(the RQ worker, which runs outside `CorrelationMiddleware`) bind a correlation ID manually where
the caller supplied one; `covers/worker.py::run_cover_job_sync` does this for cover jobs so a
cover failure's log lines trace back to the admin request that queued it. Story-generation worker
runs do not currently thread a correlation ID from the enqueuing request; correlate those by
`GenerationJob.id` instead (visible to admins via `GET /generation-jobs/{id}`).

Sentry is wired on both sides as of 2026-07-17, as a documented no-op unless a DSN is configured.
Backend: `core/observability.py::init_sentry()`, called from `app.py::create_app()`, is a no-op
unless `SENTRY_DSN` is set; when set it tags `environment` and a best-effort `release` (package
version), samples traces at `CYO_ADVENTURE_SENTRY_TRACES_SAMPLE_RATE` (default `0.1`), and always
sets `send_default_pii=False` (hardcoded in code, never a setting; this is a kids' app). Frontend:
`src/observability.ts::initSentry()`, called from `main.tsx`, is a no-op unless `VITE_SENTRY_DSN`
is set; Session Replay and BrowserTracing performance sampling are hardcoded off (no session
recording of a child's or guardian's session), and `beforeSend` strips request/response bodies and
any user identifier beyond a bare anonymous id before an event leaves the browser. Until a DSN is
configured for a given environment, logs remain the only observability surface there.

## 5. Common incidents

### 5.1 A generation job is stuck in "queued"

0. Check `GET /health/ready`'s `checks.generation_queue` first (Section 3): a nonzero
   `stale_queued`/`stale_running` count confirms a stopped or stalled worker, and a nonzero
   `recent_failed` count means the worker is running but every job is failing outright (check
   worker logs for the actual error before assuming this is a queue problem at all).
1. Confirm Redis is actually reachable from both the API and the worker process: `redis-cli -u
   "$CYO_ADVENTURE_REDIS_URL" ping`. If this fails, every enqueue since the outage started is
   either lost or stranded (see below); nothing is processing.
2. Confirm a worker process is actually running and pulling from the `"generation"` queue (`ps` /
   `docker-compose ps` / check the worker's own log stream for `generation_worker.reclaim_sweep_complete`
   at startup and per-job log lines afterward). Since this repo's compose file does not run a
   worker (Section 1), the most common cause in a fresh environment is simply that no worker was
   ever started.
3. If Redis was down or restarted without persistence, or a worker crashed mid-job, a row can sit
   at `status="queued"` forever because RQ lost the underlying job (`generation/queue.py`'s
   docstring on `requeue_stranded_jobs`). The reclaim sweep in `worker_main.py` re-enqueues any row
   stuck at `"queued"` for more than 30 minutes (`DEFAULT_STALE_AFTER`) automatically **the next
   time a worker process starts**: restarting the worker is therefore a legitimate first
   remediation step for a job that has been stuck for a while, not just a diagnostic no-op.
4. If the job is genuinely running but slow: `generation_job_timeout_seconds` defaults to 1800s
   (30 minutes) to comfortably cover a cold-start Ollama call plus the full three-stage pipeline;
   a job should never sit at `"running"` much past that without either completing or RQ's own
   timeout marking it failed.
5. `GenerationJob.status` progresses `queued` → `running` → one of `passed` / `needs_review` /
   `failed`. Check the row directly (admin-only `GET /generation-jobs/{id}`, or a database query)
   for `error` and `report` detail once it leaves `queued`.

### 5.2 Provider outage or degraded generation quality

The failover cascade (`generation/providers/fallback.py`, Section 1) tries each configured leg
in order. A leg's failure is either:

- **Transient** (retried inside that adapter, invisible to the cascade), or
- **Leg-fatal** (`ProviderError(leg_fatal=True)`): the cascade marks that leg dead for the rest of
  the run and moves to the next leg, logging `fallback.leg_dead`, or
- **Non-fatal but this attempt failed**: logs `fallback.leg_failover` and tries the next leg
  immediately.

If every configured leg is exhausted, the cascade raises and the job fails with
`fallback.all_legs_exhausted` in the logs (grep for this to confirm a full-cascade outage versus a
single-leg blip). A hard backstop of 30 total leg invocations per story
(`_DEFAULT_MAX_TOTAL_ATTEMPTS`) protects against a pathological retry storm even if the circuit
breaker logic above it misbehaves.

To diagnose: grep worker logs for `fallback.leg_dead` / `fallback.leg_failover` /
`fallback.all_legs_exhausted` around the affected job's timestamp, and check the named leg against
Section 8's provider credentials (an expired or missing key surfaces here as a leg-fatal error,
not a startup failure, per `.env.example`'s note that a missing provider key is a
`ConfigurationError` at call time). If OpenRouter (the primary and first-fallback leg) is down,
generation degrades to the local Ollama leg only, which is slower and, per `.env.example`, needs a
reachable `OLLAMA_BASE_URL` (with `OLLAMA_AUTH`/`OLLAMA_CA_BUNDLE` if it is the homelab instance
behind Traefik+Authentik) or every job fails.

### 5.3 Moderation / review backlog

`GET /api/v1/review-queue` (admin-only) lists every `in_review` storybook. There is no queue-depth
alerting; check it directly or via the admin console's Review queue page
(`/admin`, `frontend/src/admin/AdminConsolePage.tsx`). Two admin-tunable levers affect what
surfaces as needing attention there:

- **Moderation thresholds** (`GET/PUT/DELETE /api/v1/admin/moderation-thresholds`,
  `/admin/moderation-thresholds` in the console): per-(age-band, category) minimum verdict/score
  overrides, layered over `moderation.thresholds.DEFAULT_THRESHOLD`. Loosening a threshold reduces
  what gets flagged; every change is audited (`ModerationThresholdAudit`) and emits a
  `THRESHOLD_CHANGED` pipeline event.
- **Admin noise floor** (`GET/PUT /api/v1/admin/moderation/noise-floor`): a global score floor
  that denoises the *admin* review view only (bright-line BLOCK findings and unscored findings
  always surface regardless of the floor). Raising it thins the review queue without changing what
  guardians ever see (guardian-facing surfaces never apply this floor).

If the queue is growing because generation volume increased rather than reviewer capacity
shrinking, check the `/admin/moderation-dashboard` page's threshold-suggestion and
override-evidence sections (`ModerationDashboardPage.tsx`) before touching thresholds by hand.

### 5.4 Budget/quota complaints ("my family can't request more stories")

Family monthly spend is derived, not decremented from a ledger (ADR-015, interim G13): it counts
`StoryRequest` rows whose `approved_at` falls in the current UTC calendar month
(`story_requests/service.py::resolve_family_quota` / `enforce_family_quota`). There is no
persisted balance to inspect or repair directly.

- The effective quota is `Family.monthly_story_quota` if set on that family, else
  `settings.default_monthly_story_quota` (default 10).
- `GET /v1/families/me/budget` is what the guardian-facing `BudgetBanner` component reads
  ("N of M stories left this month"); it fails silently (renders nothing) on any error, so a
  guardian reporting "the counter just isn't there" is not necessarily a quota problem.
- An admin acting in the admin capacity is exempt from family quota entirely
  (`_bypasses_family_quota`): they spend platform budget, not the family's. If an admin's own
  authored request unexpectedly 409s with "monthly story budget reached," check whether they were
  resolved as a guardian principal for that call rather than admin.
- Since spend is derived by counting `approved_at` timestamps, the fix for a wrongly-blocked
  family (an admin error, a mis-set `monthly_story_quota`) is either raising
  `Family.monthly_story_quota` for that family or waiting for the UTC month to roll over; there is
  no per-family reset button.

### 5.5 A kid can't see a book that was approved

A published book reaching a child's shelf requires **both** of the following to be true; check
them in order:

1. **`Storybook.status == "published"`.** The state machine
   (`publishing/state_machine.py`) only reaches `published` via the `approve` action from
   `in_review`; `archived` (Section 9) or `needs_revision` books are excluded from every
   library read path. Confirm via the admin review screen (`/admin/review/:storybookId`) or a
   direct query.
2. **A `StorybookAssignment` row exists** for `(child_profile_id, storybook_id)`. This table is
   the sole authority for whether a child may see a story (`db/models.py::StorybookAssignment`
   docstring); approval alone does not assign a book to anyone. A guardian assigns a book from the
   Books page (`/guardian/books`, `AssignChildrenDialog.tsx`). If the guardian believes they
   already assigned it, check for a `visibility="family"` vs `"catalog"` mismatch (a catalog book
   from another family still needs an explicit assignment on this family's side) and check the
   offline-cache staleness note in Section 9 (a device that was offline when the assignment was
   made will not see it until it reconnects and syncs).
3. If both are true and the child still cannot see it: check the child's own session/device grant
   (`CHILD_SESSION_SECRET`-signed session, or a `DEVICE_GRANT_SECRET`-signed device grant per
   ADR-014) has not expired or been revoked, and that the reading client actually synced after the
   assignment (IndexedDB offline cache, `frontend/src/offline/`).

## 6. Backup and restore

**This is an explicit, owner-acknowledged gap, not an oversight.** As of this writing:

- [ADR-004](../planning/adr/adr-004-homelab-first-deployment.md) records "nightly Postgres dump
  and MinIO snapshot, with a restore drill in Phase 5" as a stated intent, and its own Success
  Criteria mark "A restore from backup succeeds in a drill" as **unchecked**.
- [ADR-009](../planning/adr/adr-009-supabase-platform.md) notes that Supabase's Pro plan (the
  production tier) includes automated backups/PITR as a platform feature, but "the restore drill
  remains ours to run" and its own Success Criteria mark the restore/export drill as
  **unchecked**.
- `docs/planning/roadmap.md`'s Phase 5 deliverable list includes "Sentry wired on client and
  server; backups and a tested restore" as **not started**.
- There is no backup script, restore script, or restore runbook anywhere in this repository today.

**Operator action, not a documented procedure**: until the Phase 5 backup-and-restore-drill
deliverable lands, do not assume any automated backup exists for the homelab/family tier beyond
whatever Supabase's Pro-plan PITR provides for the managed Postgres database itself (subject to
that plan actually being active for the target project; see ADR-009 decision 9 on plan tiers). If
you need a point-in-time restore before this deliverable ships, the immediate steps are: (1)
confirm which Supabase project tier the target environment is on and whether PITR is enabled in
the Supabase dashboard, (2) use the Supabase dashboard's own restore flow for Postgres, and (3)
treat any object-storage content (cover art in R2) as unbacked-up separately, since no export
tooling for it exists in this repo. Do not improvise a database dump/restore procedure without
first confirming it against the live schema (`supabase/migrations/`) and the async-engine
connection settings in `core/database.py`; a hand-rolled restore that skips the Supavisor
pooling constraints noted in ADR-009 (`CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE`) can corrupt
prepared-statement state under the transaction-mode pooler.

## 7. How you find out something broke

There are two scheduled, alerting synthetic checks today, both following the same pattern: on
failure, find-or-open a GitHub issue labeled `e2e-alert` whose title starts with a workflow-specific
marker, and comment on it with the failing run's URL and date, rather than leaving a red run nobody
checks the Actions tab for. The issue stays open and accumulates one comment per failing run until
someone resolves the underlying problem and closes it (a fresh issue opens after the next failure).
**Watch (or filter Issues by) the `e2e-alert` label** to be notified through GitHub's native issue
notifications; there is no other outbound channel (no Slack/email/pager integration) wired up.

- **`.github/workflows/e2e-prod.yml`** ("E2E (production)"): runs the Playwright `e2e-prod` tier
  daily (`30 13 * * *` UTC) against the live production URL (`https://cyo.williamshome.family` by
  default), signing in through the real login form with a dedicated test account and exercising a
  real device-grant mint/revoke. Its alert marker is `[e2e-prod]`.
- **`.github/workflows/e2e-real-nightly.yml`** ("E2E (real backend, nightly)"): runs nightly
  (`30 9 * * *` UTC) against a freshly seeded, real (non-mocked) backend spun up in CI (Postgres 16
  and Redis service containers, Supabase CLI migrations, a seeded dev dataset), rather than against
  live production; this is what exercises real cross-device conflict scenarios (two authorized
  devices racing a genuine 409 through the offline conflict dialog) that the mocked test suite
  cannot. Its alert marker is `[e2e-real-nightly]`.

A staging counterpart (`e2e-staging.yml`) and a corresponding `[e2e-staging]`-marker alerting step
are planned to land via PR #268 (per `e2e-prod.yml`'s own header comment) but do not exist on this
branch yet; today staging failures only produce a Playwright trace artifact on a red CI run, with
no issue-based alert. `docs/testing/` (a fuller test-strategy doc set) is likewise expected from
PR #268 and is not present in this checkout; once merged, link it here instead of duplicating its
content. For a manual, checklist-driven live verification (not automated alerting), see
[`docs/planning/r1-live-e2e-checklist.md`](../planning/r1-live-e2e-checklist.md).

## 8. Secrets and keys inventory

Names only; never commit or log actual values. Source real values from a secret manager
(Infisical is referenced in `README.md`), not from this file. Full descriptions live in
`.env.example`, which is the canonical, actively-maintained reference; this table is an index into
it, not a replacement for it.

**Backend process environment** (API and/or worker):

- `CYO_ADVENTURE_DATABASE_URL`: async SQLAlchemy connection string to Postgres (Supabase in every
  non-local tier).
- `CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE`: disables prepared-statement caching for the
  Supavisor transaction-pooler connection mode (ADR-009).
- `CYO_ADVENTURE_REDIS_URL` (`REDIS_URL` alias in compose): RQ queue and rate-limiter Redis
  connection. Needed by the backend and the worker.
- `ANTHROPIC_API_KEY`: direct Anthropic generation leg. Worker only.
- `OPENROUTER_API_KEY`: OpenRouter generation legs (primary + fallback). Worker only.
- `OLLAMA_BASE_URL` / `OLLAMA_AUTH` / `OLLAMA_CA_BUNDLE`: local/homelab Ollama fallback leg;
  `OLLAMA_AUTH` is HTTP Basic for the Traefik+Authentik-fronted homelab instance. Worker only.
- `MODAL_BASE_URL` / `MODAL_PROXY_KEY` / `MODAL_PROXY_SECRET`: experimental Modal generation leg
  (offline-only, never a production fallback). Worker only.
- `GEMINI_API_KEY`: cover-art generation (nano banana). Worker only.
- `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` /
  `R2_PUBLIC_BASE_URL`: Cloudflare R2 object storage for optimized cover images. Worker only.
- `OPENAI_API_KEY`: Stage-0 moderation classifier (OpenAI Moderation API). Backend and worker.
- `PERSPECTIVE_API_KEY`: Stage-0 moderation classifier (Google Perspective API). Backend and
  worker.
- `CYO_ADVENTURE_REVIEW_PROVIDER`: independent-review backend selector
  (`mock`/`ollama`/`openrouter`/`modal`); must differ from the generation provider. Backend and
  worker.
- `OIDC_ISSUER` / `OIDC_JWKS_URL` / `OIDC_AUDIENCE` / `OIDC_ALLOWED_ALGS`: guardian/admin
  bearer-token verification against Supabase Auth (ADR-009); required outside `local`. Backend
  only.
- `CHILD_SESSION_SECRET` / `CHILD_SESSION_TTL_SECONDS`: signs/verifies the backend-minted,
  12-hour, no-refresh child session token. Required outside `local`; never sent to the browser.
- `DEVICE_GRANT_SECRET` / `DEVICE_GRANT_TTL_SECONDS`: signs/verifies the 90-day revocable
  device-grant token (ADR-014). Required outside `local`, distinct from `CHILD_SESSION_SECRET`;
  never sent to the browser.
- `SENTRY_DSN`: backend error tracking (Section 4). Optional; a documented no-op when unset.
- `FORWARDED_ALLOW_IPS`: trust boundary for `X-Forwarded-For`/`-Proto` behind the reverse proxy;
  never `*`. Backend process env / uvicorn CLI flag.

**GitHub Actions secrets** (CI/CD, not runtime):

- `RELEASE_TOKEN`: fine-grained PAT (contents + pull-requests write) used by `release.yml` so an
  automated release PR triggers required CI checks (`GITHUB_TOKEN`-created PRs do not).
- `CODECOV_TOKEN` / `SONAR_TOKEN`: CI coverage/quality-gate upload tokens.
- `INFISICAL_CLIENT_ID` / `INFISICAL_CLIENT_SECRET`: CI machine identity for pulling secrets from
  Infisical.
- `E2E_PROD_TEST_EMAIL` / `E2E_PROD_TEST_PASSWORD` / `E2E_PROD_BASE_URL`: dedicated test-account
  credentials for the scheduled production E2E tier (Section 7), set on the `production`
  Environment; never a real family's credentials.

The frontend's own `frontend/.env.example` holds the browser-side `VITE_*` and Supabase publishable
keys; those are not backend secrets and are out of scope for this table.

## 9. Kill switch: pulling a book, incident path

The admin-only `POST /api/v1/storybooks/{storybook_id}/archive` endpoint
(`api/approval.py::archive_storybook`) is the kill switch: it moves a `published` book to
`archived` via the state machine (`publishing/state_machine.py`). This is a global,
cross-family action (`archive_storybook` does not scope by family; an admin can archive any
story). There is currently **no dedicated admin-console button** for this in
`frontend/src/admin/`; today it is invoked via the API directly (or a future console affordance),
same caveat as the authoring-plan step noted in the authoring guide.

What archiving actually does today, and what it does not:

1. **Immediately removes the book from every server-side read path.** `api/library.py` filters on
   `Storybook.status == "published"`, so an archived book stops appearing in any fresh library
   fetch (`GET` calls) the moment the transition commits. This is the "pull it everywhere the
   server serves it" half of the kill switch, and it works today.
2. **Revokes already-downloaded offline copies, at the device's next connection.** This shipped
   2026-07-17 (`frontend/src/offline/revocation.ts`, capability register G8/A5) as a purely
   client-side reconciliation: every successful, authoritative `/v1/library` fetch (including the
   refetch on reconnect) compares the profile's fresh shelf against the device's IndexedDB cache
   and drops reading state, queued offline writes, and (once no profile on the device still needs
   it) the cached story content itself for anything no longer on the shelf. No backend change was
   needed, because `/v1/library` was already the authoritative source. **One narrow, documented
   gap remains**: a book that is unassigned/archived/unpublished while a child is mid-read on the
   reader route, before their next library fetch, is not revoked until they navigate back to the
   library or the app reloads; closing that fully would need a push channel or the reader route
   re-validating against the shelf mid-session, which is out of scope of the shipped fix. A device
   that is genuinely offline (no connectivity at all) cannot be revoked until it reconnects; that
   is inherent to "offline," not a bug.
3. **Does not currently notify affected guardians automatically.** The notification feed
   (`api/notifications.py`) covers a story awaiting consent, a story ready on the shelf,
   kid-flagged content, and a failed generation; an archive action is not one of its projected
   event kinds today. This half of A5 (guardian notification) is still open.

For an incident where content reached a child and needs to be traced and contained:

1. Archive the storybook (above) to stop any further server-side reads immediately; the offline
   reconciliation above then pulls it from any device that reconnects (subject to the mid-read gap
   noted above).
2. Trace provenance via `GET /storybooks/{storybook_id}/review` (admin-only review surface): the
   moderation report on the storybook version is always available there. **The raw
   `GenerationJob.report`** (the full multi-stage prompt/model detail) **is deliberately nulled the
   instant the version is approved and published**, in the same transaction as the publish
   (ADR-007; `publishing/service.py::approve`), and again by a daily pg_cron sweep for any job
   whose report is still present 30 days after it reached a terminal status. For a story that has
   already been published, do not expect the raw generation report to still be there when
   investigating an incident after the fact; the moderation report and the pipeline event log
   (`events/`) are what remains.
3. Manually identify and contact affected guardians; there is no automated "notify everyone this
   book was assigned to" flow yet. Cross-reference `StorybookAssignment` rows for the archived
   `storybook_id` to find every affected child profile and its family.

## 10. Related documentation

- [ADR-004: Homelab-first deployment](../planning/adr/adr-004-homelab-first-deployment.md)
- [ADR-009: Supabase platform](../planning/adr/adr-009-supabase-platform.md)
- [ADR-012: Supabase CLI SQL migrations](../planning/adr/adr-012-supabase-cli-migrations.md)
- [Deployment architecture](../architecture/deployment.md)
- [Generation pipeline architecture](../architecture/generation-pipeline.md)
- `SECURITY.md` at the repository root (vulnerability reporting; also documents the
  Redis-backed rate limiter's fail-open fallback behavior referenced in Section 1; it lives
  outside the rendered docs tree, so open it on GitHub or in the repo checkout)
- [R1 live E2E checklist](../planning/r1-live-e2e-checklist.md)
- [Authoring guide](authoring-guide.md) (this deliverable's companion document, written for
  non-technical guardians and admins)
- [ADR-021: Service accounts, RLS, and in-repo worker deployment](../planning/adr/adr-021-service-account-rls-and-worker-deployment.md)
  (Section 11 below is this ADR's per-environment cutover procedure)

## 11. Service-account cutover (ADR-021)

Per [ADR-021](../planning/adr/adr-021-service-account-rls-and-worker-deployment.md), the
`cyo_api` and `cyo_worker` Postgres roles and their `service_rw` RLS policies ship as
`NOLOGIN` migrations (`supabase/migrations/20260720170100_create_service_roles.sql`,
`20260720170200_add_service_role_policies.sql`); applying those migrations changes nothing
at runtime by itself. Every environment keeps connecting as the shared `postgres` owner
role until an operator completes the steps below. **Merging the migrations is not the
cutover; this section is.**

### 11.1 Per-environment cutover procedure

Do this once per environment (staging first, always; never production first):

1. **Set each role's login password out-of-band.** Never in a migration file, never in this
   repo. Via the Supabase dashboard SQL editor (or `psql` against the project's direct
   connection, not the pooler):

   ```sql
   ALTER ROLE cyo_api LOGIN PASSWORD '<generated-secret>';
   ALTER ROLE cyo_worker LOGIN PASSWORD '<generated-secret>';
   ```

   Generate each password independently (do not reuse one password across roles or
   environments); store both in the environment's existing secrets mechanism (GitHub
   Actions Environment secrets / `homelab-infra` secret store, matching how
   `CYO_ADVENTURE_DATABASE_URL` is already stored today, Section 8).

2. **Verify allow/deny before touching any running process.** From a workstation or CI job
   with network access to the target database, run
   `uv run pytest tests/integration/test_rls_service_roles.py` against that project (or, at
   minimum, manually connect as `cyo_api`/`cyo_worker` with `psql` and confirm a `SELECT`
   against `public."user"` succeeds, then connect as `anon`/`authenticated` if those roles
   exist on the target and confirm the same query is denied). Do not proceed to step 3 on a
   failed verification.

3. **Flip the connection secrets, staging first.** Build the two new DSNs (same host/port/
   database as today, `cyo_api`/`cyo_worker` in place of `postgres`, the passwords from step
   1) and update:
   - `CYO_ADVENTURE_DATABASE_URL` (or the unprefixed `DATABASE_URL` alias): the API process's
     connection. Set it to the `cyo_api` DSN.
   - `CYO_ADVENTURE_WORKER_DATABASE_URL` (or the unprefixed `WORKER_DATABASE_URL` alias): the
     worker processes' connection. Set it to the `cyo_worker` DSN. Until this variable is
     set, the worker silently keeps using `CYO_ADVENTURE_DATABASE_URL` (the
     `worker_database_url_effective` fallback, `core/config.py`); this is intentional
     non-breaking behavior, not a bug, but means an operator who forgets this step has not
     actually completed the cutover for the worker process.

   Redeploy (or restart) the API and worker processes so the new environment variables take
   effect; both processes build their engine once at import time (`core/database.py`), so a
   running process never picks up a changed URL without a restart.

4. **Re-run the health check and a live smoke test** (Section 3; a guardian login, a library
   fetch, and if staging, a full story-request-to-review-queue pass) before considering the
   environment cut over. Watch logs (Section 4) for any `insufficient_privilege` /
   `permission denied` error in the minutes after restart; that means a table is missing
   from the grant/policy migrations (see the future-table checklist below) or a role/
   password was set incorrectly in step 1.

5. **Repeat for production only after staging has run clean for a reasonable soak period**
   (ADR-012's existing staging-first rehearsal norm applies here unchanged).

**Rollback**: revert `CYO_ADVENTURE_DATABASE_URL` / `CYO_ADVENTURE_WORKER_DATABASE_URL` (and
the worker alias) to the prior `postgres`-role DSN and restart the affected process(es). The
migrations themselves are forward-only (ADR-012) and never need to be undone: `cyo_api`/
`cyo_worker` and their policies are additive and harmless to leave in place even while
nothing connects as them. There is no data migration involved in this cutover, only a
connection-identity change, so rollback is immediate and has no data-loss risk.

### 11.2 Future-table checklist

RLS enforcement for `cyo_api`/`cyo_worker` is an explicit, per-table `GRANT` plus an
explicit, per-table `CREATE POLICY`; neither is inferred automatically from
`ENABLE ROW LEVEL SECURITY`. Any migration that adds a new application table and enables RLS
on it (following `20260711200745_enable_rls_all_tables.sql`'s precedent) must, in the same
PR, also add:

1. A `GRANT SELECT, INSERT, UPDATE, DELETE ON public.<new_table> TO cyo_api, cyo_worker;`
   statement (extend `20260720170100_create_service_roles.sql`'s table list, or add a new
   migration following the same shape if that file has already shipped to production).
2. A matching `service_rw` policy:

   ```sql
   DROP POLICY IF EXISTS service_rw ON public.<new_table>;
   CREATE POLICY service_rw ON public.<new_table>
     FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);
   ```

3. No `anon`/`authenticated` grant or policy, matching the deny-by-default posture
   established by `20260711200745_enable_rls_all_tables.sql` and preserved by this ADR.

Skipping either the `GRANT` or the policy leaves the new table effectively unreachable by
the API/worker in any environment that has completed the cutover above: a policy without a
`GRANT` is blocked at the privilege layer before RLS is even evaluated, and a `GRANT`
without a policy is blocked by RLS itself (`USING` defaults to deny with no matching
policy). `tests/integration/test_rls_service_roles.py`'s coverage-invariant test
(`test_every_rls_table_grants_both_service_roles`) fails loudly on either gap, so a CI run
against a PR that forgets this checklist should not pass silently, but the checklist exists
because that test is currently the only thing that would notice.
