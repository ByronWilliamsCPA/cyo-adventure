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
> **Amended**: 2026-08-08 (three corrections against primary rule text, and two requirements this
> ADR had recorded as satisfied when they were not. Corrected: D1's "sign and submit
> electronically" premise, D1's payment-card rejection, and D5's statement of the AI-training
> obligation. Added: D6 data inventory and processing map, D7 the security program as a
> continuing obligation, and a Sources and references section that splits primary authority from
> practitioner commentary.)
> **Amended**: 2026-08-08, later the same day, after reading the Future of Privacy Forum's June 2023
> VPC white paper. Adverse authority added to D1 (the FTC's 2015 AgeCheq denial, which reaches the
> 312.5(b)(1) fallback and not only the enumerated-method question); the 312.5(b)(3) framing in D1
> and D4 corrected from authorisation to risk reduction; new D8 recording the internal-operations
> exception at 312.5(c)(7) as a route to a consent-free free tier; new D9 scoping California
> SB 976, whose core provisions take effect 2027-01-01 and whose VPC framework incorporates
> COPPA's approved-method list, so D1's answer propagates into state law.
> **Amended**: 2026-08-09. D1 gains the engineering half of the KWS evaluation: the integration is
> built and deployed to staging against the KWS **Test** environment, with nothing wired in
> production. It records the two mechanisms that now enforce D1's "configuration is the evidence"
> constraint, why only the webhook leg may write consent state, why the Test/Production partition
> has no runtime backstop, and the three questions the Test environment exists to answer.
> **This chooses nothing**: KWS versus a direct Stripe integration is still open, and the accepted
> risks are unchanged.
> **Amended**: 2026-08-09, later the same day. **Owner ruling on D1's enumerated-method
> question.** The owner reviewed the corrected framing and the AgeCheq adverse authority and
> ruled the shipped typed-name mechanism adequate, withdrawing brief Questions 1C and 1D from
> the counsel engagement. Nothing in D1's analysis is retracted; the risk is reassigned, not
> reduced. It is carried as an accepted exception at assurance-register row O-122, expiring at
> R2. Questions 1A and 1B remain live counsel asks, so D1 is narrowed, not closed.
> **This does not flip the status.** Every decision below is an owner choice pending counsel
> confirmation; only counsel closing D1 through D5 moves this ADR to Accepted. D1's remaining
> counsel content is Questions 1A and 1B; its enumerated-method half is now an owner-accepted
> risk rather than a pending answer. **D6 and D7 are
> owner-side obligations rather than counsel questions**, and are deliberately excluded from the
> counsel engagement. **D8 rides on Question 1A as a sub-question** rather than becoming a sixth.
> The engagement stays scoped at five questions.
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
D6 and D7, added 2026-08-08, are owner-side obligations rather than counsel questions: a
complete data inventory with a purpose and a provenance per element, and the security program
treated as a continuing obligation with evidence rather than as a document that exists. D8, added
the same day, records the one route that does not require solving D1: the internal-operations
exception at 312.5(c)(7) would make a free tier that cannot request stories consent-free and
notice-free, which is the tiering design the owner proposed early on and the project shelved before
anyone noticed it had a legal basis.

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
16 CFR 312.5(a)(2) requires a separate, unbundled verifiable parental consent for
**disclosing** children's personal information to third parties where that disclosure is not
integral to the requested service, with AI training discussed as an example of such a
disclosure (D5 below, as corrected 2026-08-08); operators must maintain a
written Information Security Program and a published written data-retention policy with
hard deletion timelines (D4 and the new D7 below).

**Citation status, updated 2026-08-08.** The Federal Register document number `2025-05904` was
resolved directly against the Federal Register's public API on 2026-08-08 and corresponds to a
COPPA Rule document published at **90 Fed. Reg. 16918**; that volume-and-page citation is now
recorded here as verified against a primary source rather than a secondary one. **The dates are
not.** The 2025-04-22 publication, 2025-06-23 effective, and 2026-04-22 full-compliance dates
above still entered this document from secondary sources and remain on the Validation checklist
for counsel confirmation, as does the substance of each amendment summarised above. Verifying that
a citation resolves is not the same as verifying what the cited text says, and this ADR should not
be read as claiming the latter.

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

**Adverse authority found 2026-08-08, and it is close to on-point. Read this before relying on
anything above.** The Future of Privacy Forum's June 2023 white paper *The State of Play: Is
Verifiable Parental Consent Fit For Purpose?* describes the FTC's January 2015 conclusion of its
review of AgeCheq Inc.'s second proposed VPC method, a "Device-Signed Parental Consent Form." The
Commission declined to approve it, and two elements of the reasoning apply to what we shipped:

- The Commission noted that **in the 2013 Rule digital signatures were specifically excluded from
  the enumerated methods, because a digital signature alone is not a reliable means of obtaining
  consent**, and that AgeCheq's device-signing step did not "add indicia of reliability to the
  digital signature." This is independent support for the correction above: the absence of an
  in-app signature method is deliberate, not an omission we are reading into the text.
