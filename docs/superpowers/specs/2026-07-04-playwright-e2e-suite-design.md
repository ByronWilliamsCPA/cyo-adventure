---
title: "Two-Tier Playwright E2E Suite: Guardian Console Coverage and Real-Backend Smoke (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "Brainstorming session 2026-07-04; docs/architecture/user-journeys.md developer coverage view (merged PR #102); frontend/e2e/* existing suite; frontend/src/auth/AuthContext.tsx + supabaseClient.ts (PR #101 email/password sign-in); src/cyo_adventure/api/deps.py local auth seam; scripts/seed_dev_data.py (fixed by PR #104)."
purpose: "Close all seven amber e2e gaps in the journey coverage map (guardian sign-in, console queue, ADR-005 approve gate, send-back loop, intake, profile management, reader 409 reconciliation) with a mocked-network Playwright tier, and add a small real-backend smoke tier that catches mock/contract drift."
tags:
  - planning
  - testing
  - project
---

> Date: 2026-07-04 | Author: Byron Williams (with Claude)

## 1. Problem

The developer coverage view in
[user-journeys.md](../../architecture/user-journeys.md#developer-view-test-coverage)
shows the kid surface is well covered end-to-end, but the entire guardian
console is amber: shipped behavior with Vitest coverage and no browser-level
test. The highest-risk gap is the ADR-005 Approve gate, the mandatory
human-in-the-loop safety checkpoint before any story reaches a child. Two more
amber gaps sit outside the console: guardian sign-in success (only the
unauthenticated redirect is e2e-tested today) and the reader's 409-conflict
reconciliation (offline read is tested, conflict resolution is not).

The existing e2e suite deliberately skipped the signed-in guardian surface
because forging a persisted supabase-js GoTrue session was version-pinned
brittleness (documented in `frontend/e2e/guardian-console.spec.ts`). PR #101
(email/password sign-in) removed that blocker: `signInWithPassword` makes a
plain network call to `/auth/v1/token?grant_type=password`, which Playwright
can mock at the network seam. supabase-js then persists its own session in
whatever storage shape it owns, and the real `SIGNED_IN` event, `/v1/me`
resolution, and `ProtectedRoute` logic all run untouched.

Additionally, the whole existing suite is network-mocked, so nothing verifies
that the mocked response shapes still match what the backend actually sends.

## 2. Goals

1. Close all seven amber gaps with deterministic, network-mocked Playwright
   specs that run in the existing CI e2e job.
2. Add a small real-backend smoke tier (separate Playwright project) where only
   Supabase auth is mocked and every `/api` call hits a real FastAPI + Postgres
   stack, to catch mock/contract drift.
3. Update the journey coverage diagram so amber nodes covered by this work turn
   green, keeping the gap map truthful.

## 3. Non-goals

- No coverage of planned-but-unbuilt steps (child story request, guardian
  request approval); those stay red in the coverage map until built.
- No real Supabase project in any tier; Supabase auth is always mocked at the
  token endpoint.
- No duplication of the full mocked matrix in the smoke tier; tier 2 stays
  small (about four scenarios) by design.
- No Firefox/WebKit projects; the suite stays chromium-only like today.

## 4. Tier 1: mocked-network guardian and conflict specs

### 4.1 Auth helper

New file `frontend/e2e/support/auth.ts` exporting
`signInAsGuardian(page, { role: 'guardian' | 'admin' })`:

1. Route `**/auth/v1/token?grant_type=password**` to fulfill a canned GoTrue
   session JSON (`access_token: 'e2e-<role>-token'`, `expires_in` long enough
   that no refresh fires mid-test, minimal `user` object).
2. Route `**/api/v1/me` to fulfill a principal body whose `role` matches the
   requested role, with a stable `family_id` and `profile_ids`.
3. Navigate to `/guardian/login`, fill the real email/password form, click
   sign-in, and wait for the redirect away from the login page.

The helper mocks the network seam only. supabase-js writes and owns its
persisted session; no storage shape is forged, so library upgrades do not
break the helper. Sign-out and 401-expiry behavior continue to exercise the
real AuthContext fail-closed paths.

The stale header comments in `guardian-console.spec.ts`, `intake.spec.ts`, and
`profiles.spec.ts` (which document the old "cannot establish a session"
decision) are updated to point at the helper.

### 4.2 Spec matrix

One spec area per amber gap. All API responses are mocked per-test with
`page.route`, matching the suite's existing style (route mocks registered
before `page.goto`, user-visible assertions, request-body assertions where the
write payload matters).

| Spec file | Gap closed | Key cases |
| --------- | ---------- | --------- |
| `guardian-auth.spec.ts` (new) | Guardian sign-in success | Successful sign-in lands on the console; wrong password (token endpoint returns 400) shows the error and stays on login; sign-out returns to login and a subsequent `/guardian` visit redirects |
| `guardian-console.spec.ts` (extend) | Console review queue | Mixed mocked list renders ordered Flagged, then Ready to review, then Still processing; clicking a row navigates to `/guardian/review/:id` |
| `guardian-review.spec.ts` (new) | Review detail, ADR-005 approve, send-back | Flagged passages render before full text; Approve as admin POSTs and the UI reflects the approved state; Approve as guardian surfaces the 403 without a false success (fail-closed); send-back with a note POSTs the note and returns the story to the queue state |
| `intake.spec.ts` (extend) | Intake request and job status | Signed-in submit POSTs the expected body (who, topic, tone), the request appears with a Generating status, and a mocked poll transition flips it to Ready |
| `guardian-profiles.spec.ts` (new) | Guardian profile management | Create a child profile (POST body asserted, list refreshes), edit a display name, and the avatar picker offers presets only (no upload input) |
| `reader-conflict.spec.ts` (new) | Reader 409 reconciliation | Queued offline progress meets a 409 on reconnect; the reconciliation UI appears and resolving it does not silently lose progress (exact assertions follow `frontend/src/offline/sync.ts` and its dialogs) |

ADR-005 rationale for the two-role approve cases: the gate is admin-only, and
the guardian-403 case is the security regression that matters most (a guardian
must never be able to self-approve, and a failed approve must never look like
success).

### 4.3 What tier 1 does not prove

Mocked specs assume response shapes. If the backend renames a field, tier 1
stays green while the app breaks. That residual risk is exactly what tier 2
exists for.

## 5. Tier 2: real-backend smoke suite

### 5.1 Architecture

- New Playwright project `real-backend` in `playwright.config.ts` with
  `testMatch: 'e2e-real/**'`; the default `chromium` project excludes
  `e2e-real/` so `npm run test:e2e` keeps its current meaning. A new script
  `test:e2e:real` runs only the smoke project.
- Stack: dockerized Postgres (CI: service container on 5432; local: port 5442
  per the documented local-run recipe), uvicorn with
  `CYO_ADVENTURE_ENVIRONMENT=local`, seeded via `scripts/seed_dev_data.py`,
  and the built frontend served by `vite preview`.
- `vite.config.ts` gains a `preview.proxy` block mirroring the existing
  `server.proxy` (`/api` and `/openapi.json` to `http://localhost:8000`),
  because `vite preview` does not inherit `server.proxy`. Tier 1 is
  unaffected: its route mocks intercept before the network.
- Auth: only the Supabase token endpoint is mocked, returning an
  `access_token` equal to a seeded user's `authn_subject` (`dev-guardian` or
  `dev-admin`). The backend's `local` auth seam
  (`api/deps.py::_resolve_subject`) trusts the bearer token as the subject, so
  `/v1/me`, role authorization, and every domain endpoint run for real against
  seeded rows. This exercises the `require_principal` chain that `page.route`
  mocks can never see.

