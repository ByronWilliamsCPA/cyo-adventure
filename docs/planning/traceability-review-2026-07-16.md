---
title: "Traceability Review: Code and Plans vs Core Design Elements"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Map every implemented and planned element (including open PRs) to a capability
  register ID or ADR; queue unmapped elements for an owner ruling; record doc-vs-code
  contradictions found in the process."
tags:
  - planning
  - scope
  - testing
component: Strategy
source: "Six-subagent parallel review, 2026-07-16: backend domain, backend API/platform,
  kid frontend, adult frontend, open PRs #267/#268, planned backlog. Findings reconciled
  and verified by the supervising session."
---

# Traceability Review (2026-07-16)

> **Status**: Active | Companion to [capability-register.md](./capability-register.md) (v1.4)

## Method and headline

Six parallel review agents mapped the backend domain modules, the backend API and data
model, the kid-facing frontend, the adult-facing frontend, the two open feature PRs
(#267, #268), and the planned backlog (roadmap, PROJECT-PLAN, debt register, security
plan) against the capability register (K/G/A/S IDs) and ADRs 001-016. Findings were
cross-checked between agents and against the code before inclusion here.

**Headline**: the overwhelming majority of implemented code maps cleanly. The review
found exactly two shipped feature areas with no design home (star ratings and the AI
cover-art subsystem), one shipped UI control that contradicts a written design decision
(the Reader's back button vs the tech spec's no-backtracking rule), and a small set of
doc-vs-code contradictions, two of which are safety-relevant (moderation repair skips
re-validation; the band-policy validator fails open). Pure infrastructure (health checks,
correlation, security middleware, CI/test tooling, release plumbing) maps to CLAUDE.md's
engineering standards rather than persona capabilities, which is the expected home.

False positives removed during reconciliation: agents flagged PR #267/#268 tables and UI
as "absent from this branch"; both PRs are unmerged, and the register already attributes
that work to the open PRs. The moderation-threshold audit trail flagged as unverified by
one agent was confirmed by another (`ModerationThresholdAudit`, `ProviderModelAllowlistAudit`
tables exist).

## 1. Mapped elements (summary)

Full per-module tables live in the review transcripts; this is the confirmed mapping at
subsystem level.

| Subsystem | Maps to |
|-----------|---------|
| storybook/ (schema, conditions, evaluator) | S3; ADR-001, ADR-006, ADR-011 |
| player/ (engine, state, replay anti-forgery) | K2, K3, K4, S2, S3 |
| validator/ (two-layer gate, band profiles, series rules) | S4, S5, K13; ADR-011 |
| generation/ (orchestrator, providers, PII guard, skeletons, queue) | S7, S8, S10, A8, A9, A10; ADR-003, ADR-010 |
| moderation/ (classifiers, pipeline, thresholds, insights, repair) | S7, K13, A1, A3; privacy model Stage-0 section |
| publishing/ (approve-and-publish state machine, archive) | A6, G8 (backend half); ADR-005 |
| story_requests/ (intake, screening, approve, authoring plan, anchoring) | K11, G4, G7 (consent half), A10, S8; ADR-015 |
| events/ (pipeline event log) | S6; S9 substrate only; A7/A13 partial |
| api/ routers (14+) and db/models.py tables | Each confirmed against a specific ID; see contradictions for the exceptions |
| Kid frontend (picker, shelf, reader, offline, request UI) | K1-K5, K9-K12, K14, K16; ADR-002, ADR-014, ADR-015 |
| Adult frontend (guardian console/intake/books/profiles; admin queue/review/moderation) | G1, G4, G5(partial), G14, G15, G16, A1, A3, A6, A9(partial), A10 |
| PR #267 (user management, status gating, family connections) | A12, A13, G14, A15/K17/G17 substrate; ADR-016 ruling |
| PR #268 (testing tiers, a11y/visual suites, allowlist + authoring-queue UI) | A8, S8, K1(contrast); CLAUDE.md quality gates |
| Planned backlog (Phases 4b, 5, 6-9, debt register) | Mapped item-by-item; see section 4 for the inverse gaps |

## 2. Unmapped implemented elements: decision queue

These are the elements that serve no register ID or ADR today. Per register maintenance
rule 3, each needs a conscious call. Recommendations are the reviewer's; rulings are the
owner's.