- The method failed the general standard at 312.5(b)(1) because a child in the household could
  intercept the SMS code that bound the signature to an adult. **Our mechanism has the same shape**:
  a signature artifact (weaker than AgeCheq's, being a typed name) bound to an adult by a second
  step (an authenticated Google session, which on a shared family tablet is plausibly easier for a
  child to reach than an intercepted text message).

**Consequence for this decision.** The D1 risk is larger than this ADR has recorded. It is not only
that we are probably outside 312.5(b)(2); the fallback argument, that the flow satisfies 312.5(b)(1)
on general reasonableness, has adverse authority sitting directly on it. Nobody here has read the
Commission's decision; this entry is sourced from FPF's description and quotation of it. The primary
documents are *FTC Concludes Review of AgeCheq's Second Proposed COPPA Verifiable Parental Consent
Method* (January 29, 2015) and *AgeCheq Inc.'s Application Pursuant to Section 312.12(a)...*
(October 1, 2014). **Read the decision before treating this entry as settled**, and note that FPF
predates the 2025 amendments.

**Correction to the 312.5(b)(3) framing above, same date.** The sentence above says Safe Harbor
approval "may be the route by which the shipped implementation becomes usable rather than replaced."
That implies approval is a precondition to relying on a non-enumerated method. Per the same FPF
source, it is not: an operator may rely on an unenumerated method meeting 312.5(b)(1) without prior
approval, and the approval route buys certainty rather than permission. FPF also records that no
operator has submitted a VPC method for FTC approval since 2015. The accurate framing is **risk
reduction, not authorisation**, and the live question is how much risk the current flow carries,
which the AgeCheq material above suggests is more than previously assumed.

**Owner ruling, 2026-08-09: risk accepted, question withdrawn from counsel.** Having read the
corrected rule-text framing and the AgeCheq adverse authority above, the owner ruled that the
mechanism as built meets the requirement, and withdrew brief Questions 1C and 1D from the counsel
engagement. Three things this ruling is not:

- **It is not a retraction.** Every paragraph above stands as written, including the finding that
  312.5(b)(2)(i) has no in-app-signature method and that AgeCheq reaches the 312.5(b)(1) fallback
  rather than only the enumerated list. Editing the analysis to agree with the decision would
  falsify the record of what was known on the date the decision was made.
- **It is not a reduction in the risk.** An acceptance reassigns who carries a risk; it does not
  shrink it. `dpia.md` keeps this item at residual risk **High** for exactly that reason, and the
  withdrawal removes the route by which the risk would have been resolved, not the risk itself.
- **It is not a gap in the gate.** `api/profiles.py::_require_consent` and
  `api/admin_profiles.py::_require_family_consent` are unchanged, so no child profile can be
  created without a consent record. What is accepted is the *quality* of that consent evidence,
  never its *absence*.

Recorded as an accepted exception at `docs/security/assurance-register.md` row **O-122**, with
compensating controls and an expiry at R2. Two routes could retire it early rather than defend it:
the Safe Harbor evaluation in D4, and the KWS vendor path below, which reaches an enumerated method
at (b)(2)(ii) without our building card handling. Questions 1A and 1B remain live counsel asks, so
D1 is narrowed, not closed.

**Rule text re-verified 2026-08-09, and every correction above survives.** The 2026-08-08 readings
were taken once; they have now been checked again against the current text via eCFR's renderer API
(the section's HTML page is bot-blocked and redirects, so a future check should use the API
endpoint, not the page). The amended Rule's full compliance date, 2026-04-22, has passed, so this
text binds. Confirmed: (b)(2)(i) still reads "postal mail, facsimile, or electronic scan" with no
in-app signature method; (b)(2)(ii) reads "in connection with a transaction" with *monetary* gone,
and retains the verbatim second limb requiring the card "provide notification of each discrete
transaction to the primary account holder". Newly established: the list runs (i) through **(ix)**,
and (ix) is a **text-message method** paired with (viii) email-plus, both conditioned on an operator
that does not "disclose" **as defined at § 312.2**, whose internal-operations carve-out is a closed
enumerated list with a no-other-purpose limb. Full analysis and what it means for the vendor
characterisation is at assurance-register row O-122.

**The payment-card rejection above is withdrawn (2026-08-08), and the reason it was made no longer
exists.** The 2026-07-20 decision ruled out a payment-card transaction partly on PCI scope and
partly because the app is not monetized, treating a payment-based consent method as something that
would force a monetization decision the owner had not made. Reading 16 CFR 312.5(b)(2)(ii) directly
on 2026-08-08, the method requires a card or online payment system used "in connection with a
transaction" that notifies the primary account holder of each discrete transaction; there is no
requirement that the transaction be **monetary**, and the word "monetary" appears to have been
removed from this provision by the 2025 amendments. If that reading holds, a zero-charge card
verification qualifies, the "we are not monetized" half of the rejection was never a valid
objection, and the paid-tier/free-tier framing that the 2026-07-20 entry says is "superseded" was
being superseded for the wrong reason. The PCI half is also weaker than recorded, since a hosted
payment page keeps card data out of our systems. **Consequence for this decision: (b)(2)(ii) is
back on the table as a candidate enumerated method and may be the cheapest one available**, which
matters precisely because the chosen mechanism's own enumerated status is now in doubt. This is put
to counsel at `counsel-engagement-brief.md` Section 1.4. Nothing here reopens the separate,
still-valid objection to coupling consent to a future product-pricing decision; it observes that
the objection no longer forces a choice, because no charge is required.

**Vendor evaluated for the (b)(2)(ii) route: Epic's Kids Web Services (KWS), 2026-08-08. Two
risks identified and accepted by the owner; the route itself is not yet chosen.** With
(b)(2)(ii) reopened above, the question became whether to reach it through a VPC vendor or
directly. KWS was evaluated because it is free, self-serve, operated by an entity under a
20-year FTC assessment regime, and therefore under more outside scrutiny than its price
suggests. Findings, separated by how well each is sourced:

- **The method, for a US parent, is a zero-charge payment-card verification performed by
  Stripe** (documented, KWS developer docs). That maps to 312.5(b)(2)(ii) on the reading
  recorded above. A Social Security Number check is also offered; its mapping to (b)(2)(v)
  is less clean and it is not proposed for use.
- **An AgeGraph hit skips the verification step entirely** (primary, observed by the owner in
  the KWS Developer Portal on 2026-08-08). The portal states: "If a parent email is stored in
  the KWS AgeGraph, they are considered pre-verified as an adult and won't need to provide
  this information again." This behaviour appears on no public documentation page; the
  developer docs describe a flow with no such branch. It means a parent already verified with
  any other KWS-enabled service may be verified here **by inheritance**, under a method we did
  not choose, at a time we cannot observe, against a standard we cannot inspect. Note that
  AgeGraph is keyed on hashed parent email rather than location, so the US-only geographic
  restrictions on other methods never engage to prevent this.
- **KWS is an independent controller of AgeGraph data, not solely our processor** (documented,
  KWS terms clause 5). It reuses the parent email hash to serve its other customers. This is
  the structural reason no opt-out exists: the cross-service graph is the product, not a
  feature layered on it.
- **The callback does not report which method ran** (documented). Combined with the AgeGraph
  branch, we cannot evidence *how* any given parent was verified.
- **KWS disclaims liability for the operator's COPPA compliance** (documented). Using it
  transfers no legal exposure.

**Risks accepted by the owner, 2026-08-08**, on the stated reasoning that the approach is
adequate for the web app and that for the iOS app the verification requirement shifts to Apple:
(a) verification may be inherited from AgeGraph rather than performed, and (b) we cannot prove
which method ran for a given parent. This is a recorded owner decision taken with the portal
text above in hand, not an oversight.

**The iOS half is a new and separate claim, and it is not the same question.** The
app-store accountability statutes now in force in several US states place age-assurance and
parental-consent duties on the app store, and Apple exposes a declared-age-range signal. That
is app-store-level age assurance. COPPA's 312.5 obligation sits on the **operator** collecting
the information, and an app store obtaining consent for a download is not self-evidently
parental consent for our collection. Whether Apple's mechanism discharges an operator's VPC
obligation has not been researched here and is not answered by anything in this ADR. It is
recorded as a distinct open question rather than folded into the accepted risks above, because
if the answer is no, the iOS surface has no VPC at all, which is a larger exposure than either
accepted risk.

**Consequence for the consent record, which is a design constraint rather than a legal one.**
Because the method is not reported, a verification record must not claim one. The stored method
is the vendor and the flow (`kws_pv`), never `card`, and it is accompanied by a snapshot of the
method configuration in force at that moment. The sentence that snapshot supports is "verified
via KWS Parent Verification, with only payment-card methods enabled for US locations at the
time," which is true. "Verified by credit card" would be an assertion the callback never made.
When a vendor will not report which mechanism ran, the operator's own versioned configuration
becomes the compliance evidence, which is why the configuration must be captured per
verification rather than assumed stable.

**The alternative this evaluation surfaced: integrate Stripe directly.** KWS's US card method
*is* Stripe. Going direct costs an integration but buys method certainty (we know what ran),
first-party evidence (the charge record is ours), a plain processor relationship with no
independent-controller reuse layer and no privacy-notice complication, and no dependency on a
free tier that can be withdrawn. This is a live option, not a rejected one, and the choice
between them is recorded here as still open.

**Sourcing caveat.** A deep-research report was commissioned on KWS and informed this entry, but
its inline citations resolve to internal search-tool tokens rather than URLs, so no claim in it
traces to a page and it is treated as a lead rather than authority. The AgeGraph finding above
does not depend on it: it comes from the owner's own screenshots of the portal.

**~~Flagged for counsel~~, withdrawn 2026-08-09; now an accepted exception**: whether a
typed-name attestation captured inside our own application is an enumerated 312.5(b)(2) method
**at all** was the single highest-risk open question in this decision, and it is a broader
question than the "is our signature good enough" one this ADR originally posed. The owner ruled
the mechanism adequate and withdrew it from the engagement (see the Owner ruling above); it is
carried at assurance-register row O-122 rather than answered. **It remains the highest-risk item
in this decision after the ruling as it was before it**, which is what an acceptance means. The
DPIA and Privacy Notice drafts still go to counsel on their own merits, and the Privacy Notice
paragraph describing this flow must not acquire a claim about which method applies.

**Implemented 2026-07-20.** `POST /api/v1/onboarding`'s `consent` payload
(`accepted`/`policy_version`/`signer_name`) persists onto
`User.consent_accepted_at`/`consent_policy_version`/`consent_signer_name`/`consent_ip`
(paired, CHECK-enforced); `api/profiles.py::_require_consent` gates
`POST /api/v1/profiles` on it. Frontend: `GuardianConsentPage.tsx`, reached automatically via
a new `AuthStatus = 'needs-consent'`. This is the engineering half of D1; the flagged
counsel-review question above is unchanged by implementation. **Superseded 2026-08-09**: that
question no longer needs an answer before this ADR can flip to Accepted, because it was
withdrawn from the engagement and accepted as a risk (O-122). What still gates Accepted is
counsel closing Questions 1A and 1B, plus D2 through D5.

**Gate hole found and closed 2026-08-08.** The implementation above covered only the
guardian-facing create path. `POST /api/v1/admin/profiles`
(`api/admin_profiles.py::create_admin_profile`, WS-J) is a second child-data collection point
and enforced no consent requirement at all, so an admin could create a child profile in a
family that had never consented; a test reproduced this before the fix and got a `201`. It is
now gated by that module's own `_require_family_consent`. The two gates deliberately ask
different questions: the guardian-facing one reads the **caller's** consent record, correct
because the caller is the child's parent, while the admin one reads the **target family's**,
correct because the caller is not. Any non-`child` row in the target family satisfies it, not
only `role='guardian'`, since an adult holding the `admin` base role can still be the parent
of their own family and a guardian-only test would lock such a family out while adding no
protection. Note what this gap was and was not: it is an enforcement gap under
16 CFR 312.5(a)(1), which binds regardless of **which** VPC method D1 lands on, so it was
fixable without waiting on counsel and is independent of everything else in this decision.
**Verified**: `tests/integration/test_admin_profiles_api.py::
test_admin_create_requires_target_family_consent` (negative) and
`::test_admin_create_allowed_when_target_family_has_consented` (positive).

**Related, newly decided the same day, not itself part of D1**: a guardian self-signup
admin-approval gate. An uninvited guardian's own first-login JIT provisioning now starts
`User.status='awaiting_approval'` instead of `active`; `api/deps.py::require_principal`
already rejects every endpoint for a non-`active` status, so this alone is the enforcement
mechanism. An admin approves (`-> active`) or denies (`-> deactivated`) via the existing
`PATCH /admin/users/{id}`. This is a parallel, non-overlapping track to the admin-invite
`pending` status already in this ADR's "already decided" list; an admin-invited guardian is
still trusted immediately on bind, unaffected by this gate. Frontend:
`GuardianAwaitingApprovalPage.tsx`, reached via a new `AuthStatus = 'awaiting-approval'`.

**Built and deployed to staging 2026-08-09, against the KWS *Test* environment. This gathers
evidence for D1; it does not close it.** Everything above was decided from vendor documentation
and portal text. The owner's direction was to determine the vendor's actual behaviour empirically
rather than wait on Epic, so the integration now exists and runs: `consent/kws_client.py` (the
send leg, OAuth2 client-credentials), `consent/service.py`
(`start_parent_verification` / `record_parent_verified`), `api/kws_webhook.py` (the
`parent-verified` delivery), `api/kws_redirect.py` (the parent's browser returning from Epic's
hosted flow), and a `kws_verification` table (migration `20260809130000`). **Nothing is wired in
production**: `services/cyo-adventure/docker-compose.yml` in homelab-infra carries no `KWS_*`
variables, so the integration is off there by configuration rather than by code.

*What this does not settle.* It does not choose the route. KWS versus a direct Stripe integration
remains open exactly as recorded above; building against Test is what makes that comparison
decidable on observed behaviour instead of on documentation. It does not touch the flagged
counsel question (withdrawn and accepted later the same day, see the Owner ruling above; a
Test-environment verification would not have satisfied it in any case), and it converts neither
accepted risk into a mitigated one.

**The "configuration is the evidence" constraint now has a mechanism rather than an intention.**
The consent-record paragraph above requires the stored method to be the vendor and the flow,
accompanied by a snapshot of the method configuration in force at that moment. Two things now
enforce that:

- `kws_verification.enabled_methods` stores `settings.kws_enabled_methods` **as it stood at send
  time**, never a live read, so a later configuration change cannot retroactively rewrite what a
  past verification claims about itself.
- The application **refuses to start** when KWS credentials are present and
  `KWS_ENABLED_METHODS` is empty
  (`core/config.py::_require_declared_kws_methods_when_configured`). Because the callback reports
  no method, that declaration is the only bound on how a parent was verified, so an operator
  cannot silently run the integration without one. This is not hypothetical: it refused to boot
  the staging stack on first activation, which is a control behaving as intended rather than a
  defect.

**Only one of the three legs writes consent state, and the asymmetry is structural.** The
`parent-verified` webhook is signed Stripe-style (`t=` / `v1=`) over the raw body with a bounded
clock skew, and it alone resolves a `kws_verification` row. The redirect return is signed over
`f"{status}:{external_payload}"`, which carries **no timestamp and no nonce and is therefore
replayable by construction**, so that route is display-only and writes nothing. A consent record
that could be created by replaying a URL a parent once received would not be a consent record.

**The Test/Production partition is recorded per verification and has no runtime backstop.** Each
row stores its own `kws_environment`, because KWS reports nothing that would let the environment
be re-derived afterwards. The application's guard against production KWS credentials fires only
when its own `ENVIRONMENT` is `local`, and every deployed tier declares `production`, so **no
deployed environment can catch a misconfiguration here**. A verification performed against Epic's
Test environment is not a valid VPC, so Test credentials must never be present in the production
stack. This is an operational control resting on the operator, not an enforced one.

*Live state, 2026-08-09.* Both routes answer on staging. The webhook leg verifies signatures
(an unsigned request is rejected `401`); the redirect leg awaits its Control Panel secret.

**What the Test environment now exists to answer**, ordered by how much each would change D1:

1. **Does `parent-verified` fire at all on the pre-verified AgeGraph path?** If it does not, an
   inherited verification produces no delivery and therefore no consent record, which would
   restate accepted risk (a) from "verified under a method we did not choose" into "no record
   was created at all". That is a materially worse finding than the one the owner accepted.
2. **Does the card method capture-and-refund, or authorise only?** This bears directly on the
   312.5(b)(2)(ii) mapping recorded above.
3. **Is the webhook signature carried in a header or in the query string?** The API reference and
   the Control Panel copy disagree; `api/kws_webhook.py` records the open question as an
   `#ASSUME` marker rather than resolving it silently.

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

  **Corrected later the same day.** "Making the existing implementation lawful" is wrong, for the
  reason recorded at the end of D1: approval under 312.5(b)(3) is not a precondition to relying on
  a non-enumerated method, so the implementation is not waiting on a program's blessing to be
  lawful. A Safe Harbor program sells **certainty about a judgment we are already making and
  already carrying the risk of**, which is a real product but a different one. Two facts sharpen
  the evaluation rather than changing its sequencing: the AgeCheq material in D1 suggests the risk
  being carried is larger than assumed, which raises what certainty is worth; and no operator has
  submitted a VPC method for FTC approval since 2015, which suggests the direct-to-FTC route under
  312.12 is cold and a program is the practical channel. Also note, from the same source, that the
  FTC has previously removed an organisation from the approved safe harbor list, so membership is
  not a permanent shield and the choice of program matters.

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

**Correction, 2026-08-08: the sentence above overstates the rule, and it should not be relied on
as written.** It was drafted from secondary practitioner commentary, not from the rule text, and
the commentary's framing is broader than what the text supports. Reading 16 CFR 312.5(a)(2)
directly, the separate-consent obligation is anchored to **disclosure to third parties** that is
not integral to the service the child requested. AI training appears in the Commission's
explanatory material as a worked example of such a non-integral disclosure, rather than as a
free-standing rule reaching every first-party use of children's data for model development. The
practical difference matters to this project: on the narrow reading, D5 is a constraint about
**who we send data to**, which puts it in the same family as the counterparty list in "already
decided" item 6; on the broad reading it is additionally a constraint about **what we do in
house**. Whether an operator training its own model, in house, on data it already lawfully
collected falls inside the provision at all is not something this ADR should assert in either
direction.

**Why the decision below is unaffected.** The corpus constraint recorded in this decision excludes
child-originated data from every training and evaluation set, which satisfies the broad reading and
the narrow one at the same time. The correction therefore changes what this ADR *claims about the
law*, not what the project *does*, and no engineering work is reopened by it. The reason to fix it
anyway is that a future decision to relax the constraint would be priced against the wrong rule,
and because this ADR is an input to the counsel engagement, where an overstated premise costs
billable time to unwind. The question is put to counsel at `counsel-engagement-brief.md`
Section 2.3, and the underlying claim is already on the Validation checklist below as a
secondary-sourced fact needing Federal Register confirmation.

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

**Scope limit on that confirmation: the constraint is first-party only.** The corpus constraint
governs corpora **this company builds and controls**. It says nothing about what a third party
does with child-originated text after we send it, and the classifier leg does send such text: a
child's free-text wish goes to OpenAI's moderation endpoint and Google's Perspective API (see
"already decided" item 6, classifier leg). **We have not verified either vendor's retention,
model-training, or onward-use terms for that traffic.** So D5 should not be read as closed on a
first-party "no child data in any training set at all" premise. What is established is narrower:
no child-originated data enters a corpus we control. Whether any enters a corpus a *vendor*
controls is unresolved, sits on the same vendor due-diligence obligation D7 names, and is asked of
counsel in the brief's Section 2.3 as a third question rather than assumed away.

