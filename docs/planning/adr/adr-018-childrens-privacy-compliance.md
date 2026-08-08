---
title: "ADR-018: Children's-privacy compliance architecture (COPPA, GDPR-K, AADC)"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Consolidate the children's-privacy compliance decisions scattered across ADR-008,
  ADR-009, and the privacy model into one decision record, and name the open choices
  (consent mechanism, audience classification, launch geography) that must be closed with
  counsel before the public tier ships."
tags:
  - planning
  - architecture
  - decisions
  - privacy
  - compliance
---

# ADR-018: Children's-privacy compliance architecture (COPPA, GDPR-K, AADC)

> **Status**: Proposed (2026-07-16). Becomes Accepted only after the open decisions below
> are closed with legal counsel; this matches the privacy model's standing note that these
> documents are design references, not legal advice.
> **Date**: 2026-07-16
> **Amended**: 2026-08-01 (amended-COPPA-rule compliance date has passed; new D5 on
> AI-training consent segregation; D4 gains the written Information Security Program and a
> Safe Harbor evaluation; biometric non-ingestion recorded as a boundary)
> **Amended**: 2026-08-06 (owner decisions recorded on D2, D4, and D5; Safe Harbor sequencing
> settled as counsel-first; D4's two rule-mandated artifacts confirmed to exist; counsel
> engagement packaged in [counsel-engagement-brief.md](../../compliance/counsel-engagement-brief.md)).
> **This does not flip the status.** Every decision below is an owner choice pending counsel
> confirmation; only counsel closing D1 through D5 moves this ADR to Accepted.
> **Relates to**: [ADR-008](./adr-008-public-app-store-launch.md) (Kids Category posture,
> part 5), [ADR-009](./adr-009-supabase-platform.md) (processor, DPA), [ADR-016](./adr-016-recommendation-sharing-social-boundary.md)
> (contact boundary), [ADR-017](./adr-017-ai-cover-art.md) (image-leg counterparties),
> [Privacy model](../privacy-model.md)

## TL;DR

One record for the compliance architecture of a child-directed app: what is already
decided (guardian-only identities, no kid-context SDKs, parental gate, deletion with
Apple revocation, data classification and retention, named processor list, no biometric
ingestion), and the open choices that carry the legal risk: the
verifiable-parental-consent mechanism, the audience classification, the launch geography
(US-only first vs EU/UK in scope, which decides whether GDPR-K and the UK AADC bind at
launch), the public artifacts, and, since the amended COPPA Rule passed its 2026-04-22
compliance date, whether any training corpus may ever contain child-originated data (D5).

## Context

COPPA (US), GDPR Article 8 with member-state ages 13-16 ("GDPR-K"), and the UK Age
Appropriate Design Code become externally enforceable the moment the public tier ships
(ADR-008). Today the posture is real but scattered: ADR-008 part 5 lists Kids Category
obligations, ADR-009 defers DPA verification to P7-08, the privacy model holds the data
classification and provider-counterparty list, and Phase 7 holds the tasks. Nothing
records the *choices* compliance forces, so they cannot be checked off or contested. The
register maps this territory to S10 (privacy architecture), G11 (plain-language trust
surface), G12 (export and deletion), K14 (safe room), and A14 (compliance ops).

**Amended 2026-08-01: the amended COPPA Rule is now current law, not an upcoming change.**
The FTC's 2025 amendments to the COPPA Rule (Federal Register doc. 2025-05904, published
2025-04-22, effective 2025-06-23) carried a full-compliance date of 2026-04-22, which has
passed. Nothing changes for the internal tier, but the Track 2 launch gate (ADR-008) must
verify against the amended rule text, not the 2013 rule this ADR was originally drafted
against. The amendments relevant here: biometric identifiers (facial templates,
voiceprints) join the definition of personal information with no temporary-use exception;
using or disclosing children's personal information to train AI models requires its own
separate, unbundled verifiable parental consent (new D5 below); operators must maintain a
written Information Security Program and a published written data-retention policy with
hard deletion timelines (folded into D4 below). Dates and rule text above should be
re-confirmed against the Federal Register during the counsel review that closes this ADR;
they entered this document from secondary sources.

