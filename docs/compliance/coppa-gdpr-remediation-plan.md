---
title: "COPPA / GDPR / GDPR-K Remediation Plan"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Actionable, phased implementation plan to make CYO Adventure compliant with COPPA, GDPR, and GDPR-K from the start (not deferred to a later public-launch phase), operationalizing the findings in docs/compliance/coppa-compliance-audit.md, docs/compliance/gdpr-compliance-review.md, and ADR-018's open decisions, plus the owner's verified corrections on LLM/storage/Sentry data flows."
tags:
  - compliance
  - security
  - privacy
  - planning
component: Development-Tools
source: "Direct code verification at commit 66fe320 (2026-07-19) of generation/pii.py, story_requests/screening.py, moderation/pipeline.py, covers/prompt.py, covers/provider.py, covers/storage.py, core/observability.py, frontend/src/observability.ts, plus owner input on current user base and data-flow intent."
---

> **Status**: Draft | **Version**: 1.0 | **Date**: 2026-07-19
> **Goal**: build COPPA, GDPR, and GDPR-K compliance in from the start, rather than the
> "US-only launch, defer GDPR-K as an expansion gate" posture ADR-018's D3 currently
> recommends. This plan supersedes that recommendation with the owner's explicit direction.
> **Not legal advice.** Every artifact this plan produces (consent flow, notice, DPIA,
> retention policy, DPA/SCC execution) needs qualified privacy counsel review before launch;
> this plan sequences the engineering and documentation work counsel will need to review.

---

## 0. How to read this document

This is an execution plan, not a new audit. It assumes the findings already established in
[`docs/compliance/coppa-compliance-audit.md`](./coppa-compliance-audit.md) and
[`docs/compliance/gdpr-compliance-review.md`](./gdpr-compliance-review.md) and does not
re-derive them. Section 1 first reconciles those findings against the owner's stated
understanding of the LLM/storage/Sentry data flows (verified directly against the current
commit), because that reconciliation changes what Phase 1 needs to cover. Section 2 lists the
foundational decisions that gate everything else. Section 3 is the phased build plan. Section 4
maps every phase back to the existing `PROJECT-PLAN.md` Phase 7 items and ADR-018's D1-D4 so
nothing is planned twice. Section 5 consolidates every open question in one place.

---

## 1. Reconciling your data-flow understanding against the current code

You're right about the design intent everywhere below; the code mostly delivers on it, with
specific, fixable gaps. Verified directly at commit `66fe320`:

### "OpenRouter, Anthropic, and OpenAI never receive user data, they are stories only."

**Mostly true for the primary generation path, with one real gap.** Every call to OpenRouter,
Anthropic, and Ollama for story text generation is wrapped by `PiiGuardedProvider`
(`generation/guarded.py`), which calls `assert_prompt_pii_safe` (`generation/pii.py`) on the
fully assembled prompt before it goes out. That guard checks the prompt against the family's
*registered* real child display names (exact match, word-boundary anchored, evasion-resistant
against zero-width/compatibility-form tricks) and would catch it even if a guardian typed the
child's real registered name into the story's protagonist-name field, since the guard scans
the whole assembled prompt text, not just isolated fields.

**The gap**: the guard only knows about names already on file as a `child_profile` row (there is
no birthdate to match against: `ChildProfile` has no birthdate column, by design; see 1e below).
It has no way to catch a sibling's name, a friend's name, a home address, a school name,
or a medical/family-circumstance detail a child or guardian types into the free-text story
idea (`request_text`) or premise (`ConceptBrief.premise`). That free text becomes part of the
generation prompt after it passes the exact-name check, so *that specific class* of
identifying content does reach OpenRouter/Anthropic today if a family types it in. This is
Phase 1's first item below.

**A second, separate gap in the same family**: OpenAI Moderation and Google Perspective (the
Stage-0 safety classifiers) are called in two places. At initial request screening
(`story_requests/screening.py`), the PII guard runs first and classifiers are skipped entirely
if it blocks, which is the right order. But during post-generation node review
(`moderation/pipeline.py`, `_run_all_stages` calling `run_classifiers` directly), the raw
generated prose is sent to OpenAI Moderation and Google Perspective with **no PII guard
applied at all**, unlike the sibling LLM-review stage three lines away in the same function,
which *is* wrapped in `PiiGuardedProvider`. This is an inconsistency worth closing regardless
of the free-text gap above.

**On "we'll use parameterized inputs for the prompt": confirmed, and this materially narrows
Phase 1's scope.** `ConceptBrief` (`generation/concept.py`) is already a fully typed,
`extra="forbid"` Pydantic model with about fifteen named fields, each length-capped and
control-character-stripped at intake, and `build_structure_prompt`
(`generation/prompts.py:274-306`) inserts the whole brief into the prompt template as one
delimited `{concept_brief}` JSON block, never by string-concatenating guardian text into
instruction text. That's real, working parameterization, and it buys two things already: a
guardian/child cannot inject content that redefines the prompt's structure (the same discipline
`covers/prompt.py` uses, quote-delimited and framed as descriptive data), and every value has a
known field name and a hard length cap.

What it does not do on its own is screen the *content* inside a free-text field for another
person's identifying information. Of the roughly fifteen `ConceptBrief` fields, only two carry
genuinely open-ended prose: **`premise`** (2000 chars; confirmed as a direct, unmodified copy of
the child's raw `story_request.request_text`, `story_requests/brief.py:187`, no rewriting or
summarization step in between) and **`special_constraints`** (a list of up to 20 free-text
items, 200 chars each). Everything else (`tone`, `themes_allowed`, `protagonist.role`, etc.) is
short and effectively controlled-vocabulary in practice, even though it's typed as `str`.
`protagonist.name` is a special case: it's free text too, but the existing guard already screens
the *entire* assembled prompt (not just isolated fields) against registered real-child names, so
if a guardian sets the protagonist's name to a registered child's exact name, generation already
blocks on it today; it does not need new work.