### D6: A complete data inventory and processing map (added 2026-08-08)

**These two decisions, D6 and D7, are owner-side obligations, not counsel questions.** The counsel
engagement brief scopes itself to five questions and must stay at five; **neither D6 nor D7 is
added to that list.** They are recorded here because both are requirements this ADR was
treating as satisfied by documents that do not actually satisfy them.

**One qualification, because the boundary is not as clean as "excluded" suggests.** Documents that
D6 and D7 are *about* do appear in the brief, and that is deliberate rather than an inconsistency:

- D6's two named documents, `processor-dpa-checklist.md` and
  `records-of-processing-activities.md`, are in the brief's Section 5 because **Question 1B** turns
  on how each third-party recipient is characterised under the Rule. Counsel is being asked to
  characterise the recipients, not to rule on whether our inventory is complete. Completeness is
  the D6 obligation and stays with the owner.
- D7's subject document, `information-security-program.md`, is in the brief's Section 3 because
  counsel reviews it as a drafted artifact. Counsel is not being asked whether the program is
  *being run*, which is the D7 obligation and likewise stays with the owner.

The distinction to hold onto is that counsel reviews these documents as **text**; whether the
practice behind the text exists is the owner-side question, and that is exactly the gap D6 and D7
were written to name.

**The requirement.** A single authoritative map of every data element the system holds, recording
for each one: what it is, **from whom it is collected** (the child directly, the guardian about the
child, staff, or the generation pipeline), **why it is collected** (the specific product function
that needs it), who it is disclosed to, how long it is kept, and how it is deleted. The "from whom"
and "why" columns are the load-bearing ones and are the ones currently missing.

