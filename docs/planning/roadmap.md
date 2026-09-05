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

> **Status**: Active | **Updated**: 2026-09-05 (six-agent code-verification audit; see the
> "2026-09-05 Plan Audit" section. The dated sections below are cumulative: read the Milestones
> table and the newest dated section first, since the "Current Status (2026-07-03)" header is the
> oldest status statement in this document, not the newest)
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
| 4b Editor + Engagement | ✅ Substantially delivered | Shipped 2026-07-17 in PR #270: node editor (`PATCH .../nodes/{id}`), endings tracker UI, read-aloud/TTS, guardian content-controls UI (banned themes), per-child permission envelopes, kid feedback flag. **Closed 2026-08-09**: bookmarks (`player/engine.ts`'s save/load/delete-bookmark functions, `BookmarksButton.tsx`, wired through the existing `save_slots` field); guardian device/storage view (new `device_download` table + `api/offline_downloads.py`, `DevicesPage.tsx` downloads section). Narrow remaining piece: the storage view's removal path is implemented but not wired into the client's automatic eviction (`downloadBudget.ts`, `revocation.ts`), both deliberately network-free modules; see the G15 register row for the exact scope boundary |
| 4c Family Loops (NEW 2026-07-16) | ✅ Delivered | Shipped 2026-07-17 in PR #270: notification feed (`GET /notifications` + `NotificationBell.tsx`), guardian engagement visibility (`GET /families/me/reading-summary` + `ReadingPage.tsx`), kid-facing generation status, budget consent (envelopes + `GET /families/me/budget`). Push channel closed 2026-07-28: authenticated SSE (`GET /api/v1/notifications/stream`), `notificationsStream.ts` consumer wired into `NotificationBell.tsx` as a fallback-preserving addition to the poll (G10 flipped to ✅). **Closed 2026-08-09**: the server-scheduled digest job (`notifications/digest.py::run_notification_digest`, `scripts/run_notification_digest.py`, `.github/workflows/notification-digest.yml`, daily) writes one batched summary event per family with pending info-severity notifications since their last digest; S9 flips to ✅. In-app delivery only, no email/push provider is wired (see the S9 register row for the explicit scope boundary) |
| 4d Connections (NEW 2026-07-16) | ✅ Substantially delivered (2026-07-20 audit) | Shipped 2026-07-17 in PR #270: dual-guardian consent flow with an enforced guard at the recommendations read path (`api/recommendations.py::_is_dual_consented()`), kid-facing recommendation chips. Privacy-model erasure coverage closed 2026-08-09: `test_delete_my_family_cascades_family_connection` in `test_deletion_drill.py` now proves the CASCADE end to end. Still open: no integration or e2e test drives ring-2 dual consent itself over the real stack |
| 5 Hardening | 🟡 Partially delivered | Redis-backed rate limiter, ADR-007 purge job, offline-copy revocation, operator runbook, re-screen first cut, Sentry on client and server, admin audit view, H1 and H2 closed, nightly/staging/prod E2E ladders scheduled, weekly perf and Lighthouse budgets, daily encrypted backups (all verified against code 2026-09-05). Remaining: the restore drill has never been recorded, no capacity baseline, the adversarial safety run is executed and red on class A (`UW-C361`), review-model successor work (`UW-C02`, `UW-C04`) |

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

**2026-08-08 re-audit: items 1 through 4 are done.** (Prior 2026-07-20 status: 3 done, 1 done
modulo unverifiable infra secrets, 1 not done.) The change is item 2, whose only open caveat
was that the repo cannot see whether GitHub environment secrets are populated. That is now
settled, and by evidence rather than inspection: both scheduled tiers complete real
email/password sign-ins against their live targets, which is impossible with absent or wrong
secrets. This re-audit did not reassess item 5, which is owner-gated rather than engineering
work; read its own row below for current status rather than inferring it from this header.
Note that a tier being *red* does not reopen items 2 or 3: what those items claim is that the
harness exists and is wired, and a tier that runs, authenticates, and reports real assertion
failures has demonstrated exactly that.

