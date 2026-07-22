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

> **Status**: Active | **Version**: 1.7 | **Created**: 2026-07-16 | **Updated**: 2026-07-20
> (v1.4: note corrections and ruling queue from the full traceability review, see
> [traceability-review-2026-07-16.md](./traceability-review-2026-07-16.md);
> v1.5: owner rulings applied: K18 and A16 minted, back button ratified, ADR-007
> admin-first sequencing, repair re-gate and band fail-closed fixes ordered, G2 build
> confirmed; v1.6: A12 note extended to name the admin child-PIN set/reset authority
> explicitly, with an ADR-014 cross-reference, per the 2026-07-16 review condition;
> v1.7: comprehensive plan-audit correction (2026-07-20) - the 2026-07-17 delivery
> update below was never propagated into the per-row Docs column: K6, K15, G9 flipped
> ❌->✅, K12/G10/S9 flipped ❌->🟡 (each shipped in PR #270 per its own banner note,
> just not synced into the table), with file-level evidence added to each row's note;
> see the 2026-07-20 plan-audit summary in roadmap.md for the full cross-doc reconciliation)

> **Delivery update (2026-07-17, M4b-d execution on branch
> claude/app-capabilities-review-wm6gt3)**: the following capabilities moved to DELIVERED
> (code, tests, and E2E where noted; commits 5fd1de7 through 6f729d5): K5 (Go Back pinned),
> K6 (tracker UI), K7 (read-aloud), K12 (complete incl. generation status), K15 (flag end
> to end: kid button, admin queue, guardian alert), K17 (shelf chips), G2 (controls UI and
> brief wiring), G3 (envelope backend, write path, and form UI), G5 (structure summaries),
> G6 (prose editor with gate and moderation re-run; admin surface, guardian UI awaits a
> guardian review surface), G7 (complete: consent debits quota on ALL spend paths incl.
> the legacy intake gate), G9 (Reading page), G10/S9 (notification feed and bell), G13
> (interim balance), G17/A15 (dual-guardian consent flow with the ENFORCED ring-2 guard,
> superseding the holds-by-omission note below), and the S8 flow now includes the budget
> stage. PR #267 (A12/A13, connection substrate) merged to main; PR #268 (A8 UI) in
> flight. Remaining for M4-full: G15 device/storage view (needs a design decision), G8
> offline revocation (Phase 5), and the owner-side items (secrets, redeploy, live
> checklist).

