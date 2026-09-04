---
title: "Testing Implementation Plan"
schema_type: common
status: published
owner: core-maintainer
purpose: "Task-level implementation plan executing the WS-A through WS-D program defined by PR #768's two testing documents."
tags:
  - testing
  - ci_cd
  - quality
---

> **Superseded reference (2026-09-04):** `cross-device-e2e.yml` no longer exists. Its job moved into
> `ci.yml` as the `cross-device-e2e` job and is now a required check via `ci-gate`, rather than the
> informational standalone workflow described below. The references that follow are preserved as
> written on 2026-08-27 for the audit trail; read them as historical, not as current state.

This document executes the program defined by PR #768
([testing-improvement-plan-2026-08-27.md](testing-improvement-plan-2026-08-27.md) and
[user-side-testing-module-proposal-2026-08-27.md](user-side-testing-module-proposal-2026-08-27.md)). Those two
documents establish *what* to do and *in what order*; this one establishes *how*, at the level of files,
commands, acceptance criteria, and register rows.

Read it alongside them, not instead of them. Where this document contradicts either source, section 2 says so
explicitly and gives the evidence, because a plan that silently overwrites its own source is how a corrected
fact gets lost again.

## 0. Execution status as of 2026-08-30

This plan was written on 2026-08-27 and merged on 2026-08-30. Most of it was executed in the
interval, principally by [#780](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/780) (134
files, 25,814 lines changed). Every `+N` figure in this section is `git diff --stat`'s combined
additions-plus-deletions for that path, not additions alone.

It is merged as the record of *how* the program was specified, not as a queue of pending work. The
task detail below is preserved as written, with one class of exception: where the detail would send a
reader to do something now wrong, it is corrected in place and the correction is marked. Those are the
ADR identifier for D3, the step 1 line references, the step 4 mocked-tier snippet, the D2a migration,
and the whole of section 9. Everything else stands unedited so the specification and the result stay
comparable.

Verified against `main` at `6cc33aa5`, with the status column re-checked against live CI and issue
state on 2026-08-30 rather than tree presence alone. A file existing proves a task was implemented,
not that its acceptance criterion is met, and three rows below differ on exactly that distinction:

