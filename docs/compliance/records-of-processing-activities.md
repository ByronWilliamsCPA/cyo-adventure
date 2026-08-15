---
title: "Records of Processing Activities (GDPR Article 30)"
schema_type: planning
status: published
owner: core-maintainer
purpose: "Article 30(1)/(2) Records of Processing Activities synthesizing existing compliance material into the single record required of a controller."
tags:
  - compliance
  - privacy
  - legal
component: Development-Tools
source: "Synthesis of coppa-compliance-audit.md, gdpr-compliance-review.md, docs/planning/privacy-model.md, docs/planning/capability-register.md, and ADR-018; last reviewed 2026-07-20."
---

Status: living document. Owner: Byron Williams (byronawilliams@gmail.com). Last reviewed:
2026-07-20; amended 2026-08-10 to add activity 12 (adult verification via Kids Web Services)
and the recipient and transfer entries that follow from it.

This is a synthesis of material already documented elsewhere (`docs/compliance/coppa-compliance-audit.md`,
`docs/compliance/gdpr-compliance-review.md`, `docs/planning/privacy-model.md`,
`docs/planning/capability-register.md`, and ADR-018), assembled into the single Article
30(1)/(2) record required of a controller (and, where CYO Adventure itself relies on
processors, the parallel Article 30(2) processor record). It resolves
`gdpr-compliance-review.md` finding G-03 and `coppa-gdpr-remediation-plan.md` Phase 7a.
**No new research was performed for this document**; where the underlying material leaves a
question open, this record says so explicitly rather than inventing an answer.

## 1. Controller identity

CYO Adventure (Byron Williams, byronawilliams@gmail.com) is the controller for all processing
described below. There is no joint controller or separate data protection officer designated
as of this writing (`gdpr-compliance-review.md` finding G-11 / remediation plan item 7c: the DPO
question is explicitly open, pending Track 2 scale projections).

## 2. Categories of data subjects

Using the same persona vocabulary as `docs/planning/capability-register.md`:

- **Guardians (G)**: the adult who registers a family, creates and manages child profiles,
  reviews and approves story requests, and is the data subject for their own account data
  (email, role, family membership).
- **Children (K)**: never a direct account holder or data-subject-rights actor in their own
  right within this product's design (ADR-018's already-decided framing; see Section 9's Article
  8 note); a child profile's data is provisioned and managed by a guardian. Treated as its own
  data-subject category because a child profile carries data (display name, age band, reading
  history) distinct from and additional to the guardian's own.
- **Admins (A)**: platform operators with cross-family access for moderation, catalog
  management, and support; their own account data (email, role) is processed the same as a
  guardian's, plus an audit trail of their administrative actions (Section 5, `pipeline_event`).