1. ✅ **Done.** Both PRs merged (#267, #268, folded into #270). Both review conditions
   satisfied: `capability-register.md`'s A12 entry names the admin child-PIN authority
   with an explicit ADR-014 cross-reference, and `authorization-matrix.md` carries rows
   for the new admin endpoints (admin users CRUD, admin child-profile CRUD incl. PIN,
   family-connection CRUD).
2. ✅ **Done, and the secrets caveat is resolved.** `.github/workflows/e2e-staging.yml` exists,
   is scheduled daily, and references the three `staging` environment secrets. Re-verified
   2026-08-08: the 2026-08-07 run signed in and its main tier reported green, so the
   secrets are populated. Stated precisely, the tier ran 16 tests, 15 passing and 1 flaky;
   "15 of 15" would understate the retry. Its only red is the post-tier `device-grant-sweep`,
   which reports that the test family still holds active device grants. That is a known
   harness artifact, not a product defect and not a secrets problem: a serial-block retry runs
   on a **new** worker, so the failed first attempt never reaches its own revoke step and leaks
   its grant, while the retried attempt passes and the tier reports green. This run shows
   exactly that shape (test 15 failed, retried as 17-19 and passed, sweep then found the
   leak). One caveat the mechanism does not fully explain: the sweep names **three** grants
   (`bb2ced27`, `260fcc51`, `b631c2e2`), not one, which points at accumulation across runs
   rather than a single retry, and means the sweep is reporting a backlog that nothing clears.
3. ✅ **Done, same caveat resolved.** `e2e-prod.yml` exists (scheduled daily, 30 min after
   staging) with a dedicated "alert on failure" step that opens/comments on an issue labeled
   `e2e-alert`. Re-verified 2026-08-08: the `production-e2e` environment's secrets are populated
   and the tier authenticates against live production, evidenced by the 2026-08-07 run's 21
   passed. Note the environment name: the workflow deliberately does **not** use `production`,
   which carries a required-reviewer protection rule that would park a scheduled, unattended run
   in `waiting` indefinitely; `e2e-prod.yml` carries a `#CRITICAL` comment saying so. Its 2 failures are a real product defect it correctly caught
   ([#639](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/639) / `UW-L07`), and the
   alert path also works: the failure job is maintaining issue #623 as designed.
4. ✅ **Done.** `validator-rules.md` has a PL-22 entry (band profile fail-closed);
   `authorization-matrix.md` carries rows for the already-shipped admin surfaces.
5. 🟡 **Owner side done 2026-08-06; blocked on external counsel.** The 2026-07-20 wording of
   this row ("Not done ... only a working recommendation and no progress note since
   2026-07-16") is **superseded and was already understating the position when written**: the
   ADR was substantively amended 2026-08-01 and again 2026-08-06. Current state, decision by
   decision: **D1** mechanism chosen and *implemented* (`POST /api/v1/onboarding` consent
   payload, `GuardianConsentPage.tsx`, gated by `api/profiles.py::_require_consent`), with one
   named legal question outstanding; **D2** child-directed posture confirmed by the owner
   2026-08-06; **D3** US-only confirmed 2026-07-20; **D4** artifact ownership confirmed (owner
   drafts, counsel reviews), with
   [information-security-program.md](../compliance/information-security-program.md) published
   and [data-retention-policy.md](../compliance/data-retention-policy.md) drafted 2026-08-06
   but **not yet published** (three data classes still await an owner ruling on their deletion
   window, tracked at `UW-N07`), and Safe Harbor sequencing settled as counsel-first; **D5**
   corpus constraint confirmed 2026-08-06. The
   packet counsel receives is assembled at
   [counsel-engagement-brief.md](../compliance/counsel-engagement-brief.md). The ADR stays
   `status: proposed` and this row stays open because the remaining work is external: retaining
   counsel and getting rulings. Register home: `UW-M03`. **This is a long-lead item on the
   critical path to Phase 7 and the R2/R3 rungs, and it does not block R1;** every week the
   engagement is not started is a week added to R2/R3 regardless of engineering pace.

### Where every open register item lands

| Register items | Phase |
|----------------|-------|
| K6 tracker, K7 TTS, G6 editor, G5 skim aids, G3 permissions, K15 feedback flag | 4b |
| G15 storage view (report path live 2026-08-09; removal path not wired into automatic client-side eviction, see the register row) | 4b |
| Closed, corrected 2026-08-09 (were listed above as open, code verification found them delivered): K5/K8 test pins (`reader-go-back.spec.ts`, `admin-review-cover.spec.ts`, `BookCard.test.tsx`, all present in the working tree; `reader-go-back.spec.ts`'s own docblock records "Ratified 2026-07-16... this is its first E2E pin" -- the earlier "added 2026-08-04" note in this row was a git-log first-appearance date read off this repo's reconstructed/squashed history, not a real authorship date, and is corrected here), G2 controls UI (`ProfileFormDialog.tsx` banned-themes field + `story_requests/brief.py:122` wiring) | n/a |
| G9 visibility, K12 kid generation status, G7 budget consent. Closed since this table was written: G10 digest/alerts 2026-07-28 (SSE push transport shipped, register flipped to ✅), G13 interim quota balance 2026-07-29 (audit found budget enforcement and kid-facing status already shipped and tested, register flipped to ✅), G14 multi-guardian households 2026-07-28 (guardian self-service co-parent invite shipped, register flipped to ✅), and S9 delivery infra 2026-08-09 (server-scheduled digest job shipped, register flipped to ✅) | 4c |
| G17 consent flow, K17 recommendation surfaces, A15 enforcement guard | 4d |
| ADR-007 purge, G8/A5 offline revocation, nightly e2e-real + S2 real conflict spec, staging golden journeys, adversarial live-model run | 5 |
| K24 persistent character (minted 2026-08-08, v1.10): runtime delivered on branch `feat/persistent-characters-runtime` (creator/picker UI, server-derived binding and seed snapshot, idempotent progression writeback); no catalog book participates yet, so no reader can exercise it. Remaining work is the pathfinder pilot skeleton and its K18 ratings-comparison decision, tracked as [UW-A46](./unscheduled-work-register.md) | 5 |
| ADR-018 D1-D4 execution, G11 trust surface, G12 export, A12 abuse workflow, A14 compliance reporting | 7 |
| G13 full credits/IAP | 8 |
| A9 curation surface, A7 ops dashboards, A8 runtime levers, A4 full catalog re-screen | 9 |
| K21 collection/badges, K22 weekly reading ring, K23 day-grain reading time, G19 gamification controls (minted 2026-08-01, v1.9) | Kid-appeal implementation plan wave 3 ([kid-appeal-implementation-plan.md](./kid-appeal-implementation-plan.md)); backend and kid UI landed 2026-08-01. Open residuals: guardian ReadingPage time display, badges 9/12, teen self-set ring goal, retention job |
| S12 ring-3 recommendations, A11 corpus quality tooling | Post-launch backlog |
| Android, web direct billing, education persona, i18n | Parked: each needs its design element first (no ADR/register ID) |

**Added 2026-07-28, proposed not ratified.** The linkage check
(`scripts/check_work_linkage.py`) proved this table was incomplete: eleven capabilities are open
(🟡 or ❌) yet appeared nowhere above, which is exactly the orphan condition the check exists to
catch. They are placed here so the check can see them; the phases below are the audit's proposal
and need the owner's ratification before they count as commitments.

| Register items | Proposed phase |
|----------------|----------------|
| A3 band definitions and theme taxonomy as admin levers (thresholds already shipped) | 9, with A8 runtime levers |
| K20 kid-facing personalization, G18 guardian per-slot opt-in | Blocked on [ADR-023](./adr/adr-023-story-personalization-slots.md) moving from Proposed to Accepted. No phase until that ruling; tracked as a `decision`, not a scheduling gap |
| A2 sample audits of auto-published stories | Post-launch backlog, conditional: A6 gates every publish through a human today, so this is moot unless an auto-publish tier is ever introduced. It stays registered so the conditional survives |

**Amended 2026-07-29, union of the in-flight branch corrections.** Both tables above now carry the
same closures, so the in-flight UI branches record one consistent view instead of each dropping the
others' edits. Removed as closed rather than scheduled: K1, K9 and K10 (kid-surface presentation and
connectivity UX), K11 (kid-terms request initiation, which the audit confirmed shipped end to end),
G13 interim quota balance, G14 multi-guardian households, S8 request-flow remainder, A13 audit view,
A16 cover-art review, and A4's Phase 5 re-screen UI hook (A4's full-catalog re-screen stays in Phase
9). Each closure is evidenced in [capability-register.md](./capability-register.md). Where a row in
that register still reads 🟡 here, the flip travels with the branch that closed it and lands
when that branch merges; this note is the shared phase home in the meantime, so no closed-or-closing
capability is left unscheduled.

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
  production-eligible skeletons") is stale: 84 skeleton shells (81 flagged `production_eligible`, 74 reachable in an offered cell,
  per [catalog-census.md](./catalog-census.md) at 2026-08-22; it was 61 and 58 when this bullet
  was written) and 23 filled stories are committed to `main` (PRs #289, #292, #297). **Corrected
  2026-09-05**: they were imported to production on 2026-07-21 (issue #347) and 10 are published
  with `visibility='catalog'` as of the 2026-08-25 recount (`UW-G14`), so "zero in the catalog"
  is no longer accurate either; 17 remain `in_review` behind the Stage D sweep.
- Design docs describing real, still-open, unscheduled work with no reference anywhere in
  either master document: [catalog-first-inventory-gap.md](./catalog-first-inventory-gap.md)
  (family-scoped import blocks an admin-authored base catalog),
  [admin-guardian-dual-roles-plan.md](./admin-guardian-dual-roles-plan.md) (dual-role adult
  redesign, identifies real scoping-fork security risk),
  [skeleton-corpus-story-generation-test-plan.md](./skeleton-corpus-story-generation-test-plan.md)
  (0/21 skeletons proven end-to-end).
- Issues #125 (Supabase RLS not enabled on 13 public tables) and #214 (R2 cover-art backfill),
  both cited in `handoff-r2-readiness-2026-07-11.md` (retired in PR #444; recoverable via
  `git show 4afe490~1:docs/planning/handoff-r2-readiness-2026-07-11.md`), appear in neither
  master document by number or description.
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
this audit did not find them newly stale. **Superseded 2026-07-28**: that claim is false, see the
next section.

## 2026-07-28 Plan Audit: the unscheduled-work sweep

A six-agent sweep of every ADR, handoff doc, workstream design doc, review report, register, code
marker, and open GitHub issue looked for one thing: work that some document **directs** but no
document **schedules**. It found roughly 250 such items before consolidation; deduplicating
overlapping findings from different agents brought the register to 217 rows. All of them now have a stable `UW-*` ID and
a proposed phase in the [unscheduled work register](./unscheduled-work-register.md), which is the
placeholder mechanism this section refers to throughout. Item-level detail lives there; this section
records only what the sweep changes about the plan itself.

**The finding is structural, not clerical.** This project runs four ID namespaces, and only one of
them is wired into a phase:

| Namespace | Source | Mapped into phases? |
|-----------|--------|---------------------|
| `K`/`G`/`A`/`S` | [capability-register.md](./capability-register.md) | 🟡 via "Where every open register item lands" above, but 11 open capabilities were missing from it until the linkage check found them; see that section's 2026-07-28 addendum |
| `C`/`GS`/`U`/`T`/`P`/`SL` | [r1-deferred-debt-register.md](./r1-deferred-debt-register.md) | ❌ zero debt IDs cited in either master document |
| `AL-*` | [authoring-lessons-log.md](./authoring-lessons-log.md) | ❌ zero `AL-` hits in either master document |
| GitHub issues | the tracker | ❌ 19 of 33 open issues named in no planning document |

Work therefore did not get lost through carelessness. It got lost because three of four intake
channels had no exit into a phase. `UW-B*` and `UW-C*` close that by assigning phases to the debt
register and the lessons log wholesale, without restating their contents.

**Corrections to claims made above in this document:**

1. The 2026-07-20 note that open issues "remain accurately tracked" in the debt register is wrong.
   The register cites 9 issue numbers, 6 still open, against 33 open issues (`UW-D*`).
2. ~~Phase 4b marks `G2` controls delivered. The intake UI hardcodes empty arrays and the profile form
   has no banned-theme field, so `G2` is partial (`UW-J15`).~~ **Corrected 2026-08-09: this note was
   itself stale.** Code verification found `ProfileFormDialog.tsx` has a working banned-themes chip
   UI (add/remove, submitted as `banned_themes`), `IntakePage.tsx` reads the profile's real
   `banned_themes` (explicitly commented "instead of the previously hardcoded empty list"), and
   `story_requests/brief.py:122` sets `content_nogo = list(profile.banned_themes or [])`. `G2` is
   fully delivered; `UW-J15` should be closed, not tracked as open partial work.
3. The 2026-07-20 note lists `admin-guardian-dual-roles-plan.md` as unstarted, unscheduled work. The
   work shipped; only three open decisions remain (`UW-K16`).
4. The follow-up pass that the 2026-07-20 audit deferred (reconciling PRs #311, #321, #323) is still
   not done, and roughly 20 further releases have merged since (v0.20.0 through v0.40.1), including
   ADR-022, ADR-023, and ADR-024.

**Decisions with no plan presence at all.** Three ADRs return zero hits in this document and in
PROJECT-PLAN.md:

- **[ADR-022](./adr/adr-022-tiered-rls-scoping.md)** (tiered RLS scoping) returns zero hits in all
  four planning documents. It is the only database-enforced backstop for children's PII, and it is
  downstream of an ADR-021 production cutover that is itself untracked (`UW-A01`, `UW-A03`). Until
  that cutover provisions the `cyo_api` and `cyo_worker` role passwords and retires `postgres`-role
  traffic, **RLS is enabled but disarmed**.
- **[ADR-023](./adr/adr-023-story-personalization-slots.md)** (personalization) exists only in the
  capability register. Its Stage A shipped and its **G1 gate fired STOP at 3.3% sentinel survival**,
  voiding Stages B through D pending a re-plan. Recorded as blocked, which is its real state
  (`UW-H*`).
- **[ADR-024](./adr/adr-024-bounded-backtracking-path-replay.md)** (bounded backtracking) returns
  zero hits anywhere, including the reader-UX work that implements it (`UW-A11`, `UW-I02`).

**Two blocking items were sitting in the post-launch backlog.** Both arrive there because the
authoring lessons log's only plan linkage is one sentence inside capability row `A11`, which this
document files under post-launch:

- **`AL-014` (`UW-C01`): partially closed, corrected 2026-08-09 (was listed here as a flat
  blocker; that's stale).** `scripts/check_promotion_bundle.py` (PR #532, commit `4b6fe922`,
  2026-08-01) now runs `check_skeleton` (gate/cell/envelope) and `check_theme_contract` for a
  lineage-less shell and skips only the two parent-relative legs, confirmed by
  `test_hand_authored_shell_still_runs_the_non_lineage_checks`, so a hand-authored skeleton with
  no `.lineage.json` sidecar can, in fact, pass the CI gate today, contrary to this line's
  original wording. **Still genuinely open**: the WS-5 anti-clone floor (`check_incell_clones`)
  is parent-relative and cannot run without a lineage parent, so an original is not proved against
  its in-cell siblings; that remaining piece is tracked separately as `UW-C06`. The lessons log's
  `AL-014` row correctly stays `status: open` (the full proposed change, including the anti-clone
  floor, is not yet complete) rather than being flipped to `applied`.
- `AL-036` (`UW-C02`): the review surface cannot deliver the human approval ADR-005 requires at 746
  nodes. This undercuts the `A6` safety gate, so the approval attests less than the ADR claims.

**One release blocker.** `docs/known-vulnerabilities.md` carries PYSEC-2022-42969 (`py`, reached via
`interrogate` 1.7.0) and PYSEC-2026-89 (`markdown`, CVSS 7.5) at 68 days old, with reassessment due
2026-07-20 and now 8 days overdue. The OpenSSF release gate blocks releases for any vulnerability
older than 60 days regardless of reassessment status (`UW-K01`).

**Two live defects** were found and filed as issues rather than tracked as plan rows: RESTART on a
continuation read discarding carried series state and the continuation entry node
([#460](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/460), `UW-L01`), and a
commit-after-response race in the request session dependency
([#461](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/461), `UW-L02`).

**Phase impact.** The register assigns work to phases as follows; the phase checklists below carry
the safety-relevant and blocking items inline, and everything else is held by ID in the register.

| Cluster | Phase | Weight |
|---------|-------|--------|
| `UW-E*` security hardening (Medium and Low tiers, including three gate bypasses), `UW-F*` test hardening, `UW-C02`/`C03`/`C04`/`C05` authoring safety | 5 | largest single addition |
| `UW-G*` content diversity and catalog | new: see the Content workstream note | first phase home this workstream has had |
| `UW-I*`, `UW-J*` reader UX and console gaps | 4b | moderate |
| `UW-H*` personalization | 4b, blocked | recorded blocked, not scheduled |
| `UW-A15`, `UW-A16`, `UW-A19`, `UW-B13`, `UW-E14` processor records and counsel gates | 7 | gates App Store submission |
| `UW-A03` ADR-021 cutover | M4.1 | prerequisite for ADR-022 |
| `UW-K01` overdue CVEs, `UW-A40` ADR status flips, doc accuracy | now | small, unblocking |

**Deliberately not done in this pass**: nothing was rescheduled, no phase estimate was revised, and
no item was closed. The sweep establishes where work lives, not when it happens. Sequencing the
register against the existing phase estimates is the natural next pass.

## 2026-08-03: Story structure diversity program (pointer only)

A separate root-cause analysis and execution plan address why generated stories cluster into a few
base structures that swap themes rather than reading as distinct adventures:
[story-structure-diversity-critical-analysis.md](./story-structure-diversity-critical-analysis.md)
(the root-cause analysis) and
[story-structure-improvement-plan.md](./story-structure-improvement-plan.md) (the scheduling
document, with per-deliverable detail in
[story-structure-implementation-briefs.md](./story-structure-implementation-briefs.md)). The
improvement plan is the authority for scheduling this program, not this roadmap: it groups its
24 deliverables (SQ-01 through SQ-24) into five internal "Stages", a term chosen deliberately to
avoid colliding with this document's "Phase" vocabulary, since the Phase 0-9 ladder above is a
closed set with its own status semantics. This roadmap does not assign the SQ items a phase home;
see the improvement plan itself for their sequencing and owner gates.

## 2026-09-05 Plan Audit: code verification and the session protocol

Six Sonnet verifier agents each took one slice of this document and PROJECT-PLAN.md as allegations to
falsify against the tree, the registers, and live GitHub state, while the supervising session wrote
the corrections; the method is now standing procedure in
[implementation-session-playbook.md](./implementation-session-playbook.md) and `CLAUDE.md`'s
Implementation Session Protocol. Item-level corrections are inline above (Phase 5 checklist boxes,
the M4.1 and M5.1 rows, the phase table's Phase 5 evidence) and in PROJECT-PLAN.md's dated notes.
What the audit changes about the plan itself:

1. **Delivery is understated everywhere the plan was not re-read against code.** Eight Phase 5 items
   the checklist showed open were closed in the tree, several since 2026-08-01, when
   `plan-manifest.toml`'s own validation recorded them closed. The manifest and this document had
   drifted apart in the direction the manifest's header predicts: gap lists rot because nobody
   returns to a planning document after fixing something.
2. **Phase 9 is partially delivered.** The catalog shipped as `storybook.visibility='catalog'`
   rather than the planned state; ten books are in it. `plan-manifest.toml` moves Phase 9 to
   `shipped = "partial"`.
3. **The R2 window has closed overrun** (six to nine weeks after 2026-07-03), with Phase 6 partial
   and Phase 8 unstarted, while R1 beat its estimate by an order of magnitude. The critical path is
   owner-gated and external: counsel (`UW-M03`), Apple enrollment (P7-01), DPAs (P7-12), and
   production credentials for the re-moderation sweep (`UW-L08`, `UW-G14`). No estimate is
   re-baselined here; that is the owner's call and this is its input.
4. **Two register rows contradicted merged code** (`UW-A01`, `UW-A02`; ADR-022 is implemented and
   tested). Corrected in the register with the residuals named.
5. **The signals this document depends on were dark for weeks** and are repaired on the same
   branch: two scheduled jobs that had never executed, a mutation run that had never scored, a
   nightly tier red 37 nights, and a safety eval whose class A misses traced to an unpinned review
   model. See `AL-764` through `AL-772`.

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
| M4.1: R1-alpha sign-off | Funded provider keys; merged PRs + safety fixes redeployed; live E2E checklist executed once with a sign-off row; Now-queue items 1-4; **plus, added 2026-07-28: the ADR-021 production cutover (`UW-A03`), which the ADR itself names M4.1 as the review gate for** | ~1 wk | 🟡 Cutover done. Funded provider keys confirmed 2026-08-04; the ADR-021 production cutover (`UW-A03`) verified live 2026-08-04 (`cyo_api` holds all active production connections, `rolbypassrls=false`; see `UW-A03`/`UW-M08`); merged PRs and safety fixes redeployed (verified 2026-07-30). Now-queue items 1-4 are re-verified as of 2026-08-08 (all four done). **Corrected 2026-08-09**: `UW-L07` / [#639](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/639) (guardian profile resolution reading the Tier 1 table before the RLS context was applied, so every guardian in production saw zero profiles) is fixed in code: the GitHub issue was closed 2026-08-08 via PR #641 ("apply Tier 1 RLS context before guardian profile resolution"), which is merged and in the working tree (`api/deps.py:617-651`), with regression coverage in `test_rls_tier1_enforcement.py`. The fix shipped in the v0.68.2 release (CHANGELOG). **Re-corrected 2026-08-09**: the previous pass here read "closed... no longer a live blocker", which conflates "PR merged" with "deployed to production" -- exactly the distinction `UW-L07`'s own text warns against. The last recorded production deployment (`r1-live-e2e-checklist.md`'s sign-off table, 2026-08-08) is revision `631c0d8a` (v0.68.0), which predates v0.68.2 and therefore does NOT carry this fix; this repo has no evidence of a later deploy (the homelab-first deployment is owner-triggered and outside git history). **Still open, and #639 stays live in production until redeployed**: the live E2E checklist (`UW-F17`), which stands at **10 of 38** steps as of 2026-08-08 (unchanged at the 2026-09-05 audit: no later sign-off row exists, so the last recorded deploy is still `631c0d8a` v0.68.0 while `main` has released through v0.88.0; the repo cannot see whether production was redeployed in between), plus a redeploy to at least v0.68.2 to actually clear #639's production impact. The remaining 28 checklist steps stay owner-gated (interactive credentials, a maintenance window for the mutating worker-restart step, funded provider quota for Sections 2 and 4, and a second device for Section 5) |
| M4b: Editor + engagement | G6, K6, K7, G5, G2 usable by a real guardian, G3, K15, G15 view, K5/K8 test pins | 3-4 wks | ✅ Substantially delivered 2026-07-17 (PR #270). **Corrected 2026-08-09**: K5/K8 test pins are done, not open: `reader-go-back.spec.ts` and `admin-review-cover.spec.ts` cover Go Back state-fidelity and the admin cover-generate flow (`reader-go-back.spec.ts`'s own docblock records "Ratified 2026-07-16", consistent with this row's PR #270 delivery date, not the "2026-08-04" this row previously cited, which was a git-log first-appearance date off this repo's reconstructed/squashed history), and `BookCard.test.tsx` covers the letter-tile fallback; `test-traceability-matrix.md` already records both as ✅. **Bookmarks and G15 storage view closed 2026-08-09** (see the Phase 4b Deliverables section). Narrow remaining piece: G15's removal path is not wired into automatic client-side eviction |
| M4c: Family loops | S9, G10, G9, K12 complete, G7 real budget consent + G13 balance | 2-3 wks | ✅ Delivered. Push channel closed 2026-07-28 (SSE stream, G10 ✅); server-scheduled digest job closed 2026-08-09 (S9 ✅) |
| M4d: Connections | G17 consent, K17 surfaces, A15 enforcement guard (ADR-016 ring 2) | 2-3 wks, overlaps 4c | ✅ Delivered. Dual consent is genuinely enforced twice over (`recommendations.py:203` `_is_dual_consented`, plus a second ring-2 gate in `personalization.py`). **Corrected 2026-08-09**: the erasure CASCADE gap is closed, `test_delete_my_family_cascades_family_connection` now satisfies `models.py`'s `#VERIFY` pointer to `test_deletion_drill.py`. Still open: no integration or e2e test drives ring-2 dual consent itself (as opposed to the erasure path) over the real stack |
| M5: Hardened family tier | Phase 5 expanded scope: purge, offline revocation, audit view, re-screen, restore drill, nightly/staging/prod test ladder green with alerting | 2-3 wks | 🟡 M4b-4d dependency satisfied as of 2026-07-17. **Revised 2026-08-01 against code**: the audit view IS built (`frontend/src/admin/AuditPage.tsx`, routed at `/admin/audit`) and safety gap **H1 is closed** (`assignments.py:285-312` raises on `book_rank > profile_rank`, with a regression test); H2 is half closed, since the human cover-approval gate exists and only the automated image classifier is missing. All three test ladders have real `schedule:` triggers. Genuinely remaining: the performance pass, backups plus restore drill, the H2 classifier, and the H1 residual (the band check is fail-open on blobs lacking band metadata) |
| **M5.1 = R1 (full): "the web app functions properly"** | Every family-tier register row at delivered status; the five golden journeys green on the full test ladder | **~9-13 wks cumulative from start** | 🟡 Closer than scheduled: the register's K/G/A/S rows are now mostly ✅/🟡 with few ❌ remaining (capability-register.md v1.10: 71 rows, 50 ✅, 18 🟡, 3 ❌ at 2026-09-05); the live E2E sign-off (`r1-live-e2e-checklist.md`) has been executed twice and stands at 10 of 38 steps ticked as of 2026-08-08, with the remaining 28 owner-gated plus a redeploy still needed to clear #639's live production impact (see the M4.1 row above; the fix is merged and code-verified but not confirmed deployed past v0.68.0). **Added 2026-08-06 by owner ruling OG7** (`story-structure-improvement-plan.md` §8.1): the catalog is also reachable-empty, and `UW-G14` (promoting the 23 authored books) now carries the `R1` token as a named blocker of this row, on the argument that a library with zero reachable catalog books is not a family-tier row at delivered status, it is the core reading loop failing for any family that has not completed a custom request |
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
**Amended 2026-08-18**: the Ollama leg is retired. Modal replaces it as leg 3, but only
when `MODAL_BASE_URL` and `MODAL_MODEL` are set; otherwise the cascade runs on its two
OpenRouter legs and `build_provider` logs `generation.cascade_single_vendor` at WARNING.
See ADR-003's 2026-08-18 amendment.

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
   **Superseded 2026-08-18**: the Ollama leg is retired ahead of the homelab-to-Vultr
   move and Modal takes its place as leg 3, and the direct Anthropic adapter is no longer
   deferred (it shipped in WS-C PR1). See ADR-003's 2026-08-18 amendment.

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

**Status: all shipped 2026-07-17 in PR #270, plus bookmarks closed 2026-08-09; only the
device/storage view remains genuinely open. Note K5 ("Go back") and "bookmarks" are two
different register capabilities that a prior draft of this list conflated; K5 is delivered
(replay-based undo), bookmarks (a distinct save-slot feature) is a separate closure below.**

- [x] Lightweight node editor: read as playthrough and node list, edit a passage, re-run
      validation, re-review on edit (G6, edit half). `PATCH /storybooks/{id}/versions/{v}/nodes/{node_id}`
      (`api/node_edit.py`) re-runs the gate and moderation on edit. A dedicated
      guardian-facing review/edit surface (`GuardianReviewDetailPage.tsx`,
      `/guardian/review/:storybookId`) now exists alongside the admin one, scoped to the
      requesting family's own story. Branch re-roll and the reject/veto half of G6 (an open
      ADR-005 product decision, not an engineering gap) remain out of scope.
- [x] Ending tracker "3 of 7 endings found" (K6, UI over the shipped completion rows) and
      read-aloud/TTS for the youngest bands (K7). `EndingsProgress.tsx` and `useReadAloud.ts`
      wired into `Reader.tsx`, `tts_enabled` toggle in `ProfileFormDialog.tsx`.
- [x] Bookmarks (a distinct save-slot feature, not K5's "Go back" undo). Closed 2026-08-09:
      the backend `ReadingState.save_slots` field (`db/models.py`, `api/schemas.py`) already
      persisted, byte-capped (64KB), and multi-device-synced an opaque save-slot bag with
      nothing ever writing to it; `player/engine.ts`'s `saveBookmark`/`loadBookmark`/
      `deleteBookmark`/`listBookmarks` (pure, engine-test-covered) define the client-side
      bookmark shape, `player/machine.ts` adds `SAVE_BOOKMARK`/`LOAD_BOOKMARK`/
      `DELETE_BOOKMARK` events, and `BookmarksButton.tsx` (rendered via a new `ReaderChrome`
      slot) is the UI: one-tap "Save this spot" (auto-labeled from the current position, no
      typing required), a saved-spots list with Go here/Remove, capped at 10 saves per
      story. `ReaderPage.tsx`'s save-dedup signature was updated to include `save_slots`
      (previously excluded, per that file's own long-standing `#EDGE` comment anticipating
      exactly this change).
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
- [x] Guardian device list/revoke view: every currently-active device grant for the
      family, with a revoke action per device (`GuardianShell` "Devices" nav item ->
      `frontend/src/guardian/DevicesPage.tsx`, calling the existing family-scoped
      `GET`/`DELETE /api/v1/device-grants` endpoints in `api/device_grants.py`) (G15, ADR-014's
      own lost-device mitigation).
- [x] Guardian storage/download view: which books are downloaded on which device (G15
      remainder). Closed 2026-08-09: new `device_download` table (Tier 1 family_scoped
      RLS, migration `20260809110000_add_device_download.sql`) plus
      `api/offline_downloads.py` (`PUT`/`DELETE`/`GET /v1/device-downloads`);
      `frontend/src/offline/deviceId.ts` mints a persistent client-side device id
      (deliberately separate from `device_grant.jti`); `ReaderPage.tsx` reports every
      read via a `reportDownload` prop wired from `ReaderRoute.tsx`; `DevicesPage.tsx`
      renders a downloads section below the device list, grouped by device. Scope limit:
      the removal path (`DELETE`) works and is tested but is not wired into
      `offline/downloadBudget.ts`'s automatic space-pressure eviction or
      `offline/revocation.ts`'s server-directed removal, both deliberately network-free
      modules by existing architecture; a book evicted that way leaves a stale row until
      manually reconciled. This is why G15 stays 🟡 rather than flipping fully to ✅; see
      the register row for detail.
- [x] Test pins for the two previously shipped-but-unasserted surfaces: Go Back returns to
      the prior node with intact state (K5), `frontend/src/reader/Reader.test.tsx` plus
      dedicated e2e pin `frontend/e2e/reader-go-back.spec.ts`; cover
      render plus letter-tile fallback (K8), `frontend/src/library/BookCard.test.tsx`; the
      admin generate flow (A16), `frontend/e2e/admin-review-cover.spec.ts`.
      `test-traceability-matrix.md` records both K5 and K8 as ✅. Corrected
      2026-08-09: this item previously read as open; it is closed. **Re-corrected
      2026-08-09**: the prior correction dated both specs' addition to "2026-08-04",
      read off `git log`'s first-appearance date; `reader-go-back.spec.ts`'s own docblock
      records "Ratified 2026-07-16... this is its first E2E pin", which this repo's
      reconstructed/squashed git history cannot be trusted to date correctly this early
      in the project. The delivery status (closed) is unaffected; only the date was wrong.

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

**Status: all shipped 2026-07-17 in PR #270, the push transport closed 2026-07-28, and the
server-scheduled digest job closed 2026-08-09. Delivery is now poll-based (client re-polls
with `since`), push-based (authenticated SSE, `GET /api/v1/notifications/stream`, with the
poll kept as a fallback for a connection that cannot use SSE), AND digest-based (a daily
scheduled job, in-app only); "alert on safety" was already a real, code-enforced distinct
tier via `severity`. No open gap remains in this phase.**

- [x] Notification delivery infrastructure over the existing `pipeline_event` log: an
      in-app, poll-based surface (`notifications/service.py`) plus an authenticated SSE
      push surface (`api/notifications.py::stream_notifications`); the transport that
      K12/G10/A-alerts consume (S9). Closed 2026-08-09: a server-scheduled digest job
      (`notifications/digest.py::run_notification_digest`, run daily by
      `.github/workflows/notification-digest.yml` via `scripts/run_notification_digest.py`)
      writes one batched `NOTIFICATION_DIGEST_READY` event per family with pending
      info-severity notifications since their last digest, which then appears on that
      family's ordinary feed like any other item. In-app delivery only: no email/push
      provider is introduced, so a guardian who is not polling and whose SSE stream never
      connects still is not reached by anything outside the app; that would need a chosen
      ESP/push provider and credentials this change does not add.
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
- [x] Privacy-model erasure coverage: connections and recommendations in family deletion
      (per ADR-016). Closed 2026-08-09:
      `test_delete_my_family_cascades_family_connection`
      (`tests/integration/test_deletion_drill.py`) now creates two live `FamilyConnection`
      rows between two real families (one with the deleted family as viewer, one as
      sharer), deletes the family through the real `DELETE /api/v1/me/family` endpoint, and
      asserts both connection rows are gone while the other family is untouched. Satisfies
      the `#VERIFY` on `db/models.py`'s `FamilyConnection` CASCADE comment.

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

- [ ] Performance pass, offline-edge hardening. Accessibility split out to its own line below
      (2026-08-11): the "WCAG AA basics" framing here undersold what already exists, and
      obscured what remains.
- [ ] Accessibility, WCAG 2.1 AA (ADR-029, 2026-08-11 names the target and records what already
      verifies it): axe-core WCAG scans and a keyboard focus-trap contract already gate every PR
      (`frontend/e2e/a11y.spec.ts`, `keyboard-nav.spec.ts`); `eslint-plugin-jsx-a11y` now catches
      issues at lint time; a weekly, non-blocking Tier 2 scan (WCAG 2.2 plus axe best-practice
      rules) now runs against `main`. Stays open on: `UW-F27` (four structural gaps Tier 2's
      first run found), a manual screen-reader audit, and a published accessibility statement
      (see ADR-029's Follow-on work).
- [ ] Sentry wired on client and server; backups and a tested restore. (**Sentry fully wired
      2026-08-23**: `frontend/src/observability.ts` and `core/observability.py`, both DSN-gated and
      unit-tested; daily encrypted backups run in `supabase-backup.yml` (`UW-D27`). The restore drill
      has still never been recorded, `docs/operations/restore-drill-log.md` is an unfilled scaffold,
      so this line stays open on that one item; verified 2026-09-05)
- [x] Replace in-memory `RateLimitMiddleware` with Redis-backed rate limiting
      (in-house sliding-window Lua script over the existing `redis` client, not
      `fastapi-limiter`/`slowapi`) to support multi-process and load-balanced
      deployments, with a fail-open in-memory fallback on Redis outages
      (documented in SECURITY.md Known Infrastructure Limitations).
- [x] Operator runbook and a short authoring guide for non-technical use.
- [x] ADR-007 retention purge: the pg_cron job nulling `generation_job.report` 30 days
      post-completion (S10). The "or on publish" leg was withdrawn by ADR-007's 2026-08-11
      amendment, and a human-decided job is exempt from the sweep entirely per the 2026-08-10
      amendment; see `docs/compliance/data-retention-policy.md` Section 2 for the live rule.
- [x] Offline-copy revocation: archived/pulled books are removed from device caches at
      next connection, completing the kill switch and the incident pull-everywhere path
      (G8, A5). Guardian notification on an incident archive shipped on unmerged branch
      `feat/incident-revocation-notification` (commit 3916e99): `EventType.STORYBOOK_ARCHIVED`
      plus a G10/S9 alert-severity composer. A5 stays partial: recipients resolve from the
      storybook's OWNING family, so archiving a `visibility='catalog'` book (owned by the
      `CATALOG_FAMILY_ID` sentinel, assignable across families) notifies nobody. Following
      assignments rather than ownership is the remaining A5 gap.
- [x] Admin audit view over the pipeline event log: who did what to child-linked data,
      filterable (A13 view half). Closed: `frontend/src/admin/AuditPage.tsx` routed at
      `/admin/audit` against `api/audit.py`, tested (verified 2026-09-05; the manifest recorded
      the closure on 2026-08-01 and this box was never ticked).
- [x] Policy re-screen tooling: re-run moderation/policy over published family-tier books
      after a threshold or band-policy change (A4 first cut, delivered 2026-07-17; full
      public-catalog re-screen lands with Phase 9).
- [x] Real-backend S2 conflict-race spec (`frontend/e2e-real/offline-conflict-real.spec.ts`):
      fabricates a two-device `state_revision` race against a live 409, both resolution
      paths covered. Confirmed present by the 2026-07-20 audit.
- [x] Remaining test hardening per the test matrix: nightly `e2e-real` CI job (Postgres
      service + seed) and staging golden-journey coverage for GJ2/GJ3/GJ5 (matrix actions
      4, 6). Built: `e2e-real-nightly.yml`, `e2e-staging.yml`, `e2e-prod.yml` all run on
      `schedule:` with alerting; whether a given night is green is CI history (`UW-F48`), not a
      property of the tree. Verified 2026-09-05.
- [ ] The live-model adversarial safety run carried as Phase 3 debt (safety evaluation
      doc's model-dependent classes). **Executed, and red**: `safety-eval.yml` ran on 2026-08-24
      (twice) and weekly since; class A misses on `A9-actionable-harm-16plus` are reproducible
      (`UW-C361`, owner rubric ruling) and the 2026-08-30 miss on `A3` traced to an unpinned review
      model (`UW-C480`). The line stays open until a run meets the acceptance table, but "not yet
      run" was stale as of 2026-08-24; corrected 2026-09-05.
- [ ] Moderation review-model redesign and post-Perspective Stage-0 successor
      (owner decisions pending): see
      [moderation-review-current-state-2026-07-28.md](./safety/moderation-review-current-state-2026-07-28.md)
      and [moderation-review-redesign-2026-07-28.md](./safety/moderation-review-redesign-2026-07-28.md).
      Hard external deadline: Google Perspective API sunsets 2026-12-31.
- [x] **Newly surfaced by the 2026-07-20 audit, from `security-hardening-plan-2026-07.md`,
      neither previously tracked here nor closed**: H1, `assign_storybook` performs no
      band-ceiling comparison against the target profile, so a guardian can assign an
      off-band book across children (K13's assignment-time enforcement gap). Closed:
      `api/assignments.py:285-312` rejects `book_rank > profile_rank` with a `#CRITICAL` marker
      naming H1 and the regression test `test_assign_storybook_rejects_band_above_profile_band`;
      the residual is the documented fail-open on blobs or profiles lacking a parseable band
      (`plan-manifest.toml` Phase 5 gaps). Box ticked 2026-09-05; the manifest had it closed since
      2026-08-01.
- [x] **Newly surfaced by the 2026-07-20 audit**: H2, `generate_cover` flips
      `cover_status` straight `generating -> ready` with no moderation/approval gate, so
      an AI cover image can reach a child's shelf without the human review A16 promises
      (the story-text safety guarantee, A6, is unaffected). Closed 2026-07-28: the
      backend gate (`generate_cover` stops at `pending_review`,
      `covers.service.approve_cover` is the sole admin-only path to `ready`) merged in
      PR #469 (`30a988b5`), and the admin review UI (`ReviewDetailPage.tsx` renders the
      pending cover image plus an "Approve cover" action) merged in PR #471
      (`584a8a57`). `UW-M07` had held A16 open past H2: the R2 bucket served cover
      images at a deterministic object key over a public custom domain, so an
      unapproved cover's bytes stayed fetchable without passing this gate. The project
      owner disconnected that domain in Cloudflare on 2026-07-30 (outside this
      repository), re-verified by `dig cyo-bucket.williamshome.family` failing to
      resolve against a working general-egress check, so the gate now governs actual
      reachability and both H2 and A16 are closed. See `capability-register.md`'s A16
      row for the live status.

**Newly surfaced by the 2026-07-28 unscheduled-work sweep.** The security plan's Medium and Low
tiers, and the authoring log's blocking lessons, had no phase home. Full detail by ID in the
[unscheduled work register](./unscheduled-work-register.md); the safety-bearing items are carried
here because a gate bypass should be visible on the checklist, not only in a register.

- [x] **Three gate bypasses** (`UW-E01`, `UW-E02`, `UW-E03`): closed, corrected 2026-08-09.
      Reading/completion routes now call `_require_assignment` (`api/reading.py`, used by
      `get_reading_state`, `put_reading_state`, `record_completion`, each with a named
      regression test). Guardian blob-fetch's assignment gate was broadened from
      `Role.CHILD`/`Role.DEVICE` only to every non-admin caller (`api/library.py`, documented
      in-code as fixing a prior "M2" bug, with `test_guardian_cannot_fetch_unassigned_version`
      renamed from `test_guardian_can_fetch_unassigned_version`). Repair output re-enters the
      gate (`moderation/pipeline.py:730` calls `run_gate(revised)` after `attempt_repair`).
      These were real historical bugs, already fixed with tests before this sweep was written;
      the sweep listed them as open in error.
- [ ] **`AL-036` undercuts ADR-005** (`UW-C02`): the review surface has no pagination,
      virtualization, or per-node review state, so at 746 nodes it cannot deliver the human
      approval the ADR requires. The approval currently attests less than it claims.
- [ ] `AL-039` (`UW-C04`): repair and the Stage-1 fidelity gate both fail open and are
      structurally impossible at scale; fidelity lacks an `<untrusted_passage>` fence.
- [ ] `AL-034` (`UW-C03`): one import is ~2,986 provider round trips inside a single Postgres
      transaction holding `FOR UPDATE`, running 40 to 100 minutes.
- [ ] `AL-040` (`UW-C05`): `/admin/rescreen` sweeps synchronously in one request.
- [ ] Remaining security-plan tiers (`UW-E04` to `UW-E08`): review-model allowlist, a real PII
      detector, family cost cap on the authoring-plan path, production Postgres host-port and
      password-default exposure, inert `allowed_content_flags`, unenforced `reading_level_cap`,
      health-endpoint version disclosure.
- [ ] `UW-E16`: the `_extract_subject()` dev/test auth stub is still live in `api/deps.py`. Corrected
      2026-09-05: it is reachable only when `settings.environment == "local"`, and a non-local
      process fails at startup without OIDC config (`deps.py:97-100`), so "guarded only by unset
      OIDC environment variables" overstated the exposure. Retiring it entirely remains the item.
- [ ] **ADR-022 tiered RLS scoping** (`UW-A01`, `UW-A02`) and the rest of the ADR-021 worker and
      observability work (`UW-A04` to `UW-A07`). **Corrected 2026-09-05**: the M4.1 cutover is done
      (verified live 2026-08-04, `UW-A03`), the Tier-1 scoping migration
      (`20260724120000_scoped_rls_tier1_family_scoping.sql`), the per-request `app.family_id`
      context in `api/deps.py`, and `tests/integration/test_rls_tier1_enforcement.py` (run as the
      real `cyo_api` role) are all merged. Open: a dated entry in
      `docs/operations/rls-verification-log.md`, the ADR-022 status flip, the `UW-A02`
      denormalization question, and `UW-A04` to `UW-A07`.
- [ ] Named test-ladder actions replacing the generic line above (`UW-F*`): behavioral safety suite,
      FK `ON DELETE` parity, generated-client drift test, mutmut kill-floor, pre-Phase-9 performance
      testing, E2E driving the RQ worker, schema parity over policies and triggers, CORS and
      rate-limit negative tests, and the seven traceability-matrix actions.
- [x] `UW-K01` **release blocker**: two `docs/known-vulnerabilities.md` entries are 68 days old with
      reassessment 8 days overdue, past the 60-day OpenSSF release gate. Closed by PR #464
      (merged 2026-07-29; register row `done`); this box was never ticked. Verified 2026-09-05.
- [ ] `UW-K18`: 98 RAD markers carry no paired `#VERIFY`, including the `generation/worker.py`
      concurrency pair, the `db/models.py` cascade CRITICAL, the `classifiers.py` API-key placement
      CRITICAL, and four deploy-ordering CRITICALs in `supabase/migrations/`.

### Success Criteria

- ✅ Deployed behind Pangolin with Supabase guardian login (ADR-009); a restore from backup
  succeeds in a drill.
- ✅ Performance targets met on a real device on home wifi.

### Dependencies

- Requires: Phases 1-4.

---

## Content workstream: diversity and catalog growth (NEW 2026-07-28)

### Objective

Give the story-flexibility and content-diversity workstream its first phase home. Both master
documents previously **stated outright** that this workstream had no line item anywhere, despite
substantial merged code (PRs #300, #303, #314, #321, #415) and three governing ADRs (019, 020, 023).
This section is that line item. It runs alongside the phases rather than inside them, because its
cadence is catalog-time and offline, not release-gated.

### Governing documents

Live specs only: [story-diversity-plan-v2.md](./story-diversity-plan-v2.md) (the spec),
[story-diversity-implementation-plan.md](./story-diversity-implementation-plan.md) (the sequencer),
and [story-diversity-review-errata.md](./story-diversity-review-errata.md) (corrections). The
remediation plan, the execution plan, and the original analysis are **superseded**; their `D*` and
`M*` IDs are dead nomenclature. Do not open work from them.

### Deliverables

Full detail by ID in the [unscheduled work register](./unscheduled-work-register.md), cluster
`UW-G*`. The load-bearing items:

- [ ] **`A20` / `UW-G01`, the largest single item**: 14 of 16 skeletons and 4,305 `<<FILL>>` nodes
      are still unslotted, and closing it needs a family-based plan generator first. This is the
      ADR-019 catalog migration (`UW-A29`) and the parameterize-at-promotion runbook, as one item.
- [ ] `OQ-4` (`UW-G02`): 11 stateful Tier-2 skeletons unmigrated, plus the series-level binding design.
- [ ] **`AL-014`** (`UW-C01`): **partially closed, corrected 2026-08-09**: the CI gate itself no
      longer flatly blocks a lineage-less hand-authored skeleton (PR #532); the remaining gap is
      the WS-5 anti-clone floor not running against in-cell siblings for an original (`UW-C06`).
      See the Phase 5 checklist entry above for detail. No longer a flat blocker on hand-authored
      catalog growth, but not fully closed either.
- [ ] Per-band ATG calibration (`UW-G04`): `_BAND_THRESHOLDS` is still `{}`, so the anti-template
      guard remains advisory rather than enforcing.
- [ ] `AL-046` (`UW-C07`): the fill orchestrator is one-shot against a 32k output cap and the matcher
      has no feasibility predicate, so **13 books are unfillable today**.
- [ ] `A9` item 2 (`UW-G03`): restructure `the-sunken-temple` (5 variables, 20 conditions, 75
      effects, plus a 35-ending remix to 0.0710).
- [ ] Wave 5 (`UW-G13`): 36 new skeletons, 2 per production cell; the dagger-cell 460-node ceiling
      experiment; the Tier-2 stateful pilot.
- [ ] Promote the 23 filled stories committed to `main` to `visibility='catalog'` (`UW-G14`); 3
      legacy-shaped fills need normalization at import, paired with `AL-050`'s schema-v2 migration.
      Mechanism corrected 2026-08-03: issue #347 records an import run to `in_review` on 2026-07-21,
      so the open step is the separate admin promotion via
      `publishing/catalog_publish.py::promote_catalog_story`, not the import. Live database state is
      unverified; checking it is step 1 of the SQ-01 runbook in
      [story-structure-implementation-briefs.md](./story-structure-implementation-briefs.md).
      **Exception to this workstream's release-rung independence, ruled 2026-08-06 (gate OG7):**
      `UW-G14` now carries the `R1` phase token, not `content`. It is the one item in this list that
      gates a release rung, because it is a reachability gap rather than catalog growth. Everything
      else here stays release-rung-independent as the Objective above describes. Publication terms
      were set the same day by gate OG1: kid bands first, `the-sunken-temple` and
      `the-harrowstone-keep` held back pending the `A9` restructure, and issue #347's Q1/Q2/Q3
      closed before the #529 sweep is trusted.
- [ ] WS-0 Phase 3 calibration, WS-1 ATG wiring, WS-5 grammar composer, WS-6 fresh-generation feed,
      and WS-8 flywheel follow-ons (`UW-G05` to `UW-G10`, `UW-A32` to `UW-A36`).

### Success Criteria

- Every production-eligible skeleton carries a `.contract.json`, and the contract set is maintained
  with per-wave human quality review (`UW-A30`).
- The anti-template guard enforces per-band thresholds rather than advising.
- No production cell is unfillable.

### Dependencies

- Requires: nothing new. This work is offline and catalog-time; it does not block a release rung,
  which is precisely why it went unscheduled for so long.

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
| Google Perspective API sunset (2026-12-31), classifiers.py has no live date gate | H (calendar-driven) | M | Redesign proposes retiring the axis ahead of the deadline; see `safety/moderation-review-current-state-2026-07-28.md` and `safety/moderation-review-redesign-2026-07-28.md` |

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
- [Capability Register](./capability-register.md) - persona capability contract (`K`/`G`/`A`/`S`)
- [R1 Deferred-Debt Register](./r1-deferred-debt-register.md) - R1 deferrals (`C`/`GS`/`U`/`T`/`P`/`SL`)
- [Unscheduled Work Register](./unscheduled-work-register.md) - directed-but-unscheduled work (`UW-*`)
- [Authoring Lessons Log](./authoring-lessons-log.md) - authoring and validator lessons (`AL-*`)