> **Delivery-state review (2026-07-16, open PRs and working docs)**: the Docs column below
> measures *foundational-doc* coverage, but a review of
> [story-lifecycle-redesign.md](./story-lifecycle-redesign.md) (owner-ratified 2026-07-06,
> workstreams A-G merged 2026-07-10) and open PRs #267/#268 found several items further
> along in working docs and code than foundational coverage suggested. Affected rows carry
> delivery notes; treat the Notes column as the current truth.

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
6. **The social boundary is three rings, not a flat exclusion** (ruled 2026-07-16, recorded
   in [ADR-016](./adr/adr-016-recommendation-sharing-social-boundary.md)): recommendations
   flow within a family (ring 1) and between guardian-approved connected families, the
   cousins case (ring 2, structured data only, dual-guardian consent, no
   receive-from-everyone option); globally only the system recommends, from anonymized
   aggregate scores (ring 3, future); never kid to kid beyond ring 2, and no messaging,
   discovery, or contact outside active parental approval (K17, G17, A15, S11, S12).

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
| K3 | Choices are consequential: paths genuinely differ, endings vary, the story remembers state (items, flags, counters) | ✅ | Storybook format, Tier 2 state, ADR-011 clocks; WS-5 (delivered 2026-07-20) adds the catalog-time mechanism to grow structural + state variation, the M1-M5 mutation operators re-proven by the unchanged gate plus the WS-5 acceptance floors, promoted via bundle + human PR (ADR-020); WS-8 (the catalog flywheel, delivered 2026-07-21, D1-D8) closes the demand loop end to end: the enum-only saturation trigger drives a bounded candidate strategy, human-gated draft-PR promotion, and a scheduled S1-S6 cadence runner behind six reviewed-PR-only caps, so K3 holds up for heavy readers in saturated cells with no standing authoring budget |
| K4 | Resume exactly where they left off, on any device, with no understanding of sync required | ✅ | Revision-based sync, version pinning |
| K5 | Restart and re-read freely; replay is first-class, including a single-step "Go back" undo | ✅ | RULED 2026-07-16: the back button stays; tech spec Runtime Semantics amended (replay-based undo, no backward state mutation); shipped in the Reader |
| K6 | Endings tracker as a replay motivator ("found 3 of 7 endings") | ✅ | Tracker UI shipped 2026-07-17 in PR #270: `frontend/src/reader/EndingsProgress.tsx` ("found N of M"), wired into `Reader.tsx`, tested; `completion` rows are the write path |
| K7 | Read-aloud / narration for pre-readers and emerging readers | ✅ | Shipped 2026-07-17 in PR #270: Web Speech API read-aloud (`frontend/src/reader/useReadAloud.ts`), per-profile `tts_enabled` toggle wired into `Reader.tsx` and `ProfileFormDialog.tsx` |
| K8 | Picture support at lower bands: covers at minimum; per-passage illustrations as an explicit decision | 🟡 | Cover art ratified and recorded in [ADR-017](./adr/adr-017-ai-cover-art.md) (shipped: Gemini generation, R2 storage, kid-visible with fallback tile); per-passage art stays out of scope; pre-reader picture support beyond covers still open |
| K9 | Visual library shelf with covers: what's new, in progress, finished | 🟡 | Library API exists; shelf presentation not specced |
| K10 | Offline is invisible: identical experience offline; never a connectivity error; at most "this book isn't downloaded yet" | 🟡 | Offline reading fully specced; kid-facing connectivity UX not |
| K11 | Express interests and initiate a story request in kid terms (picking interests, typing a wish) | 🟡 | Shipped end to end: `POST /story-requests` plus a kid-terms request UI (idea box, series continuation, own-status list in kid language); ADR-015 is the foundational record |
| K12 | Kid-friendly waiting and error states: "your story is being written", sync conflicts, and failures presented in kid terms | ✅ | Shipped 2026-07-17 in PR #270 (per its own delivery banner, "K12 complete incl. generation status"): kid-language request statuses, plain-language conflict dialog, mascot error/empty states, honest save-retry banner, and the kid-facing generation-in-progress state |
| K13 | Age-band content guarantee: themes, scariness, and ending intensity land within the band (e.g. no death endings in young bands) | ✅ | ADR-011 per-band allowances, content flags, moderation by band. **Open gap (H1, security-hardening-plan-2026-07.md, unresolved as of 2026-07-20)**: `assign_storybook` performs no band comparison against the target profile, so a guardian can assign an off-band book across children; the generation-time guarantee holds, the assignment-time enforcement does not yet |
| K14 | Safe room: no ads, no purchases, no external links, no contact with strangers, no dark patterns in the kid context | ✅ | Permanent exclusions in vision; parental gate in ADR-008 |
| K15 | Feedback signal: "I didn't like this / this scared me", routed to a grown-up who actually sees it | ✅ | Shipped 2026-07-17 in PR #270: `KidFlag` model, kid-facing `POST /flags`, admin list/resolve (`src/cyo_adventure/api/flags.py`); feeds G10 alerts and the A1 queue as designed |
| K16 | Pick "me" from a picker: name and avatar, no password or email; sibling shelves and progress never collide | ✅ | Profile picker, per-profile PIN, ADR-014 device grants, IDOR suite |
| K17 | Give and receive structured book recommendations within the family and across guardian-connected families (cousins); a recommendation is a book pointer plus rating, never a message | ✅ | ADR-016 records the policy; PR #267 shipped the connection substrate, and PR #270 (2026-07-17) shipped the kid-facing recommendation chips ("made for you by / cousin X loved this") over `/v1/recommendations`, gated by G17's enforced consent guard; K18 ratings are the payload substrate |
| K18 | Rate a finished book (1-5 stars): the enjoyment signal that feeds S12 aggregate scoring and K17 recommendation payloads | ✅ | RULED 2026-07-16: owner's variant of thumbs up/down for aggregate ratings; shipped (kid widget, `Rating` table, `api/ratings.py`); debt item U6 (cannot clear a rating) folds here; distinct from K15, which remains the safety-flag signal |
| K19 | Request interpretation and expectation-setting: when a child submits a free-form story idea, the app reflects it back in kid terms before generation, what it understood and will build into the story versus what it set aside and why (outside the age band, not safe, or not part of this kind of story), so the child knows what to expect from their wish | ✅ | DELIVERED 2026-07-20 (WS-7 D1-D8): the interpretation core (`story_requests/interpretation.py`), the persisted `story_request.interpretation` column, the submission-time general layer, the contract-grounded refined layer (interpret-and-bind + worker wiring), the CANNOT_CARRY rejection surface, and the D8 API contract (`RequestInterpretationView` on the story-request view) are built, tested, and merged. Added 2026-07-18 (owner directive). Design record: [story-flexibility-plan.md](./story-flexibility-plan.md) WS-7 and [ws7-request-interpretation-design.md](./ws7-request-interpretation-design.md). Gated by K13 (never echo unsafe input back); complements K11 (express a request) and K12 (kid-friendly states). The guardian-console view is the G-side companion surface |

