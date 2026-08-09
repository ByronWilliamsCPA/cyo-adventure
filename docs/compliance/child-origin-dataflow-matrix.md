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
source: "Direct review of src/cyo_adventure/api, src/cyo_adventure/db/models.py, src/cyo_adventure/events, frontend/src/offline, frontend/src/player at commit 65883a1 (2026-08-08), synthesizing docs/planning/privacy-model.md (v0.3), docs/planning/adr/adr-016, adr-017, adr-018 (amended 2026-08-01), and docs/compliance/records-of-processing-activities.md, processor-dpa-checklist.md, coppa-compliance-audit.md (commit c9dbfa9, 2026-07-10), coppa-gdpr-remediation-plan.md, gdpr-compliance-review.md"
---

> **Status**: Draft | **Version**: 1.1 | **Compiled**: 2026-08-08 | **Updated**: 2026-08-08
> **Code reviewed at**: commit `65883a1` on `main` (Section 5's two resolutions re-verified against
> the working tree directly, same date)
> **Scope**: `src/cyo_adventure/api/`, `src/cyo_adventure/db/models.py`, `src/cyo_adventure/events/`,
> `src/cyo_adventure/story_requests/`, `src/cyo_adventure/moderation/`, `src/cyo_adventure/generation/`,
> `src/cyo_adventure/covers/`, `src/cyo_adventure/core/observability.py`, `frontend/src/offline/`,
> `frontend/src/player/`

## 0. Important disclaimer

This is an engineering-derived record, not legal advice, consistent with the standing disclaimer
carried by every sibling document in this directory. Several rows below cite
`coppa-compliance-audit.md` (dated 2026-07-10), which predates the ADR-018 consent implementation
(2026-07-20) and the D5 AI-training amendment (2026-08-01). Where a newer document supersedes an
older finding this record says so and cites both. Two conflicts between project documents that this
matrix originally flagged as unresolved (cover-art PII screening, Sentry wiring status) have since
been checked directly against current code and resolved: see [Section 5](#5-resolved-conflicts).
Neither resolution changes Section 1's open-blocker flag on Event 6 (the classifier leg, ADR-018
Blocker 1b), which is a separate, still-genuinely-open item.

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

Nine child-originated events, scanned for the three questions that matter first: does the child
type free text, does the data leave CYO's infrastructure, and is anything about it still an open
compliance item.

| # | Event | Child free text? | COPPA PI | Leaves CYO infra? | Vendors touched | Status |
| --- | ------- | ------------------- | ---------- | -------------------- | ------------------ | -------- |
| 1 | Starting a kid session (profile pick / device pickup) | No | Behavioral / identifier | No | None | Internal only |
| 2 | Choosing a branch (in-story choice) | No | Behavioral / identifier | No | None | Internal only |
| 3 | Resuming / saving progress (incl. offline sync) | No | Behavioral / identifier | No | None | Internal only |
| 4 | Rating a story | No | Behavioral / identifier | No | None | Internal only |
| 5 | Flagging content | No (closed enum only) | Behavioral / identifier | No | None | Internal only |
| 6 | Typing a story wish (child-initiated request) | **Yes**, the one free-text field | **Yes, potentially direct** | **Yes** | OpenAI Moderation, Google Perspective, OpenRouter / Anthropic (+ sub-processors) | **Open blocker (1b)** |
| 7 | Reaching an ending (completion) | No | Behavioral / identifier | No | None | Internal only |
| 8 | Active reading time (background flush) | No | Behavioral / identifier | No | None | Internal only |
| 9 | Appearing in a cousin's feed (ring-2 recommendation, derived from #4) | No | Display name + rating, cross-household | No (CYO-to-CYO, not a vendor) | None | Consent-gated, dual-guardian |

Every event below is gated upstream by the same fact: none of it can occur without a guardian first
completing verifiable parental consent at onboarding ([D1](#d1-verifiable-parental-consent), see
Section 6). Refusal means the child profile is never created, so no row in this matrix is reachable.
What differs per event is what happens after that gate.

---

## 2. Vendor register

Every third party that can receive data derived from a child event, normalized once here so the
event matrix in Section 3 can reference it by name instead of repeating it. "DPA executed" reflects
`processor-dpa-checklist.md`, dated 2026-07-20 and not yet re-confirmed.

### OpenAI Moderation (Stage-0 safety classifier)

- **Purpose**: scores child-typed wish text at intake and every generated story node during
  moderation, as the first-line safety filter ahead of guardian/admin review.
- **What it receives**: raw request text at screening, after the local PII allowlist has already
  blocked a name match; every generated node's prose during moderation. No `profile_id` /
  `family_id` / name accompanies either call; content only.
- **Retention**: 30-day API data retention by default, per OpenAI's own DPA terms (not yet
  executed).
