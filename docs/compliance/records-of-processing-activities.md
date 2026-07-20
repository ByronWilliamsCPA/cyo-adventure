# Records of Processing Activities (GDPR Article 30)

Status: living document. Owner: Byron Williams (byronawilliams@gmail.com). Last reviewed:
2026-07-20.

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
| 1 | Guardian account registration and authentication | Let a guardian create and access a family account | Email, Supabase-issued auth identity, role, `is_admin` flag | Guardian, Admin | Contract (providing the service) | Supabase (identity provider, ADR-009) | Life of the account; erased on `DELETE /api/v1/me/family` (Phase 3b) |
| 2 | Child profile creation and management | Let a guardian set up a reading profile for each child | Display name, age band, reading-level cap, avatar (closed vocabulary, not a photo), content-flag caps, banned themes, TTS preference, PIN (hashed) | Child (via guardian) | Contract, performed by the guardian on the child's behalf (Article 8 framing, Section 9) | None external; internal only | Life of the profile; erased on `DELETE /api/v1/profiles/{id}` (Phase 3b) |
| 3 | Story request intake and generation | Turn a guardian- or child-initiated story wish into a personalized storybook | Request text (screened for PII before use; blocked rows redact `request_text` at the API layer), age band, length, narrative style, generated story prose | Child (subject of the story), Guardian (requester) | Contract / legitimate interest (open — see `gdpr-compliance-review.md` Pressure Point P-3 on the moderation-pipeline leg specifically) | OpenRouter and downstream model providers, Anthropic (direct), Google Gemini (cover art) — all PII-guarded as of #304 | Generated stories: life of the account; blocked/declined raw request text: 30 days from decision (remediation plan Section 5's retention table, accepted 2026-07-20) |
| 4 | Content moderation and safety review | Screen generated story content for safety before a guardian can approve it for a child | Generated story prose, moderation classifier verdicts and scores | Child (subject of the story) | Legitimate interest / legal obligation (child-safety) — basis not formally recorded (Phase 2) | OpenAI Moderation, Google Perspective (Stage-0 classifiers; PII-guarded as of #304) | Moderation reports: 1-2 years (remediation plan Section 5's retention table, accepted 2026-07-20) |
| 5 | Reading, completion, and rating tracking | Let a child resume a story and let a guardian see reading progress | Current node, save state, path, completion records, ratings | Child | Contract | None external | Life of the profile; erased with profile deletion (Phase 3a cascade) |
| 6 | Storybook assignment | Let a guardian assign a published storybook to a specific child profile | Assignment record (profile id, storybook id, timestamp) | Child | Contract | None external | Life of the profile; erased with profile deletion (Phase 3a cascade) |
| 7 | Cross-family recommendation sharing ("three-ring" social boundary, ADR-016) | Let a guardian share or receive book recommendations with a connected family | Family connection role/status; no child-identifying data crosses the boundary by design | Guardian | Consent (Article 6(1)(a)) — recorded per-side as `FamilyConnection.consented_by_viewer_user_id`/`_at` and `consented_by_sharer_user_id`/`_at`, captured via the live guardian-facing `/guardian/connections` UI; nothing crosses until both are set (`gdpr-compliance-review.md` G-10, corrected 2026-07-20) | None external | Life of the connection; erased via family deletion cascade (Phase 3a) |
| 8 | Cover art generation | Generate AI cover art for a published storybook | Cover-art prompt (PII-guarded as of #304), generated image | Child (subject of the story) | Contract | Google Gemini ("nano banana") for generation; Cloudflare R2 for storage (private, presigned-URL access only as of Phase 1d) | Life of the storybook version |
| 9 | Admin platform operations and audit logging | Let an admin manage users/profiles across families, moderate content, and maintain an accountability trail | Every mutation and (as of Phase 8a) the one cross-family read (`profile_viewed`) as a `pipeline_event` row: actor, entity, event type, closed-vocabulary payload only (never free text, per `events/writer.py`'s allowlist, spec D3) | Guardian, Child, Admin (as actors or referenced entities) | Legal obligation / legitimate interest (accountability, COPPA 312.8/312.10, GDPR Article 5(2)) | None external | No fixed purge; retained under the Article 17(3) balancing justification in `coppa-gdpr-remediation-plan.md`'s "4d artifact" section |
| 10 | Error monitoring and observability | Detect and diagnose application errors | Error telemetry, correlation IDs; hardcoded to exclude child-linked PII by design (`docs/planning/privacy-model.md`) | All (incidentally, if an error occurs during their request) | Legitimate interest (service reliability) | Sentry | Per Sentry's platform retention (not independently confirmed; tracked as a DPA/oversight item in `information-security-program.md` Section 4) |
| 11 | Onboarding and device-authorized child access | Bind a pending admin-created invite to a real login on first sign-in; authorize a child's device for kid-mode access | Invite email/role, device grant record (`authorized_by`, timestamps) | Guardian, Admin, Child (via device grant) | Contract | Supabase (auth) | Life of the account/grant |

## 4. Categories of recipients (consolidated)

Every processor named in Section 3, consolidated here to match `information-security-program.md`
Section 4's oversight table (same list, same status column — see that document for the live
DPA/SCC execution status rather than duplicating it here):

Supabase, OpenRouter (+ downstream model providers), Anthropic (direct), OpenAI Moderation,
Google Perspective, Google Gemini, Cloudflare R2, Sentry.

No recipient outside this list receives personal data as of this writing. No data is sold or
disclosed for the recipient's own independent marketing purposes.

## 5. International transfers

Every processor above is US-hosted; the Supabase project itself runs in a US region
(`gdpr-compliance-review.md` Section "All current users are US", already-resolved per that
document). For any data subject located in the EEA/UK, this makes every recipient in Section 4 a
third-country transfer requiring a transfer mechanism (Standard Contractual Clauses or DPF
self-certification per processor) — this is remediation plan Phase 5's execution tracker;
**no transfer mechanism has been confirmed executed for any processor as of this writing**. This
record does not resolve that gap; it names it so the RoPA does not imply a false completeness.

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

**Status as of 2026-07-20**: Phase 2's consent-capture build and the Article 18/21 flag are now
both DONE (built, not just decided); G-10/Phase 8b (ADR-016 consent UI) was already resolved
(Section 3 activity 7 reflects this). Phase 5's DPA execution remains the one item still
genuinely open below.

- Article 6 legal basis: recorded per-activity in Section 3 above (was previously
  unrecorded, G-01).
- Verifiable parental consent mechanism: **DONE.** Signature-capture (typed full-legal-name
  attestation) layered on the OAuth login (ADR-018 D1), enforced at `POST /api/v1/profiles`
  via `User.consent_accepted_at` (G-02).
- Transfer mechanisms (SCCs/DPF): owner decided (account owner executes Phase 5 directly);
  not yet executed for any processor (G-05, Phase 5a).
- Articles 18/21 (restriction, objection): **DONE.** `ChildProfile.processing_restricted_at`,
  guardian-set, blocks new story-request submission (newly surfaced by this document, not
  previously a numbered finding).
- DPO designation: resolved — not required at current scale, reassess before Track 2 public
  launch (G-11, Phase 7c).
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
| ADR-018 | Already-decided items (account-scoped deletion, family-scoped consent framing) reflected in Sections 2, 3, and 7 above. |
