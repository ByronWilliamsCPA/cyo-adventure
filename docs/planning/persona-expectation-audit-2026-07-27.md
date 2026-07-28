---
purpose: >
  Cross-persona UX expectation-gap audit. Surfaces workflows where the child,
  guardian, admin, or dual-role adult would reasonably expect something
  different than what is built, so each gap becomes an active product decision
  rather than an accidental one.
component: frontend, api, publishing, moderation, story_requests
source: >
  Four parallel persona audits (child, guardian, admin, dual-role) grounded in
  capability-register.md, user-journeys.md, roadmap.md, and the shipped
  frontend/backend code, 2026-07-27.
status: draft
audience: product-owner, engineering
---

# Persona Expectation-Gap Audit (2026-07-27)

## Purpose and method

The goal is not a bug list. It is to make sure that where the app does
something a user would not expect, that mismatch is a decision we made on
purpose, not one that slipped through. Four independent persona audits ran in
parallel, each grounded in `capability-register.md`, `user-journeys.md`,
`roadmap.md`, and the shipped code. Every finding is sorted into three buckets:

1. **Works differently than expected** - the element exists but behaves in a
   way the user would not anticipate.
2. **Expected but absent** - something the user would reasonably expect that is
   not present.
3. **No choice where one is expected** - the app forces a behavior the user
   might expect to control.

Each finding is tagged **intentional** (a deliberate decision, ADR/register
cited) or **oversight** (looks like drift or a wiring gap). The action for an
*intentional* item is: confirm it is still the decision you want, and consider
whether the UI communicates it. The action for an *oversight* is: decide
whether to close it.

---

## The two cross-cutting patterns

Read these first; most individual findings are instances of one of them.

### Pattern A - The guardian/admin split (the big one)

The guardian *initiates, funds (budget envelope), and scopes (per-child content
caps)* a story. But every gate that actually *moves a story toward a child* is
admin-only:

| Step that advances a story | Who holds it |
| --- | --- |
| Approve the *request* (spend budget, ratify idea) | Guardian |
| Pick authoring plan / provider / model -> **starts generation** | Admin only |
| Read/review the generated prose | Admin only |
| Edit or reject a passage | Admin only |
| Approve + publish (the ADR-005 human gate) | Admin only |
| Archive / un-publish | Admin only |

This is deliberate (ADR-005 mandatory human approval, ADR-015 request gating).
It is also the root of the largest cluster of surprises for three of the four
personas, and it is most acute in a one-adult, guardian-only household, where
that adult can never release a story to their own child. **The design is
sound; the question is whether the product intends the guardian-only account to
be a genuine standalone persona, or effectively a companion to an admin.**

### Pattern B - Backend authority with no UI (cheap to fix, not decisions)

Several transitions exist and are correctly authorized server-side but have no
button in any console. These are not product decisions; they are wiring gaps
that read as missing features:

- `POST /storybooks/{id}/archive` - the *only* documented un-publish path.
  No UI anywhere. (Admin finding A; guardian finding 1.4.)
- `POST /storybooks/{id}/submit` - returns a `needs_revision` story to
  `in_review`. No UI on either side, so send-back is a one-way street.
  (Admin finding C.)
- `POST /admin/rescreen` - re-evaluate the catalog after a policy change. No UI
  hook. (Admin finding B.)
- `DELETE /profiles/{id}` - fully implemented, GDPR/COPPA-compliant cascade.
  Guardian console renders no delete button. (Guardian finding 2.3.)

---

## Documentation and register drift (verify before trusting status)

Independent of the personas, the audits surfaced several places where the
register or journey doc claims a capability is shipped, but the code does not
match. These matter because they make the app look more complete than it is
and can misdirect release decisions.

| Claim | Reality | Source |
| --- | --- | --- |
| K19 "reflect-back to the child in kid terms" marked DELIVERED | The kid UI renders no `interpretation`; `RequestStory.tsx` shows only generic status strings. Register's own note admits the frontend dependency is OPEN. | Child 2A |
| "Avatar flips to a 'new story ready!' pill" marked Shipped in journeys | `ProfilePickerPage.tsx` renders no status pill; deferred to C4a-6. | Child 2B |
| G8 guardian kill-switch "pull any published book off a child's shelf immediately" | No guardian unassign and no guardian archive exist. Admin archive removes the book family-wide. G8 is materially weaker than asserted. | Guardian 1.4 |
| Journey Act 5 "An approved story is assigned to the child it was written for" | No auto-assign on publish; guardian must manually assign or the child never sees it. | Guardian 1.3 |
| Stale code comments | `ProfileFormDialog.tsx:179-185` says the backend 422s on `request_auto_approve`/`monthly_request_envelope`; `api/profiles.py` now accepts them. | Guardian (maintainer note) |