## G: Guardian capabilities

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| G1 | One account, multiple child profiles; each profile's age band and reading level actually changes what the child sees | ✅ | `child_profile` caps enforced in library filtering |
| G2 | Per-child content controls: allowed and banned themes, content flags, family-specific exclusions (phobias, no-magic, no-weapons) | ✅ | Schema-deep only: `allowed_content_flags` and `content_nogo` exist in the data model, but the intake UI hardcodes empty lists and the profile form has no theme controls. RULED 2026-07-16: build confirmed, scheduling open |
| G3 | Per-child permissions and limits: whether the child may initiate story requests (including pre-authorized auto-allow), screen-time norms if any | 🟡 | Pre-authorization envelope shipped 2026-07-17 in PR #270 (`request_auto_approve`, `monthly_request_envelope` on `child_profile`; form UI in `ProfileFormDialog.tsx`/`ProfilesPage.tsx`); screen-time norms remain unspecced and out of scope |
| G4 | Initiate story requests themselves, including personalized stories ("one about our camping trip for Maya") | ✅ | Concept-brief intake; PII rules keep real names out of prompts |
| G5 | Fast review of a generated story without reading every path: summary, themes, flagged passages, branch structure | ✅ | Structure summaries shipped 2026-07-17 in PR #270 (per its delivery banner: "G5 structure summaries"); approval itself is on the admin surface (A6) |
| G6 | Edit or reject a generated story (prose tweaks, veto) with re-review on edit | 🟡 | Shipped 2026-07-17 in PR #270: `PATCH /storybooks/{id}/versions/{v}/nodes/{node_id}` (`src/cyo_adventure/api/node_edit.py`) re-runs the validation gate and moderation on edit, `needs_revision` exists; admin-side editor is built, a dedicated guardian-facing review/edit surface still awaits |
| G7 | Cost gate: a story request spends generation budget only with guardian consent; per-child auto-allow is a guardian setting | ✅ | Consent step shipped (guardian request approval precedes any concept/GenerationJob, WS-B); budget/credit debiting completed 2026-07-17 in PR #270 (per its delivery banner: "G7 complete: consent debits quota on ALL spend paths incl. the legacy intake gate"); pre-auth envelopes are G3 |
| G8 | Kill switch: pull any published book off a child's shelf immediately, including offline copies at next connection | ✅ | `archived` state exists; offline-copy revocation delivered 2026-07-17 (client-side reconcile-on-fetch/reconnect against the authoritative `/v1/library` response, no backend change needed; `frontend/src/offline/revocation.ts`) |
| G9 | Engagement visibility: what each child is reading, how much, endings found, re-reads; literacy signals, not surveillance | ✅ | Shipped 2026-07-17 in PR #270: `GET /families/me/reading-summary` (`src/cyo_adventure/api/reading_history.py`), guardian-facing `frontend/src/guardian/ReadingPage.tsx` |
| G10 | Notifications that matter: child flagged content, a story awaiting action, a story ready; digest by default, alert on safety | 🟡 | Shipped 2026-07-17 in PR #270: `GET /notifications` projects `pipeline_event` into a guardian feed (`src/cyo_adventure/api/notifications.py`, `notifications/service.py`), rendered by `frontend/src/guardian/NotificationBell.tsx`. Poll-based (client re-polls with `since`), no push channel and no server-scheduled digest job; "digest by default, alert on safety" is a client polling-cadence convention, not yet a distinct delivery tier |
| G11 | Plain-language trust surface: what data is collected, where the AI text came from, who reviewed it, no training on child inputs, COPPA/GDPR-K posture | 🟡 | Privacy model and ADR-008 compliance are strong internally; no user-facing articulation specced |
| G12 | Data export and full account/family deletion | 🟡 | Deletion-readiness and Apple revocation specced; user-facing export absent |
| G13 | Predictable cost model: quotas, "3 stories left this month", no surprise bills a child can trigger | 🟡 | Interim balance surface shipped 2026-07-17 in PR #270 (`GET /families/me/budget`, `budgetApi.ts`/`ProfilesPage.tsx`); ADR-008 full credits/IAP model for the public tier remains Phase 8 scope |
| G14 | Standard adult auth; multi-guardian households (two parents, a grandparent) | 🟡 | Supabase OIDC solid; multi-guardian implied by the data model, never specced |
| G15 | Device management: authorize and revoke devices, see which books are downloaded where, storage use | 🟡 | ADR-014 grants list/revoke ✅; download/storage visibility ❌ |
| G16 | Browse the curated catalog and assign books to their own children | ✅ | WS-E catalog visibility + assignment gate |
| G17 | Approve, decline, and revoke family connections for their own family, in each direction (share out and receive in); connections activate nothing without this consent | ✅ | ADR-016 requires dual-guardian consent; shipped 2026-07-17 in PR #270: paired consent columns (`db/models.py` `FamilyConnection`), `POST`/`DELETE /family-connections/{id}/consent`, and an enforced guard at the read path (`api/recommendations.py::_is_dual_consented()` requires both `consented_by_viewer_user_id` and `consented_by_sharer_user_id` before a connection is treated as active), superseding the prior holds-by-omission state |