### 5.2 Seed extensions

`scripts/seed_dev_data.py` (already fixed by PR #104 to publish and assign)
gains, idempotently:

- an admin `User` (`authn_subject='dev-admin'`) so the ADR-005 approve
  scenario has a real admin principal;
- one storybook in the submitted/needs-review state, with at least one
  moderation flag, so the review queue and approve path have real input.

Seed changes carry RAD tags per the package rules and keep the script
re-runnable.

### 5.3 Smoke scenarios (four, high-value only)

1. **Kid reads for real**: library for the seeded profile loads from the real
   API; open the seeded story; play to an ending.
2. **Guardian sees the real queue**: sign in as `dev-guardian`; the console
   lists the seeded submitted story from the real review endpoints.
3. **Admin approves for real (ADR-005 write path)**: sign in as `dev-admin`;
   open the seeded submitted story; approve; the queue reflects the approved
   state on reload (persisted, not optimistic).
4. **Approved story reaches the child**: after scenario 3, the story is
   assigned and appears in the child's library from the real API.

Scenarios 3 and 4 run serially in one spec file (they share DB state); the
project sets `fullyParallel: false` for `e2e-real/`.

### 5.4 CI

New `frontend-e2e-real` job in `ci.yml`: Postgres service container, `uv sync`,
seed, start uvicorn in the background, wait for the readiness probe, then
`npm run test:e2e:real`. One retry like the existing e2e job. The job is a
normal PR check (the merge queue's required-check list is a repo setting and
is not changed by this work).

## 6. Error handling and flake policy

- Tier 1 stays `fullyParallel` with per-test route mocks; no shared state.
- Tier 2 is serial, seeds once per run, and asserts on persisted state
  (reload before asserting approve took effect) rather than on transient
  toasts, which is the main anti-flake measure for real-stack tests.
- Any smoke-tier failure mode that turns out to be environmental (port
  collisions, container startup) belongs in the job setup, not in test
  retries; retries stay at 1.

## 7. Documentation follow-through

- Recolor the nodes this work covers in
  `docs/architecture/diagrams/journey-dev-coverage.*` from amber to green and
  update the amber-gap table in `user-journeys.md`.
- Update the stale header comments named in 4.1.
- CHANGELOG entry per the repo's changelog gate.

## 8. Delivery

- Branch: `test/playwright-e2e-guardian-and-real-smoke` in worktree
  `.worktrees/playwright-e2e`, based on `origin/main` at PR #104.
- Suggested implementation order: auth helper first (everything guardian
  depends on it), then the six tier-1 spec areas, then the seed extension,
  then the tier-2 project and CI job, then the docs recolor.
- Each step lands with the full frontend gate green: `npm run lint`,
  `npm run typecheck`, `npm run test:run`, `npm run test:e2e` (and
  `test:e2e:real` once it exists); backend gates for the seed change.

## 9. Risks

| Risk | Mitigation |
| ---- | ---------- |
| GoTrue rejects the canned token-endpoint JSON after a supabase-js upgrade | The canned body uses only documented session fields; if it ever breaks, the failure is loud (sign-in never completes) and confined to the helper |
| Review/approve UI state names drift from mocked assumptions | Tier 2 scenario 3 approves against the real API, so drift fails the smoke job |
| Smoke tier flakes in CI | Serial execution, persisted-state assertions, readiness-probe gating before tests start |
| 409 reconciliation UI is more complex than assumed | The spec case is written from `offline/sync.ts` and its dialog tests during implementation; if the UI turns out to be headless (auto-reconcile), the e2e asserts the reconciled outcome instead of a dialog |
