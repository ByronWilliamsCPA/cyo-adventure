---
title: "GDPR Compliance Review"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Engineering compliance review of CYO Adventure against the EU General Data Protection Regulation (GDPR, Regulation (EU) 2016/679), covering both guardian and child data subjects, mapped to Article-level requirements, and cross-referenced against the existing COPPA audit and ADR-018's open decisions."
tags:
  - compliance
  - security
  - privacy
component: Development-Tools
source: "Static review of src/cyo_adventure, frontend/src, supabase/migrations, and docs at commit 66fe320 (2026-07-19), building on docs/compliance/coppa-compliance-audit.md (commit c9dbfa9, 2026-07-10) and docs/planning/adr/adr-018-childrens-privacy-compliance.md"
---

> **Status**: Draft | **Version**: 1.0 | **Review date**: 2026-07-19
> **Code reviewed at**: commit `66fe320` on `main`
> **Scope**: `src/cyo_adventure/`, `frontend/src/`, `supabase/migrations/`, `docs/`

## 0. Important disclaimer

This is a **technical and engineering compliance review**, not legal advice. It maps the
codebase's observable data practices to the requirements of the EU General Data Protection
Regulation (GDPR, Regulation (EU) 2016/679) and, where relevant, the UK GDPR/Data Protection
Act 2018. Determinations of legal applicability, lawful basis, the sufficiency of any
consent or transfer mechanism, and the precise text of required notices must be made with
qualified EU/UK privacy counsel. Nothing here should be read as a legal opinion or as
certification of compliance. This review builds directly on the existing
[`docs/compliance/coppa-compliance-audit.md`](./coppa-compliance-audit.md) (2026-07-10) and
does not re-derive facts that audit already established with file:line citations; it cites
that audit by finding ID where the underlying fact is identical, and adds GDPR-specific
analysis (guardian data, Article 8 consent age, DPIA, international transfers, extraterritorial
scope, joint controllership, records of processing) that a COPPA-scoped audit does not cover.

---

## 1. Executive summary

GDPR and COPPA overlap heavily on the underlying engineering (data minimization, consent,
deletion, retention, third-party disclosure) but differ in scope and mechanics in ways that
matter for this project specifically:

- **GDPR covers everyone, not just children.** COPPA only regulates collection from children
  under 13. GDPR applies to *all* personal data of *all* data subjects; meaning guardian
  email addresses, family names, and Supabase auth metadata are squarely in scope even though
  the COPPA audit correctly treated them as out of its scope (Section 3, below).
