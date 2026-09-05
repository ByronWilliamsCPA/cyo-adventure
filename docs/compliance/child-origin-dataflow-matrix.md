---
title: "Child-Origin Dataflow Matrix"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "One definitive record of every event a child triggers in the kid-facing app, traced from the API call to the storage row to (where it happens at all) the third-party recipient, with vendor purpose, retention, training posture, COPPA personal-information classification, disclosure classification, and consent consequence for each."
tags:
  - compliance
  - privacy
  - security
component: Development-Tools
source: "Direct review of src/cyo_adventure/api, src/cyo_adventure/db/models.py, src/cyo_adventure/events, frontend/src/offline, frontend/src/player at commit 65883a1 (2026-08-08), synthesizing docs/planning/privacy-model.md (v0.3), docs/planning/adr/adr-016-recommendation-sharing-social-boundary.md, docs/planning/adr/adr-017-ai-cover-art.md, docs/planning/adr/adr-018-childrens-privacy-compliance.md (amended 2026-08-01), and docs/compliance/records-of-processing-activities.md, processor-dpa-checklist.md, coppa-compliance-audit.md (commit c9dbfa9, 2026-07-10), coppa-gdpr-remediation-plan.md, gdpr-compliance-review.md"
---

> **Status**: Draft | **Version**: 2.1 | **Compiled**: 2026-08-08 | **Updated**: 2026-09-05 (Perspective leg retired; see the dated callouts)
> **Code reviewed at**: commit `65883a1` on the feature branch for the original authoring; re-verified
> at the merge of `main` (13 commits, including PR #643 and PR #649) for this revision, 2026-08-09
> **Scope**: `src/cyo_adventure/api/`, `src/cyo_adventure/db/models.py`, `src/cyo_adventure/events/`,
> `src/cyo_adventure/story_requests/`, `src/cyo_adventure/moderation/`, `src/cyo_adventure/generation/`,
> `src/cyo_adventure/covers/`, `src/cyo_adventure/core/observability.py`,
> `src/cyo_adventure/characters/`, `src/cyo_adventure/storybook/personalization_values.py`,
> `frontend/src/offline/`, `frontend/src/player/`, `frontend/src/characters/`,
> `frontend/src/reader/characterSeed.ts`

## 0. Important disclaimer

This is an engineering-derived record, not legal advice. The survey below is stated exhaustively
because a partial one invites the reader to generalize from it. Of the eleven sibling documents in
this directory, **four** state a comparable disclaimer in their own words: `coppa-compliance-audit.md`,
`gdpr-compliance-review.md`, `coppa-gdpr-remediation-plan.md`, and `data-retention-policy.md` (the
last added by PR #643). Their wordings differ materially, so what is shared is the posture and not a
sentence; an earlier revision of this paragraph said the disclaimer was carried "verbatim", which is
not the case. The remaining **seven** carry none, for two distinct reasons. `privacy-notice.md` and
`dpia.md` are drafted as counsel-review deliverables, guardian-facing notice text and an Art. 35
assessment respectively, and carry a DRAFT status caveat in place of a disclaimer.
`breach-notification-runbook.md`, `counsel-engagement-brief.md` (added by PR #643),
`information-security-program.md`, `processor-dpa-checklist.md`, and
`records-of-processing-activities.md` state neither.
Several rows below cite `coppa-compliance-audit.md` (dated 2026-07-10), which predates the ADR-018
consent implementation (2026-07-20) and the D5 AI-training amendment (2026-08-01). Where a newer
document supersedes an older finding this record says so and cites both. Two conflicts between
project documents that this matrix originally flagged as unresolved (cover-art PII screening,
Sentry wiring status) have since been checked directly against current code and resolved: see
[Section 5](#5-resolved-conflicts). Neither resolution changes Section 1's open-blocker flag on
Event 6 (the classifier leg, ADR-018 Blocker 1b), which is a separate, still-genuinely-open item.

**Revision note (2026-08-09).** This matrix was authored on a branch that fell 13 commits behind
`main`, missing PR #643 (which corrected ADR-018's D1 description, among other things) and PR #649
(persistent reader characters, which added a second child free-text field this matrix's original
"one free-text field" framing missed entirely). A maintainer review caught both, plus several wrong
or drifted `file:line` citations and a locally-invented processor/recipient taxonomy that did not
match how COPPA or GDPR actually categorize third parties. This revision merges `main` and corrects
all of it; see the per-section notes below for what changed and why, rather than silently rewriting
history.

This matrix, together with `docs/security/assurance-register.md` (a broader, project-agnostic
17-category control-and-obligation catalog), was checked 2026-08-08 against GDPR, GDPR-K, COPPA,
and applicable US state law for whether enough is captured to *monitor* what is collected and how
it is used, not only to describe it once. That verification found the event/vendor-level analysis
in this matrix substantially sufficient, but found no operating mechanism that keeps either document
current as code changes (the register's own reassessment trigger, O-70, and quarterly state-law
refresh, O-108, are both specified and unbuilt), and found two regulatory areas absent from both
documents at the time: GDPR Article 8's per-member-state child-consent age, and US state sectoral
security law. Both gaps have since been closed in `assurance-register.md`: O-120 plus two
not-applicable determinations (NYDFS Part 500, California SB-327) for the state-sectoral-security
family, and O-121 for GDPR Art. 8's member-state child-consent-age table, recorded now (low
urgency while GDPR has not attached, US-only per the register's T4 determination) rather than left
silently absent. Recording a gap is not the same as closing it operationally: every row this update
touches still carries `Phase home: unassigned` in the register's own accounting, so "recorded" means
the register now names what should exist, not that it exists yet.

An interactive version of this record (sortable summary table, per-event cards) was also published
as a Claude Artifact during authoring; this markdown file is the durable, versioned copy and is the
one to keep current.

---

## 1. Quick reference

Ten child-originated events (nine in this matrix's original scope, plus Event 10, added in this
revision after PR #649 shipped a second child free-text field the original enumeration missed),
scanned for the three questions that matter first: does the child type free text, does the data
reach a third party, and is anything about it still an open compliance item. The infra and vendor
columns below track whether a payload crosses to a party outside CYO at all; Section 2's per-vendor
COPPA-activity/GDPR-role tags carry the finer question (service-provider/processor versus a
disclosure requiring separate consent), which does not collapse to a single "Yes/No" column because
it can differ by vendor and has not been fully determined for several of them. Every row in this
table, including every "No" / "None" row, is Supabase-hosted on the public tier; that is a single
fact true of the whole matrix, stated once in [Section 4](#4-cross-cutting-notes) and in the
[Supabase vendor entry](#supabase-auth-and-primary-postgres-public-tier) rather than repeated on all
ten rows, where it would carry no differentiating information.

| # | Event | Child free text? | COPPA PI | Reaches a third party? | Vendors touched | Status |
| --- | ------- | ------------------- | ---------- | -------------------- | ------------------ | -------- |
| 1 | Starting a kid session (profile pick / device pickup) | No | Behavioral / identifier | No | None | Internal only |
| 2 | Choosing a branch (in-story choice) | No | Behavioral / identifier | No | None | Internal only |
| 3 | Resuming / saving progress (incl. offline sync) | No | Behavioral / identifier | No | None | Internal only |
| 4 | Rating a story | No | Behavioral / identifier | No | None | Internal only |
| 5 | Flagging content | No (closed enum only) | Behavioral / identifier | No | None | Internal only |
| 6 | Typing a story wish (child-initiated request) | **Yes**, one of two free-text fields | **Yes, potentially direct** | **Yes** | OpenAI Moderation, OpenRouter (+ sub-processors) / Anthropic (direct, no sub-processors); Google Perspective until 2026-08-26 (leg retired, PR #764) | **Open blocker (1b); Perspective finding (C1) historical as of 2026-08-26** |
| 7 | Reaching an ending (completion) | No | Behavioral / identifier | No | None | Internal only |
| 8 | Active reading time (background flush) | No | Behavioral / identifier | No | None | Internal only |
| 9 | Appearing in a cousin's feed (ring-2 recommendation, derived from #4) | No | Display name + rating, cross-household | No (CYO-to-CYO, not a vendor) | None | Consent-gated, dual-guardian |
| 10 | Creating a character (naming, PR #649) | **Yes**, the other of two free-text fields | **Yes, potentially direct** | No | None | Internal only; server-side denylist, never reaches a model provider |

Every event below is gated upstream by the same fact: none of it can occur without a guardian first
completing verifiable parental consent at onboarding ([D1](#d1-verifiable-parental-consent), see
Section 6). Refusal means the child profile is never created, so no row in this matrix is reachable.
What differs per event is what happens after that gate.

---

## 2. Vendor register

Every third party that can receive data derived from a child event, normalized once here so the
event matrix in Section 3 can reference it by name instead of repeating it. "DPA executed" reflects
`processor-dpa-checklist.md`, dated 2026-07-20 and not yet re-confirmed.

**Correction (2026-08-09).** This section originally sorted vendors into "independent-use
recipient" versus "CYO's own infrastructure processor," a distinction invented for this document
rather than drawn from either regulatory framework, and it was internally inconsistent: the
OpenRouter/Anthropic entries describe a no-training, zero-data-retention posture (data used to
provide the generation service, not for the vendor's own purpose) while Section 1's summary column
still counted them as "vendors touched" under a rule ("processes the data for its own purpose")
that its own row contradicts. Replaced with the two frameworks that actually apply:

- **COPPA (16 CFR 312.2, 312.5(a)(2)).** COPPA does not sort by "independent use." It asks whether
  sending data to a party is a *disclosure* at all: a party that receives PI "solely to provide a
  support service internal to the operation of the [service]," does not use it for any other
  purpose, does not disclose it further, retains it no longer than necessary, and is contractually
  bound to the same protections falls under the internal-operations exception, and sending data to
  it is not itself a COPPA disclosure requiring separate parental consent. A party that does not
  meet all of those conditions (including one that may use the data for its *own* purposes, such as
  model improvement) receives a genuine disclosure, and 312.5(a)(2) requires the parent be given
  "the option to consent to the collection and use of the child's personal information without
  consenting to disclosure ... unless such disclosure is integral to the [service]." Each vendor
  entry below states which side of that line it falls on, and whether that determination has
  actually been made (most have not).
- **GDPR (Art. 4(7)-(8), Art. 28).** GDPR sorts by controller versus processor: a processor acts
  only on the controller's documented instructions, under a data processing agreement; a party that
  determines its own purposes for any of the data (common for AI vendors' trust-and-safety /
  legal-compliance processing, which several reserve as independent controllership in their own
  terms, distinct from the processing they do on a customer's instructions) is, for that slice of
  processing, an independent controller, not a processor. Each entry below states which posture the
  vendor's own published terms claim, where confirmed.

Neither framework is "internal infrastructure versus everyone else." Supabase, for instance, is a
processor under GDPR and (once a DPA is executed) inside COPPA's internal-operations exception for
the same reason any hosting processor is: it acts on CYO's instructions, for CYO's purpose, under
contract. It is grouped separately below only because, unlike every other row, it hosts the primary
datastore rather than receiving a specific payload per event; see its own entry for why it is not
repeated per event in Section 3.

### OpenAI Moderation (Stage-0 safety classifier)

- **Purpose**: scores child-typed wish text at intake and every generated story node during
  moderation, as the first-line safety filter ahead of guardian/admin review.
- **What it receives**: raw request text at screening, after the local PII allowlist has already
  blocked a name match; every generated node's prose during moderation. No `profile_id` /
  `family_id` / name accompanies either call; content only.
- **Retention**: 30-day API data retention by default, per OpenAI's own data-controls
  documentation, not the DPA (the two are separate documents; this figure has previously been
  misattributed to the DPA in this project's own records). `/v1/moderations` is separately
  documented by OpenAI as storing no logs for abuse-monitoring purposes, a narrower and more
  favorable claim than the general 30-day figure; which one actually governs this integration is
  unconfirmed.
- **Training permitted**: not confirmed in an executed contract; API-tier traffic is excluded from
  training under OpenAI's standard API terms, but that protection is only as good as confirming
  this account sits on those terms.
- **COPPA activity / GDPR role**: not yet determined against 312.2's internal-operations exception
  (does OpenAI use this content for any purpose beyond providing the moderation call, and is it
  contractually bound not to) or against GDPR's controller/processor split; see the framework note
  above. Undetermined, not assumed either way.
- **Status**: DPA not executed; COPPA PI on the wish leg.

### Google Perspective (Stage-0 toxicity classifier)

> **Update 2026-09-05 (issue #659)**: this leg no longer exists in the live gate. PR #764
> (`b2273a7`, merged 2026-08-26) retired Perspective as a Stage-0 signal source:
> `moderation/classifiers.py` no longer defines `_run_perspective`, `run_classifiers` takes no
> `perspective_key`, and neither `story_requests/screening.py` nor `api/node_edit.py` can send a
> child's text to Google. The only remaining caller of Perspective's endpoint is the offline
> calibration script `scripts/capture_stage0_baseline.py`, which sends catalog prose (never child
> free-text) and now sets `doNotStore: true`, pinned by
> `tests/unit/test_capture_stage0_baseline.py::test_perspective_request_opts_out_of_storage`.
> The finding below is therefore **historical**: it describes what was disclosed to Google before
> 2026-08-26 and remains relevant to data-subject requests covering that period, not to current
> flows. Section 6's D5 entry is corrected in the same way.

- **Purpose** (historical): toxicity/safety scoring, parallel to OpenAI Moderation, same two call sites (intake
  screening, per-node moderation).
- **What it receives**: same content pattern as OpenAI Moderation, including the child's own raw
  wish text at the screening call site. Separately flagged for a sunset/replacement effort
  ("Stage-0 Perspective sunset work") in progress per the source docs.
- **Retention and training: confirmed and adverse, not "unconfirmed."** Verified directly in code:
  `moderation/classifiers.py::_run_perspective` posts `{"comment": {"text": prose}, "languages":
  [...], "requestedAttributes": {...}}` to Perspective's `comments:analyze` endpoint with **no
  `doNotStore` field set**. Google's own API documentation defines the omission: unset, the service
  "may store comments/context for debugging purposes," and Perspective's own documentation states
  stored comments "will be used for future research and community model building purposes,"
  naming the exact trigger case this integration hits: "This should be set to true if data being
  submitted is private ... or if the data submitted contains content written by someone under 13
  years old." The screening call site sends a child's own typed wish text through exactly this
  unset-flag path.
- **COPPA activity / GDPR role: reclassified by this finding, not merely unconfirmed.** Storage for
  "future research and community model building" is use for Google's own purpose, which defeats
  312.2's internal-operations exception (whose proviso forbids use "for any other purpose"); on
  these facts this leg is a disclosure, engaging 312.5(a)(2)'s separate-consent-option requirement
  and 312.4(c)(1)/(d)'s notice content, not merely a service-provider call. Under GDPR, storing
  content "for future research" for Google's own purposes is inconsistent with acting solely as a
  processor on CYO's documented instructions.
- **Code fix is out of scope for this document** (set `doNotStore: true` in the request body) and is
  tracked as **issue #659**, which also asks for a unit test asserting the flag is present in the
  posted request body (asserting on the response would prove nothing about what was sent) and a RAD
  marker at the call site, so a later refactor cannot drop the field as apparent noise. This entry's
  job is to describe current behavior accurately, not to resolve it. See
  [D5](#d5-ai-training-consent-segregation) and Event 6's consent-consequence field, both of which
  this finding directly contradicts as previously written.
- **Status**: confirmed adverse default (no `doNotStore`), tracked as #659; DPA coverage separately
  unconfirmed; COPPA PI on the wish leg.

### OpenRouter (+ AWS Bedrock / Azure / Vertex sub-processors), generation leg (routed)

- **Purpose**: turns the approved concept brief (the wish, de-identified) into story prose. Bedrock,
  Azure, and Vertex are sub-processors OpenRouter routes to for the respective model families since
  the 2026-07-28 ZDR toggle change.
- **What it receives**: a brief with a fictional protagonist name, coarse age band, guardian-set
  banned themes and flag caps, and the child's free-typed premise text carried through verbatim but
  identifier-free; `assert_prompt_pii_safe` hard-fails the job rather than redacting.
- **Retention**: Zero Data Retention enforced by a dedicated workspace guardrail (a dated
  configuration snapshot, not a signed contract) across this routing surface. **This is narrower
  than it sounds.** The ZDR toggle selects which providers/endpoints are *eligible* to receive
  routed traffic; OpenRouter's own published ZDR documentation is explicit that this eligibility
  toggle is a routing-layer control, and OpenRouter's own retention/use of the prompt data that
  transits its infrastructure is governed separately by OpenRouter's own policies (OpenRouter states
  it does not retain prompts unless the account opts into prompt logging, which is a separate
  setting from the per-provider ZDR eligibility toggle this guardrail configures). Do not read the
  ZDR guardrail as a single control that also settles OpenRouter's own handling of the data; it does
  not, and that is a separate line item this row has not previously carried.
- **Training permitted**: No, for the routed providers this guardrail selects. The guardrail
  disables all three data-training paths (paid-trains, free-trains, free-publishes-prompts) for
  those providers. Whether OpenRouter itself trains on or otherwise uses transiting prompt content
  is the separate question above, not settled by this toggle.
- **COPPA activity / GDPR role**: presented as a processor under commercial API terms (data used to
  provide the generation service on CYO's instructions), consistent with the identifier-free,
  no-training posture above; not independently confirmed against an executed DPA.
- **Status**: training disabled by guardrail for routed providers; OpenRouter's own retention
  practice is a separate, not-yet-examined line item; identifier-free but not PII-free; DPA not
  executed.

### Anthropic (direct), generation leg (admin-selectable, bypasses guardrail)

- **Purpose**: same generation role as OpenRouter, dispatched when `generation_provider="anthropic"`.
  A separate, built code path.
- **What it receives**: the same PII-guarded brief as the OpenRouter leg.
- **Retention**: not covered by the OpenRouter workspace guardrail. This leg is a distinct, direct
  integration. Anthropic's own published retention practice (covered models, effective 2026-06-09):
  prompts and outputs are retained 30 days by default to support safety work, deleted automatically
  after that **except** when flagged by automated trust-and-safety systems as a Usage Policy
  violation, in which case inputs and outputs are retained for up to 2 years and the trust-and-safety
  classification scores for up to 7 years. This is materially adverse for a pipeline that
  deliberately routes child-derived content past safety classifiers as a matter of design (Event 6):
  a flagged generation on this leg does not fall under the 30-day default at all. Whether this
  account sits on Commercial ToS (which carries the DPA) or a different tier is unconfirmed.
- **Training permitted**: not confirmed for this leg specifically; the ZDR/no-training guardrail is
  scoped to the OpenRouter route only and does not reach this leg at all.
- **COPPA activity / GDPR role**: undetermined; the 2-year/7-year flagged-content retention above
  is itself relevant to whether this leg still qualifies as "retains no longer than necessary" under
  COPPA's internal-operations exception, and has not been assessed against that standard.
- **Status**: outside the ZDR guardrail; 30-day default does not cover flagged content (up to 2/7
  years); account tier unconfirmed.

### Google Gemini ("nano banana"), cover-art generation

- **Purpose**: admin-triggered AI cover art per storybook version, from a metadata-derived prompt
  (ADR-017).
- **What it receives**: title, protagonist name (recovered from `concept.brief`), themes, a
  240-character prose excerpt, and age band (`covers/prompt.py::build_cover_prompt`), **screened by
  the PII guard before dispatch**. Verified directly in code: `covers/service.py:243-254` recovers
  the owning concept's protagonist name and family id, builds the prompt, then calls
  `assert_prompt_pii_safe(prompt, forbidden=pii)` against the family's registered child display
  names before the Gemini call. This resolves the conflict previously recorded here; see Section 5,
  which now records the resolution rather than an open disagreement.
- **Retention**: determined by paid versus unpaid API tier, per Google's own Gemini API Additional
  Terms of Service. Paid tier: Google logs prompts/responses for a limited period solely to detect
  Prohibited Use Policy violations, and does not use content to improve products. Unpaid (free
  Google AI Studio) tier: Google uses submitted content to improve products, including for
  machine-learning purposes, and human reviewers may annotate inputs and outputs. Which tier this
  integration is configured on is unconfirmed and is the load-bearing fact for this row.
- **Training permitted**: **No on paid tier, yes on unpaid tier** (see Retention). Not "unconfirmed"
  in the abstract; it is a determinate fact this project has not yet checked its own account
  configuration against. The same terms also require API users to be 18 years of age or older,
  which this integration satisfies by design (admin-triggered only, never child- or
  guardian-triggered).
- **COPPA activity / GDPR role**: undetermined pending the tier confirmation above; the answer
  differs materially between tiers (processor-like on paid, independent-use on unpaid).
- **Status**: PII-guarded (verified 2026-08-08); training posture is tier-dependent and the tier is
  unconfirmed; DPA not yet executed.

### Cloudflare R2, cover-image object storage

- **Purpose**: stores WebP-optimized cover art. Storage only, not a model or classifier.
- **What it receives**: image bytes only. Per the RoPA (2026-07-20), access is private with
  presigned-URL delivery as of Phase 1d, superseding an earlier finding that the bucket was public
  with guessable keys.
- **Retention**: life of the storybook version.
- **Training permitted**: N/A, storage vendor, not a model provider.
- **COPPA activity / GDPR role**: a processor by design (object storage under CYO's instructions,
  no independent use of the bytes); not yet confirmed against an executed DPA.
- **Status**: private / presigned as of Phase 1d; DPA not executed.
- **Why it appears here despite no Section 3 event naming it**: cover-art generation (the event that
  sends data to R2 and to Gemini above) is admin-triggered, not child-triggered, so it falls outside
  this matrix's own child-originated-event scope and has no Event row of its own. Both vendors are
  listed anyway because the cover prompt derives from story content that is, several steps upstream,
  built from a child's own wish (Event 6); this register does not claim either vendor is the direct
  recipient of any child-originated event's payload, only that they sit downstream of one.

### Supabase, auth and primary Postgres (public tier)

- **Purpose**: identity provider for guardians (children never hold a Supabase identity) and, on
  the public tier, host of the Postgres database every "internal only" row in Section 3 actually
  lives in.
- **What it receives**: guardian auth identity directly; every child-linked table in this matrix
  indirectly, as the datastore itself, once the public tier is live.
- **Retention**: life of the account/record, per this project's own retention table (Section 4).
- **Training permitted**: N/A, infrastructure processor, not a model vendor.
- **COPPA activity / GDPR role**: a processor under both frameworks by design, the clearest case in
  this register: it acts solely on CYO's instructions, for CYO's purpose, with no independent use of
  the data. Not yet confirmed against an executed DPA.
- **Status**: processor of record for everything this matrix calls "internal only"; DPA not
  executed. Deliberately **not** repeated in each event's "Third-party recipients" field in
  Section 3: it is a constant fact true of every row on the public tier, not a differentiating one,
  and listing it ten times would not tell a reader anything Section 1's scope note and this entry
  do not already say once. Treat every "Third-party recipients: none" in Section 3 as "no third
  party outside a service-provider/processor role"; Supabase is implied throughout, not omitted.

### Sentry, error telemetry (cross-cutting, not event-specific)

- **Purpose**: exception monitoring, hardcoded by design to exclude child-linked content;
  correlation IDs only, no reading-state snapshots.
- **What it receives**: incidental only, if any event above throws an exception mid-request, and
  only when a DSN is configured (see Status). Integration is verified in code:
  `core/observability.py::init_sentry`, called from `app.py:616`, wraps `sentry_sdk.init(...)` with
  `send_default_pii=False` on every call path, asserted by
  `tests/unit/test_observability.py::TestInitSentryDisablesPii::test_init_sentry_never_sends_pii`
  (corrected citation; the function name previously cited here,
  `test_init_sentry_disables_pii`, does not exist in the test file).
- **Retention**: per Sentry's platform default; not independently confirmed.
- **Training permitted**: N/A.
- **COPPA activity / GDPR role**: a processor by design and by the no-child-PII contract asserted in
  code; not yet confirmed against an executed DPA.
- **Status**: integration exists in current code (`sentry-sdk>=2.66.0` dependency, `pyproject.toml`)
  and is a documented no-op unless `SENTRY_DSN` is set (`core/config.py:953`, unset by default in
  `.env.example`). Resolves the conflict previously recorded here; see Section 5.

---

## 3. Event-by-event matrix

Ten data points per event (the user's original ten: child-originated data, identifiers attached,
CYO storage, third-party recipients, vendor purpose, vendor retention, training permitted, COPPA
PI, disclosure classification, consent consequence), presented as eight numbered fields: vendor
purpose, retention, and training-permitted are combined into one field per event ("Vendor purpose /
retention / training") because that information belongs to the *vendor*, not the event, and is
recorded once per vendor in Section 2 rather than repeated with each event that touches it.
What the child sends, what gets attached to it, where it lands, who outside CYO ever sees it, and
what a consent decision actually controls. As in Section 1, "Third-party recipients" here means a
party outside CYO in the sense Section 2's framework note defines; Supabase hosts every row as
CYO's own infrastructure processor and is covered once in Section 2 and Section 4, not repeated per
event.
Citations are `file:line` against the current backend/frontend tree.

### Event 1: Starting a kid session

1. **Child-originated data**: none as free text. The trigger is `POST /api/v1/child-sessions`
   (`child_sessions.py:60-63`), minted by a guardian, admin, or an already-authorized device grant,
   never by the child itself. Payload is `profile_id` plus an optional picker PIN
   (`child_sessions.py:63,168-181`).
2. **Identifiers attached**: `family_id` resolved from the target `ChildProfile`
   (`child_sessions.py:196`); a JIT `User` row keyed `child-profile:{profile_id}` so the minted
   token embeds a real user id (`child_sessions.py:246-252`). A parallel device grant carries
   `family_id`, `authorized_by` (the guardian who minted it), and a `jti`
   (`device_grants.py:104-121`).
3. **CYO storage**: `User` table (JIT row) and `DeviceGrant` table (`device_grants.py:115-121`).
   The session token itself is a bearer JWT, not persisted. Frontend mirrors the device grant into
   the `device_grant` IndexedDB store (`offline/db.ts:9-14,474-490`).
4. **Third-party recipients**: none. Purely internal auth/session issuance.
5. **Vendor purpose / retention / training**: N/A, no vendor involved.
6. **COPPA personal information?**: behavioral / identifier-linked, not directly collected from the
   child in this step; the profile the session attaches to is itself guardian-created.
7. **Disclosure classification**: not a disclosure; internal session issuance only.
8. **Consent consequence**: downstream of D1 only; no profile exists to open a session for without
   prior guardian consent at onboarding.

### Event 2: Choosing a branch

1. **Child-originated data**: no dedicated "make a choice" endpoint exists; a choice is applied
   client-side (`frontend/src/player/engine.ts`, mirrored server-side for replay validation only at
   `player/engine.py:142-180`) and persisted as the resulting state via
   `PUT /api/v1/reading-state/{profile_id}/{storybook_id}` (`reading.py:622-639`): `current_node`,
   `var_state`, `path`, `visit_set`, `save_slots`. No free text; node ids and variable values only.
2. **Identifiers attached**: `child_profile_id` from the authenticated path, authorized via
   `authorize_profile` (`reading.py:669-670`); optional client-supplied `device_id` and idempotency
   `event_id` (`reading.py:883-884`). The server re-validates the full state against the pinned
   story graph before accepting it, so a forged node/path is rejected (`reading.py:458-467`).
3. **CYO storage**: `ReadingState` table, PK `(child_profile_id, storybook_id)`, cascade-deleted
   with the profile (`db/models.py:1480-1538`); mirrored offline in IndexedDB's `reading_states`
   store (`offline/db.ts:131,154-156,425-442`).
4. **Third-party recipients**: none. This event does not write to the append-only `pipeline_event`
   log either; only ratings, flags, and requests do.
5. **Vendor purpose / retention / training**: N/A.
6. **COPPA personal information?**: yes, in COPPA's broad sense; behavioral data tied to a
   persistent child identifier (`child_profile_id`) counts as personal information even though the
   node ids themselves carry no semantic content about the child.
7. **Disclosure classification**: no disclosure; internal processing only.
8. **Consent consequence**: gated only by D1 at the profile level; no per-event consent exists or is
   needed since nothing leaves CYO.

### Event 3: Resuming / saving progress (incl. offline sync)

1. **Child-originated data**: `GET /api/v1/reading-state/{profile_id}/{storybook_id}` to resume
   (`reading.py:470-475`); the same `PUT` body as Event 2 to save, including when replayed from the
   offline queue (`frontend/src/offline/sync.ts::saveProgress`, `sync.ts:206-276`, and
   `replayQueue`, `sync.ts:351-401`).
2. **Identifiers attached**: same as Event 2, plus an optimistic-concurrency `state_revision` that
   prevents one device's save from silently clobbering another's (`reading.py:622-634,780-783`); a
   conflict returns the server's current row for client-side reconciliation rather than accepting a
   stale write.
3. **CYO storage**: same `ReadingState` row as Event 2, plus the IndexedDB `offline_queue` store
   (keyed by `event_id`) that holds unsent writes on the device
   (`offline/db.ts:130-143,456-472`).
4. **Third-party recipients**: none.
5. **Vendor purpose / retention / training**: N/A.
6. **COPPA personal information?**: same classification as Event 2; persistent-identifier-linked
   behavioral data.
7. **Disclosure classification**: no disclosure.
8. **Consent consequence**: same as Event 2. **Corrected 2026-08-09**: this entry previously named
   `GET /reading-history/{profile_id}` and `GET /families/me/reading-summary` (counts and
   timestamps only, "never reading content") as satisfying the guardian's COPPA 312.6(a) access
   right. That claim contradicted this matrix's own field 6 above, which classifies `current_node`,
   `path`, `visit_set`, and `var_state` as personal information: 312.6(a) requires "a means of
   reviewing any personal information collected from the child," and a counts-and-timestamps summary
   does not review that content. The actual 312.6(a) mechanism is `GET /api/v1/me/export`
   (`me.py:330-331`), which returns the full `ReadingState` row including `current_node`
   (`me.py:159`) per profile; the reading-history/reading-summary endpoints serve a different
   purpose (a guardian engagement dashboard) and are not the access-right mechanism.

### Event 4: Rating a story

1. **Child-originated data**: `POST /api/v1/ratings` (`ratings.py:49-57`): `profile_id`,
   `storybook_id`, `value` (integer 1-5, DB-constrained). No free text.
2. **Identifiers attached**: `child_profile_id` via `authorize_profile` (`ratings.py:69-70`); the
   event log stamps `actor_id` / `actor_role` from the authenticated principal (`ratings.py:124`).
3. **CYO storage**: `Rating` table, PK `(child_profile_id, storybook_id)`, cascade
   (`db/models.py:1568-1599`). Also writes `pipeline_event`: `entity_type="rating"`,
   `event_type=RATED`, payload restricted to `{value, is_update}` by allowlist
   (`ratings.py:122-129`, `events/writer.py:50`); no story or profile id inside the payload itself,
   those live in dedicated columns.
4. **Third-party recipients**: none directly. The rating value is later read (not sent externally)
   by `GET /api/v1/recommendations/{profile_id}` to build same-family and connected-family
   recommendation feeds; see Event 9. That remains internal to CYO's own database throughout.
5. **Vendor purpose / retention / training**: N/A.
6. **COPPA personal information?**: yes; behavioral data tied to a persistent child identifier.
7. **Disclosure classification**: no third-party disclosure. Internal cross-household exposure is
   possible downstream (Event 9) under its own consent gate.
8. **Consent consequence**: D1 only, for the rating itself. Whether the rating (and the display
   name attached to it) can surface to a different family is a separate, additional consent; see
   Event 9.

### Event 5: Flagging content

1. **Child-originated data**: `POST /api/v1/flags` (`flags.py:101-103`): `profile_id`,
   `storybook_id`, `version`, `reason`, a closed vocabulary (`did_not_like`, `scared_me`,
   `confusing`, `db/models.py:2556`), optional `node_id`. Schema explicitly forbids extra fields, so
   no free-text escape hatch exists here (`flags.py:8`).
2. **Identifiers attached**: `family_id` denormalized from the profile (`flags.py:156`); actor
   stamped from the principal (`flags.py:173`).
3. **CYO storage**: `KidFlag` table (`db/models.py:2560`). Event log: `entity_type="kid_flag"`,
   `event_type=KID_FLAGGED`, payload allowlisted to `{reason, storybook_id}`; `node_id` is stored on
   the row but deliberately excluded from the event payload (`flags.py:165-178`,
   `events/writer.py:54`).
4. **Third-party recipients**: none. Feeds the admin moderation queue
   (`GET /api/v1/admin/flags`) and the guardian alert feed, both internal.
5. **Vendor purpose / retention / training**: N/A.
6. **COPPA personal information?**: yes; behavioral data tied to a persistent child identifier,
   though the content itself is a closed enum, not identifying text.
7. **Disclosure classification**: no disclosure.
8. **Consent consequence**: D1 only.

### Event 6: Typing a story wish (child-initiated request)

1. **Child-originated data**: `POST /api/v1/story-requests` (`story_requests.py:335-341`):
   `request_text`, free text up to 500 characters, one of two free-text child-originated fields in
   this matrix (see also Event 10). Runs under the guardian's bearer token in the current (R1)
   tier, but `initiator_role="child"` is stamped on the row (`story_requests.py:461`).
2. **Identifiers attached**: `family_id` (`story_requests.py:454`), `profile_id`, `age_band`
   (`story_requests.py:460`). Event log entry is deliberately thin: `entity_type="story_request"`,
   payload `{initiator_role}` only; the request text itself is not in the event-log payload
   (`story_requests.py:468-476`, `events/writer.py:18`).
3. **CYO storage**: `StoryRequest.request_text` (`db/models.py:1884`, class `StoryRequest` at
   `db/models.py:1736`), raw, retained per the accepted retention table (see field 8 below).
4. **Third-party recipients**:
   - **Screening (before storage is trusted safe)**: a local, deterministic PII guard runs first
     against the family's registered child names; a match hard-blocks and nothing leaves CYO
     (`screening.py:76-95`). If clean, the raw text goes to **OpenAI Moderation** as plain
     content, with no identifiers attached to the call. Until 2026-08-26 it also went to
     **Google Perspective**; **see Section 2's Google Perspective entry**: that leg was a
     confirmed, not merely unconfirmed, disclosure for that vendor specifically (no `doNotStore`
     set; content usable for the vendor's own research/model-building) and was retired by PR #764.
     The Perspective analysis in items 5, 7, and 8 below is retained as the historical record for
     that period.
   - **Generation (only after guardian/admin approval, but built from the child's words)**: the wish
     becomes `ConceptBrief.premise`; a fictional protagonist name is substituted for any real one,
     and the brief is re-checked against the PII guard before it reaches **OpenRouter** (whose
     traffic can sub-route to AWS Bedrock, Azure, or Google Vertex) or, on the separate
     admin-selectable path, **Anthropic (direct)**, which has no sub-processor routing of its own.
5. **Vendor purpose / retention / training**: see the vendor register in Section 2 for each
   destination's individual posture; they differ meaningfully (guardrailed ZDR and no-training on
   the OpenRouter route; confirmed adverse on Perspective; unconfirmed on the direct-Anthropic route
   and OpenAI Moderation).
6. **COPPA personal information?**: **corrected 2026-08-09**: yes, unconditionally, not
   "potentially." `request_text` is personal information under 312.2(11) the moment it is stored
   alongside `profile_id`/`family_id`/`age_band` (information concerning the child, combined with an
   identifier), regardless of whether its content is itself identifying. Separately and additionally,
   because it is free text, it *may also* directly identify the child, a friend, or a school if the
   child types that content; the registered-name allowlist screens for the family's known child
   names before egress, but is a no-op against misspellings, other children's names, or any detail
   not already on file (documented residual-risk finding, dated 2026-07-10, not superseded by any
   later fix in the sources reviewed). These are two separate facts, not one graduated claim.
7. **Disclosure classification**: third-party disclosure, analyzed against 312.2's internal-operations
   exception per vendor rather than assumed uniformly. The exception requires the recipient to use
   the data solely to provide the support service, not for any other purpose, not disclose it further,
   and retain it no longer than necessary. **Google Perspective fails this test on the facts in
   Section 2**: it is not disclosure-consent-exempt, it is a disclosure requiring the separate-consent
   option COPPA's 2025 amendments give the parent under 312.5(a)(2), "the option to consent to the
   collection and use of the child's personal information without consenting to disclosure ... unless
   such disclosure is integral to the [service]." Whether the Perspective leg is "integral" (arguably
   yes, as a safety-screening floor per the project's own design rationale) is the live question that
   determines whether 312.5(a)(2)'s separate option must actually be offered; it has not been analyzed
   or offered either way. OpenAI Moderation, OpenRouter, and Anthropic have not been individually
   assessed against the same test; do not assume they land the same way Perspective does. This is
   exactly the leg the project's own documents call the standing, open blocker (`privacy-model.md`
   "Blocker 1b"); processor terms for the classifier leg are unconfirmed, which is why this row,
   alone among the ten, carries an open-blocker flag in Section 1.
8. **Consent consequence**: three layers exist, and a fourth the 2025 amendments require has not
   been built. (1) D1 base VPC gates profile creation, as everywhere else, subject to the D1 key's
   own now-larger open risk (Section 6). (2) A guardian can invoke the restriction control described
   in Section 6's Art. 18/21 entry (`ChildProfile.processing_restricted_at`) specifically because
   this is "the concrete point where this profile's data newly reaches a third-party LLM/classifier
   provider"; it blocks new submissions without deleting existing data. (3) D5: the working position
   that child-originated data is excluded from any training/evaluation corpus is contradicted by the
   Perspective finding above for that vendor specifically; see the corrected D5 entry in Section 6.
   (4) **Missing**: 312.5(a)(2)'s separate disclosure-consent option, distinct from D1's bundled
   collection-and-use consent, has not been built or offered for any leg found to be a genuine
   disclosure (Perspective, on the facts above). This is a gap this matrix did not previously name.

### Event 7: Reaching an ending (completion)

1. **Child-originated data**: `POST /api/v1/completions` (`reading.py:1037-1040`): `profile_id`,
   `storybook_id`, `version`, `ending_id`, a story-graph identifier validated against the pinned
   version's declared endings (`reading.py:1090-1092`). No free text.
2. **Identifiers attached**: `child_profile_id` via `authorize_profile` (`reading.py:1076-1077`). No
   `pipeline_event` row is written for this event.
3. **CYO storage**: `Completion` table, composite PK
   `(child_profile_id, storybook_id, version, ending_id)`, cascade-deleted with the profile or the
   version's storybook (`db/models.py:1541-1565`). Readable by the guardian via
   `GET /completions/{profile_id}`, built explicitly for the COPPA 312.6(a) / GDPR Art. 15 access
   right.
4. **Third-party recipients**: none.
5. **Vendor purpose / retention / training**: N/A.
6. **COPPA personal information?**: yes; persistent-identifier-linked behavioral data.
7. **Disclosure classification**: no disclosure.
8. **Consent consequence**: D1 only.

### Event 8: Active reading time (background flush)

Not in the original enumerated list; found while tracing the reader/offline layer for completeness.

1. **Child-originated data**: `POST /api/v1/me/reading-time`, child-token-only
   (`reading_time.py:100-119,290-293`): `date`, server-clamped `seconds_delta`, an idempotency
   `flush_id`, optional `device_id`. No free text.
2. **Identifiers attached**: `child_profile_id` derived from the child principal's own single
   profile (`reading_time.py:309`). No event-log row is written.
3. **CYO storage**: `ReadingActivityDay` table, PK `(child_profile_id, activity_date)`
   (`reading_time.py:213-268`); client-side accumulator in the `reading_time_days` IndexedDB store
   (`offline/db.ts:30-37,102-122,548-579`).
4. **Third-party recipients**: none.
5. **Vendor purpose / retention / training**: N/A.
6. **COPPA personal information?**: yes; persistent-identifier-linked behavioral data.
7. **Disclosure classification**: no disclosure.
8. **Consent consequence**: D1, plus a dedicated guardian-facing off switch:
   `profile.time_capture_paused` discards any queued flush server-side even if the client already
   recorded it locally, a granular privacy control this matrix's other rows don't have an
   equivalent of.

### Event 9: Appearing in a cousin's feed (ring-2 recommendation, derived from Event 4)

1. **Child-originated data**: not itself a new write; `GET /api/v1/recommendations/{profile_id}`
   (`recommendations.py:256-261`) is a read-only projection over data already collected in Event 4.
   Included here because it is the one path where a child's data becomes visible to people outside
   their own family.
2. **Identifiers attached**: the exposed payload substitutes the recommending child's `display_name`
   for their `child_profile_id`; the receiving family never sees the internal identifier, only the
   name (`recommendations.py:369-377`).
3. **CYO storage**: no new storage; reads the existing `Rating` row and the connection graph
   (`FamilyConnection`).
4. **Third-party recipients**: none; this is CYO-internal, cross-family data sharing (another CYO
   household), not a disclosure to a vendor. Ring-1 (same family) needs no additional consent;
   ring-2 (a connected family, the cousins case) requires an active `FamilyConnection` verified
   per-row on both guardians' consent, not merely inferred from the connection's existence.
5. **Vendor purpose / retention / training**: N/A; no vendor.
6. **COPPA personal information?**: yes; a display name plus a reading signal (rating), disclosed
   outside the immediate family, which is the specific scenario ADR-016 was written to bound
   tightly (structured data only: book pointer, name, rating; never free text, progress, or profile
   attributes).
7. **Disclosure classification**: a distinct category from every other row: a consumer-to-consumer
   disclosure (one family to another, both CYO customers) under COPPA 312.5(a), not an
   operator-to-processor disclosure. It carries its own, separate consent bar rather than riding on
   D1.
8. **Consent consequence**: requires both guardians' active, directional consent on the
   `FamilyConnection`; without it the recommendation is never computed for that pair. Revocation is
   prospective only: it stops future visibility and future syncs immediately but does not
   retroactively erase a values payload already synced to the other household's device.
   Guardian-facing copy is required to say so rather than imply retroactive erasure.

### Event 10: Creating a character (added 2026-08-09, PR #649)

**Added in this revision.** PR #649 (persistent reader characters, ADR-028) shipped after this
matrix's original authoring and added a second child-typed free-text field this matrix's original
"one free-text field" framing missed entirely. Unlike Event 6, this field never reaches a third
party; the two events have materially different risk profiles despite both being free text, which
is exactly why collapsing them into "the one free-text field" understated the picture rather than
merely undercounting it.

1. **Child-originated data**: `POST /api/v1/characters` (`characters.py:391-392`,
   `create_character`): `name` (free text, max 32 characters,
   `frontend/src/characters/characterApi.ts:127`), `archetype` and `look` (closed enums), for a
   once-per-profile "make your character" step. `name` is rendered directly into story prose. The
   component's own `#CRITICAL: security` marker (`CharacterCreator.tsx:84-93`) states every safety
   rule beyond length is enforced **only server-side** (`_reject_unsafe_character_name`,
   `characters.py`), deliberately never shipped to the client, so the denylist itself is not
   published as a map for working around it.
2. **Identifiers attached**: `family_id` is read from the already-loaded `ChildProfile`, never
   accepted from the request body (`characters.py:416-418,449`); `profile_id` is authorized via
   `authorize_profile` before the row is created (`characters.py:421-422`).
3. **CYO storage**: `Character` table (`db/models.py:895`), `name` column at `db/models.py:976`
   (`String(32)`, matching the client-side max length). No `pipeline_event` row is written; no
   `record_event` import exists in `characters.py`, unlike Events 4-6.
4. **Third-party recipients**: **none, and this is the material difference from Event 6.** The
   active character's name is delivered to the reader client-side, resolved into
   `ReadingStateView.character_name` for rendering (`frontend/src/reader/characterSeed.ts:103-105`,
   `frontend/src/offline/sync.ts:136-177`), and is explicitly excluded from the generation-prompt
   path: `storybook/personalization_values.py:351-357` asserts the `character_name` personalization
   slot "carries no value; its value is synthesized from the active character" at render time, not
   at generation time. `generation/concept.py:192`'s `character_names` field is unrelated: it names
   characters from a *previous book in the same series* for continuation prompts, not the reader's
   own typed name. No code path was found that embeds this field's value into a provider-bound
   prompt.
5. **Vendor purpose / retention / training**: N/A; no vendor reached.
6. **COPPA personal information?**: yes, unconditionally under 312.2(11) once linked to
   `profile_id`/`family_id` (same basis as Event 6 field 6), and potentially directly identifying,
   since it is free text a child could type their own or a friend's real name into. Server-side
   denylist screens the safety dimension (rejects unsafe content per age band), not the identity
   dimension; nothing screens for a real child's name the way the generation-leg PII guard does for
   Event 6.
7. **Disclosure classification**: no disclosure; the third-party recipient analysis in Event 6 and
   Section 2 does not apply here, because nothing egresses.
8. **Consent consequence**: **corrected 2026-08-09**: D1's universal gate applies, same as every
   other event, plus no additional third-party-egress consent control is needed on top of it, since
   field 4 confirms nothing egresses. That is narrower than "no Article 18/21 or D5 consideration
   applies," which the previous version of this entry claimed and which does not follow from the
   egress fact alone. D5 (Section 6) is indeed a separate question from egress, but it cannot be
   answered here by appeal to the general "no child-originated data enters a training corpus by
   design" premise, because [D5's own entry](#d5-ai-training-consent-segregation) now records that
   premise as contradicted for at least one vendor. What holds for this field is narrower, and rests
   on what the code does today rather than on a design guarantee: field 4 found no path by which the
   name reaches any vendor, so the vendor-side training exposure D5 identifies cannot arise for it,
   and no internal training or evaluation use of `Character.name` exists. Both legs are contingent
   facts, so adding either a vendor-bound path or an internal training use would re-implicate D5 for
   this field. Article 18/21 (Section 6) is a separate question from egress entirely,
   per that section's own correction: the restriction control does not map cleanly to either
   article's actual preconditions as built, for any event, and GDPR has not attached in any case
   (T4).

---

## 4. Cross-cutting notes

Facts that apply across the whole matrix rather than to any one row.

- **The append-only event log is selective, not universal.** `pipeline_event` only receives entries
  for Events 4, 5, and 6 (RATED, KID_FLAGGED, REQUEST_CREATED) among the ten above, not
  reading-state saves (2, 3), completions (7), or character creation (10). Every payload is
  validated against a
  per-event-type key allowlist plus a 200-character value guard that rejects free text
  (`events/writer.py:17-151`). It never stores raw child-authored text: even Event 6's log entry
  excludes `request_text` itself.
- **"Internal only" means Supabase-hosted, not off-grid.** On the public tier, the primary
  datastore for every table in this matrix is Supabase-managed Postgres. "No third-party
  recipients" in Section 1 describes the absence of a disclosure requiring separate consent (see
  Section 2's COPPA-activity/GDPR-role framework note); it does not mean the data never touches
  infrastructure outside CYO's own servers. Supabase is a named processor with its own DPA still
  not executed as of the sources reviewed.
- **IP addresses and correlation IDs are not part of this matrix's child-linked rows.** The only
  place a request's client IP is captured and persisted for a person is guardian-only VPC consent
  capture at onboarding (`onboarding.py:433` extracts it, `onboarding.py:174` persists it as
  `consent_ip`; corrected citation, the file is 459 lines and the previously-cited line 894 does not
  exist), not a child event. Correlation IDs propagate
  through structured logs but are not columns on any child-linked table reviewed here
  (`ReadingState`, `Completion`, `Rating`, `KidFlag`, `StoryRequest`, `ReadingActivityDay`);
  log-layer retention is a separate question this matrix does not answer.
- **Device identifiers are client-chosen, not hardware fingerprints,** and are never
  cross-referenced to a third party; they exist purely for idempotent offline sync
  (`ReadingState.updated_by_device_id`, reading-time flush dedupe). An earlier audit flagged this
  column as a latent, currently-unset persistent identifier the shipped client never populates.

---

## 5. Resolved conflicts

Two places where the project's own compliance documents disagreed with each other as of the
2026-08-08 compiling of this matrix. Both are now resolved against current code (verified
2026-08-08) rather than left open; the original disagreement is kept below the resolution so the
record of what was uncertain, and why, is not lost.

### Google Gemini cover-art prompt: does child-derived content reach it unscreened?

**Resolved: no, it is PII-guarded.** Direct read of current code confirms `covers/service.py:243-254`
recovers the owning concept's protagonist name and family id
(`_recover_concept_context`), builds the prompt (`build_cover_prompt`), builds a `PiiContext` from
the family's registered child display names (`_pii_context_for_family`), and calls
`assert_prompt_pii_safe(prompt, forbidden=pii)` before the Gemini call, raising and failing the
cover job rather than dispatching an unscreened prompt. The guard's own comment at
`covers/service.py:246-252` states it was added specifically because the cover-art prompt was, at
one point, "the one path in the generation pipeline with zero PII screening." Two tests exercise
the block: `tests/integration/test_cover_service.py::test_generate_cover_blocks_on_registered_child_name_in_prompt`
and `::test_generate_cover_blocks_on_email_shaped_content_in_prompt`, both asserting the job reaches
`cover_status == "failed"` and the image provider is never called. **Corrected 2026-08-09**: this
entry previously claimed no exact introduction date was recoverable from history; that claim was an
artifact of a shallow local clone, not a fact about the repository. Against the full history
(`git fetch --unshallow`), `git log -S'assert_prompt_pii_safe' -- src/cyo_adventure/covers/service.py`
resolves cleanly to `bfe3d0f2`, "GDPR/COPPA review, remediation plan, and Phase 1 PII-egress
hardening" (#304), which both introduced the guard and predates this matrix's authoring by several
weeks.

**What was uncertain and why**: ADR-017 and `privacy-model.md` v0.3 (2026-07-16 / 2026-07-29) stated
cover-art prompts "derive only from story metadata" with "no child PII reaches the image provider."
`coppa-compliance-audit.md` (dated 2026-07-10, finding H-02) had found the opposite at that commit:
`covers/` importing no PII guard at all. The audit predates both newer documents, and the newer
documents turn out to be the current truth; H-02 was a real finding at the commit it audited and has
since been fixed, not a case of a document asserting a control that never existed.

**Clarification (2026-08-09), not part of the resolution above**: the previous version of this
paragraph cited the same audit's finding M-04 (`SECURITY.md` asserting a child-privacy control that
did not exist) as a contrasting example, in a way that risked reading as if M-04 were a third
resolved conflict alongside the two this section actually covers. It is not; it was cited only as an
illustration of the *opposite* pattern, and the audit's own Section 8 remediation roadmap still lists
correcting `SECURITY.md` as an outstanding action item, unchanged since 2026-07-10. Independently
checked today: current `SECURITY.md` (lines 47, 92-95) accurately describes the real OIDC
verification and the actual VPC mechanism, so M-04 does appear to be fixed in the file it was about,
even though `coppa-compliance-audit.md`'s own roadmap was never updated to reflect that. That is a
staleness note about the audit document, not a claim this matrix resolves M-04 itself.

### Sentry: wired up, or not?

**Resolved: wired up, currently inactive by default.** Direct read of current code confirms a real
integration exists: `sentry-sdk>=2.66.0` is a declared dependency (`pyproject.toml:88`),
`core/observability.py::init_sentry` wraps `sentry_sdk.init(...)` with `send_default_pii=False`
asserted by `tests/unit/test_observability.py::TestInitSentryDisablesPii::test_init_sentry_never_sends_pii`, and `app.py:616`
calls `init_sentry(settings)` on startup. It is a documented no-op unless `SENTRY_DSN` is set
(`core/observability.py:75-77`, `core/config.py:953`), and `.env.example` ships it unset. So: the
code path is live in `main`; whether Sentry is actually *receiving* telemetry from any given
deployment depends on whether that deployment's environment sets `SENTRY_DSN`, which this record
does not have visibility into.

**What was uncertain and why**: `records-of-processing-activities.md` and
`processor-dpa-checklist.md` both listed Sentry as a live processor. `coppa-compliance-audit.md`
(2026-07-10) had reported the opposite as a "negative finding (good)": no Sentry integration
existed, no `sentry_sdk` import anywhere. Same pattern as the cover-art conflict: the audit is the
older source, and the integration was built after that audit ran. Sentry's design (PII excluded by
contract, verified by test) means this conflict was always lower-stakes for child data specifically
than the cover-art one, but it does settle where Sentry belongs in Section 2's vendor register: as
an integration that exists in code, not as planned-only.

---

## 6. Consent-consequence key

The "consent consequence" field in Section 3 refers back to these mechanisms by name.

### D1: Verifiable parental consent

**Corrected 2026-08-09; the previous entry described a method that is not available and understated
the risk of the one that is built.** A typed full-legal-name attestation layered on the guardian's
existing OAuth login, implemented 2026-07-20. **There is no canvas-drawn signature**: it was
considered in the original framing but never built, `GuardianConsentPage.tsx` has no drawing
surface, and ADR-018 now explicitly instructs "do not describe a drawn signature as available."
Enforced at `POST /api/v1/profiles` via `_require_consent`. Refusal blocks every child profile from
ever being created, the universal upstream gate for all ten events in this matrix.

The compliance question is more serious than "is our signature good enough," per a 2026-08-08 direct
reading of 16 CFR 312.5(b)(2) recorded in ADR-018: method (b)(2)(i) ("a form signed by the parent
... and returned ... by postal mail, facsimile, or electronic scan") reads as a *return channel* for
a form signed away from the service, which an in-app-captured signature may not be an instance of at
all, independent of whether the signature itself is adequate. The (b)(1) fallback (the general
"reasonably calculated, in light of available technology" standard, which (b)(2)'s enumerated list
is a non-exhaustive set of examples under, not the exclusive test) is not a safe retreat either: the
FTC's 2015 AgeCheq decision rejected a materially similar mechanism (a signature artifact bound to
an adult by a second authentication step, on a shared-device threat model) on exactly this standard.
An FTC-approved Safe Harbor program (312.5(b)(3), via 312.12(a)) can bless a non-enumerated method,
but approval is not a precondition to relying on one, and no operator has sought it since 2015. See
ADR-018's D1 section and `docs/compliance/counsel-engagement-brief.md` for the full analysis,
including a since-reopened payment-card route (312.5(b)(2)(ii)) and active vendor evaluation; this
key does not attempt to compress all of it, only to stop understating it.

**Disposition, 2026-08-09.** The owner ruled the shipped mechanism adequate and withdrew this
question from the counsel engagement. Every sentence above still holds, including the AgeCheq
authority; an acceptance reassigns who carries a risk and does not shrink it. The item is now an
accepted exception at assurance-register row O-122, expiring at R2. **The gate itself is
unaffected**: `_require_consent` still blocks every child profile, so what is accepted is the
*quality* of the consent evidence, never its absence, and the universal upstream gate described
above continues to apply to all ten events in this matrix.

### Art. 18/21: Restriction and objection

**Corrected 2026-08-09.** `ChildProfile.processing_restricted_at`, guardian-set via
`PATCH /api/v1/profiles/{id}`, pauses new story-request submission without deleting anything already
collected. The previous entry filed this generically as "Article 18/21"; the two GDPR articles are
distinct rights with different preconditions, and this mechanism matches neither cleanly. Art. 18(1)
restriction is available only on four enumerated grounds (contesting accuracy, unlawful processing
where erasure is opposed, the controller no longer needing the data but the subject needing it for a
legal claim, or a pending Art. 21(1) objection), not at a guardian's discretion; Art. 18(2) restricts
processing of data *already held* down to storage, which this mechanism does not do (it stops new
submissions, not existing processing). Art. 21(1) objection engages only where the processing relies
on Art. 6(1)(e) (public task) or 6(1)(f) (legitimate interests) as its legal basis. This mechanism is
better described as a project-built restriction control that does not map to a specific GDPR Article
18 or 21 ground as built, not as an implementation of either. **Mitigating**: GDPR has not attached
(T4: US-only today, per `assurance-register.md`), so no live obligation is currently unmet; this
correction matters for accuracy, not for a compliance gap that exists today.

### D5: AI-training consent segregation

**Corrected 2026-08-09; the previous entry's premise is contradicted by a Section 2 finding.**
Amended-COPPA-Rule requirement: using a child's data to train or develop AI models needs its own
separate, opt-in, unbundled consent (312.5(a)(2)'s third-party-disclosure-consent option is the
closer analogue for the classifier leg specifically; the training-use requirement is a distinct,
narrower rule, and the two should not be conflated). The working position was that child-originated
data is excluded from any training/evaluation corpus by design, so the obligation would not trigger.
[Section 2's Google Perspective entry](#google-perspective-stage-0-toxicity-classifier) contradicts
that premise directly for one vendor: the classifier request sets no `doNotStore` field, and
Google's own Perspective documentation states stored comments are used "for future research and
community model building purposes," precisely the outcome D5's working position assumed did not
happen. **Update 2026-09-05**: the live Perspective leg was retired by PR #764 (2026-08-26), and
the one remaining offline caller (`scripts/capture_stage0_baseline.py`, catalog prose only) sets
`doNotStore: true`; issue #659 closes with that change. The training-exclusion premise now holds for
current flows, but not retroactively for wish text sent to Google before 2026-08-26, which is what
this entry continues to record. Note the scope
limit when reasoning about remedies: 312.5(a)(2)'s consent-segregation right runs to **disclosures
to third parties**, so it is the right hook for the Perspective leg but is not a general opt-out of
an operator's own internal training, which is governed instead by the 312.2 internal-operations
proviso and, prospectively, GDPR Art. 6.

### ADR-016: Dual-guardian connection consent

Directional, revocable `FamilyConnection` requiring active consent from both guardians before any
recommendation crosses the family boundary. Applies only to Event 9; every other event's data never
leaves the family regardless of this mechanism.

---

## 7. Related documents

| Document | Relationship |
| --- | --- |
| `docs/planning/privacy-model.md` | Data classification, retention rules, and the classifier/generation-leg blocker split this matrix's event-level detail is grounded in. |
| `docs/planning/adr/adr-016-recommendation-sharing-social-boundary.md` | Source for Event 9's ring-2 consent model. |
| `docs/planning/adr/adr-017-ai-cover-art.md` | Source for the Google Gemini vendor entry; the ADR side of the Section 5 cover-art resolution, confirmed correct against current code. |
| `docs/planning/adr/adr-018-childrens-privacy-compliance.md` | Source for D1, Art. 18/21, and D5 in Section 6, and the Blocker 1a (generation leg, narrowed to a documentation item, not itself a dispatch gate) / 1b (classifier leg, the real open blocker) split referenced in Event 6, which only discusses 1b since 1a does not gate anything in this matrix's scope. As of 2026-08-08 this ADR carries a substantially larger D1 risk record (adverse FTC AgeCheq authority, a reopened payment-card VPC route) than this matrix's own D1 summary attempts to reproduce; read the ADR directly for the current state, not only this matrix's key. |
| `docs/planning/adr/adr-028-persistent-reader-characters.md` | Source for Event 10 (added 2026-08-09), the character-naming free-text field PR #649 shipped. |
| `docs/compliance/counsel-engagement-brief.md` | The current, more detailed source for D1's open questions than this matrix's Section 6 key attempts to summarize; added by PR #643, not previously reflected here. |
| `docs/compliance/records-of-processing-activities.md` | Source for the vendor list and retention table this matrix's Section 2 draws from; the RoPA side of the Section 5 Sentry resolution, confirmed correct against current code. |
| `docs/compliance/processor-dpa-checklist.md` | Source for each vendor's DPA-execution status in Section 2. |
| `docs/compliance/coppa-compliance-audit.md` | Source for finding H-02, central to Section 5's cover-art resolution; also the origin of several file:line citations reused here after re-verification against current code. Finding M-04 is cited in Section 5 only as an illustrative contrast, not as a third resolved conflict; see that section's clarification. |
| `docs/compliance/coppa-gdpr-remediation-plan.md` | Source for the retention windows referenced throughout Section 3. |
| `docs/security/assurance-spine.md` | Portable, project-agnostic 17-category control-and-obligation spine; the source of the seventeen SP categories and the regime-applicability trigger method `assurance-register.md` instantiates. |
| `docs/security/assurance-register.md` | This project's instantiation of the spine: 118 obligation rows (O-01 to O-121) plus the regulatory-applicability determination for every spine-catalogued regime, including O-120 (state information-security statutes) and O-121 (GDPR Art. 8 child-consent age) added during this matrix's 2026-08-08 sufficiency verification. The broader monitoring-capability record this matrix's event-level detail feeds into. |
