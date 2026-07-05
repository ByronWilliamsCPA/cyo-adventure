---
schema_type: planning
title: "R1 Deferred-Debt Register"
description: "Consolidated register of the accepted Minors and deferred items from the R1 gap-closure final
  reviews (PRs #105-#109, #111, #112), with severity, source, and the R2 gate flags."
tags:
  - planning
  - technical-debt
  - release
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Task 4.2 of the R1 gap-closure plan: one place to triage everything consciously deferred while
  shipping R1, so R2 planning starts from a complete debt inventory instead of scattered review ledgers."
component: Strategy
source: "SDD ledgers (.superpowers/sdd/progress.md) for story-requests-kid-ui and playwright-e2e; final
  review verdicts for PRs #105, #106, #107, #108, #109, #111, #112; docs/planning/r1-handoff-2026-07-04.md"
---

## Reading this register

Every entry was consciously accepted during an R1 final review, not missed. Severity reflects impact if
left unfixed through R2. "R2 gate" marks items that block the limited-iOS rung per the release ladder.

## R2 gate items (hard blockers before TestFlight)

| # | Debt | Source | Why it gates R2 |
| --- | --- | --- | --- |
| G1 | Child-session scoping: the kid surface runs under the guardian's token; there is no child-scoped session or role separation on the wire | R1 architecture (accepted for family-internal web) | Outside a trusted household, any kid can act with guardian privileges. Must land before non-family users |
| G2 | Issue #57: residual admin-submit gap (accepted for R1 local testing only) | PR #55 closeout | Explicitly scoped as R1-only acceptance |
| G3 | Issue #64 (accepted for R1 local testing only, same ruling as #57) | C4a review cycle | Same acceptance boundary |

## Correctness and data-integrity debts

| # | Debt | Source | Severity | Suggested action |
| --- | --- | --- | --- | --- |
| C1 | Offline reader completions are fire-and-forget: a completion recorded offline that fails on replay is silently lost (event_id omitted, server PK dedupes; deviceId unwired) | PR #107 final review | Medium | Wire the replay queue (see C2) and surface replay failures; add event_id once dedup semantics need it |
| C2 | Issue #110: `replayQueue` reconnect flush is exported but never wired, so queued offline writes do not flush on reconnect | PR #112 review discovery | Medium | Wire the flush into the reconnect handler; covered by an e2e-real scenario once wired |
| C3 | Blocked story-request submissions bypass the 5-pending cap, so a kid can retry a blocked text repeatedly and each retry spends classifier budget | PR #108 accepted design | Medium | Count blocked submissions against the cap, or rate-limit screening per child |
| C4 | No true-concurrent test of the `SELECT ... FOR UPDATE` row-lock guard on request approval (double-approve race is guarded in code, tested only sequentially) | PR #108/#109 reviews | Low | Add a two-session integration test with a barrier, or accept the lock as sufficient |

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
| T2 | `frontend/e2e/` and `e2e-real/` are not covered by `npm run lint` | PR #112 ledger | Low | Add the dirs to the ESLint config |
| T3 | Kid RequestStory error-clears-on-retry behavior is only implicitly tested | PR #111 ledger | Low | Pin with an explicit component test when touching U1 |
| T4 | K3 sibling console noise in kid library tests (accepted as deliberate RAD-tagged design + pre-existing hygiene) | PR #111 final review | Low | Silence in a test-hygiene pass |
| T5 | e2e-real auth helper hardcodes `user.id = 'e2e-user'` (fine while nothing reads it) | PR #112 task 1 ledger | Low | Parameterize when a test needs real per-user ids |
| T6 | Intake poll test has ~2s margin (8s interval vs 10s timeout); flake risk under CI load | PR #112 task 5 ledger | Low | Bump timeout to 12s on first flake |
| T7 | Real smoke tier is local-only by design (`--workers=1`; backend per-IP rate limiter 100rpm/burst 10 trips at 2 workers) | PR #112 user decision | Info | Revisit if a staging environment appears; not a defect |

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