## A: Admin capabilities

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| A1 | Moderation queue: flagged, uncertain, and reader/guardian-reported items, each showing why; decisions feed back into automated rules | ✅ | `needs_review` routing and global queue ✅; feedback-into-rules shipped as the WS-F propose-and-ratify suggestion dashboard over `pipeline_event`; kid/guardian reports (K15) shipped 2026-07-17 and feed this queue (`GET /admin/flags`) |
| A2 | Sample audits: random re-review of anything published without direct human review (becomes real if any auto-publish tier ever exists) | ❌ | Moot while A6 gates everything; register it so it survives any future gating change |
| A3 | Global policy levers: age-band definitions, theme taxonomy, classifier thresholds, banned-content lists | 🟡 | Per-band moderation thresholds are DB-backed, admin-editable with an audit trail (WS-A); band definitions and taxonomy remain code-level |
| A4 | Policy re-evaluation: re-screen the already-published catalog when policy or thresholds change | 🟡 | First cut delivered 2026-07-17 (Phase 5/M5): admin-only `POST /api/v1/admin/rescreen` (`moderation/rescreen.py`, `api/rescreen.py`) re-runs the deterministic policy/band gate plus Stage-0 classifiers over already-published family-tier books, scoped by an optional id list, and writes a `moderation_completed` pipeline event per book; a flagged book is never auto-unpublished (ADR-005), only surfaced for an admin to archive by hand. Full public-catalog re-screen (Phase 9) and an admin UI hook still ❌ |
| A5 | Incident path: trace how content reached a child (prompt, model, gate version), pull it everywhere including offline, notify affected guardians | 🟡 | Provenance supports trace ✅; pull-everywhere (offline copies) delivered 2026-07-17, same client-side revocation reconcile as G8 (`frontend/src/offline/revocation.ts`); guardian notification still ❌ |
| A6 | AI safety gate: the admin's recorded approval is the only path from generated content to a child (approve-and-publish) | ✅ | ADR-005 as amended; state machine with no bypass; ratified 2026-07-16 (decision 3) |
| A7 | Pipeline observability: success/failure rates, queue depth and latency, rejection reasons by stage, cost per story, per-provider quality | 🟡 | `pipeline_event` captures every transition and the WS-F dashboard aggregates moderation outcomes; cost/latency/yield operational views still ❌ |
| A8 | Pipeline levers: switch or disable providers, tune prompts/templates, set rate limits and cost caps, kill a runaway job | 🟡 | Config-pinned swap + fallback cascade ✅; per-request provider/model against a server-side allowlist shipped (WS-C), with allowlist + authoring-queue admin UI in PR #268; kill-job and caps surfaces still ❌ |
| A9 | Curated/seed catalog management so a new child never sees an empty shelf | 🟡 | Catalog visibility + "curated starter library" (ADR-008); management surface thin |
| A10 | Admin-initiated story generation (seeding the catalog, testing the pipeline) | ✅ | Shipped (WS-B): `POST /story-requests/authored`, admin catalog-targeted with no family; ADR-015 names it foundationally |
| A11 | Structural quality tools across the corpus: broken graphs, reading-level drift, repetitive or template-y output | 🟡 | Per-story validator is world-class; corpus-level drift/repetition tooling ❌ |
| A12 | Account support ops: lockouts, deletion requests, abuse handling (an adult misusing generation) | 🟡 | PR #267 (open) delivers user/family lifecycle management: invites, edit, deactivate with auth-boundary enforcement and self-lockout guard; deletion-request and abuse workflows still ❌. Per the 2026-07-16 review condition: PR #267 also grants the admin console authority to set and reset a child profile's picker PIN (`PATCH /admin/profiles/{profile_id}`, `api/admin_profiles.py`), named here explicitly as an A12 admin-support capability rather than left implicit in the CRUD description; cross-reference [ADR-014](./adr/adr-014-device-authorized-kid-access.md), which defines the picker PIN as a convenience lock behind an already-authenticated guardian/admin bearer, not a security boundary in its own right |
| A13 | Admin action audit trail: admins touching child-related data leave a trail | 🟡 | Approver stamps and `acting_role` audit stamps ✅; no audit view/report |
| A14 | Compliance and platform ops: retention enforcement, compliance reporting, backups and tested restore | 🟡 | ADR-007 retention, backups live, restore drill planned; compliance reporting ❌ |
| A15 | Administer family connections: broker, list, and remove connection records on request; admin action never substitutes for guardian consent | 🟡 | Console shipped in PR #267 (open); ADR-016 subordinates it to G17 consent |
| A16 | Generate and manage AI cover art per storybook version, reviewed on the approval surface before it reaches a child | 🟡 | RULED 2026-07-16, recorded in [ADR-017](./adr/adr-017-ai-cover-art.md); shipped (covers/ module, admin trigger, R2 storage, best-effort with fallback). **Open gap (H2, security-hardening-plan-2026-07.md, unresolved as of 2026-07-20)**: `generate_cover` flips `cover_status` straight `generating -> ready` with no moderation/approval gate, so a cover image can reach a child's shelf without the human review this capability's own definition promises; the story text guarantee (A6) is unaffected |