## Already decided (consolidated; sources binding)

1. **Children never hold third-party identities.** Guardians are the only IdP accounts;
   child sessions are backend-minted and profile-scoped (ADR-008 decision 2, ADR-014).
2. **No ads ever, no third-party ad/analytics SDKs in the kid context** (vision permanent
   exclusion; ADR-008 part 5).
3. **Parental gate** in front of settings, purchases, generation, and external links
   (ADR-008); the kid-to-adult boundary crossing is ADR-014's step-up.
4. **Deletion**: in-app account deletion erases the family and revokes Apple tokens
   (ADR-008; Supabase admin API per ADR-009). Recommendation payloads and connections are
   in the erasure set (ADR-016).
5. **Data minimization spine**: child-linked data classification, no real child PII in
   prompts, raw-output retention with purge (ADR-007 as amended), admin-first raw-output
   access, deletion-readiness rules (privacy model).
6. **Named processor/counterparty list** (privacy model): Supabase (Postgres, auth),
   OpenRouter and downstream model providers (generation), OpenAI Moderation and Google
   Perspective (Stage-0 classifiers over all generated prose and child-typed wishes),
   Google Gemini and Cloudflare R2 (cover art, ADR-017), Sentry (exceptions, no child
   reading content). Every entry still needs verified terms at P7-08.

   **Amended 2026-07-28: the counterparties are no longer one undifferentiated tier**,
   because they do not receive the same kind of data and were never well served by one
   blocker covering all of them.

   - **Generation leg (OpenRouter and the endpoints it routes to): a documentation item,
     not a gate.** No registered child identifier can reach it: `assert_prompt_pii_safe`
     hard-fails the job rather than redacting (`generation/pii.py:229-289`). [ADR-023](./adr-023-story-personalization-slots.md)
     *proposes* to keep real values out of it permanently by resolving personalization
     client-side at render time instead of at generation time, but that ADR is
     `status: proposed`, its counsel sign-off is open, and no code exists for it yet, so it is
     a design commitment rather than a shipped property; **if ADR-023 is not adopted, this
     reason lapses.** Routing on the OpenRouter leg is additionally confined by a
     platform guardrail on a dedicated, key-scoped OpenRouter workspace configured
     2026-07-28: zero data retention required across non-frontier, Anthropic, OpenAI,
     Google, and xAI routing, and all three data-training paths disabled (paid-trains,
     free-trains, free-publishes-prompts). That guardrail reaches the OpenRouter route only;
     the built and admin-selectable direct-Anthropic leg bypasses it, which ADR-003's
     amendment records as an open item rather than a closed control. See ADR-003's 2026-07-28
     amendment for the full state and its limits. What the generation leg still carries is a
     coarse age band, guardian-set `banned_themes` and content-flag caps, and free-typed
     premise text carried through verbatim, so it is **identifier-free, not PII-free**, and its
     terms still belong in the P7-08 record.

     **The sub-processor set changed on 2026-07-28 and this list changes with it.** Enabling
     ZDR for the frontier vendors disables their *first-party* endpoints rather than the
     model families, so generation prompts now route to those families via **AWS Bedrock,
     Microsoft Azure, and Google Vertex**. Those three enter scope as OpenRouter's
     sub-processors for the generation leg and belong in the P7-08 processor record; they are
     added to `docs/compliance/processor-dpa-checklist.md` accordingly. First-party Anthropic
     and OpenAI endpoints leave scope **for traffic routed through OpenRouter**. They do not
     leave the record: the direct-Anthropic leg is built and admin-selectable and does not go
     through OpenRouter, so the "Anthropic (direct)" row stays, and
     `records-of-processing-activities.md` continues to list it as a live recipient. Note that
     this affects the **generation** leg only: OpenAI Moderation on the classifier leg is a
     separate, directly-called integration and is unaffected.
   - **Classifier leg (OpenAI Moderation, Google Perspective): this is where the gate
     lives now.** It receives child-typed request text at intake
     (`story_requests/screening.py`) and every node of generated prose during moderation.
     That is child-provided free text crossing to third parties, and nothing in ADR-023
     changes it. Blocker 1 is therefore **narrowed onto this leg rather than closed**; see
     privacy-model.md. The Perspective counterparty is separately in flux (see the Stage-0
     Perspective sunset work), which changes who is on this list but not the requirement.
   - **Cover art (Google Gemini) and storage (Cloudflare R2)** are unchanged: prompts derive
     only from story metadata and no child PII reaches the image provider (ADR-017).