- **Training permitted**: not confirmed in an executed contract; API-tier traffic is excluded from
  training under OpenAI's standard API terms, but that protection is only as good as confirming
  this account sits on those terms.
- **Status**: DPA not executed; COPPA PI on the wish leg.

### Google Perspective (Stage-0 toxicity classifier)

- **Purpose**: toxicity/safety scoring, parallel to OpenAI Moderation, same two call sites (intake
  screening, per-node moderation).
- **What it receives**: same content pattern as OpenAI Moderation. Separately flagged for a
  sunset/replacement effort ("Stage-0 Perspective sunset work") in progress per the source docs.
- **Retention**: unconfirmed. The DPA checklist could not confirm whether the Perspective API is
  actually covered by Google's Cloud DPA or needs its own terms acceptance.
- **Training permitted**: unconfirmed, same open item as retention.
- **Status**: DPA coverage unconfirmed; COPPA PI on the wish leg.

### OpenRouter (+ AWS Bedrock / Azure / Vertex sub-processors), generation leg (routed)

- **Purpose**: turns the approved concept brief (the wish, de-identified) into story prose. Bedrock,
  Azure, and Vertex are sub-processors OpenRouter routes to for the respective model families since
  the 2026-07-28 ZDR toggle change.
- **What it receives**: a brief with a fictional protagonist name, coarse age band, guardian-set
  banned themes and flag caps, and the child's free-typed premise text carried through verbatim but
  identifier-free; `assert_prompt_pii_safe` hard-fails the job rather than redacting.
- **Retention**: Zero Data Retention enforced by a dedicated workspace guardrail (a dated
  configuration snapshot, not a signed contract) across this routing surface.
- **Training permitted**: No. The guardrail disables all three data-training paths (paid-trains,
  free-trains, free-publishes-prompts) for this route.
- **Status**: training disabled by guardrail; identifier-free but not PII-free; DPA not executed.

### Anthropic (direct), generation leg (admin-selectable, bypasses guardrail)

- **Purpose**: same generation role as OpenRouter, dispatched when `generation_provider="anthropic"`.
  A separate, built code path.
- **What it receives**: the same PII-guarded brief as the OpenRouter leg.
- **Retention**: not covered by the OpenRouter workspace guardrail. This leg is a distinct, direct
  integration; its retention posture rests on Anthropic's own Commercial ToS DPA, whose
  applicability to this account (commercial vs. consumer tier) is unconfirmed.
- **Training permitted**: unconfirmed for this leg specifically; the ZDR/no-training guardrail is
  scoped to the OpenRouter route only.
- **Status**: outside the ZDR guardrail; account tier unconfirmed.

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
- **Retention**: unconfirmed; DPA not yet executed.
- **Training permitted**: unconfirmed.
- **Status**: PII-guarded (verified 2026-08-08); DPA not executed.

### Cloudflare R2, cover-image object storage

- **Purpose**: stores WebP-optimized cover art. Storage only, not a model or classifier.
- **What it receives**: image bytes only. Per the RoPA (2026-07-20), access is private with
  presigned-URL delivery as of Phase 1d, superseding an earlier finding that the bucket was public
  with guessable keys.
- **Retention**: life of the storybook version.
- **Training permitted**: N/A, storage vendor, not a model provider.
- **Status**: private / presigned as of Phase 1d; DPA not executed.

### Supabase, auth + primary Postgres (public tier)

- **Purpose**: identity provider for guardians (children never hold a Supabase identity) and, on
  the public tier, host of the Postgres database every "internal only" row in Section 3 actually
  lives in.
- **What it receives**: guardian auth identity directly; every child-linked table in this matrix
  indirectly, as the datastore itself, once the public tier is live.
