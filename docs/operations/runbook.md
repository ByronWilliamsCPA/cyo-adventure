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

**Modal**: the non-OpenRouter backstop (third leg of the default provider cascade), replacing the
retired local Ollama leg. A separate Modal Auto Endpoint the worker calls over HTTPS
(`MODAL_BASE_URL`); not started by this repo's compose files. When `MODAL_BASE_URL`/`MODAL_MODEL`
are unset the leg is omitted and the cascade runs on its two OpenRouter legs alone, which is a
single-vendor posture; `build_provider` logs `generation.cascade_single_vendor` at WARNING when
that happens.

**Live-deployment caveat**: the actual R1 internal-web deployment's container definitions
(`cyo-backend`, `cyo-worker`, `cyo-redis`, the rollback-only `cyo-postgres`, and
nginx ingress) live in `services/cyo-adventure/` in the separate `ByronWilliamsCPA/homelab-infra`
repository, not in this repository. As of ADR-021 Phase 1, this repo's `docker-compose.yml` and
`docker-compose.prod.yml` do stand up a working generation pipeline locally (`app`, `worker`,
`redis`, `db`), but the live R1 stack still runs its own separately-defined `cyo-worker`/`cyo-redis`
in homelab-infra rather than pulling this repo's service definitions directly. Treat the tables and
commands below as what this repo actually provides; cross-check the homelab-infra repo for the live
stack's exact compose file when operating production.

The default LLM provider cascade for story generation (`generation/providers/fallback.py`, per
[ADR-003](../planning/adr/adr-003-frontier-llm-generation.md) as amended) is: OpenRouter Haiku
(primary) → OpenRouter Sonnet (fallback) → Modal (backstop, only when configured). Anthropic is an
additional per-job-selectable leg gated by the admin provider allowlist (Section 5.2, Section 8),
and Modal is selectable per-job as well as serving as the cascade's third leg.

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

**After any push that includes a `CREATE INDEX CONCURRENTLY`, check the index is valid.** This is
the one migration outcome that reports success and silently delivers nothing. A concurrent build
that fails partway leaves an `INVALID` index behind: Postgres will not use it for reads, but it is
still maintained on every write, so the symptom is the index's benefit quietly absent rather than an
error anyone sees. `pg_indexes` is no help, since it has no validity column and shows a full
`indexdef` for a half-built index, and re-running the migration does not repair it because
`if not exists` matches the invalid index by name and skips the rebuild.

```bash
psql "$DATABASE_URL" -c "
  select i.relname as index_name, x.indisvalid, x.indisready
  from pg_index x join pg_class i on i.oid = x.indexrelid
  join pg_namespace n on n.oid = i.relnamespace
  where n.nspname = 'public' and not x.indisvalid;"
```

An empty result is the pass. Any row returned is an invalid index: drop it concurrently and re-run
the creating statement, and do not leave it in place.

```bash
psql "$DATABASE_URL" -c 'drop index concurrently if exists "public"."<index_name>";'
```

### 2.5 Applying pending migrations to production (drift recovery)

Production's schema deploy is decoupled from its app deploy, and nothing compares the two. The app
image auto-deploys on merge; `supabase-production.yml` is `workflow_dispatch` only and gated behind
the `production` GitHub Environment's required reviewer. A run of merged-but-unapplied migrations can
therefore accumulate silently for weeks while the deployed app declares ORM columns and tables the
live database does not have.

**The readiness probe cannot tell you this.** `/api/v1/health/ready`'s `database` check opens a
connection and returns `status: true`; it never inspects the schema. SQLAlchemy validates nothing at
import or at startup either, so a mapped column that does not exist is a runtime error on the first
query that touches it, not a boot failure. The observable symptom is a 500 on real traffic against a
service whose health endpoint is green.

**Detect drift before you need to.** Compare the applied head against the repo:

```bash
# The ref you are about to deploy. Measure everything against THIS, not against
# origin/main: the dispatch below takes a ref, and a merge landing between the
# check and the dispatch would otherwise change the migration set silently.
REF="${REF:-origin/main}"

# Applied on PRODUCTION. Do NOT use --linked here: this checkout is linked to
# STAGING (Pre-flight step 1 records why), so --linked reports the wrong
# database and the comparison below would come out clean against the wrong one.
# SUPABASE_DB_URL is the production Supavisor session-mode pooler string on port
# 5432, defined in [Section 6](#6-backup-and-restore); the direct host is
# IPv6-only and is unreachable from most operator networks.
supabase migration list --db-url "$SUPABASE_DB_URL"

# What that ref carries. Anything listed here that the command above does not show is pending.
git ls-tree --name-only "$REF" supabase/migrations/
```

#### Pre-flight

