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

**The gap**: the guard only knows about names/birthdates already on file as a `child_profile`
row. It has no way to catch a sibling's name, a friend's name, a home address, a school name,
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
prompt assembly in the same guard `generation/guarded.py` already provides). The R2 bucket
being public with a guessable key is a second, independent issue (anyone who guesses or is
handed a URL can view a specific child's cover art without authentication); it doesn't leak
identifying data on its own since keys aren't derived from anything identifying, but it is
still worth closing as part of the same work item since it is the same subsystem.

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

1. **Verifiable parental consent (VPC) method.** *Needed before Phase 2 can be built.*
2. **Supabase project region.** *Needed before Phase 4's Supabase work, and cheapest to
   decide now while the user base and data volume are both still small.*
3. **Does the product intend children to appear as themselves (named) in their own stories?**
   *Needed before Phase 1's PII-guard hardening is scoped, since it changes what "identifying
   content" even means for this product.*
4. **Who signs off on and owns the compliance artifacts** (privacy notice, DPIA, DPAs), and
   **when does privacy counsel get engaged?** *Needed before Phase 2 and Phase 7 can start in
   earnest; the engineering work in Phases 1, 3, 4, and 6 does not depend on counsel and can
   start immediately.*
5. **Retention windows per data category.** *Needed before Phase 4's purge jobs are built.*
6. **DPO designation.** *Needs your projected user scale; can be assessed in parallel with
   everything else and doesn't block any engineering work.*
7. **Zero-data-retention (ZDR) terms with OpenRouter and the other LLM/classifier vendors.**
   *ADR-018 already calls this "standing Blocker 1"; needed before Phase 5 can close.*

---

## 3. Phased implementation plan

Phases 1, 3, 4, and 6 are pure engineering and can start immediately, in parallel, without
waiting on any legal/business decision. Phase 2 needs decision 1 above. Phase 5 needs decision
7. Phase 7 needs decisions 4 and 6, and drafting time from whoever is assigned.

### Phase 1: Close the PII-egress gaps (engineering, no dependencies, start now)

Directly addresses the gaps found in Section 1.

- **1a. Extend the PII guard beyond exact-name matching.** Add pattern-based detection (email
  addresses, phone numbers, street addresses, and a configurable "other family members'
  names" list a guardian can register) to `generation/pii.py`, applied at the same
  chokepoint. Document the residual risk explicitly (a general PII/named-entity detector will
  never be perfect); this is defense-in-depth on top of the exact-match guard, not a
  replacement for the consent/notice work in Phase 2.
- **1b. Guard the cover-art path.** Wrap `covers/service.py`'s prompt assembly (which calls
  `covers/prompt.py::build_cover_prompt`) in the same `PiiGuardedProvider`/
  `assert_prompt_pii_safe` chokepoint the generation path already uses, using the same
  `PiiContext` for the family. This is the highest-value single fix in this phase: it closes
  the one path that currently has *zero* PII screening.
- **1c. Guard the Stage-0 classifier calls in the moderation pipeline.** Wrap the
  `run_classifiers` call in `moderation/pipeline.py::_run_all_stages` with the same guard
  already applied three lines away to `guarded_review`, so OpenAI Moderation and Google
  Perspective receive the same screening as every other external call in that function.
- **1d. Make the R2 cover bucket private.** Switch to signed, expiring URLs (or gate retrieval
  behind the family-scoped API) instead of a public bucket with a guessable key. Independent of
  1a-1c; can be done in parallel.
- **1e. Retire the dead birthdate-screening branch**, or wire it correctly if a birthdate is
  ever collected, so the guard's own documentation doesn't imply coverage it doesn't have.

### Phase 2: Consent and notice (needs Decision 1; drafting can start once VPC method is chosen)

- **2a. Build the consent-capture flow.** Replace `onboarding.py`'s `_record_consent()` no-op
  stub with a real implementation: present the privacy notice, capture consent by the chosen
  VPC method, persist a consent record (method, timestamp, policy version, and which processing
  purposes were consented to) on the family. Gate all child-profile creation and child-data
  collection behind this record existing.
- **2b. Add a re-consent flow** triggered on material privacy-notice changes.
- **2c. Draft and publish the privacy notice**, written once against the union of COPPA
  312.4's content list and GDPR Articles 13-14's broader content list (controller identity,
  purpose-by-purpose lawful basis, the full processor list from Section 4.2 of the GDPR
  review, retention periods per category, the complete data-subject-rights list including the
  right to complain to a supervisory authority, and the international-transfer mechanism relied
  on). Link it from the landing page, guardian console, and onboarding flow.
- **2d. Direct notice to the parent** at onboarding (email, once the `user` table gains an
  email/contact column per the existing plan item P6-03).

### Phase 3: Data-subject rights (engineering, no dependencies, start now)

- **3a. Add FK cascades** (`ON DELETE CASCADE` via migration, or an explicit application-level
  purge routine enumerating every child-linked and guardian-linked table, including the
  `pipeline_event` rows that reference a profile) so a delete request can actually be executed
  without orphaning rows or hitting a `NO ACTION` FK error.
- **3b. Build an authenticated deletion endpoint** for a child profile and for the whole family
  account, including guardian self-deletion (Article 17 applies to the guardian as a data
  subject in their own right, not only as the parent exercising the child's rights).
- **3c. Build a guardian-facing data export** assembling every record tied to the family and
  each child profile (profile, reading state, completions, ratings, story requests, generation
  reports where accessible) in a portable format, satisfying both COPPA 312.6(a) access and
  GDPR Article 20 portability in one endpoint.
- **3d. Add the missing `completion` read endpoint** (currently the one child-linked table with
  no read path at all).
- **3e. Run a deletion drill** once 3a-3b ship: create a test family, populate every table,
  delete it, and verify nothing referencing that family/profile survives outside what a
  documented retention exception (Phase 4) explicitly allows.

### Phase 4: Retention, storage governance, and the Supabase decision (needs Decision 2 and 5)

- **4a. Execute the Supabase region decision** (Section 2, Decision 2) while data volume is
  still small, since migrating a live project's region later is materially harder than choosing
  correctly now.
- **4b. Write and publish a retention policy** stating purpose and retention window per data
  category (reading state, completions, ratings, story requests including blocked/declined
  ones, generation reports, audit/event log), per Decision 5.
- **4c. Build the retention-purge jobs**: the already-designed `generation_job.report` pg_cron
  purge (ADR-007), plus a new purge/redaction path for blocked or declined `story_request` rows
  (currently retained at rest indefinitely even when blocked; only the API view layer redacts
  them), plus expiry for stale `reading_state`.
- **4d. Document an explicit Article 17(3) balancing justification** for why the
  `pipeline_event` audit log is exempted from erasure requests, rather than leaving that
  exemption implicit; this makes 3a-3b's deletion drill (3e) something you can point to during
  a review rather than something you have to re-derive on demand.

### Phase 5: Processor paperwork (needs Decision 7 for the LLM vendors; the rest can start now)

- **5a. Confirm and execute a DPA (and SCCs, given every processor listed is US-hosted) with
  each processor**: Supabase, OpenRouter and downstream model providers, Anthropic-direct,
  OpenAI Moderation, Google Perspective, Google Gemini, Cloudflare R2, and Sentry. For Sentry
  specifically, given Section 1's finding that it already receives no PII by hardcoded design,
  this is close to a formality, but "compliant from the start" means closing it rather than
  assuming it's unnecessary because the data itself is already clean.
- **5b. Prioritize zero-data-retention (ZDR) terms with OpenRouter** specifically, since
  ADR-018 already flags this as the standing blocker; resolve it explicitly rather than letting
  it stay open indefinitely.
- **5c. Record every outcome** in `docs/planning/privacy-model.md`'s processor list, so Phase 7's
  Records of Processing document (below) has a single source of truth to pull from.

### Phase 6: Security hardening (engineering, no dependencies, start now)

- **6a. Enable `TrustedHostMiddleware`** with `allowed_hosts` set, and confirm HTTPS redirect
  is enforced somewhere in the request path (app-layer or reverse-proxy; document which).
- **6b. Write a short internal information-security program document**: designated security
  contact, a documented risk-assessment cadence, and a vendor-oversight process, satisfying both
  COPPA 312.8's 2025-amendment expectation and GDPR Article 32(1)(d)'s "regularly testing,
  assessing and evaluating" requirement in one artifact.
- **6c. Draft a breach-notification runbook**, distinct from `SECURITY.md`'s external
  vulnerability-reporting policy: an internal incident-classification rubric, an escalation
  path, and the two clocks that start on discovery (GDPR Article 33's 72-hour
  notification-to-authority duty, and Article 34's separate "high risk to individuals"
  notification duty).
- **6d. Correct `SECURITY.md`**, which currently asserts a "no persistent PII without explicit
  parental consent" control that doesn't exist yet, and is stale on the auth description.

### Phase 7: Formal compliance documentation (needs Decisions 4 and 6)

- **7a. Assemble a Records of Processing Activities document (GDPR Article 30)** from material
  that already exists across the COPPA audit, the GDPR review, and `privacy-model.md`; this is
  synthesis, not new research, and is one of the lowest-cost, highest-value items in this whole
  plan.
- **7b. Commission a Data Protection Impact Assessment (GDPR Article 35(3)(b))** before, not
  after, Phase 2's consent-flow build finalizes its design, per the earlier GDPR review's
  Pressure Point P-2; use the Article-25-by-design strengths already documented (data
  minimization, no ads/analytics SDKs, closed-vocabulary avatars, real tenancy auth) as the
  DPIA's starting risk-mitigation inventory.
- **7c. Assess the DPO question (Article 37)** against your projected scale once Track 2
  planning has real numbers; record the outcome either way.
- **7d. Confirm the audience-classification and launch-geography decisions in ADR-018 (D2, D3)**
  now reflect this plan's "compliant from the start" direction rather than the deferred-GDPR-K
  posture D3 currently recommends, and flip ADR-018 from Proposed to Accepted once D1-D4 close.

### Phase 8: Ongoing compliance operations (start once Phases 1-7 are substantially done)

- **8a. Log admin views of child-linked data**, not just admin mutations (currently
  `admin_profiles.py`'s GET paths write no audit event, so an admin browsing a specific child's
  profile leaves no trace, unlike write actions elsewhere).
- **8b. Complete ADR-016's guardian-facing consent UI** for cross-family recommendation
  sharing, so the consent columns already in the schema have an actual guardian-operated
  control in front of them.
- **8c. Set an annual (or pre-major-feature) compliance review cadence**, re-running this plan's
  Phase 1-6 checks against whatever has shipped since.

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

This plan does not replace `PROJECT-PLAN.md` Phase 7 or ADR-018; it sequences them into
dependency order and adds Phase 1 (the specific egress gaps found in Section 1) and Phase 8
(ongoing operations), neither of which the existing plan tracks as discrete items.

---

## 5. Consolidated open questions

Organized by which phase they gate. A recommended default is given where one exists; items
marked **(no default)** genuinely need your input.

**Gates Phase 2 (consent):**

1. **VPC method.** FTC-recognized methods include a payment-card transaction, a signed consent
   form, government-ID matching, knowledge-based authentication, or face-match-to-ID. Do you
   have (or plan) a paid tier at all? If yes, a card transaction at signup is the
   lowest-friction option and is the working recommendation already in ADR-018. If the product
   stays free, or has a free tier that collects child data before any purchase, a different
   method is needed for that path specifically. **(no default without knowing the monetization
   plan)**

**Gates Phase 4 (retention/storage):**

2. **Supabase region.** Stay on `us-east-1` and rely on SCCs for any future EU user's data
   (cheaper now, and consistent with "all current users are US"), or proactively move to (or
   dual-run in) an EU-capable Supabase region now, given the stated "compliant from the start"
   goal? Recommendation: given the current user base is confirmed US-only and a region
   migration is expensive later, staying on `us-east-1` now and having SCCs ready is the more
   practical reading of "compliant from the start" than a premature region move, but this is
   ultimately your call to make, not a default I'd assume without asking. **(recommend staying
   US + SCC-ready, but flagging as your decision)**
3. **Retention windows per data category.** How long should reading state, ratings, story
   requests (including blocked/declined ones), generation reports, and the audit/event log be
   kept after last activity or after account deactivation? **(no default; needs your input on
   what "as long as needed to deliver the service" actually means for each category)**

**Gates Phase 1 (PII-guard hardening) and touches product design:**

4. **Will children ever appear as themselves (by their real name) as the protagonist of their
   own story?** This is a genuine product question, not just a compliance one: if yes, that's a
   deliberate personalization feature, and the guard's current behavior (block if it matches
   the registered name) may be the *wrong* behavior for the intended feature and needs a
   different design (e.g., explicitly allow it with the guardian's informed awareness, since
   it's no longer "identifying content leaking unintentionally" but "identifying content the
   feature is designed to produce"). If no, the current guard behavior is correct and Phase 1a's
   hardening should extend the same "never allowed" posture to other family members' names.
   **(no default; this is a product decision)**

**Gates Phase 5 (processor paperwork):**

5. **Zero-data-retention terms with OpenRouter and the other LLM/classifier vendors.** Who
   pursues this, and on what timeline? ADR-018 already calls it the standing blocker; it just
   needs an owner and a deadline. **(no default; needs an owner assigned)**

**Gates Phase 7 (formal documentation) and Decision 4/5 above:**

6. **Who owns and signs off on the compliance artifacts** (privacy notice, DPIA, DPA/SCC
   execution, retention policy)? **(no default; needs a named owner, likely you or whoever you
   designate)**
7. **When does privacy counsel get engaged?** Given the "compliant from the start" goal, the
   working recommendation is: now, in parallel with Phase 1/3/4/6 engineering work, so counsel's
   review of the consent mechanism and notice language (Phase 2) and the DPIA (Phase 7) doesn't
   become the critical-path bottleneck once the engineering is otherwise ready. **(recommend
   engaging now; timing is your call)**
8. **DPO designation.** Needs your projected user scale at whatever launch tier you're
   planning toward; can be assessed in parallel with everything else. **(no default; needs
   scale projections)**

---

## 6. Suggested sequencing

```text
Now, in parallel, no dependencies:
  Phase 1 (PII-egress hardening)
  Phase 3 (deletion cascades, export, access endpoints)
  Phase 6 (security hardening)
  Decision-gathering: 1, 2, 3, 4, 5, 6, 7, 8 (Section 5)

Once Decision 1 (VPC method) lands:
  Phase 2 (consent + notice build)

Once Decision 2 (Supabase region) and 3 (retention windows) land:
  Phase 4 (retention policy + purge jobs + region work)

Once Decision 5 (ZDR owner) lands, in parallel with the above:
  Phase 5 (processor DPAs/SCCs)

Once Decisions 6, 7 land and Phases 1-6 are substantially built:
  Phase 7 (DPIA, Records of Processing, DPO assessment, ADR-018 D1-D4 closeout)

Ongoing, once the above is stable:
  Phase 8 (admin-audit logging, ADR-016 consent UI, annual review cadence)
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
