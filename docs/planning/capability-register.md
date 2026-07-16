---
title: "Capability Register (Top-Down Expectation Map)"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Enumerate every persona capability derived from the top-line project goal, with stable IDs,
  so scope can be checked off and tested against expectations rather than against what happens to exist."
tags:
  - planning
  - scope
  - testing
component: Strategy
source: "Fresh-look capability review session, 2026-07-16"
---

# Capability Register

> **Status**: Active | **Version**: 1.1 | **Created**: 2026-07-16 | **Updated**: 2026-07-16

## Purpose and method

This register was produced by a deliberate fresh-look exercise: start from the top-line goal only
(an online and offline app where kids read choose-your-own-adventure books and use AI to generate
new stories based on their interests), derive what a child, guardian, and application admin would
expect the app to do, and only then compare against the foundational documents (project vision,
tech spec, ADRs 001-014, privacy model, authorization matrix). It deliberately ignores code,
sprints, and milestones.

Each capability has a stable ID: **K** (kid), **G** (guardian), **A** (admin), **S** (system,
cross-cutting). IDs are permanent; never renumber. New capabilities append at the end of their
section. This register is the checkoff sheet for scope and the basis for acceptance testing:
every item should eventually map to one or more tests, and every spec or feature should trace
back to at least one ID.

The **Docs** column records coverage in the foundational documents as of 2026-07-16:

- ✅ covered (the docs spec this, often more deeply than the expectation)
- 🟡 partial (mechanism or fragment exists; the user-facing capability is not fully specced)
- ❌ missing (absent from the foundational docs)

## Ratified decisions (2026-07-16)

These rulings from the project owner resolve the open tensions the fresh-look surfaced. They are
binding on the register below. Decisions 1-3 are recorded in
[ADR-015](./adr/adr-015-story-request-initiation-and-gating.md); all five are folded into the
vision doc (v1.2):

1. **Initiation is universal.** A child, a guardian, or an admin may initiate a story request
   (K11, G4, A10). The original guardian-only intake was scope inherited from the one-family era.
2. **The guardian is the cost gate.** A story request consumes generation budget only with
   guardian consent; guardians control spend (G7, G13).
3. **The admin is the AI gate.** The admin remains the party who gates the AI output before it
   can reach a child (A6), consistent with ADR-005 as amended 2026-06-30.
4. **The kid feedback loop exists.** Children get a simple flag/reaction signal that a grown-up
   actually sees (K15, feeding G10 and A1).
5. **Guardian visibility and notifications exist.** Engagement visibility (G9) and a
   digest-plus-alerts notification surface (G10, S9) are in scope.

The resulting canonical request flow (S8):

```text
initiate (K11 | G4 | A10)
   -> guardian cost gate (G7; may be pre-authorized per child via G3)
   -> staged generation (existing pipeline)
   -> deterministic validation + independent moderation (S4, S7)
   -> admin safety gate: approve and publish (A6)
   -> child's shelf (K9), with honest status shown to the requester throughout (K12, G10)
```

## K: Kid capabilities

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| K1 | Read with age-appropriate presentation: legible type, UI complexity, and reading level matched to the child's band | 🟡 | Bands and reading levels are deeply specced (ADR-011); per-band presentation/UX is not |
| K2 | Choices are obvious, tappable, impossible to get mechanically wrong; locked (state-gated) choices are hidden, never shown-and-disabled | ✅ | Tech spec runtime semantics |
| K3 | Choices are consequential: paths genuinely differ, endings vary, the story remembers state (items, flags, counters) | ✅ | Storybook format, Tier 2 state, ADR-011 clocks |
| K4 | Resume exactly where they left off, on any device, with no understanding of sync required | ✅ | Revision-based sync, version pinning |
| K5 | Restart and re-read freely; replay is first-class. Backtracking (a "back" button) is an explicit product decision, currently excluded in v1 | 🟡 | Replay supported; no-backtracking decided in tech spec; cheap restart UX implicit only |
| K6 | Endings tracker as a replay motivator ("found 3 of 7 endings") | ✅ | `completion` rows on stable `ending.id`; tracker in E2E plan |
| K7 | Read-aloud / narration for pre-readers and emerging readers | 🟡 | Scoped (Web Speech API, per-profile `tts_enabled`) but deferred to Phase 4b while the vision's own persona needs it |
| K8 | Picture support at lower bands: covers at minimum; per-passage illustrations as an explicit decision | ❌ | Per-passage art explicitly out of scope; cover art absent from foundational docs |
| K9 | Visual library shelf with covers: what's new, in progress, finished | 🟡 | Library API exists; shelf presentation not specced |
| K10 | Offline is invisible: identical experience offline; never a connectivity error; at most "this book isn't downloaded yet" | 🟡 | Offline reading fully specced; kid-facing connectivity UX not |
| K11 | Express interests and initiate a story request in kid terms (picking interests, typing a wish) | 🟡 | ADR-015 (accepted 2026-07-16) records the decision and flow; detailed design and implementation pending |
| K12 | Kid-friendly waiting and error states: "your story is being written", sync conflicts, and failures presented in kid terms | ❌ | Job status exists as a guardian polling endpoint only; the 409 conflict dialog is not kid-appropriate |
| K13 | Age-band content guarantee: themes, scariness, and ending intensity land within the band (e.g. no death endings in young bands) | ✅ | ADR-011 per-band allowances, content flags, moderation by band |
| K14 | Safe room: no ads, no purchases, no external links, no contact with strangers, no dark patterns in the kid context | ✅ | Permanent exclusions in vision; parental gate in ADR-008 |
| K15 | Feedback signal: "I didn't like this / this scared me", routed to a grown-up who actually sees it | ❌ | Ratified 2026-07-16 (decision 4); feeds G10 alerts and A1 queue |
| K16 | Pick "me" from a picker: name and avatar, no password or email; sibling shelves and progress never collide | ✅ | Profile picker, per-profile PIN, ADR-014 device grants, IDOR suite |