| # | Element | Evidence | Recommendation |
|---|---------|----------|----------------|
| U-1 | **Star ratings**: kid-facing 1-5 star widget, `Rating` table, `api/ratings.py`, `RATED` event, plus debt item U6 (ratings cannot be cleared) | Found independently by 3 agents | NEEDED. Mint **K18** (child rates a finished book: personal record and replay motivator). It is also the natural substrate for K17 ring-2 payloads ("book pointer plus rating") and S12 aggregate scoring the owner already ratified. Fold U6 under it. |
| U-2 | **AI cover-art subsystem**: covers/ module (Gemini generation, prompt-injection-hardened prompts, WebP optimization, R2 storage, RQ worker), `api/covers.py`, admin generate button, kid-visible covers with letter-tile fallback | 3 agents; largest doc/code gap found | NEEDED. Update K8 (covers are shipped, per-passage art stays out of scope), mint **A16** (admin generates and manages AI cover art), and write a short ADR (image provider, storage, image-moderation posture; R2 is also an undocumented vendor). |
| U-3 | **Reader "Go back" button**: one-step undo via deterministic path replay | Contradicts tech-spec "No backtracking in v1" and K5's note; code comments frame it as deliberate mis-tap recovery | DECISION NEEDED: ratify the reversal (amend tech spec Runtime Semantics and K5; the replay-based implementation avoids the state-semantics problem the original decision feared) or remove the button. Reviewer leans ratify: it is shipped, tested, and kid-valuable. |
| U-4 | **Admin sets/resets a child's PIN** (PR #267 `admin_profiles.py`) without guardian involvement | New admin authority over child authentication material; unnamed in A12, uncrossed with ADR-014 | NEEDED as support ops, but name it: extend A12's scope text and add an ADR-014 cross-reference; ensure the action is evented (audit). |
| U-5 | **JIT onboarding admin-seeding footgun**: an unseeded admin who signs in becomes a plain guardian silently | Documented only in the file's own docstring | NEEDED: record in ADR-009 (or G14 note) as an operational invariant: admin accounts must be pre-seeded before first login. |
| U-6 | Toast layer + guardian nav pending-count badge | In-session feedback only | NEEDED as-is; explicitly NOT a step toward G10 (digest/alerts). No action beyond this note. |

Planned items with no design anchor (from the backlog review): Android release (no ADR
decides Android; ADR-002/008 are iOS/PWA-scoped), web direct-billing channel (extend
ADR-008), education/teacher channel (a new persona variant the register does not have),
i18n string catalog (explicit product decision pending). None is schedulable until its
design element exists.

## 3. Doc-vs-code contradictions

Ordered by consequence. Items 1-3 are safety/privacy-relevant.

1. **ADR-007 vs code (and vs privacy model)**: ADR-007 says raw generation output
   (`GenerationJob.report`) is "admin/system role only." The code returns it to the
   owning family's guardian via `GET /generation-jobs/{id}` (`api/generation.py`), and
   the privacy model already documents the guardian-visible reality. The retention purge
   ADR-007 defines is also unbuilt, so raw output currently persists indefinitely.
   Resolution needed: amend ADR-007 to match (guardian-visible, family-scoped, list and
   child endpoints excluded) or tighten the endpoint; and schedule the purge job.
2. **Moderation repair skips re-validation**: `moderation/repair.py` states in its own
   docstring that it does not re-run `validator.gate.run_gate` on a repaired revision, so
   a repaired blob's structure is trusted, not re-proven, before the human gate. S4's
   guarantee holds only pre-repair. Recommend an engineering fix (re-gate after repair),
   not just a doc note.
3. **Band policy fails open**: `validator/policy.py` silently skips all age-safety shape
   checks (PL-15..PL-21) for a band with no configured profile; the only guard is an
   enum-lockstep test. Recommend a runtime fail-closed (unconfigured band = validation
   error).
4. **G2 is schema-deep only**: per-child content controls exist in the data model and
   brief schema, but the intake UI hardcodes `content_nogo: []` and `themes_allowed: []`
   and the profile form has no banned-theme field. No guardian can actually exercise G2.
5. **K6 endings tracker has no surface**: completions are recorded (write path solid) but
   no UI anywhere shows "found N of M endings." Phase 4b plans it; register note updated.