1. **Take a dump first, and do not assume one exists.** `supabase-backup.yml` is scheduled nightly,
   but a scheduled run that never produced a usable artifact is not a backup. Confirm the state of
   the tiered R2 backups per [Section 6](#6-backup-and-restore) before you rely on one, and take a
   fresh dump regardless. Migrations are forward-only (ADR-012): there is no downgrade script, and
   the only recovery from a bad migration is a corrective roll-forward or a restore.

   ```bash
   # Roles, schema, and data as three files, so a partial restore is possible.
   # --db-url, NOT --linked: this checkout is linked to STAGING, so --linked here
   # would dump staging and leave you believing you held a production restore point.
   # SUPABASE_DB_URL is the production session-mode pooler string (Section 6).
   set -euo pipefail
   ts="$(date -u +%Y%m%dT%H%M%SZ)"
   out="$(mktemp -d)"
   supabase db dump --db-url "$SUPABASE_DB_URL" --role-only > "$out/preflight-${ts}-roles.sql"
   supabase db dump --db-url "$SUPABASE_DB_URL"             > "$out/preflight-${ts}-schema.sql"
   supabase db dump --db-url "$SUPABASE_DB_URL" --data-only > "$out/preflight-${ts}-data.sql"

   # A dump that failed can still leave a file. Refuse to proceed on an empty one.
   for f in "$out/preflight-${ts}"-*.sql; do
     [ -s "$f" ] || { echo "EMPTY DUMP, do not dispatch: $f" >&2; exit 1; }
   done
   echo "dumps in $out"
   ```

   **These are not a platform backup, and the distinction decides what they can restore.**
   `supabase db dump` covers the application schema and cluster roles. It does NOT include the
   Supabase-managed schemas (`auth`, `storage`) or Storage objects. `auth.users` is therefore
   absent, and that table is the authoritative source for adult account emails (`public.user.email`
   is NULL for the two oldest adults). Treat these files as an application-table restore point;
   anything that needs auth or Storage back has to come from Supabase's own managed backups.

   Store these off the runner and off the operator laptop's temp directory. They contain the full
   production dataset, including children's profile data, so they are subject to the same handling
   rules as any production extract (see [Section 8](#8-secrets-and-keys-inventory)).

   **Check that you can actually run this before you need it.** On 2026-08-24 this step was not
   executable: the local checkout is `supabase link`ed to staging, no operator held
   `SUPABASE_DB_PASSWORD` for production, and `gh secret list --env backups` returned nothing, so
   `supabase-backup.yml` could not have produced an artifact on any night it ran. Do not close that
   gap by adding a dump-and-upload step to a workflow: this repository is **public**, GitHub
   workflow artifacts are readable by anyone with repo read access, and a `supabase db dump` is the
   entire production dataset. A restore point has to land somewhere access-controlled (the R2
   backup bucket, or Supabase's own managed backups), never in CI artifact storage.

   When no dump is possible, do not proceed blind and do not proceed unbounded: read the pending
   set for destructive verbs and take a targeted snapshot of exactly what they touch. On the
   2026-08-24 apply, all 18 pending migrations were scanned; every `DROP` was a
   drop-then-recreate of a constraint, policy, or index, and the only data-touching statements were
   two `UPDATE`s and one `DELETE FROM provider_model_allowlist`. Nothing touched child, family,
   story, or reading data, so a five-row snapshot of that one table, rendered as a replayable
   `INSERT`, was a proportionate restore point. That reasoning is the substitute for a dump, and it
   only works because it was written down before the dispatch.

2. **Confirm staging is green on the same migration set.** The workflow's own RUN POLICY requires it:
   only dispatch production after the staging deploy of the same migrations and config has succeeded.
   Check the most recent successful `Deploy Supabase Migrations (staging)` run and compare its
   **migration set** against the ref you are dispatching, not merely its ancestry. An ancestor check
   passes vacuously in the case that matters: if staging succeeded at commit A and you dispatch
   descendant B, A is still an ancestor of B even when B adds migrations staging never ran.

   ```bash
   STAGING_SHA="$(gh run list --workflow=supabase-staging.yml --status=success --limit=1 \
     --json headSha --jq '.[0].headSha')"
   diff <(git ls-tree --name-only "$STAGING_SHA" supabase/migrations/) \
        <(git ls-tree --name-only "$REF"         supabase/migrations/) \
     && echo "same migration set" || echo "DIFFERENT: staging did not validate this set"
   ```

3. **Read the pending set, do not just count it.** Migrations that create indexes concurrently,
   rewrite constraints, or backfill data have post-deploy checks of their own; several carry a
   `#VERIFY` line naming the check. Collect those before dispatching, because the push reports success
   whether or not they hold.

#### Dispatch

The push runs only through the workflow, never from an operator shell against production. The
workflow asserts `SUPABASE_PROJECT_ID` is non-empty and matches `[remotes.production].project_id` in
`supabase/config.toml` before it pushes anything, which is the guard that keeps a mistyped or
inherited project reference from pointing the push at the wrong database.

```bash
# --ref pins the dispatch to the commit staging validated above. Without it the
# workflow runs the DEFAULT BRANCH, so a merge landing in between silently
# changes the migration set after the pre-flight checks passed.
gh workflow run supabase-production.yml --ref "$REF"
gh run watch "$(gh run list --workflow=supabase-production.yml --limit=1 --json databaseId   --jq '.[0].databaseId')"
```

The run pauses for the `production` environment's required reviewer. Note the two deliberate
differences from staging: production runs `supabase db push` **without** `--include-all`, so an
out-of-order migration file is skipped rather than applied, and the concurrency group
`supabase-production-deploy` sets `cancel-in-progress: false`, so a second dispatch queues behind the
first instead of interrupting a half-applied push.

#### Post-deploy verification

A green workflow run is not evidence the schema is correct. Run all four checks:

1. **Applied head matches the repo.** Re-run the two commands under "Detect drift" above and confirm
   the pending set is now empty.

2. **Every concurrently-built index is valid.** Run the `indisvalid` query in
   [Section 2.4](#24-schema-migrations). An empty result is the pass. This matters whenever the pushed
   set contains a `CREATE INDEX CONCURRENTLY`, which succeeds and delivers nothing when it fails
   partway.

3. **Constraint-widening migrations actually widened the constraint.** A migration guarded by
   `IF EXISTS(... NOT LIKE ...)` exits 0 having done nothing when the constraint is absent as well as
   when it is already current, so "the migration ran" is not the same claim as "the constraint holds
   the new member". Read the constraint rather than the migration history:

   ```bash
   psql "$DATABASE_URL" -c "
     select conname, pg_get_constraintdef(oid)
     from pg_constraint
     where conrelid = 'public.pipeline_event'::regclass and contype = 'c';"
   ```

   Confirm every event type the deployed code emits appears in `ck_pipeline_event_event_type`. Note
   that the corrective fixes to nine already-applied migrations are inert on any database that has
   already recorded those versions: the CLI tracks migrations by version, not by content, so an edited
   migration never re-runs. If a member is missing on a database whose history says the migration
   applied, the fix is a new roll-forward migration, not an edit to the old one.

4. **An authenticated request actually succeeds.** The schema checks above prove the columns exist;
   only real traffic proves the deployed ORM and the live schema agree. Every authenticated adult
   request resolves its principal through a `select` against `user`, so a single authenticated call is
   a broad smoke test:

   ```bash
   # --connect-timeout/--max-time so a wedged origin fails instead of hanging, and an
   # explicit status test so the command's own exit code carries the verdict: bare
   # `curl -sS` exits 0 while printing 500, which reads as a pass in any script.
   code="$(curl -sS --connect-timeout 5 --max-time 20 -o /dev/null -w '%{http_code}' \
     -H "Authorization: Bearer $TOKEN" https://cyo.williamshome.family/api/v1/me)"
   echo "$code"
   [ "$code" = "200" ] || { echo "NOT 200, drift is not cleared" >&2; exit 1; }
   ```

   A 200 is the pass. A 500 here against a green `/health/ready` is the drift signature described at
   the top of this section.


## 3. Health checks

`api/health.py` exposes three Kubernetes-style probes plus a load-balancer alias. The router is
mounted twice (`app.py`), and **which form you probe decides whether you learn anything**:

- **`/api/v1/health/*`** is reachable from outside the cluster, through nginx's `location /api/`.
  Use this form for everything external: uptime monitors, manual `curl`, the e2e tiers.
- **`/health/*`** is reachable on the container's own port 8000 only. It exists for in-container
  loopback probes that cannot be updated in the same deploy as this repo.

> **Never probe `/health/*` from outside.** `frontend/nginx.conf` proxies only `location /api/`, so
> the un-prefixed form never reaches FastAPI from the public host. Until 2026-08-04 nginx also
> answered `location /health` with a hardcoded `200 'OK'`, so an external probe of
> `/health/ready` returned success **with the database completely down**, and this runbook's own
> "verified 200" note carried that false pass for a month (register item `UW-L04`). nginx now
> returns `404` there instead. When probing by hand, assert the response is
> `content-type: application/json` with a `checks` object, not merely a `200`: a static stub can
> forge a status code, and it cannot forge FastAPI's response model.

**`GET /api/v1/health/live`** (liveness: is the process up): checks nothing external; always returns
`200 {"status": "ok", ...}` if the process is running. This is what the Dockerfile's own
`HEALTHCHECK` and `docker-compose.yml`'s `healthcheck:` block poll. The **production** healthcheck
lives out-of-repo (homelab-infra `services/cyo-adventure/docker-compose.yml`) and still polls the
un-prefixed `/health/live`, which is exactly why the alias must not be retired until that file has
moved and been redeployed.

**`GET /api/v1/health/ready`** (readiness: can it serve traffic): runs `SELECT 1` against the
database (`check_database`). Returns `503` with per-check detail if the database is unreachable.

**`GET /api/v1/health/startup`** (startup probe): identical to `/api/v1/health/live` today; no
migration-completion check is wired in.

**`GET /api/v1/health/`** (undocumented alias, load-balancer compatibility): aliases
`/api/v1/health/live`.

**`GET /nginx-health`** is a different thing entirely: the frontend container's own two-byte stub,
served by nginx and never reaching the backend. It answers whether nginx is up, nothing more. It is
useful as a control: if `/nginx-health` succeeds while `/api/v1/health/ready` fails, the frontend
is serving and the backend is unreachable behind it.

**`check_cache()` (Redis)** is wired into `/api/v1/health/ready` and performs a real `PING` against
`CYO_ADVENTURE_REDIS_URL` (the same Redis instance and timeout the rate limiter uses;
`middleware/security.py`). It reports one of three states in the response's `checks.cache`: `"ok"`
(ping succeeded), `"degraded"` (configured for Redis but the ping failed), or `"unconfigured"`
(`CYO_ADVENTURE_RATE_LIMIT_BACKEND=memory`, so nothing in the request path depends on Redis).
**Deliberately, cache status never flips `/api/v1/health/ready`'s HTTP code**: the app fails open without
Redis (the rate limiter falls back to an in-memory counter on any Redis error), so a `200` can
still be paired with `checks.cache.status: false` when Redis is down; watch that field, or the
queue-depth and worker-log checks in Section 5.1, rather than relying on the top-level status
alone. There is deliberately no generic external-service check: LLM/story-generation providers
are optional and provider-specific, so there is no single external dependency to ping
generically. A `check_external_service()` placeholder that always returned `status=True`
was removed on 2026-08-13 (`UW-J17`) rather than left one uncommented line away from a
false-healthy readiness signal; a real external dependency should get its own named check
modelled on `check_cache()`.

**`check_generation_queue()` (ADR-021 Phase 1)** is wired into `/api/v1/health/ready` as
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

Like cache, **`generation_queue` never flips `/api/v1/health/ready`'s HTTP code**: a stuck or failing
generation pipeline must not pull API pods out of the load-balancer rotation for endpoints that
never touch generation at all. Treat a nonzero `checks.generation_queue` count as a page-worthy
signal on its own dashboard/alert, not as a 503; see Section 5.1 for the diagnosis and remediation
steps this check is meant to trigger.

**`check_database_privilege()` (ADR-021 cutover observability)** is wired into `/api/v1/health/ready` as
`checks.database_privilege` and reports whether the API's connected role can bypass row-level
security. It covers all three bypass paths PostgreSQL actually has:

1. the `rolbypassrls` role attribute;
2. `rolsuper`, which bypasses regardless of `rolbypassrls`;
3. **table ownership**. RLS never applies to a table's owner unless the table sets
   `FORCE ROW LEVEL SECURITY`, and this schema deliberately does not. The baseline migration
   assigns the Tier 1 tables to `postgres`, so ownership, not `rolbypassrls`, is the path an
   un-cut-over environment actually uses.

`"ok"` means no path applies; `"degraded"` means at least one does. The warning log names which
one (`via_role_attribute`, `via_table_ownership`), because an operator fixes ownership and role
attributes differently. A role with no `pg_roles` row reports `"degraded"`, not `"ok"`: an
unanalyzable role fails closed. `"unknown"` is distinct from `"degraded"` and means the query
itself failed, so the posture was never measured. The connected role name is logged, never
returned: `/api/v1/health/ready` is unauthenticated, so the response carries only the posture bit.

Like cache and generation_queue, **`database_privilege` never flips `/api/v1/health/ready`'s HTTP code**:
a pre-cutover environment is an open security finding, not an outage, so it must not pull pods out
of rotation. One limit matters when reading this field: it covers the **API process only**. The
worker has no HTTP surface, so a forgotten `CYO_ADVENTURE_WORKER_DATABASE_URL` is invisible here.
The worker reports itself at startup instead; see Section 11.2.

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

0. Check `GET /api/v1/health/ready`'s `checks.generation_queue` first (Section 3): a nonzero
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
   (30 minutes) to comfortably cover a cold-start Modal call plus the full three-stage pipeline;
   a job should never sit at `"running"` much past that without either completing or RQ's own
   timeout marking it failed.
5. `GenerationJob.status` progresses `queued` → `running` → one of `passed` / `needs_review` /
   `failed`. Check the row directly (admin-only `GET /generation-jobs/{id}`, or a database query)
   for `error` and `report` detail once it leaves `queued`.
6. **After a provider retirement**, a job can fail immediately with `generation provider '<name>'
   is retired and can no longer be built`. That is not a misconfiguration of the running service:
   the row was enqueued before the retirement deployed and still names the old provider in its
   `authoring_metadata`, which `process_generation_job` passes to `build_provider` verbatim.
   `build_provider` deliberately fails these rather than silently substituting a live provider,
   because substituting one would bill the story to a backend the admin did not choose and would
   make the job's own recorded provider attribution false (which is what reviewer independence is
   computed from).

   The failure is terminal, not a loop: `build_provider` raises before the pipeline's own
   try/except, so `run_generation_job`'s finally guard force-fails the row via `_record_failure`
   and it lands at `status='failed'` with the retirement message in `error`. The step-3 reclaim
   sweep only re-enqueues rows still sitting at `'queued'`, so it never picks a failed row back
   up. What that means operationally: a stale row the worker has already reached is **already
   failed** and needs a guardian re-request, not draining; a stale row still at `'queued'` (or one
   the sweep re-enqueues after a Redis loss, which is why the exposure window outlasts the deploy
   itself) will fail exactly once on the next worker pass. Rewriting a row in place is therefore
   only useful **before** a worker reaches it.

   Find the affected rows with (`'ollama'` is the only current entry in `RETIRED_PROVIDERS` in
   `generation/provider.py`; read that set rather than trusting this literal, or the query returns
   a false all-clear after the next retirement):

   ```sql
   SELECT id, status,
          authoring_metadata ->> 'provider' AS provider,
          authoring_metadata ->> 'model'    AS model
   FROM generation_job
   WHERE authoring_metadata ->> 'provider' = 'ollama'
   ORDER BY status;
   ```

   Deliberately unfiltered by status: the rows most in need of action are the ones already at
   `'failed'`, and a `status IN ('queued','running')` filter would hide exactly those.

   **Preferred remediation** is to let the rows reach `'failed'` and have the guardian re-request,
   which re-runs the authoring-plan endpoint and produces a coherent provider/model pair validated
   against the current allowlist. To drain the not-yet-executed ones immediately instead of waiting
   for a worker to fail each in turn:

   ```sql
   UPDATE generation_job
   SET status = 'failed',
       error  = 'provider retired; re-request required'
   WHERE authoring_metadata ->> 'provider' = 'ollama'
     AND status IN ('queued', 'running');
   ```

   **Rewriting the row in place** is the alternative, and it must change *both* keys.
   `process_generation_job` reads `authoring_metadata->>'provider'` **and**
   `authoring_metadata->>'model'` and passes them to `build_provider` as `provider_override` and
   `model_override` (`_authoring_provider_override` / `_authoring_model_override`). Rewriting the
   provider alone leaves the retired backend's model id (e.g. `llama3.1:8b`) as the override, and
   that string is not rejected at build time: the job would run the new provider against a model
   it does not serve, failing at the API call or, worse, resolving to some other model than the
   one recorded. Drop the `model` key to take the new provider's configured default, which is the
   safer of the two rewrites:

   ```sql
   UPDATE generation_job
   SET authoring_metadata = (authoring_metadata - 'model')
                            || jsonb_build_object('provider', 'openrouter')
   WHERE authoring_metadata ->> 'provider' = 'ollama'
     AND status IN ('queued', 'running');
   ```

   The replacement provider must be one the family lane permits (`FAMILY_LANE_PROVIDERS` in
   `generation/provider.py`: `openrouter` or `modal`; `mock` is a CI-only double). The worker
   always calls `build_provider(..., lane="family")`, so rewriting to `anthropic` just swaps the
   retirement error for a lane-rejection error. Accept, too, that this changes the job's recorded
   provider attribution, which is what the raise was protecting.

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
generation degrades to the Modal leg only, which needs a reachable `MODAL_BASE_URL`/`MODAL_MODEL`
or every job fails. **If Modal is not configured at all, an OpenRouter outage stops generation
outright**: both remaining legs are the same vendor on the same account, so there is nothing left
to fail over to. Check for `generation.cascade_single_vendor` in the worker logs to tell the two
situations apart.

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

**Partially closed** (issue #558 / `UW-D27`). A scheduled backup exists and has been observed
to complete (2026-08-27); the restore side is documented below but **not yet drilled against a
live project** -- see the `#VERIFY` note at the end of this section before relying on it in a
real incident.

> **A backup completed successfully for the first time on 2026-08-27** (run `33094165033`, a
> manual `workflow_dispatch`). All six secrets are present in the **`backups`** environment
> scope and the dump/encrypt/upload path works end to end, so there IS something to restore
> from. **The restore side is still undrilled**: see the `#VERIFY` note at the end of this
> section before relying on it in a real incident. That gap, not the backup side, is what
> keeps this section provisional.
>
> History, kept because both traps recur and neither is visible from a green dashboard. Until
> 2026-08-27 no run had ever succeeded. Runs before 2026-08-11 never executed at all: the job
> named the `production` environment, whose required-reviewer rule parks a scheduled run in
> `waiting` until it expires as `cancelled`. That is the identical trap this runbook documents
> for `e2e-prod.yml` in Section 7, and it is why `production-e2e` exists. #696 moved the job to
> a dedicated `backups` environment with no protection rules on 2026-08-24. The run that then
> executed still failed, on a malformed `R2_ACCOUNT_ID` that GitHub's secret mask rendered as
> an undiagnosable `Invalid endpoint: https:// ***.r2.cloudflarestorage.com`. Because the mask
> hides the stray character, each defect cost one dispatch to identify; `scripts/backup_database.py`
> now validates all six values up front and reports every bad one in a single run.
>
> The concurrency shape that produced the 16-day wedge is unchanged: the workflow still declares
> `group: ${{ github.workflow }}` with `cancel-in-progress: false`, so a run parked in `waiting`
> still blocks every later run in the same group rather than being superseded by one.

### What runs today

`.github/workflows/supabase-backup.yml` runs
`scripts/backup_database.py` daily at 08:00 UTC (and on
`workflow_dispatch`). Each run:

0. Verifies the destination bucket carries a `.cyo-backup-bucket` marker object before doing
   anything else, and refuses to run if it does not. Every destructive step in the script is
   scoped by bucket **name** alone, and the lifecycle write in step 5 fully REPLACES whatever
   configuration the named bucket already has, so a mistyped or rotated `R2_BACKUP_BUCKET`
   (the public covers bucket is one typo away) would otherwise be silently accepted. Initialize
   a brand-new bucket once with `--init-bucket`; never as part of the scheduled run.
1. Executes `supabase db dump` three times (roles, schema, data-via-COPY) against
   `SUPABASE_DB_URL`, which **must be the Supavisor session-mode pooler on port 5432**
   (`postgresql://postgres.<ref>:<password>@aws-0-us-east-1.pooler.supabase.com:5432/postgres`),
   **not** the transaction-mode pooler on port 6543.
   [ADR-009](../planning/adr/adr-009-supabase-platform.md)'s Supavisor constraints
   (`CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE`) describe the **transaction-mode**
   pooler, which reassigns backends mid-session and can corrupt prepared-statement state
   on a long-lived dump connection. Session mode holds one backend for the life of the
   connection and is the supported route for `pg_dump`/`pg_dumpall`; the production
   `cyo-adventure-db-backup` sidecar has dumped this database through it since 2026-07.

   > **This instruction previously said "direct (non-pooler)" and that was wrong in a way
   > that could not work.** `db.<project-ref>.supabase.co` resolves to **AAAA only** (no
   > IPv4 A record) on this project. `supabase db dump` runs `pg_dumpall` inside a Docker
   > container, whose default bridge network is IPv4-only, and GitHub-hosted runners have
   > no IPv6 egress either. Both therefore fail with `could not translate host name ... to
   > address: Name or service not known` before any authentication happens. Verified
   > 2026-08-24. Restoring the direct route would require the Supabase IPv4 add-on.
2. Encrypts each leg with AES-256-GCM (a random nonce per file; the key never leaves the
   `BACKUP_ENCRYPTION_KEY` secret and is not derivable from the ciphertext).
3. Uploads to a **dedicated** R2 bucket (`R2_BACKUP_BUCKET`, distinct from the public covers
   bucket, using a scoped R2 token distinct from the covers-upload token) under a tiered
   prefix: `daily/` always, `weekly/` on ISO Sunday, `monthly/` on the 1st.
4. Asserts that a recent **pre-existing** backup still exists: lists the date prefixes under
   `daily/`, excludes today's, and fails the run if the newest survivor is more than 3 days old
   (or if none survives at all). The workflow's failure alert fires on a run that HAPPENS and
   fails; it cannot fire for a run that never happens, and GitHub disables scheduled workflows
   after 60 days of repository inactivity. Without this, a stopped schedule would let retention
   quietly empty the bucket with zero red runs. It also doubles as the only exercise of the R2
   **read** path, so a token scoped without list permission is caught here rather than during a
   restore. An empty bucket is accepted only under `--init-bucket`.
5. Applies a per-prefix R2 lifecycle expiration rule **where the token permits it**: daily
   7 days, weekly 28 days, monthly 180 days. In this deployment it does not permit it, so the
   rules are hand-set and neither the self-healing nor the `workflow_dispatch` retention inputs
   are live; see the blockquote below before relying on either. This bounds total retained storage to roughly 7 + 4 + 6 = 17
   backup sets at any time, sized for limited R2 space rather than unbounded growth -- re-tune
   the day counts once real dump sizes are known (see the `#ASSUME` in the script's module
   docstring). Retention values are validated before anything else runs, against per-tier floors
   (daily >= 3, weekly >= 14, monthly >= 90) and a `daily <= weekly <= monthly` ordering rule;
   a deliberate shrink below a floor needs `--force-retention`, and the ordering rule is never
   waived.

   > **In this deployment the script does NOT assert these rules; they are set by hand.** R2
   > scopes API tokens by permission *class*, and lifecycle is a bucket-level operation that an
   > object-scoped token may not call. R2's admin permissions cannot be restricted to a single
   > bucket, so an admin token able to manage lifecycle here could also delete the public covers
   > bucket. We kept the least-privilege token, so `ensure_lifecycle_rules()` logs
   > `backup_lifecycle_unmanaged` and continues instead of failing the run.
   >
   > The three rules are configured on the `cyo-backups` bucket in the Cloudflare dashboard
   > (R2 > the bucket > Settings > Object lifecycle rules), and must stay in sync with the
   > defaults above:
   >
   > | Rule name | Prefix | Action | Days |
   > | --- | --- | --- | --- |
   > | `expire-daily` | `daily/` | Delete objects | 7 |
   > | `expire-weekly` | `weekly/` | Delete objects | 28 |
   > | `expire-monthly` | `monthly/` | Delete objects | 180 |
   >
   > Three consequences to hold onto:
   >
   > - **No automated check can confirm these rules exist or stayed correct**, because the token
   >   cannot read lifecycle config either. Retention silently not working looks exactly like
   >   retention working. Re-check the dashboard by eye whenever you touch the bucket.
   > - **The `workflow_dispatch` retention inputs no longer reach R2.** They still validate against
   >   the floors and still appear in the run log, but the dashboard is the only thing that decides
   >   when an object expires. Changing retention means editing the rules by hand AND passing the
   >   matching inputs, or the log and reality diverge.
   > - The bucket also carries a `Default Multipart Abort Rule` that this script does not own. If
   >   the token is ever widened, the next run's `put_bucket_lifecycle_configuration` would REPLACE
   >   the whole configuration and delete it; `backup_lifecycle_replacing_foreign_rules` warns
   >   first, and that warning must be believed.

The step order is deliberate: nothing is expired or mutated until a good backup is positively
confirmed. The lifecycle write is last (when the token permits it at all), so a run that fails its
dump cannot leave a bad retention value behind; the staleness check sits between the upload and the lifecycle write, so today's
backup is safely stored before the alarm fires and an incident starts with one more good backup,
not one fewer.

A failed run opens or comments on a `ci-failure`-labelled issue titled `[db-backup] scheduled
database backup failing`, per the "Alert on failure" step in the workflow (a separate job holding
`issues: write`, so the job that handles the six production secrets never holds it): see Section 7
for the general convention. Since #771 a green **scheduled** run also closes that issue
(`mode: resolve`), so an open one means a currently failing schedule rather than backlog. A
green `workflow_dispatch` deliberately does not close it: a manual run proves a human can make
the job pass, not that the cron fired at all.

Cover art in R2 is **not** covered by this workflow; it remains unbacked-up separately, since no
export tooling for object storage exists in this repo (tracked as its own gap, distinct from
`UW-D27`).

### Restore procedure

1. Identify the backup to restore from: list objects under `daily/`, `weekly/`, or `monthly/`
   in the R2 backup bucket for the target date (`<tier>/<YYYY-MM-DD>/{roles,schema,data}.sql.enc`).
2. Download the three `.enc` objects and decrypt each with
   `scripts/backup_database.py`'s `decrypt_bytes(blob, key)`, using the same
   `BACKUP_ENCRYPTION_KEY` the backup was taken with (store this key OUTSIDE this repo; losing
   it makes every existing backup unrecoverable). A short one-off script or a REPL invocation
   against the imported module is sufficient; there is no dedicated CLI restore command yet.
3. Restore into a **new, empty** target database first, never directly into a live project:
   `psql "$TARGET_DB_URL" -f roles.sql`, then `-f schema.sql`, then `-f data.sql`, in that
   order (roles before schema before data, matching Supabase's own documented dump/restore
   ordering).
4. Verify row counts on a handful of load-bearing tables (`family`, `profile`, `storybook`,
   `storybook_version`) against expectations before pointing any environment at the restored
   database.
5. Only after (3) and (4) succeed against a scratch database should a restore ever be pointed
   at production, and only as a deliberate incident-response decision, not a routine drill step.

> **#CRITICAL data integrity**: this restore procedure has been written to match the backup
> format exactly, but has NOT been exercised end-to-end against a real Supabase project from
> this repository. A backup that has never been restored is unverified by definition.
> **#VERIFY**: run one real restore into a scratch Supabase project (or local Postgres) before
> treating this as a closed capability; update this section with the actual command output
> and any deviation found, and flip the roadmap's Phase 5 "backups and a tested restore" line
> only after that drill succeeds.

## 7. How you find out something broke

Every alerting scheduled job now routes through ONE implementation,
`.github/actions/ci-failure-issue`.
On failure it finds-or-opens a GitHub issue whose title starts with a workflow-specific marker and
comments on it; on a green scheduled run it CLOSES that issue. There is no other outbound channel:
no Slack, email, or pager integration is wired up.

Three things about that are worth knowing before you read either label:

- **Assignment is the notification, not the comment.** A comment on an issue notifies subscribers and
  participants only, and these issues are opened by a bot with no human participant. Every issue is
  therefore assigned (`williaby` by default). GitHub silently ignores an assignee who lacks push
  access and still returns success, so the action re-reads the assignees off its own response and
  FAILS THE STEP when the login was dropped. A red alerting step means "nobody was told", and it is
  the more urgent of the two failures.
- **An open issue means a CURRENTLY failing workflow.** Since 2026-08-27 a green scheduled run closes
  the issue automatically (`mode: resolve`). Before that, closing was a sentence in the issue body
  asking a human to do it, nobody ever did, and the labels accumulated stale issues until a new alert
  was indistinguishable from backlog. Reading either label as a live list is only valid because of
  that change.
- **A resolve leg is gated on `github.event_name == 'schedule'`.** A green manual run proves a human
  can make the job pass, not that the cron is alive: a scheduled run cancelled at a
  `cancel-in-progress: false` concurrency gate dispatches zero jobs and reports nothing at all. That
  is not hypothetical, see [section 6](#6-backup-and-restore) and issue #667.

The label splits by what kind of job it is, which is deliberate rather than historical accident:
`e2e-alert` for the browser-facing scans, `ci-failure` for ops and quality jobs. **Watch (or filter
Issues by) both.**

To list the current producers:

```bash
# Every workflow that files or resolves a tracking issue. Do NOT trust a literal
# count here: the number in this section has now been wrong three separate times.
# The two commands below ARE the count. Run them.
#
# Match on `uses:`, not on the path alone, and restrict to `*.yml`. Without
# --include the pattern also matches .github/workflows/test/health-rollup.test.mjs,
# which quotes the same line inside a JavaScript comment and is not a producer;
# that one false positive is why the unfiltered grep returns one more line than
# there are producers. ci.yml names the same directory too (it runs the action's
# test harness) but never in the `uses:` form, so it does not match either grep.
grep -rln --include='*.yml' 'uses: ./.github/actions/ci-failure-issue' .github/workflows/ | wc -l
grep -rl 'label: e2e-alert' .github/workflows/ | wc -l

# Which label and marker each one uses. A call site with no `label:` line uses
# the action's default, `ci-failure`.
grep -rn -A6 'uses: ./.github/actions/ci-failure-issue' .github/workflows/ \
  | grep -E 'marker:|label:|mode:'
```

Read the two counts as: **producers minus `e2e-alert` producers is the `ci-failure` backlog**, the
workflows whose failures land under the default label. Derived on 2026-08-29 the first command
returns **21** and the second **6**, so **15** producers fall through to `ci-failure`. Those figures
are a snapshot, not the contract: if your run disagrees with them, your run is right and this
paragraph is stale.

Do NOT grep for `labels: '` here, which is what this section used to say. The label is now an input
to the composite action and most producers do not pass it at all, so that grep returns a near-empty
list that reads exactly like "almost nothing alerts". The count has been wrong three times: first
from the retired `labels: '` grep; then from a naive per-file `grep -c 'label:'`, which also matches
`label:` inside JavaScript object literals in `github-script` steps (`planning-linkage.yml`,
`scheduled-health-rollup.yml`) that are action-unrelated dictionary keys rather than `with:` inputs;
and most recently from a hardcoded 18 that later commits on the same branch left behind as producers
were added, which also made the arithmetic derived from it wrong by three. That is the reason the
numbers above are now stated as the output of a command rather than as a figure to trust.

The six that pass `label:` are accessibility-compliance-weekly, e2e-prod, e2e-real-nightly,
e2e-staging, usersim and webkit-kid, all of them `e2e-alert`, consistent with "Six workflows use
`e2e-alert`" below. Confirm per call site rather than per file if you need to be exact: a workflow
may hold several `uses: ./.github/actions/ci-failure-issue` steps, and the file-level greps above
count files. `tests/unit/test_ci_failure_action_contract.py`
enforces the invariants the commands above only report on: markers stay unique and mutually
non-prefixing, both labels stay in use, and no workflow re-inlines the lookup.

Six workflows use `e2e-alert` (verify with `grep -rl 'label: e2e-alert' .github/workflows/`). The
two E2E tiers exercising a real backend are:

- **`.github/workflows/e2e-prod.yml`** ("E2E (production)"): runs the Playwright `e2e-prod` tier
  daily (`30 13 * * *` UTC) against the live production URL (`https://cyo.williamshome.family` by
  default), signing in through the real login form with a dedicated test account and exercising a
  real device-grant mint/revoke. Its alert marker is `[e2e-prod]`.
- **`.github/workflows/e2e-real-nightly.yml`** ("E2E (real backend, nightly)"): runs nightly
  (`30 9 * * *` UTC) against a freshly seeded, real (non-mocked) backend spun up in CI (Postgres 16
  and Redis service containers, Supabase CLI migrations, a seeded dev dataset), rather than against
  live production; this is what exercises real cross-device conflict scenarios (two authorized
  devices racing a genuine 409 through the offline conflict dialog) that the mocked test suite
  cannot. Its alert marker is `[e2e-real-nightly]`. This job also runs the `usersim-real` tier
  (task B3a), the same seeded walk as `usersim.yml` below but against this job's real stack; a
  failure there surfaces under this same marker, not a separate one.

**`.github/workflows/e2e-staging.yml`** ("E2E (staging)") runs daily (`0 13 * * *` UTC) against the
staging deployment. Its alert marker is `[e2e-staging]`. This alerting is recent and, as of this
writing, branch-local: commit `8c7dd27a` ("feat(ci): give e2e-staging.yml self-alerting via
ci-failure-issue", 2026-08-27) added it on `fix/testing-ladder-trust`, and that commit is **not on
`origin/main`**. An earlier version of this section correctly said the workflow had no alerting step
at all; that wording was written in commit `15a6d520` (2026-08-11) and was true when written, it only
went stale once `8c7dd27a` landed on this branch, not before. No test currently enforces that this
step keeps existing: `tests/unit/test_ci_failure_action_contract.py` asserts invariants (marker
uniqueness, label usage, no re-inlined lookup) over whichever call sites are CURRENTLY present in the
workflow files; deleting a call site removes it from that enumeration rather than failing it, and
that suite still passes 28/28 with both of this workflow's `ci-failure-issue` steps truncated out.
Do not read this paragraph as a guarantee the tests do not make; if that guarantee is wanted, adding
it is a separate decision. For the wider test strategy see
[`docs/testing/`](../testing/README.md); for a manual, checklist-driven live verification (not
automated alerting), see [`docs/planning/r1-live-e2e-checklist.md`](../planning/r1-live-e2e-checklist.md).

**`.github/workflows/usersim.yml`** ("Usersim walk") runs the mocked-tier `usersim` Playwright
project daily (`0 14 * * *` UTC): a seeded random walk over the built app, one walk per persona,
asserting I1-I6 at every state. Its alert marker is `[usersim]`. See
`docs/testing/coverage-matrix.md`'s "Cross-cutting: user-simulation walk (usersim tier)" section for
what I1-I6 check.

**`.github/workflows/webkit-kid.yml`** ("WebKit kid-journey check") runs daily (`0 15 * * *` UTC): the
kid reading/library/offline mocked specs on real WebKit at an iPad viewport (task B2), nightly-only
and never wired into any per-PR job. Its alert marker is `[webkit-kid]`.

The sixth `e2e-alert` producer is **`.github/workflows/accessibility-compliance-weekly.yml`**
("Accessibility Compliance Weekly"): a weekly, non-blocking axe scan against `main` covering WCAG
2.2 and best-practice rules, per [ADR-029](../planning/adr/adr-029-web-accessibility-conformance.md).
The per-PR WCAG 2.1 AA gate is a required `ci.yml` job instead, so a failure here is a compliance
finding to triage, never a merge blocker. Its alert marker is `[a11y-weekly]`.

This one job runs two independent Playwright scans (task B3b), and its single filed/commented issue
labels their findings distinctly so triage does not have to guess which scan produced what:

- **Stream 1, fixed-state**: `frontend/e2e/a11y.spec.ts`, the same hand-picked list of pages/dialogs
  the per-PR gate checks, re-run with the wider WCAG 2.2 + best-practice tag scope.
- **Stream 2, newly-reached-state (I7)**: `frontend/e2e-usersim/walk-a11y.spec.ts`, an axe scan of
  each distinct route+heading state the usersim seeded random walk (`usersim.yml`, described above)
  reaches for the first time. See `docs/testing/coverage-matrix.md`'s "Cross-cutting:
  user-simulation walk" section for what a "state" means here and what it collapses. Its findings
  carry `workflow: 'usersim-a11y-weekly'`, printed as `[usersim-finding]` lines in this step's own
  job log (`frontend/e2e-usersim/support/findings.ts`'s `record()` prints at the moment a finding is
  captured; there is no findings file on disk anywhere in this repository, despite what an earlier
  version of this paragraph and the filed issue's own body used to say -- grep the run's log for
  that marker), which is what tells them apart from the nightly walks' own I1-I6 findings
  (`workflow: 'usersim-walk'`/`'usersim-walk-real'`,
  produced by `usersim.yml`/`e2e-real-nightly.yml`, not accessibility findings at all). Checking
  only one of these two streams, or only one workflow's `[usersim-finding]` lines, is not checking
  the whole system: a clean nightly usersim run says nothing about whether this week's newly-reached
  states are accessible, and a clean weekly a11y run says nothing about I1-I6 (console errors,
  dead-end states, overflow, role isolation).

### 7.1 KWS parent-verification delivery health

**`.github/workflows/kws-delivery-health.yml`** ("KWS delivery health", marker `[kws-delivery-health]`,
label `ci-failure`) runs every 6 hours (05:00, 11:00, 17:00, 23:00 UTC) against both staging and
production. It is worth calling out separately because of what it watches and why nothing else can.

On 2026-08-09 a Cloudflare custom rule blocked four KWS webhook retries at the edge. The origin
logged zero POSTs, so every log-derived view of that outage read exactly like "the vendor never sent
anything": no line to alert on, and no absence a log rule could name. The only trace it left was
`kws_verification` rows that never moved off `sent`. The alarm is therefore a query over that table,
surfaced as the non-gating `kws_verification` check on `/api/v1/health/ready`, and this workflow just
reads that endpoint. It holds no database credential of its own.

A stuck count alone would be useless, because a parent who never opens their email leaves a `sent`
row forever. The check compares two timestamps instead: it fires when **nothing has resolved since
the most recent attempt that is still waiting** (once that attempt is older than 24h, so a parent
still reading their inbox is not mistaken for an outage). A resolution counts whether the
verification succeeded or was refused, since either one proves deliveries are arriving.

**Expected detection latency is up to about 30 hours**, and knowing that matters when you are dating
an outage from the alarm. It is the 24h staleness threshold, which is how long an attempt must sit
before it counts as waiting at all, plus up to 6 hours until the next probe reads the endpoint. So
the alarm is never evidence that the outage started recently; read the `requested_at` spread for
that, not the time the issue was filed.

Two properties of that rule are worth knowing before you read an alarm:

- The anchor is the **newest** waiting attempt, not the oldest. One attempt abandoned months ago
  stays the oldest forever, so anchoring on it would let every resolution since then vouch for the
  leg and a fresh outage would never surface.
- A lone abandoned attempt on a tier with no other traffic **does** keep alarming, and that is the
  accepted cost. On the evidence available it is indistinguishable from a broken leg. The remedy is
  to resolve the row, not to widen the rule; the previous rule bought silence here by also requiring
  fresh sends, which made it quietest on exactly the low-traffic tiers where an outage is hardest to
  notice by other means.
- An attempt whose **outbound** send failed resolves to `send_failed` and is neither a waiting
  attempt nor a resolution. It is not waiting, because no email went out and nothing is coming back
  for it; and it is not a resolution, because only our own timeout handler ran, so counting it would
  let a broken return path look healthy. The consequence to know: this check watches the **inbound**
  leg only. A tier where every send fails outright has no waiting attempts at all and so reports
  `ok` here, while every guardian gets a 400 from `POST /api/v1/consent/kws/start`. That outage is
  loud in the application logs and in the guardian's face; this check is not the instrument for it.

Triage, in order, when the marker issue appears with a `degraded` state:

1. **Check the edge before the origin.** An edge block leaves zero origin log lines, so an empty
   application log is evidence of nothing. Read Cloudflare's Security Events for the webhook path.
2. Check the KWS status page and vendor console for a sending-side outage. `send_failed` rows date
   any outbound trouble independently; a burst of them alongside stuck `sent` rows points at the
   vendor rather than at our webhook path.
3. Read the `requested_at` spread of the rows still in `sent`; it dates the start of the outage.
4. If the error says **nothing has ever resolved**, suspect wiring rather than an outage: a webhook
   URL that was never reachable from the vendor's side produces exactly this, and it has no start
   date because there was never a working state to leave.
5. If the rows still in `sent` are all months old and the leg is otherwise fine, this is the
   abandonment case above. Resolve them rather than muting the check.

An `unknown` state means the check ran but its aggregate query did not return, so the delivery signal
was not measured. It is a failure, because a monitor that cannot see is not a monitor, but it is
deliberately not `degraded` and triage goes somewhere else entirely: **start at the database**, not at
KWS. Check that the backend can reach Postgres at all (the `database` check in the same readiness
response will usually be failing too), then the app role's privileges on `kws_verification`. The
distinction is worth keeping sharp in both directions. `degraded` is a specific claim, attempts were
sent and stopped coming back, and it justifies paging someone toward the vendor and the webhook route.
Reporting an unmeasured probe with that same wording sends that person hunting an outage that may not
exist, and it spends the alarm: once this check has cried "deliveries stopped" for a broken query, a
real stoppage reads as more of the same noise.

A `missing` state means the deployed build carries no `kws_verification` check at all, so nothing is
watching that tier. That is reported as a failure on purpose: a probe that treats an absent key as
benign is how a monitoring gap ships unnoticed. Production has a dated exception, `PROD_MISSING_GRACE_UNTIL`
in the workflow: until that date a `missing` production check is a notice rather than a failure,
because production still runs a build from before the check existed and a daily marker issue for a
known gap only teaches people to ignore the marker. The state is still recorded and still appears in
the alert table, and the grace expires by itself rather than needing anyone to flip it back. Redeploying
production before that date is what actually closes it.

The two probe legs deliberately name different GitHub environments: `staging` (which holds
`E2E_STAGING_BASE_URL`) and `production-e2e` (which holds nothing this workflow needs). The
production leg must NOT name the `production` environment: its required-reviewer rule parks a
scheduled run in `waiting` indefinitely instead of failing, so the alert job's `if: failure()` never
fires and the whole alarm goes quiet. `e2e-prod.yml` hit this first and is why `production-e2e`
exists. An `unconfigured` state is not a failure; it means
`KWS_VERIFICATION_REQUIRED` is off on that tier, which is production's state until Gate 3 closes.

`KWS_VERIFICATION_REQUIRED` also gates `POST /v1/consent/kws/start` itself, not just the
child-profile checks. That endpoint hands an adult's email address to Epic, so credential presence
is deliberately not what opens it: a tier holding credentials without having decided to run
verification sends nothing. The one exception is `KWS_ALLOW_START_WHILE_NOT_REQUIRED`, which exists
so staging can exercise the endpoint and its screens before the gate flips. It is refused at
startup whenever `KWS_ENVIRONMENT=production`, so the process fails to boot rather than re-opening
the endpoint on a tier serving real families. The Gate 1 procedure in
[the KWS test runbook](kws-test-runbook.md) does not need it: that script calls the service
directly and never reaches the endpoint.

### 7.2 Release pipeline deadlock (a green workflow that has stopped releasing)

`release.yml` is two jobs with two triggers. `propose` runs on a daily schedule (01:00 UTC) and
opens one auto-merging `release/vX.Y.Z` PR covering every commit since the last tag. `publish` runs
on push and tags the `chore(release):` commit once that PR merges. Between them, release state lives
in **two** places: the version in `pyproject.toml` and the git tag.

If `publish` fails after its PR has merged, those two desynchronise and the pipeline **deadlocks**.
python-semantic-release computes the next version from the last **tag**, so it keeps returning the
version `pyproject.toml` already carries; `propose`'s `NEXT == CURRENT` gate reports
`No release-worthy commits ...; nothing to do` and the run exits **success**. With
`major_on_zero = false` no commit of any type can compute past that version, so the stall is
permanent, and because the steady-state message is indistinguishable from a genuinely quiet day,
nothing alerts.

This has happened once: on 2026-08-17 `gh release create v0.82.0` hit a transient
`HTTP 503: No server is currently available to service your request` and never created the tag.
Seven days and twenty-three commits passed before anyone noticed the release PRs had stopped.

**Detection.** `propose`'s "Check release state is in sync" step
(`scripts/check_release_tag_sync.py`) now fails the run on exactly this condition, so a repeat
surfaces on the next scheduled run rather than a week later. To check by hand:

```bash
VERSION="$(grep -m1 -Po '^version = "\K[^"]+' pyproject.toml)"
git ls-remote --tags origin "v${VERSION}"   # empty output means DEADLOCKED
```

**Fix.** Create the missing release on the `chore(release):` commit; the next scheduled `propose`
then computes the following version normally. Prefer re-running the job that failed, so the real
code path (including the changelog extraction) is what executes:

```bash
gh run list --workflow=release.yml --limit 20   # find the failed run
gh run rerun <run-id> --failed
gh release view "v$(grep -m1 -Po '^version = "\K[^"]+' pyproject.toml)"   # confirm
```

Verify the unblock without side effects by dispatching a dry run, which computes the plan and skips
only the PR-creation step:

```bash
gh workflow run release.yml --ref main -f dry_run=true
# expect a version AHEAD of pyproject's, e.g. "Next version: v0.83.0 (current v0.82.0)".
# A "nothing to do" here means the deadlock is NOT cleared.
```

**Note the deploy is not gated on any of this.** The homelab stack force-pulls `:latest` on its own
timer (section 1), so production ships the code whether or not the release was cut. A deadlock costs
you tags and changelog history, not delivery, which is part of why it stayed invisible.

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
- `ANTHROPIC_API_KEY`: direct Anthropic generation leg. Backend and worker (see the note below).
- `OPENROUTER_API_KEY`: OpenRouter generation legs (primary + fallback). Backend and worker.
  Since the Ollama retirement, staging generation also runs on this path against a cheap pinned
  model (`.env.staging.example`) rather than the free local leg it used before, so staging now
  needs its own key: use a staging-scoped key with its own spend limit, never the production key.
  #CRITICAL: payment/financial: a staging key without a spend limit turns a runaway staging
  generation loop into a real, unbounded bill; the per-family monthly story quota (ADR-015 G7)
  is the backstop, so keep it low on staging.
- `MODAL_BASE_URL` / `MODAL_MODEL` / `MODAL_PROXY_KEY` / `MODAL_PROXY_SECRET`: the Modal
  generation leg. Since the Ollama retirement this is also the cascade's third leg, so setting
  `MODAL_BASE_URL` and `MODAL_MODEL` is what keeps failover spanning two vendors rather than two
  OpenRouter legs on one account. Backend and worker.
- `GEMINI_API_KEY`: cover-art generation (nano banana). Backend and worker.
- `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` /
  `R2_PUBLIC_BASE_URL`: Cloudflare R2 object storage for optimized cover images. Backend and
  worker.
- `CYO_ADVENTURE_WORKER_DATABASE_URL` (`WORKER_DATABASE_URL` alias): the queue path's own
  connection string, connecting as `cyo_worker` rather than `cyo_api` (ADR-021, Section 11).
  Optional; falls back to `CYO_ADVENTURE_DATABASE_URL` when unset. **Set on the worker only, and
  deliberately left unset on the API**, because `core/database.py` builds both engines in every
  process: an API container that has this variable set holds the `cyo_worker` credential in memory
  without ever using it, which narrows the blast-radius separation the split exists to create.
- `OPENAI_API_KEY`: Stage-0 moderation classifier (OpenAI Moderation API). Backend and worker.
- `PERSPECTIVE_API_KEY`: **inert once `feat/moderation-review-hardening` merges.** Was the Stage-0
  moderation classifier credential (Google Perspective API); Perspective's outbound call leg is
  retired (`moderation/classifiers.py`, ahead of Google's 2026-12-31 sunset;
  [moderation-review-redesign-2026-07-28.md](../planning/safety/moderation-review-redesign-2026-07-28.md)
  section 3.2 item 5), so no code path in the deployed app reads this value anymore.
  `core/config.py::perspective_api_key` keeps the field solely so an existing deployment's
  environment does not fail to parse at boot; nothing consumes it. This describes the CODE, not any
  specific environment's current secrets: removing the key from a deployed environment is safe once
  confirmed, but should be sequenced deliberately rather than assumed already done. Tracked:
  `UW-B03` (`GS3`, Perspective's 2026-12-31 sunset).
- `CYO_ADVENTURE_REVIEW_PROVIDER`: independent-review backend selector
  (`mock`/`openrouter`/`modal`, though `modal` is still deferred to slice 2b); must differ from
  the generation provider. Backend and worker.
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

The generation, cover-art, and object-storage credentials above read "Backend and worker" rather
than "Worker only" because the backend builds those clients in-request, not only in queued jobs.
`POST /api/v1/admin/remoderate/{storybook_id}/{version}` constructs a generation provider inside
the request (`api/remoderate.py` via `generation/provider.py`), the node-edit rescreen path
constructs a review provider the same way (`api/node_edit.py`), and three routers presign cover
URLs through `covers/storage.py` (`api/covers.py`, `api/library.py`, `api/recommendations.py`).
This matters when scoping which credentials are resident in which container: attributing them to
the worker alone understates the API container's exposure. `docs/operations/runtime-config.md`
records the same fact per setting, and traces each call site.

**Re-moderation sweep** (`scripts/remoderate_books.py`): calls `remoderate_storybook_version()`
(`api/remoderate.py`), the same function `POST /api/v1/admin/remoderate/{storybook_id}/{version}`
above wraps, directly in-process over a batch of books instead of one. This is a direct service
call, not an HTTP request to the endpoint: it runs under the invoking process's own database
credentials rather than an admin bearer token, stamps `Actor.system()` instead of the calling
admin's identity, and does not exercise the endpoint's own authentication or middleware layers. A
clean sweep run is not evidence the HTTP endpoint itself is healthy, and vice versa. Dry-run is the
default; it only lists targets and writes nothing. Pass `--execute` to actually run the sweep
against each target. Three mutually exclusive selectors:

- `--mock-moderated`: published books whose stored report carries the mock-reviewer stamp or a
  fail-safe-degraded marker. Use this to backfill published legacy artifacts, for example the
  catalog remediation sweep in
  [moderation-review-redesign-2026-07-28.md](../planning/safety/moderation-review-redesign-2026-07-28.md)
  section 6, Stage D.
- `--in-review`: every book sitting at the human review gate, at its latest version, with no
  content filter. Use this to clear a stuck review queue, for example books left with a fail-safe
  or mock-moderated report before this branch's approval gate started blocking them.
- `--book-id STORYBOOK_ID` (repeatable): specific storybooks, for a one-off re-run, a curated
  subset, or a single-book canary before a full sweep.

**Never run a sweep before the floor or classifier change it exists to backfill has been deployed
to that environment.** `_persist_report()` (`moderation/pipeline.py`) is the single end-of-pipeline
write per version and moderation reports are effectively write-once per run: sweeping ahead of the
deploy re-derives the same stale verdicts under the old rules, burns the LLM budget, and leaves no
cheap way to fix it besides sweeping the same books again after the deploy actually lands.

Post-sweep verification: prefer running the shared health predicate itself rather than
re-implementing it in SQL:

```bash
CYO_ADVENTURE_DATABASE_URL=... uv run python scripts/check_moderation_report_health.py
```

Exit 0 with no printed hits means no current published or in-review version anywhere in the catalog
has a report `moderation/report.py::moderation_report_unusable` would flag (absent, malformed,
non-independent/mock, or containing only pipeline artifacts): the same predicate
`publishing/service.py::approve()` enforces at approval time. This checks the whole catalog, not
only the books the sweep targeted, which is a stronger guarantee than scoping to the sweep would be.

The narrower ad hoc SQL below (read-only, via the Supabase MCP or psql) checks ONLY for the literal
`FAIL_SAFE_MESSAGE_SUBSTRING` string inside `findings`; it does not detect an absent report, a
non-list `findings` value, a non-independent (mock) reviewer, or a structural/mock-moderated-concern
artifact carrying a different message. Treat it as a quick, narrower diagnostic for the
fail-safe-specific case only, never as proof that `report_unusable` is false: run the script above
for that.

```sql
select count(*)
from storybook s
join storybook_version sv
  on sv.storybook_id = s.storybook_id
 and sv.version = (
   select max(v2.version) from storybook_version v2 where v2.storybook_id = s.storybook_id
 )
where s.status = 'in_review'
  and exists (
    select 1
    from jsonb_array_elements(sv.moderation_report -> 'findings') as f
    where f ->> 'message' like '%defaulted to fail-safe%'
  );
```

Expected: `0`, understood only as "no remaining `FAIL_SAFE_MESSAGE_SUBSTRING` hits," not as full
proof of health; run `scripts/check_moderation_report_health.py` above for that. If any remain,
re-run the dry-run selector for the stragglers and diagnose per book (the count is the same
substring `moderation/report.py::FAIL_SAFE_MESSAGE_SUBSTRING` checks at read time to set
`report_unusable`, so a nonzero count here is the same condition the admin queue badge shows as
"Moderation unavailable").

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

### 11.2 Verifying the cutover actually happened

Do not read a `.env*` file or a compose file to answer "which role is this environment on";
those are the operator's local copy and the deployment's template, neither of which is the
running process. Two sources are authoritative:

- `/api/v1/health/ready` reports a `database_privilege` check (`api/health.py`). `state: "ok"` means
  the connected role cannot bypass RLS (cut over); `state: "degraded"` means it can (not cut
  over). The check is deliberately non-gating, so a pre-cutover environment stays HTTP 200,
  and it deliberately omits the role name because the endpoint is unauthenticated.
- `SELECT usename, count(*) FROM pg_stat_activity WHERE datname = 'postgres' GROUP BY 1;`
  against the target project shows which roles actually hold connections.

The worker reports itself separately, because `CYO_ADVENTURE_WORKER_DATABASE_URL` silently falls
back to `CYO_ADVENTURE_DATABASE_URL` when unset (`core/config.py::worker_database_url_effective`),
so a forgotten worker variable is indistinguishable from a completed cutover by inspection.
`generation/worker_main.py` runs the same role probe against the **worker** engine once per
process start and logs the verdict:

| Log event | Level | Meaning |
| --- | --- | --- |
| `generation_worker.role_least_privileged` | `warning` | Cut over. `role` names the connected role; `worker_dsn_explicitly_set` says whether that happened by configuration or by fallback. |
| `generation_worker.role_bypasses_rls` | `warning` | Not cut over. `via_role_attribute` and `via_table_ownership` say which path, and are fixed differently. |
| `generation_worker.rls_posture_unknown` | `warning` | The probe itself failed; posture unmeasured, not clean. |

All three are WARNING-level, not INFO, because production runs `LOG_LEVEL=WARNING` and an INFO
posture line is filtered out before it is written. That is the same rule
[the security event catalog](security-events.md) applies to every security event, for the same
reason. Do not "quiet down" the affirmative line to INFO: doing so turns a successful cutover
back into silence and makes it indistinguishable from a worker running an image with no probe.

**Alert on either of these, not just the bypass event:**

```text
event == "generation_worker.role_bypasses_rls"
  OR (event == "generation_worker.role_least_privileged"
      AND worker_dsn_explicitly_set == false)
```

The second clause is not redundant. When `CYO_ADVENTURE_WORKER_DATABASE_URL` is unset the worker
falls back to the API DSN and connects as `cyo_api`, which has `rolbypassrls = false` and owns no
Tier 1 table. The probe therefore emits the **affirmative** event, so an alert keyed only on
`role_bypasses_rls` reports green for a worker that is still sharing the API credential. Alerting
on `role != "cyo_worker"` works equally well and is easier to express in some backends.

Treat a deploy that emits no posture line at all as running an image older than PR #608.

None of these gate startup: the worker starts on all three outcomes, by design, because a
pre-cutover worker is a security finding while a worker that refuses to start is an outage. That
property depends on the probe rolling its transaction back when it fails. The probe and the
stranded-job reclaim sweep share one transaction and the probe runs first, so a probe that failed
without rolling back would leave the sweep unable to issue any statement (PostgreSQL SQLSTATE
25P02) and, under `restart_policy: on-failure`, put the worker in an uncapped crash loop. If you
ever see `rls_posture_unknown` followed by a worker that will not stay up, that is the regression
to look for; it is pinned by
`tests/integration/test_worker_role_posture.py::test_statement_error_in_probe_still_lets_the_sweep_run`.

The verdict is emitted once at startup, so restart the worker after changing its DSN rather than
waiting for the next job. To confirm from the database side instead, check that a `cyo_worker`
connection appears in `pg_stat_activity` while a real generation job runs.

### 11.3 Operator scripts must not run as `cyo_api`

These entry points read or write the ADR-022 Tier 1 tables (`child_profile`, `story_request`,
`device_grant`) outside the request path, where nothing sets the `app.family_id` GUC:

**Seed and local-harness scripts:** `scripts/seed_dev_data.py`, `scripts/seed_staging.py`,
`scripts/seed_moderation_qa.py`, `scripts/seed_series_catalog.py`,
`scripts/seed_catalog_validation_states.py`, `scripts/series_e2e_local.py`.

**Import CLIs:** `src/cyo_adventure/generation/import_cli.py` and
`src/cyo_adventure/generation/import_catalog.py`. Both reach `import_filled_story()`, which reads
`child_profile.display_name` for the family to build the moderation pass's `PiiContext`. These are
the one exception to the owner-DSN rule below: `import_filled_story()` sets the family RLS context
itself before that read (`apply_family_rls_context`, transaction-scoped), so it is correct under
`cyo_api`. Any new code path added to these CLIs that touches a Tier 1 table must do the same.

**Local-only reset:** `scripts/reset_e2e_real_state.py` deletes `story_request` rows by family.
It self-guards with `_require_local_database()` and refuses any non-local host, so it cannot hit a
deployed database, but it belongs on this list.

This list is accurate as of PR #597 and is not self-maintaining. Before adding any new
non-request-path entry point that touches a Tier 1 table, add it here.

Run these with the **owner** (`postgres`) DSN, never the `cyo_api` DSN. Under `cyo_api` with no
RLS context the Tier 1 predicate is unsatisfiable, so reads return zero rows and inserts are
rejected by `WITH CHECK`. The read failure is silent: the script sees an empty result and
reports "nothing to do" rather than an error. This is the same fail-closed-looks-like-empty
failure mode that hid the device-grant defect in staging for two weeks (PR #560).

The import CLIs carried a sharper version of that failure mode, which is why
`import_filled_story()` now sets the context itself: an empty `child_profile` read does not stop
the import, it produces an empty `child_names` set, so the moderation pass runs with no PII
context and cannot recognize a real child's name in the generated prose. The import still reports
success. That is fail-closed at the database becoming fail-open at the safety gate, and it is the
shape to look for in any future non-request-path caller.

### 11.4 Future-table checklist

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