## G: Guardian capabilities

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| G1 | One account, multiple child profiles; each profile's age band and reading level actually changes what the child sees | ✅ | `child_profile` caps enforced in library filtering |
| G2 | Per-child content controls: allowed and banned themes, content flags, family-specific exclusions (phobias, no-magic, no-weapons) | ✅ | `allowed_content_flags`, brief-level `content_nogo` |
| G3 | Per-child permissions and limits: whether the child may initiate story requests (including pre-authorized auto-allow), screen-time norms if any | 🟡 | ADR-015 defines the pre-authorization envelope semantics; screen-time norms still unspecced |
| G4 | Initiate story requests themselves, including personalized stories ("one about our camping trip for Maya") | ✅ | Concept-brief intake; PII rules keep real names out of prompts |
| G5 | Fast review of a generated story without reading every path: summary, themes, flagged passages, branch structure | 🟡 | Review surface named; skim aids (summary, branch view) not specced; approval itself moved to admin |
| G6 | Edit or reject a generated story (prose tweaks, veto) with re-review on edit | 🟡 | `PATCH .../nodes/{id}` + re-review specced for Phase 4b; `needs_revision` exists |
| G7 | Cost gate: a story request spends generation budget only with guardian consent; per-child auto-allow is a guardian setting | 🟡 | ADR-015 records the consent-before-spend rule; implementation pending |
| G8 | Kill switch: pull any published book off a child's shelf immediately, including offline copies at next connection | 🟡 | `archived` state exists; offline-copy revocation unaddressed |
| G9 | Engagement visibility: what each child is reading, how much, endings found, re-reads; literacy signals, not surveillance | ❌ | Ratified 2026-07-16 (decision 5); raw data (`reading_state`, `completion`) exists with no reporting capability |
| G10 | Notifications that matter: child flagged content, a story awaiting action, a story ready; digest by default, alert on safety | ❌ | Ratified 2026-07-16 (decision 5); no notification surface anywhere |
| G11 | Plain-language trust surface: what data is collected, where the AI text came from, who reviewed it, no training on child inputs, COPPA/GDPR-K posture | 🟡 | Privacy model and ADR-008 compliance are strong internally; no user-facing articulation specced |
| G12 | Data export and full account/family deletion | 🟡 | Deletion-readiness and Apple revocation specced; user-facing export absent |
| G13 | Predictable cost model: quotas, "3 stories left this month", no surprise bills a child can trigger | 🟡 | ADR-008 credits/quotas for the public tier; no in-app balance surface specced |
| G14 | Standard adult auth; multi-guardian households (two parents, a grandparent) | 🟡 | Supabase OIDC solid; multi-guardian implied by the data model, never specced |
| G15 | Device management: authorize and revoke devices, see which books are downloaded where, storage use | 🟡 | ADR-014 grants list/revoke ✅; download/storage visibility ❌ |
| G16 | Browse the curated catalog and assign books to their own children | ✅ | WS-E catalog visibility + assignment gate |