6. **K12 was understated**: kid-friendly waiting/error states are substantially built
   (kid-language request statuses, plain-language conflict dialog, mascot-illustrated
   error/empty states, honest save-retry banner). Register note updated; remaining gap is
   generation-progress visibility inside the kid surface.
7. **ADR-016 consent constraint holds by omission**: nothing reads `family_connection`
   yet, so the "no child-facing visibility without dual-guardian consent" rule is
   satisfied vacuously. The first consumer must add an enforced guard; register G17 note
   updated so this cannot land silently.
8. **Authorization matrix is missing rows** for shipped admin surfaces: `GET /admin/families`,
   provider-allowlist CRUD, moderation thresholds/noise floor, moderation dashboard, and
   cover generate/status endpoints all enforce admin-only in code but have no matrix row.
9. **"G1" identifier collision**: code comments cite "G1 / P6-04" meaning a PROJECT-PLAN
   task, which now collides with register G1. Convention going forward: cite register IDs
   as "register G1" and plan tasks by their P-number only.
10. **PR #267 process gaps** (for its review, not blockers): it updates neither the
    authorization matrix (new admin endpoints) nor any planning doc; family deactivation
    cascades to members but reactivation deliberately does not (documented in code only).

## 4. Register items with no planned work anywhere

The scheduling gaps to resolve when slotting work into the plan (from the backlog agent,
verified against roadmap/PROJECT-PLAN):

| Register items | Gap | Natural slot |
|----------------|-----|--------------|
| K15 | Kid feedback signal: ratified, zero planned items | Phase 4b (feeds G10/A1) |
| G10, S9 | Notification surface + delivery infra: ratified, unplanned | Own slice in 4b/5; public tier needs it too |
| G17, A15, K17, S12 | Connection consent flow, recommendation surfaces, ring-3 aggregation | New slice after 4b, or fold into Phase 6 (consent machinery) |
| G5 | Guardian skim aids (summary, branch view) | Phase 4b |
| G7, G13 | Budget/credit substrate and balance UI (consent exists; nothing is priced) | Phase 8 (entitlements) with an interim quota in 4b/5 |
| G8, A5 | Offline-copy revocation half of kill switch and incident path | Phase 5 offline hardening |
| G15 | Download/storage visibility per device | Phase 4b/5 |
| G3 | Screen-time norms half (pre-auth envelope is ADR-015's) | Phase 4b |
| A4 | Re-screen published catalog on policy change | Phase 9 (pairs with catalog state) or 5 |
| A11 | Corpus-level drift/repetition tooling | Generation-quality follow-up |
| A12, A13 | Abuse-handling workflow; admin audit view | Phase 7/9; Phase 5/9 |
| A2 | Sample audits: moot while A6 gates everything | Non-issue unless auto-publish ever proposed |

## 5. Owner decision queue (condensed)

> **Rulings received 2026-07-16 (same day)**: 1 yes (K18 minted), 2 yes (K8 updated, A16
> minted, ADR-017 written), 3 ratify (tech spec amended), 4 open until PR #267 review,
> 5 tighten the endpoint (admin-first; ADR-007 amended, code fixed), 6 yes (both fixes
> implemented), 7 deferred as a batch. G2 build confirmed, scheduling open. The register
> (v1.5) carries the applied state; the list below is preserved as the record of what was
> asked.

1. U-1 ratings: mint K18? (recommended yes)
2. U-2 cover art: update K8, mint A16, short ADR? (recommended yes)
3. U-3 back button: ratify reversal of no-backtracking, or remove? (recommended ratify)
4. U-4 admin PIN reset: name under A12 with ADR-014 cross-ref? (recommended yes)
5. ADR-007: amend to guardian-visible, or tighten the endpoint? (privacy model already
   documents guardian-visible; either is defensible, pick one)
6. Repair re-gate and band-profile fail-closed: approve as engineering fixes (recommended
   yes, both small and safety-positive)
7. Android / web-billing / education channel / i18n: each needs its design element before
   scheduling (can be deferred as a batch)

## Related documents

- [Capability register](./capability-register.md) (v1.4 carries the note corrections from
  this review)
- [Authorization matrix](./authorization-matrix.md) (missing rows listed in section 3.8)
- [ADR index](./adr/README.md)