**Why this is a requirement and not documentation hygiene.** Four separate obligations take this map
as their input, and none of them can be discharged correctly without it:

- **16 CFR 312.4(d)**, the content of the notice published on the service, is a description of what
  is collected and why.
- **16 CFR 312.4(b) and (c)**, the direct notice to the parent, has its own content list. This ADR
  had not distinguished it from the published notice at all; the gap is recorded in
  `counsel-engagement-brief.md` Section 3.
- **16 CFR 312.10**, the retention obligation, requires a business need and a deletion timeline per
  class of children's data. D4 already records that three classes carry no window (`UW-N07`). A
  window cannot be justified without a stated purpose, so the missing "why" column is upstream of
  that residual rather than a separate problem.
- **The Rule's necessity limit**, which bars conditioning a child's participation on collecting more
  personal information than is reasonably necessary to participate, is unassessable per element
  until each element has a stated purpose. Today we could not answer "why do we hold this?" for
  every field from any single document.

**Why the existing documents do not already do this.** Four documents each hold part of it and no
document reconciles them: `privacy-model.md` holds the child-linked data classification,
`records-of-processing-activities.md` holds a per-activity view, `data-retention-policy.md` holds
per-category windows, and `processor-dpa-checklist.md` holds counterparties. They are separately
maintained, and nothing checks that they agree with each other or with the schema. The specific
column no document has is provenance: whether a given element was collected **from the child** or
**from the guardian about the child**. That distinction is not cosmetic. It is what Question 1A in
the counsel brief turns on, because information an operator collects from a parent is treated
differently from information collected online from a child, and most of what this product holds
about a child is guardian-entered.

