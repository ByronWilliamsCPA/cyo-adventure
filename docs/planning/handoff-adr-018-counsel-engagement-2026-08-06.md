---
purpose: What ADR-018 (children's-privacy compliance) needs from outside counsel, narrowed to the
  specific open questions so engaging counsel is a scoped ask rather than "review this ADR"
component: docs/planning/adr/adr-018-childrens-privacy-compliance.md, docs/compliance/
source: R1-completion review session, 2026-08-06
---

# Handoff: ADR-018 counsel engagement

Written 2026-08-06. This is item 3 of a four-item R1-completion review. The other three items were
carried as their own pull requests and register rows rather than as sibling handoff documents, so
there is nothing to cross-read: the R1 live E2E sign-off is
[#640](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/640) and the OG1/OG7 owner decisions
are [#642](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/642).

> **Status: partly superseded by the same commit that adds this file.** This document records the
> state at the *start* of the 2026-08-06 session and was written to drive the owner rulings that
> session then produced. Where it says a decision is still needed on D2, D4, or D5, that ask has
> since been answered and recorded in ADR-018; the paragraphs below are corrected inline and note
> what changed. **ADR-018 governs wherever the two disagree.** What survives unchanged is the
> engagement framing: what to send counsel, in what order, and why.

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
account-id logged server-side) and it's already implemented (`POST /api/v1/onboarding`'s `consent`
payload, `GuardianConsentPage.tsx`, gated via `api/profiles.py::_require_consent`). **The ADR itself
names the single highest-risk open question**: whether a typed-name or canvas signature captured
this way satisfies COPPA Rule 312.5(b)(2)(i)'s "signed" requirement for the "sign and submit
electronically" consent method. That's the question to put in front of counsel first, it's already
drafted as a yes/no with supporting detail in the ADR's D1 section, not an open-ended design
question.

### D2: Audience classification: **owner decision now recorded; counsel confirms it**

When this handoff was written, D2 was the one item with no recorded owner decision, only a
recommendation ("confirm child-directed as the declared posture, matching product reality;
mixed-audience defenses are unavailable"), and the ask here was to get the owner to affirm it
before sending anything to counsel. **That ask is closed:** ADR-018 D2 now records "Decision
confirmed 2026-08-06 (owner choice; pending counsel confirmation)," child-directed as the declared
posture with mixed-audience "actual knowledge" defenses recorded as unavailable. Counsel's role on
this item is confirmation, not selection.

### D3: Launch geography: **confirmed, low-risk counsel check**

Owner confirmed US-only launch 2026-07-20 (no UK/EEA users exist or are planned; GDPR-K/AADC
shelved as a later expansion gate, not worked now). This is the lowest-risk item to clear with
counsel, it's a straightforward "confirm GDPR-K/AADC don't bind at a US-only launch" question.

### D4: Public artifacts: **owner sign-off recorded; one artifact still a draft**

Two things were needed before this became counsel-ready, and **both are now decided**:
1. Owner sign-off that the artifact list (privacy notice, App Store nutrition labels, retention
   schedule, breach/incident-response plan) are Phase 7 deliverables checked off at P7-08, and who
   drafts the notice. **Recorded 2026-08-06: Phase 7 deliverables with P7-08 as the checkpoint, and
   the project owner drafts every artifact while counsel reviews rather than drafts.**
2. A decision on **Safe Harbor program membership** (PRIVO, kidSAFE, ESRB Privacy Certified), added
   2026-08-01. This handoff argued for deciding it *before* sending D1 to counsel, on the reasoning
   that a Safe Harbor program would answer D1's signature-question with a presumption-of-compliance
   posture and ongoing external audit instead of a one-off legal opinion. **The owner decided the
   opposite ordering on 2026-08-06: alongside, counsel first.** Counsel scheduling is the long-lead
   item on the critical path to Phase 7 and a Safe Harbor evaluation is not, so D1 goes to counsel
   now and the evaluation proceeds in parallel as a Track 2 task. The accepted cost is that a later
   decision to join a program could supersede the D1 opinion, which is why the engagement flags that
   possibility to counsel explicitly and asks them to scope the D1 opinion accordingly.

   **Still open under D4:** the retention policy is drafted but `status: draft`, and three data
   classes (consent evidence, product analytics, application logs) carry no deletion window yet.
   The rule wants a hard timeline per class, so D4 is not discharged until those rulings land and
   the document is published. Tracked at `UW-N07`.
3. Two artifacts the amended COPPA Rule now makes mandatory rather than best-practice: a **written**
   Information Security Program (annual risk assessment, vulnerability-testing cadence, vendor due
   diligence, a designated compliance owner) and a **published, written** data-retention policy with
   a hard deletion timeline per data class. Most of the WISP's substance already exists as tooling
   (the scanner suite, dependency scanning, container scanning), what's missing is the document
   that names it, its cadence, and its owner. This can be drafted internally before counsel sees it.

### D5: AI-training consent segregation: **owner confirmation now recorded, counsel-light**

Added 2026-08-01 in response to the amended COPPA Rule (training/developing AI models on a child's
personal information now requires its own separate, unbundled, opt-in verifiable consent). Working
position: build any training/eval corpus exclusively from adult-originated and pipeline-originated
material (reviewer decisions, moderation findings, PII-gate-passed generated prose); exclude
child-typed wish text, flags, ratings, and reading state entirely. Under this constraint the
segregated-consent obligation never triggers, **and it costs nothing today because no planned corpus
needs child-originated data.** **The owner confirmed this as the standing constraint on 2026-08-06**
(it is mostly a policy decision, not a legal one), so this item goes to counsel as a confirmation
rather than an open question. If a future corpus ever wants child-originated data, the
ADR already prices the fallback (a `policy_version` bump plus an independent, default-off
consent-toggle, built *before* collection, not after).

## 3. What to actually hand counsel

Do not send the whole ADR as a first document. Package these together for an efficient engagement:

1. The ADR's D1 section (already-drafted mechanism plus the named 312.5(b)(2)(i) question).
2. The confirmed D3 answer (US-only launch) as a one-line confirmation ask.
3. The D4 owner decisions on Safe Harbor sequencing and artifact ownership (both recorded
   2026-08-06), plus the WISP and the retention policy. Send the WISP as finished work and the
   retention policy as a draft, naming the three classes whose deletion window is still unset so
   counsel is not asked to review a gap as though it were a position.
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
not after, the rest of the R1-completion work.
