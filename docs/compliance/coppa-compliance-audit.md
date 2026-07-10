---
title: "COPPA Compliance Audit"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Full-scope engineering audit of CYO Adventure against the Children's Online Privacy Protection Act (COPPA, 16 CFR Part 312), mapping data practices to each Rule requirement and ranking remediation before the ADR-008 public launch."
tags:
  - compliance
  - security
component: Development-Tools
source: "Static review of src/cyo_adventure, frontend/src, migrations, and docs at commit c9dbfa9 (2026-07-10)"
---

> **Status**: Draft | **Version**: 1.0 | **Audit date**: 2026-07-10
> **Code reviewed at**: commit `c9dbfa9` on `main`
> **Scope**: `src/cyo_adventure/`, `frontend/src/`, `migrations/`, `docs/`

## 0. Important disclaimer

This is a **technical and engineering compliance audit**, not legal advice. It maps the codebase's
observable data practices to the requirements of the Children's Online Privacy Protection Act
(COPPA) and the FTC's implementing Rule (16 CFR Part 312, as amended in 2025). Determinations of
legal sufficiency, the correct verifiable-parental-consent method, and the precise text of required
notices must be made with qualified privacy counsel. Nothing here should be read as a legal opinion
or as certification of compliance.

---

## 1. Executive summary

CYO Adventure is a **child-directed** reading service (age bands `3-5`, `5-8`, `8-11`, `10-13`,
`13-16`, `16+`; see `src/cyo_adventure/storybook/models.py` `AgeBand`). COPPA governs the online
collection of personal information from children under 13. The project's own planning documents
correctly identify COPPA as a launch blocker for the public tier (`docs/planning/privacy-model.md`
lines 218-233; `docs/planning/adr/adr-008-public-app-store-launch.md` lines 56-59, 127-133) and
schedule the work as Phase 7 (`feat/phase-7-kids-compliance`, `docs/planning/PROJECT-PLAN.md`
lines 883-915). **That work is not yet implemented.**

**Overall posture.** The engineering foundations relevant to child privacy are unusually strong for
a project at this stage: genuine data minimization by design (no birthdate, no exact age, no child
photos, no child email/phone/address, no geolocation), a real authentication and family-tenancy
authorization layer, an outbound PII egress guard on the main generation path, a mandatory
human-approval safety pipeline, and no analytics, advertising, or tracking SDKs anywhere. What is
missing is the entire **compliance control plane** that COPPA requires once the service is offered
to the public: verifiable parental consent, a published privacy notice and direct notice to
parents, parental deletion rights, a data-retention policy with enforced purging, and confirmed
processor terms for the third parties that receive child-derived content.

**Applicability nuance (tiered).** COPPA attaches to a commercial online service offered to the
public. The current private family / homelab / "R1" tier (guardian accounts provisioned by hand in
Supabase, generation and review providers defaulting to `mock`) is most likely outside COPPA's
scope as operated today. The **public App Store tier decided in ADR-008 is squarely in scope**, and
the current architecture already accumulates child-linked data in ways that must be remediated
before that launch. This audit assesses readiness for the public tier and flags issues that exist
regardless of tier.

**Headline findings (detail in Section 6):**