- **System (S)**: not a data subject; included here only because `pipeline_event` rows can carry
  `actor_role='system'` for automated actions (the generation worker, the moderation pipeline)
  with no associated personal data (`actor_id` is null for these rows by design, per
  `events/models.py`'s spec decision D2).

## 3. Processing activities

Each row is one purpose-grouped activity. "Legal basis" reflects the open question already
flagged as G-01/Pressure-Point-P-3 in `gdpr-compliance-review.md`: no Article 6 basis has been
formally recorded for any activity yet (remediation plan Phase 2), so this column states the
*most plausible* basis per the existing review's analysis, marked open where genuinely
undecided, rather than asserting a basis has been chosen.

| # | Activity | Purpose | Data categories | Data subjects | Legal basis (plausible / open) | Recipients | Retention |
|---|---|---|---|---|---|---|---|
| 1 | Guardian account registration and authentication | Let a guardian create and access a family account, and determine which regulatory regime applies to that account (jurisdiction and adulthood signals; O-117, O-119 in `docs/security/assurance-register.md`) | Email, Supabase-issued auth identity, role, `is_admin` flag, country of residence (`residence_country`, ISO 3166-1 alpha-2, guardian-selected, nullable), adulthood-attestation timestamp (`adulthood_attested_at`, self-declared, nullable) | Guardian, Admin | Contract (providing the service) for the core account fields; legitimate interest (determining the applicable regulatory regime, O-117/O-119) for `residence_country` and `adulthood_attested_at` | Supabase (identity provider, ADR-009) | Life of the account; erased on `DELETE /api/v1/me/family` (Phase 3b), including `residence_country` and `adulthood_attested_at` |
| 2 | Child profile creation and management | Let a guardian set up a reading profile for each child | Display name, age band, reading-level cap, avatar (closed vocabulary, not a photo), content-flag caps, banned themes, TTS preference, PIN (hashed) | Child (via guardian) | Contract, performed by the guardian on the child's behalf (Article 8 framing, Section 9) | None external; internal only | Life of the profile; erased on `DELETE /api/v1/profiles/{id}` (Phase 3b) |
| 3 | Story request intake and generation | Turn a guardian- or child-initiated story wish into a personalized storybook | Request text (screened for PII before use; blocked rows redact `request_text` at the API layer), age band, length, narrative style, generated story prose | Child (subject of the story), Guardian (requester) | Contract / legitimate interest (open; see `gdpr-compliance-review.md` Pressure Point P-3 on the moderation-pipeline leg specifically) | OpenRouter and downstream model providers, Anthropic (direct), Google Gemini (cover art), all PII-guarded as of #304 | Generated stories: life of the account; blocked/declined raw request text: 30 days from decision (remediation plan Section 5's retention table, accepted 2026-07-20) |
| 4 | Content moderation and safety review | Screen generated story content for safety before a guardian can approve it for a child | Generated story prose, moderation classifier verdicts and scores | Child (subject of the story) | Legitimate interest / legal obligation (child-safety); basis not formally recorded (Phase 2) | OpenAI Moderation, Google Perspective (Stage-0 classifiers; PII-guarded as of #304) | Moderation reports: 1-2 years (remediation plan Section 5's retention table, accepted 2026-07-20) |
| 5 | Reading, completion, and rating tracking | Let a child resume a story and let a guardian see reading progress | Current node, save state, path, completion records, ratings | Child | Contract | None external | Life of the profile; erased with profile deletion (Phase 3a cascade) |
| 6 | Storybook assignment | Let a guardian assign a published storybook to a specific child profile | Assignment record (profile id, storybook id, timestamp) | Child | Contract | None external | Life of the profile; erased with profile deletion (Phase 3a cascade) |
| 7 | Cross-family recommendation sharing ("three-ring" social boundary, ADR-016) | Let a guardian share or receive book recommendations with a connected family | Family connection role/status; no child-identifying data crosses the boundary by design | Guardian | Consent (Article 6(1)(a)), recorded per-side as `FamilyConnection.consented_by_viewer_user_id`/`_at` and `consented_by_sharer_user_id`/`_at`, captured via the live guardian-facing `/guardian/connections` UI; nothing crosses until both are set (`gdpr-compliance-review.md` G-10, corrected 2026-07-20) | None external | Life of the connection; erased via family deletion cascade (Phase 3a) |
| 8 | Cover art generation | Generate AI cover art for a published storybook | Cover-art prompt (PII-guarded as of #304), generated image | Child (subject of the story) | Contract | Google Gemini ("nano banana") for generation; Cloudflare R2 for storage (private, presigned-URL access only as of Phase 1d) | Life of the storybook version |
| 9 | Admin platform operations and audit logging | Let an admin manage users/profiles across families, moderate content, and maintain an accountability trail | Every mutation and (as of Phase 8a) the one cross-family read (`profile_viewed`) as a `pipeline_event` row: actor, entity, event type, closed-vocabulary payload only (never free text, per `events/writer.py`'s allowlist, spec D3) | Guardian, Child, Admin (as actors or referenced entities) | Legal obligation / legitimate interest (accountability, COPPA 312.8/312.10, GDPR Article 5(2)) | None external | No fixed purge; retained under the Article 17(3) balancing justification in `coppa-gdpr-remediation-plan.md`'s "4d artifact" section |
| 10 | Error monitoring and observability | Detect and diagnose application errors | Error telemetry, correlation IDs; hardcoded to exclude child-linked PII by design (`docs/planning/privacy-model.md`) | All (incidentally, if an error occurs during their request) | Legitimate interest (service reliability) | Sentry | Per Sentry's platform retention (not independently confirmed; tracked as a DPA/oversight item in `information-security-program.md` Section 4) |
| 11 | Onboarding and device-authorized child access | Bind a pending admin-created invite to a real login on first sign-in; authorize a child's device for kid-mode access | Invite email/role, device grant record (`authorized_by`, timestamps) | Guardian, Admin, Child (via device grant) | Contract | Supabase (auth) | Life of the account/grant |
| 12 | Adult verification before child-profile creation (added 2026-08-10) | Establish, through an independent service, that the person about to create a child profile is an adult, ahead of capturing that person's consent | Sent to the vendor: the adult's **email address**, the country they selected, a language tag, and an opaque reference number. Stored here: the reference number, country, timestamps, and the vendor's verdict (confirmed / refused / never answered). **No child data is sent, and no email address is stored in the verification table** (`kws_verification` has no email column, in any form) | Guardian, and adults who start a check and never become users (see the note below the table) | Legal obligation (COPPA 312.5's requirement that the consenting person be a parent); GDPR Article 6(1)(c) on the same footing as activity 1's regime-determination fields | **Epic Games (Kids Web Services)** | Verification record: life of the account. No purge job covers this table today; this states current behaviour, not a chosen retention policy (`data-retention-policy.md` has no row for it) |

**Note on activity 12's data-subject category.** Every other activity above processes data about
someone who is, or is becoming, a user. Activity 12 does not: the email address goes to the vendor
when the check *starts*, so a person whose check is refused, or who abandons it, has still had
their address disclosed. No ordering of the flow avoids this, because the vendor's job is to
contact that address. It is the only activity in this record with that property, and it is why the
DPIA assesses it separately at section 2.8 rather than folding it into the existing
processor-disclosure analysis.

**Deployment status of activity 12 (as of 2026-08-10).** Built and wired on staging against the
vendor's **Test** environment; the production feature flag is off, so no real family's address has
reached this recipient. Switching it on is gated on the open items in Section 5 and on
assurance-register row O-125.

## 4. Categories of recipients (consolidated)

Every processor named in Section 3, consolidated here to match `information-security-program.md`
Section 4's oversight table (same list, same status column; see that document for the live
DPA/SCC execution status rather than duplicating it here):

Supabase, OpenRouter (+ downstream model providers), Anthropic (direct), OpenAI Moderation,
Google Perspective, Google Gemini, Cloudflare R2, Sentry, Epic Games (Kids Web Services).

No recipient outside this list receives personal data as of this writing. No data is sold or
disclosed for the recipient's own independent marketing purposes.

Epic Games is the newest entry and the only one that is not yet live in production. It is also the
only one whose **counterparty entity is unresolved**: Epic operates Kids Web Services from both US
and EU entities, and which one would receive our traffic has not been established. That has to be
settled before the transfer analysis in Section 5 can say anything true about this recipient, which
is why it is named here as an open question rather than assumed into the "every processor is
US-hosted" sentence below.

## 5. International transfers

Every processor above is US-hosted; the Supabase project itself runs in a US region
(`gdpr-compliance-review.md` Section "All current users are US", already-resolved per that
document). For any data subject located in the EEA/UK, this makes every recipient in Section 4 a
third-country transfer requiring a transfer mechanism (Standard Contractual Clauses or DPF
self-certification per processor); this is remediation plan Phase 5's execution tracker;
**no transfer mechanism has been confirmed executed for any processor as of this writing**. This
record does not resolve that gap; it names it so the RoPA does not imply a false completeness.

**Carve-out added 2026-08-10.** "Every processor above is US-hosted" now has one exception, and it
is an exception of ignorance rather than of fact: for Epic Games (Kids Web Services, activity 12),
neither the receiving entity nor its hosting location has been established, so this record cannot
place it on either side of the line. Nothing is inferred from the vendor's US corporate identity;
Epic operates the service from more than one entity. Until that is settled, treat the Epic row as
having **no** transfer analysis rather than a US-hosted one, and do not switch the production flag
on. Tracked at assurance-register row O-125, DPIA section 2.8, and the Epic row of
`processor-dpa-checklist.md`.

## 6. Technical and organisational security measures (summary)

Full detail lives in `SECURITY.md` and `docs/compliance/information-security-program.md`;
summarized here per Article 30(1)(g)'s requirement for "a general description" within the
record itself:

- Data minimization by design: coarse age bands, no birthdate/exact age/photo/email/phone/
  geolocation collected from a child.
- A PII egress guard blocking real-child identifiers and email/phone/address-shaped content
  before any external-provider call (#304).
- Encryption in transit (TLS) everywhere; cover images served only via short-lived presigned R2
  URLs (Phase 1d).
- Authentication via Supabase-issued, cryptographically verified JWTs (RS256/ES256 only); an
  explicit algorithm allowlist prevents downgrade.
- OWASP-aligned security headers, `TrustedHostMiddleware`, and HTTPS redirect (Phase 6a).
- Dependency and static-analysis scanning (Bandit, OSV-Scanner, pip-audit, CodeQL, Dependabot,
  SonarCloud) in CI.
- A documented risk-assessment cadence and vendor-oversight process
  (`information-security-program.md`).
- A documented incident-classification and breach-notification procedure
  (`breach-notification-runbook.md`).
- An append-only, PII-scrubbed-by-contract audit log of admin mutations and (as of Phase 8a)
  cross-family reads of child-linked data.

## 7. Data subject rights implementation

| Right | Status | Mechanism |
|---|---|---|
| Access (Article 15) / Portability (Article 20) | Implemented | `GET /api/v1/me/export` (Phase 3c) |
| Erasure (Article 17) | Implemented | `DELETE /api/v1/profiles/{id}`, `DELETE /api/v1/me/family` (Phase 3b); FK cascades (Phase 3a); Article 17(3) exception documented for `pipeline_event` (Phase 4d) |
| Rectification (Article 16) | Implemented (partial) | Profile fields editable via existing guardian/admin PATCH endpoints; no separate "rectification request" workflow exists beyond direct edit, which the review has not flagged as a gap given the direct-edit affordance already covers it |
| Restriction of processing (Article 18) | **DONE (2026-07-20)** | `ChildProfile.processing_restricted_at` (guardian-set via `PATCH /api/v1/profiles/{id}`) pauses new story-request submission for that profile -- the point new data would reach a third-party LLM/classifier provider -- without deleting any existing data |
| Objection (Article 21) | **DONE**, same mechanism as Article 18 | Same flag covers the practical substance of an objection request at this scale |
| Rights related to automated decision-making (Article 22) | Not applicable | Story generation and moderation inform guardian approval; they do not themselves produce a legal or similarly significant effect on a data subject without guardian review (the mandatory-human-approval ADR is the relevant design decision) |

## 8. Open items this record surfaces

**Status as of 2026-08-10**: activity 12 (adult verification before child-profile creation) was
added to Section 3 on this date, and it brings one new open item with it. The check discloses the
**adult's own email address to Epic Games when it starts**, before any verdict, so refused and
abandoned applicants are disclosed too; there is no executed DPA behind that relationship and the
receiving Epic entity is not yet established. That is tracked as **O-125** in
`docs/security/assurance-register.md` and assessed in `dpia.md` section 2.8, and it is a
precondition of switching the gate on in production, not a follow-up to it. The gate ships behind
`KWS_VERIFICATION_REQUIRED`, which is off in production, so activity 12 describes a built path
rather than one currently processing real adults' data there.

It also does not replace the consent mechanism below. KWS establishes that the person is an adult;
the record of what was agreed to is still ours, captured by the typed-name attestation. Epic's own
documentation says the same, that the service is not designed to obtain consent or address direct
notice.

**Status as of 2026-07-20** (retained, and still accurate for the items it covers): Phase 2's
consent-capture build and the Article 18/21 flag are now both DONE (built, not just decided);
G-10/Phase 8b (ADR-016 consent UI) was already resolved (Section 3 activity 7 reflects this).
Phase 5's DPA execution remains genuinely open below, and O-125 above is a second instance of
exactly that gap rather than a separate kind of problem.

- Article 6 legal basis: a plausible basis is recorded per-activity in Section 3 above
  (was previously unrecorded, G-01); two activities (3: story generation, 4: content
  moderation) remain explicitly marked open pending counsel input on the
  moderation-pipeline leg specifically (Pressure Point P-3), not yet formally decided.
- Verifiable parental consent mechanism: **DONE.** Signature-capture (typed full-legal-name
  attestation) layered on the OAuth login (ADR-018 D1), enforced at `POST /api/v1/profiles`
  via `User.consent_accepted_at` (G-02).
- Transfer mechanisms (SCCs/DPF): owner decided (account owner executes Phase 5 directly);
  not yet executed for any processor (G-05, Phase 5a).
- Articles 18/21 (restriction, objection): **DONE.** `ChildProfile.processing_restricted_at`,
  guardian-set, blocks new story-request submission (newly surfaced by this document, not
  previously a numbered finding).
- DPO designation: resolved; not required at current scale, reassess before Track 2 public
  launch (G-11, Phase 7c).
- Newly surfaced 2026-08-10 by activity 12: a **new recipient with no executed DPA, no named
  counterparty entity, and no transfer mechanism**, receiving an adult's email address at the
  moment a check starts rather than on any success condition. Unlike every other row in Phase 5's
  DPA backlog, this one is not trailing a live integration: the production flag is off, so the gap
  is closable before any real family's data moves. Treat it as a switch-on precondition, not a
  to-do. Tracked at assurance-register row O-125 and DPIA section 2.8.
- Newly surfaced 2026-07-20, not previously tracked anywhere: a guardian self-signup
  approval gate (`User.status='awaiting_approval'`, admin approve/deny via
  `PATCH /admin/users/{id}`) -- **DONE**, added mid-session as a parallel access-control track
  alongside Phase 2's consent work, not itself a GDPR/COPPA requirement but relevant context
  for Section 2's data-subject-category note on guardians.

## 9. Relationship to other compliance documents

| Document | Relationship |
|---|---|
| `docs/compliance/coppa-compliance-audit.md` | COPPA-specific finding register this record's Section 3 data inventory draws from. |
| `docs/compliance/gdpr-compliance-review.md` | GDPR-specific finding register (G-03 resolved by this document); Pressure Points P-1 and P-3 bear directly on Sections 5 and 3 above. |
| `docs/compliance/coppa-gdpr-remediation-plan.md` | Phase 7a, whose completion this document is; Phases 2, 5, and 8b are the open items in Section 8. |
| `docs/compliance/information-security-program.md` | Section 4's vendor-oversight table is the live-status counterpart to this record's Section 4/5. |
| `docs/planning/privacy-model.md` | Source material for Section 3's data classification and Section 6's PII-guard description. |
| `docs/planning/capability-register.md` | Source for the K/G/A/S persona vocabulary used in Section 2. |
| ADR-018 | Already-decided items (account-scoped deletion, family-scoped consent framing) reflected in Sections 2, 3, and 7 above. D1 is the decision activity 12 implements. |
| `docs/compliance/dpia.md` | Section 2.8 is the risk assessment for activity 12; this record is the inventory it assesses against. |
| `docs/compliance/processor-dpa-checklist.md` | The Epic Games row is the execution tracker for activity 12's recipient; Section 5's carve-out above stays open until that row closes. |