- **Retention**: life of the account/record, per this project's own retention table (Section 4).
- **Training permitted**: N/A, infrastructure processor, not a model vendor.
- **Status**: processor of record for everything this matrix calls "internal only"; DPA not
  executed.

### Sentry, error telemetry (cross-cutting, not event-specific)

- **Purpose**: exception monitoring, hardcoded by design to exclude child-linked content;
  correlation IDs only, no reading-state snapshots.
- **What it receives**: incidental only, if any event above throws an exception mid-request, and
  only when a DSN is configured (see Status). Integration is verified in code:
  `core/observability.py::init_sentry`, called from `app.py:603`, wraps `sentry_sdk.init(...)` with
  `send_default_pii=False` on every call path, asserted by
  `tests/unit/test_observability.py::test_init_sentry_disables_pii`.
- **Retention**: per Sentry's platform default; not independently confirmed.
- **Training permitted**: N/A.
- **Status**: integration exists in current code (`sentry-sdk>=2.66.0` dependency, `pyproject.toml`)
  and is a documented no-op unless `SENTRY_DSN` is set (`core/config.py:953`, unset by default in
  `.env.example`). Resolves the conflict previously recorded here; see Section 5.

---

## 3. Event-by-event matrix

The full ten-field trace for each event: what the child sends, what gets attached to it, where it
lands, who outside CYO ever sees it, and what a consent decision actually controls. Citations are
`file:line` against the current backend/frontend tree.

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
   `PUT /api/v1/reading-state/{profile_id}/{storybook_id}` (`reading.py:472-489`): `current_node`,
   `var_state`, `path`, `visit_set`, `save_slots`. No free text; node ids and variable values only.
2. **Identifiers attached**: `child_profile_id` from the authenticated path, authorized via
   `authorize_profile` (`reading.py:519-520`); optional client-supplied `device_id` and idempotency
   `event_id` (`reading.py:600-601`). The server re-validates the full state against the pinned
   story graph before accepting it, so a forged node/path is rejected (`reading.py:309-317`).
3. **CYO storage**: `ReadingState` table, PK `(child_profile_id, storybook_id)`, cascade-deleted
   with the profile (`db/models.py:1226-1267`); mirrored offline in IndexedDB's `reading_states`
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
   (`reading.py:320-325`); the same `PUT` body as Event 2 to save, including when replayed from the
   offline queue (`frontend/src/offline/sync.ts::saveProgress`, `sync.ts:141-201`, and
   `replayQueue`, `sync.ts:276-326`).
2. **Identifiers attached**: same as Event 2, plus an optimistic-concurrency `state_revision` that
   prevents one device's save from silently clobbering another's (`reading.py:472-484,550-559`); a
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
8. **Consent consequence**: same as Event 2; additionally, this is the data a guardian can review
   via `GET /reading-history/{profile_id}` and `GET /families/me/reading-summary` as their COPPA
   312.6(a) access right, counts and timestamps, "never reading content."

### Event 4: Rating a story

1. **Child-originated data**: `POST /api/v1/ratings` (`ratings.py:49-57`): `profile_id`,
   `storybook_id`, `value` (integer 1-5, DB-constrained). No free text.
2. **Identifiers attached**: `child_profile_id` via `authorize_profile` (`ratings.py:69-70`); the
   event log stamps `actor_id` / `actor_role` from the authenticated principal (`ratings.py:124`).
3. **CYO storage**: `Rating` table, PK `(child_profile_id, storybook_id)`, cascade
   (`db/models.py:1297-1328`). Also writes `pipeline_event`: `entity_type="rating"`,
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
   `confusing`, `db/models.py:2285`), optional `node_id`. Schema explicitly forbids extra fields, so
   no free-text escape hatch exists here (`flags.py:8`).
2. **Identifiers attached**: `family_id` denormalized from the profile (`flags.py:156`); actor
   stamped from the principal (`flags.py:173`).
3. **CYO storage**: `KidFlag` table (`db/models.py:2289`). Event log: `entity_type="kid_flag"`,
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
   `request_text`, free text up to 500 characters, the single free-text child-originated field in
   this entire matrix. Runs under the guardian's bearer token in the current (R1) tier, but
   `initiator_role="child"` is stamped on the row (`story_requests.py:461`).