## S: System capabilities (cross-cutting)

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| S1 | Offline as a first-class mode: reading, choices, progress, and flags all work offline and reconcile later | ✅ | ADR-002, sync rules, offline queue with idempotent replay |
| S2 | Multi-device conflict resolution that never silently loses a child's progress | ✅ | Revision-based 409 model; kid-facing presentation tracked as K12 |
| S3 | Story representation that supports the format: branching graph, state, conditions, multiple ending types | ✅ | ADR-001, ADR-006, ADR-011; deeper than the expectation |
| S4 | Deterministic pre-publication validation that a story is playable (no dead ends, orphans, traps, unsatisfiable paths) | ✅ | Two-layer gate incl. state-space walk; RULED 2026-07-16: repair output must re-run the gate and the band policy must fail closed on an unconfigured band (fixes implemented on this branch) |
| S5 | Age-banding as the system-wide spine: reading level, theme intensity, safety thresholds keyed off one per-child band | ✅ | ADR-011 |
| S6 | Human-legible provenance per story: who or what created it, checks passed, approver, when | ✅ | Per-version model/provider/prompt/approver stamps |
| S7 | Independent safety pipeline: moderation independent of the generator; no path to a child bypasses the automated gates plus the human gate | ✅ | ADR-005, ADR-010, prompt-injection defenses |
| S8 | End-to-end request flow: initiate (K/G/A) -> guardian cost gate -> generation -> validation/moderation -> admin gate -> shelf, with honest async status | 🟡 | Flow shipped end to end (WS-A..G: request -> guardian approve -> admin authoring plan -> pipeline -> admin release) except budget accounting at consent and kid-facing status; ADR-015 is the foundational record |
| S9 | Notification/event delivery infrastructure underlying K12, G10, and admin alerts | 🟡 | Shipped 2026-07-17 in PR #270: `notifications/service.py` projects the append-only `pipeline_event` log into the K12/G10 feeds. Delivery is poll-based only (no WebSocket/SSE push, no scheduled digest job) - the "infrastructure" is a read projection, not a push transport |
| S10 | Privacy architecture: no child PII to providers, data minimization, deletion-readiness, no third-party trackers in the kid context | ✅ | Privacy model, PII guard, ADR-007/008/009 |
| S11 | Social boundary enforcement: no messaging or free text between users, no user/family discovery, no kid contact outside active parental approval; cross-family flows exist only through ring-2 connections | ✅ | ADR-016 + vision v1.3; enforcement is structural (no such surfaces exist) plus the ADR-016 validation criteria |
| S12 | System recommendations from anonymized aggregate book scores (ring 3): no identity in or inferable from a global recommendation; minimum-population threshold before aggregates surface | 🟡 | Named as permitted future scope in ADR-016; no design |

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