- **GDPR's children's-consent age is not a fixed line.** Article 8 sets 16 as the default
  digital-consent age but lets EU member states lower it to any value between 13 and 16 by
  national law, so "is this child old enough to consent themselves" is a per-country lookup,
  not a single COPPA-style "under 13" test. CYO Adventure's `AgeBand` enum (`3-5` through
  `16+`) has no Article 8 consent-age logic at all (confirmed absent, Section 5.2).
  This project's actual reliance is on **parental** consent regardless of the child's age band
  (a guardian, not the child, provisions every profile), which is the correct posture for a
  child-directed service and sidesteps most of the Article 8 age-threshold complexity; but
  the *mechanism* for capturing that parental consent does not exist (Section 5.2, same gap as
  COPPA's C-01).
- **GDPR applies based on where the data subject is, not which App Store storefront serves
  them.** ADR-018's D3 frames "GDPR-K applicability" as a launch-geography choice ("US-only
  App Store storefront" vs. "EU/UK storefronts in scope"). That framing is incomplete for
  GDPR: Article 3(2) applies GDPR extraterritorially to any offering of goods/services to, or
  monitoring of, data subjects **who are in the EU/UK**, regardless of storefront geofencing,
  the operator's location, or where the servers sit. A US App Store listing does not by itself
  exclude EU users; an EU-resident guardian can download a US-storefront app if Apple allows
  it in their region, use a VPN, or (most concretely for the *current* private/homelab tier)
  simply be a person the operator personally invited who happens to live in the EU. This is a
  pressure point, not a settled fact: see Section 4.1.
- **GDPR imposes obligations absent from COPPA**: a Data Protection Impact Assessment (DPIA)
  this project's combined risk profile (children's data, profiling-adjacent moderation, and
  confirmed special-category risk in free text) makes likely required under Article 35's
  risk-based standard (Section 5.7 has the full analysis; Article 35(3)(b)'s automatic trigger
  applies only if the special-category risk is confirmed at scale), a
  Records of Processing Activities document (Article 30), an international-transfer legal
  mechanism for every non-EEA processor (Articles 44-49, and this covers *all* of this
  project's processors, since Supabase, the LLM vendors, and Google are all US-hosted), a
  broader set of data-subject rights (portability, Article 20, has no COPPA analogue), and a
  72-hour breach notification duty to a supervisory authority (Article 33) instead of COPPA's
  more general security-program expectation.
- **The engineering foundation the COPPA audit found** (data minimization by design, no
  ads/analytics SDKs, real auth/tenancy, an outbound PII guard, human-in-the-loop safety) **is
  exactly what GDPR's Article 25 "data protection by design and by default" principle asks
  for**, and materially reduces GDPR risk in the same way it reduces COPPA risk. What is
  missing is the same **compliance control plane** (consent, notice, DSAR handling, retention
  policy, transfer mechanism, DPIA) the COPPA audit identified, examined here through the GDPR
  lens with GDPR-specific gaps layered on top.

**Applicability nuance (tiered, and less settled than the COPPA case).** The COPPA audit
concluded the private/homelab tier is "most likely outside COPPA's scope as operated today"
because COPPA turns on being "a commercial online service offered to the public." GDPR has no
equivalent "not yet public" carve-out: if a single guardian who is an EU/UK data subject uses
the app **today**, in the current private tier, GDPR already applies to that guardian's and
their child's data, in full, regardless of the app's public/private status or revenue model.
Whether that is true in practice depends entirely on who the actual current users are; a fact
this review cannot determine from source code. This is the review's single most important
open question and is flagged as Pressure Point P-1 (Section 6).

**Headline findings (detail in Section 6):**

| ID | Finding | Severity |
|----|---------|----------|
| G-01 | No lawful basis is established or recorded for any processing activity | Critical (once GDPR applies) |
| G-02 | No mechanism for verifiable parental/guardian consent, and none of the six Article 6 lawful bases is cleanly available as a substitute | Critical (once GDPR applies) |
| G-03 | No Records of Processing Activities (Article 30) document exists | Critical (once GDPR applies) / paperwork item, low engineering cost |
| G-04 | No Data Protection Impact Assessment; the combined risk profile makes one likely required under Article 35's risk-based standard | Critical (once GDPR applies) |
| G-05 | No international-transfer mechanism (SCCs or equivalent) for any of the US-hosted processors (Supabase, OpenRouter/Anthropic, OpenAI, Google Perspective/Gemini, Sentry) | Critical (once GDPR applies) |
| G-06 | No erasure/rectification/access/portability rights implemented for **guardian** data (distinct from the COPPA audit's C-03, which is scoped to child data) | High |
| G-07 | No published privacy notice satisfying Articles 12-14's higher transparency bar (COPPA C-02 covers the same absence; GDPR's required content is broader) | Critical (once GDPR applies) |
| G-08 | ADR-018 D3's "US-only launch" framing does not itself resolve Article 3(2) extraterritorial applicability | Pressure point, not yet a code finding |
| G-09 | No breach-notification runbook (72-hour Article 33 duty) | High |
| G-10 | Cross-family recommendation sharing (ADR-016) discloses one family's data to another without a documented Article 6 basis for that specific disclosure | Medium |
| G-11 | No Data Protection Officer designation analysis performed (Article 37) | Medium (assessment gap, not necessarily a required hire) |
| G-12 | `pipeline_event` audit log is retained indefinitely with no Article 17(3) balancing test documented for why it survives an erasure request | Medium |

Findings G-01 through G-05, G-07, and G-09 largely track the COPPA audit's C-01 through H-04
one-for-one at the engineering-artifact level (the same missing consent flow, notice page,
deletion cascade, and processor-terms confirmation would close most of both). They are listed
separately here because GDPR's *content* requirements for each artifact differ from COPPA's
(Section 5), and because G-03, G-04, G-05, G-06, G-11, and G-12 have **no COPPA counterpart at
all**; building only to COPPA's checklist would leave the app non-compliant with GDPR even
after COPPA Gate 0 (per the COPPA audit's Section 8) is cleared.

---

## 2. Methodology and scope

Static source review only; no code was executed and no live data was inspected. This review
reuses the file:line evidence already gathered in `docs/compliance/coppa-compliance-audit.md`
Sections 2-4 (personal-information inventory, third-party disclosure map) rather than
re-deriving it, and cites it by finding ID. New evidence gathered specifically for this GDPR
review covers: guardian-side personal data (out of COPPA's scope, in of GDPR's), the ADR-018
open decisions (D1-D4), ADR-009's Supabase processor/region language, ADR-014's device-grant
consent model, ADR-016's cross-family disclosure/consent model, and `docs/planning/roadmap.md`
/ `docs/planning/capability-register.md` / `docs/planning/PROJECT-PLAN.md` for what compliance
work is already planned versus built.

The regulatory frame is Regulation (EU) 2016/679 (GDPR) and, where the UK market may be in
scope, the UK GDPR as retained by the Data Protection Act 2018 (materially identical on the
points discussed here). "Absent" means searched for and not found in source, mirroring the
COPPA audit's convention.

---

## 3. Personal data inventory (GDPR scope: guardians *and* children)

GDPR's definition of personal data (Article 4(1): any information relating to an identified or
identifiable natural person) is broader than COPPA's "personal information from a child," so
this inventory adds the guardian-side data the COPPA audit correctly excluded.

### 3.1 Guardian (adult) personal data; new to this review, absent from the COPPA audit's scope

| Data | Where stored | GDPR notes |
|------|--------------|------------|
| Email address | Delegated to Supabase Auth (GoTrue); **not** stored in the application database; the backend persists only an opaque OIDC `authn_subject` (`db/models.py`, per both audits) | Still personal data under Article 4(1) even though CYO Adventure does not hold it directly; Supabase is a processor for it and CYO Adventure remains the controller |
| Family/last name | `family.name` (String200) | Directly identifying |
| Guardian role, admin capability, dual-role flags | `user` table | Identifying + used for access-control decisions about the guardian themself |
| Device grant labels | `device_grant.label`, guardian-set | Potentially identifying (e.g. "Mom's iPad") |
| Consent records for cross-family sharing | `family_connection.consented_by_*_user_id/at` | Personal data about the guardian's own consent choices |

### 3.2 Child personal data

Reuse of the COPPA audit's Section 3.1-3.5 inventory (`request_text`, `proposed_series_title`,
ratings, reading state, completions, `child_profile.display_name`/`age_band`/avatar/TTS
preference, the `child_profile.id` persistent identifier, `reading_state.updated_by_device_id`,
and the `pipeline_event` audit trail) applies unchanged; that audit's citations are accurate as
of this review's commit. One GDPR-specific addition:

- **Special-category-data risk in free text (new observation, not in the COPPA audit).**
  `story_request.request_text` and `concept.brief.premise` are guardian/child-authored free
  text describing "what story do you want" (`story_requests/brief.py`, per the third-party
  data-flow research for this review). GDPR Article 9 treats data revealing health, family
  circumstances tied to a legal/medical condition, or similar as *special category* data with
  a stricter lawful-basis requirement than ordinary personal data. A guardian requesting "a
  story to help my son process his parents' divorce" or "a story about a character who uses a
  wheelchair like my daughter" would put special-category-adjacent content into a
  free-text field with **no field-level flag and no separate consent capture**. As of the Phase
  1 hardening landed in the same pull request as this review (see
  `docs/compliance/coppa-gdpr-remediation-plan.md`), the PII guard also screens every prompt for
  email-, phone-, and street-address-shaped content, not just the registered-name allowlist
  COPPA audit finding M-01 originally described; but that pattern-based screening does not, and
  cannot, detect *semantic* special-category content like "divorce" or "wheelchair" that carries
  no identifying pattern of its own. This residual risk is distinct from COPPA (which has no
  special-category concept) and is not mentioned in the COPPA audit.

---

## 4. GDPR-specific scope questions ADR-018 does not fully resolve

### 4.1 Extraterritorial applicability (Article 3); the gap in D3's framing

ADR-018's D3 ("Launch geography and GDPR-K/AADC applicability," lines 93-100) treats GDPR-K
exposure as contingent on whether the App Store listing includes EU/UK storefronts, with a
"working recommendation" of a US-only storefront to defer GDPR-K as an "expansion gate."

Article 3(2) GDPR does not key off storefront geography. It applies to a controller outside
the EU whenever processing relates to (a) offering goods or services to data subjects in the
EU (whether or not payment is required), or (b) monitoring the behaviour of data subjects in
the EU. A US-only App Store listing is evidence relevant to whether the service is "targeted"
at EU data subjects (language, currency, delivery, marketing), but it is not dispositive, and
it does **nothing** to exclude the *current* private/homelab tier, which has no storefront
gating at all; guardian accounts are provisioned by hand (per the COPPA audit's C-01
evidence), so an EU/UK-resident guardian invited into the current family tier is a real,
present-day GDPR data subject regardless of any future App Store decision. D3's "US-only"
framing is a reasonable simplification for the *public App Store launch* decision but should
not be read as resolving GDPR exposure for the tier that exists today. See Pressure Point P-1.

### 4.2 Controller/processor roles

ADR-009 (`adr-009-supabase-platform.md:222`, per the auth/session research for this review)
calls Supabase "a US processor" without naming a controller. Under GDPR, CYO Adventure (the
operator) is the controller for guardian and child personal data; Supabase, the LLM vendors,
OpenAI Moderation, Google Perspective/Gemini, and Sentry are processors (or, if any of them
uses the data for their own purposes such as model training, potentially independent
controllers for that use; a distinction the "OpenRouter ZDR [zero-data-retention] question"
flagged as ADR-018's "standing Blocker 1" and the COPPA audit's H-04 exists precisely to
resolve, since GDPR's transfer and processor-contract obligations differ sharply between the
two roles). No Data Processing Agreement (Article 28) is confirmed signed with any processor
in either audit's evidence.

### 4.3 Cross-family sharing as a distinct lawful-basis question (ADR-016)

