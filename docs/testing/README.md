---
title: "Frontend Testing Strategy"
schema_type: common
status: published
owner: core-maintainer
purpose: "Frontend test tiers, the environments they run against, and where each type of coverage lives."
tags:
  - testing
  - documentation
---

This directory documents the frontend test tiers, the environments they run
against, and how to find what's covered where. Backend (pytest) testing
strategy lives separately in `docs/development/testing.md`.

## Test layers

| Layer | Tool | Location | Backend |
| --- | --- | --- | --- |
| Unit / Component | Vitest + Testing Library | `frontend/src/**/*.test.{ts,tsx}` | none, mocked at the module boundary |
| E2E (mocked) | Playwright, `chromium` project | `frontend/e2e/` | none, API responses mocked via route interception |
| E2E (real-backend) | Playwright, `real-backend` project | `frontend/e2e-real/` | local Postgres + local uvicorn, via local Supabase CLI |
| E2E (staging) | Playwright, scheduled + manual | `frontend/e2e-staging/` | shared staging Supabase project, targets an already-deployed staging frontend |
| E2E (production smoke) | Playwright, manual + one scheduled workflow | `frontend/e2e-prod/` | live production; CI execution is default-deny when `CI` is set (`requireProdCredentials()`), with a single audited override in `.github/workflows/e2e-prod.yml` |

See [`coverage-matrix.md`](coverage-matrix.md) for the full journey-by-layer
breakdown and current known gaps.

## Environment model

Given the Supabase free-tier limit of two active projects, a dedicated
`dev` backend is not available: any future `dev` frontend deployment would
have to share the staging Supabase project rather than get one of its own.
That `dev` tier is not built yet (it also needs a frontend deploy pipeline,
which lives outside this repo, see below); this section documents what
exists today plus the shape a `dev` addition would take.

| Environment | Frontend | Supabase backend | Purpose |
| --- | --- | --- | --- |
| local | localhost | local Supabase CLI (Docker) | dev loop; unit/component, E2E-mocked, E2E-real |
| dev (not yet built) | `dev.` subdomain (proposed) | staging project (shared) | integration smoke-testing before staging promotion |
| staging | already-deployed staging URL | staging project | pre-production gate, migration validation, E2E-staging tier |
| production | production URL | production project | live |

See `docs/planning/handoff-homelab-infra-dev-environment-2026-07-16.md` for
the concrete spec handed to the homelab-infra team to build this out.

**This repo has no frontend deploy workflow.** The frontend image is built
and shipped by a separate repository, `homelab-infra`, via a
`repository_dispatch` on merges to `main`
(`.github/workflows/trigger-image-build.yml`), decoupled from the Supabase
migration promotion in `supabase-staging.yml`. The `e2e-staging` tier
therefore targets whatever staging frontend URL is already running,
supplied via the `E2E_STAGING_BASE_URL` secret; it does not trigger or wait
on any staging deploy itself. Building an automated `dev` deployment (and
tying an E2E run to it) requires coordinating with `homelab-infra`, which is
out of scope for this repo alone.

### Data isolation on the shared staging project

The staging Supabase project holds one stable, idempotent fixture set
(`scripts/seed_staging.py`): a seeded guardian, a seeded admin, and a "Test
Reader" child profile with two published stories, not per-run synthetic
accounts. `frontend/e2e-staging/` authenticates as those two accounts
directly rather than minting new ones. Given that, the isolation concerns
are:

- **Concurrent runs must not race the same fixtures.** `.github/workflows/e2e-staging.yml`
  runs under a `concurrency:` group (`e2e-staging`, `cancel-in-progress: false`)
  so a scheduled run and a manual dispatch can never execute at the same
  time against the shared project.
- **The one write path cleans up after itself, and is checked twice.**
  `kid-library-smoke.spec.ts` (and `moderation-qa-invisibility.spec.ts`)
  mints a device grant to reach the populated library, then revokes it in
  the test itself, with an `afterAll` backstop DELETE if an earlier
  assertion failed first, mirroring the same pattern already proven in
  `frontend/e2e-prod/kid-device-grant.spec.ts`. Cleanup is not trusted on
  its own word: Playwright's serial-block retry spawns a fresh worker, so a
  failed first attempt can leak its own grant while the retry cleanly
  revokes a different one and the run still reports "flaky" and exits 0.
  Two signals close that. The **diagnostic** is a jsonl ledger
  (`test-results/leaked-device-grants.jsonl`) that names which spec left a
  grant live; the **authoritative backstop** is
  `frontend/e2e-staging-sweep/`, a separate post-run Playwright config that
  the workflow runs on `if: always()` and that asks staging itself whether
  the test family still holds an active grant. The sweep is fail-closed: a
  429, a non-2xx, or an unparseable list response fails the job rather than
  being read as "no leaks". It reports without auto-revoking, so a live
  grant keeps the job red until a human acts.
- **If a future `dev` tier is added** on this same shared staging project,
  it must join the same `concurrency:` group (or a shared one covering both
  workflows) before being enabled, and any new fixtures it creates should
  follow an identifiable naming convention (e.g. `e2e-*`-prefixed) so they
  can be told apart from the stable seeded fixtures and cleaned up
  independently.

`#CRITICAL: concurrency: any additional automated workflow that authenticates
against or mutates data on the shared staging Supabase project must join the
e2e-staging concurrency group (or an equivalent one scoped to that project)
before being enabled, or it can race e2e-staging's device-grant mint/revoke
and leave the shared fixtures in a bad state. #VERIFY: check
.github/workflows/e2e-staging.yml's concurrency: block is included whenever
a new staging-project-touching workflow is added.`

## Failure-alert label convention

Every scheduled workflow that files or updates a tracking issue on failure
(the "pinned issue" pattern used throughout `.github/workflows/`) must label
that issue with exactly one of the following two labels. Apply this without
asking when adding the pattern to a new workflow:

| Label | For |
| --- | --- |
| `e2e-alert` | Browser-journey failures: any Playwright e2e tier (`frontend/e2e-prod/`, `frontend/e2e-staging/`, `frontend/e2e-real/` when run on a schedule, and the weekly accessibility scan, which drives the same Playwright/axe stack against a real browser). |
| `ci-failure` | Everything else: pytest tiers, fuzzing, mutation testing, link checking, performance regression, database backup, notification digest, KWS delivery health, moderation report health, planning linkage, and the semantic-release pipeline. |

The dividing line is "does this failure mean a real browser journey broke",
not "does this workflow touch the frontend". `security-analysis.yml`'s
`semgrep-frontend` job lints the React tree but never drives a browser, so a
failure there is `ci-failure`; `e2e-prod.yml` drives real Chromium through a
real login form, so a failure there is `e2e-alert`.

`.github/workflows/scheduled-health-rollup.yml`'s own rollup issue carries
`ci-failure`, not `e2e-alert`: it is a meta-report over the whole scheduled
test ladder (most of which is not browser-driven), not itself a browser
journey, so it sorts with "everything else" under this convention even
though several of the workflows it surveys are `e2e-alert` workflows in
their own right.

## Maintaining coverage documentation

Add or update the relevant section in `coverage-matrix.md` in the same PR
that adds a new page, journey, or test file. Don't let this document become
stale, it is the primary tool for spotting untested journeys before they
reach staging or production.