7. **Contact boundary**: no messaging, no discovery, cross-family flows only through
   dual-guardian-consented connections (ADR-016).
8. **No biometric ingestion (recorded 2026-08-01; pending owner confirmation like the
   rest of this list).** The amended COPPA Rule adds biometric identifiers, facial
   templates and voiceprints included, to personal information, and the FTC declined to
   allow even temporary security or age-verification use without prior VPC. The app is
   out of this category entirely today: avatars are preset-only (no photo upload), and
   there is no voice input anywhere. This is recorded as a compliance boundary rather
   than a backlog gap: photo-derived avatars, photo personalization, and voice dictation
   are excluded features, and a future proposal to add any of them is a revision of this
   ADR (it would trigger maximum-protocol VPC for biometric data), not a product ticket.
   Competitors compete on photo-personalized avatars, so this temptation will recur; the
   boundary exists so it is contested here, deliberately, instead of in a sprint.

## Open decisions (the reason this ADR exists; close with counsel before Accepted)

### D1: Verifiable parental consent (VPC) mechanism

COPPA requires consent verification stronger than a tap-through; the App Store parental
gate does not satisfy VPC on its own. FTC-recognized methods include a payment-card
transaction, signed consent form, government-ID match, knowledge-based authentication,
and face-match-to-ID.

**Decision recorded 2026-07-20 (owner choice; pending counsel confirmation, not yet
"closed" per this ADR's own Validation checklist below).** The account owner ruled out a
payment-card transaction (avoids introducing PCI scope) and a third-party ID-verification
service (avoids a new processor and its own DPA/SCC/vendor-oversight burden). Chosen
mechanism instead: a signature-capture step layered on the existing Supabase/Google OAuth
login already used for guardian sign-in. Concretely, the guardian provides a
signature-equivalent (a typed full-legal-name attestation) plus an explicit checkbox
affirming specific consent language, a country-of-residence selection (O-117), and an
adulthood attestation checkbox (O-119); the app logs IP address, timestamp, and the
OAuth-authenticated account id server-side alongside it. **As built, the typed name is the
only signature-equivalent captured**; a canvas-drawn signature was considered in the
2026-07-20 framing but never implemented, and `GuardianConsentPage.tsx` has no drawing
surface. Do not describe a drawn signature as available. This was designed on the
understanding that it satisfied a "sign and submit electronically" method on the FTC's
enumerated list at 312.5(b)(2)(i), with the OAuth login supplying the identity binding
rather than a separate verification step. The mechanism applies uniformly regardless of
tier; the prior working recommendation's paid-tier/free-tier split (Apple IAP as the VPC
event) is superseded, since the app is not currently monetized and the owner does not want
VPC design coupled to a future payment decision.

**That premise is now in doubt and must not be restated as settled.** On 2026-08-08 the rule
text at 16 CFR 312.5(b)(2) was read directly and contains no "sign and submit
electronically" method. Method (i) reads as a *return channel*: a form signed away from the
service and returned by postal mail, facsimile, or electronic scan. If that reading holds,
an electronic signature captured inside our own application is not within method (i) at all,
and the open question is not whether our signature is good enough but whether we are using
an enumerated method at all. Note also 312.5(b)(3), under which an FTC-approved Safe Harbor
program may approve a non-enumerated method meeting the general standard in 312.5(b)(1);
that may be the route by which the shipped implementation becomes usable rather than
replaced. `docs/compliance/counsel-engagement-brief.md` Sections 1.1, 1.3, and 1.5 carry the
corrected framing and the questions actually put to counsel.

