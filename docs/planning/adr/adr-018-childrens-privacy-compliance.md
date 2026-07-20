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
> **Relates to**: [ADR-008](./adr-008-public-app-store-launch.md) (Kids Category posture,
> part 5), [ADR-009](./adr-009-supabase-platform.md) (processor, DPA), [ADR-016](./adr-016-recommendation-sharing-social-boundary.md)
> (contact boundary), [ADR-017](./adr-017-ai-cover-art.md) (image-leg counterparties),
> [Privacy model](../privacy-model.md)

## TL;DR

One record for the compliance architecture of a child-directed app: what is already
decided (guardian-only identities, no kid-context SDKs, parental gate, deletion with
Apple revocation, data classification and retention, named processor list), and the three
choices still open that carry the legal risk: the verifiable-parental-consent mechanism,
the audience classification, and the launch geography (US-only first vs EU/UK in scope,
which decides whether GDPR-K and the UK AADC bind at launch).

## Context

COPPA (US), GDPR Article 8 with member-state ages 13-16 ("GDPR-K"), and the UK Age
Appropriate Design Code become externally enforceable the moment the public tier ships
(ADR-008). Today the posture is real but scattered: ADR-008 part 5 lists Kids Category
obligations, ADR-009 defers DPA verification to P7-08, the privacy model holds the data
classification and provider-counterparty list, and Phase 7 holds the tasks. Nothing
records the *choices* compliance forces, so they cannot be checked off or contested. The
register maps this territory to S10 (privacy architecture), G11 (plain-language trust
surface), G12 (export and deletion), K14 (safe room), and A14 (compliance ops).

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
   reading content). Every entry needs verified terms at P7-08; the OpenRouter ZDR
   question is the standing Blocker 1.
7. **Contact boundary**: no messaging, no discovery, cross-family flows only through
   dual-guardian-consented connections (ADR-016).

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
signature-equivalent (a canvas-drawn signature or a typed full-legal-name attestation)
plus an explicit checkbox affirming specific consent language; the app logs IP address,
timestamp, and the OAuth-authenticated account id server-side alongside it. This is meant
to satisfy the "sign and submit electronically" method already on the FTC's enumerated
list (312.5(b)(2)(i)), with the OAuth login supplying the identity binding rather than a
separate verification step. This applies uniformly regardless of tier; the prior working
recommendation's paid-tier/free-tier split (Apple IAP as the VPC event) is superseded,
since the app is not currently monetized and the owner does not want VPC design coupled to
a future payment decision.

**Flagged for counsel**: whether a typed-name or canvas signature captured this way
satisfies 312.5(b)(2)(i)'s "signed" requirement is the single highest-risk open question in
this decision and should be the first thing reviewed in the drafted consent-flow copy
(`docs/compliance/` DPIA and Privacy Notice drafts, in progress).

**Implemented 2026-07-20.** `POST /v1/onboarding`'s `consent` payload
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

## Consequences

- ✅ Compliance stops being folklore spread over four documents; Phase 7 becomes the
  implementation of this ADR and P7-08 its checklist.
- ✅ The already-decided list above is now contestable and testable (deletion E2E,
  egress-guard tests, SDK audit map to it).
- ⚠️ Until D1-D3 are closed, Phase 7 cannot be scoped precisely; this ADR staying
  Proposed is itself the tracking signal.
- ⚠️ Counsel review is a real dependency and cost; the recommendations above are
  design positions, not legal conclusions.

## Validation

- [ ] D1-D4 closed with counsel; status flipped to Accepted with the choices recorded.
- [ ] P7-08 checklist maps one-to-one to the "already decided" list and the closed
      decisions.
- [ ] Deletion E2E (family erasure incl. Apple revocation) and the kid-context SDK audit
      pass before submission.

## Related

- [Capability register](../capability-register.md): S10, G11, G12, K14, A14.
- [Privacy model](../privacy-model.md): classification, counterparties, Blocker 1.
- [PROJECT-PLAN.md](../PROJECT-PLAN.md): Phase 7.
