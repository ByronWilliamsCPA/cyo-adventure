---
schema_type: planning
title: "R1 (full) Scope Reconciliation"
description: "De-duplicated work-unit inventory, dependency ordering, and phase-placement audit
  for the M5.1 = R1 (full) milestone, produced before starting the Path B / M5 execution run."
tags:
  - planning
  - scope
  - r1-full
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Reconcile the 2026-07-28 unscheduled-work-register audit's raw row count against the
  real, de-duplicated scope of M5.1 = R1 (full) before committing implementation effort to it,
  and record where the audit's phase placements do not survive contact with the code."
component: Strategy
source: "Two-agent read-only audit, 2026-07-29: one over unscheduled-work-register.md,
  capability-register.md, r1-deferred-debt-register.md, and roadmap.md; one over staging CI
  history and docs/planning/safety/moderation-review-*-2026-07-28.md."
---

# R1 (full) Scope Reconciliation

> **Status**: Active | **Version**: 1.0 | **Created**: 2026-07-29
>
> Produced as Stage 0 of the Path B / M5 execution run (see the run's kickoff prompt). Read
> alongside [unscheduled-work-register.md](./unscheduled-work-register.md),
> [capability-register.md](./capability-register.md), and [roadmap.md](./roadmap.md), which this
> document does not replace or supersede; it corrects and orders them.

## 1. M5 duplicate numbering: resolved

`roadmap.md`'s Milestones table carried two rows both labeled `M5`. Renumbered the "R1 (full)"
row to `M5.1` (roadmap.md line 335). No `UW-*` row cited bare `M5`, and the register's phase
vocabulary already permits dotted sub-milestones (`M4.1` precedent), so no validator change was
needed. `M5: Hardened family tier` (the narrower Phase-5-scope predecessor) keeps its number.

## 2. Family-tier open-row count: 121, not 108

The kickoff prompt's estimate (~108 rows: ~68 at Phase 5, ~35 at 4b, 4 at 4c, 1 at 4d) omitted
the `now` bucket, which the prompt's own filter (`4b`, `4c`, `4d`, `5`, `now`) included. The
`now` bucket adds 13 rows. Corrected inventory:

| Phase | Rows |
|-------|------|
| 5 | 68 |
| 4b | 35 |
| now | 13 |
| 4c | 4 |
| 4d | 1 |
| **Total** | **121** |

Status split: 96 `unscheduled`, 10 `blocked`, 9 `decision`, 3 `verify`, 3 `done` at audit time
(now 7 `done` after the Stage 0 closures in §5) &rarr; **118 open family-tier rows** at the start
of this reconciliation.

## 3. De-duplication: 75 work units (~72 real ones)

118 open rows collapse to **75 distinct work units**, several explicitly flagged in the register
as the same defect under two ID schemes (`[D]`), others consolidated because they are one
indivisible branch (`[C]`). Two units (the ADR-023 personalization epic and its K19-copy
precondition, 8 rows) are blocked on an ADR ruling with a G1 STOP verdict against them and have
no phase per `roadmap.md`'s own addendum; the register's 4b placement for them (see §4, D2)
contradicts that and should not be scheduled. Net: **73 units / 110 rows** if ADR-023 work is
excluded, and **~72 units** after subtracting four rows in the "verify-and-close" unit that
proved stale on inspection (§5).

The full 75-row unit table, with exact row-ID mappings, dependency notes per unit, and the
"why merged" citation for every `[D]`/`[C]` pairing, is preserved in the Stage 0 audit transcript
rather than duplicated here; the counts and the disagreements below are what changed downstream
planning. Ask for the full table if a future session needs the row-level mapping again.

## 4. Dependency ordering (six waves)

1. **Free wins / truth restoration** — the verify-and-close sweep (§5) and doc-hygiene sweep.
   Days, not weeks; shrinks the register and stops it asserting things that are false.
2. **Safety gates and auth boundary** — assignment-gate bypass (`UW-E01`/`E02`), the
   `_extract_subject()` dev/test auth stub, moderation and repair fail-open closures, the
   direct-Anthropic-leg decision, mock-moderation retirement, review-model allowlist, real PII
   detector, device-auth/AdultGate hardening. These are the items that make the ADR-005 approval
   attestation actually true.
3. **Schema/migration-first items** — `StorybookVersion` timestamps, replay-origin durable state,
   FK `ON DELETE` parity, push-channel + `pipeline_event.family_id` backfill, `schema_version`
   reader gate. Sequenced first because later UI work reads these schemas.
4. **Infrastructure gate** — `UW-A03` (ADR-021 production cutover) is a hard prerequisite for
   ADR-022 tiered RLS scoping and for schema-parity testing (a parity test over policies that do
   not yet exist is vacuous). This is an owner/homelab-infra dependency, not code in this repo.
5. **Guardian/kid surface completion** — the 4b/4c capability bar: G2 controls, guardian-console
   UX debt, admin/guardian missing-button pairs, K19 interpretation surfaces, error-state
   handling, reader-surface defects, two-device conflict UI, book groups, consent-time budget
   semantics.
6. **The test ladder itself** (the M5.1 exit criterion) — test-ladder hygiene, full-stack E2E
   through the RQ worker, schema parity, player-parity corpus, rate-limit/CORS negative tests,
   coverage-gap batches, the behavioral safety-eval suite, nightly/staging/prod golden journeys,
   skeleton-corpus proof, performance/load, accessibility. Staging-dependent items in this wave
   cannot go green until the staging stale-image problem (§6) is resolved.

External/owner-gated items that do not block any capability (PQC/TLS readiness, Python 3.14
residual, CVE tracking, Snyk posture, ingress topology) can proceed in parallel throughout and are
not sequenced above.

## 5. Verify-and-close sweep: 4 of 5 rows were already stale

Closed in this change with citations (see `unscheduled-work-register.md` and
`capability-register.md` diffs in this commit):

| Row | Verdict | Evidence |
|-----|---------|----------|
| `UW-E03` (`M3` repair skips validator) | **Done, was stale** | `moderation/repair.py:7-12`: `moderation/pipeline.py` already schema-validates and re-runs `validator.gate.run_gate` before repaired output replaces the pre-repair blob, per capability S4's 2026-07-16 ruling. Distinct from `UW-C04` (fidelity-gate fence gap), which still stands. |
| `UW-B09` (`T3` RequestStory error-clear) | **Done, was stale** | Explicit regression tests at `frontend/src/library/RequestStory.test.tsx:411,433`; the debt register's own `U1` row already says it was pinned by a T3 test. |
| `UW-J10` (guardian per-child unassign) | **Done, was stale** | `DELETE /storybooks/{storybook_id}/assignments/{profile_id}` at `api/assignments.py:348-351`; capability G8 recorded delivered 2026-07-27. |
| `UW-B05` (`U5` no guardian reading tracker) | **Done, was stale** | `GET /families/me/reading-summary` + `frontend/src/guardian/ReadingPage.tsx` shipped 2026-07-17 in PR #270; capability G9 recorded delivered. |
| `UW-A20` | Not re-verified this pass | Left `unscheduled`/4d as recorded; not part of this sweep's scope. |

Three capability-register rows were also stale and flipped to done in this commit:

- **K11** (kid-terms story request): was 🟡 despite the register's own note flagging it as
  "likely already shipped end to end." Verified on a real child principal, not a
  guardian-on-behalf token: `api/story_requests.py:313-363`, `frontend/src/library/RequestStory.tsx`,
  test coverage in `tests/integration/test_story_requests_api.py`. Flipped ✅. **This moves K11 out
  of the 18 open family-tier capabilities entirely; it required zero code.**
- **A15** (family-connections admin console): was 🟡 citing PR #267 as "open"; #267 is merged
  (folded into #270, per `roadmap.md`'s M4d row, "Delivered 2026-07-17"). Flipped ✅. **This
  empties Phase 4d down to `UW-A20` alone.**
- **G3** (per-child request permissions): was 🟡 citing "screen-time norms remain unspecced" as
  an open item, but the same note already says screen-time norms are explicitly out of scope, not
  a residual. Flipped ✅.

**Net effect: the open family-tier capability set drops from 18 to 15.**

## 6. Staging health check (blocks Stage 3, Action 4)

The local-only handoff (`docs/planning/handoff-staging-stale-backend-image-2026-07-21.md`, dated
2026-07-21, 4/6 specs passing) is **not yet resolved**. Every scheduled `e2e-staging.yml` run from
2026-07-21 through 2026-07-28 (8 consecutive daily runs, most recent
[30364118803](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/30364118803)) shows
the identical 4-passed/2-failed signature, same two specs
(`guardian-admin-smoke.spec.ts`, `kid-library-smoke.spec.ts`), same symptom (guardian stuck on a
false awaiting-approval gate because the deployed backend image predates PR #311's `status` field
on `POST /v1/onboarding`). This repo's `trigger-image-build.yml` has dispatched rebuild requests
on every `main` push since 2026-07-21, but whether `homelab-infra` rebuilt the image and Portainer
restarted the staging containers is outside this repo's visibility.

**Consequence**: do not extend staging e2e to GJ2/GJ3/GJ5 (Stage 3, Action 4) until a staging
`e2e-staging.yml` run goes green, confirming the redeploy landed. Deeper journey tests inherit the
same guardian-console failure and produce noise, not signal, on a stale image.

## 7. Blocked/decision inventory: confirmed 13 blocked, 21 decision

Full per-row detail (ID, what it waits on, who rules) is in the Stage 0 audit transcript. Two
items flagged there are worth surfacing here because they are mislabelled:

- `UW-J01` and `UW-J03` are tagged `blocked` but are blocked only on migrations this repo can
  write itself (a `requested_by_profile_id` migration and `StorybookVersion` timestamps,
  respectively). They are self-unblockable, not truly `blocked`.
- `UW-I10` is tagged `decision` ("left for a maintainer decision") but is a one-line frontend
  union-type addition (`awaiting_manual_fill` missing from `JobStatus`). Not a real decision.

**8 of the 21 decisions gate family-tier work directly**: `UW-C11` (two-clock estimate copy),
`UW-E10` (homoglyph folding / OIDC clock skew), `UW-F14` (Tier-3 LLM eval budget), `UW-I03`
(replay-origin durable state, ADR-024 Decision 6), `UW-I05` (two-device conflict UI), `UW-I10`
(trivial, see above), `UW-K07` (Snyk's role in the tool stack), `UW-K16` (3 dual-role decisions).
Plus the three moderation-redesign decisions in §8 below, which sit at Phase 5.

## 8. Moderation review-model redesign: 3 open owner decisions, mostly unbuilt

`docs/planning/safety/moderation-review-current-state-2026-07-28.md` and
`moderation-review-redesign-2026-07-28.md` (both `status: draft`) document that 99.8% of stored
`llm_safety` findings (5,048 of 5,056) are the mock review provider's structural fail-safe, not
genuine reviewer judgments, and that Google Perspective API contributes zero live findings ahead
of its 2026-12-31 sunset. Implementation status: only the config-layer fix (PR #441,
`ed76c2d`, satisfying the classifier-presence invariant on `OPENAI_API_KEY` alone) and an unrun
baseline-capture script exist; the schema changes, merge/synthesis stage, surface redesign, and
guard-model evaluation are proposal only.

**Open owner decisions** (from redesign doc §7):

1. **Stage-2 (LLM readability) disposition**: retire it in favor of the validator's existing
   deterministic RL-13 reading-level signal (recommended), replace per-node calls with one
   whole-story call, or keep it as-is with the schema/merge changes layered on.
2. **Remediation timing**: sweep the 18 mock-moderated books immediately after Stage B ships, or
   batch with the next real catalog refresh.
3. **Moderation QA corpus**: confirm the owner's 2026-07-28 proposal to seed labeled test
   storybooks into staging (namespaced `mqa_`, containment-guarded) for moderation testing
   without real unsafe content in production.

The Modal guard-model experiment (Qwen3Guard, ShieldGemma, Llama Guard 4, Granite Guardian) is
already approved (2026-07-28, $30/mo Modal free credits cover the eval sweep); Perspective
retirement is stated as ratified by the evidence rather than an open decision.

## 9. Estimate impact

The roadmap's standing "~9-13 wks cumulative from start" figure for M5.1 does not yet need
revision on the evidence gathered so far: the de-duplication (75 units, ~72 real after known
exclusions) is smaller than the raw 118-row count implied, and 3 of the 18 open family-tier
capabilities closed with zero code (K11, A15, G3, via documentation catching up to already-merged
work). Whether the figure survives contact with implementation (as opposed to scoping) is not yet
testable; Stage 1 has not been executed at time of writing this document.