| ID | Finding | Severity |
|----|---------|----------|
| C-01 | No verifiable parental consent mechanism, and no signup flow to attach one to | Critical (at launch) |
| C-02 | No published privacy notice and no direct notice to parents | Critical (at launch) |
| C-03 | No child-data deletion capability; schema lacks the cascades that would make deletion feasible | Critical (at launch) / High (now) |
| H-01 | No data-retention policy or purge; child data (including raw free text) is retained indefinitely | High |
| H-02 | Cover-image generation to Google Gemini applies no PII screening at all | High |
| H-03 | Stage-0 safety classifiers (OpenAI, Perspective) bypass the PII guard in the moderation pipeline | High |
| H-04 | Third-party LLM processor data-handling terms are unconfirmed (project's own open blocker) | High (at launch) |
| M-01 | The PII egress guard is a registered-name allowlist, not PII detection (misses free-form child PII) | Medium |
| M-02 | Public, unauthenticated cover-image bucket with guessable object keys | Medium |
| M-03 | Raw child free text is retained at rest even when blocked or declined (redaction is view-only) | Medium |
| M-04 | `SECURITY.md` asserts a child-privacy control that does not exist, and is stale on auth | Medium |
| M-05 | No aggregate parental access / data export; some child data has no read endpoint | Medium |
| M-06 | Client does not enforce child token scoping; kid surface runs under the guardian token in `localStorage` | Medium |
| L-01 | `updated_by_device_id` persistent identifier column exists on child reading state (latent) | Low |
| L-02 | `TrustedHostMiddleware` disabled and app-layer HTTPS redirect off | Low |
| L-03 | Birthdate screening in the PII guard is dead code (no birthdate stored), giving false assurance | Low / Info |
| L-04 | Supabase project ref committed in `.mcp.json` (developer tooling) | Low / Info |

Strengths that materially reduce risk are catalogued in Section 7 and should be preserved through
the Phase 7 work.

---

## 2. Methodology and scope

Static source review only; no code was executed and no live data was inspected. Coverage:

- **Backend**: all FastAPI routers (`src/cyo_adventure/api/`), ORM models (`src/cyo_adventure/db/models.py`),
  Alembic migrations (`migrations/versions/`), the auth seam (`api/deps.py`), the generation and
  moderation pipelines (`generation/`, `moderation/`), the PII egress guard (`generation/pii.py`),
  configuration (`core/config.py`), middleware (`middleware/`), and the cover-image path (`covers/`).
- **Frontend**: `frontend/src/` routing, auth context, guardian console, kid surface, profile and
  story-request forms.
- **Docs and config**: `docs/planning/` (privacy model, ADRs, project plan), `SECURITY.md`,
  `README.md`, `.env.example`, `.mcp.json`.

Findings cite `file:line` evidence. "Absent" means searched for and not found in source (not merely
undocumented). The regulatory frame is COPPA (15 U.S.C. 6501-6506) and 16 CFR Part 312, including
the FTC's 2025 amendments (written data-retention policy and prohibition on indefinite retention,
separate consent for third-party disclosures, and a written information-security program).

---

## 3. Personal information inventory

All persistent data lives in one Postgres schema defined in `src/cyo_adventure/db/models.py`
(19 tables). No file datastore, SQLite, or local dumps exist (`data/` and `configs/` hold only
`.gitkeep`). Guardian identity (email, password, OAuth identity) is delegated to Supabase Auth and
is **not** stored in the application database; the backend persists only an opaque OIDC subject.

### 3.1 Data collected directly from a child

The child actor (running under the guardian token in R1; see Section 5.3) can submit only:

| Data | Where collected | Where stored | COPPA classification |
|------|-----------------|--------------|----------------------|
| Free-text story idea (`request_text`, <=500 chars) | `frontend/src/library/RequestStory.tsx:185-190` | `story_request.request_text` (`db/models.py:558`) | Personal information if the child types identifying content |
| Proposed series title (<=120 chars) | `RequestStory.tsx:202-208` | `story_request.proposed_series_title` (`db/models.py:589`) | Same as above |
| Book rating (1-5) | `frontend/src/library/StarRating.tsx` | `rating.value` (`db/models.py:374`) | Behavioral data tied to the child |
| Reading progress (node, path, visit set, save slots) | reader UI | `reading_state.*` (`db/models.py:287-324`) | Behavioral data tied to the child |
| Endings reached | reader UI | `completion.*` (`db/models.py:327-344`) | Behavioral data tied to the child |

There is **no** child-entered name, birthdate, age, photo, email, phone, address, or geolocation.

### 3.2 Data the guardian enters about a child

| Data | Where collected | Where stored | Notes |
|------|-----------------|--------------|-------|
| Child display name / nickname (<=120) | `frontend/src/guardian/ProfileFormDialog.tsx:108-113` | `child_profile.display_name` (`db/models.py:181`) | A first name or nickname; the only stored child name |
| Age band (coarse category) | `ProfileFormDialog.tsx:117-126` | `child_profile.age_band` (`db/models.py:182`) | One of six bands; not a birthdate or exact age |
| Reading-level cap | `ProfileFormDialog.tsx:130-138` | `child_profile.reading_level_cap` (`db/models.py:183`) | |
| Avatar | `ProfileFormDialog.tsx:143-165` | `child_profile.avatar` (`db/models.py:188`) | Closed 8-glyph vocabulary, never a photo (`api/schemas.py:705-712`) |
| TTS preference | `ProfileFormDialog.tsx:166-173` | `child_profile.tts_enabled` (`db/models.py:187`) | |