ADR-016's dual-guardian-consented Ring-2 recommendation sharing (confirmed implemented with
real consent-tracking columns and endpoints per the auth/session research: `family_connections.py`,
`recommendations.py`) is a genuinely strong control from a *disclosure* standpoint; better
than most COPPA-only apps build. From a GDPR standpoint it raises a question the ADR does not
address: cross-family disclosure of one family's reading/rating signal to another family is a
new processing purpose (social recommendation) layered on data originally collected for a
different purpose (personal reading tracking). GDPR's purpose-limitation principle (Article
5(1)(b)) and the need for a lawful basis *for that specific disclosure* (the dual-consent UI
that would supply Article 6(1)(a) consent is itself flagged in ADR-016 as "not yet built" per
the auth/session research) mean the consent gate that exists today (an admin-managed
connection table with consent *columns* but no guardian-facing consent *UI*) is a partial,
not complete, basis for this processing.

---

## 5. Requirement-by-requirement assessment

Status legend: **Implemented**, **Partial**, **Not implemented**, **N/A (current tier)**; matching the COPPA audit's convention for direct comparability.

### 5.1 Lawful basis for processing (Article 6)

**Status: Not implemented / not documented.**

No code or planning document records which of the six Article 6 bases (consent, contract,
legal obligation, vital interests, public task, legitimate interests) applies to which
processing activity. The most plausible bases for this product are consent (Article 6(1)(a),
for the guardian, on behalf of the child) for account/profile creation, and contract
performance (Article 6(1)(b)) for delivering the reading service itself; but neither is
recorded anywhere, and Article 6(1)(f) "legitimate interests" cannot lawfully be used as the
basis for processing a child's data for anything beyond what is strictly necessary, per
Recital 38's specific caution about children. This is the same underlying absence as the
COPPA audit's C-01 (no consent code, no signup endpoint gating child-data collection) but the
required remediation artifact is broader: GDPR needs a *documented basis per processing
purpose*, not just a consent checkbox.

### 5.2 Conditions applicable to child's consent (Article 8)

**Status: Not implemented; conceptually simpler than COPPA's VPC but not built.**

As the executive summary notes, this product's actual model; a guardian, never the child,
provisions every profile and holds every credential (confirmed unchanged from the COPPA
audit and the auth/session research: "children never mint their own sessions," device grants
minted only by guardian/admin, no child IdP identity); means Article 8's child-self-consent
threshold (13-16 depending on member state) is largely moot: the *guardian* is the one
consenting to processing of their own data and authorizing processing of their child's, which
is Article 8's own fallback ("consent given or authorized by the holder of parental
responsibility") when a child is below the relevant national threshold, and remains a sound
model regardless of the child's age band because the product design never asks the child to
consent to anything. What is missing, identically to COPPA's C-01, is the actual consent
capture mechanism and a persisted record (method, timestamp, policy version); currently
absent (no consent code in `src/` or `frontend/src/`, `_record_consent()` in `onboarding.py`
confirmed a documented no-op stub per the data-subject-rights research for this review).
GDPR additionally requires "reasonable efforts" to verify the consent-giver holds parental
responsibility (Article 8(2)); a lighter bar than COPPA's VPC methods (card transaction,
ID match, etc.), so whatever P7-02 mechanism the team builds for COPPA's C-01/D1 will very
likely satisfy Article 8(2) as a byproduct, but that should be confirmed with counsel rather
than assumed.

### 5.3 Transparency and information obligations (Articles 12-14)

**Status: Not implemented.**

Identical underlying absence to the COPPA audit's C-02 (no privacy-policy route, no notice
page, `README.md`/`LandingPage.tsx` carry no notice). GDPR's Article 13/14 content
requirements are more prescriptive than COPPA's Section 312.4: identity/contact details of the
controller, the lawful basis for *each* purpose, recipients or categories of recipients
(mapped directly to the processor list in ADR-018 §"already decided" item 6), the
international-transfer mechanism relied on for each non-EEA recipient, the specific retention
period per category (not just "as long as needed"), and the full Article 15-21 rights list
including the right to lodge a complaint with a supervisory authority. A single privacy notice
drafted to satisfy COPPA's 312.4 content list will need materially more content to also
satisfy Articles 13-14; this is worth flagging to whoever drafts D4's public artifacts so the
notice is written once, comprehensively, rather than twice.

### 5.4 Data-subject rights (Articles 15-22)

**Status: Not implemented, and broader than the COPPA audit's C-03/M-05 scope.**

