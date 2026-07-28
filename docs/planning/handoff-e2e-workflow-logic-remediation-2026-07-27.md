---
purpose: Remediation record for the 2026-07-22 E2E workflow-logic review; maps each open/partial finding to the commit that closed it, records the verification boundary, and lists residual blockers
component: frontend/e2e, frontend/e2e-real, frontend/src/guardian, frontend/src/reader, frontend/src/landing, src/cyo_adventure/generation
source: branch test/e2e-workflow-logic-remediation (8 commits off origin/main 85de102), supervised subagent implementation, 2026-07-27
---

# E2E Workflow-Logic Remediation (2026-07-27)

Companion to [handoff-e2e-workflow-logic-review-2026-07-22.md](handoff-e2e-workflow-logic-review-2026-07-22.md).
That review raised findings `P-1..P-6`, `F-1..F-6`, `S-1..S-7`. A status-delta
against current `main` (v0.37.0) showed roughly half were already closed by
prior PRs. This branch closes the remaining open and partial items.

## What shipped

Branch `test/e2e-workflow-logic-remediation`, based on `origin/main` `85de102`.
8 signed commits, 58 files, +3128 / -232. **Not pushed. Push and PR are
USER-GATED.**

| Commit | Findings | Nature |
| --- | --- | --- |
| `f6f57a7` | F-1, S-3 | e2e: device-authorization + admin-user-management security coverage (mocked + real) |
| `6e36341` | F-3, F-5, F-6 | e2e: child read-aloud, naive-kid-misuse, library, reader-conflict coverage (mocked + real); F-6c real spec is a skipped stub (seed-blocked) |
| `50dd5e5` | S-4, S-6 | e2e: re-screen invariant on edit + authored-request materialization |
| `ea0e916` | S-7, P-3 | e2e: guardian auth negatives + ending-affordance proof |
| `e59c172` | P-6a,b,c,d,e | feat(guardian): guardian + landing UX gaps (intake copy, requests heading + intro, profile recovery, landing "New here? Get started") |
| `8045876` | P-5 | feat(reader): follow-along read-aloud highlight + flag-reason a11y |
| `d00dd6e` | S-5 | feat(generation): dev/test-only hook to drive the pipeline to a hard validator block |
| `cef1d10` | (P-6b follow-up) | test(e2e): align stale guardian heading assertions with the P-6b rename |

## Finding-by-finding disposition

- **F-1 (device authorization coverage)**: closed. New `device-authorization.spec.ts`
  and real-tier `admin-management-real.spec.ts`.
- **F-3 (child read-aloud)**: closed. `kid-read-aloud.spec.ts` (+ real) now asserts
  the follow-along behaviour delivered under P-5.
- **F-5 (naive kid misuse)**: closed. `naive-kid-misuse.spec.ts` (+ real).
- **F-6a/b (library, reader conflict recovery)**: closed. `library.spec.ts`,
  `reader-conflict.spec.ts`.
- **F-6c (child "go back" on a gated real story)**: **BLOCKED-ON-SEED.** There is
  no usable gated, published real-story fixture to drive the real-tier path.
  `kid-go-back-gated-real.spec.ts` is committed as a `test.skip` stub with a
  `TODO(seed)` marker. Unblock by seeding a gated real Storybook, then remove
  the skip.
- **P-3 (ending affordance)**: closed. `reader.spec.ts`.
- **P-5 (read-aloud follow-along + flag-reason a11y)**: closed as a real feature,
  not test-only. New `player/readAloudHighlight.ts` (+ test), `useReadAloud.ts`,
  `Reader.tsx`, `FlagButton.tsx`, design-system `PassageText`.
- **P-6a..e (guardian + landing UX)**: closed. Heading split per the owner's
  decision (guardian console reads "Requests from your kids"; the admin
  cross-family console keeps the neutral default "Story requests"). Landing CTA
  is "New here? Get started" per owner instruction.
- **S-3 (admin user management)**: closed. `admin-user-management.spec.ts`.
- **S-4 (re-screen invariant)**: closed. `review-edit.spec.ts` proves an edit
  re-runs screening and reflects the verdict.
- **S-6 (authored-request materialization)**: closed. `story-requests-authored.spec.ts`;
  the agent caught a false-green where `series_id` was conflated with
  `proposed_series_title`.