**Decision needed:** owner confirms the map is a P7-08 deliverable and names the single document
that owns it (extending `records-of-processing-activities.md` is the cheapest option, since it is
already per-activity and already lists recipients).

**Generated, not hand-maintained: this leg is decided rather than open.** An earlier draft left
"generated from the ORM models or maintained by hand" as an owner decision while the Validation
checklist below already required reconciliation against the ORM models "rather than maintained by
hand." That presented an option the gate made impossible. Resolving it in favour of the gate: the
inventory is **generated from the ORM models**, and a hand-maintained inventory is not an
acceptable form of this deliverable. The reason is the one that made it preferable in the first
place: a hand-maintained inventory drifts from the schema silently, and this ADR already carries
one instance of exactly that failure in D4's three windowless classes. What remains open for the
owner is the host document, not the mechanism.

### D7: The Information Security Program as a continuing obligation (added 2026-08-08)

**The requirement.** 16 CFR 312.8 places a substantive, continuing security obligation on the
operator: reasonable procedures to protect the confidentiality, security, and integrity of
children's personal information, including due diligence over the service providers that receive
it. The amended rule's addition is that the program be **written**.

**What this ADR currently gets wrong about it.** D4 lists the written Information Security Program
as one of the "public artifacts," alongside the privacy notice and the retention policy, and
records it as complete because the document exists. Two problems follow from that placement:

1. **It is not a public artifact.** The retention policy is published because the Rule requires the
   retention practice to appear in the online notice. The security program is an internal document.
   Filing them under one heading invites publishing something that describes our controls to
   anyone who asks, which is a security decision nobody has actually made. D4's list should be read
   as "artifacts counsel reviews," not "artifacts we publish," and the two are different sets.
2. **A document is not a program.** `information-security-program.md` names an annual
   risk-assessment cadence, a vulnerability-testing cadence, vendor due diligence, and an owner.
   D4 records those four elements as present, which they are, **as text**. Nothing in this
   repository records that any of those cadences has run. An obligation discharged by writing that
   we will do something annually is not discharged until the year's instance exists and is
   evidenced.

**A concrete instance, stated precisely, because an earlier draft of this section overstated it.**
The service-provider set changed materially on 2026-07-28: enabling zero-data-retention for the
frontier vendors moved generation traffic onto **AWS Bedrock, Microsoft Azure, and Google Vertex**
as OpenRouter sub-processors (see "already decided" item 6). An earlier draft asserted that the
security program's vendor due-diligence section *predates* that change and therefore describes a
counterparty list that is no longer the counterparty list. **That is not true, and the correction
is worth recording because it is the same restated-without-checking failure mode this ADR exists to
fix.** Both registers were updated the same day, in the same commit series:
[information-security-program.md](../../compliance/information-security-program.md) names the three
sub-processors and stamps the guardrail `(2026-07-28)`, and
[processor-dpa-checklist.md](../../compliance/processor-dpa-checklist.md) gained a dedicated row
for each of Bedrock, Azure, and Vertex on the same date.

**The residual is real but different, and it is the point D7 is actually making.** Updating the
register is not the same act as performing diligence. The three new rows each carry their own open
item on their face: confirm that OpenRouter's terms name and bind its sub-processors, and that ZDR
routing actually holds at that endpoint. Nothing in this repository records that anyone has
assessed those counterparties, only that they were written down. So the failure mode a
written-but-unexercised program produces is present here in its exact form: the paperwork tracked
the change and the diligence did not. That still argues for treating a vendor-set change as a
trigger that re-runs diligence rather than as a documentation update, but the trigger fired
correctly on the documentation leg, and it is the assessment leg that is outstanding.

**Decision needed:** owner confirms (a) that the security program is tracked as a continuing
obligation with dated evidence per cadence rather than as a completed artifact, (b) whether it is
internal or published, and (c) that a change to the service-provider set is itself a trigger for
re-running vendor diligence. Item (c) has a live instance waiting on it: the 2026-07-28
sub-processor rows are recorded but not assessed.