| Right | Article | Status | Note |
|---|---|---|---|
| Access | 15 | Partial (guardian can GET some resources, per COPPA audit §5.3) | No `completion` read endpoint (COPPA M-05); no equivalent for guardian's own data at all |
| Rectification | 16 | Partial | Profile fields are PATCH-able (per profiles.py, both audits); no equivalent for guardian's own Supabase-held data (delegated, would require a Supabase-side flow) |
| **Erasure ("right to be forgotten")** | 17 | **Not implemented** | Same root cause as COPPA's C-03 (no DELETE endpoint, no `ondelete` cascades, per the data-subject-rights research: only admin-config DELETE routes exist) but Article 17 is broader; it applies to *any* data subject's request, not only a parent acting for a child, so guardian-initiated self-erasure is equally unimplemented |
| **Data portability** | 20 | **Not implemented; no COPPA analogue** | No export endpoint exists for guardian or child data (confirmed by the data-subject-rights research: no "export"/"download my data" route anywhere) |
| Restriction of processing | 18 | Not implemented | No "pause processing pending dispute" mechanism (e.g. no way to freeze a profile's data without deleting it) |
| Right to object | 21 | Not implemented | No opt-out mechanism for any processing purpose (most relevant to the Ring-2 recommendation sharing, ADR-016) |
| Automated decision-making safeguards | 22 | **Likely not triggered, worth documenting why** | The moderation/safety pipeline classifies and can block a child's story request or generated content using automated classifiers (OpenAI Moderation, Google Perspective per the third-party-flow research), but the project's own mandatory-human-approval design (ADR-005, referenced in both audits) means no *decision producing legal or similarly significant effects* is made by the automated system alone; a guardian/admin always approves before anything reaches the child. This is a genuine strength and should be recorded as the documented basis for why Article 22 does not require additional safeguards, rather than left implicit. |

### 5.5 Data protection by design and by default (Article 25)

**Status: Substantially implemented in engineering terms; not formally documented as such.**

This is the one section where the review is largely positive. The COPPA audit's Section 7
"Strengths to preserve"; no birthdate/exact age, no photos, no email/phone/address/
geolocation collected from the child, closed-vocabulary avatar, opaque OIDC subject only for
guardians, real JWT/tenancy authorization, the `PiiGuardedProvider` egress chokepoint on the
main generation path, the PII-free-by-allowlist-contract event log, no analytics/ad SDKs; is
precisely the substance Article 25 asks for (data protection built into the architecture, and
privacy-protective defaults). Recommendation: cite this section explicitly in the DPIA (G-04)
and the Records of Processing document (G-03) as the Article 25 evidence base, rather than
re-deriving it from scratch when those documents are drafted.

### 5.6 Records of processing activities (Article 30)

**Status: Not implemented as a discrete document; the raw material exists scattered across
`docs/planning/`.**

No document titled or structured as an Article 30 record exists. The COPPA audit's Section 3
inventory, the third-party disclosure map (Section 4 of that audit), and
`docs/planning/privacy-model.md`'s data-classification section together contain most of the
raw material an Article 30 record needs (categories of data subjects, categories of data,
purposes, recipients, retention, transfers) but it has never been assembled into the single
document Article 30 requires controllers to maintain and produce to a supervisory authority on
request. The Article 30(5) small-organization exemption (fewer than 250 employees) does not
turn on children's data by itself; it is unavailable when the processing is likely to result in
a risk to data subjects' rights and freedoms, is not occasional, or includes Article 9/10
special-category or criminal-offence data. This project's processing of children's data is a
plausible fit for at least the "likely risk" and "not occasional" prongs in practice (regular,
ongoing collection of a child's reading activity and story requests), which is why the
recommendation below stands, but the disqualification is a risk/frequency test, not an
automatic children's-data carve-out. This is a paperwork/synthesis task, not new engineering;
low cost, currently unstarted.

### 5.7 Data Protection Impact Assessment (Article 35)

**Status: Not implemented; this has no COPPA counterpart and is likely mandatory here.**

Article 35(3)(b)'s automatic DPIA trigger is specifically "processing on a large scale of
special categories of data" (Article 9/10): a textual trigger this project meets only if the
special-category risk in Section 3.2 above (health/family-circumstance content in free-text
story requests) is confirmed to occur at scale, which is not yet established. Article 35(1)'s
broader "likely to result in a high risk" standard is a risk-based assessment, not a checklist:
EU supervisory-authority guidance (WP29/EDPB's nine-criteria list) and most member-state DPA
guidance treat "large-scale processing of children's data" and "systematic evaluation including
profiling" (arguably applicable to the moderation/classification pipeline scoring a child's
content) as risk indicators that support a DPIA when several are present together, not as
standalone automatic triggers in every case on their own. Taken together, this project's
combined profile (children's data, profiling-adjacent moderation scoring, and the confirmed
special-category risk in free text) makes a DPIA likely required under the Article 35(1)
risk-based standard even without conceding an Article 35(3)(b) automatic trigger; that
risk-based case, not an automatic-trigger claim, is the basis for the recommendation. No DPIA
exists in `docs/` or `src/`. This is a real gap, distinct from and not curable by anything COPPA
requires, and should be scheduled alongside D1-D4 in ADR-018 rather than treated as a Phase-7
afterthought; a DPIA is often the document that *drives* the consent-mechanism and
retention-policy design choices, not one that follows them.

### 5.8 Security of processing (Article 32)

**Status: Partial; same underlying facts as the COPPA audit's Section 5.5.**

Reuse of COPPA's M-02 (public cover-image bucket, guessable keys), L-02 (`TrustedHostMiddleware`
disabled, HTTPS redirect delegated to proxy), and the "no written information-security program"
observation applies identically under Article 32, which requires "a process for regularly
testing, assessing and evaluating the effectiveness of technical and organisational measures"
;  a written security program is the concrete artifact Article 32(1)(d) is asking for, and its
absence is a GDPR finding in its own right, not just a COPPA one.

### 5.9 International data transfers (Articles 44-49)

**Status: Not implemented; this is a hard blocker distinct from COPPA and larger in scope
than ADR-018's framing suggests.**

**Every** third-party processor in the ADR-018 "named processor list" (Supabase/Postgres,
OpenRouter and downstream model providers, Anthropic-direct, Ollama, OpenAI Moderation, Google
Perspective, Google Gemini, Cloudflare R2, Sentry) is US-headquartered, and the database
connection string confirmed in the auth/session research
(`aws-0-us-east-1.pooler.supabase.com`) places the primary datastore physically in `us-east-1`.
If GDPR applies to any data subject whose data flows through this system (Section 4.1), every
one of these transfers out of the EEA needs a valid Article 44-49 mechanism; Standard
Contractual Clauses (SCCs) with supplementary measures being the most likely fit for a project
this size, since the US does not have a general EU adequacy decision (the EU-US Data Privacy
Framework covers only self-certified participating organizations, and self-certification would
need to be confirmed per-vendor, not assumed). No SCC, adequacy reliance, or transfer
impact assessment is referenced anywhere in `docs/`. This maps directly onto the COPPA audit's
H-04 ("unconfirmed third-party LLM processor terms") and ADR-018's "OpenRouter ZDR question,
standing Blocker 1" but the *legal instrument needed to close it under GDPR* (an SCC annex,
specifically) is not currently on either the COPPA remediation roadmap or ADR-018's D1-D4 list,
and should be added explicitly rather than assumed to fall out of "confirm processor terms."

