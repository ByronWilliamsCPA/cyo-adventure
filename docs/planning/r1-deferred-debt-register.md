---
schema_type: planning
title: "R1 Deferred-Debt Register"
description: "Consolidated register of the accepted Minors and deferred items from the R1 gap-closure final
  reviews (PRs #105-#109, #111, #112), plus the pre-R1 generation/safety/tooling debt carried in
  completion-plan.md (merged, doc archived), with severity, source, and the R2 gate flags."
tags:
  - planning
  - technical-debt
  - release
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "One place to triage everything consciously deferred while shipping R1, so R2 planning starts
  from a complete debt inventory instead of scattered review ledgers. Originated as Task 4.2 of the R1
  gap-closure plan (merged, doc archived)."
component: Strategy
source: "SDD ledgers (.superpowers/sdd/progress.md) for story-requests-kid-ui and playwright-e2e; final
  review verdicts for PRs #105, #106, #107, #108, #109, #111, #112"
---

## Reading this register

Every entry was consciously accepted during an R1 final review, not missed. Severity reflects impact if
left unfixed through R2. "R2 gate" marks items that block the limited-iOS rung per the release ladder.

## R2 gate items (hard blockers before TestFlight)

| # | Debt | Source | Why it gates R2 |
| --- | --- | --- | --- |
| G1 | Child-session scoping: the kid surface runs under the guardian's token; there is no child-scoped session or role separation on the wire. Cross-reference: safety-eval Finding 6 (kid surface sends the guardian token) is the same gap, deliberately left unfixed in R1 per the remediation plan's Task C4 decision record: the kid surface has no principal of its own, so removing the token breaks every kid read; the real fix is child-scoped sessions, tracked here as G1. | R1 architecture (accepted for family-internal web); Finding 6 deferral recorded in the R1 remediation plan's Task C4 (merged, doc archived) | Outside a trusted household, any kid can act with guardian privileges. Must land before non-family users |
| G2 | **[Closed]** Issue #57: residual admin-submit gap (accepted for R1 local testing only). Closed by the Task E4 hardening pass: `submit()` (`publishing/service.py`) now refuses the draft/needs_revision -> in_review transition when the story's latest version has `moderation_report is None`, mirroring the gate `approve()` already enforced. | PR #55 closeout | Explicitly scoped as R1-only acceptance (resolved) |
| G3 | **[Closed]** Issue #64 (safety-eval Finding 5: a documented control-character strip in concept.py does not exist; accepted for R1 local testing only, same ruling as #57). Closed by the Task E4 hardening pass: `ConceptBrief` now strips control characters from every string field at intake (`generation/concept.py`). | C4a review cycle | Same acceptance boundary (resolved) |

## Correctness and data-integrity debts

| # | Debt | Source | Severity | Suggested action |
| --- | --- | --- | --- | --- |
| C1 | Offline reader completions are fire-and-forget: a completion recorded offline that fails on replay is silently lost (event_id omitted, server PK dedupes; deviceId unwired) | PR #107 final review | Medium | Wire the replay queue (see C2) and surface replay failures; add event_id once dedup semantics need it |
| C2 | **[Resolved]** Issue #110: `replayQueue` reconnect flush is exported but never wired, so queued offline writes do not flush on reconnect. Resolved by Workstream B (PR #145): `useReplayOnReconnect` flushes on reader mount and on the browser `online` event; a replayed 409 surfaces a conflict dialog; a new e2e-real spec (`reader-reload-resume.spec.ts`) covers the resume path. | PR #112 review discovery; resolved PR #145 | Medium | Closed; no further action |
| C3 | Blocked story-request submissions bypass the 5-pending cap, so a kid can retry a blocked text repeatedly and each retry spends classifier budget | PR #108 accepted design | Medium | Count blocked submissions against the cap, or rate-limit screening per child |
| C4 | No true-concurrent test of the `SELECT ... FOR UPDATE` row-lock guard on request approval (double-approve race is guarded in code, tested only sequentially) | PR #108/#109 reviews | Low | Add a two-session integration test with a barrier, or accept the lock as sufficient |
| C5 | `choice_path` is optional in reading-state saves this slice; absent it, only the structural floor runs, not full deterministic replay (`api/reading.py`) | Slice 3 (#45) accepted design; migrated from `completion-plan.md` (merged, doc archived) | Medium | Update the React player to send `choice_path`, regenerate the client, then make the field required so replay runs on every save |

## Generation and safety debts (pre-R1, migrated from completion-plan.md)

| # | Debt | Source | Severity | Suggested action |
| --- | --- | --- | --- | --- |
| GS1 | Tier-2 generation yield weak (3/7 on the 2026-06-22 live run vs Tier-1's 11/13); dominant failure was L1-7 "budget" (branch depth over the band cap, ending count off-brief) | Phase 2b live run, `yield-results/phase-2b-2026-06-22-analysis.md` | Medium | Tighten the Stage A structure prompt to state band budgets inline and numerically (highest-leverage, model-independent lever per `phase-2b-live-provider.md`); re-measure before relying on Tier-2 generation in production |
| GS2 | Adversarial safety gate's "flag and route to human review" claim is unverified for the model-dependent classes: no live-model adversarial run has been executed (blocked on credential availability in this environment, not code) | `safety/adversarial-safety-evaluation.md`, Findings A/B/E | Medium | Run the credentialed adversarial harness (`scripts/adversarial_harness.py`) against a live review model and archive per-class results |

## UX debts

| # | Debt | Source | Severity | Suggested action |
| --- | --- | --- | --- | --- |
| U1 | Kid RequestStory: a late rejection after Cancel re-arms the error, which is shown on next dialog open (Cancel is disabled while sending, which narrows but does not close this) | PR #111 K2 ledger | Low | Clear error state on dialog open, or abort the in-flight request on cancel |
| U2 | Intake "Still processing" section is inert (no polling/refresh affordance) | Issue #74 (C4a-4) | Low | Tracked in issue #74 |
| U3 | Unused `age_band` field returned by GET /guardian/books | PR #106 final review | Low | Use it for filtering in R2 or drop it from the response |
| U4 | ConsolePage JSX duplication (pre-existing, noted during #106) | PR #106 final review | Low | Fold into the next guardian-console refactor |

## Test and tooling debts

| # | Debt | Source | Severity | Suggested action |
| --- | --- | --- | --- | --- |
| T1 | ADR-005 admin-only approve 403 is not exercised server-side in the real tier (mock-layer 403 only) | PR #112 final review | Medium | Add a real-tier guardian POST /approve expecting 403 |
| T2 | **[Resolved]** `frontend/e2e/` and `e2e-real/` are not covered by `npm run lint`. Resolved by Task F3 (PR #154): ESLint switched to `recommendedTypeChecked`, both directories added to lint coverage with their own `tsconfig.e2e.json` project, and every violation the type-aware rules surfaced (including the `no-floating-promises` class that would have caught #110) was fixed. | PR #112 ledger; resolved PR #154 | Low | Closed; no further action |
| T3 | Kid RequestStory error-clears-on-retry behavior is only implicitly tested | PR #111 ledger | Low | Pin with an explicit component test when touching U1 |
| T4 | K3 sibling console noise in kid library tests (accepted as deliberate RAD-tagged design + pre-existing hygiene) | PR #111 final review | Low | Silence in a test-hygiene pass |
| T5 | e2e-real auth helper hardcodes `user.id = 'e2e-user'` (fine while nothing reads it) | PR #112 task 1 ledger | Low | Parameterize when a test needs real per-user ids |
| T6 | Intake poll test has ~2s margin (8s interval vs 10s timeout); flake risk under CI load | PR #112 task 5 ledger | Low | Bump timeout to 12s on first flake |
| T7 | Real smoke tier is local-only by design (`--workers=1`; backend per-IP rate limiter 100rpm/burst 10 trips at 2 workers) | PR #112 user decision | Info | Revisit if a staging environment appears; not a defect |
| T8 | `esbuild` Renovate re-proposal: no `renovate.json` rule pins/groups `esbuild` to Vite's range, so the #22 bump keeps getting re-proposed | Carried TODO; migrated from `completion-plan.md` (merged, doc archived) | Low | Open a `renovate.json` rule pinning/grouping `esbuild` to Vite's range |
| T9 | markdownlint whole-repo table/heading debt (non-gating, pre-push only) | Carried TODO; migrated from `completion-plan.md` (merged, doc archived) | Low | Address opportunistically; do not block planning-doc updates on it |

## Policy and architecture deferrals (adjacent, pre-R1)

| # | Debt | Source | Suggested action |
| --- | --- | --- | --- |
| P1 | App-wide rate-limit policy never decided (per-endpoint limits are ad hoc) | PR #69 review | Decide one policy in R2 planning |
| P2 | `get_generation_job` reports errors to guardians in tension with ADR-007 report-to-admin | PR #69 review | Reconcile with ADR-007 |
| P3 | `useApi` does not redirect on 401 | PR #69 review | Decide global 401 handling with P1 |
| P4 | Issues #77, #78, #79: deferred behavioral items from the skeleton scale enabler | PR #70 review | Skeleton workstream backlog, independent of R1 |

## Bookkeeping

- The SDD ledgers backing this register: story-requests-kid-ui and playwright-e2e ledgers are preserved
  verbatim in this register's source PRs; other worktree ledgers were consolidated via the review-session
  memory notes before their worktrees were removed.
- Local e2e Postgres container `cyo-e2e-real-db` (port 5443) may still be running from the PR #112
  session; stop it when no real-tier work is active.