### D8: The internal-operations exception and a consent-free free tier (added 2026-08-08)

**This reopens a design the project set aside, and it reopens it on a legal basis rather than a
product one.** Early in the ADR-018 work the owner proposed tiering the product: a free tier that
cannot request stories and keeps data on the device, and a paid or otherwise consent-gated tier that
unlocks story requests and cross-device sync. The idea was set aside as an unattractive amount of
engineering, since eight tables key to `child_profile_id` and `api/reading.py::_require_assignment`
gates reads on a server-side assignment row. What nobody checked at the time was whether the design
had a specific legal payoff. It appears to.

**The exception.** 16 CFR 312.5(c)(7) excepts from the prior-consent requirement an operator that
collects **a persistent identifier and no other personal information** and uses that identifier
**only** to support the internal operations of the service. Per the Future of Privacy Forum's
June 2023 white paper, the exception also carries **no notice obligation**, and "support for internal
operations" is read broadly: analysing site functioning, authenticating users, personalising content,
statistical reporting and analytics, debugging, and similar. The same source gives saving a game
score or achievement level as an example of permitted personalisation.

**Why the free tier fits and the current product does not.** The disqualifying words are "and no
other personal information." As built, a child types a free-text story wish that we store against a
profile, which is other personal information under 312.2 and breaks the exception. **Remove story
requests and that data disappears**, leaving a session identifier used for authentication and
progress personalisation. On that reading a free tier requires neither VPC nor notice. The owner's
original "cannot request stories" restriction turns out to be precisely the condition the exception
needs, arrived at by product intuition before anyone knew why it was the right line.

**One likely relaxation of the original design.** The original proposal kept all free-tier data on
the device. If saving reading position is personalisation within the exception, the free tier could
sync progress across a family's devices and still qualify, which is a materially better product than
device-locked reading and removes much of the engineering objection that shelved the idea.

**Why this matters strategically, stated bluntly.** D1 is in trouble. The AgeCheq material recorded
there suggests the shipped consent mechanism is probably outside the enumerated methods and that its
312.5(b)(1) fallback has adverse authority on it. D8 is the only option on the table that does not
require solving D1 at all: it makes a whole tier of the product consent-free rather than
consent-compliant. That does not rescue story requests, which remain the feature that forces VPC,
but it decouples a usable free product from an unresolved legal question, and it is worth pricing
against the cost of retrofitting an enumerated method.

**Sourcing and its limit.** The exception's scope here is taken from a June 2023 secondary source
and therefore describes the pre-2025 Rule. The internal-operations exception is exactly the kind of
provision the 2025 amendments plausibly touched. **Nothing may be built against this entry until the
exception's current scope is confirmed against the amended text.** This is asked of counsel as a
sub-question of Question 1A in the engagement brief rather than as a sixth question; the engagement
stays scoped at five.

**Decision needed:** owner rules on whether the free tier is pursued, contingent on counsel
confirming the exception's current scope and whether reading-progress sync survives inside it.

### D9: California SB 976 and the state-law gap, made concrete (added 2026-08-08)

**This turns an abstract gap into a dated one.** The Validation checklist below records that D3's
US-only decision removes GDPR-K and the UK AADC but says nothing about US state law. California
SB 976, the *Protecting Our Kids from Social Media Addiction Act* (2024), is the first concrete
instance, and it has a near-term date attached.

**The facts, as we understand them.** The California Department of Justice is conducting a
rulemaking under Cal. Health & Safety Code section 27001(b). A notice of proposed rulemaking
published 2026-05-15 and comments closed 2026-06-30. **Core provisions take effect 2027-01-01.**
The statute prohibits providing an "addictive feed" to a minor without either a reasonable
determination that the user is an adult or verifiable parental consent, and the proposed
regulations set a performance-based age-assurance framework that **rejects age declaration as a
standalone solution** while permitting layered approaches.

