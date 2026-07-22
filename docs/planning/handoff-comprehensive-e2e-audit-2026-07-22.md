---
purpose: Comprehensive cross-environment e2e audit (local/dev/staging/prod) to find
  gaps blocking real user testing, with prioritized remediation.
component: testing
source: session 2026-07-22, branch test/comprehensive-e2e-audit
---

# Comprehensive E2E Audit, all environments, 2026-07-22

**Goal:** run every available Playwright tier across local, dev, staging, and prod,
find the gaps that would make a real tester "hit a new error on each page," and
classify each finding as a product defect vs a deployment/env issue vs test-harness
debt.

## Readiness verdict

The application is in **good functional health**. The 130-spec mocked behavioral
suite is fully green, dev and prod public surfaces are clean, and with the local DB
at schema head the core real-backend journeys (kid-read, series-continue, ratings)
work end to end. There is **one genuine product defect** (offline multi-device
resync), **one broad unknown to verify** (the prod parental-consent gate), and one
deployment blocker on **staging only** (a stale backend image). Everything else is
test-harness or local-env hygiene, not user-facing.

## Results by environment

| Environment | Tier / method | Result | Interpretation |
| --- | --- | --- | --- |
| **local** | mocked (`test:e2e`) | 130 pass / 18 fail | All 18 fails are `visual.spec.ts` pixel-diff (0.01-0.07) from host-vs-CI font rendering. **Zero behavioral failures.** |
| **local** | real-backend (`test:e2e:real`) | 8 pass / 7 fail / 5 skip | 1 real defect (offline resync), 6 test/state artifacts. Required migrating local DB to head first. |
| **dev** (`cyo-dev.williamshome.family`) | manual browser smoke | healthy | Landing, `/guardian`->login, `/kids`->device-gate all render, 0 console errors. Auth depth untested (shares staging Supabase; no creds). |
| **staging** (`cyo-staging.williamshome.family`) | CI `e2e-staging.yml` | 4 pass / 2 fail | Passwords fine (admin console signed in + passed). 2 fails = stale-image gate on guardian surface. |
| **prod** (`cyo.williamshome.family`) | prod tier (`test:e2e:prod`) | 2 pass / 2 fail / 10 skip | Public surfaces green. Auth surfaces blocked: test account parked at live parental-consent gate. |

## Prioritized gaps

### P0-1 (product defect): offline multi-device resync save fails with 422

- **Where:** `frontend/src/offline/sync.ts`.
- **Symptom:** a reader who resumes a story on a second device and saves a second
  time gets a silent save failure (backend `422 extra_forbidden`).
- **Cause:** the sync client caches the server `ReadingStateView` verbatim
  (`putReadingState(res.row / serverRow)`), then the next save builds `body = {...state}`,
  echoing View-only fields the strict PUT body forbids: `child_profile_id`,
  `storybook_id`, `updated_by_device_id`, `last_synced_at`.
- **Why it was invisible:** the mocked tier does not enforce `extra=forbid`, so the
  130-spec suite never caught it; it only reproduces against the real backend on the
  *second* cross-device save. Caught by `offline-conflict-real.spec.ts:157`.
- **Fix:** strip View-only fields before PUT (whitelist the engine-owned state fields).
- **User impact:** narrow but real, offline reading across two devices.

### P0-2 (RESOLVED): prod parental-consent gate is passable

- Every real guardian's first screen after login is the COPPA/GDPR consent gate
  ("Before you get started", legal name + consent checkbox, "Agree and continue"
  disabled until filled). Intended PR #311 feature, live in prod.
- **Verified 2026-07-22 via a real prod login** (E2E test account): the gate gates the
  guardian *action* routes (e.g. `/guardian/intake` redirects to `/guardian/consent`)
  while `/guardian` console home renders. Filling legal name + checkbox enables the
  button; submitting redirects back to the console and **unblocks all action pages**.
- Post-consent walkthrough, all clean (0 console errors): `/guardian` (Family console),
  `/guardian/intake` (functional request form, "10 of 10 stories left"),
  `/guardian/profiles` (E2E Test Kid), `/admin` (review queue loads ~26 books).
