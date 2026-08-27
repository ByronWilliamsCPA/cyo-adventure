---
title: "Testing Improvement Plan"
schema_type: common
status: draft
owner: core-maintainer
purpose: "Actions-health findings for main's scheduled test ladder and a sequenced plan to improve testing."
tags:
  - testing
  - evaluation
---

Companion to
[user-side-testing-module-proposal-2026-08-27.md](user-side-testing-module-proposal-2026-08-27.md), which holds
the full process inventory and the external-recommendation comparison. This document adds what a review of the
actual workflow runs against `main` found on 2026-08-27, and turns everything discovered into one sequenced
plan. The through-line of the findings: the merge gate is healthy, the scheduled ladder is not, and a month of
tolerated red has been quietly converting real signal into noise.

## 1. Findings: state of the runs against main (2026-08-27)

**Push-triggered CI is green.** The 2026-08-26 merge of #764 ran the full required set (CI, Security Analysis,
Python Compatibility, FIPS, REUSE, Scorecard, Docs, Cruft) and everything passed. The problems are all in the
scheduled tier.

### The nightly real-backend E2E has been red every day for over a month, and is one fix from green

`e2e-real-nightly.yml` has failed on every scheduled run from at least 2026-07-29 through today (issue #290
has collected daily bot comments since 2026-07-18). Sampling the runs shows this is a burn-down, not a plateau:

| Run date | Failures | Failing specs |
| --- | --- | --- |
| 2026-08-15 | 10 failed / 46 passed | authored-request (x2), contract-smoke, full-pipeline-negative, kid-go-back, kid-read-aloud, more |
| 2026-08-23 | 3 failed / 53 passed | kid-flag, kid-go-back, offline-online-parity, offline-reconnect |
| 2026-08-25 | 5 failed / 52 passed | authoring-plan, kid-go-back, offline-reconnect, series-continue (x2) |
| 2026-08-26 | 1 failed / 57 passed | kid-go-back |
| 2026-08-27 | 1 failed / 57 passed | kid-go-back |

