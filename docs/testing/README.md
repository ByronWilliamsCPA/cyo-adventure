# Frontend Testing Strategy

This directory documents the frontend test tiers, the environments they run
against, and how to find what's covered where. Backend (pytest) testing
strategy lives separately in `docs/development/testing.md`.

## Test layers

| Layer | Tool | Location | Backend |
|---|---|---|---|
| Unit / Component | Vitest + Testing Library | `frontend/src/**/*.test.{ts,tsx}` | none, mocked at the module boundary |
| E2E (mocked) | Playwright, `chromium` project | `frontend/e2e/` | none, API responses mocked via route interception |
| E2E (real-backend) | Playwright, `real-backend` project | `frontend/e2e-real/` | local Postgres + local uvicorn, via local Supabase CLI |
| E2E (staging) | Playwright | `frontend/e2e-staging/` (planned, not yet created) | shared staging Supabase project |
| E2E (production smoke) | Playwright, separate config | `frontend/e2e-prod/` | live production, run manually or on a schedule with synthetic accounts only |

See [`coverage-matrix.md`](coverage-matrix.md) for the full journey-by-layer
breakdown and current known gaps.

## Environment model

Given the Supabase free-tier limit of two active projects, `dev` and
`staging` frontend deployments share a single staging Supabase project
rather than each getting a dedicated backend:

| Environment | Frontend | Supabase backend | Purpose |
|---|---|---|---|
| local | localhost | local Supabase CLI (Docker) | dev loop; unit/component, E2E-mocked, E2E-real |
| dev | `dev.` subdomain (planned) | staging project (shared) | integration smoke-testing before staging promotion |
| staging | staging URL | staging project (shared) | pre-production gate, migration validation |
| production | production URL | production project | live |

### Data isolation on the shared staging project

Because `dev` and `staging` share one Postgres instance, isolation is
data-layer, not infra-layer:

- All synthetic E2E accounts/families use a reserved naming convention
  (e.g. `e2e-*` prefixed emails) so they're identifiable and cleanable, and
  never collide with real guardian accounts.
- `dev`-tier and `staging`-tier E2E workflows run under a shared CI
  `concurrency:` group so they never write to the shared project at the
  same time.
- A scheduled cleanup job removes synthetic rows older than a threshold so
  failed runs don't leave permanent cruft.

`#CRITICAL: concurrency: dev and staging e2e suites writing to the same
Supabase project can race or corrupt each other's fixtures. #VERIFY: enforce
the CI concurrency group and naming convention described above before
enabling automated dev/staging E2E runs.`

## Maintaining coverage documentation

Add or update the relevant section in `coverage-matrix.md` in the same PR
that adds a new page, journey, or test file. Don't let this document become
stale, it is the primary tool for spotting untested journeys before they
reach staging or production.
