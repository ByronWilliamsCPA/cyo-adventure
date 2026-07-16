---
schema_type: planning
title: "R1 Deferred-Debt Register"
description: "Consolidated register of the accepted Minors and deferred items from the R1 gap-closure final
  reviews (PRs #105-#109, #111, #112), the pre-R1 generation/safety/tooling debt carried in
  completion-plan.md (merged, doc archived), plus the post-R1 story-lifecycle-redesign deferrals
  (WS-A through WS-G), with severity, source, and the R2 gate flags."
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
| U1 | **[Resolved]** Kid RequestStory: a late rejection after Cancel re-arms the error, which is shown on next dialog open (Cancel is disabled while sending, which narrows but does not close this). Resolved by the 2026-07-15 UX-improvements pass: the error state now clears on every dialog open (both the button-driven and anchor-driven open paths), pinned by a T3 regression test. | PR #111 K2 ledger; resolved 2026-07-15 | Low | Closed; no further action |
| U2 | Intake "Still processing" section is inert (no polling/refresh affordance) | Issue #74 (C4a-4) | Low | Tracked in issue #74 |
| U3 | Unused `age_band` field returned by GET /guardian/books | PR #106 final review | Low | Use it for filtering in R2 or drop it from the response |
| U4 | ConsolePage JSX duplication (pre-existing, noted during #106) | PR #106 final review | Low | Fold into the next guardian-console refactor |
| U5 | No guardian-facing reading tracker: `POST /completions` records a finish but no endpoint reads completions back, so a guardian has zero visibility into what a child has actually read. This is Phase 4b scope, not fixed in the 2026-07-15 UX pass because it needs a new backend read endpoint (and likely a schema/index decision) before any frontend page is worth building. | 2026-07-15 UX-improvements pass (comprehensive review) | Medium | Design and add a `GET` completions/reading-history endpoint scoped per family, then build the guardian tracker page against it |
| U6 | Star ratings cannot be cleared once set (tapping the same star re-saves the same value): `POST /ratings` requires `value: int = Field(ge=1, le=5)` with no DELETE endpoint, so the frontend correctly declines to fake clearing. | 2026-07-15 UX-improvements pass | Low | Add a `DELETE /v1/ratings/{profile_id}/{storybook_id}` (or accept a null value) and wire a clear affordance into `StarRating.tsx` |
| U7 | The "Recent threshold changes" audit feed (`ModerationDashboardPage.tsx`) now renders human-readable before/after values from `payload`, but still cannot show WHO made a change: `ThresholdChangeView` carries no actor field. | 2026-07-15 UX-improvements pass | Low | Add an actor/admin-id column to the threshold-change event and surface it in the feed |
| U8 | **[Resolved]** Admin story review (`ReviewDetailPage.tsx`) had no version picker or passage-level diff. Resolved 2026-07-15: a "Compare with version N-1" toggle fetches the previous version and renders an added/removed/changed passage diff (old vs. new body, a choices-changed note), gracefully handling a missing previous version; the repaired badge now hints at it. Deliberately "compare with the immediately prior version," not a full version-history picker, since no backend endpoint enumerates a storybook's existing versions. | 2026-07-15 UX-improvements pass; resolved 2026-07-15 | Medium | Closed; a true version-history picker still needs a backend enumeration endpoint if ever wanted |
| U9 | No i18n readiness (all copy is inline JSX, no string catalog), and no push channel (WebSocket/SSE): every long-running status (generation, moderation review) is poll-only. Dark mode was resolved 2026-07-15 (see below); i18n and the push channel remain out of scope (product/architecture decisions, not frontend polish). | 2026-07-15 UX-improvements pass | Low (i18n) / Medium (push channel, as usage scales) | i18n: extract strings to a catalog while the surface is still small. Push channel: revisit if polling load becomes a real cost. |
| U9a | **[Resolved]** No dark mode. Resolved 2026-07-15: a full dark palette behind `@media (prefers-color-scheme: dark)` in `tokens.css`, overriding every color token under the same custom-property names (contrast-verified), plus `index.html`'s `color-scheme` meta set to `"light dark"`. Two real contrast regressions the new palette would otherwise have shipped were fixed in the same pass: the admin hard-block badge's white-on-error fill (pinned to the light-mode error tone, since `--color-error` is now brighter for its foreground-text role) and every text input's background (`FormField.css` routed through the already-per-theme `--surface-raised` token instead of a bare white literal). | 2026-07-15 UX-improvements pass; resolved 2026-07-15 | Low | Closed; see U9b for the dark-mode polish gap this surfaced |
| U9b | About a dozen low-opacity decorative background washes in `guardian.css` (flag badges, flagged/highlighted passage tints, the at-gate insight row) are hand-encoded `rgb(r g b / X%)` literals rather than token references, so they will not re-tint for dark mode (found while verifying U9a). Each sits behind separately color-tokened text, so this is a polish gap, not a contrast failure. | 2026-07-15 UX-improvements pass (dark-mode verification) | Low | Route each wash through its underlying token (e.g. `--color-error`, `--color-forest`, `--color-amber`) at low opacity via `color-mix()` or a dedicated `-wash` token per family |
| U10 | **[Resolved]** `docs/architecture/diagrams/journey-kid.puml`/`.svg` showed the old "Continue this story" label. Resolved 2026-07-15: both updated to "Ask for the next book"; the `.svg` was hand-patched (exact text run plus its container width recalculated) rather than regenerated, since no PlantUML renderer producing output consistent with the file's existing layout was available in that session (only an old bundled 2019 jar with markedly different output dimensions/style). A note in the `.puml` source flags this for the next real layout change, which should regenerate properly. | 2026-07-15 UX-improvements pass; resolved 2026-07-15 | Low | Closed; regenerate with a current PlantUML on the next real layout change to this diagram |
| U11 | **[Resolved]** The guardian responsive pass (2026-07-15) covered the review-queue action row, profile/book cards, and tables; a follow-up screenshot-driven audit (real Chromium renders at 360-800px, not just CSS review) of `ConsolePage.tsx`'s device-management section and `IntakePage.tsx`'s "My Requests" rows found and fixed two genuine flexbox intrinsic-sizing bugs only visible below ~640px (device buttons sized inconsistently by their own hint paragraph's wrapped width; request rows with both a status pill and an assign/retry button crushed the title column). Resolved 2026-07-15. | 2026-07-15 UX-improvements pass; resolved 2026-07-15 | Low | Closed; a broader per-page audit can still follow once real usage data shows which guardian pages matter most on mobile |

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

## Story-lifecycle redesign deferrals (post-R1, WS-A through WS-G)

The story-lifecycle redesign (umbrella PR #161, ten ratified decisions, seven workstreams WS-A through
WS-G, all merged as of 2026-07-10) is feature-complete. These items were consciously deferred during that
work: four are forward-looking, data-driven, or v2 decisions carried in the umbrella spec's "Open items"
section; the rest are per-workstream follow-ups recorded in each workstream's final review. None blocks the
merged feature set; all are R2-planning inputs.

| # | Debt | Source | Severity | Suggested action |
| --- | --- | --- | --- | --- |
| SL1 | Per-band moderation threshold seed values do not exist yet: v1 ships zero seed rows and relies on the code default everywhere, by deliberate design; per-band values are a future addition once WS-F dashboard evidence justifies deviating from the uniform default | story-lifecycle-redesign.md Open item 1 (WS-F), resolved 2026-07-07 | Low | Add per-band threshold rows once WS-F dashboard evidence supports deviating from the uniform code default |
| SL2 | The pipeline event taxonomy is a deliberate starting set, not exhaustive; new event kinds are expected as the pipeline grows | story-lifecycle-redesign.md Open item 2 (WS-D) | Info | Extend the taxonomy as new pipeline stages emit events |
| SL3 | Catalog-continuation admin notification is undecided: when a guardian branches a catalog (non-family-authored) trunk into a family-owned continuation, whether and how to notify an admin is unresolved | story-lifecycle-redesign.md Open item 3 (WS-E/WS-G) | Low | Decide the notification policy during R2 planning |
| SL4 | Prompt-adjustment dashboard suggestions are deferred to v2: the guardian suggestion dashboard surfaces requests but does not yet feed prompt tuning | story-lifecycle-redesign.md Open item 4 (WS-F) | Low | Design the prompt-adjustment loop in v2 |
| SL5 | WS-D deferred an enum-derived CHECK constraint on the event-log kind column and a `request_approved`-authored-path event | WS-D PR #168 review | Low | Add the CHECK constraint and the missing event once the taxonomy stabilizes (see SL2) |
| SL6 | WS-E deferred guardian full-blob catalog scope confirmation, catalog pagination, and issue #173 (make `StoryRequest.family_id` nullable for catalog-origin requests) | WS-E PR #180 review | Low | Confirm catalog scope, add pagination, and land #173's schema change |
| SL7 | WS-F deferred suggestion-dashboard scaling (compute-on-read cost of three whole-corpus reads per page view) and a `schemas.py` type-annotation batch | WS-F PR #176 review | Low | Address dashboard scaling in a follow-up pass, and batch the schemas.py type-layer tightening into a separate follow-up (touches the OpenAPI client) |
| SL8 | WS-G deferred test/perf/architecture follow-ups F11-F23 (worker-path integration test for embed-failure rollback, budget-over-limit embed test, multi-version sibling selection, chain-loading perf caps, ordering data-flow doc, grandfather sunset/backfill plan, re-embed path) | WS-G PR #184 Fix Summary (issuecomment-4935226310) | Low | Pull the test-gap items regardless of usage; revisit the perf caps as series usage grows |
| SL9 | WS-G v2 declared-export block: the annotated-variables plus validator-checked-import escalation, the known fallback if reader-side name-matched variable seeding proves too weak; out of WS-G v1 scope | WS-G design decision G3 | Info | Implement only if name-matching proves insufficient in practice |
| SL10 | WS-G reader v1 carry-state limits: RESTART on a continued book drops carried state (M1), and a hard refresh before the first save loses the location-state seed | WS-G PR #192 body | Low | Persist the continuation seed (for example, to IndexedDB), and decide whether RESTART should preserve or intentionally drop carried state |

Adjacent tooling deferrals surfaced alongside this workstream (not part of the redesign itself):

- Codecov Bundle Analysis is deferred (issue #172).
- Promotion of the Postman collection to a required CI gate is deferred (issue #187).

## Bookkeeping

- The SDD ledgers backing this register: story-requests-kid-ui and playwright-e2e ledgers are preserved
  verbatim in this register's source PRs; other worktree ledgers were consolidated via the review-session
  memory notes before their worktrees were removed.
- Local e2e Postgres container `cyo-e2e-real-db` (port 5443) may still be running from the PR #112
  session; stop it when no real-tier work is active.