---

## Findings by persona

Severity is the persona auditor's estimate. "Intentional" items still deserve a
confirm-and-communicate pass; "oversight" items deserve a fix/no-fix decision.

### Child (kid)

| # | Bucket | Finding | Sev | Kind |
| --- | --- | --- | --- | --- |
| 2A | Absent | K19 reflect-back promised but the kid UI shows none of it; child gets only "waiting for a grown-up" | High | Oversight (register-flagged OPEN) |
| 1A | Differently | "Your story is being written..." can display forever; "on your shelf" is a client-side title guess with no request->storybook link, so non-series ideas never flip to done | Med | Oversight |
| 2B | Absent | No "new story ready!" pill on the Profile Picker; child must open each sibling shelf to find a new book | Med | Oversight (doc says shipped) |
| 3A | No choice | Child cannot enable read-aloud themselves; gated on guardian `tts_enabled`, no child-side request path, invisible to the youngest readers who need it | Med | Partly intentional |
| 3B | No choice | Child cannot pick or change their own avatar (guardian-set, preset-only) | Med | Intentional (#65) |
| 3D | No choice | Reader text size is device-local (localStorage), unlike `tts_enabled`/`reduce_motion` which sync per-profile | Low | Oversight |
| 1B | Differently | Progress bar under-fills mid-story (denominator = all nodes, not the reachable branch) | Low | Intentional |
| 1C | Differently | Declined/blocked ideas give no reason, so a child may resubmit the same blocked idea | Low | Intentional (safety) |
| 1D | Differently | Multi-device 409 silently relocates the child (newest-write-wins), can move them backward with no dialog | Low | Intentional (S2/K12) |
| 3C | No choice | A rating cannot be cleared/undone (no delete endpoint) | Low | Documented debt (U6) |
| 2C | Absent | No manual bookmark / mark-my-spot (auto-resume exists) | Low | Deferred (Phase 4b) |

Solid and *not* gaps (so we do not re-investigate): go-back undo (K5),
always-visible Leave, endings tracker (K6), offline-honest shelf tiles,
kid-language error/empty states, PIN "ask a grown-up" escape, cross-profile
IDOR refusal from cache.

### Guardian (guardian-only)

| # | Bucket | Finding | Sev | Kind |
| --- | --- | --- | --- | --- |
| 3.1 | No choice | A guardian cannot approve/publish any story, even one their own child requested; the gate is a global admin | High | Intentional (ADR-005) |
| 3.2 | No choice | A self-signed-up guardian is inert (cannot even load `/v1/me`) until an admin approves the account | High | Intentional but surprising |
| 3.3 | No choice | A guardian's approved request does not start generating; an admin-only authoring-plan step does, with no guardian visibility | High | Intentional (ADR-015) |
| 1.1 | Differently | "Approve" approves the *request* (budget/idea), not the *story*; toast says "the story is being made" when, for a child request, nothing is generating yet | High | Oversight (messaging) |
| 2.1 | Absent | A guardian cannot read/preview the full prose before the child does; the review surface is admin-only | High | Register-flagged (G6) |
| 1.4 | Differently | G8 kill-switch: no guardian unassign, no guardian archive; only admin can archive, and that removes the book family-wide | Med-High | Oversight vs register claim |
| 1.2 | Differently | Guardian's own intake generates immediately, but an approved child request does not; two entry points the journey presents as equivalent behave differently | Med | Oversight |
| 1.3 | Differently | Publish does not put the book on the child's shelf; a separate manual assign is required (journey doc implies auto-assign) | Med | Oversight vs doc |
| 2.2 | Absent | No guardian-facing edit/reject of prose before publish (admin editor exists) | Med | Register-flagged (G6) |
| 2.3 | Absent | Delete-a-child-profile has a full backend but no guardian UI | Med | Oversight |
| 3.4 | No choice | Content caps can only tighten below the age band, never loosen above it | Med | Intentional (K13/S5) |
| 1.5 | Differently | Async multi-gated pipeline shows only a coarse "Generating..."; no stage, no ETA, no push | Med | Intentional |
| 2.4 | Absent | No data export (family deletion exists; export does not) (G12) | Med | Known |
| 2.5 | Absent | No push tier / "story ready" push; notifications are poll-only (G10/S9) | Med | Known |
| 2.6 | Absent | No plain-language trust/privacy surface (provenance, no-training) (G11) | Med | Known |
| 2.7 | Absent | No cancel of an in-flight request/job; provider/model/cost are admin-side (budget envelope is the one guardian lever) | Med | Mixed |
| 3.5 | No choice | Avatars preset-only, no child photo | Low | Intentional (COPPA) |
| 2.8 | Absent | No device download/storage visibility (G15) | Low | Known |

### Admin

| # | Bucket | Finding | Sev | Kind |
| --- | --- | --- | --- | --- |
| A | Absent | No archive / un-publish control anywhere in the UI; the safety operator's only "undo" is reachable only by raw API | High | Oversight |
| C | Absent | Send-back is one-way; no resubmit-for-review control returns a `needs_revision` story to the queue | Med-High | Oversight |
| B | Absent | No re-screen UI; the only policy-re-evaluation lever is unreachable | Med | Intentional-but-incomplete (A4) |
| D | Absent | No kill-job or cost-cap operator controls (A8) | Med | Deferred |
| E | Absent | No pipeline/operational observability; the "dashboard" is a moderation-threshold evidence view, not an operator health panel (A7) | Med | Deferred |
| G | Differently | Threshold changes are not retroactive; the lever silently affects only stories screened after the change | Med | Intentional but surprising |
| H | Differently | "Approve" publishes immediately and (given A) irreversibly; "Catalog" is a one-click global share guarded only by text | Med | Works-as-designed, sharp edge |
| I | Differently | Editing a passage re-gates structurally, but a fresh moderation BLOCK does not stop the save and status never advances; a stale page can approve pre-edit content | Med | Intentional (ADR-005) |
| J | Differently | The review surface hides sub-floor findings via a configurable noise floor; "screened clean" is a floored view | Low-Med | Intentional |
| F | Absent | No bulk actions in the review queue (fine at family tier, not at Phase 9 catalog scale) | Low-Med | Known |
| K | Differently | Audit-log `storybook_id` filter misses `kid_flagged` events; incident tracing has coverage holes | Low | Documented edge |
| L | No choice | Cannot force-publish an unscreened version (correct per S7; a hard no-override point) | Low | Intentional |
| M | No choice | Rescreen is synchronous, no scheduling/recurring re-evaluation | Low | Intentional first cut |
| N | No choice | A flagged book is never auto-unpublished (correct direction, but combines with A into a manual archive with no UI) | Low | Intentional |

### Dual-role adult (guardian + `is_admin`)

| # | Bucket | Finding | Sev | Kind |
| --- | --- | --- | --- | --- |
| 1.1 | Differently | A dual-role adult can consent-as-guardian AND safety-approve-and-publish their OWN family's story; four-eyes fully collapses, with no `approved_by != requester` guard and no UI signal at the moment it happens | High | Intentional (ADR-007) but structurally invisible |
| 1.2 | Differently | The self-review collapse is invisible to a role-based audit query: own-family request approval stamps `guardian`, publish always stamps `admin`, so one human doing both shows as two roles on the same `user_id` | Med | Oversight |
| 1.3 | Differently | The global admin queues surface the adult's OWN family items with no self-flag; the reviewer gets no signal they are about to review their own household's content | Med | Intentional-ish, unflagged |
| 1.4 | Differently | Console switch does not preserve context (story/family/profile); it dumps the adult on the destination index. (Good: no re-login; the warm AdultGate spans both trees, and each shell labels the active hat.) | Med | Mixed |
| 2.1 | Absent | No unified inbox; the notification bell exists only in the guardian shell, so an admin-console dual-role adult is blind to guardian-feed alerts about their own children | Med | Oversight |
| 2.2 | Absent | No deep-link handoff from "my child's item" in one console to the matching action in the other | Med | Oversight |
| 2.3 | Absent | No warning banner when an admin reviews their own family's content | Med | Oversight |
| 3.1 | No choice | No option to skip admin review for your own family even though you ARE the admin; forced multi-step ordering across two consoles | Low | Intentional (A6/S7) |
| 3.2 | No choice | Forced separate navigation between the two capacities; no single "adult console" | Low | Intentional |

Works correctly (do not re-investigate): warm AdultGate spans both trees (no
re-login on switch); active hat is labeled per shell; admin capability does not
silently widen the everyday guardian list (`GET /story-requests` is
family-scoped for all callers); guardian-only acts (Books, Profiles, G17
consent) gate on the base `guardian` role, not `is_admin`; cross-family actions
are correctly stamped `admin`.

---

## Recommended decision agenda

Grouped so each row is one active decision to make. Nothing here is a
recommendation to change behavior on its own; the point is to convert accidents
into choices.

### Tier 1 - decisions taken (2026-07-27, product owner)

The three Tier-1 questions were walked through and answered:

1. **Guardian-only is the typical-parent persona and is a genuine standalone
   role.** In the normal case the admin is a separate operator who reviews
   across families, so the guardian/admin split (Guardian 3.1/3.2/3.3) is
   confirmed intentional: every ordinary guardian has an admin behind them.
   The one exception is the app owner, who must be both admin and the guardian
   of their own children.
2. **Four-eyes review collapses only for the owner's own family, and that is
   accepted.** Chosen visibility: **audit fix only** - no UI banner, but the
   pipeline-event actor stamping is to be made consistent so one `user_id`
   performing both request-approval and publish is detectable in the log
   (closes Dual 1.2's role-stamp inconsistency; Dual 1.1 stays accepted).
3. **Recovery model: admin family-wide archive + guardian per-child unassign.**
   Wire the existing admin archive endpoint to a button, and build the real G8
   (a guardian per-child unassign, including its reading-state and
   offline-cache handling). Register G8 to be corrected to match.

Copy decision (Tier 3, actioned same day): the guardian approve toast uses the
**queued/soft-ETA** wording. Landed on branch `docs/persona-ux-audit`:
`RequestsPage.tsx` override and the shared `StoryRequestQueue.tsx` default now
say the story is queued and will be written soon (not "being made"), and the
two stale descriptions of approve-enqueues-generation were corrected
(`api/story_requests.py` module docstring; `StoryRequestQueue.tsx` concurrency
comment). Tests updated; 44 pass.

Resulting backlog: (a) audit-stamp consistency fix [decision 2]; (b) admin
archive button [decision 3]; (c) guardian per-child unassign + G8 correction
[decision 3]; plus the still-open Tier-2 wiring gaps and Tier-3 items below.

### Tier 1 - Decisions that change the product's shape

1. **Is the guardian-only account a standalone persona?** If yes, the
   one-adult household cannot currently release a story to their own child
   (Guardian 3.1/3.2/3.3). If no, say so and design onboarding around
   admin-companionship. (Pattern A.)
2. **Do we accept the four-eyes collapse for dual-role adults on their own
   family, and if so, do we surface it?** The collapse is intentional
   (ADR-007), but there is no `approved_by != requester` guard and no UI signal
   (Dual 1.1). Minimum: a self-family banner at approval (Dual 2.3) and a
   consistent actor-role stamp so audit can detect it (Dual 1.2).
3. **What is the real un-publish / recovery story?** Archive is the only exit
   from `published` and has no UI for admin or guardian, while G8 claims a
   guardian kill-switch that does not exist (Admin A, Guardian 1.4, Dual N).

### Tier 2 - Wiring gaps (backend exists, decide whether to expose)

1. Admin archive/un-publish button (Admin A).
2. Admin resubmit-for-review button so send-back is not one-way (Admin C).
3. Guardian profile-delete button (Guardian 2.3).
4. Auto-assign-on-publish, or fix the journey doc that promises it (Guardian 1.3).

### Tier 3 - Messaging and status honesty

1. Fix the two-"approve" collision: the guardian toast should not say "the
   story is being made" when a child-initiated request still needs the admin
   authoring-plan step (Guardian 1.1/1.2). **Done 2026-07-27** on branch
   `docs/persona-ux-audit` (copy + stale-comment corrections).
2. Link a request to the storybook it produced so the child's "being written"
   state can flip to done (Child 1A), and add the "new story ready!" pill or
   correct the doc (Child 2B).
3. Ship the K19 kid-facing reflect-back, or downgrade its register status from
   DELIVERED (Child 2A).

### Tier 4 - Confirm-and-communicate (intentional, likely fine)

Threshold non-retroactivity (Admin G), progress-bar denominator (Child 1B),
no-reason declines (Child 1C), content caps tighten-only (Guardian 3.4),
preset-only avatars (Child 3B / Guardian 3.5), forced dual-console navigation
(Dual 3.1/3.2). For each: confirm it is still the intent and that the UI (or a
help surface) explains it.
