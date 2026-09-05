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

> **Superseded reference (2026-09-04):** `cross-device-e2e.yml` no longer exists. Its job moved into
> `ci.yml` as the `cross-device-e2e` job and is now a required check via `ci-gate`, rather than the
> informational standalone workflow described below. The references that follow are preserved as
> written on 2026-08-27 for the audit trail; read them as historical, not as current state.

Companion to
[user-side-testing-module-proposal-2026-08-27.md](user-side-testing-module-proposal-2026-08-27.md), which holds
the full process inventory and the external-recommendation comparison. This document adds what a review of the
actual workflow runs against `main` found on 2026-08-27, and turns everything discovered into one sequenced
plan. The through-line of the findings: the merge gate is healthy, the scheduled ladder is not, and a month of
tolerated red has been quietly converting real signal into noise.

## 1. Findings: state of the runs against main (2026-08-27)

**The merge gate is green; the wider push tier is not.** The 2026-08-26 merge of #764 passed all four checks
GitHub actually enforces on `main` (`Security Gate Validation`, `Dependency & Standards Validation`,
`Check REUSE Compliance` from the `ByronWilliamsCPA-default-branch-baseline` ruleset, and `CI Gate` from
`cyo-require-ci-gate`). Two non-required checks failed on that same commit `b2273a71`: Container Vulnerability
Scan (Trivy) in the merge queue's own pre-merge run, and SonarCloud Code Analysis twice just after the merge
landed. Neither blocked the merge, and the Trivy red is a known chronic condition, but "the required set" is
four checks and not the eight workflows that happen to run on a push, so do not read a green merge as a green
push tier. The problems below are all in the scheduled tier.

### The nightly real-backend E2E has been red every day for over a month, and is one fix from green