### 3.3 Persistent identifiers about a child

- `child_profile.id` (UUID), the stable per-child key referenced by all behavioral tables.
- A `child`-role `user.authn_subject` linked to one profile (`db/models.py:166-170`), if a
  child-scoped token is ever issued (not exercised by the shipped client; see Section 5.3).
- `reading_state.updated_by_device_id` (String 64) (`db/models.py:319`), a client-supplied device
  identifier. Under COPPA a persistent identifier is personal information. The shipped kid client
  never populates it today (finding L-01), so this is latent, not active.

### 3.4 Child-influenced content that flows downstream

A child's typed words propagate: `story_request.request_text` becomes `ConceptBrief.premise`
(`story_requests/brief.py:99`) stored in `concept.brief` (`db/models.py:440`); that drives the
generation prompt whose raw output is stored in `generation_job.report` (`db/models.py:988`); the
finished prose is stored in `storybook_version.blob` with possible echoes in `moderation_report`
(`db/models.py:247,252`). Each hop is a place child-derived content is retained and, in several
cases, disclosed to a third party (Section 4).

### 3.5 Audit and event logs

`pipeline_event` (`db/models.py:714-768`) is a durable, append-only log (DB-trigger enforced) that
retains child identifiers (`actor_id` when a child acts, composite `entity_id` values, and a
`child_profile_id` in the `BOOK_ASSIGNED` payload, `events/writer.py:38`) and rating values. Its
payload is free of child free text by contract (key allowlist plus a scalar-only value guard,
`events/writer.py:17-83`). The two `*_audit` tables hold admin edits only, no child data.

---

## 4. Third-party disclosure map