- **S-7 (auth negatives)**: closed. `guardian-auth.spec.ts`; the agent caught a
  false-green where a seeded init-script replayed the guardian session.
- **S-5 (full-pipeline-to-hard-block)**: closed with a minimal backend hook (see
  below). New `full-pipeline-negative-real.spec.ts` (real tier).

## S-5 backend hook (the one non-test change worth flagging)

S-5 could not be proven as a pure test. It needs the pipeline to reach a
deterministic validator ERROR on demand. Implementation:

- `core/config.py`: added `mock_story_fixture: Literal["safe", "invalid"] = "safe"`.
- `generation/provider.py`: the invalid fixture (`_INVALID_STORY` / `_INVALID_STORY_JSON`,
  a non-ending `n_start` with empty `choices: []` that trips a validator topology
  ERROR) lives in `provider.py`; the mock branch serves it when
  `settings.mock_story_fixture == "invalid"`.

**Blast radius**: default is `"safe"`, so zero behaviour change on any real path.
The mock provider is already prod-forbidden, so the invalid fixture is
unreachable in production regardless of the setting. Covered by
`tests/integration/test_generation_worker.py`.

## Verification boundary (what was actually run)

Locally runnable and green:

- **Mocked e2e** (`frontend/e2e/`, self-starting webserver): **202 passed, 1 failed**.
  The single failure is the pre-existing `authoring-queue.spec.ts:52` flake (see
  below), not a regression.
- **a11y e2e**: 20/20 passed, including the renamed guardian requests page with
  the new intro paragraph and cross-link (zero axe violations introduced).
- Vitest, frontend typecheck/lint, backend pytest/ruff/basedpyright/bandit: green
  at each commit (pre-commit hooks enforced).

Authored but NOT executed here (no backend on `:8000`; these tiers need a live
stack, out of scope for this worktree):

- All new/edited `e2e-real/` specs (device-authorization real, kid-read-aloud
  real, naive-kid-misuse real, admin-management-real, `full-pipeline-negative-real`).
- `kid-go-back-gated-real.spec.ts` (also seed-blocked; see F-6c).

Run these against a live backend before relying on them.

## CI follow-up: visual baselines need regeneration

`frontend/e2e/visual.spec.ts` is `testIgnore`d locally and runs only in CI
(platform-specific pixel baselines; regenerating locally produces off-platform
anti-aliasing mismatches, per the config's own comment). Four page appearances
changed on this branch, so their committed baseline PNGs are now stale and the
CI `visual` job will fail until regenerated:

- `guardian-requests` (P-6b heading + intro)
- `landing` (P-6e CTA)
- `guardian-intake` (P-6a copy)
- `guardian-profiles` (P-6c recovery control)

Regenerate via the `update-visual-snapshots.yml` workflow on this branch after
push. Do NOT regenerate locally. Reader and admin baselines are unaffected (the
read-aloud highlight clears at rest; flag reasons render only in a dialog; the
admin queue uses unchanged defaults).

## Pre-existing flake (do not "fix" as part of this work)

`authoring-queue.spec.ts:52` ("an admin builds a skill-mechanism authoring plan
and the row disappears") is a load-sensitive flake, not a regression:

- The spec is byte-identical to `origin/main`.
- The only shared SUT it touches (`StoryRequestQueue.tsx`) changed on this branch,
  but the admin caller hits unchanged defaults (`heading` defaults to
  "Story requests", `intro` defaults to undefined), so the admin render is
  DOM-equivalent to `origin/main`.
- It passes 3/3 in isolation on this branch and 3/3 in isolation on pristine
  `origin/main`; it fails intermittently only under heavy parallel CPU load.
- Matches the standing project note: "AdminShell/BookCard timeout-flaky under
  parallel CPU load."

A proper fix (deflaking the row-removal wait) is out of scope; track separately.

## Next actions for the resuming instance

1. Decide push/PR (USER-GATED). PR title suggestion:
   `test(e2e): remediate 2026-07-22 workflow-logic review (F/S/P findings)`.
2. After push, trigger `update-visual-snapshots.yml` on the branch to refresh the
   four stale baselines.
3. Execute the authored `e2e-real/` specs against a live backend.
4. Seed a gated real Storybook to unblock F-6c, then un-skip
   `kid-go-back-gated-real.spec.ts`.