2. **Identifiers attached**: `family_id` (`story_requests.py:454`), `profile_id`, `age_band`
   (`story_requests.py:460`). Event log entry is deliberately thin: `entity_type="story_request"`,
   payload `{initiator_role}` only; the request text itself is not in the event-log payload
   (`story_requests.py:468-476`, `events/writer.py:18`).
3. **CYO storage**: `StoryRequest.request_text` (`db/models.py:1499-1503`), raw, retained per the
   accepted retention table (see field 8 below).
4. **Third-party recipients**:
   - **Screening (before storage is trusted safe)**: a local, deterministic PII guard runs first
     against the family's registered child names; a match hard-blocks and nothing leaves CYO
     (`screening.py:76-95`). If clean, the raw text goes to **OpenAI Moderation** and
     **Google Perspective** as plain content, with no identifiers attached to the call.
   - **Generation (only after guardian/admin approval, but built from the child's words)**: the wish
     becomes `ConceptBrief.premise`; a fictional protagonist name is substituted for any real one,
     and the brief is re-checked against the PII guard before it reaches **OpenRouter** or
     **Anthropic (direct)**, whose traffic can sub-route to AWS Bedrock, Azure, or Google Vertex.
5. **Vendor purpose / retention / training**: see the vendor register in Section 2 for each
   destination's individual posture; they differ meaningfully (guardrailed ZDR and no-training on
   the OpenRouter route; unconfirmed on the direct-Anthropic route and both classifiers).
6. **COPPA personal information?**: yes, and potentially direct. This is the one field where a
   child could type their own name, a friend's name, a school, or other identifying detail. The
   registered-name allowlist screens for the family's known child names before this leg, but is a
   no-op against misspellings, other children's names, or any detail not already on file
   (documented residual-risk finding, dated 2026-07-10, not superseded by any later fix in the
   sources reviewed).
7. **Disclosure classification**: third-party disclosure claimed under the internal-operations
   exception (safety screening, service delivery) rather than as an independent-use disclosure.
   This is exactly the leg the project's own documents call the standing, open blocker
   (`privacy-model.md` "Blocker 1b"); processor terms for the classifier leg are unconfirmed, which
   is why this row, alone among the nine, carries an open-blocker flag in Section 1.
8. **Consent consequence**: three layers, not one. (1) D1 base VPC gates profile creation, as
   everywhere else. (2) A guardian can invoke Article 18/21 restriction
   (`ChildProfile.processing_restricted_at`) specifically because this is "the concrete point where
   this profile's data newly reaches a third-party LLM/classifier provider"; it blocks new
   submissions without deleting existing data. (3) D5: today's working position excludes all
   child-originated data, including this wish text, from any AI-training corpus by design, so no
   separate training-consent toggle is triggered yet; if that position ever changes, a distinct,
   default-off opt-in must be added before collection for that purpose, not after.

### Event 7: Reaching an ending (completion)

1. **Child-originated data**: `POST /api/v1/completions` (`reading.py:695-698`): `profile_id`,
   `storybook_id`, `version`, `ending_id`, a story-graph identifier validated against the pinned
   version's declared endings (`reading.py:748-750`). No free text.
2. **Identifiers attached**: `child_profile_id` via `authorize_profile` (`reading.py:734-735`). No
   `pipeline_event` row is written for this event.
3. **CYO storage**: `Completion` table, composite PK
   `(child_profile_id, storybook_id, version, ending_id)`, cascade-deleted with the profile or the
   version's storybook (`db/models.py:1270-1294`). Readable by the guardian via
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

---

## 4. Cross-cutting notes

Facts that apply across the whole matrix rather than to any one row.

- **The append-only event log is selective, not universal.** `pipeline_event` only receives entries
  for Events 4, 5, and 6 (RATED, KID_FLAGGED, REQUEST_CREATED) among the nine above, not
  reading-state saves (2, 3) or completions (7). Every payload is validated against a
  per-event-type key allowlist plus a 200-character value guard that rejects free text
  (`events/writer.py:17-151`). It never stores raw child-authored text: even Event 6's log entry
  excludes `request_text` itself.
- **"Internal only" means Supabase-hosted, not off-grid.** On the public tier, the primary
  datastore for every table in this matrix is Supabase-managed Postgres. "No third-party
  recipients" in Section 1 describes the absence of a disclosure to an independent-use vendor; it
  does not mean the data never touches infrastructure outside CYO's own servers. Supabase is a
  named processor with its own DPA still not executed as of the sources reviewed.