`e2e-real-nightly.yml` has failed on every scheduled run from 2026-07-28 through today, the last green being
2026-07-27 (issue #290 has collected 36 daily bot comments since 2026-07-19). Sampling the runs shows this is
a burn-down, not a plateau:

| Run date | Failures | Failing specs |
| --- | --- | --- |
| 2026-08-15 | 10 failed / 46 passed | authored-request (x2), contract-smoke, full-pipeline-negative, kid-go-back, kid-read-aloud, more |
| 2026-08-23 | 3 failed / 53 passed (+2 flaky) | kid-flag, kid-go-back, offline-reconnect; offline-online-parity and a second offline-reconnect case passed on retry |
| 2026-08-25 | 5 failed / 52 passed | authoring-plan, kid-go-back, offline-reconnect, series-continue (x2) |
| 2026-08-26 | 1 failed / 57 passed | kid-go-back |
| 2026-08-27 | 1 failed / 57 passed | kid-go-back |

The recent fixes (#724 and #761) genuinely worked: series-continue, offline-reconnect, parity, and the
save-concurrency failures are gone. (#763 is not among them: it fixed the Google sign-in loop and sign-out
killing every device, which is unrelated to this tier.)

**One spec remains, and it is a regression with a one-day onset window, not an unproven assertion.**
`e2e-real/kid-go-back-real.spec.ts` fails at line 140, the `expect(savedRow.current_node).toBe('n_pools')`
assertion; line 99 is the `test(...)` declaration Playwright cites as the locator. The symptom is as follows:
after two real choices the kid taps go-back, the reading-state PUT returns 200, and the returned row's
`current_node` is still `n_crab` where the spec expects the reverted `n_pools`. It fails deterministically,
both attempts, every night, under two seconds in.

What matters for diagnosis is the history, which is the opposite of "never passed":

- The spec landed **2026-07-23** in #369 (`259421fa`), not 2026-08-14.
- It **passed every nightly it ran in from 2026-07-24 through 2026-08-06**, 12 of 12 sampled, including the
  nights from 07-28 onward when the workflow was red overall for other specs.
- It has failed **every night from 2026-08-07** through today, 21 consecutive nights.
- The onset window is therefore one day wide: between the 08-06 nightly (11:42 UTC) and the 08-07 nightly
  (10:28 UTC). Exactly eight commits landed on `main` in it, and one of them, `f68c4f71` (#635,
  "make PL-25's first-decision floor blocking and fix the catalog"), **modified the very fixture this spec
  walks**, `tests/fixtures/storybook/valid/06_tier1_tide_pools.json`. That file had not been touched since
  2026-06-25. The change moved `start_node` from `n_start` to `n_open` and inserted an establishing prelude,
  because PL-25 now requires the first decision to land at least two nodes in.

That prelude is already documented inside the spec itself: the comment above line 146 records that the
recorded path now starts at `n_open`, and line 146's path assertion was updated to
`['n_open', 'n_start', 'n_pools']` accordingly, while the line-140 `current_node` assertion was not
re-derived. So part of the spec was migrated for #635 and part was not.

This does not settle which side is wrong, but it removes one of the two readings and gives the other a
starting point. The remaining question is narrower: did #635's inserted prelude change what the reader
persists on a go-back, or change which save the spec's `waitForReadingStatePut` helper catches? Both are
answerable from the 08-06-to-08-07 diff rather than from first principles:

- **A real product defect exposed by the new graph shape**: a kid's go-back is not persisted (or is persisted
  then overwritten), so a reload or second device bounces the reader forward again. This is a kid-facing
  state-integrity bug, exactly the class the nightly tier exists to catch. If so, it has been live since
  2026-08-07, not "the whole time".
- **A partially-migrated spec**: the mocked-tier `reader-go-back.spec.ts` asserts only UI state
  (button visibility, rendered node), never the persisted PUT payload, so the real-backend spec is the only
  place the persisted-row contract after go-back is pinned. Note that the coverage matrix's `#ASSUME` about
  these specs shipping verified by tsc/ESLint/`--list` only does **not** apply here: this one ran live and
  green 12 nights running, so the question is not whether it was ever exercised but whether #635 moved the
  ground under it. If the helper is now catching a different save than assumed (a trailing save of the
  pre-back state, plausible once the graph gained a node), the spec's model of the save pipeline is what
  needs updating, not the product.

Either way the exit is the same: decide which side is wrong from the code (`Reader.tsx` go-back path,
`ReaderPage.tsx` persist pipeline as rewritten by #761, `player/` state), fix that side, and pin the resolved
contract at BOTH tiers (add the missing persisted-PUT assertion to the mocked spec so the contract cannot
silently regress to UI-only coverage again).

### The rest of the scheduled ladder, one line each

| Workflow | State on 2026-08-27 | Disposition |
| --- | --- | --- |
| E2E (production) | Failing since 2026-08-05 (#623), but not unbroken: scheduled runs on 08-24 and 08-25 both succeeded, then 08-26 failed again | Diagnose with the same run-log sampling used above; the two greens are the most informative runs in the series, so diff them against 08-23 and 08-26 first |
| E2E (staging) | Red on **every** scheduled run from 2026-08-04 through 2026-08-26, 23 consecutively; last green 08-03; no dedicated tracking issue observed | Not a one-off. This is a streak as long as the production one and the only long-red tier with no bot issue filed at all, so nothing has been nagging about it; treat at the same urgency as e2e-prod and check the fail-closed leak sweep too |
| Semantic Release | Failed 2026-08-27 02:40 (#765) | Runbook section 7.2 names this signature: a version/tag desync deadlocks `propose` while later runs still report success; verify tag sync first |
| KWS delivery health | 3 failures on 08-26, then green twice (#766) | Confirm recovery, then close #766 |
| Accessibility weekly | Succeeded 2026-08-19 and 2026-08-26; only failure was 08-12 | #700 is closable now: two consecutive greens already exist, and the issue has zero comments |
| Container Security | Failed 2026-08-26 07:36 | Triage (likely scanner findings or registry pull; not user-facing) |
| Mutation testing weekly | #302 open since 07-19 | Keep, low priority relative to the above |
| Database backup | Cancelled 08-26, still pending at 11:23 UTC today (schedule is 08:00) | Investigate with Notification digest below; a backup that silently stops running is #667 all over again |
| Notification digest | Cancelled 08-26, waiting today | Same symptom, same day as the backup: suspect a shared cause (runner capacity, concurrency group, or environment approval), not two coincidences |

### The process finding underneath the individual failures

Every scheduled workflow dutifully files or updates one tracking issue, and that pattern demonstrably did not
drive action: #290 accumulated 36 daily "failed again" comments, each carrying only a run link (no failing
spec names), while the failure composition underneath changed week to week. The bot comments made the streak
easy to ignore and expensive to interrogate (diagnosing this morning's failure required downloading run-log
archives). Two cheap mechanical fixes follow in WS-A7.

## 2. The plan

Four workstreams, ordered by a single principle: **restore trust in the existing signal before adding new
signal.** A red ladder swallows every new tier added on top of it.

### WS-A: Make the scheduled ladder trustworthy (first, ahead of everything)

| Item | Action | Exit criterion |
| --- | --- | --- |
| A1 | Fix `kid-go-back-real.spec.ts:140`. Start from the 08-06-to-08-07 onset window and specifically from #635 (`f68c4f71`), which reshaped the tide-pools fixture this spec walks; decide whether the inserted `n_open` prelude changed what the reader persists on go-back or which save the helper catches, then fix that side and pin the resolved persisted-row contract in the mocked tier too | Nightly green; contract asserted at both tiers; the onset commit named in #290 |
| A2 | Diagnose e2e-prod (#623) from its run logs; fix or re-scope | e2e-prod green or a dated decision recorded on #623 |
| A3 | Work the e2e-staging streak (23 consecutive failures from 08-04): file the tracking issue that was never opened, then diagnose from the 08-03-to-08-04 boundary; verify the leak-sweep result | Staging green or tracked with owner |
| A4 | Work #765 per runbook 7.2 (check `pyproject.toml` version vs tags; unblock `propose`) | A release PR opens on the next scheduled run |
| A5 | Investigate the backup + digest stuck pair as one incident (both cancelled 08-26, both queued today) | Both run to completion on schedule |
| A6 | Close the recovered issues: #700 now (two consecutive a11y greens already banked) and #766 after one more clean KWS cycle | Open e2e-alert/ci-failure issues describe only live failures |
| A7 | Fix the alerting mechanics: scheduled-failure comments must include the failing test names (the Playwright summary lines), and a red streak of 3+ consecutive runs escalates (a weekly scheduled-health rollup listing every red scheduled workflow, so one glance shows the ladder) | The next streak is visible in one place and names its specs |

### WS-B: User-side module and engine expansion (after A1, can overlap A2-A7)

| Item | Action | Source |
| --- | --- | --- |
| B1 | Build usersim leg A phase 1: seeded invariant walk on the mocked tier (clean console, no dead ends, loading resolves, overflow, isolation canaries, history safety), informational workflow | Proposal section 3, phase 1 |
| B2 | Engine expansion: a `webkit-kid` PR-path project (reader, library, offline, read-aloud specs on WebKit, the engine iPads actually use) in its own CI job, plus full mocked suite on WebKit and Firefox nightly, informational, excluding visual snapshots and axe | **No documented source.** Not proposed anywhere in the companion proposal, whose only WebKit/Firefox mention describes the already-shipped, already-informational `cross-device-e2e.yml`. B2 is also the sole WS-B item that adds work to the per-PR path, the thing ADR-029 constrains, so it needs either a written rationale in the proposal or removal from this plan before it is picked up |
| B3 | Leg A real-tier nightly variant plus axe-on-new-states (placement per the open question in the proposal's leg A section) | Proposal phase 2 |

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
| D4 | Load testing (k6) | Deferred to Track 2 hardening |
| D5 | DAST (ZAP baseline vs staging) | After the module lands, per the proposal: authenticated scanning needs the same seeded-credential and concurrency discipline as e2e-staging. Earlier than D4, not bundled with it |

## 3. Success criteria

- `e2e-real-nightly` green for 7 consecutive runs, and #290 closed with the go-back root cause and its
  onset commit linked.
- No scheduled workflow red for more than 3 consecutive runs without a named owner and a dated comment.
- The scheduled-health rollup exists and lists zero unexplained reds.
- usersim phase 1 merged, producing findings in its JSONL contract, with at least one finding promoted to a
  deterministic regression spec plus coverage-matrix row (proving the triage loop end to end).
- The `webkit-kid` project runs per PR within budget, and the WebKit/Firefox nightly has completed its first
  week with its findings triaged.

Execution note: items accepted from WS-B/C/D should enter the normal planning flow (unscheduled-work-register
rows or issues per the linkage contract) when picked up; this document is the plan of record for sequencing,
not a tracking surface.