### 5.10 Data Protection Officer (Article 37)

**Status: Not assessed; flagged as an open question, not a finding of non-compliance.**

Article 37(1)(b)/(c) requires DPO designation where the controller's core activities consist
of processing that requires "regular and systematic monitoring of data subjects on a large
scale," or large-scale processing of special-category data. Whether CYO Adventure's reading-
progress tracking and moderation-classification pipeline meet the "large scale" and "core
activity" thresholds is a fact-and-scale question this static review cannot answer (it depends
on projected user counts at the public-launch tier, not on anything visible in source code).
This should be assessed with counsel once Track 2 launch-scale projections exist, and recorded
in ADR-018 alongside D1-D4 as a fifth open decision if it isn't already implicitly covered by
D4's "owner sign-off" language.

### 5.11 Breach notification (Articles 33-34)

**Status: Not implemented.**

No incident-response or breach-notification runbook exists in `docs/` (searched; only
`SECURITY.md`'s vulnerability-*reporting* policy exists, which is a different document with a
different purpose; how outsiders report a vulnerability to CYO Adventure, not how CYO
Adventure notifies a supervisory authority and affected data subjects after a breach). Article
33's 72-hour notification-to-authority clock and Article 34's "high risk to individuals"
notification-to-data-subject duty both need a defined internal escalation path, an
incident classification rubric, and (per Article 33(5)) an internal breach log; none of which
currently exist. This is the same gap ADR-018's D4 ("breach/incident-response plan") already
names as a Phase 7 deliverable; this review confirms it is still unbuilt as of commit `66fe320`.

---

## 6. Pressure points (open judgment calls, not yet code findings)

These are the places where the right engineering answer depends on a business/legal decision
this review cannot make, listed in the order they should be resolved because later decisions
depend on earlier ones.

**P-1: Does GDPR apply to the *current* private/homelab tier, right now?** (Section 4.1)
This is the single highest-leverage open question. If the current guardian user base is
entirely US-resident, GDPR is a Track-2/public-launch planning concern and the existing
COPPA-first roadmap sequencing is fine. If even one current guardian is an EU/UK data subject,
GDPR obligations (lawful basis, notice, DSAR readiness, transfer mechanism) already apply
today, independent of ADR-018's "launch geography" framing, which only speaks to the *future
public* tier. Recommend: confirm current user residency before treating D3's "US-only"
recommendation as closing this question.

**P-2: Is a DPIA a Phase-7 checklist item, or a Phase-7 *input*?** (Section 5.7)
A DPIA typically should inform consent-mechanism and retention-policy design, not validate
choices already made. If ADR-018's D1 (VPC mechanism) and Phase 7's technical build proceed
before a DPIA is drafted, there is a real risk of building the consent/retention system twice.
Recommend surfacing this to whoever owns ADR-018's D1-D4 sequencing.

