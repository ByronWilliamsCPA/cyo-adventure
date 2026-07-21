---
title: "Deployment"
schema_type: common
status: published
owner: core-maintainer
purpose: "Homelab-first Docker deployment architecture for CYO Adventure."
tags:
  - architecture
  - deployment
---

CYO Adventure deploys to a self-hosted homelab using Docker containers orchestrated
by Dockge (ADR-004: homelab-first deployment). External access is secured by Pangolin
zero-trust reverse proxy (Tailscale or Cloudflare Tunnel). Supabase Auth provides OIDC
identity for the guardian and admin roles (ADR-009; children authenticate via
backend-minted scoped sessions, not Supabase), and the operational database is
Supabase Postgres, reached through the session pooler (ADR-009 decision 2; R1 Task 1.7,
cut over 2026-07-05).

## Deployment Diagram

![Deployment View](diagrams/deployment.svg)

## Container Stack

| Container | Image | Purpose |
| ----------- | ------- | --------- |
| `cyo-backend` | `cyo-backend:latest` | FastAPI application (uvicorn, port 8000) |
| `cyo-worker` | `cyo-worker:latest` | RQ generation worker (long-running, no inbound HTTP) |
| `cyo-postgres` | `postgres:16-alpine` | Retained for one-redeploy rollback only; off the data path, tracked for removal in homelab-infra #577 |
| `cyo-redis` | `redis:7-alpine` | Redis 7, port 6379, RQ job broker |
| `cyo-ollama` | `ollama/ollama:latest` | Local LLM fallback, port 11434 |
| `cyo-minio` | `minio/minio` | Object storage, planned Phase 5 |

The backend and worker share the same Python codebase but run as separate containers.
Separating the worker prevents long-running LLM calls (30-120s per story) from
blocking the API event loop.

The operational database itself is **Supabase Postgres** (managed, external to the
homelab), not a container in this stack; `cyo-backend` and `cyo-worker` reach it over
the internet through Supabase's session pooler (`aws-0-us-east-1.pooler.supabase.com:5432`,
session mode). See the Network Architecture section below.

## Network Architecture

All family device traffic enters through **Pangolin**, which terminates TLS and
forwards plain HTTP to the backend container on port 8000. Pangolin runs as its own
container in the stack and handles the zero-trust tunnel to the homelab.

The R1 internal-web deploy (`services/cyo-adventure/` in the separate
`ByronWilliamsCPA/homelab-infra` repo) is a distinct rung from this ADR-004 topology:
there, nginx is the ingress point on `docker-host`, reverse-proxying `/api` to the
FastAPI container internally rather than Pangolin forwarding to it directly. See the
`frontend/nginx.conf` `location /api/` block.

Internal container-to-container communication uses Docker's bridge network:

- `cyo-backend` -> `cyo-redis` (RQ enqueue, port 6379)
- `cyo-worker` -> `cyo-redis` (job dequeue, port 6379)
- `cyo-worker` -> `cyo-ollama` (LLM fallback, port 11434)
- `cyo-worker` -> OpenRouter API (HTTPS, egress to internet, primary LLM)

Egress to the managed database (not on the Docker bridge network):

- `cyo-backend` -> Supabase Postgres (async SQLAlchemy, session pooler, port 5432,
  connects as the `cyo_api` service role, ADR-021)
- `cyo-worker` -> Supabase Postgres (job status updates, session pooler, port 5432,
  connects as the `cyo_worker` service role, ADR-021)