- **Conclusion:** the gate is a passable first-login step, not a wall. A real guardian
  will not be blocked. This also completed consent on the E2E account, which unblocks
  future automated prod-tier runs (they were only stuck because consent was pending).

### P1 (deployment): staging backend image is stale

- Staging's deployed backend predates PR #311, so `POST /v1/onboarding` omits `status`;
  `AuthContext` reads `undefined !== 'active'` and shows a false "awaiting approval"
  gate on the **guardian** surface (admin surface is unaffected and passes).
- Fails `guardian-admin-smoke.spec.ts:34` and `kid-library-smoke.spec.ts:75`.
- **Fix:** homelab-infra rebuild + redeploy of the `:staging` backend and worker from
  current `main`. No code change. Confirms the 2026-07-21 handoff.

### P2 (test-harness debt, not user-facing)

- **Visual baselines are CI-locked:** all 18 mocked "failures" are host rendering
  drift. Regenerate baselines in CI or gate `visual.spec.ts` to CI-only so local runs
  are not noisy.
- **Real-backend tier is stateful and non-resetting:** `seed_dev_data.py` early-returns
  when data exists, so a prior run's published stories and at-ending `reading_state`
  persist and cause false failures (`approval-flow:40`, `kid-reads:34`,
  `series-continue:35`). Add a pre-tier reset (truncate `reading_state`, reset the
  review story to `in_review`) or drop+recreate the DB volume.
- **Two stale moderation tests:** `moderation-real.spec.ts:26` and `:46` predate the
  confirmation-dialog UI; they never click through the dialog so no PUT fires. Backend
  verified working via curl. Update the tests.
- **One stale contract expectation:** `naive-kid-misuse-real.spec.ts:35` expects 403,
  gets 401. Denial is correct (content not served); under ADR-014 per-profile child
  sessions a missing session is unauthenticated (401). Confirm 401 is intended and
  update the assertion.

### P2 (test-ops gaps)

- **Staging E2E passwords are unrecoverable by design** (`openssl rand`, never
  persisted; `seed_staging.py` docstring). Only the `staging` GitHub Environment secret
  holds them. Locally the tier cannot run without a reset. Consider recording them in a
  secret manager at seed time.
- **No `dev` Playwright tier exists.** `cyo-dev` can only be smoke-tested manually.
- **Coverage holes (from `docs/testing/coverage-matrix.md`):** offline sync/conflict,
  ratings, and provider-allowlist/authoring have no staging/prod coverage; staging is
  smoke-only.

## Verified working (reassurance)

- Mocked behavioral suite: 130/130.
- Kid read-to-ending and series-continue: both reached valid endings against the real
  backend (the "failures" were state-at-ending artifacts, not broken reads).
- Ratings persist across reload (real backend).
- Approval and moderation backends: verified read+write via direct API calls.
- Offline device-A create + save: works. Device-auth gate (ADR-014): enforced correctly
  on dev and in the real tier.
- Prod + dev public surfaces: clean, 0 console errors, no CSP breakage, Google OAuth
  button loads.

## Recommended actions (ordered)

1. **Verify the prod consent gate is passable** (P0-2). Highest leverage: it gates
   every guardian. A prod login driven through the gate confirms real users are not
   walled out.
2. **Fix the offline resync 422** (P0-1) in `frontend/src/offline/sync.ts`, strip
   View-only fields before PUT. Add/keep `offline-conflict-real.spec.ts:157` as the
   regression guard.
3. **Redeploy staging backend** (P1) from current `main` (homelab-infra), then re-run
   `e2e-staging.yml`, expect 6/6.
4. **Make the real-backend tier deterministic** (P2): pre-run DB reset; update the two
   moderation tests and the 401/403 assertion.
5. **Un-noise visual tests** (P2): CI-only baselines.

## Artifacts

Logs in `e2e-audit-results/` on branch `test/comprehensive-e2e-audit`:
`mocked.log`, `real.log` (pre-migration), `real2.log` (post-migration), `prod.log`,
`migrate.log`, `seed*.log`. Dev landing screenshot: `frontend/dev-landing-2026-07-22.png`
(via `.playwright-mcp/`).