**P-3: Which lawful basis for the moderation/classification pipeline's use of a child's raw
free text?** (Sections 5.1, 3.2, and COPPA's H-03) Sending a child's unfiltered story request
to OpenAI Moderation and Google Perspective (confirmed in the third-party-data-flow research:
`moderation/pipeline.py`, bypassing the PII guard applied elsewhere in the same pipeline) is
plausibly justifiable under "necessary for the performance of a contract" or "legitimate
interests in child safety," but Recital 38's caution against relying on legitimate interests
for children's data cuts against the latter, and no basis is currently documented for either.
This is also where COPPA's H-03 and GDPR's Article 9 special-category risk (Section 3.2)
compound: the same unscreened text is the evidentiary basis for both findings.

**P-4: Does the `pipeline_event` audit log's indefinite retention survive an erasure
request?** (G-12) Article 17(3)(b) allows retention despite an erasure request "for compliance
with a legal obligation" or similar exceptions, and a safety/audit log plausibly qualifies; but that is a documented balancing test a controller is expected to perform and be able to
show, not an automatic exemption. No such documented balancing test exists today.

**P-5: Is the PII guard (registered-name matching plus the pattern-based email/phone/address
screening shipped in the same PR as this review, superseding COPPA's M-01 as originally
described) sufficient evidence of "appropriate technical measures" for Article 25/32 purposes,
or does GDPR's broader standard push toward building semantic special-category detection too?**
GDPR does not have a COPPA-style enumerated list of what counts as personal information; its
broader definition (Article 4(1)) makes even the now-expanded guard look thin once the
special-category risk in Section 3.2 (content a pattern can't detect, like "divorce" or
"wheelchair") is factored in. This is a prioritization question for a future hardening pass, not
something this review can resolve on its own.

---

## 7. Findings register

Severity reflects risk **once GDPR applies** (Section 6, P-1) with current-state notes, mirroring
the COPPA audit's convention. Findings with a direct COPPA-audit counterpart are cross-referenced
rather than re-argued.

### G-01. No lawful basis established or recorded for any processing activity (Critical once GDPR applies)

**GDPR**: Article 6, Article 8. **Evidence**: no consent code, no signup endpoint gating
child-data collection (identical evidence to COPPA C-01). **Recommendation**: for each
processing purpose in the eventual Article 30 record (G-03), record the Article 6 basis relied
on; do not default to "legitimate interests" for anything touching a child's data (Recital 38).

### G-02. No verifiable parental/guardian consent mechanism (Critical once GDPR applies)

**GDPR**: Article 8(2). Directly shares root cause and remediation with COPPA's C-01/D1.
**Recommendation**: build the P7-02 consent flow to satisfy both regimes at once; persist
method, timestamp, and policy version, and confirm with counsel that the chosen VPC method also
constitutes Article 8(2) "reasonable efforts."

### G-03. No Records of Processing Activities document (Article 30) (Critical once GDPR applies / low engineering cost)

**Status: DONE.** See `docs/compliance/records-of-processing-activities.md` (remediation plan
Phase 7a).

**Evidence**: no such document exists in `docs/`; raw material scattered across the COPPA
audit, `privacy-model.md`, and ADR-018. **Recommendation**: synthesize one document from
existing sources (Section 5.6); assign an owner alongside ADR-018's D4.

### G-04. No Data Protection Impact Assessment (Article 35) (Critical once GDPR applies)

**Evidence**: none exists; no COPPA counterpart; see Section 5.7 for the risk-based case (not an
automatic Article 35(3)(b) trigger absent confirmed special-category processing at scale).
**Recommendation**: commission a DPIA before, not after, D1's consent-mechanism build (Pressure
Point P-2); use Section 5.5's Article-25 strengths as the starting risk-mitigation inventory.

### G-05. No international-transfer mechanism for any US-hosted processor (Critical once GDPR applies)

**GDPR**: Articles 44-49. **Evidence**: `us-east-1` Supabase hosting confirmed; no SCC/DPF
reliance documented for any of the eight named processors. **Recommendation**: add "execute
SCCs (or confirm DPF self-certification) with every non-EEA processor" as an explicit line
item under ADR-018/Phase 7; do not assume it is subsumed by COPPA's H-04 "confirm processor
terms," since the legal instrument required differs by regime.

### G-06. No data-subject rights implementation for guardian's own data (High)

**Evidence**: same absence of DELETE/export endpoints as COPPA's C-03/M-05, but scoped to the
guardian as a data subject in their own right, not only as the parent exercising a child's
rights. **Recommendation**: ensure the deletion/export build (COPPA Gate 0 items 1-3) covers
"delete my own guardian account and all data about me" as a first-class case, not only "delete
my child's profile."

### G-07. No published privacy notice meeting Articles 12-14's content bar (Critical once GDPR applies)

Shares root cause with COPPA's C-02; GDPR's required content is broader (Section 5.3).
**Recommendation**: draft the D4 privacy notice against the union of COPPA's 312.4 checklist
and GDPR Articles 13-14, once, rather than twice.

### G-08. ADR-018 D3's launch-geography framing does not resolve Article 3(2) extraterritoriality (Pressure point / documentation gap)