**This means Phase 1a below should target `premise` and `special_constraints` specifically**,
rather than trying to build a general-purpose PII detector over arbitrary text. Two ways to
place that screening were on the table: at `ConceptBrief` construction time
(`story_requests/brief.py`/`concept.py`), before `story_request.request_text` and
`concept.brief` are ever persisted; or at the existing `assert_prompt_pii_safe` chokepoint every
provider call already passes through. As shipped (see Phase 1a's status below), it landed at
the chokepoint, not at construction time: that gives every call site the new coverage for free,
including the cover-art and classifier paths added in 1b/1c, but it screens egress, not
storage, so a PII hit is still written to `story_request.request_text`/`concept.brief` before
being blocked from reaching a provider. Pre-persistence screening (so a hit is rejected, or sent
back to the guardian for edit, before the text is stored at all, which would also mean nothing
to purge later) remains an open follow-up, not something this phase delivered; Phase 4's
retention/purge work (4b-4c) still needs to cover this data as retained, not assume it was
screened out at intake.

### "Google [Gemini] and R2 contain stories and images, this is app info not user info."

**Two separate systems, and this is where the real gap is.** Gemini ("nano banana", via
`covers/provider.py`) generates the cover image from a prompt built in `covers/prompt.py`:
story title, protagonist name, themes, and a 240-character excerpt of the opening scene.
Cloudflare R2 (`covers/storage.py`, confirmed as the actual current storage backend, not
Supabase Storage) then stores the resulting image at a public URL with a predictable key
(`{storybook_id}/{version}.webp`).

Both are largely "app info" as you describe, **except**: `covers/` never imports or calls the
PII guard at all, at any point. If a protagonist name or excerpt happens to contain a real
child's registered name (the same scenario the generation path catches), the cover-art call to
Google is not screened for it, because it is a completely separate code path from the guarded
generation pipeline. This is the single largest gap in the "stories/app-info only" design
intent as currently implemented, and it is an easy, contained fix (wrap `covers/service.py`'s
prompt assembly in the same guard `generation/guarded.py` already provides; **done, Phase 1b**).
The R2 bucket being public with a guessable key was a second, independent issue (anyone who
guesses or is handed a URL could view a specific child's cover art without authentication); it
didn't leak identifying data on its own since keys aren't derived from anything identifying, but
closing it (**done, Phase 1d**: covers are now served via short-lived presigned URLs, never a
permanent public one) removes the standing exposure regardless.

### "I'm not sure how Sentry is used."

**This one is good news, and better than the existing COPPA audit's stale note.** The COPPA
audit (reviewed at commit `c9dbfa9`, 2026-07-10) found no Sentry integration at all; Sentry was
added to the codebase after that audit and is confirmed live at the current commit, but it is
implemented with real care:

- Backend (`core/observability.py`): `sentry_sdk.init()` hardcodes `send_default_pii=False`
  (not exposed as a configurable setting, specifically so no future config change can silently
  turn PII collection on), and is a documented no-op unless a DSN is explicitly configured.
- Frontend (`frontend/src/observability.ts`): `sendDefaultPii: false`, Session Replay and
  performance tracing are never enabled (not even gated behind a sample rate; the integrations
  simply aren't added), and a `beforeSend` hook (`scrubEvent`) strips request/response bodies,
  cookies, headers, and any `event.user` field beyond a bare anonymous ID before an event ever
  leaves the browser.
- Both sides are unit-tested for this behavior (`test_init_sentry_disables_pii`,
  `observability.test.ts`).

In short: Sentry only ever receives exception/error metadata and an anonymous ID, never a
child's name, a guardian's email, or request/response content, by a hardcoded control that
also has test coverage. The remaining work here is paperwork, not engineering: confirm
Sentry's own data-processing terms and (if the "compliant from the start" goal extends to
having every processor transfer-ready even pre-EU-users) get an SCC or confirm their DPF
self-certification on file, exactly as with every other processor in Section 3, Phase 5.

### "Supabase is the one key point."

**Agreed, and this framing is correct.** Supabase is the only processor holding two things at
once: guardian identity (email/OAuth via Supabase Auth) and all child-linked application data
(Postgres, `us-east-1`). Every other processor sees narrow, purpose-built content (a prompt,
an image request, an error report); Supabase sees everything, indefinitely, in one place. This
is why Phase 4's Supabase-specific work (region, DPA, and shrinking what actually needs to live
there long-term) is weighted heavily below, and why Section 2's region decision is the single
highest-leverage foundational choice in this plan.

### "All current users are US."

This resolves the most important open question from the earlier GDPR review (that review's
"Pressure Point P-1": whether GDPR already applies to the current private tier). With a
confirmed all-US current user base and no EU marketing/targeting, GDPR's extraterritorial
trigger (Article 3(2), which turns on *offering to* or *monitoring* EU-resident data subjects)
is not presently met. That means nothing in this plan is a live compliance violation today.
It changes the plan's *urgency*, not its *shape*: you've asked to build COPPA, GDPR, and GDPR-K
compliance in from the start rather than wait for a live EU user to force it, so the phases
below are sequenced as if that user could show up at any time, without treating the current
US-only fact as license to defer.

---

## 2. Foundational decisions (resolve these first; everything else depends on them)

These aren't engineering tasks, they're the choices that determine what the engineering tasks
should actually build. Recommended defaults are given where there is a reasonably clear best
answer for a project at this stage; the rest are genuinely yours to make. Full context for each
is in Section 5.

**Status as of 2026-07-20: every item below is resolved.** Full records are in Section 5 and, for
the four ADR-018 items, in ADR-018 itself; each resolution is marked "pending counsel
confirmation" where that ADR's own Validation checklist requires counsel sign-off before the
decision is final, per the "we draft, counsel reviews" model adopted this round.

- **VPC method.** *Resolved: signature-capture layered on the existing Supabase/Google OAuth
  login* (canvas or typed-name signature-equivalent + checkbox, logged server-side), ruling out
  both card-verification and a third-party ID vendor. See Section 5 ("VPC method") and ADR-018
  D1 for the full record; the "does a typed/canvas signature count as signed" question is
  flagged for counsel.
- **Supabase project region.** *Resolved: stay US.* You've confirmed Supabase stays in the US,
  with a possible future move from `us-east-1` to a US-west region. See Section 5 ("Supabase
  region") for why this is compliance-neutral and needs no further analysis.
- **Does the product intend children to appear as themselves (named) in their own stories?**
  *Resolved: no, self-naming is disallowed by design.* See Section 5 ("Self-naming") for the
  requested impact analysis of both routes, kept for reference in case this is revisited later.
- **Who signs off on and owns the compliance artifacts** (privacy notice, DPIA, DPAs)?
  *Resolved: the account owner, with this assistant drafting and counsel reviewing rather than
  drafting from scratch.* See Section 5 ("Artifact owner").
- **When does privacy counsel get engaged?** *Resolved: now,* reviewing drafts rather than
  originating them, in parallel with the engineering work in Phases 1/3/4/6 (already complete).
  See Section 5 ("Counsel timing").
- **Retention windows per data category.** *Resolved: the proposed table in Section 5
  ("Retention windows") is accepted as the actual policy.*
- **DPO designation.** *Resolved: not required at current/near-term scale;* reassess before
  Track 2 public launch. See Section 5 ("DPO designation").
- **Zero-data-retention (ZDR) terms with OpenRouter and the other LLM/classifier vendors.**
  *Resolved: the account owner executes Phase 5 directly.* See Section 5 ("ZDR terms").
- **UK/EEA user status** (gates Phase 9 and ADR-018 D3). *Resolved: none currently, none
  planned; Phase 9 is shelved on this basis.*

---

## 3. Phased implementation plan

Phases 1, 3, and 6 are pure engineering and can start immediately, in parallel, without waiting
on any legal/business decision. Phase 4 is split: 4a (Supabase region) and 4d (documenting the
audit-log retention justification) can start now, since their gating decisions are already
resolved or need no decision at all; 4b and 4c (the retention policy and purge jobs) need the
retention-windows decision. Phase 2 needs the VPC method decision. Phase 5 needs the ZDR-terms
decision. Phase 7 needs the artifact-owner and counsel-timing decisions, and drafting time from
whoever is assigned.

### Phase 1: Close the PII-egress gaps (engineering, no dependencies, start now)

Directly addresses the gaps found in Section 1. **Status as of 2026-07-19: 1a, 1b, 1c, 1d, 1e
all shipped (commit on `claude/gdpr-compliance-review-qzyvc2`).**

- **1a. DONE.** Pattern-based content screening (email, phone, street address) added to
  `generation/pii.py::assert_prompt_pii_safe`, the same chokepoint every provider call already
  goes through, rather than at brief-construction time as originally scoped: this was a
  deliberate implementation choice once the parameterization review showed the guard already
  screens the fully-assembled prompt (which includes `premise`/`special_constraints`) before
  every provider call, so extending that one chokepoint gives every existing and new call site
  the new coverage automatically, including the cover-art and classifier paths added in 1b/1c
  below. The nickname/variant-matching enhancement for `protagonist.name` was **not** built this
  pass (deprioritized as lower-confidence, higher-maintenance than the pattern-based work) and
  remains a documented follow-up if it's wanted later.
- **1b. DONE.** `covers/service.py::generate_cover` now screens the cover-art prompt via the
  same guard before calling Gemini, closing the one path that previously had zero PII screening.
- **1c. DONE.** `moderation/pipeline.py::_run_all_stages` and `api/node_edit.py::edit_node` (a
  second, identical gap found while fixing 1c, same pattern: an admin/guardian's edited node
  text reached the classifier call unguarded) now screen node text before the Stage-0 classifier
  calls.
- **1d. DONE, via the presigned-URL route, with no R2 migration needed.** Every cover has always
  been written to the same deterministic key (`{storybook_id}/{version}.webp`, both on fresh
  upload and via `scripts/backfill_covers_r2.py`'s historical migration), so the object itself
  never needed to move. `covers/storage.py::generate_presigned_cover_url`/
  `generate_presigned_cover_urls` compute a fresh, short-lived (1-hour) signed GET URL from that
  key on every read; `api/covers.py`, `api/library.py`, and `api/recommendations.py` all switched
  from returning the stored `cover_image_url` column to calling these functions instead. The
  stored column is kept, unchanged, purely as an upload-time audit value and for the backfill
  script's own URL-classification logic; it is never served to a client again. Both functions
  degrade to `None`/`{}` (logged, not raised) if R2 is unconfigured or a presign call fails, so a
  storage hiccup shows a missing cover image rather than 500ing the whole library or
  recommendations listing. **Operator action still required, outside this codebase**: the R2
  bucket's public custom domain (or `r2.dev` public access) must be disabled in the Cloudflare
  dashboard; presigned URLs only add security value once the bucket itself is not also publicly
  readable by the old, permanent URL shape. Verified with unit tests (mocked boto3) and one
  integration test exercising the full HTTP round-trip with a mocked R2 client; the migration
  itself needed no live R2 credentials or Docker since no object ever moves.
- **1e. DONE.** The birthdate-matching code path is removed outright (not just left unused):
  `ChildProfile` has no birthdate column and the product only ever collects a coarse age band by
  design, so every call site could only ever pass an empty set. Kept as a documented, deliberate
  design note in the module docstring rather than dead code implying coverage that never existed.

### Phase 2: Consent and notice (2a DONE, 2e DONE (newly scoped); 2b-2d remain)

- **2a. DONE.** Replaced `onboarding.py`'s `_record_consent()` no-op stub with a real
  implementation: `User.consent_accepted_at`/`consent_policy_version`/`consent_signer_name`/
  `consent_ip` (paired, CHECK-enforced), written once by `POST /v1/onboarding` when the
  guardian submits `{accepted: true, policy_version, signer_name}`, never overwritten
  afterward. `api/profiles.py::_require_consent` gates `POST /api/v1/profiles` (400) on this
  record existing, satisfying "gate all child-profile creation ... behind this record
  existing." Frontend: `GuardianConsentPage.tsx`, a typed full-legal-name attestation +
  checkbox (the FTC's "sign and submit electronically" method, 312.5(b)(2)(i); see ADR-018
  D1), reached automatically via a new `AuthStatus = 'needs-consent'` that `ProtectedRoute`
  routes to before any other guardian page. Also fixed a real, independent gap found while
  wiring this in: the frontend never called `POST /v1/onboarding` at all before this change,
  so a brand-new guardian's first `GET /v1/me` would have 401'd on "unknown subject" -- this
  is now called first, every sign-in, ahead of `/me`.
- **2b. Add a re-consent flow** triggered on material privacy-notice changes. Not started;
  `CONSENT_POLICY_VERSION` (frontend/src/auth/onboardingApi.ts) is the version stamp a future
  re-consent flow would compare against, but nothing currently prompts re-consent on a bump.
- **2c. DRAFTED, not yet published.** [`privacy-notice.md`](privacy-notice.md), written
  against the union of COPPA 312.4's content list and GDPR Articles 13-14's broader content
  list, synthesized from the actual shipped design (Phase 2a's consent mechanism, Phase 4's
  accepted retention table, the RoPA's processor list) rather than written in the abstract.
  Every open legal question is a flagged `[COUNSEL: ...]` bracket in the document itself.
  Remaining: counsel review, then publish as a real guardian-facing route and link it from the
  landing page, guardian console, and `GuardianConsentPage.tsx`'s consent screen.
- **2d. Direct notice to the parent** at onboarding (email, once the `user` table gains an
  email/contact column per the existing plan item P6-03).
- **2e. DONE, newly scoped mid-session (2026-07-20).** A guardian self-signup approval gate,
  parallel to (and never sharing state with) the existing admin-invite `'pending'` track:
  `onboarding.py::_provision_guardian` now starts an uninvited guardian's own first-login row
  at `User.status='awaiting_approval'`, not `'active'`; `require_principal` already rejects
  every endpoint for a non-`'active'` status (401 "unknown subject"), including `GET /v1/me`,
  so this alone was the enforcement mechanism -- no new authorization code needed. An admin
  approves (`awaiting_approval` -> `active`) or denies (`awaiting_approval` -> `deactivated`)
  via the existing `PATCH /admin/users/{id}` status transition (extended to allow this pair,
  still rejecting any direct transition INTO `awaiting_approval`). Frontend:
  `GuardianAwaitingApprovalPage.tsx`, reached via a new `AuthStatus = 'awaiting-approval'`.
  An admin-created invite (`POST /admin/users`) is unaffected: that guardian is already vetted
  by the admin who invited them, so their first login binds straight to `'active'` as before.

### Phase 3: Data-subject rights (engineering, no dependencies, start now)

**Status as of 2026-07-19: 3a-3e all shipped (commit on `claude/gdpr-compliance-review-qzyvc2`),
with one verification caveat that applies to all five sub-items: this sandbox has no Docker, so
none of the changes below have run against a live Postgres. `tests/integration/test_schema_parity.py`
and the new `tests/integration/test_deletion_drill.py` are both written and exercise the exact
behavior described, but need a CI run (or a local run with Docker available) before this phase is
considered verified rather than just implemented.**

- **3a. DONE.** Added `ondelete=` (`CASCADE` or `SET NULL`) to every FK in `db/models.py` that
  sits on the family/child-profile ownership closure, mirrored in a new Supabase migration
  (`supabase/migrations/20260719190000_add_erasure_cascades.sql`). Three edges needed
  non-default handling, each documented with a `#CRITICAL` comment at its column:
  `pipeline_event.actor_id`'s FK is dropped entirely (the table's append-only trigger blocks
  the `UPDATE` a `SET NULL` cascade would issue, so it would otherwise block deleting any user
  who has ever authored an event); `storybook.series_id`/`story_request.series_id` and
  `kid_flag.resolved_by` are left off a bare `SET NULL` because each is paired with a sibling
  column by a CHECK constraint that a same-transaction cascade could violate before the owning
  row's own cascade removes it; the `kid_flag.resolved_by` case is the one that's actually
  reachable in practice (a resolving admin need not belong to the flagged family), so it's
  handled by an explicit application-level `UPDATE` in the family-deletion endpoint instead
  (see 3b). `moderation_threshold_audit.changed_by` and `provider_model_allowlist_audit.changed_by`
  were additionally relaxed from `NOT NULL` to nullable, since either would otherwise block a
  guardian/admin's own self-deletion if they had ever touched a global admin-config surface.
- **3b. DONE.** `DELETE /api/v1/profiles/{profile_id}` (guardian-only, own family, works even on
  an already-deactivated profile) deletes a single child profile; `DELETE /api/v1/me/family`
  (guardian-only) deletes the caller's entire family account, satisfying Article 17 for the
  guardian as a data subject in their own right per ADR-018's already-decided framing ("account
  deletion erases the family") rather than adding a separate narrower mechanism. The family
  endpoint runs the `kid_flag.resolved_by` reopen step from 3a before the cascade delete.
- **3c. DONE.** `GET /api/v1/me/export` (guardian-only) returns the family, every
  guardian/admin/child login row, every child profile with nested reading state, completions,
  ratings, and assignments, and every family story request, as one JSON document. Deliberately
  excludes `generation_job.report` (raw multi-stage LLM output): that field is admin-only
  everywhere else in this API, and the export must not become a side channel around that
  restriction. A blocked story request's raw text is redacted, mirroring the guardian-facing
  API's own redaction of that field.
- **3d. DONE.** `GET /api/v1/completions/{profile_id}` (mirrors `GET /ratings/{profile_id}`)
  lists a profile's completions; `completion` was the one child-linked table with no read path
  at all before this.
- **3e. DONE**, with the verification caveat above. `tests/integration/test_deletion_drill.py`
  covers: profile deletion cascading reading state/completions/ratings/assignments/the child's
  own login row while de-linking (not deleting) their story requests; family deletion cascading
  everything family- and child-owned; the `kid_flag` cross-family reopen case from 3a; guardian-only
  authorization on both delete endpoints and the export endpoint; and the export's blocked-request
  redaction.

### Phase 4: Retention and storage governance (4a: infra execution outstanding; 4c/4d DONE; 4b unblocked, not yet published)

- **4a. Execute the Supabase region decision** (already resolved, Section 2) while data volume is
  still small, since migrating a live project's region later is materially harder than choosing
  correctly now. No decision gate: startable immediately.
- **4b. Write and publish a retention policy** stating purpose and retention window per data
  category (reading state, completions, ratings, story requests including blocked/declined
  ones, generation reports, audit/event log). Unblocked (the retention table in Section 5 was
  accepted 2026-07-20); still needs to actually be published as its own artifact rather than
  living only inside this plan.
- **4c. DONE.** Two new pg_cron jobs, mirroring the existing `generation_job.report` purge
  (ADR-007): `purge_blocked_declined_story_request_text` overwrites `story_request.request_text`
  with a fixed placeholder 30 days after `COALESCE(reviewed_at, created_at)` for `blocked`/
  `declined` rows (the API view layer's redaction was already in place; this is the underlying
  data catching up to it); `purge_stale_deactivated_profile_activity` (plus two sibling jobs for
  `completion` and `rating`) delete `reading_state`/`completion`/`rating` rows for any
  `child_profile` deactivated more than 90 days ago, per the accepted retention table's
  "life of the active profile, plus 30-90 days after deactivation" window (the profile row
  itself is untouched; a guardian who wants it gone entirely already has
  `DELETE /api/v1/profiles/{id}`). Same idempotent, pg_cron-optional migration pattern as the
  existing purge job, so it is a no-op on any Postgres without the extension (local/test/CI).
- **4d. DONE.** Documented below: an explicit Article 17(3) balancing justification for why the
  `pipeline_event` audit log is exempted from erasure requests, resolving gdpr-compliance-review.md's
  G-12/P-4.

#### 4d artifact: Article 17(3) balancing test for `pipeline_event` retention

This is the documented balancing test P-4/G-12 found missing: a controller relying on an Article
17(3) exception is expected to be able to produce one on request, not merely assert the exception
applies. It covers every row in `pipeline_event` (the append-only audit log written by
`events/writer.py::record_event`; see `db/models.py::PipelineEvent`), including rows naming a
child profile, a family, or a guardian/admin account that has since been erased via Phase 3's
`DELETE /api/v1/profiles/{id}` or `DELETE /api/v1/me/family`.

**1. What is retained, and why an erasure request does not remove it.** When a profile or family
is deleted, every *operational* table cascades away with it (Phase 3a's `ondelete=` FKs): reading
state, completions, ratings, story requests, login rows, the lot. `pipeline_event` rows naming
that profile/family/user as `entity_id`, or naming a now-deleted user as `actor_id`, are the one
deliberate exception (Phase 3a's `#CRITICAL` comments on `PipelineEvent.actor_id` and the
`ondelete=`-free edges already flag this; this section is the justification those comments point
to). The row is neither cascaded away nor retroactively scrubbed; it survives the erasure request
that removed the data it describes.

**2. Legal basis for the exception (Article 17(3)).** Two of the six Article 17(3) grounds apply:

- **17(3)(b), compliance with a legal obligation.** COPPA 312.10 and GDPR Article 5(2)'s
  accountability principle both require a controller to be able to demonstrate what it did with
  a child's data and who authorized it (this is also the substance of COPPA finding H-01 and
  GDPR finding G-12 that this justification resolves). An audit trail that could itself be erased
  on request cannot serve that demonstrative function; the record would be exactly as reliable as
  self-reporting.
- **17(3)(e), establishment, exercise, or defense of legal claims.** If a guardian or regulator
  later disputes what data an admin accessed, when a story was approved, or who resolved a safety
  flag on a child's account, the pipeline_event log is the only record capable of answering that
  question authoritatively. Erasing it on the same request that triggers the dispute would remove
  the evidence needed to resolve the dispute, for either party.

**3. Proportionality: why retention here does not defeat Article 17's purpose.** Article 17(3)'s
exceptions are not a blanket retention license; they justify retaining only what is necessary for
the stated purpose, no more. Three properties keep this retention proportionate rather than a
backdoor around erasure:

- **The payload is already PII-scrubbed by contract, not by policy promise.** `events/writer.py`'s
  `_PAYLOAD_ALLOWLIST` and `_validate_payload_value` reject any payload key or value outside a
  fixed per-event-type allowlist of ids, enum values, scores, and counts before a row can even be
  written (spec decision D3; see the COPPA audit's Section 3.5). A retained row never contains a
  child's name, story prose, or other free text, only ids, event kind, and closed-vocabulary
  facts. This is what makes the retention-risk profile in the Section 5 retention table
  materially lower than any other retained category.
- **What survives erasure has no further bearing on a live account.** Since the referenced
  profile/family/user row itself is gone, a surviving `pipeline_event` row cannot be used to
  re-derive, re-contact, or re-profile the erased data subject; it is historical fact about a
  past action ("this admin viewed this family's profiles on this date"), not a live copy of the
  erased personal data.
- **Access is restricted, not published.** `GET /api/v1/admin/audit` (the only read surface over
  this table) is admin-only (`_require_admin`, enforced before any query runs); the erasure of an
  account does not create a new exposure, since the log was never guardian- or child-visible in
  the first place.

**4. Retention window.** No fixed TTL/purge exists today (Section 5's retention table already
records this); the justification above supports indefinite retention under 17(3)(b)/(e) for as
long as the accountability/legal-claims purpose remains live, which for an audit log is
effectively the life of the product. If a future purge policy is adopted for this table (e.g. to
bound storage growth), it should be sized to the applicable claims-limitation period, not to the
data subject's own retention preference; that would be a storage-governance decision (Phase 4b),
not a change to this exception's validity.

**5. Conclusion.** `pipeline_event` retention after an erasure request is justified under Article
17(3)(b) and (e), proportionate given the payload's PII-scrubbed-by-contract design and
admin-only access, and does not require guardian notice beyond what the privacy notice (Phase 2)
already discloses about audit logging. No code change follows from this section; it documents the
justification for a design decision (Phase 3a's FK-cascade exceptions) already shipped.

### Phase 5: Processor paperwork (checklist drafted 2026-07-20; execution not yet done)

- **5a. Confirm and execute a DPA (and SCCs, given every processor listed is US-hosted) with
  each processor**: Supabase, OpenRouter and downstream model providers, Anthropic-direct,
  OpenAI Moderation, Google Perspective, Google Gemini, Cloudflare R2, and Sentry. For Sentry
  specifically, given Section 1's finding that it already receives no PII by hardcoded design,
  this is close to a formality, but "compliant from the start" means closing it rather than
  assuming it's unnecessary because the data itself is already clean.
  **Checklist drafted**: [`processor-dpa-checklist.md`](processor-dpa-checklist.md), with
  every DPA link live-verified (not reused from training-data memory) on 2026-07-20; execution
  itself is still the account owner's to-do.
- **5b. Prioritize zero-data-retention (ZDR) terms with OpenRouter** specifically, since
  ADR-018 already flags this as the standing blocker; resolve it explicitly rather than letting
  it stay open indefinitely. The checklist's OpenRouter row is flagged as needing an actual
  conversation (confirm account-wide ZDR is enabled and covers every downstream
  model/provider), not just a click-through DPA.
- **5c. Record every outcome** in `docs/planning/privacy-model.md`'s processor list, so Phase 7's
  Records of Processing document (below) has a single source of truth to pull from. Not yet
  done for any row (the checklist is the to-do list, not the durable record).

### Phase 6: Security hardening (engineering, no dependencies, start now)

**Status as of 2026-07-20: 6a, 6b, 6c, and 6d shipped.**

- **6a. DONE.** `TrustedHostMiddleware` wiring was already correctly implemented and tested
  (verified, no change needed: `allowed_hosts` is env-configurable and conditionally wires the
  middleware). HTTPS redirect was the real gap: `enable_https_redirect` was never passed to
  `add_security_middleware`, so it was always off regardless of environment. Now enabled for
  every non-local environment, gated the same way the rate limiter already is. This was only
  safe to turn on because `forwarded_allow_ips` already makes uvicorn trust `X-Forwarded-Proto`
  from the TLS-terminating reverse proxy (a separate, already-fixed trust boundary); without
  that fix in place first, enabling this could have redirect-looped real HTTPS traffic instead
  of closing a gap.
- **6b. DONE.** [`docs/compliance/information-security-program.md`](information-security-program.md):
  designated security contact, a documented risk-assessment cadence (annual, pre-major-feature,
  pre-processor-onboarding, per-CI-finding, and post-incident triggers), and a vendor-oversight
  process with a per-processor table, satisfying both COPPA 312.8's 2025-amendment expectation
  and GDPR Article 32(1)(d)'s "regularly testing, assessing and evaluating" requirement in one
  artifact.
- **6c. DONE.** [`docs/compliance/breach-notification-runbook.md`](breach-notification-runbook.md),
  distinct from `SECURITY.md`'s external vulnerability-reporting policy: an internal
  incident-classification rubric (severity driven primarily by whether child-linked data is
  implicated), an escalation path, the two GDPR clocks (Article 33's 72-hour
  notification-to-authority duty and Article 34's separate "high risk to individuals" duty), and
  a flagged-open COPPA/state-law breach-notice gap rather than a silent omission.
- **6d. DONE.** `SECURITY.md` corrected: the auth section no longer describes an unresolved
  dev-only stub needing future Authentik JWT validation (real Supabase-issued JWT verification
  is already implemented and enforced for every non-local environment); the child-safety bullet
  no longer asserts "no persistent PII without explicit parental consent" (not implemented),
  replaced with an accurate description of what's built (data minimization, the PII egress
  guard) and what isn't yet (verifiable parental consent, a retention policy), pointing to the
  compliance docs rather than asserting compliance inline.

### Phase 7: Formal compliance documentation (artifact-owner and counsel-timing decided 2026-07-20; 7a/7c/7d DONE, 7b in progress)

- **7a. DONE.** [`docs/compliance/records-of-processing-activities.md`](records-of-processing-activities.md):
  eleven processing activities synthesized from the COPPA audit, the GDPR review, and
  `privacy-model.md`, plus a consolidated recipient/transfer-mechanism table and a data-subject-rights
  status table. Originally surfaced (without resolving) a newly-found gap, Articles 18/21
  having no implementation; that gap is now closed (see the Article 18/21 entry under Phase
  8's sequencing).
- **7b. DONE (drafted, not yet counsel-reviewed).** [`dpia.md`](dpia.md), drafted *after*
  Phase 2's consent-flow build finalized (per Pressure Point P-2: assess the real, shipped
  design), using the Article-25-by-design strengths already documented (data minimization, no
  ads/analytics SDKs, closed-vocabulary avatars, real tenancy auth) as the risk-mitigation
  inventory. Every risk section is rated with residual risk after existing mitigations; the
  two flagged as still genuinely open (the semantic-PII gap in free text, G-13; and counsel
  confirmation of the VPC method, ADR-018 D1) are the priority items before Track 2 launch.
- **7c. DONE (recorded, not a full DPO analysis).** Current/near-term scale (small,
  homelab-first, no near-term mass-growth plan) does not trigger Article 37's "large scale,
  regular and systematic monitoring" threshold. Recorded outcome: DPO not required now;
  concrete reassessment trigger set to "before Track 2 public launch" rather than left as an
  open-ended future maybe.
- **7d. DONE (decisions recorded in ADR-018 2026-07-20; pending counsel confirmation per that
  ADR's own Validation checklist, not yet flipped to Accepted).** D1 (VPC mechanism), D2
  (audience classification, confirmed child-directed per the ADR's existing recommendation),
  and D3 (launch geography, confirmed US-only given no UK/EEA users) all now carry a recorded
  owner decision rather than an open question. ADR-018's status stays Proposed until counsel
  reviews the drafted consent flow, Privacy Notice, and DPIA (Phase 2/7b) and signs off; this
  bullet's engineering-adjacent scope (recording the decisions themselves) is complete.

### Phase 8: Ongoing compliance operations (start once Phases 1-7 are substantially done)

- **8a. DONE.** `GET /api/v1/admin/profiles` (`admin_profiles.py::list_admin_profiles`) now
  writes one `profile_viewed` `pipeline_event` per call (not one per row returned), carrying the
  `family_id` filter used (or `None`/`"all"` for an unfiltered cross-family listing) and the
  count of profiles returned. This is the only cross-tenant read anywhere in the admin console
  (every other admin GET is same-family or non-child data), and the only READ this audit log
  covers at all: every other `EventType` member logs a mutation. Queryable via the existing
  `GET /api/v1/admin/audit?kind=profile_viewed`; no new read surface was needed.
- **8b. DONE, and was already done before this plan flagged it as open.** This bullet (and
  `gdpr-compliance-review.md` finding G-10) described the guardian-facing consent UI as
  not-yet-built based on a stale reading of ADR-016's status; on inspection (2026-07-20),
  `frontend/src/guardian/ConnectionsPage.tsx` is a live, routed guardian page at
  `/guardian/connections`, and `recommendations.py` gates every read on both
  `FamilyConnection.consented_by_viewer_user_id` and `consented_by_sharer_user_id` being set
  (paired with a `_at` timestamp each, CHECK-enforced), not on the admin-managed connection row
  alone. Nothing about either family's reading/rating data crosses to the other family until
  both guardians have explicitly clicked "Allow." See `gdpr-compliance-review.md` Section 4.3
  and G-10 for the corrected write-up.
- **8c. Set an annual (or pre-major-feature) compliance review cadence**, re-running this plan's
  Phase 1-6 checks against whatever has shipped since.

### Phase 9: GDPR-K / UK AADC-specific conformance

**Shelved 2026-07-20, not worked.** The launch-geography decision this phase needed is now
confirmed (ADR-018 D3): no UK or EEA users exist or are planned. Every item below stays
unscheduled until that changes; if UK/EEA users are ever expected, revisit this phase and
ADR-018 D3 together before that expansion ships. Left in place, not deleted, so the plan is
ready to resume rather than re-derived from scratch if the fact changes. Documentation-heavy;
most items would build on Phases 2/3/7 artifacts existing first.

"GDPR-K" is not a separate statute; it is GDPR's ordinary rules as applied to children (Article
8's consent age, Article 25's design-by-default duty, Article 35's risk-based DPIA), plus, for
UK users specifically, the ICO's Age Appropriate Design Code (AADC, "Children's Code", DPA 2018
s.123). Phases 1-8 above already build the GDPR/COPPA foundation GDPR-K sits on (egress
guarding, consent, rights, retention, processor terms, security, DPIA/RoPA/DPO, ongoing ops).
This phase is what is *additionally* required once a service is "likely to be accessed by
children" under UK law, a lower bar than "directed at children," so a US-hosted app with even
one UK child user is in scope regardless of App Store storefront geography (the same Article
3(2) extraterritorial logic as Pressure Point P-1 and finding G-08, applied to the AADC's UK
statutory basis specifically rather than GDPR generally).

- **9a. Formally record the Article 8 self-consent bypass.** The app's actual design (a guardian
  provisions every profile; no child ever supplies their own consent, regardless of `AgeBand`,
  including `16+`) sidesteps Article 8's per-member-state 13-16 consent-age lookup entirely. This
  is already true in code today; the gap is that it is not written down anywhere as a deliberate
  compliance position. Costs nothing to build; costs a paragraph in the DPIA (Phase 7b) and RoPA
  (Phase 7a) to state explicitly, so it reads as a documented design decision instead of an
  unexamined gap during a review.
- **9b. Confirm AADC applicability with the same rigor as Pressure Point P-1.** Determine whether
  any current or planned user is UK-resident; if so, the AADC binds today, not at a future public
  launch, the same conclusion the GDPR review already reached for GDPR generally. This is a fact
  question about the current user base, not an engineering task; see the new open question below.
- **9c. Run a 15-standard AADC conformance self-assessment** and record the result (pass, gap, or
  not-applicable) for each standard. Most of the underlying engineering already exists via Phases
  1-8 or the "already decided" list in ADR-018; this item is the paperwork that turns existing
  practice into a defensible, citable record:

  | AADC standard | Status against current build | Where the gap (if any) is tracked |
  |---|---|---|
  | 1. Best interests of the child | Not yet a named DPIA section | New: fold into Phase 7b's DPIA as an explicit subsection, not just generic Article 35 risk-to-rights analysis |
  | 2. Age-appropriate application | Likely satisfied: all child data collection sits behind a guardian gate (once Phase 2's 2a makes that gate a real precondition, not just the intended attachment point it is today) | Depends on Phase 2 landing |
  | 3. Transparency | Gap: G-07's privacy notice is a single adult-legal document; AADC wants content pitched to the child's age/development stage too | New: 9e below, extends Phase 2's notice build |
  | 4. Detrimental use of data | Likely satisfied (no ads, no dark-pattern engagement loops); not yet self-certified in writing | New: one-paragraph sign-off once Phase 2/7 notices exist to point to |
  | 5. Policies and community standards | Depends on the published notice/terms existing | Depends on Phase 2 |
  | 6. Default settings ("high privacy" unless justified) | Satisfied for cross-family recommendation sharing specifically: connections are opt-in (dual-consent, off by default) not opt-out (G-10/8b, DONE). A broader default-settings audit across the rest of the app is still worth doing on its own merits | New: audit item, no longer gated on Phase 8b |
  | 7. Data minimization | Satisfied; already the headline strength of both the COPPA audit and GDPR review (Article 25-by-design) | Reference existing findings, no new work |
  | 8. Data sharing | Satisfied: Article 6(1)(a) consent is now the recorded basis for cross-family disclosure (G-10/8b, DONE) | No further work |
  | 9. Geolocation | Satisfied: no geolocation collected anywhere in the data inventory (Section 3) | Confirm explicitly in the RoPA (Phase 7a), no code change |
  | 10. Parental controls | Guardian consoles exist by design; needs child-facing copy explaining what a guardian can see/do | New: small copy addition, pairs with 9e |
  | 11. Profiling | The moderation/recommendation pipeline is profiling-adjacent (already flagged in G-04's DPIA discussion); needs its own compelling-reason-and-safeguards note distinct from the general DPIA entry | New: DPIA subsection, pairs with 9a |
  | 12. Nudge techniques | Likely satisfied (no ads, no engagement dark patterns); not yet self-certified | New: one-paragraph UX sign-off |
  | 13. Connected toys and devices | Not applicable; no IoT/connected-device component | Document as N/A with reasoning, no work |
  | 14. Online tools for exercising rights | Gap: Phase 3's deletion/export endpoints are guardian-only, matching COPPA/GDPR's rights model; AADC additionally expects a prominent, *child-accessible* way to seek help (e.g., an in-reader "tell a grown-up" control), which is new product surface, not just a Phase 3 extension | New: scope as a small kid-shell feature once Phase 3 ships |
  | 15. Governance and accountability | Depends on Phase 7c's DPO/accountable-owner assessment | Depends on Phase 7c |

- **9d. Assess UK ICO registration/notification.** Separate from GDPR's Article 30 RoPA duty
  (Phase 7a), UK controllers processing personal data generally owe the ICO an annual
  data-protection fee under DPA 2018 ss.137-138. Gated on 9b's applicability confirmation.
- **9e. Add age-band-specific child-facing notice content.** Extends Phase 2's consent/notice
  build (finding G-07) with a second, simpler layer of copy actually shown to the child across
  `AgeBand` tiers (kid-shell help text, in-reader copy), distinct from the guardian-facing legal
  notice; AADC Standard 3 treats these as separate obligations, not one document serving both
  audiences.
- **9f. Extend the Phase 7b DPIA with an explicit "best interests of the child" section**
  (AADC Standard 1), a distinct, mandatory lens under UK law beyond GDPR's generic
  risk-to-rights-and-freedoms standard; folds in the age-appropriate-application (9c row 2) and
  profiling (9c row 11) findings as supporting evidence rather than duplicating the analysis.

---

## 4. Cross-reference: this plan vs. the existing Phase 7 plan and ADR-018

| This plan | `PROJECT-PLAN.md` Phase 7 | ADR-018 |
|---|---|---|
| Phase 2 (consent, notice) | P7-02, P7-03 | D1, D4 |
| Phase 3 (rights) | P7-04, P7-05 | already-decided item 4 |
| Phase 4 (retention, Supabase) | P7-09 | already-decided item 5 |
| Phase 5 (processor paperwork) | P7-06, P7-12 | already-decided item 6, "Blocker 1" |
| Phase 6 (security) | P7-13 | Article 32 / 312.8, not separately named in ADR-018 |
| Phase 7 (DPIA, RoPA, DPO) | P7-08 | D2, D3, D4 |
| Phase 1 (PII-guard hardening) | not separately tracked | data-minimization spine (already-decided item 5) |
| Phase 8 (ongoing ops) | not separately tracked | new |
| Phase 9 (GDPR-K / AADC conformance) | not separately tracked | D3 (launch geography), D4 |

This plan does not replace `PROJECT-PLAN.md` Phase 7 or ADR-018; it sequences them into
dependency order and adds Phase 1 (the specific egress gaps found in Section 1), Phase 8
(ongoing operations), and Phase 9 (GDPR-K/AADC-specific conformance), none of which the existing
plan tracks as discrete items.

---

## 5. Consolidated open questions

Organized by which phase they gate. A recommended default is given where one exists; items
marked **(no default)** genuinely need your input.

**Gates Phase 2 (consent):**

- **VPC method.** *Resolved 2026-07-20 (owner decision; see ADR-018 D1 for the full record).*
  A fifth option not listed below was chosen instead of the four originally drafted here: a
  signature-capture step (canvas or typed-name signature-equivalent + checkbox, logged with
  IP/timestamp/account-id) layered on the existing Supabase/Google OAuth login, explicitly
  ruling out both the card-verification and third-party-vendor options below to avoid PCI
  scope and a new processor respectively. The options originally drafted here are kept for
  reference, not because any of them was chosen:
- *Originally open, but now well-scoped: no paid tier exists, and the product's stated
  design is that a guardian registers before any child can use the app.* That said, per
  `PROJECT-PLAN.md` there is currently no onboarding/signup endpoint at all, and `POST /profiles`
  is ungated today (no consent precondition). So guardian registration is not yet an existing
  child-data gate; it's the intended attachment point for one, and Phase 2's 2a is exactly the
  work that must make it one: block profile creation and any child-data collection until a
  consent record exists at that step. What's still undecided is *which* verification method runs
  there. Registration alone (an email/password or OAuth signup), even once gated, proves someone
  completed a signup, not that they're an adult, so it doesn't by itself satisfy VPC under either
  COPPA 312.5 or GDPR Article 8(2). Options, since a payment-card transaction isn't available
  without a paid tier:
   - **A nominal, non-charging card-verification step** (e.g., a Stripe `SetupIntent`-style $0
     authorization, not an actual charge) at registration. This satisfies COPPA's enumerated
     "payment card" method without requiring you to sell anything or build billing; it only
     needs card-present verification, not a transaction amount. Cheapest to build of the strong
     options, and doesn't force a monetization decision you haven't made yet.
   - **A third-party VPC vendor** (e.g., Persona, Yoti, Privo, k-ID, SuperAwesome, ID.me) doing
     ID verification or knowledge-based authentication as a service. Higher cost and integration
     effort, but several of these are purpose-built for child-directed apps and explicitly cover
     COPPA, GDPR-K, and the UK AADC in one integration, which fits the "compliant from the start,
     all three regimes" goal directly rather than requiring you to separately confirm each
     method satisfies each regime.
   - **Email-plus** (send a confirming email to the parent, 312.5(b)(2)): the FTC's own weakest
     accepted method, and it's explicitly limited to cases where the collected information is
     used only for internal purposes and not disclosed to third parties. Given this app calls
     external LLM/moderation/image providers (even with the screening controls in Phase 1),
     relying on email-plus alone is the option most likely to need a harder look from counsel
     before you'd want to depend on it.
   - **A signed consent form** (upload or e-sign at registration): lowest engineering cost, no
     vendor dependency, but the highest guardian friction of the four.
   None of the four above was chosen; see the resolution note at the top of this item and
   ADR-018 D1 for what was picked instead and why. **(resolved 2026-07-20)**

**Gates Phase 4 (retention/storage):**

- **Supabase region.** *Resolved.* Staying on US infrastructure (with a possible future
  `us-east-1` to a US-west region move) is compliance-neutral either way: both are non-EEA for
  GDPR purposes, so the SCC/transfer-mechanism need in Phase 5 is identical regardless of which
  US region is active, and an east-to-west move raises no new compliance question on its own.
  One practical note for whenever that move happens: it's a natural point to also land any
  schema-level retention/deletion changes from Phase 3/4 in the same maintenance window, since
  you'll already be touching the data at rest.
- **Retention windows per data category.** *Resolved 2026-07-20: accepted as drafted.* Kept
  below as the actual policy, not a proposal, and now what Phase 4b publishes and Phase 4c's
  purge jobs build against:

  | Data category | Proposed window | Rationale |
  |---|---|---|
  | Active profile/reading data (reading state, completions, ratings) | Life of the active profile, plus 30-90 days after deactivation before purge | Grace period covers accidental deactivation/reactivation without permanent data loss |
  | Approved/published story requests and their stories | Life of the active account (this is delivered content, not incidental collection) | Matches the product's core value; not "collection" in the retention-risk sense once it's the child's book |
  | Blocked or declined story requests (raw `request_text`) | 30 days from decision, then purge raw text and keep only the redacted category/verdict | Short window covers guardian review/appeal; raw declined text has no ongoing purpose after that |
  | `generation_job.report` (raw LLM output) | 30 days, or immediately on publish, whichever first | Already the ADR-007 design; just needs the pg_cron job built (Phase 4c) |
  | Moderation reports | 1-2 years | Balances safety/audit value against indefinite retention |
  | `pipeline_event` audit log | No fixed purge; retain under a documented Article 17(3)/312.10 safety-and-integrity justification (Phase 4d) | Already PII-scrubbed by allowlist contract (Section 3.5 of the COPPA audit), so the retention-risk profile is much lower than raw free text |
  | Erasure request: response to the guardian | Acknowledge and respond within 1 month of the request (GDPR Article 12(3)); may be extended by up to 2 further months for complex/numerous requests, but only if the guardian is notified of the extension and the reason within the initial 1-month window | This is the deadline to communicate *what action was taken*, a distinct obligation from the deletion itself |
  | Erasure request: actual purge | Purge within 30 days of the request, well inside the Article 12(3) response window above | Article 17's "without undue delay" duty; the two deadlines (respond vs. purge) are tracked separately so a fast purge doesn't imply a fast *response* is optional, and vice versa |

  **(resolved 2026-07-20; accepted as-is)**

**Resolved, kept for reference:**

- **Self-naming.** **Will children ever appear as themselves (by their real name) as the
  protagonist of their own story?** *Resolved: no, disallowed by design.* Since you asked for the
  impact of either route for the record:

   **Route A: disallow self-naming (your plan).**
   - The exact-match guard already enforces this today for registered display names, at no
     extra engineering cost beyond Phase 1a's nickname/variant hardening.
   - Keeps the "no real child PII in prompts" invariant airtight across every downstream
     surface: generation, moderation classifiers, and cover art all inherit the same guarantee
     once Phase 1 closes their respective gaps, with no per-field carve-out to maintain.
   - Keeps the DPIA/Records-of-Processing story simple: "a child's real name never leaves the
     database" is a much easier claim to make and defend than "a child's real name leaves the
     database, but only in this one specific, carefully-scoped case."
   - Cost: a personalized-story competitor that does let the child be the named hero has a
     product feature this design doesn't offer. That's a product tradeoff, not a compliance one.

   **Route B: allow self-naming.**
   - Would require deliberately routing around the existing guard for exactly one field, which
     means redesigning the guard's invariant ("this is the sole chokepoint preventing real-child
     PII from reaching a provider") into "sole chokepoint, except this one intentional case",
     which is a meaningfully different and harder-to-verify design.
   - The real name would then be sent to every text/image provider in scope and *persisted* in
     the finished story content itself (`storybook_version.blob`), not just transient prompt
     content, which extends retention, export, and deletion obligations to cover story content
     as PII-bearing, not just metadata.
   - Would need its own explicit lawful basis and specific notice/consent language (GDPR
     purpose-limitation, Article 5(1)(b)), since it's a distinct, higher-risk processing purpose
     from the rest of the app's data-minimized design, and would likely raise the DPIA's risk
     rating.
   - Benefit: a materially more personalized reading experience, which is a real product
     differentiator some competitors in this space lead with.

   Route A is the more defensible default for a project building compliance in from the start,
   and matches your stated plan; Route B remains available later as a deliberate, separately
   scoped feature decision if the product calls for it.

**Gates Phase 5 (processor paperwork):**

- **ZDR terms.** **Zero-data-retention terms with OpenRouter and the other LLM/classifier
  vendors.** *Resolved 2026-07-20.* The account owner executes Phase 5 directly (not counsel,
  not a hired vendor manager); most processors' DPAs are vendor-supplied click-through
  agreements, OpenRouter's ZDR terms are the one item needing actual negotiation. **(owner
  assigned: account owner)**

**Gates Phase 9 (GDPR-K / AADC conformance):**

- **UK-user confirmation.** Same underlying fact question as Pressure Point P-1 (does an
  EU/UK-resident guardian or child use the app today, in the current private tier), asked here
  specifically because the AADC's "likely to be accessed by children" test is a lower bar than
  GDPR's general Article 3(2) targeting test. *Resolved 2026-07-20: no, US-only now and for the
  foreseeable future.* Phase 9 is shelved on this basis (see that phase's status note); if this
  answer changes, both Pressure Point P-1's GDPR conclusion and Phase 9's shelved status need
  revisiting together, not separately.

**Gates Phase 7 (formal documentation), and the retention-windows decision above:**

- **Artifact owner.** **Who owns and signs off on the compliance artifacts** (privacy notice,
  DPIA, DPA/SCC execution, retention policy)? *Resolved 2026-07-20, by the working model this
  whole decision round adopted:* the account owner and this assistant draft every artifact;
  counsel reviews and signs off rather than drafting from scratch. Named owner: account owner.
- **Counsel timing.** **When does privacy counsel get engaged?** *Resolved 2026-07-20,
  consistent with the working recommendation already here:* now, in parallel with the
  engineering work already complete (Phases 1/3/4/6). The DPIA and Privacy Notice are being
  drafted next (Phase 7b / Phase 2) specifically so counsel's first look is a review pass, not
  a blank page.
- **DPO designation.** *Resolved 2026-07-20; see Phase 7c above.* Current/near-term scale
  (small, homelab-first) does not trigger Article 37; recorded as not required now, with
  reassessment tied to "before Track 2 public launch."

---

## 6. Suggested sequencing

**Decisions made 2026-07-20** (superseding the "decision-gathering still open" line this
section used to carry):

- **VPC method**: signature-capture layered on the existing Supabase/Google OAuth login
  (canvas or typed-name signature-equivalent + checkbox, logged with IP/timestamp/account-id
  server-side). No new vendor, no PCI scope. The one flagged legal question (does a
  typed/canvas signature satisfy 312.5(b)(2)(i)'s "signed") is the top item for counsel's
  review of the drafted consent flow and Privacy Notice.
- **Retention windows**: the draft table in Section 5 is accepted as-is; Phase 4b can now
  publish it as the retention policy.
- **ZDR/processor-paperwork owner**: the account owner (not counsel, not a hired vendor
  manager) will execute Phase 5's DPAs directly; most are vendor-supplied click-through
  agreements, OpenRouter's ZDR terms are the one needing actual back-and-forth.
- **UK/EEA users**: none currently, none expected. Phase 9 (GDPR-K/AADC) is shelved, not
  worked, until that changes; Phase 7d's ADR-018 D3 closes on the US-only framing already in
  the ADR.
- **DPO (Article 37)**: current/near-term scale does not trigger a "large scale, regular and
  systematic monitoring" DPO requirement. Phase 7c is recorded as "not required now," with a
  concrete reassessment trigger of "before Track 2 public launch," not a full DPO analysis
  commissioned today.
- **Articles 18/21 (restriction, objection)**: build a minimal "restrict processing" flag
  (newly scoped, not previously in this plan) rather than leaving the gap the RoPA surfaced
  undocumented and unaddressed.

```text
Now, in parallel, no dependencies (Supabase region and self-naming already resolved):
  Phase 1 (PII-egress hardening, field-targeted per Section 1's parameterization note) - DONE
  Phase 3 (deletion cascades, export, access endpoints) - DONE, pending a Docker-available
    CI run to actually verify test_schema_parity.py and test_deletion_drill.py (see Phase 3's
    status note)
  Phase 4a (Supabase region execution); 4c DONE; 4d DONE (audit-log retention justification)
  Phase 6 (security hardening) - DONE (6a, 6b, 6c, 6d)
  Phase 8a DONE; 8b DONE (was already built; the finding describing it as missing was stale,
    corrected 2026-07-20 -- see G-10)
  Phase 2a DONE (consent-capture flow, backend + frontend); 2e DONE (newly scoped self-signup
    admin-approval gate)
  Articles 18/21 minimal "restrict processing" flag - DONE (newly scoped)

Unblocked now that the VPC method is decided and 2a is built:
  Phase 2b-2d (re-consent-on-policy-change flow; draft the Privacy Notice for counsel review
  and link it from 2a's consent screen; direct email notice at onboarding)

Unblocked now that the retention table is accepted:
  Phase 4b (publish the retention policy from the accepted table; 4c's purge jobs are already
  built against it)

Checklist drafted, execution remains:
  Phase 5 (processor DPAs/SCCs -- processor-dpa-checklist.md drafted with live-verified links;
  the account owner still has to actually execute each one)

Drafted for counsel review, per the "we draft, counsel reviews" model:
  Phase 7b DONE (dpia.md drafted, informed by Phase 2's shipped consent-flow design); 7c DONE
  (recorded as not-required, reassess before Track 2 launch); 7d DONE (ADR-018 D3 closes on
  US-only; 7a already DONE)
  Phase 2c DONE (privacy-notice.md drafted, informed by the shipped consent/retention/processor
  design); 2b/2d remain unbuilt

Remaining small item:
  Phase 8c (schedule the annual review cadence -- e.g. a yearly reminder/Routine)

Shelved, not worked, until UK/EEA user status changes:
  Phase 9 (GDPR-K / AADC conformance: Article 8 bypass write-up, 15-standard self-assessment,
  ICO registration check, child-facing notice layer, best-interests DPIA addendum)
```

---

## 7. References

- `docs/compliance/coppa-compliance-audit.md`
- `docs/compliance/gdpr-compliance-review.md`
- `docs/planning/adr/adr-018-childrens-privacy-compliance.md`
- `docs/planning/adr/adr-007-*` (raw-output retention, referenced for the `generation_job.report`
  purge design), `adr-009-supabase-platform.md`, `adr-016-recommendation-sharing-social-boundary.md`,
  `adr-017-ai-cover-art.md`
- `docs/planning/privacy-model.md`, `docs/planning/PROJECT-PLAN.md` (Phase 7)
- Direct code verification for this plan: `src/cyo_adventure/generation/pii.py`,
  `src/cyo_adventure/generation/guarded.py`, `src/cyo_adventure/story_requests/screening.py`,
  `src/cyo_adventure/moderation/pipeline.py`, `src/cyo_adventure/covers/prompt.py`,
  `src/cyo_adventure/covers/provider.py`, `src/cyo_adventure/covers/storage.py`,
  `src/cyo_adventure/core/observability.py`, `frontend/src/observability.ts`.

*End of plan. A point-in-time engineering and process plan at commit `66fe320`, not legal
advice or a certification of compliance.*
