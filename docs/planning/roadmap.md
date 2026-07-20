---
title: "CYO Adventure - Development Roadmap"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Document the phased implementation plan and milestones."
tags:
  - planning
  - roadmap
component: Strategy
source: "Project Ariadne scoping handoff (architecture rev 3, 2026-06-20)"
---

# Development Roadmap: CYO Adventure

> **Status**: Active | **Updated**: 2026-07-20 (comprehensive plan audit: verified every
> phase-status claim below against actual code and closed the gap between this document
> and roughly 20 releases merged since the 2026-07-16 replan; see the "2026-07-20 plan
> audit" section)
> **Codename**: Ariadne

## TL;DR

Build the schema first, then the player and reader, then the two-layer validator, then
generation, then safety and review, then library/profiles, editor, and hardening, across
six phases over roughly 16 to 25 weeks for a 1 to 2 developer team. The decided release
cut puts generation in R1 (the internal release: web PWA only, Phases 0-3 plus the Phase 4a
library-and-profiles slice, roughly 11 to 16 weeks). R1 is feature-complete (2026-07-03);
the WS-A through WS-G story-lifecycle redesign (see below) then hardened it through
2026-07-10, and R2 planning follows.

## Current Status (2026-07-03)

Phases 0, 1, 2, 2b, and the **Phase 3 backend** are **delivered and merged to `main`**.
The reader plays hand-authored stories offline with multi-device 409 reconciliation; the
full validation gate (Layer 1 graph checks, Layer 2 state-space walk, deterministic
age-band policy gate) is in place; the staged generation pipeline runs against live
providers (OpenRouter cascade plus an Ollama homelab leg) and measured **70% yield
(14/20)** on a live run, clearing the 60% bar. Tier-2 generation remains the weak leg
(3/7) and is the carried quality risk. The Phase 3 safety and approval workflow shipped
across three PRs: the staged content-moderation pipeline (#36), the publish state machine
plus guardian approval/send-back endpoints and the published-requires-approval invariant
(#34), and the review-surface read API plus reading-state save-state integrity (#45).

**Phase 4a is delivered: R1 (the internal release) is feature-complete as of 2026-07-03.**
The guardian-facing frontend now exists end to end: the app shell and Supabase auth (#56),
per-child profile management (#60), the kid library UI (#68), the guardian
review-and-approve console (#76), concept intake (#69), and assign-to-profile (#75) are all
merged. The Phase 3 backend guarantee is now reachable through the browser: a guardian can
generate, review, approve, and assign a story, and a child reads it offline. See
[`r1-deferred-debt-register.md`](./r1-deferred-debt-register.md) for what remains toward
full v1 (Phase 4b and Phase 5) and the later release rungs (R2/R3).

| Phase | Status | Evidence |
|-------|--------|----------|
| 0 Foundations | ✅ Delivered | schema, scaffold, CI/security baseline merged |
| 1 Schema + Reader | ✅ Delivered | player, evaluator, Layer-1, offline PWA reader merged |
| 2 Gen + Gate | ✅ Delivered | Layer-2 walk, orchestrator, RQ worker, policy gate merged |
| 2b Live providers + yield | ✅ Delivered | OpenRouter + Ollama adapters; 70% live yield recorded |
| 3 Safety + Review | ✅ Delivered (backend) | moderation pipeline (#36), publish state machine + approval/send-back + core invariant (#34), review-surface API + save-state integrity (#45); guardian console UI is Phase 4a |
| 4a Library + Profiles | ✅ Delivered (R1 feature-complete) | app shell/auth #56, profiles #60, library #68, guardian console #76, intake #69, assign #75 (all merged 2026-07-03) |
| 4b Editor + Engagement | ✅ Substantially delivered (2026-07-20 audit) | Shipped 2026-07-17 in PR #270: node editor (`PATCH .../nodes/{id}`), endings tracker UI, read-aloud/TTS, guardian content-controls UI (banned themes), per-child permission envelopes, kid feedback flag. Real gaps remaining: bookmarks (not built at all), guardian device/storage view (revoke exists, download visibility doesn't) |
| 4c Family Loops (NEW 2026-07-16) | ✅ Substantially delivered (2026-07-20 audit) | Shipped 2026-07-17 in PR #270: notification feed (`GET /notifications` + `NotificationBell.tsx`), guardian engagement visibility (`GET /families/me/reading-summary` + `ReadingPage.tsx`), kid-facing generation status, budget consent (envelopes + `GET /families/me/budget`). Gap: delivery is poll-based only, no push channel or server-scheduled digest job (S9/G10 "digest by default" is not yet a real distinct tier) |
| 4d Connections (NEW 2026-07-16) | ✅ Substantially delivered (2026-07-20 audit) | Shipped 2026-07-17 in PR #270: dual-guardian consent flow with an enforced guard at the recommendations read path (`api/recommendations.py::_is_dual_consented()`), kid-facing recommendation chips. Privacy-model erasure coverage for connections not independently re-verified in this audit pass |
| 5 Hardening | 🟡 Partially delivered | Redis-backed rate limiter, ADR-007 purge job, offline-copy revocation, operator runbook, and a re-screen first cut are merged (see checklist below); performance pass, Sentry backups/restore drill, admin audit view, and the nightly/staging test ladder remain open |

## Story-Lifecycle Redesign (2026-07-06 to 2026-07-10, post-R1)

Between R1 feature-complete (2026-07-03) and R2 planning, seven workstreams (WS-A through
WS-G) hardened and extended the story lifecycle across moderation, request handling,
generation matching, observability, catalog sharing, and series continuation. This work is
orthogonal to the Phase 0-5 ladder above, refining capabilities already shipped in Phases
2-4a rather than opening a new phase. All seven are merged; see
[`story-lifecycle-redesign.md`](./story-lifecycle-redesign.md) for the full design.

| Workstream | Scope | PRs |
|------------|-------|-----|
| WS-A | Moderation thresholds + admin noise floor | #141, #161, #162 |
| WS-B | Story-request lifecycle | #163, #164, #165, #167 |
| WS-C | Provider selection + skeleton matching | #170, #175 |
| WS-D | Pipeline event log | #168 |
| WS-E | Catalog sharing + guardian assignment | #180 |
| WS-F | Suggestion dashboard | #176 |
| WS-G | Series chaining (continuation) | #184, #192, #194 |

WS-G's "PR3" (`AnchorContext` declared variable names + continuation prompts, #194)
merged 2026-07-10, completing all seven workstreams.

## 2026-07-16 Replan: staging the register-driven remaining work

A fresh-look capability review produced the
[capability register](./capability-register.md) (stable K/G/A/S IDs), a
[full traceability review](./traceability-review-2026-07-16.md) of code, open PRs, and
backlog, and a [test traceability matrix](./test-traceability-matrix.md), plus ADRs
015-018. This section stages every remaining register gap; every item below cites its
register ID, per the register's maintenance rule. Phases 4c and 4d are new; 4b and 5 are
expanded in place below.

### Now queue (days, before Phase 4b starts)

**2026-07-20 audit status: 3 of 5 done, 1 done modulo unverifiable infra secrets, 1 not
done.**

1. ✅ **Done.** Both PRs merged (#267, #268, folded into #270). Both review conditions
   satisfied: `capability-register.md`'s A12 entry names the admin child-PIN authority
   with an explicit ADR-014 cross-reference, and `authorization-matrix.md` carries rows
   for the new admin endpoints (admin users CRUD, admin child-profile CRUD incl. PIN,
   family-connection CRUD).
2. 🟡 **Workflow done, secrets unverifiable from the repo.** `.github/workflows/e2e-staging.yml`
   exists, scheduled daily, and references the three `staging` environment secrets; whether
   they are actually populated in GitHub cannot be checked from this repo.
3. ✅ **Done.** `e2e-prod.yml` exists (scheduled daily, 30 min after staging) with a
   dedicated "alert on failure" step that opens/comments on an issue labeled `e2e-alert`.
   Requires a `production` GitHub Environment with its own secrets before the first
   scheduled run can succeed (same infra-secrets caveat as item 2).
4. ✅ **Done.** `validator-rules.md` has a PL-22 entry (band profile fail-closed);
   `authorization-matrix.md` carries rows for the already-shipped admin surfaces.
5. ❌ **Not done.** `adr-018-childrens-privacy-compliance.md` is still `status: proposed`
   with D1/D2/D3 each showing only a working recommendation and no counsel sign-off or
   progress note since 2026-07-16.

### Where every open register item lands

| Register items | Phase |
|----------------|-------|
| K5/K8 test pins, K6 tracker, K7 TTS, G6 editor, G5 skim aids, G2 controls UI, G3 permissions, K15 feedback flag, G15 storage view | 4b |
| S9 delivery infra, G10 digest/alerts, G9 visibility, K12 kid generation status, G7 budget consent + G13 interim quota balance | 4c |
| G17 consent flow, K17 recommendation surfaces, A15 enforcement guard | 4d |
| ADR-007 purge, G8/A5 offline revocation, A13 audit view, A4 re-screen tooling, nightly e2e-real + S2 real conflict spec, staging golden journeys, adversarial live-model run | 5 |
| ADR-018 D1-D4 execution, G11 trust surface, G12 export, A12 abuse workflow, A14 compliance reporting | 7 |
| G13 full credits/IAP | 8 |
| A9 curation surface, A7 ops dashboards, A8 runtime levers, A4 full catalog re-screen | 9 |
| S12 ring-3 recommendations, A11 corpus quality tooling | Post-launch backlog |
| Android, web direct billing, education persona, i18n | Parked: each needs its design element first (no ADR/register ID) |

## 2026-07-20 Plan Audit: verification and previously untracked work

A 12-agent fan-out verified every phase-status claim in this document and
[PROJECT-PLAN.md](./PROJECT-PLAN.md) against actual code, since roughly 20 releases (v0.7.0
through v0.20.0) had merged since the 2026-07-16 replan without either master document being
updated. Headline result: **Phases 4b, 4c, and 4d, and much of Phase 6, were substantially
delivered on 2026-07-17 in PR #270** ("capability register, ADRs 015-018, safety fixes, and
the M4b-d family-tier wave"), the same PR that created the capability register itself; the
register's own delivery banner (`capability-register.md` line 26) already said so, but the
per-row status symbols further down the same document were never synced to match, so this
audit also corrected `capability-register.md` directly (v1.6 -> v1.7). The phase table above
and the Phase 4b/4c/4d/5 deliverable checklists below now reflect verified reality; see
[PROJECT-PLAN.md's Phase 6 section](./PROJECT-PLAN.md) for the equivalent Phase 6 correction.

**Genuinely open work this audit found with no home in either master document** (full detail
in PROJECT-PLAN.md section 1's audit note):

- Two safety-relevant gaps from `security-hardening-plan-2026-07.md` never closed and never
  tracked here: H1 (no age-band ceiling check when a guardian assigns a book across
  children) and H2 (AI cover images reach a child's shelf with no moderation gate). Both
  added to the Phase 5 checklist above.
- A live-code-but-unregistered feature: K19 (kid request-interpretation, WS-7, delivered
  2026-07-20) has no line item in either master document. Design records:
  [story-flexibility-plan.md](./story-flexibility-plan.md) and
  [ws7-request-interpretation-design.md](./ws7-request-interpretation-design.md).
- The entire "story-flexibility" content-diversity workstream (WS-0 metrics/harness, WS-1
  leaf diversity, WS-2 parameterized catalog/theme contracts per
  [ADR-019](./adr/adr-019-parameterized-skeletons-theme-contracts.md), WS-4 selection, WS-7
  above) has merged substantial code (PRs #300, #303, #314, #321) with zero
  mentions in either master document. ADR-017 (AI cover art, already shipped) and ADR-019 are
  both missing from PROJECT-PLAN.md's ADR table; ADR-020 and ADR-021 (merged the same day,
  after this audit was written) are missing too and are not yet reconciled here at all.
- The Content workstream note in PROJECT-PLAN.md section 1 ("main still has zero
  production-eligible skeletons") is stale: 61 skeletons (58 production-eligible) and 23
  filled stories are committed to `main` (PRs #289, #292, #297); none are yet imported to
  Postgres or published, so "zero in the catalog" is still accurate, "zero in the repo" is not.
- Design docs describing real, still-open, unscheduled work with no reference anywhere in
  either master document: [catalog-first-inventory-gap.md](./catalog-first-inventory-gap.md)
  (family-scoped import blocks an admin-authored base catalog),
  [admin-guardian-dual-roles-plan.md](./admin-guardian-dual-roles-plan.md) (dual-role adult
  redesign, identifies real scoping-fork security risk),
  [skeleton-corpus-story-generation-test-plan.md](./skeleton-corpus-story-generation-test-plan.md)
  (0/21 skeletons proven end-to-end).
- Issues #125 (Supabase RLS not enabled on 13 public tables) and #214 (R2 cover-art backfill),
  both cited in `handoff-r2-readiness-2026-07-11.md`, appear in neither master document by
  number or description.
- **Update, same day**: #321 (WS-5 structure/state variation, ADR-020), #323 (ADR-021, service
  accounts/RLS/worker deployment), and #311 (a second, larger COPPA/GDPR remediation pass:
  data rights, verifiable parental consent, self-signup approval, audit logging, plus new
  `docs/compliance/` artifacts - breach-notification runbook, DPIA, infosec program,
  privacy notice, processor DPA checklist, records of processing) were all still open when
  this audit was written and **merged to `main` within hours of it**, pulled into this
  branch by a catch-up merge. Their content is real and substantial (#311 alone touches over
  20 files including new Supabase migrations for consent/retention), but it has not been
  reconciled against the Phase 5/6/7 corrections above - that reconciliation is a needed
  follow-up pass, not done in this one.
- An external-dependency ask in `handoff-homelab-infra-dev-environment-2026-07-16.md` (a `dev`
  frontend subdomain plus `staging` GitHub Environment secrets from the homelab-infra owner) is
  tracked here only as a generic unchecked test-matrix line, not by its specific asks.

Not re-litigated in this pass: the ~25 open GitHub issues already itemized in
`docs/planning/r1-deferred-debt-register.md` and elsewhere remain accurately tracked there;
this audit did not find them newly stale.

## Timeline Overview

```text
Phase 0: Foundations    ████░░░░░░░░░░░░░░░░░░░░  (1-2 wks)  - Gate: lock decisions
Phase 1: Schema+Reader  ░░░░██████░░░░░░░░░░░░░░  (3-5 wks)  - Offline PWA, Layer-1 validator
Phase 2: Gen + Gate     ░░░░░░░░░░████████░░░░░░  (4-6 wks)  - Layer-2 validator, pipeline
Phase 3: Safety+Review  ░░░░░░░░░░░░░░██████░░░░  (3-4 wks)  - Moderation + approval (overlaps P2)
Phase 4a: Library       ░░░░░░░░░░░░░░░░░░████░░  (part of 3-5 wks) - R1 (INTERNAL) line
Phase 4b: Editor + UX   ░░░░░░░░░░░░░░░░░░░░████  (post-release) - Editor, TTS, tracker
Phase 5: Hardening      ░░░░░░░░░░░░░░░░░░░░░░██  (2-3 wks)  - Deploy, backups, restore drill
```

## Milestones (re-anchored 2026-07-16 to the capability register)

The register review exposed a naming problem: what this roadmap historically called "R1"
is the **core loop** working (request -> generate -> gate -> admin approve -> assign ->
offline read), which shipped and is live. It is not the register's bar for "the web app
functions properly": the family-tier capability set. The ladder below renames the
delivered rung **R1-alpha** and defines **R1 (full)** as the register-complete web app.
The old wording stands in historical sections above; this table governs.

| Milestone | Definition (register exit criteria) | Est | Status / Dependencies |
|-----------|--------------------------------------|-----|------------------------|
| M0-M3 | Foundations through enforced approval gate | done | ✅ Delivered |
| M4 = **R1-alpha** | Core loop live internally, web only (Phases 0-3 + 4a; historic "R1") | done | ✅ Feature-complete 2026-07-03, live 2026-07-05 |
| M4.1: R1-alpha sign-off | Funded provider keys; merged PRs + safety fixes redeployed; live E2E checklist executed once with a sign-off row; Now-queue items 1-4 | ~1 wk | ⏸️ Next up |
| M4b: Editor + engagement | G6, K6, K7, G5, G2 usable by a real guardian, G3, K15, G15 view, K5/K8 test pins | 3-4 wks | ✅ Substantially delivered 2026-07-17 (PR #270); open: bookmarks (not built), G15 device/storage view, K5/K8 test pins |
| M4c: Family loops | S9, G10, G9, K12 complete, G7 real budget consent + G13 balance | 2-3 wks | ✅ Substantially delivered 2026-07-17 (PR #270); open: push channel/server-scheduled digest (S9/G10 are poll-based only) |
| M4d: Connections | G17 consent, K17 surfaces, A15 enforcement guard (ADR-016 ring 2) | 2-3 wks, overlaps 4c | ✅ Delivered 2026-07-17 (PR #270); privacy-model erasure coverage for connections not independently re-verified |
| M5: Hardened family tier | Phase 5 expanded scope: purge, offline revocation, audit view, re-screen, restore drill, nightly/staging/prod test ladder green with alerting | 2-3 wks | 🟡 M4b-4d dependency satisfied as of 2026-07-17 (see the 2026-07-20 audit note above); remaining Phase 5 gaps are audit view, restore drill, remaining test ladder, plus the newly surfaced H1/H2 |
| **M5 = R1 (full): "the web app functions properly"** | Every family-tier register row at delivered status; the five golden journeys green on the full test ladder | **~9-13 wks cumulative from start** | 🟡 Closer than scheduled: the register's K/G/A/S rows are now mostly ✅/🟡 with few ❌ remaining (see capability-register.md v1.7); the live E2E sign-off (`r1-live-e2e-checklist.md`) is still an empty, unexecuted table |
| M6 = R2: TestFlight iOS | Phase 6 (public auth/multi-tenancy) + Phase 8 (Capacitor shell, IAP); R2-gate debt items closed (G1 child-session scoping is already substantially closed by ADR-014; verify and mark) | 6-9 wks | 🟡 Phase 6's guardian-side substance (JIT onboarding, child-session tokens, profile picker + PIN, parental gate) is already built and tested per the 2026-07-20 audit (see PROJECT-PLAN.md Phase 6); the native iOS/Capacitor path (P6-05 remainder) and all of Phase 8 remain fully unstarted |
| M7 = R3: Public launch | Phase 7 (ADR-018 D1-D4 executed and Accepted, G11/G12/A12/A14) + Phase 9 (catalog ops, hosted infra, A7/A8 ops levers, submission) | 5-8 wks, partial overlap with M6 | ⏸️ Counsel engagement should start now (long lead) |
| Completion | Register fully delivered except the post-launch backlog (S12 ring-3, A11 corpus tooling) and parked no-design-element items | - | - |

## Release ladder (R1/R2/R3) and later phases

This roadmap details Phases 0-5, the family-first build. The product reaches users in three
rungs, each an overlay on the phases below rather than a new phase:

- **R1, internal release (web only)**: the web PWA for the maintainer's own family. Scope is
  Phases 0-3 plus the Phase 4a library-and-profiles slice; feature-complete 2026-07-03.
- **R2, limited release (adds iOS)**: a Capacitor iOS shell plus public guardian
  authentication, distributed over TestFlight. Scope adds Phases 6 and 8.
- **R3, public launch**: the full App Store product (Kids Category and COPPA compliance,
  public catalog, hosted infra, submission). Scope adds Phases 7 and 9.

Phases 6 through 9 and the full rung definitions are not detailed here; they live in
[`PROJECT-PLAN.md`](./PROJECT-PLAN.md) (Sections 1 and 5) and in
[ADR-008](./adr/adr-008-public-app-store-launch.md) (public App Store launch) and
[ADR-009](./adr/adr-009-supabase-platform.md) (Supabase public tier). Phases 4b, 4c, 4d,
and 5 below are post-R1 family-tier work; the 2026-07-16 replan added register-tagged
items to Phases 7 (ADR-018 compliance execution, G11/G12/A12/A14), 8 (G13 full
credits/IAP), and 9 (A9 curation, A7 ops dashboards, A8 runtime levers, A4 full catalog
re-screen), detailed in PROJECT-PLAN.md.

---

## Phase 0: Implementation gate (1-2 weeks)

**Status**: ✅ Delivered. Schema, runtime semantics, validator rule catalog, MVP cut,
auth matrix, privacy model, and the CI/security baseline are merged; the Phase-0 punch
list (PL-01..PL-18) is closed.

### Objective

Lock the decisions and artifacts that are expensive to change once code exists. No app
code until this gate passes. Tracked item-by-item in the Phase-0 punch list (PL-01
through PL-14).

### Deliverables

- [ ] MVP cut locked: a one-page in/out scope, approved (`docs/mvp-cut.md`).
- [ ] Decision log ratified: the seven Part V decisions (`docs/phase0-decisions.md`).
- [ ] Storybook schema v1 in Pydantic with JSON Schema export at
      `schema/storybook.schema.json`, plus at least 5 valid and 10 invalid fixtures.
- [ ] Story Runtime Semantics v1 documented and cross-signed by the player and validator
      owners.
- [ ] Validator design: rule ids and failure messages for Layer 1 and Layer 2, including
      the state-space approach and the configuration cap.
- [ ] Condition evaluator spec plus conformance fixtures for both in-house evaluators.
- [ ] Technical baseline (`TECHNICAL_BASELINE.md`): exact pinned versions; RQ and
      in-house evaluator confirmed; no `latest` image tags.
- [ ] Authorization matrix: endpoint access by guardian and child role, with IDOR
      negative tests listed.
- [ ] Privacy and provider data-handling model: data classification, retention,
      deletion-readiness.
- [ ] Repos scaffolded with the full CI and security baseline; hosting target chosen and a
      bare environment reachable through Pangolin.
- [ ] Drafting guide and stage prompt templates authored (migrate Appendix A from the
      scoping handoff). The 60% generation yield cannot be measured without them, and
      generation ships in R1, so this is a Phase-0 precondition, not a
      Phase-2 afterthought.
- [ ] Configuration-cap worked example: document the practical Tier-2 variable budget
      that stays under the 100,000 ceiling (e.g. compute the reachable-config count for 2
      booleans plus one `int(0-5)` across ~50 nodes) so authors and the generator have a
      concrete budget, not just a ceiling.
- [ ] Alembic migration convention recorded in `TECHNICAL_BASELINE.md`: naming,
      down-revision policy, and a CI migration check.

### Success Criteria

- ✅ Schema, runtime semantics, validator rules, MVP scope, and the auth and privacy
  model are locked and cross-signed.
- ✅ A "hello world" Storybook validates against the v1 schema.
- ✅ CI runs lint, type check, and security scans green on the empty project.

### Tasks

| Task | Est. Hours | Status |
|------|------------|--------|
| Pydantic schema v1 + JSON Schema export + round-trip test | 8 | ⏸️ |
| Runtime Semantics v1 document | 6 | ⏸️ |
| Validator rule catalog (Layer 1 + Layer 2) | 8 | ⏸️ |
| Fixture corpus (5 valid, 10 invalid) | 8 | ⏸️ |
| Authz matrix + privacy model docs | 6 | ⏸️ |
| Repo scaffold + CI/security baseline green | 10 | ⏸️ |

### Dependencies

- Product Owner answers to the Open Decisions (resolved: see the PVS release cut).

---

## Phase 1: Schema, runtime, and reader MVP (3-5 weeks)

**Status**: ✅ Delivered. Deterministic player (Python + TypeScript, cross-impl
conformance), in-house condition evaluator, Layer-1 validator, the offline PWA reader
(XState, IndexedDB, service worker), revision-based sync with the 409 conflict and
post-eviction download UX, and two hand-authored stories are merged to `main`.

### Objective

Prove the format and the player with human-written stories before any LLM is involved.
This phase has no external network egress.

### Deliverables

- [ ] Deterministic player library (node traversal, state effects per Runtime Semantics
      v1, in-house condition evaluator).
- [ ] PWA reader: state-gated choices, offline caching (service worker + IndexedDB),
      save/resume, multi-device sync (revision-based, 409 reconciliation).
- [ ] Offline-conflict UX: the 409 "continue from this device" vs "use newer progress"
      dialog designed (copy plus a wireframe), and the iOS post-eviction "download
      needed" state, before the Playwright reconciliation test is written so the test
      asserts the real UX.
- [ ] Layer-1 graph validator with the valid/invalid fixture corpus from Phase 0.
- [ ] Two hand-authored stories: one Tier 1 (8-11 band) and one Tier 2 (older band).

### Success Criteria

- ✅ A child reads a downloaded story to multiple endings with the network disabled.
- ✅ State-gated choices appear and resolve correctly under different variable states.
- ✅ Progress survives reopening the app; a two-device conflict resolves without silent
  loss.
- ✅ The same fixtures play identically in the test harness and the browser.

### User Stories

#### US-101: Offline read to an ending

**As a** child reader
**I want** to play a downloaded story without a network connection
**So that** I can read anywhere, even offline.

**Acceptance Criteria**:

- [ ] A previously downloaded story plays start to ending with the network disabled.
- [ ] Reaching an ending records a completion that syncs on reconnect.

#### US-102: State-gated choice

**As a** middle-band reader
**I want** choices that depend on what I have collected to appear only when valid
**So that** the story reacts to my decisions.

**Acceptance Criteria**:

- [ ] A choice with a false condition is hidden, not shown-and-disabled.
- [ ] The player and validator agree on the condition's value (conformance fixtures pass).

### Dependencies

- Requires: Phase 0 schema and scaffold. Blocks: Phase 2.

---

## Phase 2: Validation gate and authoring pipeline (4-6 weeks)

**Status**: ✅ Delivered, including Phase 2b. The validation gate and the
orchestrator shipped first against MockProvider; the two deferred criteria (live
adapters and measured yield) are now closed: the OpenRouter cascade and Ollama leg are
merged, and a live run recorded **70% yield (14/20)** on 2026-06-22, clearing the 60%
bar. Tier-2 is the weak leg (3/7) and carries forward as a quality risk.

### Objective

Generate stories that hold together, with the gate as the arbiter. First external LLM
call, so the privacy controls and provider data-handling decision are preconditions.

### Deliverables

- [x] Layer-2 state-space validator (configuration walk, stateful dead-end, termination
      and loop escape, conditional usefulness, configuration cap).
- [x] Generation orchestrator with staged passes (structure, prose, repair with the 3-cap
      and no-progress abort) and the provider interface protocol (`GenerationProvider`;
      MockProvider ships; live adapters deferred to Phase 2b).
- [x] Concept intake (no real child PII) and the RQ worker queue.
- [x] The known-bad and Tier-2 state corpora and their tests.
- [x] Guardian-only API endpoints for concept intake, generation jobs, and validation.
- [x] `concept` and `generation_job` database tables with Alembic migration.
- [x] Mock-driven yield harness (`scripts/yield_harness.py`).

### Success Criteria

- ✅ The validator rejects 100% of the known-bad and Tier-2 corpora with correct rule and
  node attribution.
- ✅ No prompt sent to the provider contains a real child name, birthdate, or sensitive
  trait.
- ✅ From a concept brief, the pipeline produces a story that passes the full gate with
  zero structural edits at least 60% of the time over a 20-story sample. (Met in Phase
  2b: 70% (14/20) on a live OpenRouter run, 2026-06-22.)

### Phase 2b (closed)

Two acceptance criteria were deferred from the Phase 2 cut and are now both met:

1. **60% generation yield over a 20-story sample** met at **70% (14/20)** on a live
   OpenRouter run (`anthropic/claude-haiku-4.5`); result recorded under
   [`yield-results/`](./yield-results/). Tier-1 passed 11/13; Tier-2 passed only 3/7,
   so Tier-2 prompt/structure tightening is the open follow-up lever.
2. **Concrete provider adapters** shipped: OpenRouter (primary, with in-provider
   fallback) and Ollama (homelab final fallback). A direct Anthropic SDK adapter remains
   intentionally deferred (Claude is reached via OpenRouter).

Full scope and the residual Tier-2 lever are in
[`docs/planning/phase-2b-live-provider.md`](./phase-2b-live-provider.md).

### Dependencies

- Requires: Phase 1 format, player, Layer-1 validator; Phase 0 provider and privacy
  decisions. Blocks: Phase 3, Phase 4a.

---

## Phase 3: Safety and review workflow (3-4 weeks; overlaps Phase 2)

**Status**: ✅ Delivered (backend), merged across three slices: slice 1 (PR #34),
slice 2 (PR #36), and slice 3 (PR #45). The staged content-moderation pipeline now runs
behind the `SAFE-14` seam
and persists to `moderation_report`; the publish state machine, guardian
approval/send-back endpoints, and the enforced invariant that no `published` story exists
without a recorded `approved_by` are in place; the review-surface read API projects the
story blob plus flagged passages plus the moderation report for the parent UI; and
reading-state saves are validated against the pinned version (structural floor plus
optional full replay). The one piece not yet reachable is the browser UI that exercises
these APIs, which is Phase 4a (guardian console, C4a-4).

### Objective

Make the kids-facing guarantee real.

### Deliverables

- [x] Moderation pass (provider moderation plus an independent LLM-reviewer) scored
      against per-age-band policy. (#36)
- [x] Publish state machine with the guardian-only approval transition. (#34)
- [x] Parent review surface API (read the story, see flagged passages, approve or send
      back); the consuming UI is Phase 4a. (#45)
- [x] Provenance and audit on every published version. (#34)

### Success Criteria

- ✅ No story reaches a child profile without a recorded guardian approval (verified by
  attempting every transition path).
- 🔄 Adversarial briefs are flagged and cannot be auto-published. "Cannot auto-publish"
  holds; the import and admin-submit paths no longer reach a publishable state with no
  moderation (closed structurally). What remains: no live-model adversarial run has been
  executed yet for the model-dependent classes (see
  [adversarial-safety-evaluation.md](./safety/adversarial-safety-evaluation.md)). Tracked as
  Phase 3 debt into Phase 4a/5.

### Dependencies

- Requires: Phase 2 generation and validation.

---

## Phase 4: Library, profiles, editor, and engagement (3-5 weeks)

**Status**: ✅ 4a delivered (R1 feature-complete 2026-07-03); 4b substantially delivered
2026-07-17 (PR #270, confirmed by the 2026-07-20 plan audit). The
`library` and `ratings` APIs are merged (the library filters to `published`,
profile-scoped books), and the guardian-facing frontend is now built end to end: app shell
and Supabase auth (#56), profile management (#60), library UI (#68), guardian
review-and-approve console (#76), concept intake (#69), and assign-to-profile (#75). 4b's
node editor, TTS, and ending tracker are built and merged; only bookmarks and the
device/storage view remain open (see the Deliverables checklist below).

### Objective

Make authoring and reading pleasant. Split by the release cut: 4a ships in R1, 4b follows.

### Deliverables (4a, in R1)

- [x] Library browsing and per-child profiles with age-band and reading-level limits.
- [x] The minimal guardian path to view, approve, publish, and assign a generated story to
      a profile.

### Deliverables (4b, after R1; scope expanded 2026-07-16, register IDs cited)

**2026-07-20 audit: all shipped 2026-07-17 in PR #270 except bookmarks and the device/storage
view, which remain genuinely open. Note K5 ("Go back") and "bookmarks" are two different
register capabilities that a prior draft of this list conflated; K5 is delivered (replay-based
undo), bookmarks (a distinct save-slot feature) is not built at all.**

- [x] Lightweight node editor: read as playthrough and node list, edit a passage, re-run
      validation, re-review on edit (G6). `PATCH /storybooks/{id}/versions/{v}/nodes/{node_id}`
      (`api/node_edit.py`) re-runs the gate and moderation on edit. Branch re-roll and a
      dedicated guardian-facing (as opposed to admin) review surface still remain open.
- [x] Ending tracker "3 of 7 endings found" (K6, UI over the shipped completion rows) and
      read-aloud/TTS for the youngest bands (K7). `EndingsProgress.tsx` and `useReadAloud.ts`
      wired into `Reader.tsx`, `tts_enabled` toggle in `ProfileFormDialog.tsx`.
- [ ] Bookmarks (a distinct save-slot feature, not K5's "Go back" undo): not built.
- [x] Guardian review skim aids: content summary and branch-structure view (G5).
- [x] Per-child content controls UI: banned themes on the profile form, wired through
      intake (`content_nogo = profile.banned_themes` in `story_requests/brief.py`) instead
      of the hardcoded empty lists (G2).
- [x] Per-child permissions: the ADR-015 pre-authorization envelope settings
      (`request_auto_approve`, `monthly_request_envelope`) (G3; screen-time norms stay
      deferred and unspecced, not in scope).
- [x] Kid feedback flag: "I didn't like this / this scared me", routed into the admin
      queue and the Phase 4c alert surface (K15, feeds A1/G10). `KidFlag` model,
      `POST /flags`, admin list/resolve in `api/flags.py`.
- [ ] Guardian device/storage view: which books are downloaded on which device (G15
      remainder). ADR-014 device authorize/revoke exists; per-device storage/download
      visibility does not.
- [ ] Test pins for the two shipped-but-unasserted surfaces: Go Back returns to the prior
      node with intact state (K5), cover render plus letter-tile fallback and the admin
      generate flow (K8/A16); test matrix action 7 (not independently re-verified in this
      audit pass, status unchanged pending a dedicated test-coverage check).

### Success Criteria

- ✅ R1: a child sees only stories permitted for their profile; a guardian can
  assign an approved generated story to one or more children.
- ✅ 4b: concept to published through the UI alone including a small edit; read-aloud
  works for the youngest band; a guardian can actually exclude a theme for a child and
  see it honored in generation; a kid can flag a story and an admin sees the flag.

### Dependencies

- 4a requires Phases 2 and 3. 4b can follow R1.

---

## Phase 4c: Family loops: notifications, visibility, budget (NEW 2026-07-16; 2-3 weeks)

### Objective

Close the interaction loops that make the creation flow feel alive for a family: honest
status for the kid, awareness for the guardian, and the ADR-015 budget consent made real.
This is the highest-leverage gap the capability review found after initiation itself.

### Deliverables

**Status (2026-07-20 audit): all shipped 2026-07-17 in PR #270. The one genuine remaining
gap is transport: delivery is poll-based (client re-polls with `since`), with no push
channel or server-scheduled digest job, so "digest by default, alert on safety" is not yet
a real distinct delivery tier.**

- [x] Notification delivery infrastructure over the existing `pipeline_event` log: an
      in-app, poll-based surface (`notifications/service.py`); the transport that
      K12/G10/A-alerts consume (S9). Server-scheduled digest and a push channel remain open.
- [x] Guardian notifications: story awaiting consent, story ready, kid flagged content
      (G10). `GET /notifications` (`api/notifications.py`), `NotificationBell.tsx`.
- [x] Guardian engagement visibility: per-child reading time, books finished, endings
      found, re-reads, over the existing `reading_state`/`completion` data (G9).
      `GET /families/me/reading-summary`, `guardian/ReadingPage.tsx`.
- [x] Kid-facing generation status: "your story is being written" inside the kid surface,
      completing K12.
- [x] Budget consent (ADR-015 delta): guardian approve debits a family quota, per-child
      pre-auth envelopes enforce their budget, and the guardian sees a remaining-balance
      figure (G7 complete, G13 interim; full credits/IAP stays Phase 8).
      `GET /families/me/budget`, `budgetApi.ts`.

### Success Criteria

- ✅ A kid who requests a story can watch its honest status through to the shelf without
  asking an adult.
- ✅ A guardian learns about a waiting consent, a ready story, and a kid flag without
  opening the app on a hunch.
- ✅ No generation spend occurs beyond the family quota, provably at the provider seam.

### Dependencies

- Requires 4b's K15 flag (for the alert type) but can start on S9/G9 in parallel with
  late 4b.

---

## Phase 4d: Connections and recommendations (NEW 2026-07-16; 2-3 weeks)

### Objective

Deliver ADR-016 ring 2: cousins exchange book recommendations under dual-guardian
consent. PR #267's admin-managed `family_connection` substrate plus family provisioning
makes this feasible on the family tier (admin-created cousin families), before Track 2.

### Deliverables

**Status (2026-07-20 audit): the first three items shipped 2026-07-17 in PR #270. Erasure
coverage was not independently re-verified in this audit pass and stays open pending a
dedicated privacy-model review.**

- [x] Dual-guardian consent flow: each side approves share-out and receive-in per
      direction; revocation immediate (G17). `POST`/`DELETE /family-connections/{id}/consent`.
- [x] Enforced consent guard at the read path, so a connection without both consents
      activates nothing; this replaces the prior holds-by-omission state (A15/ADR-016
      constraint). `api/recommendations.py::_is_dual_consented()` requires both consent
      columns before treating a connection as active.
- [x] Recommendation surfaces: kid sees "made for you by / cousin X loved this"
      (structured payload only: book, name, rating; K17, riding K18 ratings).
- [ ] Privacy-model erasure coverage: connections and recommendations in family deletion
      (per ADR-016). Not independently re-verified in the 2026-07-20 audit; status unchanged.

### Success Criteria

- ✅ ADR-016 validation criteria pass: visibility only with both consents, revocation
  removes it immediately, no free-text anywhere, no cross-family enumeration beyond
  active connections' payloads.

### Dependencies

- Requires PR #267 merged (substrate) and K18 ratings (shipped). Ring 3 (S12) is
  post-launch backlog, not this phase.

---

## Phase 5: Hardening and deploy (2-3 weeks)

### Objective

Production readiness on the homelab (or Azure) for the family tier. The public tier (R2/R3)
runs on Supabase-managed infrastructure instead of the homelab; see
[ADR-009](./adr/adr-009-supabase-platform.md).

### Deliverables (scope expanded 2026-07-16, register IDs cited)

- [ ] Performance pass, offline-edge hardening, accessibility (WCAG AA basics: contrast,
      focus order, scalable text).
- [ ] Sentry wired on client and server; backups and a tested restore. (Sentry half delivered 2026-07-17; backups remain)
- [x] Replace in-memory `RateLimitMiddleware` with Redis-backed rate limiting
      (in-house sliding-window Lua script over the existing `redis` client, not
      `fastapi-limiter`/`slowapi`) to support multi-process and load-balanced
      deployments, with a fail-open in-memory fallback on Redis outages
      (documented in SECURITY.md Known Infrastructure Limitations).
- [x] Operator runbook and a short authoring guide for non-technical use.
- [x] ADR-007 retention purge: the pg_cron job nulling `generation_job.report` 30 days
      post-completion or on publish (raw output currently persists indefinitely; S10).
- [x] Offline-copy revocation: archived/pulled books are removed from device caches at
      next connection, completing the kill switch and the incident pull-everywhere path
      (G8, A5).
- [ ] Admin audit view over the pipeline event log: who did what to child-linked data,
      filterable (A13 view half).
- [x] Policy re-screen tooling: re-run moderation/policy over published family-tier books
      after a threshold or band-policy change (A4 first cut, delivered 2026-07-17; full
      public-catalog re-screen lands with Phase 9).
- [x] Real-backend S2 conflict-race spec (`frontend/e2e-real/offline-conflict-real.spec.ts`):
      fabricates a two-device `state_revision` race against a live 409, both resolution
      paths covered. Confirmed present by the 2026-07-20 audit.
- [ ] Remaining test hardening per the test matrix: nightly `e2e-real` CI job (Postgres
      service + seed) and staging golden-journey coverage for GJ2/GJ3/GJ5 (matrix actions
      4, 6).
- [ ] The live-model adversarial safety run carried as Phase 3 debt (safety evaluation
      doc's model-dependent classes).
- [ ] **Newly surfaced by the 2026-07-20 audit, from `security-hardening-plan-2026-07.md`,
      neither previously tracked here nor closed**: H1, `assign_storybook` performs no
      band-ceiling comparison against the target profile, so a guardian can assign an
      off-band book across children (K13's assignment-time enforcement gap).
- [ ] **Newly surfaced by the 2026-07-20 audit**: H2, `generate_cover` flips
      `cover_status` straight `generating -> ready` with no moderation/approval gate, so
      an AI cover image can reach a child's shelf without the human review A16 promises
      (the story-text safety guarantee, A6, is unaffected).

### Success Criteria

- ✅ Deployed behind Pangolin with Supabase guardian login (ADR-009); a restore from backup
  succeeds in a drill.
- ✅ Performance targets met on a real device on home wifi.

### Dependencies

- Requires: Phases 1-4.

---

## Critical Path

Schema (Phase 0) → player and reader plus Layer-1 validator (Phase 1) → Layer-2
state-space validator (Phase 2) → generation (Phase 2) → safety and review (Phase 3) →
library and editor (Phase 4). The schema is the keystone; settle and version it first.
Generation cannot precede the validator that judges it, and for Tier-2 that means the
Layer-2 validator gates generation, not just the graph checks. The honest long pole is
Phase 2, where generation reliability and the state-space validator absorb most of the
iteration; the reader itself is straightforward.

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Combinatorial branch explosion | M | H | Branch-and-bottleneck structure; node/depth budgets in the drafting guide and validator |
| Stateful runtime dead ends | M | H | Layer-2 state-space validator; configuration cap bounds the walk |
| LLM coherence across branches | H | M | Structure-first staged generation; validator; repair loop (3-cap, no-progress abort); small Tier-2 state |
| Unsafe or off-band content | L | H | Independent moderation + mandatory guardian approval + age-band policy; never auto-publish |
| Generation cost and latency | M | L | Infrequent generation; async worker; immutable cached outputs; per-family quota |
| Condition-evaluator divergence | L | H | Tiny in-house interpreter; property-tested for totality; shared conformance fixtures |
| Multi-device progress loss | M | M | Revision-based concurrency; explicit conflict resolution; server canonical |
| Scope creep (dice, combat, sharing) | M | M | Dice and combat out of v1; sharing beyond the family is deferred to the R2/R3 public rungs (ADR-008), not v1; revisit others only on demand |
| iOS PWA storage eviction | M | M | IndexedDB as cache only; Postgres canonical; sync on every choice |

## Definition of Done

A feature is complete when:

- [ ] Code reviewed and approved.
- [ ] Tests written and passing (≥ 80% line, 70% branch; 90% on critical paths).
- [ ] Documentation updated.
- [ ] No linting or type errors (Ruff, BasedPyright).
- [ ] Security scans show no high/critical findings.
- [ ] Merged to main via a signed commit.

The roadmap is complete when every phase meets its acceptance criteria, a generated story
can travel from concept to a child's tablet with a parent's approval and play offline to
multiple endings, and the validator (Layer 1 and Layer 2) provably rejects the known-bad
and Tier-2 corpora.

## Related Documents

- [Project Vision](./project-vision.md)
- [Technical Spec](./tech-spec.md)
- [Architecture Decisions](./adr/README.md)