## A: Admin capabilities

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| A1 | Moderation queue: flagged, uncertain, and reader/guardian-reported items, each showing why; decisions feed back into automated rules | 🟡 | `needs_review` routing and global queue ✅; kid/guardian reports (K15) and the feedback-into-rules loop ❌ |
| A2 | Sample audits: random re-review of anything published without direct human review (becomes real if any auto-publish tier ever exists) | ❌ | Moot while A6 gates everything; register it so it survives any future gating change |
| A3 | Global policy levers: age-band definitions, theme taxonomy, classifier thresholds, banned-content lists | 🟡 | Band profiles and thresholds exist as config; admin-facing management surface partial |
| A4 | Policy re-evaluation: re-screen the already-published catalog when policy or thresholds change | ❌ | Nothing specced |
| A5 | Incident path: trace how content reached a child (prompt, model, gate version), pull it everywhere including offline, notify affected guardians | 🟡 | Provenance supports trace ✅; pull-everywhere and guardian notification ❌ |
| A6 | AI safety gate: the admin's recorded approval is the only path from generated content to a child (approve-and-publish) | ✅ | ADR-005 as amended; state machine with no bypass; ratified 2026-07-16 (decision 3) |
| A7 | Pipeline observability: success/failure rates, queue depth and latency, rejection reasons by stage, cost per story, per-provider quality | ❌ | Measured ad hoc in ADRs (yield harness, cost probes); no operational dashboard capability |
| A8 | Pipeline levers: switch or disable providers, tune prompts/templates, set rate limits and cost caps, kill a runaway job | 🟡 | Config-pinned provider swap and fallback cascade ✅; runtime levers (kill job, caps surface) ❌ |
| A9 | Curated/seed catalog management so a new child never sees an empty shelf | 🟡 | Catalog visibility + "curated starter library" (ADR-008); management surface thin |
| A10 | Admin-initiated story generation (seeding the catalog, testing the pipeline) | 🟡 | Authorization matrix already allows admin concept submission; named as a capability in ADR-015 (platform-funded, bypasses the family cost gate) |
| A11 | Structural quality tools across the corpus: broken graphs, reading-level drift, repetitive or template-y output | 🟡 | Per-story validator is world-class; corpus-level drift/repetition tooling ❌ |
| A12 | Account support ops: lockouts, deletion requests, abuse handling (an adult misusing generation) | ❌ | Rate limiting named once as a mitigation; no support capability |
| A13 | Admin action audit trail: admins touching child-related data leave a trail | 🟡 | Approver stamps and `acting_role` audit stamps ✅; no audit view/report |
| A14 | Compliance and platform ops: retention enforcement, compliance reporting, backups and tested restore | 🟡 | ADR-007 retention, backups live, restore drill planned; compliance reporting ❌ |

## S: System capabilities (cross-cutting)

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| S1 | Offline as a first-class mode: reading, choices, progress, and flags all work offline and reconcile later | ✅ | ADR-002, sync rules, offline queue with idempotent replay |
| S2 | Multi-device conflict resolution that never silently loses a child's progress | ✅ | Revision-based 409 model; kid-facing presentation tracked as K12 |
| S3 | Story representation that supports the format: branching graph, state, conditions, multiple ending types | ✅ | ADR-001, ADR-006, ADR-011; deeper than the expectation |
| S4 | Deterministic pre-publication validation that a story is playable (no dead ends, orphans, traps, unsatisfiable paths) | ✅ | Two-layer gate incl. state-space walk |
| S5 | Age-banding as the system-wide spine: reading level, theme intensity, safety thresholds keyed off one per-child band | ✅ | ADR-011 |
| S6 | Human-legible provenance per story: who or what created it, checks passed, approver, when | ✅ | Per-version model/provider/prompt/approver stamps |
| S7 | Independent safety pipeline: moderation independent of the generator; no path to a child bypasses the automated gates plus the human gate | ✅ | ADR-005, ADR-010, prompt-injection defenses |
| S8 | End-to-end request flow: initiate (K/G/A) -> guardian cost gate -> generation -> validation/moderation -> admin gate -> shelf, with honest async status | 🟡 | ADR-015 records the canonical flow; the request lifecycle states and surfaces are not yet designed |
| S9 | Notification/event delivery infrastructure underlying K12, G10, and admin alerts | ❌ | Append-only pipeline event log exists in code; no delivery capability in foundational docs |
| S10 | Privacy architecture: no child PII to providers, data minimization, deletion-readiness, no third-party trackers in the kid context | ✅ | Privacy model, PII guard, ADR-007/008/009 |

## Known doc debt this register supersedes or exposes

All three items below were resolved in the 2026-07-16 alignment pass; kept for the record:

- ~~The vision doc still says "no story reaches a child until a parent approves it"~~:
  resolved in vision v1.2 (TL;DR, success metrics, and MVP capability 5 now name the global
  safety admin per ADR-005 as amended); the guardian's residual controls are G5/G6/G7/G8,
  not approval.
- ~~The vision doc's one-family target-user framing predates the public pivot~~: resolved in
  vision v1.2 (scope note generalizes to the three roles; the founding family is kept as
  reference personas).
- ~~The "children cannot request stories" narrowing was never a recorded decision~~: resolved
  by [ADR-015](./adr/adr-015-story-request-initiation-and-gating.md), which reverses it
  explicitly and refines ADR-008's "children never trigger generation" phrasing to the
  enforceable invariant (no spend or provider egress without adult consent).

## Maintenance rules

1. IDs are stable forever. Append, never renumber; mark dead items "Retired" with a reason.
2. When a capability lands, flip Docs status and link the spec/ADR and the tests that cover it.
3. Any new feature proposal must cite the ID(s) it serves; a proposal serving no ID is either
   scope creep or a missing register entry, and that call gets made consciously.

## Related documents

- [Project Vision](./project-vision.md) (update pending per doc debt above)
- [Tech Spec](./tech-spec.md)
- [ADR index](./adr/README.md)
- [Authorization Matrix](./authorization-matrix.md)
- [Privacy Model](./privacy-model.md)
