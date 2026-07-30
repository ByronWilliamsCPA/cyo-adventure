---
title: "Personalization vocabulary-expansion request: feature specification"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Specify a guardian-initiated, admin-reviewed path for adding a value to a closed
  personalization vocabulary (a kinship label, a favorite category, a pet species, a home type)
  when a family's own term is missing, without ever opening free text into story prose. Execution
  plan Task D7 (docs/planning/story-personalization-execution-plan.md), depends on Task D6."
tags:
  - planning
  - privacy
  - safety
  - generation
component: Backend
source: "Owner decision 2026-07-29; src/cyo_adventure/storybook/personalization_values.py;
  ADR-023 (docs/planning/adr/adr-023-story-personalization-slots.md) rows 4a/5/6/7;
  docs/planning/story-personalization-execution-plan.md Tasks D6/D7; docs/planning/
  capability-register.md"
---

# Personalization vocabulary-expansion request: feature specification

> **Status**: Draft (2026-07-29). Spec only, no implementation. Blocked on Task D6 (seeding the
> shipped `CLOSED_VOCABULARIES` lists and splitting `favorite` into `favorite_color`,
> `favorite_food`, `favorite_hobby`), which itself lands after draft PR #489 merges to main. See
> "Dependency" at the end of this document.
> **Serves**: [G18](./capability-register.md) (extends it; see "Capability register linkage").
> **Proposes**: a new admin row, **A17** (see "Capability register linkage").
> **Constrained by**: [S10](./capability-register.md) (privacy architecture), the ADR-023 "never
> free text" decision for closed-vocabulary slots, and the egress invariant
> (`assert_prompt_pii_safe` is never touched by this feature; nothing here reaches a provider).

## 1. Problem statement and capability-register linkage

ADR-023 rows 4a, 5, 6, and 7 give a child four closed-vocabulary personalization slots: pet
species, a trusted-adult kinship label, favorites (split by Task D6 into `favorite_color`,
`favorite_food`, `favorite_hobby`), and home type. Every one of these is deliberately closed: "a
real name plus a real specific location" and other free-text risks are excluded by the taxonomy,
and `_shape_violations` in `src/cyo_adventure/storybook/personalization_values.py` enforces at
write time that these slot types "must use value_enum", never `value_text`. The vocabularies
themselves ship as `CLOSED_VOCABULARIES: dict[str, frozenset[str]]`
(`src/cyo_adventure/storybook/personalization_values.py:101-106`), and Task D6 seeds them with a
shippable list per ADR-023's illustrative examples ("Grandma", "Abuela", "Auntie", "Grandpa" for
kinship label; house/apartment/farm for home type; and so on).

A shipped list is necessarily incomplete. A family whose grandmother is called "Nonna", "Yiayi",
or a name specific to their own household culture, or whose pet is a species the list did not
anticipate, has exactly one fallback today: the generic sentinel default, silently, forever,
because closed-vocabulary slots reject free text by design (`personalization_values.py:163-164`,
the `enum_membership` rejection at `:255-274`). That gap is real and worth closing, but the
closing mechanism cannot be "let the guardian type anything": that would reopen precisely the
free-text-into-prose hole ADR-023's taxonomy was built to close, and it would bypass the
denylist and PII screening every other personalization value passes through.

This feature closes the gap the other way: a guardian may **propose** a value; nothing about
the proposal is usable in a story until an **admin** has screened it exactly the way a new
denylist-safe, non-identifying vocabulary member must be screened, and only then does the value
become a selectable closed-enum option, available to every family, indistinguishable from a
value that shipped in Task D6.

### Capability register linkage

**Guardian side: extends G18, no new guardian ID.** G18 ("Opt a child's real details into their
stories, per child and per slot, scoped by ring... and revoke either at any time",
`docs/planning/capability-register.md`) already owns the guardian-facing personalization
surface. This feature is a narrow widening of what G18's closed-vocabulary slots can contain,
not a new guardian authority; it does not change consent, ring scoping, or revocation, and it
adds no new data category to what a guardian already sets (a closed-enum choice for a slot they
already control). The register's own convention (see its "Why two and not more" ruling on G18
and K20) is to extend an existing row with a scope note rather than mint a new ID when a feature
is an implementation detail of an authority the persona already holds. The scope note this spec
proposes, for whoever next edits `capability-register.md`, reads:

> Scope note (D7, proposed): where a family's desired value for a closed-vocabulary slot
> (`kinship_label`, `favorite_color`, `favorite_food`, `favorite_hobby`, `pet_species`,
> `home_type`) is missing from the shipped list, G18 extends to a request-and-review path (see
> `docs/planning/personalization-vocab-expansion-spec.md`): the guardian submits a candidate
> value and an admin screens it for denylist collisions and PII before it joins the vocabulary
> any family can select. This creates no new consent surface; it only widens what a slot's
> closed enum may contain.

**Admin side: propose a new row, A17.** No existing admin ID fits. A3 ("Global policy levers:
age-band definitions, theme taxonomy, classifier thresholds, banned-content lists") is the
closest adjacent row, and its Notes column already frames closed-vocabulary lists as a taxonomy
an admin can edit, but A3's mechanism today is unilateral admin editing with no guardian-facing
intake. A1 ("Moderation queue... decisions feed back into automated rules") has the right
*shape* (a reviewed queue with closed-vocabulary reason codes, no free text reaching a child)
but the wrong *domain*: A1 is content moderation of a specific storybook or a reader's flag, not
a request to permanently widen a data taxonomy every family can subsequently select from. A
guardian proposing a taxonomy addition, and an admin deciding whether it becomes available to
every other family, is a distinct authority from either. Proposed row, appended after A16:

| ID | Capability | Docs | Notes |
|----|------------|------|-------|
| A17 | Review and decide guardian-submitted requests to add a value to a closed personalization vocabulary (a kinship label, a favorite color/food/hobby, a pet species, a home type), screening for denylist collisions and PII (no real personal names) before an entry becomes available to any family | (proposed) | Proposed here (D7 spec, 2026-07-29). Extends A3's "theme taxonomy" lever with a guardian-initiated intake path rather than purely admin-unilateral editing; the decision surface reuses A1's flagged-item queue shape (closed reason codes, no free text reaching a child) applied to a different domain, data taxonomy rather than content |

**Not affected.** K20 (the child's own reading and toggle capability) is unchanged: a child
never sees a pending request, a vocabulary list, or this feature's admin surface; they only
eventually read a story that uses a value their guardian set, exactly as today. S10 (privacy
architecture) is touched the same way G18 already touches it, one more small child-linked or
family-linked data category to classify (Section 6, and Task D5's compliance sweep already
covers G18's classification work); no new S11 (social boundary) surface exists, since this
feature has no cross-family flow at all, unlike G18's ring-2 leg.

## 2. Data model

Two new tables, both under the `child_profile_personalization`/`personalization_disclosure_consent`
naming and audit conventions already established in `src/cyo_adventure/db/models.py`. Neither is
built by this spec; the shapes below are the contract an implementation task must satisfy.

### 2.1 `personalization_vocabulary_request`

The ask. One row per guardian submission.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Surrogate key, mirrors `KidFlag`. |
| `family_id` | UUID FK -> `family`, `ON DELETE CASCADE` | Denormalized owning family, indexed; mirrors `KidFlag.family_id` and `StoryRequest.family_id`. |
| `requested_by_user_id` | UUID FK -> `user`, `ON DELETE SET NULL` | The submitting guardian; nullable so a deleted user does not orphan the audit row, mirroring `FamilyConnection.created_by`. |
| `slot_type` | `String(32)`, CHECK IN closed set | The six post-D6 closed-vocabulary slot types: `pet_species`, `kinship_label`, `favorite_color`, `favorite_food`, `favorite_hobby`, `home_type`. Mirrors the `_KID_FLAG_REASON_VALUES`-style named CHECK-string constant pattern. |
| `requested_value` | `Text` | The guardian's candidate value, quarantined (see 2.3). Free text at rest, by construction; never copied into any other table's `value_text`/`value_enum` column. |
| `status` | `String(16)`, CHECK IN `('pending', 'approved', 'rejected')`, `server_default 'pending'` | Mirrors `StoryRequest.status`'s closed-vocabulary CHECK pattern. |
| `decided_by_user_id` | UUID FK -> `user`, `ON DELETE SET NULL`, nullable | The deciding admin; null while pending. |
| `decided_at` | `TIMESTAMPTZ`, nullable | Null while pending. |
| `decision_reason` | `String(32)`, CHECK IN closed set, nullable | Closed reason-code vocabulary (Section 3); null while pending. |
| `created_at` | `TIMESTAMPTZ` (`CreatedAtMixin`) | Submission time. |

A pairing CHECK constraint (mirroring `ck_pdc_consent_pairing` and `KidFlag`'s resolved-pairing
CHECK) enforces `decided_by_user_id`, `decided_at`, and `decision_reason` are all null or all
set together, so the row is never a partial decision. A partial index on `status = 'pending'`
over `(family_id)` backs the per-family pending-cap check (Section 3) and the guardian's own
request-history query; a plain index on `status` backs the admin queue.

### 2.2 `personalization_vocabulary_overlay`

The materialized result. One row per approved value, per slot type. This table, not the request
table, is what a validation call site actually reads.

| Column | Type | Notes |
|---|---|---|
| `slot_type` | `String(32)`, CHECK IN the same closed set, part of composite PK | |
| `value` | `String(64)`, part of composite PK | Matches the width of `ChildProfilePersonalization.value_enum`. Composite `(slot_type, value)` PK prevents a duplicate overlay entry for the same slot and value, the natural-key style `ChildProfilePersonalization` already uses. |
| `added_via_request_id` | UUID FK -> `personalization_vocabulary_request`, `ON DELETE SET NULL` | Audit link only; losing it (request row deleted) does not invalidate the overlay entry, since the entry's presence is what makes a value usable, not the FK. |
| `added_by_user_id` | UUID FK -> `user`, `ON DELETE SET NULL` | The approving admin. |
| `added_at` | `TIMESTAMPTZ` (`CreatedAtMixin`) | |
| `active` | `bool`, `server_default true` | Soft-deactivation switch (Section 7, open question 3). Deactivating a value does not touch any `ChildProfilePersonalization` row already using it; the existing render-time fallback contract (an invalid value at payload-build time is omitted, never an error, per `personalization_value_for_payload`'s documented contract) already handles a value that stops validating after the fact. |

### 2.3 Quarantine, stated explicitly

`requested_value` is quarantined free text. It NEVER enters story prose, a render payload, or
any kid-facing surface, at any point in its lifecycle, including after approval:

- **While pending or rejected**, it exists in exactly two places: the request row itself, and
  the two surfaces that read that row (the submitting guardian's own request-history view of
  their own family's requests, and the admin review queue). No write path connects it to
  `ChildProfilePersonalization.value_text` or `value_enum`; that write path does not accept a
  slot's own pending-request row as an input.
- **On approval**, the request row's `requested_value` is not itself promoted anywhere; the
  admin decision inserts a *separate* `personalization_vocabulary_overlay` row whose `value`
  column happens to carry the same string, re-validated at insert time (Section 3). This
  separation matters: the request row remains a record of what was asked, the overlay row is
  the thing that is actually usable, and the two can diverge if an admin edits the value while
  approving (Section 5, decide endpoint).
- **Never logged.** `personalization_values.py`'s own `enum_membership` rejection message
  (`:264-274`) already documents why: application logs have no erasure path, and a kinship
  term names a real relative. The same reasoning applies here with more force, since a request
  row's whole purpose is to carry a real family term. Pipeline event payloads for this feature
  (Section 5) carry `slot_type` and closed-vocabulary decision codes only, never
  `requested_value`.

## 3. Safety gating

An admin's approval is the sole path from a guardian's proposal to a globally selectable
vocabulary member; there is no automatic or majority-vote path. Two mandatory pre-approval
validations, both re-run server-side at decision time regardless of what the admin UI already
showed the reviewer (the codebase's standing defense-in-depth pattern: personalization values
are checked at write time AND again at payload-build time; this decision endpoint checks at
submission time AND again at decision time):

### 3.1 Denylist non-collision (mandatory, mechanical)

Run `cyo_adventure.validator.slots.denylisted_bundles(requested_value, bundle_ids)` against the
**union of `band_mandatory_bundles(age_band)` for every `AgeBand` member**, not just one band.
`CLOSED_VOCABULARIES` is a single global dict with no per-band variant: an approved value is
immediately selectable by a family with a 3-5 band child and a family with a 16+ band child
alike, so it must clear the strictest floor any band enforces, not the floor of whichever band
happened to be open in the admin's review tab. Any bundle hit rejects outright; there is no
partial-pass state. This is the same lethal/weapon/toxic/capture/graphic/despair floor every
other personalization value clears (`personalization_values.py:33-38`), applied here before a
value can even become eligible, not just before it can be assigned to one child.

Structural checks (`structural_value_violations`, the charset/length/control-character/fence-
marker guard) run as a cheap first-pass filter at **submission** time too, rejecting an
obviously malformed request (an attempted `{SLOT}` forge, a `<<FILL>>` directive, control
characters) before it is ever stored, mirroring the same reuse pattern
`personalization_values.py` already documents for every other personalization value.

### 3.2 PII screening: generic term, never a real person's name (mandatory, human judgment)

ADR-023 row 5 is explicit for kinship labels: "Include, closed enum only. A real adult's
personal name is excluded: a third party who never consented." This spec generalizes that rule
to every closed-vocabulary slot type in scope: a requested value must read as a **category or
relationship term**, not a proper name. "Nonna", "Yiayi", "Auntie Ro" pass (kinship
relationship-and-affection vocabulary, the same register as the shipped "Grandma"/"Abuela"
examples); a specific person's given name ("Susan", "the name of the actual grandmother") does
not, because it identifies a specific, non-consenting third party the moment it is selected by
any family, not only the requesting one.

This screen is **not** fully mechanizable in v1. The codebase has no name-detection classifier
today, and building one is out of this spec's scope (it would be its own feature). The primary
control is a human admin applying a documented rubric at decision time, the same posture ADR-005
already establishes for content moderation: automated gates are a floor, human judgment is the
actual decision. The rubric, to be carried into the admin review UI as inline guidance:

1. Does the term describe a **role or relationship** (kinship label), a **category**
   (favorite/species/home type), rather than naming one specific individual?
2. Would the term read identically if said by any family about their own relative, pet, or
   home, or is it a name unique to one person (a proper noun with no relational meaning)?
3. Is the term free of any other identifying detail (no surname, no location, no age; those
   remain excluded classes under ADR-023's row 9-14 exclusions regardless of this feature)?

A candidate that fails any rubric question is rejected with `rejected_pii_personal_name`
(Section 5). Automated pre-screening (reusing an NER-style classifier as a first-pass flag, not
a hard gate) is a reasonable v2 hardening item once real request volume justifies building it;
see Section 7, open question 4.

### 3.3 Duplicate and synonym collision (mandatory, mechanical assist)

Before insert, normalize the candidate (`storybook`/`validator` conventions: NFC-normalize,
casefold, collapse whitespace, the same `_normalize` used by `denylisted_bundles`) and compare
against both the shipped `CLOSED_VOCABULARIES[slot_type]` set and every other **active**
`personalization_vocabulary_overlay` row for that `slot_type`. An exact normalized match means
the value already exists; the admin resolves with `rejected_duplicate_or_synonym` and the
guardian is told (in the response, not in a queued event) that their term is already available.
A near-miss (a plural, a minor spelling variant) is a human judgment call at decision time, not
a hard block, since the vocabulary is small enough that an admin can eyeball it.

## 4. How an approved value lands: DB-backed overlay, unioned at validation time

`CLOSED_VOCABULARIES` today is a code constant, explicitly gated by a `#VERIFY` marker: "do not
hand-add values here without a design-plan update or an ADR-023 amendment recording the
vocabulary" (`personalization_values.py:98-100`). This feature resolves that tension directly,
because it must: without a resolution, "approve a request" has nowhere to write.

**Recommendation: option (a), a DB-backed overlay table unioned with the code constant at
validation time.** Not option (b), a tracked code change a maintainer ships on the next
deploy.

### Why (a)

- **Precedent already exists in this exact module.** `validate_personalization_value` already
  takes `family_profile_ids`, a collection resolved by the caller (the route/service layer, via
  `authorize_family`) and passed in, specifically so the module itself stays free of database
  access ("Keeping the authorization lookup out of this module is what keeps it importable,
  without a database, from both the write route and the payload builder",
  `personalization_values.py:45-50`). The overlay union follows the identical shape: the
  route/service layer resolves `CLOSED_VOCABULARIES[slot_type] | {active overlay rows for
  slot_type}` and passes the merged set in. `personalization_values.py` itself gains **no new
  import**, no DB dependency, and no change to its "pure module: stdlib + storybook.models +
  validator.slots only" contract. The exact call-site plumbing (a parameter shape on
  `validate_personalization_value`/`personalization_value_for_payload`, or a thin wrapper in the
  caller) is an implementation-task decision, not fixed by this spec, but the constraint is
  fixed: the module's purity does not change.
- **Predictable guardian-facing latency.** An approved value is usable the moment the admin
  approves it, not after the next release. A guardian waiting weeks for a deploy to pick up
  their grandmother's name defeats the point of a self-service request path.
- **Auditability is at least as good, arguably better.** The overlay row's `added_via_request_id`
  and `added_by_user_id` are a direct, queryable link from "this value is usable" to "this is
  who asked and who approved it", which a bare code-constant diff (a git commit, reviewed by
  whoever happened to be the PR reviewer) does not give for free.
- **Serves the guardian-facing "valid options" UI need directly.** The personalization settings
  screen (execution plan Task D2) has to render a closed dropdown of current options for each
  slot; that list has to be fetchable live regardless of this feature. A DB-backed overlay is a
  natural extension of that same fetch; a code-only constant would require shipping a
  synchronized frontend catalog update at the same time as the backend one, doubling the
  coordination cost this feature exists to avoid.

### Tradeoffs, named rather than hidden

- **Two sources of truth for one vocabulary.** The code constant remains the shipped baseline
  (seeded per Task D6 from ADR-023's illustrative examples, reviewed as part of a design-doc or
  ADR change); the DB overlay is the incremental, admin-approved layer on top. Which one is
  authoritative for what must be documented plainly wherever the union is computed: the code
  constant is the reviewed, versioned baseline; the overlay is the fast-moving, admin-approved
  delta. A future large-batch addition (e.g., "the 30 most common kinship terms across active
  languages") belongs back in the code constant via a design-doc update, not accreted one
  overlay row at a time.
- **A real (if small) runtime dependency change.** Membership checks that were previously a pure
  dict lookup, testable with zero fixtures, now depend on a resolved collection the caller must
  fetch. Unit tests of `personalization_values.py` itself are unaffected (they already pass
  `family_profile_ids` as a plain collection); integration tests of the route/service layer gain
  one more DB read per personalization write, which is negligible next to the reads that call
  already does (profile, family, existing rows).
- **Offline client resolution is unaffected, and worth saying so explicitly.** The client-side
  resolver (`frontend/src/player/personalization.ts`, per the execution plan's Task C1) never
  performs vocabulary validation; it only substitutes an already-validated value from a payload
  into a sentinel. Vocabulary membership is checked exclusively server-side, at write time and
  at payload-build time. The overlay table therefore adds nothing to what the client fetches,
  caches, or resolves offline; it only changes what the server accepts as valid input and what
  the server includes when building the "current options" list for the guardian-facing form.

Option (b) was rejected as the primary mechanism because it makes "admin approved" and "value
actually usable" two states that can silently drift out of sync (approved-but-not-yet-deployed
is a confusing state to expose to a guardian, and a natural source of "why isn't my grandma's
name showing up yet" support load), and because it does not serve the settings-screen dropdown
need without a second, separately-shipped artifact. It remains the right mechanism for
*periodic* consolidation, moving a batch of proven-stable overlay entries into the reviewed code
constant on a design-doc cadence, which is a maintenance operation this spec does not need to
design further.

## 5. API surface, events, and frontend touchpoints

### 5.1 Routes

New router, `src/cyo_adventure/api/personalization_vocabulary.py`, wired in `app.py` alongside
the existing `api/personalization.py` and `api/flags.py`, whose shapes it mirrors directly.

| Method + path | Role | Behavior |
|---|---|---|
| `POST /api/v1/vocabulary-expansion-requests` | Guardian | Body: `slot_type`, `requested_value`. Family resolved from the principal (never a caller-supplied `family_id`, mirroring `flags.py`'s ownership-scoping discipline). Runs the submission-time structural check (3.1) and the per-family pending-request cap (Section 6) before insert. Returns 201 with the new request's id and `status: "pending"`. |
| `GET /api/v1/families/me/vocabulary-expansion-requests` | Guardian | Lists the caller's own family's requests, every status, newest first. This is the only guardian-facing surface that ever echoes `requested_value` back, and only the requester's own. |
| `GET /api/v1/admin/vocabulary-expansion-requests` | Admin | The queue. Filters by `status` (default `pending`), newest first, mirrors `GET /admin/flags` exactly, including the `is_admin` gate checked before any row loads. |
| `POST /api/v1/admin/vocabulary-expansion-requests/{id}/decide` | Admin | Body: `decision` (`approved`/`rejected`), `decision_reason` (closed code, Section 5.2), and for `approved` only, an optional `value_override` (the admin may correct capitalization or trivial spelling before it becomes the overlay's canonical `value`). Re-runs 3.1 and 3.3 server-side unconditionally; `approved` inserts the `personalization_vocabulary_overlay` row and flips `status`/`decided_by_user_id`/`decided_at`/`decision_reason` together in one transaction, mirroring `resolve_flag`'s set-together pattern. |
| `GET /api/v1/personalization/vocabularies` | Any authenticated principal | Returns the current merged (code constant union active overlay) vocabulary per `slot_type`, for rendering the closed dropdown and for the request form's own "is my value already available" pre-check. Read-only, no PII (values only, no request provenance). |

### 5.2 Closed decision-reason vocabulary

Mirrors `KidFlagResolutionLiteral`'s no-free-text discipline exactly: `decision_reason` is a
closed set, not a free-text admin note, because it is the field a guardian eventually sees on
their own request-history view (Section 5.1's `GET .../vocabulary-expansion-requests`), and this
codebase's standing rule (ADR-016) is no free text crossing that kind of boundary.

`approved`, `rejected_denylist_collision`, `rejected_pii_personal_name`,
`rejected_duplicate_or_synonym`, `rejected_inappropriate`, `rejected_other`.

### 5.3 Pipeline events

Two new `EventType` values, following the `PERSONALIZATION_TOGGLED`/`RING2_CONSENT_GRANTED`
precedent in `src/cyo_adventure/events/models.py` and its payload-allowlist discipline in
`src/cyo_adventure/events/writer.py`:

- `VOCABULARY_EXPANSION_REQUESTED = "vocabulary_expansion_requested"`. Payload allowlist:
  `{"slot_type"}` only, mirroring `KID_FLAGGED`'s no-free-text payload. `requested_value` never
  appears in a pipeline event, for the same erasure-path reasoning as Section 2.3.
- `VOCABULARY_EXPANSION_DECIDED = "vocabulary_expansion_decided"`. Payload allowlist:
  `{"slot_type", "decision_reason"}`. Both are closed-vocabulary values (Section 3's `slot_type`
  set, Section 5.2's reason set), never free text, so this is safe under the same allowlist
  discipline every other event type in this module follows.

### 5.4 Frontend touchpoints

- **Guardian personalization settings form** (execution plan Task D2, `frontend/src/guardian/`):
  each closed-vocabulary slot's dropdown gains a "Don't see it? Ask us to add it" affordance
  that opens a small inline form (slot type pre-filled from context, one text input for the
  candidate value), submitting to 5.1's `POST` route. The same screen (or a linked "My
  requests" panel) shows the guardian's own pending/approved/rejected history via the `GET
  .../vocabulary-expansion-requests` route, so a guardian is never left wondering whether their
  request went anywhere.
- **Admin console**: a new page, most naturally a tab alongside the existing moderation surfaces
  (`frontend/src/admin/`, following the `ModerationDashboardPage.tsx`/`AdminRequestsPage.tsx`
  pattern rather than a wholly new shell section), listing pending requests with `slot_type`,
  `requested_value`, the requesting family's identifier, and submission date, with
  Approve/Reject actions backed by the closed `decision_reason` picker from 5.2 and the
  rubric text from Section 3.2 shown inline as reviewer guidance.

## 6. Non-goals

- **No free-text passthrough, ever.** A closed-vocabulary slot's write shape never changes: it
  is `value_enum` before this feature and after it (`_shape_violations`'s existing "this slot
  has a closed vocabulary and must use value_enum" rule is untouched). This feature only widens
  what may appear as a member of that enum; it never lets a guardian write arbitrary text
  directly into a `ChildProfilePersonalization` row.
- **No per-family private vocabularies in v1.** An approved value is global: every family sees
  and may select it, indistinguishable from a value that shipped in Task D6.
  **Privacy consideration, addressed rather than ignored**: a sufficiently distinctive family
  term (an invented pet-name-shaped kinship word, say) becoming a globally visible dropdown
  option could theoretically let an attentive third party infer that *some* family requested it,
  if they already suspected which family. This spec's mitigation is that **provenance stays
  strictly admin-only**: `added_via_request_id` and `added_by_user_id` never appear on any
  guardian- or kid-facing response (5.1's `GET .../personalization/vocabularies` returns values
  only), so the realistic exposure is "this term now exists as an option for every family," not
  "family X uses this term." Given that bound, true per-family private vocabularies are deferred
  rather than built now: they would reintroduce per-family variance into a contract every other
  part of this feature (the DB CHECK constraints, the offline client bundle assumptions, the
  settings-screen dropdown) currently treats as globally uniform, and no evidence yet exists
  that the residual risk above justifies that redesign. Revisit if real usage surfaces a
  concrete case where global visibility is unacceptable to a requesting family.
- **No automated PII/name detection in v1** (Section 3.2); human review is the primary and only
  control at launch.
- **No change to consent, ring scoping, or revocation.** This feature is entirely upstream of
  G18's existing toggle/consent machinery: it only ever changes what a closed enum may contain.

## 7. Open questions for the owner

1. **Request scope: family-level or profile-level?** Recommendation: **family-level**. A
   vocabulary term (a kinship label, a home type) is not really about one child; it is shared
   across siblings the same way the vocabulary itself is shared across families. Scoping the
   request to the family, resolved from the principal the same way `authorize_family` already
   works elsewhere, avoids an unnecessary profile-selection step in the request form.
2. **Per-family pending-request cap?** Recommendation: **yes**, a small cap (suggest 5 pending
   requests per family, across all slot types combined), mirroring the existing abuse-throttle
   precedent (`MAX_OPEN_FLAGS_PER_PROFILE`, `story_requests/service.py`'s pending-request cap).
   This is an abuse throttle, not a correctness invariant, and can accept the same benign
   race-condition posture those two precedents already accept.
3. **Should an approved value be revocable later?** Recommendation: **yes**, via the overlay
   table's `active` flag (Section 2.2), with no new mechanism needed beyond what already exists:
   deactivating an overlay row means any `ChildProfilePersonalization` row already using that
   value silently falls back to the generic default at next render, exactly matching
   `personalization_value_for_payload`'s documented render-time fallback contract. No
   retroactive story-content change and no error surfaced to a family mid-read.
4. **Automated PII pre-screening: build now or defer?** Recommendation: **defer**. No
   name-detection classifier exists in this codebase today; building one is its own feature with
   its own false-positive/false-negative tradeoffs, and Section 3.2's human rubric is the correct
   floor until real request volume (post-launch) demonstrates the manual review does not scale.
5. **Uniform across all six slot types, or a narrower launch subset?** Recommendation:
   **uniform**. The mechanism (request, denylist check, PII rubric, duplicate check, overlay
   insert) is identical regardless of which closed-vocabulary slot it targets; restricting it to
   a subset (e.g., kinship label and pet species only, deferring the three favorite slots and
   home type) would need its own justification, and none is apparent. Simpler to launch uniform
   and narrow later if a specific slot type proves to attract low-quality requests.

## 8. Dependency

Blocked on **Task D6** (seed the accepted vocabularies from ADR-023 rows 4a/5/6/7, including
splitting `favorite` into `favorite_color`/`favorite_food`/`favorite_hobby`), which is not yet
on `origin/main` as of this spec's writing. D6, and the five-key `CLOSED_VOCABULARIES` dict that
includes a `dedication` entry alongside it, currently exist only on draft PR #489
(`docs/planning/personalization-closed-vocabularies-proposal.md`, unmerged). This feature (D7)
cannot land its data model or routes against a vocabulary that is still all-empty frozensets;
implementation work on this spec should not start until draft PR #489 merges and D6 is verified
present on `origin/main`.

## Related

- [ADR-023](./adr/adr-023-story-personalization-slots.md), the decision record this feature
  extends (rows 4a, 5, 6, 7; the "never free text" closed-vocabulary decision).
- [Story personalization execution plan](./story-personalization-execution-plan.md), Tasks D6
  (dependency) and D7 (this feature's task slot).
- [Story personalization implementation plan](./story-personalization-implementation-plan.md),
  the design-plan authority the execution plan compresses.
- [Capability register](./capability-register.md), G18 (extended) and the proposed A17 row.