`cyo-postgres` is retained in the compose stack only as a one-redeploy rollback
fallback; it carries no live traffic (tracked for removal in homelab-infra #577).

## Service Accounts and Row Level Security (ADR-021)

The single shared `postgres` owner-role connection has been replaced with two
dedicated, least-privilege Postgres roles: `cyo_api` (the FastAPI web process) and
`cyo_worker` (`generation/worker.py`, `generation/worker_main.py`, `covers/worker.py`).
`core/config.py`'s `worker_database_url` defaults to `database_url` when unset, so an
environment that has not split credentials yet keeps working unchanged.

Row Level Security, enabled on every application table since
`supabase/migrations/20260711200745_enable_rls_all_tables.sql`, is now enforced by
explicit `CREATE POLICY` grants for both roles
(`supabase/migrations/20260720170100_create_service_roles.sql` and
`20260720170200_add_service_role_policies.sql`). Previously RLS was enabled with zero
policies attached, a placeholder that the RLS-enable migration's own comment warned
would start restricting queries the moment a non-owner role connected.

`docker-compose.yml` and `docker-compose.prod.yml` now also define the `worker` and
`redis` services directly in this repository (previously only defined in the separate
`homelab-infra` repo), so `docker-compose up` exercises the full story
request -> generation -> review queue pipeline locally and in CI without depending on
that sibling repo's state. `homelab-infra` remains the deployment orchestrator of
record for the live environment.

## PWA Delivery

The React 19 PWA is built as static assets and served by the backend container (or
a co-located nginx, which can also reverse-proxy `/api` when nginx is the deploy's
ingress point; see the Network Architecture note above). A Workbox service worker
(via `vite-plugin-pwa`) caches assets for offline use. IndexedDB (`offline/db.ts`)
caches reading state locally so children can continue reading without a network
connection.

## Phase 1 vs Phase 5 Storage

**Phase 1 (current):** Storybook JSON is stored inline as `JSONB` in the
`storybook_version.blob` column. No object storage is needed.

**Phase 5 (planned):** The MinIO container is added to the stack. The
`storybook_version.blob_ref` column is set to the MinIO S3 object key. The `blob`
column is kept for backward compatibility with rows written in Phase 1.

## Environment Configuration

All secrets and environment-specific values are loaded from environment variables
via `core/config.py` (Pydantic Settings). The `model_validator` in `config.py`
raises `ConfigurationError` if the localhost-only development database URL is
detected in a non-local environment, preventing accidental credential leakage.

Two backend-only signing secrets are validated at startup, not just read: a
`model_validator` raises `ConfigurationError` outside the `local` environment if
either is unset, empty, or shorter than the minimum key length.

| Env var | Purpose | Validated at startup |
| --------- | --------- | ----------------------- |
| `CHILD_SESSION_SECRET` | Signs/verifies the 12-hour, no-refresh child-session HS256 token (`core/child_session.py`) | Yes, outside `local` |
| `DEVICE_GRANT_SECRET` | Signs/verifies the 90-day, revocable device-grant HS256 token, audience `cyo-device-grant` (`core/device_grant.py`, ADR-014) | Yes, outside `local`, mirroring `CHILD_SESSION_SECRET` |

Neither secret is ever sent to the browser; both are backend-only signing keys
distinct from the Supabase JWKS used to verify guardian/admin OIDC tokens.

## Authentication Flow

**Production:** The PWA initiates an OIDC authorization code flow with Supabase Auth
(ADR-009). The resulting access token is sent as a `Bearer` header with every API
request. Outside the `local` environment the backend verifies the token signature via
`jwt.PyJWKClient` (JWKS fetched from `OIDC_JWKS_URL`), plus issuer, audience, and
expiry (`_verify_oidc_jwt` in `api/deps.py`). Supabase is reached through the
provider-agnostic `oidc_*` config, so no Supabase SDK is imported.

**Development seam:** in the `local` environment only, `api/deps.py` uses a
`_extract_subject()` stub that treats the raw bearer token as the verified OIDC
subject without signature validation. A `#CRITICAL: security` guard raises
`ConfigurationError` at import time if the environment is non-local and
`OIDC_ISSUER`/`OIDC_JWKS_URL` are unset, so the stub can never be active outside
local development.

## Container Images

Container images are pinned by tag, never `latest` in production (per `CLAUDE.md` and
ADR-004). The `cyo-backend:latest` and `cyo-worker:latest` tags above denote the local
development convention; CI produces versioned tags aligned with SemVer releases.

## Observability

- **Structured logging:** `utils/logging.py` (structlog) emits JSON logs with
  correlation IDs injected by `CorrelationMiddleware`.
- **Sentry:** error tracking (planned; configurable via `settings.sentry_dsn`).
- **Correlation IDs:** every request carries `X-Correlation-ID`; the header propagates
  into all log lines for the request lifecycle.
- **Generation-queue health (ADR-021):** `GET /health/ready`'s non-gating
  `check_generation_queue` sub-check (`api/health.py`) counts stale `queued`/`running`
  `GenerationJob` rows and recent failures, so a stopped or misbehaving worker becomes
  an observable readiness signal instead of a silent stuck queue.

## Related ADRs

- ADR-004: [Homelab-First Deployment](../planning/adr/adr-004-homelab-first-deployment.md)
- ADR-021: [Dedicated Least-Privilege Service Accounts, Enforced RLS, and In-Repo Worker Deployment](../planning/adr/adr-021-service-account-rls-and-worker-deployment.md)
- ADR-002: [Client: Progressive Web App](../planning/adr/adr-002-client-pwa.md)
- ADR-003: [Frontier LLM Story Generation](../planning/adr/adr-003-frontier-llm-generation.md)