The recent fixes (#724, #761, #763) genuinely worked: series-continue, offline-reconnect, parity, and the
save-concurrency failures are gone. **One spec remains, and it has never passed at this tier**:
`e2e-real/kid-go-back-real.spec.ts:99` has failed on every nightly since the spec landed on 2026-08-14,
deterministically (both attempts, every day, ~1.5s in): after two real choices (n_pools then n_crab), the kid
taps go-back, the reading-state PUT this triggers returns 200, and the returned row's `current_node` is still
`n_crab` where the spec expects the reverted `n_pools`.

Two readings are possible, and adjudicating them is the single highest-value testing task open right now:

- **A real product defect**: a kid's go-back is not persisted (or is persisted then overwritten), so a reload
  or second device bounces the reader forward again. This is a kid-facing state-integrity bug that has been in
  production the whole time, exactly the class the nightly tier exists to catch.
- **A spec authored against assumed behavior**: the mocked-tier `reader-go-back.spec.ts` asserts only UI state
  (button visibility, rendered node), never the persisted PUT payload, so the real-backend spec is the only
  place the persisted-row contract after go-back is pinned, and it was written without a live run (the
  coverage matrix's own `#ASSUME` records that these specs shipped verified by tsc/ESLint/`--list` only). If
  the reader intentionally persists go-back lazily (on the next action) or the helper is catching a different
  save than assumed (a trailing save of the pre-back state), the spec's model of the save pipeline is wrong,
  not the product.

Either way the exit is the same: decide which side is wrong from the code (`Reader.tsx` go-back path,
`ReaderPage.tsx` persist pipeline as rewritten by #761, `player/` state), fix that side, and pin the resolved
contract at BOTH tiers (add the missing persisted-PUT assertion to the mocked spec so the contract cannot
silently regress to UI-only coverage again).

### The rest of the scheduled ladder, one line each

| Workflow | State on 2026-08-27 | Disposition |
| --- | --- | --- |
| E2E (production) | Red since 2026-08-05 (#623, last failure 08-26) | Diagnose with the same run-log sampling used above; three weeks without production smoke is its own risk |
| E2E (staging) | Failed 2026-08-26 13:22, no dedicated tracking issue observed | Triage: one-off vs new breakage; check the fail-closed leak sweep too |
| Semantic Release | Failed 2026-08-27 02:40 (#765) | Runbook section 7.2 names this signature: a version/tag desync deadlocks `propose` while later runs still report success; verify tag sync first |
| KWS delivery health | 3 failures on 08-26, then green twice (#766) | Confirm recovery, then close #766 |
| Accessibility weekly | Succeeded 2026-08-26 | #700 is likely closable; confirm one more green run |
| Container Security | Failed 2026-08-26 07:36 | Triage (likely scanner findings or registry pull; not user-facing) |
| Mutation testing weekly | #302 open since 07-19 | Keep, low priority relative to the above |
| Database backup | Cancelled 08-26, still pending at 11:23 UTC today (schedule is 08:00) | Investigate with Notification digest below; a backup that silently stops running is #667 all over again |
| Notification digest | Cancelled 08-26, waiting today | Same symptom, same day as the backup: suspect a shared cause (runner capacity, concurrency group, or environment approval), not two coincidences |

### The process finding underneath the individual failures

Every scheduled workflow dutifully files or updates one tracking issue, and that pattern demonstrably did not
drive action: #290 accumulated ~40 daily "failed again" comments, each carrying only a run link (no failing
spec names), while the failure composition underneath changed week to week. The bot comments made the streak
easy to ignore and expensive to interrogate (diagnosing this morning's failure required downloading run-log
archives). Two cheap mechanical fixes follow in WS-A7.

## 2. The plan

Four workstreams, ordered by a single principle: **restore trust in the existing signal before adding new
signal.** A red ladder swallows every new tier added on top of it.

### WS-A: Make the scheduled ladder trustworthy (first, ahead of everything)

| Item | Action | Exit criterion |
| --- | --- | --- |
| A1 | Adjudicate and fix `kid-go-back-real.spec.ts:99` (product defect vs wrong spec assumption, per section 1); pin the resolved persisted-row contract in the mocked tier too | Nightly green; contract asserted at both tiers |
| A2 | Diagnose e2e-prod (#623) from its run logs; fix or re-scope | e2e-prod green or a dated decision recorded on #623 |
| A3 | Triage the 08-26 e2e-staging failure; verify the leak-sweep result from that run | Staging green or tracked with owner |
| A4 | Work #765 per runbook 7.2 (check `pyproject.toml` version vs tags; unblock `propose`) | A release PR opens on the next scheduled run |
| A5 | Investigate the backup + digest stuck pair as one incident (both cancelled 08-26, both queued today) | Both run to completion on schedule |
| A6 | Close the recovered issues: #700 (a11y weekly green), #766 (KWS health green twice) after one more clean cycle | Open e2e-alert/ci-failure issues describe only live failures |
| A7 | Fix the alerting mechanics: scheduled-failure comments must include the failing test names (the Playwright summary lines), and a red streak of 3+ consecutive runs escalates (a weekly scheduled-health rollup listing every red scheduled workflow, so one glance shows the ladder) | The next streak is visible in one place and names its specs |

### WS-B: User-side module and engine expansion (after A1, can overlap A2-A7)

| Item | Action | Source |
| --- | --- | --- |
| B1 | Build usersim leg A phase 1: seeded invariant walk on the mocked tier (clean console, no dead ends, loading resolves, overflow, isolation canaries, history safety), informational workflow | Proposal section 3, phase 1 |
| B2 | Engine expansion: a `webkit-kid` PR-path project (reader, library, offline, read-aloud specs on WebKit, the engine iPads actually use) in its own CI job, plus full mocked suite on WebKit and Firefox nightly, informational, excluding visual snapshots and axe | Browser-expansion discussion |
| B3 | Leg A real-tier nightly variant plus axe-on-new-states in the weekly a11y slot | Proposal phases 2 |

B2's PR-path slice is deliberately after A1: WebKit will surface real engine differences in exactly the
reader/offline code A1 touches, and those findings should land on a green baseline.

### WS-C: Story-QA adoptions from the external recommendation (parallel to WS-B, LLM budget permitting)

| Item | Action | Guardrail |
| --- | --- | --- |
| C1 | Comprehension-probe offline pilot over the committed corpus (question generation by one model, answerability judged by another) | Measured before believed: promotion requires precision materially better than continuity.py's recorded 1-in-6 |
| C2 | Define the fixed age-banded reader persona set (shared by leg B UI runs and story-experience walks) | Personas are fixtures, versioned in-repo |
| C3 | Calibration analysis job: join Stage-4 engagement advisories and validator statistics with aggregated real reading outcomes per storybook, feeding flywheel strategy | ADR-018 privacy review first; aggregate-only, per-storybook, no new collection |

### WS-D: Remaining gaps and deliberately deferred items

| Item | Action | Timing |
| --- | --- | --- |
| D1 | Lighthouse CI weekly with LCP/INP/CLS and bundle budgets, informational, single tracking issue | After WS-B lands |
| D2 | Leg B agentic persona runner (`workflow_dispatch` first, weekly once verdicts are trusted) | After C2 |
| D3 | Leg C first-party friction beacon plus digest | Gated on its ADR; build last |
| D4 | Load testing (k6) and DAST (ZAP baseline vs staging) | Deferred to Track 2 hardening |

## 3. Success criteria

- `e2e-real-nightly` green for 7 consecutive runs, and #290 closed with the go-back adjudication linked.
- No scheduled workflow red for more than 3 consecutive runs without a named owner and a dated comment.
- The scheduled-health rollup exists and lists zero unexplained reds.
- usersim phase 1 merged, producing findings in its JSONL contract, with at least one finding promoted to a
  deterministic regression spec plus coverage-matrix row (proving the triage loop end to end).
- The `webkit-kid` project runs per PR within budget, and the WebKit/Firefox nightly has completed its first
  week with its findings triaged.

Execution note: items accepted from WS-B/C/D should enter the normal planning flow (unscheduled-work-register
rows or issues per the linkage contract) when picked up; this document is the plan of record for sequencing,
not a tracking surface.