- **IP addresses and correlation IDs are not part of this matrix's child-linked rows.** The only
  place a request's client IP is captured and persisted for a person is guardian-only VPC consent
  capture at onboarding (`onboarding.py:429,894`), not a child event. Correlation IDs propagate
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
`cover_status == "failed"` and the image provider is never called. `git log -p` on
`covers/service.py` shows the guard call already present in the earliest tracked revision reachable
from `main`, so no exact introduction date is recoverable from history, only that it predates this
matrix's authoring.

**What was uncertain and why**: ADR-017 and `privacy-model.md` v0.3 (2026-07-16 / 2026-07-29) stated
cover-art prompts "derive only from story metadata" with "no child PII reaches the image provider."
`coppa-compliance-audit.md` (dated 2026-07-10, finding H-02) had found the opposite at that commit:
`covers/` importing no PII guard at all. The audit predates both newer documents, and the newer
documents turn out to be the current truth; H-02 was a real finding at the commit it audited and has
since been fixed, not a case of a document asserting a control that never existed (contrast with the
audit's own finding M-04, which is a case of exactly that pattern elsewhere in the same audit).

### Sentry: wired up, or not?

**Resolved: wired up, currently inactive by default.** Direct read of current code confirms a real
integration exists: `sentry-sdk>=2.66.0` is a declared dependency (`pyproject.toml:88`),
`core/observability.py::init_sentry` wraps `sentry_sdk.init(...)` with `send_default_pii=False`
asserted by `tests/unit/test_observability.py::test_init_sentry_disables_pii`, and `app.py:603`
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

A signature-capture step (canvas signature or typed full-legal-name attestation) layered on the
guardian's existing OAuth login, implemented 2026-07-20. Enforced at `POST /api/v1/profiles` via
`_require_consent`. Refusal blocks every child profile from ever being created, the universal
upstream gate for all nine events above. Whether a typed-name/canvas signature satisfies the FTC's
"signed" requirement (312.5(b)(2)(i)) is still an open counsel question, not yet closed.

### Art. 18/21: Restriction and objection

`ChildProfile.processing_restricted_at`, guardian-set via `PATCH /api/v1/profiles/{id}`. Pauses new
story-request submission specifically, the point new data would reach a third-party
classifier/LLM, without deleting anything already collected. The one per-event consent control in
this matrix finer-grained than D1 itself.

### D5: AI-training consent segregation

Amended-COPPA-Rule requirement: using a child's data to train or develop AI models needs its own
separate, opt-in, unbundled consent. Current working position excludes all child-originated data
from any training/evaluation corpus by design, so the obligation isn't triggered today. If that
position changes, the toggle must exist before collection for that purpose, not retrofitted after.

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
| `docs/planning/adr/adr-018-childrens-privacy-compliance.md` | Source for D1 and D5 in Section 6, and the Blocker 1a/1b split referenced in Event 6. |
| `docs/compliance/records-of-processing-activities.md` | Source for the vendor list and retention table this matrix's Section 2 draws from; the RoPA side of the Section 5 Sentry resolution, confirmed correct against current code. |
| `docs/compliance/processor-dpa-checklist.md` | Source for each vendor's DPA-execution status in Section 2. |
| `docs/compliance/coppa-compliance-audit.md` | Source for the H-02 and M-04 findings central to Section 5's now-resolved conflicts, both since fixed in code; also the origin of several file:line citations reused here after re-verification against current code. |
| `docs/compliance/coppa-gdpr-remediation-plan.md` | Source for the retention windows referenced throughout Section 3. |
| `docs/security/assurance-spine.md` | Portable, project-agnostic 17-category control-and-obligation spine; the source of the seventeen SP categories and the regime-applicability trigger method `assurance-register.md` instantiates. |
| `docs/security/assurance-register.md` | This project's instantiation of the spine: 118 obligation rows (O-01 to O-121) plus the regulatory-applicability determination for every spine-catalogued regime, including O-120 (state information-security statutes) and O-121 (GDPR Art. 8 child-consent age) added during this matrix's 2026-08-08 sufficiency verification. The broader monitoring-capability record this matrix's event-level detail feeds into. |
