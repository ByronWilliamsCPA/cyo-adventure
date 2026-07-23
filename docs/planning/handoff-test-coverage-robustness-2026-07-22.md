---
purpose: Work order to close EVERY gap identified by the 2026-07-22 cross-environment
  e2e audit and the action-level coverage-robustness verdict. A fresh session should
  execute the phases below top to bottom; each item has a concrete acceptance criterion.
component: testing
source: session 2026-07-22, worktree .worktrees/e2e-audit, branch test/comprehensive-e2e-audit
---

# Work order: close all audit + robustness holes, 2026-07-22

This is an executable gap-closure plan, not just a status note. It consolidates
every hole from two source documents so a fresh session can drive them all to
done without re-deriving state:

- Audit: [`handoff-comprehensive-e2e-audit-2026-07-22.md`](handoff-comprehensive-e2e-audit-2026-07-22.md)
  (P0/P1/P2, per environment).
- Verdict: [`../testing/action-coverage-robustness-2026-07-22.md`](../testing/action-coverage-robustness-2026-07-22.md)
  (per-action x per-tier grading, component-only areas, micro-holes).

Work from the worktree `.worktrees/e2e-audit`. Branch per phase (`fix/`, `test/`,
`ci/`, `docs/`); never commit to `main`; sign commits; push and open PRs only
with user approval. Regenerate the frontend client and re-run the relevant tier
after any backend contract touch.

## Status legend

DONE = shipped this session. TODO = open. USER = needs the user or another repo.

## Phase 0, already shipped this session (do not redo)

- **DONE, P0-1 offline resync 422.** `frontend/src/offline/sync.ts` `toPutPayload()`
  whitelist. Branch `fix/offline-sync-put-payload` (PR A). Regression guard:
  `frontend/e2e-real/offline-conflict-real.spec.ts` (4/4 green).
- **DONE, P0-2 consent gate verified passable** on prod against the E2E account
  (it is not a wall). But it still has NO automated E2E, so it reappears as
  item 1.1 below.
- **DONE, matrix drift corrected** (8 orphan sections + gap-6 rewrite) and the
  verdict doc written. Branch `docs/test-coverage-robustness-audit` (PR B).

## Phase 1, highest-leverage E2E holes (do first)

- **1.1 TODO, consent-gate mocked E2E.** Highest traffic x blast-radius untested
  action. New `frontend/e2e/guardian-consent.spec.ts`: sign in a `needs-consent`
  principal (mock `GET /v1/me` status), assert `/guardian/intake` redirects to
  `/guardian/consent`, fill legal name + tick consent, submit (`POST /v1/onboarding`
  via `recordConsent`), assert redirect back to console and that
  `/guardian/intake` now renders instead of redirecting. Also assert the
  awaiting-approval interstitial path. Accept: spec green in the mocked tier;
  add a real-backend variant in `frontend/e2e-real/` if the seed can mint a
  pre-consent user.
- **1.2 TODO, CI drift-guard.** New CI step (extend `ci.yml` or a small script)
  that fails if any `frontend/e2e*/**/*.spec.ts` or `frontend/src/**/*.test.{ts,tsx}`
  is not referenced by path in `docs/testing/coverage-matrix.md`. Accept: adding
  an unreferenced spec fails CI locally; the current tree passes. This is the
  structural fix that prevents the 8-orphan recurrence and the matrix already
  requests it.

## Phase 2, backfill E2E for component-only write paths

Each area below currently has a component test but NO browser-level proof at any
tier (confirmed by grep across all four e2e dirs). Add mocked-tier E2E first;
promote the real mutations to `e2e-real` where a seed supports it.

- **2.1 TODO, guardian family-connections consent.** `ConnectionsPage` Allow
  (`POST /v1/family-connections/{id}/consent`) and Revoke
  (`DELETE .../consent`), both confirm-gated. Privacy-load-bearing (ADR-016
  three-ring boundary). New `frontend/e2e/guardian-connections.spec.ts`.
- **2.2 TODO, review passage-edit save.** `PATCH .../nodes/{id}` from
  `ReviewDetailPage` (both reachable AND unreachable-passage sections share
  wiring, cover both). Add to a review spec or new `frontend/e2e/review-edit.spec.ts`;
  promote to `e2e-real` alongside `approval-flow.spec.ts`.
- **2.3 TODO, password recovery.** Request reset + set-new-password, including
  the cross-tab `BroadcastChannel` handoff (recovery link opened in tab A must
  surface the set-new form in tab B). New `frontend/e2e/guardian-password-reset.spec.ts`.