## Unregistered scope: rulings

Per maintenance rule 3, work serving no register ID gets a conscious call. Found in the
2026-07-16 open-PR review; both now ruled:

- **Cross-family recommendation connections** (PR #267): RULED 2026-07-16 (decision 6).
  Registered as K17/G17/A15/S11/S12 and recorded in
  [ADR-016](./adr/adr-016-recommendation-sharing-social-boundary.md). The PR's substrate
  stands; the binding constraint is that no connection activates child-facing visibility
  until the dual-guardian consent flow (G17) exists.
- **Provider allowlist admin UI** (PR #268): serves A8 and is cited there; no separate
  ruling needed.

Added by the full traceability review (2026-07-16, see
[traceability-review-2026-07-16.md](./traceability-review-2026-07-16.md) section 2);
RULED by the owner later the same day:

- **Star ratings**: RULED, registered as **K18** (the owner's variant of thumbs up/down,
  feeding aggregate ratings/S12). Debt item U6 folds under K18.
- **AI cover-art subsystem**: RULED, wanted as a register item; K8 updated, **A16**
  minted, recorded in [ADR-017](./adr/adr-017-ai-cover-art.md).
- **Reader "Go back" button**: RULED, the app should have one; tech spec Runtime
  Semantics amended, K5 updated.
- **ADR-007 raw output**: RULED, admin reviews first, then the parent (a dual-role adult
  is covered by the admin capability); the job-detail endpoint is tightened to
  admin-only `report` access and ADR-007 amended. The parent may ultimately receive
  unedited LLM output when the admin approves without changes; accepted, since it has
  passed the automated gates and admin review by then.
- **Repair re-gate and band fail-closed**: RULED, both fixes ordered and implemented on
  this branch (S4 note updated).
- **G2 content controls**: RULED, will be built; scheduling open.
- **Admin child-PIN set/reset** (PR #267): still open, recommend naming in A12 with an
  ADR-014 cross-reference at PR review time.
- **Planned items lacking a design element** (not schedulable until one exists): Android
  release, web direct-billing channel, education/teacher persona, i18n catalog. Still
  open as a batch.

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
