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
zero-trust reverse proxy (Tailscale or Cloudflare Tunnel). Authentik provides OIDC
identity for both guardian and child roles.

## Deployment Diagram

![Deployment View](diagrams/deployment.svg)

## Container Stack

| Container | Image | Purpose |
|-----------|-------|---------|
| `cyo-backend` | `cyo-backend:latest` | FastAPI application (uvicorn, port 8000) |
| `cyo-worker` | `cyo-worker:latest` | RQ generation worker (long-running, no inbound HTTP) |
| `cyo-postgres` | `postgres:16-alpine` | PostgreSQL 16, port 5432 |
| `cyo-redis` | `redis:7-alpine` | Redis 7, port 6379, RQ job broker |
| `cyo-ollama` | `ollama/ollama:latest` | Local LLM fallback, port 11434 |
| `cyo-minio` | `minio/minio` | Object storage, planned Phase 5 |

The backend and worker share the same Python codebase but run as separate containers.
Separating the worker prevents long-running LLM calls (30-120s per story) from
blocking the API event loop.

## Network Architecture

All family device traffic enters through **Pangolin**, which terminates TLS and
forwards plain HTTP to the backend container on port 8000. Pangolin runs as its own
container in the stack and handles the zero-trust tunnel to the homelab.

Internal container-to-container communication uses Docker's bridge network:

- `cyo-backend` -> `cyo-postgres` (async SQLAlchemy, port 5432)
- `cyo-backend` -> `cyo-redis` (RQ enqueue, port 6379)
- `cyo-worker` -> `cyo-postgres` (job status updates, port 5432)
- `cyo-worker` -> `cyo-redis` (job dequeue, port 6379)
- `cyo-worker` -> `cyo-ollama` (LLM fallback, port 11434)
- `cyo-worker` -> OpenRouter API (HTTPS, egress to internet, primary LLM)

## PWA Delivery

The React 19 PWA is built as static assets and served by the backend container (or
a co-located nginx). A Workbox service worker (via `vite-plugin-pwa`) caches assets
for offline use. IndexedDB (`offline/db.ts`) caches reading state locally so children
can continue reading without a network connection.

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

## Authentication Flow

**Production:** The PWA initiates an OIDC authorization code flow with Authentik.
The resulting access token is sent as a `Bearer` header with every API request. The
backend validates the token signature, issuer, audience, and expiry against Authentik.

**Development seam:** `api/deps.py` uses a `_extract_subject()` stub that treats
the raw bearer token as the verified OIDC subject without signature validation.
This stub must be replaced with real JWT validation before any non-local deployment
(`#CRITICAL: security` marker in `deps.py`).

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

## Related ADRs

- ADR-004: [Homelab-First Deployment](../planning/adr/adr-004-homelab-first-deployment.md)
- ADR-002: [Client: Progressive Web App](../planning/adr/adr-002-client-pwa.md)
- ADR-003: [Frontier LLM Story Generation](../planning/adr/adr-003-frontier-llm-generation.md)