- **2.4 TODO, admin read-heavy pages.** Audit log (filter/page), admin library
  lifecycle filter, review version-compare panel. Lower exposure; one spec each
  or fold into `guardian-console.spec.ts`.
- **2.5 TODO, offline-copy revocation reconcile.** `offline/revocation.ts` purge
  on library refetch; also fix/track its known latency gap (a book unassigned
  mid-read is not caught until the next library fetch).
- **2.6 USER-decision, OAuth sign-in.** Not mock-testable. Decide: script a
  staging Google-login check (Google is live on staging) or accept manual-only.
  Document the decision in the matrix.

## Phase 3, deepen the real-backend tier

Ten areas are mocked-only (graded "Solid-local"). Add `e2e-real` coverage,
prioritizing writes, against the seeded local stack (`real-stack.ts` helpers):

- **3.1 TODO, writes:** guardian profile CRUD, provider-allowlist CRUD, admin
  user/profile/family management (WS-J), story-request submit end to end.
- **3.2 TODO, reads/interactions:** notifications (G10), reading-history (G9),
  read-aloud (K7), flag (K15), go-back (K5), cover generation (A16).
- Accept: each new `e2e-real` spec passes against the migrated local DB; note
  any real bug found (the authoring-plan real spec already caught one this way).

## Phase 4, make the test harness deterministic (P2 harness debt)

- **4.1 TODO, un-noise visual tests.** All 18 mocked "failures" are host-vs-CI
  font pixel drift. Gate `frontend/e2e/visual.spec.ts` to CI-only, or regenerate
  baselines in CI. Accept: a clean local `npm run test:e2e` shows 0 visual fails.
- **4.2 TODO, deterministic real-backend tier.** `scripts/seed_dev_data.py`
  early-returns when data exists, so prior-run published stories and at-ending
  `reading_state` persist and cause false failures (`approval-flow:40`,
  `kid-reads:34`, `series-continue:35`). Add a pre-tier reset (truncate
  `reading_state`, reset the review story to `in_review`) or drop+recreate the
  DB volume in the tier's setup. Accept: `npm run test:e2e:real` is green on a
  second consecutive run without manual DB surgery.
- **4.3 TODO, 2 stale moderation tests.** `frontend/e2e-real/moderation-real.spec.ts:26`
  and `:46` predate the confirmation-dialog UI and never click through it, so no
  PUT fires. Update them to click through the dialog. Backend verified working.
- **4.4 TODO, 1 stale contract assertion.** `frontend/e2e-real/naive-kid-misuse-real.spec.ts:35`
  expects 403 but gets 401 (under ADR-014 per-profile child sessions a missing
  session is unauthenticated). Confirm 401 is intended and update the assertion.

## Phase 5, verify the micro-holes (assert-or-add)

For each, read the existing component test; if the branch is not asserted, add
coverage. From the verdict doc's "suspected micro-holes":

- Modified-click / new-tab bypass on the profile-picker tile.
- Read-aloud "broken" latch (first `speak()` throw hides the toggle for the session).
- Cover-generation timeout branch (30x2s poll exhausts, distinct from failed).
- Endings-tracker under-report race (must never over-count vs the completion POST).
- Unknown-category threshold override extra-confirm depth; noise-floor 0.3 boundary warning.
- Unreachable-passage edit (shares wiring with reachable edit).
- `ProfileFormDialog` envelope "touched" gating (untouched inclusion 422s the whole PATCH today).
- `GET /v1/device-grants` (list): confirm dead code before writing any coverage; if dead, delete it.

## Phase 6, environment and infra (USER / cross-repo)

- **6.1 USER, staging backend redeploy (P1).** homelab-infra: rebuild+redeploy
  the `:staging` backend and worker from current `main` (predates PR #311, so
  `POST /v1/onboarding` omits `status`, false "awaiting approval" gate; fails
  `guardian-admin-smoke.spec.ts:34`, `kid-library-smoke.spec.ts:75`). No app-repo
  code change. Then re-run `e2e-staging.yml`, expect 6/6.
- **6.2 USER, staging password durability.** Passwords are `openssl rand`, never
  persisted (`scripts/seed_staging.py`). Record them in a secret manager at seed
  time so the staging tier can run locally without a reset.