**Flagged for counsel**: whether a typed-name attestation captured inside our own application
is an enumerated 312.5(b)(2) method **at all** is the single highest-risk open question in
this decision, and it is a broader question than the "is our signature good enough" one this
ADR originally posed. It should be the first thing reviewed in the drafted consent-flow copy
(`docs/compliance/` DPIA and Privacy Notice drafts, in progress).

**Implemented 2026-07-20.** `POST /api/v1/onboarding`'s `consent` payload
(`accepted`/`policy_version`/`signer_name`) persists onto
`User.consent_accepted_at`/`consent_policy_version`/`consent_signer_name`/`consent_ip`
(paired, CHECK-enforced); `api/profiles.py::_require_consent` gates
`POST /api/v1/profiles` on it. Frontend: `GuardianConsentPage.tsx`, reached automatically via
a new `AuthStatus = 'needs-consent'`. This is the engineering half of D1; the flagged
counsel-review question above is unchanged by implementation and still needs an answer
before this ADR can flip to Accepted.

**Related, newly decided the same day, not itself part of D1**: a guardian self-signup
admin-approval gate. An uninvited guardian's own first-login JIT provisioning now starts
`User.status='awaiting_approval'` instead of `active`; `api/deps.py::require_principal`
already rejects every endpoint for a non-`active` status, so this alone is the enforcement
mechanism. An admin approves (`-> active`) or denies (`-> deactivated`) via the existing
`PATCH /admin/users/{id}`. This is a parallel, non-overlapping track to the admin-invite
`pending` status already in this ADR's "already decided" list; an admin-invited guardian is
still trusted immediately on bind, unaffected by this gate. Frontend:
`GuardianAwaitingApprovalPage.tsx`, reached via a new `AuthStatus = 'awaiting-approval'`.

### D2: Audience classification

Kids Category listing (ADR-008) effectively declares the app child-directed, which takes
the strictest COPPA lane and removes the "actual knowledge" defenses of mixed-audience
apps. Decision needed: confirm child-directed as the declared posture (recommended,
matches product reality) and record that mixed-audience arguments are unavailable.

**Decision confirmed 2026-08-06 (owner choice; pending counsel confirmation).** Child-directed
is the declared posture. Mixed-audience "actual knowledge" defenses are recorded as
unavailable and must not be relied on in any later design argument. This closes the gap that
made D2 unreviewable: until an owner had actually ruled, there was no position for counsel to
confirm, only a recommendation. Counsel's role on this item is confirmation, not selection.

### D3: Launch geography and GDPR-K/AADC applicability

If launch is US-only (App Store storefront restriction), GDPR-K and the UK AADC do not
bind at launch and become expansion gates instead; if EU/UK storefronts are in scope, a
DPIA, per-state consent ages (13-16), and AADC conformance (default-high privacy,
best-interests assessment) join Phase 7. **Working recommendation**: launch US storefront
only, record EU/UK as an explicit later expansion with its own compliance gate. Decision
needed: confirm.

**Decision confirmed 2026-07-20 (owner choice; pending counsel confirmation).** No UK or
EEA users exist today, and none are planned. US-only is confirmed as the working
recommendation above, not merely proposed. `coppa-gdpr-remediation-plan.md` Phase 9
(GDPR-K/AADC conformance) is shelved, not worked, pending a change in this fact; if UK/EEA
users are ever expected, revisit this decision and Phase 9 together before that expansion
ships, not after.

### D4: Public artifacts

A published privacy notice, App Store privacy nutrition labels derived from the
data classification, a data-retention schedule, and a breach/incident-response plan
(feeds register A5/A14). Decision needed: owner sign-off that these are Phase 7
deliverables with P7-08 as the checkpoint, and who drafts the notice.

**Decision confirmed 2026-08-06 (owner choice).** These are Phase 7 deliverables with P7-08
as the checkpoint. **The project owner drafts every artifact; counsel reviews rather than
drafts.** That ordering is deliberate: drafting internally and sending finished text is
cheaper than paying counsel to originate documents whose substance is already decided
elsewhere in this repository.

**Amended 2026-08-01, two additions.**

