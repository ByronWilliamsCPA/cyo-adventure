---
title: "Data Protection Impact Assessment (Draft for Counsel Review)"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Data Protection Impact Assessment of the shipped consent-capture and data-handling design under GDPR Article 35, drafted for counsel review as coppa-gdpr-remediation-plan.md Phase 7b."
tags:
  - compliance
  - security
  - privacy
  - legal
component: Development-Tools
source: "Deliverable for coppa-gdpr-remediation-plan.md Phase 7b, assessing the shipped design after Phase 2's consent-capture build; draft date 2026-07-20."
---

**Status: DRAFT.** Written for counsel to review and redline, not a completed, signed-off
DPIA. This is the deliverable for `coppa-gdpr-remediation-plan.md` Phase 7b, drafted *after*
Phase 2's consent-capture design was finalized and built (per Pressure Point P-2 in
`gdpr-compliance-review.md`: a DPIA should inform the consent-mechanism design, and since the
mechanism is now built, this DPIA assesses the real, shipped design rather than a proposal).
Article 35(3)(b) does not clearly mandate a DPIA here (no confirmed "large scale" systematic
monitoring at current scale — see `information-security-program.md`'s scale note), but the
data category (children's information) and the novel-method question flagged in ADR-018 D1
both weigh toward doing one anyway, consistent with this project's "compliant from the start"
posture.

**Draft date: 2026-07-20.**

---

## 1. Description of the processing

### 1.1 Nature, scope, context, and purposes

CYO Adventure is a choose-your-own-adventure reading app for children. A guardian creates an
account, sets up one or more child profiles, and either requests stories directly or lets
their child submit story ideas for guardian approval. Approved requests are turned into
personalized, illustrated stories by an LLM generation pipeline, screened by a deterministic
safety gate and human review before any child sees them. See
`records-of-processing-activities.md` Section 3 for the full itemized list of processing
activities (11 activities); this DPIA does not re-enumerate them, only assesses the risk they
carry collectively.

**Scale**: small, homelab-first deployment as of this writing (`information-security-program.md`
Section 3). A Track 2 public App Store launch is planned but not yet scheduled.

**Data subjects**: guardians (adults), children (via their guardian, never directly), and
admins/system actors incidentally (Section 2 of the RoPA).

### 1.2 Necessity and proportionality

- **Data minimization is the core design choice, not an afterthought.** A child is
  represented by a display name (a nickname, not a legal name), a coarse age band (one of six
  bands, not a birthdate or exact age), a reading-level cap, and a closed-vocabulary avatar
  (a fixed illustration set, never a photo). No email, phone, birthdate, exact age, photo, or
  geolocation is ever collected from a child. This is the single strongest mitigating factor
  in this assessment: most of the risk categories below are structurally narrowed before any
  technical control is even applied.
- **No advertising or behavioral-analytics SDKs** exist anywhere in the child-facing surface,
  by permanent design decision (not a configuration that could silently be turned on).
- **Purpose limitation is enforced by the pipeline shape, not just policy.** A story request's
  text is used only to generate that child's story; it is not aggregated, profiled, or reused
  for any other purpose. Cross-family sharing (recommendations) carries only book
  titles/ratings/first names, never reading content or a child's identifying data, and only
  after explicit dual-guardian consent (Section 2.3 below).
- **Real tenancy auth** (guardian-scoped, family-scoped, profile-scoped authorization checks
  on every endpoint) means one family's data is never reachable from another family's session,
  narrowing the blast radius of any single account compromise to one family, not the whole
  user base.

## 2. Risk assessment

Each risk is rated Low/Medium/High reflecting residual risk *after* the mitigations already
built, not the theoretical risk of the activity in the abstract; this DPIA is assessing the
shipped system, not a blank-slate proposal.

### 2.1 Third-party disclosure of a child's free-text story ideas (Medium, mitigated from High)

**Risk**: a child's own typed story wish, or a guardian's request text, is sent to external
LLM and moderation providers (OpenRouter/downstream models, Anthropic, OpenAI Moderation,
Google Perspective) as part of generating and safety-screening the story. Free text is the
one place a child could type something identifying (their own name, a friend's name, a home
detail) that structured fields (display name, age band) never expose.

**Mitigation**: `assert_prompt_pii_safe` (the PII egress guard) screens every prompt for
email-, phone-, and street-address-shaped content and for registered child names before it
reaches any external provider, covering both the generation leg and, as of #304, the
cover-art and Stage-0 classifier legs that were previously unguarded. A blocked hit routes to
a `blocked` status with no external call.

**Residual risk**: the guard is pattern-based, not semantic. It reliably catches
"look-like-PII" shapes (an email address, a phone number, an exact registered name) but
cannot catch a child describing something identifying in prose that doesn't match those
patterns (e.g., "my mom drives a red Honda and picks me up at Lincoln Elementary"). This gap
is already recorded as `gdpr-compliance-review.md` finding G-13 (special-category-data risk
in free text) and is not resolved by this DPIA; it is a known, accepted residual risk at
current scale, revisit before Track 2 launch.

### 2.2 Verifiable parental consent method is novel, not FTC-enumerated (High)

> **Severity raised from Medium to High on 2026-08-08**, and the premise below was corrected
> the same day. Both changes follow from reading 16 CFR 312.5(b)(2) directly and from adverse
> authority found in the Future of Privacy Forum's June 2023 VPC white paper. See ADR-018 D1.

**Risk**: the VPC mechanism (a typed full-legal-name attestation layered on the guardian's
OAuth login) is not one of COPPA's enumerated methods (312.5(b)(2)). An earlier version of
this entry said it "is designed to satisfy the 'sign and submit electronically' method
((b)(2)(i))"; **that method does not exist**. Method (i) is a return channel: a form signed
away from the service and returned by mail, fax, or electronic scan. The open question is
therefore broader than originally recorded. It is not whether our signature is good enough,
it is whether we are using an enumerated method **at all**.

The fallback argument, that the flow satisfies the general standard at 312.5(b)(1), now has
adverse authority sitting on it. In January 2015 the FTC declined to approve AgeCheq Inc.'s
"Device-Signed Parental Consent Form," noting that the 2013 Rule **specifically excluded
digital signatures** from the enumerated methods because a digital signature alone is not a
reliable means of obtaining consent, and that the method failed (b)(1) because a child in the
household could intercept the code binding the signature to an adult. Our mechanism has the
same shape, with a weaker signature artifact (a typed name) and a binding step (an
authenticated Google session on a shared family tablet) that is plausibly easier for a child
to reach than an intercepted text message.

If the reading is wrong, every consent recorded under it is defective, which could mean every
child profile created since launch was created without valid VPC.

**Mitigation**: **changed 2026-08-09.** This was the top item in the counsel engagement. The
owner ruled that the approach as built meets the requirement and withdrew it from the engagement
(`counsel-engagement-brief.md` Sections 1.0, 1.3, 6). It is now carried as an **accepted
exception** at assurance-register row **O-122**, with the AgeCheq authority above recorded as the
residual risk, compensating controls named, and an expiry at R2. An acceptance changes who carries
this risk, not how large it is; the severity below is unchanged and deliberately so. Two things
limit the blast radius:

- **The consent record survives a change of method.** Typed name, timestamp, IP, policy
  version, residence country, and adulthood attestation, all tied to the authenticated OAuth
  identity, are required under every candidate method. Only the verification step is in
  doubt, so a stronger method layers in additively rather than forcing a redesign.
- **A prior-approval route is not required.** Per the same FPF source, an operator may rely
  on an unenumerated method meeting 312.5(b)(1) without FTC approval; the 312.5(b)(3) Safe
  Harbor route buys certainty, not permission. This is risk reduction, not authorisation.

**Update 2026-08-10**: the additive layering the first bullet anticipated is now built. A Kids Web
Services adult check gates child-profile creation ahead of the consent capture, wired on staging
against the vendor's Test environment and switched off in production. It does not close this
section, and this DPIA makes no claim that it does: the vendor's own documentation states that its
Parent Verification service is not itself a COPPA consent mechanism, the consent artifact is still
the typed name, and a Test-environment verification is not evidence of anything (O-123). What the
gate *does* create is a new processor disclosure, assessed separately at **2.8**.

One further owner ruling the same day, recorded here so this section is not read as more settled
than it is: 312.5(b)(2)(ii)'s notification limb is **accepted as satisfied** on the reading that the
$0.05 capture and its 8-13 business day refund post as two discrete statement entries, and the
question is withdrawn from counsel. The structural limb was answered by observation; this limb was
not, and could not be, because the Test environment produces no real notification by construction.
**The residual risk of this section stays High.** An owner reading of rule text taken without
counsel review is a decision about who carries the risk, not a reduction of it. Full acceptance
record, with basis, compensating controls, and expiry: assurance-register row O-122.

**Residual risk**: **High, and now accepted rather than pending.** It stays High: the 2026-08-09
owner ruling withdrew the question from counsel, which removes the route by which the risk would
have been resolved, not the risk. This remains the single highest-priority open item this DPIA
surfaces. Neither mitigation reaches the core exposure: consent cannot be obtained retroactively
for collection that has already happened, so if the method is in fact defective, re-consenting
the existing population is the remedy and the prior collection stays defective. Two live counsel
questions could still retire the exception rather than defend it, and both are cheaper than
re-consenting later: `counsel-engagement-brief.md` Section 1.6 (whether a separate signature step
is required at all) and Question 1B (whether "email plus" at 312.5(b)(2)(viii) is open to us).
Tracked at assurance-register row O-122; expiry R2.

### 2.3 Cross-family disclosure without adequate control (Low, resolved)

**Risk**: a guardian's family's reading/rating data could be disclosed to another family
without a proper legal basis or adequate consent.

**Mitigation**: dual-guardian, explicit, revocable consent per connection
(`FamilyConnection.consented_by_viewer_user_id`/`_at` and `consented_by_sharer_user_id`/`_at`,
paired and DB-enforced), surfaced through a real guardian-facing UI
(`ConnectionsPage.tsx`). Nothing crosses until both sides click "Allow." This was previously
misdocumented as unbuilt (`gdpr-compliance-review.md` G-10, corrected 2026-07-20) — it is, in
fact, one of the stronger controls in the system.

**Residual risk**: Low. The default state is opt-in (no data flows on connection creation
alone), satisfying Article 25's default-privacy expectation for this specific activity.

### 2.4 Admin over-access to child-linked data across families (Low, mitigated)

**Risk**: an admin can view any family's child profiles for moderation/support purposes,
creating a potential over-access surface.

**Mitigation**: admin-only gate on every cross-family read; as of Phase 8a, every such read
(`GET /api/v1/admin/profiles`) is itself logged as a `profile_viewed` audit event (one per
call, not one per row, so the log cannot become a second copy of the data it audits),
queryable via `GET /api/v1/admin/audit`.

**Residual risk**: Low. Access is necessary for the product's safety-review model (a human
must review generated content before a child sees it) and is now fully auditable.

### 2.5 Indefinite retention of the accountability log (Low, documented exception)

**Risk**: `pipeline_event` rows survive a guardian's erasure request, which could look like an
Article 17 violation absent justification.

**Mitigation**: the Article 17(3)(b)/(e) balancing test in
`coppa-gdpr-remediation-plan.md`'s "4d artifact" section, combined with the payload being
PII-scrubbed by contract (`events/writer.py`'s allowlist), not by policy promise.

**Residual risk**: Low, provided the documented justification holds up to counsel review (not
yet independently confirmed by counsel, same caveat as elsewhere in this document).

### 2.6 Self-signup account creation without vetting (Low, newly mitigated)

**Risk**: a guardian self-signup flow (as opposed to admin-invited) that immediately
activates the account has no human check on who is creating child profiles.

**Mitigation**: added mid-session (2026-07-20), a self-signup guardian's account starts
`awaiting_approval`, not `active`; every endpoint (including `GET /v1/me`) is rejected until
an admin approves. This is an access-control measure, not itself a GDPR/COPPA requirement, but
it materially reduces the risk of an unvetted account creating child profiles at all.

**Residual risk**: Low. The approval step is currently manual with no defined SLA; if signup
volume grows, an unstaffed approval queue could become a usability problem (not a privacy
risk) worth revisiting operationally.

### 2.7 Retention windows enforced late or inconsistently (Low, mitigated)

**Risk**: data retained past its stated window (raw declined story text, stale reading
activity) if no enforcement mechanism exists.

**Mitigation**: Phase 4c's two pg_cron purge jobs (blocked/declined `request_text`, and
stale-deactivated-profile `reading_state`/`completion`/`rating`) enforce the accepted
retention table server-side, not just as a stated policy.

**Residual risk**: Low. `generation_job.report`'s purge (ADR-007) predates this DPIA; both new
jobs mirror its idempotent, pg_cron-optional design.

### 2.8 A guardian's email is disclosed to a new processor before, and regardless of, any outcome (Medium)

> Added 2026-08-10, when the KWS adult-check gate was built. Wired on the staging tier against
> the vendor's Test environment only; switched off in production. Assessed now rather than at
> switch-on, because the disclosure is inherent to the design and does not become assessable
> later.

**Risk**: to establish that an account holder is an adult, we send their email address to Kids
Web Services, operated by Epic Games. Three properties make this different in kind from the
other processor disclosures in 2.1:

- **The disclosure happens at the start of the check, not on success.** An adult whose check is
  refused, who abandons it, or who never creates a child profile has still had their address
  disclosed. There is no ordering that confirms an adult without disclosing first.
- **It reaches people who never become users.** Every other processor in the RoPA receives data
  about someone who is already a customer. This one receives data about applicants, including
  rejected ones.
- **It is a new processor with no executed DPA.** `processor-dpa-checklist.md` carries an Epic
  row, added alongside this section, but that row records no DPA requested, no DPA reviewed, and
  no transfer mechanism nameable while the counterparty entity is unresolved. The gap is the
  agreement, not the tracking: the processor-only claim asserted for every vendor in
  `privacy-notice.md` is, for this vendor, currently unbacked.

**Mitigation**: the disclosure is minimised at the point of design rather than by policy. The
outbound body carries the adult's email, the country they picked, a language tag, and an opaque
reference number, and nothing else; `assert_prompt_pii_safe` is not involved because no child
data is in scope to screen. The `kws_verification` table has **no** email column under any name,
enforced by a source-text guard, so the address is transmitted and then not retained by us. The
vendor tells us only confirmed or refused, never the method used, so we do not receive payment
or identity artifacts back. Anti-automation limits (an open-attempt refusal plus an hourly cap)
bound how many addresses one account can cause to be disclosed, which also blocks the obvious
abuse of the endpoint as an unmetered mailer.

**Residual risk**: **Medium, and unresolved on three fronts.** (a) No DPA is executed, so the
Article 28 basis for this transfer does not currently exist on paper. (b) Epic operates KWS from
both US and EU entities and we have not established which receives our traffic, so neither the
"all processors are US-based" statement in the privacy notice nor any transfer mechanism covers
this row. (c) Whether the disclosure needs surfacing to the guardian *before* they trigger the
send, rather than only in the notice, is a live question. All three are carried as `[COUNSEL: ...]`
brackets in `privacy-notice.md`'s processor section. **This risk must be resolved before the
production flag is switched on**, not before Track 2: unlike 2.1 and 2.2, switching it on is a
discrete, reversible act entirely under our control, so there is no reason to accept it in the
meantime. Tracked at assurance-register row **O-125**, added with this assessment. O-123 and
O-124 are switch-on preconditions for the same feature but are not substitutes for it: they ask
whether the *evidence* a verification produces is sound (which vendor environment, which permitted
methods), while this one asks whether the *disclosure* that produces the evidence is lawful at all.

## 3. Consultation

No formal consultation with data subjects (guardians) has been performed for this DPIA draft;
at this deployment scale, the controller and the primary user base substantially overlap
(homelab-first, small user count). [COUNSEL: advise whether a formal consultation step is
expected before this DPIA can be considered complete, given the scale caveat above.]

## 4. Overall conclusion (draft)

The processing is proportionate to its stated purpose, with data minimization doing most of
the structural risk-reduction work. Three items carry genuine residual risk, and they do not
share a deadline. **2.1** (semantic PII gap in free text, G-13) and **2.2** (the VPC method,
now an accepted exception rather than an open question) should be resolved before Track 2
public launch increases scale. **2.8** (disclosing a guardian's email to a new processor with
no executed DPA) has an earlier and firmer trigger: it must be resolved before the production
KWS flag is switched on, which is a discrete act under our own control rather than a
scale-driven horizon. Everything else assessed here is Low residual risk given the mitigations
already shipped.

[COUNSEL: this conclusion is a draft synthesis, not a sign-off. Please review each section,
resolve the bracketed items, and record your own conclusion before this DPIA is treated as
complete for Article 35 purposes.]

## 5. Relationship to other compliance documents

| Document | Relationship |
|---|---|
| `records-of-processing-activities.md` | Source for Section 1.1's activity inventory. |
| `information-security-program.md` | Source for Section 1.1's scale statement and the general security-measures inventory this DPIA's mitigations draw from. |
| `coppa-gdpr-remediation-plan.md` | Phase 7b, whose completion this document is; Section 2's items map to specific remediation-plan phases/findings as cited inline. |
| `privacy-notice.md` | The guardian-facing document describing the same processing this DPIA assesses internally; both carry the same `[COUNSEL: ...]` flag on the VPC method question (2.2), and the processor-table brackets added for the KWS disclosure are the guardian-facing face of Section 2.8. |
| ADR-018 | D1's VPC decision is the direct subject of Section 2.2, and the KWS gate built under it is the subject of Section 2.8. |
| `docs/security/assurance-register.md` | Rows O-122 (VPC method, accepted exception) and O-125 (KWS processor disclosure, added with Section 2.8) are where these risks are tracked to closure; O-123 and O-124 are the adjacent switch-on preconditions. |
| `processor-dpa-checklist.md` | Carries the Epic/KWS row added with Section 2.8; that row's unexecuted DPA and undetermined counterparty entity are the first of Section 2.8's three unresolved fronts. |