**Evidence**: Section 4.1. **Recommendation**: add an explicit note to ADR-018 D3 that "US-only
App Store storefront" addresses the *public launch* decision only, and does not itself answer
whether GDPR already applies to the current private tier's user base (Pressure Point P-1).

### G-09. No breach-notification runbook (High)

**Status: DONE.** See `docs/compliance/breach-notification-runbook.md` (remediation plan Phase 6c).

**GDPR**: Articles 33-34. Shares the "D4 incident-response plan" placeholder with ADR-018 but
confirmed still unbuilt. **Recommendation**: draft an internal breach-classification and
72-hour-notification runbook, distinct from `SECURITY.md`'s external vulnerability-reporting
policy.

### G-10. Cross-family sharing lacks a documented lawful basis for the *disclosure* itself (Medium)

**Evidence**: Section 4.3; ADR-016's consent-column/no-consent-UI gap already flagged in the
auth/session research. **Recommendation**: complete ADR-016's planned guardian-facing consent
UI before treating Ring-2 sharing as GDPR-ready; record Article 6(1)(a) consent as the basis
once that UI exists.

### G-11. No DPO designation analysis performed (Medium)

**Evidence**: Section 5.10; no assessment found in `docs/`. **Recommendation**: assess against
Article 37 once Track 2 scale projections exist; record the outcome (DPO required / not
required and why) in ADR-018 or a successor document.

### G-12. Indefinite `pipeline_event` retention has no documented Article 17(3) balancing test (Medium)

**Status: DONE.** See `coppa-gdpr-remediation-plan.md`'s "4d artifact" section for the documented
balancing test (17(3)(b)/(e), proportionality against the PII-scrubbed-by-contract payload
design, admin-only access).

**Evidence**: confirmed no TTL/purge on `pipeline_event` (data-inventory research for this
review); COPPA's H-01 flags the same table's indefinite retention from a COPPA 312.10 angle.
**Recommendation**: when the retention policy required by both audits is drafted, include an
explicit documented justification for why the audit log is exempted from erasure requests
under Article 17(3), rather than leaving the exemption implicit.

### G-13. Special-category-data risk in free-text story requests (Medium, no COPPA counterpart)

**Evidence**: Section 3.2. **Recommendation**: extend the pattern-based PII detection shipped in
this PR to also flag likely special-category content (health, family-circumstance language) for
additional handling, or at minimum document the residual risk and decide whether Article 9's
stricter basis requirement is triggered in practice.

---

## 8. How this integrates with the existing COPPA-first roadmap

The COPPA audit's Section 8 "Prioritized remediation roadmap" (Gate 0/1/2) already sequences
the majority of the engineering work both regimes need: consent, notice, deletion, retention,
processor-terms confirmation. This review's recommendation is **not** a parallel roadmap; it
is a set of additions and content changes to that same roadmap:

- **Gate 0 (before any public/non-family exposure)**: keep COPPA's four items; add G-05
  (execute SCCs, not just "confirm terms") and G-04 (commission the DPIA *before* building D1's
  consent mechanism, per Pressure Point P-2, i.e. potentially resequence ahead of the existing
  Gate 0 item 1).
- **Gate 0 content changes**: when drafting the privacy notice (COPPA item 2 / this review's
  G-07) and the consent flow (COPPA item 1 / this review's G-02), write to the union of both
  regimes' content requirements the first time.
- **New, GDPR-only items with no COPPA equivalent**: G-03 (Records of Processing document),
  G-04 (DPIA), G-05 (transfer mechanism), G-11 (DPO assessment); none of these are satisfied
  by anything on the COPPA roadmap and should be added explicitly, ideally as line items under
  ADR-018's D1-D4 or as a D5.
- **Resolve first, before scoping further**: Pressure Point P-1 (does GDPR already apply to
  the current tier); this determines whether any of the above is urgent now or can wait for
  Track 2 planning.

---

## 9. References

- Regulation (EU) 2016/679 (GDPR); UK GDPR / Data Protection Act 2018 where the UK market may
  be in scope.
- Article 29 Working Party / European Data Protection Board guidance on DPIA trigger criteria
  (WP248 rev.01) and on children's data (relevant to Section 5.7's "large scale" analysis).
- `docs/compliance/coppa-compliance-audit.md` (this review's primary evidentiary source for
  facts shared between the two regimes).
- `docs/planning/adr/adr-018-childrens-privacy-compliance.md` (open decisions D1-D4).
- `docs/planning/adr/adr-008-public-app-store-launch.md`, `adr-009-supabase-platform.md`,
  `adr-014-device-authorized-kid-access.md`, `adr-016-recommendation-sharing-social-boundary.md`,
  `adr-017-ai-cover-art.md`.
- `docs/planning/privacy-model.md`, `docs/planning/capability-register.md` (S10, G11, G12,
  A14), `docs/planning/PROJECT-PLAN.md` (Phase 7).

*End of review. This document records observed data practices and planning-document content at
commit `66fe320` and is a point-in-time engineering assessment, not legal advice or a
certification of compliance.*