- **6.3 TODO, raise staging above smoke.** Once 6.2 lands, add ONE real
  approval-and-read journey on staging; that single spec would have caught the
  stale-image bug before a user did.
- **6.4 USER-decision, dev Playwright tier.** None exists (no frontend deploy
  pipeline this repo owns). Decide whether to add one or keep dev as manual smoke.

## Phase 7, structural test-design gaps (second-team review, 2026-07-22)

A second team reviewed `main` (before this work order's changes landed) and
surfaced structural gaps that Phases 1 to 6 do not cover. Deduplicated against
the phases above; only the genuinely-new items are listed. Their G5
(performance/load) is out of this order's scope and already owned by roadmap
Phase 9 (P9-13 capacity baseline), so it is not added here.

- **7.1 TODO (G1, highest), full-pipeline E2E through the real RQ worker.** The
  request to generate to gate to moderate to approve to publish to read pipeline
  is only asserted in fragments; `e2e-real` seeds data rather than generating
  it, and the RQ generation/cover workers are never in a browser E2E loop. Not
  covered by Phase 3.1 (which submits a request but does not drive real
  generation). Done when one nightly E2E submits a real story request, lets the
  real RQ worker process it through the real validator gate + moderation, has a
  guardian/admin approve via the real approval API, publishes, and drives a kid
  to read the published book to a valid ending. Redis + worker must run in-loop.
  Needs a dedicated nightly job with its own infra (see decision below); heavier
  than the rest of Phase 3.
- **7.2 TODO (G2), pin the mocked tier to the real contract.** The ~35
  hand-written `page.route` fulfilments in `frontend/e2e/` can drift from the
  real backend with no link to the OpenAPI schema; this is the same failure
  class as the audit's P0-1 (the mocked tier did not enforce `extra=forbid`, so
  the offline-resync defect was invisible until the real backend caught it).
  Done when either the mocked-tier bodies are validated against the OpenAPI
  component schemas, OR a few real-backend "contract smoke" specs cover the
  highest-drift endpoints (library, reading-state PUT, intake, review).
  Recommended: the contract-smoke route (lighter, and the real backend already
  enforces `extra=forbid`).
- **7.3 TODO (G3), offline-vs-online branching parity.** `back()`/`canGoBack()`
  replay and `startContinuation()` are the client-engine paths most likely to
  diverge from a server-side recompute, and no E2E asserts equivalence. Phase
  3.2 adds a go-back (K5) spec, but not a parity assertion. Done when an E2E
  reads a branching story offline (go back, re-choose, continue a series) and
  asserts the resulting current node, variable state, and ending match the
  online/server path for the same choice sequence.
- **7.4 TODO (G4), promote one real-stack smoke to the PR path.** The real tier
  is nightly-only, so developers get no full-stack signal per PR. Unblocked now
  that Phase 4.2 made the tier deterministic. Done when one fast happy-path
  real-stack spec (e.g. `kid-reads` or `approval-flow`) runs on PRs.

### Phase 7 open questions (answered)

- **G1 infra:** run the full-pipeline test as a DEDICATED nightly job with its
  own Redis + RQ worker services, not on the per-PR path. The per-PR full-stack
  signal is 7.4 (a fast seeded happy-path), which needs neither the worker nor
  live generation.
- **G2 approach:** prefer a few real-backend contract smokes over
  OpenAPI-example fixture generation; the real backend's `extra=forbid` is the
  exact check that catches shape drift, and example-driven fixtures are brittle.
- **G5 performance/load:** out of this order's scope; owned by roadmap Phase 9.
  Confirm with the product owner rather than folding it in here.

## Do-not-re-derive facts

- Deep specs are LOCAL only (mocked 34 + real 9). Staging (2) + prod (3) are
  smoke-only; no dev tier.
- Staging CI 2/6 failure is stale-image, NOT passwords.
- Prod consent gate is passable (verified this session); real guardians are not walled out.
- Real-backend blocker earlier was a stale local DB; apply all `supabase/migrations`
  >= 20260716120000 before the real tier (2 RLS-GRANT errors on plain postgres are expected/harmless).

## Kickoff prompt for a fresh session

> Take over `docs/planning/handoff-test-coverage-robustness-2026-07-22.md` and
> close every open (TODO) hole in it, phase by phase, starting with Phase 1.
> PRs `fix/offline-sync-put-payload` and `docs/test-coverage-robustness-audit`
> are already open and user-gated. Branch per phase, sign commits, and hold
> pushes for approval. Read the linked verdict and audit docs first.