COPPA treats disclosure of a child's personal information to third parties as a distinct, tightly
regulated event, and the 2025 amendments require separate consent for most third-party disclosures
(other than disclosures to service providers acting solely as the operator's processors, and those
that support the service's internal operations, which remain within the original consent).
The single technical control is `assert_prompt_pii_safe` (`generation/pii.py:101`), a case-insensitive
**allowlist match** against the family's registered `child_profile.display_name` values. Its coverage
and gaps are analysed in finding M-01.

| # | Destination | What is sent | Contains child data? | PII guard applied? |
|---|-------------|--------------|----------------------|--------------------|
| 1 | LLM text generation: OpenRouter (prod default), Anthropic, Ollama (local), Modal | Full `ConceptBrief` including `premise` (child free text after approval), plus story JSON on repair | Yes | Yes, via `PiiGuardedProvider` (`generation/orchestrator.py:647`, `generation/guarded.py:71-72`); allowlist gap applies |
| 2 | OpenAI Moderation API (`api.openai.com`) | Child's raw request text at screening; each generated node body at moderation | Yes | **Screening only**; **bypassed at moderation** (`moderation/pipeline.py:306-311` sends raw nodes) |
| 3 | Google Perspective API | Same content as #2 | Yes | Same as #2 (bypass at moderation) |
| 4 | Moderation LLM review stages: OpenRouter / Ollama | Generated node prose in `<untrusted_passage>` tags | Yes (derived) | Yes (`moderation/pipeline.py:104-112`) |
| 5 | Google Gemini "nano banana" cover generation | Story title, protagonist name recovered from `concept.brief`, themes, a 240-char prose excerpt, age band | Yes | **No guard at all** (`covers/` never imports the guard) |
| 6 | Supabase Storage (cover bucket) | WebP image bytes only | Derived (artwork) | N/A (binary), but bucket is public (M-02) |
| 7 | Supabase Auth / GoTrue | Guardian email/password or OAuth identity | Guardian only, not child | N/A |
| 8 | Supabase MCP (`.mcp.json`) | Developer tooling, read-only; not a runtime data path | No | N/A (project ref committed, L-04) |

**Production default path.** `generation_provider` defaults to `mock` (`core/config.py:134-136`), so
CI and local runs make no live calls; the documented production default routes generation through
**OpenRouter cloud** first, falling back to local Ollama (`generation/provider.py:594-606`;
`docs/planning/privacy-model.md:174-176`). The review provider defaults to `mock` (`config.py:302`).

**Negative findings (good).** No Sentry integration exists (only a commented `SENTRY_DSN`
placeholder, `.env.example:137-140`; no `sentry_sdk` import anywhere). No PostHog, Google Analytics,
Mixpanel, Segment, Datadog, or OpenTelemetry anywhere in backend or frontend. Logging is on-box only
(structlog to stdout/stderr, `utils/logging.py`); providers deliberately avoid logging prompt or
response bodies (`generation/providers/openrouter.py:230-231`); correlation IDs are UUIDs, not PII.
The browser uses Supabase for **authentication only** (no `.from()`, `.storage`, or `.rpc()` calls in
`frontend/src`), so no child data is written to Supabase from the client.

---

## 5. Requirement-by-requirement assessment

Status legend: **Implemented**, **Partial**, **Not implemented**, **N/A (current tier)**.

### 5.1 Notice (16 CFR 312.4)

**Status: Not implemented.**

- No privacy-policy or terms page or route exists in the frontend (`frontend/src/router.tsx` has no
  such route; `LandingPage.tsx:12-30` has no policy link; `frontend/index.html` has none).
- `README.md` describes the app ("A choose-your-own-adventure reading app for kids") but contains no
  privacy notice or data-collection disclosure.
- The only privacy document is the internal `docs/planning/privacy-model.md`, which itself lists "a
  published privacy notice" as future work (line 231).
- No direct-notice-to-parents mechanism exists (no email or notice dispatch anywhere in source). The
  `user` table has no email/contact column today; `docs/planning/PROJECT-PLAN.md:826` (P6-03) plans
  to add one.

COPPA requires both a clear online privacy notice describing what is collected, how it is used, and
disclosure practices, and a direct notice to the parent before collection. Neither exists.

### 5.2 Verifiable parental consent (16 CFR 312.5)

**Status: Not implemented (most consequential gap).**

- No consent code exists anywhere; `consent`, `COPPA`, `verifiable`, and `parental` match only in
  planning docs, not in `src/` or `frontend/src/`.
- There is **no signup or account-provisioning endpoint** (all routers are wired in
  `app.py:172-185`; none creates a `Family` or guardian `User`). Guardian accounts are created
  by hand in Supabase for the R1 families (`frontend/src/guardian/LoginPage.tsx:22-27`). There is
  therefore not even a structural point at which consent could be captured.
- Child-profile creation (`POST /profiles`, `api/profiles.py:101-132`) requires only the guardian
  role; there is no consent precondition, verification step, or consent record on the model
  (`db/models.py:174-189`).
- Child behavioral data (`reading_state`, `completion`, `rating`) and child free text
  (`story_request`) are collected with no consent gate.

The guardian-only identity model (children never obtain third-party IdP identities;
`adr-008` lines 100-111) is a sound foundation for a low-friction consent method, but the consent
step itself, and a persisted consent artifact (method, timestamp, policy version), do not exist.
This is planned as P7-02 (`PROJECT-PLAN.md:893`).

### 5.3 Parental access, deletion, and refusal of further collection (16 CFR 312.6)

**Status: Partial (review) / Not implemented (deletion).**

**Review**: A guardian principal is scoped to all family profiles (`api/deps.py:332-336`), so
per-resource review is possible: `GET /profiles` (`api/profiles.py:73-98`), `GET /reading-state/...`
(`api/reading.py:120-151`), `GET /ratings/{profile_id}` (`api/ratings.py:109-138`). Gaps: there is
no read endpoint for `completion` data, and no aggregate "all data about my child" export
(finding M-05).

**Deletion and refusal**: Not implemented.

- No DELETE handler exists for child profiles or any child data. The only DELETE routes are for
  admin config tables (`api/moderation_thresholds.py:240`, `api/provider_allowlist.py:204`).
- No soft-delete column (`deleted_at`, `is_active`) exists on `child_profile` or any child table.
- **No foreign-key cascades are defined.** Every FK in `migrations/versions/20260621_1926_initial_schema.py`
  and in `db/models.py` omits `ondelete` (child_profile is referenced by `user`, `reading_state`,
  `completion`, `rating`, `storybook_assignment`, and `story_request`). A raw delete of a referenced
  `child_profile` would fail: with no `ON DELETE` action Postgres defaults to `NO ACTION`, which blocks
  the delete while dependent rows exist (orphaned rows would arise only from an incomplete
  application-level purge, not from the database default). This directly contradicts the project's own
  stated requirement that "Cascades must be defined in the Alembic schema"
  (`docs/planning/privacy-model.md:133`). See finding C-03.

### 5.4 Prohibition on conditioning participation (16 CFR 312.7)

**Status: Largely satisfied by design.** The service collects only what is needed to deliver
personalized reading (a nickname, a coarse age band, reading progress). It does not condition access
on the disclosure of more personal information than is reasonably necessary. This should be
re-verified once monetization and the parental gate land (ADR-008 part 3).

### 5.5 Confidentiality, security, and integrity (16 CFR 312.8)

**Status: Partial. Reasonable baseline with specific gaps.**

Strengths (Section 7) include real OIDC JWT verification, family/profile authorization, secret
hygiene, and OWASP security headers. Gaps:

- **Public cover bucket** (M-02): covers are uploaded to a public Supabase Storage bucket with a
  guessable key `{storybook_id}/{version}.webp` and a public URL is returned
  (`covers/storage.py:41-53`). Child-derived artwork is retrievable without authentication.
- **`TrustedHostMiddleware` not added** and app-layer HTTPS redirect off (`middleware/security.py`
  defaults via `app.py:167`), delegating Host validation and TLS entirely to the reverse proxy
  (L-02).
- **No written information-security program** artifact (a 2025-amendment expectation): no designated
  coordinator, documented risk assessment, or vendor-oversight process is present in the repo.
- The unconfirmed processor terms (H-04) also fall under this section.

### 5.6 Data retention and deletion (16 CFR 312.10)

**Status: Not implemented.**

- No retention policy, TTL, scheduled purge, or minimization job exists. `reading_state`,
  `completion`, `rating`, and `story_request` (including raw `request_text`) accumulate indefinitely.
- The one documented retention rule, purging `generation_job.report` after 30 days or on publish
  (ADR-007), is explicitly not built (`db/models.py:973-982` marks it a Phase 5 pg_cron task;
  `privacy-model.md:96-98` says "The purge worker is a Phase 5 deliverable and is not yet built").
- The 2025 amendments require a written, published retention policy and prohibit indefinite
  retention; both are currently unmet. See finding H-01.

### 5.7 Data minimization and the internal-operations exception (16 CFR 312.2)

**Status: Strong on minimization; a nuance on classifiers.** The absence of birthdate, exact age,
photos, and contact data is exactly the posture COPPA's minimization principle favors. The safety
classifiers and moderation LLMs process child content to protect the integrity and safety of the
service, which can align with the "support for internal operations" concept, but only if the third
parties act strictly as the operator's processors under contract and do not use the data for their
own purposes. That contractual posture is unconfirmed (H-04), and the classifier calls are not PII
screened (H-03).

---

## 6. Findings register

Severity reflects risk at the **public launch** for which COPPA is binding, with current-state notes.

### C-01. No verifiable parental consent mechanism (Critical at launch)

**COPPA**: 312.5. **Evidence**: no consent code in `src/`/`frontend/src`; no signup endpoint
(`app.py:172-185`); manual Supabase provisioning (`LoginPage.tsx:22-27`); ungated
`POST /profiles` (`api/profiles.py:101-132`).
**Risk**: Collecting personal information from children without prior verifiable parental consent is
the core COPPA violation.
**Recommendation**: Implement onboarding (P6-03) with a consent step (P7-02): present the privacy
notice, obtain consent by a COPPA-acceptable method appropriate to the data use, and persist a
consent record (method, timestamp, policy version) on the family. Block child-data collection until
consent exists. Add a re-consent flow on material policy change.

### C-02. No published privacy notice or direct notice to parents (Critical at launch)

**COPPA**: 312.4. **Evidence**: no policy page/route; `README.md` and `LandingPage.tsx` carry no
notice; only the internal `privacy-model.md`.
**Risk**: COPPA requires a compliant online notice and direct notice to the parent before
collection.
**Recommendation**: Publish a privacy policy (derivable from the Section 3 inventory and
`privacy-model.md`), link it from the landing page, the guardian console, and the app-store listing,
and deliver direct notice to the parent at onboarding. Align it with the Apple privacy nutrition
label (ADR-008 part 5).

### C-03. No deletion capability; schema cannot cascade a child delete (Critical at launch / High now)

**COPPA**: 312.6, 312.10; ADR-008 App Store Guideline 5.1.1(v). **Evidence**: no profile DELETE
(`api/profiles.py` exposes GET/POST/PATCH only); no soft-delete column (`db/models.py:174-189`); no
`ondelete` on any FK (`migrations/versions/20260621_1926_initial_schema.py:40,51-52,100-112`);
contradicts `privacy-model.md:133`.
**Risk**: A parent cannot exercise the deletion right, and the data model cannot currently satisfy a
deletion request even manually without orphaning or FK errors. Data is already accumulating.
**Recommendation**: Add cascade behavior (DB-level `ON DELETE CASCADE` via migration, or an explicit
application-level purge that enumerates every child-linked table, plus the `pipeline_event`
`BOOK_ASSIGNED` rows) and expose an authenticated in-app deletion endpoint for a child profile and
for the whole family account. Add the deletion drill from P7-04. Verify erasure against the Section 3
inventory.

### H-01. No data-retention policy or purge; indefinite retention (High)

**COPPA**: 312.10. **Evidence**: no TTL/purge/cron for user data; `generation_job.report` purge
documented but unbuilt (`db/models.py:973-982`, `privacy-model.md:96-98`).
**Recommendation**: Write and publish a retention policy stating purposes and retention windows per
data category; implement the pg_cron purge for `generation_job.report`; add retention/expiry for
`story_request` (especially blocked/declined rows, see M-03) and stale `reading_state`.

### H-02. Cover generation to Google Gemini has no PII screening (High)

**COPPA**: 312.2 (disclosure), 312.8. **Evidence**: `covers/` never imports or calls the PII guard;
the cover prompt includes the protagonist name recovered from `concept.brief` and a 240-char prose
excerpt (`covers/prompt.py:43-112`, `covers/service.py:41-61`, `covers/provider.py:36-44`).
**Risk**: Guardian-entered names and generated prose (which may echo names) are disclosed to Google
with no screening at all, the weakest egress path in the system.
**Recommendation**: Route cover-prompt assembly through `assert_prompt_pii_safe` with the family's
`PiiContext` before calling the image model, or strip names to role descriptors in the cover prompt.
Confirm the image provider's data-handling terms (H-04).

### H-03. Stage-0 classifiers bypass the PII guard in the moderation pipeline (High)

**COPPA**: 312.2, 312.8. **Evidence**: `moderation/pipeline.py:306-311` calls `run_classifiers` with
raw node prose (to OpenAI Moderation and Perspective), while the sibling LLM review stages in the
same pipeline are wrapped by `PiiGuardedProvider` (`pipeline.py:104-112`). At story-request screening
the local guard runs first (`story_requests/screening.py:80-95`) but the classifiers then receive
everything else (`:105-111`).
**Recommendation**: Apply the same PII screening to classifier inputs, or document and confirm the
classifier vendors as safety processors under terms consistent with COPPA's internal-operations
posture. Prefer screening at the pipeline boundary so all egress is uniformly guarded.

### H-04. Unconfirmed third-party LLM processor terms (High at launch)

**COPPA**: 312.4(d), 312.8. **Evidence**: the project's own open blocker,
`privacy-model.md:165-189` (OpenRouter standard-retention vs zero-data-retention unconfirmed for both
the generation and the review legs).
**Recommendation**: Obtain written data-handling terms (retention, sub-processing, no independent
use) for every cloud egress destination (OpenRouter and its downstream models, Anthropic-direct,
Google Gemini image, OpenAI Moderation, Perspective, Supabase). Prefer zero-data-retention routes.
Record the outcome in `privacy-model.md` before enabling any live provider for the public tier.

### M-01. PII guard is a registered-name allowlist, not PII detection (Medium)

**Evidence**: `generation/pii.py:101-158` matches only registered `child_profile.display_name`
tokens; it is a no-op when a family has no profiles (`pii.py:108`) and cannot detect other
children's names, nicknames, misspellings, addresses, schools, or phone numbers a child types into
free text. The child's raw request egresses to OpenAI and Perspective at submission
(`screening.py:105-111`) and to the generation LLM as `premise` after approval.
**Recommendation**: Treat the allowlist as one layer; add pattern-based detectors (emails, phone
numbers, street addresses) and consider a broader named-entity pass on child free text before egress.
Document the residual risk. Do not rely on the guard as the sole disclosure control.

### M-02. Public cover-image bucket with guessable keys (Medium)

**Evidence**: `covers/storage.py:41-53` uploads to a public bucket and returns
`/object/public/{bucket}/{key}` with `key = {storybook_id}/{version}.webp`.
**Recommendation**: Use a private bucket with signed, expiring URLs, or gate cover retrieval behind
the family-scoped API. Avoid predictable keys.

### M-03. Raw child free text retained at rest even when blocked or declined (Medium)

**Evidence**: `story_requests/service.py:375-390` stores `request_text` unconditionally and only
flips `status` to `blocked`; `proposed_series_title` is "retained as an audit trail after
ratification or request decline" (`db/models.py:487-488`). Redaction happens only at the API view
layer (`api/schemas.py`, `story_requests.py:236`).
**Recommendation**: For blocked or declined requests, purge or null the raw text at rest (retain only
the redacted category/verdict for audit), or apply a short retention window. Align with H-01.

### M-04. `SECURITY.md` misstates a child-privacy control and is stale on auth (Medium)

**Evidence**: `SECURITY.md:55` claims a mitigation of "no persistent PII without explicit parental
consent," which is not implemented (child names and free text are persisted with no consent gate).
`SECURITY.md:37-42` still describes the dev auth stub and pending Authentik JWT validation, although
Supabase OIDC verification is already implemented (`api/deps.py:207-258`) per ADR-009.
**Recommendation**: Correct the security policy to reflect the real state, and avoid asserting
compliance controls that do not exist (such assertions can themselves create exposure).

### M-05. No aggregate parental access / export (Medium)

**COPPA**: 312.6(a). **Evidence**: per-resource GETs exist but there is no `completion` read endpoint
and no single export of all data about a child.
**Recommendation**: Provide a guardian-facing export that assembles every child-linked record
(profile, reading state, completions, ratings, story requests, generation reports) per the Section 3
inventory.

### M-06. Client does not enforce child token scoping (Medium)

**Evidence**: the kid surface is not auth-gated (`frontend/src/router.tsx:63-77`) and both surfaces
share one bearer token in `localStorage['auth_token']` (`frontend/src/hooks/useApi.ts:39-44`); the
backend `child` role and scoping exist (`api/deps.py:332-339`) but the shipped client never obtains a
child-scoped token. ADR-008 (part 6) itself calls for tokens out of `localStorage`.
**Recommendation**: Issue and use the backend-minted, single-profile child token described in ADR-008
part 2 for the kid surface, and move tokens out of `localStorage` (memory plus silent refresh on web,
Keychain in the shell). This is a defense-in-depth and child-data-separation improvement.

### L-01. Latent persistent-identifier column (Low)

**Evidence**: `reading_state.updated_by_device_id` (`db/models.py:319`) is defined but unset by the
shipped kid client. **Recommendation**: Keep it unset, or if used, treat device IDs as personal
information (retention, deletion, disclosure in the notice).

### L-02. `TrustedHostMiddleware` disabled and app-layer HTTPS redirect off (Low)

**Evidence**: `app.py:167` uses `add_security_middleware` defaults (`middleware/security.py:548,
588-592`). **Recommendation**: Set `allowed_hosts` and enable HTTPS redirect (or confirm the proxy
enforces both) before public launch.

### L-03. Birthdate screening is dead code (Low / Info)

**Evidence**: `PiiContext.birthdates` is always empty because no birthdate is stored
(`generation/worker.py:648,675,682`). **Recommendation**: Remove the dead branch or wire it only if a
birthdate is ever collected, so the guard does not imply coverage it lacks.

### L-04. Supabase project ref committed (Low / Info)

**Evidence**: `.mcp.json` embeds a Supabase project ref for read-only developer tooling.
**Recommendation**: This is dev tooling, not a runtime path; confirm the ref is not sensitive and
that project access is otherwise controlled.

---

## 7. Strengths to preserve

These controls materially reduce child-privacy risk and should be maintained through Phase 7:

- **Data minimization by design**: no birthdate or exact age (coarse `age_band` only), **no child
  photos** (closed 8-glyph avatar vocabulary enforced by a `Literal` type, `api/schemas.py:705-712`,
  plus a `camera=()` permissions-policy header), no child email/phone/address/geolocation, and no
  child-entered name (only a guardian-set nickname).
- **Guardian identity delegated and minimized**: no guardian email, password, phone, or real name in
  the app database; only an opaque OIDC subject (`db/models.py:166`), with credentials held by
  Supabase.
- **Real authentication**: Supabase OIDC JWT verification with JWKS, an RS256/ES256 algorithm
  allowlist (defeating `alg=none`/HS256 confusion), issuer/audience/expiry checks, and HTTPS-only
  JWKS (`api/deps.py:181-258`), with a hard import-time guard preventing the dev stub outside
  `local` (`api/deps.py:67-76`).
- **Strong tenancy authorization**: family and profile scoping derived from the verified principal
  (never the client), cross-family IDOR blocked with no existence oracle, and a closed `Role` enum
  backed by at-rest CHECK constraints (`api/deps.py:45-55`; `db/models.py:159-161`).
- **PII egress chokepoint** on the main generation path (`generation/guarded.py`), even though its
  coverage is allowlist-limited (M-01).
- **Human-in-the-loop safety**: mandatory guardian approval (ADR-005), an independent moderation
  pipeline, and screening of child free text before a guardian ever sees it, with classifier scores
  and sources redacted from guardians (`story_requests/screening.py:46-55`).
- **No analytics, advertising, or tracking SDKs**; no Sentry wired; on-box logging only; providers
  avoid logging content; the durable event log is PII-free by allowlist contract.
- **Secret hygiene**: no committed secrets, secret-manager sourcing, and fail-fast production guards
  for database and OIDC configuration (`core/config.py`).
- **A documented privacy model and an explicit COPPA plan** (`privacy-model.md`, ADR-008/009,
  Phase 7 in `PROJECT-PLAN.md`): the team already knows this work is required and has scoped it.

---

## 8. Prioritized remediation roadmap

Ordered by dependency and severity. Items map to the existing plan where one exists.

**Gate 0: before any public (non-family) exposure or app-store submission.**

1. Verifiable parental consent at onboarding, with a persisted consent record (C-01; plan P6-03,
   P7-02).
2. Published privacy notice plus direct notice to parents, linked from all surfaces (C-02).
3. In-app deletion of a child profile and of the family account, with schema cascades or an explicit
   enumerated purge, verified by a deletion drill (C-03; plan P7-04).
4. Written, published data-retention policy and the `generation_job.report` purge; retention for
   blocked/declined `story_request` text (H-01, M-03).
5. Confirm processor data-handling terms for every cloud egress destination and prefer
   zero-data-retention routes (H-04).

**Gate 1: harden the disclosure surface.**

6. Add PII screening to the cover-generation prompt (H-02) and to the Stage-0 classifier inputs
   (H-03); strengthen the guard beyond the name allowlist (M-01).
7. Move covers to a private bucket with signed URLs (M-02).
8. Issue and use child-scoped tokens for the kid surface; move tokens out of `localStorage` (M-06).

**Gate 2: governance and hygiene.**

9. Correct `SECURITY.md` (M-04); add a guardian data-export endpoint (M-05); set `allowed_hosts` and
   HTTPS redirect (L-02); produce a written information-security program artifact (312.8).
10. Retire the dead birthdate branch or wire it correctly (L-03); review the committed project ref
    (L-04).

**Cross-cutting**: run the Phase 7 compliance checklist (P7-08) as the submission gate, and engage
privacy counsel to confirm the consent method, notice text, and retention windows.

---

## 9. References

- 15 U.S.C. 6501-6506 (COPPA); 16 CFR Part 312 (COPPA Rule), including the 2025 amendments.
- FTC, "Complying with COPPA: Frequently Asked Questions."
- `docs/planning/privacy-model.md` (internal data classification and retention rules).
- `docs/planning/adr/adr-008-public-app-store-launch.md`, `adr-009-supabase-platform.md`.
- `docs/planning/PROJECT-PLAN.md` (Phase 6 and Phase 7 deliverables).

*End of audit. This document records observed data practices at commit `c9dbfa9` and is a
point-in-time engineering assessment, not legal advice or a certification of compliance.*