- **Two artifacts above are now rule requirements, not best practice.** The amended COPPA
  Rule mandates (a) a *written* Information Security Program: annual risk assessment, a
  vulnerability-testing cadence, vendor due diligence over the processors in this ADR's
  counterparty list, and a designated compliance owner; and (b) a *published* written
  data-retention policy naming the business need and a hard deletion timeline for each
  class of children's data (the privacy model's data classification is the direct input).
  Both join the D4 deliverable list by name so P7-08 can check them off individually. The
  existing security tooling (scanner suite, dependency scanning, container scanning) is
  most of the WISP's substance; what is missing is the written program document that names
  it, its cadence, and its owner.

  **Status corrected 2026-08-06: both artifacts now exist, but only (a) satisfies the rule
  today.** (a) is complete and published; (b) is drafted, not yet published, and still
  carries three data classes with no deletion window set, so D4's published-policy leg is
  not yet met. (a) The written Information Security Program is
  [information-security-program.md](../../compliance/information-security-program.md),
  `status: published`, and it already carries all four mandated elements: the annual
  risk-assessment cadence (section 3), the vulnerability-testing cadence tied to the
  scanner suite and `SECURITY.md`'s severity/response table (section 3), vendor and
  service-provider due diligence over this ADR's counterparty list (section 4), and a named
  compliance owner (section 2). It predates this amendment, which is why the amendment
  described it as missing. (b) The written data-retention policy is
  [data-retention-policy.md](../../compliance/data-retention-policy.md), created 2026-08-06
  and currently `status: draft`. It consolidates the per-category schedule resolved
  2026-07-20 in `coppa-gdpr-remediation-plan.md` (which governs, and is reproduced rather
  than re-derived) with the guardian-facing table in `privacy-notice.md` and the
  per-activity view in `records-of-processing-activities.md`, and adopts the additional
  categories `UW-N07` names. **Three of its classes carry no window yet** and are written
  as "Not yet set, owner ruling required" rather than given an invented number: consent
  evidence, product analytics, and application logs. The rule requires a hard deletion
  timeline for *each* class of children's data, and product analytics and application logs
  are both children's data, so (b) does not discharge D4 until those three rulings land and
  the document moves to `status: published`. That residual is tracked at `UW-N07`. Both go
  to counsel under this decision's owner-drafts/counsel-reviews split: (a) as finished work
  for review, (b) as a draft with three named gaps.
- **Evaluate COPPA Safe Harbor membership (PRIVO, kidSAFE, ESRB Privacy Certified) as an
  explicit Track 2 task.** A Safe Harbor program would answer D1's flagged highest-risk
  question (whether the signature-capture flow is an enumerated 312.5(b)(2) method at all)
  with a presumption-of-compliance posture and ongoing external audit, instead of a one-off
  counsel opinion, at the cost of a recurring fee and an added vendor. Decision needed:
  whether this evaluation happens before or alongside the counsel review of D1, since a
  yes here changes what D1's counsel question is worth.

  **Reweighted 2026-08-08 by the D1 correction above.** This bullet was written treating a
  Safe Harbor program as an *alternative* to the counsel opinion. Under 312.5(b)(3) it is
  also a mechanism for *approving* a non-enumerated method, so if counsel concludes the
  shipped flow sits outside 312.5(b)(2), this stops being an optional cost-saver and becomes
  a candidate route to making the existing implementation lawful without rebuilding it. The
  sequencing decision below stands; what changes is the value of the evaluation's outcome.

  **Sequencing decided 2026-08-06 (owner choice): alongside, counsel first.** D1 goes to
  counsel now rather than waiting on a Safe Harbor evaluation, because counsel scheduling is
  the long-lead item on the critical path to Phase 7 and the public rungs, and a Safe Harbor
  evaluation is not. The evaluation proceeds in parallel as a Track 2 task. The accepted cost
  of this ordering is that a later decision to join a program could supersede the D1 opinion,
  so the counsel engagement flags that possibility explicitly and asks counsel to scope the
  D1 opinion accordingly rather than assuming it is the permanent basis of compliance.

### D5: AI-training use of children's data (consent segregation; added 2026-08-01)