**Threshold question, and our tentative answer is probably "out of scope."** SB 976 targets
addictive feeds and the services built around them. This product has no user-generated content, no
social graph, no messaging (ADR-016's contact boundary), no advertising, and no infinite feed; a
child reads books a guardian assigned. On that description we do not believe we are a covered
service. **We are recording this as an open question rather than a conclusion**, because the
product does expose a recommendations surface (`api/recommendations`), and because the source we
have does not address whether non-social services such as reading or educational apps fall inside
the definition. The cost of being wrong is a statute with a 2027-01-01 date, so the check is worth
making rather than assuming.

**Two findings that matter even if we are out of scope.**

1. **D1's answer propagates into state law.** The proposed California VPC framework ties acceptable
   methods to COPPA's approved list. Whatever conclusion counsel reaches about our typed-name
   mechanism under 16 CFR 312.5 is therefore not contained to COPPA; a mechanism that is not an
   approved COPPA method is unlikely to be acceptable under a state regime that incorporates that
   list by reference. This is an argument for resolving D1 properly rather than minimally.
2. **A no-account, no-purchase, no-government-ID option may be required.** We understand the
   proposal to require that operators offer at least one consent option that requires none of an
   account, a purchase, or a government-issued ID. If that survives to the final text and we are in
   scope, it would rule out the payment-card route reopened in D1, the government-ID match, and the
   face-match-to-ID method **as sole options**, leaving email plus, text message plus, the
   toll-free call, the video conference, and the mailed or scanned form. That points at the same
   place D8 and the email-plus analysis already point, which is worth noting as convergence rather
   than coincidence.

**Sourcing and its limits, which are significant here.** This entry is drawn from a Future of
Privacy Forum blog post dated 2026-07-15 describing FPF's own comments in the rulemaking. Two
cautions follow. **It is advocacy**: FPF's recommendations, such as replacing static approved-method
lists with criteria-based standards, are what FPF asked for, not what the regulations say, and this
entry should not be read as conflating them. **And the regulations are proposed, not final**: the
comment period closed six weeks ago and the final text may differ. Nothing here is settled law. One
fact from the same source is worth carrying forward independently because it updates a
2023-vintage claim to 2026: COPPA has approved only two new VPC methods since 2013, with no new
submissions since 2015.

**Decision needed:** owner rules on whether SB 976 scoping is added to the counsel engagement or
handled separately. It is **not** in the engagement today, and adding it would break the five-question
scope. Our recommendation is to keep it out of this engagement and raise it as a short follow-on
question once D1 is answered, since D1's answer is an input to it. Note also that California's
Age-Appropriate Design Code Act (AB 2273) is a separate statute with its own litigation history,
and is not covered by this entry.

## Consequences

- ✅ Compliance stops being folklore spread over four documents; Phase 7 becomes the
  implementation of this ADR and P7-08 its checklist.
- ✅ The already-decided list above is now contestable and testable (deletion E2E,
  egress-guard tests, SDK audit map to it).
- ⚠️ Until D1-D3 are closed, Phase 7 cannot be scoped precisely; this ADR staying
  Proposed is itself the tracking signal.
- ⚠️ Counsel review is a real dependency and cost; the recommendations above are
  design positions, not legal conclusions.
- ⚠️ **Added 2026-08-08.** Three claims in this ADR were restated from secondary commentary as
  though they were rule text, and two of them (D1's enumerated-method premise, D1's payment-card
  rejection) drove real engineering decisions before anyone read the provision. The Sources and
  references section below exists to make that failure mode harder to repeat, but it is a
  convention rather than a control: nothing in CI checks whether a legal claim in this repository
  is sourced. Treat every unattributed legal assertion in the compliance document set as
  unverified until it carries a primary citation.

## Validation

**Progress note, 2026-08-06.** The owner-side prerequisites are done: D2, D3, D4, and D5 all
carry recorded owner decisions, D1's mechanism is decided and implemented, and the packet
counsel receives is assembled at
[counsel-engagement-brief.md](../../compliance/counsel-engagement-brief.md). What remains on
every unchecked box below is external: retaining counsel and getting rulings. No checkbox is
ticked by internal work alone, which is why none are ticked here.

**Correction to that note, 2026-08-08: the owner-side prerequisites are not done.** The claim above
was true of D1 through D5 and remains true of them. It was wrong as a claim about the ADR as a
whole, because two obligations had been recorded as satisfied by documents that do not satisfy them
(D6, D7) and were therefore invisible to a checklist derived from the D-list. The lesson worth
keeping is that "every remaining item is external" was itself the signal to re-check, since an
internal register that reports zero internal work left is more likely to be incomplete than
finished.

- [ ] D1-D5 closed with counsel; status flipped to Accepted with the choices recorded.
- [ ] Amended-rule facts (biometric definition, AI-training consent, WISP and
      retention-policy mandates) re-confirmed against the Federal Register text during
      counsel review; they entered this ADR from secondary sources. **Scope of this box narrowed
      2026-08-08: the citation and the three dates are no longer part of it.** The 90 Fed. Reg.
      16918 citation, the 2025-04-22 publication date, the 2025-06-23 effective date, and the
      2026-04-22 general compliance date are all confirmed against the Federal Register (document
      2025-05904), as is the carve-out under which 16 CFR 312.11(d)(1), (d)(4), and (g) carry a
      different transition. What remains unconfirmed is the amendments' **content**, which is what
      this box now tracks.
- [ ] **D6**: the data inventory and processing map exists in one named document, carries a
      provenance column (collected from the child vs from the guardian) and a purpose column for
      every element, and is reconciled against the ORM models rather than maintained by hand.
- [ ] **D7**: the security program is tracked as a continuing obligation with dated evidence for
      each cadence it names, its internal-vs-published status is ruled on, and vendor diligence has
      been re-run over the service-provider set as it stands after the 2026-07-28 change (AWS
      Bedrock, Microsoft Azure, Google Vertex).
- [ ] State children's-privacy and age-appropriate-design statutes are scoped. D3 confirms a
      US-only launch, which removes GDPR-K and the UK AADC but does not remove US state law.
      **D9 makes this concrete for California SB 976, whose core provisions take effect
      2027-01-01**; the scoping question there (are we a covered service at all?) is open, and
      California's AB 2273 and other states remain entirely unscoped.
- [ ] **D8**: the current scope of the internal-operations exception at 312.5(c)(7) is confirmed
      against the amended rule text, including whether reading-progress sync survives inside it,
      before any free-tier engineering starts. The entry is sourced from a pre-amendment document.
- [ ] P7-08 checklist maps one-to-one to the "already decided" list and the closed
      decisions.
- [ ] Deletion E2E (family erasure incl. Apple revocation) and the kid-context SDK audit
      pass before submission.

## Follow-on work

Required by [the ADR README's follow-on rule](./README.md), which applies to any ADR materially
amended from 2026-07-28 onward. Note that `scripts/check_work_linkage.py` does not read
`docs/planning/adr/`, so nothing in CI enforces this section; PR review is the enforcement point.
Every item below cites a real home, and "counsel will decide" is not one: the counsel engagement is
itself scheduled work, and the items that wait on it say what they wait on.

- **D1 through D5 close with counsel.** The engagement is assembled at
  [counsel-engagement-brief.md](../../compliance/counsel-engagement-brief.md) and scheduled under
  `UW-M03` (external and owner-gated). `UW-N02` carries the VPC-method decision specifically and
  `UW-N07` the retention rulings. Nothing here is blocked on further internal sourcing; the
  remaining work on those two rows is counsel's ruling.
- **D6, the data inventory and processing map**: `UW-A50` (Phase 7, `unscheduled`). Owner-side, not
  a counsel question. The mechanism is decided in D6 above (generated from the ORM models); the
  host document is the open part.
- **D7, the security program as a continuing obligation**: `UW-A51` (Phase 7, `unscheduled`). Also
  owner-side. Carries the live instance named in D7: the three 2026-07-28 sub-processor rows are
  recorded in both registers but have not been assessed, and it carries the internal-vs-published
  ruling.
- **D8, the internal-operations exception and a consent-free free tier**: `UW-A52` (Phase 7,
  `decision`). A gate, not an implementation row. The ADR entry is sourced from a pre-amendment
  document, so the exception's current scope has to be confirmed against the amended rule text
  before any tiering engineering starts.
- **D9 and the wider US state-law gap**: `UW-A53` (Phase 7, `decision`). Covers the Validation
  checkbox on state children's-privacy and age-appropriate-design statutes, which previously
  directed work nowhere. California SB 976 is the concrete instance; AB 2273 and other states are
  unscoped.
- **The amended rule's content re-confirmed against the Federal Register.** Part of the counsel
  engagement above and tracked by the Validation checkbox as narrowed on 2026-08-08. The citation
  and the three dates are confirmed and no longer part of that box; the amendments' substantive
  content is what remains.
- **P7-08 checklist maps one-to-one to this ADR.** Phase 7 in
  [roadmap.md](../roadmap.md); it is the phase this ADR is the implementation spec for, so it needs
  no separate register row.

## Sources and references

Recorded 2026-08-08. This list exists because several claims in this ADR entered it from
secondary commentary and were restated as if they were rule text, twice with material
consequences (see the D1 and D5 corrections above). The split below is the point of the section:
**a claim sourced from the primary column can be relied on here; a claim sourced from the
secondary column is a lead, and belongs in this ADR only with its provenance attached.**

### Primary sources

| Source | What it is authoritative for | Retrieval note |
|---|---|---|
| [16 CFR 312.5, Parental consent](https://www.law.cornell.edu/cfr/text/16/312.5) (Cornell Legal Information Institute) | The enumerated VPC methods at (b)(2), the general standard at (b)(1), the safe-harbor approval route at (b)(3), and the prior-consent exceptions at (c). | Cornell is an unofficial reproduction. It was used on 2026-08-08 because `ecfr.gov` redirected automated retrieval and `ftc.gov` returned HTTP 403. **Counsel should confirm against the eCFR or the printed CFR**, not against this copy. |
| [Federal Register doc. 2025-05904](https://www.federalregister.gov/d/2025-05904), COPPA Rule amendments, 90 Fed. Reg. 16918 | The 2025 amendments themselves: what changed, the Commission's stated reasoning, and the Statement of Basis and Purpose. | The document number was resolved against the Federal Register public API on 2026-08-08, which is how the 90 Fed. Reg. 16918 citation was confirmed. The API returns metadata; **the text of the amendments has not been read in full by anyone on this project.** |
| [Apple Developer: Kids Apps](https://developer.apple.com/app-store/kids-apps/) | Platform requirements for the Kids Category, which is the basis of D2's child-directed declaration. | Authoritative for Apple's rules, which are contractual rather than legal. Apple's requirements are stricter than COPPA in places; satisfying one does not satisfy the other. |
| FTC, *FTC Concludes Review of AgeCheq's Second Proposed COPPA Verifiable Parental Consent Method* (January 29, 2015), and *AgeCheq Inc.'s Application Pursuant to Section 312.12(a)...* (October 1, 2014) | The Commission's reasoning on why a digital signature plus a device-binding step fails 312.5(b)(1), and its statement that digital signatures were deliberately excluded from the enumerated methods. **The single most important authority for D1.** | **Cited, not read.** Surfaced via the FPF paper below and quoted from it. URLs are omitted deliberately: `ftc.gov` returned HTTP 403 to automated retrieval on 2026-08-08, so the links are unverifiable from here and would risk the link-check gate. Retrieve manually or via counsel. |

### Secondary sources (practitioner commentary; leads, not authority)

These are useful for spotting what changed and what practitioners think it means. None should be
cited in this ADR as a statement of the rule.

- **[Future of Privacy Forum, *The State of Play: Is Verifiable Parental Consent Fit For Purpose?*](https://fpf.org/wp-content/uploads/2023/06/FPF-VPC-White-Paper-06-02-23-final2.pdf)**
  (June 2023). **The most productive source this project has used, and the only secondary source
  here that changed conclusions rather than confirming them.** It supplied the AgeCheq authority in
  D1, the internal-operations analysis in D8, the correction that 312.5(b)(3) approval is optional,
  and independent confirmation that method (i) is a physical form returned by mail, fax, or scan.
  It is a research paper from a privacy think tank rather than vendor or client-alert content, and
  it footnotes the FTC's own published decisions, which is what makes it usable as a lead
  generator. **Its hard limit: it is dated June 2023 and describes the 2013 Rule throughout.** Every
  claim taken from it needs checking against the amended text, and D8 in particular must not be
  built against until that check happens.
- **[FPF, *FPF Submits Comments to Inform California Children's Social Media Protections Rulemaking Process*](https://fpf.org/blog/fpf-submits-comments-to-inform-california-childrens-social-media-protections-rulemaking-process/)**
  (2026-07-15). The source for D9. **Read it as advocacy**: it describes FPF's own comments in the
  SB 976 rulemaking, so its recommendations are asks rather than rule text, and the regulations it
  discusses are proposed rather than final. Useful for two things independent of that: the
  2027-01-01 effective date, and the current state of the COPPA approval channel (two new methods
  since 2013, no submissions since 2015), which updates the same claim from the 2023 white paper
  above.
- **Vendor marketing on "building a COPPA-compliant learning platform"** (Intellivon, reviewed
  2026-08-08). **Recorded as rejected, not as a reference.** It carries no citation to any part of
  16 CFR Part 312, lists "signed consent forms" as a method without the return channel that
  constitutes method (i), and presents consent vendors as if they were themselves enumerated
  methods. Both errors are the same shape as the ones this ADR has already had to correct, which is
  why it is named here: someone will find it again, and this entry is cheaper than re-litigating it.

- **"FTC's COPPA Rule changes include AI training consent requirement"** (Data Protection Report).
  **Read this entry together with the D5 correction above.** This ADR's original D5 framing, that AI
  training requires its own separate consent as a category of use, matches this article's headline
  proposition and does not match what 16 CFR 312.5(a)(2) says, which is anchored to third-party
  disclosure. This is the clearest example in the project of a secondary source's framing being
  absorbed as rule text, and it is kept in this list for that reason rather than despite it.
- **"New COPPA Obligations for AI Technologies Collecting Data from Children"** (Akin).
- **"Children's Online Privacy in 2025: The Amended COPPA Rule"** (Loeb & Loeb).
- **"State Kids' Privacy Laws: 2025 Review and 2026 Outlook"** (Keller and Heckman). **Relevant to a
  gap in D3.** D3 confirms a US-only launch and treats that as removing the geography question by
  putting GDPR-K and the UK AADC out of scope. It does not follow that no sub-national law applies:
  a US-only launch is exactly the posture in which state children's-privacy and age-appropriate-design
  statutes bind. This ADR records no decision on them. That is an open gap, not a settled scope
  boundary, and it is not currently in the counsel engagement.
- **"Children's Privacy Mid-Year Update 2026"** (Mayer Brown).

URLs are omitted for the five commentary items above because they were supplied by title and have
not been resolved from this repository; add a URL only after fetching it, since an unresolved link
would fail the link-check gate and, more importantly, an invented one would repeat the sourcing
failure this section exists to prevent.

## Related

- [Capability register](../capability-register.md): S10, G11, G12, K14, A14.
- [Privacy model](../privacy-model.md): classification, counterparties, Blocker 1.
- [PROJECT-PLAN.md](../PROJECT-PLAN.md): Phase 7.
