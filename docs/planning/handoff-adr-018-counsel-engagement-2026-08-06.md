---
purpose: What ADR-018 (children's-privacy compliance) needs from outside counsel, narrowed to the
  specific open questions so engaging counsel is a scoped ask rather than "review this ADR"
component: docs/planning/adr/adr-018-childrens-privacy-compliance.md, docs/compliance/
source: R1-completion review session, 2026-08-06
---

# Handoff: ADR-018 counsel engagement

Written 2026-08-06. This is item 3 of a four-item R1-completion handoff set; see the sibling
handoffs for the CVE gate/live defects (item 1), the R1 live E2E sign-off (item 2), and the OG1/OG7
owner decisions (item 4).

## 1. Correction to how this was framed earlier

`roadmap.md`'s Now-queue item 5 (2026-07-20 audit) says ADR-018 "is still `status: proposed` ...
with no counsel sign-off or progress note since 2026-07-16." **That undersells how much internal
work has actually happened since.** The ADR was substantively amended 2026-08-01: D1 (consent
mechanism) and D3 (launch geography) both moved from "decision needed" to "decision recorded /
confirmed (owner choice; pending counsel confirmation)," D1's engineering half is already
implemented and merged, D4 gained two new rule-mandated artifacts, and D5 is a wholly new open
decision the amended COPPA Rule forced. **This is not a "start from scratch" ask, it's "get a
lawyer to bless work that is already drafted, and rule on the one item that has no working position
yet."** Frame the engagement that way; asking for a general privacy-compliance review will cost more
time and money than necessary.

## 2. What counsel needs to look at, one item at a time

The ADR has five open decisions (D1-D5). Their state differs, and that difference should shape the
engagement scope:

### D1: Verifiable parental consent mechanism: **narrow, specific question**

Owner already chose the mechanism (signature-capture layered on existing Supabase/Google OAuth
login: canvas signature or typed full-legal-name attestation, plus a checkbox, with IP/timestamp/
account-id logged server-side) and it's already implemented (`POST /v1/onboarding`'s `consent`
payload, `GuardianConsentPage.tsx`, gated via `api/profiles.py::_require_consent`). **The ADR itself
names the single highest-risk open question**: whether a typed-name or canvas signature captured
this way satisfies COPPA Rule 312.5(b)(2)(i)'s "signed" requirement for the "sign and submit
electronically" consent method. That's the question to put in front of counsel first, it's already
drafted as a yes/no with supporting detail in the ADR's D1 section, not an open-ended design
question.

### D2: Audience classification: **needs an owner recommendation confirmed, not just counsel**

This is the one item with no recorded owner decision yet, only a recommendation ("confirm
child-directed as the declared posture, matching product reality; mixed-audience defenses are
unavailable"). Get the owner to formally affirm this recommendation before or alongside sending it
to counsel, there's nothing to review yet if the owner hasn't actually decided.

### D3: Launch geography: **confirmed, low-risk counsel check**

Owner confirmed US-only launch 2026-07-20 (no UK/EEA users exist or are planned; GDPR-K/AADC
shelved as a later expansion gate, not worked now). This is the lowest-risk item to clear with
counsel, it's a straightforward "confirm GDPR-K/AADC don't bind at a US-only launch" question.

### D4: Public artifacts: **owner sign-off needed on scope, then counsel drafts/reviews**

Two things needed before this is counsel-ready:
1. Owner sign-off that the artifact list (privacy notice, App Store nutrition labels, retention
   schedule, breach/incident-response plan) are Phase 7 deliverables checked off at P7-08, and who
   drafts the notice.
2. A decision on **Safe Harbor program membership** (PRIVO, kidSAFE, ESRB Privacy Certified), added
   2026-08-01. This is worth deciding *before* sending D1 to counsel, not after: a Safe Harbor
   program would answer D1's signature-question with a presumption-of-compliance posture and
   ongoing external audit instead of a one-off legal opinion, at the cost of a recurring fee and an
   added vendor. If the owner is inclined toward Safe Harbor, sequence that decision first so D1's
   counsel question isn't asked twice.
3. Two artifacts the amended COPPA Rule now makes mandatory rather than best-practice: a **written**
   Information Security Program (annual risk assessment, vulnerability-testing cadence, vendor due
   diligence, a designated compliance owner) and a **published, written** data-retention policy with
   a hard deletion timeline per data class. Most of the WISP's substance already exists as tooling
   (the scanner suite, dependency scanning, container scanning), what's missing is the document
   that names it, its cadence, and its owner. This can be drafted internally before counsel sees it.

### D5: AI-training consent segregation: **owner confirmation needed, counsel-light**

Added 2026-08-01 in response to the amended COPPA Rule (training/developing AI models on a child's
personal information now requires its own separate, unbundled, opt-in verifiable consent). Working
position: build any training/eval corpus exclusively from adult-originated and pipeline-originated
material (reviewer decisions, moderation findings, PII-gate-passed generated prose); exclude
child-typed wish text, flags, ratings, and reading state entirely. Under this constraint the
segregated-consent obligation never triggers, **and it costs nothing today because no planned corpus
needs child-originated data.** Get the owner to confirm this as the standing constraint (this is
mostly a policy decision, not a legal one), if a future corpus ever wants child-originated data, the
ADR already prices the fallback (a `policy_version` bump plus an independent, default-off
consent-toggle, built *before* collection, not after).

## 3. What to actually hand counsel

Do not send the whole ADR as a first document. Package these together for an efficient engagement:

1. The ADR's D1 section (already-drafted mechanism plus the named 312.5(b)(2)(i) question).
2. The confirmed D3 answer (US-only launch) as a one-line confirmation ask.
3. Once available: the D4 owner decisions on Safe Harbor and artifact ownership, plus the drafted
   WISP and retention-policy documents.
4. The D5 working position as a one-paragraph policy-confirmation ask (lower legal complexity than
   D1/D4).
5. Flag explicitly: **all dates and rule text in the ADR (the 2026-04-22 compliance date, the
   biometric-identifier definition, the AI-training consent requirement) entered from secondary
   sources and are marked in the ADR itself as needing re-confirmation against the Federal Register
   during this review.** Counsel should verify these independently rather than take the ADR's word
   for them, this is the ADR's own stated caveat, not new work invented for this handoff.

## 4. Definition of done (per the ADR's own Validation checklist)

- [ ] D1-D5 closed with counsel; ADR status flipped from `Proposed` to `Accepted` with the closed
      choices recorded in place.
- [ ] Amended-COPPA-Rule facts re-confirmed against the actual Federal Register text.
- [ ] The Phase 7 `P7-08` checklist maps one-to-one to the ADR's "already decided" list and the newly
      closed decisions.
- [ ] Deletion E2E (family erasure including Apple token revocation) and the kid-context-SDK audit
      both pass before any public submission, these are gated on this ADR closing, not on Phase 7
      generally.

## 5. Why this matters now, not later

This is a genuinely long-lead item (external counsel scheduling, review turnaround) sitting on the
critical path to Phase 7 and the public rungs (R2/R3). It does not block R1 (full)/M5.1, the ADR is
explicitly public-tier-facing, but every week it isn't started is a week added to the R2/R3
timeline regardless of how fast the engineering side moves. Start the engagement in parallel with,
not after, the R1-completion work in the sibling handoffs.