| Task | State | Evidence on `main` |
| --- | --- | --- |
| A1 nightly go-back | partial | Specs edited (`frontend/e2e-real/kid-go-back-real.spec.ts`, `frontend/e2e/reader-go-back.spec.ts`), but `e2e-real-nightly` is still red: 8 consecutive failures 2026-08-22 to 2026-08-29, on the same contested assertion. [#290](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/290) is open |
| A2 e2e-prod, A3 e2e-staging | done | `e2e-prod.yml` (+88), `e2e-staging.yml` (+286) |
| A4 release workflow | done | `release.yml` (+22) |
| A5a backup | partial | `supabase-backup.yml` ships and a first backup exists, but the acceptance bar below (two consecutive scheduled successes plus one recorded restore drill) is unmet: `docs/operations/restore-drill-log.md` still reads "No drill has been recorded yet" |
| A5b digest | not done | `notification-digest.yml:54` still declares `environment: production`, the exact line A5b exists to remove; runs 2026-08-25 to 2026-08-28 are `cancelled` and 2026-08-29 is `waiting` |
| A7 alerting mechanics | done | `scheduled-health-rollup.yml` plus `workflows/test/health-rollup.test.mjs` |
| B1, B3 usersim legs | done | `frontend/e2e-usersim/` (`walk.spec.ts`, `walk-real.spec.ts`, `walk-a11y.spec.ts`) |
| B2 `webkit-kid` per DR-2 | done | `frontend/playwright.config.ts:369`, nightly-only as ruled |
| I7 in the weekly a11y slot per DR-1 | done | `tests/unit/test_a11y_weekly_i7_flag_contract.py` |
| C1 comprehension probe | done | `scripts/comprehension_probe.py` |
| C2 fixed reader persona set | done | `schema/personas/reader_personas.json` |
| C3 calibration loop | done | `src/cyo_adventure/analysis/engagement_correlation.py`, `engagement-correlation.yml` |
| D1 Lighthouse weekly | done | `.github/workflows/lighthouse-weekly.yml`, which cites this document by path |
| D2 agentic persona runner | partial | `.claude/skills/naive-ux-check/` with `scenarios.json` and `render.py` |
| D3 friction beacon | designed, not built | `docs/planning/adr/adr-031-first-party-friction-beacon.md` |
| D4 load testing (k6) | deferred by decision | No k6 artifact in the tree, and none is due: `UW-F54` on `main` records the ruling that a homelab-measured figure is worse than no figure |
| D5 DAST baseline | done | `.github/workflows/dast-baseline-weekly.yml`, whose header cites this document by task id |

A6 (close the recovered issues) is issue-state, not repository state, and is not assertable from a
tree scan. Nothing in this program is now unaccounted for: D4 is deferred by a recorded decision
(`UW-F54`), D3 is specified but unbuilt, and A1 and A5 are the two rows where the work landed but the
acceptance bar did not.

Merging this document also repairs two references that shipped ahead of their referent:
`.github/workflows/lighthouse-weekly.yml:3` and `frontend/playwright.config.ts:435` both cite
`docs/testing/testing-implementation-plan-2026-08-27.md` by exact path, and until now that path
did not exist on `main`.

## 1. Decisions of record

Three decisions were open when PR #768 merged. All three are now settled and are binding on the tasks below.

| ID | Decision | Ruling | Consequence |
| --- | --- | --- | --- |
| DR-1 | Where invariant I7 (axe on newly reached states) runs | `accessibility-compliance-weekly.yml`, gated behind `A11Y_EXTENDED=1` | The proposal's option 2. Matches `CLAUDE.md`'s operative wording verbatim and satisfies ADR-029's Constraints. No new a11y workflow. Leg A findings therefore split across two workflows by design, and the JSONL contract must carry a `workflow` field so they rejoin at triage |
| DR-2 | Disposition of B2 (`webkit-kid` Playwright project) | Keep, but **nightly-only and informational**. It does not enter the per-PR path | Removes the ADR-029 scope argument entirely, since the merge gate is untouched. The missing rationale must still be written into the proposal, because B2 shipped with none |
| DR-3 | Depth of this plan | Task-level detail for all 18 items | Items gated on an unwritten ADR or an unmade budget decision are specified under stated assumptions and tagged with RAD markers. Their detail is a design, not a commitment |

`#ASSUME: data-integrity: the task-level detail for WS-C and WS-D items is written against the current
architecture and the current privacy posture, both of which may move before those items are picked
up. #VERIFY: re-read sections 6 and 7 against the then-current ADR set before starting any WS-C or WS-D
item; treat a contradiction as a signal to re-plan that item, not to force the plan through.`

## 2. Corrections to the source documents

These were established by re-verifying the source documents' factual claims against live GitHub state and git
history on 2026-08-27. Five claims moved. Each correction changes the task it belongs to, so the corrections
come before the tasks.

### C-1: WS-A4 is not a tag desync (REFUTED)

The source plan routes #765 to runbook section 7.2, the version/tag desync deadlock. That deadlock is not
live. `pyproject.toml` on `origin/main` read `0.84.0` when this was written and reads `0.85.0` at merge;
the matching tag exists on `origin` in both cases, and `git merge-base --is-ancestor v0.84.0 origin/main`
succeeds. The workflow is genuinely red, but the current
failure in the `Propose Release PR` job is:

```text
type object 'Actor' has no attribute 'name_email_regex'
```

That is a GitPython / python-semantic-release API incompatibility, not a repository state problem. The 08-17
tag desync referenced in #765's body was resolved; the same issue number now tracks a different root cause.
Task A4 is rewritten accordingly.

This is a textbook instance of a detection literal outliving its cause: the runbook signature still matched the
*symptom* (release workflow red) after the *mechanism* had moved.

### C-2: WS-A5 is two incidents, not one (PARTIALLY REFUTED)

The source plan asks to investigate the database backup and the notification digest as one incident on the
theory of a shared cause. They no longer share one.

- `supabase-backup.yml` already migrated off `environment: production` onto a dedicated `environment: backups`
  with no protection rules, and its own header comments record why: the reviewer gate silently ate three of
  the four runs preceding 2026-08-11. Its 2026-08-27 scheduled run executed and failed for a real reason
  (tracked by #667), plus three manual dispatch failures the same day.
- `notification-digest.yml` still declares `environment: production`, and its 2026-08-27 scheduled run was
  still in `waiting` at audit time.

So the digest has the disease the backup already recovered from, and the backup has a new, unrelated one. A5
is split into A5a and A5b, and A5b has a proven in-repo fix precedent rather than an investigation.

### C-3: the go-back onset story is half wrong, and the mechanism is now known (REFINED)

The source plan states that #635 updated the spec's path assertion at line 146 while leaving the `current_node`
assertion at line 140 un-re-derived, i.e. a partial migration. Git refutes the migration story:
`git log origin/main -- frontend/e2e-real/kid-go-back-real.spec.ts` returns exactly two commits, `259421fa`
(#369, the spec's birth) and `c071c3dc` (#761, 2026-08-25). The path assertion came from #761, eighteen days
*after* onset, and that commit's message asserts line 140 "was already correct and passes unchanged."

The plan's onset commit is nevertheless correct, and the mechanism now follows from it. `f68c4f71` (#635)
changed the fixture's `start_node` from `n_start` to `n_open` and inserted a single-choice prelude node. Under
ADR-026 flowed reading, a single-choice node flows through silently, so **mount now emits two reading-state
PUTs** (`n_open`, then `n_start`) where it previously emitted one. This is independently pinned by
`frontend/src/reader/ReaderPage.test.tsx`, which asserts at most two saves on mount for this story shape.

The spec's helper is order-blind and content-blind:

```ts
function waitForReadingStatePut(page: Page) {
  return page.waitForResponse(
    (res) =>
      res.url().includes('/api/v1/reading-state/') &&
      res.url().includes(STORYBOOK_ID) &&
      res.request().method() === 'PUT',
    { timeout: 10_000 }
  )
}
```

It resolves on whichever matching PUT lands next, with no correlation to the action that caused it. One extra
mount save shifts every subsequent wait by exactly one position, so `backSave` observes the second choice's
save (`current_node: 'n_crab'`) while the real go-back save (`n_pools`) is still queued behind it. That
accounts for every observed symptom: HTTP 200 on a legitimate save, exactly `n_crab` rather than corruption,
full determinism, sub-two-second failure, and passing UI assertions (which read React state, not the network).

Supporting evidence that the product side is sound:

- `player/engine.ts::back()` replays `path` and returns the second-to-last state, which for
  `[n_open, n_start, n_pools, n_crab]` is the `n_pools` state.
- `Reader.tsx` computes `goBackSteps` from the flowed stop; at `n_crab` (two choices) that is 1, so exactly
  one `BACK` is dispatched. No double revert.
- `api/reading.py::put_reading_state` and `player/replay.py::validate_reading_state` enforce only revision
  based optimistic concurrency and replay validity. Nothing rejects a backwards `current_node`, so a genuine
  `n_pools` save would persist as `n_pools`.

**Working verdict: spec defect.** It is not yet proven, and A1 step 1 is the experiment that proves it rather
than an argument that assumes it.

### C-4: the mocked tier cannot regress-guard this contract (VERIFIED, and worse than stated)

The source plan says `frontend/e2e/reader-go-back.spec.ts` asserts only UI state. Confirmed, and the reason is
structural: it routes `**/api/v1/reading-state/**` to `route.fulfill({ status: 200, json: READING_ROW })`
unconditionally, never reading the request body. It cannot detect a persisted-payload defect even in
principle, so "add an assertion" there means "add request-body capture first."

### C-5: three infrastructure assumptions in the proposal do not hold (NEW)

| Proposal assumption | Reality | Effect |
| --- | --- | --- |
| I1 reuses existing console-error handling | No `pageerror` or `console.error` listener utility exists anywhere in the frontend suites | I1 is net-new code plus an allowlist file, not a wiring job |
| Leg B automates the naive-ux scenario set | The 17 scenarios exist only as markdown prose under `.claude/skills/naive-ux-check/prompts/{kid,guardian,admin}.md`, keyed by headings such as `## K0: ...`. There is no machine-readable form | Leg B gains a mandatory prerequisite: migrate the scenario set to structured data. Specified as D2a |
| A route manifest sync test is new work | `frontend/src/router.test.tsx` already imports the `routes` array and walks it structurally, with a positive control | The sync test copies an existing, proven pattern instead of inventing one |

One further trap, not an assumption but an omission: `scripts/check_coverage_matrix.py` scans exactly
`frontend/e2e/`, `frontend/e2e-real/`, `frontend/e2e-staging/`, `frontend/e2e-prod/` and
`frontend/src/**/*.test.{ts,tsx}`. A new `frontend/e2e-usersim/` directory is invisible to it. The tier would
ship outside the very drift guard that exists to catch untracked specs unless the scan set is extended in the
same PR.

## 3. Execution model

Rules that apply to every task below, stated once.

**Branching.** One feature branch per task or per tightly coupled task pair, named per the convention table in
`CLAUDE.md` (`fix/` for A1 to A5, `feat/` for B and C items, `chore/` for A6 and A7 tooling, `docs/` for
document-only steps). Never work on `main`. Use `.worktrees/<branch-slug>` when two tasks run concurrently,
and run `uv sync --all-extras` in each new worktree, since worktrees share git but not virtualenvs.

**Gates before every commit.** `pre-commit run --all-files`, and for backend changes the quality quartet from
`CLAUDE.md`. Note that a full `pytest` run dirties tracked files and `pre-commit run --all-files` dirties more;
that is known drift, not your change. Sign every commit with `-S`. Stage only the paths you touched.

**Register linkage is not optional.** Every task in this plan gets a row in
`docs/planning/unscheduled-work-register.md` before or with its first commit. `check_work_linkage.py` runs both
as a pre-commit hook and as the `Planning Linkage` CI workflow, and a row that carries a status without
evidence is an orphan that fails the build. Section 9 gives the exact rows.

**Informational first, always.** Every new workflow this plan adds starts non-gating and files exactly one
tracking issue, following the `cross-device-e2e.yml` and `e2e-real-pr-smoke.yml` posture. Promotion to gating
is a separate, explicit decision per leg, never a side effect of the workflow working well.

**The staging concurrency rule is a hard constraint.** `docs/testing/README.md` carries a `#CRITICAL` marker:
any additional automated workflow that authenticates against or mutates data on the shared staging Supabase
project must join the `e2e-staging` concurrency group before being enabled, or it races the device-grant
mint/revoke cycle and corrupts shared fixtures. This binds D2 and D5 directly.

**Label convention, settled here because the repo currently disagrees with itself.** `e2e-alert` for anything
that runs browser journeys (nightly, prod, staging, a11y weekly, usersim). `ci-failure` for everything else
(release, backup, digest, mutation, safety eval, container security). Record this in
`docs/testing/README.md` as part of A7 so the next workflow author does not have to guess.

## 4. WS-A: make the scheduled ladder trustworthy

This workstream is the critical path. Nothing in WS-B lands on a red ladder, per the source proposal's own
argument, because a new red among many reds is invisible.

### A1: fix the nightly go-back failure

The single item blocking `e2e-real-nightly` green. Section 2's C-3 establishes the working verdict; this task
proves it before acting on it.

**Step 1, the decisive experiment (do this first, do not skip to the fix).** Stand up the real stack per
`docs/testing/README.md`, then run the spec with the two contested assertions neutralised so execution reaches
the direct `GET` at line 169:

```bash
cd frontend
npm run test:e2e:real -- e2e-real/kid-go-back-real.spec.ts
```

Temporarily comment the two `savedRow` assertions (`expect(savedRow.current_node)` and
`expect(savedRow.path)`) for this run only, then read what the later `serverRow` `GET /reading-state`
check returns. Anchor on those identifiers rather than line numbers: this spec grew from 172 to 263 lines
after [#780](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/780), so the original line 140 now
holds an `Authorization` header and line 146 a fixture guard.

- Returns `n_pools`: the persisted end state is correct, the spec observed the wrong PUT, and the verdict is
  **spec defect**. Proceed to step 2a.
- Returns `n_crab`: the go-back is genuinely not persisted, and this is a live kid-facing state-integrity bug
  dating to 2026-08-07. Proceed to step 2b, and treat it as a production incident, not a test fix.

Record the observed value in #290 either way. This experiment is cheap and it is the difference between fixing
a test and fixing a product.

**Step 2a, spec defect path.** Correlate the wait with the action instead of with the URL. Change
`waitForReadingStatePut` at `frontend/e2e-real/kid-go-back-real.spec.ts:51-58` to accept a predicate over the
request body, so each wait names the save it expects:

```ts
function waitForReadingStatePut(
  page: Page,
  match?: (body: { current_node?: string; state_revision?: number }) => boolean
) {
  return page.waitForResponse((res) => {
    if (!res.url().includes('/api/v1/reading-state/')) return false
    if (!res.url().includes(STORYBOOK_ID)) return false
    if (res.request().method() !== 'PUT') return false
    if (!match) return true
    return match(res.request().postDataJSON())
  }, { timeout: 10_000 })
}
```

Then at each call site name the expected node: mount drains through `n_start`, the first choice expects
`n_pools`, the second expects `n_crab`, and the go-back expects `n_pools`. Matching on the request body rather
than the response makes the assertion independent of queue position, which is the actual defect.

Do not fix this by adding a timeout or a `waitForTimeout`. A sleep would make the spec pass by making the race
usually resolve the other way, which is how a deterministic failure becomes a flake.

**Step 2b, product defect path.** The fix sites are `frontend/src/reader/ReaderPage.tsx`'s `persist()` and its
`saveChainRef` serialization, or `frontend/src/reader/useFlowedStop.ts`'s derived-state sync. Both were
rewritten by #761; start from that diff.

**Step 3, class sweep (this is the part that prevents a recurrence).** The order-blind wait is a pattern, not
one line. Audit every spec in `frontend/e2e-real/` for the same shape:

```bash
grep -rn "waitForResponse" frontend/e2e-real/ frontend/e2e-staging/ frontend/e2e-prod/
```

Any wait that matches only on URL and method, in a flow where more than one such request can be in flight, has
the same latent defect and is one fixture change away from failing the same way. Fix or annotate each.

**Step 4, pin the contract at the mocked tier.** Per C-4, `frontend/e2e/reader-go-back.spec.ts` must first
capture request bodies before it can assert on them:

```ts
const puts: Array<Record<string, unknown>> = []
await page.route('**/api/v1/reading-state/**', async (route) => {
  if (route.request().method() === 'PUT') puts.push(route.request().postDataJSON())
  await route.fulfill({ status: 200, json: READING_ROW })
})

// ... drive the reader forward to n_crab ...

const before = puts.length
await page.getByTestId('go-back').click()
await expect.poll(() => puts.length).toBe(before + 1)
expect(puts[before].current_node).toBe('n_pools')
```

Correlate the assertion to the go-back action by index, as above. Do **not** assert that `puts` merely
*contains* `n_pools`: the first choice already sends `n_pools`, so a membership check passes when the go-back
PUT is wrong or absent entirely. That is the same order-blind shape step 3 sweeps for, and this step's own
first draft carried it, which is a fair measure of how easily the pattern reappears. Without an
action-correlated assertion the contract lives only in the nightly tier and silently regresses to UI-only
coverage again.

**Step 5, accounting.** Update `docs/testing/coverage-matrix.md`'s kid reading journey to cite the changed
specs. Comment on #290 with the onset commit (`f68c4f71`, #635), the mechanism, and the step-1 result.
Close #290 only after seven consecutive nightly greens, per the source plan's success criterion.

**Acceptance.** `e2e-real-nightly` green seven consecutive runs; the persisted go-back contract asserted at
both the mocked and real tiers; every other order-blind wait in the real tier fixed or annotated; #290 closed
citing the onset commit.

**Files.** `frontend/e2e-real/kid-go-back-real.spec.ts`, `frontend/e2e/reader-go-back.spec.ts`,
`docs/testing/coverage-matrix.md`, plus whatever step 3 surfaces.

### A2: diagnose e2e-prod (#623)

**What the audit established.** Failing since 2026-08-05, but not unbroken: the 08-24 and 08-25 scheduled runs
both genuinely succeeded (job executed, 26 specs passed in 3.1 minutes, verified not a skip artifact), and
08-26 failed again.

**Method.** The two greens are the most informative runs in the series, so diff around them rather than
reading the newest failure in isolation:

```bash
gh run list --workflow=e2e-prod.yml --limit 15 --json databaseId,conclusion,createdAt
gh run view <08-23-red-id> --log-failed | head -80
gh run view <08-26-red-id> --log-failed | head -80
```

Compare the failing spec names across 08-23 (red), 08-24 and 08-25 (green), 08-26 (red). If the failing spec
set differs between reds, this is environmental rather than a code defect.

**Correlate with what actually shipped.** Production currency has two reliable oracles and two anti-oracles in
this repo: the image `revision` label and the compose `config_files` label are authoritative; the `/health`
`version` field and the `:latest` tag are not. Check whether the 08-24 and 08-25 greens bracket a deploy.

**Acceptance.** e2e-prod green, or a dated decision recorded on #623 naming an owner and a re-scope. A red tier
with a written, dated decision is an acceptable outcome; a red tier with silence is not.

### A3: work the e2e-staging streak

**What the audit established.** 23 consecutive scheduled failures from 2026-08-04 through 2026-08-26, last
green 2026-08-03, and no tracking issue exists. The only staging-labelled open issue is #571, which predates
the streak and is unrelated.

**Step 1, find out why no issue was ever filed.** This is the more important half of the task. Every other
scheduled workflow files or updates exactly one tracking issue on failure via an inline
`actions/github-script` step. Read `.github/workflows/e2e-staging.yml` and determine whether that step is
absent, mis-conditioned (`if:` guard), or failing silently. A workflow that fails for 23 days without nagging
anyone is a monitoring defect that outranks whatever the specs are failing on, because it is the reason nobody
noticed.

**Step 2, add the missing alerting** using the same shape the nightly uses: search open issues labelled
`e2e-alert` for a title carrying the `[e2e-staging]` marker, comment if found, create if not. Per A7, include
the failing spec names in the body.

**Step 3, diagnose from the 08-03 to 08-04 boundary.** Enumerate what landed in that window, the same method
that resolved the go-back onset.

**Step 4, verify the leak sweep.** `playwright.e2e-staging-sweep.config.ts` runs a post-run device-grant
cleanup with `trace`, `screenshot` and `video` deliberately `off` because this is a public repo. Confirm the
sweep still runs and still passes; a 23-day-red tier may have left shared fixtures dirty, and dirty shared
fixtures are self-perpetuating.

**Acceptance.** Staging green, or tracked by a named owner with a dated decision. The alerting step exists and
is proven by a deliberate failure.

### A4: unblock the release workflow (#765), rewritten per C-1

**Do not follow runbook 7.2 for this.** The tag is in sync. The failure is:

```text
type object 'Actor' has no attribute 'name_email_regex'
```

**Method.** This is a dependency-surface break between python-semantic-release and GitPython. Reproduce
locally against the pinned versions, then resolve by bumping python-semantic-release to a release that
supports the current GitPython, or by constraining GitPython to the last version exposing that attribute.
Prefer the forward fix. Per `CLAUDE.md`, do not resolve it by disabling the step or bypassing the gate.

**Guard against silent recurrence.** `scripts/check_release_tag_sync.py` already guards the desync class. This
failure class (a dependency API break inside `propose`) is not guarded, and the pipeline's failure mode is
that it deadlocks while later runs still report success. Confirm the propose job fails loudly on this class.

**Update #765's body** so the issue describes its current cause rather than the resolved 08-17 desync. An issue
whose body describes a fixed problem is how the next reader wastes an hour.

**Acceptance.** A release PR opens on the next scheduled `propose` run. #765 closed or re-titled to its actual
cause.

### A5a: database backup real failure (#667)

The `environment: production` reviewer gate is already fixed for this workflow; it moved to
`environment: backups`. The 2026-08-27 scheduled run executed and failed for a real reason, alongside three
manual dispatch failures the same day.

**Method.** Read the failed run log. Known live hazards recorded for this workflow, to check first: the
`R2_ACCOUNT_ID` secret holds a shell line rather than an account id; R2 token permission classes are
account-wide so a denial lands after upload rather than before; and a bucket without the `.cyo-backup-bucket`
marker is refused by design.

**The larger point.** A first backup exists as of 2026-08-24, but **restore has never been tested and no
Actions run has succeeded**. Whatever the immediate failure is, the acceptance bar here includes the restore
drill from `docs/operations/runbook.md` section 6. A backup that has never been restored is a hypothesis.

**Acceptance.** Two consecutive scheduled backup runs succeed, and one restore drill completes and is recorded.

### A5b: notification digest stuck in waiting

**Cause, already known.** `notification-digest.yml` declares `environment: production`, whose required
reviewer gate leaves scheduled runs in `waiting` until they are cancelled. This is exactly the condition
`supabase-backup.yml` documented and escaped.

**Fix.** Mirror the precedent: move the digest to a dedicated environment with no protection rules
(`environment: notifications`), carrying over only the secrets it needs. Copy the explanatory header comment
from `supabase-backup.yml` so the reasoning travels with the file.

**Verify the secret scoping** rather than assuming it: confirm the new environment holds every secret the job
reads, because an environment switch that drops a secret converts a queued job into a failing one.

**Acceptance.** Two consecutive scheduled digest runs complete rather than wait or cancel.

### A6: close the recovered issues

- **#700 (a11y weekly) closes now.** Verified: 08-12 failed and opened it, 08-19 and 08-26 both genuinely
  succeeded with the job executing. Two consecutive greens is the bar. Close with a comment citing both run
  ids.
- **#766 (KWS delivery health) closes after one more clean cycle.** Three failures on 08-26, then green twice.
  Wait for the next scheduled cycle, then close.

**Why this matters more than it looks.** The open-issue set is the ladder's dashboard. Every stale issue in it
lowers the signal value of every other one, which is the same mechanism that let #290 accumulate 36 comments.

**Acceptance.** Every open `e2e-alert` and `ci-failure` issue describes a live failure.

### A7: fix the alerting mechanics

Three sub-items. This is the process fix underneath every individual failure above, and it is what stops the
next streak from costing a month.

**A7-i, name the failing specs in the comment.** Today's comments carry only a run link, so diagnosing
requires downloading log archives. `safety-eval.yml` already solves this: it builds a `failure-summary.md`
naming the failing test and its assertion message, and embeds it in the issue body. Port that pattern to
`e2e-real-nightly.yml`, `e2e-prod.yml`, `e2e-staging.yml` and the a11y weekly, sourcing the summary from
Playwright's JSON reporter rather than scraping stdout.

**A7-ii, escalate a streak.** Add `.github/workflows/scheduled-health-rollup.yml`: weekly, queries the Actions
API for the last N runs of every scheduled workflow, and maintains exactly one issue listing each red
workflow with its streak length and last-green date. One glance shows the ladder. Three or more consecutive
reds on any workflow is the escalation threshold from the source plan.

**A7-iii, settle the label convention** per section 3 and record it in `docs/testing/README.md`.

**Consider consolidating the copy-pasted issue-filing step.** It is currently inlined in every workflow, which
is why the e2e-staging omission went unnoticed for 23 days. A composite action under `.github/actions/` would
make its absence visible. Weigh this against churn across many workflow files; if deferred, say so in the
register row rather than leaving it implicit.

**Acceptance.** The next scheduled failure comment names its failing specs. The rollup exists and lists zero
unexplained reds. `docs/testing/README.md` documents the label convention.

## 5. WS-B: the user-side module and engine expansion

### B1: usersim leg A phase 1 (seeded invariant walk, mocked tier)

The largest single build in this plan and the one that delivers the proposal's two cheapest wins: a global
clean-console invariant everywhere the walk reaches, and mechanical dead-end detection for all three personas.

**New files.**

| Path | Purpose |
| --- | --- |
| `frontend/e2e-usersim/walk.spec.ts` | The walk itself, one `test()` per persona |
| `frontend/e2e-usersim/support/prng.ts` | Seeded PRNG (mulberry32 or xorshift; small and inlined, no dependency) |
| `frontend/e2e-usersim/support/route-manifest.ts` | Checked-in list of walkable routes with per-route persona eligibility |
| `frontend/e2e-usersim/support/invariants.ts` | I1 to I6 as composable assertions |
| `frontend/e2e-usersim/support/console-allowlist.ts` | Commented allowlist of known third-party console noise |
| `frontend/e2e-usersim/support/findings.ts` | JSONL findings emitter |
| `frontend/e2e-usersim/support/personas.ts` | Persona entry points and expected chrome (see C2) |
| `frontend/src/router.usersim-manifest.test.ts` | Sync test: manifest against the real route table |

**Where it plugs in.** Add a `usersim` project to `frontend/playwright.config.ts` with
`testDir: './e2e-usersim'`, reusing the existing `webServer` (`npm run build && npm run preview`,
`baseURL: http://localhost:4173`). Do not create a fifth config file; the mocked tier's server setup is exactly
what this needs. Add `"test:e2e:usersim": "playwright test --project=usersim"` to `frontend/package.json`.

Note that the shared config sets `serviceWorkers: 'block'`. That is correct for phase 1 and worth stating
explicitly in a comment, because this repo has a live defect class where the service worker answers navigations
it should not; a walk with the SW enabled would be testing a different application.

**The route manifest and its sync test.** Copy the proven pattern from `frontend/src/router.test.tsx`: import
the `routes` array from `frontend/src/router.tsx` and walk the nested `{ path, element, children }` tree
structurally rather than scraping source text. The sync test asserts every reachable leaf path appears in the
manifest and vice versa, so a new surface must register itself for walking. Include a positive control, as
`router.test.tsx` does, so the test cannot pass by finding nothing.

**The invariants.**

| ID | Assertion | Implementation note |
| --- | --- | --- |
| I1 | No `pageerror`, no unhandled rejection, no `console.error` | Net-new per C-5. Attach listeners in a fixture before first navigation; buffer and assert per step so the failing step is identifiable. Allowlist entries carry a required comment explaining each |
| I2 | Every state offers an enabled interactive element, or is a recognised terminal | Terminals are the auth gates K0, G0 and A0 already define as legitimate stops in the naive-ux skill |
| I3 | Spinners and skeletons resolve within budget | Assert on the absence of loading testids after a bounded wait, not on a fixed sleep |
| I4 | Zero page-level horizontal overflow | Reuse `frontend/e2e/support/responsiveChecks.ts`. Its overflow helper is currently internal to that module, so export `assertNoHorizontalOverflow` rather than duplicating the logic |
| I5 | Role and family isolation holds | Highest severity. Mocked fixtures embed canary strings for the other family and the other role; a kid walk that surfaces a guardian or family-B canary is a hard failure. This is ADR-016's three-ring boundary checked continuously instead of at hand-picked spots |
| I6 | A random back or forward step lands in a state still satisfying I1 to I4 | Generalises the specific cases in `frontend/e2e/naive-user/` |

**Determinism is the design centre.** The seed is read from `USERSIM_SEED`, defaults to a fixed value in CI,
and is printed on every failure so any finding replays exactly. A finding that cannot be replayed is a rumour.

**The findings contract.** One JSONL line per finding:
`{leg, persona, scenario_or_seed, url, invariant_or_verdict, severity, evidence_path, workflow}`. The
`workflow` field is required by DR-1, since leg A findings will originate from two workflows.

**The drift-guard extension, mandatory and in the same PR.** Extend
`scripts/check_coverage_matrix.py` to scan `frontend/e2e-usersim/`, and add the corresponding sections to
`docs/testing/coverage-matrix.md`. Without this the new tier is invisible to the guard that exists to catch
untracked specs. Confirm by deliberately adding an unreferenced spec and watching the guard fail; a guard that
has never failed is not known to work.

**The workflow.** `.github/workflows/usersim.yml`, scheduled plus `workflow_dispatch`, informational, files or
updates exactly one issue with the `[usersim]` marker and the `e2e-alert` label per section 3. Runs against
the mocked tier only in phase 1, so it needs no secrets and touches no shared environment.

**Acceptance.** The walk runs green on a fixed seed; a deliberately introduced `console.error` fails I1; a
deliberately introduced dead-end fails I2; the manifest sync test fails when a route is added without
registering it; the coverage-matrix guard fails on an unreferenced usersim spec; the workflow files exactly
one issue on failure.

### B2: `webkit-kid` nightly project, per DR-2

Revised from the source plan: nightly-only and informational, **not** per-PR. This removes the ADR-029
argument entirely, because the merge gate is untouched.

**Write the missing rationale first.** B2 shipped with none, which is why the source plan flagged it. The
rationale to record, in the proposal document alongside the other WS-B items: iPads run WebKit, iPads are a
primary kid reading device, and the reader, offline and read-aloud paths are the most engine-sensitive code in
the app (IndexedDB behaviour, service worker lifecycle, speech synthesis, and scroll containment all differ
materially on WebKit). `cross-device-e2e.yml` already runs a WebKit profile, but only against
`cross-device.spec.ts`, so no kid reading journey is exercised on the engine kids actually use.

**Implementation.** Add a `webkit-kid` project to `frontend/playwright.config.ts` using the WebKit device
profile, matching the reader, library, offline and read-aloud specs. Exclude visual snapshot specs (baselines
are engine-specific and would need a second baseline set) and exclude axe (a11y scope is governed by ADR-029
and DR-1, and this project is not the place to widen it). Run it as an added job in the nightly slot,
informational, with the same tracking-issue pattern.

**Sequencing.** After A1. WebKit will surface real engine differences in exactly the reader and offline code
A1 touches, and those findings should land on a green baseline rather than compounding a red one.

**Acceptance.** The project runs nightly within the existing time budget; its first week of findings is
triaged; each confirmed finding gets a deterministic spec plus a coverage-matrix row.

### B3: leg A real-tier variant, and I7 in the weekly a11y slot

**B3a, real-tier walk.** Add a second usersim project bound to the real stack and run it inside
`e2e-real-nightly.yml`, so walks exercise genuine state transitions rather than fixture responses. Reuse the
nightly's existing Postgres, Redis, migration and seeding steps; do not stand up a parallel stack.

The I5 isolation invariant becomes materially stronger here and materially more dangerous: on the real tier
the canaries are real rows belonging to a real second family, so seeding must create them deterministically
and the walk must never mutate across the boundary. Treat an I5 failure on the real tier as a security finding
with immediate escalation, not as a test failure.

**B3b, I7 per DR-1.** Implement axe-on-newly-reached-states inside `accessibility-compliance-weekly.yml`,
gated behind the existing `A11Y_EXTENDED=1`. Mechanically: derive distinct state signatures (route plus main
heading) during the walk, and scan each signature the first time it is reached. This directly widens the
known "one fixed mock state per surface" gap recorded in `coverage-matrix.md`, which is the whole point.

Because DR-1 splits leg A across two workflows, the findings emitter must tag `workflow` and the triage step
must read both streams. State that in the runbook text, or the split quietly becomes two half-watched
channels.

**Acceptance.** The real-tier walk runs nightly alongside the existing suites without extending the job past
its timeout; the weekly a11y job reports newly-reached-state findings distinctly from its fixed-state ones;
`coverage-matrix.md`'s fixed-state gap entry is updated rather than deleted, per its keep-current policy.

## 6. WS-C: story-QA adoptions

Three items, each carrying the same discipline the repo already applied to `validator/continuity.py`: measured
before believed, advisory before gating, never a silent pass.

### C1: comprehension probe, offline pilot

**What it is.** An offline script over the committed story corpus in `skeletons/`. One model generates, per
passage, three questions of the form "what happened / why / what should the reader remember". A **different**
model answers them from the story text alone. Questions that cannot be answered from the text flag ambiguity,
a missing causal link, or an unclear referent.

**Implementation.** `scripts/comprehension_probe.py`, offline and CLI-only, in the same mould as the other
catalog-time scripts. It reads no database and no request; it is an authoring accelerator, not production
surface. Model routing follows the repo's OpenRouter-first policy. Bound token spend per run and stop at the
cap rather than free-running.

**Output.** A per-story JSON report plus an aggregate precision figure, written under a gitignored reports
path so raw model output never lands in the repo.

**The promotion bar, non-negotiable.** `validator/continuity.py` built three formulations, measured 3.48
findings per node at a 1-in-6 true-positive rate, and shipped none as a rule. C1 earns promotion to an
advisory moderation stage only on a measured precision materially better than 1-in-6, against human-reviewed
stories. If it does not clear the bar, it is recorded as measured-and-rejected in the authoring lessons log,
which is a real and valuable outcome, not a failure.

`#ASSUME: external-resources: the comprehension probe's two-model split remains available under the current
provider allowlist and budget. #VERIFY: confirm both model ids against the provider allowlist before the
pilot run, and record the model ids and prompt-set version in every report, so a precision figure is
attributable to a configuration.`

**Acceptance.** A measured precision figure exists over a stated corpus slice, with model ids and prompt
version recorded, and a written promote-or-reject decision citing the 1-in-6 baseline.

### C2: the fixed reader persona set

**What it is.** Roughly ten fixed, age-banded reader personas (emerging, average, strong and reluctant readers
across the app's bands), each with a behavioural constraint block in the style the external recommendation
prescribes: "do not infer functionality that is not visible; prefer what this persona would attempt."

**Where they live.** Versioned in-repo as fixtures, not as prose. This is the smallest item in WS-C and it
unblocks two larger ones, so it should be done early despite its size.

Two consumers, so the format must serve both:

- `frontend/e2e-usersim/support/personas.ts` consumes entry points, expected chrome and prohibited chrome
  (the I5 canaries) for leg A.
- The leg B agentic runner (D2) consumes the persona text and constraint block.

Define the canonical data once (a JSON or YAML fixture) and have the TypeScript module import it, rather than
maintaining two copies that drift.

**Acceptance.** The persona set is committed, both consumers read the same source, and adding a persona
requires no edit in two places.

### C3: prediction-versus-behaviour calibration loop

The strongest new idea in the external recommendation, and the one with the hardest precondition.

**What it is.** A read-only analysis job joining Stage-4 engagement advisories and validator statistics
(consequence distance, reconvergence, diversity scores) against aggregated real reading outcomes (completion
rate, return reads, ratings, flags) per storybook. Output feeds the flywheel's candidate strategy, which
currently triggers on request-side saturation only, and over time calibrates which synthetic scores actually
predict that a band's readers finish and return.

**Hard precondition, before any code.** An ADR-018 children's-privacy review. Aggregate-only, per-storybook
and never per-child, and no new collection: this analyses only what the reading APIs already store.

**Implementation shape.** A scheduled analysis job writing a report artifact, not an API surface. It must not
acquire a route, because a route is a data-egress path and this data set is exactly the kind that should not
gain one.

`#CRITICAL: security: a per-storybook aggregate can re-identify a child when a storybook has very few readers,
which is the normal case for a homelab-scale catalog. #VERIFY: the privacy review must set and the job must
enforce a minimum-cohort threshold below which a storybook is excluded from the output entirely, and the
threshold must be asserted by a test, not merely documented.`

**Acceptance.** Privacy review recorded; minimum-cohort threshold enforced by a test; the job produces a
report; at least one flywheel strategy input is demonstrably derived from it.

## 7. WS-D: remaining gaps and deferred items

Specified at task level per DR-3. Several are gated on decisions that have not been made; their detail is a
design under stated assumptions, not a commitment.

### D1: Lighthouse CI weekly

Weekly, non-blocking, against the built app first and staging later. Budgets on LCP, INP, CLS and bundle size.
Single tracking issue via the standard pattern, `ci-failure` label per section 3.

Set budgets from a measured baseline rather than from published thresholds. A budget that fails on day one
teaches everyone to ignore the workflow, which is the exact failure mode WS-A exists to undo. Record the
baseline run id in the workflow file as a comment.

**Sequencing.** After WS-B lands, so it joins a ladder that is already trusted.

**Acceptance.** Four consecutive weekly runs complete, with budgets that are green at baseline and a recorded
rationale for each threshold.

### D2: leg B agentic persona runner

**D2a, the prerequisite the proposal missed (see C-5).** Migrate the 17 naive-ux scenarios from markdown prose
to machine-readable data. Today they exist only as headed prose blocks in
`.claude/skills/naive-ux-check/prompts/{kid,guardian,admin}.md`. **This migration has since been done:** on
`main` the `prompts/` directory no longer exists and `scenarios.json` already holds all 17 scenarios, so this
task is a record of the specification rather than work to do. The structured form needs, per scenario:
`id`, `persona_text`, `task_text`, `report_back_questions[]`, `requires_credentials`, `production_safe`, and
the operator-only notes kept in a separate field never sent to the model.

Keep the human skill working off the same source, so the manual and automated entry points cannot drift. That
is the whole reason to do the migration rather than fork the scenarios.

**D2b, the runner.** `tools/usersim-agent/`, a Playwright-driven loop: observe an accessibility-tree snapshot,
decide, act. Each step is a structured `{action, target, reason}` decision that **the harness executes, not
the model**. One scenario per invocation. Emits the skill's existing verdict enum, `pass` / `friction-found` /
`dead-end`, plus the four rubric answers.

**Postures inherited verbatim from the skill, not renegotiated.**

- Credentialed scenarios run only against staging's seeded accounts. Production gets only K0, signed-out and
  non-mutating. The mutating scenarios (G4, G5, G6, A2, A3) never point at production.
- Any run touching the shared staging project joins the `e2e-staging` concurrency group before it is enabled.
  This is the `#CRITICAL` from `docs/testing/README.md` and it is not negotiable. Reuse
  `frontend/e2e-support/rate-limit.ts` for pacing rather than inventing new backoff.
- Transcripts are redacted before persistence (emails, display names, tokens, correlation ids to
  placeholders). Raw model output never lands in an artifact.
- Cadence and failure handling copy `safety-eval.yml`: weekly plus manual dispatch, fail closed when
  credentials are missing, one tracking issue updated on `dead-end`, model id and prompt-set version recorded
  per run, token spend bounded per scenario with a hard stop at the cap.

**Start behind `workflow_dispatch` only.** Promote to weekly once verdict quality is trusted, which means
after a measured agreement rate against human runs of the same scenarios, not after it merely runs without
crashing.

**Acceptance.** D2a complete with both entry points reading one source; the runner executes one scenario end
to end against staging inside the concurrency group; redaction proven by a test over a synthetic transcript
containing each redactable class; a measured agreement rate against human verdicts recorded before weekly
promotion.

### D3: leg C first-party friction beacon

**Gated on its own ADR.** This ADR was written after this plan and landed as
`docs/planning/adr/adr-031-first-party-friction-beacon.md`, not the `adr-030` slug reserved here: `ADR-030`
was taken by C3's engagement-correlation privacy review. It follows the ADR-029 structure and
cross-references ADR-018 as the children's-privacy authority. It is still `status: proposed`, and no code
may land before it is accepted.

**Client.** A small module beside `frontend/src/observability.ts`, batching a closed enum of events via
`sendBeacon` on `visibilitychange`: bucketed Web Vitals (LCP, INP, CLS), error-boundary hits as a
component-stack hash only, offline-sync failure counts, rage clicks (three or more on one target inside a
second) and dead clicks (a click with no DOM or network consequence), identified by role plus testid only. No
free text, no story content, no names, no per-child identifiers: role class plus a non-persistent random
session id. Kill switch via env flag, fire-and-forget, local rate limiting.

**Server.** `POST /api/v1/client-events`, writing through the existing append-only `events/` pipeline with a
30-day retention window, rate-limited by the existing middleware.

**Consumption.** A weekly digest job in the mould of `moderation-report-health.yml`, thresholding aggregates
(a new error-boundary hash, an INP p75 regression, a rage-click hotspot on one testid) and filing or updating
one tracking issue.

The Session Replay ban in `observability.ts` stays absolute, and the ADR must say so rather than leaving it to
be inferred from current code.

`#ASSUME: security: the leg C payload enum can be kept free of attributable child data (no names, no free
text, no stable per-profile identifiers) while remaining useful for triage. #VERIFY: the ADR review must walk
every enum variant against the privacy model in docs/planning/ and against observability.ts's existing
scrubbing rules before implementation starts; if any variant needs an identifier to be actionable, that
variant is dropped rather than the rule bent.`

Two further hazards worth pre-empting, because both have bitten this repo: retention must be enforced at sweep
time against the decision-time exemption set (a sweep that re-evaluates exemptions at sweep time deletes rows
it should keep, and vice versa), and the redaction censor currently misses several credential shapes, so the
beacon path must not assume the shared censor is sufficient.

**Acceptance.** ADR-031 accepted; every enum variant walked against the privacy model in writing; retention
enforced and tested; a digest issue filed from synthetic data before any real traffic is enabled.

### D4: load testing (k6)

Deferred to Track 2 hardening. Pointless against a homelab-scale R1, and a load figure measured against the
wrong topology is worse than no figure because it will be quoted later. Record as deferred with the Track 2
phase, not as an open gap.

### D5: DAST, ZAP baseline against staging

Earlier than D4, and explicitly not bundled with it. A ZAP baseline scan is cheap; authenticated scanning is
not, because it needs the same seeded-credential and concurrency discipline as `e2e-staging`.

**Sequencing.** After the module lands. Start with an unauthenticated baseline scan, which needs no credential
handling at all, and only then consider authenticated scanning, which must join the `e2e-staging` concurrency
group per the `#CRITICAL`.

**Acceptance.** An unauthenticated baseline runs weekly and is informational; its findings are triaged once
before any authenticated extension is considered.

## 8. Sequencing and the critical path

The ordering principle from the source plan is a single sentence: **restore trust in the existing signal before
adding new signal.** A red ladder swallows every new tier added on top of it. Everything below follows from
that.

### Dependency graph

```text
A1 (go-back) ────┬──> B1 (usersim leg A phase 1) ──┬──> B3a (real-tier walk)
                 │                                  ├──> B3b (I7 in weekly a11y)
                 └──> B2 (webkit-kid nightly)       └──> D1 (Lighthouse weekly)

A3 (staging) ──────> D5 (DAST baseline)        [both need a trustworthy staging tier]

A7 (alerting) ─────> every new workflow this plan adds

C2 (personas) ──┬──> B1's persona definitions
                └──> D2b (agentic runner)

D2a (scenario migration) ──> D2b (agentic runner)

C3, D3 ────────────> blocked on privacy review / ADR-031 (not on any task here)

A2, A4, A5a, A5b, A6, C1, D4 ── independent, no blockers
```

### Recommended order

| Wave | Items | Rationale |
| --- | --- | --- |
| 1 | A1, A6 | A1 is the critical path and the only thing between the nightly and green. A6 is minutes of work and immediately raises the signal value of every remaining issue |
| 2 | A4, A5b, A3 | Each has a known cause or a known precedent, so each is bounded. A5b in particular is a copy of a fix this repo already made and documented |
| 3 | A2, A5a, A7 | A2 and A5a need real diagnosis, so they are less predictable. A7 lands before any new workflow so the new ones inherit good alerting rather than being retrofitted |
| 4 | C2, B1 | C2 is small and unblocks B1's persona definitions. B1 is the largest single build in the plan |
| 5 | B2, B3a, B3b | All three sit on a green nightly and a working usersim tier |
| 6 | C1, D1, D2a | Parallelisable. C1 is budget-gated, D1 is cheap, D2a is a data migration with no external dependency |
| 7 | D2b, D5 | Both touch shared staging and both need the concurrency discipline in place |
| 8 | C3, D3, D4 | Gated on privacy review, ADR-031, and Track 2 respectively. Do not start these to fill time |

### What can run concurrently, and what must not

Waves 1 to 3 are mostly independent and can run in parallel worktrees. Two cautions:

- **A3, A7 and the e2e-staging workflow file collide.** A3 adds the missing tracking-issue step, A7 changes
  the tracking-issue body format across workflows. Sequence them or expect a conflict in the same file.
- **Nothing in waves 4 onward should start while the nightly is red.** That is the entire premise of the
  ordering, and starting B1 early is the most tempting way to violate it, because B1 is the interesting work.

## 9. Register rows to create

Every task needs a row in `docs/planning/unscheduled-work-register.md` before or with its first commit.
`check_work_linkage.py` enforces this both as a pre-commit hook and as the `Planning Linkage` CI workflow.

> **Superseded as an instruction (2026-08-30). Do not transcribe this table.**
> The ids below were never claimed. This program's rows were filed during execution under
> `UW-F46` through `UW-F57`, which are the same numbers this section proposed, for different work. The
> table is kept as the record of what was specified; `docs/planning/unscheduled-work-register.md` is the
> source of truth for what exists. Reconcile against it before filing anything, and allocate above the
> live maximum, not above `UW-F45`.

**Cluster and namespace.** Cluster F ("test and quality hardening") is the home for all of it. This section
originally read that the highest `UW-F` id in use was `UW-F45`. That was wrong when written: the maximum was
already `UW-F47` on 2026-08-27 and is `UW-F57` at `6cc33aa5`, the commit section 0 verifies against. The
register tolerates gaps, so if a concurrent session claims an id first, renumber above the maximum rather
than trying to merge textually. Note the contrast with the authoring lessons log, which is gapless and
sequential and where a gap is an error.

**Four of these were filed under different ids, and one is already closed.** Verified against `main`:

| Proposed here | Actually filed as | State on `main` |
| --- | --- | --- |
| `UW-F67` load testing (k6) | `UW-F54` | `blocked`, Phase 8 |
| `UW-F54` name failing specs in failure comments | `UW-F49` | **`done`** |
| `UW-F65` leg B agentic persona runner | `UW-F56` | `unscheduled` |
| `UW-F63` Lighthouse weekly budgets | `UW-F57` | `unscheduled` |

The remaining rows were not individually reconciled; treat every one as unverified against the register.

**Status vocabulary.** The Status values below were corrected on 2026-08-30. This section originally used
`scheduled`, which is not a member of the enforced set. `check_work_linkage.py` accepts exactly
`unscheduled`, `blocked`, `decision`, `verify`, and `done`; `scheduled` is a disposition word from the
linkage-contract prose, not a cell value, and 16 of the rows below would have failed the gate as written.

**Phase value.** `5` for anything with a product tie, since the Phase 5 "Hardening" row in `roadmap.md`
explicitly names "the nightly/staging test ladder" as remaining open. `CI hygiene` for pure tooling with no
product tie. Never a comma-list, never a cross-reference, never a repeat of the Status value.

| Proposed ID (superseded) | Item | Phase | Status |
| --- | --- | --- | --- |
| UW-F46 | Fix `kid-go-back-real.spec.ts` order-blind PUT wait; pin persisted go-back contract at both tiers | now | unscheduled |
| UW-F47 | Sweep all e2e tiers for order-blind `waitForResponse` matchers (class defect from UW-F46) | now | unscheduled |
| UW-F48 | Diagnose e2e-prod streak (#623) or record a dated re-scope decision | now | unscheduled |
| UW-F49 | Work e2e-staging 23-run streak; add the missing tracking-issue step | now | unscheduled |
| UW-F50 | Unblock release `propose` job: python-semantic-release / GitPython API break (#765) | CI hygiene | unscheduled |
| UW-F51 | Database backup real failure (#667) plus first restore drill | now | unscheduled |
| UW-F52 | Move notification digest off `environment: production` reviewer gate | CI hygiene | unscheduled |
| UW-F53 | Close recovered tracking issues (#700 now, #766 after one clean cycle) | CI hygiene | verify |
| UW-F54 | Scheduled-failure comments name failing specs; weekly scheduled-health rollup; label convention | CI hygiene | unscheduled |
| UW-F55 | usersim leg A phase 1: walk, invariants I1-I6, seed replay, route manifest, `usersim.yml` | 5 | unscheduled |
| UW-F56 | Extend `check_coverage_matrix.py` to scan `frontend/e2e-usersim/` | 5 | unscheduled |
| UW-F57 | `webkit-kid` nightly informational project, with the rationale B2 shipped without (DR-2) | 5 | unscheduled |
| UW-F58 | usersim real-tier nightly variant; blocked on UW-F55 | 5 | blocked |
| UW-F59 | I7 axe-on-newly-reached-states in `accessibility-compliance-weekly.yml` behind `A11Y_EXTENDED=1` (DR-1); names no prerequisite, and section 0 records I7 as shipped | 5 | blocked |
| UW-F60 | Comprehension probe offline pilot, measured against continuity's 1-in-6 baseline | 5 | unscheduled |
| UW-F61 | Fixed age-banded reader persona set as versioned fixtures | 5 | unscheduled |
| UW-F62 | Prediction-versus-behaviour calibration job; blocked on the ADR-018 privacy review | 5 | blocked |
| UW-F63 | Lighthouse CI weekly with measured baseline budgets | 5 | unscheduled |
| UW-F64 | Migrate naive-ux scenarios from prose to machine-readable data | 5 | unscheduled |
| UW-F65 | Leg B agentic persona runner; blocked on UW-F64 and LLM budget sign-off | 5 | blocked |
| UW-F66 | Leg C friction beacon plus weekly digest; blocked on ADR-031 acceptance | 5 | blocked |
| UW-F67 | Load testing (k6); blocked on Track 2 public-launch scope | 8 | blocked |
| UW-F68 | DAST: unauthenticated ZAP baseline against staging | 5 | unscheduled |

**Blocked rows must name their prerequisite** in the Item text, or the linkage check treats them as orphans.
UW-F62 and UW-F66 name the ADR-018 privacy review and ADR-031 respectively; UW-F65 names D2a plus the LLM
budget sign-off; UW-F67 names Track 2. `UW-F59` names none, and would have been an orphan as written.

**Authoring lessons log.** A testing or CI finding qualifies for `docs/planning/authoring-lessons-log.md` only
when it arose from an authoring or validator run, per that log's own "When to append" clause. Most of this
plan does not qualify. Two candidates that plausibly do, if they surface during authoring work: the
order-blind wait pattern (category `tooling`, since the tooling reported a failure without pointing at the
cause) and any C1 comprehension-probe outcome (category `validator`, and a rejection is as loggable as an
adoption). The current maximum is `AL-711`; ids there are gapless and sequential, so claim the next one only
at write time.

## 10. Risks and standing assumptions

| Risk | Why it is plausible here | Mitigation built into the plan |
| --- | --- | --- |
| A1 turns out to be a product defect, not a spec defect | The evidence is strong but circumstantial; the decisive experiment has not been run | Step 1 of A1 is the experiment, not the fix. The two paths have different fix sites and A1 names both |
| The go-back fix is applied as a sleep | It is the fastest way to make the failure stop | A1 step 2a explicitly forbids it, with the reason: it converts a deterministic failure into a flake |
| usersim becomes the fifth un-triaged red streak | Exactly what happened to #290, #623, #700 and #302 | A7 lands before B1's workflow. Every new workflow starts informational and files one issue. The findings contract requires a replay seed so a finding is actionable rather than a notification |
| The new tier escapes the coverage-matrix drift guard | The guard scans four hard-coded directories and a fifth is invisible to it | UW-F56 is a required part of B1's PR, and its acceptance requires proving the guard fails on an unreferenced spec |
| Seeded walks produce findings nobody can reproduce | A random walk without a printed seed is a rumour | Seed is settable via `USERSIM_SEED`, defaulted in CI, and printed on every failure |
| I5 isolation canaries are weaker on the real tier than they look | Real-tier canaries are real rows for a real second family | B3a treats an I5 failure as a security finding with immediate escalation, not a test failure |
| Leg C collects something attributable | Aggregates over small cohorts re-identify, and this catalog has small cohorts | D3 and C3 both carry RAD markers; C3's is `#CRITICAL` and requires a minimum-cohort threshold enforced by a test, not by documentation |
| A concurrent session claims the same register ids | This repo runs concurrent sessions in one working tree | Section 9 says renumber above the maximum rather than merging textually, which is the register's own documented resolution |

`#EDGE: timing: waves 1 to 3 are written to run in parallel worktrees, but A3 and A7 both edit the
e2e-staging workflow file. #VERIFY: if both are in flight, land A3 first and rebase A7 onto it rather than
resolving a workflow-file conflict by union, since a union resolution invents a precedence neither branch
tested.`

## 11. Success criteria

Carried from the source plan, with the corrections from section 2 folded in and each made checkable.

**Trust restored (WS-A).**

- `e2e-real-nightly` green for seven consecutive runs, and #290 closed citing the go-back root cause and its
  onset commit `f68c4f71`.
- No scheduled workflow red for three or more consecutive runs without a named owner and a dated comment,
  matching the A7-ii escalation threshold exactly.
- The scheduled-health rollup exists and lists zero unexplained reds.
- Every open `e2e-alert` and `ci-failure` issue describes a live failure.
- A release PR opens on the next scheduled `propose` run.
- Backup and digest each complete two consecutive scheduled runs, and one restore drill is recorded.

**New signal earning its place (WS-B and WS-C).**

- usersim phase 1 merged, emitting findings in the JSONL contract, with **at least one finding promoted to a
  deterministic regression spec plus a coverage-matrix row**. This is the criterion that proves the triage
  loop end to end, and it is the one worth defending: a tier that produces findings nobody converts is a
  notification service, not a test tier.
- The coverage-matrix drift guard demonstrably fails on an unreferenced usersim spec.
- `webkit-kid` completes its first nightly week with findings triaged.
- The persona set has one canonical source read by both consumers.
- C1 has a measured precision figure and a written promote-or-reject decision citing the 1-in-6 baseline.

**Deferred items honestly deferred (WS-D).**

- Every WS-D item has a register row naming its prerequisite. An item with no owner and no prerequisite is
  either scheduled or deleted, not left in a document.

## 12. What this plan deliberately does not do

- **It does not promote anything to a merge gate.** Every workflow it adds is informational. Promotion is a
  separate, explicit decision per leg.
- **It does not widen the required a11y job.** DR-1 puts I7 in the weekly slot, which is what both ADR-029 and
  `CLAUDE.md` permit.
- **It does not add work to the per-PR path at all.** DR-2 moved the only item that would have.
- **It does not build the do-not-build list** from the source proposal: no standalone story-QA harness, no
  sampled path traversal, no per-node LLM readability judge, no LLM continuity gating, no commercial
  synthetic-user platform. Each was measured, retired, or architecturally superseded, and the reasons are in
  the proposal's own section 2b.
- **It does not treat any LLM verdict as gating.** Advisory before gating, measured before believed, and never
  a silent pass, which is the discipline `validator/continuity.py` and `validator/blind_spots.py` already
  established.