The amended COPPA Rule treats using or disclosing a child's personal information to train
or develop AI models as non-integral to the service: it requires its own separate, opt-in
verifiable parental consent, unbundled from the core-service consent, and refusing it
cannot cost the child access to the core service.

This intersects one live plan directly: the proposed self-labeled moderation corpus (human
review decisions collected as future fine-tuning and evaluation data for the moderation
reviewer, the Gate 3/4 follow-on from the 2026-08-01 datasets research). Whether the
obligation triggers depends entirely on what the corpus contains.

**Working position (2026-08-01, pending owner confirmation):** build any training or
evaluation corpus exclusively from adult-originated and pipeline-originated material:
reviewer decisions, moderation findings, and generated prose that has passed the PII gate
(`generation/pii.py`). Child-originated data, child-typed wish text from intake, and child
behavioral signals (flags, ratings, reading state) are excluded from every training set.
Under this constraint no child personal information is used for AI training and the
segregated-consent obligation never triggers; the constraint costs nothing today because
no planned corpus needs child-originated data.

**Escape hatch, priced now while the D1 flow is fresh:** if child-originated data is ever
wanted in a training set, the D1 consent flow gains a separate opt-in toggle first, before
any such data is collected for that purpose: a `policy_version` bump plus an independent,
default-off checkbox whose refusal has no effect on service access. That is a small change
against the existing `POST /api/v1/onboarding` consent payload and `GuardianConsentPage.tsx`,
but it must precede collection, not follow it.

Decision needed: owner confirms the corpus constraint as the default, or opts to build the
segregated-consent toggle now.

**Decision confirmed 2026-08-06 (owner choice).** The corpus constraint is adopted as the
standing default; the segregated-consent toggle is **not** built now. Any training or
evaluation corpus is built exclusively from adult-originated and pipeline-originated
material. Child-typed wish text from intake, and child behavioral signals (flags, ratings,
reading state), are excluded from every training set. This is a standing constraint on future
work, not a one-time assessment: a proposal that wants child-originated data in a corpus is a
revision of this decision, and the escape hatch above (a `policy_version` bump plus an
independent, default-off opt-in whose refusal cannot affect service access) must be built
**before** any such collection begins, not after. Counsel's role on this item is a light
confirmation that the segregated-consent obligation does not trigger under the constraint,
not a design question.

- ✅ Compliance stops being folklore spread over four documents; Phase 7 becomes the
  implementation of this ADR and P7-08 its checklist.
- ✅ The already-decided list above is now contestable and testable (deletion E2E,
  egress-guard tests, SDK audit map to it).
- ⚠️ Until D1-D3 are closed, Phase 7 cannot be scoped precisely; this ADR staying
  Proposed is itself the tracking signal.
- ⚠️ Counsel review is a real dependency and cost; the recommendations above are
  design positions, not legal conclusions.

## Validation

**Progress note, 2026-08-06.** The owner-side prerequisites are done: D2, D3, D4, and D5 all
carry recorded owner decisions, D1's mechanism is decided and implemented, and the packet
counsel receives is assembled at
[counsel-engagement-brief.md](../../compliance/counsel-engagement-brief.md). What remains on
every unchecked box below is external: retaining counsel and getting rulings. No checkbox is
ticked by internal work alone, which is why none are ticked here.

- [ ] D1-D5 closed with counsel; status flipped to Accepted with the choices recorded.
- [ ] Amended-rule facts (dates, biometric definition, AI-training consent, WISP and
      retention-policy mandates) re-confirmed against the Federal Register text during
      counsel review; they entered this ADR from secondary sources.
- [ ] P7-08 checklist maps one-to-one to the "already decided" list and the closed
      decisions.
- [ ] Deletion E2E (family erasure incl. Apple revocation) and the kid-context SDK audit
      pass before submission.

## Related

- [Capability register](../capability-register.md): S10, G11, G12, K14, A14.
- [Privacy model](../privacy-model.md): classification, counterparties, Blocker 1.
- [PROJECT-PLAN.md](../PROJECT-PLAN.md): Phase 7.
